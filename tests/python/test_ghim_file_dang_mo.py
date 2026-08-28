"""Regression: mở file trong trình sửa thì file đó tự thành đầu vào của cuộc trò chuyện.

Kiểu Obsidian/Claudian: click một file .md là nó ghim vào khung chat, click file khác thì
thay chỗ. Ghim KHÁC đính kèm ở hai điểm dễ làm hỏng nhất khi sửa code sau này:
  1. Chỉ có MỘT ghim - render phải thay chứ không cộng dồn.
  2. Ghim KHÔNG bị clearAttachments() dọn sau khi gửi. Đính kèm là dữ liệu một lượt, ghim
     là ngữ cảnh nền của cả cuộc trò chuyện.

Chạy:
    .venv/Scripts/python.exe tests/python/test_ghim_file_dang_mo.py
"""
import re

from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path

APP = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
CONSOLE = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
STYLE = (ROOT / "dashboard" / "style.css").read_text(encoding="utf-8")
MAIN = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
CLAUDE_MD = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
DOC05 = (ROOT / "docs" / "05-quan-ly-tep-tin.md").read_text(encoding="utf-8")
DOC02 = (ROOT / "docs" / "02-tro-chuyen-va-giong-noi.md").read_text(encoding="utf-8")

fails = []


def check(name: str, condition: bool) -> None:
    print(("PASS: " if condition else "FAIL: ") + name)
    if not condition:
        fails.append(name)


# --- Server: /files/read phải trả đường dẫn THẬT -----------------------------
# Client không tự ghép được: `path` tính theo TRẦN DUYỆT còn engine cần đường dẫn hệ thống,
# và hai cái lệch nhau khi trần cao hơn gốc brain.
_read = MAIN.split("async def files_read(", 1)[1].split("\n@app.", 1)[0]
check("/files/read trả thêm khoá 'abs'", '"abs": str(f)' in _read)


# --- app.js: trạng thái ghim ------------------------------------------------
check("có state pinnedNote riêng, không nhét chung pendingAttachments",
      re.search(r"^let pinnedNote = null;", APP, re.M) is not None)
check("mở API JavisPin cho console.js gọi",
      "window.JavisPin = JavisPin;" in APP
      and re.search(r"const JavisPin = \{[\s\S]*?get\(\)[\s\S]*?set\(note\)[\s\S]*?clear\(\)", APP) is not None)

# Chỉ MỘT ghim: set() gán đè chứ không push vào mảng.
_set = APP.split("set(note) {", 1)[1].split("clear()", 1)[0]
check("set() gán đè (một ghim duy nhất), không push",
      "pinnedNote = {" in _set and ".push(" not in _set)

# Thanh chip phải bung ra khi CHỈ có ghim (chưa đính kèm gì) - nếu quên vế này thì
# ghim vô hình vì .attach-bar cao 0 khi không có .has-items.
check("thanh chip bung ra khi chỉ có ghim",
      'attachBar.classList.toggle("has-items", pendingAttachments.length > 0 || !!pinnedNote)' in APP)
check("chip ghim render với class riêng .pinned", '"attach-chip pinned"' in APP)
check("chip ghim có nút bỏ ghim riêng", 'data-unpin="1"' in APP and "if (b.dataset.unpin) JavisPin.clear();" in APP)

# --- Bấm chip = quay lại sửa file đó ---------------------------------------
# Chip là lối quay lại DUY NHẤT khi trình sửa đã đóng: không có nó thì phải đi tìm lại file
# trong cây vault, đúng cái việc mà ghim sinh ra để khỏi phải làm.
_chips = APP.split("function renderChips()", 1)[1].split("\n}", 1)[0]
check("chip ghim bấm được (role + tabIndex cho bàn phím)",
      'chip.setAttribute("role", "button")' in _chips and "chip.tabIndex = 0" in _chips)
check("bấm chip gọi mở lại file", "reopenPinnedNote()" in _chips)
check("bấm nút X KHÔNG mở lại file (chỉ bỏ ghim)",
      'e.target.closest(".chip-x")) return;' in _chips)
check("Enter/Space cũng mở lại được", 'e.key !== "Enter" && e.key !== " "' in _chips)
check("chip có dấu hiệu nhìn thấy được là bấm được (cây bút)", "chip-edit" in _chips)

_reopen = APP.split("function reopenPinnedNote()", 1)[1].split("\n}", 1)[0]
check("mở lại đi qua trình sửa đính trước",
      "window.JavisOpenNoteAt(rel, pinnedNote.name)" in _reopen)
check("màn hẹp / console chưa nạp thì rơi về khung sửa bung giữa màn",
      "window.JavisEditFile(rel)" in _reopen and "window.JavisOpenFiles(rel)" in _reopen)
check("mở lại dùng rel (path theo trần) chứ không phải abs của máy",
      "pinnedNote.rel" in _reopen and "pinnedNote.abs" not in _reopen)

