"""Hồi quy: reminder mode=task chỉ gửi kết quả, không lộ prompt nội bộ.

Chạy:
    python tests/run.py reminder_delivery
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-reminder-delivery-state-")

import reminders  # noqa: E402

fails = []
sent = []
brain = Path(tempfile.mkdtemp(prefix="javis-reminder-delivery-brain-"))


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


def atomic_write(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


async def fake_send(chat_id, text):
    sent.append((chat_id, text))
    return True, ""


deps = reminders.RemindersDeps(
    brain_root=lambda _brain: str(brain),
    atomic_write_text=atomic_write,
    send_telegram=fake_send,
    build_system_prompt=lambda _brain: "",
    aux_model=lambda: None,
    safe_tools=[],
    readonly_tools=[],
    scheduler_brains=lambda: [],
)
feature = reminders.RemindersFeature(deps)
internal = (
    "Bạn là Coach Mục Tiêu & Kỷ Luật. Mở/tạo Daily Log rồi hỏi user trọng tâm "
    "quan trọng nhất hôm nay và Big 3."
)
answer = "Hôm nay 27/07/2026, việc quan trọng nhất anh muốn chốt là gì? Và Big 3 hôm nay của anh là gì?"


async def run():
    # `_run_task` nhận thêm mức quyền từ 0.26.0 (nhắc hẹn có 3 mức như việc lặp). Bắt luôn
    # tham số đó ở stub để test này khoá đúng phần GIAO KẾT QUẢ, không phải chữ ký hàm.
    async def task_ok(_brain, _text, _muc_quyen=""):
        return answer, ""

    feature._run_task = task_ok
    await feature._fire(str(brain), {
        "id": "r_test_ok",
        "mode": "task",
        "text": internal,
        "label": "Coach buổi sáng",
        "chat_id": "123",
    })
    check("task thành công gửi đúng phần kết quả", sent[-1] == ("123", answer))
    check("task thành công không lộ prompt nội bộ", internal not in sent[-1][1])
    check("task thành công bỏ prefix 'Javis đã làm'", "Javis đã làm" not in sent[-1][1])

    async def task_error(_brain, _text, _muc_quyen=""):
        return "", "engine timeout"

    feature._run_task = task_error
    await feature._fire(str(brain), {
        "id": "r_test_error",
        "mode": "task",
        "text": internal,
        "label": "Coach buổi sáng",
        "chat_id": "123",
    })
    check("task lỗi báo ngắn gọn", "engine timeout" in sent[-1][1])
    check("task lỗi cũng không lộ prompt nội bộ", internal not in sent[-1][1])

    await feature._fire(str(brain), {
        "id": "r_test_notify",
        "mode": "notify",
        "text": "Uống thuốc",
        "chat_id": "123",
    })
    check("notify thường vẫn gửi nguyên nội dung nhắc", sent[-1][1] == "⏰ Nhắc bạn: Uống thuốc")


asyncio.run(run())

if fails:
    print(f"\nFAIL - test_reminder_delivery: {len(fails)} lỗi: {fails}")
    sys.exit(1)
print("\nOK - test_reminder_delivery: tất cả pass")
