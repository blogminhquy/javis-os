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

import team_migration


VALID_STATUS = {
    "triage", "todo", "ready", "running", "review", "blocked", "done",
    "cancelled", "archived",
}
# Sổ hỏi đáp của một việc (`metadata.qa`, 0.235.0): giữ ngần này lượt gần nhất, mỗi câu tối đa
# QA_TEXT_MAX ký tự, phần "đã làm tới đâu" tối đa QA_PROGRESS_MAX. Đủ cho lần chạy sau hiểu
# chuyện, không đủ để phình kho hay prompt.
QA_KEEP = 8
QA_TEXT_MAX = 1000
QA_PROGRESS_MAX = 1500
TERMINAL_STATUS = {"done", "cancelled", "archived"}
ACTIVE_STATUS = {"triage", "todo", "ready", "running", "review", "blocked"}
# Trạng thái của làn `team` (nhóm chat). Cố ý KHÔNG nằm trong VALID_STATUS: lệnh kéo thả
# của bảng Việc (`move`) không thể đặt một việc Kanban vào làn nhóm hay ngược lại.
TEAM_OPEN_STATUS = ("team_queued", "team_running", "team_blocked")
_TEAM_COLUMNS = (
    ("lane", "TEXT NOT NULL DEFAULT ''"),
    ("team_id", "TEXT NOT NULL DEFAULT ''"),
    ("team_seq", "INTEGER NOT NULL DEFAULT 0"),
    ("team_prio", "INTEGER"),
    ("team_rev", "INTEGER NOT NULL DEFAULT 0"),
    ("assignee_key", "TEXT NOT NULL DEFAULT ''"),
    ("coordinator_key", "TEXT NOT NULL DEFAULT ''"),
    ("source_ref", "TEXT NOT NULL DEFAULT ''"),
    ('acceptance_ready', 'INTEGER NOT NULL DEFAULT 0'),
    ('acceptance_revision', 'INTEGER NOT NULL DEFAULT 0'),
    ('acceptance_contract_version', 'INTEGER NOT NULL DEFAULT 0'),
)
_TEAM_ORDER = "(team_prio IS NULL), team_prio, team_seq"


class QueueConflict(Exception):
    """Lệnh hàng đợi dùng `queue_version` cũ (hai tab cùng đổi, điều phối vừa nhận việc).
    `queue` là hàng đợi hiện tại để giao diện vẽ lại theo trạng thái thật (HTTP 409)."""

    def __init__(self, queue: dict):
        super().__init__("queue_version_conflict")
        self.queue = queue


class QueueError(ValueError):
    """Lệnh hàng đợi không áp được cho việc này (không thuộc làn team, đã kết thúc...)."""


def now() -> float:
    return time.time()


