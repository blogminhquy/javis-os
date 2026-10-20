"""Đọc theo đoạn và tìm trong code cho engine API (0.256.0).

    python tests/run.py read_search_file

Hai lời hứa phải giữ:
  - Chat thường KHÔNG truyền offset/limit thì `javis_read_file` trả y như cũ (chatbot và luồng
    brain dựa vào output đó). Trong thư mục làm việc của phiên Coding, hoặc khi xin offset/limit,
    output có số dòng "N|..." và báo đọc tiếp ở đâu.
  - `javis_search_files` tìm được cả khi máy không có ripgrep (Windows thường không có).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="javis-readsearch-")
os.environ["JAVIS_STATE_DIR"] = _TMP

import coding_files as cf  # noqa: E402
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
(VAULT / "ghi-chu").mkdir(parents=True)
(WS / "src" / "con").mkdir(parents=True)
(WS / "node_modules" / "rac").mkdir(parents=True)
(VAULT / "ghi-chu" / "a.md").write_text("dòng một\ndòng hai\n", encoding="utf-8")
DAI = "\n".join(f"dong {i}" for i in range(1, 3001)) + "\n"
(WS / "src" / "dai.py").write_text(DAI, encoding="utf-8")
(WS / "src" / "con" / "b.py").write_text("def tim_toi():\n    return 42\n", encoding="utf-8")
(WS / "node_modules" / "rac" / "x.js").write_text("tim_toi()\n", encoding="utf-8")

# ---- 1. Hàm thuần đọc theo đoạn ----
out, den, tong = cf.doc_theo_dong(DAI, 1, 2000)
check("mặc định 2000 dòng đầu", den == 2000 and tong == 3000 and out.startswith("   1|dong 1"))
check("báo đọc tiếp ở đâu", "offset=2001" in out)
out, den, tong = cf.doc_theo_dong(DAI, 2995, 50)
check("offset gần cuối đọc tới hết, không báo đọc tiếp", den == 3000 and "offset=" not in out)
out, _, _ = cf.doc_theo_dong(DAI, 5000, 10)
check("offset quá cuối file thì nói rõ", "quá cuối file" in out)
out, den, _ = cf.doc_theo_dong("x" * 60_000 + "\n" + "y" * 60_000 + "\n", 1, 2000)
check("chạm trần ký tự thì cắt theo ranh giới dòng", den == 1 and "offset=2" in out)

# ---- 2. Qua hub: chat thường giữ output cũ ----
_t, r_thuong = mcp_hub._builtin_tools("full", str(VAULT))
check("chat thường: đọc không offset trả nguyên văn cũ",
      goi(r_thuong, "javis_read_file", {"path": "ghi-chu/a.md"}) == "dòng một\ndòng hai\n")
check("chat thường: xin offset/limit thì có số dòng",
      goi(r_thuong, "javis_read_file", {"path": "ghi-chu/a.md", "offset": 2, "limit": 1}).startswith("2|dòng hai"))
check("chat thường cũng có javis_edit_file và javis_search_files",
      "javis_edit_file" in r_thuong and "javis_search_files" in r_thuong)

# ---- 3. Qua hub: phiên Coding đọc có số dòng ----
ctx = CodingToolContext(session_id="phien-1", workspace_root=str(WS), workspace_roots=(str(WS),),
                        permission_mode="auto")
_t, r_cd = mcp_hub._builtin_tools("auto", str(VAULT), workspace_root=[str(WS)], coding_ctx_cua_phien=ctx)
ra = goi(r_cd, "javis_read_file", {"path": "src/dai.py"})
check("phiên Coding: file trong repo đọc có số dòng", ra.startswith("   1|dong 1") and "offset=2001" in ra)
check("phiên Coding: file brain không đổi kiểu đọc",
      goi(r_cd, "javis_read_file", {"path": "ghi-chu/a.md"}) == "dòng một\ndòng hai\n")

# ---- 4. Tìm ----
ra = goi(r_cd, "javis_search_files", {"pattern": "tim_toi"})
check("tìm theo nội dung, đường dẫn tương đối repo", "src/con/b.py:1:def tim_toi" in ra)
check("bỏ qua node_modules", "node_modules" not in ra)
ra = goi(r_cd, "javis_search_files", {"pattern": "*.py", "target": "files"})
check("tìm theo tên bằng glob", "src/dai.py" in ra and "src/con/b.py" in ra)
ra = goi(r_cd, "javis_search_files", {"pattern": "dong", "file_glob": "*.py", "limit": 5})
check("limit và báo xem tiếp", ra.count("\n") >= 4 and "offset=5" in ra)
ra = goi(r_cd, "javis_search_files", {"pattern": "return", "path": "src/con", "context": 1})
check("context kèm dòng xung quanh", "def tim_toi" in ra and "return 42" in ra)
ra = goi(r_cd, "javis_search_files", {"pattern": "x", "path": "/etc"})
check("đường dẫn ngoài brain và repo bị từ chối", ra.startswith("ERROR"))

# Không có ripgrep: bản Python phải cho cùng kết quả cốt lõi.
ra = cf.tim(WS, "tim_toi", hien_thi=WS, dung_rg=False)
check("không có rg vẫn tìm được", "src/con/b.py:1:" in ra and "node_modules" not in ra)
ra = cf.tim(WS, "b.py", target="files", hien_thi=WS, dung_rg=False)
check("không có rg vẫn tìm được theo tên", ra.strip() == "src/con/b.py")
ra = cf.tim(WS, "tim_toi(", hien_thi=WS, dung_rg=False)
check("regex hỏng thì tìm như chữ thường", "src/con/b.py" in ra)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_read_search_file: tất cả pass")
