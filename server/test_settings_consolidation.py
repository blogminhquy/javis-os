"""Hợp đồng UI cho việc gom Tổng quan/Cài đặt/Cập nhật.

Chạy:
    .venv/Scripts/python.exe server/test_settings_consolidation.py
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONSOLE = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
CONSOLE_CSS = (ROOT / "dashboard" / "console.css").read_text(encoding="utf-8")
STYLE = (ROOT / "dashboard" / "style.css").read_text(encoding="utf-8")
MOBILE = (ROOT / "dashboard" / "mobile-chat.js").read_text(encoding="utf-8")

fails = []


def check(name: str, condition: bool) -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        print(f"FAIL: {name}")
        fails.append(name)


rail_block = CONSOLE.split("const RAIL_ITEMS = [", 1)[1].split("];", 1)[0]
meta_block = CONSOLE.split("const VIEW_META = {", 1)[1].split("};", 1)[0]
router_block = CONSOLE.split("function renderPage(id)", 1)[1].split("// Trang Studio", 1)[0]

check("rail không còn tab Tổng quan", 'id: "overview"' not in rail_block and 'label: "Tổng quan"' not in rail_block)
check("metadata không còn trang Tổng quan", "overview:" not in meta_block)
check("router không còn render Tổng quan", 'id === "overview"' not in router_block)
check("lite mode vào thẳng Trò chuyện", 'navigateTo("chat")' in CONSOLE and 'navigateTo("overview")' not in CONSOLE[-2500:])
check("Cập nhật sở hữu khung kiểm tra phiên bản", 'id="updVerUpdate"' in CONSOLE and "wireUpdateManager(el)" in CONSOLE)
check("Nhật ký không còn chỉ người dùng sang Tổng quan", "Cập nhật ở mục <b>Tổng quan</b>" not in CONSOLE)
check("Cài đặt có khung đọc giới hạn chiều rộng", ".settings-page { width: min(100%, 960px)" in CONSOLE_CSS)
check("Cài đặt chia nhóm gập mở", CONSOLE.count('class="settings-group"') >= 4)
check("Trạng thái hệ thống đã vào Cài đặt", 'class="settings-status-grid"' in CONSOLE)
check("Cài đặt có lối tắt thay vì nhân đôi form", all(f'data-settings-go="{x}"' in CONSOLE for x in ("models", "channels", "account", "logs")))
check("quick settings dùng lưới hai cột và mobile một cột", ".settings-page .quick-set-body" in STYLE and "@media (max-width: 700px)" in STYLE)
check("mobile không kéo nút cài đặt cũ vào drawer", 'moveEl(document.getElementById("settingsBtn")' not in MOBILE)

if fails:
    raise SystemExit(f"\nFAIL - test_settings_consolidation: {len(fails)} lỗi")
print("\nOK - test_settings_consolidation: tất cả pass")
