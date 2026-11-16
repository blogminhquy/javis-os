"""Chat turns in flight, kept on disk so a restart does not lose them (16/11/2026).

Why this file exists
====================
Owner, 16/11/2026: "Những việc nào đang dang dở kể cả ở cộng sự, ở chat hay team và workflow, khởi động lại server sau
khi update cũng phải khởi động lại tất cả các tiến trình". Before this a chat turn that was still answering when the
server stopped left nothing behind: the question was stored, the answer was not, no marker said a turn had been running,
and after the restart the question sat there with no answer and no notice. The book of running turns
(`luot_dang_chay`, `chat_runtime`) lives in memory only.

What it does
============
One row per chat session whose turn is running: which stored user message it answers, the exact text the turn was
given, the brain. `begin` writes it when the turn starts, `end` removes it when the turn ends in any way the process
lives to see (answer, error, the owner's Stop). A row that carries the id of an EARLIER process is a turn the restart
cut short. `take_cut` hands those rows out once; the chat host (main.py) runs each one again as an ordinary chat job.

Two guards, the same two the team runner uses (team_runner.RESTART_RESUME_MAX, once_ledger.py):

- `acted`: the turn already called a tool that does something outside (send, post, order: every hub call that is not a
  read). Running it again could do that twice, so such a turn is NOT run again; the chat gets a line saying so.
- `resumes`: how many times a restart already cut this same question. Past MAX_RESUMES it is not run again: a server
  that keeps dying on one question must not burn the plan's quota for ever.

A clean stop cancels the running turns, and a cancelled turn ends like any other. `closing` is set by the server's
shutdown hook first, so those rows stay for the next process.

No FastAPI and no main import: sqlite3 only, so a bare test can drive it.
"""
from __future__ import annotations

import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

# One id per process: a row with another id belongs to a process that is gone.
BOOT = secrets.token_hex(8)
MAX_RESUMES = 2
# A cut turn older than this is not run again: the owner has long since moved on, and an answer that pops up a day
# later reads like a new message out of nowhere.
MAX_AGE_S = 6 * 3600
_TEXT_MAX = 200_000

closing = False

_lock = threading.Lock()
_db: Optional[sqlite3.Connection] = None
_path: Optional[Path] = None


def resume_on() -> bool:
    """JAVIS_RESUME_AFTER_RESTART=0 gives the old behaviour back (the same switch as the team runner's)."""
    return str(os.environ.get("JAVIS_RESUME_AFTER_RESTART", "1")).strip().lower() not in ("0", "false", "off", "no")


def configure(path) -> None:
    """Point the ledger at a file (tests, or a state dir chosen by the host). Closes the file open before."""
    global _db, _path
    with _lock:
        if _db is not None:
            try:
                _db.close()
            except Exception:  # noqa: BLE001
                pass
        _db = None
        _path = Path(path)


def _conn() -> sqlite3.Connection:
    global _db, _path
    if _db is None:
        if _path is None:
            from config import STATE_DIR
            _path = Path(STATE_DIR) / "turn_ledger.sqlite3"
        _path.parent.mkdir(parents=True, exist_ok=True)
        _db = sqlite3.connect(str(_path), check_same_thread=False)
        _db.row_factory = sqlite3.Row
        _db.execute("PRAGMA journal_mode=WAL")
        _db.execute("PRAGMA busy_timeout=5000")
        _db.executescript(
            """
            CREATE TABLE IF NOT EXISTS turns (
                session_id TEXT PRIMARY KEY,
                user_mid INTEGER NOT NULL DEFAULT 0,
                user_message TEXT NOT NULL DEFAULT '',
                user_text TEXT,
                brain TEXT NOT NULL DEFAULT '',
                boot TEXT NOT NULL DEFAULT '',
                acted INTEGER NOT NULL DEFAULT 0,
                resumes INTEGER NOT NULL DEFAULT 0,
                started_at REAL NOT NULL
            );
            """
        )
        _db.commit()
    return _db


def begin(session_id: str, user_mid: int, user_message: str, user_text: Optional[str], brain: str) -> None:
    """A turn of this session starts. The same question running again (after a cut) keeps its count of resumes."""
    sid = str(session_id or "")
    if not sid:
        return
    try:
        with _lock:
            _conn().execute(
                """INSERT INTO turns(session_id, user_mid, user_message, user_text, brain, boot, acted, resumes, started_at)
                   VALUES (?,?,?,?,?,?,0,0,?)
                   ON CONFLICT(session_id) DO UPDATE SET
                     resumes=CASE WHEN turns.user_mid=excluded.user_mid AND excluded.user_mid<>0 THEN turns.resumes ELSE 0 END,
                     user_mid=excluded.user_mid, user_message=excluded.user_message, user_text=excluded.user_text,
                     brain=excluded.brain, boot=excluded.boot, acted=0, started_at=excluded.started_at""",
                (sid, int(user_mid or 0), str(user_message or "")[:_TEXT_MAX],
                 None if user_text is None else str(user_text)[:_TEXT_MAX], str(brain or ""), BOOT, time.time()))
            _conn().commit()
    except Exception:  # noqa: BLE001 - the ledger must never stop a turn from running
        pass


def end(session_id: str) -> None:
    """The turn ended while the process lives: nothing to resume. Kept during shutdown (see `closing`)."""
    if closing or not session_id:
        return
    try:
        with _lock:
            _conn().execute("DELETE FROM turns WHERE session_id=? AND boot=?", (str(session_id), BOOT))
            _conn().commit()
    except Exception:  # noqa: BLE001
        pass


def mark_acted(session_id: str) -> None:
    """The running turn of this session just called a tool that acts outside. No row (not a chat turn): nothing."""
    if not session_id:
        return
    try:
        with _lock:
            _conn().execute("UPDATE turns SET acted=1 WHERE session_id=? AND boot=? AND acted=0",
                            (str(session_id), BOOT))
            _conn().commit()
    except Exception:  # noqa: BLE001
        pass


def take_cut() -> list[dict]:
    """Turns a restart cut short, each handed out ONCE: the row moves to this process and its count of resumes goes
    up, so a second page connecting right after gets nothing, and a turn that keeps getting cut is counted. `resumes`
    in the returned row is the count BEFORE this one. Rows too old to answer are dropped here."""
    try:
        with _lock:
            c = _conn()
            rows = [dict(r) for r in c.execute("SELECT * FROM turns WHERE boot<>? ORDER BY started_at", (BOOT,)).fetchall()]
            if rows:
                c.execute("DELETE FROM turns WHERE boot<>? AND started_at<?", (BOOT, time.time() - MAX_AGE_S))
                c.execute("UPDATE turns SET boot=?, resumes=resumes+1 WHERE boot<>?", (BOOT, BOOT))
                c.commit()
        cut = time.time() - MAX_AGE_S
        return [r for r in rows if float(r.get("started_at") or 0) >= cut]
    except Exception:  # noqa: BLE001
        return []


def drop(session_id: str) -> None:
    """Forget this session's row whatever process wrote it (the cut turn is not going to run again)."""
    try:
        with _lock:
            _conn().execute("DELETE FROM turns WHERE session_id=?", (str(session_id or ""),))
            _conn().commit()
    except Exception:  # noqa: BLE001
        pass


def rows() -> list[dict]:
    """Every row, for tests and the health page."""
    try:
        with _lock:
            return [dict(r) for r in _conn().execute("SELECT * FROM turns ORDER BY started_at").fetchall()]
    except Exception:  # noqa: BLE001
        return []
