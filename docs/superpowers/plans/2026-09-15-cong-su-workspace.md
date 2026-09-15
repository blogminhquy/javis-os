# Trang Cộng sự + kho lịch sử chạy quy trình - Kế hoạch triển khai

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Một trang "Cộng sự" thay hai trang Trợ lý/Quy trình, chat được với từng trợ lý và từng quy trình trên cùng khung chat của app, mọi lần chạy quy trình được lưu lại và Javis tra được.

**Architecture:** Mọi thứ là một phiên chat: phiên kênh `agent:<slug>` đổi system prompt sang prompt của trợ lý, phiên kênh `workflow:<slug>` biến mỗi tin thành một lần chạy `execute_workflow` và trả kết quả như một lượt chat. Kho `workflow_runs.sqlite3` ghi mọi lần chạy (từ trang Cộng sự lẫn Kanban). Dashboard mượn khung chat có sẵn, thêm cột trái (danh sách) và cột phải (cài đặt / tiến độ / lịch sử).

**Tech Stack:** Python 3 + FastAPI + sqlite3 (server/), vanilla JS + Alpine (dashboard/), test chạy bằng `python tests/run.py <lọc>` (tự chọn .venv), test JS bằng node.

**Spec:** `docs/superpowers/specs/2026-09-15-cong-su-workspace-design.md`

## Global Constraints

- KHÔNG dùng ký tự em dash (U+2014) ở bất kỳ đâu: code, chuỗi, comment, docs, CHANGELOG. Dùng "-" hoặc viết lại câu.
- Chuỗi hiển thị cho người dùng phải là tiếng Việt có dấu, lấy từ từ điển `dashboard/i18n/vi.json` (kèm `en.json`), không viết cứng trong JS.
- Tên hàm/biến mới trong server viết theo phong cách repo (tiếng Việt không dấu hoặc tiếng Anh ngắn), comment tiếng Việt giải thích VÌ SAO.
- Trang mới phải đăng ký ở đủ ba nơi: `RAIL_ITEMS` (dashboard/console.js), `PAGES` (dashboard/ui-actions.js), `PAGES` (server/ui_targets.py). `tests/js/test_ui_actions.js` canh việc này.
- Test Python theo khuôn repo: file `tests/python/test_<ten>.py`, đầu file `from _paths import ROOT, SERVER`, đặt `os.environ["JAVIS_STATE_DIR"]` sang thư mục tạm TRƯỚC khi import module server, hàm `check(name, cond)` in `ok`/`FAIL`, cuối file `sys.exit(1 if fails else 0)`.
- Chạy test: `python tests/run.py <tên-lọc>` (Windows tự dùng .venv). Trên máy này có 13 file Python đỏ sẵn trên main sạch (xem memory), chỉ quan tâm test của mình.
- Commit nhỏ, mỗi task một commit, kết thúc message commit bằng `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Nhánh làm việc: `feat/cong-su-workspace` (đã có, chứa spec).

---

### Task 1: Kho lịch sử chạy `server/workflow_runs.py`

**Files:**
- Create: `server/workflow_runs.py`
- Test: `tests/python/test_workflow_runs.py`

**Interfaces:**
- Produces:
  - `workflow_runs.get_store() -> WorkflowRunStore` (singleton, DB tại `config.STATE_DIR / "workflow_runs.sqlite3"`)
  - `WorkflowRunStore.bat_dau(*, brain, slug, name, input, source, session_id="") -> str` (run_id)
  - `WorkflowRunStore.ghi_buoc(run_id, i, **fields)` với fields trong `agent, task, output, verified, error`
  - `WorkflowRunStore.ket_thuc(run_id, status, *, output="", error="", task_id="")`
  - `WorkflowRunStore.lay(run_id) -> dict | None`
  - `WorkflowRunStore.gan_nhat(brain, *, slug=None, session_id=None, status=None, limit=20) -> list[dict]`
  - `WorkflowRunStore.dem_theo_phien(session_id) -> int`
  - `WorkflowRunStore.tim_theo_task(task_id) -> dict | None`
  - `WorkflowRunStore.moc_moi_nhat_theo_slug(brain) -> dict[str, float]`
  - Hằng: `TRANG_THAI = ("running", "done", "error", "waiting")`, `NHAN_TRANG_THAI = {"running": "đang chạy", "done": "xong", "error": "lỗi", "waiting": "chờ duyệt"}`

- [ ] **Step 1: Viết test đỏ**

```python
"""Kho lịch sử chạy quy trình (server/workflow_runs.py).

    python tests/run.py workflow_runs

Vì sao có kho này: trước đây bấm Chạy ở trang Quy trình thì kết quả stream vào một ngăn kéo
tạm, đóng là mất. Hỏi Javis "quy trình chạy gần nhất ra sao" là không có gì để tra.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-wfruns-")

import workflow_runs  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


st = workflow_runs.get_store()

# 1. Bắt đầu một lần chạy -> có id, trạng thái running
rid = st.bat_dau(brain="/b1", slug="viet-bai", name="Viết bài", input="chủ đề A",
                 source="web", session_id="s1")
r = st.lay(rid)
check("bat_dau tra id va running", bool(rid) and r["status"] == "running")
check("bat_dau giu input/source/session", r["input"] == "chủ đề A" and r["source"] == "web"
      and r["session_id"] == "s1" and r["name"] == "Viết bài")

# 2. Ghi bước: tạo mới rồi cập nhật cùng chỉ số
st.ghi_buoc(rid, 0, agent="Nhà nghiên cứu", task="tìm hiểu")
st.ghi_buoc(rid, 0, output="kết quả bước 0", verified=True)
st.ghi_buoc(rid, 1, agent="Người viết", task="viết", error="hết hạn")
steps = st.lay(rid)["steps"]
check("ghi_buoc gop cung chi so", len(steps) == 2 and steps[0]["agent"] == "Nhà nghiên cứu"
      and steps[0]["output"] == "kết quả bước 0" and steps[0]["verified"] is True)
check("ghi_buoc giu loi buoc", steps[1]["error"] == "hết hạn")

# 3. Kết thúc: done + output, finished_at có
st.ket_thuc(rid, "done", output="bài hoàn chỉnh")
r = st.lay(rid)
check("ket_thuc done", r["status"] == "done" and r["output"] == "bài hoàn chỉnh" and r["finished_at"] > 0)

# 4. Cắt độ dài: input 4000, task 2000, output bước 4000, output cuối 20000
rid2 = st.bat_dau(brain="/b1", slug="viet-bai", name="Viết bài", input="x" * 9000, source="kanban")
st.ghi_buoc(rid2, 0, task="t" * 5000, output="o" * 9000)
st.ket_thuc(rid2, "error", output="k" * 30000, error="lỗi thật")
r2 = st.lay(rid2)
check("cat input 4000", len(r2["input"]) == 4000)
check("cat task 2000 va output buoc 4000", len(r2["steps"][0]["task"]) == 2000
      and len(r2["steps"][0]["output"]) == 4000)
check("cat output cuoi 20000", len(r2["output"]) == 20000 and r2["error"] == "lỗi thật")

# 5. gan_nhat: mới nhất trước, lọc slug/session/status, limit
rid3 = st.bat_dau(brain="/b1", slug="ban-tin", name="Bản tin", input="", source="web", session_id="s2")
ds = st.gan_nhat("/b1")
check("gan_nhat moi nhat truoc", [x["id"] for x in ds] == [rid3, rid2, rid])
check("gan_nhat loc slug", [x["id"] for x in st.gan_nhat("/b1", slug="ban-tin")] == [rid3])
check("gan_nhat loc session+status", [x["id"] for x in st.gan_nhat("/b1", session_id="s1", status="done")] == [rid])
check("gan_nhat limit", len(st.gan_nhat("/b1", limit=2)) == 2)
check("gan_nhat khac brain rong", st.gan_nhat("/khac") == [])
check("gan_nhat khong mang output day du", "output_tom_tat" in ds[1] and "output" not in ds[1]
      and len(ds[1]["output_tom_tat"]) == 200)

# 6. dem_theo_phien, tim_theo_task, moc_moi_nhat_theo_slug
check("dem_theo_phien", st.dem_theo_phien("s1") == 1 and st.dem_theo_phien("s9") == 0)
st.ket_thuc(rid3, "waiting", task_id="task-77")
check("tim_theo_task", (st.tim_theo_task("task-77") or {}).get("id") == rid3
      and st.tim_theo_task("khong-co") is None)
moc = st.moc_moi_nhat_theo_slug("/b1")
check("moc_moi_nhat_theo_slug", set(moc) == {"viet-bai", "ban-tin"} and moc["ban-tin"] >= moc["viet-bai"])

# 7. Nhãn trạng thái tiếng Việt có đủ
check("nhan trang thai", set(workflow_runs.NHAN_TRANG_THAI) == set(workflow_runs.TRANG_THAI))

print("\nFAIL:" if fails else "\nOK - workflow_runs", fails or "")
sys.exit(1 if fails else 0)
```

- [ ] **Step 2: Chạy test, phải đỏ vì thiếu module**

Run: `python tests/run.py workflow_runs`
Expected: FAIL / ModuleNotFoundError: workflow_runs

- [ ] **Step 3: Viết `server/workflow_runs.py`**

```python
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
                f"SELECT * FROM workflow_runs WHERE {' AND '.join(where)} ORDER BY started_at DESC LIMIT ?",
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
```

Lưu ý: `gan_nhat` trong test kiểm `moc["ban-tin"] >= moc["viet-bai"]`; hai lần `bat_dau` liên tiếp có thể cùng `time.time()` nên dùng `>=`, đúng như test.

- [ ] **Step 4: Chạy test, phải xanh**

Run: `python tests/run.py workflow_runs`
Expected: mọi dòng `ok`, kết thúc `OK - workflow_runs`

- [ ] **Step 5: Commit**

```bash
git add server/workflow_runs.py tests/python/test_workflow_runs.py
git commit -m "Kho lịch sử chạy quy trình (workflow_runs.py)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Ghi lịch sử ngay trong `execute_workflow` + API đọc lịch sử

**Files:**
- Modify: `server/main.py` (quanh `execute_workflow` :7600, `execute_workflow_resume` :7743, `workflows_index` :6544, `agents_index` :5405, route `/workflows/run` :7827)
- Modify: `server/tasks.py:720` (truyền `source="kanban"`)
- Test: `tests/python/test_workflow_runs_api.py`

**Interfaces:**
- Consumes: `workflow_runs.get_store()` (Task 1)
- Produces:
  - `execute_workflow(brain, slug, input="", tools=None, session_id="", source="other")`: sự kiện `start` có thêm `run_id`
  - `execute_workflow_resume(brain, slug, task_id, node_id, code, tools=None, session_id="", source="other")`
  - `_ghi_lich_su(gen, *, brain, slug, name, input, source, session_id, run_id=None)` async generator bọc
  - `GET /workflows/runs?slug=&brain=&limit=` -> `{"runs": [...]}`
  - `GET /workflows/runs/{run_id}` -> bản ghi đầy đủ hoặc 404
  - `GET /workflows` mỗi mục thêm `last_run_at` (float, 0 nếu chưa chạy)
  - `GET /agents` mỗi mục thêm `last_chat_at` (float, 0 nếu chưa chat)

- [ ] **Step 1: Viết test đỏ cho generator bọc và hai route**

```python
"""Ghi lịch sử chạy ngay trong execute_workflow + route đọc lịch sử.

    python tests/run.py workflow_runs_api

Không chạy engine thật: bọc một generator giả phát đúng dãy sự kiện của execute_workflow.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-wfapi-")

import main  # noqa: E402
import workflow_runs  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


async def gia_done():
    yield {"type": "start", "workflow": "Viết bài", "steps": 2}
    yield {"type": "step_start", "i": 0, "agent": "Nhà nghiên cứu", "task": "tìm"}
    yield {"type": "step_text", "i": 0, "content": "..."}
    yield {"type": "step_done", "i": 0, "agent": "Nhà nghiên cứu", "output": "dữ liệu", "verified": None}
    yield {"type": "step_start", "i": 1, "agent": "Người viết", "task": "viết"}
    yield {"type": "step_done", "i": 1, "agent": "Người viết", "output": "bài xong", "verified": True}
    yield {"type": "done", "result": "bài xong"}


async def gia_error():
    yield {"type": "start", "workflow": "Viết bài", "steps": 1}
    yield {"type": "step_start", "i": 0, "agent": "A", "task": "t"}
    yield {"type": "step_error", "i": 0, "content": "engine chết"}
    yield {"type": "error", "content": "dừng vì lỗi"}


async def gia_wait():
    yield {"type": "start", "workflow": "Đăng bài", "steps": 2}
    yield {"type": "wait_user", "node": "dang", "prompt": "duyệt đăng?", "task_id": "tk1", "code": "AB12"}


async def gom(gen):
    return [e async for e in gen]


st = workflow_runs.get_store()

evs = asyncio.run(gom(main._ghi_lich_su(gia_done(), brain="/b", slug="viet-bai", name="Viết bài",
                                        input="chủ đề", source="web", session_id="s1")))
check("start co run_id, cac su kien giu nguyen", evs[0]["type"] == "start" and evs[0].get("run_id")
      and [e["type"] for e in evs[1:]] == ["step_start", "step_text", "step_done", "step_start", "step_done", "done"])
r = st.lay(evs[0]["run_id"])
check("ban ghi done du buoc", r["status"] == "done" and r["output"] == "bài xong"
      and [s["agent"] for s in r["steps"]] == ["Nhà nghiên cứu", "Người viết"] and r["steps"][1]["verified"] is True)

evs = asyncio.run(gom(main._ghi_lich_su(gia_error(), brain="/b", slug="viet-bai", name="Viết bài",
                                        input="", source="kanban", session_id="")))
r = st.lay(evs[0]["run_id"])
check("ban ghi error", r["status"] == "error" and r["error"] == "dừng vì lỗi" and r["steps"][0]["error"] == "engine chết"
      and r["source"] == "kanban")

evs = asyncio.run(gom(main._ghi_lich_su(gia_wait(), brain="/b", slug="dang-bai", name="Đăng bài",
                                        input="", source="web", session_id="s2")))
r = st.lay(evs[0]["run_id"])
check("ban ghi waiting + task_id", r["status"] == "waiting" and r["task_id"] == "tk1")

# Resume: truyền run_id cũ thì cập nhật đúng bản ghi đó thay vì tạo mới
truoc = len(st.gan_nhat("/b"))
evs = asyncio.run(gom(main._ghi_lich_su(gia_done(), brain="/b", slug="dang-bai", name="Đăng bài",
                                        input="", source="web", session_id="s2", run_id=r["id"])))
check("resume cap nhat ban ghi cu", len(st.gan_nhat("/b")) == truoc and st.lay(r["id"])["status"] == "done")


# Dừng giữa chừng (client đóng): bản ghi không kẹt ở running
async def dung_som():
    gen = main._ghi_lich_su(gia_done(), brain="/b", slug="viet-bai", name="Viết bài",
                            input="", source="web", session_id="s3")
    first = await gen.__anext__()
    await gen.aclose()
    return first["run_id"]

rid = asyncio.run(dung_som())
check("dong som -> error 'dung giua chung'", st.lay(rid)["status"] == "error")

# Route đọc
c = TestClient(main.app)
ds = c.get("/workflows/runs", params={"brain": "/b", "limit": 5}).json()["runs"]
check("GET /workflows/runs tra danh sach gon", len(ds) == 5 and "output_tom_tat" in ds[0] and "output" not in ds[0])
ds2 = c.get("/workflows/runs", params={"brain": "/b", "slug": "dang-bai"}).json()["runs"]
check("GET /workflows/runs loc slug", all(x["slug"] == "dang-bai" for x in ds2) and ds2)
one = c.get(f"/workflows/runs/{ds[0]['id']}").json()
check("GET /workflows/runs/{id} day du", one["id"] == ds[0]["id"] and "output" in one and "steps" in one)
check("GET /workflows/runs/{id} 404", c.get("/workflows/runs/khong-co").status_code == 404)

