"""Durable state of GitHub work per conversation and repo (spec docs/dev/2026-10-github-trong-chat-spec.md, section 14).

One row per (conversation, repo): its branch, the commit Javis last pushed, the PR, and three SEPARATE state fields
(section 12.1) from which the status icons are computed:

    exec   idle | running | done | stuck            what Javis is doing on it right now
    ci     none | pending | running | green | red | no_ci | cancelled    for the pushed commit ONLY
    integ  no_pr | pr_open | ready | merged | conflict | merge_failed
    post_merge  "" | pending | green | red      checks of the merge commit on the base branch

Never one field for everything: a merged PR whose post-merge check failed keeps `merged` AND shows the warning.

`steps` makes every outward action idempotent (push of a SHA, PR creation, a fix round for a SHA, a merge): an event
that repeats, or a restart in the middle, finds the step already recorded and does not do it twice. `checks` keeps the
check runs seen per SHA, so a result is always tied to the commit it belongs to. `metrics` is filled in phase G5.

SQLite in WAL mode, one connection guarded by a lock, like task_store. No FastAPI, no main import.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import STATE_DIR

DB_PATH = STATE_DIR / "github_work.db"

EXEC = ("idle", "running", "done", "stuck")
CI = ("none", "pending", "running", "green", "red", "no_ci", "cancelled")
INTEG = ("no_pr", "pr_open", "ready", "merged", "conflict", "merge_failed")
POST_MERGE = ("", "pending", "green", "red")

_COLS = ("sid", "full_name", "brain", "branch", "worktree", "base_branch", "head_sha", "pushed_at",
         "pr_number", "pr_url", "pr_node_id", "exec", "ci", "integ", "stuck_reason", "fix_rounds",
         "rerun_used", "merge_block", "gate", "checks_summary", "merged_sha", "post_merge", "title", "engine", "model",
         "notified", "created_at", "updated_at")


class Store:
    def __init__(self, path: Path = DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(self.path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=5000")
        self._schema()

    def _schema(self) -> None:
        with self._lock:
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS work (
                    sid TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    brain TEXT NOT NULL DEFAULT '',
                    branch TEXT NOT NULL DEFAULT '',
                    worktree TEXT NOT NULL DEFAULT '',
                    base_branch TEXT NOT NULL DEFAULT '',
                    head_sha TEXT NOT NULL DEFAULT '',
                    pushed_at REAL NOT NULL DEFAULT 0,
                    pr_number INTEGER NOT NULL DEFAULT 0,
                    pr_url TEXT NOT NULL DEFAULT '',
                    pr_node_id TEXT NOT NULL DEFAULT '',
                    exec TEXT NOT NULL DEFAULT 'idle',
                    ci TEXT NOT NULL DEFAULT 'none',
                    integ TEXT NOT NULL DEFAULT 'no_pr',
                    stuck_reason TEXT NOT NULL DEFAULT '',
                    fix_rounds INTEGER NOT NULL DEFAULT 0,
                    rerun_used INTEGER NOT NULL DEFAULT 0,
                    merge_block TEXT NOT NULL DEFAULT '[]',
                    gate TEXT NOT NULL DEFAULT '{}',
                    checks_summary TEXT NOT NULL DEFAULT '[]',
                    merged_sha TEXT NOT NULL DEFAULT '',
                    post_merge TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    engine TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT '',
                    notified TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (sid, full_name)
                );
                CREATE TABLE IF NOT EXISTS steps (
                    key TEXT PRIMARY KEY,
                    done_at REAL NOT NULL,
                    result TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS checks (
                    full_name TEXT NOT NULL,
                    sha TEXT NOT NULL,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT '',
                    conclusion TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL DEFAULT '',
                    job_id INTEGER NOT NULL DEFAULT 0,
                    seen_at REAL NOT NULL,
                    PRIMARY KEY (full_name, sha, name)
                );
                CREATE TABLE IF NOT EXISTS queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sid TEXT NOT NULL,
                    text TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'waiting',
                    created_at REAL NOT NULL,
                    started_at REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sid TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    engine TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT '',
                    first_push_green INTEGER NOT NULL DEFAULT 0,
                    fix_rounds INTEGER NOT NULL DEFAULT 0,
                    review_findings INTEGER NOT NULL DEFAULT 0,
                    seconds REAL NOT NULL DEFAULT 0,
                    outcome TEXT NOT NULL DEFAULT '',
                    at REAL NOT NULL
                );
                """
            )
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # ---- work rows ----
    @staticmethod
    def _row(r: sqlite3.Row) -> Dict[str, Any]:
        d = dict(r)
        for k in ("merge_block", "checks_summary"):
            try:
                d[k] = json.loads(d.get(k) or "[]")
            except ValueError:
                d[k] = []
        try:
            d["gate"] = json.loads(d.get("gate") or "{}")
        except ValueError:
            d["gate"] = {}
        return d

    def get(self, sid: str, full_name: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            r = self._db.execute("SELECT * FROM work WHERE sid=? AND full_name=?", (sid, full_name)).fetchone()
        return self._row(r) if r else None

    def ensure(self, sid: str, full_name: str, **fields) -> Dict[str, Any]:
        now = time.time()
        with self._lock:
            self._db.execute("INSERT OR IGNORE INTO work (sid, full_name, created_at, updated_at) VALUES (?,?,?,?)",
                             (sid, full_name, now, now))
            self._db.commit()
        if fields:
            return self.update(sid, full_name, **fields)
        return self.get(sid, full_name) or {}

    def update(self, sid: str, full_name: str, **fields) -> Dict[str, Any]:
        sets, vals = [], []
        for k, v in fields.items():
            if k not in _COLS or k in ("sid", "full_name", "created_at"):
                raise KeyError(k)
            if (k == "exec" and v not in EXEC or k == "ci" and v not in CI or k == "integ" and v not in INTEG
                    or k == "post_merge" and v not in POST_MERGE):
                raise ValueError(f"{k}={v}")
            if k in ("merge_block", "checks_summary", "gate"):
                v = json.dumps(v, ensure_ascii=False)
            sets.append(f"{k}=?")
            vals.append(v)
        sets.append("updated_at=?")
        vals.append(time.time())
        with self._lock:
            self._db.execute(f"UPDATE work SET {', '.join(sets)} WHERE sid=? AND full_name=?",
                             (*vals, sid, full_name))
            self._db.commit()
        return self.get(sid, full_name) or {}

    def for_session(self, sid: str) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM work WHERE sid=? ORDER BY created_at", (sid,)).fetchall()
        return [self._row(r) for r in rows]

    def active(self) -> List[Dict[str, Any]]:
        """Rows the watcher must look at: a pushed commit whose CI or PR is not settled yet."""
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM work WHERE head_sha != '' AND (ci IN ('pending','running') OR "
                "integ IN ('pr_open','ready') OR (integ='merged' AND post_merge='pending'))").fetchall()
        return [self._row(r) for r in rows]

    def for_repo(self, brain: str, full_name: str) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM work WHERE brain=? AND lower(full_name)=lower(?)",
                                    (brain, full_name)).fetchall()
        return [self._row(r) for r in rows]

    def sessions(self, sids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """Rows of many sessions at once (the chat list draws an icon per conversation)."""
        out: Dict[str, List[Dict[str, Any]]] = {}
        ids = [s for s in sids if s][:500]
        if not ids:
            return out
        with self._lock:
            rows = self._db.execute(f"SELECT * FROM work WHERE sid IN ({','.join('?' * len(ids))})", ids).fetchall()
        for r in rows:
            d = self._row(r)
            out.setdefault(d["sid"], []).append(d)
        return out

    def delete_session(self, sid: str) -> None:
        with self._lock:
            self._db.execute("DELETE FROM work WHERE sid=?", (sid,))
            self._db.execute("DELETE FROM queue WHERE sid=?", (sid,))
            self._db.commit()

    # ---- steps (idempotency) ----
    def step_done(self, key: str) -> bool:
        with self._lock:
            return self._db.execute("SELECT 1 FROM steps WHERE key=?", (key,)).fetchone() is not None

    def mark_step(self, key: str, result: str = "") -> bool:
        """Record a step. Returns False when it was already recorded (someone else did it first)."""
        with self._lock:
            cur = self._db.execute("INSERT OR IGNORE INTO steps (key, done_at, result) VALUES (?,?,?)",
                                   (key, time.time(), result))
            self._db.commit()
            return cur.rowcount == 1

    # ---- checks ----
    def save_checks(self, full_name: str, sha: str, runs: List[Dict[str, Any]]) -> None:
        now = time.time()
        with self._lock:
            for r in runs:
                self._db.execute(
                    "INSERT INTO checks (full_name, sha, name, status, conclusion, url, job_id, seen_at) "
                    "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(full_name, sha, name) DO UPDATE SET "
                    "status=excluded.status, conclusion=excluded.conclusion, url=excluded.url, "
                    "job_id=excluded.job_id, seen_at=excluded.seen_at",
                    (full_name, sha, r.get("name") or "", r.get("status") or "", r.get("conclusion") or "",
                     r.get("url") or "", int(r.get("job_id") or 0), now))
            self._db.commit()

    def checks(self, full_name: str, sha: str) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM checks WHERE full_name=? AND sha=? ORDER BY name",
                                    (full_name, sha)).fetchall()
        return [dict(r) for r in rows]

    # ---- next jobs (spec 11.2): what the person asked to do once this chat's PRs are merged ----
    def queue_add(self, sid: str, text: str) -> int:
        with self._lock:
            cur = self._db.execute("INSERT INTO queue (sid, text, created_at) VALUES (?,?,?)", (sid, text, time.time()))
            self._db.commit()
            return int(cur.lastrowid)

    def queue_list(self, sid: str, state: str = "waiting") -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM queue WHERE sid=? AND state=? ORDER BY id", (sid, state)).fetchall()
        return [dict(r) for r in rows]

    def queue_take(self, sid: str) -> Optional[Dict[str, Any]]:
        """The oldest waiting job of a chat, marked started in the same transaction (never handed out twice)."""
        with self._lock:
            r = self._db.execute("SELECT * FROM queue WHERE sid=? AND state='waiting' ORDER BY id LIMIT 1",
                                 (sid,)).fetchone()
            if not r:
                return None
            cur = self._db.execute("UPDATE queue SET state='started', started_at=? WHERE id=? AND state='waiting'",
                                   (time.time(), r["id"]))
            self._db.commit()
            return dict(r) if cur.rowcount == 1 else None

    def queue_cancel(self, sid: str, qid: int) -> bool:
        with self._lock:
            cur = self._db.execute("UPDATE queue SET state='cancelled' WHERE sid=? AND id=? AND state='waiting'",
                                   (sid, int(qid)))
            self._db.commit()
            return cur.rowcount == 1

    # ---- metrics (G5) ----
    def add_metric(self, **m) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO metrics (sid, full_name, engine, model, first_push_green, fix_rounds, review_findings, "
                "seconds, outcome, at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (m.get("sid", ""), m.get("full_name", ""), m.get("engine", ""), m.get("model", ""),
                 int(bool(m.get("first_push_green"))), int(m.get("fix_rounds") or 0),
                 int(m.get("review_findings") or 0), float(m.get("seconds") or 0), m.get("outcome", ""),
                 time.time()))
            self._db.commit()

    def metrics(self, full_name: str = "") -> List[Dict[str, Any]]:
        q = "SELECT * FROM metrics" + (" WHERE lower(full_name)=lower(?)" if full_name else "") + " ORDER BY at DESC LIMIT 500"
        with self._lock:
            rows = self._db.execute(q, (full_name,) if full_name else ()).fetchall()
        return [dict(r) for r in rows]


