"""Department mandate of a Team and opportunity detection from granted sources (0.208.0).

Design: docs/superpowers/specs/2026-10-17-team-duyet-muc-tieu-nghiem-thu-design.md, part 2.

A team can carry ONE mandate, set only by the owner (HTTP routes in team_api, never a JAVIS_TEAM directive):

    outcome        what the department is for ("Giữ trang bán hàng chạy và đúng giá")
    metrics        how the owner judges it (lines of text, shown to members)
    sources        what the team may watch, each a granted reference:
                     folder:<path inside the brain>   files (mtime, size) of that folder
                     kanban                            failed or blocked Kanban jobs of the brain
                     mcp:<connection id>               health of one connection (missing = shown, never invented)
                     test:<check command>              exit code of a command the OWNER wrote (run_command at `auto`:
                                                      it can run code such as pytest; a timeout counts as failing)
    scope          the boundary of what the team may take on
    budget         observations per day, jobs the mandate may open per day
    cadence_min    how often the sources are observed
    autonomy       per opportunity kind: `act` (open the job), `approve` (open it waiting for the owner's approval card),
                   `propose` (a card in the chat, the owner decides), anything else is only watched
    stop           {"max_open_jobs": N}: above it nothing new is opened, only proposed

Status: off (no row or switched off) | active | paused | revoked. An existing team has no mandate, so nothing changes for
it until the owner writes one. Every edit is a new version (history kept); revoking cancels the mandate's jobs that have
not started and closes its open opportunities and requests.

Observation is code only (no model): each granted source is read, the observation is stored with its version key, and
a change from the previous observation of the same source becomes an opportunity carrying the source, the reference,
the data version, the reason tied to the outcome and the expected benefit. A source that cannot be read is recorded as
missing and shown; no opportunity is made up for it. Opportunities are deduplicated by (team, source, ref, version), a
rejected one never reopens until the data version changes, each (source, ref) has a cooldown, and an opportunity left
open expires. The decision none | watch | propose | ask | enqueue follows the autonomy table, the budget and the stop
rule; a job the mandate opens carries the trace mandate@version -> observation -> opportunity in its source reference
and intent, and its approval (if any) goes through the 0.207.0 gate like any other.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Callable, Optional

STATUSES = ("off", "active", "paused", "revoked")
SOURCE_TYPES = ("folder", "kanban", "mcp", "test")
KINDS = ("file_changed", "job_failed", "test_failing", "connection_down")
DECISIONS = ("none", "watch", "propose", "ask", "enqueue")
OPEN_OPP = ("open", "proposed")
DEFAULT_BUDGET = {"observe_per_day": 48, "jobs_per_day": 3}
DEFAULT_CADENCE_MIN = 60
DEFAULT_COOLDOWN_MIN = 60
DEFAULT_EXPIRE_H = 48
FOLDER_MAX_FILES = 300
TEXT_MAX = 2000

KIND_LABEL = {"file_changed": "tài liệu trong thư mục được giao thay đổi",
              "job_failed": "việc Kanban của bộ não bị lỗi hay bị chặn",
              "test_failing": "lệnh kiểm tra đang báo lỗi",
              "connection_down": "kết nối được giao đang lỗi"}
KIND_BENEFIT = {"file_changed": "cập nhật kịp theo dữ liệu mới",
                "job_failed": "gỡ việc đang kẹt trước khi ảnh hưởng tiếp",
                "test_failing": "sửa lỗi trước khi tới tay khách",
                "connection_down": "khôi phục nguồn dữ liệu của nhóm"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS team_mandates(
  team_id TEXT PRIMARY KEY, version INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'off',
  outcome TEXT NOT NULL DEFAULT '', metrics_json TEXT NOT NULL DEFAULT '[]', sources_json TEXT NOT NULL DEFAULT '[]',
  scope TEXT NOT NULL DEFAULT '', budget_json TEXT NOT NULL DEFAULT '{}', cadence_min INTEGER NOT NULL DEFAULT 60,
  autonomy_json TEXT NOT NULL DEFAULT '{}', stop_json TEXT NOT NULL DEFAULT '{}', updated_by TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL, updated_at REAL NOT NULL, last_observed_at REAL);
CREATE TABLE IF NOT EXISTS team_mandate_versions(
  team_id TEXT NOT NULL, version INTEGER NOT NULL, snapshot_json TEXT NOT NULL, by TEXT NOT NULL DEFAULT '',
  at REAL NOT NULL, PRIMARY KEY(team_id, version));
CREATE TABLE IF NOT EXISTS team_mandate_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, team_id TEXT NOT NULL, kind TEXT NOT NULL, by TEXT NOT NULL DEFAULT '',
  detail_json TEXT NOT NULL DEFAULT '{}', at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS team_mandate_events_team ON team_mandate_events(team_id, id);
CREATE TABLE IF NOT EXISTS mandate_observations(
  id INTEGER PRIMARY KEY AUTOINCREMENT, team_id TEXT NOT NULL, mandate_version INTEGER NOT NULL, source TEXT NOT NULL,
  ref TEXT NOT NULL, version_key TEXT NOT NULL, ok INTEGER NOT NULL, summary_json TEXT NOT NULL DEFAULT '{}',
  observed_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS mandate_observations_src ON mandate_observations(team_id, source, ref, id);
CREATE INDEX IF NOT EXISTS mandate_observations_day ON mandate_observations(team_id, observed_at);
CREATE TABLE IF NOT EXISTS mandate_opportunities(
  opp_id TEXT PRIMARY KEY, team_id TEXT NOT NULL, mandate_version INTEGER NOT NULL, source TEXT NOT NULL,
  ref TEXT NOT NULL, version_key TEXT NOT NULL, kind TEXT NOT NULL, reason TEXT NOT NULL, benefit TEXT NOT NULL,
  evidence_json TEXT NOT NULL DEFAULT '[]', observation_id INTEGER, decision TEXT NOT NULL DEFAULT 'none',
  status TEXT NOT NULL DEFAULT 'open', task_id TEXT, approval_id TEXT, message_id INTEGER,
  created_at REAL NOT NULL, updated_at REAL NOT NULL, expires_at REAL NOT NULL, decided_by TEXT NOT NULL DEFAULT '',
  UNIQUE(team_id, source, ref, version_key));
CREATE INDEX IF NOT EXISTS mandate_opps_team ON mandate_opportunities(team_id, status, created_at);
"""


