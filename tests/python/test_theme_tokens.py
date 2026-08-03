"""Regression: giao diện phải lật đúng giữa tông tối và tông sáng.

Hai lỗi thật ở 0.9.269, cùng một gốc là "gõ cứng thay vì dùng token":

1. CSS tiêm động cho tab Trò chuyện (`_injectChatCss` trong console.js) gõ cứng
   `rgba(24,24,34,.6)` làm nền khung nhập. Tông tối trông tạm được nên không ai để ý,
   tông sáng thì lòi ra một dải xám đen giữa nền giấy trắng.

2. Năm nút phụ ở trang Model viết `style="background:transparent"` thẳng trên thẻ.
   Style inline thắng mọi rule `:hover`, nên rê chuột vào chỉ nửa hiệu ứng chạy: nền giữ
   nguyên trong suốt còn chữ đã đổi sang `var(--on-accent)` - màu dành cho chữ đặt TRÊN
   nền cam đặc. Tông tối `--on-accent` gần đen trên nền tối, tông sáng nó trắng trên nền
   trắng: cả hai đều mất chữ.

Chạy:
    .venv/Scripts/python.exe tests/python/test_theme_tokens.py
"""
import re

from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path

CONSOLE_JS = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
CONSOLE_CSS = (ROOT / "dashboard" / "console.css").read_text(encoding="utf-8")
STYLE = (ROOT / "dashboard" / "style.css").read_text(encoding="utf-8")

fails = []


def check(name: str, condition: bool) -> None:
    print(("PASS: " if condition else "FAIL: ") + name)
    if not condition:
        fails.append(name)


# --- 1. Khối CSS tiêm động của tab Trò chuyện ---------------------------------
_m = re.search(r"function _injectChatCss\(\)[\s\S]*?const css = `([\s\S]*?)`;", CONSOLE_JS)
check("tìm được khối cp-css trong console.js", _m is not None)
CP_CSS = _m.group(1) if _m else ""
# Bỏ chú thích trước khi soi màu: chú thích có quyền nhắc lại giá trị cũ để giải thích
# vì sao nó sai, đó không phải màu đang chạy.
CP_RULES = re.sub(r"/\*[\s\S]*?\*/", "", CP_CSS)

# Màu gõ cứng (#abc, #aabbcc, rgb(), rgba()) không lật theo tông. Khối này chỉ được
# dùng var(--...) hoặc màu trong suốt hoàn toàn.
_hard = [c for c in re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)", CP_RULES)
         if not re.fullmatch(r"rgba?\(\s*0\s*,\s*0\s*,\s*0\s*,\s*0\s*\)", c)]
check(f"cp-css không gõ cứng màu (còn: {_hard})", not _hard)

check("khung nhập ở tab Trò chuyện dùng đúng nền của thanh nhập màn Javis",
      ".chatpage-slot .hud-voice{ background:var(--bg2);" in CP_CSS)
check("khung nhập ở tab Trò chuyện bo góc bằng bản gốc (18px)",
      re.search(r"\.chatpage-slot \.hud-voice\{[^}]*border-radius:18px", CP_CSS) is not None)

# HAI chỗ đặt chat phải cùng một bộ mặt, nếu không lật tông là thấy ngay chỗ vênh.
# (Trước 0.12.4 có ba: cockpit, tab Trò chuyện, và lớp nổi "phóng to". Lớp nổi đã bỏ - phóng
# to nay là chuyển hẳn sang tab Trò chuyện, xem tests/js/test_chat_zoom_sang_trang.js.)
check("thanh nhập gốc ở cockpit vẫn là --bg2 + bo 18px",
      re.search(r"\.hud-voice \{[^}]*border-radius: 18px;[^}]*background: var\(--bg2\)", STYLE) is not None)
check("không còn bộ mặt thứ ba đi lạc (lớp nổi đã bỏ)",
      ".chat-stage-body" not in STYLE)


# --- 2. Nút: style inline không được chặn hiệu ứng hover ----------------------
# `background` gõ inline thắng cả `:hover`, nên nút đứng im nền cũ mà chữ vẫn đổi màu
# theo hover -> chữ tàng hình. Nút phụ phải dùng class .ghost (có rule hover riêng).
# Chỉ soi thẻ <button>: div/iframe gõ nền inline thì không có hover nên vô hại.
_inline_bg = re.findall(r'<button[^>]*style="[^"]*background\s*:[^"]*"', CONSOLE_JS)
check(f"không nút nào gõ background inline (còn: {_inline_bg})", not _inline_bg)

check("class .ghost có rule hover riêng, đủ đè lên .gcard-btn:hover",
      ".gcard-btn.ghost:hover" in CONSOLE_CSS)
check("class .ghost để chữ ở màu đọc được, không mượn --on-accent",
      re.search(r"\.gcard-btn\.ghost \{[^}]*color: var\(--text2\)", CONSOLE_CSS) is not None
      and re.search(r"\.gcard-btn\.ghost:hover \{[^}]*color: var\(--text\)", CONSOLE_CSS) is not None)

# Năm nút từng dính lỗi - chốt lại là chúng đi đường .ghost.
for marker in ('data-oauth-browser="1"', 'data-oauth-disc="1"', 'id="cliLogout"', 'id="cliRecheck"'):
    _line = next((l for l in CONSOLE_JS.splitlines() if marker in l and "<button" in l), "")
    check(f"nút {marker} dùng class ghost", "gcard-btn ghost" in _line)
check('nút "Ngắt" của provider dùng key cũng dùng class ghost',
      'class="gcard-btn ghost" data-disc=' in CONSOLE_JS)

# Nút disabled: rê chuột vào không được tô cam (tô cam xong chữ đổi màu trong khi
# opacity hạ xuống là đọc không ra).
check("nút disabled giữ nguyên bộ mặt khi rê chuột", ".gcard-btn:disabled:hover" in CONSOLE_CSS)


if fails:
    raise SystemExit(f"\nFAIL - test_theme_tokens: {len(fails)} lỗi")
print("\nOK - test_theme_tokens: tất cả pass")