print("\nFAIL:" if fails else "\nOK - workflow_runs_api", fails or "")
sys.exit(1 if fails else 0)
```

Ghi chú cho route: `brain` ở đây là chuỗi bất kỳ; route phải khoá bằng `_brain_key(brain)`. Với brain giả "/b", `_brain_root("/b")` trả về gì thì kho dùng đúng chuỗi đó, test chỉ cần route và generator bọc dùng CÙNG hàm khoá. Vì vậy trong test, brain truyền cho `_ghi_lich_su` phải qua cùng phép khoá: sửa test cho khớp bằng cách đặt `B = main._brain_key("/b")` và truyền `brain=B` vào `_ghi_lich_su`, còn route thì truyền `brain="/b"` (route tự khoá). Làm ngay khi viết test.

- [ ] **Step 2: Chạy test, phải đỏ**

Run: `python tests/run.py workflow_runs_api`
Expected: AttributeError: module 'main' has no attribute '_ghi_lich_su'

- [ ] **Step 3: Thêm generator bọc và đổi tên hàm cũ trong main.py**

Đổi tên hàm hiện tại `execute_workflow` (dòng ~7600) thành `_execute_workflow_raw` (giữ nguyên thân, kể cả docstring). Ngay dưới nó thêm:

```python
async def _ghi_lich_su(gen, *, brain, slug, name, input, source, session_id, run_id=None):
    """Bọc luồng sự kiện của một lần chạy workflow để ghi kho lịch sử (workflow_runs).

    Không nuốt, không đổi sự kiện nào; chỉ gắn thêm `run_id` vào sự kiện `start`. Đặt ở đây
    (chứ không ở từng chỗ gọi) để trang Cộng sự, Kanban, nhắc hẹn và loop đều được ghi mà
    không ai phải nhớ. `run_id` truyền vào khi chạy TIẾP một lần đang chờ duyệt: cập nhật
    đúng bản ghi cũ thay vì đẻ bản mới.

    Luồng bị đóng giữa chừng (người dùng dừng, client rớt) thì `finally` chốt bản ghi là
    lỗi "dừng giữa chừng", không để nó kẹt ở "đang chạy" mãi.
    """
    import workflow_runs
    st = workflow_runs.get_store()
    rid = run_id or st.bat_dau(brain=brain, slug=slug, name=name, input=input or "",
                               source=source or "other", session_id=session_id or "")
    ket = None
    try:
        async for ev in gen:
            t = ev.get("type")
            if t == "start":
                ev = dict(ev, run_id=rid)
            elif t == "step_start":
                st.ghi_buoc(rid, int(ev.get("i", 0)), agent=ev.get("agent", ""), task=ev.get("task", ""))
            elif t == "step_done":
                st.ghi_buoc(rid, int(ev.get("i", 0)), output=ev.get("output", ""), verified=ev.get("verified"))
            elif t == "step_error":
                st.ghi_buoc(rid, int(ev.get("i", 0)), error=ev.get("content", ""))
            elif t == "wait_user":
                ket = "waiting"
                st.ket_thuc(rid, "waiting", task_id=str(ev.get("task_id") or ""))
            elif t == "error":
                ket = "error"
                st.ket_thuc(rid, "error", error=str(ev.get("content") or ""))
            elif t == "done":
                ket = "done"
                st.ket_thuc(rid, "done", output=str(ev.get("result") or ""))
            yield ev
    finally:
        if ket is None:
            try:
                st.ket_thuc(rid, "error", error="dừng giữa chừng")
            except Exception:
                pass


async def execute_workflow(brain, slug, input="", tools=None, session_id="", source="other"):
    """Chạy workflow và GHI LỊCH SỬ. Mọi chỗ gọi (trang Cộng sự, Kanban, nhắc hẹn) đi qua đây.
    `source`: web | kanban | reminder | loop | other, chỉ để lọc khi đọc lại."""
    wf_file = _workflows_dir(brain) / f"{slug}.md"
    if not wf_file.exists():
        yield {"type": "error", "content": "workflow not found"}
        return
    meta, _ = _read_md(wf_file)
    async for ev in _ghi_lich_su(
            _execute_workflow_raw(brain, slug, input, tools, session_id),
            brain=_brain_key(brain), slug=slug, name=meta.get("name", slug), input=input,
            source=source, session_id=session_id):
        yield ev
```

Tương tự với `execute_workflow_resume` (dòng ~7743): đổi tên thân cũ thành `_execute_workflow_resume_raw(brain, slug, task_id, node_id, code, tools=None, session_id="")` và thêm:

```python
async def execute_workflow_resume(brain, slug, task_id, node_id, code, tools=None,
                                  session_id="", source="other"):
    """Chạy tiếp lần đang chờ duyệt, ghi vào ĐÚNG bản ghi lịch sử đang `waiting`."""
    import workflow_runs
    cu = workflow_runs.get_store().tim_theo_task(task_id)
    wf_file = _workflows_dir(brain) / f"{slug}.md"
    meta, _ = _read_md(wf_file) if wf_file.exists() else ({}, "")
    async for ev in _ghi_lich_su(
            _execute_workflow_resume_raw(brain, slug, task_id, node_id, code, tools, session_id),
            brain=_brain_key(brain), slug=slug, name=meta.get("name", slug), input=(cu or {}).get("input", ""),
            source=source, session_id=session_id or (cu or {}).get("session_id", ""),
            run_id=(cu or {}).get("id")):
        yield ev