def _j(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def _clip(v: Any, n: int = TEXT_MAX) -> str:
    return str(v or "").strip()[:n]


class MandateError(ValueError):
    pass


# One lock per team for everything that changes what a mandate may do (status, revoke) and everything that acts on it
# (opening a job, an owner's accept). Review 0.208.0: a revoke during a long observation must stop what follows.
_TEAM_LOCKS: dict = {}
_TEAM_LOCKS_GUARD = threading.Lock()


def team_lock(team_id: str) -> threading.RLock:
    with _TEAM_LOCKS_GUARD:
        lk = _TEAM_LOCKS.get(team_id)
        if lk is None:
            lk = _TEAM_LOCKS[team_id] = threading.RLock()
        return lk


def parse_source(raw: Any) -> Optional[dict]:
    """`folder:<rel>`, `kanban`, `mcp:<id>`, `test:<cmd>` -> {"type", "ref", "raw"}; None when not a granted source."""
    s = str(raw or "").strip()
    if not s:
        return None
    typ, _, ref = s.partition(":")
    typ = typ.strip().lower()
    ref = ref.strip()
    if typ not in SOURCE_TYPES:
        return None
    if typ == "kanban":
        return {"type": "kanban", "ref": "kanban", "raw": "kanban"}
    if not ref:
        return None
    if typ == "folder":
        p = Path(ref)
        if p.is_absolute() or ".." in p.parts:
            return None
    return {"type": typ, "ref": ref[:400], "raw": f"{typ}:{ref[:400]}"}


def clean(body: dict) -> dict:
    """Validate an owner's mandate. Raises MandateError with a reason a person can act on."""
    outcome = _clip(body.get("outcome"), 1000)
    if not outcome:
        raise MandateError("thiếu mục tiêu (outcome)")
    metrics = [_clip(m, 300) for m in (body.get("metrics") or []) if str(m or "").strip()][:12]
    sources, bad = [], []
    for raw in (body.get("sources") or [])[:20]:
        got = parse_source(raw)
        if got is None:
            bad.append(str(raw)[:80])
        elif got["raw"] not in [x["raw"] for x in sources]:
            sources.append(got)
    if bad:
        raise MandateError("nguồn không hợp lệ: " + ", ".join(bad))
    if not sources:
        raise MandateError("cần ít nhất một nguồn được giao")
    budget = dict(DEFAULT_BUDGET)
    for k in DEFAULT_BUDGET:
        if k in (body.get("budget") or {}):
            try:
                budget[k] = max(0, min(1000, int(body["budget"][k])))
            except (TypeError, ValueError):
                raise MandateError(f"ngân sách {k} phải là số")
    try:
        cadence = max(5, min(7 * 24 * 60, int(body.get("cadence_min") or DEFAULT_CADENCE_MIN)))
    except (TypeError, ValueError):
        raise MandateError("chu kỳ quan sát phải là số phút")
    auto = body.get("autonomy") or {}
    autonomy = {}
    for lvl in ("act", "approve", "propose"):
        autonomy[lvl] = [k for k in (auto.get(lvl) or []) if k in KINDS]
    seen = set()
    for lvl in ("act", "approve", "propose"):   # a kind sits at one level only, the strictest wins below
        autonomy[lvl] = [k for k in autonomy[lvl] if not (k in seen or seen.add(k))]
    stop = {}
    if (body.get("stop") or {}).get("max_open_jobs") not in (None, ""):
        try:
            stop["max_open_jobs"] = max(0, int(body["stop"]["max_open_jobs"]))
        except (TypeError, ValueError):
            raise MandateError("giới hạn việc mở phải là số")
    return {"outcome": outcome, "metrics": metrics, "sources": [s["raw"] for s in sources],
            "scope": _clip(body.get("scope"), 1000), "budget": budget, "cadence_min": cadence,
            "autonomy": autonomy, "stop": stop}


class MandateStore:
    def __init__(self, path: Path, clock: Callable[[], float] = time.time):
        self.path = Path(path)
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._conn()) as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        return c

    class _Tx:
        def __init__(self, store):
            self.c = store._conn()

        def __enter__(self):
            self.c.execute("BEGIN IMMEDIATE")
            return self.c

        def __exit__(self, et, ev, tb):
            try:
                self.c.execute("ROLLBACK" if et else "COMMIT")
            finally:
                self.c.close()

    @staticmethod
    def _m(r) -> Optional[dict]:
        if r is None:
            return None
        d = dict(r)
        for k in ("metrics", "sources", "budget", "autonomy", "stop"):
            d[k] = json.loads(d.pop(k + "_json") or ("[]" if k in ("metrics", "sources") else "{}"))
        return d

    def _event(self, c, team_id: str, kind: str, by: str, detail: Optional[dict] = None) -> None:
        c.execute("INSERT INTO team_mandate_events(team_id, kind, by, detail_json, at) VALUES(?,?,?,?,?)",
                  (team_id, kind, by, _j(detail or {}), self.clock()))

    def get(self, team_id: str) -> Optional[dict]:
        with closing(self._conn()) as c:
            return self._m(c.execute("SELECT * FROM team_mandates WHERE team_id=?", (team_id,)).fetchone())

    def active(self) -> list:
        with closing(self._conn()) as c:
            return [self._m(r) for r in c.execute("SELECT * FROM team_mandates WHERE status='active'").fetchall()]

    def put(self, team_id: str, body: dict, by: str = "owner", status: Optional[str] = None) -> dict:
        """Create or edit (a new version). A new mandate starts `off` unless `status` says otherwise."""
        m = clean(body)
        if status not in (None, "off", "active", "paused"):
            raise MandateError("sửa mục tiêu chỉ đặt được trạng thái tắt, bật hay tạm dừng; thu hồi dùng nút Thu hồi")
        now = self.clock()
        with team_lock(team_id), self._Tx(self) as c:
            old = c.execute("SELECT version, status, created_at FROM team_mandates WHERE team_id=?",
                            (team_id,)).fetchone()
            ver = (int(old["version"]) + 1) if old else 1
            st = status or (old["status"] if old and old["status"] != "revoked" else "off")
            if st not in STATUSES:
                raise MandateError("trạng thái không hợp lệ")
            c.execute("INSERT OR REPLACE INTO team_mandates(team_id, version, status, outcome, metrics_json, sources_json,"
                      " scope, budget_json, cadence_min, autonomy_json, stop_json, updated_by, created_at, updated_at,"
                      " last_observed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)",
                      (team_id, ver, st, m["outcome"], _j(m["metrics"]), _j(m["sources"]), m["scope"], _j(m["budget"]),
                       m["cadence_min"], _j(m["autonomy"]), _j(m["stop"]), by, old["created_at"] if old else now, now))
            c.execute("INSERT INTO team_mandate_versions(team_id, version, snapshot_json, by, at) VALUES(?,?,?,?,?)",
                      (team_id, ver, _j(dict(m, status=st)), by, now))
            self._event(c, team_id, "edited" if old else "created", by, {"version": ver, "status": st})
        return self.get(team_id)

    def set_status(self, team_id: str, status: str, by: str = "owner") -> Optional[dict]:
        if status not in STATUSES:
            raise MandateError("trạng thái không hợp lệ")
        with team_lock(team_id), self._Tx(self) as c:
            r = c.execute("SELECT status FROM team_mandates WHERE team_id=?", (team_id,)).fetchone()
            if r is None:
                raise MandateError("nhóm chưa có mục tiêu")
            if r["status"] == "revoked":
                raise MandateError("mục tiêu đã thu hồi; viết lại mục tiêu mới để dùng tiếp")
            c.execute("UPDATE team_mandates SET status=?, updated_at=? WHERE team_id=?", (status, self.clock(), team_id))
            self._event(c, team_id, "status", by, {"from": r["status"], "to": status})
        return self.get(team_id)

    def versions(self, team_id: str) -> list:
        with closing(self._conn()) as c:
            return [dict(r, snapshot=json.loads(r["snapshot_json"])) for r in c.execute(
                "SELECT team_id, version, snapshot_json, by, at FROM team_mandate_versions WHERE team_id=? "
                "ORDER BY version", (team_id,)).fetchall()]

    def events(self, team_id: str) -> list:
        with closing(self._conn()) as c:
            return [dict(r, detail=json.loads(r["detail_json"])) for r in c.execute(
                "SELECT * FROM team_mandate_events WHERE team_id=? ORDER BY id", (team_id,)).fetchall()]

    def mark_observed(self, team_id: str, at: float) -> None:
        with self._Tx(self) as c:
            c.execute("UPDATE team_mandates SET last_observed_at=? WHERE team_id=?", (at, team_id))

    # ---- observations ----
    def last_observation(self, team_id: str, source: str, ref: str) -> Optional[dict]:
        """The baseline for the next comparison: the last observation whose change was not held back by a cooldown
        (review 0.208.0: a change seen during the cooldown must still come out once the cooldown is over)."""
        with closing(self._conn()) as c:
            r = c.execute("SELECT * FROM mandate_observations WHERE team_id=? AND source=? AND ref=? AND "
                          "json_extract(summary_json, '$.suppressed') IS NULL ORDER BY id DESC LIMIT 1",
                          (team_id, source, ref)).fetchone()
            return dict(r, summary=json.loads(r["summary_json"])) if r else None

    def observation(self, obs_id: int) -> Optional[dict]:
        with closing(self._conn()) as c:
            r = c.execute("SELECT * FROM mandate_observations WHERE id=?", (int(obs_id or 0),)).fetchone()
            return dict(r, summary=json.loads(r["summary_json"])) if r else None

    def suppress_observation(self, obs_id: int) -> None:
        with self._Tx(self) as c:
            r = c.execute("SELECT summary_json FROM mandate_observations WHERE id=?", (int(obs_id),)).fetchone()
            if r is not None:
                d = json.loads(r["summary_json"] or "{}")
                d["suppressed"] = True
                c.execute("UPDATE mandate_observations SET summary_json=? WHERE id=?", (_j(d), int(obs_id)))

    def add_observation(self, team_id: str, version: int, source: str, ref: str, version_key: str, ok: bool,
                        summary: dict, at: float) -> int:
        with self._Tx(self) as c:
            cur = c.execute("INSERT INTO mandate_observations(team_id, mandate_version, source, ref, version_key, ok, "
                            "summary_json, observed_at) VALUES(?,?,?,?,?,?,?,?)",
                            (team_id, int(version), source, ref, version_key, 1 if ok else 0, _j(summary), at))
            return int(cur.lastrowid)

    def observations(self, team_id: str, limit: int = 50) -> list:
        with closing(self._conn()) as c:
            return [dict(r, summary=json.loads(r["summary_json"])) for r in c.execute(
                "SELECT * FROM mandate_observations WHERE team_id=? ORDER BY id DESC LIMIT ?",
                (team_id, int(limit))).fetchall()]

    def observations_since(self, team_id: str, since: float) -> int:
        with closing(self._conn()) as c:
            return int(c.execute("SELECT COUNT(DISTINCT observed_at) FROM mandate_observations WHERE team_id=? AND "
                                 "observed_at>=?", (team_id, since)).fetchone()[0])

    # ---- opportunities ----
    @staticmethod
    def _o(r) -> Optional[dict]:
        if r is None:
            return None
        d = dict(r)
        d["evidence"] = json.loads(d.pop("evidence_json") or "[]")
        return d

    def opportunity(self, opp_id: str) -> Optional[dict]:
        with closing(self._conn()) as c:
            return self._o(c.execute("SELECT * FROM mandate_opportunities WHERE opp_id=?", (opp_id,)).fetchone())

    def opportunities(self, team_id: str, statuses: Optional[tuple] = None, limit: int = 50) -> list:
        q, args = "SELECT * FROM mandate_opportunities WHERE team_id=?", [team_id]
        if statuses:
            q += f" AND status IN ({','.join('?' * len(statuses))})"
            args += list(statuses)
        q += " ORDER BY created_at DESC LIMIT ?"
        args.append(int(limit))
        with closing(self._conn()) as c:
            return [self._o(r) for r in c.execute(q, args).fetchall()]

    def add_opportunity(self, *, team_id: str, version: int, source: str, ref: str, version_key: str, kind: str,
                        reason: str, benefit: str, evidence: list, observation_id: int, at: float, expire_h: float,
                        cooldown_min: float) -> Any:
        """A new opportunity, or the reason there is none: "dup" (same data version already seen, rejected ones
        included) or "cooldown" (the source is still resting after its last opportunity)."""
        with self._Tx(self) as c:
            if c.execute("SELECT 1 FROM mandate_opportunities WHERE team_id=? AND source=? AND ref=? AND version_key=?",
                         (team_id, source, ref, version_key)).fetchone():
                return "dup"
            last = c.execute("SELECT created_at FROM mandate_opportunities WHERE team_id=? AND source=? AND ref=? "
                             "ORDER BY created_at DESC LIMIT 1", (team_id, source, ref)).fetchone()
            if last is not None and at - float(last["created_at"]) < cooldown_min * 60:
                return "cooldown"
            oid = "op_" + secrets.token_hex(8)
            c.execute("INSERT INTO mandate_opportunities(opp_id, team_id, mandate_version, source, ref, version_key, kind,"
                      " reason, benefit, evidence_json, observation_id, created_at, updated_at, expires_at) "
                      "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (oid, team_id, int(version), source, ref, version_key, kind, _clip(reason, 600),
                       _clip(benefit, 300), _j(list(evidence)[:10]), observation_id, at, at, at + expire_h * 3600))
            self._event(c, team_id, "opportunity", "host", {"opp_id": oid, "source": source, "ref": ref,
                                                             "version_key": version_key, "kind": kind})
            return self._o(c.execute("SELECT * FROM mandate_opportunities WHERE opp_id=?", (oid,)).fetchone())

    def update_opportunity(self, opp_id: str, *, expect: Optional[tuple] = None, **fields) -> bool:
        allowed = {"decision", "status", "task_id", "approval_id", "message_id", "decided_by"}
        if set(fields) - allowed:
            raise MandateError("trường không đổi được")
        with self._Tx(self) as c:
            q = "UPDATE mandate_opportunities SET " + ", ".join(f"{k}=?" for k in fields) + ", updated_at=? WHERE opp_id=?"
            args = list(fields.values()) + [self.clock(), opp_id]
            if expect:
                q += f" AND status IN ({','.join('?' * len(expect))})"
                args += list(expect)
            n = c.execute(q, args).rowcount
            if n and "status" in fields:
                r = c.execute("SELECT team_id FROM mandate_opportunities WHERE opp_id=?", (opp_id,)).fetchone()
                self._event(c, r["team_id"], "opportunity_" + str(fields["status"]), fields.get("decided_by") or "host",
                            {"opp_id": opp_id})
            return n == 1

    def jobs_opened_since(self, team_id: str, since: float) -> int:
        with closing(self._conn()) as c:
            return int(c.execute("SELECT COUNT(*) FROM mandate_opportunities WHERE team_id=? AND task_id IS NOT NULL "
                                 "AND decided_by='mandate' AND updated_at>=?", (team_id, since)).fetchone()[0])

    def expire_due(self, at: float) -> list:
        with self._Tx(self) as c:
            rows = c.execute("SELECT * FROM mandate_opportunities WHERE status IN ('open','proposed','accepting') "
                             "AND expires_at<?",
                             (at,)).fetchall()
            for r in rows:
                c.execute("UPDATE mandate_opportunities SET status='expired', updated_at=? WHERE opp_id=?",
                          (at, r["opp_id"]))
                self._event(c, r["team_id"], "opportunity_expired", "host", {"opp_id": r["opp_id"]})
            return [self._o(r) for r in rows]


