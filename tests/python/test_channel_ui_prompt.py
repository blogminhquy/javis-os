"""Khối kênh web dặn model về javis_ui / javis_app_*, và tiêu đề hội thoại lột khối ngữ cảnh UI.

    python tests/run.py channel_ui_prompt

Voice V1 chỉ thêm prompt ở khối KÊNH WEB (dashboard). Telegram không nhận mấy dòng điều khiển
dashboard: ở đó không có dashboard nào để mở, dặn thêm chỉ tốn token và dễ khiến model gọi
nhầm. Khối `[NGỮ CẢNH GIAO DIỆN: ...]` do dashboard chèn trước câu hỏi phải bị lột khỏi tiêu
đề hội thoại, cùng cách với khối FILE ĐANG MỞ (bug 2026-07-31 lặp lại nếu quên).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-chui-"))

import channel_context  # noqa: E402
import sessions  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


web = channel_context.build_channel_block("dashboard", {"session_id": "s123"}, False, 7777, "/brain")
tg = channel_context.build_channel_block("telegram", {"chat_id": 1, "user_name": "A"}, True, 7777, "/brain")

check("web: nhắc javis_ui", "javis_ui" in web)
check("web: nhắc javis_app_open / javis_app_close", "javis_app_open" in web and "javis_app_close" in web)
check("web: giải nghĩa khối NGỮ CẢNH GIAO DIỆN", "NGỮ CẢNH GIAO DIỆN" in web and "ngắt_lời" in web)
check("web: vẫn có mã phiên", "s123" in web)
check("telegram: KHÔNG có đoạn điều khiển dashboard", "javis_ui" not in tg and "NGỮ CẢNH GIAO DIỆN" not in tg)

# Tiêu đề hội thoại
msg = ('[NGỮ CẢNH GIAO DIỆN: trang=kanban; chọn="đoạn abc"]\n\n'
       "Tóm tắt giúp mình việc đang chạy")
check("tiêu đề: lột khối ngữ cảnh UI", sessions.title_from_message(msg) == "Tóm tắt giúp mình việc đang chạy")
msg2 = ("[FILE ĐANG MỞ trong trình sửa của Javis: /b/a.md\nĐây là file]\n\n"
        '[NGỮ CẢNH GIAO DIỆN: trang=files; ngắt_lời="Doanh thu tháng này"]\n\n'
        "Viết tiếp phần kết luận")
check("tiêu đề: lột cả ghim lẫn ngữ cảnh UI", sessions.title_from_message(msg2) == "Viết tiếp phần kết luận")
check("tiêu đề: câu mở bằng [gấp] vẫn giữ", sessions.title_from_message("[gấp] xem giúp anh doanh thu").startswith("[gấp]"))

if _fails:
    print("\nFAIL:", len(_fails), _fails)
    raise SystemExit(1)
print("\nOK - channel ui prompt")
