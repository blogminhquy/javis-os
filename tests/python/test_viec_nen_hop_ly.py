"""Việc nền không được tự nâng quyền, và việc bị chặn phải có lối ra.

    python tests/run.py viec_nen_hop_ly      (KHÔNG mạng, không spawn engine)

Chủ repo báo 01/09 kèm ba ảnh: cột "Cần bạn xử lý" đọng 20 ngoại lệ, phần lớn mang đúng một
câu - "Task cần hành động ra ngoài. Chỉ worker mode=full mới được thực thi." - và chuông thì
đầy thông báo "Việc ... bị chặn, cần bạn xem".

Soi ra hai lỗi tách rời nhau, cả hai đều ở tầng THIẾT KẾ chứ không phải một dòng code hỏng:

1. NGÕ CỤT CÓ BẢO ĐẢM. Prompt của specifier dặn thẳng: việc cần thao tác ra ngoài thì để mức
   auto "để kernel chặn và xin quyền". Kernel chặn thật - nhưng chưa từng có đường nào để XIN.
   `javis_task` cố ý từ chối tạo việc mức full, trang Việc không có ô đổi mức quyền, nên lối
   thoát duy nhất là xoá. Nút "Thử lại" bày ngay đó thì chạy lại đúng nhánh chặn ấy, chặn lại
   y hệt, và kêu thêm một tiếng chuông nữa.

2. NÓI MỘT ĐẰNG CHẠY MỘT NẺO. `prepared()` ghi đè execution_mode bằng thứ specifier trả về.
   Việc tạo mức `suggest` (chỉ đọc, đúng câu tool báo lại cho người dùng) lặng lẽ chạy ở mức
   `auto`; và specifier - cũng chỉ là một model - trả về chuỗi "full" là tự cấp cho mình mức
   tháo sạch rào, đúng mức mà `javis_task` từ chối tạo và CLAUDE.md bắt phải do người tự đặt.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-viecnen-"))

from fastapi import FastAPI  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

import tasks as tasks_mod  # noqa: E402
from tasks import TasksDeps, TasksFeature  # noqa: E402

_fails = []


def check(ten, dieu_kien, them=""):
    print(("ok   " if dieu_kien else "FAIL ") + ten
          + (("  [" + str(them) + "]") if them and not dieu_kien else ""))
    if not dieu_kien:
        _fails.append(ten)


# ============================================================
# 1. Kẹp trần quyền: specifier chỉ được HẠ, không được nâng
# ============================================================
_kep = TasksFeature._kep_quyen

check("việc tạo mức suggest thì specifier đòi auto cũng vẫn là suggest",
      _kep("suggest", "auto") == "suggest", _kep("suggest", "auto"))
check("và đòi full cũng vẫn là suggest", _kep("suggest", "full") == "suggest")
check("việc tạo mức auto thì specifier KHÔNG tự cấp được full",
      _kep("auto", "full") == "auto", _kep("auto", "full"))
check("chiều HẠ vẫn mở: trần auto, specifier xin suggest thì được suggest",
      _kep("auto", "suggest") == "suggest")
check("người dùng đã đặt full thì specifier dùng full được",
      _kep("full", "full") == "full")
check("trần lạ/rỗng rơi về auto chứ không rơi về full",
      _kep("", "full") == "auto" and _kep("linh tinh", "full") == "auto")
check("mức xin lạ cũng rơi về auto, không leo lên trần",
      _kep("full", "linh tinh") == "auto", _kep("full", "linh tinh"))

_src = (SERVER / "tasks.py").read_text(encoding="utf-8")
check("CANARY: kẹp trần nằm ĐÚNG chỗ specifier ghi vào kho (prepared)",
      "self._kep_quyen(task.get(\"execution_mode\"), spec[\"execution_mode\"])" in _src)


# ============================================================
# 2. Dựng một bảng việc thật để thử endpoint
# ============================================================
_tmp = Path(tempfile.mkdtemp(prefix="javis-viecnen-brain-"))
_brain = _tmp / "Brain Test"
_brain.mkdir(parents=True)


def _atomic(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


async def _workflow(*_a, **_k):
    if False:
        yield {}


async def _report(*_a, **_k):
    return True


app = FastAPI()
deps = TasksDeps(
    brain_root=lambda v="brain": str(_brain),
    atomic_write_text=_atomic,
    execute_workflow=_workflow,
    workflows_dir=lambda brain: Path(_brain) / "workflows",
    build_system_prompt=lambda brain: "system",
    aux_model=lambda: None,
    safe_tools=["Read", "Write"],
    state_dir=_tmp / "state",
    scheduler_brains=lambda: [str(_brain)],
    report=_report,
)
feat = TasksFeature(deps)
app.include_router(feat.router)
client = TestClient(app, base_url="http://127.0.0.1")
_root = str(_brain)


def _tao(title, **kw):
    tid = feat.enqueue(_root, title, kw.pop("intent", title), "auto", 2, None, False,
                       "chat", "", kw.pop("capability", "files"),
                       kw.pop("execution_mode", "auto"), "")
    return tid


def _chan(tid, kind, reason):
    """Đưa việc vào đúng trạng thái 'bị chặn vì <kind>' như worker thật để lại."""
    assert feat.store.claim(tid, "w-test", 60), tid
    feat.store.block(tid, "w-test", kind, reason)


# ---- Cấp quyền: chỉ mở cho việc bị chặn VÌ THIẾU QUYỀN ----
_t_quyen = _tao("Gửi báo cáo cho khách", capability="external-write", execution_mode="auto")
_chan(_t_quyen, "capability", tasks_mod.LY_DO_CAN_QUYEN)
_t_thieu_tin = _tao("Test kịch bản webinar")
_chan(_t_thieu_tin, "needs_input", "Không có thông tin nào về số lượng buyer hiện tại.")

r = client.post("/kanban/task/grant", data={"id": _t_quyen, "brain": "brain"}).json()
check("cấp quyền cho việc kẹt vì thiếu quyền: OK", r.get("ok"), r)
_sau = feat.store.get_task(_t_quyen)
check("mức quyền lên full", _sau["execution_mode"] == "full", _sau["execution_mode"])
check("và việc quay lại hàng chờ chạy (ready), không còn nằm ở cột kẹt",
      _sau["status"] == "ready", _sau["status"])
check("lý do chặn được xoá sạch", not _sau["block_reason"] and not _sau["block_kind"])
check("số lần thử đặt lại 0 (không mang theo lần thử đã cháy)", _sau["attempts"] == 0,
      _sau["attempts"])
_ev = [e.get("event_type") for e in feat.store.list_events(_t_quyen)]
check("có dấu vết ai đó đã cấp quyền trong nhật ký vòng đời", "operator_grant" in _ev, _ev)

r2 = client.post("/kanban/task/grant", data={"id": _t_thieu_tin, "brain": "brain"}).json()
check("KHÔNG cấp quyền được cho việc kẹt vì lý do khác (thiếu dữ liệu)",
      r2.get("ok") is False, r2)
check("và việc đó không bị đụng vào mức quyền",
      feat.store.get_task(_t_thieu_tin)["execution_mode"] == "auto")
r3 = client.post("/kanban/task/grant", data={"id": "khong-co-that", "brain": "brain"}).json()
check("id không tồn tại -> báo lỗi, không nổ", r3.get("ok") is False, r3)


# ---- Xoá tất cả theo khu ----
_a1 = _tao("Kẹt 1")
_chan(_a1, "capability", tasks_mod.LY_DO_CAN_QUYEN)
_a2 = _tao("Chờ duyệt 1")
feat.store.claim(_a2, "w-test", 60)
feat.store.complete(_a2, "w-test", "xong", needs_approval=True)
_h1 = _tao("Đã xong 1")
feat.store.claim(_h1, "w-test", 60)
feat.store.complete(_h1, "w-test", "xong")

_bang = feat.board_view("brain")
check("trước khi dọn: khu Cần bạn xử lý có việc",
      len(_bang["operations"]["attention"]) >= 2, len(_bang["operations"]["attention"]))
check("trước khi dọn: khu Lịch sử có việc",
      len(_bang["operations"]["history"]) >= 1, len(_bang["operations"]["history"]))

rc = client.post("/kanban/panel/clear", data={"panel": "attention", "brain": "brain"}).json()
check("xoá tất cả khu Cần bạn xử lý: OK", rc.get("ok") and rc.get("removed") >= 2, rc)
_bang = feat.board_view("brain")
check("khu Cần bạn xử lý sạch", not _bang["operations"]["attention"],
      _bang["operations"]["attention"])
check("nhưng việc chỉ ARCHIVE chứ không xoá hẳn (vẫn tra lại được)",
      feat.store.get_task(_a1) is not None
      and feat.store.get_task(_a1)["status"] == "archived",
      (feat.store.get_task(_a1) or {}).get("status"))
check("dọn khu này KHÔNG đụng tới khu Lịch sử",
      len(_bang["operations"]["history"]) >= 1, len(_bang["operations"]["history"]))

rh = client.post("/kanban/panel/clear", data={"panel": "history", "brain": "brain"}).json()
check("xoá tất cả khu Lịch sử: OK", rh.get("ok") and rh.get("removed") >= 1, rh)
check("khu Lịch sử là xoá HẲN khỏi kho", feat.store.get_task(_h1) is None)
rx = client.post("/kanban/panel/clear", data={"panel": "linh-tinh", "brain": "brain"}).json()
check("panel lạ -> báo lỗi, không dọn bừa", rx.get("ok") is False, rx)

# Việc ĐANG CHẠY không được dọn theo: xoá bản ghi dưới chân worker là để lại worker mồ côi.
_dang_chay = _tao("Đang chạy")
feat.store.claim(_dang_chay, "w-live", 600)
feat.store.archive_by_status(_root, ("blocked", "review", "running"))
check("việc đang chạy KHÔNG bị dọn dù có gọi kèm",
      feat.store.get_task(_dang_chay)["status"] == "running",
      feat.store.get_task(_dang_chay)["status"])


# ============================================================
# 3. Câu báo cho người, không phải câu báo cho máy
# ============================================================
check("lý do chặn nói rõ VIỆC PHẢI LÀM chứ không nói 'mode=full'",
      "mode=full" not in tasks_mod.LY_DO_CAN_QUYEN
      and "Cho phép chạy thật" in tasks_mod.LY_DO_CAN_QUYEN, tasks_mod.LY_DO_CAN_QUYEN)
check("và nói luôn lối thoát thứ hai: xoá nếu đã xử lý trong chat",
      "xoá khỏi bảng" in tasks_mod.LY_DO_CAN_QUYEN.lower())

print()
if _fails:
    print(f"FAIL {len(_fails)}: " + "; ".join(_fails))
    raise SystemExit(1)
print("TẤT CẢ PASS")