_STORE: Optional[Store] = None
_STORE_LOCK = threading.Lock()


def store() -> Store:
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = Store()
        return _STORE


def icon(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The conversation's icon from its rows (spec 12.1). Worst state wins; running work shows with its count.

    Returns {state, running, merged_warning}. state: "" (no GitHub work), working, ready, merged, broken.
    Secondary marks ride along in `sub`: waiting_ci, waiting_review, stuck.
    """
    if not rows:
        return {"state": "", "running": 0, "sub": "", "merged_warning": False}
    running = sum(1 for r in rows if r["exec"] == "running" or r["ci"] in ("pending", "running"))
    broken = [r for r in rows if r["integ"] in ("conflict", "merge_failed")]
    stuck = [r for r in rows if r["exec"] == "stuck"]
    if broken or stuck:
        state = "broken"       # a person is needed: never hide it behind "ready" or "working"
    elif running:
        state = "working"
    elif all(r["integ"] == "merged" for r in rows):
        state = "merged"
    elif rows and all(r["integ"] in ("ready", "merged") for r in rows):
        state = "ready"
    else:
        state = "working" if any(r["head_sha"] for r in rows) else ""
    sub = "stuck" if stuck else ("waiting_ci" if any(r["ci"] in ("pending", "running") for r in rows) else
                                 ("waiting_review" if any(r["integ"] == "ready" for r in rows) else ""))
    return {"state": state, "running": running, "sub": sub,
            "merged_warning": any(r["integ"] == "merged" and r.get("post_merge") == "red" for r in rows)}