# Gửi xong KHÔNG được mất ghim: clearAttachments chỉ đụng pendingAttachments.
_clear = APP.split("function clearAttachments()", 1)[1].split("\n}", 1)[0]
check("clearAttachments() KHÔNG đụng tới ghim", "pinnedNote" not in _clear)

# Khối ngữ cảnh phải nằm TRƯỚC câu của user và mang đường dẫn thật.
_send = APP.split("function sendMessage(", 1)[1].split("\nfunction ", 1)[0]
check("gửi kèm khối FILE ĐANG MỞ", "[FILE ĐANG MỞ trong trình sửa của Javis: ${pinnedNote.abs}" in _send)
check("khối ghim đứng TRƯỚC nội dung user gõ (câu của user nối vào cuối)",
      re.search(r"outMsg = `\[FILE ĐANG MỞ[\s\S]{0,900}?\\n\\n\$\{outMsg\}`;", _send) is not None)
check("bong bóng chat vẫn hiện câu GỐC của user, không lẫn khối ghim",
      "appendUserMessage(msg, atts)" in _send)

# Sống qua F5 - cùng lý do với khôi phục hội thoại ở 0.9.268.
check("ghim lưu xuống localStorage", 'const PIN_KEY = "javis.pinnedNote"' in APP)
check("khôi phục ghim lúc khởi động", "_pinRestore();" in APP)
check("ghim của brain khác bị bỏ khi khôi phục", "p.brain === currentBrainPath()" in APP)


# --- console.js: trình sửa nối vào ghim -------------------------------------
_open = CONSOLE.split("async function openNote(", 1)[1].split("\n  function ", 1)[0]
check("openNote ghim file vừa mở",
      "window.JavisPin.set({ name: d.name || it.name || rel, rel, abs: d.abs })" in _open)
check("ghim dùng abs từ server chứ không tự ghép đường dẫn",
      "d.abs" in _open and "_vtHome +" not in _open)

# Cửa "mở lại" của console.js: nhận path THEO TRẦN DUYỆT (đúng dạng ghim đang giữ). Đi vòng
# qua JavisOpenNote sẽ ghép tiền tố trần lần hai → mở hụt file khi trần cao hơn gốc brain.
check("console.js mở cửa JavisOpenNoteAt cho chip ghim gọi",
      "window.JavisOpenNoteAt = function (ceilRel, name)" in CONSOLE)
_at = CONSOLE.split("window.JavisOpenNoteAt = function (ceilRel, name) {", 1)[1].split("\n  };", 1)[0]
check("màn hẹp thì trả false để người gọi tự lo đường lui", "if (isNarrow()) return false;" in _at)
check("đúng file đang mở sẵn thì KHÔNG nạp lại (giữ chữ đang gõ dở)",
      "_neOpenRel === ceilRel" in _at and "openNote(ceilRel" in _at.split("_neOpenRel === ceilRel", 1)[1])
check("mở lại ở trang Trò chuyện thì trình sửa chiếm chỗ khung chat",
      '_borrowNoteEditor();' in _at)
check("openNote nhớ file đang mở để so", "_neOpenRel = rel" in CONSOLE)
check("đóng trình sửa thì quên file đang mở", '_neOpenRel = "";' in CONSOLE)

check("đổi brain thì bỏ ghim (file thuộc brain cũ)",
      re.search(r"_vtCache\.clear\(\);[\s\S]{0,400}?window\.JavisPin\.clear\(\)", CONSOLE) is not None)
_del = CONSOLE.split("async function _neDeleteCur(", 1)[1].split("\n  function ", 1)[0]
check("xoá file đang ghim thì bỏ ghim", "p.rel === rel" in _del and "JavisPin.clear()" in _del)


# --- Giao diện + tài liệu ---------------------------------------------------
check("chip ghim có kiểu riêng để phân biệt với đính kèm",
      ".attach-chip.pinned {" in STYLE)
check("chip ghim trông như bấm được (con trỏ tay + viền nhấn khi rê chuột)",
      ".attach-chip.pinned { cursor: pointer; }" in STYLE
      and ".attach-chip.pinned:hover {" in STYLE
      and ".attach-chip.pinned .chip-edit {" in STYLE)
check("system prompt dạy Javis xử lý khối FILE ĐANG MỞ",
      "## The open file (the FILE ĐANG MỞ block)" in CLAUDE_MD
      and "write straight into this file" in CLAUDE_MD)
check("doc Quản lý tệp tin mô tả tính năng ghim",
      "đang mở - bấm để sửa tiếp" in DOC05)
check("doc Quản lý tệp tin dạy cách bấm thẻ để sửa tiếp",
      "Bấm vào thẻ là quay lại sửa file đó" in DOC05)
check("doc Trò chuyện nói rõ ghim không mất sau khi gửi",
      "không mất sau khi gửi" in DOC02)
check("doc Trò chuyện nói thẻ ghim là lối quay lại trình sửa",
      "lối quay lại" in DOC02)


if fails:
    raise SystemExit(f"\nFAIL - test_ghim_file_dang_mo: {len(fails)} lỗi")
print("\nOK - test_ghim_file_dang_mo: tất cả pass")
