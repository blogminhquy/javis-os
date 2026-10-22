"""Rào ghi đè file chưa đọc trong phiên Coding, và mốc khôi phục trước khi ghi (0.256.0).

    python tests/run.py rao_ghi_de

Ghi đè mù là cách nhanh nhất làm mất code người khác vừa viết. Trong thư mục làm việc của phiên
Coding, `javis_write_file` chỉ ghi đè một file ĐÃ CÓ khi phiên đã đọc trọn nó và nó chưa đổi từ
lúc đọc. Rào này phải từ chối TRƯỚC khi chạm đĩa, và KHÔNG áp cho brain (luồng ghi ghi chú, ghi
nhớ, báo cáo xưa nay không phải đọc trước).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="javis-raoghide-")
os.environ["JAVIS_STATE_DIR"] = _TMP

import coding_checkpoint  # noqa: E402
import mcp_hub  # noqa: E402
from coding_ctx import CodingToolContext  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def goi(route, ten, args):
    return asyncio.run(route[ten]["call"](args))


VAULT = Path(_TMP) / "brain"
WS = Path(_TMP) / "du-an"
VAULT.mkdir(parents=True)
WS.mkdir(parents=True)
(VAULT / "note.md").write_text("cũ", encoding="utf-8")
(WS / "app.py").write_text("print(1)\n" * 5, encoding="utf-8")

ctx = CodingToolContext(session_id="phien-ghi", workspace_root=str(WS), workspace_roots=(str(WS),),
                        permission_mode="auto")
_t, r = mcp_hub._builtin_tools("auto", str(VAULT), workspace_root=[str(WS)], coding_ctx_cua_phien=ctx)

# ---- 1. Chưa đọc thì không ghi đè ----
ra = goi(r, "javis_write_file", {"path": "app.py", "content": "xoa het"})
check("ghi đè file chưa đọc bị từ chối", ra.startswith("ERROR") and "javis_edit_file" in ra)
check("từ chối TRƯỚC khi chạm đĩa", (WS / "app.py").read_text(encoding="utf-8") == "print(1)\n" * 5)

# ---- 2. Đọc trọn rồi thì ghi được ----
goi(r, "javis_read_file", {"path": "app.py"})
ra = goi(r, "javis_write_file", {"path": "app.py", "content": "print(2)\n"})
check("đọc trọn rồi thì ghi đè được", ra.startswith("Đã ghi") and (WS / "app.py").read_text() == "print(2)\n")
ra = goi(r, "javis_write_file", {"path": "app.py", "content": "print(3)\n"})
check("vừa ghi xong thì ghi tiếp được (nội dung model đã biết)", ra.startswith("Đã ghi"))

# ---- 3. File đổi sau lần đọc thì không ghi đè ----
time.sleep(0.02)
(WS / "app.py").write_text("nguoi dung sua tay\n", encoding="utf-8")
os.utime(WS / "app.py", (time.time() + 5, time.time() + 5))
ra = goi(r, "javis_write_file", {"path": "app.py", "content": "print(4)\n"})
check("file đổi sau khi đọc thì từ chối", ra.startswith("ERROR") and "đã đổi" in ra)
check("nội dung người dùng còn nguyên", (WS / "app.py").read_text() == "nguoi dung sua tay\n")

# ---- 4. Đọc dở thì không ghi đè ----
(WS / "dai.py").write_text("\n".join(f"x{i}" for i in range(3000)), encoding="utf-8")
goi(r, "javis_read_file", {"path": "dai.py", "limit": 100})
ra = goi(r, "javis_write_file", {"path": "dai.py", "content": "ngan"})
check("mới đọc một phần thì từ chối", ra.startswith("ERROR") and "mới đọc tới dòng" in ra)

# ---- 5. File mới và brain: không rào ----
check("tạo file mới trong repo thì ghi bình thường",
      goi(r, "javis_write_file", {"path": "moi.py", "content": "x = 1\n"}).startswith("Đã ghi"))
check("brain không bị rào: ghi đè note chưa đọc vẫn được",
      goi(r, "javis_write_file", {"path": "note.md", "content": "mới"}).startswith("Đã ghi"))
ra = goi(r, "javis_write_file", {"path": "moi2.py", "content": "1|a\n2|b\n3|c\n4|d\n"})
check("từ chối nội dung dán nguyên output có số dòng", ra.startswith("ERROR") and "số|" in ra)

# ---- 6. Mốc khôi phục trước thao tác thay đổi ----
ds = coding_checkpoint.danh_sach("phien-ghi")
check("lần ghi đầu tiên trong repo có tạo mốc", len(ds) >= 1 and ds[-1]["ws"] == str(WS.resolve()))
n = len(ds)
goi(r, "javis_write_file", {"path": "moi3.py", "content": "y = 2\n"})
check("cùng một lượt thì không tạo thêm mốc", len(coding_checkpoint.danh_sach("phien-ghi")) == n)
coding_checkpoint.luot_moi("phien-ghi")
goi(r, "javis_write_file", {"path": "moi4.py", "content": "z = 3\n"})
check("lượt mới thì có mốc mới", len(coding_checkpoint.danh_sach("phien-ghi")) == n + 1)

# ---- 7. Mức Plan: không ghi được gì ----
ctx_s = CodingToolContext(session_id="phien-plan", workspace_root=str(WS), workspace_roots=(str(WS),),
                          permission_mode="suggest")
_t, r_s = mcp_hub._builtin_tools("suggest", str(VAULT), workspace_root=[str(WS)], coding_ctx_cua_phien=ctx_s)
check("mức Plan: ghi file bị chặn", goi(r_s, "javis_write_file", {"path": "x.py", "content": "1"}).startswith("ERROR"))
check("mức Plan: sửa file bị chặn",
      goi(r_s, "javis_edit_file", {"path": "moi.py", "old_string": "x = 1", "new_string": "x = 2"}).startswith("ERROR"))
check("mức Plan: file không đổi", (WS / "moi.py").read_text() == "x = 1\n")

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_rao_ghi_de: tất cả pass")
