"""Regression: dòng HỆ THỐNG/MCP không được làm nở cockpit và đẩy cột chat ra ngoài."""
import re  # noqa: E402
from _paths import ROOT, SERVER  # noqa: E402,F401


STYLE = (ROOT / "dashboard" / "style.css").read_text(encoding="utf-8")
CONSOLE_CSS = (ROOT / "dashboard" / "console.css").read_text(encoding="utf-8")
APP = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
INDEX = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")

fails = []


def check(name: str, condition: bool) -> None:
    print(("PASS: " if condition else "FAIL: ") + name)
    if not condition:
        fails.append(name)


track_block = APP.split("function trackMCP(toolName)", 1)[1].split(
    "// ============================================", 1
)[0]

check("cột graph được phép co dưới min-content của canvas",
      "grid-template-columns: 260px minmax(0, 1fr) 320px;" in STYLE)
check("mọi hàng trực tiếp của HUD không ép rộng grid", ".hud > * { min-width: 0; }" in STYLE)
check("model bar tự chặn tràn ngang",
      ".model-bar {" in STYLE and "width: 100%; max-width: 100%; min-width: 0;" in STYLE
      and "padding: 8px 18px 6px;" in STYLE)
# Chặn tràn ở hàng model là CẤM: menu đổi model (.mb-pop) là con position:absolute nằm
# hoàn toàn phía trên hàng, mà hàng lại là khối chứa của nó - cắt tràn ở đây là menu
# biến mất sạch, bấm chip không ra gì (lỗi thật của 0.9.257, sửa ở 0.9.261).
# Việc chống nở ngang phải nằm ở .sysbar và .mb-chip, đúng hai check kế bên.
_model_bar_block = STYLE.split(".model-bar {", 1)[1].split("}", 1)[0] if ".model-bar {" in STYLE else ""
check("model bar KHÔNG cắt tràn (cắt là mất menu đổi model)",
      "overflow" not in _model_bar_block)
check("chip model tự chặn bề ngang thay cho việc cắt tràn ở hàng",
      ".mb-chip {" in STYLE
      and "flex: 0 1 auto; min-width: 0; max-width: 100%; white-space: nowrap; overflow: hidden;" in STYLE)
check("sysbar co theo phần rộng còn lại",
      "flex: 1 1 0; width: 0; min-width: 0; max-width: 100%;" in STYLE)
check("danh sách MCP tự cắt trong vùng của nó",
      ".sysbar .mcp-list {" in STYLE and "flex: 1 1 0; width: 0; min-width: 0;" in STYLE
      and "text-overflow: ellipsis;" in STYLE)
check("câu lệnh shell chỉ hiện nhãn Terminal", 'label: "Terminal", cat: "Local"' in APP)
check("status chỉ giữ tối đa bốn loại tool", "while (usedMCPs.size > 4)" in track_block)
check("nhãn tool không chèn HTML thô", "div.innerHTML" not in track_block)
check("sysbar trong drawer mobile lấy lại đủ chiều rộng",
      ".rail-sys .sysbar {" in CONSOLE_CSS
      and "display: flex; flex: none; width: 100%; min-width: 0; max-width: 100%;" in CONSOLE_CSS)
# Ghim SỐ CHÍNH XÁC thì mỗi lần sửa CSS ở nơi khác là test này đỏ oan, và người sửa sẽ học
# cách "chỉnh test cho xanh" - đúng thói quen làm test mất giá trị. Chỉ khoá SÀN: đã lên tới
# đây rồi thì không được tụt xuống (tụt = trình duyệt của người dùng giữ bản cũ trong cache).
_SAN = {"style.css": 53, "console.css": 39, "app.js": 75}
for _ten, _san in _SAN.items():
    _m = re.search(re.escape(_ten) + r"\?v=(\d+)", INDEX)
    check(f"cache bust {_ten} không tụt dưới v{_san}",
          _m is not None and int(_m.group(1)) >= _san)

if fails:
    raise SystemExit(f"\nFAIL - test_sysbar_layout: {len(fails)} lỗi")
print("\nOK - test_sysbar_layout: tất cả pass")
