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
M2 (webhook_rules.py) adds three states decided AT RECEIPT, which never run and never notify the owner:
`filtered` (the hook's filter did not match), `invalid` (schema or mapping failed) and `duplicate` (the business
key was already seen in its namespace within its TTL). They are stored, with their trace, so the owner can see why
an event did not run, but they do not count toward the hourly rate and have their own cap (IGNORED_PER_HOUR).
Business keys live in `biz_keys`, scoped by (brain, namespace), written in the SAME transaction as the event.
M3 (webhook_actions.py): an event runs as independent BRANCHES, one per action of the hook, in `branches`. Each
branch has its own dispatch mark, outcome and stable delivery id; a retry runs only the branches that failed or are
unknown, never one that completed. Recovery decides per branch: dispatched and unfinished -> unknown, not started ->
the event goes back to the queue for the rest.
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

SCHEMA_VERSION = 6
RATE_PER_HOUR = 30
BACKLOG_MAX = 6               # waiting + running per hook (the old RAM queue: 1 running + QUEUE_MAX=5 waiting)
LEASE_S = 120.0               # a running event's lease; the worker renews it every HEARTBEAT_S
HEARTBEAT_S = 30.0
MAX_AUTO_TRIES = 3            # automatic retries, ONLY for failures before dispatch
BACKOFF_S = (5.0, 30.0, 120.0)
KEEP_DAYS = 30                # finished events kept this long (M5 makes this configurable)
KEEP_PER_HOOK = 500           # and at most this many finished events per hook
KEEP_DAYS_MAX = 365           # M5: a hook may keep its log up to this long (retention_days)
BODY_KEEP_DAYS = 7            # the body of a FINISHED event is emptied after this (the row and its log stay)
DEDUP_KEEP_DAYS = 7           # idempotency keys outlive their events (Stripe/Shopify retry for up to 72 h)
DB_MAX_BYTES = 256 * 1024 * 1024   # LIVE data (not free pages, not the WAL) past this: evict, then refuse (503)
NOTIFY_TRIES = 3              # owner notice attempts before giving up (the event log still shows the result)
IGNORED_PER_HOUR = 300       # filtered/invalid/duplicate events LOGGED per hook per hour (past it: answered, not logged)
KEEP_IGNORED_PER_HOOK = 200   # and kept per hook, apart from the KEEP_PER_HOOK real runs (a flood cannot push them out)
FINAL = ("done", "silent", "waiting", "failed", "unknown", "dead")
IGNORED = ("filtered", "invalid", "duplicate")

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
    notify_tries INTEGER NOT NULL DEFAULT 0,
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
    error TEXT NOT NULL DEFAULT '',
    late_result TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_att_ev ON attempts(event_id, n);
