"""Encrypted, short-lived store of FULL tool results.

Why it exists: a connected source often answers with far more than a model should read (ten shop
orders measured 99,000 to 183,000 characters). The old answer was to cut the text, which silently
dropped the middle. The hub now keeps the whole answer here and hands the model a small view plus
a reference (`tool_result_shaper`); `javis_query` reads the rest back by that reference, so
nothing is lost and no tool has to be called twice.

Rules of this store:
  - Fail closed. No working encryption key means nothing is stored; `put` returns "" and the caller
    keeps the old behaviour. Business data never lands on disk in plain text.
  - A result belongs to ONE scope (the brain it was read for). `get` with another scope answers
    None, exactly like an unknown reference.
  - Bounded. Every row has a time to live, one row has a size ceiling, and the whole store has a
    ceiling; the oldest rows leave first. Nothing here is a source of truth, only a copy.

One SQLite file in JAVIS_STATE_DIR. Bodies are zlib-compressed before encryption (JSON shrinks by
five to ten times), so a day of heavy reading stays in the tens of megabytes.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
import zlib
from pathlib import Path
from typing import Optional

REF_PREFIX = "tr_"
DEFAULT_TTL_S = 24 * 3600
MAX_ITEM_CHARS = 24_000_000          # one stored result (a paged dataset can be large)
DEFAULT_TOTAL_BYTES = 256 * 1024 * 1024
_SWEEP_EVERY_S = 600

_lock = threading.RLock()
_db: Optional[sqlite3.Connection] = None
_path: Optional[Path] = None
_last_sweep = 0.0
_crypto = None                        # (encrypt, decrypt, available) override for tests


def configure(path=None, crypto=None) -> None:
    """Point the store somewhere else (tests). Closes the open connection."""
    global _db, _path, _crypto, _last_sweep
    with _lock:
        if _db is not None:
            try:
                _db.close()
            except sqlite3.Error:
                pass
        _db = None
        _path = Path(path) if path else None
        _crypto = crypto
        _last_sweep = 0.0


def _env_int(name: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(os.getenv(name, "") or default)))
    except (TypeError, ValueError):
        return default


def ttl_seconds() -> int:
    return _env_int("JAVIS_TOOL_RESULT_TTL_HOURS", DEFAULT_TTL_S // 3600, 1, 24 * 14) * 3600


def total_bytes_cap() -> int:
    return _env_int("JAVIS_TOOL_RESULT_STORE_MB", DEFAULT_TOTAL_BYTES // (1024 * 1024), 8, 8192) * 1024 * 1024


def _conn() -> sqlite3.Connection:
    global _db, _path
    if _db is None:
        if _path is None:
            from config import STATE_DIR
            _path = Path(STATE_DIR) / "tool_results.sqlite3"
        _path.parent.mkdir(parents=True, exist_ok=True)
        _db = sqlite3.connect(str(_path), check_same_thread=False)
        _db.execute("PRAGMA journal_mode=WAL")
        _db.execute("PRAGMA busy_timeout=5000")
        _db.executescript(
            """
            CREATE TABLE IF NOT EXISTS results (
                ref TEXT PRIMARY KEY,
                scope TEXT NOT NULL DEFAULT '',
                tool TEXT NOT NULL DEFAULT '',
                conn_id TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT 'result',
                created REAL NOT NULL,
                expires REAL NOT NULL,
                chars INTEGER NOT NULL,
                stored_bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                meta TEXT NOT NULL DEFAULT '{}',
                body TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_results_expires ON results(expires);
            CREATE INDEX IF NOT EXISTS idx_results_created ON results(created);
            """
        )
        _db.commit()
        try:
            os.chmod(_path, 0o600)
        except OSError:
            pass
    return _db


def _codec():
    if _crypto is not None:
        return _crypto
    import secrets_store
    return secrets_store.encrypt_required, secrets_store.decrypt, secrets_store.encryption_available


def available() -> bool:
    """True when a result can be stored right now (an encryption key is usable)."""
    try:
        return bool(_codec()[2]())
    except Exception:  # noqa: BLE001 - an unusable key simply means "do not store"
        return False


def norm_scope(scope) -> str:
    """One spelling per brain. The hub, a scout and a recipe replay each learn the brain's folder their own way
    (a request header, the open brain, a reminder's brain), so the same folder can arrive as a symlink, with a
    trailing slash or in another letter case; a result stored under one spelling must be readable under another."""
    raw = str(scope or "").strip()
    if not raw:
        return ""
    try:
        return os.path.normcase(os.path.realpath(raw))
    except (OSError, ValueError):
        return raw


def _pack(text: str) -> str:
    packed = base64.b64encode(zlib.compress(text.encode("utf-8", errors="replace"), 6)).decode("ascii")
    return _codec()[0](packed)


def _unpack(body: str) -> str:
    packed = _codec()[1](body)
    if not packed:
        raise ValueError("tool_result_undecryptable")
    return zlib.decompress(base64.b64decode(packed)).decode("utf-8", errors="replace")


def put(text: str, *, scope: str = "", tool: str = "", conn_id: str = "", kind: str = "result",
        meta: Optional[dict] = None, ttl: Optional[int] = None) -> str:
    """Store one full result. Returns its reference, or "" when it was not stored.

    "" is never an error for the caller: no key, an oversized body or a full disk all mean "carry
    on without a stored copy"."""
    if not isinstance(text, str) or not text or len(text) > MAX_ITEM_CHARS or not available():
        return ""
    try:
        body = _pack(text)
        now = time.time()
        ref = REF_PREFIX + secrets.token_hex(12)
        digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        with _lock:
            db = _conn()
            db.execute(
                "INSERT INTO results(ref, scope, tool, conn_id, kind, created, expires, chars, stored_bytes, "
                "sha256, meta, body) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (ref, norm_scope(scope), str(tool or "")[:200], str(conn_id or "")[:200], str(kind or "result")[:40],
                 now, now + max(60, int(ttl or ttl_seconds())), len(text), len(body), digest,
                 json.dumps(meta or {}, ensure_ascii=False, default=str)[:20_000], body))
            db.commit()
        _maybe_sweep()
        return ref
    except Exception as e:  # noqa: BLE001 - storing is an optimisation, never a reason to fail a tool call
        import sys
        print(f"[tool results] not stored: {type(e).__name__}: {e}", file=sys.stderr)
        return ""


def get(ref: str, scope: str = "") -> Optional[dict]:
    """{'text', 'tool', 'conn_id', 'kind', 'chars', 'created', 'expires', 'meta'} or None.

    None covers every refusal the same way (unknown, expired, another brain's, undecryptable), so a
    caller cannot use the answer to probe which references exist."""
    ref = str(ref or "").strip()
    if not ref.startswith(REF_PREFIX) or len(ref) > 64:
        return None
    try:
        with _lock:
            row = _conn().execute(
                "SELECT scope, tool, conn_id, kind, created, expires, chars, meta, body FROM results WHERE ref=?",
                (ref,)).fetchone()
        if not row or row[0] != norm_scope(scope) or row[5] <= time.time():
            return None
        try:
            meta = json.loads(row[7] or "{}")
        except ValueError:
            meta = {}
        return {"ref": ref, "text": _unpack(row[8]), "tool": row[1], "conn_id": row[2], "kind": row[3],
                "created": row[4], "expires": row[5], "chars": row[6], "meta": meta if isinstance(meta, dict) else {}}
    except Exception:  # noqa: BLE001 - a broken row reads as "not there"
        return None


def delete(ref: str) -> None:
    try:
        with _lock:
            db = _conn()
            db.execute("DELETE FROM results WHERE ref=?", (str(ref or ""),))
            db.commit()
    except sqlite3.Error:
        pass


def sweep(now: Optional[float] = None) -> dict:
    """Drop expired rows, then the oldest rows while the store is over its size ceiling."""
    global _last_sweep
    out = {"expired": 0, "evicted": 0}
    try:
        with _lock:
            db = _conn()
            cur = db.execute("DELETE FROM results WHERE expires<=?", (float(now or time.time()),))
            out["expired"] = cur.rowcount or 0
            cap = total_bytes_cap()
            total = db.execute("SELECT COALESCE(SUM(stored_bytes),0) FROM results").fetchone()[0] or 0
            if total > cap:
                for ref, size in db.execute("SELECT ref, stored_bytes FROM results ORDER BY created").fetchall():
                    if total <= cap * 0.8:
                        break
                    db.execute("DELETE FROM results WHERE ref=?", (ref,))
                    total -= size
                    out["evicted"] += 1
            db.commit()
            _last_sweep = time.time()
    except sqlite3.Error:
        pass
    return out


def _maybe_sweep() -> None:
    if time.time() - _last_sweep > _SWEEP_EVERY_S:
        sweep()


def stats() -> dict:
    try:
        with _lock:
            n, chars, stored = _conn().execute(
                "SELECT COUNT(*), COALESCE(SUM(chars),0), COALESCE(SUM(stored_bytes),0) FROM results").fetchone()
        return {"items": int(n or 0), "chars": int(chars or 0), "stored_bytes": int(stored or 0)}
    except sqlite3.Error:
        return {"items": 0, "chars": 0, "stored_bytes": 0}
