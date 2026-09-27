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
check("cache bust console.css không tụt dưới v40",
      _m_css is not None and int(_m_css.group(1)) >= 40)
check("mobile dùng dynamic viewport", CSS.count("100dvh") >= 3)
check("graph mobile có fallback nhỏ hơn bản cũ", "height: 30vh;" in CSS)
# Khoá theo SÀN, đúng tinh thần ghi ở trên chứ không ghim nguyên chuỗi: ghim nguyên chuỗi thì
# một lần nới khoang não lên cho dễ nhìn cũng làm test đỏ oan. Cái phải chặn là chiều ngược
# lại - khoang não TỤT xuống dưới mức đã từng có, vì dưới đó thì đồ thị lại thành cục nhỏ xíu
# đúng như bản 0.25.2 đi sửa.
_m_ctr = re.search(r"height: clamp\((\d+)px,\s*(\d+)dvh,\s*(\d+)px\);", CSS)
check("graph mobile có trần/sàn theo chiều cao", _m_ctr is not None)
check("khoang não mobile không tụt dưới mức cũ (190px / 27dvh / 260px)",
      _m_ctr is not None and int(_m_ctr.group(1)) >= 190
      and int(_m_ctr.group(2)) >= 27 and int(_m_ctr.group(3)) >= 260)
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

# Bàn phím ảo (chủ repo báo 27/09): ô nhập phải nằm sát bàn phím, không chừa lề vạch Home
# khi vạch đó đã nằm dưới bàn phím. mobile-chat.js gắn lớp theo visualViewport, CSS dùng nó.
MOBILE_CHAT = (ROOT / "dashboard" / "mobile-chat.js").read_text(encoding="utf-8")
check("mobile-chat đo visualViewport và gắn lớp kb-open",
      "visualViewport" in MOBILE_CHAT and '"kb-open"' in MOBILE_CHAT and "--vv-h" in MOBILE_CHAT)
check("khung chat đặt theo vùng nhìn thấy khi bàn phím mở",
      "body.kb-open .hud {" in CSS and "var(--vv-h" in CSS and "body.kb-open .cview {" in CSS)
check("bàn phím mở thì ô nhập bỏ lề an toàn", "body.kb-open .hud-voice { margin-bottom: 6px; }" in CSS)
check("trang quản lý không cộng chồng hai lề đáy dưới ô nhập", ".cview .hud-voice { margin-bottom: 0; }" in CSS)
check("Android co trang theo bàn phím", "interactive-widget=resizes-content" in INDEX)
_cd = re.search(r"\.cd-menu \{[^}]*\}", CSS)
check("menu chip Coding có nền đặc, không dùng lớp phủ trong suốt",
      _cd is not None and "var(--surface-1)" not in _cd.group(0) and "var(--bg2)" in _cd.group(0))

# 0.64.64: .hud KHÔNG được fixed khi bàn phím mở - fixed dựng ngữ cảnh xếp chồng mới và ép
# bảng chọn model (con của header) xuống dưới .cview, kẹt sau khung chat.
_kb = re.search(r"body\.kb-open \.hud \{[^}]*\}", CSS)
check("khung chính khi bàn phím mở không dựng ngữ cảnh xếp chồng (không fixed)",
      _kb is not None and "position: fixed" not in _kb.group(0) and "position: relative" in _kb.group(0))
PICKER = (ROOT / "dashboard" / "model-picker.js").read_text(encoding="utf-8")
check("bảng chọn model không tự bật bàn phím trên màn cảm ứng", "pointer: coarse" in PICKER and "camUng()" in PICKER)
check("bảng chọn model mở ngay, không chờ mạng", "noWait" in PICKER and "peek(" in PICKER)

if fails:
    raise SystemExit(f"\nFAIL - test_mobile_layout: {len(fails)} lỗi")
print("\nOK - test_mobile_layout: tất cả pass")
