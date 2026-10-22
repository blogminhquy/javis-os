"""Owner approval requests for Team jobs (0.207.0): a real gate, not a chat flag.

Before this version an agent could write "@Chủ nhóm anh duyệt phương án này trước khi em thực hiện nhé?", the message was
flagged `asks_owner`, and the job still ended `done` (a plan with no assignment became the job's result). Design:
docs/superpowers/specs/2026-10-17-team-duyet-muc-tieu-nghiem-thu-design.md, part 1.

One row per request in `team_approvals` (team.sqlite3, new tables only, an older build ignores them):

- bound to a team, a job (`task_id`), the step that asked, the job revision (`team_rev`) and the agent that asked;
- says exactly what is asked (`title`, `action`, `scope`, `impact`, `evidence`, optional `deadline_at`) and, for an
  action the tool gate stopped or the agent listed, the action's fingerprints (tool + exact arguments);
- `held_ops`: what the step wanted to do once approved (a plan's assignments), applied only after approval.

Lifecycle: pending -> approved -> consumed, or rejected / changes_requested / expired / superseded / cancelled / revoked.
At most one pending request per job. A decision is a compare-and-set (still pending, same job revision) with an
idempotency key per click: the same key replays the first answer (a retry after a lost connection), another key after
the decision gets `already_decided` (a second tab). Only the signed-in owner decides, through the HTTP route; no team
directive and no chat text can approve. An approved action's fingerprint is consumed in the same transaction that lets
the tool call through, so a restart or a rerun of the step never repeats the effect without a new approval.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Callable, Optional

KINDS = ("action", "plan", "question")
OPEN = ("pending",)
LIVE = ("pending", "approved")
STATUSES = ("pending", "approved", "consumed", "rejected", "changes_requested", "expired", "superseded",
            "cancelled", "revoked")
DECISIONS = {"approve": "approved", "reject": "rejected", "changes": "changes_requested"}
TEXT_MAX = 2000
EVIDENCE_MAX = 10
JOIN_MAX_CALLS = 15        # calls one card may list once sibling steps of a wave joined it (3 steps x 5 calls)

SCHEMA = """
CREATE TABLE IF NOT EXISTS team_approvals(
  approval_id TEXT PRIMARY KEY, team_id TEXT NOT NULL, task_id TEXT NOT NULL, step_id TEXT NOT NULL DEFAULT '',
  team_rev INTEGER NOT NULL, requested_by TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '', action TEXT NOT NULL DEFAULT '', scope TEXT NOT NULL DEFAULT '',
  impact TEXT NOT NULL DEFAULT '', evidence_json TEXT NOT NULL DEFAULT '[]', deadline_at REAL,
  fingerprints_json TEXT NOT NULL DEFAULT '[]', held_ops_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'pending', decided_by TEXT NOT NULL DEFAULT '', decision_note TEXT NOT NULL DEFAULT '',
  decision_key TEXT, decided_at REAL, consumed_at REAL, close_reason TEXT NOT NULL DEFAULT '',
  message_id INTEGER, created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS team_approvals_one_pending ON team_approvals(task_id) WHERE status='pending';
CREATE UNIQUE INDEX IF NOT EXISTS team_approvals_decision_key ON team_approvals(decision_key)
  WHERE decision_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS team_approvals_team ON team_approvals(team_id, status, created_at);
CREATE INDEX IF NOT EXISTS team_approvals_task ON team_approvals(task_id, created_at);
CREATE TABLE IF NOT EXISTS team_approval_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, approval_id TEXT NOT NULL, at REAL NOT NULL, kind TEXT NOT NULL,
  by TEXT NOT NULL DEFAULT '', detail_json TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS team_approval_events_ap ON team_approval_events(approval_id, id);
"""


def fingerprint(kind: str, name: str, args: Any) -> str:
    """Stable id of one exact action: the tool and its exact arguments. A different argument is a different action."""
    try:
        canon = json.dumps(args, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        canon = str(args)
    return hashlib.sha256(f"{kind}|{name}|{canon}".encode("utf-8")).hexdigest()[:32]


def _clip(v: Any, n: int = TEXT_MAX) -> str:
    return str(v or "").strip()[:n]


def _j(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False)


# The words an agent uses to ask the owner for a decision in prose (the safety net, never the protocol). Matched only
# on a step's result when it carried no structured request.
ASKS_DECISION_RE = re.compile(
    r"@(?:chủ nhóm|chủ team|chu nhom|owner)(?![\w])|"
    r"(?:anh|chị|chủ nhóm|bạn)\s+(?:có\s+)?(?:duyệt|phê duyệt|đồng ý|xác nhận|chốt|quyết định|cho phép)[^.\n?]{0,160}\?|"
    r"(?:cần|xin|chờ)\s+(?:anh|chị|chủ nhóm|bạn)\s+(?:duyệt|phê duyệt|xác nhận|quyết định|cho phép)|"
    r"\b(?:need\s+your\s+approval|awaiting\s+your\s+approval|should\s+i\s+proceed|can\s+you\s+approve|do\s+you\s+approve)\b",
    re.IGNORECASE)


_CODE_RE = re.compile(r"```.*?```|`[^`\n]*`", re.S)


def _own_words(text: str) -> str:
    """The agent's own prose: without code blocks, inline code and quoted lines (a deliverable that quotes a customer's
    "Chị có đồng ý không?" is not the agent asking the owner)."""
    t = _CODE_RE.sub(" ", str(text or ""))
    return "\n".join(line for line in t.splitlines() if not line.lstrip().startswith(">"))


def asks_decision(text: str) -> bool:
    return bool(ASKS_DECISION_RE.search(_own_words(text)))


def excerpt(text: str, n: int = 600) -> str:
    """The part of a prose request the owner should read: the sentence that asks, with a little before it."""
    t = str(text or "").strip()
    m = ASKS_DECISION_RE.search(t)
    if not m:
        return t[:n]
    start = max(0, t.rfind("\n", 0, max(0, m.start() - 200)) + 1)
    return t[start:start + n].strip()


def parse_request(op: dict) -> Optional[dict]:
    """Validate an `ask_approval` directive. None when it says nothing an owner could decide on."""
    if not isinstance(op, dict):
        return None
    title = _clip(op.get("title"), 200)
    action = _clip(op.get("action"))
    if not (title or action):
        return None
    evidence = op.get("evidence") or []
    if isinstance(evidence, str):
        evidence = [evidence]
    evidence = [_clip(e, 400) for e in evidence if str(e or "").strip()][:EVIDENCE_MAX]
    actions = []
    for a in (op.get("actions") or [])[:5]:
        if isinstance(a, dict) and str(a.get("tool") or "").strip():
            actions.append({"tool": _clip(a.get("tool"), 120), "args": a.get("args") if isinstance(a.get("args"), dict) else {}})
    deadline = op.get("deadline_at")
    try:
        deadline = float(deadline) if deadline not in (None, "") else None
    except (TypeError, ValueError):
        deadline = None
    return {"title": title or action[:200], "action": action or title, "scope": _clip(op.get("scope"), 600),
            "impact": _clip(op.get("impact"), 600), "evidence": evidence, "deadline_at": deadline, "actions": actions}


class ApprovalStore:
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
    def _row(r) -> Optional[dict]:
        if r is None:
            return None
        d = dict(r)
        d["evidence"] = json.loads(d.pop("evidence_json") or "[]")
        d["fingerprints"] = json.loads(d.pop("fingerprints_json") or "[]")
        d["held_ops"] = json.loads(d.pop("held_ops_json") or "[]")
        return d

    def _event(self, c, aid: str, kind: str, by: str = "", detail: Optional[dict] = None) -> None:
        c.execute("INSERT INTO team_approval_events(approval_id, at, kind, by, detail_json) VALUES(?,?,?,?,?)",
                  (aid, self.clock(), kind, by, _j(detail or {})))

    # ---- create ----
    def create(self, *, team_id: str, task_id: str, step_id: str, team_rev: int, requested_by: str, kind: str,
               title: str, action: str, scope: str = "", impact: str = "", evidence: Optional[list] = None,
               deadline_at: Optional[float] = None, fingerprints: Optional[list] = None,
               held_ops: Optional[list] = None) -> dict:
        """A new pending request, or the job's existing pending one (at most one per job): a second ask while the job
        already waits is folded into the first, never a second card."""
        if kind not in KINDS:
            raise ValueError("kind")
        now = self.clock()
        aid = "ap_" + secrets.token_hex(8)
        fps = [{"fp": str(f.get("fp")), "label": _clip(f.get("label"), 300), "call": _clip(f.get("call"), 1500),
                "used_at": None}
               for f in (fingerprints or []) if isinstance(f, dict) and f.get("fp")]
        with self._Tx(self) as c:
            old = c.execute("SELECT * FROM team_approvals WHERE task_id=? AND status='pending'", (task_id,)).fetchone()
            if old is not None:
                return self._row(old)
            c.execute(
                "INSERT INTO team_approvals(approval_id,team_id,task_id,step_id,team_rev,requested_by,kind,title,action,"
                "scope,impact,evidence_json,deadline_at,fingerprints_json,held_ops_json,status,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',?,?)",
                (aid, team_id, task_id, step_id or "", int(team_rev), requested_by or "", kind, _clip(title, 200),
                 _clip(action), _clip(scope, 600), _clip(impact, 600), _j(list(evidence or [])[:EVIDENCE_MAX]),
                 deadline_at, _j(fps), _j(list(held_ops or [])), now, now))
            self._event(c, aid, "requested", requested_by, {"kind": kind, "team_rev": int(team_rev), "step_id": step_id})
            return self._row(c.execute("SELECT * FROM team_approvals WHERE approval_id=?", (aid,)).fetchone())

    def join(self, aid: str, *, step_id: str, requested_by: str, who: str, action: str,
             fingerprints: Optional[list] = None) -> Optional[dict]:
        """0.271.0: fold the request of another step of the same job into this pending request (the job waits for one
        card at a time). Before this, a sibling step of the same wave that also needed approval was parked and its request
        dropped: the member said it filed one and no card ever showed it (customer report, codes 5 and 22). The joined
        step is recorded (`joined` event) so the approval opens it too. None when the request is no longer pending."""
        now = self.clock()
        with self._Tx(self) as c:
            r = c.execute("SELECT * FROM team_approvals WHERE approval_id=? AND status='pending'", (aid,)).fetchone()
            if r is None:
                return None
            fps = json.loads(r["fingerprints_json"] or "[]")
            have = {f.get("fp") for f in fps}
            for f in fingerprints or []:
                if isinstance(f, dict) and f.get("fp") and f["fp"] not in have and len(fps) < JOIN_MAX_CALLS:
                    fps.append({"fp": str(f["fp"]), "label": _clip(f.get("label"), 300), "call": _clip(f.get("call"), 1500),
                                "used_at": None})
                    have.add(f["fp"])
            text = _clip(f"{r['action']}\n\n{_clip(who, 80) or requested_by}: {_clip(action, 800)}")
            kind = "action" if fps and r["kind"] == "question" else r["kind"]
            c.execute("UPDATE team_approvals SET fingerprints_json=?, action=?, kind=?, updated_at=? WHERE approval_id=?",
                      (_j(fps), text, kind, now, aid))
            self._event(c, aid, "joined", requested_by, {"step_id": step_id})
            return self._row(c.execute("SELECT * FROM team_approvals WHERE approval_id=?", (aid,)).fetchone())

    def joined_steps(self, aid: str) -> list:
        """Step ids folded into this request with `join`, in order."""
        out = []
        for e in self.events(aid):
            sid = (e.get("detail") or {}).get("step_id")
            if e["kind"] == "joined" and sid and sid not in out:
                out.append(sid)
        return out

    def set_message(self, aid: str, message_id: int) -> None:
        with self._Tx(self) as c:
            c.execute("UPDATE team_approvals SET message_id=? WHERE approval_id=?", (int(message_id), aid))

    # ---- read ----
    def get(self, aid: str) -> Optional[dict]:
        with closing(self._conn()) as c:
            return self._row(c.execute("SELECT * FROM team_approvals WHERE approval_id=?", (aid,)).fetchone())

    def pending_for_task(self, task_id: str) -> Optional[dict]:
        with closing(self._conn()) as c:
            return self._row(c.execute("SELECT * FROM team_approvals WHERE task_id=? AND status='pending'",
                                       (task_id,)).fetchone())

    def for_task(self, task_id: str) -> list:
        with closing(self._conn()) as c:
            return [self._row(r) for r in c.execute(
                "SELECT * FROM team_approvals WHERE task_id=? ORDER BY created_at", (task_id,)).fetchall()]

    def for_team(self, team_id: str, statuses: Optional[tuple] = None, limit: int = 50) -> list:
        q = "SELECT * FROM team_approvals WHERE team_id=?"
        args: list = [team_id]
        if statuses:
            q += f" AND status IN ({','.join('?' * len(statuses))})"
            args += list(statuses)
        q += " ORDER BY created_at DESC LIMIT ?"
        args.append(max(1, int(limit)))
        with closing(self._conn()) as c:
            return [self._row(r) for r in c.execute(q, args).fetchall()]

    def events(self, aid: str) -> list:
        with closing(self._conn()) as c:
            return [dict(r, detail=json.loads(r["detail_json"] or "{}")) for r in c.execute(
                "SELECT id, approval_id, at, kind, by, detail_json FROM team_approval_events WHERE approval_id=? "
                "ORDER BY id", (aid,)).fetchall()]

    def approved_for_step(self, step_id: str) -> Optional[dict]:
        with closing(self._conn()) as c:
            return self._row(c.execute(
                "SELECT * FROM team_approvals WHERE status='approved' AND approval_id IN "
                "(SELECT approval_id FROM team_approval_events WHERE kind='granted_step' "
                "AND json_extract(detail_json,'$.step_id')=?) ORDER BY decided_at DESC LIMIT 1", (step_id,)).fetchone())

    # ---- decide ----
    def decide(self, aid: str, decision: str, *, by: str, note: str = "", decision_key: str,
               current_rev: Optional[int] = None) -> dict:
        """{"ok", "status", "approval", "replay", "error"}. CAS on pending + job revision; `decision_key` makes a retry
        return the first answer."""
        target = DECISIONS.get(str(decision or "").strip().lower())
        key = str(decision_key or "").strip()[:80]
        if not target:
            return {"ok": False, "error": "bad_decision"}
        if not key:
            return {"ok": False, "error": "no_decision_key"}
        now = self.clock()
        with self._Tx(self) as c:
            same = c.execute("SELECT * FROM team_approvals WHERE decision_key=?", (key,)).fetchone()
            if same is not None:
                ap = self._row(same)
                ok = ap["approval_id"] == aid
                return {"ok": ok, "replay": True, "status": ap["status"], "approval": ap,
                        "error": "" if ok else "key_reused"}
            r = c.execute("SELECT * FROM team_approvals WHERE approval_id=?", (aid,)).fetchone()
            if r is None:
                return {"ok": False, "error": "not_found"}
            ap = self._row(r)
            if ap["status"] != "pending":
                return {"ok": False, "error": "already_decided", "status": ap["status"], "approval": ap}
            if ap["deadline_at"] and now > float(ap["deadline_at"]):
                c.execute("UPDATE team_approvals SET status='expired', close_reason='deadline', updated_at=? "
                          "WHERE approval_id=?", (now, aid))
                self._event(c, aid, "expired", "host", {})
                return {"ok": False, "error": "expired", "status": "expired"}
            if current_rev is not None and int(current_rev) != int(ap["team_rev"]):
                c.execute("UPDATE team_approvals SET status='superseded', close_reason='revision', updated_at=? "
                          "WHERE approval_id=?", (now, aid))
                self._event(c, aid, "superseded", "host", {"reason": "revision", "current_rev": int(current_rev)})
                return {"ok": False, "error": "stale", "status": "superseded"}
            c.execute("UPDATE team_approvals SET status=?, decided_by=?, decision_note=?, decision_key=?, decided_at=?, "
                      "updated_at=? WHERE approval_id=? AND status='pending'",
                      (target, str(by or "owner")[:80], _clip(note), key, now, now, aid))
            self._event(c, aid, target, by, {"note": _clip(note, 400)})
            out = self._row(c.execute("SELECT * FROM team_approvals WHERE approval_id=?", (aid,)).fetchone())
        return {"ok": True, "replay": False, "status": target, "approval": out}

    def granted_step(self, aid: str, step_id: str) -> None:
        """Record the step the approval opened, so the tool gate of that step (and only that step) can use it."""
        with self._Tx(self) as c:
            self._event(c, aid, "granted_step", "host", {"step_id": step_id})

    # ---- use ----
    def consume_fingerprint(self, step_id: str, fp: str) -> Optional[str]:
        """Let ONE approved action through: the approval granted to this step lists this fingerprint and it was not used
        yet. Marked used in the same transaction, before the tool runs. Returns the approval id, or None."""
        now = self.clock()
        with self._Tx(self) as c:
            rows = c.execute(
                "SELECT a.* FROM team_approvals a JOIN team_approval_events e ON e.approval_id=a.approval_id "
                "WHERE a.status='approved' AND e.kind='granted_step' AND json_extract(e.detail_json,'$.step_id')=?",
                (step_id,)).fetchall()
            for r in rows:
                fps = json.loads(r["fingerprints_json"] or "[]")
                for f in fps:
                    if f.get("fp") == fp and not f.get("used_at"):
                        f["used_at"] = now
                        done = all(x.get("used_at") for x in fps)
                        c.execute("UPDATE team_approvals SET fingerprints_json=?, status=?, consumed_at=?, updated_at=? "
                                  "WHERE approval_id=?",
                                  (_j(fps), "consumed" if done else "approved", now if done else None, now,
                                   r["approval_id"]))
                        self._event(c, r["approval_id"], "used", "host", {"fp": fp, "step_id": step_id})
                        return r["approval_id"]
        return None

    def consume(self, aid: str, reason: str = "step_done") -> bool:
        now = self.clock()
        with self._Tx(self) as c:
            n = c.execute("UPDATE team_approvals SET status='consumed', consumed_at=?, close_reason=?, updated_at=? "
                          "WHERE approval_id=? AND status='approved'", (now, reason, now, aid)).rowcount
            if n:
                self._event(c, aid, "consumed", "host", {"reason": reason})
            return n == 1

    # ---- invalidate ----
    def close_task(self, task_id: str, status: str, reason: str, from_statuses: tuple = LIVE) -> list:
        """Requests of a job that no longer apply (job edited, cancelled, permission revoked). Returns closed ids."""
        if status not in STATUSES:
            raise ValueError("status")
        now = self.clock()
        with self._Tx(self) as c:
            rows = c.execute(f"SELECT approval_id FROM team_approvals WHERE task_id=? AND status IN "
                             f"({','.join('?' * len(from_statuses))})", (task_id, *from_statuses)).fetchall()
            ids = [r["approval_id"] for r in rows]
            for aid in ids:
                c.execute("UPDATE team_approvals SET status=?, close_reason=?, updated_at=? WHERE approval_id=?",
                          (status, _clip(reason, 200), now, aid))
                self._event(c, aid, status, "host", {"reason": _clip(reason, 200)})
        return ids

    def close_one(self, aid: str, status: str, reason: str, from_statuses: tuple = LIVE) -> bool:
        if status not in STATUSES:
            raise ValueError("status")
        now = self.clock()
        with self._Tx(self) as c:
            n = c.execute(f"UPDATE team_approvals SET status=?, close_reason=?, updated_at=? WHERE approval_id=? AND status IN "
                          f"({','.join('?' * len(from_statuses))})",
                          (status, _clip(reason, 200), now, aid, *from_statuses)).rowcount
            if n:
                self._event(c, aid, status, "host", {"reason": _clip(reason, 200)})
            return n == 1

    def expire_due(self) -> list:
        now = self.clock()
        with self._Tx(self) as c:
            rows = c.execute("SELECT * FROM team_approvals WHERE status='pending' AND deadline_at IS NOT NULL "
                             "AND deadline_at < ?", (now,)).fetchall()
            out = []
            for r in rows:
                c.execute("UPDATE team_approvals SET status='expired', close_reason='deadline', updated_at=? "
                          "WHERE approval_id=? AND status='pending'", (now, r["approval_id"]))
                self._event(c, r["approval_id"], "expired", "host", {})
                out.append(self._row(r))
            return out


def view(ap: Optional[dict]) -> Optional[dict]:
    """What the dashboard shows: no internal fingerprints, only their labels and whether each was used."""
    if not ap:
        return None
    return {k: ap.get(k) for k in ("approval_id", "team_id", "task_id", "step_id", "team_rev", "requested_by", "kind",
                                   "title", "action", "scope", "impact", "evidence", "deadline_at", "status",
                                   "decided_by", "decision_note", "decided_at", "consumed_at", "close_reason",
                                   "message_id", "created_at")} | {
        "actions": [{"label": f.get("label"), "call": f.get("call") or "", "used": bool(f.get("used_at"))}
                    for f in ap.get("fingerprints") or []],
        "held_steps": len(ap.get("held_ops") or [])}
