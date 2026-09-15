"""Plugin bundled: tool `javis_ui` - bảo dashboard mở trang / file / việc, cuộn khung chat.

Vì sao là TOOL chứ không phải khối `<!-- JAVIS_UI -->` trong câu trả lời: tool có kết quả trả về
ngay trong lượt (dashboard đáp "đã mở" hay "không có tab nào"), đi qua hub nên mọi bộ não gọi
được như nhau, và tôn trọng ba mức quyền bằng code. Khối trong câu trả lời thì server đang lột
mọi `JAVIS_*` trước khi lưu, và không có đường báo kết quả về. Xem
docs/dev/2026-09-voice-v1-spec.md mục 6.

Đường đi: handler -> ui_bridge.request() -> frame `ui_action` qua /ws -> dashboard chạy và trả
`ui_result` -> ui_bridge.resolve() -> handler có kết quả. Không import main: main gắn runtime vào
ui_bridge lúc khởi động.

Kiểm target Ở CẢ HAI ĐẦU. Server chặn trước để model nhận lỗi rõ ràng thay vì đợi 4 giây; dashboard
kiểm lại lần nữa vì nó là bên thực hiện và không tin server tuyệt đối.
"""
from __future__ import annotations

import ui_bridge
import ui_targets   # bảng tên trang/nhóm + bí danh tiếng Việt, dùng CHUNG với đường tắt giọng nói

# Tên trang, tên nhóm và bí danh nằm ở server/ui_targets.py. Trước 0.57.6 bảng đó nằm ngay
# trong file này, nên đường tắt giọng nói (main.py, dòng JAVIS_UI:) không tra được và cứ nói
# tiếng Việt là dashboard trả "trang không tồn tại".
PAGES = ui_targets.PAGES
ALIASES = ui_targets.ALIASES
GROUPS = ui_targets.GROUPS
GROUP_ALIASES = ui_targets.GROUP_ALIASES
resolve_page = ui_targets.resolve_page
resolve_group = ui_targets.resolve_group
normalize_target = ui_targets.normalize_target
resolve_scroll = ui_targets.resolve_scroll
SCROLL_TARGETS = ui_targets.SCROLL_TARGETS
_khong_dau = ui_targets.khong_dau

ACTIONS = ("open_page", "open_file", "open_task", "scroll", "open_group", "sidebar")


def check_target(action: str, target: str) -> str:
    """Chuỗi lý do chặn, hoặc rỗng nếu ổn. Trả target đã chuẩn hoá qua `normalize_target`."""
    if action not in ACTIONS:
        return f"action '{action}' không có. Chọn một trong: {', '.join(ACTIONS)}."
    t = str(target or "").strip()
    if action == "open_page":
        if not resolve_page(t):
            return f"không có trang '{target}'. Trang hợp lệ: {', '.join(PAGES)}."
    elif action == "open_file":
        if not t:
            return "thiếu target: đường dẫn file tương đối trong brain."
        bad = t.replace("\\", "/")
        if bad.startswith("/") or ":" in bad.split("/")[0] or ".." in bad.split("/") or bad.startswith("~"):
            return "target phải là đường dẫn TƯƠNG ĐỐI trong brain (không '..', không tuyệt đối, không scheme)."
    elif action == "open_task":
        if not t:
            return "thiếu target: mã việc Kanban (lấy từ javis_task op=list)."
    elif action == "scroll":
        if not resolve_scroll(t):
            return ("scroll nhận target: " + " | ".join(SCROLL_TARGETS) + " (hoặc tiếng Việt như "
                    "'xuống dưới', 'cuộn trang này lên', 'cuộn khung chat xuống').")
    elif action == "open_group":
        if not resolve_group(t):
            return f"không có nhóm '{target}'. Nhóm hợp lệ: {', '.join(GROUPS)}."
    elif action == "sidebar":
        if _khong_dau(t) not in ("open", "close", "mo", "dong", "bung", "thu", "thu gon"):
            return "sidebar chỉ nhận target 'open' (bung thanh bên) hoặc 'close' (thu gọn)."
    return ""


async def _ui(args, ctx) -> str:
    action = str((args or {}).get("action") or "").strip().lower()
    target = str((args or {}).get("target") or "")
    why = check_target(action, target)
    if why:
        return "ERROR: " + why
    target = normalize_target(action, target)
    sid = str((args or {}).get("session_id") or "").strip()
    if sid.startswith("web:"):
        sid = sid[4:]
    res = await ui_bridge.request(action, target, session_id=sid)
    if not res.get("ok"):
        return "ERROR: " + (res.get("detail") or "dashboard không thực hiện được")
    detail = res.get("detail") or ""
    if action == "scroll":
        # `detail` là thứ dashboard THẬT SỰ cuộn ("nội dung trang" hay "khung chat"). Đừng đoán:
        # target 'bottom' là để dashboard tự chọn theo trang đang mở.
        return f"Đã cuộn {detail or 'khung chat'} {'lên đầu' if target.endswith('top') else 'xuống cuối'}."
    if action == "sidebar":
        return "Đã bung thanh bên." if target == "open" else "Đã thu gọn thanh bên."
    if action == "open_group":
        return f"Đã bung nhóm {target} trên thanh bên."
    ten = {"open_page": "trang", "open_file": "file", "open_task": "việc"}[action]
    return f"Đã mở {ten} {target} trên dashboard." + (f" {detail}" if detail else "")


def register(ctx):
    ctx.register_tool(
        name="javis_ui",
        description=(
            "Điều khiển DASHBOARD Javis đang mở trong trình duyệt của người dùng: mở trang, mở file, "
            "mở việc, cuộn. Dùng khi người dùng bảo (bằng lời hoặc gõ) 'mở trang Việc', 'mở file X', "
            "'cho xem việc vừa giao', 'cuộn xuống'. action=open_page (target: id trang - "
            + ", ".join(PAGES) + " - hoặc ĐÚNG tên tiếng Việt đang hiện trên thanh bên: 'việc', 'tệp tin', 'cài đặt', 'trợ lý' và 'quy trình' = workspace (trang Cộng sự), 'kỹ năng' = skills, 'công cụ' = plugins); "
            "open_file (target: đường dẫn tương đối trong brain); open_task (target: mã việc Kanban); "
            "scroll (cuộn THỨ NGƯỜI DÙNG ĐANG XEM - target: top | bottom để dashboard tự chọn "
            "theo trang đang mở, page_top | page_bottom khi họ nói rõ 'cuộn trang này', "
            "chat_top | chat_bottom khi họ nói rõ 'cuộn khung chat'); open_group (BUNG một nhóm đang gập trên thanh bên mà "
            "KHÔNG đổi trang, dùng khi người dùng nói 'mở mục Năng lực', 'bung nhóm Kết nối', 'cho xem "
            "phần ẩn trong menu' - target: " + ", ".join(GROUPS) + " hoặc tên tiếng Việt như 'năng lực'); "
            "sidebar (target: open để bung cả thanh bên, close để thu gọn còn icon). session_id: mã phiên "
            "web trong khối KÊNH HỘI THOẠI HIỆN TẠI "
            "(để đúng tab thực hiện; bỏ trống thì mọi tab đang mở làm). Tool trả về 'Đã mở ...' khi "
            "dashboard xác nhận, hoặc ERROR khi không có tab nào mở / trang không tồn tại."
        ),
        handler=_ui, min_mode="safe",
        schema={"type": "object", "properties": {
            "action": {"type": "string", "enum": list(ACTIONS)},
            "target": {"type": "string"},
            "session_id": {"type": "string"},
        }, "required": ["action", "target"]},
    )
