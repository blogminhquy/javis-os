"""Chữa file .md đã bị vòng lưu WYSIWYG của bản cũ làm hỏng.

    python tests/python/test_sua_md_hong.py

Bản <= 0.33.3 lưu note .md qua trình sửa trực quan là phá hai thứ (xem server/md_repair.py):
frontmatter `---` biến thành `* * *`, và dấu gạch chéo dồn lên qua mỗi lần lưu. 0.33.4 bịt
đường đó; file đã hỏng thì phải chữa lại.

Thứ test này canh gắt nhất KHÔNG phải "có chữa được không" mà là **KHÔNG ĐƯỢC CHỮA NHẦM**:
đây là mã tự tay ghi đè note của người dùng, nên một cái nhận dạng quá tay còn tệ hơn là để
nguyên file hỏng. Mỗi luật đều đi kèm một ca âm tính canh đúng chỗ đó.
"""
import asyncio
import json
import os
import tempfile
from pathlib import Path

from _paths import ROOT, SERVER  # noqa: E402,F401

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-suamd-"))

import main  # noqa: E402
import md_repair as M  # noqa: E402

CONSOLE = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


# =====================================================================
# 1. Nhận dạng: bắt đúng dấu vết của lỗi
# =====================================================================
HONG = ("* * *\n\nstatus: active  \npriority: high  \n\n* * *\n\n"
        "# Kế Hoạch\n\n## 1\\\\. Tóm tắt\n\n-   Mục A\n")
check("thấy cả hai vấn đề trong file hỏng thật",
      M.tim_van_de(HONG) == [M.FRONTMATTER, M.DAU_THOAT])

moi, da_sua = M.sua(HONG)
check("dựng lại đúng khối frontmatter",
      moi.startswith("---\nstatus: active\npriority: high\n---\n\n# Kế Hoạch"))
check("bỏ dấu cách thừa cuối dòng frontmatter (vết <br> của turndown)",
      "active  \n" not in moi and "high  \n" not in moi)
check("gỡ dấu gạch chéo dồn: '1\\\\.' về '1.'", "## 1. Tóm tắt" in moi)
check("báo đúng những gì đã sửa", da_sua == [M.FRONTMATTER, M.DAU_THOAT])
check("CANARY: chữa xong thì sạch, chạy lại không còn gì để sửa", M.tim_van_de(moi) == [])
check("chữa hai lần cho ra y hệt (không tự phá tiếp)", M.sua(moi)[0] == moi)

# Danh sách trong YAML bị turndown thoát thành "\- x"
DS = "* * *\n\ntype: wiki  \ntags:  \n\\- một  \n\\- hai  \n\n* * *\n\n# Note\n"
check("khôi phục cả mục danh sách trong frontmatter",
      M.sua(DS)[0].startswith("---\ntype: wiki\ntags:\n- một\n- hai\n---\n"))

check("giữ nguyên phần thân sau frontmatter", "# Note\n" in M.sua(DS)[0])

# =====================================================================
# 2. KHÔNG ĐƯỢC CHỮA NHẦM - phần quan trọng nhất
# =====================================================================
check("file frontmatter còn LÀNH: không đụng vào",
      M.tim_van_de("---\nstatus: ok\n---\n\n# Note\n") == [])
check("đường kẻ ngang GIỮA bài: không phải frontmatter",
      M.tim_van_de("# Bài\n\n* * *\n\nĐoạn sau.\n") == [])
check("`* * *` ở đầu nhưng bên trong KHÔNG giống YAML: để yên",
      M.tim_van_de("* * *\n\nĐây là một câu văn bình thường.\n\n* * *\n\n# Bài\n") == [])
check("`* * *` mở mà không có dòng đóng: để yên",
      M.tim_van_de("* * *\n\nstatus: active\n\n# Bài\n") == [])
check("CANARY: MỘT dấu gạch chéo là hợp lệ, KHÔNG được gỡ",
      M.tim_van_de("## 1\\. Tóm tắt\n") == [] and M.sua("Gõ \\* để in sao\n")[0] == "Gõ \\* để in sao\n")
check("gạch chéo trước chữ thường (đường dẫn Windows) không bị đụng",
      M.sua("C:\\\\Users\\\\note.md\n")[0] == "C:\\\\Users\\\\note.md\n")
check("file rỗng / chỉ có chữ: không nhận nhầm",
      M.tim_van_de("") == [] and M.tim_van_de("Xin chào.\n") == [])

