"""Test cấu trúc chuẩn vault có bộ sổ bullet journal (v0.9.219). Chạy tay / CI:

    python tests/run.py vault_scaffold

KHÔNG mạng. Phủ: _check_structure nhận diện linh hoạt tên có số thứ tự
("01 - Daily Log" / "Daily Log" / "daily"), /vault/init tạo đủ 4 thư mục log
khi thiếu, chạy lại lần 2 không tạo trùng (idempotent), vault đã có sổ theo
tên khác thì KHÔNG đẻ thêm bản "01 - ...".
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-scaftest-"))

import main  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok  " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


LOG_KEYS = ("daily", "weekly", "monthly", "future")
LOG_DIRS = ("01 - Daily Log", "02 - Weekly Log", "03 - Monthly Log", "04 - Future Log")


def present_keys(root):
    return {i["key"] for i in main._check_structure(Path(root)) if i["present"]}


try:
    # ---- 1. Nhận diện các biến thể tên ----
    v1 = Path(tempfile.mkdtemp(prefix="javis-scaf1-"))
    for d in LOG_DIRS:
        (v1 / d).mkdir()
    check("detect: tên chuẩn '01 - Daily Log'...", set(LOG_KEYS) <= present_keys(v1))

    v2 = Path(tempfile.mkdtemp(prefix="javis-scaf2-"))
    for d in ("Daily Log", "weekly", "Monthly", "future log"):
        (v2 / d).mkdir()
    check("detect: tên không số / viết thường vẫn tính là có", set(LOG_KEYS) <= present_keys(v2))

    v3 = Path(tempfile.mkdtemp(prefix="javis-scaf3-"))
    check("detect: vault trống báo thiếu cả 4", not (set(LOG_KEYS) & present_keys(v3)))
    check("detect: log là mục tuỳ chọn, không essential",
          all(not i["essential"] for i in main._check_structure(v3) if i["key"] in LOG_KEYS))

    # ---- 2. Chuẩn hoá (/vault/init) tạo đủ 4 sổ ----
    v4 = Path(tempfile.mkdtemp(prefix="javis-scaf4-")) / "brains" / "vault"
    main._brain_root = lambda brain: str(v4)
    r = asyncio.run(main.vault_init(brain="brain"))
    check("init: chạy ok", isinstance(r, dict) and r.get("ok"))
    check("init: tạo đủ 4 thư mục log đúng tên", all((v4 / d).is_dir() for d in LOG_DIRS))
    check("init: các mục cũ vẫn được tạo (sources/agents/wiki...)",
          (v4 / "sources").is_dir() and (v4 / "agents").is_dir() and (v4 / "wiki").is_dir())

    check("init: có thư mục Dashboard + seed Dashboard.md",
          (v4 / "00 - Dashboard" / "Dashboard.md").is_file())
    # CANARY 03/09: Task Inbox KHÔNG còn được rải sẵn. Nút "+ Việc" tự tạo nó ở lần thêm
    # việc đầu tiên (test_dataview_tasks canh đường đó), nên seed sẵn chỉ để lại một file
    # rỗng trong Dashboard của người không dùng tính năng ấy - chủ repo báo chưa mở tới nó
    # lần nào. Rải lại là quay về đúng chỗ đã bỏ.
    check("CANARY: init KHÔNG rải sẵn Task Inbox.md",
          not (v4 / "00 - Dashboard" / "Task Inbox.md").exists())
    check("init: seed Dashboard.md dùng khối ```tasks chạy thật",
          "```tasks" in (v4 / "00 - Dashboard" / "Dashboard.md").read_text(encoding="utf-8"))

    r2 = asyncio.run(main.vault_init(brain="brain"))
    check("init: idempotent - lần 2 không báo tạo lại log",
          isinstance(r2, dict) and not any("log" in c for c in r2.get("created", [])))

    # ---- 3. Vault đã có sổ tên khác -> không đẻ bản trùng ----
    v5 = Path(tempfile.mkdtemp(prefix="javis-scaf5-")) / "brains" / "vault"
    (v5 / "Daily Log").mkdir(parents=True)
    main._brain_root = lambda brain: str(v5)
    asyncio.run(main.vault_init(brain="brain"))
    check("init: đã có 'Daily Log' thì KHÔNG tạo thêm '01 - Daily Log'",
          not (v5 / "01 - Daily Log").exists() and (v5 / "02 - Weekly Log").is_dir())
finally:
    pass

print()
if _fails:
    print(f"{len(_fails)} test FAIL: {_fails}")
    sys.exit(1)
print("Tất cả test scaffold OK")
