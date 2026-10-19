"""webhook_store.py - durable receive and dispatch for webhook events (0.229.0, webhook platform M1).

Before this module an accepted event lived only in RAM (a deque per hook): a restart, a crash or an update
between the 202 and the run lost it, while the sender had already been told "accepted" and would not retry.
And the idempotency key was written to webhooks.json BEFORE the queue decided, so a 429 kept the key and the
sender's retry was answered "duplicate" (fixed in 0.229.0; here the key and the event are one transaction).

The rules this store keeps, each checked by tests/python/test_webhook_store_m1.py:

  1. ACK only after commit. `ingest()` writes the event row and its dedup row in ONE transaction; the 202 is
     returned only after that commit. If anything fails before the commit, nothing is kept: no event, no key.
  2. Dedup is (hook, key) -> event, unique in SQLite, so two copies arriving at once (two threads, two
     processes) cannot both be accepted.
  3. Limits stay: at most RATE_PER_HOUR accepted events per hook per hour and at most BACKLOG_MAX events of a
     hook waiting or running. Both are counted from the store, so a restart does not reset them.
  4. A worker CLAIMS an event with a lease and a fencing number (`fence` grows at every claim). Every later
     write of that worker (heartbeat, start, finish) is conditional on its fence, so a worker whose lease ran
     out and was taken over can never overwrite the newer owner's result.
  5. A task or workflow run is an outside effect (the model may send messages, write orders). The store records
     `dispatched_at` (committed) BEFORE calling the runner. A lease that expires after that point does NOT put
     the event back in the queue: it becomes `unknown`, because the run may already have acted. Only the owner
     resolves an unknown event (retry or mark done); nothing retries it blindly. A lease that expires before
     dispatch is safe to run again and goes back to `queued`.
  6. A failure BEFORE dispatch (hook lookup, store) is retried with backoff up to MAX_AUTO_TRIES; a run that
     returned an error is `failed` and is retried only by hand (`retry()`), since it may have acted partly.
  7. An event whose hook was deleted or switched off by the time it runs is `dead` (never run).
  8. The owner notice is sent after the result is committed; `notified_at` marks it done, and a notice lost to
     a crash is sent again at recovery under the same dedup key (the notifier drops a second copy).

States: queued -> running -> done | silent | waiting | failed | unknown | dead.
Nothing here imports main or calls a model.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Iterable, Optional

SCHEMA_VERSION = 1
RATE_PER_HOUR = 30
BACKLOG_MAX = 6               # waiting + running per hook (the old RAM queue: 1 running + QUEUE_MAX=5 waiting)
LEASE_S = 120.0               # a running event's lease; the worker renews it every HEARTBEAT_S
HEARTBEAT_S = 30.0
MAX_AUTO_TRIES = 3            # automatic retries, ONLY for failures before dispatch
BACKOFF_S = (5.0, 30.0, 120.0)
KEEP_DAYS = 30                # finished events kept this long (M5 makes this configurable)
KEEP_PER_HOOK = 500           # and at most this many finished events per hook
DB_MAX_BYTES = 256 * 1024 * 1024   # past this the store refuses new events (503) instead of filling the disk
FINAL = ("done", "silent", "waiting", "failed", "unknown", "dead")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(
    id TEXT PRIMARY KEY,
    hook_id TEXT NOT NULL,
    brain TEXT NOT NULL DEFAULT '',
    received_at REAL NOT NULL,
    content_type TEXT NOT NULL DEFAULT '',
    body BLOB NOT NULL,
    body_sha TEXT NOT NULL,
    idem_key TEXT NOT NULL DEFAULT '',
    hook_snapshot TEXT NOT NULL DEFAULT '{}',
    source TEXT NOT NULL DEFAULT 'http',
    status TEXT NOT NULL,
    tries INTEGER NOT NULL DEFAULT 0,
    next_at REAL NOT NULL DEFAULT 0,
    lease_owner TEXT NOT NULL DEFAULT '',
    lease_until REAL NOT NULL DEFAULT 0,
    fence INTEGER NOT NULL DEFAULT 0,
    dispatched_at REAL NOT NULL DEFAULT 0,
    finished_at REAL NOT NULL DEFAULT 0,
    notified_at REAL NOT NULL DEFAULT 0,
    result TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_ev_claim ON events(status, next_at);
CREATE INDEX IF NOT EXISTS ix_ev_hook ON events(hook_id, received_at);
CREATE TABLE IF NOT EXISTS dedup(
    hook_id TEXT NOT NULL,
    idem_key TEXT NOT NULL,
    event_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY(hook_id, idem_key)
);
CREATE TABLE IF NOT EXISTS attempts(
    event_id TEXT NOT NULL,
    n INTEGER NOT NULL,
    fence INTEGER NOT NULL,
    worker TEXT NOT NULL,
    started_at REAL NOT NULL,
    ended_at REAL NOT NULL DEFAULT 0,
    outcome TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_att_ev ON attempts(event_id, n);
"""