# =====================================================================
# 3. Endpoint: soi thì KHÔNG ghi, chữa thì ghi đúng file
# =====================================================================
_TMP = Path(tempfile.mkdtemp(prefix="javis-suamd-brain-")).resolve()
BRAIN = _TMP / "brains" / "Bộ Não"
(BRAIN / "06 - Sources").mkdir(parents=True)
F_HONG = BRAIN / "06 - Sources" / "ke-hoach.md"
F_LANH = BRAIN / "note-lanh.md"
F_HR = BRAIN / "hr-giua-bai.md"
F_HONG.write_text(HONG, encoding="utf-8")
F_LANH.write_text("---\nstatus: ok\n---\n\n# Lành\n", encoding="utf-8")
F_HR.write_text("# Bài\n\n* * *\n\nĐoạn sau.\n", encoding="utf-8")

main._brain_root = lambda brain: str(BRAIN)
main.BRAINS_DIR = str(_TMP / "brains")
os.environ["JAVIS_HOST"] = "0.0.0.0"          # public → trần = gốc brain
os.environ.pop("JAVIS_FILES_ROOT", None)
os.environ.pop("JAVIS_REQUIRE_LOGIN", None)

soi = asyncio.run(main.files_md_hong(brain="brain"))
check("soi: chỉ liệt file thật sự hỏng",
      [i["name"] for i in soi["items"]] == ["ke-hoach.md"])
check("soi: nói bằng tiếng người, không phải mã lỗi",
      "khối thuộc tính" in soi["items"][0]["mo_ta"])
check("CANARY: soi KHÔNG ghi gì lên đĩa", F_HONG.read_text(encoding="utf-8") == HONG)

lanh_truoc, hr_truoc = F_LANH.read_text(encoding="utf-8"), F_HR.read_text(encoding="utf-8")
kq = asyncio.run(main.files_md_hong_sua(brain="brain", paths=""))
check("chữa: báo đúng số file đã sửa",
      kq.get("ok") and len(kq["da_sua"]) == 1 and not kq["loi"])
check("chữa: file trên đĩa đã đúng", F_HONG.read_text(encoding="utf-8").startswith("---\nstatus: active"))
check("CANARY: file lành không bị đụng tới",
      F_LANH.read_text(encoding="utf-8") == lanh_truoc and F_HR.read_text(encoding="utf-8") == hr_truoc)

lai = asyncio.run(main.files_md_hong(brain="brain"))
check("chữa xong thì soi lại sạch trơn", lai["items"] == [])

# Chữa CÓ CHỌN LỌC: chỉ đúng đường dẫn được nêu
F_HONG.write_text(HONG, encoding="utf-8")
F2 = BRAIN / "06 - Sources" / "note-2.md"
F2.write_text(HONG, encoding="utf-8")
rel2 = main._files_rel(main._files_root("brain"), F2)
kq2 = asyncio.run(main.files_md_hong_sua(brain="brain", paths=json.dumps([rel2])))
check("chữa theo danh sách: đúng một file được chọn",
      len(kq2["da_sua"]) == 1 and kq2["da_sua"][0]["name"] == "note-2.md")
check("CANARY: file KHÔNG nằm trong danh sách vẫn nguyên trạng",
      F_HONG.read_text(encoding="utf-8") == HONG)

# =====================================================================
# 4. Giao diện: tự soi khi vào trang, im lặng nếu không có gì
# =====================================================================
check("trang Tệp tin tự soi khi vào (không bắt người dùng đi tìm nút)",
      "async function soiMdHong()" in CONSOLE and "soiMdHong();" in CONSOLE)
check("CANARY: không có file hỏng thì KHÔNG vẽ gì cả",
      "if (!items.length || !fixEl.isConnected) return;" in CONSOLE)
check("server cũ chưa có endpoint thì im lặng, không hiện lỗi",
      "if (!r.ok) return;" in CONSOLE)
check("có nút chữa hết và nút để sau", 'id="fmFixGo"' in CONSOLE and 'id="fmFixNo"' in CONSOLE)
check("chữa xong thì nạp lại danh sách file", "if (xong) load(cur);" in CONSOLE)
check("báo cả số file chữa hỏng chứ không nuốt đi",
      "d.loi || []" in CONSOLE and "không ghi được" in CONSOLE)

print()
if fails:
    print(f"FAIL - test_sua_md_hong: {len(fails)} lỗi: " + ", ".join(fails))
    raise SystemExit(1)
print("OK - test_sua_md_hong: tất cả pass")
