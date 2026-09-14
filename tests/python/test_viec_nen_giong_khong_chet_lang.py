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

# ---- 4. Việc nền của giọng là THẺ THẬT trên trang Việc (0.57.20) ----
# Chủ dự án 15/09: "việc ngầm chạy thì cập nhật vào trang việc luôn nhé vì hiện tại đang không
# cập nhật". Trước đó loại việc này chỉ sống trong bộ nhớ tiến trình: xong là bay hơi, không
# để lại dấu, và trong lúc chạy không nhìn thấy ở đâu để biết còn sống hay đã chết.
import background_status as bs  # noqa: E402
from task_store import TaskStore  # noqa: E402

v_khong = bs.active_view([], [], [], chat_id="web:abc")
check("chưa có việc gì: dải ẩn", v_khong["level"] == "idle" and v_khong.get("voice_count") == 0)

# `voice_tasks` giờ CHỈ để đếm việc còn sống trong tiến trình, KHÔNG sinh mục riêng nữa: mỗi
# việc đã là một thẻ Kanban, thêm mục nữa là đếm đôi cùng một việc trên dải trạng thái.
the_giong = {"id": "t_v1", "title": "tổng hợp việc hôm nay", "status": "running",
             "chat_id": "web:abc", "created_by": "voice"}
v = bs.active_view([the_giong], [], [], chat_id="web:abc",
                   voice_tasks=[{"request": "tổng hợp việc hôm nay", "at": 1700000000.0}])
check("một việc = MỘT mục, không đếm đôi", v["count"] == 1 and v["running_count"] == 1)
check("vẫn đếm riêng được số việc nền của giọng (cho câu hỏi thăm)", v["voice_count"] == 1)
check("là việc CỦA khung chat này", v["mine_count"] == 1)
check("has_pending_work thấy nó (hết bị dán nhầm cảnh báo hứa suông)",
      bs.has_pending_work(v) is True)

# ---- 5. Vòng đời thẻ: tạo đang chạy -> đóng, và điều phối KHÔNG được nhặt lên chạy lại ----
kho = TaskStore(__import__("pathlib").Path(os.environ["JAVIS_STATE_DIR"]) / "kanban-thu.sqlite3")
ROOT_THU = "/brain/thu"
tid = kho.enqueue(ROOT_THU, title="tổng hợp việc hôm nay", intent="tổng hợp việc hôm nay",
                  status="running", created_by="voice", chat_id="web:abc")
t = kho.get_task(tid)
check("thẻ tạo ra ở trạng thái ĐANG CHẠY", t["status"] == "running")
check("thẻ ghi rõ do giọng giao và thuộc khung chat nào",
      t["created_by"] == "voice" and t["chat_id"] == "web:abc")
check("ĐIỀU PHỐI KHÔNG NHẶT thẻ đang chạy lên chạy lại (chống chạy hai lần)",
      kho.next_candidate(ROOT_THU) is None)
check("reclaim_stale không đụng tới (thẻ chưa từng có hạn giữ chỗ)",
      kho.reclaim_stale(ROOT_THU, set()) == 0 and kho.get_task(tid)["status"] == "running")

# Xong: đóng thẻ kèm kết quả, dù chưa bao giờ có worker nào giữ chỗ.
kho.complete(tid, "", "Hôm nay anh đã sửa ngắt lời và việc nền.")
t = kho.get_task(tid)
check("việc xong thì thẻ sang XONG và giữ kết quả",
      t["status"] == "done" and "ngắt lời" in (t["result"] or ""))

# Hỏng: phải là CHẶN chứ không phải xong. Thẻ xanh cho một việc thất bại là nói dối.
tid2 = kho.enqueue(ROOT_THU, title="việc sẽ hỏng", intent="việc sẽ hỏng",
                   status="running", created_by="voice", chat_id="web:abc")
kho.block(tid2, "", "voice_bg", "quá hạn giờ")
t2 = kho.get_task(tid2)
check("việc hỏng thì thẻ sang CHẶN kèm lý do thật",
      t2["status"] == "blocked" and "quá hạn" in (t2["block_reason"] or ""))
kho.close()

# ---- 6. main.py nối đúng vòng đời ấy ----
check("tạo thẻ ngay khi nhận việc, trạng thái running, đánh dấu created_by=voice",
      re.search(r"tasks_feature\.store\.enqueue\([\s\S]{0,260}status=\"running\", created_by=\"voice\"", src) is not None)
check("mọi đường ra đều đóng thẻ (xong / lỗi / quá hạn / bị huỷ)",
      len(re.findall(r"_dong_the\(", body)) >= 5)
check("hỏng thì đóng bằng block, xong mới complete",
      "tasks_feature.store.block(tid" in body and "tasks_feature.store.complete(tid" in body)
check("khởi động lại thì dọn thẻ mồ côi, không để kẹt 'đang chạy' vĩnh viễn",
      "_don_the_viec_giong_mo_coi" in src
      and 'server khởi động lại nên việc nền không còn chạy' in src)

print(("\n%d FAIL" % len(_fails)) if _fails else "\nTat ca OK")
raise SystemExit(1 if _fails else 0)
