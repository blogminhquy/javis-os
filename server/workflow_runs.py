"""Kho lịch sử chạy quy trình - SQLite trong JAVIS_STATE_DIR.

Vì sao có: tới 0.58.5, bấm Chạy ở trang Quy trình thì kết quả chỉ stream vào một ngăn kéo tạm,
đóng là mất, và Javis không có chỗ nào để tra "quy trình chạy gần nhất ra sao". Kho này ghi
MỌI lần chạy, bất kể khởi phát từ trang Cộng sự, Kanban, nhắc hẹn hay loop, vì nó được bọc
ngay trong `execute_workflow` (main.py) chứ không ở từng chỗ gọi.

Vì sao SQLite riêng chứ không chung kanban.sqlite3: task_store là hàng đợi có luật chuyển
trạng thái riêng; lịch sử chạy chỉ là nhật ký append. Tách file thì hai bên không kéo nhau.

Ghi chú: KHÔNG dùng ký tự em dash ở bất kỳ đâu trong file này.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import STATE_DIR

TRANG_THAI = ("running", "done", "error", "waiting")
NHAN_TRANG_THAI = {"running": "đang chạy", "done": "xong", "error": "lỗi", "waiting": "chờ duyệt"}

# Trần ký tự. Kết quả tool đi thẳng vào ngữ cảnh chat (engine API cắt 8000), nên kho giữ đủ
# để đọc lại chứ không giữ nguyên bản: đầu vào 4000, việc mỗi bước 2000, kết quả mỗi bước
# 4000, kết quả cuối 20000, tóm tắt trong danh sách 200.
TRAN_INPUT = 4000
TRAN_TASK = 2000
TRAN_OUT_BUOC = 4000
TRAN_OUT_CUOI = 20000
TRAN_TOM_TAT = 200

_SCHEMA = """
CREATE TABLE IF NOT EXISTS workflow_runs (
    id          TEXT PRIMARY KEY,
    brain       TEXT NOT NULL,
    slug        TEXT NOT NULL,
    name        TEXT NOT NULL DEFAULT '',
    session_id  TEXT NOT NULL DEFAULT '',
    source      TEXT NOT NULL DEFAULT 'other',
    input       TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'running',
    started_at  REAL NOT NULL,
    finished_at REAL NOT NULL DEFAULT 0,
    steps_json  TEXT NOT NULL DEFAULT '[]',
    output      TEXT NOT NULL DEFAULT '',
    error       TEXT NOT NULL DEFAULT '',
    task_id     TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_wfruns_brain_started ON workflow_runs(brain, started_at DESC);
CREATE INDEX IF NOT EXISTS ix_wfruns_session ON workflow_runs(session_id);
CREATE INDEX IF NOT EXISTS ix_wfruns_task ON workflow_runs(task_id);
"""

_COT = ("id", "brain", "slug", "name", "session_id", "source", "input", "status",
        "started_at", "finished_at", "steps_json", "output", "error", "task_id")


def _cat(s: Any, n: int) -> str:
    return str(s or "")[:n]


class WorkflowRunStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(self.path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=5000")
        with self._lock:
            self._db.executescript(_SCHEMA)

    # ---- ghi ----
    def bat_dau(self, *, brain: str, slug: str, name: str, input: str, source: str,
                session_id: str = "") -> str:
        rid = uuid.uuid4().hex
        with self._lock:
            self._db.execute(
                "INSERT INTO workflow_runs (id, brain, slug, name, session_id, source, input, "
                "status, started_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (rid, str(brain), str(slug), str(name or slug), str(session_id or ""),
                 str(source or "other"), _cat(input, TRAN_INPUT), "running", time.time()))
            self._db.commit()
        return rid

    def ghi_buoc(self, run_id: str, i: int, **fields: Any) -> None:
        """Gộp vào bước `i` (tạo mới nếu chưa có). Chỉ nhận agent, task, output, verified, error."""
        with self._lock:
            row = self._db.execute("SELECT steps_json FROM workflow_runs WHERE id=?", (run_id,)).fetchone()
            if not row:
                return
            steps = json.loads(row["steps_json"] or "[]")
            while len(steps) <= int(i):
                steps.append({"i": len(steps), "agent": "", "task": "", "output": "", "verified": None, "error": ""})
            b = steps[int(i)]
            if "agent" in fields:
                b["agent"] = str(fields["agent"] or "")
            if "task" in fields:
                b["task"] = _cat(fields["task"], TRAN_TASK)
            if "output" in fields:
                b["output"] = _cat(fields["output"], TRAN_OUT_BUOC)
            if "verified" in fields:
                b["verified"] = fields["verified"]
            if "error" in fields:
                b["error"] = _cat(fields["error"], TRAN_OUT_BUOC)
            self._db.execute("UPDATE workflow_runs SET steps_json=? WHERE id=?",
                             (json.dumps(steps, ensure_ascii=False), run_id))
            self._db.commit()

    def ket_thuc(self, run_id: str, status: str, *, output: str = "", error: str = "",
                 task_id: str = "") -> None:
        if status not in TRANG_THAI:
            status = "error"
        with self._lock:
            self._db.execute(
                "UPDATE workflow_runs SET status=?, finished_at=?, output=CASE WHEN ?<>'' THEN ? ELSE output END, "
                "error=?, task_id=CASE WHEN ?<>'' THEN ? ELSE task_id END WHERE id=?",
                (status, time.time(), _cat(output, TRAN_OUT_CUOI), _cat(output, TRAN_OUT_CUOI),
                 _cat(error, TRAN_OUT_BUOC), str(task_id or ""), str(task_id or ""), run_id))
            self._db.commit()

    # ---- đọc ----
    @staticmethod
    def _row(r: sqlite3.Row, day_du: bool) -> Dict[str, Any]:
        d = {k: r[k] for k in _COT}
        d["steps"] = json.loads(d.pop("steps_json") or "[]")
        d["nhan"] = NHAN_TRANG_THAI.get(d["status"], d["status"])
        if not day_du:
            d["output_tom_tat"] = _cat(d.pop("output"), TRAN_TOM_TAT)
            d["steps"] = [{"i": s.get("i"), "agent": s.get("agent"), "verified": s.get("verified"),
                           "error": bool(s.get("error"))} for s in d["steps"]]
        return d

    def lay(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            r = self._db.execute("SELECT * FROM workflow_runs WHERE id=?", (run_id,)).fetchone()
        return self._row(r, True) if r else None

    def gan_nhat(self, brain: str, *, slug: Optional[str] = None, session_id: Optional[str] = None,
                 status: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        where, params = ["brain=?"], [str(brain)]
        if slug:
            where.append("slug=?"); params.append(slug)
        if session_id:
            where.append("session_id=?"); params.append(session_id)
        if status:
            where.append("status=?"); params.append(status)
        params.append(int(limit))
        with self._lock:
            rows = self._db.execute(
                f"SELECT * FROM workflow_runs WHERE {' AND '.join(where)} ORDER BY started_at DESC, rowid DESC LIMIT ?",
                params).fetchall()
        return [self._row(r, False) for r in rows]

    def dem_theo_phien(self, session_id: str) -> int:
        with self._lock:
            r = self._db.execute("SELECT COUNT(*) FROM workflow_runs WHERE session_id=?", (session_id,)).fetchone()
        return int(r[0]) if r else 0

    def tim_theo_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        if not task_id:
            return None
        with self._lock:
            r = self._db.execute("SELECT * FROM workflow_runs WHERE task_id=? ORDER BY started_at DESC LIMIT 1",
                                 (task_id,)).fetchone()
        return self._row(r, True) if r else None

    def moc_moi_nhat_theo_slug(self, brain: str) -> Dict[str, float]:
        with self._lock:
            rows = self._db.execute("SELECT slug, MAX(started_at) AS m FROM workflow_runs WHERE brain=? GROUP BY slug",
                                    (str(brain),)).fetchall()
        return {r["slug"]: float(r["m"] or 0) for r in rows}


_STORE: Optional[WorkflowRunStore] = None
_STORE_LOCK = threading.Lock()


def get_store() -> WorkflowRunStore:
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = WorkflowRunStore(Path(STATE_DIR) / "workflow_runs.sqlite3")
        return _STORE
