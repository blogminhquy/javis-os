"""Portable mirror of what chatbots and agents have LEARNED, kept inside the brain folder.

Owner request (2026-10-25): copying or moving a brain to another machine, or restoring it from its GitHub backup, must
keep what a chatbot's reply-policy judge and the agents have learned. That knowledge lives in SQLite stores under
STATE_DIR, keyed by machine-local random ids (`bot_<uuid>`, `ag_<hex>`, `tm_<hex>`), so it never travelled with the
brain. The SQLite stores stay the source of truth; this module writes a JSON mirror next to the brain's other files and
imports it on a machine whose stores do not have it yet (same idea as `Javis/kanban.json`, see server/tasks.py).

Layout, under `<brain>/Javis/learned/`:

  bots/<bot-slug>.json            judge knowledge WITHOUT customer chat text: role profile, tuning knobs, lessons,
                                  per-chat threshold offsets, bootstrap cases (model-written from the Agent text).
  bots/<bot-slug>.private.json    judge cases whose text came from customer chat (auto and owner-labelled).
  agents/<agent-slug>.json        scoped agent lessons (active and revoked, so a revoked lesson keeps blocking
                                  re-learning), active presentation lessons, per-agent judge profile and offsets.
  agents/<agent-slug>.private.json  per-agent judge cases (they keep a chat excerpt in their features).

Privacy (owner decision "Tach rieng", 2026-10-25): files without chat text go to the GitHub brain backup; every
`*.private.json` under `Javis/learned/` never does (git_brain `_backup_skip` and the managed brain `.gitignore` block).
Copying the brain folder keeps everything; a GitHub restore keeps everything except the private files.

Ids are remapped on import:
  - a bot file belongs to the local bot whose own brain resolves to this brain and whose `slug` matches. Two local bots
    with the same slug in one brain are ambiguous: neither is mirrored nor imported (logged).
  - an agent file belongs to the live `resonance_agents` row for (brain, slug). No key is minted just to import: the
    file is imported when the agent first gets a key (`resonance_store.AGENT_KEY_HOOKS`) or at the next tick.
  - scopes and judge contexts: `dm:<agent_key>` <-> `dm`, `*` <-> `*`, `team:<tm_id>` <-> `team-name:<team name>`
    (skipped when the name is missing or not unique in the brain).

Import only fills EMPTY slots, section by section (a bot that already has lessons keeps its own lessons, and so on),
respects the stores' caps, and runs once per file content: `STATE_DIR/learned_mirror.json` remembers, per mirror file,
the content hash last seen or imported, the hash last written by this machine and the hash of the local data last
exported. The exporter only writes when the local data changed since its last export, so two machines sharing a
brain through GitHub do not overwrite each other's file on every tick, and it only deletes a file it wrote itself
(unless asked to, after "forget" or deleting a bot).

Nothing is written for an entity that learned nothing, and reading never creates a SQLite store.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import brain_ident
import config as cfgmod

VERSION = 1
PRIVATE_SUFFIX = ".private.json"
STATE_NAME = "learned_mirror.json"
TICK_S = 600                # background export/import every 10 minutes
FIRST_TICK_S = 90           # and once shortly after startup
AGENT_CASES_MAX = 500       # newest per-agent judge cases imported
AGENT_REVOKED_MAX = 200     # newest revoked agent lessons imported

_lock = threading.RLock()
_providers: Dict[str, Optional[Callable[[bool], Any]]] = {"resonance": None, "judge": None}
_cache: Dict[str, Any] = {}


def configure(resonance: Optional[Callable[[bool], Any]] = None, judge: Optional[Callable[[bool], Any]] = None) -> None:
    """main.py hands over its lazily-built stores so this module reuses them. Each provider takes `create` and returns
    the store, or None when it does not exist and `create` is False."""
    _providers["resonance"] = resonance
    _providers["judge"] = judge


def _log(msg: str) -> None:
    print(f"[learned mirror] {msg}", file=sys.stderr)


# ───────────── paths, hashing, state ─────────────

def learned_dir(root: Any) -> Path:
    return Path(root) / "Javis" / "learned"


def _paths(root: str, kind: str, name: str) -> Tuple[Path, Path]:
    d = learned_dir(root) / ("bots" if kind == "bot" else "agents")
    return d / f"{name}.json", d / f"{name}{PRIVATE_SUFFIX}"


def _safe_name(slug: Any) -> str:
    """A slug usable as a file name inside `Javis/learned/<kind>/`, or "" when it could escape the folder."""
    s = str(slug or "").strip()
    if not s or len(s) > 120 or s.startswith(".") or any(ch in s for ch in "/\\\0:") or ".." in s:
        return ""
    if s.endswith(".private"):
        return ""      # would collide with the private file of another slug
    return s


def _canon(doc: dict) -> str:
    body = {k: v for k, v in doc.items() if k != "updated"}
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha(p: Path) -> Optional[str]:
    try:
        return _sha(p.read_bytes())
    except OSError:
        return None


def _iso(ts: Optional[float] = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if ts is None else ts))


def _atomic_write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")      # `.tmp` is skipped by the backup
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
        fh.flush()
        try:
            os.fsync(fh.fileno())
        except OSError:
            pass
    os.replace(tmp, p)


def _state_path() -> Path:
    return Path(cfgmod.STATE_DIR) / STATE_NAME


class _State:
    """`learned_mirror.json`: {"version": 1, "files": {abs path: {"seen", "wrote", "local", "imported"}}}."""

    def __init__(self):
        self.path = _state_path()
        self.dirty = False
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            self.files = d.get("files") if isinstance(d, dict) and isinstance(d.get("files"), dict) else {}
        except (OSError, ValueError):
            self.files = {}

    def get(self, p: Path) -> dict:
        return dict(self.files.get(str(p)) or {})

    def put(self, p: Path, rec: dict) -> None:
        if self.files.get(str(p)) != rec:
            self.files[str(p)] = rec
            self.dirty = True

    def drop(self, p: Path) -> None:
        if self.files.pop(str(p), None) is not None:
            self.dirty = True

    def roots(self) -> List[str]:
        out = []
        for k in self.files:
            try:
                out.append(str(Path(k).parents[3]))     # <root>/Javis/learned/<kind>/<file>
            except IndexError:
                continue
        return out

    def save(self) -> None:
        if not self.dirty:
            return
        try:
            _atomic_write(self.path, json.dumps({"version": VERSION, "files": self.files}, ensure_ascii=False,
                                                indent=1, sort_keys=True) + "\n")
            self.dirty = False
        except OSError as e:
            _log(f"state not saved: {e}")


# ───────────── stores (never created just to read) ─────────────

def _rps():
    import chatbot_reply_policy_store as rps
    return rps


def _rps_exists() -> bool:
    return _rps().db_path().exists()


def _resonance(create: bool = False):
    fn = _providers.get("resonance")
    if fn is not None:
        return fn(create)
    p = Path(cfgmod.STATE_DIR) / "resonance.sqlite3"
    if not create and not p.is_file():
        return None
    key = "rs:" + str(p)
    if key not in _cache:
        import resonance_store
        _cache[key] = resonance_store.GoalStore(p)
    return _cache[key]


def _judge(create: bool = False):
    fn = _providers.get("judge")
    if fn is not None:
        return fn(create)
    import agent_judge_store
    p = Path(cfgmod.STATE_DIR) / agent_judge_store.STORE_NAME
    if not create and not p.is_file():
        return None
    key = "aj:" + str(p)
    if key not in _cache:
        _cache[key] = agent_judge_store.JudgeStore(p)
    return _cache[key]


def _has_table(c, name: str) -> bool:
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _teams() -> List[dict]:
    """Teams from `team.sqlite3`, read-only; [] when the store does not exist."""
    p = Path(cfgmod.STATE_DIR) / "team.sqlite3"
    if not p.is_file():
        return []
    try:
        with closing(sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True, timeout=10)) as c:
            c.row_factory = sqlite3.Row
            if not _has_table(c, "teams"):
                return []
            return [dict(r) for r in c.execute("SELECT team_id, brain_id, name, status FROM teams")]
    except sqlite3.Error as e:
        _log(f"teams unreadable: {e}")
        return []


class _TeamMap:
    """team_id <-> team name within one brain. A name shared by two live teams maps to nothing."""

    def __init__(self, root: str, teams: List[dict]):
        mine = [t for t in teams if brain_ident.same_brain(t.get("brain_id"), root)]
        self.name_of = {t["team_id"]: str(t.get("name") or "").strip() for t in mine}
        by_name: Dict[str, List[str]] = {}
        for t in mine:
            if t.get("status") != "archived":
                by_name.setdefault(str(t.get("name") or "").strip(), []).append(t["team_id"])
        self.id_of = {n: ids[0] for n, ids in by_name.items() if n and len(ids) == 1}

    def scope_out(self, scope: str, key: str) -> Optional[str]:
        s = str(scope or "")
        if s == "*":
            return "*"
        if s == f"dm:{key}":
            return "dm"
        if s.startswith("team:"):
            name = self.name_of.get(s[5:], "")
            if name and name in self.id_of:
                return "team-name:" + name
        return None

    def scope_in(self, scope: str, key: str) -> Optional[str]:
        s = str(scope or "")
        if s == "*":
            return "*"
        if s == "dm":
            return f"dm:{key}"
        if s.startswith("team-name:"):
            tid = self.id_of.get(s[len("team-name:"):])
            return f"team:{tid}" if tid else None
        return None


def _json_obj(s: Any) -> Any:
    try:
        v = json.loads(s) if isinstance(s, str) and s else (s if isinstance(s, (dict, list)) else {})
        return v if v is not None else {}
    except ValueError:
        return {}


# ───────────── bots: read ─────────────

def _bot_knowledge(bot_id: str) -> Tuple[dict, List[dict]]:
    """(public sections, private cases) of one bot. Empty when the judge store does not exist."""
    pub: dict = {"role_profile": None, "tuning": {}, "lessons": [], "threshold_offsets": [], "cases": []}
    priv: List[dict] = []
    if not _rps_exists():
        return pub, priv
    rps = _rps()
    b = str(bot_id)
    with rps._lock, rps._conn() as con:
        r = con.execute("SELECT generated_text, agent_hash, updated_ts FROM role_profiles WHERE bot_id=?",
                        (b,)).fetchone()
        if r is not None and (r["generated_text"] or r["agent_hash"]):
            pub["role_profile"] = {"generated_text": r["generated_text"] or "", "agent_hash": r["agent_hash"] or "",
                                   "updated_ts": r["updated_ts"]}
        pub["tuning"] = {x["key"]: x["value"] for x in con.execute(
            "SELECT key, value FROM tuning WHERE bot_id=? ORDER BY key", (b,))}
        pub["lessons"] = [{"text": x["text"], "source": x["source"] or "", "ts": x["ts"]} for x in con.execute(
            "SELECT text, ts, source FROM lessons WHERE bot_id=? ORDER BY id", (b,))]
        pub["threshold_offsets"] = [{"chat_id": x["chat_id"], "offset": x["offset"], "updated_ts": x["updated_ts"]}
                                    for x in con.execute("SELECT chat_id, offset, updated_ts FROM threshold_offsets"
                                                         " WHERE bot_id=? ORDER BY chat_id", (b,))]
        for x in con.execute("SELECT * FROM cases WHERE bot_id=? ORDER BY ts, id", (b,)):
            case = {"chat_id": x["chat_id"] or "", "ts": x["ts"], "text": x["text"] or "", "tokens": x["tokens"] or "",
                    "features": _json_obj(x["features_json"]), "correct_verdict": x["correct_verdict"],
                    "reason": x["reason"] or "", "source": x["source"], "weight": x["weight"]}
            (pub["cases"] if x["source"] == "bootstrap" else priv).append(case)
    return pub, priv


def _bot_docs(bot: dict) -> Tuple[Optional[dict], Optional[dict]]:
    pub, priv = _bot_knowledge(bot["id"])
    has_pub = any(pub[k] for k in ("role_profile", "tuning", "lessons", "threshold_offsets", "cases"))
    head = {"slug": bot.get("slug") or "", "name": bot.get("name") or "",
            "agent_slug": str((bot.get("agent") or {}).get("slug") or "")}
    now = _iso()
    pub_doc = {"version": VERSION, "kind": "bot", "bot": head, "updated": now, **pub} if has_pub else None
    priv_doc = ({"version": VERSION, "kind": "bot-private", "bot": {"slug": head["slug"]}, "updated": now,
                 "cases": priv} if priv else None)
    return pub_doc, priv_doc


# ───────────── bots: import ─────────────

def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _insert_bot_cases(con, bot_id: str, rows: list, bootstrap: bool, now: float, chats: set) -> int:
    """Insert mirrored judge cases for one bot (local ids dropped); `chats` collects the chat ids for the cap trim."""
    rps = _rps()
    added = 0
    for x in rows:
        if not isinstance(x, dict) or not x.get("correct_verdict"):
            continue
        src = "bootstrap" if bootstrap else str(x.get("source") or "auto")
        if src == "bootstrap" and not bootstrap:
            continue           # a private file never smuggles in bootstrap cases
        text = str(x.get("text") or "")[:rps.TEXT_MAX]
        tokens = str(x.get("tokens") or "") or " ".join(rps.tokens_of(text))
        chat = str(x.get("chat_id") or "")
        con.execute("INSERT INTO cases(bot_id, chat_id, ts, text, tokens, features_json, correct_verdict,"
                    " reason, source, weight) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (bot_id, chat, _f(x.get("ts"), now), text, tokens,
                     json.dumps(x.get("features") or {}, ensure_ascii=False), str(x["correct_verdict"]),
                     str(x.get("reason") or "")[:200], src, _f(x.get("weight"), 1.0)))
        chats.add(chat)
        added += 1
    return added


def _import_bot(bot_id: str, pub: Optional[dict], priv: Optional[dict]) -> Dict[str, int]:
    """Fill the empty sections of one local bot from mirror documents. Returns counts of imported rows."""
    rps = _rps()
    b = str(bot_id)
    out = {"lessons": 0, "tuning": 0, "offsets": 0, "role_profile": 0, "cases": 0, "private_cases": 0}
    pub = pub if isinstance(pub, dict) and pub.get("kind") == "bot" else {}
    priv = priv if isinstance(priv, dict) and priv.get("kind") == "bot-private" else {}
    if not any(pub.get(k) for k in ("role_profile", "tuning", "lessons", "threshold_offsets", "cases")) \
            and not priv.get("cases"):
        return out
    now = time.time()
    chats: set = set()
    with rps._lock, rps._conn() as con:
        rp = pub.get("role_profile")
        if isinstance(rp, dict) and not con.execute("SELECT 1 FROM role_profiles WHERE bot_id=?", (b,)).fetchone():
            con.execute("INSERT INTO role_profiles(bot_id, generated_text, agent_hash, updated_ts) VALUES(?,?,?,?)",
                        (b, str(rp.get("generated_text") or "")[:3000], str(rp.get("agent_hash") or ""),
                         _f(rp.get("updated_ts"), now)))
            out["role_profile"] = 1
        tuning = pub.get("tuning") if isinstance(pub.get("tuning"), dict) else {}
        for k, v in sorted(tuning.items()):
            cur = con.execute("INSERT OR IGNORE INTO tuning(bot_id, key, value, updated_ts) VALUES(?,?,?,?)",
                              (b, str(k), str(v), now))
            out["tuning"] += cur.rowcount
        lessons = [x for x in (pub.get("lessons") or []) if isinstance(x, dict) and str(x.get("text") or "").strip()]
        if lessons and not con.execute("SELECT 1 FROM lessons WHERE bot_id=? LIMIT 1", (b,)).fetchone():
            seen = set()
            keep = []
            for x in lessons:
                line = " ".join(str(x["text"]).split())[:200]
                key = " ".join(rps.tokens_of(line))
                if key in seen:
                    continue
                seen.add(key)
                keep.append((line, _f(x.get("ts"), now), str(x.get("source") or "")))
            for line, ts, src in keep[-rps.MAX_LESSONS:]:
                con.execute("INSERT INTO lessons(bot_id, text, ts, source) VALUES(?,?,?,?)", (b, line, ts, src))
                out["lessons"] += 1
        for x in pub.get("threshold_offsets") or []:
            if not isinstance(x, dict) or not str(x.get("chat_id") or ""):
                continue
            off = max(-rps.OFFSET_LIMIT, min(rps.OFFSET_LIMIT, _f(x.get("offset"))))
            cur = con.execute("INSERT OR IGNORE INTO threshold_offsets(bot_id, chat_id, offset, updated_ts)"
                              " VALUES(?,?,?,?)", (b, str(x["chat_id"]), off, _f(x.get("updated_ts"), now)))
            out["offsets"] += cur.rowcount

        boot = pub.get("cases") or []
        if boot and not con.execute("SELECT 1 FROM cases WHERE bot_id=? AND source='bootstrap' LIMIT 1",
                                    (b,)).fetchone():
            out["cases"] = _insert_bot_cases(con, b, boot, True, now, chats)
        pc = priv.get("cases") or []
        if pc and not con.execute("SELECT 1 FROM cases WHERE bot_id=? AND source!='bootstrap' LIMIT 1",
                                  (b,)).fetchone():
            out["private_cases"] = _insert_bot_cases(con, b, pc, False, now, chats)
        if chats:
            rps._trim_cases(con, b, "", now)
            for chat in sorted(chats):
                if chat:
                    rps._trim_cases(con, b, chat, now)
    return out


# ───────────── agents: read ─────────────

def _agent_rows(rs) -> Optional[List[dict]]:
    """Live agent rows, or None when the registry cannot be read (callers then leave agent files alone)."""
    try:
        with closing(rs._conn()) as c:
            return [dict(r) for r in c.execute(
                "SELECT agent_key, brain_id, slug, status FROM resonance_agents WHERE status IN ('active','missing')")]
    except sqlite3.Error as e:
        _log(f"agent registry unreadable: {e}")
        return None


def _agent_docs(agent: dict, teams: _TeamMap) -> Tuple[Optional[dict], Optional[dict]]:
    key, brain_id = agent["agent_key"], agent["brain_id"]
    lessons: List[dict] = []
    presentation: List[dict] = []
    rs = _resonance(False)
    if rs is not None:
        with closing(rs._conn()) as c:
            if _has_table(c, "agent_lessons"):
                for r in c.execute("SELECT * FROM agent_lessons WHERE agent_key=? AND status IN ('active','revoked')"
                                   " ORDER BY created_at, id", (key,)):
                    scope = teams.scope_out(r["scope"], key)
                    if scope is None:
                        continue
                    lessons.append({"scope": scope, "kind": r["kind"], "text": r["text"], "source": r["source"],
                                    "status": r["status"], "created_at": r["created_at"],
                                    "revoked_at": r["revoked_at"], "revoked_by": r["revoked_by"] or "",
                                    "revoke_reason": r["revoke_reason"] or ""})
            for r in c.execute("SELECT * FROM lessons WHERE brain_id=? AND agent_key=? AND lane='presentation' AND"
                               " status='active' AND goal_id='' ORDER BY created_at, id", (brain_id, key)):
                presentation.append({"lane": r["lane"], "key": r["key"], "from_value": r["from_value"],
                                     "to_value": r["to_value"], "scope": r["scope"],
                                     "policy_version": r["policy_version"], "status_reason": r["status_reason"],
                                     "decided_by": r["decided_by"], "decided_at": r["decided_at"],
                                     "created_at": r["created_at"]})
    judge: dict = {}
    cases: List[dict] = []
    js = _judge(False)
    if js is not None:
        with closing(js._conn()) as c:
            p = c.execute("SELECT * FROM profiles WHERE agent_key=?", (key,)).fetchone()
            if p is not None:
                judge["profile"] = {"role_text": p["role_text"], "eagerness": p["eagerness"],
                                    "role_hash": p["role_hash"], "eagerness_source": p["eagerness_source"]}
            offs = []
            for r in c.execute("SELECT context_ref, offset, updated_at FROM offsets WHERE agent_key=?"
                               " ORDER BY context_ref", (key,)):
                ctx = teams.scope_out(r["context_ref"], key)
                if ctx is not None and ctx != "*":
                    offs.append({"context": ctx, "offset": r["offset"], "updated_at": r["updated_at"]})
            if offs:
                judge["offsets"] = offs
            for r in c.execute("SELECT * FROM cases WHERE agent_key=? ORDER BY created_at, id", (key,)):
                ctx = teams.scope_out(r["context_ref"], key)
                if ctx is None or ctx == "*":
                    continue
                cases.append({"context": ctx, "text_sha": r["text_sha"], "features": _json_obj(r["features_json"]),
                              "label": r["label"], "weight": r["weight"], "source": r["source"],
                              "created_at": r["created_at"]})
    now = _iso()
    pub_doc = None
    if lessons or presentation or judge:
        pub_doc = {"version": VERSION, "kind": "agent", "agent": {"slug": agent["slug"]}, "updated": now,
                   "lessons": lessons, "presentation": presentation, "judge": judge}
    priv_doc = ({"version": VERSION, "kind": "agent-private", "agent": {"slug": agent["slug"]}, "updated": now,
                 "judge_cases": cases} if cases else None)
    return pub_doc, priv_doc


# ───────────── agents: import ─────────────

def _import_agent(agent: dict, teams: _TeamMap, pub: Optional[dict], priv: Optional[dict]) -> Dict[str, int]:
    key, brain_id = agent["agent_key"], agent["brain_id"]
    out = {"lessons": 0, "presentation": 0, "judge_profile": 0, "judge_offsets": 0, "judge_cases": 0}
    pub = pub if isinstance(pub, dict) and pub.get("kind") == "agent" else {}
    priv = priv if isinstance(priv, dict) and priv.get("kind") == "agent-private" else {}
    now = time.time()
    lessons = [x for x in (pub.get("lessons") or []) if isinstance(x, dict)]
    pres = [x for x in (pub.get("presentation") or []) if isinstance(x, dict)]
    if lessons or pres:
        import agent_lessons as AL
        rs = _resonance(True)
        AL.ensure(rs)
        with rs._Tx(rs) as c:
            if lessons and not c.execute("SELECT 1 FROM agent_lessons WHERE agent_key=? LIMIT 1", (key,)).fetchone():
                active: Dict[str, List[tuple]] = {}
                revoked: List[tuple] = []
                for x in lessons:
                    scope = teams.scope_in(x.get("scope"), key)
                    body = AL.clean_text(x.get("text"))
                    norm = AL.normalize(body)
                    if scope is None or not norm or x.get("kind") not in AL.KINDS or x.get("source") not in AL.SOURCES:
                        continue
                    row = (scope, x["kind"], body, norm, x["source"], _f(x.get("created_at"), now), x)
                    if x.get("status") == "revoked":
                        revoked.append(row)
                    elif x.get("status") == "active":
                        active.setdefault(scope, []).append(row)
                picked: List[tuple] = []
                for scope, rows in active.items():
                    uniq: Dict[str, tuple] = {}
                    for r in rows:
                        uniq[r[3]] = r                       # the newest copy of the same words wins
                    ranked = sorted(uniq.values(), key=lambda r: (r[4] == "owner", r[5]), reverse=True)
                    picked += [(r, "active") for r in ranked[:AL.SCOPE_ACTIVE_CAP]]
                picked += [(r, "revoked") for r in sorted(revoked, key=lambda r: r[5])[-AGENT_REVOKED_MAX:]]
                for (scope, kind, body, norm, src, created, x), status in sorted(picked, key=lambda p: p[0][5]):
                    lid = int(c.execute(
                        "INSERT INTO agent_lessons(agent_key,scope,kind,text,text_norm,source,source_refs_json,status,"
                        "created_at,revoked_at,revoked_by,revoke_reason) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (key, scope, kind, body, norm, src, "[]", status, created,
                         (_f(x.get("revoked_at"), now) if status == "revoked" else None),
                         str(x.get("revoked_by") or "") if status == "revoked" else "",
                         str(x.get("revoke_reason") or "")[:200] if status == "revoked" else "")).lastrowid)
                    AL._event(c, lid, key, "import", "mirror", {"scope": scope, "status": status}, now)
                    out["lessons"] += 1
            if pres and not c.execute("SELECT 1 FROM lessons WHERE brain_id=? AND agent_key=? AND lane='presentation'"
                                      " AND status='active' LIMIT 1", (brain_id, key)).fetchone():
                for x in pres:
                    if x.get("lane") != "presentation" or not str(x.get("key") or ""):
                        continue
                    lid = rs._insert_lesson(c, brain_id, key, "presentation", str(x["key"]),
                                            str(x.get("from_value") or ""), str(x.get("to_value") or ""), "active",
                                            now, reason="imported", scope=str(x.get("scope") or "agent"))
                    if lid:
                        out["presentation"] += 1
    judge = pub.get("judge") if isinstance(pub.get("judge"), dict) else {}
    jcases = [x for x in (priv.get("judge_cases") or []) if isinstance(x, dict)]
    if judge or jcases:
        import agent_judge_store as AJ
        js = _judge(True)
        prof = judge.get("profile") if isinstance(judge.get("profile"), dict) else None
        with js._Tx(js) as c:
            if prof and not c.execute("SELECT 1 FROM profiles WHERE agent_key=?", (key,)).fetchone():
                eag = prof.get("eagerness") if prof.get("eagerness") in AJ.EAGERNESS else AJ.DEFAULT_EAGERNESS
                c.execute("INSERT INTO profiles(agent_key,role_text,eagerness,role_hash,eagerness_source,updated_at)"
                          " VALUES(?,?,?,?,?,?)", (key, str(prof.get("role_text") or "")[:2000], eag,
                                                   str(prof.get("role_hash") or ""),
                                                   str(prof.get("eagerness_source") or ""), now))
                out["judge_profile"] = 1
            for x in judge.get("offsets") or []:
                ctx = teams.scope_in(x.get("context") if isinstance(x, dict) else None, key)
                if ctx is None or ctx == "*":
                    continue
                cur = c.execute("INSERT OR IGNORE INTO offsets(agent_key,context_ref,offset,updated_at) VALUES(?,?,?,?)",
                                (key, ctx, AJ.clamp_offset(_f(x.get("offset"))), _f(x.get("updated_at"), now)))
                out["judge_offsets"] += cur.rowcount
            if jcases and not c.execute("SELECT 1 FROM cases WHERE agent_key=? LIMIT 1", (key,)).fetchone():
                for x in sorted(jcases, key=lambda r: _f(r.get("created_at")))[-AGENT_CASES_MAX:]:
                    ctx = teams.scope_in(x.get("context"), key)
                    if ctx is None or ctx == "*" or not x.get("label"):
                        continue
                    c.execute("INSERT INTO cases(agent_key,context_ref,text_sha,features_json,label,weight,decision_id,"
                              "source,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                              (key, ctx, str(x.get("text_sha") or ""),
                               json.dumps(x.get("features") or {}, ensure_ascii=False, sort_keys=True),
                               str(x["label"]), _f(x.get("weight"), 1.0), None, str(x.get("source") or ""),
                               _f(x.get("created_at"), now)))
                    out["judge_cases"] += 1
    return out


# ───────────── the sync core ─────────────

class _Entity:
    def __init__(self, kind: str, name: str, ident: str, build: Callable[[], Tuple[Optional[dict], Optional[dict]]],
                 load: Callable[[Optional[dict], Optional[dict]], Dict[str, int]]):
        self.kind, self.name, self.ident, self.build, self.load = kind, name, ident, build, load


def _read_doc(p: Path) -> Optional[dict]:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) and int(d.get("version") or 0) <= VERSION else None
    except (OSError, ValueError, TypeError):
        return None


def _write_or_delete(st: _State, p: Path, doc: Optional[dict], force: bool) -> str:
    """Bring one mirror file in line with local data. Returns 'wrote', 'deleted' or ''."""
    rec = st.get(p)
    sha = _file_sha(p)
    if doc is None:
        if sha is not None and (force or rec.get("wrote") == sha):
            try:
                p.unlink()
            except OSError as e:
                _log(f"cannot delete {p}: {e}")
                return ""
            st.drop(p)
            return "deleted"
        if sha is None:
            st.drop(p)
        return ""
    canon = _canon(doc)
    local = _sha(canon.encode("utf-8"))
    if sha is not None and rec.get("local") == local:
        return ""                      # our data did not change since our last export
    if sha is not None:
        cur = _read_doc(p)
        if cur is not None and _canon(cur) == canon:
            st.put(p, {**rec, "local": local, "seen": sha, "wrote": sha})
            return ""
    text = json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    try:
        _atomic_write(p, text)
    except OSError as e:
        _log(f"cannot write {p}: {e}")
        return ""
    new = _sha(text.encode("utf-8"))
    st.put(p, {**rec, "local": local, "seen": new, "wrote": new})
    return "wrote"


def _process(st: _State, root: str, kind: str, name: str, ent: Optional[_Entity], *, blocked: bool = False,
             force: bool = False, report: Optional[dict] = None) -> None:
    """Import foreign mirror content into `ent` (empty slots only), then export `ent`'s data. Without an entity, a
    file this machine wrote is deleted (its bot moved, was deleted or its agent was retired); `blocked` (ambiguous slug,
    unreadable registry) leaves the files alone."""
    report = report if report is not None else {}
    pub_p, priv_p = _paths(root, kind, name)
    if ent is None:
        if blocked:
            return
        for p in (pub_p, priv_p):
            if _write_or_delete(st, p, None, False) == "deleted":
                report["deleted"] = report.get("deleted", 0) + 1
        return
    docs: Dict[str, Optional[dict]] = {"pub": None, "priv": None}
    fresh: List[Tuple[Path, str]] = []
    for tag, p in (("pub", pub_p), ("priv", priv_p)):
        sha = _file_sha(p)
        if sha is None or sha == st.get(p).get("seen"):
            continue
        docs[tag] = _read_doc(p)
        fresh.append((p, sha))
    if fresh:
        try:
            counts = ent.load(docs["pub"], docs["priv"])
        except Exception as e:  # noqa: BLE001 - one bad file must not stop the other entities
            _log(f"import {kind} {name} failed: {type(e).__name__}: {e}")
            return
        for p, sha in fresh:
            st.put(p, {**st.get(p), "seen": sha, "imported": sha})
        n = sum(counts.values())
        if n:
            report["imported"] = report.get("imported", 0) + n
            _log(f"imported {n} rows into {kind} {name} ({ent.ident}) from {learned_dir(root)}")
    try:
        pub, priv = ent.build()
    except Exception as e:  # noqa: BLE001
        _log(f"export {kind} {name} failed: {type(e).__name__}: {e}")
        return
    for p, doc in ((pub_p, pub), (priv_p, priv)):
        r = _write_or_delete(st, p, doc, force)
        if r:
            report[r] = report.get(r, 0) + 1


def _listed(root: str) -> Dict[Tuple[str, str], bool]:
    """(kind, name) of every mirror file present in the brain."""
    out: Dict[Tuple[str, str], bool] = {}
    for kind, sub in (("bot", "bots"), ("agent", "agents")):
        d = learned_dir(root) / sub
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for fn in names:
            if fn.endswith(PRIVATE_SUFFIX):
                stem = fn[:-len(PRIVATE_SUFFIX)]
            elif fn.endswith(".json"):
                stem = fn[:-5]
            else:
                continue
            if _safe_name(stem):
                out[(kind, stem)] = True
    return out


def _bot_root(bot: dict) -> str:
    c = brain_ident.canonical(bot.get("brain"))
    return c if c and os.path.isdir(c) else ""


def _load_bots() -> Optional[List[dict]]:
    try:
        import chatbot_store
        with chatbot_store._lock:
            return [dict(b) for b in chatbot_store._load()["bots"]]
    except Exception as e:  # noqa: BLE001
        _log(f"bots unreadable: {type(e).__name__}: {e}")
        return None


class _World:
    """One snapshot of local entities, grouped by brain root."""

    def __init__(self):
        self.bots = _load_bots()
        self.bot_ok = self.bots is not None
        self.bot_by: Dict[str, Dict[str, List[dict]]] = {}
        for b in self.bots or []:
            root, name = _bot_root(b), _safe_name(b.get("slug"))
            if root and name:
                self.bot_by.setdefault(root, {}).setdefault(name, []).append(b)
        rs = _resonance(False)
        rows = _agent_rows(rs) if rs is not None else []
        self.agent_ok = rows is not None
        self.agent_by: Dict[str, Dict[str, dict]] = {}
        for a in rows or []:
            root, name = brain_ident.canonical(a.get("brain_id")), _safe_name(a.get("slug"))
            if root and name and os.path.isdir(root):
                self.agent_by.setdefault(root, {})[name] = a
        self._teams: Optional[List[dict]] = None

    def teams(self, root: str) -> _TeamMap:
        if self._teams is None:
            self._teams = _teams()
        return _TeamMap(root, self._teams)

    def roots(self, extra: List[str]) -> List[str]:
        out = []
        for r in list(self.bot_by) + list(self.agent_by) + extra:
            c = brain_ident.canonical(r)
            if c and c not in out and os.path.isdir(c):
                out.append(c)
        return out

    def entity(self, root: str, kind: str, name: str) -> Tuple[Optional[_Entity], bool]:
        """(entity, blocked). Blocked = the files must be left alone (ambiguous slug or unreadable store)."""
        if kind == "bot":
            if not self.bot_ok:
                return None, True
            bots = self.bot_by.get(root, {}).get(name) or []
            if len(bots) > 1:
                _log(f"{len(bots)} bots share the slug {name!r} in {root}: not mirrored")
                return None, True
            if not bots:
                return None, False
            bot = bots[0]
            return _Entity("bot", name, bot["id"], lambda: _bot_docs(bot),
                           lambda pub, priv: _import_bot(bot["id"], pub, priv)), False
        if not self.agent_ok:
            return None, True
        a = self.agent_by.get(root, {}).get(name)
        if a is None:
            return None, False
        tm = self.teams(root)
        return _Entity("agent", name, a["agent_key"], lambda: _agent_docs(a, tm),
                       lambda pub, priv: _import_agent(a, tm, pub, priv)), False


def sync_brain(root: Any, world: Optional[_World] = None, st: Optional[_State] = None) -> dict:
    """Import then export every mirrored bot and agent of one brain. Returns counts."""
    report: dict = {}
    with _lock:
        own_state = st is None
        st = st or _State()
        world = world or _World()
        r = brain_ident.canonical(root)
        if not r or not os.path.isdir(r):
            return report
        keys = dict(_listed(r))
        for name in world.bot_by.get(r, {}):
            keys[("bot", name)] = True
        for name in world.agent_by.get(r, {}):
            keys[("agent", name)] = True
        for k in st.files:
            p = Path(k)
            try:
                if str(p.parents[3]) == r and p.parent.name in ("bots", "agents"):
                    stem = p.name[:-len(PRIVATE_SUFFIX)] if p.name.endswith(PRIVATE_SUFFIX) else p.stem
                    keys[("bot" if p.parent.name == "bots" else "agent", stem)] = True
            except IndexError:
                continue
        for kind, name in sorted(keys):
            ent, blocked = world.entity(r, kind, name)
            _process(st, r, kind, name, ent, blocked=blocked, report=report)
        if own_state:
            st.save()
    return report


def sync_all() -> dict:
    """Every brain that holds a bot, a live agent or a mirror file this machine tracks. Cheap when nothing changed:
    a few SQLite reads per entity and no file write."""
    total: dict = {}
    with _lock:
        st = _State()
        world = _World()
        for root in world.roots(st.roots()):
            for k, v in sync_brain(root, world, st).items():
                total[k] = total.get(k, 0) + v
        st.save()
    return total


def sync_bot(bot_id: str, force: bool = False) -> dict:
    """Export (and import) one bot now. `force` deletes mirror files even if this machine did not write them: used right
    after the owner's "forget", so forgotten chat text leaves the brain at once."""
    report: dict = {}
    with _lock:
        world = _World()
        bot = next((b for b in world.bots or [] if b.get("id") == bot_id), None)
        if bot is None:
            return report
        root, name = _bot_root(bot), _safe_name(bot.get("slug"))
        if not root or not name:
            return report
        ent, blocked = world.entity(root, "bot", name)
        st = _State()
        _process(st, root, "bot", name, ent, blocked=blocked, force=force, report=report)
        st.save()
    return report


