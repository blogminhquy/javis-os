"""Test /notes trên Telegram: lệnh có trong menu + caption-lệnh kèm ảnh route đúng.

Chạy tay / CI (không cần pytest, không chạm mạng):

    cd server && python test_telegram_notes.py

Phủ: BOT_COMMANDS có 'notes' và mọi tên lệnh hợp lệ (a-z0-9_); _caption_command_text
(caption là lệnh → đưa lệnh lên đầu + marker path; caption thường/rỗng → giữ nguyên;
đính kèm rỗng → rỗng) và kết quả nhánh lệnh parse ra đúng cmd 'notes' + arg còn path.
"""
import os
import re
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-tgnotes-"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import telegram_bot as tb  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- BOT_COMMANDS ----
names = [c["command"] for c in tb.BOT_COMMANDS]
check("BOT_COMMANDS có 'notes'", "notes" in names)
check("notes có mô tả nhắc tới Sources", any(
    c["command"] == "notes" and "source" in c["description"].lower() for c in tb.BOT_COMMANDS))
_NAME_RE = re.compile(r"^[a-z0-9_]+$")   # Telegram chỉ nhận a-z0-9_ cho tên lệnh menu
check("mọi tên lệnh hợp lệ a-z0-9_", all(_NAME_RE.match(n) for n in names))
check("không trùng tên lệnh", len(names) == len(set(names)))

# ---- _caption_command_text: marker 1 dòng, _ingest_attachment ghép caption vào cuối ----
MARK = "[Người dùng gửi ảnh qua Telegram, gateway đã tải về: /inbox/telegram/photo_9.jpg]"

# caption là lệnh + có nội dung note → lệnh lên đầu, marker path theo sau
ing1 = MARK + "\n/notes mua sữa cho khách"
out1 = tb._caption_command_text(ing1, "/notes mua sữa cho khách")
check("caption '/notes ...' → bắt đầu bằng lệnh", out1.startswith("/notes "))
check("caption '/notes ...' → còn giữ marker path", MARK in out1)

# _dispatch parse: split(maxsplit=1) phải ra cmd 'notes' + arg còn path (mô phỏng _dispatch)
head = out1.split(maxsplit=1)
cmd = head[0][1:].lower()
arg = head[1].strip() if len(head) > 1 else ""
check("parse ra cmd 'notes'", cmd == "notes")
check("arg giữ nội dung note", "mua sữa cho khách" in arg)
check("arg giữ đường dẫn ảnh", "/inbox/telegram/photo_9.jpg" in arg)

# caption '/notes' TRỐNG (chỉ chộp ảnh) → vẫn route lệnh, arg = marker path
out_bare = tb._caption_command_text(MARK + "\n/notes", "/notes")
check("caption '/notes' trống → vẫn là lệnh", out_bare.startswith("/notes"))
check("caption '/notes' trống → arg có path", MARK in out_bare)

# caption THƯỜNG (không phải lệnh) → giữ nguyên ingested (hành vi cũ)
ing_norm = MARK + "\nảnh sản phẩm nước mắm"
check("caption thường → giữ nguyên ingested", tb._caption_command_text(ing_norm, "ảnh sản phẩm nước mắm") == ing_norm)
check("caption thường → KHÔNG bắt đầu bằng '/'", not tb._caption_command_text(ing_norm, "ảnh sản phẩm nước mắm").startswith("/"))

# caption rỗng (ảnh không caption) → giữ nguyên marker
check("caption rỗng → giữ marker", tb._caption_command_text(MARK, "") == MARK)
check("caption None → giữ marker", tb._caption_command_text(MARK, None) == MARK)

# đính kèm rỗng (không tải được gì) + caption lệnh → rỗng (không có file để nói)
check("ingested rỗng → trả rỗng", tb._caption_command_text("", "/notes x") == "")

print()
if _fails:
    print("FAILED (%d): %s" % (len(_fails), ", ".join(_fails)))
    sys.exit(1)
print("ALL PASS")
