"""Mở file trong trang Tệp tin: DÍNH vào trang, và link trỏ hụt không được dẫn vào ngõ cụt.

Chủ repo báo 2026-08-13, hai chuyện cùng một gốc:

  1. "Một số file kèm theo .md đang không đọc được." Link trong chat ghi tên CÓ DẤU
     ("Kế hoạch SaaS...md") trong khi file trên đĩa là bản KHÔNG DẤU ("Ke Hoach SaaS...md"),
     nên đường dẫn trỏ vào chỗ trống.
  2. "Click file .md trên khung chat thi thoảng nó lại mở tệp tin và tệp tin ra trống ghi
     không phải thư mục." Cùng gốc: /files/list nhận một đường dẫn không phải thư mục (trỏ
     vào FILE, hoặc trỏ vào chỗ không có gì) rồi trả 400 kèm đúng câu đó, trang Tệp tin in
     câu lỗi lên nền rỗng và người dùng mắc kẹt.
  3. Trang Tệp tin mở .md/.txt/.html bằng một POPUP textarea trần - nghèo hơn hẳn trình sửa
     của khung chat (không WYSIWYG, không thanh định dạng, không đổi tên/xoá/phóng to).

Chạy:
    python tests/python/test_mo_file_trong_trang_tep_tin.py
"""
import asyncio
import os
import tempfile
from pathlib import Path

from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-motep-"))

import main  # noqa: E402

CONSOLE = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
STYLE = (ROOT / "dashboard" / "style.css").read_text(encoding="utf-8")

fails = []


def check(name: str, condition: bool) -> None:
    print(("ok   " if condition else "FAIL ") + name)
    if not condition:
        fails.append(name)


# =====================================================================
# 1. Server: /files/list không được bỏ người dùng ở ngõ cụt
# =====================================================================
_TMP = Path(tempfile.mkdtemp(prefix="javis-motep-brain-")).resolve()
BRAIN = _TMP / "brains" / "Bo Nao"
(BRAIN / "06 - Sources").mkdir(parents=True)
(BRAIN / "06 - Sources" / "Ke Hoach SaaS Quan Ly Tai Chinh.md").write_text("# Kế hoạch", encoding="utf-8")
(BRAIN / "ghi-chu.md").write_text("hi", encoding="utf-8")

main._brain_root = lambda brain: str(BRAIN)
main.BRAINS_DIR = str(_TMP / "brains")
os.environ["JAVIS_HOST"] = "0.0.0.0"          # public → trần = gốc brain (khỏi lệ thuộc ổ đĩa máy chạy test)
os.environ.pop("JAVIS_FILES_ROOT", None)
os.environ.pop("JAVIS_REQUIRE_LOGIN", None)


def _list(path):
    return asyncio.run(main.files_list(brain="brain", path=path))


d_file = _list("06 - Sources/Ke Hoach SaaS Quan Ly Tai Chinh.md")
check("trỏ vào FILE: mở thư mục CHA thay vì trả lỗi 'Không phải thư mục'",
      isinstance(d_file, dict) and d_file.get("path") == "06 - Sources")
check("trỏ vào FILE: nói rõ file nào để client mở thẳng ra sửa",
      isinstance(d_file, dict) and d_file.get("focus") == "Ke Hoach SaaS Quan Ly Tai Chinh.md")

d_miss = _list("06 - Sources/Kế hoạch SaaS Quản Lý Tài Chính.md")   # tên CÓ DẤU - không có trên đĩa
check("trỏ HỤT: vẫn mở thư mục tổ tiên gần nhất còn tồn tại",
      isinstance(d_miss, dict) and d_miss.get("path") == "06 - Sources"
      and any(i["name"].endswith(".md") for i in d_miss.get("items", [])))
check("trỏ HỤT: báo lại đường dẫn đã hỏi (client tự đi tìm theo tên)",
      isinstance(d_miss, dict) and "Kế hoạch SaaS" in (d_miss.get("missing") or ""))

d_sau = _list("khong-he-co/tang-nua/x.md")
check("trỏ hụt SÂU: leo lên tới thư mục có thật, không rơi vào lỗi",
      isinstance(d_sau, dict) and d_sau.get("path") == "" and d_sau.get("missing"))

d_dir = _list("06 - Sources")
check("thư mục thật: focus/missing rỗng (không báo động giả)",
      isinstance(d_dir, dict) and not d_dir.get("focus") and not d_dir.get("missing"))

d_home = _list(None)
check("điểm vào mặc định vẫn là brain", isinstance(d_home, dict) and d_home.get("path") == "")

# Tên khác dấu vẫn tìm ra: đây là đường cứu của cả hai chỗ (trang Tệp tin + trình sửa).
hits = asyncio.run(main.files_search(brain="brain", q="Kế hoạch SaaS Quản Lý Tài Chính.md",
                                     limit=8, mode="name"))
