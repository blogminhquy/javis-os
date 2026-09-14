"""Việc nền của bộ não giọng không được chết lặng (0.57.18).

    python tests/run.py viec_nen_giong

Chủ dự án báo 15/09: giao hai việc, Javis nói "đang chạy nền, kết quả sẽ tự hiện", rồi không
bao giờ có gì hiện ra. Hỏi lại thì nó vẫn báo "đang chạy" vì sổ việc chưa bao giờ được gạch tên.

Gốc: `asyncio.create_task(_voice_bg_task(...))` THẢ TRÔI, không gán vào đâu. asyncio chỉ giữ
tham chiếu YẾU tới task đang chờ (asyncio.all_tasks dùng WeakSet), nên bộ gom rác có thể nuốt
task ngay giữa chừng: không kết quả, không lỗi, không cả `note_task_done`. Chính repo này đã
biết bẫy đó ở `_UPDATE_TASKS` và `_PUSH_TASKS`, riêng chỗ việc nền của giọng thì bỏ sót.

Hai lỗ thứ cấp cùng đợt: `await push_to_chat(...)` nằm NGOÀI try/finally nên việc bị huỷ là im
lặng tuyệt đối; và không có hạn giờ nên bộ não chính treo là task nằm đó vĩnh viễn.

Test soi NGUỒN (những nhánh này nằm trong một hàm lồng trong endpoint WebSocket, không nhấc ra
gọi trực tiếp được) cộng chạy thật sổ việc nền để chắc gạch tên hai lần không vỡ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import re
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-bgtask-"))

import voice_brain as vb  # noqa: E402

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


src = open(os.path.join(ROOT, "server", "main.py"), encoding="utf-8").read()

# ---- 1. Giữ ref mạnh cho task việc nền ----
check("CANARY: không còn create_task thả trôi cho _voice_bg_task",
      not re.search(r"^\s*asyncio\.create_task\(_voice_bg_task\(", src, re.M))
check("task việc nền được gán và giữ trong _VOICE_BG_TASKS",
      re.search(r"_bg = asyncio\.create_task\(_voice_bg_task\([\s\S]{0,120}"
                r"_VOICE_BG_TASKS\.add\(_bg\)[\s\S]{0,120}"
                r"_bg\.add_done_callback\(_VOICE_BG_TASKS\.discard\)", src) is not None)
check("_VOICE_BG_TASKS khai báo ở cấp module (task sống lâu hơn lượt)",
      re.search(r"^_VOICE_BG_TASKS = set\(\)", src, re.M) is not None)

# ---- 2. Mọi đường ra đều báo về khung chat ----
body = (re.search(r"async def _voice_bg_task\([\s\S]*?\n        async def _start_resumed_turn", src)
        or [""])[0]
check("tìm được thân _voice_bg_task", bool(body))
check("có hạn giờ, không treo im vô hạn",
      "asyncio.wait_for(" in body and "timeout=VOICE_BG_TIMEOUT" in body)
check("quá hạn thì nói thật bằng lời, không im",
      "asyncio.TimeoutError" in body and "chưa xong nên em dừng lại" in body)
check("bị HUỶ cũng báo về khung chat rồi mới ném tiếp",
      re.search(r"except asyncio\.CancelledError:[\s\S]{0,300}push_to_chat\([\s\S]{0,120}raise", body) is not None)
check("lỗi thường vẫn đẩy câu lỗi về chat", "Việc nền lỗi:" in body)
check("gạch tên trong sổ việc ở finally (mọi đường ra)",
      re.search(r"finally:\s*\n\s*voice_brain\.note_task_done\(conv_sid, request\)", body) is not None)
check("hạn giờ đặt ở cấp module, đọc được",
      re.search(r"^VOICE_BG_TIMEOUT = ", src, re.M) is not None)

# ---- 3. Sổ việc nền: gạch tên hai lần không vỡ ----
# Nhánh CancelledError gọi note_task_done rồi finally gọi lần nữa. Phải chịu được.
SID = "phien-thu"
vb.note_task_start(SID, "tổng hợp việc hôm nay")
vb.note_task_start(SID, "kiểm tra tiến độ")
check("hai việc vào sổ", len(vb.pending_tasks(SID)) == 2)
check("có việc thì có dòng ghi chú cho bộ não giọng", bool(vb.pending_note(SID)))
vb.note_task_done(SID, "tổng hợp việc hôm nay")
vb.note_task_done(SID, "tổng hợp việc hôm nay")   # gọi lần hai (đường huỷ) không được vỡ
check("gạch tên hai lần vẫn đúng một việc còn lại", len(vb.pending_tasks(SID)) == 1)
vb.note_task_done(SID, "kiểm tra tiến độ")
check("hết việc thì sổ sạch, không còn báo đang chạy",
      vb.pending_tasks(SID) == [] and vb.pending_note(SID) == "")

# ---- 4. Việc nền của giọng phải CÓ MẶT trong sổ việc nền chung (0.57.19) ----
# Trước đó loại việc này không hiện ở đâu cả: dải trạng thái không đếm, `has_pending_work`
# không tính nên Javis còn bị dán nhầm cảnh báo "hứa suông" trong khi vừa giao việc thật, và
# người dùng chỉ còn cách hỏi miệng mới biết nó còn sống hay đã chết.
import background_status as bs  # noqa: E402

v_khong = bs.active_view([], [], [], chat_id="web:abc")
check("chưa có việc gì: dải ẩn", v_khong["level"] == "idle" and v_khong.get("voice_count") == 0)

v = bs.active_view([], [], [], chat_id="web:abc",
                   voice_tasks=[{"request": "tổng hợp việc hôm nay", "at": 1700000000.0}])
check("việc nền của giọng vào sổ chung", v["count"] == 1 and v["voice_count"] == 1)
check("được tính là ĐANG CHẠY THẬT (task asyncio sống, không phải thẻ chờ điều phối)",
      v["running_count"] == 1 and v["level"] == "run")
check("luôn là việc CỦA khung chat này", v["mine_count"] == 1)
check("giữ nguyên nội dung yêu cầu để người dùng biết đang chờ cái gì",
      v["items"][0]["title"] == "tổng hợp việc hôm nay" and v["items"][0]["kind"] == "voice")
check("has_pending_work thấy nó (hết bị dán nhầm cảnh báo hứa suông)",
      bs.has_pending_work(v) is True)

v2 = bs.active_view([{"id": "t1", "title": "việc bảng", "status": "running"}], [], [],
                    chat_id="web:abc",
                    voice_tasks=[{"request": "kiểm tra tiến độ", "at": 1700000000.0}])
check("lẫn việc bảng: tổng đúng, phần của giọng đếm riêng",
      v2["count"] == 2 and v2["running_count"] == 2 and v2["voice_count"] == 1)

print(("\n%d FAIL" % len(_fails)) if _fails else "\nTat ca OK")
raise SystemExit(1 if _fails else 0)
