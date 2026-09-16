"""Test: registry Lịch giả đã xoá sạch, nguồn thật của trang Việc còn nguyên. Chạy tay / CI:

    python tests/run.py jobs

Bối cảnh: automations.json CHƯA TỪNG có executor - _scheduler_loop (main.py:3613-3656) không
có nhánh nào đọc nó, và 0 file automations.json tồn tại trên cả 4 brain. Giai đoạn 1 xoá nó,
KHÔNG thêm endpoint nào: trang Việc dùng thẳng /loops + /reminders đã có sẵn.

Phủ:
- 4 path /automations* đã biến mất khỏi app.routes.
- 3 helper registry + 2 lớp chiếu đã xoá (caller duy nhất của chúng là /automations GET).
- caps: key 'automations' đã xoá, và _gather_capabilities/_render_javis_index còn chạy được
  (nếu xoá helper mà để lại lời gọi thì rebuild_javis_index NameError MỖI tick scheduler).
- Các endpoint THẬT mà trang Việc dựa vào vẫn còn sống.
- /automations/sync đã xoá: nó ghi vào chính registry vừa xoá, và là engine call ít rào nhất.
"""
from _paths import ROOT, SERVER, moi_duong_dan  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-jobstest-"))

import main  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok  " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


src = (SERVER / "main.py").read_text(encoding="utf-8")
# moi_duong_dan: đi đệ quy qua router con. Đọc thẳng app.routes thì từ fastapi 0.141 nó
# không thấy 67 endpoint nằm trong router con, và phép thử "đã xoá" bên dưới XANH OAN.
paths = moi_duong_dan(main.app)

# ---- 1. Route Lịch đã chết ----
check("route: mọi /automations* đã xoá", not any(p.startswith("/automations") for p in paths))

# ---- 2. Helper registry đã xoá hẳn (không còn đường ghi automations.json) ----
check("helper: _read_automations đã xoá", not hasattr(main, "_read_automations"))
check("helper: _write_automations đã xoá", not hasattr(main, "_write_automations"))
check("helper: _automations_path đã xoá", not hasattr(main, "_automations_path"))
# Assert CHÍNH XÁC vào biểu thức dựng đường dẫn, KHÔNG assert chuỗi trần "automations.json":
# main.py:121 có nhắc tên file đó trong một comment không liên quan (bàn về ghi file nguyên
# tử), và comment mới ở đầu khối cũng nhắc nó để giải thích vì sao đã xoá. Assert trần sẽ
# BẤT KHẢ THI dù code đã đúng.
check("nguồn: không còn code dựng đường dẫn tới automations.json",
      '"Javis" / "automations.json"' not in src)

# ---- 2b. Hai lớp chiếu vào hình dạng Lịch giả cũng chết theo ----
# Caller duy nhất của cả hai là /automations GET (main.py:3199). Chúng chiếu loop/nhắc hẹn
# vào dòng-Lịch với chuỗi schedule BỊA RA lúc GET (main.py:3187). Hết Lịch thì hết lý do.
check("chiếu: _loops_as_routines đã xoá", not hasattr(main, "_loops_as_routines"))
check("chiếu: pending_as_automations đã xoá",
      not hasattr(main.reminders_feature, "pending_as_automations"))

# ---- 3. caps sạch VÀ còn chạy được ----
# Đây là assert quan trọng nhất của task: xoá _read_automations mà để lại lời gọi ở
# _gather_capabilities:3352 → rebuild_javis_index (main.py:3650-3651) ném NameError mỗi tick.
caps = main._gather_capabilities("brain")
check("caps: không còn key 'automations'", "automations" not in caps)
check("caps: _gather_capabilities vẫn chạy (không NameError)", isinstance(caps, dict))
check("caps: _render_javis_index vẫn chạy", isinstance(main._render_javis_index(caps), str))
check("caps: index không còn mục 'Lịch (automations)'",
      "Lịch (automations)" not in main._render_javis_index(caps))

# ---- 4. Endpoint THẬT mà trang Việc dựa vào phải còn sống ----
# Xoá Lịch KHÔNG được kéo theo hai nguồn thật. Task 3 (UI) gọi đúng ba cái này; nếu task này
# xoá nhầm thì trang Việc trắng và test UI mới phát hiện - bắt ngay tại đây rẻ hơn nhiều.
check("route: GET /loops còn (trang Việc lấy loop từ đây)", "/loops" in paths)
check("route: GET /reminders còn (trang Việc lấy nhắc hẹn từ đây)", "/reminders" in paths)
check("route: POST /reminders/cancel còn (nút Huỷ nhắc hẹn)", "/reminders/cancel" in paths)

# ---- 5. /automations/sync đã xoá: không còn engine call bypassPermissions ----
# main.py:3269 cũ gọi claude_engine(..., tag="routines") KHÔNG truyền allowed_tools →
# claude_sdk_engine.py:290-301 đặt permission_mode="bypassPermissions" + nạp setting_sources.
# Đây là engine call ít rào nhất codebase; "CHỈ LIỆT KÊ" của nó chỉ là chữ trong prompt.
check("sync: route /automations/sync đã xoá", "/automations/sync" not in paths)
check("sync: không còn engine call tag='routines'", 'tag="routines"' not in src)
check("sync: không còn prompt RemoteTrigger list", "RemoteTrigger" not in src)


if _fails:
    print(f"\nFAIL - test_jobs: {len(_fails)} lỗi: {_fails}")
    sys.exit(1)
print("\nOK - test_jobs: tất cả pass")