def norm_title(text: str) -> str:
    value = unicodedata.normalize("NFD", (text or "").lower())
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", value)).strip()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def agent_prefix(idempotency_key: Any) -> str:
    """`agent:<mã>:` của việc giao trực tiếp cho một trợ lý (khoá `agent:<mã>:<slug>:...`, 0.142.0), rỗng nếu không phải.

    Một trợ lý chạy MỘT việc giao trực tiếp một lúc: giao nhiều việc không tự mở nhiều lượt model đồng thời cho cùng
    trợ lý. Việc của trợ lý khác, việc Kanban thường vẫn chạy song song tới trần JAVIS_KANBAN_MAX_WORKERS."""
    k = str(idempotency_key or "")
    if not k.startswith("agent:"):
        return ""
    rest = k[len("agent:"):]
    head, sep, _tail = rest.partition(":")
    return f"agent:{head}:" if head and sep else ""


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
        # 0.140.0: kho có từ trước thì chụp một bản trước khi thêm cột làn `team` (khôi phục khi hạ phiên bản).
        team_migration.snapshot_once(self.path, "tasks", "lane")
        team_migration.snapshot_once(self.path, 'tasks', 'acceptance_ready', suffix='.pre-0.283.0')
        self.quality_prepare = None
        self.quality_prepare_task = None
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
                    not_before REAL NOT NULL DEFAULT 0,
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
            # Cột thêm sau khi kho đã có trên máy người dùng. `not_before` (0.59.44): việc vấp
            # "gói thuê bao hết lượt" được hoãn tới mốc reset; dispatcher bỏ qua việc chưa tới
            # giờ thay vì nhặt lại sau 5 giây rồi đốt hết lượt thử trước khi hạn mức mở lại.
            cot = {r["name"] for r in self._db.execute("PRAGMA table_info(tasks)").fetchall()}
            if "not_before" not in cot:
                self._db.execute(
                    "ALTER TABLE tasks ADD COLUMN not_before REAL NOT NULL DEFAULT 0"
                )
            # Làn `team` (0.140.0, nhóm chat): việc nhóm là dòng `tasks` với lane='team' và trạng
            # thái riêng `team_*`, nên next_candidate/reclaim_stale của Kanban (kể cả bản cũ khi hạ
            # phiên bản) không bao giờ nhặt. `team_prio` để null = việc thường.
            for name, decl in _TEAM_COLUMNS:
                if name not in cot:
                    self._db.execute(f"ALTER TABLE tasks ADD COLUMN {name} {decl}")
            self._db.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_tasks_team_queue
                    ON tasks(team_id, status, team_prio, team_seq) WHERE lane='team';
                CREATE TABLE IF NOT EXISTS team_queues (
                    team_id TEXT PRIMARY KEY,
                    version INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS team_quality_required(team_id TEXT PRIMARY KEY, enabled INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS team_acceptance_applied(
                    task_id TEXT NOT NULL, decision_key TEXT NOT NULL, revision INTEGER NOT NULL,
                    PRIMARY KEY(task_id,decision_key));
                -- 0.411.0: "this job keeps coming back" hints the owner dismissed, per brain.
                CREATE TABLE IF NOT EXISTS board_hints_dismissed(
                    brain_root TEXT NOT NULL, hint_key TEXT NOT NULL, created_at REAL NOT NULL,
                    PRIMARY KEY(brain_root, hint_key));
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
        dedupe_title: bool = True,
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
                if normalized and dedupe_title:
                    row = self._db.execute(
                        f"""SELECT id FROM tasks
                            WHERE brain_root=? AND normalized_title=? AND lane<>'team'
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

    def _task_from_row(self, row: sqlite3.Row, deps: Optional[list] = None) -> dict:
        task = dict(row)
        task["needs_approval"] = bool(task.get("needs_approval"))
        task["metadata"] = _loads(task.pop("metadata_json", "{}"), {})
        task["artifacts"] = _loads(task.pop("artifacts_json", "[]"), [])
        if deps is not None:
            task["deps"] = deps
            return task
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
        sql = "SELECT * FROM tasks WHERE brain_root=? AND lane<>'team'"
        args: list[Any] = [brain_root]
        if not include_archived:
            sql += " AND status <> 'archived'"
        sql += " ORDER BY priority, created_at LIMIT ?"
        args.append(max(1, min(5000, int(limit))))
        with self._lock:
            rows = self._db.execute(sql, args).fetchall()
        return [self._task_from_row(r) for r in rows]

    def board_lists(self, brain_root: str, history_limit: int = 20, cap: int = 500) -> dict:
        """What the Work page shows, in a handful of queries (0.411.0).

        `list_tasks` sorted everything by priority then age and cut at 500, then ran one dependency query per task.
        On a busy brain that hid NEW jobs behind 500 old finished ones, showed the 20 OLDEST finished jobs as
        History, and cost 500 queries per 3-second poll. Open jobs and history are now separate queries, history
        newest first with its own limit, and dependencies come in one query."""
        root = str(brain_root)
        open_status = sorted(ACTIVE_STATUS)
        hist = max(1, min(500, int(history_limit or 20)))
        with self._lock:
            open_rows = self._db.execute(
                f"""SELECT * FROM tasks WHERE brain_root=? AND lane<>'team'
                    AND status IN ({','.join('?' for _ in open_status)})
                    ORDER BY priority, created_at LIMIT ?""",
                (root, *open_status, max(1, int(cap))),
            ).fetchall()
            hist_rows = self._db.execute(
                """SELECT * FROM tasks WHERE brain_root=? AND lane<>'team'
                   AND status IN ('done', 'cancelled')
                   ORDER BY updated_at DESC LIMIT ?""",
                (root, hist + 1),
            ).fetchall()
            counts = {r["status"]: int(r["n"]) for r in self._db.execute(
                """SELECT status, COUNT(*) AS n FROM tasks WHERE brain_root=? AND lane<>'team'
                   GROUP BY status""", (root,)).fetchall()}
            ids = [r["id"] for r in open_rows] + [r["id"] for r in hist_rows[:hist]]
            deps: dict[str, list] = {i: [] for i in ids}
            for start in range(0, len(ids), 500):
                chunk = ids[start:start + 500]
                for d in self._db.execute(
                    f"""SELECT task_id, depends_on_id FROM task_dependencies
                        WHERE task_id IN ({','.join('?' for _ in chunk)}) ORDER BY depends_on_id""",
                    chunk,
                ).fetchall():
                    deps[d["task_id"]].append(str(d["depends_on_id"]))
        return {
            "open": [self._task_from_row(r, deps[r["id"]]) for r in open_rows],
            "history": [self._task_from_row(r, deps[r["id"]]) for r in hist_rows[:hist]],
            "history_more": len(hist_rows) > hist,
            "counts": counts,
        }

    def board_rev(self, brain_root: str) -> str:
        """A cheap fingerprint of a brain's board: any added, removed or changed job, or a mode switch, changes it."""
        root = str(brain_root)
        with self._lock:
            row = self._db.execute(
                """SELECT COUNT(*) AS n, COALESCE(MAX(updated_at), 0) AS u FROM tasks
                   WHERE brain_root=? AND lane<>'team'""", (root,)).fetchone()
            board = self._db.execute(
                "SELECT orchestration, updated_at FROM boards WHERE brain_root=?", (root,)).fetchone()
        b = f"{board['orchestration']}:{board['updated_at']}" if board else ""
        return f"{int(row['n'])}:{float(row['u']):.6f}:{b}"

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

    def list_events_bulk(self, task_ids: list[str], limit: int = 20) -> dict[str, list[dict]]:
        """{task_id: [event, ...]} cho NHIỀU task trong một truy vấn thay vì N+1.

        _snapshot của Kanban trước đây lấy list_tasks(limit=5000) rồi gọi list_events cho
        TỪNG task - đúng khuôn N+1, chi phí tăng tuyến tính theo số việc trên bảng, mà nó
        chạy sau mỗi lần giao việc, mỗi lần worker xong và mỗi nhịp dọn dẹp.

        Cắt theo lô 500 id: SQLite bản mới cho tới 32.766 tham số nhưng bản cũ chỉ 999,
        mà kho này chạy trên cả máy người dùng lẫn image Docker nên đừng đoán.
        Thứ tự trong mỗi task giữ nguyên như list_events: cũ -> mới.
        """
        out: dict[str, list[dict]] = {tid: [] for tid in task_ids}
        if not task_ids:
            return out
        lim = max(1, min(500, int(limit)))
        with self._lock:
            for i in range(0, len(task_ids), 500):
                lo = task_ids[i:i + 500]
                marks = ",".join("?" * len(lo))
                rows = self._db.execute(
                    f"""SELECT * FROM (
                            SELECT *, ROW_NUMBER() OVER (PARTITION BY task_id ORDER BY id DESC) AS _rn
                            FROM task_events WHERE task_id IN ({marks})
                        ) WHERE _rn <= ?
                        ORDER BY task_id, id ASC""",
                    (*lo, lim),
                ).fetchall()
                for row in rows:
                    value = dict(row)
                    value.pop("_rn", None)
                    value["metadata"] = _loads(value.pop("metadata_json", "{}"), {})
                    out.setdefault(value["task_id"], []).append(value)
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

    def waiting_on(self, task_id: str) -> list[dict]:
        """Tasks still in `todo` because they depend on `task_id`.

        A blocked parent never reaches `done`, so its dependents sit in Todo forever with no
        event of their own. The blocked-task report lists them so the owner knows that fixing
        this one task also unblocks those."""
        with self._lock:
            rows = self._db.execute(
                """
                SELECT t.id, t.title FROM task_dependencies d
                JOIN tasks t ON t.id=d.task_id
                WHERE d.depends_on_id=? AND t.status='todo'
                ORDER BY t.created_at
                """,
                (task_id,),
            ).fetchall()
        return [{"id": str(r["id"]), "title": str(r["title"])} for r in rows]

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

    def archive_old_terminal(self, brain_root: str, age_days: float = 3.0) -> int:
        """Tự dọn bảng: task đã kết thúc (done/cancelled) quá age_days thì chuyển archived.

        Việc một-lần xong rồi không nằm mãi trên bảng Việc; archived chỉ bị ẨN
        (list_tasks mặc định lọc ra), lịch sử vẫn tra được với include_archived=True.
        Chạy trong housekeep mỗi vòng dispatch nên phải idempotent và rẻ."""
        ts = now()
        cutoff = ts - age_days * 86400
        with self._lock:
            self._tx()
            try:
                rows = self._db.execute(
                    """SELECT id, status FROM tasks
                       WHERE brain_root=? AND status IN ('done','cancelled')
                         AND updated_at < ? AND lane<>'team'""",
                    (brain_root, cutoff),
                ).fetchall()
                for row in rows:
                    tid = str(row["id"])
                    self._db.execute(
                        "UPDATE tasks SET status='archived', updated_at=? WHERE id=?",
                        (ts, tid),
                    )
                    self._event(
                        tid, "auto_archive",
                        f"{row['status']} -> archived: đã kết thúc quá {age_days:g} ngày",
                    )
                self._db.commit()
                return len(rows)
            except Exception:
                self._db.rollback()
                raise

    # Chỉ những trạng thái đã KẾT THÚC mới được xoá. Whitelist cứng để một lời gọi sai
    # tham số không thể quét mất việc đang chờ hay đang chạy.
    _PURGEABLE = ("archived", "cancelled", "done")

    def purge_terminal(
        self, brain_root: str, statuses: tuple = ("archived", "cancelled")
    ) -> int:
        """XOÁ HẲN task đã kết thúc khỏi kho (kèm event/run/dependency). Trả số đã xoá.

        Khác archive_old_terminal (chỉ ẩn khỏi bảng, vẫn tra được): đây là dọn thật, dùng
        khi bảng đầy việc rác không còn giá trị tra cứu. Mặc định giữ 'done' vì đó là lịch
        sử việc Javis làm được; muốn dọn cả thì truyền statuses vào."""
        allowed = tuple(s for s in statuses if s in self._PURGEABLE)
        if not allowed:
            return 0
        marks = ",".join("?" for _ in allowed)
        with self._lock:
            self._tx()
            try:
                rows = self._db.execute(
                    f"SELECT id FROM tasks WHERE brain_root=? AND status IN ({marks}) AND lane<>'team'",
                    (brain_root, *allowed),
                ).fetchall()
                ids = [str(r["id"]) for r in rows]
                for tid in ids:
                    self._db.execute("DELETE FROM task_events WHERE task_id=?", (tid,))
                    self._db.execute("DELETE FROM task_runs WHERE task_id=?", (tid,))
                    self._db.execute(
                        "DELETE FROM task_dependencies WHERE task_id=? OR depends_on_id=?",
                        (tid, tid),
                    )
                    self._db.execute("DELETE FROM tasks WHERE id=?", (tid,))
                self._db.commit()
                return len(ids)
            except Exception:
                self._db.rollback()
                raise

    def clear_board(self, brain_root: str) -> int:
        """XOÁ TRẮNG bảng: mọi việc của brain này, TRỪ việc đang có worker cầm.

        Khác purge_terminal (chỉ đụng việc đã kết thúc): đây là lệnh dứt khoát của chủ khi
        cả bảng không còn giá trị. Giữ lại 'running' vì xoá task trong lúc worker còn chạy
        sẽ để lại worker mồ côi ghi vào một task không còn tồn tại."""
        with self._lock:
            self._tx()
            try:
                rows = self._db.execute(
                    "SELECT id FROM tasks WHERE brain_root=? AND status<>'running' AND lane<>'team'",
                    (brain_root,),
                ).fetchall()
                ids = [str(r["id"]) for r in rows]
                for tid in ids:
                    self._db.execute("DELETE FROM task_events WHERE task_id=?", (tid,))
                    self._db.execute("DELETE FROM task_runs WHERE task_id=?", (tid,))
                    self._db.execute(
                        "DELETE FROM task_dependencies WHERE task_id=? OR depends_on_id=?",
                        (tid, tid),
                    )
                    self._db.execute("DELETE FROM tasks WHERE id=?", (tid,))
                self._db.commit()
                return len(ids)
            except Exception:
                self._db.rollback()
                raise

    # 0.411.0: a stopped job only the owner can move on (a question, a permission, a result to approve), as opposed
    # to one Javis handles itself (technical hitch, usage limit). The Work page and the notices split on this.
    OWNER_BLOCK_KINDS = ("needs_input", "capability")

    @classmethod
    def waits_for_owner(cls, task: dict) -> bool:
        st = str(task.get("status") or "")
        return st == "review" or (st == "blocked" and str(task.get("block_kind") or "") in cls.OWNER_BLOCK_KINDS)

    def archive_attention(self, brain_root: str, owner: bool) -> int:
        """Wipe one of the two stopped-job areas: `owner=True` the "Javis is asking you" area (review + owner
        kinds), False the "Javis is handling it" area (every other blocked job). Same rules as archive_by_status."""
        with self._lock:
            rows = self._db.execute(
                """SELECT id, status, block_kind FROM tasks WHERE brain_root=? AND lane<>'team'
                   AND status IN ('blocked', 'review')""", (brain_root,)).fetchall()
        ids = [str(r["id"]) for r in rows if self.waits_for_owner(dict(r)) == bool(owner)]
        if not ids:
            return 0
        with self._lock:
            self._tx()
            try:
                ts = now()
                for tid in ids:
                    self._db.execute(
                        """UPDATE tasks SET status='archived', block_kind='', block_reason='',
                           claimed_by='', claim_expires_at=0, current_run_id='', updated_at=?
                           WHERE id=? AND status IN ('blocked', 'review')""",
                        (ts, tid),
                    )
                    self._event(tid, "operator_move", "-> archived: xoá tất cả")
                self._db.commit()
            except Exception:
                self._db.rollback()
                raise
        return len(ids)

    def archive_by_status(self, brain_root: str, statuses: tuple) -> int:
        """Đẩy MỌI việc đang ở các trạng thái này sang `archived`. Trả số việc đã dọn.

        Dùng cho nút "Xoá tất cả" của bảng Cần bạn xử lý. Cố ý ARCHIVE chứ không xoá hẳn -
        giống hệt nút "Xoá khỏi bảng" của từng dòng, nên hai lối cùng một hậu quả và việc vẫn
        tra lại được. Việc đang chạy KHÔNG bị đụng: xoá task trong lúc worker còn cầm là để
        lại một worker mồ côi ghi vào bản ghi không còn tồn tại.
        """
        allowed = tuple(s for s in statuses if s in VALID_STATUS and s != "running")
        if not allowed:
            return 0
        marks = ",".join("?" for _ in allowed)
        with self._lock:
            self._tx()
            try:
                rows = self._db.execute(
                    f"SELECT id FROM tasks WHERE brain_root=? AND status IN ({marks}) AND lane<>'team'",
                    (brain_root, *allowed),
                ).fetchall()
                ids = [str(r["id"]) for r in rows]
                ts = now()
                for tid in ids:
                    self._db.execute(
                        """UPDATE tasks SET status='archived', block_kind='', block_reason='',
                           claimed_by='', claim_expires_at=0, current_run_id='', updated_at=?
                           WHERE id=?""",
                        (ts, tid),
                    )
                    self._event(tid, "operator_move", "-> archived: xoá tất cả")
                self._db.commit()
                return len(ids)
            except Exception:
                self._db.rollback()
                raise

    def grant_full(self, task_id: str, reason: str = "operator grant") -> bool:
        """Chủ CẤP QUYỀN toàn quyền cho một việc rồi đưa nó chạy lại. Trả False nếu không được.

        Đây là nửa còn thiếu của thiết kế cũ. Specifier được dặn thẳng trong prompt là gặp việc
        cần thao tác ra ngoài thì "để kernel chặn và xin quyền" - nhưng chưa từng có đường nào
        để XIN, nên việc nằm mãi ở cột Cần bạn xử lý với một câu tiếng máy, còn nút Thử lại thì
        chạy lại đúng nhánh chặn ấy rồi chặn lại y hệt.

        Ghi một sự kiện riêng (`operator_grant`) chứ không dùng chung `operator_move`: đây là
        lần một con người mở khoá cho việc tự thao tác thật ra ngoài, thứ không hoàn tác được,
        nên nó phải đọc ra được trong nhật ký vòng đời.
        """
        with self._lock:
            self._tx()
            try:
                row = self._db.execute(
                    "SELECT status FROM tasks WHERE id=? AND lane<>'team'", (task_id,)
                ).fetchone()
                if not row or row["status"] == "running":
                    self._db.rollback()
                    return False
                self._db.execute(
                    """UPDATE tasks SET status='ready', execution_mode='full',
                       block_kind='', block_reason='', attempts=0,
                       claimed_by='', claim_expires_at=0, current_run_id='', updated_at=?
                       WHERE id=?""",
                    (now(), task_id),
                )
                self._event(task_id, "operator_grant",
                            f"{row['status']} -> ready, mức quyền = full: {reason}")
                self._db.commit()
                return True
            except Exception:
                self._db.rollback()
                raise

    def next_candidate(self, brain_root: str) -> Optional[dict]:
        with self._lock:
            # Trợ lý đang chạy một việc giao trực tiếp thì việc kế của CÙNG trợ lý đứng chờ; việc khác vẫn đi tiếp
            # (không bỏ đói ai), và việc của trợ lý đó vẫn theo đúng thứ tự (FIFO trong cùng ưu tiên).
            busy = {
                agent_prefix(r["idempotency_key"])
                for r in self._db.execute(
                    """SELECT idempotency_key FROM tasks
                       WHERE brain_root=? AND status='running' AND idempotency_key LIKE 'agent:%'""",
                    (brain_root,),
                ).fetchall()
            }
            busy.discard("")
            # `not_before`: việc đang đợi gói thuê bao mở lại hạn mức chưa tới giờ thì
            # không phải ứng viên, dù status vẫn là ready.
            cur = self._db.execute(
                """SELECT * FROM tasks
                   WHERE brain_root=? AND status IN ('triage','ready')
                     AND not_before <= ?
                   ORDER BY CASE status WHEN 'triage' THEN 0 ELSE 1 END,
                            priority, created_at""",
                (brain_root, now()),
            )
            row = None
            for r in cur:
                if busy and agent_prefix(r["idempotency_key"]) in busy:
                    continue
                row = r
                break
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
                ap = agent_prefix(row["idempotency_key"])
                if ap and self._db.execute(
                    """SELECT 1 FROM tasks WHERE brain_root=? AND status='running' AND id<>?
                       AND substr(idempotency_key, 1, ?)=? LIMIT 1""",
                    (str(row["brain_root"]), task_id, len(ap), ap),
                ).fetchone():
                    # Cùng trợ lý đang chạy một việc giao trực tiếp: việc này chờ tới lượt (kiểm trong giao dịch nhận
                    # việc, nên hai đường nhận song song cũng không mở hai lượt cho một trợ lý).
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
                           claim_expires_at=?, not_before=0, last_heartbeat_at=?,
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
        not_before: float = 0.0,
        keep_attempt: bool = False,
    ) -> Optional[dict]:
        """`not_before`: mốc epoch trước đó dispatcher không nhặt lại việc (hoãn vì hết hạn mức).
        `keep_attempt`: trả lại lượt thử mà `claim` vừa cộng - lượt vấp hạn mức không phải lỗi
        của việc, tính nó là ba lần vấp cùng một cửa sổ hết lượt là việc chết oan."""
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
                           claim_expires_at=0, not_before=?, last_heartbeat_at=?,
                           current_run_id='', updated_at=?
                       WHERE id=?""",
                    (
                        status, (result or "")[:20000], block_kind or "",
                        (block_reason or "")[:2000], _json(metadata or {}),
                        _json(artifacts or []), float(not_before or 0.0), ts, ts, task_id,
                    ),
                )
                if keep_attempt:
                    self._db.execute(
                        """UPDATE tasks
                           SET attempts=CASE WHEN attempts > 0 THEN attempts - 1 ELSE 0 END
                           WHERE id=?""",
                        (task_id,),
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
        not_before: float = 0.0,
        keep_attempt: bool = False,
    ) -> Optional[dict]:
        """`transient=True` -> về ready để thử lại (còn lượt). `not_before` hoãn lần thử tới
        mốc đó; `keep_attempt` không tính lần vấp này vào `attempts` (hết hạn mức gói thuê bao
        đã biết giờ mở lại: đợi đúng giờ rồi thử là chắc ăn, không có lý do gì để đốt lượt)."""
        task = self.get_task(task_id)
        if not task:
            return None
        con_luot = keep_attempt or int(task["attempts"]) < int(task["max_attempts"])
        retry = bool(transient and con_luot)
        # GIỮ metadata (điều kiện hoàn thành do specifier viết) và artifacts: `_finish` ghi đè
        # cột bằng thứ được truyền, bản trước không truyền gì nên mỗi lần chặn/thử lại là việc
        # chạy lại với "ĐIỀU KIỆN HOÀN THÀNH: []".
        return self._finish(
            task_id, worker_id, "ready" if retry else "blocked",
            result=result, error=reason, block_kind=kind,
            block_reason=reason, event_type="retry_scheduled" if retry else "blocked",
            metadata=task.get("metadata") or {}, artifacts=task.get("artifacts") or [],
            not_before=float(not_before or 0.0) if retry else 0.0,
            keep_attempt=bool(keep_attempt and retry),
        )

    def ask(
        self, task_id: str, worker_id: str, question: str, result: str = "",
        extra_meta: Optional[dict] = None,
    ) -> Optional[dict]:
        """Chặn việc ở `needs_input` VÀ ghi câu hỏi vào `metadata.qa` (0.235.0).

        Trước đây câu hỏi chỉ nằm lẫn trong `block_reason`, và đường duy nhất để gỡ là Thử lại:
        việc chạy lại từ đầu mà không ai nói cho nó câu trả lời, nên nó hỏi lại y hệt. Giờ mỗi
        lần hỏi là một mục `{q, asked_at, progress}`; `answer` điền `a` vào mục đó, và lần chạy
        sau đọc cả sổ (ý tưởng `ask_user` của OpenMuse). `progress` là đầu bản tường thuật của
        lần chạy vừa dừng, để lần sau biết phần nào đã làm xong."""
        task = self.get_task(task_id)
        if not task:
            return None
        meta = dict(task.get("metadata") or {})
        qa = [x for x in (meta.get("qa") or []) if isinstance(x, dict)]
        qa.append({
            "q": (question or "").strip()[:QA_TEXT_MAX],
            "asked_at": now(),
            "progress": (result or "").strip()[:QA_PROGRESS_MAX],
        })
        meta["qa"] = qa[-QA_KEEP:]
        meta.update(extra_meta or {})
        return self._finish(
            task_id, worker_id, "blocked",
            result=result, error=question, block_kind="needs_input",
            block_reason=question, event_type="blocked",
            metadata=meta, artifacts=task.get("artifacts") or [],
        )

    def answer(self, task_id: str, text: str, by: str = "owner") -> tuple[Optional[dict], str]:
        """Chủ trả lời việc đang chờ ở `needs_input`: điền câu trả lời rồi đưa việc về `ready`.

        Trả (task, "") khi xong, (None, mã lỗi) khi không: "not_found", "empty", "not_waiting".
        TRẢ LẠI lượt thử mà lần chạy vừa hỏi đã tiêu: hỏi người không phải là việc hỏng, tính
        nó thì việc hỏi ba câu là chết vì hết lượt dù chưa hỏng lần nào."""
        text = (text or "").strip()
        if not text:
            return None, "empty"
        with self._lock:
            self._tx()
            try:
                row = self._db.execute(
                    "SELECT * FROM tasks WHERE id=? AND lane<>'team'", (task_id,)
                ).fetchone()
                if not row:
                    self._db.rollback()
                    return None, "not_found"
                if row["status"] != "blocked" or row["block_kind"] != "needs_input":
                    self._db.rollback()
                    return None, "not_waiting"
                meta = _loads(row["metadata_json"], {})
                qa = [x for x in (meta.get("qa") or []) if isinstance(x, dict)]
                if not qa or qa[-1].get("a"):
                    # Việc kẹt từ trước bản này: câu hỏi chỉ còn trong block_reason.
                    qa.append({"q": str(row["block_reason"] or "")[:QA_TEXT_MAX],
                               "asked_at": float(row["updated_at"] or now())})
                qa[-1].update({"a": text[:QA_TEXT_MAX], "answered_at": now(), "by": by})
                meta["qa"] = qa[-QA_KEEP:]
                meta.pop("once_pending", None)     # câu hỏi "đã gửi chưa" (0.238.0) đã có lời đáp
                self._db.execute(
                    """UPDATE tasks SET status='ready', block_kind='', block_reason='',
                       attempts=CASE WHEN attempts > 0 THEN attempts - 1 ELSE 0 END,
                       metadata_json=?, claimed_by='', claim_expires_at=0, not_before=0,
                       current_run_id='', updated_at=?
                       WHERE id=?""",
                    (_json(meta), now(), task_id),
                )
                self._event(task_id, "answered", text[:500], metadata={"by": by})
                self._db.commit()
            except Exception:
                self._db.rollback()
                raise
        return self.get_task(task_id), ""

    # A follow-up can be sent to any job that is not running and not already waiting for an answer (that one goes
    # through `answer`). Finished jobs included: "make paragraph 2 shorter" on a done job is the common case.
    FOLLOWUP_STATUS = ("blocked", "review", "done", "cancelled", "triage", "todo", "ready")

    def followup(self, task_id: str, text: str, by: str = "owner") -> tuple[Optional[dict], str]:
        """The owner's extra instruction for a job, then back to the queue (0.411.0).

        Before this the only way to change a stopped or finished job was Retry, which ran it again unchanged. The
        note joins the job's Q&A log as an answered entry, with the last report as `progress`, so the next run
        (`TasksFeature._hoi_dap`) builds on the earlier work instead of starting over, and does not resend what
        was already sent. Attempts start fresh: this is a new instruction, not another try at the old one.
        Returns (task, "") or (None, "empty" | "not_found" | "running" | "waiting")."""
        text = (text or "").strip()
        if not text:
            return None, "empty"
        with self._lock:
            self._tx()
            try:
                row = self._db.execute(
                    "SELECT * FROM tasks WHERE id=? AND lane<>'team'", (task_id,)
                ).fetchone()
                if not row:
                    self._db.rollback()
                    return None, "not_found"
                if row["status"] == "running":
                    self._db.rollback()
                    return None, "running"
                if row["status"] == "blocked" and row["block_kind"] == "needs_input":
                    self._db.rollback()
                    return None, "waiting"
                if row["status"] not in self.FOLLOWUP_STATUS:
                    self._db.rollback()
                    return None, "not_found"
                meta = _loads(row["metadata_json"], {})
                qa = [x for x in (meta.get("qa") or []) if isinstance(x, dict)]
                qa.append({
                    "q": "Chủ nhắn thêm cho việc này",
                    "a": text[:QA_TEXT_MAX], "kind": "followup", "by": by,
                    "asked_at": now(), "answered_at": now(),
                    "progress": str(row["result"] or "").strip()[:QA_PROGRESS_MAX],
                })
                meta["qa"] = qa[-QA_KEEP:]
                meta.pop("once_pending", None)
                if meta.get("acceptance_check") in ("unverified", "checking"):
                    meta.pop("acceptance_check", None)
                self._db.execute(
                    """UPDATE tasks SET status='ready', block_kind='', block_reason='', attempts=0,
                       metadata_json=?, claimed_by='', claim_expires_at=0, not_before=0,
                       current_run_id='', updated_at=?
                       WHERE id=?""",
                    (_json(meta), now(), task_id),
                )
                self._event(task_id, "followup", text[:500], metadata={"by": by, "from": row["status"]})
                self._db.commit()
            except Exception:
                self._db.rollback()
                raise
        return self.get_task(task_id), ""

    def set_acceptance(self, task_id: str, state: str, why: str = "") -> Optional[dict]:
        """Record a re-check of a finished job (0.411.0). `state`: "checking" while it runs, "ai" when it passed,
        "failed" when it did not (the job moves to Needs you with the reason as its question, so the reply box can
        fix it), "unverified" when the checker could not run again. Only a done or review job is touched."""
        with self._lock:
            self._tx()
            try:
                row = self._db.execute(
                    "SELECT status, metadata_json FROM tasks WHERE id=? AND lane<>'team'", (task_id,)
                ).fetchone()
                if not row or row["status"] not in ("done", "review"):
                    self._db.rollback()
                    return None
                meta = _loads(row["metadata_json"], {})
                if state == "failed":
                    reason = ("Chưa đạt điều kiện hoàn thành: " + (why or "lượt kiểm không nói rõ."))[:QA_TEXT_MAX]
                    qa = [x for x in (meta.get("qa") or []) if isinstance(x, dict)]
                    qa.append({"q": reason, "asked_at": now()})
                    meta["qa"] = qa[-QA_KEEP:]
                    meta["acceptance_check"] = "failed"
                    self._db.execute(
                        """UPDATE tasks SET status='blocked', block_kind='needs_input', block_reason=?,
                           metadata_json=?, updated_at=? WHERE id=?""",
                        (reason, _json(meta), now(), task_id),
                    )
                    self._event(task_id, "acceptance_failed", reason[:500])
                else:
                    meta["acceptance_check"] = state
                    self._db.execute("UPDATE tasks SET metadata_json=?, updated_at=? WHERE id=?",
                                     (_json(meta), now(), task_id))
                    if state != "checking":
                        self._event(task_id, "acceptance_" + state, why[:500])
                self._db.commit()
            except Exception:
                self._db.rollback()
                raise
        return self.get_task(task_id)

    # Repeat-job hints (0.411.0): a job the owner keeps asking for by hand is a reminder or a workflow waiting to
    # happen. Only jobs a person asked for count; assistants, teams and schedules already run on their own.
    HINT_SOURCES = ("user", "chat", "voice")
    HINT_MIN_COUNT = 3
    HINT_WINDOW_DAYS = 60
    HINT_SCAN = 300

    @staticmethod
    def hint_words(title: str) -> frozenset:
        """Words of a title with numbers dropped: "Báo cáo doanh thu 28/10" and "... 4/11" are the same job."""
        return frozenset(w for w in norm_title(title).split() if not any(c.isdigit() for c in w) and len(w) > 1)

    def repeat_hints(self, brain_root: str, limit: int = 3) -> list[dict]:
        root = str(brain_root)
        since = now() - self.HINT_WINDOW_DAYS * 86400
        with self._lock:
            rows = self._db.execute(
                f"""SELECT id, title, intent, created_at FROM tasks
                    WHERE brain_root=? AND lane<>'team' AND created_at>=?
                      AND created_by IN ({','.join('?' for _ in self.HINT_SOURCES)})
                    ORDER BY created_at DESC LIMIT ?""",
                (root, since, *self.HINT_SOURCES, self.HINT_SCAN),
            ).fetchall()
            dismissed = {r["hint_key"] for r in self._db.execute(
                "SELECT hint_key FROM board_hints_dismissed WHERE brain_root=?", (root,)).fetchall()}
        groups: list[dict] = []
        for r in rows:
            words = self.hint_words(r["title"])
            if len(words) < 2:
                continue
            for g in groups:
                inter = len(words & g["words"])
                if inter and inter / len(words | g["words"]) >= 0.7:
                    g["count"] += 1
                    break
            else:
                groups.append({"words": words, "count": 1, "title": r["title"], "intent": r["intent"],
                               "task_id": r["id"], "last_at": float(r["created_at"])})
        out = []
        for g in groups:
            key = " ".join(sorted(g["words"]))
            if g["count"] >= self.HINT_MIN_COUNT and key not in dismissed:
                out.append({"key": key, "count": g["count"], "title": g["title"],
                            "intent": str(g["intent"] or "")[:600], "task_id": g["task_id"],
                            "last_at": g["last_at"]})
        out.sort(key=lambda h: (-h["count"], -h["last_at"]))
        return out[:limit]

    def dismiss_hint(self, brain_root: str, hint_key: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO board_hints_dismissed(brain_root, hint_key, created_at) VALUES (?, ?, ?)",
                (str(brain_root), str(hint_key)[:500], now()))
            self._db.commit()

    def move(self, task_id: str, status: str, reason: str = "operator") -> bool:
        if status not in VALID_STATUS:
            return False
        with self._lock:
            self._tx()
            try:
                row = self._db.execute(
                    "SELECT status FROM tasks WHERE id=? AND lane<>'team'", (task_id,)
                ).fetchone()
                if not row:
                    self._db.rollback()
                    return False
                if row["status"] == "running":
                    self._db.rollback()
                    return False
                # Người dùng tự kéo việc: bỏ luôn mốc hoãn (họ muốn chạy NGAY, kể cả khi
                # Javis đang đợi gói thuê bao mở lại).
                self._db.execute(
                    """UPDATE tasks SET status=?, block_kind='', block_reason='',
                       claimed_by='', claim_expires_at=0, not_before=0, current_run_id='',
                       updated_at=?
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

    # ---- Làn `team` (nhóm chat, spec 2026-10-13-team-chat-design mục 5.4 và 8) ----
    #
    # Mỗi thao tác đổi hàng đợi tăng `team_queues.version` trong CÙNG giao dịch với thay đổi,
    # kể cả bước điều phối nhận việc. Lệnh của chủ mang `expected_version`; sai thì 409 kèm hàng
    # mới, nên hai tab cùng bấm hay điều phối vừa nhận việc đều không tạo trạng thái lạ.

    def _bump_queue(self, team_id: str) -> None:
        self._db.execute(
            """INSERT INTO team_queues(team_id, version) VALUES (?, 1)
               ON CONFLICT(team_id) DO UPDATE SET version=version+1""",
            (team_id,),
        )

    def _queue_version(self, team_id: str) -> int:
        row = self._db.execute(
            "SELECT version FROM team_queues WHERE team_id=?", (team_id,)
        ).fetchone()
        return int(row["version"]) if row else 0

    def _team_row(self, task_id: str) -> Optional[sqlite3.Row]:
        return self._db.execute(
            "SELECT * FROM tasks WHERE id=? AND lane='team'", (task_id,)
        ).fetchone()

    def enqueue_team(
        self, brain_root: str, team_id: str, title: str, intent: str, source_ref: str,
        assignee_key: str = '', coordinator_key: str = '', chat_id: str = '', created_by: str = 'owner',
        blocked_kind: str = '', blocked_reason: str = '',
    ) -> tuple[str, bool]:
        result = self._enqueue_team_record(brain_root, team_id, title, intent, source_ref, assignee_key,
            coordinator_key, chat_id, created_by, blocked_kind, blocked_reason)
        if self.quality_prepare_task:
            self.quality_prepare_task(result[0])
        return result

    def _enqueue_team_record(
        self,
        brain_root: str,
        team_id: str,
        title: str,
        intent: str,
        source_ref: str,
        assignee_key: str = "",
        coordinator_key: str = "",
        chat_id: str = "",
        created_by: str = "owner",
        blocked_kind: str = "",
        blocked_reason: str = "",
    ) -> tuple[str, bool]:
        """Thêm một việc nhóm vào cuối hàng. Trả (task_id, created).

        `blocked_kind` (0.208.0): the job is created already stopped (e.g. `waiting_user` for a job the department
        mandate opens at the approve level), in the same transaction, so no crash or error can leave it runnable.

        Khoá idempotency là `source_ref` (tin giao việc): gửi lại cùng tin trả việc cũ. KHÔNG gộp
        theo tiêu đề như Kanban: hai việc khác nhau cùng tên vẫn là hai việc."""
        root = str(brain_root)
        team_id = str(team_id or "").strip()
        source_ref = str(source_ref or "").strip()
        if not team_id or not source_ref:
            raise QueueError("team_id_and_source_ref_required")
        self.ensure_board(root)
        title = (title or intent or "Việc nhóm")[:160]
        key = f"team:{team_id}:{source_ref}"
        ts = now()
        with self._lock:
            self._tx()
            try:
                row = self._db.execute(
                    "SELECT id FROM tasks WHERE brain_root=? AND idempotency_key=? LIMIT 1",
                    (root, key),
                ).fetchone()
                if row:
                    self._db.commit()
                    return str(row["id"]), False
                seq = int(self._db.execute(
                    "SELECT COALESCE(MAX(team_seq), 0) AS m FROM tasks WHERE lane='team' AND team_id=?",
                    (team_id,),
                ).fetchone()["m"]) + 1
                tid = "t_" + uuid.uuid4().hex[:12]
                self._db.execute(
                    """INSERT INTO tasks (
                        id, brain_root, title, normalized_title, intent, route, capability,
                        execution_mode, priority, status, created_by, chat_id, idempotency_key,
                        max_attempts, created_at, updated_at, lane, team_id, team_seq, team_prio,
                        team_rev, assignee_key, coordinator_key, source_ref, block_kind, block_reason
                    ) VALUES (?, ?, ?, ?, ?, 'team', 'auto', 'auto', 2, ?, ?, ?, ?, 1,
                              ?, ?, 'team', ?, ?, NULL, 1, ?, ?, ?, ?, ?)""",
                    (
                        tid, root, title, norm_title(title), intent or title,
                        "team_blocked" if blocked_kind else "team_queued", created_by or "owner",
                        str(chat_id or ""), key, ts, ts, team_id, seq, assignee_key or "",
                        coordinator_key or "", source_ref, str(blocked_kind or ""), str(blocked_reason or "")[:2000],
                    ),
                )
                self._event(tid, "team_queued", f"team {team_id} #{seq}", metadata={"source_ref": source_ref})
                self._bump_queue(team_id)
                self._db.commit()
                return tid, True
            except Exception:
                self._db.rollback()
                raise

    def _team_queue_locked(self, team_id: str) -> dict:
        rows = self._db.execute(
            f"""SELECT * FROM tasks WHERE lane='team' AND team_id=?
                  AND status IN ('team_queued','team_running','team_blocked')
                ORDER BY {_TEAM_ORDER}""",
            (team_id,),
        ).fetchall()
        out: dict[str, Any] = {"team_id": team_id, "version": self._queue_version(team_id),
                               "running": [], "waiting": [], "blocked": []}
        bucket = {"team_running": "running", "team_queued": "waiting", "team_blocked": "blocked"}
        for row in rows:
            task = dict(row)
            task["metadata"] = _loads(task.pop("metadata_json", "{}"), {})
            task["artifacts"] = _loads(task.pop("artifacts_json", "[]"), [])
            out[bucket[str(row["status"])]].append(task)
        return out

    def team_queue(self, team_id: str) -> dict:
        """Hàng đợi của một nhóm: {version, running, waiting, blocked}; `waiting` theo thứ tự chạy."""
        with self._lock:
            return self._team_queue_locked(str(team_id))

    def team_priority(self, task_id: str, prioritize: bool, expected_version: int) -> dict:
        """Ưu tiên / bỏ ưu tiên một việc đang chờ (hay bị chặn). Trả hàng đợi mới.

        Ưu tiên: `team_prio = max + 1`, nên nhiều việc ưu tiên chạy theo thứ tự được bấm. Bấm lần
        nữa trên việc đã ưu tiên: không đổi gì (version giữ nguyên). Bỏ ưu tiên: null, việc về chỗ
        theo `team_seq`. Không ngắt việc đang chạy, không gọi model."""
        with self._lock:
            self._tx()
            try:
                row = self._team_row(task_id)
                if not row:
                    self._db.rollback()
                    raise QueueError("not_team_task")
                team_id = str(row["team_id"])
                if int(expected_version) != self._queue_version(team_id):
                    queue = self._team_queue_locked(team_id)
                    self._db.rollback()
                    raise QueueConflict(queue)
                if row["status"] not in ("team_queued", "team_blocked"):
                    self._db.rollback()
                    raise QueueError("not_waiting")
                already = row["team_prio"] is not None
                if bool(prioritize) != already:
                    if prioritize:
                        top = self._db.execute(
                            "SELECT COALESCE(MAX(team_prio), 0) AS m FROM tasks WHERE lane='team' AND team_id=?",
                            (team_id,),
                        ).fetchone()["m"]
                        value: Optional[int] = int(top) + 1
                    else:
                        value = None
                    self._db.execute(
                        "UPDATE tasks SET team_prio=?, updated_at=? WHERE id=?",
                        (value, now(), task_id),
                    )
                    self._event(task_id, "team_priority" if prioritize else "team_unpriority",
                                "" if value is None else f"prio {value}")
                    self._bump_queue(team_id)
                queue = self._team_queue_locked(team_id)
                self._db.commit()
                return queue
            except (QueueConflict, QueueError):
                raise
            except Exception:
                self._db.rollback()
                raise

    def set_quality_required(self, team_id, enabled):
        with self._lock:
            self._db.execute('INSERT INTO team_quality_required VALUES(?,?) ON CONFLICT(team_id) DO UPDATE SET enabled=excluded.enabled',
                             (team_id, int(enabled)))
            self._db.commit()

    def set_acceptance_ready(self, task_id, revision, contract_version):
        with self._lock:
            self._db.execute('UPDATE tasks SET acceptance_ready=1, acceptance_revision=?, acceptance_contract_version=? '
                             'WHERE id=? AND team_rev=?', (revision, contract_version, task_id, revision))
            self._db.commit()

    def claim_team_next(
        self, team_id: str, worker_id: str, lease_s: int = 90, max_running: int = 1,
    ) -> Optional[dict]:
        """Nhận việc đầu hàng của nhóm nếu nhóm còn chỗ chạy (mặc định một việc mỗi nhóm).

        Kiểm chỗ chạy, chọn việc, đặt `team_running`, ghi `task_runs` và tăng version trong MỘT
        giao dịch `BEGIN IMMEDIATE`: không bao giờ có hai việc cùng chạy trong một nhóm."""
        team_id = str(team_id)
        # Cross-store preparation deliberately precedes the claim transaction. A crash leaves the task unready.
        if self.quality_prepare:
            self.quality_prepare(team_id)
        ts = now()
        run_id = "run_" + uuid.uuid4().hex[:14]
        with self._lock:
            self._tx()
            try:
                running = self._db.execute(
                    "SELECT COUNT(*) AS n FROM tasks WHERE lane='team' AND team_id=? AND status='team_running'",
                    (team_id,),
                ).fetchone()["n"]
                if int(running) >= max(1, int(max_running)):
                    self._db.rollback()
                    return None
                row = self._db.execute(
                    f"""SELECT * FROM tasks WHERE lane='team' AND team_id=? AND status='team_queued'
                        ORDER BY {_TEAM_ORDER} LIMIT 1""",
                    (team_id,),
                ).fetchone()
                if not row:
                    self._db.rollback()
                    return None
                tid = str(row["id"])
                required = self._db.execute('SELECT enabled FROM team_quality_required WHERE team_id=?', (team_id,)).fetchone()
                if (required and required[0]) or row['acceptance_contract_version']:
                    if not row['acceptance_ready'] or row['acceptance_revision'] != row['team_rev']:
                        self._db.rollback()
                        return None
                self._db.execute(
                    """UPDATE tasks SET status='team_running', attempts=attempts+1, claimed_by=?,
                       claim_expires_at=?, last_heartbeat_at=?, current_run_id=?, block_kind='',
                       block_reason='', updated_at=? WHERE id=? AND status='team_queued'""",
                    (worker_id, ts + lease_s, ts, run_id, ts, tid),
                )
                self._db.execute(
                    """INSERT INTO task_runs (id, task_id, brain_root, worker_id, engine_provider,
                       status, started_at, heartbeat_at) VALUES (?, ?, ?, ?, '', 'running', ?, ?)""",
                    (run_id, tid, str(row["brain_root"]), worker_id, ts, ts),
                )
                self._event(tid, "team_claimed", f"claimed by {worker_id}", run_id)
                self._bump_queue(team_id)
                self._db.commit()
            except Exception:
                self._db.rollback()
                raise
        return self.get_task(tid)

    def team_heartbeat(self, task_id: str, worker_id: str, lease_s: int = 90) -> bool:
        ts = now()
        with self._lock:
            cur = self._db.execute(
                """UPDATE tasks SET last_heartbeat_at=?, claim_expires_at=?
                   WHERE id=? AND lane='team' AND status='team_running' AND claimed_by=?""",
                (ts, ts + lease_s, task_id, worker_id),
            )
            self._db.commit()
            return cur.rowcount == 1

    def _team_move(
        self, task_id: str, allowed_from: tuple, status: str, event_type: str, message: str = "",
        *, block_kind: str = "", block_reason: str = "", result: Optional[str] = None,
        run_status: str = "", expected_rev: Optional[int] = None, acceptance_decision: Optional[str] = None,
    ) -> Optional[str]:
        """Chuyển trạng thái một việc nhóm. Trả trạng thái TRƯỚC khi chuyển, None nếu không áp. `expected_rev`: chỉ áp
        khi `team_rev` vẫn là bản đó (CAS cùng giao dịch, review T1 R7)."""
        ts = now()
        with self._lock:
            self._tx()
            try:
                if acceptance_decision and self._db.execute('SELECT 1 FROM team_acceptance_applied WHERE task_id=? AND decision_key=?',
                        (task_id, acceptance_decision)).fetchone():
                    self._db.rollback()
                    return 'applied'
                row = self._team_row(task_id)
                if not row or row["status"] not in allowed_from or (
                        expected_rev is not None and int(row["team_rev"] or 1) != int(expected_rev)):
                    self._db.rollback()
                    return None
                prev = str(row["status"])
                self._db.execute(
                    """UPDATE tasks SET status=?, block_kind=?, block_reason=?, claimed_by='',
                       claim_expires_at=0, current_run_id='', result=COALESCE(?, result), updated_at=?
                       WHERE id=?""",
                    (status, block_kind, (block_reason or "")[:2000],
                     None if result is None else str(result)[:20000], ts, task_id),
                )
                run_id = str(row["current_run_id"] or "")
                if run_id and run_status:
                    self._db.execute(
                        """UPDATE task_runs SET status=?, finished_at=?, heartbeat_at=?, error=?
                           WHERE id=? AND status='running'""",
                        (run_status, ts, ts, (block_reason or "")[:4000], run_id),
                    )
                self._event(task_id, event_type, message or block_reason or status, run_id)
                if acceptance_decision:
                    self._db.execute('INSERT INTO team_acceptance_applied VALUES(?,?,?)',
                                     (task_id, acceptance_decision, int(row['team_rev'])))
                self._bump_queue(str(row["team_id"]))
                self._db.commit()
                return prev
            except Exception:
                self._db.rollback()
                raise

    def team_block(self, task_id: str, kind: str, reason: str = "") -> Optional[str]:
        """Việc bị chặn RỜI chỗ chạy (hàng đi tiếp). Giữ `team_seq`/`team_prio` để gỡ chặn về chỗ cũ."""
        return self._team_move(task_id, ("team_running", "team_queued"), "team_blocked", "team_blocked",
                               block_kind=str(kind or "failed"), block_reason=reason, run_status="blocked")

    def team_reblock(self, task_id: str, kind: str, reason: str = "", *, decision_key=None, expected_rev=None) -> Optional[str]:
        """A blocked job stays blocked for another reason (0.207.0: the owner rejected or revoked an approval, the request
        expired). Same place in the queue; the new kind decides which buttons the owner gets."""
        return self._team_move(task_id, ("team_blocked",), "team_blocked", "team_reblocked",
                               block_kind=str(kind or "failed"), block_reason=reason,
                               acceptance_decision=decision_key, expected_rev=expected_rev)

    def team_unblock(self, task_id: str, *, decision_key=None, expected_rev=None) -> Optional[str]:
        return self._team_move(task_id, ("team_blocked",), "team_queued", "team_unblocked",
                               acceptance_decision=decision_key, expected_rev=expected_rev)

    def acceptance_decision_applied(self, task_id, decision_key):
        with self._lock:
            return self._db.execute('SELECT 1 FROM team_acceptance_applied WHERE task_id=? AND decision_key=?',
                                    (task_id, decision_key)).fetchone() is not None

    def team_requeue(self, task_id: str, reason: str = "") -> Optional[str]:
        """Việc đang chạy về hàng chờ, giữ chỗ cũ (restart trước mốc gọi engine)."""
        return self._team_move(task_id, ("team_running",), "team_queued", "team_requeued", reason,
                               run_status="stale")

    def team_finish(self, task_id: str, result: str = "", expected_rev: Optional[int] = None) -> Optional[str]:
        """Chốt việc xong. Có `expected_rev` thì chỉ chốt khi yêu cầu chưa bị sửa sang bản khác: kết quả của bản cũ
        không bao giờ thành kết quả của bản mới (review T1 R7)."""
        return self._team_move(task_id, ("team_running",), "done", "team_done", "done",
                               result=result, run_status="completed", expected_rev=expected_rev)

    def team_finish_reviewed(self, task_id: str, result: str = "", expected_rev: Optional[int] = None, *, decision_key=None) -> Optional[str]:
        """0.209.0: the owner confirmed the product of a job that waited for acceptance (blocked) -> done, same CAS."""
        return self._team_move(task_id, ("team_blocked",), "done", "team_done", "done (owner accepted)",
                               result=result, run_status="completed", expected_rev=expected_rev, acceptance_decision=decision_key)

    def team_cancel(self, task_id: str, reason: str = "owner cancel") -> Optional[str]:
        return self._team_move(task_id, TEAM_OPEN_STATUS, "cancelled", "team_cancelled", reason,
                               block_kind="cancelled", block_reason=reason, run_status="cancelled")

    # ───── Javis Core giao việc cho nhóm (0.357.0, issue #826) ─────
    # Việc nhóm không dùng `metadata_json` ở đâu khác, nên nơi giao việc nằm ở đó: `core` (mã đối chiếu, nơi báo kết
    # quả, kênh), `core_said` (trạng thái đã báo gần nhất), `core_closed` (đã báo lần cuối, thôi theo dõi).

    def team_core_mark(self, task_id: str, info: dict) -> None:
        """Ghi nơi giao của một việc nhóm do Core mở. Chỉ ghi lần đầu: gửi lại cùng mã đối chiếu không đổi nơi báo."""
        with self._lock:
            row = self._db.execute("SELECT metadata_json FROM tasks WHERE id=? AND lane='team'", (task_id,)).fetchone()
            if not row:
                return
            meta = _loads(row["metadata_json"], {}) or {}
            if isinstance(meta.get("core"), dict):
                return
            meta["core"] = dict(info or {})
            self._db.execute("UPDATE tasks SET metadata_json=? WHERE id=?", (_json(meta), task_id))
            self._db.commit()

    def team_core_watch(self, limit: int = 200) -> list:
        """Việc nhóm do Core mở mà chưa báo lần cuối, cũ nhất trước."""
        with self._lock:
            rows = self._db.execute(
                """SELECT * FROM tasks WHERE lane='team' AND metadata_json LIKE '%"core":{%'
                     AND metadata_json NOT LIKE '%"core_closed":true%' ORDER BY updated_at LIMIT ?""",
                (int(limit),),
            ).fetchall()
        return [self._task_from_row(r) for r in rows]

    def team_core_find(self, team_id: str, correlation_id: str) -> Optional[dict]:
        """Việc nhóm do Core mở theo mã đối chiếu (mới nhất nếu trùng)."""
        cid = str(correlation_id or "").strip()
        if not cid:
            return None
        with self._lock:
            rows = self._db.execute(
                """SELECT * FROM tasks WHERE lane='team' AND team_id=? AND metadata_json LIKE ?
                   ORDER BY created_at DESC LIMIT 20""",
                (team_id, '%"correlation_id":' + _json(cid) + '%'),
            ).fetchall()
        for row in rows:
            task = self._task_from_row(row)
            if ((task.get("metadata") or {}).get("core") or {}).get("correlation_id") == cid:
                return task
        return None

    def team_core_said(self, task_id: str, said: str, closed: bool = False) -> None:
        with self._lock:
            row = self._db.execute("SELECT metadata_json FROM tasks WHERE id=? AND lane='team'", (task_id,)).fetchone()
            if not row:
                return
            meta = _loads(row["metadata_json"], {}) or {}
            meta["core_said"] = str(said or "")
            if closed:
                meta["core_closed"] = True
            self._db.execute("UPDATE tasks SET metadata_json=? WHERE id=?", (_json(meta), task_id))
            self._db.commit()

    def team_amend(self, task_id: str, addition: str) -> Optional[int]:
        """Chủ sửa yêu cầu của việc chưa kết thúc: nối phần thêm vào `intent`, tăng `team_rev`."""
        addition = str(addition or "").strip()
        if not addition:
            return None
        with self._lock:
            self._tx()
            try:
                row = self._team_row(task_id)
                if not row or row["status"] not in TEAM_OPEN_STATUS:
                    self._db.rollback()
                    return None
                rev = int(row["team_rev"] or 1) + 1
                intent = (str(row["intent"] or "") + f"\n\n[Sửa yêu cầu, bản {rev}] " + addition)[:20000]
                self._db.execute(
                    "UPDATE tasks SET intent=?, team_rev=?, updated_at=? WHERE id=?",
                    (intent, rev, now(), task_id),
                )
                self._event(task_id, "team_amended", f"rev {rev}")
                self._bump_queue(str(row["team_id"]))
                self._db.commit()
                return rev
            except Exception:
                self._db.rollback()
                raise

    def team_set_coordinator(self, task_id: str, coordinator_key: str) -> bool:
        """Đổi trưởng nhóm điều phối của một việc chưa kết thúc (trưởng nhóm đổi giữa chừng, spec 6.3)."""
        with self._lock:
            cur = self._db.execute(
                f"""UPDATE tasks SET coordinator_key=?, updated_at=?
                    WHERE id=? AND lane='team' AND status IN ({','.join('?' for _ in TEAM_OPEN_STATUS)})""",
                (str(coordinator_key or ""), now(), task_id, *TEAM_OPEN_STATUS),
            )
            if cur.rowcount == 1:
                self._event(task_id, "coordinator_changed", str(coordinator_key or ""))
            self._db.commit()
            return cur.rowcount == 1

    def team_tasks_by_status(self, status: str) -> list[dict]:
        """Mọi việc nhóm (mọi nhóm) ở một trạng thái `team_*`, cho việc nhắc chặn lâu và phục hồi."""
        if status not in TEAM_OPEN_STATUS:
            return []
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM tasks WHERE lane='team' AND status=? ORDER BY updated_at", (status,)
            ).fetchall()
        return [self._task_from_row(r) for r in rows]

    def team_running_tasks(self) -> list[dict]:
        """Mọi việc nhóm đang `team_running` (mọi nhóm), cho bộ chạy nhóm khôi phục sau restart."""
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM tasks WHERE lane='team' AND status='team_running' ORDER BY updated_at"
            ).fetchall()
        return [self._task_from_row(r) for r in rows]

    def team_take_over(self, task_id: str, worker_id: str, lease_s: int = 90) -> bool:
        """Tiến trình mới nhận lại một việc đang chạy (sau restart), giữ nguyên run hiện tại."""
        ts = now()
        with self._lock:
            cur = self._db.execute(
                """UPDATE tasks SET claimed_by=?, claim_expires_at=?, last_heartbeat_at=?, updated_at=?
                   WHERE id=? AND lane='team' AND status='team_running'""",
                (worker_id, ts + lease_s, ts, ts, task_id),
            )
            if cur.rowcount == 1:
                self._event(task_id, "team_taken_over", f"taken over by {worker_id}")
            self._db.commit()
            return cur.rowcount == 1

    def teams_with_waiting(self) -> list[str]:
        with self._lock:
            rows = self._db.execute(
                "SELECT DISTINCT team_id FROM tasks WHERE lane='team' AND status='team_queued' ORDER BY team_id"
            ).fetchall()
        return [str(r["team_id"]) for r in rows]

    def team_history(self, team_id: str, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                """SELECT * FROM tasks WHERE lane='team' AND team_id=? AND status IN ('done','cancelled')
                   ORDER BY updated_at DESC LIMIT ?""",
                (str(team_id), max(1, min(500, int(limit)))),
            ).fetchall()
        return [self._task_from_row(r) for r in rows]

    def team_open_brief(self, team_id: str, limit: int = 8) -> list[dict]:
        """Việc đang mở của một nhóm cho khối lịch sử dài (T4, 0.170.0): chỉ các cột cần, một truy vấn theo chỉ mục
        `idx_tasks_team_queue`, có trần dòng. Đang làm trước, rồi ưu tiên, rồi thứ tự xếp hàng."""
        with self._lock:
            rows = self._db.execute(
                f"""SELECT id, title, intent, status, team_rev, team_prio, team_seq, block_kind, block_reason, updated_at
                    FROM tasks WHERE lane='team' AND team_id=? AND status IN ({','.join('?' for _ in TEAM_OPEN_STATUS)})
                    ORDER BY CASE status WHEN 'team_running' THEN 0 WHEN 'team_queued' THEN 1 ELSE 2 END,
                             team_prio IS NULL, team_prio DESC, team_seq LIMIT ?""",
                (str(team_id), *TEAM_OPEN_STATUS, max(1, min(100, int(limit)))),
            ).fetchall()
        return [dict(r) for r in rows]

    def team_last_done(self, team_id: str) -> Optional[dict]:
        """Việc xong gần nhất của một nhóm (nguồn đóng góp của kết quả gần nhất, T4 0.170.0). Không đọc phụ thuộc."""
        with self._lock:
            row = self._db.execute(
                """SELECT id, title, status, result, updated_at FROM tasks
                   WHERE lane='team' AND team_id=? AND status='done' ORDER BY updated_at DESC LIMIT 1""",
                (str(team_id),),
            ).fetchone()
        return dict(row) if row else None

    def health(self, brain_root: Optional[str] = None) -> dict:
        where = " WHERE lane<>'team'" + (" AND brain_root=?" if brain_root else "")
        args = (brain_root,) if brain_root else ()
        with self._lock:
            rows = self._db.execute(
                f"SELECT status, COUNT(*) AS n FROM tasks{where} GROUP BY status", args
            ).fetchall()
            recent = self._db.execute(
                f"""SELECT COUNT(*) AS n FROM tasks{where}
                    AND status='done' AND updated_at>=?""",
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
