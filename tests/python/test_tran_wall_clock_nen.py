"""Trần wall-clock của fork nền phải đủ cho việc nền THẬT, và chỉnh được không cần sửa code.

    python tests/run.py tran_wall_clock

Lỗi thật (người dùng báo 18/08/2026): lịch 07:05 quét 11 phân mục Meta Ads + ghi Google
Sheet + tổng hợp gửi Telegram bị chặt ngang ở giây 300 với "Fork vượt trần 300s - đã dừng
(cap wall-clock nền)" - result rỗng, Sheet ghi dở, Telegram không có gì. Ba nơi ghim ba số
cứng khác nhau (nhắc hẹn 300, bước workflow 300, việc Kanban 600) trong khi việc nền hợp lệ
có thể chạy 30-60 phút.

Trần này là LƯỚI ĐỠ chống fork treo vô hạn chứ không phải quản chi phí (fork đơ có
idle-timeout riêng bắt sớm hơn), nên nó phải đặt theo việc dài nhất hợp lệ. Nay cả ba nơi
dùng chung aux_engine.bg_max_wall_s(): mặc định 3600s, env JAVIS_BG_MAX_WALL_S đổi được.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import re
import sys

_fails = []


def check(ten, cond, them=""):
    print(("ok   " if cond else "FAIL ") + ten + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(ten)


import aux_engine  # noqa: E402

# ---- 1. Helper: mặc định + env override + chống giá trị rác ----
os.environ.pop("JAVIS_BG_MAX_WALL_S", None)
check("mặc định 3600s (1 giờ) - đủ cho việc nền 30-60 phút",
      aux_engine.bg_max_wall_s() == 3600)
os.environ["JAVIS_BG_MAX_WALL_S"] = "7200"
check("env JAVIS_BG_MAX_WALL_S đổi được trần", aux_engine.bg_max_wall_s() == 7200)
for rac in ("abc", "-5", "0", ""):
    os.environ["JAVIS_BG_MAX_WALL_S"] = rac
    check(f"giá trị rác {rac!r} rơi về mặc định", aux_engine.bg_max_wall_s() == 3600)
os.environ.pop("JAVIS_BG_MAX_WALL_S", None)

# ---- 2. Cả ba nơi chạy nền dùng CHUNG helper, không còn số cứng ----
for f, mo_ta in (("reminders.py", "nhắc hẹn/cron"), ("tasks.py", "việc Kanban"),
                 ("main.py", "bước workflow")):
    src = (ROOT / "server" / f).read_text(encoding="utf-8")
    check(f"{f} ({mo_ta}) đặt trần qua aux_engine.bg_max_wall_s()",
          "aux_engine.bg_max_wall_s()" in src)
    # Số cứng cũ không được quay lại: bắt đúng dạng gán `max_wall_s = <số>` (learn.py và
    # test dùng số riêng của chúng, không nằm trong ba file này).
    cung = re.findall(r"max_wall_s\s*=\s*\d+", src)
    check(f"{f} không còn ghim số cứng cho max_wall_s (thấy: {cung})", not cung)

print()
if _fails:
    print(f"{len(_fails)} test HỎNG: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả test tran_wall_clock_nen đã qua.")