def _crash(point: str) -> None:
    """Fault injection for the crash tests (tests/python/test_webhook_store_m1.py run this module in a child
    process). Does nothing unless JAVIS_WH_CRASH_AT names this exact point."""
    if os.environ.get("JAVIS_WH_CRASH_AT") == point:
        os._exit(77)


class Busy(Exception):
    """The store refused to take an event (disk cap, database locked past the timeout)."""


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(self.path), timeout=10, isolation_level=None, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")      # an ACKed event must survive a power cut
        self._db.execute("PRAGMA busy_timeout=10000")
        with self._lock:
            self._db.executescript(_SCHEMA)
            row = self._db.execute("SELECT v FROM meta WHERE k='schema_version'").fetchone()
            if row is None:
                self._db.execute("INSERT INTO meta(k, v) VALUES('schema_version', ?)", (str(SCHEMA_VERSION),))
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def close(self) -> None:
        with self._lock:
            try:
                self._db.close()
            except Exception:
                pass

    # ── helpers ──
    def _tx(self):
        """BEGIN IMMEDIATE: the write lock is taken at the start, so check-then-insert is atomic across
        processes too (the dedup and the limits are decided inside it)."""
        self._db.execute("BEGIN IMMEDIATE")

    @contextlib.contextmanager
    def _write(self):
        """One write transaction: committed when the block ends (also on `return`), rolled back on any exception,
        so a failure can never leave the shared connection inside an open transaction (which would lock the file
        for every other worker and process)."""
        with self._lock:
            self._tx()
            try:
                yield
            except BaseException:
                try:
                    self._db.execute("ROLLBACK")
                except Exception:
                    pass
                raise
            else:
                self._db.execute("COMMIT")

    def schema_version(self) -> int:
        row = self._db.execute("SELECT v FROM meta WHERE k='schema_version'").fetchone()
        return int(row["v"]) if row else 0

    def size_bytes(self) -> int:
        n = 0
        for suf in ("", "-wal", "-shm"):
            try:
                n += os.path.getsize(str(self.path) + suf)
            except OSError:
                pass
        return n

    # ── receive ──
    def ingest(self, hook: dict, body: bytes, content_type: str, idem_key: str = "", now: Optional[float] = None,
               source: str = "http") -> tuple:
        """Store one event. Returns (code, info):
            (202, {"event_id"})             stored and committed: only now may the caller answer "accepted";
            (200, {"event_id", "duplicate"}) the key was already stored for this hook;
            (429, {"reason": "rate"|"backlog"})  refused, NOTHING stored (no event, no key);
            raises Busy                      the store cannot take it (disk cap, locked): answer 503, keep nothing.
        """
        now = time.time() if now is None else now
        key = str(idem_key or "").strip()[:200]
        hid = str(hook["id"])
        if self.size_bytes() > DB_MAX_BYTES:
            raise Busy("store full")
        snap = {k: hook.get(k) for k in ("name", "brain", "target", "workflow", "text", "level", "chat_id")}
        snap["rev"] = hashlib.sha256(json.dumps(snap, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
        eid = "ev_" + uuid.uuid4().hex[:16]
        with self._lock:
            try:
                self._tx()
            except sqlite3.OperationalError as e:
                raise Busy(str(e))
            try:
                if key:
                    row = self._db.execute("SELECT event_id FROM dedup WHERE hook_id=? AND idem_key=?",
                                           (hid, key)).fetchone()
                    if row is not None:
                        self._db.execute("ROLLBACK")
                        return 200, {"event_id": row["event_id"], "duplicate": True}
                n_hour = self._db.execute("SELECT COUNT(*) FROM events WHERE hook_id=? AND received_at>?",
                                          (hid, now - 3600)).fetchone()[0]
                if n_hour >= RATE_PER_HOUR:
                    self._db.execute("ROLLBACK")
                    return 429, {"reason": "rate"}
                backlog = self._db.execute(
                    "SELECT COUNT(*) FROM events WHERE hook_id=? AND status IN ('queued','running')",
                    (hid,)).fetchone()[0]
                if backlog >= BACKLOG_MAX:
                    self._db.execute("ROLLBACK")
                    return 429, {"reason": "backlog"}
                self._db.execute(
                    "INSERT INTO events(id, hook_id, brain, received_at, content_type, body, body_sha, idem_key,"
                    " hook_snapshot, source, status, next_at) VALUES(?,?,?,?,?,?,?,?,?,?, 'queued', ?)",
                    (eid, hid, str(hook.get("brain") or ""), now, str(content_type or "")[:200], bytes(body),
                     hashlib.sha256(bytes(body)).hexdigest(), key, json.dumps(snap, ensure_ascii=False), source,
                     now))
                if key:
                    self._db.execute("INSERT INTO dedup(hook_id, idem_key, event_id, created_at) VALUES(?,?,?,?)",
                                     (hid, key, eid, now))
                _crash("before_commit")
                self._db.execute("COMMIT")
            except sqlite3.IntegrityError:
                # Another process stored the same key between our SELECT and INSERT (cannot happen under
                # BEGIN IMMEDIATE, kept as a guard): report the stored one.
                self._db.execute("ROLLBACK")
                row = self._db.execute("SELECT event_id FROM dedup WHERE hook_id=? AND idem_key=?",
                                       (hid, key)).fetchone()
                return 200, {"event_id": row["event_id"] if row else "", "duplicate": True}
            except sqlite3.OperationalError as e:
                try:
                    self._db.execute("ROLLBACK")
                except Exception:
                    pass
                raise Busy(str(e))
            except BaseException:
                try:
                    self._db.execute("ROLLBACK")
                except Exception:
                    pass
                raise
        _crash("after_commit")
        return 202, {"event_id": eid}

    def import_legacy_keys(self, hook_id: str, keys: Iterable[str], now: Optional[float] = None) -> int:
        """Keys a pre-0.229.0 hook kept in webhooks.json stay duplicates after the upgrade. They point at no event
        (the old runs were never stored), which `event_id = ''` says."""
        now = time.time() if now is None else now
        n = 0
        with self._write():
            for k in keys:
                k = str(k or "").strip()[:200]
                if k:
                    cur = self._db.execute("INSERT OR IGNORE INTO dedup(hook_id, idem_key, event_id, created_at)"
                                           " VALUES(?,?,'',?)", (hook_id, k, now))
                    n += cur.rowcount
        return n

    # ── work ──
    def claim(self, worker: str, now: Optional[float] = None) -> Optional[dict]:
        """Take the oldest runnable event whose hook has nothing else running. Returns the row with the new
        `fence`, or None. One event per hook at a time, as before."""
        now = time.time() if now is None else now
        with self._write():
            row = self._db.execute(
                "SELECT * FROM events e WHERE e.status='queued' AND e.next_at<=? AND NOT EXISTS ("
                " SELECT 1 FROM events r WHERE r.hook_id=e.hook_id AND r.status='running' AND r.lease_until>?)"
                " ORDER BY e.received_at, e.id LIMIT 1", (now, now)).fetchone()
            if row is None:
                return None
            fence = int(row["fence"]) + 1
            tries = int(row["tries"]) + 1
            self._db.execute("UPDATE events SET status='running', lease_owner=?, lease_until=?, fence=?, tries=?"
                             " WHERE id=?", (worker, now + LEASE_S, fence, tries, row["id"]))
            self._db.execute("INSERT INTO attempts(event_id, n, fence, worker, started_at) VALUES(?,?,?,?,?)",
                             (row["id"], tries, fence, worker, now))
        d = dict(row)
        d.update(status="running", lease_owner=worker, fence=fence, tries=tries)
        return d

    def _fenced(self, sql: str, args: tuple, eid: str, fence: int) -> bool:
        with self._lock:
            cur = self._db.execute(sql + " WHERE id=? AND fence=? AND status='running'", args + (eid, fence))
            return cur.rowcount == 1

    def heartbeat(self, eid: str, fence: int, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        return self._fenced("UPDATE events SET lease_until=?", (now + LEASE_S,), eid, fence)

    def mark_dispatched(self, eid: str, fence: int, now: Optional[float] = None) -> bool:
        """Committed BEFORE the runner is called. False = this worker lost the event: do NOT run it."""
        now = time.time() if now is None else now
        return self._fenced("UPDATE events SET dispatched_at=?", (now,), eid, fence)

    def finish(self, eid: str, fence: int, status: str, result: str = "", error: str = "",
               now: Optional[float] = None) -> bool:
        """Final state for this attempt. False = a newer owner holds the event; this result is dropped."""
        assert status in FINAL
        now = time.time() if now is None else now
        with self._write():
            cur = self._db.execute(
                "UPDATE events SET status=?, result=?, error=?, finished_at=?, lease_owner='', lease_until=0"
                " WHERE id=? AND fence=? AND status='running'",
                (status, str(result or "")[:4000], str(error or "")[:2000], now, eid, fence))
            ok = cur.rowcount == 1
            if ok:
                self._db.execute("UPDATE attempts SET ended_at=?, outcome=?, error=? WHERE event_id=? AND fence=?",
                                 (now, status, str(error or "")[:500], eid, fence))
        return ok

    def requeue_before_dispatch(self, eid: str, fence: int, error: str, now: Optional[float] = None) -> str:
        """A failure before the runner was called: safe to try again. Back off, or `dead` after MAX_AUTO_TRIES.
        Returns the new status ('' if this worker no longer owns the event)."""
        now = time.time() if now is None else now
        with self._write():
            row = self._db.execute("SELECT tries, dispatched_at FROM events WHERE id=? AND fence=? AND"
                                   " status='running'", (eid, fence)).fetchone()
            if row is None:
                return ""
            if row["dispatched_at"]:
                raise ValueError("already dispatched: use finish(..., 'failed')")
            tries = int(row["tries"])
            if tries >= MAX_AUTO_TRIES:
                st, nxt = "dead", 0.0
            else:
                st, nxt = "queued", now + BACKOFF_S[min(tries - 1, len(BACKOFF_S) - 1)]
            self._db.execute("UPDATE events SET status=?, next_at=?, error=?, lease_owner='', lease_until=0,"
                             " finished_at=? WHERE id=?",
                             (st, nxt, str(error)[:2000], now if st == "dead" else 0, eid))
            self._db.execute("UPDATE attempts SET ended_at=?, outcome=?, error=? WHERE event_id=? AND fence=?",
                             (now, "retry" if st == "queued" else "dead", str(error)[:500], eid, fence))
        return st

    def recover(self, now: Optional[float] = None) -> dict:
        """Expired leases (a worker died or hung). Not yet dispatched -> queued again. Dispatched -> unknown:
        the run may have acted, so it is NOT re-run on its own. Returns counts."""
        now = time.time() if now is None else now
        with self._write():
            rows = self._db.execute("SELECT id, fence, dispatched_at FROM events WHERE status='running' AND"
                                    " lease_until<=?", (now,)).fetchall()
            back = unknown = 0
            for r in rows:
                if r["dispatched_at"]:
                    self._db.execute("UPDATE events SET status='unknown', finished_at=?, lease_owner='',"
                                     " lease_until=0, error=? WHERE id=?",
                                     (now, "lease expired after dispatch: the run may have acted", r["id"]))
                    outcome = "unknown"
                    unknown += 1
                else:
                    self._db.execute("UPDATE events SET status='queued', next_at=?, lease_owner='', lease_until=0"
                                     " WHERE id=?", (now, r["id"]))
                    outcome = "lease_expired"
                    back += 1
                self._db.execute("UPDATE attempts SET ended_at=?, outcome=? WHERE event_id=? AND fence=?",
                                 (now, outcome, r["id"], r["fence"]))
        return {"requeued": back, "unknown": unknown}

    def has_claimable(self, now: Optional[float] = None) -> bool:
        """Is there an event this or another worker could claim right now (same rule as claim)?"""
        now = time.time() if now is None else now
        return self._db.execute(
            "SELECT 1 FROM events e WHERE e.status='queued' AND e.next_at<=? AND NOT EXISTS ("
            " SELECT 1 FROM events r WHERE r.hook_id=e.hook_id AND r.status='running' AND r.lease_until>?) LIMIT 1",
            (now, now)).fetchone() is not None

    def mark_notified(self, eid: str, now: Optional[float] = None) -> None:
        with self._lock:
            self._db.execute("UPDATE events SET notified_at=? WHERE id=?", (time.time() if now is None else now, eid))

    def unnotified(self, limit: int = 50) -> list:
        """Finished events whose owner notice was never confirmed (a crash between commit and notice)."""
        rows = self._db.execute("SELECT * FROM events WHERE status IN ('done','waiting','failed','unknown','dead')"
                                " AND notified_at=0 AND finished_at>0 ORDER BY finished_at LIMIT ?",
                                (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ── owner actions ──
    def retry(self, eid: str, now: Optional[float] = None) -> tuple:
        """The owner asks to run an event again (failed, unknown, dead). Returns (ok, error_code)."""
        now = time.time() if now is None else now
        with self._write():
            row = self._db.execute("SELECT status FROM events WHERE id=?", (eid,)).fetchone()
            if row is None:
                return False, "not_found"
            if row["status"] not in ("failed", "unknown", "dead"):
                return False, "not_retryable"
            self._db.execute("UPDATE events SET status='queued', next_at=?, dispatched_at=0, finished_at=0,"
                             " notified_at=0, error='', result='' WHERE id=?", (now, eid))
        return True, ""

    def resolve(self, eid: str, outcome: str, note: str = "", now: Optional[float] = None) -> tuple:
        """Reconcile an `unknown` event after checking the outside system: it did happen (done) or not (failed,
        which can then be retried). Returns (ok, error_code)."""
        if outcome not in ("done", "failed"):
            return False, "bad_outcome"
        now = time.time() if now is None else now
        with self._write():
            cur = self._db.execute("UPDATE events SET status=?, result=CASE WHEN ?='' THEN result ELSE ? END,"
                                   " finished_at=?, notified_at=? WHERE id=? AND status='unknown'",
                                   (outcome, note, str(note)[:1000], now, now, eid))
        return (True, "") if cur.rowcount == 1 else (False, "not_unknown")

    # ── reading ──
    def get(self, eid: str, with_body: bool = False) -> Optional[dict]:
        row = self._db.execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        if not with_body:
            d.pop("body", None)
        d["attempts"] = [dict(a) for a in self._db.execute(
            "SELECT n, fence, worker, started_at, ended_at, outcome, error FROM attempts WHERE event_id=? ORDER BY n",
            (eid,)).fetchall()]
        return d

    def page(self, hook_id: str = "", status: str = "", limit: int = 20, before: str = "") -> dict:
        """Newest first, keyset pagination: `before` is the `cursor` of the previous page."""
        limit = max(1, min(int(limit or 20), 100))
        where, args = [], []
        if hook_id:
            where.append("hook_id=?"); args.append(hook_id)
        if status:
            where.append("status=?"); args.append(status)
        if before:
            try:
                ts, eid = before.split("|", 1)
                where.append("(received_at<? OR (received_at=? AND id<?))"); args += [float(ts), float(ts), eid]
            except ValueError:
                pass
        sql = ("SELECT id, hook_id, brain, received_at, status, tries, idem_key, source, dispatched_at, finished_at,"
               " result, error, length(body) AS size FROM events" + (" WHERE " + " AND ".join(where) if where else "")
               + " ORDER BY received_at DESC, id DESC LIMIT ?")
        rows = [dict(r) for r in self._db.execute(sql, args + [limit + 1]).fetchall()]
        more = len(rows) > limit
        rows = rows[:limit]
        cur = f"{rows[-1]['received_at']}|{rows[-1]['id']}" if more and rows else ""
        return {"items": rows, "next": cur}

    def counts(self, hook_id: str) -> dict:
        rows = self._db.execute("SELECT status, COUNT(*) AS n FROM events WHERE hook_id=? GROUP BY status",
                                (hook_id,)).fetchall()
        return {r["status"]: r["n"] for r in rows}

    def last(self, hook_id: str) -> Optional[dict]:
        row = self._db.execute("SELECT status, finished_at, received_at FROM events WHERE hook_id=?"
                               " ORDER BY received_at DESC, id DESC LIMIT 1", (hook_id,)).fetchone()
        return dict(row) if row else None

    def forget_hook(self, hook_id: str) -> None:
        """A deleted hook: its waiting events become `dead` (they will never run), its keys are dropped."""
        now = time.time()
        with self._write():
            self._db.execute("UPDATE events SET status='dead', finished_at=?, notified_at=?, error='hook deleted'"
                             " WHERE hook_id=? AND status='queued'", (now, now, hook_id))
            self._db.execute("DELETE FROM dedup WHERE hook_id=?", (hook_id,))

    def prune(self, now: Optional[float] = None) -> int:
        """Finished events older than KEEP_DAYS, and past KEEP_PER_HOOK per hook. Dedup keys of pruned events go
        with them; keys of events still kept stay (a late retry is still a duplicate)."""
        now = time.time() if now is None else now
        cut = now - KEEP_DAYS * 86400
        fin = "('done','silent','waiting','failed','dead')"   # unknown is kept until the owner resolves it
        with self._write():
            ids = [r[0] for r in self._db.execute(
                f"SELECT id FROM events WHERE status IN {fin} AND finished_at>0 AND finished_at<?", (cut,))]
            for (hid,) in self._db.execute("SELECT DISTINCT hook_id FROM events").fetchall():
                ids += [r[0] for r in self._db.execute(
                    f"SELECT id FROM events WHERE hook_id=? AND status IN {fin} ORDER BY received_at DESC"
                    " LIMIT -1 OFFSET ?", (hid, KEEP_PER_HOOK))]
            ids = list(dict.fromkeys(ids))
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                q = ",".join("?" * len(chunk))
                self._db.execute(f"DELETE FROM attempts WHERE event_id IN ({q})", chunk)
                self._db.execute(f"DELETE FROM dedup WHERE event_id IN ({q})", chunk)
                self._db.execute(f"DELETE FROM events WHERE id IN ({q})", chunk)
            self._db.execute("DELETE FROM dedup WHERE event_id='' AND created_at<?", (cut,))
        return len(ids)
