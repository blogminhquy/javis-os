"""Durable SQLite store for the autonomous Javis task queue.

The queue is runtime state, so SQLite lives in JAVIS_STATE_DIR instead of inside a
brain that may be synchronized by Git. A JSON snapshot is still exported by
``tasks.py`` for portability and backwards compatibility with older Javis builds.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import unicodedata
import re
import uuid
from pathlib import Path
from typing import Any, Iterable, Optional


VALID_STATUS = {
    "triage", "todo", "ready", "running", "review", "blocked", "done",
    "cancelled", "archived",
}
TERMINAL_STATUS = {"done", "cancelled", "archived"}
ACTIVE_STATUS = {"triage", "todo", "ready", "running", "review", "blocked"}


def now() -> float:
    return time.time()


def norm_title(text: str) -> str:
    value = unicodedata.normalize("NFD", (text or "").lower())
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", value)).strip()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _loads(value: Any, fallback: Any) -> Any:
    try:
        parsed = json.loads(value or "")
        return parsed
    except Exception:
        return fallback


class TaskStore:
    """Small transactional task database.

    All mutations use ``BEGIN IMMEDIATE`` and compare-and-set status transitions.
    This makes claiming safe even when the API and dispatcher race.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(self.path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.execute("PRAGMA busy_timeout=5000")
        self._schema()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def _schema(self) -> None:
        with self._lock:
            self._db.executescript(
                """
                CREATE TABLE IF NOT EXISTS boards (
                    brain_root TEXT PRIMARY KEY,
                    orchestration TEXT NOT NULL DEFAULT 'off',
                    paused_reason TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    brain_root TEXT NOT NULL,
                    title TEXT NOT NULL,
                    normalized_title TEXT NOT NULL,
                    intent TEXT NOT NULL DEFAULT '',
                    route TEXT NOT NULL DEFAULT 'auto',
                    capability TEXT NOT NULL DEFAULT 'auto',
                    execution_mode TEXT NOT NULL DEFAULT 'auto',
                    priority INTEGER NOT NULL DEFAULT 2,
                    status TEXT NOT NULL DEFAULT 'triage',
                    needs_approval INTEGER NOT NULL DEFAULT 0,
                    block_kind TEXT NOT NULL DEFAULT '',
                    block_reason TEXT NOT NULL DEFAULT '',
                    created_by TEXT NOT NULL DEFAULT 'user',
                    chat_id TEXT NOT NULL DEFAULT '',
                    idempotency_key TEXT NOT NULL DEFAULT '',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    claimed_by TEXT NOT NULL DEFAULT '',
                    claim_expires_at REAL NOT NULL DEFAULT 0,
                    last_heartbeat_at REAL NOT NULL DEFAULT 0,
                    current_run_id TEXT NOT NULL DEFAULT '',
                    result TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    artifacts_json TEXT NOT NULL DEFAULT '[]',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_tasks_board_status
                    ON tasks(brain_root, status, priority, created_at);
                CREATE INDEX IF NOT EXISTS idx_tasks_claim
                    ON tasks(status, claim_expires_at);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_idempotency
                    ON tasks(brain_root, idempotency_key)
                    WHERE idempotency_key <> '';

                CREATE TABLE IF NOT EXISTS task_dependencies (
                    task_id TEXT NOT NULL,
                    depends_on_id TEXT NOT NULL,
                    PRIMARY KEY(task_id, depends_on_id)
                );

                CREATE TABLE IF NOT EXISTS task_runs (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    brain_root TEXT NOT NULL,
                    worker_id TEXT NOT NULL,
                    engine_provider TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    heartbeat_at REAL NOT NULL,
                    finished_at REAL NOT NULL DEFAULT 0,
                    error TEXT NOT NULL DEFAULT '',
                    result TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_runs_task
                    ON task_runs(task_id, started_at DESC);

                CREATE TABLE IF NOT EXISTS task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    run_id TEXT NOT NULL DEFAULT '',
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_events_task
                    ON task_events(task_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS task_migrations (
                    migration_key TEXT PRIMARY KEY,
                    migrated_at REAL NOT NULL
                );
                """
            )
            self._db.commit()

    def _tx(self) -> None:
        self._db.execute("BEGIN IMMEDIATE")

    def ensure_board(self, brain_root: str, orchestration: str = "off") -> None:
        ts = now()
        with self._lock:
            self._db.execute(
                """INSERT OR IGNORE INTO boards
                   (brain_root, orchestration, created_at, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (brain_root, orchestration, ts, ts),
            )
            self._db.commit()

    def set_orchestration(self, brain_root: str, mode: str) -> None:
        self.ensure_board(brain_root)
        with self._lock:
            self._db.execute(
                "UPDATE boards SET orchestration=?, updated_at=? WHERE brain_root=?",
                (mode, now(), brain_root),
            )
            self._db.commit()

    def board_mode(self, brain_root: str) -> str:
        self.ensure_board(brain_root)
        with self._lock:
            row = self._db.execute(
                "SELECT orchestration FROM boards WHERE brain_root=?", (brain_root,)
            ).fetchone()
        return str(row["orchestration"] if row else "off")

    def board_roots(self) -> list[str]:
        with self._lock:
            rows = self._db.execute(
                "SELECT brain_root FROM boards ORDER BY brain_root"
            ).fetchall()
        return [str(r["brain_root"]) for r in rows]

    def _event(
        self,
        task_id: str,
        event_type: str,
        message: str = "",
        run_id: str = "",
        metadata: Optional[dict] = None,
    ) -> None:
        self._db.execute(
            """INSERT INTO task_events
               (task_id, run_id, event_type, message, metadata_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (task_id, run_id, event_type, message, _json(metadata or {}), now()),
        )

    def enqueue(
        self,
        brain_root: str,
        title: str,
        intent: str,
        route: str = "auto",
        priority: int = 2,
        deps: Optional[Iterable[str]] = None,
        needs_approval: bool = False,
        created_by: str = "user",
        chat_id: str = "",
        capability: str = "auto",
        execution_mode: str = "auto",
        idempotency_key: str = "",
        status: str = "triage",
        max_attempts: int = 3,
        task_id: str = "",
    ) -> str:
        root = str(brain_root)
        self.ensure_board(root)
        title = (title or intent or "Task")[:160]
        normalized = norm_title(title)
        ts = now()
        with self._lock:
            self._tx()
            try:
                if idempotency_key:
                    row = self._db.execute(
                        """SELECT id FROM tasks
                           WHERE brain_root=? AND idempotency_key=? LIMIT 1""",
                        (root, idempotency_key),
                    ).fetchone()
                    if row:
                        self._db.commit()
                        return str(row["id"])
                if normalized:
                    row = self._db.execute(
                        f"""SELECT id FROM tasks
                            WHERE brain_root=? AND normalized_title=?
                              AND status IN ({','.join('?' for _ in ACTIVE_STATUS)})
                            ORDER BY created_at LIMIT 1""",
                        (root, normalized, *sorted(ACTIVE_STATUS)),
                    ).fetchone()
                    if row:
                        self._db.commit()
                        return str(row["id"])

                tid = task_id or ("t_" + uuid.uuid4().hex[:12])
                safe_status = status if status in VALID_STATUS else "triage"
                self._db.execute(
                    """INSERT INTO tasks (
                        id, brain_root, title, normalized_title, intent, route,
                        capability, execution_mode, priority, status, needs_approval,
                        created_by, chat_id, idempotency_key, max_attempts,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        tid, root, title, normalized, intent or title, route or "auto",
                        capability or "auto", execution_mode or "auto",
                        max(1, min(3, int(priority or 2))), safe_status,
                        int(bool(needs_approval)), created_by or "user", str(chat_id or ""),
                        idempotency_key or "", max(1, int(max_attempts or 3)), ts, ts,
                    ),
                )
                for dep in dict.fromkeys(str(d) for d in (deps or []) if str(d)):
                    self._db.execute(
                        """INSERT OR IGNORE INTO task_dependencies(task_id, depends_on_id)
                           VALUES (?, ?)""",
                        (tid, dep),
                    )
                self._event(tid, "created", f"created by {created_by or 'user'}")
                self._db.commit()
                return tid
            except Exception:
                self._db.rollback()
                raise

    def _task_from_row(self, row: sqlite3.Row) -> dict:
        task = dict(row)
        task["needs_approval"] = bool(task.get("needs_approval"))
        task["metadata"] = _loads(task.pop("metadata_json", "{}"), {})
        task["artifacts"] = _loads(task.pop("artifacts_json", "[]"), [])
        with self._lock:
            deps = self._db.execute(
                "SELECT depends_on_id FROM task_dependencies WHERE task_id=? ORDER BY depends_on_id",
                (task["id"],),
            ).fetchall()
        task["deps"] = [str(d["depends_on_id"]) for d in deps]
        return task

    def get_task(self, task_id: str) -> Optional[dict]:
        with self._lock:
            row = self._db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        return self._task_from_row(row) if row else None

    def list_tasks(
        self,
        brain_root: str,
        include_archived: bool = False,
        limit: int = 500,
    ) -> list[dict]:
        sql = "SELECT * FROM tasks WHERE brain_root=?"
        args: list[Any] = [brain_root]
        if not include_archived:
            sql += " AND status <> 'archived'"
        sql += " ORDER BY priority, created_at LIMIT ?"
        args.append(max(1, min(5000, int(limit))))
        with self._lock:
            rows = self._db.execute(sql, args).fetchall()
        return [self._task_from_row(r) for r in rows]

    def list_events(self, task_id: str, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                """SELECT * FROM task_events WHERE task_id=?
                   ORDER BY id DESC LIMIT ?""",
                (task_id, max(1, min(500, int(limit)))),
            ).fetchall()
        out = []
        for row in reversed(rows):
            value = dict(row)
            value["metadata"] = _loads(value.pop("metadata_json", "{}"), {})
            out.append(value)
        return out

    def list_runs(self, task_id: str, limit: int = 20) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                """SELECT * FROM task_runs WHERE task_id=?
                   ORDER BY started_at DESC LIMIT ?""",
                (task_id, max(1, min(100, int(limit)))),
            ).fetchall()
        out = []
        for row in rows:
            value = dict(row)
            value["metadata"] = _loads(value.pop("metadata_json", "{}"), {})
            out.append(value)
        return out

    def promote_dependencies(self, brain_root: str) -> int:
        """Move dependency-waiting tasks to ready when every parent is terminal-successful."""
        with self._lock:
            self._tx()
            try:
                ids = [
                    str(r["id"])
                    for r in self._db.execute(
                        """
                        SELECT t.id
                        FROM tasks t
                        WHERE t.brain_root=? AND t.status='todo'
                          AND EXISTS (
                              SELECT 1 FROM task_dependencies d WHERE d.task_id=t.id
                          )
                          AND NOT EXISTS (
                              SELECT 1
                              FROM task_dependencies d
                              LEFT JOIN tasks p ON p.id=d.depends_on_id
                              WHERE d.task_id=t.id
                                AND (p.id IS NULL OR p.status NOT IN ('done','archived'))
                          )
                        """,
                        (brain_root,),
                    ).fetchall()
                ]
                ts = now()
                for tid in ids:
                    self._db.execute(
                        "UPDATE tasks SET status='ready', updated_at=? WHERE id=? AND status='todo'",
                        (ts, tid),
                    )
                    self._event(tid, "dependency_ready", "all dependencies completed")
                self._db.commit()
                return len(ids)
            except Exception:
                self._db.rollback()
                raise

    def reclaim_stale(self, brain_root: str, active_worker_ids: set[str]) -> int:
        ts = now()
        with self._lock:
            self._tx()
            try:
                rows = self._db.execute(
                    """SELECT id, claimed_by, current_run_id FROM tasks
                       WHERE brain_root=? AND status='running'
                         AND claim_expires_at > 0 AND claim_expires_at < ?""",
                    (brain_root, ts),
                ).fetchall()
                reclaimed = 0
                for row in rows:
                    if str(row["claimed_by"]) in active_worker_ids:
                        continue
                    tid = str(row["id"])
                    run_id = str(row["current_run_id"] or "")
                    self._db.execute(
                        """UPDATE tasks SET status='ready', claimed_by='',
                           claim_expires_at=0, current_run_id='', updated_at=?
                           WHERE id=? AND status='running'""",
                        (ts, tid),
                    )
                    if run_id:
                        self._db.execute(
                            """UPDATE task_runs SET status='stale', finished_at=?,
                               error='worker heartbeat expired'
                               WHERE id=? AND status='running'""",
                            (ts, run_id),
                        )
                    self._event(tid, "reclaimed", "worker heartbeat expired", run_id)
                    reclaimed += 1
                self._db.commit()
                return reclaimed
            except Exception:
                self._db.rollback()
                raise

    def next_candidate(self, brain_root: str) -> Optional[dict]:
        with self._lock:
            row = self._db.execute(
                """SELECT * FROM tasks
                   WHERE brain_root=? AND status IN ('triage','ready')
                   ORDER BY CASE status WHEN 'triage' THEN 0 ELSE 1 END,
                            priority, created_at
                   LIMIT 1""",
                (brain_root,),
            ).fetchone()
        return self._task_from_row(row) if row else None

    def claim(
        self,
        task_id: str,
        worker_id: str,
        lease_seconds: int = 90,
        engine_provider: str = "",
    ) -> Optional[dict]:
        """Atomically claim exactly one selected task."""
        ts = now()
        run_id = "run_" + uuid.uuid4().hex[:14]
        with self._lock:
            self._tx()
            try:
                row = self._db.execute(
                    "SELECT * FROM tasks WHERE id=?", (task_id,)
                ).fetchone()
                if not row or row["status"] not in ("triage", "ready"):
                    self._db.rollback()
                    return None
                if row["status"] == "ready":
                    unfinished = self._db.execute(
                        """
                        SELECT COUNT(*) AS n
                        FROM task_dependencies d
                        LEFT JOIN tasks p ON p.id=d.depends_on_id
                        WHERE d.task_id=?
                          AND (p.id IS NULL OR p.status NOT IN ('done','archived'))
                        """,
                        (task_id,),
                    ).fetchone()["n"]
                    if unfinished:
                        self._db.execute(
                            "UPDATE tasks SET status='todo', updated_at=? WHERE id=?",
                            (ts, task_id),
                        )
                        self._event(task_id, "waiting_dependency", "unfinished dependency")
                        self._db.commit()
                        return None
                changed = self._db.execute(
                    """UPDATE tasks
                       SET status='running', attempts=attempts+1, claimed_by=?,
                           claim_expires_at=?, last_heartbeat_at=?,
                           current_run_id=?, block_kind='', block_reason='', updated_at=?
                       WHERE id=? AND status IN ('triage','ready')""",
                    (worker_id, ts + lease_seconds, ts, run_id, ts, task_id),
                ).rowcount
                if changed != 1:
                    self._db.rollback()
                    return None
                self._db.execute(
                    """INSERT INTO task_runs
                       (id, task_id, brain_root, worker_id, engine_provider, status,
                        started_at, heartbeat_at)
                       VALUES (?, ?, ?, ?, ?, 'running', ?, ?)""",
                    (
                        run_id, task_id, str(row["brain_root"]), worker_id,
                        engine_provider or "", ts, ts,
                    ),
                )
                self._event(task_id, "claimed", f"claimed by {worker_id}", run_id)
                self._db.commit()
            except Exception:
                self._db.rollback()
                raise
        return self.get_task(task_id)

    def heartbeat(self, task_id: str, worker_id: str, lease_seconds: int = 90) -> bool:
        ts = now()
        with self._lock:
            self._tx()
            try:
                row = self._db.execute(
                    "SELECT current_run_id FROM tasks WHERE id=? AND status='running' AND claimed_by=?",
                    (task_id, worker_id),
                ).fetchone()
                if not row:
                    self._db.rollback()
                    return False
                self._db.execute(
                    """UPDATE tasks SET last_heartbeat_at=?, claim_expires_at=?, updated_at=?
                       WHERE id=?""",
                    (ts, ts + lease_seconds, ts, task_id),
                )
                if row["current_run_id"]:
                    self._db.execute(
                        "UPDATE task_runs SET heartbeat_at=? WHERE id=?",
                        (ts, row["current_run_id"]),
                    )
                self._db.commit()
                return True
            except Exception:
                self._db.rollback()
                raise

    def _finish(
        self,
        task_id: str,
        worker_id: str,
        status: str,
        result: str = "",
        error: str = "",
        block_kind: str = "",
        block_reason: str = "",
        metadata: Optional[dict] = None,
        artifacts: Optional[list] = None,
        event_type: str = "completed",
    ) -> Optional[dict]:
        if status not in VALID_STATUS:
            raise ValueError("invalid task status")
        ts = now()
        with self._lock:
            self._tx()
            try:
                row = self._db.execute(
                    """SELECT current_run_id FROM tasks
                       WHERE id=? AND status='running' AND claimed_by=?""",
                    (task_id, worker_id),
                ).fetchone()
                if not row:
                    self._db.rollback()
                    return None
                run_id = str(row["current_run_id"] or "")
                self._db.execute(
                    """UPDATE tasks
                       SET status=?, result=?, block_kind=?, block_reason=?,
                           metadata_json=?, artifacts_json=?, claimed_by='',
                           claim_expires_at=0, last_heartbeat_at=?, current_run_id='',
                           updated_at=?
                       WHERE id=?""",
                    (
                        status, (result or "")[:20000], block_kind or "",
                        (block_reason or "")[:2000], _json(metadata or {}),
                        _json(artifacts or []), ts, ts, task_id,
                    ),
                )
                if run_id:
                    run_status = "completed" if status in ("done", "review", "ready") else status
                    self._db.execute(
                        """UPDATE task_runs
                           SET status=?, finished_at=?, heartbeat_at=?, error=?,
                               result=?, metadata_json=?
                           WHERE id=?""",
                        (
                            run_status, ts, ts, (error or block_reason or "")[:4000],
                            (result or "")[:20000], _json(metadata or {}), run_id,
                        ),
                    )
                self._event(
                    task_id, event_type, block_reason or error or status, run_id, metadata
                )
                self._db.commit()
            except Exception:
                self._db.rollback()
                raise
        return self.get_task(task_id)

    def complete(
        self,
        task_id: str,
        worker_id: str,
        result: str,
        needs_approval: bool = False,
        metadata: Optional[dict] = None,
        artifacts: Optional[list] = None,
    ) -> Optional[dict]:
        return self._finish(
            task_id, worker_id, "review" if needs_approval else "done",
            result=result, metadata=metadata, artifacts=artifacts,
            event_type="completed",
        )

    def prepared(
        self,
        task_id: str,
        worker_id: str,
        intent: str,
        capability: str,
        execution_mode: str,
        metadata: Optional[dict] = None,
    ) -> Optional[dict]:
        ts = now()
        with self._lock:
            self._tx()
            try:
                row = self._db.execute(
                    """SELECT current_run_id FROM tasks
                       WHERE id=? AND status='running' AND claimed_by=?""",
                    (task_id, worker_id),
                ).fetchone()
                if not row:
                    self._db.rollback()
                    return None
                run_id = str(row["current_run_id"] or "")
                self._db.execute(
                    """UPDATE tasks
                       SET status='ready', attempts=CASE WHEN attempts > 0 THEN attempts - 1 ELSE 0 END,
                           intent=?, capability=?, execution_mode=?,
                           metadata_json=?, claimed_by='', claim_expires_at=0,
                           current_run_id='', updated_at=?
                       WHERE id=?""",
                    (
                        intent, capability or "files", execution_mode or "auto",
                        _json(metadata or {}), ts, task_id,
                    ),
                )
                if run_id:
                    self._db.execute(
                        """UPDATE task_runs SET status='specified', finished_at=?,
                           heartbeat_at=?, result=?, metadata_json=? WHERE id=?""",
                        (ts, ts, intent[:20000], _json(metadata or {}), run_id),
                    )
                self._event(
                    task_id, "specified", f"capability={capability}", run_id, metadata
                )
                self._db.commit()
            except Exception:
                self._db.rollback()
                raise
        return self.get_task(task_id)

    def block(
        self,
        task_id: str,
        worker_id: str,
        kind: str,
        reason: str,
        result: str = "",
        transient: bool = False,
    ) -> Optional[dict]:
        task = self.get_task(task_id)
        if not task:
            return None
        retry = bool(transient and int(task["attempts"]) < int(task["max_attempts"]))
        return self._finish(
            task_id, worker_id, "ready" if retry else "blocked",
            result=result, error=reason, block_kind=kind,
            block_reason=reason, event_type="retry_scheduled" if retry else "blocked",
        )

    def move(self, task_id: str, status: str, reason: str = "operator") -> bool:
        if status not in VALID_STATUS:
            return False
        with self._lock:
            self._tx()
            try:
                row = self._db.execute(
                    "SELECT status FROM tasks WHERE id=?", (task_id,)
                ).fetchone()
                if not row:
                    self._db.rollback()
                    return False
                if row["status"] == "running":
                    self._db.rollback()
                    return False
                self._db.execute(
                    """UPDATE tasks SET status=?, block_kind='', block_reason='',
                       claimed_by='', claim_expires_at=0, current_run_id='', updated_at=?
                       WHERE id=?""",
                    (status, now(), task_id),
                )
                self._event(task_id, "operator_move", f"{row['status']} -> {status}: {reason}")
                self._db.commit()
                return True
            except Exception:
                self._db.rollback()
                raise

    def recover_codex_global_flag_blocks(self, brain_root: str) -> int:
        """Retry tasks blocked by the v0.9.173 Codex argv ordering regression once.

        The match is intentionally narrow so operator/input blocks and unrelated
        Codex failures remain untouched.
        """
        key = "recovery:codex-global-flags-v1:" + str(brain_root)
        with self._lock:
            self._tx()
            try:
                seen = self._db.execute(
                    "SELECT 1 FROM task_migrations WHERE migration_key=?", (key,)
                ).fetchone()
                if seen:
                    self._db.rollback()
                    return 0
                rows = self._db.execute(
                    """SELECT id FROM tasks
                       WHERE brain_root=? AND status='blocked'
                         AND block_reason LIKE '%unexpected argument%'
                         AND block_reason LIKE '%--ask-for-approval%'""",
                    (brain_root,),
                ).fetchall()
                ts = now()
                for row in rows:
                    task_id = str(row["id"])
                    self._db.execute(
                        """UPDATE tasks
                           SET status='ready',
                               attempts=CASE WHEN attempts > 0 THEN attempts - 1 ELSE 0 END,
                               block_kind='', block_reason='', claimed_by='',
                               claim_expires_at=0, current_run_id='', updated_at=?
                           WHERE id=? AND status='blocked'""",
                        (ts, task_id),
                    )
                    self._event(
                        task_id,
                        "system_recovered",
                        "retry after Codex global flag ordering fix",
                    )
                self._db.execute(
                    """INSERT INTO task_migrations(migration_key, migrated_at)
                       VALUES (?, ?)""",
                    (key, ts),
                )
                self._db.commit()
                return len(rows)
            except Exception:
                self._db.rollback()
                raise

    def cancel_running(self, task_id: str, reason: str = "operator cancel") -> bool:
        ts = now()
        with self._lock:
            self._tx()
            try:
                row = self._db.execute(
                    "SELECT current_run_id FROM tasks WHERE id=? AND status='running'",
                    (task_id,),
                ).fetchone()
                if not row:
                    self._db.rollback()
                    return False
                self._db.execute(
                    """UPDATE tasks SET status='cancelled', block_kind='cancelled',
                       block_reason=?, claimed_by='', claim_expires_at=0,
                       current_run_id='', updated_at=? WHERE id=?""",
                    (reason, ts, task_id),
                )
                if row["current_run_id"]:
                    self._db.execute(
                        """UPDATE task_runs SET status='cancelled', finished_at=?, error=?
                           WHERE id=?""",
                        (ts, reason, row["current_run_id"]),
                    )
                self._event(task_id, "cancelled", reason, str(row["current_run_id"] or ""))
                self._db.commit()
                return True
            except Exception:
                self._db.rollback()
                raise

    def health(self, brain_root: Optional[str] = None) -> dict:
        where = " WHERE brain_root=?" if brain_root else ""
        args = (brain_root,) if brain_root else ()
        with self._lock:
            rows = self._db.execute(
                f"SELECT status, COUNT(*) AS n FROM tasks{where} GROUP BY status", args
            ).fetchall()
            recent = self._db.execute(
                f"""SELECT COUNT(*) AS n FROM tasks{where}
                    {'AND' if where else 'WHERE'} status='done' AND updated_at>=?""",
                (*args, now() - 86400),
            ).fetchone()
        counts = {s: 0 for s in VALID_STATUS}
        counts.update({str(r["status"]): int(r["n"]) for r in rows})
        return {"counts": counts, "completed_24h": int(recent["n"] if recent else 0)}

    def import_legacy(self, brain_root: str, json_path: Path) -> int:
        """Import a legacy board once, preserving ids and terminal state."""
        key = "legacy-json:" + str(Path(json_path).resolve())
        with self._lock:
            seen = self._db.execute(
                "SELECT 1 FROM task_migrations WHERE migration_key=?", (key,)
            ).fetchone()
        if seen:
            return 0
        data: dict = {}
        try:
            if json_path.is_file():
                parsed = json.loads(json_path.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    data = parsed
        except Exception:
            data = {}
        self.ensure_board(brain_root, str(data.get("orchestration") or "off"))
        imported = 0
        for old in data.get("tasks", []) if isinstance(data.get("tasks"), list) else []:
            try:
                old_status = str(old.get("status") or "triage")
                if old_status not in VALID_STATUS:
                    old_status = "triage"
                # A process from the legacy in-memory dispatcher cannot still be
                # alive after migration/restart, so never import it as running.
                if old_status == "running":
                    old_status = "ready"
                created_by = str(old.get("created_by") or "legacy")
                self.enqueue(
                    brain_root=brain_root,
                    title=str(old.get("title") or old.get("intent") or "Task"),
                    intent=str(old.get("intent") or old.get("title") or ""),
                    route=str(old.get("route") or "auto"),
                    priority=int(old.get("priority") or 2),
                    deps=old.get("deps") or [],
                    # Old Learn tasks all forced review. The autonomous queue now
                    # reserves intervention for typed external-write/input blocks.
                    needs_approval=bool(old.get("needs_approval", False)) and created_by != "learn",
                    created_by=created_by,
                    chat_id=str(old.get("chat_id") or ""),
                    capability=str(old.get("capability") or "auto"),
                    execution_mode=str(old.get("execution_mode") or "auto"),
                    status=old_status,
                    task_id=str(old.get("id") or ""),
                )
                task = self.get_task(str(old.get("id") or ""))
                if task and (old.get("result") or old.get("block_reason")):
                    with self._lock:
                        self._db.execute(
                            """UPDATE tasks SET result=?, block_kind=?, block_reason=?,
                               created_at=?, updated_at=? WHERE id=?""",
                            (
                                str(old.get("result") or "")[:20000],
                                str(old.get("block_kind") or old.get("block_reason") or ""),
                                str(old.get("block_reason") or "")[:2000],
                                float(old.get("created_at") or now()),
                                float(old.get("updated_at") or now()),
                                task["id"],
                            ),
                        )
                        self._db.commit()
                imported += 1
            except Exception:
                continue
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO task_migrations(migration_key, migrated_at) VALUES (?, ?)",
                (key, now()),
            )
            self._db.execute(
                "UPDATE boards SET orchestration=?, updated_at=? WHERE brain_root=?",
                (str(data.get("orchestration") or "off"), now(), brain_root),
            )
            self._db.commit()
        return imported
