"""Regression tĩnh cho cockpit mobile.

Chạy:
    .venv/Scripts/python.exe server/test_mobile_layout.py
"""
import re  # noqa: E402
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
from pathlib import Path


INDEX = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "dashboard" / "console.css").read_text(encoding="utf-8")
STYLE = (ROOT / "dashboard" / "style.css").read_text(encoding="utf-8")
BRAIN_VIEW = (ROOT / "dashboard" / "brain-view.js").read_text(encoding="utf-8")

fails = []


def check(name: str, condition: bool) -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        print(f"FAIL: {name}")
        fails.append(name)


check("viewport hỗ trợ safe area", "viewport-fit=cover" in INDEX)
# Khoá SÀN chứ không ghim số: ghim số thì mỗi lần sửa CSS ở nơi khác là test đỏ oan, và
# người sửa sẽ học cách "chỉnh test cho xanh". Tụt xuống mới là lỗi thật (trình duyệt của
# người dùng giữ bản CSS cũ trong cache).
_m_css = re.search(r"console\.css\?v=(\d+)", INDEX)
check("cache bust console.css không tụt dưới v39",
      _m_css is not None and int(_m_css.group(1)) >= 39)
check("mobile dùng dynamic viewport", CSS.count("100dvh") >= 3)
check("graph mobile có fallback nhỏ hơn bản cũ", "height: 30vh;" in CSS)
check("graph mobile có trần/sàn theo chiều cao", "height: clamp(190px, 27dvh, 260px);" in CSS)
check("transcript mobile được phép co trong viewport", ".hud-right .transcript {" in CSS and "min-height: 0;" in CSS)
check("thanh năng lực mobile chia đều ba mục", ".bstat { flex: 1 1 0;" in CSS)
check("ô nhập chừa safe area dưới", "env(safe-area-inset-bottom, 0px)" in CSS)
check("desktop không bị đổi kích thước graph gốc", ".hud-center {\n  position: relative; overflow: hidden;" in STYLE)
check("renderer 3D đã được gỡ", not (ROOT / "dashboard" / "graph3d.js").exists())
check("dashboard không còn nạp hoặc dựng graph 3D",
      "graph3d" not in INDEX.lower() and "forcegraph3d" not in APP.lower() and "three.min.js" not in APP.lower())
check("có nút mắt điều khiển overlay brain", 'id="brainOverlayToggle"' in INDEX and 'brain-view.js?v=1' in INDEX)
check("nút mắt ẩn đúng nhãn và thanh năng lực", ".hud-center.brain-overlays-hidden .concept-labels" in STYLE and ".hud-center.brain-overlays-hidden .brain-stats" in STYLE)
check("trạng thái nút mắt được nhớ", "localStorage.setItem(STORAGE_KEY" in BRAIN_VIEW)

if fails:
    raise SystemExit(f"\nFAIL - test_mobile_layout: {len(fails)} lỗi")
print("\nOK - test_mobile_layout: tất cả pass")
