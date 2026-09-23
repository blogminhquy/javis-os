"""Hàng ô chọn model: không được làm nở cockpit, và dải "VỪA GỌI" đã bỏ hẳn.

Phần chống-nở là hồi quy cũ (dải cạnh ô model từng đẩy cột chat ra ngoài màn hình). Phần nội
dung: 27/08 chủ repo bỏ hai đèn "HỆ THỐNG" thay bằng ba tool vừa gọi; 23/09 bỏ nốt dải đó vì
từng bước tool đã hiện ngay trong khung chat, dải xanh lá chỉ lặp lại.
"""
import json  # noqa: E402
import re  # noqa: E402
from _paths import ROOT, SERVER  # noqa: E402,F401


STYLE = (ROOT / "dashboard" / "style.css").read_text(encoding="utf-8")
CONSOLE_CSS = (ROOT / "dashboard" / "console.css").read_text(encoding="utf-8")
APP = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
INDEX = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
# Từ 0.55.14 câu tiếng Việt trong giao diện dời vào từ điển i18n, .js chỉ còn gọi
# window.t("khoa"). Muốn giữ nguyên bảo đảm thì phải soi CẢ HAI vế: file .js gọi
# đúng khoá, và khoá đó trong vi.json mang đúng câu cần có.
_VI = json.loads((ROOT / "dashboard" / "i18n" / "vi.json").read_text(encoding="utf-8"))

fails = []


def check(name: str, condition: bool) -> None:
    print(("PASS: " if condition else "FAIL: ") + name)
    if not condition:
        fails.append(name)


check("cột graph được phép co dưới min-content của canvas",
      "grid-template-columns: 260px minmax(0, 1fr) 320px;" in STYLE)
check("mọi hàng trực tiếp của HUD không ép rộng grid", ".hud > * { min-width: 0; }" in STYLE)
check("model bar tự chặn tràn ngang",
      ".model-bar {" in STYLE and "width: 100%; max-width: 100%; min-width: 0;" in STYLE
      and "padding: 8px 18px 6px;" in STYLE)
# Chặn tràn ở hàng model là CẤM: menu đổi model (.mb-pop) là con position:absolute nằm
# hoàn toàn phía trên hàng, mà hàng lại là khối chứa của nó - cắt tràn ở đây là menu
# biến mất sạch, bấm chip không ra gì (lỗi thật của 0.9.257, sửa ở 0.9.261).
# Việc chống nở ngang phải nằm ở .mb-chip, đúng check kế bên.
_model_bar_block = STYLE.split(".model-bar {", 1)[1].split("}", 1)[0] if ".model-bar {" in STYLE else ""
check("model bar KHÔNG cắt tràn (cắt là mất menu đổi model)",
      "overflow" not in _model_bar_block)
check("chip model tự chặn bề ngang thay cho việc cắt tràn ở hàng",
      ".mb-chip {" in STYLE
      and "flex: 0 1 auto; min-width: 0; max-width: 100%; white-space: nowrap; overflow: hidden;" in STYLE)
check("nhãn Terminal cho câu lệnh shell vẫn còn (orb dùng)", 'label: "Terminal", cat: "Local"' in APP)
# 0.64.15 (chủ repo chốt 23/09): bỏ hẳn dải VỪA GỌI. Bước tool đã hiện trong khung chat
# (khối bước + chip đang chạy), dải xanh lá cạnh ô model chỉ lặp lại thứ đã thấy.
check("dải VỪA GỌI đã bỏ khỏi HTML",
      'id="sysBar"' not in INDEX and 'id="mcpList"' not in INDEX and "VỪA GỌI" not in INDEX)
check("JS không còn vẽ dải tool gần nhất",
      "trackMCP" not in APP and "veToolGanNhat" not in APP and "mcpList" not in APP)
check("CSS của dải đã dọn", ".sysbar" not in STYLE and ".sysbar" not in CONSOLE_CSS)
check("khoá i18n của dải đã dọn",
      "mb.recent" not in _VI and "mb.no_tools" not in _VI and "app.no_tool_yet" not in _VI)
check("hai đèn HỆ THỐNG vẫn không quay lại",
      'id="claudeStatus"' not in INDEX and 'id="ttsStatus"' not in INDEX
      and "updateSysStatus" not in APP)
# Ghim SỐ CHÍNH XÁC thì mỗi lần sửa CSS ở nơi khác là test này đỏ oan, và người sửa sẽ học
# cách "chỉnh test cho xanh" - đúng thói quen làm test mất giá trị. Chỉ khoá SÀN: đã lên tới
# đây rồi thì không được tụt xuống (tụt = trình duyệt của người dùng giữ bản cũ trong cache).
_SAN = {"style.css": 91, "console.css": 68, "app.js": 111}
for _ten, _san in _SAN.items():
    _m = re.search(re.escape(_ten) + r"\?v=(\d+)", INDEX)
    check(f"cache bust {_ten} không tụt dưới v{_san}",
          _m is not None and int(_m.group(1)) >= _san)

if fails:
    raise SystemExit(f"\nFAIL - test_sysbar_layout: {len(fails)} lỗi")
print("\nOK - test_sysbar_layout: tất cả pass")