check("tìm theo tên bỏ dấu vẫn ra đúng file trên đĩa",
      len(hits["items"]) == 1 and hits["items"][0]["name"].startswith("Ke Hoach SaaS"))

# =====================================================================
# 2. Trang Tệp tin: trình sửa DÍNH vào trang, không còn popup
# =====================================================================
check("CANARY: popup .fm-modal của trang Tệp tin đã bỏ hẳn (cả markup, CSS lẫn handler)",
      'class="fm-modal"' not in CONSOLE and ".fm-modal{" not in CONSOLE
      and "fmModalCard" not in CONSOLE and "closeModal" not in CONSOLE)
check("có khung riêng cho trình sửa trong trang Tệp tin", 'id="fmEdit"' in CONSOLE)
check("mở file = MƯỢN đúng #noteEditor của khung chat, không dựng trình sửa thứ hai",
      "function moTrongTrang(" in CONSOLE
      and "_borrowNoteEditor(slot)" in CONSOLE
      and CONSOLE.index("_borrowNoteEditor(slot)") < CONSOLE.index("openNote(rel, { name: ten"))
check("bấm tên file / nút Sửa / nút Xem đều đi vào trình sửa dính",
      CONSOLE.count("moTrongTrang(rel, it)") >= 2 and "moTrongTrang(it.path, target)" in CONSOLE)
check("_borrowNoteEditor nhận khung để mượn (chat và Tệp tin dùng chung một hàm)",
      "function _borrowNoteEditor(into)" in CONSOLE
      and 'into = into || document.getElementById("chatPageEdit")' in CONSOLE)
check("trả trình sửa về theo CHA hiện tại, không tra cứng khung của trang Trò chuyện",
      "const into = s.node.parentNode;" in CONSOLE)
check("rời trang Tệp tin thì TRẢ trình sửa về khoang não (kẻo mất node)",
      "function _fmRoiTrang()" in CONSOLE and "_pageLeave = _fmRoiTrang" in CONSOLE)
check("vào lại trang Tệp tin cũng trả node trước khi ghi đè DOM",
      'if (document.getElementById("fmEdit")) _fmRoiTrang();' in CONSOLE)
check("đóng trình sửa thì danh sách file nạp lại (đổi tên/xoá ngay trong đó)",
      "_fmSauKhiDong" in CONSOLE and "function closeNote()" in CONSOLE
      and "_fmSauKhiDong" in CONSOLE.split("function closeNote()", 1)[1].split("\n  }", 1)[0])
check("CSS: trình sửa chiếm chỗ danh sách, không nổi lên như popup",
      ".fm-page.edit-on>.fm-edit{display:flex" in CONSOLE
      and ".fm-page.edit-on>.fm-browse{display:none}" in CONSOLE
      and ".fm-edit>.note-editor:not(.ne-full)" in CONSOLE)
check("trang Tệp tin dùng CHUNG danh sách đuôi sửa được với trình sửa",
      "const TEXT_EDIT_EXTS = VT_TEXT_EXTS;" in CONSOLE)
check(".pdf vẫn xem tại chỗ (popup cũ có, bỏ popup không được mất)",
      "VT_FRAME_EXTS" in CONSOLE and 'class="ne-frame"' in CONSOLE and ".ne-frame" in STYLE)

# =====================================================================
# 3. Link trỏ hụt: gợi ý file tên gần giống thay vì ngõ cụt
# =====================================================================
check("trình sửa: không thấy file thì tự đi tìm theo tên",
      "async function _neTimFileGan(" in CONSOLE
      and "_neTimFileGan(String(rel).split" in CONSOLE)
check("trang Tệp tin: link hụt cũng có gợi ý bấm là mở",
      "async function khongThayFile(" in CONSOLE and "if (d.missing) khongThayFile(d.missing, d.home)" in CONSOLE)
check("gợi ý dùng đúng đường tìm không phân biệt dấu (mode=name)",
      CONSOLE.count("&mode=name&limit=8") >= 2)
check("đường dẫn hoá ra là FILE thì MỞ THẲNG chứ không chỉ tô sáng",
      "if (d && d.focus)" in CONSOLE and "moTrongTrang(cur ? cur" in CONSOLE)
check("server cũ trả 400 thì client vẫn lùi về thư mục cha (không đứng nhìn lỗi)",
      "resp.status === 400 && lui.includes" in CONSOLE)

print()
if fails:
    print(f"FAIL - test_mo_file_trong_trang_tep_tin: {len(fails)} lỗi: " + ", ".join(fails))
    raise SystemExit(1)
print("OK - test_mo_file_trong_trang_tep_tin: tất cả pass")
