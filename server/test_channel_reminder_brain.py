"""Test: recipe curl POST /reminders trong channel_context PHẢI mang field 'brain' của phiên.

Đây là bug "chat bằng brain khác (vd My Bullet Journal) nhưng nhắc hẹn vẫn rơi vào Brain Default":
recipe curl cũ bỏ trống brain, mà endpoint /reminders thiếu brain thì âm thầm dùng default.

Chạy tay / CI (không cần pytest, không chạm mạng):

    cd server && python test_channel_reminder_brain.py

Phủ: có brain_root → recipe /reminders (Telegram + dashboard) chứa 'brain' đúng path và JSON hợp lệ;
path có KHOẢNG TRẮNG vẫn là JSON chuỗi hợp lệ; recipe send-file KHÔNG bị chèn brain; thiếu brain_root
→ không có field brain (giữ tương thích) và có ghi chú cảnh báo rơi về Brain Default; có gợi ý dùng
tool javis_schedule.
"""
import json
import os
import re
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-chanbrain-"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import channel_context as cc  # noqa: E402

_fails = []
BRAIN = "/brains/My Bullet Journal"   # có KHOẢNG TRẮNG - kiểm JSON quoting


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def _reminder_json(block):
    """Bóc JSON body của curl POST /reminders trong block (thu gọn xuống 1 dòng trước).
    Trả dict đã parse, hoặc None nếu không tìm/không parse được."""
    flat = " ".join(block.split("\n"))
    # mọi payload -d '{...}' trong block; chọn cái của /reminders = có "delay_min" và "text" (không "path")
    for blob in re.findall(r"-d '(\{.*?\})'", flat):
        if '"delay_min"' in blob and '"path"' not in blob:
            try:
                return json.loads(blob)
            except json.JSONDecodeError:
                return None
    return None


# ---- Telegram CÓ brain_root ----
tg = cc.build_channel_block("telegram", {"chat_id": "12345"}, telegram_running=True,
                            port=7777, brain_root=BRAIN)
check("TG: recipe /reminders có field brain đúng path (substring)", f'"brain":{json.dumps(BRAIN)}' in tg)
rj = _reminder_json(tg)
check("TG: body /reminders là JSON hợp lệ", isinstance(rj, dict))
check("TG: brain trong body = path phiên", (rj or {}).get("brain") == BRAIN)
check("TG: vẫn giữ chat_id đúng người", (rj or {}).get("chat_id") == "12345")
check("TG: gợi ý dùng tool javis_schedule", "javis_schedule" in tg)
# send-file KHÔNG được dính brain (chỉ /reminders cần)
sendfile_blobs = [b for b in re.findall(r"-d '(\{.*?\})'", " ".join(tg.split("\n"))) if '"path"' in b]
check("TG: recipe send-file KHÔNG chèn brain", sendfile_blobs and all('"brain"' not in b for b in sendfile_blobs))

# ---- Telegram KHÔNG brain_root → tương thích cũ, không có brain, có cảnh báo ----
tg0 = cc.build_channel_block("telegram", {"chat_id": "1"}, telegram_running=True, port=7777)
rj0 = _reminder_json(tg0)
check("TG không brain_root: body KHÔNG có field brain", isinstance(rj0, dict) and "brain" not in rj0)
check("TG không brain_root: có ghi chú rơi về Brain Default", "Brain Default" in tg0)

# ---- Dashboard CÓ brain_root ----
dash = cc.build_channel_block("dashboard", telegram_running=True, port=7777, brain_root=BRAIN)
check("Dashboard: recipe /reminders có brain đúng path", f'"brain":{json.dumps(BRAIN)}' in dash)
rjd = _reminder_json(dash)
check("Dashboard: body /reminders JSON hợp lệ + brain đúng", isinstance(rjd, dict) and rjd.get("brain") == BRAIN)

# ---- Dashboard KHÔNG brain_root → không brain (tương thích) ----
dash0 = cc.build_channel_block("dashboard", telegram_running=True, port=7777)
rjd0 = _reminder_json(dash0)
check("Dashboard không brain_root: body KHÔNG có brain", isinstance(rjd0, dict) and "brain" not in rjd0)

print()
if _fails:
    print("FAILED (%d): %s" % (len(_fails), ", ".join(_fails)))
    sys.exit(1)
print("ALL PASS")