def remove_bot(bot: dict) -> int:
    """The bot was deleted: remove its two mirror files (unless another bot of the brain shares the slug)."""
    root, name = _bot_root(bot or {}), _safe_name((bot or {}).get("slug"))
    if not root or not name:
        return 0
    n = 0
    with _lock:
        world = _World()
        if world.bot_ok and (world.bot_by.get(root, {}).get(name) or []):
            return 0
        st = _State()
        for p in _paths(root, "bot", name):
            if _write_or_delete(st, p, None, True) == "deleted":
                n += 1
        st.save()
    return n


def on_bot_created(bot: dict) -> None:
    """A bot was just created: import its mirror right away, before the judge writes anything of its own."""
    try:
        if bot and bot.get("id"):
            sync_bot(str(bot["id"]))
    except Exception as e:  # noqa: BLE001 - creating a bot must not fail because of the mirror
        _log(f"bot import failed: {type(e).__name__}: {e}")


def on_agent_key(brain_id: str, slug: str, agent_key: str) -> None:
    """`resonance_store` minted a key for (brain, slug): import that agent's mirror before it learns anything."""
    try:
        root, name = brain_ident.canonical(brain_id), _safe_name(slug)
        if not root or not name or not os.path.isdir(root):
            return
        with _lock:
            world = _World()
            ent, blocked = world.entity(root, "agent", name)
            if ent is None or ent.ident != agent_key:
                return
            st = _State()
            _process(st, root, "agent", name, ent, blocked=blocked)
            st.save()
    except Exception as e:  # noqa: BLE001 - registering an agent must not fail because of the mirror
        _log(f"agent import failed: {type(e).__name__}: {e}")


def _register_hook() -> None:
    try:
        import resonance_store
        hooks = getattr(resonance_store, "AGENT_KEY_HOOKS", None)
        if hooks is not None and on_agent_key not in hooks:
            hooks.append(on_agent_key)
    except Exception as e:  # noqa: BLE001
        _log(f"hook not registered: {type(e).__name__}: {e}")


_register_hook()
