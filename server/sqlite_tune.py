"""One place for the durability level of Javis's SQLite stores (performance, 2026-11-10).

A WAL database at SQLite's default `synchronous=FULL` calls fsync on every commit. One chat turn commits about 26 times
across the stores (measured with strace: telemetry rows, the two chat messages, the registry), part of it on the event
loop. On the fast disk of a dev machine that is a millisecond; on a small VPS or a spinning disk an fsync costs 2 to
20 ms, so a turn paid 50 to 500 ms for it.

`synchronous=NORMAL` in WAL mode syncs at checkpoints instead. A crash of Javis loses nothing. A power cut or kernel
crash can lose the last few commits, and never corrupts the database (SQLite's own guarantee for WAL + NORMAL). That is
the trade `task_store` has made since the Kanban store was written. It is only safe in WAL mode, so it is applied only
when the database really is in WAL mode: a filesystem that refuses WAL keeps FULL.

Stores where one lost commit is a lost promise (the webhook inbox: an accepted delivery must survive) do not call this.
"""
from __future__ import annotations

import sqlite3


def wal_normal(db: sqlite3.Connection) -> bool:
    """Put `db` in WAL mode and, if that took, at synchronous=NORMAL. True when both hold."""
    try:
        row = db.execute("PRAGMA journal_mode=WAL").fetchone()
    except sqlite3.OperationalError:
        return False
    if not row or str(row[0]).lower() != "wal":
        return False
    return normal_if_wal(db)


def normal_if_wal(db: sqlite3.Connection) -> bool:
    """synchronous=NORMAL for a connection whose database is already in WAL mode. No-op in any other journal mode."""
    try:
        row = db.execute("PRAGMA journal_mode").fetchone()
        if not row or str(row[0]).lower() != "wal":
            return False
        db.execute("PRAGMA synchronous=NORMAL")
        return True
    except sqlite3.OperationalError:
        return False
