"""webhook_store.py - durable receive, evaluation and dispatch for webhook events (0.274.0, webhook platform).

Before this module an accepted event lived only in RAM (a deque per hook): a restart, a crash or an update between the
202 and the run lost it, while the sender had already been told "accepted" and would not retry. And the idempotency
key was written to webhooks.json BEFORE the queue decided, so a 429 kept the key and the sender's retry was answered
"duplicate" (fixed in 0.274.0: here the key and the event are one transaction).

Spec of record: docs/superpowers/specs/2026-10-19-webhook-event-platform-design.md (§4, §6, §7, §11, §13). The rules
this store keeps, each checked by the tests named in docs/webhook-platform/README.md:

  1. ACK only after commit. `ingest()` writes the event row, its delivery key and its receipt in ONE transaction; the
     202 is returned only after that commit. A refusal (429, 503) keeps nothing: no event, no key.
  2. Delivery dedup is (hook, policy kind + key) -> event, unique in SQLite, so two copies arriving at once (threads,
     processes) cannot both be stored. A duplicate only adds a short receipt row.
  3. The hook's rules are applied AFTER the commit, by `triage_*` (any worker, any process): the decision (ignored,
     quarantined, or run), the business key and the deliveries are written in ONE transaction, conditional on the event
     still being `received`, so two workers never both decide.
  4. A worker CLAIMS an event with a lease and a fencing number (`fence` grows at every claim). Every later write of
     that worker is conditional on its fence, so a worker whose lease ran out can never overwrite the newer owner's
     result.
  5. A delivery is marked dispatched (committed) BEFORE its effect starts. A lease that expires after that point does
     NOT run it again on its own: it becomes `unknown` (it may have acted), unless the delivery was marked retry-safe
     (the receiver drops a second copy of the same delivery id), in which case it is tried again.
  6. Hooks live here too (`hooks` + `hook_revisions`): an event records the revision it arrived under, and its run uses
     that revision's configuration, while permissions are those of the hook NOW.

Event states (internal):  received -> queued -> running -> done | silent | waiting | blocked | failed | unknown |
dead | cancelled, and the ignored ones decided by triage: filtered | invalid | duplicate. The API shows the spec's
names (`spec_event_state`, `spec_delivery_state`). Nothing here imports main or calls a model.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Iterable, Optional

SCHEMA_VERSION = 7
MiB = 1024 * 1024
# Limits (spec §11). Starting values, not measured capacity; each hook may change its own within bounds.
BODY_DEFAULT = 256 * 1024
BODY_CEILING = 2 * MiB
INGRESS_PER_MIN = 300
INGRESS_BURST = 100           # events accepted in any 10 s (the burst of the per-minute rate)
BACKLOG_MAX = 10000           # unsettled events of one hook (received, queued, running, unknown, waiting, blocked)
BACKLOG_BYTES = 256 * MiB     # and their bodies
DB_MAX_BYTES = 1024 * MiB     # live pages plus the WAL: past this, evict finished events, then refuse (503)
DISK_RESERVE = 128 * MiB      # free disk kept: past it, refuse rather than fill the disk
RATE_PER_HOUR = 0             # optional hour cap (0 = off: code-only processing is not limited to 30/hour any more)
LEASE_S = 120.0
HEARTBEAT_S = 30.0
MAX_AUTO_TRIES = 3            # automatic retries of a failure BEFORE any dispatch (poison guard)
SAFE_RESEND_MAX = 4           # a retry-safe delivery found running after a crash is resent below this many attempts
                              # (webhook_actions.MAX_BRANCH_TRIES), never past it
BACKOFF_S = (5.0, 30.0, 120.0)
KEEP_DAYS = 30                # metadata of finished events
KEEP_PER_HOOK = 5000          # finished runs kept per hook (rows), apart from the ignored ones
KEEP_IGNORED_PER_HOOK = 2000  # ignored/quarantined events kept per hook
KEEP_DAYS_MAX = 365
BODY_KEEP_DAYS = 7            # body of a FINISHED event; unknown/waiting/blocked keep theirs until settled
RETRY_WINDOW_S = 24 * 3600.0  # an owner's retry gets this window from now unless the hook sets its own (deadline_h)
DEP_CANCEL = "not run: an action it depends on did not succeed"   # the detail of a dependent the owner's retry re-runs
DEDUP_KEEP_DAYS = 7           # delivery keys outlive their events (Stripe/Shopify retry for up to 72 h)
NOTIFY_TRIES = 5
RECEIPTS_PER_HOUR = 600       # duplicate receipts logged per hook per hour (accepted events always get one)
APPROVAL_TTL_DAYS = 14
RECENT_KEEP_S = 90000.0       # nothing received in the last 25 h is cap-pruned (quotas count those rows)
BREAKER_FAILS = 5
BREAKER_COOLDOWN_S = 600.0
BREAKER_MAX_S = 3600.0
OPEN = ("received", "queued", "running", "unknown", "waiting", "blocked")   # count toward the backlog
FINAL = ("done", "silent", "waiting", "blocked", "failed", "unknown", "dead", "cancelled")
IGNORED = ("filtered", "invalid", "duplicate")
SETTLED = ("done", "silent", "failed", "dead", "cancelled") + IGNORED
# Delivery states. pending/retry: may run; running: dispatched, outcome not written; the rest are final for the run.
BRANCH_FINAL = ("completed", "accepted", "silent", "waiting", "cancelled", "failed", "unknown", "approval", "blocked")
BRANCH_OK = ("completed", "accepted", "silent")
SPEC_DELIVERY = {"pending": "pending", "retry": "retry_wait", "running": "running", "completed": "succeeded",
                 "silent": "succeeded", "accepted": "waiting_result", "waiting": "waiting_approval",
                 "approval": "waiting_approval", "blocked": "blocked", "unknown": "unknown", "failed": "dead",
                 "cancelled": "cancelled"}
JSON_COL_MAX = 64000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS hooks(
    id TEXT PRIMARY KEY,
    brain TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    token_hash TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    paused INTEGER NOT NULL DEFAULT 0,
    revision INTEGER NOT NULL DEFAULT 1,
    config TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL DEFAULT 0,
    runs INTEGER NOT NULL DEFAULT 0,
    last_at REAL NOT NULL DEFAULT 0,
    last_status TEXT NOT NULL DEFAULT '',
    legacy INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS hook_revisions(
    hook_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    config TEXT NOT NULL,
    at REAL NOT NULL,
    by TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(hook_id, revision)
);
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
CREATE INDEX IF NOT EXISTS ix_ev_hook_status ON events(hook_id, status);
CREATE TABLE IF NOT EXISTS dedup(
    hook_id TEXT NOT NULL,
    idem_key TEXT NOT NULL,
    event_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY(hook_id, idem_key)
);
CREATE TABLE IF NOT EXISTS receipts(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hook_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    at REAL NOT NULL,
    result TEXT NOT NULL,
    idem TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_rc_hook ON receipts(hook_id, at);
CREATE INDEX IF NOT EXISTS ix_rc_ev ON receipts(event_id);
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
CREATE TABLE IF NOT EXISTS deliveries(
    event_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    generation INTEGER NOT NULL DEFAULT 1,
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
    safe INTEGER NOT NULL DEFAULT 0,
    deadline REAL NOT NULL DEFAULT 0,
    depends TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY(event_id, action_id, generation)
);
CREATE TABLE IF NOT EXISTS delivery_attempts(
    event_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    generation INTEGER NOT NULL,
    n INTEGER NOT NULL,
    worker TEXT NOT NULL,
    fence INTEGER NOT NULL,
    started_at REAL NOT NULL,
    ended_at REAL NOT NULL DEFAULT 0,
    request_sha TEXT NOT NULL DEFAULT '',
    http_status INTEGER NOT NULL DEFAULT 0,
    outcome TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    maybe_acted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_da_ev ON delivery_attempts(event_id, action_id, generation, n);
CREATE TABLE IF NOT EXISTS notifications(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dkey TEXT NOT NULL UNIQUE,
    hook_id TEXT NOT NULL DEFAULT '',
    event_id TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL,
    chat_id TEXT NOT NULL DEFAULT '',
    brain TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL,
    web TEXT NOT NULL DEFAULT '',
    viec TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    tries INTEGER NOT NULL DEFAULT 0,
    next_at REAL NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    sent_at REAL NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_nt_due ON notifications(status, next_at);
CREATE TABLE IF NOT EXISTS audit(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at REAL NOT NULL,
    action TEXT NOT NULL,
    hook_id TEXT NOT NULL DEFAULT '',
    event_id TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS ai_runs(
    hook_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ai_runs ON ai_runs(hook_id, at);
CREATE INDEX IF NOT EXISTS ix_ai_runs_at ON ai_runs(at);
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
_EVENT_COLUMNS = (("trace", "TEXT NOT NULL DEFAULT '{}'"), ("fields", "TEXT NOT NULL DEFAULT '{}'"),
                  ("biz_key", "TEXT NOT NULL DEFAULT ''"), ("biz_ttl", "REAL NOT NULL DEFAULT 0"),
                  ("hook_rev", "INTEGER NOT NULL DEFAULT 0"), ("headers", "TEXT NOT NULL DEFAULT '{}'"),
                  ("verified_at", "REAL NOT NULL DEFAULT 0"), ("key_version", "TEXT NOT NULL DEFAULT ''"),
                  ("correlation", "TEXT NOT NULL DEFAULT ''"), ("provider_id", "TEXT NOT NULL DEFAULT ''"),
                  ("generation", "INTEGER NOT NULL DEFAULT 1"), ("size", "INTEGER NOT NULL DEFAULT 0"),
                  ("reasons", "TEXT NOT NULL DEFAULT '[]'"))
_DELIVERY_COLS = ("event_id, action_id, generation, kind, delivery_id, status, tries, next_at, dispatched_at,"
                  " finished_at, detail, receipt, result, approved_at, safe, deadline, depends")
PROVIDER_KEY_PREFIXES = ("stripe:", "github:", "shopify:", "systeme_io:")


def _dumps(v, limit: int = JSON_COL_MAX) -> str:
    """JSON for a column: always valid. Unserialisable or oversized -> a small marker object instead of a slice."""
    try:
        t = json.dumps(v if v is not None else {}, ensure_ascii=False, default=str, allow_nan=False)
    except (ValueError, TypeError, OverflowError, RecursionError):
        return json.dumps({"_unstorable": True})
    return t if len(t) <= limit else json.dumps({"_truncated": True, "size": len(t)})


def _loads(t, fallback):
    try:
        v = json.loads(t or "")
        return v if isinstance(v, type(fallback)) else fallback
    except (ValueError, TypeError):
        return fallback


def _crash(point: str) -> None:
    """Fault injection for the crash tests (run in a child process). Does nothing unless JAVIS_WH_CRASH_AT names this
    exact point."""
    if os.environ.get("JAVIS_WH_CRASH_AT") == point:
        os._exit(77)


def idem_storage_key(key: str, kind: str) -> str:
    """The delivery key as stored: its POLICY KIND first (`h:` a sender's Idempotency-Key header, `p:` the provider's
    own message id), so the two kinds never collide (spec §6.1)."""
    k = str(key or "").strip()[:200]
    return ("p:" if kind == "provider" else "h:") + k if k else ""


def spec_delivery_state(status: str) -> str:
    return SPEC_DELIVERY.get(status, status)


def spec_event_state(status: str, deliveries: Optional[list] = None) -> str:
    """The event's state in the spec's words (§7): ignored, quarantined, processing, waiting, done, partial_failed,
    failed, cancelled."""
    if status in ("filtered", "duplicate"):
        return "ignored"
    if status == "invalid":
        return "quarantined"
    if status in ("received", "queued", "running"):
        return "processing"
    if status in ("waiting", "unknown", "blocked"):
        return "waiting"
    if status in ("done", "silent"):
        return "done"
    if status == "cancelled":
        return "cancelled"
    if status in ("failed", "dead"):
        if any((d.get("status") in BRANCH_OK) for d in deliveries or []):
            return "partial_failed"
        return "failed"
    return status


def dep_state(row: dict, by_id: dict) -> str:
    """ready | wait (a dependency still runs) | held (a dependency waits for the owner, or was only queued by its
    receiver while this one needs it finished) | doomed (a dependency failed or was cancelled)."""
    deps = row.get("depends")
    if isinstance(deps, str):
        deps = _loads(deps, [])
    st = "ready"
    for d in deps or []:
        dep = by_id.get(d.get("id"))
        if dep is None:
            continue
        s = dep["status"]
        if s in ("completed", "silent") or (s == "accepted" and d.get("on") == "accepted"):
            continue
        if s in ("failed", "cancelled"):
            return "doomed"
        if s in ("pending", "retry", "running"):
            st = "wait"
        elif st == "ready":
            st = "held"
    return st


class Busy(Exception):
    """The store refused to take an event (disk cap, free disk, database locked past the timeout)."""

    def __init__(self, msg: str, code: str = "store_busy"):
        super().__init__(msg)
        self.code = code


class Conflict(Exception):
    """A hook was changed meanwhile (another tab): the caller reloads and tries again."""

    def __init__(self, revision: int):
        super().__init__("revision_conflict")
        self.revision = revision


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
        self.busy_count = 0
        self._db = sqlite3.connect(str(self.path), timeout=5, isolation_level=None, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        mode = str(self._db.execute("PRAGMA journal_mode=WAL").fetchone()[0]).lower()
        if mode != "wal":
            import sys
            print(f"[webhook_store] journal_mode is {mode}, not wal (network drive?): writes may block readers",
                  file=sys.stderr)
        self._db.execute("PRAGMA synchronous=FULL")      # an ACKed event must survive a power cut
        self._db.execute("PRAGMA busy_timeout=5000")     # finite: past it the sender gets 503 and retries
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute("PRAGMA journal_size_limit=16777216")   # the WAL is truncated back to 16 MB at checkpoints
        with self._lock:
            self._db.executescript(_SCHEMA)
            self._migrate()

    def _migrate(self) -> None:
        """v1..v6 -> v7 in place, under BEGIN IMMEDIATE and re-read inside it (several processes may open one old file
        at once). Never LOWERS the version marker: an older build opening a newer file leaves it as it is."""
        self._tx()
        try:
            have = {r[1] for r in self._db.execute("PRAGMA table_info(events)")}
            for col, decl in _EVENT_COLUMNS:
                if col not in have:
                    self._db.execute(f"ALTER TABLE events ADD COLUMN {col} {decl}")
            # Indexes for the paged log across hooks, the order / correlation search and retention (spec §12: no
            # whole-table read). Here, after the columns exist on an upgraded file.
            for ix in ("ix_ev_received ON events(received_at)", "ix_ev_corr ON events(correlation)",
                       "ix_ev_prov ON events(provider_id)", "ix_ev_idem ON events(idem_key)",
                       "ix_dd_created ON dedup(created_at)", "ix_dd_event ON dedup(event_id)"):
                self._db.execute(f"CREATE INDEX IF NOT EXISTS {ix}")
            old = self._db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='branches'").fetchone()
            if old is not None:
                cols = {r[1] for r in self._db.execute("PRAGMA table_info(branches)")}
                appr = "approved_at" if "approved_at" in cols else "0"
                # v6 branches -> v7 deliveries (generation 1). Kept as one INSERT ... SELECT inside the transaction.
                self._db.execute(
                    "INSERT OR IGNORE INTO deliveries(event_id, action_id, generation, kind, delivery_id, status, tries,"
                    " next_at, dispatched_at, finished_at, detail, receipt, result, approved_at) SELECT event_id,"
                    f" action_id, 1, kind, delivery_id, status, tries, next_at, dispatched_at, finished_at, detail,"
                    f" receipt, result, {appr} FROM branches")
                self._db.execute("DROP TABLE branches")
            if self._db.execute("SELECT 1 FROM meta WHERE k='dedup_kinds'").fetchone() is None:
                cond = " OR ".join(f"idem_key LIKE '{p}%'" for p in PROVIDER_KEY_PREFIXES)
                self._db.execute(f"UPDATE dedup SET idem_key='p:'||idem_key WHERE ({cond}) AND idem_key NOT LIKE 'p:%'"
                                 " AND idem_key NOT LIKE 'h:%'")
                self._db.execute("UPDATE dedup SET idem_key='h:'||idem_key WHERE idem_key NOT LIKE 'p:%' AND"
                                 " idem_key NOT LIKE 'h:%'")
                self._db.execute("UPDATE events SET size=length(body) WHERE size=0")
                self._db.execute("INSERT OR REPLACE INTO meta(k, v) VALUES('dedup_kinds', '1')")
            row = self._db.execute("SELECT v FROM meta WHERE k='schema_version'").fetchone()
            if row is None or int(row["v"]) < SCHEMA_VERSION:
                self._db.execute("INSERT OR REPLACE INTO meta(k, v) VALUES('schema_version', ?)", (str(SCHEMA_VERSION),))
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
        """BEGIN IMMEDIATE: the write lock is taken at the start, so check-then-insert is atomic across processes too."""
        self._db.execute("BEGIN IMMEDIATE")

    @contextlib.contextmanager
    def _write(self):
        """One write transaction: committed when the block ends (also on `return`), rolled back on any exception, so a
        failure can never leave the shared connection inside an open transaction."""
        with self._lock:
            self._tx()
            try:
                yield
                self._db.execute("COMMIT")
            except BaseException:
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
        """LIVE data in the database: pages in use (free pages left by deletions do not count)."""
        with self._read():
            pc = self._db.execute("PRAGMA page_count").fetchone()[0]
            fl = self._db.execute("PRAGMA freelist_count").fetchone()[0]
            ps = self._db.execute("PRAGMA page_size").fetchone()[0]
        return int((pc - fl) * ps)

    def wal_bytes(self) -> int:
        try:
            return os.path.getsize(str(self.path) + "-wal")
        except OSError:
            return 0

    def disk_free(self) -> int:
        try:
            return int(shutil.disk_usage(str(self.path.parent)).free)
        except OSError:
            return 1 << 62

    def checkpoint(self) -> None:
        """Fold the WAL back into the database and truncate it (it counts against the cap). Best effort: a reader in
        another process may keep part of it for a moment."""
        try:
            with self._lock:
                self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.OperationalError:
            pass

    def used_bytes(self) -> int:
        """What counts against DB_MAX_BYTES: live pages plus the WAL (spec §11: the WAL counts too)."""
        return self.size_bytes() + self.wal_bytes()

    def space_state(self) -> dict:
        used, free = self.used_bytes(), self.disk_free()
        return {"db_bytes": self.size_bytes(), "wal_bytes": self.wal_bytes(), "used": used, "cap": DB_MAX_BYTES,
                "disk_free": free, "reserve": DISK_RESERVE,
                "level": "full" if used >= DB_MAX_BYTES or free < DISK_RESERVE else
                         "warn" if used >= DB_MAX_BYTES * 0.8 or free < DISK_RESERVE * 2 else "ok"}

    def backup(self, dest: Path) -> Path:
        """A consistent copy through SQLite's backup API (never a plain copy of a file with a WAL), mode 600."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.close(os.open(str(dest), os.O_CREAT | os.O_RDWR | os.O_TRUNC, 0o600))
        out = sqlite3.connect(str(dest))
        try:
            with self._lock:
                self._db.backup(out)
        finally:
            out.close()
        os.chmod(dest, 0o600)
        return dest

    # ── hooks (spec §13: the configuration lives here, with its revisions) ──
    @staticmethod
    def _hook_row(r) -> dict:
        h = _loads(r["config"], {})
        h.update(id=r["id"], brain=r["brain"], name=r["name"], token_hash=r["token_hash"],
                 enabled=bool(r["enabled"]), paused=bool(r["paused"]), revision=int(r["revision"]),
                 created_at=r["created_at"], updated_at=r["updated_at"], count=int(r["runs"]), last_at=r["last_at"],
                 last_status=r["last_status"], legacy=bool(r["legacy"]))
        return h

    _HOOK_COLS = ("id", "brain", "name", "token_hash", "enabled", "paused", "revision", "created_at", "updated_at",
                  "count", "last_at", "last_status", "legacy", "seen_keys", "runs")

    @classmethod
    def _config_of(cls, hook: dict) -> dict:
        return {k: v for k, v in hook.items() if k not in cls._HOOK_COLS}

    def hooks_all(self, brain: str = "") -> list:
        with self._read():
            rows = self._db.execute("SELECT * FROM hooks" + (" WHERE brain=?" if brain else "") +
                                    " ORDER BY created_at, id", (brain,) if brain else ()).fetchall()
        return [self._hook_row(r) for r in rows]

    def hook_get(self, hid: str) -> Optional[dict]:
        with self._read():
            r = self._db.execute("SELECT * FROM hooks WHERE id=?", (hid,)).fetchone()
        return self._hook_row(r) if r else None

    def hook_count(self) -> int:
        with self._read():
            return int(self._db.execute("SELECT COUNT(*) FROM hooks").fetchone()[0])

    def hook_revision(self, hid: str, rev: int) -> Optional[dict]:
        with self._read():
            r = self._db.execute("SELECT config FROM hook_revisions WHERE hook_id=? AND revision=?", (hid, rev)).fetchone()
        return _loads(r["config"], {}) if r else None

    def _insert_hook(self, hook: dict, now: float, by: str, legacy: bool = False) -> None:
        cfg = self._config_of(hook)
        self._db.execute(
            "INSERT INTO hooks(id, brain, name, token_hash, enabled, paused, revision, config, created_at, updated_at,"
            " runs, last_at, last_status, legacy) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (hook["id"], str(hook.get("brain") or ""), str(hook.get("name") or ""), str(hook.get("token_hash") or ""),
             1 if hook.get("enabled", True) else 0, 1 if hook.get("paused") else 0, int(hook.get("revision") or 1),
             _dumps(cfg, 10 ** 7), float(hook.get("created_at") or now), now, int(hook.get("count") or 0),
             float(hook.get("last_at") or 0), str(hook.get("last_status") or ""), 1 if legacy else 0))
        self._db.execute("INSERT OR REPLACE INTO hook_revisions(hook_id, revision, config, at, by) VALUES(?,?,?,?,?)",
                         (hook["id"], int(hook.get("revision") or 1), _dumps(cfg, 10 ** 7), now, by))
        # The id lives again (re-imported after a rollback): its tombstone would refuse every dispatch.
        self._db.execute("DELETE FROM meta WHERE k=?", (f"deleted:{hook['id']}",))

    def hook_insert(self, hook: dict, max_hooks: int = 0, now: Optional[float] = None, by: str = "owner") -> int:
        """A new hook at revision 1. Returns 1; raises ValueError('too_many') past `max_hooks`."""
        now = time.time() if now is None else now
        with self._write():
            if max_hooks and int(self._db.execute("SELECT COUNT(*) FROM hooks").fetchone()[0]) >= max_hooks:
                raise ValueError("too_many")
            self._insert_hook(dict(hook, revision=1), now, by)
        return 1

    def hook_update(self, hook: dict, expected: Optional[int] = None, now: Optional[float] = None,
                    by: str = "owner") -> int:
        """Save a changed hook as a NEW revision (the old one stays readable for events that arrived under it).
        `expected` = the revision the caller edited: a different current revision raises Conflict (two tabs). Returns
        the new revision."""
        now = time.time() if now is None else now
        with self._write():
            r = self._db.execute("SELECT revision FROM hooks WHERE id=?", (hook["id"],)).fetchone()
            if r is None:
                raise KeyError(hook["id"])
            cur = int(r["revision"])
            if expected is not None and int(expected) != cur:
                raise Conflict(cur)
            rev = cur + 1
            cfg = self._config_of(hook)
            self._db.execute("UPDATE hooks SET brain=?, name=?, token_hash=?, enabled=?, paused=?, revision=?, config=?,"
                             " updated_at=? WHERE id=?",
                             (str(hook.get("brain") or ""), str(hook.get("name") or ""),
                              str(hook.get("token_hash") or ""), 1 if hook.get("enabled", True) else 0,
                              1 if hook.get("paused") else 0, rev, _dumps(cfg, 10 ** 7), now, hook["id"]))
            self._db.execute("INSERT OR REPLACE INTO hook_revisions(hook_id, revision, config, at, by) VALUES(?,?,?,?,?)",
                             (hook["id"], rev, _dumps(cfg, 10 ** 7), now, by))
            # A delivery `blocked` on this hook's configuration (a missing credential, a plugin that was off, a 401)
            # may work now: it runs again (spec §7: blocked waits for the configuration to be fixed).
            self._unblock(hook["id"], now)
        return rev

    def unblock(self, hid: str, now: Optional[float] = None) -> int:
        """The owner fixed the cause OUTSIDE the hook (plugin switched back on, receiver key fixed, Apps Script
        redeployed): run the blocked deliveries of this hook again. Nothing acted for them (a block is decided before
        the receiver did anything), so this cannot double an effect. Audited. Returns events re-queued."""
        now = time.time() if now is None else now
        with self._write():
            n = self._unblock(hid, now)
            if n:
                self._audit(now, "retry_blocked", hid, "", f"{n} events")
        return n

    def _unblock(self, hid: str, now: float) -> int:
        ids = [r[0] for r in self._db.execute(
            "SELECT DISTINCT e.id FROM events e JOIN deliveries d ON d.event_id=e.id AND d.generation=e.generation"
            " WHERE e.hook_id=? AND d.status='blocked'", (hid,))]
        for eid in ids:
            self._db.execute("UPDATE deliveries SET status='pending', next_at=0, finished_at=0, detail=detail ||"
                             " ' | configuration changed: tried again' WHERE event_id=? AND status='blocked' AND"
                             " generation=(SELECT generation FROM events WHERE id=?)", (eid, eid))
            self._db.execute("UPDATE events SET status='queued', next_at=?, finished_at=0, notified_at=0,"
                             " notify_tries=0, tries=0, dispatched_at=0 WHERE id=? AND status IN ('blocked','failed',"
                             "'waiting','unknown','done')", (now, eid))
        return len(ids)

    def rewrite_revisions(self, hid: str, fn) -> int:
        """Apply `fn(config) -> config` to every stored revision of a hook (secret scrubbing). Returns rows changed."""
        n = 0
        with self._write():
            for r in self._db.execute("SELECT revision, config FROM hook_revisions WHERE hook_id=?", (hid,)).fetchall():
                old = r["config"]
                new = _dumps(fn(_loads(old, {})), 10 ** 7)
                if new != old:
                    self._db.execute("UPDATE hook_revisions SET config=? WHERE hook_id=? AND revision=?",
                                     (new, hid, r["revision"]))
                    n += 1
            row = self._db.execute("SELECT config FROM hooks WHERE id=?", (hid,)).fetchone()
            if row is not None:
                new = _dumps(fn(_loads(row["config"], {})), 10 ** 7)
                if new != row["config"]:
                    self._db.execute("UPDATE hooks SET config=? WHERE id=?", (new, hid))
                    n += 1
        return n

    def hook_set(self, hid: str, **cols) -> bool:
        """Columns that are state, not configuration (token, switches, stats): no new revision."""
        allowed = {"token_hash", "enabled", "paused", "runs", "last_at", "last_status"}
        cols = {k: v for k, v in cols.items() if k in allowed}
        if not cols:
            return False
        with self._write():
            cur = self._db.execute("UPDATE hooks SET " + ", ".join(f"{k}=?" for k in cols) + ", updated_at=? WHERE id=?",
                                   tuple(cols.values()) + (time.time(), hid))
            return cur.rowcount == 1

    def hook_ran(self, hid: str, status: str, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        with self._write():
            self._db.execute("UPDATE hooks SET runs=runs+1, last_at=?, last_status=? WHERE id=?", (now, status, hid))

    def hook_delete(self, hid: str) -> bool:
        with self._write():
            cur = self._db.execute("DELETE FROM hooks WHERE id=?", (hid,))
            return cur.rowcount == 1

    def import_hooks(self, hooks: list, now: Optional[float] = None) -> int:
        """Migration from webhooks.json (spec §13), idempotent: a hook already here keeps its rows; one changed in the
        JSON since (a rollback to an older build, then an upgrade again) becomes a new revision. Legacy seen keys stay
        duplicates. The marker is written in the same transaction. Returns hooks imported or updated."""
        now = time.time() if now is None else now
        n = 0
        with self._write():
            # After a rollback (server/webhook_rollback.py) the file holds hooks the tool switched OFF only because the
            # older build could not run them: their own switch comes back from what the tool recorded, never from
            # the forced value. A hook the store has but the file lost was deleted in the older build: it stops
            # receiving (kept, not deleted, so nothing of its log is lost), audited.
            row = self._db.execute("SELECT v FROM meta WHERE k='rollback_state'").fetchone()
            rb = _loads(row[0], {}) if row else {}
            forced = set(rb.get("forced_off") or [])
            listed = {h["id"] for h in hooks or [] if isinstance(h, dict) and h.get("id")}
            for hid in rb.get("hooks") or []:
                if hid not in listed:
                    if self._db.execute("UPDATE hooks SET enabled=0, updated_at=? WHERE id=? AND enabled=1",
                                        (now, hid)).rowcount:
                        self._audit(now, "rollback:deleted_in_older_build", hid, "", "receiving stopped")
            for h in hooks or []:
                if not isinstance(h, dict) or not h.get("id"):
                    continue
                h = dict(h)
                if h["id"] in forced and not h.get("enabled", True):
                    h["enabled"] = bool((rb.get("enabled") or {}).get(h["id"], True))
                r = self._db.execute("SELECT config, revision, token_hash, enabled, name, brain FROM hooks WHERE id=?",
                                     (h["id"],)).fetchone()
                if r is None:
                    self._insert_hook(dict(h, revision=1), now, "migration", legacy=True)
                    n += 1
                else:
                    cfg = _loads(r["config"], {})
                    new_cfg = dict(cfg, **self._config_of(h))
                    if (new_cfg != cfg or r["token_hash"] != h.get("token_hash") or r["name"] != h.get("name")
                            or bool(r["enabled"]) != bool(h.get("enabled", True))):
                        rev = int(r["revision"]) + 1
                        self._db.execute("UPDATE hooks SET name=?, token_hash=?, enabled=?, revision=?, config=?,"
                                         " updated_at=? WHERE id=?", (str(h.get("name") or r["name"]),
                                                                      str(h.get("token_hash") or r["token_hash"]),
                                                                      1 if h.get("enabled", True) else 0, rev,
                                                                      _dumps(new_cfg, 10 ** 7), now, h["id"]))
                        self._db.execute("INSERT OR REPLACE INTO hook_revisions(hook_id, revision, config, at, by)"
                                         " VALUES(?,?,?,?,?)", (h["id"], rev, _dumps(new_cfg, 10 ** 7), now, "migration"))
                        n += 1
                for k in h.get("seen_keys") or []:
                    k = idem_storage_key(k, "header")
                    if k:
                        self._db.execute("INSERT OR IGNORE INTO dedup(hook_id, idem_key, event_id, created_at)"
                                         " VALUES(?,?,'',?)", (h["id"], k, now))
            self._db.execute("INSERT OR REPLACE INTO meta(k, v) VALUES('hooks_migrated', ?)", (str(now),))
            self._db.execute("INSERT OR REPLACE INTO meta(k, v) VALUES('legacy_keys_imported', ?)", (str(now),))
            self._db.execute("DELETE FROM meta WHERE k='rollback_state'")
        return n

    def hold_for_rollback(self, ids: list, now: Optional[float] = None) -> int:
        """The rollback tool exported these unsettled events for the owner to reconcile: they become unknown (the owner
        decides: Mark done or Retry), so an upgrade later never runs them on its own beside a manual resend."""
        now = time.time() if now is None else now
        n = 0
        with self._write():
            for eid in ids:
                cur = self._db.execute("UPDATE events SET status='unknown', error='exported at rollback: reconcile it"
                                       " from backlog.jsonl, then Mark done or Retry', lease_owner='', lease_until=0,"
                                       " finished_at=?, notified_at=? WHERE id=? AND status IN ('received','queued',"
                                       "'running','waiting','blocked','unknown')", (now, now, eid))
                if cur.rowcount:
                    self._db.execute("UPDATE deliveries SET status='unknown', detail='exported at rollback', finished_at=?"
                                     " WHERE event_id=? AND status IN ('pending','retry','running','approval','waiting',"
                                     "'blocked')", (now, eid))
                    n += 1
        return n

    def import_legacy_keys(self, hook_id: str, keys: Iterable[str], now: Optional[float] = None) -> int:
        """Keys a pre-0.274.0 hook kept in webhooks.json stay duplicates after the upgrade (bounded tombstones: they
        go after DEDUP_KEEP_DAYS). They point at no event (the old runs were never stored)."""
        now = time.time() if now is None else now
        n = 0
        with self._write():
            for k in keys:
                k = idem_storage_key(k, "header")
                if k:
                    cur = self._db.execute("INSERT OR IGNORE INTO dedup(hook_id, idem_key, event_id, created_at)"
                                           " VALUES(?,?,'',?)", (hook_id, k, now))
                    n += cur.rowcount
        return n

    # ── space ──
    def make_room(self, need: int = 0, now: Optional[float] = None) -> int:
        """Near the cap: free space from SETTLED events the owner has already been told about, oldest first: ignored
        ones first, then bodies of finished runs, then whole rows. Never an open event (received, queued, running,
        unknown, waiting, blocked: spec §11, never drop pending work to make room), never a failed or dead one (its body
        is what the owner's retry sends: kept until the owner settles or deletes it), never one whose notice is still
        due, never one holding a live business key. Last resort: delivery keys past their own keep time
        (DEDUP_KEEP_DAYS: senders retry for days), never younger ones: past that the store refuses (503)."""
        now = time.time() if now is None else now
        self.checkpoint()
        target = int(DB_MAX_BYTES * 0.8) - int(need)
        n = 0
        # Quarantined (invalid) events go only once the owner was told, after the merely ignored ones.
        told = ("status IN ('done','silent','cancelled','filtered','invalid','duplicate') AND"
                " (notified_at>0 OR status IN ('silent','cancelled')) AND id NOT IN (SELECT event_id FROM biz_keys)")
        steps = ("SELECT id FROM events WHERE status IN ('filtered','duplicate') ORDER BY received_at LIMIT 100",
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
                        self._delete_events(ids)
                n += len(ids)
        while self.size_bytes() > target:
            with self._write():
                cur = self._db.execute("DELETE FROM dedup WHERE rowid IN (SELECT rowid FROM dedup WHERE created_at<?"
                                       " ORDER BY created_at LIMIT 2000)", (now - DEDUP_KEEP_DAYS * 86400,))
            if cur.rowcount <= 0:
                break
            n += cur.rowcount
        return n

    def _delete_events(self, ids: list) -> None:
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            q = ",".join("?" * len(chunk))
            for t in ("attempts", "deliveries", "delivery_attempts", "receipts"):
                self._db.execute(f"DELETE FROM {t} WHERE event_id IN ({q})", chunk)
            self._db.execute(f"DELETE FROM events WHERE id IN ({q})", chunk)

    # ── receive ──
    def ingest(self, hook: dict, body: bytes, content_type: str, idem_key: str = "", now: Optional[float] = None,
               source: str = "http", meta: Optional[dict] = None) -> tuple:
        """Store one authenticated event, BEFORE any rule is applied (spec §4.2). `idem_key` is the stored form
        (`idem_storage_key`). `meta`: headers (the allowed ones), verified_at, key_version, provider_id, event (the
        provider's normalised event), correlation. Returns (code, info):
            (202, {"event_id"})                       stored and committed: only now may the caller answer "accepted";
            (200, {"event_id", "duplicate": True})    the delivery key was already stored for this hook;
            (429, {"reason", "retry_after"})          refused (rate, burst, backlog, bytes), NOTHING stored;
            raises Busy                               the store cannot take it (space, locked): 503, keep nothing.
        """
        now = time.time() if now is None else now
        meta = meta or {}
        key = str(idem_key or "")[:210]
        hid = str(hook["id"])
        lim = hook.get("limits") or {}
        if key:
            # A duplicate is answered even when the store is full or the hook's backlog is: it needs no new body.
            with self._read():
                row = self._db.execute("SELECT event_id FROM dedup WHERE hook_id=? AND idem_key=?", (hid, key)).fetchone()
            if row is not None:
                self._receipt(hid, row["event_id"], now, "duplicate", key, source)
                return 200, {"event_id": row["event_id"], "duplicate": True}
        sp = self.space_state()
        if sp["used"] + len(body) > DB_MAX_BYTES or sp["disk_free"] < DISK_RESERVE + len(body):
            self.make_room(len(body), now)
            sp = self.space_state()
            if sp["used"] + len(body) > DB_MAX_BYTES or sp["disk_free"] < DISK_RESERVE + len(body):
                raise Busy("store full", "store_full")
        eid = "ev_" + uuid.uuid4().hex[:16]
        brain = str(hook.get("brain") or "")
        with self._lock:
            try:
                self._tx()
            except sqlite3.OperationalError as e:
                self.busy_count += 1
                raise Busy(str(e))
            try:
                if key:
                    row = self._db.execute("SELECT event_id FROM dedup WHERE hook_id=? AND idem_key=?",
                                           (hid, key)).fetchone()
                    if row is not None:
                        self._db.execute("COMMIT")
                        self._receipt(hid, row["event_id"], now, "duplicate", key, source)
                        return 200, {"event_id": row["event_id"], "duplicate": True}
                cur_h = self._db.execute("SELECT enabled, revision FROM hooks WHERE id=?", (hid,)).fetchone()
                if cur_h is None and (self._db.execute("SELECT 1 FROM meta WHERE k=?", (f"deleted:{hid}",)).fetchone()
                                      or self._db.execute("SELECT 1 FROM hooks LIMIT 1").fetchone()):
                    # The hook was deleted between the token check and this transaction (its tombstone says so, even
                    # when it was the last one): nothing stored.
                    self._db.execute("ROLLBACK")
                    return 401, {"reason": "off"}
                if cur_h is not None and not cur_h["enabled"]:
                    # Switched off between the token check and this transaction (spec §4.2 step 4): nothing stored.
                    self._db.execute("ROLLBACK")
                    return 401, {"reason": "off"}
                if cur_h is not None:
                    hook = dict(hook, revision=int(cur_h["revision"]))     # the revision current at the commit
                refusal = self._quota(hid, lim, now, len(body))
                if refusal:
                    self._db.execute("ROLLBACK")
                    return 429, refusal
                self._db.execute(
                    "INSERT INTO events(id, hook_id, brain, received_at, content_type, body, body_sha, idem_key,"
                    " hook_snapshot, source, status, next_at, hook_rev, headers, verified_at, key_version, provider_id,"
                    " trace, size) VALUES(?,?,?,?,?,?,?,?,'{}',?,'received',?,?,?,?,?,?,?,?)",
                    (eid, hid, brain, now, str(content_type or "")[:200], bytes(body),
                     hashlib.sha256(bytes(body)).hexdigest(), key, source, now, int(hook.get("revision") or 0),
                     _dumps(meta.get("headers") or {}, 8000), float(meta.get("verified_at") or 0),
                     str(meta.get("key_version") or "")[:40], str(meta.get("provider_id") or "")[:200],
                     _dumps({"event": meta["event"]} if meta.get("event") else {}, 8000), len(body)))
                if key:
                    self._db.execute("INSERT INTO dedup(hook_id, idem_key, event_id, created_at) VALUES(?,?,?,?)",
                                     (hid, key, eid, now))
                self._db.execute("INSERT INTO receipts(hook_id, event_id, at, result, idem, source) VALUES(?,?,?,?,?,?)",
                                 (hid, eid, now, "accepted", key, source))
                _crash("before_commit")
                self._db.execute("COMMIT")
            except sqlite3.IntegrityError:
                self._db.execute("ROLLBACK")
                row = self._db.execute("SELECT event_id FROM dedup WHERE hook_id=? AND idem_key=?", (hid, key)).fetchone()
                return 200, {"event_id": row["event_id"] if row else "", "duplicate": True}
            except sqlite3.OperationalError as e:
                try:
                    self._db.execute("ROLLBACK")
                except Exception:
                    pass
                self.busy_count += 1
                raise Busy(str(e), "store_full" if "full" in str(e).lower() else "store_busy")
            except BaseException:
                try:
                    self._db.execute("ROLLBACK")
                except Exception:
                    pass
                raise
        _crash("after_commit")
        return 202, {"event_id": eid}

    def _quota(self, hid: str, lim: dict, now: float, size: int) -> Optional[dict]:
        """Inside ingest's transaction. None, or the refusal with a Retry-After in seconds."""
        per_min = int(lim.get("per_minute") or INGRESS_PER_MIN)
        burst = int(lim.get("burst") or INGRESS_BURST)
        n10, n60 = self._db.execute(
            "SELECT SUM(received_at>?), COUNT(*) FROM events WHERE hook_id=? AND received_at>?",
            (now - 10, hid, now - 60)).fetchone()
        if int(n10 or 0) >= burst:
            return {"reason": "burst", "retry_after": 10}
        if int(n60 or 0) >= per_min:
            return {"reason": "rate", "retry_after": 60}
        for k, span, why in (("per_hour", 3600, "hour"), ("per_day", 86400, "day")):
            cap = int(lim.get(k) or 0)
            if cap and int(self._db.execute("SELECT COUNT(*) FROM events WHERE hook_id=? AND received_at>? AND status"
                                            " NOT IN ('filtered','invalid','duplicate')",
                                            (hid, now - span)).fetchone()[0]) >= cap:
                return {"reason": why, "retry_after": 600 if why == "hour" else 3600}
        cnt, byts = self._db.execute("SELECT COUNT(*), COALESCE(SUM(size),0) FROM events WHERE hook_id=? AND status IN"
                                     " ('received','queued','running','unknown','waiting','blocked')", (hid,)).fetchone()
        # Bodies kept for failed and dead events (until the owner settles them) count toward the byte quota (§11).
        byts = int(byts) + int(self._db.execute("SELECT COALESCE(SUM(length(body)),0) FROM events WHERE hook_id=? AND"
                                                " status IN ('failed','dead')", (hid,)).fetchone()[0])
        if int(cnt) >= int(lim.get("backlog") or BACKLOG_MAX):
            return {"reason": "backlog", "retry_after": 60}
        if int(byts) + size > int(lim.get("backlog_mb") or BACKLOG_BYTES // MiB) * MiB:
            return {"reason": "backlog_bytes", "retry_after": 60}
        return None

    def _receipt(self, hid: str, eid: str, now: float, result: str, key: str, source: str) -> None:
        """A sender's delivery of an event already stored: a short row, while the hour's quota lasts."""
        try:
            with self._write():
                n = self._db.execute("SELECT COUNT(*) FROM receipts WHERE hook_id=? AND at>? AND result='duplicate'",
                                     (hid, now - 3600)).fetchone()[0]
                if n < RECEIPTS_PER_HOUR:
                    self._db.execute("INSERT INTO receipts(hook_id, event_id, at, result, idem, source) VALUES(?,?,?,?,?,?)",
                                     (hid, eid, now, result, key, source))
        except sqlite3.OperationalError:
            pass                                   # a receipt is evidence, never a reason to refuse the duplicate

    # ── triage (spec §5-6: rules after the commit) ──
    def triage_candidates(self, limit: int = 50, now: Optional[float] = None) -> list:
        """Received events waiting for their rules, oldest first, of hooks not paused."""
        now = time.time() if now is None else now
        with self._read():
            rows = self._db.execute(
                "SELECT e.id, e.hook_id, e.brain, e.received_at, e.content_type, e.body, e.hook_rev, e.trace, e.source,"
                " e.headers FROM events e LEFT JOIN hooks h ON h.id=e.hook_id WHERE e.status='received' AND"
                " e.next_at<=? AND COALESCE(h.paused,0)=0 ORDER BY e.received_at, e.id LIMIT ?", (now, limit)).fetchall()
        return [dict(r) for r in rows]

    def _live_key(self, brain: str, scope: str, bkey: str, now: float):
        """Inside a transaction: the event holding this business key, if the key is still live. A key past its TTL
        still holds while its event has not run yet (a backlog must not let a second copy through)."""
        return self._db.execute(
            "SELECT b.event_id FROM biz_keys b LEFT JOIN events e ON e.id=b.event_id WHERE b.brain=? AND b.scope=? AND"
            " b.bkey=? AND (b.expires_at>? OR e.status IN ('received','queued','running'))",
            (brain, scope, bkey, now)).fetchone()

    @staticmethod
    def key_scope(hid: str, bk: dict, source: str = "http") -> str:
        """The business key's space: the hook's own (spec §6.2: two hooks never block each other) unless the rules name
        a namespace shared on purpose. Test events have their own space (spec §12: a test send never takes a real
        order's key)."""
        base = f"ns:{bk['shared']}" if bk.get("shared") else f"hook:{hid}"
        return ("test:" if source == "test" else "") + f"{base}:v{int(bk.get('policy') or 1)}"

    def triage_commit(self, eid: str, pre: dict, deliveries: list, now: Optional[float] = None) -> str:
        """Write the triage decision of a received event in ONE transaction, only if it is still `received` (another
        worker may have decided first). `pre` = webhook_rules.evaluate() (decision run/filtered/invalid), `deliveries`
        = rows to create when it runs: {"action_id", "kind", "delivery_id", "status", "detail", "safe", "deadline",
        "depends"}. Returns the new status, or '' if it was not `received` any more."""
        now = time.time() if now is None else now
        decision = str(pre.get("decision") or "run")
        with self._write():
            row = self._db.execute("SELECT hook_id, brain, source, status, trace FROM events WHERE id=?", (eid,)).fetchone()
            if row is None or row["status"] != "received":
                return ""
            trace = dict(_loads(row["trace"], {}), **(pre.get("trace") or {}))
            bk = pre.get("business_key") if decision == "run" else None
            scope = self.key_scope(row["hook_id"], bk, row["source"]) if bk else ""
            first = ""
            if bk:
                held = self._live_key(row["brain"], scope, bk["hash"], now)
                if held is not None and held["event_id"] != eid:
                    decision, first = "duplicate", held["event_id"]
                    trace["duplicate_of"] = first
            reasons = list(pre.get("reasons") or [])
            reason = str(pre.get("reason") or "")
            if decision == "duplicate":
                reason, reasons = f"duplicate_of:{first}", ["duplicate"]
            common = (_dumps(trace), _dumps(pre.get("fields") or {}), str(pre.get("correlation") or "")[:120],
                      _dumps(reasons[:10]), reason[:2000])
            if decision != "run":
                st = decision if decision in IGNORED else "invalid"
                # A quarantined event (the payload or the rules are wrong) is an error the owner must hear of (spec
                # §12): its notice is queued by the worker. Ignored ones (filtered, duplicate) are not told.
                told = 0 if st == "invalid" and reason != "hook_deleted" else now
                self._db.execute("UPDATE events SET status=?, trace=?, fields=?, correlation=?, reasons=?, error=?,"
                                 " finished_at=?, notified_at=?, biz_key=? WHERE id=?",
                                 (st,) + common + (now, told, (scope + "/" + bk["hash"]) if bk else "", eid))
                return st
            if bk:
                self._db.execute("INSERT OR REPLACE INTO biz_keys(brain, scope, bkey, event_id, hook_id, created_at,"
                                 " expires_at) VALUES(?,?,?,?,?,?,?)",
                                 (row["brain"], scope, bk["hash"], eid, row["hook_id"], now, now + float(bk["ttl_s"])))
            for d in deliveries:
                self._insert_delivery(eid, 1, d)
            self._db.execute("UPDATE events SET status='queued', next_at=?, trace=?, fields=?, correlation=?, reasons=?,"
                             " error=?, biz_key=?, biz_ttl=? WHERE id=?",
                             (now,) + common + ((scope + "/" + bk["hash"]) if bk else "",
                                                float(bk["ttl_s"]) if bk else 0.0, eid))
            _crash("triage_before_commit")
            return "queued"

    def triage_defer(self, eid: str, delay: float, why: str, now: Optional[float] = None) -> None:
        """The hook's configuration could not be read right now: decide later (never drop or guess)."""
        now = time.time() if now is None else now
        with self._write():
            self._db.execute("UPDATE events SET next_at=?, error=? WHERE id=? AND status='received'",
                             (now + delay, str(why)[:500], eid))

    def _insert_delivery(self, eid: str, gen: int, d: dict) -> None:
        self._db.execute(
            "INSERT OR IGNORE INTO deliveries(event_id, action_id, generation, kind, delivery_id, status, detail, safe,"
            " deadline, depends, finished_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (eid, d["action_id"], gen, d["kind"], d["delivery_id"], d.get("status") or "pending",
             str(d.get("detail") or "")[:1000], 1 if d.get("safe") else 0, float(d.get("deadline") or 0),
             _dumps(d.get("depends") or [], 2000), time.time() if d.get("status") == "cancelled" else 0))

    def _ever_dispatched(self, eid: str) -> bool:
        """Did ANY attempt of this event reach its effect? Delivery dispatch marks are kept across retries."""
        return self._db.execute(
            "SELECT 1 FROM deliveries WHERE event_id=? AND dispatched_at>0 UNION ALL SELECT 1 FROM events WHERE id=? AND"
            " dispatched_at>0 UNION ALL SELECT 1 FROM attempts WHERE event_id=? AND (outcome IN ('done','silent',"
            "'waiting','failed','unknown') OR outcome LIKE 'late:%') AND NOT EXISTS (SELECT 1 FROM deliveries WHERE"
            " event_id=?) LIMIT 1", (eid, eid, eid, eid)).fetchone() is not None

    def _release_keys(self, eid: str) -> None:
        """Inside a write: an event that will never run (dead) gives its business key back, so the source's next copy
        of that order is not refused as a duplicate of something that never happened. Only if nothing of it was ever
        dispatched."""
        if not self._ever_dispatched(eid):
            self._db.execute("DELETE FROM biz_keys WHERE event_id=?", (eid,))

    # ── work ──
    def claim(self, worker: str, now: Optional[float] = None, avoid: Optional[list] = None) -> Optional[dict]:
        """Take the oldest runnable event whose hook has nothing else running and is not paused. Returns the row with
        the new `fence`, or None. One event per hook at a time (spec §11: concurrency 1 per hook). `avoid`: hooks not
        to take an event of now (the worker keeps a slot for code-only hooks)."""
        now = time.time() if now is None else now
        av = [str(x) for x in (avoid or [])][:5000]
        extra = f" AND e.hook_id NOT IN ({','.join('?' * len(av))})" if av else ""
        with self._write():
            row = self._db.execute(
                "SELECT e.* FROM events e WHERE e.status='queued' AND e.next_at<=? AND NOT EXISTS ("
                " SELECT 1 FROM events r WHERE r.hook_id=e.hook_id AND r.status='running') AND NOT EXISTS ("
                " SELECT 1 FROM hooks h WHERE h.id=e.hook_id AND h.paused=1)" + extra +
                " ORDER BY e.received_at, e.id LIMIT 1", (now, *av)).fetchone()
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

    def heartbeat(self, eid: str, fence: int, now: Optional[float] = None) -> bool:
        """Renew. While the event is still `running` at our fence it is ours (claim() never takes a running row)."""
        now = time.time() if now is None else now
        with self._write():
            cur = self._db.execute("UPDATE events SET lease_until=? WHERE id=? AND fence=? AND status='running'",
                                   (now + LEASE_S, eid, fence))
            return cur.rowcount == 1

    def mark_dispatched(self, eid: str, fence: int, now: Optional[float] = None) -> bool:
        """Event-level dispatch mark, committed BEFORE a run as a whole (a run without deliveries, older callers).
        Renews the lease. False = this worker lost the event (or its lease ran out): do NOT run it."""
        now = time.time() if now is None else now
        with self._write():
            cur = self._db.execute("UPDATE events SET dispatched_at=?, lease_until=? WHERE id=? AND fence=? AND"
                                   " status='running' AND lease_until>?", (now, now + LEASE_S, eid, fence, now))
            return cur.rowcount == 1

    def finish(self, eid: str, fence: int, status: str, result: str = "", error: str = "",
               now: Optional[float] = None) -> bool:
        """Final state for this attempt (an event that ends without its deliveries: hook deleted). False = a newer
        owner holds the event."""
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
                self._db.execute("UPDATE attempts SET ended_at=?, outcome=?, late_result=? WHERE event_id=? AND fence=?",
                                 (now, "late:" + status, str(result or error or "")[:4000], eid, fence))
        return ok

    def requeue_before_dispatch(self, eid: str, fence: int, error: str, now: Optional[float] = None) -> str:
        """A failure before anything was dispatched: safe to try again. Back off, or `dead` after MAX_AUTO_TRIES."""
        now = time.time() if now is None else now
        with self._write():
            row = self._db.execute("SELECT tries, dispatched_at FROM events WHERE id=? AND fence=? AND"
                                   " status='running'", (eid, fence)).fetchone()
            if row is None:
                return ""
            if row["dispatched_at"]:
                raise ValueError("already dispatched")
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

    # ── deliveries ──
    def _owns(self, eid: str, fence: int) -> bool:
        return self._db.execute("SELECT 1 FROM events WHERE id=? AND fence=? AND status='running'",
                                (eid, fence)).fetchone() is not None

    def _gen(self, eid: str) -> int:
        r = self._db.execute("SELECT generation FROM events WHERE id=?", (eid,)).fetchone()
        return int(r["generation"]) if r else 1

    def branches_init(self, eid: str, fence: int, actions: list, delivery_of) -> Optional[list]:
        """The delivery rows of this event's current generation (created at triage; created here for an event queued
        by an older build). Returns all rows, or None if this worker no longer owns the event."""
        with self._write():
            if not self._owns(eid, fence):
                return None
            gen = self._gen(eid)
            if not self._db.execute("SELECT 1 FROM deliveries WHERE event_id=? AND generation=?", (eid, gen)).fetchone():
                for a in actions:
                    self._insert_delivery(eid, gen, {"action_id": a["id"], "kind": a["kind"],
                                                     "delivery_id": delivery_of(eid, a["id"], gen),
                                                     "depends": a.get("depends_on") or []})
            return [dict(r) for r in self._db.execute(
                f"SELECT {_DELIVERY_COLS} FROM deliveries WHERE event_id=? AND generation=? ORDER BY rowid", (eid, gen))]

    def branches(self, eid: str, gen: Optional[int] = None) -> list:
        with self._read():
            g = self._gen(eid) if gen is None else gen
            return [dict(r) for r in self._db.execute(
                f"SELECT {_DELIVERY_COLS} FROM deliveries WHERE event_id=? AND generation=? ORDER BY rowid", (eid, g))]

    def branch_dispatch(self, eid: str, fence: int, aid: str, worker: str = "", safe: bool = False,
                        request_sha: str = "", ai: bool = False, now: Optional[float] = None) -> bool:
        """Committed BEFORE the delivery's effect starts, with its attempt row. False = do NOT run it (lost the event,
        or the delivery is not runnable any more). `safe` = a lost lease may resend it (the receiver dedups)."""
        now = time.time() if now is None else now
        with self._write():
            ok = self._db.execute("SELECT generation FROM events WHERE id=? AND fence=? AND status='running' AND"
                                  " lease_until>? AND NOT EXISTS (SELECT 1 FROM meta WHERE k='deleted:' || events.hook_id)",
                                  (eid, fence, now)).fetchone()
            if not ok:
                return False
            gen = int(ok["generation"])
            cur = self._db.execute("UPDATE deliveries SET status='running', dispatched_at=?, tries=tries+1, safe=? WHERE"
                                   " event_id=? AND action_id=? AND generation=? AND status IN ('pending','retry')",
                                   (now, 1 if safe else 0, eid, aid, gen))
            if cur.rowcount != 1:
                return False
            n = self._db.execute("SELECT tries FROM deliveries WHERE event_id=? AND action_id=? AND generation=?",
                                 (eid, aid, gen)).fetchone()[0]
            self._db.execute("INSERT INTO delivery_attempts(event_id, action_id, generation, n, worker, fence, started_at,"
                             " request_sha, maybe_acted) VALUES(?,?,?,?,?,?,?,?,1)",
                             (eid, aid, gen, int(n), worker, fence, now, request_sha))
            self._db.execute("UPDATE events SET dispatched_at=CASE WHEN dispatched_at=0 THEN ? ELSE dispatched_at END,"
                             " lease_until=? WHERE id=?", (now, now + LEASE_S, eid))
            if ai:
                # Every dispatch of an AI action (a retry too) is one model run for the AI budget: append-only.
                self._db.execute("INSERT INTO ai_runs(hook_id, event_id, at) SELECT hook_id, id, ? FROM events WHERE"
                                 " id=?", (now, eid))
        return True

    def branch_finish(self, eid: str, fence: int, aid: str, status: str, detail: str = "", receipt: Optional[dict] = None,
                      result: str = "", next_at: float = 0.0, now: Optional[float] = None, http_status: int = 0,
                      maybe_acted: Optional[bool] = None) -> bool:
        """Outcome of one delivery (also one closed before dispatch: a permission, a missing plugin). `retry` keeps it
        runnable from `next_at`. False = a newer owner holds the event (the caller keeps the outcome with
        branch_late)."""
        assert status in BRANCH_FINAL or status == "retry"
        now = time.time() if now is None else now
        with self._write():
            if not self._owns(eid, fence):
                return False
            gen = self._gen(eid)
            self._db.execute(
                "UPDATE deliveries SET status=?, detail=?, receipt=?, result=?, next_at=?, finished_at=? WHERE"
                " event_id=? AND action_id=? AND generation=? AND status IN ('running','pending','retry')",
                (status, str(detail or "")[:1000], _dumps(receipt or {}, 4000), str(result or "")[:4000],
                 float(next_at or 0), 0 if status == "retry" else now, eid, aid, gen))
            if maybe_acted is None:
                maybe_acted = status in ("completed", "accepted", "silent", "unknown", "waiting")
            self._db.execute(
                "UPDATE delivery_attempts SET ended_at=?, outcome=?, detail=?, http_status=?, maybe_acted=? WHERE"
                " event_id=? AND action_id=? AND generation=? AND fence=? AND ended_at=0",
                (now, status, str(detail or "")[:500], int(http_status or 0), 1 if maybe_acted else 0, eid, aid, gen,
                 fence))
        return True

    def branch_late(self, eid: str, aid: str, status: str, detail: str, receipt: Optional[dict], result: str) -> None:
        """The event was taken over while this delivery was still running (lease lost): its real outcome is not written
        as the state (the owner reconciles that), but it is kept next to it."""
        note = f"late outcome: {status}" + (f" ({detail[:300]})" if detail else "")
        if receipt:
            note += " " + _dumps(receipt, 1500)
        if result:
            note += " " + str(result)[:1500]
        with self._write():
            self._db.execute("UPDATE deliveries SET detail=substr(detail || ' | ' || ?, 1, 4000) WHERE event_id=? AND"
                             " action_id=? AND generation=(SELECT generation FROM events WHERE id=?)", (note, eid, aid, eid))

    def attempts_of(self, eid: str) -> list:
        with self._read():
            return [dict(r) for r in self._db.execute(
                "SELECT action_id, generation, n, started_at, ended_at, http_status, outcome, detail, maybe_acted FROM"
                " delivery_attempts WHERE event_id=? ORDER BY started_at, n", (eid,))]

    @staticmethod
    def _summarize_flat(rows: list) -> tuple:
        st = [r["status"] for r in rows]
        if not st:
            return "done", 0.0
        if "running" in st:
            return "unknown", 0.0
        later = [float(r.get("next_at") or 0) for r in rows if r["status"] in ("retry", "pending")]
        if later:
            return "queued", min(later)
        if "unknown" in st:
            return "unknown", 0.0
        if "approval" in st:
            return "waiting", 0.0
        if "blocked" in st:
            return "blocked", 0.0
        if "failed" in st:
            return "failed", 0.0
        if "waiting" in st:
            return "waiting", 0.0
        if all(s == "cancelled" for s in st):
            return "cancelled", 0.0
        if all(s in ("silent", "cancelled") for s in st):
            return "silent", 0.0
        return "done", 0.0

    @staticmethod
    def summarize(rows: list) -> tuple:
        """(event status, next_at) from the delivery rows. `queued` = some delivery still runs later. Aware of
        `depends_on` (spec §8.5): a delivery held behind a dependency that waits for the owner does not keep the event
        in the queue (it would loop); it makes the event wait. One whose dependency failed is due now (to be cancelled)."""
        by_id = {r.get("action_id"): r for r in rows}
        # A delivery is due no sooner than what it waits for, down the whole chain: a dependent pending at next_at 0
        # behind a delivery that retries in 30 minutes must not requeue the event now (it would be claimed and settled
        # again in a loop, an attempt row each time).
        eff = {r.get("action_id"): float(r.get("next_at") or 0) for r in rows}
        deps_of = {}
        for r in rows:
            d = r.get("depends")
            deps_of[r.get("action_id")] = [x.get("id") for x in (_loads(d, []) if isinstance(d, str) else (d or []))]
        for _ in range(len(rows)):
            changed = False
            for aid, ds in deps_of.items():
                for dep in ds:
                    if (by_id.get(dep) or {}).get("status") in ("pending", "retry") and eff.get(dep, 0) > eff[aid]:
                        eff[aid], changed = eff[dep], True
            if not changed:
                break
        # Held is transitive: a delivery that waits on one which is itself held (behind an approval, a block, an unknown
        # outcome) is held too, else the event would be requeued at once in a loop.
        held_ids = {r.get("action_id") for r in rows if r["status"] in ("pending", "retry")
                    and dep_state(r, by_id) == "held"}
        for _ in range(len(rows)):
            more = {aid for aid, ds in deps_of.items() if aid not in held_ids
                    and (by_id.get(aid) or {}).get("status") in ("pending", "retry") and any(d in held_ids for d in ds)
                    and dep_state(by_id[aid], by_id) != "doomed"}
            if not more:
                break
            held_ids |= more
        held = []
        timed = []
        for r in rows:
            if r["status"] in ("pending", "retry"):
                if r.get("action_id") in held_ids:
                    held.append(r)
                    continue
                if dep_state(r, by_id) == "wait":
                    r = dict(r, next_at=eff[r.get("action_id")])
            timed.append(r)
        rows = timed + held
        if not held:
            return Store._summarize_flat(rows)
        rest = [r for r in rows if r not in held]
        st, nxt = Store._summarize_flat(rest) if rest else ("waiting", 0.0)
        if st in ("done", "silent", "cancelled"):
            return "waiting", 0.0
        return st, nxt

    def settle(self, eid: str, fence: int, text_of, now: Optional[float] = None) -> tuple:
        """End of a run over deliveries, in ONE write: read them as they are NOW (an approval may have landed), then
        requeue the event if one can still run, or write its final state. Returns (status, next_at), or ("", 0) if this
        worker no longer owns the event."""
        now = time.time() if now is None else now
        with self._write():
            if not self._owns(eid, fence):
                return "", 0.0
            gen = self._gen(eid)
            rows = [dict(r) for r in self._db.execute(
                f"SELECT {_DELIVERY_COLS} FROM deliveries WHERE event_id=? AND generation=? ORDER BY rowid", (eid, gen))]
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
        """The owner approves or rejects ONE delivery waiting for approval. Approve: it runs at the next pass (the
        current permissions are checked again then). Reject: it is cancelled. Returns (ok, error_code)."""
        if decision not in ("approve", "reject"):
            return False, "bad_decision"
        now = time.time() if now is None else now
        with self._write():
            row = self._db.execute("SELECT status, generation FROM events WHERE id=?", (eid,)).fetchone()
            if row is None:
                return False, "not_found"
            gen = int(row["generation"])
            cur = self._db.execute(
                "UPDATE deliveries SET status=?, approved_at=?, detail=?, finished_at=? WHERE event_id=? AND action_id=?"
                " AND generation=? AND status='approval'",
                ("pending", now, "approved by the owner", 0, eid, aid, gen) if decision == "approve"
                else ("cancelled", 0, "rejected by the owner", now, eid, aid, gen))
            if cur.rowcount != 1:
                return False, "not_waiting"
            self._audit(now, decision, "", eid, aid)
            if row["status"] == "queued":
                self._db.execute("UPDATE events SET next_at=? WHERE id=?", (now, eid))
                return True, ""
            if row["status"] == "running":
                return True, ""
            br = [dict(b) for b in self._db.execute("SELECT action_id, status, next_at, depends FROM deliveries WHERE"
                                                    " event_id=? AND generation=?", (eid, gen))]
            st, nxt = self.summarize(br)
            if st == "queued":
                self._db.execute("UPDATE events SET status='queued', next_at=?, dispatched_at=0, finished_at=0,"
                                 " notified_at=0, notify_tries=0, tries=0 WHERE id=?", (max(now, nxt), eid))
            else:
                self._db.execute("UPDATE events SET status=?, finished_at=?, notified_at=? WHERE id=?",
                                 (st, now, now, eid))
        return True, ""

    def recover(self, now: Optional[float] = None) -> dict:
        """Expired leases (a worker died or hung). Per delivery: one dispatched and never finished becomes `unknown`
        (it may have acted), unless it was marked retry-safe, which is tried again (spec §7: retry when proven safe).
        If some never started, the event goes back to the queue for those. Returns counts."""
        now = time.time() if now is None else now
        with self._write():
            rows = self._db.execute("SELECT id, fence, tries, dispatched_at, generation FROM events WHERE"
                                    " status='running' AND lease_until<=?", (now,)).fetchall()
            back = unknown = 0
            for r in rows:
                gen = int(r["generation"])
                br = [dict(b) for b in self._db.execute("SELECT action_id, status, next_at, depends FROM deliveries"
                                                         " WHERE event_id=? AND generation=?", (r["id"], gen))]
                if br:
                    # A retry-safe delivery is sent again, within the same bounds as any retry (attempts, deadline):
                    # a worker that keeps crashing must not resend it forever. Past them it is unknown.
                    self._db.execute("UPDATE deliveries SET status='retry', next_at=?, detail=? WHERE event_id=? AND"
                                     " generation=? AND status='running' AND safe=1 AND tries<? AND (deadline=0 OR"
                                     " deadline>?)",
                                     (now, "lease expired after dispatch: resent with the same delivery id (the receiver"
                                      " drops a second copy)", r["id"], gen, SAFE_RESEND_MAX, now))
                    self._db.execute("UPDATE deliveries SET status='unknown', finished_at=?, detail=? WHERE event_id=? AND"
                                     " generation=? AND status='running'",
                                     (now, "lease expired after dispatch: it may have acted", r["id"], gen))
                    self._db.execute("UPDATE delivery_attempts SET ended_at=?, outcome='lease_lost' WHERE event_id=? AND"
                                     " generation=? AND ended_at=0", (now, r["id"], gen))
                    br = [dict(b) for b in self._db.execute("SELECT action_id, status, next_at, depends FROM deliveries"
                                                             " WHERE event_id=? AND generation=?", (r["id"], gen))]
                    fin, nxt = self.summarize(br)
                    pend = fin == "queued"
                    if pend and not r["dispatched_at"] and int(r["tries"]) >= MAX_AUTO_TRIES:
                        self._db.execute("UPDATE events SET status='dead', finished_at=?, lease_owner='', lease_until=0,"
                                         " error=? WHERE id=?", (now, "worker lost it before dispatch too many times",
                                                                 r["id"]))
                        self._release_keys(r["id"])
                        outcome = "dead"
                    elif pend:
                        # tries is reset only when this attempt dispatched something: an event that keeps killing the
                        # worker BEFORE any dispatch must reach MAX_AUTO_TRIES and stop (the poison guard).
                        self._db.execute("UPDATE events SET status='queued', next_at=?, lease_owner='', lease_until=0,"
                                         " dispatched_at=0, tries=CASE WHEN ? THEN 0 ELSE tries END WHERE id=?",
                                         (max(now, nxt), 1 if r["dispatched_at"] else 0, r["id"]))
                        outcome = "lease_expired"
                        back += 1
                    else:
                        err = "lease expired after dispatch: a delivery may have acted" if fin == "unknown" else ""
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
        """Is there work this or another worker could take right now (an event to triage or to run)?"""
        now = time.time() if now is None else now
        with self._read():
            if self._db.execute("SELECT 1 FROM events e LEFT JOIN hooks h ON h.id=e.hook_id WHERE e.status='received'"
                                " AND e.next_at<=? AND COALESCE(h.paused,0)=0 LIMIT 1", (now,)).fetchone():
                return True
            return self._db.execute(
                "SELECT 1 FROM events e WHERE e.status='queued' AND e.next_at<=? AND NOT EXISTS ("
                " SELECT 1 FROM events r WHERE r.hook_id=e.hook_id AND r.status='running') AND NOT EXISTS ("
                " SELECT 1 FROM hooks h WHERE h.id=e.hook_id AND h.paused=1) LIMIT 1", (now,)).fetchone() is not None

    def mark_notified(self, eid: str, fence: Optional[int] = None, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        with self._write():
            if fence is None:
                self._db.execute("UPDATE events SET notified_at=? WHERE id=?", (now, eid))
            else:
                self._db.execute("UPDATE events SET notified_at=? WHERE id=? AND fence=?", (now, eid, fence))

    def unnotified(self, limit: int = 50) -> list:
        """Finished events whose notice was never queued (a crash between the commit and the notice)."""
        with self._read():
            rows = self._db.execute("SELECT * FROM events WHERE status IN ('done','waiting','blocked','failed','unknown',"
                                    "'dead','invalid') AND notified_at=0 AND finished_at>0 ORDER BY finished_at LIMIT ?",
                                    (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ── notifications outbox (spec §4.1, §12: a failed notice is retried alone, never the action) ──
    def notify_enqueue(self, dkey: str, kind: str, text: str, *, hook_id: str = "", event_id: str = "",
                       chat_id: str = "", brain: str = "", web: str = "", viec: Optional[dict] = None,
                       mark_event: Optional[tuple] = None, now: Optional[float] = None) -> bool:
        """Queue one notice under its dedup key (a second enqueue of the same key is a no-op). `mark_event` =
        (event_id, fence): the event is marked told in the SAME transaction, so a crash can neither lose the notice nor
        queue it twice. Returns True when it was new."""
        now = time.time() if now is None else now
        with self._write():
            cur = self._db.execute(
                "INSERT OR IGNORE INTO notifications(dkey, hook_id, event_id, kind, chat_id, brain, text, web, viec,"
                " created_at, next_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (dkey[:300], hook_id, event_id, kind, chat_id, brain, text[:8000], (web or text)[:8000],
                 _dumps(viec or {}, 2000), now, now))
            if mark_event:
                eid, fence = mark_event
                if fence is None:
                    self._db.execute("UPDATE events SET notified_at=? WHERE id=?", (now, eid))
                else:
                    self._db.execute("UPDATE events SET notified_at=? WHERE id=? AND fence=?", (now, eid, fence))
            return cur.rowcount == 1

    def notify_due(self, now: Optional[float] = None, limit: int = 50) -> list:
        now = time.time() if now is None else now
        with self._read():
            return [dict(r) for r in self._db.execute(
                "SELECT * FROM notifications WHERE status='pending' AND next_at<=? ORDER BY id LIMIT ?", (now, limit))]

    def notify_result(self, nid: int, ok: bool, error: str = "", now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        with self._write():
            if ok:
                self._db.execute("UPDATE notifications SET status='sent', sent_at=?, tries=tries+1 WHERE id=?", (now, nid))
                return
            r = self._db.execute("SELECT tries FROM notifications WHERE id=?", (nid,)).fetchone()
            tries = int(r["tries"]) + 1 if r else NOTIFY_TRIES
            st = "failed" if tries >= NOTIFY_TRIES else "pending"
            self._db.execute("UPDATE notifications SET status=?, tries=?, next_at=?, error=? WHERE id=?",
                             (st, tries, now + min(30 * 2 ** tries, 3600), str(error)[:500], nid))

    def notify_exists(self, dkey: str) -> bool:
        with self._read():
            return self._db.execute("SELECT 1 FROM notifications WHERE dkey=?", (dkey,)).fetchone() is not None

    def notifications(self, hook_id: str = "", event_id: str = "", limit: int = 50) -> list:
        with self._read():
            return [dict(r) for r in self._db.execute(
                "SELECT id, dkey, hook_id, event_id, kind, status, tries, created_at, sent_at, error FROM notifications"
                " WHERE (?='' OR hook_id=?) AND (?='' OR event_id=?) ORDER BY id DESC LIMIT ?",
                (hook_id, hook_id, event_id, event_id, limit))]

    # ── audit (spec §12: viewing or exporting raw data is recorded) ──
    def _audit(self, now: float, action: str, hook_id: str, event_id: str, detail: str = "") -> None:
        self._db.execute("INSERT INTO audit(at, action, hook_id, event_id, detail) VALUES(?,?,?,?,?)",
                         (now, action, hook_id, event_id, str(detail)[:500]))

    def audit(self, action: str, hook_id: str = "", event_id: str = "", detail: str = "") -> None:
        with self._write():
            self._audit(time.time(), action, hook_id, event_id, detail)

    def audit_rows(self, hook_id: str = "", limit: int = 100) -> list:
        with self._read():
            return [dict(r) for r in self._db.execute(
                "SELECT at, action, hook_id, event_id, detail FROM audit WHERE (?='' OR hook_id=?) ORDER BY id DESC"
                " LIMIT ?", (hook_id, hook_id, limit))]

    # ── owner actions ──
    def retry(self, eid: str, now: Optional[float] = None, window_s: float = 0.0) -> tuple:
        """The owner asks to run an event again (failed, unknown, dead, blocked), after reconciling. Only deliveries that
        failed, are unknown or blocked run again, with the SAME delivery ids and the same snapshot; a delivery that
        succeeded never does. Returns (ok, error_code)."""
        now = time.time() if now is None else now
        with self._write():
            row = self._db.execute("SELECT status, brain, hook_id, biz_key, biz_ttl, generation, size, received_at,"
                                   " length(body) AS blen FROM events WHERE id=?", (eid,)).fetchone()
            if row is None:
                return False, "not_found"
            if row["status"] not in ("failed", "unknown", "dead", "blocked"):
                return False, "not_retryable"
            if int(row["size"] or 0) > 0 and not int(row["blen"] or 0):
                # The body is gone (an owner deletion or an older build's pruning): running again would send nothing
                # and look done. Refused, never sent empty.
                return False, "body_pruned"
            if row["biz_key"] and "/" in row["biz_key"]:
                scope, bkey = row["biz_key"].rsplit("/", 1)
                held = self._live_key(row["brain"], scope, bkey, now)
                if held is not None and held["event_id"] != eid:
                    return False, "key_taken"
                if held is None:
                    self._db.execute("INSERT OR REPLACE INTO biz_keys(brain, scope, bkey, event_id, hook_id, created_at,"
                                     " expires_at) VALUES(?,?,?,?,?,?,?)",
                                     (row["brain"], scope, bkey, eid, row["hook_id"], now,
                                      now + float(row["biz_ttl"] or 7 * 86400)))
            # The owner's retry gets a fresh retry window from now (else an event retried after a day had one try).
            # Deliveries cancelled only because a dependency failed run again too (the chain the owner set up).
            self._db.execute("UPDATE deliveries SET status='pending', next_at=0, finished_at=0, tries=0,"
                             " deadline=CASE WHEN deadline>0 THEN ? ELSE 0 END WHERE event_id=?"
                             " AND generation=? AND (status IN ('failed','unknown','blocked') OR (status='cancelled'"
                             " AND detail LIKE ?))", (now + float(window_s or RETRY_WINDOW_S), eid,
                                                      int(row["generation"]), DEP_CANCEL + "%"))
            # Never triaged (held at rollback while still `received`): no delivery exists yet, so it goes back through
            # triage (rules, filter, business key) instead of running every action unfiltered.
            fresh = self._db.execute("SELECT 1 FROM deliveries WHERE event_id=? AND generation=? UNION ALL SELECT 1"
                                     " FROM attempts WHERE event_id=? LIMIT 1",
                                     (eid, int(row["generation"]), eid)).fetchone() is None
            self._db.execute("UPDATE events SET status=?, next_at=?, dispatched_at=0, finished_at=0,"
                             " notified_at=0, notify_tries=0, tries=0, error='', result='' WHERE id=?",
                             ("received" if fresh else "queued", now, eid))
            self._audit(now, "retry", row["hook_id"], eid)
        return True, ""

    def replay(self, eid: str, deliveries: list, now: Optional[float] = None, revision: int = 0,
               bk: Optional[dict] = None) -> tuple:
        """"Process with the new configuration" (spec §7): a NEW generation of deliveries (new delivery ids) built by
        the caller from the hook's current revision, after the owner saw the simulation. The event keeps its business
        identity (its key is not dropped). Returns (ok, error_code)."""
        now = time.time() if now is None else now
        with self._write():
            row = self._db.execute("SELECT status, generation, hook_id, brain, source FROM events WHERE id=?",
                                   (eid,)).fetchone()
            if row is None:
                return False, "not_found"
            if row["status"] in ("received", "queued", "running"):
                return False, "busy"
            if bk:
                # Business dedup holds for a replay too (spec §7): another event holding this order's key means the
                # order ran there; this one is refused, named. Otherwise this event takes (or refreshes) the key, so
                # the source's next copy of the order is a duplicate of it.
                scope = self.key_scope(row["hook_id"], bk, row["source"])
                held = self._live_key(row["brain"], scope, bk["hash"], now)
                if held is not None and held["event_id"] not in (eid, ""):
                    return False, f"key_taken:{held['event_id']}"
                self._db.execute("INSERT OR REPLACE INTO biz_keys(brain, scope, bkey, event_id, hook_id, created_at,"
                                 " expires_at) VALUES(?,?,?,?,?,?,?)",
                                 (row["brain"], scope, bk["hash"], eid, row["hook_id"], now, now + float(bk["ttl_s"])))
                self._db.execute("UPDATE events SET biz_key=?, biz_ttl=? WHERE id=?",
                                 (scope + "/" + bk["hash"], float(bk["ttl_s"]), eid))
            gen = int(row["generation"]) + 1
            for d in deliveries:
                self._insert_delivery(eid, gen, d)
            # The new generation runs under the revision it was planned from (the hook as it is now), else the
            # worker would read the old snapshot and cancel every action that changed.
            self._db.execute("UPDATE events SET status='queued', generation=?, next_at=?, dispatched_at=0, finished_at=0,"
                             " notified_at=0, notify_tries=0, tries=0, error='', result='',"
                             " hook_rev=CASE WHEN ?>0 THEN ? ELSE hook_rev END WHERE id=?",
                             (gen, now, int(revision or 0), int(revision or 0), eid))
            self._audit(now, "replay", row["hook_id"], eid, f"generation {gen}, revision {revision or 'kept'}")
        return True, ""

    def resolve(self, eid: str, outcome: str, note: str = "", now: Optional[float] = None) -> tuple:
        """Reconcile an `unknown` event after checking the outside system (done: it happened; failed: it did not, and
        can be retried). Also closes a `waiting` or `blocked` event the owner has dealt with, and settles a receiver
        that only ACCEPTED (queued) the work: done counts it finished, so actions waiting for it run; failed cancels
        them."""
        if outcome not in ("done", "failed"):
            return False, "bad_outcome"
        now = time.time() if now is None else now
        with self._write():
            row = self._db.execute("SELECT status, generation, hook_id FROM events WHERE id=?", (eid,)).fetchone()
            if row is not None and row["status"] in ("failed", "dead"):
                # The owner settles a failed event without resending (done: handled outside; failed: given up). It
                # leaves the kept-body set, so its body follows the normal retention and stops counting in the quota.
                self._db.execute("UPDATE deliveries SET status=CASE WHEN ?='done' THEN 'completed' ELSE status END,"
                                 " detail='owner: ' || ? WHERE event_id=? AND generation=? AND status IN ('failed',"
                                 "'unknown','blocked')", (outcome, str(note or "settled")[:900], eid,
                                                          int(row["generation"])))
                self._db.execute("UPDATE events SET status=?, result=CASE WHEN ?='' THEN result ELSE ? END,"
                                 " finished_at=?, notified_at=? WHERE id=?",
                                 ("done" if outcome == "done" else "cancelled", note, str(note)[:1000], now, now, eid))
                self._audit(now, "settle:" + outcome, row["hook_id"], eid, note)
                return True, ""
            if row is None or row["status"] not in ("unknown", "waiting", "blocked"):
                return False, "not_unknown"
            gen = int(row["generation"])
            self._db.execute("UPDATE deliveries SET status=?, detail=CASE WHEN ?='' THEN detail ELSE ? END, finished_at=?"
                             " WHERE event_id=? AND generation=? AND status IN ('unknown','waiting','blocked','accepted')",
                             ("completed" if outcome == "done" else "failed", note, "owner: " + str(note)[:900], now,
                              eid, gen))
            self._db.execute("UPDATE deliveries SET status='cancelled', detail='closed by the owner', finished_at=? WHERE"
                             " event_id=? AND generation=? AND status='approval'", (now, eid, gen))
            br = [dict(b) for b in self._db.execute("SELECT action_id, status, next_at, depends FROM deliveries WHERE"
                                                     " event_id=? AND generation=?", (eid, gen))]
            final, nxt = self.summarize(br) if br else (outcome, 0.0)
            self._audit(now, "resolve:" + outcome, row["hook_id"], eid, note)
            if final == "queued":
                self._db.execute("UPDATE events SET status='queued', next_at=?, dispatched_at=0, finished_at=0,"
                                 " notified_at=0, notify_tries=0, tries=0, result=CASE WHEN ?='' THEN result ELSE ? END"
                                 " WHERE id=?", (max(now, nxt), note, str(note)[:1000], eid))
                return True, ""
            self._db.execute("UPDATE events SET status=?, result=CASE WHEN ?='' THEN result ELSE ? END,"
                             " finished_at=?, notified_at=? WHERE id=?",
                             (final, note, str(note)[:1000], now, now, eid))
        return True, ""

    def close_failed(self, hook_id: str, now: Optional[float] = None) -> int:
        """Settle every failed or dead event of a hook as given up (cancelled, audited), without resending: the way out
        when kept failed bodies fill the hook's byte quota."""
        now = time.time() if now is None else now
        with self._write():
            ids = [r[0] for r in self._db.execute("SELECT id FROM events WHERE hook_id=? AND status IN ('failed','dead',"
                                                   "'invalid')", (hook_id,))]
            for i in range(0, len(ids), 500):
                q = ",".join("?" * len(ids[i:i + 500]))
                self._db.execute(f"UPDATE events SET status='cancelled', error='closed by the owner: ' || error,"
                                 f" finished_at=?, notified_at=? WHERE id IN ({q})", [now, now] + ids[i:i + 500])
            if ids:
                self._audit(now, "close_failed", hook_id, "", f"{len(ids)} events")
        return len(ids)

    def delete_event(self, eid: str, now: Optional[float] = None) -> tuple:
        """The owner deletes one event that is not being processed (spec §11: a failed body is kept until the owner
        settles or deletes it). Its delivery key goes too, so a resend from the source is received again; the business
        key is given back. Audited. Returns (ok, error_code)."""
        now = time.time() if now is None else now
        with self._write():
            row = self._db.execute("SELECT status, hook_id FROM events WHERE id=?", (eid,)).fetchone()
            if row is None:
                return False, "not_found"
            if row["status"] not in ("failed", "dead", "invalid"):
                # A finished or ignored event keeps its delivery key (a provider resend stays a duplicate); an open
                # one is being processed. Only failed, dead and quarantined events are deleted by hand.
                return False, "not_deletable"
            # May have acted: a delivery that succeeded or is unclear, an attempt that may have acted, or a delivery
            # that was dispatched with no attempt rows to say otherwise (moved from an older store). Only a delivery
            # whose every attempt was a certain no-effect (a 4xx refusal, a block) gives the order back.
            acted = self._db.execute(
                "SELECT 1 FROM deliveries WHERE event_id=? AND status IN ('completed','accepted','silent','unknown',"
                "'running','waiting') UNION ALL SELECT 1 FROM delivery_attempts WHERE event_id=? AND maybe_acted=1"
                " UNION ALL SELECT 1 FROM deliveries d WHERE d.event_id=? AND d.dispatched_at>0 AND NOT EXISTS ("
                " SELECT 1 FROM delivery_attempts a WHERE a.event_id=d.event_id AND a.action_id=d.action_id) LIMIT 1",
                (eid, eid, eid)).fetchone() is not None
            if not self._db.execute("SELECT 1 FROM deliveries WHERE event_id=? LIMIT 1", (eid,)).fetchone():
                acted = self._ever_dispatched(eid)        # an event of an older build: no delivery rows
            if not acted:
                # Nothing of it may have acted (a receiver that refused with a 4xx did nothing): a resend from the
                # source is received and runs again.
                self._db.execute("DELETE FROM dedup WHERE event_id=?", (eid,))
                self._db.execute("DELETE FROM biz_keys WHERE event_id=?", (eid,))
            # Else a delivery may have acted (partly done, or unclear): its keys outlive the event, as after retention,
            # so the source's resend is a duplicate and the part that succeeded never runs twice. They expire on
            # their own.
            self._db.execute("DELETE FROM notifications WHERE event_id=? AND status='pending'", (eid,))
            self._delete_events([eid])
            self._audit(now, "delete_event", row["hook_id"], eid, row["status"])
        return True, ""

    def expire(self, hid: str, max_age_s: float, now: Optional[float] = None) -> int:
        """Business expiry (spec §11), only when the hook configured it: an event of this hook that has not run after
        `max_age_s` is not sent days late; it becomes dead with the reason, audited, and the owner is told."""
        now = time.time() if now is None else now
        with self._write():
            ids = [r[0] for r in self._db.execute(
                "SELECT id FROM events WHERE hook_id=? AND status IN ('received','queued') AND received_at<? AND"
                " dispatched_at=0 AND NOT EXISTS (SELECT 1 FROM deliveries d WHERE d.event_id=events.id AND"
                " d.dispatched_at>0)", (hid, now - max_age_s))]
            for eid in ids:
                self._db.execute("UPDATE events SET status='dead', finished_at=?, notified_at=0, error=? WHERE id=?",
                                 (now, f"expired: not run within {int(max_age_s // 3600)} h (the hook's expiry)", eid))
                self._release_keys(eid)
                self._audit(now, "expired", hid, eid)
        return len(ids)

    # ── reading ──
    def get(self, eid: str, with_body: bool = False) -> Optional[dict]:
        with self._read():
            row = self._db.execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()
            if row is None:
                return None
            d = dict(row)
            gen = int(d.get("generation") or 1)
            d["attempts"] = [dict(a) for a in self._db.execute(
                "SELECT n, fence, started_at, ended_at, outcome, error, late_result FROM attempts WHERE event_id=?"
                " ORDER BY n", (eid,)).fetchall()]
            d["branches"] = []
            for b in self._db.execute("SELECT action_id, kind, generation, delivery_id, status, tries, dispatched_at,"
                                      " finished_at, approved_at, detail, receipt, substr(result, 1, 600) AS result, safe,"
                                      " depends FROM deliveries WHERE event_id=? AND generation=? ORDER BY rowid",
                                      (eid, gen)):
                b = dict(b)
                b["receipt"] = _loads(b["receipt"], {})
                b["depends"] = _loads(b["depends"], [])
                b["state"] = spec_delivery_state(b["status"])
                d["branches"].append(b)
            d["older_generations"] = int(self._db.execute(
                "SELECT COUNT(DISTINCT generation) FROM deliveries WHERE event_id=? AND generation<?",
                (eid, gen)).fetchone()[0])
            d["receipts"] = [dict(r) for r in self._db.execute(
                "SELECT at, result, source FROM receipts WHERE event_id=? ORDER BY id LIMIT 50", (eid,))]
            d["delivery_attempts"] = [dict(r) for r in self._db.execute(
                "SELECT action_id, generation, n, started_at, ended_at, http_status, outcome, detail, maybe_acted FROM"
                " delivery_attempts WHERE event_id=? ORDER BY started_at, n LIMIT 200", (eid,))]
            d["notices"] = [dict(r) for r in self._db.execute(
                "SELECT kind, status, tries, created_at, sent_at, error FROM notifications WHERE event_id=? ORDER BY id",
                (eid,))]
        if not with_body:
            d.pop("body", None)
        for k in ("trace", "fields", "headers"):
            d[k] = _loads(d.get(k), {})
        d["reasons"] = _loads(d.get("reasons"), [])
        d["state"] = spec_event_state(d["status"], d["branches"])
        return d

    def page(self, hook_id: str = "", status: str = "", limit: int = 20, before: str = "",
             ran_only: bool = False, since: float = 0.0, until: float = 0.0, q: str = "",
             hooks: Optional[list] = None) -> dict:
        """Newest first, keyset pagination: `before` is the `next` cursor of the previous page. Filters: hook (or a
        list of hooks: one brain's), statuses, `ran_only` (leave out the ignored ones), received time range, and `q`
        (exact correlation id, delivery key or event id)."""
        limit = max(1, min(int(limit or 20), 100))
        where, args = [], []
        if ran_only:
            where.append("status NOT IN ('filtered','invalid','duplicate')")
        if hook_id:
            where.append("hook_id=?")
            args.append(hook_id)
        elif hooks is not None:
            where.append("hook_id IN (" + (",".join("?" * len(hooks)) or "''") + ")")
            args += list(hooks)
        if status:
            sts = [x for x in str(status).split(",") if x][:16]
            where.append("status IN (" + ",".join("?" * len(sts)) + ")")
            args += sts
        if since:
            where.append("received_at>=?")
            args.append(float(since))
        if until:
            where.append("received_at<?")
            args.append(float(until))
        if q:
            qq = str(q).strip()[:200]
            where.append("(correlation=? OR id=? OR idem_key IN (?, ?, ?) OR provider_id=?)")
            args += [qq, qq, "h:" + qq, "p:" + qq, qq, qq]
        if before:
            try:
                ts, eid = before.split("|", 1)
                where.append("(received_at<? OR (received_at=? AND id<?))")
                args += [float(ts), float(ts), eid]
            except ValueError:
                pass
        sql = ("SELECT id, hook_id, brain, received_at, status, tries, idem_key, biz_key, source, dispatched_at,"
               " finished_at, correlation, generation, substr(result, 1, 300) AS result, substr(error, 1, 300) AS error,"
               " size, reasons FROM events" + (" WHERE " + " AND ".join(where) if where else "")
               + " ORDER BY received_at DESC, id DESC LIMIT ?")
        with self._read():
            rows = [dict(r) for r in self._db.execute(sql, args + [limit + 1]).fetchall()]
            for r in rows[:limit]:
                br = [dict(b) for b in self._db.execute("SELECT action_id, status FROM deliveries WHERE event_id=? AND"
                                                         " generation=?", (r["id"], r["generation"]))]
                r["deliveries"] = [{"action_id": b["action_id"], "state": spec_delivery_state(b["status"])} for b in br]
                r["state"] = spec_event_state(r["status"], br)
                r["reasons"] = _loads(r["reasons"], [])
        more = len(rows) > limit
        rows = rows[:limit]
        cur = f"{rows[-1]['received_at']}|{rows[-1]['id']}" if more and rows else ""
        return {"items": rows, "next": cur}

    def biz_key_holder(self, brain: str, scope: str, bkey: str, now: Optional[float] = None) -> str:
        """Read only: the event holding this business key as ingest and replay judge it (a key past its TTL still holds
        while its event has not run), or ''."""
        now = time.time() if now is None else now
        with self._read():
            row = self._live_key(brain, scope, bkey, now)
        return str(row["event_id"]) if row else ""

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

    def health(self, hook_id: str = "", now: Optional[float] = None, window: float = 86400) -> dict:
        """Spec §12 health: received / matched / ignored / duplicate, backlog, age of the oldest open event, latency of
        processing, retry / dead / unknown, AI calls, errors by target, SQL busy, DB and WAL size."""
        now = time.time() if now is None else now
        h, args = ("hook_id=? AND ", (hook_id,)) if hook_id else ("", ())
        with self._read():
            by = {r["status"]: r["n"] for r in self._db.execute(
                f"SELECT status, COUNT(*) AS n FROM events WHERE {h}received_at>? GROUP BY status", args + (now - window,))}
            open_n, oldest = self._db.execute(
                f"SELECT COUNT(*), MIN(received_at) FROM events WHERE {h}status IN ('received','queued','running',"
                "'unknown','waiting','blocked')", args).fetchone()
            lat = [r[0] for r in self._db.execute(
                f"SELECT finished_at-received_at FROM events WHERE {h}finished_at>? AND status IN ('done','silent',"
                "'failed','waiting','unknown','blocked','cancelled') ORDER BY finished_at DESC LIMIT 500",
                args + (now - window,))]
            dups = self._db.execute(f"SELECT COUNT(*) FROM receipts WHERE {h}at>? AND result='duplicate'",
                                    args + (now - window,)).fetchone()[0]
            dstat = {r["status"]: r["n"] for r in self._db.execute(
                "SELECT d.status, COUNT(*) AS n FROM deliveries d JOIN events e ON e.id=d.event_id AND"
                f" d.generation=e.generation WHERE {('e.' + h) if h else ''}e.received_at>? GROUP BY d.status",
                args + (now - window,))}
            errs = [dict(r) for r in self._db.execute(
                "SELECT d.action_id, d.kind, COUNT(*) AS n FROM deliveries d JOIN events e ON e.id=d.event_id AND"
                f" d.generation=e.generation WHERE {('e.' + h) if h else ''}e.received_at>? AND d.status IN"
                " ('failed','unknown','blocked') GROUP BY d.action_id, d.kind ORDER BY n DESC LIMIT 20",
                args + (now - window,))]
            ai = self._db.execute(f"SELECT COUNT(*) FROM ai_runs WHERE {h}at>?", args + (now - window,)).fetchone()[0]
        lat.sort()

        def pct(p):
            return round(lat[min(len(lat) - 1, int(len(lat) * p))], 3) if lat else None
        ignored = sum(by.get(k, 0) for k in ("filtered", "duplicate"))
        received = sum(by.values())
        return {"window_s": window, "received": received, "ignored": ignored, "quarantined": by.get("invalid", 0),
                "matched": received - ignored - by.get("invalid", 0) - by.get("received", 0),
                "duplicate_deliveries": int(dups), "duplicate_business": by.get("duplicate", 0),
                "backlog": int(open_n or 0), "oldest_open_age_s": round(now - oldest, 1) if oldest else 0,
                "processing_p50_s": pct(0.5), "processing_p95_s": pct(0.95),
                "retry_wait": dstat.get("retry", 0), "dead": dstat.get("failed", 0) + by.get("dead", 0),
                "unknown": dstat.get("unknown", 0), "blocked": dstat.get("blocked", 0), "ai_calls": int(ai),
                "errors_by_target": errs, "sql_busy": self.busy_count, **self.space_state()}

    def last(self, hook_id: str) -> Optional[dict]:
        with self._read():
            row = self._db.execute("SELECT status, finished_at, received_at FROM events WHERE hook_id=?"
                                   " ORDER BY received_at DESC, id DESC LIMIT 1", (hook_id,)).fetchone()
        return dict(row) if row else None

    def forget_hook(self, hook_id: str) -> None:
        """A deleted hook: its waiting events become `dead` (they will never run), its keys and switches are dropped."""
        now = time.time()
        with self._write():
            for (qid,) in self._db.execute("SELECT id FROM events WHERE hook_id=? AND status IN ('queued','received')",
                                           (hook_id,)).fetchall():
                self._release_keys(qid)
            # Cancelled, not dead: nobody can retry them any more, and retention removes cancelled events (a dead one
            # is kept for the owner's retry, which a deleted hook can never get: its customer data would stay forever).
            self._db.execute("UPDATE events SET status='cancelled', finished_at=?, notified_at=?, error='hook deleted'"
                             " WHERE hook_id=? AND status IN ('queued','received')", (now, now, hook_id))
            # Events waiting for the owner (unknown, waiting, blocked) and the kept failed ones belong to a hook
            # that no longer exists, so no view can show them: they are closed, and retention removes them.
            self._db.execute("UPDATE events SET status='cancelled', finished_at=?, notified_at=?, error='hook deleted: '"
                             " || error WHERE hook_id=? AND status IN ('unknown','waiting','blocked','failed','dead')"
                             " AND error NOT LIKE 'hook deleted%'", (now, now, hook_id))
            self._db.execute("DELETE FROM breakers WHERE hook_id=?", (hook_id,))
            self._db.execute("DELETE FROM meta WHERE k LIKE ? OR k LIKE ? OR k LIKE ? OR k LIKE ? OR k=? OR k=?",
                             (f"digest_day:{hook_id}", f"digest_at:{hook_id}", f"digest_try:{hook_id}:%",
                              f"inc:{hook_id}:%", f"inc:{hook_id}", f"qinc:{hook_id}"))
            self._db.execute("INSERT OR REPLACE INTO meta(k, v) VALUES(?, ?)", (f"deleted:{hook_id}", str(now)))
            self._db.execute("DELETE FROM dedup WHERE hook_id=?", (hook_id,))
            self._db.execute("DELETE FROM hooks WHERE id=?", (hook_id,))

    def prune(self, now: Optional[float] = None, keep_days: Optional[dict] = None) -> int:
        """Settled events past their retention (KEEP_DAYS, or the hook's own), and past the per-hook row caps; bodies
        of settled events after BODY_KEEP_DAYS, with their mapped fields (customer data does not outlive the body);
        delivery keys after DEDUP_KEEP_DAYS. Open events (unknown, waiting, blocked included) and FAILED or DEAD ones
        are kept with their body until the owner settles them (Mark done, Retry) or deletes them (spec §11): a retry
        must send what was received, never an empty body."""
        now = time.time() if now is None else now
        cut = now - KEEP_DAYS * 86400
        ran = "('done','silent','cancelled')"
        fin = "('done','silent','cancelled','filtered','invalid','duplicate')"
        with self._write():
            stale = [r[0] for r in self._db.execute(
                "SELECT id FROM events WHERE status='waiting' AND finished_at>0 AND finished_at<?",
                (now - APPROVAL_TTL_DAYS * 86400,))]
            for sid in stale:
                self._db.execute("UPDATE deliveries SET status='cancelled', detail='approval expired: nobody answered',"
                                 " finished_at=? WHERE event_id=? AND status='approval'", (now, sid))
                self._db.execute("UPDATE deliveries SET status='failed', detail='no answer from the owner', finished_at=?"
                                 " WHERE event_id=? AND status='waiting'", (now, sid))
                self._db.execute("UPDATE events SET status='failed', error='expired: nobody answered in "
                                 f"{APPROVAL_TTL_DAYS} days', finished_at=?, notified_at=? WHERE id=?", (now, now, sid))
            ids = [r[0] for r in self._db.execute(
                f"SELECT id FROM events WHERE (status IN {fin}) AND finished_at>0 AND finished_at<?", (cut,))]
            for hid_k, days in (keep_days or {}).items():
                d = max(1, min(int(days or KEEP_DAYS), KEEP_DAYS_MAX))
                if d < KEEP_DAYS:
                    ids += [r[0] for r in self._db.execute(
                        f"SELECT id FROM events WHERE hook_id=? AND (status IN {fin}) AND finished_at>0 AND finished_at<?",
                        (hid_k, now - d * 86400))]
            if keep_days:
                longer = {h: max(1, min(int(d or KEEP_DAYS), KEEP_DAYS_MAX)) for h, d in keep_days.items()
                          if int(d or KEEP_DAYS) > KEEP_DAYS}
                ids = [i for i in ids if not self._kept_longer(i, longer, now)]
            for (hid,) in self._db.execute("SELECT DISTINCT hook_id FROM events").fetchall():
                for group, keep in ((ran, KEEP_PER_HOOK), ("('filtered','duplicate')", KEEP_IGNORED_PER_HOOK),
                                    ("('invalid')", KEEP_IGNORED_PER_HOOK)):
                    ids += [r[0] for r in self._db.execute(
                        f"SELECT id FROM events WHERE hook_id=? AND status IN {group} ORDER BY received_at DESC"
                        " LIMIT -1 OFFSET ?", (hid, keep))]
            ids = list(dict.fromkeys(ids))
            if ids:
                held = {r[0] for r in self._db.execute(
                    "SELECT e.id FROM events e JOIN biz_keys b ON b.event_id=e.id WHERE e.status IN ('failed','dead')"
                    " AND b.expires_at>?", (now,))}
                ids = [x for x in ids if x not in held]
            if ids:
                recent = set()
                for i in range(0, len(ids), 500):
                    chunk = ids[i:i + 500]
                    q = ",".join("?" * len(chunk))
                    recent |= {r[0] for r in self._db.execute(
                        f"SELECT id FROM events WHERE id IN ({q}) AND received_at>? AND status NOT IN"
                        " ('filtered','duplicate')", chunk + [now - RECENT_KEEP_S])}
                ids = [x for x in ids if x not in recent]
        # Deleted in small transactions: one long write would hold the store lock and make every receive wait.
        for i in range(0, len(ids), 200):
            with self._write():
                # Re-checked inside the delete's own transaction: an event replayed meanwhile is open again.
                chunk = ids[i:i + 200]
                q = ",".join("?" * len(chunk))
                still = [r[0] for r in self._db.execute(f"SELECT id FROM events WHERE id IN ({q}) AND (status IN {fin})",
                                                         chunk)]
                self._delete_events(still)
        with self._write():
            self._db.execute("DELETE FROM dedup WHERE created_at<?", (now - DEDUP_KEEP_DAYS * 86400,))
            self._db.execute("DELETE FROM ai_runs WHERE at<?", (now - 3 * 86400,))
            self._db.execute("DELETE FROM receipts WHERE at<? AND result='duplicate'", (now - KEEP_DAYS * 86400,))
            self._db.execute("DELETE FROM notifications WHERE status IN ('sent','failed') AND created_at<?",
                             (now - KEEP_DAYS * 86400,))
            self._db.execute("DELETE FROM audit WHERE at<?", (now - KEEP_DAYS_MAX * 86400,))
            self._db.execute("DELETE FROM hook_revisions WHERE at<? AND (hook_id, revision) NOT IN (SELECT id, revision"
                             " FROM hooks) AND (hook_id, revision) NOT IN (SELECT hook_id, hook_rev FROM events)",
                             (now - KEEP_DAYS_MAX * 86400,))
            self._db.execute("DELETE FROM biz_keys WHERE expires_at<=? AND event_id NOT IN (SELECT id FROM events WHERE"
                             " status IN ('received','queued','running'))", (now,))
            # A quarantined event keeps its body for its whole retention (KEEP_DAYS), so the owner told of it can fix
            # the rules and process it again; the per-hook row cap bounds how much that holds.
            self._db.execute(f"UPDATE events SET body=x'', fields='{{}}' WHERE (status IN {fin}) AND status<>'invalid'"
                             " AND finished_at>0 AND"
                             " finished_at<? AND length(body)>0", (now - BODY_KEEP_DAYS * 86400,))
        try:
            with self._lock:
                self._db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.OperationalError:
            pass
        return len(ids)

    def _kept_longer(self, eid: str, longer: dict, now: float) -> bool:
        if not longer:
            return False
        r = self._db.execute("SELECT hook_id, finished_at FROM events WHERE id=?", (eid,)).fetchone()
        return bool(r) and r["hook_id"] in longer and r["finished_at"] >= now - longer[r["hook_id"]] * 86400

    # ── breakers, AI budget, meta, export ──
    def breaker_open_until(self, hook_id: str, action_id: str, now: Optional[float] = None) -> float:
        now = time.time() if now is None else now
        with self._read():
            r = self._db.execute("SELECT open_until FROM breakers WHERE hook_id=? AND action_id=?",
                                 (hook_id, action_id)).fetchone()
        return float(r["open_until"]) if r and float(r["open_until"]) > now else 0.0

    def breaker_record(self, hook_id: str, action_id: str, ok: bool, now: Optional[float] = None) -> str:
        """One outcome of a target. Returns "opened" when this failure opened the breaker, "closed" when a success closed
        an open or failing one, else ""."""
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
                fails = BREAKER_FAILS - 1        # half-open after the cooldown: ONE more failure reopens it
                out = "opened"
            self._db.execute("INSERT OR REPLACE INTO breakers(hook_id, action_id, fails, open_until, opens, updated_at)"
                             " VALUES(?,?,?,?,?,?)", (hook_id, action_id, fails, until, opens, now))
            return out

    def breaker_reset(self, hook_id: str, action_id: str = "") -> None:
        with self._write():
            if action_id:
                self._db.execute("DELETE FROM breakers WHERE hook_id=? AND action_id=?", (hook_id, action_id))
            else:
                self._db.execute("DELETE FROM breakers WHERE hook_id=?", (hook_id,))

    def breakers(self, hook_id: str, now: Optional[float] = None) -> list:
        now = time.time() if now is None else now
        with self._read():
            return [dict(r) for r in self._db.execute("SELECT action_id, fails, open_until, opens FROM breakers WHERE"
                                                       " hook_id=? AND (open_until>? OR fails>0)", (hook_id, now))]

    def ai_runs_since(self, hook_id: str, since: float) -> int:
        """AI dispatches of this hook since `since` ('' = every hook: the global ceiling)."""
        with self._read():
            if hook_id:
                return int(self._db.execute("SELECT COUNT(*) FROM ai_runs WHERE hook_id=? AND at>=?",
                                            (hook_id, since)).fetchone()[0])
            return int(self._db.execute("SELECT COUNT(*) FROM ai_runs WHERE at>=?", (since,)).fetchone()[0])

    def ai_oldest_since(self, hook_id: str, since: float) -> float:
        with self._read():
            r = self._db.execute("SELECT MIN(at) FROM ai_runs WHERE (?='' OR hook_id=?) AND at>=?",
                                 (hook_id, hook_id, since)).fetchone()
        return float(r[0] or 0)

    def ai_record(self, hook_id: str, event_id: str, now: Optional[float] = None) -> None:
        """A model call outside a delivery (incident triage when the hook enabled it): it counts in the same ledger."""
        now = time.time() if now is None else now
        with self._write():
            self._db.execute("INSERT INTO ai_runs(hook_id, event_id, at) VALUES(?,?,?)", (hook_id, event_id, now))

    def meta_get(self, k: str) -> str:
        with self._read():
            r = self._db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return r["v"] if r else ""

    def meta_set(self, k: str, v: str) -> None:
        with self._write():
            self._db.execute("INSERT OR REPLACE INTO meta(k, v) VALUES(?,?)", (k, str(v)))

    def meta_prefix(self, prefix: str) -> list:
        with self._read():
            return [(r["k"], r["v"]) for r in self._db.execute("SELECT k, v FROM meta WHERE k LIKE ? ESCAPE '\\'",
                                                              (prefix.replace("_", "\\_") + "%",))]

    def meta_del(self, k: str) -> None:
        with self._write():
            self._db.execute("DELETE FROM meta WHERE k=?", (k,))

    def finished_counts(self, hook_id: str, since: float, until: float) -> dict:
        with self._read():
            rows = self._db.execute("SELECT status, COUNT(*) AS n FROM events WHERE hook_id=? AND finished_at>=? AND"
                                    " finished_at<? GROUP BY status", (hook_id, since, until)).fetchall()
            partial = self._db.execute(
                "SELECT COUNT(DISTINCT e.id) FROM events e JOIN deliveries d ON d.event_id=e.id AND"
                " d.generation=e.generation WHERE e.hook_id=? AND e.finished_at>=? AND e.finished_at<? AND e.status IN"
                " ('failed','dead') AND d.status IN ('completed','accepted','silent')", (hook_id, since, until)).fetchone()[0]
        out = {r["status"]: r["n"] for r in rows}
        out["partial_failed"] = int(partial)
        return out

    def export_rows(self, hook_id: str = "", since: float = 0.0, until: float = 0.0, with_body: bool = False,
                    batch: int = 200, hooks: Optional[list] = None):
        """Every event of a hook (or of a list of hooks, or all), oldest first, in batches (keyset on received_at, id).
        Bodies only when asked. Never the hook configuration."""
        last_ts, last_id = float(since or 0), ""
        until = float(until or 0) or 1e18
        while True:
            with self._read():
                cond = "(?='' OR hook_id=?)"
                args = [hook_id, hook_id]
                if not hook_id and hooks is not None:
                    cond = "hook_id IN (" + (",".join("?" * len(hooks)) or "''") + ")"
                    args = list(hooks)
                rows = self._db.execute(
                    "SELECT id, hook_id, brain, received_at, status, tries, idem_key, biz_key, source, dispatched_at,"
                    " finished_at, correlation, generation, result, error, fields, trace, reasons" +
                    (", body, content_type" if with_body else "") +
                    f" FROM events WHERE {cond} AND received_at<? AND (received_at>? OR (received_at=? AND"
                    " id>?)) ORDER BY received_at, id LIMIT ?",
                    args + [until, last_ts, last_ts, last_id, batch]).fetchall()
                rows = [dict(r) for r in rows]
                for r in rows:
                    br = [dict(b) for b in self._db.execute(
                        "SELECT action_id, kind, generation, status, tries, delivery_id, detail FROM deliveries WHERE"
                        " event_id=? ORDER BY generation, rowid", (r["id"],))]
                    for b in br:
                        b["state"] = spec_delivery_state(b["status"])
                    r["branches"] = br
                    r["state"] = spec_event_state(r["status"], [b for b in br if b["generation"] == r["generation"]])
            if not rows:
                return
            for r in rows:
                yield r
            last_ts, last_id = rows[-1]["received_at"], rows[-1]["id"]

    def open_events(self) -> list:
        """Events not settled (for the rollback tool): what an older build would have to take over."""
        with self._read():
            return [dict(r) for r in self._db.execute(
                "SELECT id, hook_id, status, received_at, generation, error FROM events WHERE status IN ('received',"
                "'queued','running','unknown','waiting','blocked') ORDER BY received_at")]

    def live_leases(self, now: Optional[float] = None) -> int:
        now = time.time() if now is None else now
        with self._read():
            return int(self._db.execute("SELECT COUNT(*) FROM events WHERE status='running' AND lease_until>?",
                                        (now,)).fetchone()[0])