```

Kiểm bằng grep rằng không còn chỗ nào gọi `execute_workflow(` với tham số vị trí vượt quá `tools` (tasks.py:720 truyền 4 vị trí, hợp lệ). `deps=execute_workflow` ở main.py:8290 giữ nguyên (nay trỏ vào hàm bọc).

- [ ] **Step 4: Thêm hai route đọc và trường sắp xếp**

Ngay trên `@app.get("/workflows/run")` (dòng ~7827) thêm (khai `/workflows/runs/{run_id}` SAU `/workflows/runs` không sao vì đường khác nhau, nhưng cả hai phải khai TRƯỚC bất kỳ route `/workflows/{gì đó}` động nếu sau này có):

```python
@app.get("/workflows/runs")
async def workflow_runs_list(brain: str = Query("brain"), slug: str = Query(""), limit: int = Query(20)):
    """Lịch sử chạy quy trình, mới nhất trước, bản gọn (không kèm kết quả đầy đủ)."""
    import workflow_runs
    return {"runs": workflow_runs.get_store().gan_nhat(
        _brain_key(brain), slug=slug or None, limit=max(1, min(int(limit or 20), 100)))}


@app.get("/workflows/runs/{run_id}")
async def workflow_runs_get(run_id: str):
    import workflow_runs
    r = workflow_runs.get_store().lay(run_id)
    if not r:
        return JSONResponse({"error": "not found"}, status_code=404)
    return r
```

Trong `workflows_index(brain)` (dòng ~6544): sau vòng lặp, gắn mốc chạy gần nhất:

```python
    try:
        import workflow_runs
        moc = workflow_runs.get_store().moc_moi_nhat_theo_slug(_brain_key(brain))
    except Exception:
        moc = {}
    for w in out:
        w["last_run_at"] = float(moc.get(w["slug"], 0) or 0)
    return out
```

Trong `agents_index(brain)` (dòng ~5405): sau vòng lặp:

```python
    try:
        moc = get_store().moc_cap_nhat_theo_kenh(_brain_keys(brain), "agent:")
    except Exception:
        moc = {}
    for a in out:
        a["last_chat_at"] = float(moc.get("agent:" + a["slug"], 0) or 0)
    return out
```

`moc_cap_nhat_theo_kenh` là hàm mới của `SessionStore` (viết ở Task 3). Để Task 2 chạy độc lập, Task 2 chỉ thêm đoạn trên cho agents khi Task 3 đã xong; nếu làm Task 2 trước thì để `try/except` đó nguyên (nó rơi về `{}`), nhưng NHỚ quay lại Task 3 để hàm tồn tại thật.

Trong `server/tasks.py:720`, gọi `self.deps.execute_workflow(task["brain_root"], slug, intent, tools, source="kanban")`. Kiểm `TaskDeps` (grep `execute_workflow` trong tasks.py) là `Callable` không ràng kiểu tham số; nếu là dataclass với chữ ký cố định thì thêm `source` vào chữ ký đó.

- [ ] **Step 5: Chạy test, phải xanh; chạy cả test cũ liên quan**

Run: `python tests/run.py workflow_runs_api` rồi `python tests/run.py workflow_graph` và `python tests/run.py tasks_autonomous`
Expected: test mới xanh; hai test cũ giữ nguyên kết quả như trên main (so với `git stash` không được dùng, xem memory về cây làm việc dùng chung: nếu nghi ngờ, chạy test đó trên worktree sạch).

- [ ] **Step 6: Commit**

```bash
git add server/main.py server/tasks.py tests/python/test_workflow_runs_api.py
git commit -m "Ghi lịch sử mọi lần chạy workflow, thêm /workflows/runs

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Phiên theo kênh cộng sự trong kho phiên

**Files:**
- Modify: `server/sessions.py` (`list_sessions` :562)
- Modify: `server/main.py` (`sessions_list` :12412, thêm `POST /sessions/new` ngay dưới)
- Test: `tests/python/test_sessions_kenh_cong_su.py`

**Interfaces:**
- Produces:
  - `SessionStore.list_sessions(..., channel: Optional[str] = None)`: `channel` cụ thể thì lọc đúng kênh; `None` thì loại các kênh tiền tố `agent:` và `workflow:`
  - `SessionStore.moc_cap_nhat_theo_kenh(brain, tien_to) -> dict[channel, updated_at]`
  - `GET /sessions?channel=` ; `POST /sessions/new` (Form: `brain`, `channel`) -> `{"id", "channel"}`; 400 nếu kênh sai dạng; 404 nếu trợ lý/quy trình không có file.
  - Hằng trong `sessions.py`: `KENH_CONG_SU = ("agent:", "workflow:")`

- [ ] **Step 1: Viết test đỏ**

```python
"""Phiên chat theo kênh cộng sự: agent:<slug>, workflow:<slug>.

    python tests/run.py sessions_kenh_cong_su
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="javis-kenh-")
os.environ["JAVIS_STATE_DIR"] = _TMP
os.environ["JAVIS_SESSIONS_DB"] = str(Path(_TMP) / "conv.db")

import sessions  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


st = sessions.SessionStore(Path(_TMP) / "conv.db")
a = st.create_session(brain="/b", engine="cli", channel="web")
b = st.create_session(brain="/b", engine="cli", channel="agent:nguoi-viet")
c = st.create_session(brain="/b", engine="cli", channel="workflow:viet-bai")
d = st.create_session(brain="/b", engine="cli", channel="telegram")
for sid in (a, b, c, d):
    st.append_message(sid, "user", "xin chào")

ids = {s["id"] for s in st.list_sessions(brain="/b")}
check("mac dinh loai kenh cong su, giu web + telegram", ids == {a, d})
check("loc dung kenh agent", [s["id"] for s in st.list_sessions(brain="/b", channel="agent:nguoi-viet")] == [b])
check("loc dung kenh workflow", [s["id"] for s in st.list_sessions(brain="/b", channel="workflow:viet-bai")] == [c])
moc = st.moc_cap_nhat_theo_kenh(["/b"], "agent:")
check("moc_cap_nhat_theo_kenh", set(moc) == {"agent:nguoi-viet"} and moc["agent:nguoi-viet"] > 0)

# Route: POST /sessions/new
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
cl = TestClient(main.app)
r = cl.post("/sessions/new", data={"brain": "brain", "channel": "agent:khong-ton-tai"})
check("POST /sessions/new agent khong co -> 404", r.status_code == 404)
r = cl.post("/sessions/new", data={"brain": "brain", "channel": "gi-do"})
check("POST /sessions/new kenh sai dang -> 400", r.status_code == 400)
# Tạo một agent thật trong brain test rồi mở phiên
ag_dir = main._agents_dir("brain"); ag_dir.mkdir(parents=True, exist_ok=True)
(ag_dir / "nguoi-viet.md").write_text("---\nname: Người viết\nrole: viết\nmodel: gpt-5\nmodel_provider: openai-oauth\n---\nViết hay.\n", encoding="utf-8")
r = cl.post("/sessions/new", data={"brain": "brain", "channel": "agent:nguoi-viet"})
check("POST /sessions/new agent that -> id", r.status_code == 200 and r.json().get("id"))
row = main.get_store().get_session(r.json()["id"])
check("phien ghi dung kenh va ghim model cua agent", row["channel"] == "agent:nguoi-viet"
      and row.get("pinned_model") == "gpt-5" and row.get("pinned_provider") == "openai-oauth")
r = cl.get("/sessions", params={"brain": "brain", "channel": "agent:nguoi-viet"}).json()
check("GET /sessions?channel= tra dung phien", [s["id"] for s in r["sessions"]] == [row["id"]])

print("\nFAIL:" if fails else "\nOK - sessions_kenh_cong_su", fails or "")
sys.exit(1 if fails else 0)
```

Lưu ý: `main.get_store()` phải trỏ cùng DB với `sessions.get_store()` (env `JAVIS_SESSIONS_DB` đặt trước import). Nếu `_agents_dir("brain")` trỏ vào brain thật của máy thì đổi test sang tạo brain tạm: đặt `os.environ["JAVIS_BRAINS_DIR"]` hay biến tương đương mà `_brain_root` đọc (grep `def _brain_root` để biết biến env), ĐẶT TRƯỚC `import main`. Không được ghi file vào brain thật của máy.

- [ ] **Step 2: Chạy test, phải đỏ**

Run: `python tests/run.py sessions_kenh_cong_su`
Expected: TypeError: list_sessions() got an unexpected keyword argument 'channel'

- [ ] **Step 3: Sửa `sessions.py`**

Thêm hằng gần đầu file (sau `WEB` hằng khác nếu có):

```python
# Kênh của phiên "cộng sự": chat với MỘT trợ lý hoặc MỘT quy trình (trang Cộng sự, 0.59).
# Thanh lịch sử của trang Trò chuyện không liệt kê các kênh này: chúng thuộc về cột phải của
# trang Cộng sự, lẫn vào đây thì người dùng thấy hai bản ghi cho một việc.
KENH_CONG_SU = ("agent:", "workflow:")
```

Trong `list_sessions`, thêm tham số `channel: Optional[str] = None` và trong phần dựng `where`:

```python
        if channel:
            where.append("s.channel = ?")
            params.append(channel)
        else:
            for tien_to in KENH_CONG_SU:
                where.append("s.channel NOT LIKE ?")
                params.append(tien_to + "%")
```

Thêm phương thức mới cạnh `list_sessions`:

```python
    def moc_cap_nhat_theo_kenh(self, brain: Any, tien_to: str) -> Dict[str, float]:
        """{kênh: updated_at mới nhất} cho các kênh bắt đầu bằng `tien_to` (vd "agent:").
        Trang Cộng sự dùng để xếp trợ lý vừa chat gần nhất lên đầu."""
        cond, bparams = loc_brain(brain)
        sql = "SELECT channel, MAX(updated_at) AS m FROM sessions s WHERE s.channel LIKE ?"
        params: list = [tien_to + "%"]
        if cond:
            sql += " AND " + cond
            params += bparams
        sql += " GROUP BY channel"
        return {r["channel"]: float(r["m"] or 0) for r in self._read(sql, tuple(params))}
```

Kiểm chữ ký `self._read(sql, params)` trong file (grep `def _read`) và gọi đúng dạng nó nhận.

- [ ] **Step 4: Sửa route trong main.py**

`sessions_list`: thêm `channel: str = Query("")` và truyền `channel=channel or None`.

Ngay dưới `sessions_list` (TRƯỚC `@app.get("/sessions/{session_id}")`, vì `/sessions/new` là POST nên không đụng nhưng đặt gần cho dễ đọc):

```python
_KENH_CONG_SU_RE = re.compile(r"^(agent|workflow):([a-z0-9][a-z0-9-]*)$")


@app.post("/sessions/new")
async def sessions_new(brain: str = Form("brain"), channel: str = Form("web")):
    """Mở một phiên TRỐNG với kênh định trước. Trang Cộng sự gọi trước tin đầu tiên: kho phiên
    phải biết phiên này là chat với trợ lý/quy trình nào thì lượt đầu mới đi đúng đường.
    Phiên chat thường vẫn mint id ở client như cũ; route này chỉ cho kênh cộng sự."""
    ch = (channel or "").strip()
    m = _KENH_CONG_SU_RE.match(ch)
    if not m:
        return JSONResponse({"error": "channel phải là agent:<slug> hoặc workflow:<slug>"}, status_code=400)
    loai, slug = m.group(1), m.group(2)
    thu_muc = _agents_dir(brain) if loai == "agent" else _workflows_dir(brain)
    if not (thu_muc / f"{slug}.md").exists():
        return JSONResponse({"error": f"{loai} '{slug}' không có trong brain này"}, status_code=404)
    store = get_store()
    sid = store.create_session(brain=_brain_key(brain), engine="cli", channel=ch)
    if loai == "agent":
        meta, _ = _read_md(thu_muc / f"{slug}.md")
        mdl, prov = (meta.get("model") or "").strip(), (meta.get("model_provider") or "").strip()
        if mdl and prov:
            try:
                store.set_pinned_model(sid, prov, mdl)
            except Exception:
                pass
    return {"id": sid, "channel": ch}
```

Route này cần đăng nhập như các route `/sessions` khác (không thêm vào danh sách miễn auth).

- [ ] **Step 5: Hoàn tất `agents_index.last_chat_at` (Task 2 Step 4) nếu chưa, rồi chạy test**

Run: `python tests/run.py sessions_kenh_cong_su` và `python tests/run.py telegram_sessions`
Expected: xanh; test cũ không đổi.

- [ ] **Step 6: Commit**

```bash
git add server/sessions.py server/main.py tests/python/test_sessions_kenh_cong_su.py
git commit -m "Phiên chat theo kênh agent:/workflow:, POST /sessions/new

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Module thuần `server/workflow_chat.py` (ghép đầu vào, dựng tin, tiêu thụ sự kiện)

**Files:**
- Create: `server/workflow_chat.py`
- Test: `tests/python/test_workflow_chat.py`

**Interfaces:**
- Produces:
  - `persona_cua_phien(row) -> tuple[str, str] | None` ("agent"|"workflow", slug)
  - `ghep_dau_vao(user_message, ket_qua_truoc) -> str`
  - `tin_xong(so_lan, so_buoc, giay, ket_qua) -> str`
  - `tin_loi(i, agent, loi) -> str`
  - `tin_cho_duyet(node, prompt) -> str`
  - `async chay(events, emit) -> dict` với khoá `trang_thai` ("done"|"error"|"waiting"), `ket_qua`, `so_buoc`, `loi` ({"i","agent","content"} hoặc None), `wait` (dict sự kiện wait_user hoặc None), `run_id`
  - Hằng `TRAN_KET_QUA_TRUOC = 8000`

- [ ] **Step 1: Viết test đỏ**

```python
"""workflow_chat: phần thuần của "chạy quy trình như một lượt chat".

    python tests/run.py workflow_chat
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import sys

import workflow_chat as wc  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


# persona
check("persona agent", wc.persona_cua_phien({"channel": "agent:nguoi-viet"}) == ("agent", "nguoi-viet"))
check("persona workflow", wc.persona_cua_phien({"channel": "workflow:viet-bai"}) == ("workflow", "viet-bai"))
check("persona web/None/rong", wc.persona_cua_phien({"channel": "web"}) is None and wc.persona_cua_phien(None) is None
      and wc.persona_cua_phien({"channel": "agent:"}) is None)

# ghép đầu vào
check("ghep khong co ket qua truoc", wc.ghep_dau_vao("viết về A", "") == "viết về A")
g = wc.ghep_dau_vao("sửa đoạn 2", "x" * 9000)
check("ghep co ket qua truoc, cat 8000", g.startswith("sửa đoạn 2\n\n# Kết quả lần trước\n") and g.endswith("x" * 8000)
      and len(g) == len("sửa đoạn 2\n\n# Kết quả lần trước\n") + 8000)

# tin
check("tin_xong", wc.tin_xong(2, 3, 42, "bài") == "Lần chạy #2 · 3 bước · 42 giây\n\nbài")
check("tin_xong rong", "không có nội dung" in wc.tin_xong(1, 1, 0, ""))
check("tin_loi", wc.tin_loi(1, "Người viết", "engine chết") == "Quy trình dừng ở bước 2 (Người viết): engine chết")
check("tin_loi khong ro buoc", wc.tin_loi(None, "", "hỏng") == "Quy trình dừng vì lỗi: hỏng")
check("tin_cho_duyet", wc.tin_cho_duyet("dang", "đăng bài?") ==
      "Quy trình đang chờ duyệt bước \"dang\": đăng bài?. Bấm Duyệt ở cột phải để chạy tiếp.")
check("tin_cho_duyet khong prompt", wc.tin_cho_duyet("dang", "") ==
      "Quy trình đang chờ duyệt bước \"dang\". Bấm Duyệt ở cột phải để chạy tiếp.")


# chay(): tiêu thụ sự kiện, emit đúng khung
async def gia(evs):
    for e in evs:
        yield e


def run(evs):
    frames = []

    async def emit(f):
        frames.append(f)
    kq = asyncio.run(wc.chay(gia(evs), emit))
    return kq, frames


kq, fr = run([
    {"type": "start", "workflow": "W", "steps": 2, "run_id": "r1"},
    {"type": "step_start", "i": 0, "agent": "A", "task": "t"},
    {"type": "step_text", "i": 0, "content": "abc"},
    {"type": "step_done", "i": 0, "agent": "A", "output": "o0"},
    {"type": "step_start", "i": 1, "agent": "B", "task": "t2"},
    {"type": "step_done", "i": 1, "agent": "B", "output": "o1"},
    {"type": "done", "result": "o1"},
])
check("chay done", kq["trang_thai"] == "done" and kq["ket_qua"] == "o1" and kq["so_buoc"] == 2 and kq["run_id"] == "r1")
loai = [f["type"] for f in fr]
check("chay emit wf_event cho moi su kien tru step_text", loai.count("wf_event") == 6
      and not any(f.get("type") == "wf_event" and f.get("event", {}).get("type") == "step_text" for f in fr))
st = [f for f in fr if f["type"] == "status"]
check("chay emit status moi buoc", [f["content"] for f in st] == ["Bước 1/2: A đang làm...", "Bước 2/2: B đang làm..."])

kq, fr = run([
    {"type": "start", "workflow": "W", "steps": 1},
    {"type": "step_start", "i": 0, "agent": "A", "task": "t"},
    {"type": "step_error", "i": 0, "content": "engine chết"},
    {"type": "error", "content": "dừng"},
])
check("chay error giu buoc + agent", kq["trang_thai"] == "error" and kq["loi"] == {"i": 0, "agent": "A", "content": "dừng"})

kq, fr = run([
    {"type": "start", "workflow": "W", "steps": 2},
    {"type": "wait_user", "node": "dang", "prompt": "?", "task_id": "tk", "code": "AB"},
])
check("chay waiting", kq["trang_thai"] == "waiting" and kq["wait"]["task_id"] == "tk" and kq["wait"]["code"] == "AB")

kq, fr = run([{"type": "start", "workflow": "W", "steps": 1}])
check("chay luong dut -> error", kq["trang_thai"] == "error" and "không kết thúc" in kq["loi"]["content"])


# chay() đóng generator khi bị huỷ
class Dem:
    dong = False


async def gia_cham():
    try:
        yield {"type": "start", "workflow": "W", "steps": 1}
        await asyncio.sleep(10)
        yield {"type": "done", "result": ""}
    finally:
        Dem.dong = True


async def huy():
    async def emit(f):
        pass
    t = asyncio.ensure_future(wc.chay(gia_cham(), emit))
    await asyncio.sleep(0.05)
    t.cancel()
    try:
        await t
    except asyncio.CancelledError:
        return True
    return False

check("chay bi huy thi dong generator", asyncio.run(huy()) and Dem.dong)

print("\nFAIL:" if fails else "\nOK - workflow_chat", fails or "")
sys.exit(1 if fails else 0)
```

- [ ] **Step 2: Chạy test, phải đỏ**

Run: `python tests/run.py workflow_chat`
Expected: ModuleNotFoundError: workflow_chat

- [ ] **Step 3: Viết `server/workflow_chat.py`**

```python
"""Chat với cộng sự: phần THUẦN (không I/O) của trang Cộng sự.

Hai việc:
1. `persona_cua_phien`: đọc cột `channel` của một phiên ra ("agent"|"workflow", slug). main.py
   dùng nó ở bộ điều phối lượt để rẽ nhánh: phiên trợ lý đổi system prompt, phiên quy trình
   chạy `execute_workflow` thay vì hỏi bộ não chính.
2. Quy trình chạy như một lượt chat: `chay()` tiêu thụ luồng sự kiện của execute_workflow,
   đẩy khung WebSocket cho khung chat (status) và cột phải (wf_event), rồi trả về kết quả
   để main.py dựng tin trả lời bằng `tin_xong` / `tin_loi` / `tin_cho_duyet`. Tách khỏi
   main.py để test được bằng một generator giả, không cần engine.

Luật quan trọng: một lần chạy KHÔNG BAO GIỜ kết thúc mà không có tin trong chat. Luồng đứt
(engine chết không kịp phát `error`) vẫn thành `trang_thai="error"` với câu lỗi rõ.

Ghi chú: KHÔNG dùng ký tự em dash.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

TRAN_KET_QUA_TRUOC = 8000
_LOAI = ("agent", "workflow")


def persona_cua_phien(row: Optional[dict]) -> Optional[Tuple[str, str]]:
    ch = str((row or {}).get("channel") or "")
    for loai in _LOAI:
        tien_to = loai + ":"
        if ch.startswith(tien_to) and len(ch) > len(tien_to):
            return loai, ch[len(tien_to):]
    return None


def ghep_dau_vao(user_message: str, ket_qua_truoc: str) -> str:
    """Tin sau trong cùng hội thoại vẫn hiểu được "sửa đoạn 2": nối kết quả lần trước vào."""
    u = str(user_message or "")
    k = str(ket_qua_truoc or "")
    if not k:
        return u
    return f"{u}\n\n# Kết quả lần trước\n{k[:TRAN_KET_QUA_TRUOC]}"


def tin_xong(so_lan: int, so_buoc: int, giay: int, ket_qua: str) -> str:
    than = str(ket_qua or "").strip() or "(quy trình xong nhưng không có nội dung)"
    return f"Lần chạy #{int(so_lan)} · {int(so_buoc)} bước · {int(giay)} giây\n\n{than}"


def tin_loi(i: Optional[int], agent: str, loi: str) -> str:
    loi = str(loi or "").strip() or "không rõ lý do"
    if i is None:
        return f"Quy trình dừng vì lỗi: {loi}"
    ten = f" ({agent})" if agent else ""
    return f"Quy trình dừng ở bước {int(i) + 1}{ten}: {loi}"


def tin_cho_duyet(node: str, prompt: str) -> str:
    p = str(prompt or "").strip()
    dau = f"Quy trình đang chờ duyệt bước \"{node}\""
    return (dau + (f": {p}" if p else "") + ". Bấm Duyệt ở cột phải để chạy tiếp.")


async def chay(events, emit: Callable[[dict], Awaitable[None]]) -> Dict[str, Any]:
    """Tiêu thụ luồng sự kiện của một lần chạy. `emit(frame)` gửi khung về trình duyệt.

    Khung phát ra:
    - `status` mỗi khi một bước bắt đầu (chip "đang làm" của khung chat);
    - `wf_event` cho MỌI sự kiện trừ `step_text` (cột phải vẽ tiến độ; step_text quá dày và
      cột phải không hiện chữ từng bước).
    Không phát `stream`: main.py gửi cả tin trả lời một lần sau khi có kết quả, để bong bóng
    sống và bản lưu giống hệt nhau.
    """
    kq: Dict[str, Any] = {"trang_thai": "error", "ket_qua": "", "so_buoc": 0, "loi": None,
                          "wait": None, "run_id": ""}
    agent_cua_buoc: Dict[int, str] = {}
    buoc_dang_chay: Optional[int] = None
    da_ket = False
    try:
        async for ev in events:
            t = ev.get("type")
            if t == "start":
                kq["so_buoc"] = int(ev.get("steps") or 0)
                kq["run_id"] = str(ev.get("run_id") or "")
            elif t == "step_start":
                i = int(ev.get("i") or 0)
                buoc_dang_chay = i
                agent_cua_buoc[i] = str(ev.get("agent") or "")
                tong = kq["so_buoc"] or (i + 1)
                await emit({"type": "status", "content": f"Bước {i + 1}/{tong}: {agent_cua_buoc[i]} đang làm..."})
            elif t == "done":
                kq["trang_thai"] = "done"
                kq["ket_qua"] = str(ev.get("result") or "")
                da_ket = True
            elif t == "error":
                kq["trang_thai"] = "error"
                kq["loi"] = {"i": buoc_dang_chay, "agent": agent_cua_buoc.get(buoc_dang_chay or -1, ""),
                             "content": str(ev.get("content") or "")}
                da_ket = True
            elif t == "wait_user":
                kq["trang_thai"] = "waiting"
                kq["wait"] = dict(ev)
                da_ket = True
            if t != "step_text":
                await emit({"type": "wf_event", "event": dict(ev)})
    finally:
        aclose = getattr(events, "aclose", None)
        if aclose:
            try:
                await aclose()
            except Exception:
                pass
    if not da_ket:
        kq["trang_thai"] = "error"
        kq["loi"] = {"i": buoc_dang_chay, "agent": agent_cua_buoc.get(buoc_dang_chay or -1, ""),
                     "content": "luồng chạy không kết thúc (engine dừng mà không báo)"}
    return kq
```

- [ ] **Step 4: Chạy test, phải xanh**

Run: `python tests/run.py workflow_chat`
Expected: OK - workflow_chat

- [ ] **Step 5: Commit**

```bash
git add server/workflow_chat.py tests/python/test_workflow_chat.py
git commit -m "workflow_chat: phần thuần của chat với quy trình

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Phiên trợ lý đổi system prompt trong `_do_turn`

**Files:**
- Modify: `server/main.py`: thêm `_agent_chat_prompt` gần `_workflow_agent_helpers` (:7348); sửa `_do_turn` (:10870 trở đi: `_row0`, `_legacy_system_prompt` :10948, `_subscription_system_prompt` :10960, chỗ `_phase8_plan.action == "use"` :11536, chỗ lưu lượt :11819)
- Test: `tests/python/test_agent_chat_prompt.py`

**Interfaces:**
- Consumes: `workflow_chat.persona_cua_phien` (Task 4), `_workflow_agent_helpers` (có sẵn), `_log_agent_run`, `_ghi_bai_hoc`/`_boc_bai_hoc` (có sẵn)
- Produces: `_agent_chat_prompt(brain, slug) -> str` (ném `FileNotFoundError` nếu trợ lý không có file); `_ket_luot_agent(brain, slug, user_message, final_text) -> str` (bóc JAVIS_LESSON, ghi bộ nhớ + nhật ký, trả text sạch)

- [ ] **Step 1: Viết test đỏ**

```python
"""Chat với một trợ lý ở trang Cộng sự: system prompt là prompt của trợ lý, không phải Javis.

    python tests/run.py agent_chat_prompt

Không chạy engine. Kiểm hai hàm thuần trong main.py và canh (bằng đọc mã) rằng bộ điều
phối lượt rẽ nhánh theo persona ở đủ các chỗ chọn prompt.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import re
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-agchat-")

import main  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


# Brain tạm (xem ghi chú Task 3 về biến env chọn thư mục brains; đặt TRƯỚC import main nếu cần)
ag_dir = main._agents_dir("brain"); ag_dir.mkdir(parents=True, exist_ok=True)
(ag_dir / "nguoi-viet.md").write_text("---\nname: Người viết\nrole: viết bài\nskills: [viet-email]\n---\nViết súc tích.\n",
                                       encoding="utf-8")

p = main._agent_chat_prompt("brain", "nguoi-viet")
check("prompt la cua tro ly", "Bạn là agent **Người viết**" in p and "Viết súc tích." in p and "JAVIS_LESSON" in p)
check("prompt noi ro dang chat truc tiep", "trò chuyện trực tiếp" in p)
check("prompt KHONG keo CLAUDE.md cua Javis", "SWAPPABLE BRAIN" not in p and "# === LỚP AGENTIC" not in p)
try:
    main._agent_chat_prompt("brain", "khong-co")
    check("tro ly khong co -> FileNotFoundError", False)
except FileNotFoundError:
    check("tro ly khong co -> FileNotFoundError", True)

sach = main._ket_luot_agent("brain", "nguoi-viet", "viết giúp", "Bài đây.\nJAVIS_LESSON: chủ thích câu ngắn")
check("ket luot boc JAVIS_LESSON", sach.strip() == "Bài đây.")
mem = (main._brain_memory_dir("brain") / "agents" / "nguoi-viet" / "MEMORY.md")
check("bai hoc vao bo nho agent", mem.exists() and "chủ thích câu ngắn" in mem.read_text(encoding="utf-8"))
runs = list((main._brain_memory_dir("brain") / "agents" / "nguoi-viet" / "runs").glob("*.md"))
check("nhat ky run cua agent co dong", runs and "viết giúp" in runs[0].read_text(encoding="utf-8"))

# Canh mã: _do_turn rẽ theo persona ở các chỗ chọn prompt
src = (SERVER / "main.py").read_text(encoding="utf-8")
than = src[src.index("async def _do_turn("):src.index("async def run_turn(")]
check("_do_turn doc persona tu phien", "_persona = workflow_chat.persona_cua_phien(_row0)" in than)
check("_legacy_system_prompt dung prompt tro ly", "_agent_chat_prompt(brain, _persona[1])" in than)
check("_subscription_system_prompt bo qua nen ngu canh khi co persona",
      re.search(r"def _subscription_system_prompt\(.*?\):\s*\"\"\".*?\"\"\"\s*if _persona:\s*return _legacy_system_prompt\(\), None", than, re.S) is not None)
check("nhanh phase8 API khong dung plan khi co persona", 'action == "use" and not _persona' in than)
check("cuoi luot goi _ket_luot_agent", "_ket_luot_agent(brain, _persona[1], user_message, final_text)" in than)

print("\nFAIL:" if fails else "\nOK - agent_chat_prompt", fails or "")
sys.exit(1 if fails else 0)
```

- [ ] **Step 2: Chạy test, phải đỏ**

Run: `python tests/run.py agent_chat_prompt`
Expected: AttributeError: _agent_chat_prompt

- [ ] **Step 3: Thêm hai hàm vào main.py ngay dưới `_workflow_agent_helpers`**

```python
def _agent_chat_prompt(brain, slug) -> str:
    """System prompt khi CHỦ chat trực tiếp với một trợ lý ở trang Cộng sự.

    Là ĐÚNG prompt mà workflow dùng cho trợ lý đó (vai, thân file, kỹ năng, bộ nhớ riêng, luật
    JAVIS_LESSON), cộng một câu nói rõ đây là trò chuyện chứ không phải một bước quy trình.
    Cố ý KHÔNG nối CLAUDE.md, bộ nhớ của chủ hay khối kênh: người dùng đang muốn nói chuyện với
    "Người viết", không phải với Javis đội mũ Người viết.
    """
    if not (_agents_dir(brain) / f"{slug}.md").exists():
        raise FileNotFoundError(slug)
    _mk, _agent_sysprompt, _log, _learn = _workflow_agent_helpers(brain, None)
    _name, sysprompt, _model, _prov = _agent_sysprompt(slug)
    return (sysprompt + "\n\n# Kênh: bạn đang trò chuyện trực tiếp với chủ trên dashboard Javis "
            "(trang Cộng sự). Trả lời như đang nói chuyện, theo ngôn ngữ chủ đang dùng; "
            "không cần báo cáo dạng nhiệm vụ trừ khi được giao việc cụ thể.")


def _ket_luot_agent(brain, slug, user_message, final_text) -> str:
    """Cuối một lượt chat với trợ lý: bóc JAVIS_LESSON vào bộ nhớ trợ lý, ghi nhật ký chạy của
    trợ lý (memory/agents/<slug>/runs), trả về text SẠCH để lưu phiên và hiện lên chat."""
    _mk, _agent_sysprompt, _log, _learn = _workflow_agent_helpers(brain, None)
    sach = _learn(slug, final_text or "")
    _log(slug, user_message or "", sach or "")
    return sach
```

- [ ] **Step 4: Rẽ nhánh trong `_do_turn`**

(a) Ngay sau dòng `_row0 = store.get_session(conv_sid) or {}` thêm:

```python
            # Phiên cộng sự (trang Cộng sự, 0.59): kênh agent:<slug> đổi system prompt sang prompt
            # của trợ lý đó. Đọc MỘT lần ở đây, mọi chỗ chọn prompt bên dưới đều hỏi `_persona`.
            _persona = workflow_chat.persona_cua_phien(_row0)
            if _persona and _persona[0] == "agent" and not (_agents_dir(brain) / f"{_persona[1]}.md").exists():
                await ws.send_text(json.dumps({"type": "error",
                    "content": f"Trợ lý '{_persona[1]}' không còn trong brain này. Mở trang Cộng sự để chọn trợ lý khác."}))
                return ""
```

Thêm `import workflow_chat` ở khối import đầu main.py (cạnh `import chatbot_runtime`).

(b) `_legacy_system_prompt`:

```python
            def _legacy_system_prompt():
                nonlocal sysprompt
                if sysprompt is None:
                    if _persona and _persona[0] == "agent":
                        sysprompt = _agent_chat_prompt(brain, _persona[1])
                    else:
                        sysprompt = build_system_prompt(
                            brain, lang=_lang_qd, project_id=_row0.get("project_id") or "",
                            session_id=conv_sid or ""
                        ) + channel_context.build_channel_block(
                            "dashboard", {"session_id": conv_sid}, telegram_running=bool(_TG_BOT),
                            port=_javis_port(), brain_root=_brain_root(brain),
                        )
                return sysprompt
```

(c) `_subscription_system_prompt`: dòng đầu tiên SAU docstring:

```python
                if _persona:
                    return _legacy_system_prompt(), None
```

(d) Tại dòng ~11536 (`... if _phase8_plan.action == "use" else _legacy_system_prompt()`), đổi điều kiện thành `if _phase8_plan.action == "use" and not _persona else _legacy_system_prompt()`. Đọc 30 dòng quanh đó: nếu `_phase8_plan` được dựng bằng `prepare(...)` tốn công thì bọc cả việc dựng bằng `if not _persona`.

(e) Fast Path: grep `used_fast_path = True` trong `_do_turn`; điều kiện vào fast path thêm `and not _persona` (fast path bỏ memory và lịch sử, và dùng prompt riêng, không hợp với trợ lý).

(f) Chỗ lưu lượt (dòng ~11819 `if final_text:`), ngay TRƯỚC `await _persist_turn(...)`:

```python
                if _persona and _persona[0] == "agent":
                    final_text = _ket_luot_agent(brain, _persona[1], user_message, final_text)
```

(g) Kiểm `channel_context.strip_control_blocks` không xoá gì thêm; giữ nguyên.

- [ ] **Step 5: Chạy test**

Run: `python tests/run.py agent_chat_prompt` rồi `python tests/run.py agent_tu_boi_dap` và `python tests/run.py chat_runtime`
Expected: xanh; hai test cũ giữ nguyên.

- [ ] **Step 6: Commit**

```bash
git add server/main.py tests/python/test_agent_chat_prompt.py
git commit -m "Phiên agent:<slug> chat bằng prompt của chính trợ lý

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Lượt quy trình trong WebSocket (`run_workflow_turn`) + duyệt tiếp (`wf_resume`)

**Files:**
- Modify: `server/main.py`: trong `websocket_endpoint` (:10815): thêm `run_workflow_turn` cạnh `run_turn` (:11850); vòng nhận tin (:12150 trở đi): thêm action `wf_resume`, rẽ nhánh khi persona là workflow trước khi tạo `run_turn`
- Test: `tests/python/test_workflow_turn_ws.py`

**Interfaces:**
- Consumes: `workflow_chat.chay/ghep_dau_vao/tin_*` (Task 4), `execute_workflow(..., source="web")`, `execute_workflow_resume(..., source="web")` (Task 2), `workflow_runs.get_store()` (Task 1), `_persist_turn`, `_SendProxy`, `_CHAT_RUNTIME`
- Produces: khung WS `{"type":"wf_event","event":{...},"session_id"}`, `{"type":"status"}`, `{"type":"stream"}`, `{"type":"turn_done"}`; action client `{"action":"wf_resume","session_id","task_id","node","code"}`

- [ ] **Step 1: Viết test đỏ (kiểm bằng đọc mã + chạy hàm lõi qua monkeypatch)**

`run_workflow_turn` là closure trong `websocket_endpoint` nên không gọi thẳng được. Tách LÕI ra hàm module-level `_luot_quy_trinh(store, conv_sid, user_message, brain, slug, emit, resume=None) -> str` (trả text đã lưu), còn closure chỉ bọc trace, đăng ký job, `turn_done`. Test gọi `_luot_quy_trinh` với `execute_workflow` giả.

```python
"""Lượt quy trình trong WebSocket: mỗi tin ở phiên workflow:<slug> là một lần chạy.

    python tests/run.py workflow_turn_ws
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="javis-wfturn-")
os.environ["JAVIS_STATE_DIR"] = _TMP
os.environ["JAVIS_SESSIONS_DB"] = str(Path(_TMP) / "conv.db")

import main  # noqa: E402
import workflow_runs  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


store = main.get_store()
sid = store.create_session(brain=main._brain_key("brain"), engine="cli", channel="workflow:viet-bai")
goi = []


async def gia_execute(brain, slug, input="", tools=None, session_id="", source="other"):
    goi.append({"input": input, "source": source, "session_id": session_id})
    rid = workflow_runs.get_store().bat_dau(brain=main._brain_key(brain), slug=slug, name="Viết bài",
                                           input=input, source=source, session_id=session_id)
    yield {"type": "start", "workflow": "Viết bài", "steps": 1, "run_id": rid}
    yield {"type": "step_start", "i": 0, "agent": "Người viết", "task": "viết"}
    yield {"type": "step_done", "i": 0, "agent": "Người viết", "output": "BÀI 1"}
    workflow_runs.get_store().ket_thuc(rid, "done", output="BÀI 1")
    yield {"type": "done", "result": "BÀI 1"}


main.execute_workflow = gia_execute   # _luot_quy_trinh tra cứu qua module lúc gọi


def run(msg, resume=None):
    frames = []

    async def emit(f):
        frames.append(f)
    store.append_message(sid, "user", msg)
    text = asyncio.run(main._luot_quy_trinh(store, sid, msg, "brain", "viet-bai", emit, resume=resume))
    return text, frames


text, fr = run("viết về A")
check("tin tra loi co dong dau + ket qua", text.startswith("Lần chạy #1 · 1 bước · ") and text.endswith("\n\nBÀI 1"))
check("emit status, wf_event, stream (khong turn_done: closure lo)",
      [f["type"] for f in fr].count("status") == 1 and any(f["type"] == "wf_event" for f in fr)
      and fr[-1]["type"] == "stream" and fr[-1]["content"] == text)
msgs = store.get_messages(sid)
check("phien luu tin assistant", msgs[-1]["role"] == "assistant" and msgs[-1]["content"] == text)
check("lan dau khong noi ket qua truoc", goi[0]["input"] == "viết về A" and goi[0]["source"] == "web"
      and goi[0]["session_id"] == sid)

text2, _ = run("sửa ngắn lại")
check("lan hai noi ket qua truoc + dem lan chay", goi[1]["input"].startswith("sửa ngắn lại\n\n# Kết quả lần trước\nBÀI 1")
      and text2.startswith("Lần chạy #2"))


async def gia_loi(brain, slug, input="", tools=None, session_id="", source="other"):
    yield {"type": "start", "workflow": "Viết bài", "steps": 1}
    yield {"type": "step_start", "i": 0, "agent": "Người viết", "task": "viết"}
    yield {"type": "error", "content": "engine chết"}

main.execute_workflow = gia_loi
text3, fr3 = run("lại đi")
check("loi van thanh tin trong chat", text3 == "Quy trình dừng ở bước 1 (Người viết): engine chết"
      and store.get_messages(sid)[-1]["content"] == text3)


async def gia_cho(brain, slug, input="", tools=None, session_id="", source="other"):
    yield {"type": "start", "workflow": "Viết bài", "steps": 2}
    yield {"type": "wait_user", "node": "dang", "prompt": "đăng?", "task_id": "tk9", "code": "ZZ"}

main.execute_workflow = gia_cho
text4, fr4 = run("đăng bài")
check("cho duyet thanh tin + wf_event mang code", "chờ duyệt bước \"dang\"" in text4
      and any(f["type"] == "wf_event" and f["event"].get("code") == "ZZ" for f in fr4))


async def gia_resume(brain, slug, task_id, node_id, code, tools=None, session_id="", source="other"):
    goi.append({"resume": (task_id, node_id, code)})
    yield {"type": "start", "workflow": "Viết bài", "steps": 2}
    yield {"type": "step_start", "i": 1, "agent": "Người đăng", "task": "đăng"}
    yield {"type": "step_done", "i": 1, "agent": "Người đăng", "output": "ĐÃ ĐĂNG"}
    yield {"type": "done", "result": "ĐÃ ĐĂNG"}

main.execute_workflow_resume = gia_resume
text5, _ = run("Đã duyệt bước dang.", resume={"task_id": "tk9", "node": "dang", "code": "ZZ"})
check("resume goi execute_workflow_resume dung tham so", goi[-1].get("resume") == ("tk9", "dang", "ZZ")
      and text5.endswith("ĐÃ ĐĂNG"))

# Canh mã vòng nhận tin
src = (SERVER / "main.py").read_text(encoding="utf-8")
ws = src[src.index("async def websocket_endpoint("):src.index("@app.get(\"/tts/voices\")") if "@app.get(\"/tts/voices\")" in src else len(src)]
check("vong nhan tin re nhanh workflow", "run_workflow_turn(" in ws and 'action == "wf_resume"' in ws)

print("\nFAIL:" if fails else "\nOK - workflow_turn_ws", fails or "")
sys.exit(1 if fails else 0)
```

Nếu `@app.get("/tts/voices")` không nằm sau `websocket_endpoint` thì đổi mốc cắt sang một chuỗi chắc chắn nằm sau (vd `"# Phiên hội thoại - list / view / search"`).

- [ ] **Step 2: Chạy test, phải đỏ**

Run: `python tests/run.py workflow_turn_ws`
Expected: AttributeError: _luot_quy_trinh

- [ ] **Step 3: Thêm lõi module-level vào main.py (đặt ngay trên `_persist_turn`)**

```python
async def _luot_quy_trinh(store, conv_sid, user_message, brain, slug, emit, resume=None) -> str:
    """LÕI của một lượt ở phiên workflow:<slug>: chạy quy trình, đẩy khung về trình duyệt, lưu
    tin trả lời. Trả về text đã lưu. Không đăng ký job, không gửi turn_done: closure trong
    websocket_endpoint lo, để hàm này gọi được từ test với execute_workflow giả.

    `resume` = {"task_id","node","code"} khi người dùng bấm Duyệt: chạy tiếp lần đang chờ.
    Tra `execute_workflow` qua globals() LÚC GỌI để test thay được.
    """
    import workflow_runs
    st = workflow_runs.get_store()
    t0 = time.time()
    if resume:
        events = globals()["execute_workflow_resume"](
            brain, slug, resume["task_id"], resume["node"], resume["code"],
            session_id=conv_sid, source="web")
    else:
        truoc = st.gan_nhat(_brain_key(brain), slug=slug, session_id=conv_sid, status="done", limit=1)
        ket_truoc = ""
        if truoc:
            day_du = st.lay(truoc[0]["id"]) or {}
            ket_truoc = day_du.get("output", "")
        dau_vao = workflow_chat.ghep_dau_vao(user_message, ket_truoc)
        events = globals()["execute_workflow"](brain, slug, dau_vao, session_id=conv_sid, source="web")
    kq = await workflow_chat.chay(events, emit)
    giay = int(time.time() - t0)
    if kq["trang_thai"] == "done":
        so_lan = st.dem_theo_phien(conv_sid) or 1
        text = workflow_chat.tin_xong(so_lan, kq["so_buoc"], giay, kq["ket_qua"])
    elif kq["trang_thai"] == "waiting":
        w = kq["wait"] or {}
        text = workflow_chat.tin_cho_duyet(str(w.get("node") or ""), str(w.get("prompt") or ""))
    else:
        loi = kq["loi"] or {}
        text = workflow_chat.tin_loi(loi.get("i"), loi.get("agent", ""), loi.get("content", ""))
    await emit({"type": "stream", "content": text})
    await _persist_turn(store, conv_sid, brain, user_message, text)
    return text
```

Kiểm `time` đã import ở đầu main.py (grep `^import time`); nếu chưa thì thêm.

- [ ] **Step 4: Closure `run_workflow_turn` trong `websocket_endpoint`, ngay dưới `run_turn`**

```python
        async def run_workflow_turn(conv_sid, user_message, brain, turn_tag, runtime_trace, slug, resume=None):
            """Lượt ở phiên workflow:<slug>. Cùng khung với run_turn (trace, Dừng, turn_done)
            nhưng thân là _luot_quy_trinh. Lỗi bất ngờ vẫn thành một tin trong chat: luật của
            trang Cộng sự là chạy quy trình không bao giờ kết thúc trong im lặng."""
            ws = _SendProxy(conv_sid, runtime_trace)
            _trace_token = context_runtime.bind_trace(runtime_trace)

            async def emit(frame):
                await ws.send_text(json.dumps(frame, ensure_ascii=False))
            try:
                await _luot_quy_trinh(store, conv_sid, user_message, brain, slug, emit, resume=resume)
                _CONTEXT_RUNTIME.finish(runtime_trace, "COMPLETED")
            except asyncio.CancelledError:
                _CONTEXT_RUNTIME.finish(runtime_trace, "CANCELLED", "cancelled")
                _cau = "Đã dừng lần chạy này theo yêu cầu."
                try:
                    await _persist_turn(store, conv_sid, brain, user_message, _cau)
                except Exception:
                    pass
                await send_raw({"type": "system", "content": _cau, "session_id": conv_sid,
                                **context_runtime.event_fields(runtime_trace)})
            except Exception as e:
                _CONTEXT_RUNTIME.note_error(runtime_trace, type(e).__name__)
                _CONTEXT_RUNTIME.finish(runtime_trace, "FAILED", type(e).__name__)
                _cau = workflow_chat.tin_loi(None, "", f"{type(e).__name__}: {e}")
                try:
                    await _persist_turn(store, conv_sid, brain, user_message, _cau)
                except Exception:
                    pass
                await send_raw({"type": "error", "content": _cau, "session_id": conv_sid,
                                **context_runtime.event_fields(runtime_trace)})
            finally:
                context_runtime.reset_trace(_trace_token)
                await send_raw({"type": "turn_done", "session_id": conv_sid,
                                **context_runtime.event_fields(runtime_trace)})
```

Đọc phần `finally` của `run_turn` (dòng ~11876 trở đi) và sao y các việc dọn khác nó làm sau `turn_done` (vd `_CHAT_RUNTIME` gỡ job, cập nhật dải việc nền) vào `finally` này, để hai closure không lệch.

- [ ] **Step 5: Rẽ nhánh trong vòng nhận tin**

(a) Ngay sau `store.append_message(conv_sid, "user", user_message)` và khối tạo `turn_tag`/`runtime_trace`, TRƯỚC khối Voice V2 `_vconf`, thêm:

```python
            _pers = workflow_chat.persona_cua_phien(store.get_session(conv_sid) or {})
            if _pers and _pers[0] == "workflow":
                task = asyncio.create_task(run_workflow_turn(
                    conv_sid, user_message, brain, turn_tag, runtime_trace, _pers[1]))
                _CHAT_RUNTIME.register_job(
                    conv_sid, task, turn_tag,
                    runtime_task_id=runtime_trace.task_id if runtime_trace else "",
                    runtime_step_id=runtime_trace.step_id if runtime_trace else "",
                )
                continue
```

(b) Thêm action mới cạnh `if action == "stop":`:

```python
            if action == "wf_resume":
                # Nút Duyệt ở cột phải trang Cộng sự: chạy tiếp lần đang chờ, kết quả về cùng phiên.
                _sid = str(payload.get("session_id") or "")
                _row = store.get_session(_sid) or {}
                _pers = workflow_chat.persona_cua_phien(_row)
                if not (_pers and _pers[0] == "workflow"):
                    await send_raw({"type": "error", "session_id": _sid, "content": "Phiên này không phải phiên quy trình."})
                    continue
                if _CHAT_RUNTIME.get_job(_sid):
                    await send_raw({"type": "error", "session_id": _sid, "content": "Quy trình đang chạy, đợi xong đã."})
                    continue
                _node = str(payload.get("node") or "")
                _msg = f"Đã duyệt bước \"{_node}\"."
                store.append_message(_sid, "user", _msg)
                _brain_r = _row.get("brain") or payload.get("brain") or "brain"
                _tag = f"chat:{_sid[:12]}:{uuid.uuid4().hex[:8]}"
                _trace = _CONTEXT_RUNTIME.start_turn(_sid, _brain_r, "dashboard")
                task = asyncio.create_task(run_workflow_turn(
                    _sid, _msg, _brain_r, _tag, _trace, _pers[1],
                    resume={"task_id": str(payload.get("task_id") or ""), "node": _node,
                            "code": str(payload.get("code") or "")}))
                _CHAT_RUNTIME.register_job(_sid, task, _tag,
                    runtime_task_id=_trace.task_id if _trace else "",
                    runtime_step_id=_trace.step_id if _trace else "")
                continue
```

`_row.get("brain")` là khoá đã resolve (đường dẫn tuyệt đối); `_brain_root` nhận được cả đường dẫn tuyệt đối (xem `_brain_key`). Nếu không, dùng `payload.get("brain")` mà client gửi kèm.

- [ ] **Step 6: Chạy test**

Run: `python tests/run.py workflow_turn_ws` rồi `python tests/run.py chat_runtime` và `python tests/run.py viec_nen`
Expected: xanh.

- [ ] **Step 7: Commit**

```bash
git add server/main.py tests/python/test_workflow_turn_ws.py
git commit -m "Phiên workflow:<slug>: mỗi tin là một lần chạy, kết quả về chat

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Plugin `javis-workflow` + dòng "lần chạy gần nhất" trong system prompt

**Files:**
- Create: `system/plugins/javis-workflow/plugin.yaml`, `system/plugins/javis-workflow/plugin.py`
- Modify: `server/main.py` `_javis_capability_summary` (:9024)
- Test: `tests/python/test_javis_workflow_plugin.py`

**Interfaces:**
- Consumes: `workflow_runs.get_store()` (Task 1)
- Produces: tool `javis_workflow` (op `runs` [slug?, limit?], op `show` [id]); hàm `_dong_lan_chay_gan_nhat(brain) -> str` trong main.py

- [ ] **Step 1: Viết test đỏ**

```python
"""Plugin javis-workflow: Javis tra được lịch sử chạy quy trình từ mọi engine.

    python tests/run.py javis_workflow_plugin
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-wfplug-")

import workflow_runs  # noqa: E402
import plugins_host  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


spec = importlib.util.spec_from_file_location(
    "javis_workflow_plugin", ROOT / "system" / "plugins" / "javis-workflow" / "plugin.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

VAULT = tempfile.mkdtemp(prefix="javis-vault-")
B = str(Path(VAULT).resolve())
ctx = plugins_host.PluginContext("javis-workflow", "bundled", ROOT / "system/plugins/javis-workflow", VAULT)
m.register(ctx)
tool = ctx._tools[0]
check("dang ky tool javis_workflow readonly", tool["name"] == "javis_workflow" and tool["min_mode"] == "readonly")

st = workflow_runs.get_store()
r1 = st.bat_dau(brain=B, slug="viet-bai", name="Viết bài", input="A", source="web", session_id="s")
st.ghi_buoc(r1, 0, agent="Người viết", task="viết", output="xong A")
st.ket_thuc(r1, "done", output="BÀI A")
r2 = st.bat_dau(brain=B, slug="ban-tin", name="Bản tin", input="", source="kanban")
st.ket_thuc(r2, "error", error="engine chết")

h = tool["handler"]
out = asyncio.run(h({"op": "runs"}, ctx))
check("runs liet ke moi nhat truoc, co ten/trang thai/id", out.index("Bản tin") < out.index("Viết bài")
      and "lỗi" in out and "xong" in out and r1 in out and r2 in out)
out = asyncio.run(h({"op": "runs", "slug": "viet-bai"}, ctx))
check("runs loc slug", "Viết bài" in out and "Bản tin" not in out)
out = asyncio.run(h({"op": "show", "id": r1}, ctx))
check("show co dau vao, buoc, ket qua", "A" in out and "Người viết" in out and "BÀI A" in out)
check("show id la -> loi ro", "ERROR" in asyncio.run(h({"op": "show", "id": "xxx"}, ctx)))
check("op la -> loi ro", "ERROR" in asyncio.run(h({"op": "bay"}, ctx)))
ctx2 = plugins_host.PluginContext("javis-workflow", "bundled", ROOT / "system/plugins/javis-workflow", None)
check("khong co vault_root -> loi ro", "ERROR" in asyncio.run(h({"op": "runs"}, ctx2)))

# Dòng trong system prompt
import main  # noqa: E402
d = main._dong_lan_chay_gan_nhat(B)
check("dong lan chay gan nhat", d.startswith("Lần chạy quy trình gần nhất: Bản tin") and "lỗi" in d and "javis_workflow" in d)
check("brain chua chay -> rong", main._dong_lan_chay_gan_nhat("/khong-co") == "")
src = (SERVER / "main.py").read_text(encoding="utf-8")
than = src[src.index("def _javis_capability_summary("):src.index("def _skill_router_block(")]
check("capability summary goi dong lan chay", "_dong_lan_chay_gan_nhat(" in than)

print("\nFAIL:" if fails else "\nOK - javis_workflow_plugin", fails or "")
sys.exit(1 if fails else 0)
```

Trong `_dong_lan_chay_gan_nhat(B)`, test truyền `B` là đường dẫn tuyệt đối đã resolve; hàm phải khoá bằng `_brain_key(brain)` và `_brain_key` với đường dẫn tuyệt đối phải trả về chính nó (xem `_brain_root`). Nếu `_brain_root` từ chối đường dẫn ngoài thư mục brains thì test dùng `main._brain_key("brain")` làm `B` và ghi bản ghi với khoá đó.

- [ ] **Step 2: Chạy test, phải đỏ**

Run: `python tests/run.py javis_workflow_plugin`
Expected: FileNotFoundError plugin.py

- [ ] **Step 3: Viết plugin**

`system/plugins/javis-workflow/plugin.yaml`:

```yaml
name: Lịch sử quy trình
slug: javis-workflow
version: 1.0.0
description: Xem các lần chạy quy trình gần đây và kết quả từng lần, ngay từ chat. Trước tool này, chạy quy trình xong là kết quả mất, hỏi "quy trình chạy gần nhất ra sao" Javis không có gì để tra.
author: Javis (bundled)
enabled: true
min_mode: readonly
tools:
  - javis_workflow
hooks: []
```

`system/plugins/javis-workflow/plugin.py`:

```python
"""Plugin bundled: tool `javis_workflow` - đọc lịch sử chạy quy trình, từ MỌI engine.

Vì sao tồn tại: kho `workflow_runs` (server/workflow_runs.py) ghi mọi lần chạy quy trình, nhưng
bộ não chính không có đường nào tới nó. Người dùng hỏi "quy trình vừa chạy ra sao" là Javis
trả lời trống, đúng lỗi chủ dự án báo 2026-09-15. Tool này chỉ ĐỌC (min_mode readonly), nên
chạy được cả ở chế độ suggest. Muốn chạy quy trình thì giao việc Kanban (javis_task, route
wf:<slug>) hoặc vào trang Cộng sự.

Khoá brain: kho ghi `_brain_key` = đường dẫn tuyệt đối đã resolve của brain, nên ở đây cũng
resolve `ctx.vault_root` cùng cách. `vault_root` rỗng thì báo lỗi rõ, không rơi về brain khác.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import workflow_runs

_LIST_MAX = 20
_TRAN_OUT = 6000     # kết quả cuối in ra tool: engine API cắt 8000, chừa chỗ cho phần còn lại


def _khoa(ctx) -> str:
    return str(Path(ctx.vault_root).resolve())


def _gio(ts: float) -> str:
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%H:%M %d/%m")
    except Exception:
        return "?"


def _liet_ke(args, ctx) -> str:
    if not ctx.vault_root:
        return "ERROR: chưa biết đang làm việc trên brain nào nên không xem được lịch sử."
    slug = str((args or {}).get("slug") or "").strip() or None
    try:
        limit = max(1, min(int((args or {}).get("limit") or 10), _LIST_MAX))
    except Exception:
        limit = 10
    ds = workflow_runs.get_store().gan_nhat(_khoa(ctx), slug=slug, limit=limit)
    if not ds:
        return "Chưa có lần chạy quy trình nào" + (f" của '{slug}'" if slug else "") + "."
    dong = []
    for r in ds:
        dong.append(f"- {_gio(r['started_at'])} · {r['name']} ({r['slug']}) · {r['nhan']} · nguồn {r['source']}"
                    f" · id {r['id']}" + (f"\n  {r['output_tom_tat']}" if r.get("output_tom_tat") else "")
                    + (f"\n  lỗi: {r['error']}" if r.get("error") else ""))
    dong.append("Xem đủ một lần: op=show với id ở trên.")
    return "\n".join(dong)


def _xem(args, ctx) -> str:
    rid = str((args or {}).get("id") or "").strip()
    if not rid:
        return "ERROR: op=show cần id của lần chạy (lấy từ op=runs)."
    r = workflow_runs.get_store().lay(rid)
    if not r:
        return f"ERROR: không có lần chạy id {rid}."
    ra = [f"{r['name']} ({r['slug']}) · {r['nhan']} · bắt đầu {_gio(r['started_at'])}"
          + (f" · xong {_gio(r['finished_at'])}" if r.get("finished_at") else ""),
          f"Đầu vào: {r['input'] or '(trống)'}"]
    for s in r.get("steps") or []:
        kc = "" if s.get("verified") is None else (" · kiểm chứng đạt" if s.get("verified") else " · kiểm chứng CHƯA đạt")
        ra.append(f"Bước {int(s.get('i', 0)) + 1} · {s.get('agent') or '?'}{kc}: {s.get('task') or ''}")
        if s.get("output"):
            ra.append("  -> " + str(s["output"])[:800])
        if s.get("error"):
            ra.append("  lỗi: " + str(s["error"]))
    if r.get("error"):
        ra.append(f"Lỗi: {r['error']}")
    ra.append("Kết quả cuối:\n" + (str(r.get("output") or "")[:_TRAN_OUT] or "(không có)"))
    return "\n".join(ra)


async def _chay(args, ctx) -> str:
    op = str((args or {}).get("op") or "").strip().lower()
    if op == "runs":
        return _liet_ke(args, ctx)
    if op == "show":
        return _xem(args, ctx)
    return "ERROR: op phải là 'runs' (liệt kê lần chạy) hoặc 'show' (xem một lần)."


def register(ctx):
    ctx.register_tool(
        "javis_workflow",
        "Lịch sử chạy quy trình (workflow). op=runs: các lần chạy gần nhất, mới trước, lọc theo "
        "slug nếu có, limit mặc định 10. op=show: một lần chạy đầy đủ (đầu vào, từng bước, kết quả) "
        "theo id. Dùng khi người dùng hỏi quy trình vừa chạy ra sao, kết quả lần trước, hay quy "
        "trình nào đang chờ duyệt. Chỉ đọc; muốn chạy quy trình thì dùng javis_task với route "
        "wf:<slug> hoặc trang Cộng sự.",
        _chay,
        schema={
            "type": "object",
            "properties": {
                "op": {"type": "string", "enum": ["runs", "show"]},
                "slug": {"type": "string", "description": "Lọc theo quy trình (op=runs)"},
                "limit": {"type": "integer", "description": "Số lần tối đa (op=runs)"},
                "id": {"type": "string", "description": "Id lần chạy (op=show)"},
            },
            "required": ["op"],
        },
        min_mode="readonly",
        emoji="🧾",
    )
```

- [ ] **Step 4: Dòng trong system prompt**

Trong main.py, ngay trên `_javis_capability_summary`:

```python
def _dong_lan_chay_gan_nhat(brain) -> str:
    """Một dòng cho system prompt: lần chạy quy trình gần nhất của brain, rỗng nếu chưa có.
    Nhờ dòng này, hỏi "quy trình chạy gần nhất ra sao" ở khung chat chính là Javis biết ngay
    có gì để tra và tra bằng tool nào."""
    try:
        import workflow_runs
        from datetime import datetime
        ds = workflow_runs.get_store().gan_nhat(_brain_key(brain), limit=1)
    except Exception:
        return ""
    if not ds:
        return ""
    r = ds[0]
    try:
        luc = datetime.fromtimestamp(float(r["started_at"])).strftime("%H:%M %d/%m")
    except Exception:
        luc = "?"
    return (f"Lần chạy quy trình gần nhất: {r['name']} lúc {luc} ({r['nhan']}). "
            "Chi tiết hay các lần khác: tool javis_workflow (op=runs, op=show).")
```

Trong `_javis_capability_summary`, sau khối `if c["workflows"]:`:

```python
    _lc = _dong_lan_chay_gan_nhat(brain)
    if _lc:
        parts.append(_lc)
```

- [ ] **Step 5: Chạy test**

Run: `python tests/run.py javis_workflow_plugin` rồi `python tests/run.py plugins_host`
Expected: xanh.

- [ ] **Step 6: Commit**

```bash
git add system/plugins/javis-workflow server/main.py tests/python/test_javis_workflow_plugin.py
git commit -m "Tool javis_workflow + dòng lần chạy gần nhất trong system prompt

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Đăng ký trang `workspace`, gỡ hai trang cũ, bí danh, từ điển

**Files:**
- Modify: `dashboard/console.js` (`VIEW_ICON` :27, `RAIL_ITEMS` :81, `RAIL_GROUPS` :104, `VIEW_META` :150, `STUDIO_PAGES` :163, `TRANG_GOP` :254, `renderPage` :396, `LOAI_KHO` :433)
- Modify: `dashboard/ui-actions.js:17`, `server/ui_targets.py` (`PAGES` :20, `ALIASES` :28)
- Modify: `dashboard/packs.js:191-193`, `dashboard/chatbots.js:699`
- Modify: `dashboard/i18n/vi.json`, `dashboard/i18n/en.json`
- Modify: `tests/python/test_ui_bridge.py:100-102`
- Test: `tests/js/test_ui_actions.js` (có sẵn), `tests/python/test_ui_bridge.py`

**Interfaces:**
- Produces: id trang `workspace`; `renderPage` gọi `renderWorkspace(el)` (viết ở Task 9, tạm placeholder trong task này); khoá i18n `page.workspace.label|title|sub`

- [ ] **Step 1: Sửa test kỳ vọng bí danh (đỏ trước)**

Trong `tests/python/test_ui_bridge.py` dòng 100-102 đổi kỳ vọng `"agents"` và `"workflows"` thành `"workspace"`, thêm một dòng:

```python
    check("resolve_page: 'cộng sự' -> workspace", m.resolve_page("cộng sự") == "workspace")
```

Run: `python tests/run.py ui_bridge` -> FAIL ở ba dòng đó.

- [ ] **Step 2: Sửa server/ui_targets.py**

`PAGES`: thay `"workflows", "agents"` bằng `"workspace"` (đúng vị trí của "workflows", bỏ "agents"):

```python
PAGES = (
    "home", "chat", "settings", "workspace", "skills", "chatbots", "files",
    "terminal", "selfimprove", "learn", "kanban", "models", "channels", "mcp", "plugins",
    "packs", "logs", "account", "usage", "pet",
)
```

`ALIASES`: đổi mọi giá trị `"workflows"` và `"agents"` thành `"workspace"`, thêm `"cong su": "workspace", "workspace": "workspace", "tro ly va quy trinh": "workspace"`. Thêm comment: trang Trợ lý và Quy trình gộp thành Cộng sự ở 0.59.0, bí danh cũ giữ để lệnh nói quen tay không chết.

- [ ] **Step 3: Sửa dashboard/ui-actions.js**

```js
  var PAGES = ["home", "chat", "settings", "workspace", "skills", "chatbots", "files",
               "terminal", "selfimprove", "learn", "kanban", "models", "channels", "mcp", "plugins",
               "packs", "logs", "account", "usage", "pet"];
```

- [ ] **Step 4: Sửa dashboard/console.js**

- `VIEW_ICON`: bỏ `workflows` và `agents`, thêm `workspace: "bot"` (icon `bot` có trong manifest; `users` không có, không thêm icon mới ở task này).
- `RAIL_ITEMS`: `"home", "chat", "settings", "workspace", "skills", "chatbots", "files", ...` (bỏ workflows, agents).
- `RAIL_GROUPS` nhóm `nang_luc`: `ids: ["workspace", "chatbots", "skills", "plugins"]`.
- `VIEW_META`: danh sách id thay tương ứng.
- `STUDIO_PAGES = ["skills"]`.
- `TRANG_GOP = { runtime: "usage", agents: "workspace", workflows: "workspace" }` với comment: hai trang gộp ở 0.59.0; ai bấm nút cũ trong chat hay bookmark vẫn tới nơi.
- `LOAI_KHO`: bỏ hai khoá `agents`, `workflows` (trang Cộng sự có nút Store riêng).
- `renderPage`: thêm dòng `if (id === "workspace") return renderWorkspace(el);` NGAY TRƯỚC dòng `STUDIO_PAGES`.
- Thêm hàm tạm (Task 9 thay thân thật):

```js
  // Trang Cộng sự: dựng bởi workspace.js, mượn khung chat như trang Trò chuyện.
  function renderWorkspace(el) {
    if (!window.JavisWorkspace) { el.innerHTML = placeholder("workspace", window.t("cs.mod_not_ready", { ten: "workspace.js" })); return; }
    _injectChatCss();
    if (_chatSlots.length) _returnChatNodes();
    document.body.classList.add("on-chat");
    window.JavisWorkspace.render(el, { borrow: _borrowChatNodes });
    _pageLeave = _returnChatNodes;
  }
```

- `packs.js:191-193`: `trang: "workspace"` cho `agent` và `workflow`.
- `chatbots.js:699`: `window.JavisNav.go("workspace")`.
- Grep toàn `dashboard/*.js` và `server/*.py` cho `"agents"`/`"workflows"` dùng như ID TRANG (không phải đường dẫn API `/agents`): còn chỗ nào thì đổi.

- [ ] **Step 5: Từ điển**

`vi.json`: bỏ 6 khoá `page.workflows.*`, `page.agents.*`; thêm:

```json
  "page.workspace.label": "Cộng sự",
  "page.workspace.title": "Cộng sự (Agents & Workflows)",
  "page.workspace.sub": "Trò chuyện với từng trợ lý, chạy quy trình, xem lại lịch sử",
```

`en.json`: `"Partners"`, `"Partners (Agents & Workflows)"`, `"Chat with each agent, run workflows, review run history"`. Kiểm `tests/js/test_i18n.mjs` (nó có thể canh hai file cùng bộ khoá).

- [ ] **Step 6: Chạy test**

Run: `node tests/js/test_ui_actions.js`, `python tests/run.py ui_bridge`, `node tests/js/test_i18n.mjs`, `node tests/js/test_nhom_agent_workflow.js`
Expected: xanh. Nếu `test_nhom_agent_workflow.js` canh trang `agents`/`workflows` bằng chuỗi trong console.js thì cập nhật kỳ vọng sang `workspace` (đọc test trước khi sửa).

- [ ] **Step 7: Commit**

```bash
git add dashboard/console.js dashboard/ui-actions.js dashboard/packs.js dashboard/chatbots.js dashboard/i18n/vi.json dashboard/i18n/en.json server/ui_targets.py tests/python/test_ui_bridge.py tests/js/test_nhom_agent_workflow.js
git commit -m "Trang Cộng sự thay hai trang Trợ lý và Quy trình trên thanh bên

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: `dashboard/workspace.js` (ba cột) + khung `wf_event` + trình sửa inline

**Files:**
- Create: `dashboard/workspace.js`
- Modify: `dashboard/index.html` (thêm `<script src="/static/workspace.js?v=1">` NGAY SAU `studio.js`, TRƯỚC `console.js`)
- Modify: `dashboard/app.js` (chuỗi `else if (data.type === "system")` ~:678: thêm nhánh `wf_event`)
- Modify: `dashboard/studio.js` (`editAgent(a)` :541, `editWorkflow(w)` :380, `window.JavisStudio` :76)
- Modify: `dashboard/i18n/vi.json`, `en.json` (khoá `ws.*`)
- Test: `tests/js/test_workspace.js`

**Interfaces:**
- Consumes: `POST /sessions/new`, `GET /sessions?channel=`, `GET /agents` (`last_chat_at`), `GET /workflows` (`last_run_at`), `GET /workflows/runs`, `window.JavisSessions.open/new/current/brain`, `window.JavisWsSend(obj)`, `window.JavisPacks.moKho(kind, fromPage, label)`, `window.JavisStudio.editAgent(a, opts)` / `editWorkflow(w, opts)`
- Produces: `window.JavisWorkspace = { render(el, {borrow}), onWfEvent(frame), state() }`; khung WS gửi `{"action":"wf_resume", session_id, task_id, node, code, brain}`

- [ ] **Step 1: Sửa studio.js để trình sửa vẽ được vào host bất kỳ**

Trong `editAgent(a)` đổi chữ ký thành `editAgent(a, opts)`; `opts = opts || {}`:
- `const box = opts.host || document.getElementById("editorBox");`
- Mọi `editor.classList.add("open")` / `remove("open")` thay bằng `moDong(true|false)` với `const moDong = (mo) => { if (!opts.host) editor.classList.toggle("open", mo); };`
- Nút Huỷ: `box.querySelector("#cancelEd").onclick = () => { if (opts.host) return; moDong(false); };` và khi có host thì ẩn nút Huỷ: thêm `style="display:none"` nếu `opts.host`.
- Sau lưu: `moDong(false); if (opts.onSaved) opts.onSaved(); else loadAgents();`
- Vì form dùng id (`#agName`...) và cả trang chỉ có MỘT form agent mở tại một lúc, giữ id.

`editWorkflow(w)` -> `editWorkflow(w, opts)`: sau lưu `editor.classList.remove("open"); if (opts && opts.onSaved) opts.onSaved(); else loadWorkflows();`. Modal `#studioEditor` vẫn dùng (nó nằm trong index.html toàn cục).

`window.JavisStudio` thêm `editAgent, editWorkflow, exportItem`.

- [ ] **Step 2: app.js chuyển khung `wf_event`**

Trong chuỗi `if/else` xử lý `data.type` (gần dòng 678), thêm TRƯỚC nhánh `"system"`:

```js
  } else if (data.type === "wf_event") {
    // Tiến độ từng bước của một lần chạy quy trình (trang Cộng sự vẽ ở cột phải). Khung chat
    // không vẽ gì: chip trạng thái đã đi bằng khung status riêng.
    try { if (window.JavisWorkspace) window.JavisWorkspace.onWfEvent(data); } catch (e) {}
```

- [ ] **Step 3: Viết test JS đỏ**

`tests/js/test_workspace.js`:

```js
/* Trang Cộng sự (dashboard/workspace.js): sắp xếp, chọn phiên, tiến độ quy trình.

       node tests/js/test_workspace.js

   Chạy dưới node với DOM giả tối thiểu: workspace.js phơi phần thuần qua window.JavisWorkspace. */
const fs = require("fs");
const path = require("path");
const root = path.join(__dirname, "..", "..");

global.window = { t: (k) => k, ic: () => "", addEventListener() {}, matchMedia: () => ({ matches: false }) };
global.document = { getElementById: () => null, createElement: () => ({ classList: { add() {}, remove() {} }, appendChild() {} }), body: { classList: { add() {}, remove() {} } } };
global.localStorage = { getItem: () => null, setItem() {} };
require(path.join(root, "dashboard", "workspace.js"));
const W = window.JavisWorkspace;

let fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

// Sắp xếp: mốc gần nhất lên đầu, chưa có mốc xếp sau theo tên
const wfs = [{ slug: "a", name: "Bản tin", last_run_at: 0 }, { slug: "b", name: "Viết bài", last_run_at: 50 }, { slug: "c", name: "Ads", last_run_at: 99 }, { slug: "d", name: "Zalo", last_run_at: 0 }];
check("xep quy trinh theo lan chay gan nhat", W.sapXep(wfs, "last_run_at").map(x => x.slug).join(",") === "c,b,a,d");
const ags = [{ slug: "x", name: "Người viết", last_chat_at: 0 }, { slug: "y", name: "Javis", last_chat_at: 3 }];
check("xep tro ly theo lan chat gan nhat", W.sapXep(ags, "last_chat_at").map(x => x.slug).join(",") === "y,x");

// Lọc: tìm không dấu + nhóm
const ds = [{ slug: "a", name: "Người viết", role: "viết", group: "Marketing" }, { slug: "b", name: "Kế toán", role: "sổ sách", group: "Finance" }];
check("loc theo chu khong dau", W.loc(ds, "nguoi viet", "").map(x => x.slug).join() === "a");
check("loc theo nhom", W.loc(ds, "", "Finance").map(x => x.slug).join() === "b");

// Tiến độ quy trình từ wf_event
const st = W.tienDoMoi(3);
W.apDung(st, { type: "step_start", i: 0, agent: "A" });
check("step_start -> buoc 0 dang lam", st.buoc[0].trang_thai === "dang" && st.hien_tai === 0);
W.apDung(st, { type: "step_done", i: 0 });
W.apDung(st, { type: "step_start", i: 1, agent: "B" });
check("step_done -> xong, sang buoc 1", st.buoc[0].trang_thai === "xong" && st.buoc[1].trang_thai === "dang");
W.apDung(st, { type: "wait_user", node: "dang", task_id: "tk", code: "AB" });
check("wait_user -> cho duyet + giu code", st.cho_duyet && st.cho_duyet.code === "AB" && st.trang_thai === "cho");
W.apDung(st, { type: "done" });
check("done -> xong het", st.trang_thai === "xong" && st.buoc.every(b => b.trang_thai === "xong"));
const st2 = W.tienDoMoi(2);
W.apDung(st2, { type: "step_start", i: 0, agent: "A" });
W.apDung(st2, { type: "error", content: "chết" });
check("error -> buoc dang lam thanh loi", st2.trang_thai === "loi" && st2.buoc[0].trang_thai === "loi");
check("phan tram", W.phanTram(W.tienDoMoi(4)) === 0 && W.phanTram(st) === 100);

// Dây nối
const app = fs.readFileSync(path.join(root, "dashboard", "app.js"), "utf8");
check("app.js chuyen wf_event sang JavisWorkspace", /data\.type === "wf_event"/.test(app) && /JavisWorkspace\.onWfEvent\(/.test(app));
const html = fs.readFileSync(path.join(root, "dashboard", "index.html"), "utf8");
check("index.html nap workspace.js sau studio.js, truoc console.js",
  html.indexOf("studio.js") < html.indexOf("workspace.js") && html.indexOf("workspace.js") < html.indexOf("console.js"));
const con = fs.readFileSync(path.join(root, "dashboard", "console.js"), "utf8");
check("console.js co renderWorkspace muon khung chat", /function renderWorkspace\(el\)/.test(con) && /JavisWorkspace\.render\(el, \{ borrow: _borrowChatNodes \}\)/.test(con));
const studio = fs.readFileSync(path.join(root, "dashboard", "studio.js"), "utf8");
check("studio.js editAgent nhan host + onSaved", /function editAgent\(a, opts\)/.test(studio) && /opts\.host/.test(studio) && /opts\.onSaved/.test(studio));

if (fails.length) { console.log("\nFAIL:", fails.length, fails); process.exit(1); }
console.log("\nOK - workspace");
```

Run: `node tests/js/test_workspace.js` -> FAIL (module chưa có).

- [ ] **Step 4: Viết `dashboard/workspace.js`**

```js
/* workspace.js - trang Cộng sự: chat với từng trợ lý và từng quy trình trên cùng khung chat.

   Ba cột: trái = danh sách (Trợ lý | Quy trình), giữa = khung chat MƯỢN của app (console.js
   mượn/trả node, file này chỉ nhận slot), phải = cài đặt trợ lý hoặc tiến độ + lịch sử chạy.

   Mỗi cộng sự có phiên riêng trong kho phiên (kênh agent:<slug> / workflow:<slug>). Gửi tin
   vẫn đi đường WebSocket thường của app.js; server nhìn kênh của phiên mà rẽ nhánh. Khung
   wf_event (tiến độ từng bước) app.js chuyển vào onWfEvent() ở đây.

   Phần thuần (sapXep, loc, tienDoMoi, apDung, phanTram) phơi ra để test bằng node.
   Ghi chú: KHÔNG dùng ký tự em dash. Chữ hiện ra lấy từ từ điển window.t. */
(function () {
  "use strict";
  var t = function (k, v) { return (window.t ? window.t(k, v) : k); };
  var ic = function (n, o) { return (window.ic ? window.ic(n, o) : ""); };
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]; }); }
  function khongDau(s) { return String(s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase(); }
  function brain() { try { return window.JavisSessions ? window.JavisSessions.brain() : "brain"; } catch (e) { return "brain"; } }
  async function api(url, opt) { var r = await fetch(url, opt); return r.json(); }
  function fd(o) { var f = new FormData(); Object.keys(o).forEach(function (k) { f.append(k, o[k]); }); return f; }

  // ---------- phần thuần ----------
  function sapXep(ds, khoa) {
    return ds.slice().sort(function (a, b) {
      var ma = Number(a[khoa] || 0), mb = Number(b[khoa] || 0);
      if (ma !== mb) return mb - ma;
      return String(a.name || "").localeCompare(String(b.name || ""), "vi");
    });
  }
  function loc(ds, q, nhom) {
    var nq = khongDau(q || "").trim();
    return ds.filter(function (x) {
      if (nhom && (x.group || "Chung") !== nhom) return false;
      if (!nq) return true;
      return khongDau([x.name, x.role, x.description, x.slug].join(" ")).indexOf(nq) >= 0;
    });
  }
  function tienDoMoi(n) {
    var buoc = [];
    for (var i = 0; i < n; i++) buoc.push({ i: i, agent: "", trang_thai: "cho", loi: "" });
    return { buoc: buoc, hien_tai: -1, trang_thai: "cho", cho_duyet: null, run_id: "" };
  }
  function apDung(st, ev) {
    var i = Number(ev.i);
    if (ev.type === "start") { st.run_id = ev.run_id || ""; if (Number(ev.steps) > st.buoc.length) { while (st.buoc.length < Number(ev.steps)) st.buoc.push({ i: st.buoc.length, agent: "", trang_thai: "cho", loi: "" }); } st.trang_thai = "dang"; }
    else if (ev.type === "step_start") { while (st.buoc.length <= i) st.buoc.push({ i: st.buoc.length, agent: "", trang_thai: "cho", loi: "" }); st.buoc[i].agent = ev.agent || st.buoc[i].agent; st.buoc[i].trang_thai = "dang"; st.hien_tai = i; st.trang_thai = "dang"; }
    else if (ev.type === "step_done") { if (st.buoc[i]) st.buoc[i].trang_thai = "xong"; }
    else if (ev.type === "step_error") { if (st.buoc[i]) { st.buoc[i].loi = ev.content || ""; } }
    else if (ev.type === "wait_user") { st.trang_thai = "cho"; st.cho_duyet = { node: ev.node || "", prompt: ev.prompt || "", task_id: ev.task_id || "", code: ev.code || "" }; }
    else if (ev.type === "error") { st.trang_thai = "loi"; if (st.hien_tai >= 0 && st.buoc[st.hien_tai] && st.buoc[st.hien_tai].trang_thai === "dang") { st.buoc[st.hien_tai].trang_thai = "loi"; st.buoc[st.hien_tai].loi = ev.content || ""; } }
    else if (ev.type === "done") { st.trang_thai = "xong"; st.cho_duyet = null; st.buoc.forEach(function (b) { b.trang_thai = "xong"; }); }
    return st;
  }
  function phanTram(st) {
    if (!st.buoc.length) return 0;
    if (st.trang_thai === "xong") return 100;
    return Math.round(st.buoc.filter(function (b) { return b.trang_thai === "xong"; }).length / st.buoc.length * 100);
  }

  // ---------- trạng thái trang ----------
  var S = { loai: "agent", q: "", nhom: "", agents: [], workflows: [], chon: { agent: null, workflow: null },
            el: null, tienDo: {}, sessionCuaPhien: {} };   // tienDo[session_id] = tiến độ lần chạy đang xem

  function danhSach() { return S.loai === "agent" ? S.agents : S.workflows; }
  function kenh(item) { return (S.loai === "agent" ? "agent:" : "workflow:") + item.slug; }
  function dangChon() { var slug = S.chon[S.loai]; return danhSach().find(function (x) { return x.slug === slug; }) || null; }

  async function taiDanhSach() {
    var b = encodeURIComponent(brain());
    var r = await Promise.all([api("/agents?brain=" + b), api("/workflows?brain=" + b)]);
    S.agents = sapXep(r[0].agents || [], "last_chat_at");
    S.workflows = sapXep((r[1].workflows || []).filter(function (w) { return w.status === "active"; }), "last_run_at");
  }

  // ---------- dựng khung ----------
  function render(el, opts) {
    S.el = el;
    el.innerHTML =
      '<div class="wspage" id="wsPage">' +
        '<aside class="ws-left" id="wsLeft">' +
          '<div class="ws-seg"><button type="button" data-loai="agent">' + ic("bot") + ' ' + esc(t("ws.tab_agent")) + '</button>' +
          '<button type="button" data-loai="workflow">' + ic("workflow") + ' ' + esc(t("ws.tab_workflow")) + '</button></div>' +
          '<input class="ws-search" id="wsSearch" placeholder="' + esc(t("ws.search_ph")) + '">' +
          '<select class="ws-group" id="wsGroup"></select>' +
          '<div class="ws-list" id="wsList"></div>' +
          '<div class="ws-left-foot"><button type="button" class="ws-btn" id="wsNew">' + ic("plus") + ' ' + esc(t("ws.new_item")) + '</button>' +
          '<button type="button" class="ws-btn" id="wsStore">' + ic("package") + ' Javis Store</button></div>' +
        '</aside>' +
        '<div class="ws-main">' +
          '<div class="ws-bar">' +
            '<button type="button" class="ws-ico" id="wsLeftBtn" title="' + esc(t("ws.toggle_list")) + '">' + ic("panel-left") + '</button>' +
            '<div class="ws-id" id="wsIdentity"></div>' +
            '<button type="button" class="ws-btn" id="wsNewChat">' + esc(t("sess.new_chat")) + '</button>' +
            '<button type="button" class="ws-ico" id="wsRightBtn" title="' + esc(t("ws.toggle_panel")) + '">' + ic("panel-right") + '</button>' +
          '</div>' +
          '<div class="ws-slot" id="wsSlot"></div>' +
        '</div>' +
        '<aside class="ws-right" id="wsRight"></aside>' +
      '</div>';
    if (opts && opts.borrow) opts.borrow(el.querySelector("#wsSlot"));
    el.querySelectorAll("[data-loai]").forEach(function (b) { b.onclick = function () { S.loai = b.dataset.loai; luuChon(); veTrai(); chonMacDinh(); }; });
    el.querySelector("#wsSearch").oninput = function (e) { S.q = e.target.value; veDanhSach(); };
    el.querySelector("#wsGroup").onchange = function (e) { S.nhom = e.target.value; veDanhSach(); };
    el.querySelector("#wsNew").onclick = taoMoi;
    el.querySelector("#wsStore").onclick = function () { if (window.JavisPacks && window.JavisPacks.moKho) window.JavisPacks.moKho(S.loai, "workspace", t("page.workspace.label")); };
    el.querySelector("#wsNewChat").onclick = function () { var x = dangChon(); if (x) moPhien(x, true); };
    el.querySelector("#wsLeftBtn").onclick = function () { el.querySelector("#wsPage").classList.toggle("left-open"); };
    el.querySelector("#wsRightBtn").onclick = function () { el.querySelector("#wsPage").classList.toggle("right-open"); };
    try { var l = localStorage.getItem("javis_ws_loai"); if (l === "agent" || l === "workflow") S.loai = l; S.chon.agent = localStorage.getItem("javis_ws_agent"); S.chon.workflow = localStorage.getItem("javis_ws_workflow"); } catch (e) {}
    taiDanhSach().then(function () { veTrai(); chonMacDinh(); });
  }
  function luuChon() { try { localStorage.setItem("javis_ws_loai", S.loai); if (S.chon.agent) localStorage.setItem("javis_ws_agent", S.chon.agent); if (S.chon.workflow) localStorage.setItem("javis_ws_workflow", S.chon.workflow); } catch (e) {} }

  function veTrai() {
    var el = S.el; if (!el) return;
    el.querySelectorAll("[data-loai]").forEach(function (b) { b.classList.toggle("on", b.dataset.loai === S.loai); });
    var nhoms = {}; danhSach().forEach(function (x) { nhoms[x.group || "Chung"] = 1; });
    var sel = el.querySelector("#wsGroup");
    sel.innerHTML = '<option value="">' + esc(t("ws.all_groups")) + '</option>' + Object.keys(nhoms).sort().map(function (g) { return '<option value="' + esc(g) + '"' + (g === S.nhom ? " selected" : "") + '>' + esc(g) + '</option>'; }).join("");
    el.querySelector("#wsNew").innerHTML = ic("plus") + " " + esc(S.loai === "agent" ? t("ws.new_agent") : t("ws.new_workflow"));
    veDanhSach();
  }
  function veDanhSach() {
    var el = S.el; if (!el) return;
    var ds = loc(danhSach(), S.q, S.nhom), chon = S.chon[S.loai];
    var host = el.querySelector("#wsList");
    if (!ds.length) { host.innerHTML = '<div class="ws-empty">' + esc(t("ws.empty")) + '</div>'; return; }
    host.innerHTML = ds.map(function (x) {
      var phu = S.loai === "agent" ? (x.group || "Chung") + " · " + (x.role || "") : (x.group || "Chung") + " · " + (x.steps || []).length + " " + t("studio.steps");
      return '<button type="button" class="ws-item' + (x.slug === chon ? " on" : "") + '" data-slug="' + esc(x.slug) + '">' +
        '<span class="ws-item-ic">' + ic(S.loai === "agent" ? "bot" : "workflow") + '</span>' +
        '<span class="ws-item-text"><strong>' + esc(x.name) + '</strong><small>' + esc(phu) + '</small></span></button>';
    }).join("");
    host.querySelectorAll("[data-slug]").forEach(function (b) { b.onclick = function () { S.chon[S.loai] = b.dataset.slug; luuChon(); veDanhSach(); moPhien(dangChon(), false); S.el.querySelector("#wsPage").classList.remove("left-open"); }; });
  }
  function chonMacDinh() {
    var ds = danhSach(); if (!ds.length) { veGiua(null); vePhai(null); return; }
    if (!ds.some(function (x) { return x.slug === S.chon[S.loai]; })) S.chon[S.loai] = ds[0].slug;
    veDanhSach(); moPhien(dangChon(), false);
  }

  // ---------- phiên ----------
  async function moPhien(item, moiHan) {
    veGiua(item); vePhai(item);
    if (!item) return;
    var b = encodeURIComponent(brain()), ch = kenh(item), id = null;
    if (!moiHan) {
      var r = await api("/sessions?brain=" + b + "&channel=" + encodeURIComponent(ch) + "&limit=1");
      if (r.sessions && r.sessions[0]) id = r.sessions[0].id;
    }
    if (!id) {
      var n = await api("/sessions/new", { method: "POST", body: fd({ brain: brain(), channel: ch }) });
      if (!n.id) { veLoi(n.error || t("ws.err_session")); return; }
      id = n.id;
    }
    S.sessionCuaPhien[id] = item.slug;
    if (window.JavisSessions) window.JavisSessions.open(id);
    if (S.loai === "workflow") taiLichSu(item);
  }
  function veLoi(msg) { var el = S.el && S.el.querySelector("#wsIdentity"); if (el) el.innerHTML += '<small class="ws-err">' + esc(msg) + '</small>'; }
  function veGiua(item) {
    var el = S.el && S.el.querySelector("#wsIdentity"); if (!el) return;
    if (!item) { el.innerHTML = '<strong>' + esc(t("ws.pick_one")) + '</strong>'; return; }
    var phu = S.loai === "agent" ? (item.group || "Chung") + " · " + (item.role || "") : t("ws.wf_sub", { n: (item.steps || []).length });
    el.innerHTML = ic(S.loai === "agent" ? "bot" : "workflow") + '<div><strong>' + esc(item.name) + '</strong><small>' + esc(phu) + '</small></div>';
    var inp = document.getElementById("chatInput");
    if (inp) inp.placeholder = S.loai === "agent" ? t("ws.ph_agent", { ten: item.name }) : t("ws.ph_workflow");
  }

  // ---------- cột phải ----------
  function vePhai(item) {
    var host = S.el && S.el.querySelector("#wsRight"); if (!host) return;
    if (!item) { host.innerHTML = ""; return; }
    if (S.loai === "agent") {
      host.innerHTML = '<div class="ws-rtitle">' + esc(t("ws.agent_settings")) + '</div><div class="ws-form" id="wsAgentForm"></div>' +
        '<div class="ws-acts"><button type="button" class="ws-btn" id="wsExport">' + esc(t("studio.export")) + '</button>' +
        '<button type="button" class="ws-btn danger" id="wsDel">' + esc(t("common.delete")) + '</button></div>' +
        '<div class="ws-rtitle">' + esc(t("ws.recent_chats")) + '</div><div class="ws-sess" id="wsSess"></div>';
      if (window.JavisStudio && window.JavisStudio.editAgent) {
        window.JavisStudio.editAgent(item, { host: host.querySelector("#wsAgentForm"), onSaved: async function () { await taiDanhSach(); veTrai(); veGiua(dangChon()); } });
      }
      host.querySelector("#wsExport").onclick = function () { window.JavisStudio && window.JavisStudio.exportItem("agent", item.slug); };
      host.querySelector("#wsDel").onclick = async function () {
        if (!confirm(t("studio.del_ag", { ten: item.name }))) return;
        await api("/agents/delete", { method: "POST", body: fd({ slug: item.slug, brain: brain() }) });
        S.chon.agent = null; await taiDanhSach(); veTrai(); chonMacDinh();
      };
      taiPhienGanDay(item);
    } else {
      var td = tienDoHienTai(item);
      host.innerHTML = '<div class="ws-rtitle">' + esc(t("ws.wf_progress")) + '</div>' +
        '<div class="ws-prog"><div style="width:' + phanTram(td) + '%"></div></div>' +
        '<div class="ws-status" id="wsWfStatus">' + esc(nhanTienDo(td)) + '</div>' +
        '<div class="ws-steps" id="wsSteps"></div>' +
        '<div class="ws-acts"><button type="button" class="ws-btn" id="wsEditWf">' + esc(t("ws.edit_steps")) + '</button>' +
        '<button type="button" class="ws-btn" id="wsExport">' + esc(t("studio.export")) + '</button>' +
        '<button type="button" class="ws-btn danger" id="wsDel">' + esc(t("common.delete")) + '</button></div>' +
        '<div class="ws-rtitle">' + esc(t("ws.run_history")) + '</div><div class="ws-runs" id="wsRuns"></div>';
      veBuoc(item, td);
      host.querySelector("#wsEditWf").onclick = function () { window.JavisStudio && window.JavisStudio.editWorkflow(item, { onSaved: async function () { await taiDanhSach(); veTrai(); vePhai(dangChon()); } }); };
      host.querySelector("#wsExport").onclick = function () { window.JavisStudio && window.JavisStudio.exportItem("workflow", item.slug); };
      host.querySelector("#wsDel").onclick = async function () {
        if (!confirm(t("studio.del_wf", { ten: item.name }))) return;
        await api("/workflows/delete", { method: "POST", body: fd({ slug: item.slug, brain: brain() }) });
        S.chon.workflow = null; await taiDanhSach(); veTrai(); chonMacDinh();
      };
    }
  }
  function tenAgent(slug) { var a = S.agents.find(function (x) { return x.slug === slug; }); return a ? a.name : slug; }
  function tienDoHienTai(item) {
    var sid = window.JavisSessions ? window.JavisSessions.current() : null;
    if (sid && S.tienDo[sid]) return S.tienDo[sid];
    var td = tienDoMoi((item.steps || []).length);
    td.buoc.forEach(function (b, i) { b.agent = tenAgent((item.steps[i] || {}).agent); });
    return td;
  }
  function nhanTienDo(td) {
    if (td.trang_thai === "dang") return t("ws.running_step", { a: td.hien_tai + 1, b: td.buoc.length });
    if (td.trang_thai === "xong") return t("ws.done");
    if (td.trang_thai === "loi") return t("ws.failed");
    if (td.cho_duyet) return t("ws.waiting");
    return t("ws.ready");
  }
  function veBuoc(item, td) {
    var host = S.el && S.el.querySelector("#wsSteps"); if (!host) return;
    host.innerHTML = td.buoc.map(function (b, i) {
      var task = ((item.steps || [])[i] || {}).task || "";
      var nhan = { cho: t("ws.step_wait"), dang: t("ws.step_doing"), xong: t("ws.step_done"), loi: t("ws.step_err") }[b.trang_thai];
      return '<div class="ws-step ' + b.trang_thai + '"><span class="ws-num">' + (b.trang_thai === "xong" ? ic("check") : (i + 1)) + '</span>' +
        '<strong>' + esc(task.slice(0, 80) || t("ws.step_n", { n: i + 1 })) + '</strong><small>' + esc(nhan) + (b.loi ? ": " + esc(b.loi) : "") + '</small>' +
        '<div class="ws-who">' + ic("bot") + ' ' + esc(b.agent || tenAgent((item.steps[i] || {}).agent)) + '</div></div>';
    }).join("") + (td.cho_duyet ? '<div class="ws-wait">' + esc(t("studio.wait1")) + ' "' + esc(td.cho_duyet.node) + '"' + (td.cho_duyet.prompt ? ": " + esc(td.cho_duyet.prompt) : "") +
      '<div><button type="button" class="ws-btn primary" id="wsApprove">' + esc(t("studio.approve")) + ' ' + esc(td.cho_duyet.code) + '</button><small>' + esc(t("studio.wait_warn")) + '</small></div></div>' : "");
    var ap = host.querySelector("#wsApprove");
    if (ap) ap.onclick = function () {
      ap.disabled = true;
      var sid = window.JavisSessions ? window.JavisSessions.current() : null;
      if (!sid || !window.JavisWsSend) return;
      window.JavisWsSend({ action: "wf_resume", session_id: sid, task_id: td.cho_duyet.task_id, node: td.cho_duyet.node, code: td.cho_duyet.code, brain: brain() });
      td.cho_duyet = null; td.trang_thai = "dang"; veBuoc(item, td);
    };
    var stt = S.el.querySelector("#wsWfStatus"); if (stt) stt.textContent = nhanTienDo(td);
    var pg = S.el.querySelector(".ws-prog > div"); if (pg) pg.style.width = phanTram(td) + "%";
  }
  async function taiLichSu(item) {
    var host = S.el && S.el.querySelector("#wsRuns"); if (!host) return;
    var r = await api("/workflows/runs?brain=" + encodeURIComponent(brain()) + "&slug=" + encodeURIComponent(item.slug) + "&limit=10");
    var ds = r.runs || [];
    if (!ds.length) { host.innerHTML = '<div class="ws-empty">' + esc(t("ws.no_runs")) + '</div>'; return; }
    host.innerHTML = ds.map(function (x) {
      var d = new Date(x.started_at * 1000);
      return '<button type="button" class="ws-run ' + esc(x.status) + '" data-sid="' + esc(x.session_id || "") + '">' +
        '<span>' + esc(d.toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit" })) + '</span>' +
        '<span class="ws-run-st">' + esc(x.nhan) + '</span><small>' + esc(x.input || "").slice(0, 60) + '</small></button>';
    }).join("");
    host.querySelectorAll("[data-sid]").forEach(function (b) { b.onclick = function () { if (b.dataset.sid && window.JavisSessions) window.JavisSessions.open(b.dataset.sid); }; });
  }
  async function taiPhienGanDay(item) {
    var host = S.el && S.el.querySelector("#wsSess"); if (!host) return;
    var r = await api("/sessions?brain=" + encodeURIComponent(brain()) + "&channel=" + encodeURIComponent("agent:" + item.slug) + "&limit=8");
    var ds = r.sessions || [];
    if (!ds.length) { host.innerHTML = '<div class="ws-empty">' + esc(t("ws.no_chats")) + '</div>'; return; }
    host.innerHTML = ds.map(function (s) { return '<button type="button" class="ws-run" data-sid="' + esc(s.id) + '"><strong>' + esc(s.title || s.preview || t("ws.untitled")) + '</strong></button>'; }).join("");
    host.querySelectorAll("[data-sid]").forEach(function (b) { b.onclick = function () { window.JavisSessions && window.JavisSessions.open(b.dataset.sid); }; });
  }

  // ---------- sự kiện quy trình từ WebSocket ----------
  function onWfEvent(frame) {
    var sid = frame.session_id, ev = frame.event || {}; if (!sid) return;
    var item = dangChon();
    if (!S.tienDo[sid]) { var n = (item && S.loai === "workflow" && S.sessionCuaPhien[sid] === item.slug) ? (item.steps || []).length : Number(ev.steps || 0); S.tienDo[sid] = tienDoMoi(n); }
    apDung(S.tienDo[sid], ev);
    var cur = window.JavisSessions ? window.JavisSessions.current() : null;
    if (item && S.loai === "workflow" && cur === sid) { veBuoc(item, S.tienDo[sid]); if (ev.type === "done" || ev.type === "error" || ev.type === "wait_user") { taiLichSu(item); taiDanhSach().then(veTrai); } }
  }

  // ---------- tạo mới ----------
  function taoMoi() {
    if (!window.JavisStudio) return;
    var sau = async function () { await taiDanhSach(); veTrai(); chonMacDinh(); };
    if (S.loai === "agent") window.JavisStudio.editAgent(null, { onSaved: sau });
    else window.JavisStudio.editWorkflow(null, { onSaved: sau });
  }

  window.JavisWorkspace = { render: render, onWfEvent: onWfEvent, sapXep: sapXep, loc: loc, tienDoMoi: tienDoMoi, apDung: apDung, phanTram: phanTram, state: function () { return S; } };
})();
```

Khi `editAgent(null, {onSaved})` không có `host` thì mở modal như cũ (tạo mới). Kiểm `window.JavisSessions.current()` tồn tại (app.js:1084 có `current`).

- [ ] **Step 5: CSS**

Thêm vào `dashboard/console.css` (cuối file) khối `.wspage` theo mẫu `.chatpage` trong `_injectChatCss` (console.js:6257): ba cột `display:flex; height:100%`, `.ws-left{width:260px}`, `.ws-right{width:320px; overflow:auto}`, `.ws-main{flex:1; min-width:0; display:flex; flex-direction:column}`, `.ws-slot{flex:1; min-height:0; display:flex; flex-direction:column}`, `.ws-seg` hai nút, `.ws-item.on` nền cam nhạt viền `#7d532d`, `.ws-step` có `.ws-num` tròn, `.ws-prog` thanh 4px màu `var(--accent)` (dùng biến màu có sẵn của theme, grep `--accent` hay tương đương trong style.css), `.ws-run` nút full-width. Màn hẹp `@media (max-width: 900px)`: `.ws-left`, `.ws-right` thành `position:absolute` ngăn kéo, hiện khi `.wspage.left-open` / `.right-open`. Dùng biến màu `var(--surface-1)`, `var(--glass-brd)`, `var(--text2)` như `.chatpage`.

- [ ] **Step 6: Từ điển `ws.*`**

vi.json:

```json
  "ws.tab_agent": "Trợ lý",
  "ws.tab_workflow": "Quy trình",
  "ws.search_ph": "Tìm cộng sự...",
  "ws.all_groups": "Tất cả nhóm",
  "ws.new_item": "Tạo mới",
  "ws.new_agent": "Tạo trợ lý",
  "ws.new_workflow": "Tạo quy trình",
  "ws.toggle_list": "Ẩn/hiện danh sách",
  "ws.toggle_panel": "Ẩn/hiện cột phải",
  "ws.empty": "Chưa có mục phù hợp. Tạo mới hoặc tìm trong Javis Store.",
  "ws.pick_one": "Chọn một cộng sự ở cột trái",
  "ws.wf_sub": "Quy trình · {n} bước",
  "ws.ph_agent": "Nhắn cho {ten}...",
  "ws.ph_workflow": "Mô tả kết quả bạn muốn nhận, mỗi tin là một lần chạy...",
  "ws.err_session": "Không mở được hội thoại",
  "ws.agent_settings": "Cài đặt trợ lý",
  "ws.recent_chats": "Hội thoại gần đây",
  "ws.no_chats": "Chưa có hội thoại nào",
  "ws.untitled": "(chưa đặt tên)",
  "ws.wf_progress": "Tiến độ",
  "ws.edit_steps": "Sửa các bước",
  "ws.run_history": "Lịch sử chạy",
  "ws.no_runs": "Chưa chạy lần nào. Gửi một tin để chạy.",
  "ws.running_step": "Đang chạy · Bước {a}/{b}",
  "ws.done": "Đã hoàn tất",
  "ws.failed": "Dừng vì lỗi",
  "ws.waiting": "Đang chờ duyệt",
  "ws.ready": "Sẵn sàng nhận yêu cầu",
  "ws.step_wait": "Chờ đến lượt",
  "ws.step_doing": "Đang thực hiện...",
  "ws.step_done": "Đã hoàn tất",
  "ws.step_err": "Lỗi",
  "ws.step_n": "Bước {n}",
```

en.json: bản dịch tương ứng (Agents, Workflows, Search partners..., All groups, New, New agent, New workflow, Toggle list, Toggle panel, Nothing matches. Create one or browse Javis Store., Pick a partner on the left, Workflow · {n} steps, Message {ten}..., Describe the result you want; each message is one run..., Could not open conversation, Agent settings, Recent chats, No chats yet, (untitled), Progress, Edit steps, Run history, No runs yet. Send a message to run., Running · Step {a}/{b}, Completed, Stopped on error, Waiting for approval, Ready, Waiting, In progress..., Done, Error, Step {n}).

- [ ] **Step 7: index.html**

Sau dòng `studio.js?v=30` thêm `<script src="/static/workspace.js?v=1"></script>` (cache-bust theo VERSION tự gắn ở server, số v chỉ là mặc định).

- [ ] **Step 8: Chạy test và xem bằng trình duyệt**

Run: `node tests/js/test_workspace.js`, `node tests/js/test_ui_actions.js`, `node tests/js/test_i18n.mjs`, `node tests/js/test_studio_chon_model_agent.js`
Expected: xanh.

Khởi động server cục bộ (memory: port 7777, start-javis.bat, kill trực tiếp + đường dẫn tuyệt đối) rồi mở `http://localhost:7777`, vào Cộng sự:
1. Tab Trợ lý: chọn một trợ lý, gửi "chào bạn, bạn là ai?" -> câu trả lời theo vai trợ lý. F5 -> hội thoại còn.
2. Cột phải sửa vai trò, Lưu -> header đổi.
3. Tab Quy trình: chọn quy trình mẫu (bấm Tạo mẫu ở trang Kỹ năng/Studio seed nếu chưa có: `POST /studio/seed`), gửi đầu vào -> chip "Bước 1/2..." hiện, cột phải sáng từng bước, tin kết quả "Lần chạy #1 · ..." xuất hiện. F5 giữa chừng -> vẫn thấy chạy tiếp.
4. Gửi tin thứ hai "ngắn lại một nửa" -> tin "Lần chạy #2".
5. Lịch sử chạy có 2 dòng; bấm dòng -> mở đúng phiên.
6. Quay lại tab Quy trình: quy trình vừa chạy nằm đầu danh sách.
7. Trang Trò chuyện: thanh lịch sử KHÔNG có phiên cộng sự. Hỏi Javis "quy trình chạy gần nhất ra sao?" -> trả lời có tên quy trình và kết quả (qua tool javis_workflow).
8. Nói/gõ ở chat chính "mở trang trợ lý" -> tới Cộng sự.
9. Thu cửa sổ xuống 400px: hai cột thành ngăn kéo, khung chat dùng được.

Ghi lại kết quả từng mục; mục nào hỏng thì sửa trước khi commit.

- [ ] **Step 9: Commit**

```bash
git add dashboard/workspace.js dashboard/console.js dashboard/console.css dashboard/app.js dashboard/studio.js dashboard/index.html dashboard/i18n/vi.json dashboard/i18n/en.json tests/js/test_workspace.js
git commit -m "Trang Cộng sự: chat với trợ lý và quy trình, tiến độ và lịch sử ở cột phải

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: Tài liệu, CHANGELOG, VERSION, PR và merge

**Files:**
- Modify: `docs/07-agents-va-workflows.md` (mục "Mở ở đâu trong Javis" và cách chạy), `docs/en/07-agents-and-workflows.md`
- Modify: `CHANGELOG.md`, `VERSION`

- [ ] **Step 1: Docs**

Trong `docs/07-agents-va-workflows.md`: mục "Mở ở đâu" đổi thành nhóm Năng lực có mục **Cộng sự** với hai tab Trợ lý | Quy trình; thêm mục "Trò chuyện với một trợ lý" (chọn ở cột trái, chat ở giữa, cài đặt ở cột phải, mỗi trợ lý có nhiều hội thoại); mục "Chạy quy trình" viết lại: gửi một tin là một lần chạy, tiến độ ở cột phải, kết quả về chat, tin sau nhớ kết quả trước, lịch sử chạy ở cột phải và Javis tra được bằng câu hỏi ở khung chat chính. Sửa câu "bấm ▶ Chạy trực tiếp ở trang Workflows" thành "gửi tin ở trang Cộng sự". Bản tiếng Anh sửa tương ứng.

- [ ] **Step 2: CHANGELOG + VERSION**

`git fetch origin` rồi đọc số trên `origin/main` (memory: bump theo số REMOTE). Nếu remote vẫn 0.58.x thì bản này là `0.59.0` (tính năng mới). Ghi VERSION và thêm đầu CHANGELOG:

```markdown
## [0.59.0] - 2026-09-15
### Thêm mới
- **Trang Cộng sự thay cho hai trang Trợ lý và Quy trình.** Chọn một trợ lý là chat được ngay với đúng vai đó, mỗi trợ lý có hội thoại riêng và cài đặt nằm ở cột phải.
- **Quy trình chạy ngay trong khung chat.** Gửi một tin là một lần chạy, tiến độ từng bước hiện ở cột phải, kết quả về chat và tin sau vẫn nhớ kết quả trước để bạn góp ý tiếp.
- **Lịch sử chạy được lưu lại.** Cột phải liệt kê các lần chạy gần nhất, bấm vào là mở lại; hỏi Javis "quy trình chạy gần nhất ra sao" ở khung chat chính là có câu trả lời thật. Quy trình vừa chạy tự lên đầu danh sách.
```

- [ ] **Step 3: Chạy toàn bộ test**

Run: `python tests/run.py`
Expected: các file mới xanh; các file đỏ chỉ là 13 file đỏ sẵn trên máy (so với danh sách trong memory `reference_test-do-gia-tren-may-nay`). Ghi rõ trong báo cáo.

- [ ] **Step 4: Commit, push, PR, merge**

```bash
git add docs CHANGELOG.md VERSION
git commit -m "Docs + CHANGELOG 0.59.0: trang Cộng sự

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push -u origin feat/cong-su-workspace
gh pr create --title "Trang Cộng sự: chat với trợ lý và quy trình, lưu lịch sử chạy (0.59.0)" --body "$(cat <<'EOF'
Spec: docs/superpowers/specs/2026-09-15-cong-su-workspace-design.md
Plan: docs/superpowers/plans/2026-09-15-cong-su-workspace.md

- Trang `workspace` (Cộng sự) thay `agents` + `workflows`; ba cột, mượn khung chat của app.
- Phiên kênh `agent:<slug>` dùng prompt của trợ lý; phiên `workflow:<slug>` biến mỗi tin thành một lần chạy `execute_workflow`, kết quả về chat, kể cả lỗi và chờ duyệt.
- Kho `workflow_runs.sqlite3` ghi mọi lần chạy (Cộng sự, Kanban); `GET /workflows/runs`; tool `javis_workflow`; dòng "lần chạy gần nhất" trong system prompt.
- `POST /sessions/new`, `GET /sessions?channel=`; thanh lịch sử chat chính bỏ phiên cộng sự.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Chờ CI xanh (dùng ccd_pr để xem), rồi merge squash vào main theo luật repo (CLAUDE.md: CI xanh là merge thẳng, lịch sử tuyến tính). CI đỏ thì sửa trước, không merge.

---

## Self-review

**Spec coverage:**
- §3 giao diện ba cột, ngăn kéo màn hẹp, Store, Tạo mới, sắp xếp: Task 9 (+ Task 8 đăng ký trang).
- §4 phiên theo kênh, `POST /sessions/new`, lọc kênh, ghim model: Task 3.
- §5 chat với trợ lý, JAVIS_LESSON, nhật ký, lỗi khi trợ lý mất: Task 5.
- §6 lượt quy trình, status/wf_event/stream, tin xong/lỗi/chờ duyệt, nối kết quả trước, wf_resume: Task 4 + 6.
- §7 kho lịch sử, bọc `execute_workflow`, `source`, API, `last_run_at`/`last_chat_at`: Task 1 + 2 (+3).
- §8 plugin `javis_workflow`, dòng system prompt: Task 7.
- §9 kiểm thử: mỗi task có test; kiểm tay ở Task 9 Step 8.
- §11 docs, CHANGELOG, VERSION: Task 10.

**Type consistency:** `execute_workflow(..., source=)` (Task 2) được Task 6 gọi đúng tên tham số; `workflow_chat.chay` trả các khoá `trang_thai/ket_qua/so_buoc/loi/wait/run_id` (Task 4) được `_luot_quy_trinh` (Task 6) đọc đúng; `gan_nhat` trả `output_tom_tat` (Task 1) được plugin (Task 7) và workspace.js (Task 9, dùng `input`, `nhan`, `session_id`, `started_at`, `status`) đọc đúng; `JavisStudio.editAgent(a, {host,onSaved})` (Task 9 Step 1) khớp cách gọi trong workspace.js.

**Placeholder scan:** không còn "TBD"; các bước "đọc rồi sao y" (Task 6 Step 4 phần `finally`, Task 8 Step 4 grep id trang) là chỉ dẫn cụ thể về nơi đọc và việc làm.
