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

# Trang hợp lệ = RAIL_ITEMS trong dashboard/console.js. Thêm trang mới thì thêm ở cả hai chỗ.
PAGES = (
    "home", "chat", "settings", "workflows", "agents", "skills", "chatbots", "files",
    "terminal", "selfimprove", "learn", "kanban", "models", "channels", "mcp", "plugins",
    "packs", "logs", "account", "usage",
)

# Bí danh người dùng hay nói, ánh xạ về id trang. Thường hoá không dấu trước khi tra.
ALIASES = {
    "viec": "kanban", "cong viec": "kanban", "bang viec": "kanban", "task": "kanban", "tasks": "kanban",
    "tep": "files", "tep tin": "files", "file": "files", "thu muc": "files", "brain": "files",
    "cai dat": "settings", "setting": "settings", "thiet lap": "settings",
    "mo hinh": "models", "model": "models", "bo nao": "models", "engine": "models",
    "ket noi": "mcp", "nguon": "mcp", "connect": "mcp",
    "goi": "packs", "kho": "packs", "store": "packs", "pack": "packs",
    "kenh": "channels", "telegram": "channels", "zalo": "channels",
    "muc dung": "usage", "token": "usage", "chi phi": "usage",
    "tro chuyen": "chat", "hoi thoai": "chat", "trang chu": "home", "javis": "home",
    "tu hoc": "selfimprove", "self improve": "selfimprove", "hoc": "learn",
    "code": "terminal", "ma": "terminal", "nhat ky": "logs", "log": "logs",
    "tai khoan": "account", "quy trinh": "workflows", "workflow": "workflows",
    "ky nang": "skills", "skill": "skills", "agent": "agents", "chatbot": "chatbots", "bot": "chatbots",
}

ACTIONS = ("open_page", "open_file", "open_task", "scroll")


def _khong_dau(s: str) -> str:
    import unicodedata
    s = str(s or "").strip().lower().replace("đ", "d")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(s.split())


def resolve_page(target: str) -> str:
    """Trả id trang hợp lệ hoặc chuỗi rỗng."""
    t = _khong_dau(target)
    for tien_to in ("trang ", "page ", "mo ", "open "):
        if t.startswith(tien_to):
            t = t[len(tien_to):].strip()
    if t in PAGES:
        return t
    if t in ALIASES:
        return ALIASES[t]
    # "trang viec kanban" -> thử từng từ
    for w in t.split():
        if w in PAGES:
            return w
        if w in ALIASES:
            return ALIASES[w]
    return ""


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
        if _khong_dau(t) not in ("top", "bottom", "len", "xuong", "dau", "cuoi", "len dau", "xuong cuoi"):
            return "scroll chỉ nhận target 'top' hoặc 'bottom'."
    return ""


def normalize_target(action: str, target: str) -> str:
    t = str(target or "").strip()
    if action == "open_page":
        return resolve_page(t)
    if action == "open_file":
        return t.replace("\\", "/").lstrip("./")
    if action == "scroll":
        return "top" if _khong_dau(t) in ("top", "len", "dau", "len dau") else "bottom"
    return t


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
    ten = {"open_page": "trang", "open_file": "file", "open_task": "việc", "scroll": "cuộn"}[action]
    detail = res.get("detail") or ""
    if action == "scroll":
        return f"Đã cuộn khung chat {'lên đầu' if target == 'top' else 'xuống cuối'}."
    return f"Đã mở {ten} {target} trên dashboard." + (f" {detail}" if detail else "")


def register(ctx):
    ctx.register_tool(
        name="javis_ui",
        description=(
            "Điều khiển DASHBOARD Javis đang mở trong trình duyệt của người dùng: mở trang, mở file, "
            "mở việc, cuộn. Dùng khi người dùng bảo (bằng lời hoặc gõ) 'mở trang Việc', 'mở file X', "
            "'cho xem việc vừa giao', 'cuộn xuống'. action=open_page (target: id trang - "
            + ", ".join(PAGES) + " - hoặc tên tiếng Việt như 'việc', 'tệp', 'cài đặt'); "
            "open_file (target: đường dẫn tương đối trong brain); open_task (target: mã việc Kanban); "
            "scroll (target: top | bottom). session_id: mã phiên web trong khối KÊNH HỘI THOẠI HIỆN TẠI "
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
