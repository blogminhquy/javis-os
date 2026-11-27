"""Lịch và thẻ "Nhắc hẹn" của việc nền không lạc vào khung chat chẳng liên quan.

    python tests/python/test_reminders_stay_in_their_chat.py

Chủ repo 27/11/2026: đang hỏi chuyện Google Search trong một khung chat, thì một luồng việc nền của đơn
POSCake 3472 tạo lịch "Nhắc thanh toán đơn POSCake 3472" và "Duyệt nhóm Zoom...". Khung chat đó nhận:
1. các dòng "Đã tạo lịch: ... · Hoàn tác" (change_receipt chụp CẢ brain trước và sau lượt chat, nên lịch
   việc nền tạo trong lúc đó bị tính là của lượt chat);
2. rồi tới giờ, các thẻ "Nhắc hẹn" (tool javis_schedule không có ngữ cảnh lượt nên hỏi sổ lượt đang chạy,
   và sổ đoán người nhận là khung chat DUY NHẤT đang chạy trên brain, tức khung chat của chủ).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import tempfile
import time
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-lac-khung-state-"))

import change_receipt as cr  # noqa: E402
import luot_dang_chay as ldc  # noqa: E402
import memory_control  # noqa: E402
import turn_context  # noqa: E402

fails = []


def check(ten, dk, them=""):
    print(("ok   " if dk else "FAIL ") + ten + ("" if dk or not them else f"  [{them}]"))
    if not dk:
        fails.append(ten)


def reset_spans():
    with memory_control._LOCK:
        memory_control._WRITER_SPANS.clear()


A = tempfile.mkdtemp(prefix="brainA-")

# ---- 1. Sổ lượt đang chạy không còn đoán bừa ----
ldc._DANG.clear()
reset_spans()
k = ldc.bat_dau("web:chat-google", A)
check("không ngữ cảnh, không việc nền: vẫn đoán được như cũ (engine chưa mang khoá lượt)",
      ldc.doan_chat_id(A) == "web:chat-google")
with memory_control.background_writer(A, "full"):
    check("brain đang chạy việc nền: KHÔNG đoán khung chat chủ đang mở", ldc.doan_chat_id(A) == "",
          ldc.doan_chat_id(A))
    check("doan_luot cũng không mượn lượt chat lúc đó", ldc.doan_luot(A) is None)
check("việc nền xong thì đoán lại được", ldc.doan_chat_id(A) == "web:chat-google")
with memory_control.background_writer(A, "suggest"):
    check("loop chỉ đọc (suggest) không đánh dấu, không chặn", ldc.doan_chat_id(A) == "web:chat-google")

tok = turn_context.bind(turn_context.make("kanban", chat_id="", job="kanban:t1"))
try:
    check("lượt Kanban không giao từ chat: không mượn khung chat đang chạy", ldc.doan_chat_id(A) == "")
finally:
    turn_context.reset(tok)
tok = turn_context.bind(turn_context.make("reminder", chat_id="web:chat-shop", job="r1"))
try:
    check("lượt nhắc hẹn: không mượn khung chat đang chạy", ldc.doan_chat_id(A) == "")
finally:
    turn_context.reset(tok)
tok = turn_context.bind(turn_context.make("zalo", sender_id="u1", chat_id="g1"))
try:
    check("lượt chatbot Zalo: không mượn khung chat dashboard", ldc.doan_chat_id(A) == "")
finally:
    turn_context.reset(tok)
tok = turn_context.bind(turn_context.make("dashboard", chat_id="s9", la_chu=True, session_id="s9"))
try:
    check("lượt dashboard: đúng khung của nó, không đoán", ldc.doan_chat_id(A) == "web:s9")
finally:
    turn_context.reset(tok)
ldc.ket_thuc(k)

# ---- 2. javis_schedule: lịch của việc nền không mang chat_id của khung chat chủ ----
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "javis_schedule_plugin", str(Path(ROOT) / "system" / "plugins" / "javis-schedule" / "plugin.py"))
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)
k = ldc.bat_dau("web:chat-google", A)
with memory_control.background_writer(A, "full"):
    check("javis_schedule gọi trần trong lúc việc nền chạy: không gán khung chat chủ",
          plugin._turn_origin(A)[0] == "", plugin._turn_origin(A))
ldc.ket_thuc(k)

# ---- 3. Dòng "Đã tạo lịch" chỉ tính việc của chính lượt chat ----
reset_spans()
root = Path(tempfile.mkdtemp(prefix="javis-receipt-lac-"))
(root / "Javis" / "loops").mkdir(parents=True)
rem_file = root / "Javis" / "reminders.json"
rem_file.write_text(json.dumps({"reminders": [
    {"id": "r_fire", "status": "pending", "label": "Báo cáo 9h", "chat_id": "web:me", "created_at": 1.0},
    {"id": "r_pause", "status": "pending", "label": "Tạm dừng", "chat_id": "web:me", "created_at": 1.0},
    {"id": "r_bo", "status": "pending", "label": "Bỏ", "chat_id": "web:me", "created_at": 1.0}]}), encoding="utf-8")
snap = cr.snapshot(root)
now = time.time()
rows = [
    {"id": "r_fire", "status": "done", "label": "Báo cáo 9h", "chat_id": "web:me", "created_at": 1.0},
    {"id": "r_pause", "status": "paused", "label": "Tạm dừng", "chat_id": "web:me", "created_at": 1.0},
    {"id": "r_bo", "status": "cancelled", "label": "Bỏ", "chat_id": "web:me", "created_at": 1.0},
    {"id": "r_mine", "status": "pending", "label": "Nhắc tôi gọi khách", "chat_id": "web:me", "created_at": now},
    {"id": "r_other", "status": "pending", "label": "Nhắc chat khác", "chat_id": "web:khac", "created_at": now},
    {"id": "r_tg", "status": "pending", "label": "Nhắc qua Telegram", "chat_id": "12345", "created_at": now},
]
rem_file.write_text(json.dumps({"reminders": rows}), encoding="utf-8")
by = {(i["kind"], i["id"]): i for i in cr.diff(snap, root, "web:me")}
check("lịch chính chat này tạo: có dòng", ("reminder", "r_mine") in by)
check("lịch mang khung chat khác: không có dòng", ("reminder", "r_other") not in by)
check("lịch gửi Telegram chủ dặn trong lượt (không việc nền chạy): vẫn có dòng", ("reminder", "r_tg") in by)
check("lịch tới giờ đã chạy xong không phải 'Đã gỡ'", ("reminder", "r_fire") not in by)
check("lịch tạm dừng không phải 'Đã gỡ'", ("reminder", "r_pause") not in by)
check("lịch chat này huỷ: vẫn là 'Đã gỡ'", by.get(("reminder", "r_bo"), {}).get("act") == "removed")

# Đúng ca của chủ: việc nền của đơn POSCake tạo lịch (không chat_id, hoặc chat_id bị đoán sai) trong lúc lượt chạy.
rem_file.write_text(json.dumps({"reminders": [
    {"id": "r_old", "status": "pending", "label": "Cũ", "chat_id": "", "created_at": 1.0}]}), encoding="utf-8")
snap = cr.snapshot(root)
with memory_control.background_writer(root, "full"):
    t_bg = time.time()
    rem_file.write_text(json.dumps({"reminders": [
        {"id": "r_old", "status": "pending", "label": "Cũ", "chat_id": "", "created_at": 1.0},
        {"id": "r_pos", "status": "pending", "label": "Nhắc thanh toán đơn POSCake 3472", "chat_id": "",
         "created_at": t_bg}]}), encoding="utf-8")
    (root / "Javis" / "loops" / "don-poscake.md").write_text("---\nname: Đơn POSCake\nowner_chat: \n---\n",
                                                            encoding="utf-8")
items = cr.diff(snap, root, "web:me")
check("lịch việc nền tạo trong lúc lượt chat chạy: KHÔNG lên dòng 'Đã tạo lịch'", not items, items)

# Lịch chat tạo NGAY lúc việc nền chạy nhưng mang đúng khung chat này: vẫn là của chat này.
snap = cr.snapshot(root)
with memory_control.background_writer(root, "full"):
    data = json.loads(rem_file.read_text(encoding="utf-8"))
    data["reminders"].append({"id": "r_me2", "status": "pending", "label": "Của tôi", "chat_id": "web:me",
                              "created_at": time.time()})
    rem_file.write_text(json.dumps(data), encoding="utf-8")
by = {(i["kind"], i["id"]) for i in cr.diff(snap, root, "web:me")}
check("lịch mang đúng khung chat này vẫn có dòng dù việc nền đang chạy", ("reminder", "r_me2") in by)

print()
print("ĐẠT" if not fails else f"TRƯỢT {len(fails)}: {fails}")
raise SystemExit(1 if fails else 0)
