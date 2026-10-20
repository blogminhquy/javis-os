"""`javis_edit_file`: sửa từng đoạn, khớp mờ, lỗi dạy được model, kiểm lỗi sau khi sửa (0.256.0).

    python tests/run.py edit_file_khop_mo

Công cụ này là lý do chính engine API của Javis sửa được code mà không viết lại cả file. Ba
thứ phải giữ:
  - **Khớp chính xác luôn thắng**, khớp mờ chỉ là lưới đỡ cho thụt lề, khoảng trắng, dấu nháy
    cong, "\\n" bị escape hai lần. Khớp mờ thì thụt lề của đoạn mới theo file, không theo model.
  - **Không đoán bừa**: khớp nhiều chỗ mà không replace_all là từ chối kèm vị trí; hai chiến
    lược "tương tự" không bao giờ chạy với replace_all.
  - **Gửi lại một sửa đã áp không nhân đôi nó.**
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-edit-"))

import coding_files as cf  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


C = "def a():\n    x = 1\n    return x\n\ndef b():\n    x = 1\n    return 2\n"

# ---- 1. Từng chiến lược ----
r = cf.thay_the(C, "return 2", "return 3")
check("khớp chính xác", r["ok"] and r["chien_luoc"] == "exact" and "return 3" in r["content"])

r = cf.thay_the(C, "def a():\n  x = 1\n  return x", "def a():\n  x = 5\n  return x")
check("line_trimmed khi model thụt 2 dấu cách", r["ok"] and r["chien_luoc"] == "line_trimmed")
check("thụt lề của đoạn mới theo file (4 dấu cách)", "\n    x = 5\n    return x" in r["content"])

C2 = "if ok:\n    goi(a,   b)\n"
r = cf.thay_the(C2, "goi(a, b)", "goi(a, c)")
check("whitespace_normalized gộp khoảng trắng", r["ok"] and r["chien_luoc"] == "whitespace_normalized")

r = cf.thay_the("x = 1\ny = 2\n", "x = 1\\ny = 2", "x = 1\ny = 3")
check("escape_normalized khi '\\n' bị escape hai lần", r["ok"] and r["chien_luoc"] == "escape_normalized"
      and "y = 3" in r["content"])

r = cf.thay_the('print("xin chào")\n', "print(\u201cxin chào\u201d)", 'print("chào")')
check("unicode_normalized cho dấu nháy cong", r["ok"] and r["chien_luoc"] == "unicode_normalized")

C3 = "def f():\n    a = 1\n    b = 2\n    c = 3\n    return a\n"
r = cf.thay_the(C3, "def f():\n    a = 1\n    b = 22\n    c = 3\n    return a",
                "def f():\n    return 0")
check("chiến lược tương tự khi lệch nhẹ ở giữa", r["ok"] and r["chien_luoc"] in cf.TUONG_TU)

# ---- 2. Lỗi dạy được model ----
r = cf.thay_the(C, "x = 1", "x = 2")
check("khớp nhiều chỗ thì từ chối", not r["ok"] and "2 chỗ" in r["loi"])
check("kèm vị trí từng chỗ", "L2:" in r["loi"] and "L6:" in r["loi"])
r = cf.thay_the(C, "x = 1", "x = 2", replace_all=True)
check("replace_all sửa hết", r["ok"] and r["so_cho"] == 2 and r["content"].count("x = 2") == 2)
r = cf.thay_the(C, "return 99", "return 3")
check("không khớp thì có gợi ý dòng gần giống", not r["ok"] and "L3:" in r["loi"])
check("old_string rỗng bị từ chối", not cf.thay_the(C, "  ", "x")["ok"])
check("old == new bị từ chối", not cf.thay_the(C, "return 2", "return 2")["ok"])
r = cf.thay_the(C3, "def f():\n    a = 1\n    b = 22\n    c = 3\n    return a", "x", replace_all=True)
check("chiến lược tương tự KHÔNG chạy với replace_all", not r["ok"])

# ---- 3. Sửa đã áp thì không áp lại ----
r1 = cf.thay_the(C, "def a():", "def a():\n    pass")
r2 = cf.thay_the(r1["content"], "def a():", "def a():\n    pass")
check("gửi lại sửa đã áp (new chứa old) là không đổi", r2["ok"] and r2.get("khong_doi")
      and r2["content"] == r1["content"])
r3 = cf.thay_the(cf.thay_the(C, "return 2", "return 7")["content"], "return 2", "return 7")
check("gửi lại sửa đã áp (old không còn) là không đổi", r3["ok"] and r3.get("khong_doi"))

# ---- 4. Model chép nguyên số dòng từ output đọc ----
r = cf.thay_the(C, "7|    return 2", "7|    return 9")
check("bỏ tiền tố 'N|' khi mọi dòng đều có", r["ok"] and "return 9" in r["content"] and "7|" not in r["content"])

# ---- 5. Trên đĩa: CRLF, diff, lint chỉ báo lỗi mới ----
d = Path(tempfile.mkdtemp())
f = d / "m.py"
f.write_bytes(C.replace("\n", "\r\n").encode())
out = cf.sua_file(f, "return 2", "return 3", sid="s1")
check("sửa được file CRLF", out.startswith("Đã sửa") and b"return 3\r\n" in f.read_bytes())
check("giữ CRLF, không trộn LF", b"\n" not in f.read_bytes().replace(b"\r\n", b""))
check("trả unified diff", "-    return 2" in out and "+    return 3" in out)
out = cf.sua_file(f, "return 3", "return (", sid="s1")
check("lỗi cú pháp do lần sửa sinh ra thì cảnh báo", "CẢNH BÁO" in out)
out = cf.sua_file(f, "return x", "return y", sid="s1")
check("lỗi có từ trước thì im", "CẢNH BÁO" not in out)
j = d / "c.json"
j.write_text('{"a": 1}', encoding="utf-8")
check("json hỏng sau khi sửa thì cảnh báo", "CẢNH BÁO" in cf.sua_file(j, '"a": 1', '"a": 1,', sid="s1"))
check("file không có thì báo dùng write_file", "javis_write_file" in cf.sua_file(d / "khong.py", "a", "b"))
for _ in range(3):
    out = cf.sua_file(j, "khong-co-dau", "x", sid="s2")
check("hỏng 3 lần liên tiếp thì bảo đọc lại file", "Đã hỏng 3 lần" in out)

# ---- 6. Ranh giới mã nguồn ----
_src = (SERVER / "coding_files.py").read_text(encoding="utf-8")
for cam in ("import main", "from main", "fastapi", "import mcp_hub"):
    check(f"module thuần, không '{cam}'", cam not in _src)
check("không có ký tự em dash trong mã", "\u2014" not in _src and "\u2013" not in _src)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_edit_file_khop_mo: tất cả pass")
