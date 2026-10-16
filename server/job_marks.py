"""Owner marks on finished jobs (0.193.0): "done, reviewed" moves a job to the archive, deleting from the archive hides it.

Owner, 16/10/2026: finished work must stay visible in the Jobs lists until the owner presses Done; Done only moves it to an
Archive inside the same list (nothing is deleted, the history stays for review); only from the Archive can the owner delete
one job or clear them all. The jobs themselves live in their own stores (team queue, Kanban, Auto goals) and are never
touched here: this store only remembers what the owner did with each finished job, by the job id the Jobs lists already
use ("team:<task>", "kanban:<task>", "auto:<goal>"), per brain.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Dict, Iterable, Optional

STATES = ("archived", "deleted")
MAX_IDS = 500

_lock = threading.Lock()
_path: Optional[Path] = None


def configure(path) -> None:
    global _path
    _path = Path(path)


def _conn() -> sqlite3.Connection:
    if _path is None:
        raise RuntimeError("job_marks not configured")
    c = sqlite3.connect(str(_path), timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE IF NOT EXISTS job_marks(brain TEXT NOT NULL, job_id TEXT NOT NULL, state TEXT NOT NULL, "
              "at REAL NOT NULL, PRIMARY KEY(brain, job_id))")
    return c


def marks(brain: str) -> Dict[str, dict]:
    """{job_id: {"state", "at"}} for one brain."""
    with _lock, closing(_conn()) as c:
        return {r["job_id"]: {"state": r["state"], "at": r["at"]}
                for r in c.execute("SELECT job_id, state, at FROM job_marks WHERE brain=?", (str(brain),))}


def set_state(brain: str, ids: Iterable[str], state: str) -> int:
    """Mark jobs `archived` or `deleted`; an empty state takes the mark off (back to the list). Returns rows changed."""
    ids = [str(i) for i in list(ids or [])[:MAX_IDS] if str(i or "").strip()]
    if not ids:
        return 0
    if state and state not in STATES:
        raise ValueError("state")
    now = time.time()
    with _lock, closing(_conn()) as c:
        with c:
            if not state:
                return c.executemany("DELETE FROM job_marks WHERE brain=? AND job_id=?",
                                     [(str(brain), i) for i in ids]).rowcount
            return c.executemany("INSERT INTO job_marks(brain, job_id, state, at) VALUES(?,?,?,?) "
                                 "ON CONFLICT(brain, job_id) DO UPDATE SET state=excluded.state, at=excluded.at",
                                 [(str(brain), i, state, now) for i in ids]).rowcount


def split(jobs: list, mk: Dict[str, dict], done_bucket: str = "done", archive_max: int = 50):
    """(kept, archived): deleted jobs dropped, archived FINISHED jobs moved out (newest archive first). A job that is
    not finished any more (retried, reopened) ignores an old archive mark and comes back to the list."""
    kept, archived = [], []
    for j in jobs:
        m = mk.get(j.get("id")) or {}
        st = m.get("state")
        if st == "deleted" and j.get("bucket") == done_bucket:
            continue
        if st == "archived" and j.get("bucket") == done_bucket:
            archived.append(dict(j, archived_at=m.get("at")))
            continue
        kept.append(j)
    archived.sort(key=lambda j: -(j.get("archived_at") or 0))
    return kept, archived[:archive_max]