CREATE TABLE IF NOT EXISTS biz_keys(
    brain TEXT NOT NULL,
    scope TEXT NOT NULL,
    bkey TEXT NOT NULL,
    event_id TEXT NOT NULL,
    hook_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    PRIMARY KEY(brain, scope, bkey)
);
CREATE INDEX IF NOT EXISTS ix_bk_exp ON biz_keys(expires_at);
CREATE INDEX IF NOT EXISTS ix_bk_ev ON biz_keys(event_id);
CREATE TABLE IF NOT EXISTS branches(
    event_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    delivery_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    tries INTEGER NOT NULL DEFAULT 0,
    next_at REAL NOT NULL DEFAULT 0,
    dispatched_at REAL NOT NULL DEFAULT 0,
    finished_at REAL NOT NULL DEFAULT 0,
    detail TEXT NOT NULL DEFAULT '',
    receipt TEXT NOT NULL DEFAULT '{}',
    result TEXT NOT NULL DEFAULT '',
    approved_at REAL NOT NULL DEFAULT 0,
    PRIMARY KEY(event_id, action_id)
);
CREATE TABLE IF NOT EXISTS ai_runs(
    hook_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ai_runs ON ai_runs(hook_id, at);
CREATE TABLE IF NOT EXISTS breakers(
    hook_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    fails INTEGER NOT NULL DEFAULT 0,
    open_until REAL NOT NULL DEFAULT 0,
    opens INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL DEFAULT 0,
    PRIMARY KEY(hook_id, action_id)
);
"""
# M5: circuit breaker of an outside action (per hook and action). BREAKER_FAILS failures in a row open it for
# BREAKER_COOLDOWN_S, doubling at each reopening up to BREAKER_MAX_S; one success closes it.
BREAKER_FAILS = 5
BREAKER_COOLDOWN_S = 600.0
BREAKER_MAX_S = 3600.0
PARKED_MAX = 200          # events of one hook waiting for a later resend (breaker, backoff): their own cap, so a
                          # receiver that is down does not fill the backlog and refuse events the other branches run
OWED_MAX = 200            # unknown + waiting events of one hook (kept until the owner settles them)
APPROVAL_TTL_DAYS = 14    # an approval nobody answered is cancelled after this (the event is then settled)
RECENT_KEEP_S = 90000.0   # nothing received in the last 25 h is pruned: the day quota and AI budget count those rows
# Branch states. pending/retry: may run; running: dispatched, outcome not written; the rest are final for the run.
BRANCH_FINAL = ("completed", "accepted", "silent", "waiting", "cancelled", "failed", "unknown", "approval")
BRANCH_OK = ("completed", "accepted", "silent", "cancelled")
_COLUMNS_V2 = (("trace", "TEXT NOT NULL DEFAULT '{}'"), ("fields", "TEXT NOT NULL DEFAULT '{}'"),
               ("biz_key", "TEXT NOT NULL DEFAULT ''"), ("biz_ttl", "REAL NOT NULL DEFAULT 0"))
JSON_COL_MAX = 64000          # a trace/fields column larger than this is stored as a marker, never cut mid-JSON


def _dumps(v, limit: int = JSON_COL_MAX) -> str:
    """JSON for a column: always valid. Unserialisable or oversized -> a small marker object instead of a slice."""
    try:
        t = json.dumps(v or {}, ensure_ascii=False, default=str, allow_nan=False)
    except (ValueError, TypeError, OverflowError, RecursionError):
        return json.dumps({"_unstorable": True})
    return t if len(t) <= limit else json.dumps({"_truncated": True, "size": len(t)})


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
        # The file holds event bodies (customer data). Create it 0600 BEFORE SQLite opens it: SQLite gives the -wal
        # and -shm files the mode of the main file, so they are private too (a chmod afterwards misses them).
        try:
            os.close(os.open(str(self.path), os.O_CREAT | os.O_RDWR, 0o600))
            os.chmod(self.path, 0o600)
        except OSError:
            pass
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(self.path), timeout=10, isolation_level=None, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        mode = str(self._db.execute("PRAGMA journal_mode=WAL").fetchone()[0]).lower()
        if mode != "wal":
            import sys
            print(f"[webhook_store] journal_mode is {mode}, not wal (network drive?): writes may block readers",
                  file=sys.stderr)
        self._db.execute("PRAGMA synchronous=FULL")      # an ACKed event must survive a power cut
        self._db.execute("PRAGMA busy_timeout=10000")
        self._db.execute("PRAGMA journal_size_limit=16777216")   # the WAL is truncated back to 16 MB at checkpoints
        with self._lock:
            self._db.executescript(_SCHEMA)
            # v1 -> v2/v3 (M2, M3): columns added in place; an older reader ignores them, so a rollback keeps working.
            # Under BEGIN IMMEDIATE and re-read inside it: several processes opening one old file at once would each
            # see the column missing and the second ALTER would fail.
            self._tx()
            try:
                have = {r[1] for r in self._db.execute("PRAGMA table_info(events)")}
                for col, decl in _COLUMNS_V2:
                    if col not in have:
                        self._db.execute(f"ALTER TABLE events ADD COLUMN {col} {decl}")
                have_b = {r[1] for r in self._db.execute("PRAGMA table_info(branches)")}
                if "approved_at" not in have_b:                     # v3 -> v4 (M4)
                    self._db.execute("ALTER TABLE branches ADD COLUMN approved_at REAL NOT NULL DEFAULT 0")
                row = self._db.execute("SELECT v FROM meta WHERE k='schema_version'").fetchone()
                if row is None or int(row["v"]) < SCHEMA_VERSION:
                    # Never LOWER the marker: an older build opening a newer file leaves it as it is.
                    self._db.execute("INSERT OR REPLACE INTO meta(k, v) VALUES('schema_version', ?)",
                                     (str(SCHEMA_VERSION),))
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

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
                self._db.execute("COMMIT")
            except BaseException:
                # Also when COMMIT itself fails (busy, disk full): never leave the transaction open.
                try:
                    self._db.execute("ROLLBACK")
                except Exception:
                    pass
                raise

    @contextlib.contextmanager
    def _read(self):
        """Reads take the same lock as writes: on the shared connection a read between another thread's BEGIN and
        COMMIT would see that thread's uncommitted rows."""
        with self._lock:
            yield

    def schema_version(self) -> int:
        row = self._db.execute("SELECT v FROM meta WHERE k='schema_version'").fetchone()
        return int(row["v"]) if row else 0

    def size_bytes(self) -> int:
        """LIVE data in the database: pages in use. Free pages left by deletions and the WAL do not count, so
        pruning brings this down at once (the file itself is reused, and the WAL is capped by journal_size_limit)."""
        with self._read():
            pc = self._db.execute("PRAGMA page_count").fetchone()[0]
            fl = self._db.execute("PRAGMA freelist_count").fetchone()[0]
            ps = self._db.execute("PRAGMA page_size").fetchone()[0]
        return int((pc - fl) * ps)

    def make_room(self, need: int = 0, now: Optional[float] = None) -> int:
        """Near the cap: free space from FINISHED events the owner has already been told about, oldest first: their
        bodies first, then whole rows. Never queued, running or unknown events, and never a finished event whose
        notice has not gone out yet. Last resort: idempotency keys older than a day. Returns rows touched."""
        now = time.time() if now is None else now
        target = int(DB_MAX_BYTES * 0.8) - int(need)
        n = 0
        told = ("status IN ('done','silent','failed','dead','filtered','invalid','duplicate') AND"
                " (notified_at>0 OR status='silent') AND id NOT IN (SELECT event_id FROM biz_keys)")
        # Events that never ran go first (a flood of filtered events must not push out real runs), then bodies of
        # finished runs, then whole rows.
        steps = ("SELECT id FROM events WHERE status IN ('filtered','invalid','duplicate') ORDER BY received_at LIMIT 100",
                 f"SELECT id FROM events WHERE {told} AND length(body)>0 ORDER BY received_at LIMIT 100",
                 f"SELECT id FROM events WHERE {told} ORDER BY received_at LIMIT 100")
        for i, sel in enumerate(steps):
            while self.size_bytes() > target:
                with self._write():
                    ids = [r[0] for r in self._db.execute(sel)]
                    if not ids:
                        break
                    q = ",".join("?" * len(ids))
                    if i == 1:
                        self._db.execute(f"UPDATE events SET body=x'' WHERE id IN ({q})", ids)
                    else:
                        self._db.execute(f"DELETE FROM attempts WHERE event_id IN ({q})", ids)
                        self._db.execute(f"DELETE FROM branches WHERE event_id IN ({q})", ids)
                        self._db.execute(f"DELETE FROM events WHERE id IN ({q})", ids)
                n += len(ids)
        while self.size_bytes() > target:
            with self._write():
                cur = self._db.execute("DELETE FROM dedup WHERE rowid IN (SELECT rowid FROM dedup WHERE created_at<?"
                                       " ORDER BY created_at LIMIT 2000)", (now - 86400,))
            if cur.rowcount <= 0:
                break
            n += cur.rowcount
        return n

    # ── receive ──
    def ingest(self, hook: dict, body: bytes, content_type: str, idem_key: str = "", now: Optional[float] = None,
               source: str = "http", pre: Optional[dict] = None) -> tuple:
        """Store one event. `pre` is webhook_rules.evaluate() of the hook's rules on this body (None = no rules).
        Returns (code, info):
            (202, {"event_id"})             stored and committed: only now may the caller answer "accepted";
            (200, {"event_id", "duplicate"}) the idempotency key was already stored for this hook;
            (200, {"event_id", "ignored": "filtered"|"duplicate", "first"?})  logged, will not run;
            (422, {"event_id", "reason"})   invalid for the hook's schema/mapping: logged, will not run;
            (429, {"reason": "rate"|"backlog"})  refused, NOTHING stored (no event, no key);
            raises Busy                      the store cannot take it (disk cap, locked): answer 503, keep nothing.
        An ignored event past IGNORED_PER_HOUR is answered the same way but not logged (event_id ""). An ignored event
        keeps no idempotency key: a copy under the same key is evaluated again.
        """
        now = time.time() if now is None else now
        key = str(idem_key or "").strip()[:200]
        hid = str(hook["id"])
        if self.size_bytes() + len(body) > DB_MAX_BYTES:
            self.make_room(len(body), now)
            if self.size_bytes() + len(body) > DB_MAX_BYTES:
                raise Busy("store full")         # only waiting/unknown events left: refuse rather than drop them
        pre = pre or {}
        decision = str(pre.get("decision") or "run")
        snap = {k: hook.get(k) for k in ("name", "brain", "target", "workflow", "text", "level", "chat_id")}
        if hook.get("actions"):
            # Header VALUES (API keys) are not copied into the event store: the run takes them from the hook as it is
            # then, so a rotated key applies to waiting events and the log never holds a secret.
            snap["actions"] = [dict(a, headers={k: "••••" for k in a["headers"]}) if a.get("headers") else a
                               for a in hook["actions"]]
        if hook.get("rules"):
            snap["rules_rev"] = hashlib.sha256(json.dumps(hook["rules"], sort_keys=True, ensure_ascii=False)
                                               .encode()).hexdigest()[:12]
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
                brain = str(hook.get("brain") or "")
                bk = pre.get("business_key") if decision == "run" else None
                first = ""
                if bk:
                    row = self._live_key(brain, bk["scope"], bk["key"], now)
                    if row is not None:
                        decision, first = "duplicate", row["event_id"]
                if decision != "run":
                    return self._ingest_ignored(hid, brain, decision, first, pre, snap, body, content_type, key, eid,
                                                source, now)
                n_hour = self._db.execute(
                    "SELECT COUNT(*) FROM events WHERE hook_id=? AND received_at>? AND status NOT IN"
                    " ('filtered','invalid','duplicate')", (hid, now - 3600)).fetchone()[0]
                lim = hook.get("limits") or {}
                if n_hour >= int(lim.get("per_hour") or RATE_PER_HOUR):
                    self._db.execute("ROLLBACK")
                    return 429, {"reason": "rate"}
                backlog = self._db.execute(
                    "SELECT COUNT(*) FROM events WHERE hook_id=? AND (status='running' OR (status='queued' AND"
                    " next_at<=?))", (hid, now)).fetchone()[0]
                parked = self._db.execute(
                    "SELECT COUNT(*) FROM events WHERE hook_id=? AND status='queued' AND next_at>?",
                    (hid, now)).fetchone()[0]
                if parked >= PARKED_MAX:
                    self._db.execute("ROLLBACK")
                    return 429, {"reason": "backlog"}
                owed = self._db.execute("SELECT COUNT(*) FROM events WHERE hook_id=? AND status IN ('unknown','waiting')",
                                        (hid,)).fetchone()[0]
                if owed >= OWED_MAX:
                    # Events the owner still owes something are never pruned: past this many, THIS hook refuses
                    # (429) until the owner settles them, instead of filling the store shared by every brain.
                    self._db.execute("ROLLBACK")
                    return 429, {"reason": "owner"}
                if backlog >= int(lim.get("backlog") or BACKLOG_MAX):
                    self._db.execute("ROLLBACK")
                    return 429, {"reason": "backlog"}
                per_day = int(lim.get("per_day") or 0)
                if per_day:
                    n_day = self._db.execute(
                        "SELECT COUNT(*) FROM events WHERE hook_id=? AND received_at>? AND status NOT IN"
                        " ('filtered','invalid','duplicate')", (hid, now - 86400)).fetchone()[0]
                    if n_day >= per_day:
                        self._db.execute("ROLLBACK")
                        return 429, {"reason": "day"}
                self._insert_event(eid, hid, brain, now, content_type, body, key, snap, source, "queued", pre,
                                   bk["scope"] + "/" + bk["key"] if bk else "", float(bk["ttl_s"]) if bk else 0.0)
                if bk:
                    self._db.execute("INSERT OR REPLACE INTO biz_keys(brain, scope, bkey, event_id, hook_id,"
                                     " created_at, expires_at) VALUES(?,?,?,?,?,?,?)",
                                     (brain, bk["scope"], bk["key"], eid, hid, now, now + float(bk["ttl_s"])))
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

    def _live_key(self, brain: str, scope: str, bkey: str, now: float):
        """Inside a transaction: the event holding this business key, if the key is still live. A key past its TTL
        still holds while its event has not run yet (a backlog must not let a second copy through)."""
        return self._db.execute(
            "SELECT b.event_id FROM biz_keys b LEFT JOIN events e ON e.id=b.event_id WHERE b.brain=? AND b.scope=? AND"
            " b.bkey=? AND (b.expires_at>? OR e.status IN ('queued','running'))", (brain, scope, bkey, now)).fetchone()

    def _insert_event(self, eid, hid, brain, now, content_type, body, key, snap, source, status, pre, biz,
                      biz_ttl: float = 0.0) -> None:
        fin = now if status in IGNORED else 0
        self._db.execute(
            "INSERT INTO events(id, hook_id, brain, received_at, content_type, body, body_sha, idem_key,"
            " hook_snapshot, source, status, next_at, finished_at, notified_at, error, trace, fields, biz_key, biz_ttl)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (eid, hid, brain, now, str(content_type or "")[:200], bytes(body), hashlib.sha256(bytes(body)).hexdigest(),
             key, _dumps(snap), source, status, now, fin, fin,
             str((pre or {}).get("reason") or "")[:2000],
             _dumps((pre or {}).get("trace") or {}), _dumps((pre or {}).get("fields") or {}), biz, biz_ttl))

    def _ingest_ignored(self, hid, brain, decision, first, pre, snap, body, content_type, key, eid, source,
                        now) -> tuple:
        """Inside ingest's open transaction: log an event that will not run (and commit), or only answer when the
        hook already logged IGNORED_PER_HOUR of them this hour."""
        n = self._db.execute("SELECT COUNT(*) FROM events WHERE hook_id=? AND received_at>? AND status IN"
                             " ('filtered','invalid','duplicate')", (hid, now - 3600)).fetchone()[0]
        logged = n < IGNORED_PER_HOUR
        if logged:
            if decision == "duplicate":
                pre = dict(pre)
                pre["reason"] = f"business key already seen (event {first})"
                pre["trace"] = dict(pre.get("trace") or {}, duplicate_of=first)
            bk = pre.get("business_key") or {}
            self._insert_event(eid, hid, brain, now, content_type, body, key, snap, source, decision, pre,
                               (bk.get("scope", "") + "/" + bk.get("key", "")) if bk else "")
            # No idempotency key for an event that did not run: the sender's copy under the same key is decided
            # again (rules may have changed, the first holder of the business key may have died since).
            self._db.execute("COMMIT")
        else:
            self._db.execute("ROLLBACK")
        out_id = eid if logged else ""
        if decision == "invalid":
            return 422, {"event_id": out_id, "reason": str(pre.get("reason") or "invalid")}
        info = {"event_id": out_id, "ignored": decision}
        if first:
            info["first"] = first
        return 200, info

    def _ever_dispatched(self, eid: str) -> bool:
        """Did ANY attempt of this event reach its effect? Not `events.dispatched_at`, which an owner's retry resets:
        branch dispatch marks are kept across retries, and finished attempts are kept too."""
        return self._db.execute(
            # With branches, their sticky dispatch marks say it (an attempt that ended "failed" because every branch was
            # refused before dispatch does not count). Without branches (a run as a whole), a finished attempt does.
            "SELECT 1 FROM branches WHERE event_id=? AND dispatched_at>0 UNION ALL SELECT 1 FROM events WHERE id=? AND"
            " dispatched_at>0 UNION ALL SELECT 1 FROM attempts WHERE event_id=? AND (outcome IN ('done','silent',"
            "'waiting','failed','unknown') OR outcome LIKE 'late:%') AND NOT EXISTS (SELECT 1 FROM branches WHERE"
            " event_id=?) LIMIT 1", (eid, eid, eid, eid)).fetchone() is not None

    def _release_keys(self, eid: str) -> None:
        """Inside a write: an event that will never run (dead) gives its business key back, so the source's next
        copy of that order is not refused as a duplicate of something that never happened. Only if no attempt of it
        was ever dispatched: a retried event that may have acted the first time keeps its key."""
        if not self._ever_dispatched(eid):
            self._db.execute("DELETE FROM biz_keys WHERE event_id=?", (eid,))

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
                " SELECT 1 FROM events r WHERE r.hook_id=e.hook_id AND r.status='running')"
                " ORDER BY e.received_at, e.id LIMIT 1", (now,)).fetchone()
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

    def _fenced(self, sql: str, args: tuple, eid: str, fence: int, now: float) -> bool:
        """Only the current owner, and only while its lease is still valid: an expired lease that recover() has not
        reached yet may already be someone else's."""
        with self._write():
            cur = self._db.execute(sql + " WHERE id=? AND fence=? AND status='running' AND lease_until>?",
                                   args + (eid, fence, now))
            return cur.rowcount == 1

    def heartbeat(self, eid: str, fence: int, now: Optional[float] = None) -> bool:
        """Renew. No live-lease condition here: claim() never takes a running row, so while the event is still
        `running` at our fence it is ours, and a beat that comes a little late keeps a healthy run alive."""
        now = time.time() if now is None else now
        with self._write():
            cur = self._db.execute("UPDATE events SET lease_until=? WHERE id=? AND fence=? AND status='running'",
                                   (now + LEASE_S, eid, fence))
            return cur.rowcount == 1

    def mark_dispatched(self, eid: str, fence: int, now: Optional[float] = None) -> bool:
        """Committed BEFORE the runner is called (and renews the lease). False = this worker lost the event: do
        NOT run it."""
        now = time.time() if now is None else now
        return self._fenced("UPDATE events SET dispatched_at=?, lease_until=?", (now, now + LEASE_S), eid, fence, now)

    def finish(self, eid: str, fence: int, status: str, result: str = "", error: str = "",
               now: Optional[float] = None) -> bool:
        """Final state for this attempt. False = a newer owner holds the event; this result is dropped."""
        assert status in FINAL
        now = time.time() if now is None else now
        with self._write():
            cur = self._db.execute(
                "UPDATE events SET status=?, result=?, error=?, finished_at=?, lease_owner='', lease_until=0,"
                " notified_at=0, notify_tries=0 WHERE id=? AND fence=? AND status='running'",
                (status, str(result or "")[:4000], str(error or "")[:2000], now, eid, fence))
            ok = cur.rowcount == 1
            if ok:
                self._db.execute("UPDATE attempts SET ended_at=?, outcome=?, error=? WHERE event_id=? AND fence=?",
                                 (now, status, str(error or "")[:500], eid, fence))
                if status == "dead":
                    self._release_keys(eid)
            else:
                # The event was taken over (lease lost while the run was alive). The run's own result is not thrown
                # away: it is kept on this attempt's row, where the owner reconciling the event can read it.
                self._db.execute("UPDATE attempts SET ended_at=?, outcome=?, late_result=? WHERE event_id=? AND fence=?",
                                 (now, "late:" + status, str(result or error or "")[:4000], eid, fence))
        return ok

    # ── branches (M3) ──
    def _owns(self, eid: str, fence: int) -> bool:
        """Inside a write: this worker still holds the event (claim() never takes a running row)."""
        return self._db.execute("SELECT 1 FROM events WHERE id=? AND fence=? AND status='running'",
                                (eid, fence)).fetchone() is not None

    def branches_init(self, eid: str, fence: int, actions: list, delivery_of) -> Optional[list]:
        """Create the branch rows of this event once (idempotent): one per action, each with its stable delivery id.
        Returns all branch rows, or None if this worker no longer owns the event."""
        with self._write():
            if not self._owns(eid, fence):
                return None
            for a in actions:
                self._db.execute("INSERT OR IGNORE INTO branches(event_id, action_id, kind, delivery_id) VALUES(?,?,?,?)",
                                 (eid, a["id"], a["kind"], delivery_of(eid, a["id"])))
            return [dict(r) for r in self._db.execute("SELECT * FROM branches WHERE event_id=? ORDER BY rowid", (eid,))]

    def branches(self, eid: str) -> list:
        with self._read():
            return [dict(r) for r in self._db.execute("SELECT * FROM branches WHERE event_id=? ORDER BY rowid", (eid,))]

    def branch_dispatch(self, eid: str, fence: int, aid: str, now: Optional[float] = None) -> bool:
        """Committed BEFORE the branch's effect starts. False = do NOT run it (lost the event, or the branch is not
        runnable any more)."""
        now = time.time() if now is None else now
        with self._write():
            ok = self._db.execute("SELECT 1 FROM events WHERE id=? AND fence=? AND status='running' AND lease_until>?",
                                  (eid, fence, now)).fetchone()
            if not ok:
                return False
            cur = self._db.execute("UPDATE branches SET status='running', dispatched_at=?, tries=tries+1 WHERE"
                                   " event_id=? AND action_id=? AND status IN ('pending','retry')", (now, eid, aid))
            if cur.rowcount != 1:
                return False
            self._db.execute("UPDATE events SET dispatched_at=CASE WHEN dispatched_at=0 THEN ? ELSE dispatched_at END,"
                             " lease_until=? WHERE id=?", (now, now + LEASE_S, eid))
            # Every dispatch of an AI branch (a retry too) is one model run for the AI budget: append-only.
            self._db.execute("INSERT INTO ai_runs(hook_id, event_id, at) SELECT e.hook_id, e.id, ? FROM events e JOIN"
                             " branches b ON b.event_id=e.id WHERE e.id=? AND b.action_id=? AND b.kind='ai'",
                             (now, eid, aid))
        return True

    def branch_finish(self, eid: str, fence: int, aid: str, status: str, detail: str = "", receipt: Optional[dict] = None,
                      result: str = "", next_at: float = 0.0, now: Optional[float] = None) -> bool:
        # (A False return means the event is no longer ours; the caller keeps the outcome with branch_late.)
        """Outcome of one branch. `retry` keeps it runnable from `next_at`. A branch that never started may be closed
        too (a permission or a missing plugin found before dispatch). False = a newer owner holds the event."""
        assert status in BRANCH_FINAL or status == "retry"
        now = time.time() if now is None else now
        with self._write():
            if not self._owns(eid, fence):
                return False
            self._db.execute(
                "UPDATE branches SET status=?, detail=?, receipt=?, result=?, next_at=?, finished_at=? WHERE event_id=?"
                " AND action_id=? AND status IN ('running','pending','retry')",
                (status, str(detail or "")[:1000], _dumps(receipt or {}, 4000),
                 str(result or "")[:4000], float(next_at or 0), 0 if status == "retry" else now, eid, aid))
        return True

    def _kept_longer(self, eid: str, longer: dict, now: float) -> bool:
        if not longer:
            return False
        r = self._db.execute("SELECT hook_id, finished_at FROM events WHERE id=?", (eid,)).fetchone()
        return bool(r) and r["hook_id"] in longer and r["finished_at"] >= now - longer[r["hook_id"]] * 86400

    # ── M5: breakers, AI budget, meta, export ──
    def breaker_open_until(self, hook_id: str, action_id: str, now: Optional[float] = None) -> float:
        now = time.time() if now is None else now
        with self._read():
            r = self._db.execute("SELECT open_until FROM breakers WHERE hook_id=? AND action_id=?",
                                 (hook_id, action_id)).fetchone()
        return float(r["open_until"]) if r and float(r["open_until"]) > now else 0.0

    def breaker_record(self, hook_id: str, action_id: str, ok: bool, now: Optional[float] = None) -> str:
        """One branch outcome of an outside action. Returns "opened" when this failure opened the breaker, "closed"
        when a success closed an open or failing one, else ""."""
        now = time.time() if now is None else now
        with self._write():
            r = self._db.execute("SELECT fails, open_until, opens FROM breakers WHERE hook_id=? AND action_id=?",
                                 (hook_id, action_id)).fetchone()
            fails, opens = (int(r["fails"]), int(r["opens"])) if r else (0, 0)
            if ok:
                if r and (fails or float(r["open_until"])):
                    self._db.execute("UPDATE breakers SET fails=0, open_until=0, opens=0, updated_at=? WHERE hook_id=?"
                                     " AND action_id=?", (now, hook_id, action_id))
                    return "closed"
                return ""
            fails += 1
            out, until = "", float(r["open_until"]) if r else 0.0
            if fails >= BREAKER_FAILS:
                until = now + min(BREAKER_COOLDOWN_S * (2 ** opens), BREAKER_MAX_S)
                opens += 1
                # Half-open after the cooldown: ONE more failure reopens it (not another BREAKER_FAILS).
                fails = BREAKER_FAILS - 1
                out = "opened"
            self._db.execute("INSERT OR REPLACE INTO breakers(hook_id, action_id, fails, open_until, opens, updated_at)"
                             " VALUES(?,?,?,?,?,?)", (hook_id, action_id, fails, until, opens, now))
            return out

    def breaker_reset(self, hook_id: str, action_id: str = "") -> None:
        """The action points elsewhere now (or is gone): its failures say nothing about the new target."""
        with self._write():
            if action_id:
                self._db.execute("DELETE FROM breakers WHERE hook_id=? AND action_id=?", (hook_id, action_id))
            else:
                self._db.execute("DELETE FROM breakers WHERE hook_id=?", (hook_id,))

    def meta_prefix(self, prefix: str) -> list:
        with self._read():
            return [(r["k"], r["v"]) for r in self._db.execute("SELECT k, v FROM meta WHERE k LIKE ? ESCAPE '\\'",
                                                              (prefix.replace("_", "\\_") + "%",))]

    def meta_del(self, k: str) -> None:
        with self._write():
            self._db.execute("DELETE FROM meta WHERE k=?", (k,))

    def breakers(self, hook_id: str, now: Optional[float] = None) -> list:
        now = time.time() if now is None else now
        with self._read():
            return [dict(r) for r in self._db.execute("SELECT action_id, fails, open_until, opens FROM breakers WHERE"
                                                       " hook_id=? AND (open_until>? OR fails>0)", (hook_id, now))]

    def ai_runs_since(self, hook_id: str, since: float) -> int:
        """AI branches of this hook dispatched since `since` (the AI budget counts runs that reached a model)."""
        with self._read():
            return int(self._db.execute("SELECT COUNT(*) FROM ai_runs WHERE hook_id=? AND at>=?",
                                        (hook_id, since)).fetchone()[0])

    def meta_get(self, k: str) -> str:
        with self._read():
            r = self._db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return r["v"] if r else ""

    def meta_set(self, k: str, v: str) -> None:
        with self._write():
            self._db.execute("INSERT OR REPLACE INTO meta(k, v) VALUES(?,?)", (k, str(v)))

    def finished_counts(self, hook_id: str, since: float, until: float) -> dict:
        with self._read():
            rows = self._db.execute("SELECT status, COUNT(*) AS n FROM events WHERE hook_id=? AND finished_at>=? AND"
                                    " finished_at<? GROUP BY status", (hook_id, since, until)).fetchall()
        return {r["status"]: r["n"] for r in rows}

    def export_rows(self, hook_id: str = "", since: float = 0.0, until: float = 0.0, with_body: bool = False,
                    batch: int = 200):
        """Every event of a hook (or all), oldest first, in batches (keyset on received_at, id): for export. Bodies
        only when asked. Never the hook snapshot (it is configuration, not data)."""
        last_ts, last_id = float(since or 0), ""
        until = float(until or 0) or 1e18
        while True:
            with self._read():
                rows = self._db.execute(
                    "SELECT id, hook_id, brain, received_at, status, tries, idem_key, biz_key, source, dispatched_at,"
                    " finished_at, result, error, fields, trace" + (", body, content_type" if with_body else "") +
                    " FROM events WHERE (?='' OR hook_id=?) AND received_at<? AND (received_at>? OR (received_at=? AND"
                    " id>?)) ORDER BY received_at, id LIMIT ?",
                    (hook_id, hook_id, until, last_ts, last_ts, last_id, batch)).fetchall()
                rows = [dict(r) for r in rows]
                for r in rows:
                    r["branches"] = [dict(b) for b in self._db.execute(
                        "SELECT action_id, kind, status, tries, delivery_id, detail FROM branches WHERE event_id=?"
                        " ORDER BY rowid", (r["id"],))]
            if not rows:
                return
            for r in rows:
                yield r
            last_ts, last_id = rows[-1]["received_at"], rows[-1]["id"]

    def branch_late(self, eid: str, aid: str, status: str, detail: str, receipt: Optional[dict], result: str) -> None:
        """The event was taken over while this branch was still running (lease lost): its real outcome is not
        written as the branch state (the owner reconciles that), but it is kept next to it so the owner can read
        what actually happened."""
        note = f"late outcome: {status}" + (f" ({detail[:300]})" if detail else "")
        if receipt:
            note += " " + _dumps(receipt, 1500)
        if result:
            note += " " + str(result)[:1500]
        with self._write():
            self._db.execute("UPDATE branches SET detail=substr(detail || ' | ' || ?, 1, 4000) WHERE event_id=? AND"
                             " action_id=?", (note, eid, aid))

    @staticmethod
    def summarize(rows: list) -> tuple:
        """(event status, next_at) from the branch rows. `queued` = some branch still runs later (retry/pending)."""
        st = [r["status"] for r in rows]
        if not st:
            return "done", 0.0
        if "running" in st:
            return "unknown", 0.0
        # Branches that can still run go first: an unknown sibling must not stop a busy receiver's resend. The event
        # becomes unknown once nothing is left to run.
        later = [float(r["next_at"] or 0) for r in rows if r["status"] in ("retry", "pending")]
        if later:
            return "queued", min(later)
        if "unknown" in st:
            return "unknown", 0.0
        if "approval" in st:
            return "waiting", 0.0          # the owner must approve (or reject) a branch before it runs
        if "failed" in st:
            return "failed", 0.0
        if "waiting" in st:
            return "waiting", 0.0
        if all(s == "silent" for s in st):
            return "silent", 0.0
        return "done", 0.0

    def settle(self, eid: str, fence: int, text_of, now: Optional[float] = None) -> tuple:
        """End of a run over branches, in ONE write: read the branches as they are NOW (an approval may have landed
        while the run was finishing), then requeue the event if a branch can still run, or write its final state.
        `text_of(rows) -> (result, error)` builds the texts from those rows. Returns (status, next_at), or ("", 0)
        if this worker no longer owns the event."""
        now = time.time() if now is None else now
        with self._write():
            if not self._owns(eid, fence):
                return "", 0.0
            rows = [dict(r) for r in self._db.execute("SELECT * FROM branches WHERE event_id=? ORDER BY rowid", (eid,))]
            status, nxt = self.summarize(rows)
            if status == "queued":
                self._db.execute(
                    "UPDATE events SET status='queued', next_at=?, lease_owner='', lease_until=0, dispatched_at=0, tries=0"
                    " WHERE id=?", (max(nxt, now), eid))
                self._db.execute("UPDATE attempts SET ended_at=?, outcome='branch_retry' WHERE event_id=? AND fence=?",
                                 (now, eid, fence))
                return "queued", nxt
            result, error = text_of(rows)
            self._db.execute(
                "UPDATE events SET status=?, result=?, error=?, finished_at=?, lease_owner='', lease_until=0,"
                " notified_at=0, notify_tries=0 WHERE id=?", (status, str(result or "")[:4000], str(error or "")[:2000],
                                                              now, eid))
            self._db.execute("UPDATE attempts SET ended_at=?, outcome=?, error=? WHERE event_id=? AND fence=?",
                             (now, status, str(error or "")[:500], eid, fence))
            return status, 0.0

    def approve(self, eid: str, aid: str, decision: str, now: Optional[float] = None) -> tuple:
        """The owner approves or rejects ONE branch waiting for approval. Approve: it runs at the next pass (the
        current permissions are checked again then). Reject: it is cancelled. Returns (ok, error_code)."""
        if decision not in ("approve", "reject"):
            return False, "bad_decision"
        now = time.time() if now is None else now
        with self._write():
            row = self._db.execute("SELECT status FROM events WHERE id=?", (eid,)).fetchone()
            if row is None:
                return False, "not_found"
            cur = self._db.execute(
                "UPDATE branches SET status=?, approved_at=?, detail=?, finished_at=? WHERE event_id=? AND action_id=?"
                " AND status='approval'",
                ("pending", now, "approved by the owner", 0, eid, aid) if decision == "approve"
                else ("cancelled", 0, "rejected by the owner", now, eid, aid))
            if cur.rowcount != 1:
                return False, "not_waiting"
            if row["status"] == "queued":
                # Run the approved branch now, not at a sibling's later resend time.
                self._db.execute("UPDATE events SET next_at=? WHERE id=?", (now, eid))
                return True, ""
            if row["status"] == "running":
                return True, ""             # the run in progress settles it (settle() re-reads the branches)
            br = [dict(b) for b in self._db.execute("SELECT status, next_at FROM branches WHERE event_id=?", (eid,))]
            st, nxt = self.summarize(br)
            if st == "queued":
                self._db.execute("UPDATE events SET status='queued', next_at=?, dispatched_at=0, finished_at=0,"
                                 " notified_at=0, notify_tries=0, tries=0 WHERE id=?", (max(now, nxt), eid))
            else:
                self._db.execute("UPDATE events SET status=?, finished_at=?, notified_at=? WHERE id=?",
                                 (st, now, now, eid))
        return True, ""

    def requeue_branches(self, eid: str, fence: int, next_at: float, now: Optional[float] = None) -> bool:
        """Some branches run again later (receiver busy, not sent): the event goes back to the queue. The branches
        that finished keep their outcome and are not run again."""
        now = time.time() if now is None else now
        with self._write():
            cur = self._db.execute(
                "UPDATE events SET status='queued', next_at=?, lease_owner='', lease_until=0, dispatched_at=0, tries=0"
                " WHERE id=? AND fence=? AND status='running'", (max(next_at, now), eid, fence))
            if cur.rowcount == 1:
                self._db.execute("UPDATE attempts SET ended_at=?, outcome='branch_retry' WHERE event_id=? AND fence=?",
                                 (now, eid, fence))
            return cur.rowcount == 1

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
            if st == "dead":
                self._release_keys(eid)
        return st

    def recover(self, now: Optional[float] = None) -> dict:
        """Expired leases (a worker died or hung). Not yet dispatched -> queued again. Dispatched -> unknown:
        the run may have acted, so it is NOT re-run on its own. Returns counts."""
        now = time.time() if now is None else now
        with self._write():
            rows = self._db.execute("SELECT id, fence, tries, dispatched_at FROM events WHERE status='running' AND"
                                    " lease_until<=?", (now,)).fetchall()
            back = unknown = 0
            for r in rows:
                br = [dict(b) for b in self._db.execute("SELECT status, next_at FROM branches WHERE event_id=?",
                                                         (r["id"],))]
                if br:
                    # Per branch: one that was dispatched and never finished may have acted -> unknown. The others keep
                    # their outcome; if some never started, the event goes back to the queue to run just those.
                    self._db.execute("UPDATE branches SET status='unknown', finished_at=?, detail=? WHERE event_id=? AND"
                                     " status='running'", (now, "lease expired after dispatch: it may have acted", r["id"]))
                    br = [dict(b) for b in self._db.execute("SELECT status, next_at FROM branches WHERE event_id=?",
                                                             (r["id"],))]
                    pend = [b for b in br if b["status"] in ("pending", "retry")]
                    if pend and not r["dispatched_at"] and int(r["tries"]) >= MAX_AUTO_TRIES:
                        # Lost again and again before ANY branch started (it crashes the worker): stop looping.
                        self._db.execute("UPDATE events SET status='dead', finished_at=?, lease_owner='', lease_until=0,"
                                         " error=? WHERE id=?", (now, "worker lost it before dispatch too many times",
                                                                 r["id"]))
                        self._release_keys(r["id"])
                        outcome = "dead"
                    elif pend:
                        # tries is reset only when this attempt dispatched something: an event that keeps killing the
                        # worker BEFORE any dispatch must reach MAX_AUTO_TRIES and stop (the M1 poison guard).
                        self._db.execute("UPDATE events SET status='queued', next_at=?, lease_owner='', lease_until=0,"
                                         " dispatched_at=0, tries=CASE WHEN ? THEN 0 ELSE tries END WHERE id=?",
                                         (max(now, min(float(b["next_at"] or 0) for b in pend)),
                                          1 if r["dispatched_at"] else 0, r["id"]))
                        outcome = "lease_expired"
                        back += 1
                    else:
                        fin, _ = self.summarize(br)
                        err = "lease expired after dispatch: a branch may have acted" if fin == "unknown" else ""
                        self._db.execute("UPDATE events SET status=?, finished_at=?, lease_owner='', lease_until=0,"
                                         " notified_at=0, notify_tries=0, error=CASE WHEN ?='' THEN error ELSE ? END"
                                         " WHERE id=?", (fin, now, err, err, r["id"]))
                        outcome = fin
                        unknown += fin == "unknown"
                elif r["dispatched_at"]:
                    self._db.execute("UPDATE events SET status='unknown', finished_at=?, lease_owner='',"
                                     " lease_until=0, error=? WHERE id=?",
                                     (now, "lease expired after dispatch: the run may have acted", r["id"]))
                    outcome = "unknown"
                    unknown += 1
                elif int(r["tries"]) >= MAX_AUTO_TRIES:
                    # It keeps dying before dispatch (e.g. it crashes the worker): stop, do not loop forever.
                    self._db.execute("UPDATE events SET status='dead', finished_at=?, lease_owner='', lease_until=0,"
                                     " error=? WHERE id=?", (now, "worker lost it before dispatch too many times",
                                                             r["id"]))
                    self._release_keys(r["id"])
                    outcome = "dead"
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
        with self._read():
            return self._db.execute(
                "SELECT 1 FROM events e WHERE e.status='queued' AND e.next_at<=? AND NOT EXISTS ("
                " SELECT 1 FROM events r WHERE r.hook_id=e.hook_id AND r.status='running') LIMIT 1",
                (now,)).fetchone() is not None

    def mark_notified(self, eid: str, fence: Optional[int] = None, now: Optional[float] = None) -> None:
        """`fence` given: only if the event is still at that attempt (a retry since then gets its own notice)."""
        now = time.time() if now is None else now
        with self._write():
            if fence is None:
                self._db.execute("UPDATE events SET notified_at=? WHERE id=?", (now, eid))
            else:
                self._db.execute("UPDATE events SET notified_at=? WHERE id=? AND fence=?", (now, eid, fence))

    def notify_failed(self, eid: str, fence: int) -> None:
        """A notice that did not go out: tried again at the next sweep, up to NOTIFY_TRIES times."""
        with self._write():
            self._db.execute("UPDATE events SET notify_tries=notify_tries+1 WHERE id=? AND fence=?", (eid, fence))

    def unnotified(self, limit: int = 50) -> list:
        """Finished events whose owner notice was never confirmed (a crash between commit and notice, or a failed
        delivery), up to NOTIFY_TRIES attempts."""
        with self._read():
            rows = self._db.execute("SELECT * FROM events WHERE status IN ('done','waiting','failed','unknown','dead')"
                                    " AND notified_at=0 AND finished_at>0 AND notify_tries<? ORDER BY finished_at"
                                    " LIMIT ?", (NOTIFY_TRIES, limit)).fetchall()
        return [dict(r) for r in rows]

    # ── owner actions ──
    def retry(self, eid: str, now: Optional[float] = None) -> tuple:
        """The owner asks to run an event again (failed, unknown, dead). Returns (ok, error_code)."""
        now = time.time() if now is None else now
        with self._write():
            row = self._db.execute("SELECT status, brain, hook_id, biz_key, biz_ttl FROM events WHERE id=?",
                                   (eid,)).fetchone()
            if row is None:
                return False, "not_found"
            if row["status"] not in ("failed", "unknown", "dead"):
                return False, "not_retryable"
            if row["biz_key"] and "/" in row["biz_key"]:
                # The business key must be this event's again before it runs: a dead event gave it back, and another
                # copy of the same order may hold it now.
                scope, bkey = row["biz_key"].split("/", 1)
                held = self._live_key(row["brain"], scope, bkey, now)
                if held is not None and held["event_id"] != eid:
                    return False, "key_taken"
                if held is None:
                    self._db.execute("INSERT OR REPLACE INTO biz_keys(brain, scope, bkey, event_id, hook_id, created_at,"
                                     " expires_at) VALUES(?,?,?,?,?,?,?)",
                                     (row["brain"], scope, bkey, eid, row["hook_id"], now,
                                      now + float(row["biz_ttl"] or 30 * 86400)))
            # Only the branches that failed or are unknown run again; a completed or accepted branch never does.
            self._db.execute("UPDATE branches SET status='pending', next_at=0, finished_at=0, tries=0 WHERE event_id=?"
                             " AND status IN ('failed','unknown')", (eid,))
            self._db.execute("UPDATE events SET status='queued', next_at=?, dispatched_at=0, finished_at=0,"
                             " notified_at=0, notify_tries=0, tries=0, error='', result='' WHERE id=?", (now, eid))
        return True, ""

    def resolve(self, eid: str, outcome: str, note: str = "", now: Optional[float] = None) -> tuple:
        """Reconcile an `unknown` event after checking the outside system: it did happen (done) or not (failed,
        which can then be retried). Also closes a `waiting` event the owner has dealt with (a workflow question
        answered elsewhere, an approval no longer wanted): its waiting branches end done or failed, approvals are
        cancelled. Returns (ok, error_code)."""
        if outcome not in ("done", "failed"):
            return False, "bad_outcome"
        now = time.time() if now is None else now
        with self._write():
            row = self._db.execute("SELECT status FROM events WHERE id=?", (eid,)).fetchone()
            if row is None or row["status"] not in ("unknown", "waiting"):
                return False, "not_unknown"
            self._db.execute("UPDATE branches SET status=?, detail=CASE WHEN ?='' THEN detail ELSE ? END, finished_at=?"
                             " WHERE event_id=? AND status IN ('unknown','waiting')",
                             ("completed" if outcome == "done" else "failed", note, "owner: " + str(note)[:900], now, eid))
            self._db.execute("UPDATE branches SET status='cancelled', detail='closed by the owner', finished_at=? WHERE"
                             " event_id=? AND status='approval'", (now, eid))
            br = [dict(b) for b in self._db.execute("SELECT status, next_at FROM branches WHERE event_id=?", (eid,))]
            # With branches, the event's state follows them (a branch that failed on its own stays failed; one that
            # still has to run puts the event back in the queue).
            final, nxt = self.summarize(br) if br else (outcome, 0.0)
            if final == "queued":
                self._db.execute("UPDATE events SET status='queued', next_at=?, dispatched_at=0, finished_at=0,"
                                 " notified_at=0, notify_tries=0, tries=0, result=CASE WHEN ?='' THEN result ELSE ? END"
                                 " WHERE id=?", (max(now, nxt), note, str(note)[:1000], eid))
                return True, ""
            self._db.execute("UPDATE events SET status=?, result=CASE WHEN ?='' THEN result ELSE ? END,"
                             " finished_at=?, notified_at=? WHERE id=?",
                             (final, note, str(note)[:1000], now, now, eid))
        return True, ""

    # ── reading ──
    def get(self, eid: str, with_body: bool = False) -> Optional[dict]:
        with self._read():
            row = self._db.execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()
            if row is None:
                return None
            d = dict(row)
            d["attempts"] = [dict(a) for a in self._db.execute(
                "SELECT n, fence, started_at, ended_at, outcome, error, late_result FROM attempts WHERE event_id=?"
                " ORDER BY n", (eid,)).fetchall()]
            d["branches"] = []
            for b in self._db.execute("SELECT action_id, kind, delivery_id, status, tries, dispatched_at, finished_at,"
                                      " approved_at, detail, receipt, substr(result, 1, 600) AS result FROM branches"
                                      " WHERE event_id=?"
                                      " ORDER BY rowid", (eid,)):
                b = dict(b)
                try:
                    b["receipt"] = json.loads(b["receipt"] or "{}")
                except ValueError:
                    b["receipt"] = {}
                d["branches"].append(b)
        if not with_body:
            d.pop("body", None)
        for k in ("trace", "fields"):
            try:
                d[k] = json.loads(d.get(k) or "{}")
            except ValueError:
                d[k] = {}
        return d

    def page(self, hook_id: str = "", status: str = "", limit: int = 20, before: str = "",
             ran_only: bool = False) -> dict:
        """Newest first, keyset pagination: `before` is the `cursor` of the previous page. `ran_only` leaves out the
        events the rules stopped (filtered/invalid/duplicate), for the card's short history."""
        limit = max(1, min(int(limit or 20), 100))
        where, args = [], []
        if ran_only:
            where.append("status NOT IN ('filtered','invalid','duplicate')")
        if hook_id:
            where.append("hook_id=?"); args.append(hook_id)
        if status:
            sts = [x for x in str(status).split(",") if x][:12]
            where.append("status IN (" + ",".join("?" * len(sts)) + ")"); args += sts
        if before:
            try:
                ts, eid = before.split("|", 1)
                where.append("(received_at<? OR (received_at=? AND id<?))"); args += [float(ts), float(ts), eid]
            except ValueError:
                pass
        sql = ("SELECT id, hook_id, brain, received_at, status, tries, idem_key, biz_key, source, dispatched_at,"
               " finished_at,"
               " substr(result, 1, 300) AS result, substr(error, 1, 300) AS error, length(body) AS size FROM events" + (" WHERE " + " AND ".join(where) if where else "")
               + " ORDER BY received_at DESC, id DESC LIMIT ?")
        with self._read():
            rows = [dict(r) for r in self._db.execute(sql, args + [limit + 1]).fetchall()]
        more = len(rows) > limit
        rows = rows[:limit]
        cur = f"{rows[-1]['received_at']}|{rows[-1]['id']}" if more and rows else ""
        return {"items": rows, "next": cur}

    def biz_key_lookup(self, brain: str, scope: str, bkey: str, now: Optional[float] = None) -> Optional[dict]:
        """Read only (simulation): the live event holding this business key, or None."""
        now = time.time() if now is None else now
        with self._read():
            row = self._db.execute("SELECT event_id, hook_id, created_at, expires_at FROM biz_keys WHERE brain=? AND"
                                   " scope=? AND bkey=? AND expires_at>?", (brain, scope, bkey, now)).fetchone()
        return dict(row) if row else None

    def counts(self, hook_id: str) -> dict:
        with self._read():
            rows = self._db.execute("SELECT status, COUNT(*) AS n FROM events WHERE hook_id=? GROUP BY status",
                                    (hook_id,)).fetchall()
        return {r["status"]: r["n"] for r in rows}

    def last(self, hook_id: str) -> Optional[dict]:
        with self._read():
            row = self._db.execute("SELECT status, finished_at, received_at FROM events WHERE hook_id=?"
                                   " ORDER BY received_at DESC, id DESC LIMIT 1", (hook_id,)).fetchone()
        return dict(row) if row else None

    def forget_hook(self, hook_id: str) -> None:
        """A deleted hook: its waiting events become `dead` (they will never run), its keys are dropped."""
        now = time.time()
        with self._write():
            for (qid,) in self._db.execute("SELECT id FROM events WHERE hook_id=? AND status='queued'",
                                           (hook_id,)).fetchall():
                self._release_keys(qid)
            self._db.execute("UPDATE events SET status='dead', finished_at=?, notified_at=?, error='hook deleted'"
                             " WHERE hook_id=? AND status='queued'", (now, now, hook_id))
            self._db.execute("DELETE FROM breakers WHERE hook_id=?", (hook_id,))
            for k in (f"digest_day:{hook_id}", f"digest_at:{hook_id}"):
                self._db.execute("DELETE FROM meta WHERE k=?", (k,))
            self._db.execute("DELETE FROM meta WHERE k LIKE ?", (f"digest_try:{hook_id}:%",))
            self._db.execute("DELETE FROM dedup WHERE hook_id=?", (hook_id,))

    def prune(self, now: Optional[float] = None, keep_days: Optional[dict] = None) -> int:
        """Finished events older than KEEP_DAYS, and past KEEP_PER_HOOK per hook; bodies of finished events after
        BODY_KEEP_DAYS; idempotency keys after DEDUP_KEEP_DAYS (by age, whatever happened to their event)."""
        now = time.time() if now is None else now
        cut = now - KEEP_DAYS * 86400
        # `unknown` and `waiting` (an answer or an approval the owner still owes) are kept, with their body.
        ran = "('done','silent','failed','dead')"
        ign = "('filtered','invalid','duplicate')"
        fin = "('done','silent','failed','dead','filtered','invalid','duplicate')"
        with self._write():
            # Stale owner items: an approval or question nobody answered in APPROVAL_TTL_DAYS ends, so it cannot hold
            # space forever. The event is settled (failed: "nobody answered") and stays in the log like any other.
            stale = [r[0] for r in self._db.execute(
                "SELECT id FROM events WHERE status='waiting' AND finished_at>0 AND finished_at<?",
                (now - APPROVAL_TTL_DAYS * 86400,))]
            for sid in stale:
                self._db.execute("UPDATE branches SET status='cancelled', detail='approval expired: nobody answered',"
                                 " finished_at=? WHERE event_id=? AND status='approval'", (now, sid))
                self._db.execute("UPDATE branches SET status='failed', detail='no answer from the owner', finished_at=?"
                                 " WHERE event_id=? AND status='waiting'", (now, sid))
                self._db.execute("UPDATE events SET status='failed', error='expired: nobody answered in "
                                 f"{APPROVAL_TTL_DAYS} days', finished_at=?, notified_at=? WHERE id=?", (now, now, sid))
            ids = [r[0] for r in self._db.execute(
                f"SELECT id FROM events WHERE status IN {fin} AND finished_at>0 AND finished_at<?", (cut,))]
            for hid_k, days in (keep_days or {}).items():
                # M5: a hook's own retention (shorter or longer than the default, at most KEEP_DAYS_MAX).
                d = max(1, min(int(days or KEEP_DAYS), KEEP_DAYS_MAX))
                if d < KEEP_DAYS:
                    ids += [r[0] for r in self._db.execute(
                        f"SELECT id FROM events WHERE hook_id=? AND status IN {fin} AND finished_at>0 AND finished_at<?",
                        (hid_k, now - d * 86400))]
            if keep_days:
                longer = {h: max(1, min(int(d or KEEP_DAYS), KEEP_DAYS_MAX)) for h, d in keep_days.items()
                          if int(d or KEEP_DAYS) > KEEP_DAYS}
                ids = [i for i in ids if not self._kept_longer(i, longer, now)]
            for (hid,) in self._db.execute("SELECT DISTINCT hook_id FROM events").fetchall():
                for group, keep in ((ran, KEEP_PER_HOOK), (ign, KEEP_IGNORED_PER_HOOK)):
                    ids += [r[0] for r in self._db.execute(
                        f"SELECT id FROM events WHERE hook_id=? AND status IN {group} ORDER BY received_at DESC"
                        " LIMIT -1 OFFSET ?", (hid, keep))]
            ids = list(dict.fromkeys(ids))
            if ids:
                # A failed/dead event whose business key is still live stays: without it the order could neither be
                # retried nor resent (the key refuses the source's copy as a duplicate).
                held = {r[0] for r in self._db.execute(
                    "SELECT e.id FROM events e JOIN biz_keys b ON b.event_id=e.id WHERE e.status IN ('failed','dead')"
                    " AND b.expires_at>?", (now,))}
                ids = [x for x in ids if x not in held]
            if ids:
                # Nothing received in the last RECENT_KEEP_S goes, whatever the caps say: the day quota and the AI
                # budget are counted from these rows.
                recent = set()
                for i in range(0, len(ids), 500):
                    chunk = ids[i:i + 500]
                    q = ",".join("?" * len(chunk))
                    recent |= {r[0] for r in self._db.execute(
                        f"SELECT id FROM events WHERE id IN ({q}) AND received_at>? AND status NOT IN"
                        " ('filtered','invalid','duplicate')", chunk + [now - RECENT_KEEP_S])}
                ids = [x for x in ids if x not in recent]
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                q = ",".join("?" * len(chunk))
                self._db.execute(f"DELETE FROM attempts WHERE event_id IN ({q})", chunk)
                self._db.execute(f"DELETE FROM branches WHERE event_id IN ({q})", chunk)
                self._db.execute(f"DELETE FROM events WHERE id IN ({q})", chunk)
            # Keys are kept by AGE, not with their event: a sender retrying for days must still get "duplicate".
            self._db.execute("DELETE FROM dedup WHERE created_at<?", (now - DEDUP_KEEP_DAYS * 86400,))
            self._db.execute("DELETE FROM ai_runs WHERE at<?", (now - 3 * 86400,))
            # Business keys live for their own TTL, not with their event (an order seen 20 days ago is still seen).
            self._db.execute("DELETE FROM biz_keys WHERE expires_at<=? AND event_id NOT IN (SELECT id FROM events WHERE"
                             " status IN ('queued','running'))", (now,))
            self._db.execute(f"UPDATE events SET body=x'' WHERE status IN {fin} AND finished_at>0 AND finished_at<?"
                             " AND length(body)>0", (now - BODY_KEEP_DAYS * 86400,))
        try:
            with self._lock:
                self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.OperationalError:
            pass
        return len(ids)