# ───────────── observers (code only) ─────────────

def folder_listing(root: Path, rel: str, limit: int = FOLDER_MAX_FILES) -> Optional[dict]:
    """{path: [size, int(mtime)]} of the files under `root/rel`, or None when the folder is not there."""
    base = (Path(root) / rel).resolve()
    try:
        base.relative_to(Path(root).resolve())
    except ValueError:
        return None
    if not base.is_dir():
        return None
    out = {}
    for dp, dns, fns in os.walk(base):
        dns[:] = sorted(d for d in dns if not d.startswith("."))
        for fn in sorted(fns):
            if fn.startswith("."):
                continue
            p = Path(dp) / fn
            if p.is_symlink():
                continue   # never read through a link that may point outside the brain (review 0.208.0)
            try:
                st = p.lstat()
            except OSError:
                continue
            out[str(p.relative_to(base)).replace(os.sep, "/")] = [int(st.st_size), int(st.st_mtime)]
            if len(out) >= limit:
                out["__truncated__"] = [limit, 0]
                return out
    return out


class _NullLock:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _hash(v: Any) -> str:
    return hashlib.sha256(_j(v).encode("utf-8")).hexdigest()[:24]


class MandateEngine:
    """One observation pass per due mandate (`tick`), and the owner's decisions on proposals. `deps`:

        brain_root(team) -> Path          folder sources resolve inside the team's brain
        kanban_failures(brain, since) -> [{"ref", "title", "error", "at"}]
        mcp_status(conn_id) -> {"known": bool, "ok": bool, "label": str, "error": str}
        run_test(command, cwd) -> {"ran": bool, "exit": int, "output": str, "error": str}
        open_job(team, title, intent, source_ref) -> (task_id, created)
        clock() -> float
    The TeamRunner gives posting, approvals and blocking (0.207.0 gate)."""

    def __init__(self, store: MandateStore, runner: Any, deps: Any, cooldown_min: float = DEFAULT_COOLDOWN_MIN,
                 expire_h: float = DEFAULT_EXPIRE_H):
        self.store, self.runner, self.deps = store, runner, deps
        self.cooldown_min, self.expire_h = cooldown_min, expire_h

    def _now(self) -> float:
        return float(self.deps.clock())

    @staticmethod
    def _day_start(now: float) -> float:
        lt = time.localtime(now)
        return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))

    def due(self, m: dict, now: float) -> bool:
        if m["status"] != "active":
            return False
        last = m.get("last_observed_at")
        if last is not None and now - float(last) < int(m["cadence_min"]) * 60:
            return False
        cap = int((m.get("budget") or {}).get("observe_per_day", DEFAULT_BUDGET["observe_per_day"]))
        return self.store.observations_since(m["team_id"], self._day_start(now)) < cap

    def tick(self) -> list:
        """Observe every due mandate once and act on what changed. Returns a list of what happened (for logs/tests)."""
        now = self._now()
        done = []
        for o in self.store.expire_due(now):
            self._refresh_card(o["team_id"], o["opp_id"])
        for m in self.store.active():
            try:
                team = self.runner.teams.get(m["team_id"])
                if not team or team.get("status") != "active" or not self.due(m, now):
                    continue
                self.store.mark_observed(m["team_id"], now)
                for raw in m["sources"]:
                    src = parse_source(raw)
                    if src is None:
                        continue
                    for ev in self._observe(team, m, src, now):
                        done.append(self._act(team, m, ev, now))
            except Exception as ex:  # noqa: BLE001 - one broken mandate must not stop the others
                import sys
                print(f"[team mandate] {m.get('team_id')}: {type(ex).__name__}: {ex}", file=sys.stderr)
        return [d for d in done if d]

    def _still(self, m: dict) -> Optional[dict]:
        """The mandate as it is NOW, only if still active and the same version (call under team_lock)."""
        cur = self.store.get(m["team_id"])
        if not cur or cur["status"] != "active" or int(cur["version"]) != int(m["version"]):
            return None
        return cur

    # ---- observe ----
    def _observe(self, team: dict, m: dict, src: dict, now: float) -> list:
        """Store one observation per reference of the source; return the changes worth an opportunity."""
        tid, ver = team["team_id"], int(m["version"])
        typ, ref = src["type"], src["ref"]
        out = []
        if typ == "folder":
            listing = folder_listing(self.deps.brain_root(team), ref)
            if listing is None:
                self.store.add_observation(tid, ver, typ, ref, "missing", False,
                                           {"missing": f"không có thư mục '{ref}' trong bộ não"}, now)
                return []
            key = _hash(listing)
            prev = self.store.last_observation(tid, typ, ref)
            trunc = listing.pop("__truncated__", None) is not None
            oid = self.store.add_observation(tid, ver, typ, ref, key, True, {"files": len(listing), "listing": listing,
                                                                              "truncated": trunc},
                                             now)
            if prev is None or not prev["ok"]:
                return []   # first sight of a folder is the baseline, not news
            if prev["version_key"] != key:
                old = (prev.get("summary") or {}).get("listing") or {}
                changed = sorted(p for p in set(listing) | set(old) if listing.get(p) != old.get(p))
                out.append({"source": typ, "ref": ref, "version_key": key, "kind": "file_changed", "obs": oid,
                            "evidence": [f"{ref}/{p}" + ("" if p in listing else " (đã xoá)") for p in changed[:10]],
                            "detail": f"{len(changed)} tệp trong '{ref}' thay đổi"})
            return out
        if typ == "kanban":
            last = self.store.last_observation(tid, typ, ref)
            since = float(last["observed_at"]) if last else now - 24 * 3600
            items = self.deps.kanban_failures(team["brain_id"], since) or []
            oid = self.store.add_observation(tid, ver, typ, ref, _hash([(i["ref"], i.get("at")) for i in items]), True,
                                             {"failed": len(items)}, now)
            for i in items[:20]:
                out.append({"source": typ, "ref": str(i["ref"]), "version_key": str(i.get("at") or ""),
                            "kind": "job_failed", "obs": oid, "evidence": [f"kanban:{i['ref']} {i.get('error') or ''}"[:300]],
                            "detail": f"việc \"{_clip(i.get('title'), 120)}\" đang lỗi: {_clip(i.get('error'), 200)}"})
            return out
        if typ == "mcp":
            st = self.deps.mcp_status(ref) or {}
            if not st.get("known"):
                self.store.add_observation(tid, ver, typ, ref, "missing", False,
                                           {"missing": f"chưa có kết nối '{ref}'"}, now)
                return []
            key = "ok" if st.get("ok") else "down:" + _clip(st.get("error"), 80)
            prev = self.store.last_observation(tid, typ, ref)
            oid = self.store.add_observation(tid, ver, typ, ref, key, True, {"label": st.get("label"), "ok": bool(st.get("ok"))},
                                             now)
            if not st.get("ok") and (prev is None or prev["version_key"] != key):
                out.append({"source": typ, "ref": ref, "version_key": key, "kind": "connection_down", "obs": oid,
                            "evidence": [f"mcp:{ref} {st.get('error') or ''}"[:300]],
                            "detail": f"kết nối {st.get('label') or ref} đang lỗi"})
            return out
        if typ == "test":
            res = self.deps.run_test(ref, self.deps.brain_root(team)) or {}
            if not res.get("ran"):
                self.store.add_observation(tid, ver, typ, ref, "missing", False,
                                           {"missing": _clip(res.get("error") or "lệnh không chạy được", 300)}, now)
                return []
            code = int(res.get("exit") or 0)
            key = f"exit:{code}:{_hash(_clip(res.get('output'), 4000))}"
            prev = self.store.last_observation(tid, typ, ref)
            oid = self.store.add_observation(tid, ver, typ, ref, key, True, {"exit": code}, now)
            if code != 0 and (prev is None or prev["version_key"] != key):
                out.append({"source": typ, "ref": ref, "version_key": key, "kind": "test_failing", "obs": oid,
                            "evidence": [f"test:{ref} exit {code}", _clip(res.get("output"), 280)],
                            "detail": f"lệnh kiểm tra `{ref}` trả mã {code}"})
            return out
        return out

    # ---- decide and act ----
    def classify(self, m: dict, kind: str, now: float) -> str:
        auto = m.get("autonomy") or {}
        if kind in (auto.get("act") or []):
            want = "enqueue"
        elif kind in (auto.get("approve") or []):
            want = "ask"
        elif kind in (auto.get("propose") or []):
            want = "propose"
        else:
            return "watch"
        if want in ("enqueue", "ask"):
            cap = int((m.get("budget") or {}).get("jobs_per_day", DEFAULT_BUDGET["jobs_per_day"]))
            if self.store.jobs_opened_since(m["team_id"], self._day_start(now)) >= cap:
                return "propose"
            mx = (m.get("stop") or {}).get("max_open_jobs")
            if mx is not None and self._open_jobs(m["team_id"]) >= int(mx):
                return "propose"
        return want

    def _open_jobs(self, team_id: str) -> int:
        n = 0
        for o in self.store.opportunities(team_id, ("enqueued", "asked"), limit=200):
            t = self.runner.tasks.get_task(o["task_id"]) if o.get("task_id") else None
            if t and t["status"] not in ("done", "cancelled") and t.get("block_kind") != "rejected":
                n += 1
        return n

    def _act(self, team: dict, m: dict, ev: dict, now: float) -> Optional[dict]:
        with team_lock(team["team_id"]):
            if self._still(m) is None:
                return None   # paused, revoked or edited while the sources were read: act on nothing
            return self._act_locked(team, m, ev, now)

    def _act_locked(self, team: dict, m: dict, ev: dict, now: float) -> Optional[dict]:
        reason = f"{KIND_LABEL[ev['kind']]}: {ev['detail']}. Gắn với mục tiêu: {m['outcome'][:200]}"
        opp = self.store.add_opportunity(team_id=team["team_id"], version=int(m["version"]), source=ev["source"],
                                         ref=ev["ref"], version_key=ev["version_key"], kind=ev["kind"], reason=reason,
                                         benefit=KIND_BENEFIT[ev["kind"]], evidence=ev["evidence"],
                                         observation_id=ev["obs"], at=now, expire_h=self.expire_h,
                                         cooldown_min=self.cooldown_min)
        if opp == "cooldown":
            self.store.suppress_observation(ev["obs"])
            return None
        if not isinstance(opp, dict):
            return None
        decision = self.classify(m, ev["kind"], now)
        self.store.update_opportunity(opp["opp_id"], decision=decision)
        if decision == "watch":
            self.store.update_opportunity(opp["opp_id"], status="watched")
        elif decision in ("enqueue", "ask"):
            self._open(team, m, self.store.opportunity(opp["opp_id"]), by="mandate", ask=decision == "ask")
        elif decision == "propose":
            self._propose(team, m, self.store.opportunity(opp["opp_id"]))
        return {"opp_id": opp["opp_id"], "decision": decision, "kind": ev["kind"], "ref": ev["ref"]}

    def _intent(self, m: dict, opp: dict) -> str:
        ev = "\n".join(f"- {e}" for e in opp["evidence"]) or "- (không có)"
        return (f"{opp['reason']}\n\nLợi ích dự kiến: {opp['benefit']}.\nPhạm vi được giao: {m['scope'] or '(theo mục tiêu)'}"
                f"\nBằng chứng:\n{ev}\n\nDấu vết: mục tiêu v{m['version']} -> quan sát #{opp['observation_id']} -> cơ hội "
                f"{opp['opp_id']} ({opp['source']}:{opp['ref']} @ {opp['version_key']}).")

    def _open(self, team: dict, m: dict, opp: dict, *, by: str, ask: bool) -> Optional[str]:
        title = f"[Mục tiêu] {KIND_LABEL[opp['kind']].capitalize()}: {opp['ref']}"[:160]
        # Opening and stopping for approval happen under the runner's pool lock, so the dispatcher cannot claim the job
        # in between and run it before the owner decides.
        # Review 0.208.0: an approve-level job is created already stopped (same transaction), so neither an error nor a
        # crash before its approval card exists can leave it runnable.
        tid, created = self.deps.open_job(team, title, self._intent(m, opp), f"mandate:{opp['opp_id']}",
                                          blocked_kind="waiting_user" if ask else "")
        aid = None
        if ask and created:
            try:
                aid = self.runner.mandate_job_needs_approval(team, tid, title, opp, m)
            except Exception:
                self.runner.cancel_job(tid, "không tạo được thẻ duyệt cho việc của mục tiêu")
                raise
        if not created:
            self.store.update_opportunity(opp["opp_id"], status="enqueued", task_id=tid, decided_by=by)
            return tid
        self.store.update_opportunity(opp["opp_id"], status="asked" if ask else "enqueued", task_id=tid,
                                      approval_id=aid, decided_by=by)
        self.runner._system(team, (f"Mục tiêu phòng ban mở việc \"{title}\"" + (" (chờ bạn duyệt)" if ask else "") +
                                   f". Lý do: {opp['reason'][:240]}"), "mandate_job")
        self.runner._state(team["team_id"])
        return tid

    def _propose(self, team: dict, m: dict, opp: dict) -> None:
        mid = self.runner._post(team, f"Cơ hội theo mục tiêu: {opp['reason'][:300]}", author_kind="system",
                                meta={"kind": "mandate_opportunity", "opportunity": view(opp)})
        self.store.update_opportunity(opp["opp_id"], status="proposed", message_id=mid)

    def _refresh_card(self, team_id: str, opp_id: str) -> None:
        opp = self.store.opportunity(opp_id)
        team = self.runner.teams.get(team_id)
        if not opp or not team or not opp.get("message_id"):
            return
        self.runner.sessions.update_team_message_meta(team["session_id"], int(opp["message_id"]),
                                                      {"opportunity": view(opp)})
        msg = self.runner.sessions.team_message(team["session_id"], int(opp["message_id"]))
        if msg:
            self.runner._publish({"type": "team_message", "team_id": team_id, "message": self.runner.message_view(team, msg)})

    def decide(self, team_id: str, opp_id: str, decision: str, by: str = "owner") -> dict:
        """Owner on a proposal card: `accept` opens the job (owner-opened, not counted against the mandate budget),
        `reject` closes it; the same data version never comes back. Compare-and-set on the open states."""
        opp = self.store.opportunity(opp_id)
        if not opp or opp["team_id"] != team_id:
            return {"ok": False, "error": "not_found"}
        with team_lock(team_id):
            m = self.store.get(team_id)
            team = self.runner.teams.get(team_id)
            if decision == "reject":
                ok = self.store.update_opportunity(opp_id, expect=OPEN_OPP, status="rejected", decided_by=by)
            elif decision == "accept":
                if not m or m["status"] in ("revoked", "off"):
                    return {"ok": False, "error": "mandate_off"}
                if not team or team.get("status") != "active":
                    return {"ok": False, "error": "team_inactive"}
                ok = self.store.update_opportunity(opp_id, expect=OPEN_OPP, status="accepting", decided_by=by)
                if ok:
                    try:
                        self._open(team, m, self.store.opportunity(opp_id), by=by, ask=False)
                    except Exception:
                        # Never stuck in `accepting`: back to the owner's card (review 0.208.0).
                        self.store.update_opportunity(opp_id, expect=("accepting",), status="proposed", decided_by="")
                        raise
            else:
                return {"ok": False, "error": "bad_decision"}
        self._refresh_card(team_id, opp_id)
        return {"ok": ok, "error": "" if ok else "already_decided", "opportunity": view(self.store.opportunity(opp_id))}

    def revoke(self, team_id: str, by: str = "owner") -> dict:
        """Revoke: nothing new from this mandate. Jobs it opened that did not start are cancelled, open opportunities
        close, its waiting approval cards close (through the job cancel)."""
        with team_lock(team_id):
            return self._revoke_locked(team_id, by)

    def _revoke_locked(self, team_id: str, by: str) -> dict:
        m = self.store.set_status(team_id, "revoked", by)
        cancelled, closed = [], []
        for o in self.store.opportunities(team_id, limit=500):
            if o["status"] in OPEN_OPP + ("accepting",):
                self.store.update_opportunity(o["opp_id"], status="dismissed", decided_by=by)
                closed.append(o["opp_id"])
                self._refresh_card(team_id, o["opp_id"])
            if o.get("task_id"):
                t = self.runner.tasks.get_task(o["task_id"])
                if t and t["status"] in ("team_queued", "team_blocked"):
                    if self.runner.cancel_job(o["task_id"], "mục tiêu phòng ban đã thu hồi") is not None:
                        cancelled.append(o["task_id"])
        return {"ok": True, "mandate": m, "cancelled": cancelled, "closed": closed}

    def trace(self, team_id: str, opp_id: str) -> Optional[dict]:
        """goal -> observation -> opportunity -> decision -> approval -> job -> steps -> result."""
        opp = self.store.opportunity(opp_id)
        if not opp or opp["team_id"] != team_id:
            return None
        vers = {v["version"]: v for v in self.store.versions(team_id)}
        obs = self.store.observation(opp["observation_id"]) if opp.get("observation_id") else None
        task = self.runner.tasks.get_task(opp["task_id"]) if opp.get("task_id") else None
        approvals = self.runner.approvals_view(team_id, opp["task_id"]) if opp.get("task_id") else []
        steps = self.runner.teams.steps(opp["task_id"]) if opp.get("task_id") else []
        return {"mandate": vers.get(opp["mandate_version"]), "observation": obs, "opportunity": view(opp),
                "decision": opp["decision"], "approvals": approvals,
                "job": ({k: task.get(k) for k in ("id", "title", "status", "block_kind", "result", "team_rev")}
                        if task else None),
                "steps": [{k: s.get(k) for k in ("step_id", "kind", "agent_key", "status", "note")} for s in steps],
                # 0.209.0: the last link, the product acceptance of the job (None when the owner set no criteria).
                "acceptance": (self.runner.acceptance_view(self.runner.teams.get(team_id), opp["task_id"])
                               if opp.get("task_id") and getattr(self.runner, "acceptance", None) is not None else None)}


def view(opp: Optional[dict]) -> Optional[dict]:
    if not opp:
        return None
    return {k: opp.get(k) for k in ("opp_id", "team_id", "mandate_version", "source", "ref", "version_key", "kind",
                                    "reason", "benefit", "evidence", "decision", "status", "task_id", "approval_id",
                                    "created_at", "expires_at", "decided_by")}


def sources_view(store: MandateStore, m: Optional[dict]) -> list:
    """Each granted source with its last observation: read fine, or missing (what is missing), or not observed yet."""
    if not m:
        return []
    out = []
    for raw in m.get("sources") or []:
        src = parse_source(raw)
        if not src:
            continue
        last = store.last_observation(m["team_id"], src["type"], src["ref"]) if src["type"] != "kanban" else \
            store.last_observation(m["team_id"], "kanban", "kanban")
        out.append({"source": raw, "state": "never" if last is None else ("ok" if last["ok"] else "missing"),
                    "missing": (last or {}).get("summary", {}).get("missing", "") if last and not last["ok"] else "",
                    "observed_at": (last or {}).get("observed_at")})
    return out
