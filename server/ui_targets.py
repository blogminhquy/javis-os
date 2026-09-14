"""Tên trang và nhóm trên thanh bên, cùng cách đổi LỜI NÓI thành id máy hiểu.

Vì sao tách thành module riêng: chỗ cần tra tên trang có HAI đường, và trước đây chỉ một đường
có bảng bí danh.
  - Bộ não chính gọi tool `javis_ui` (system/plugins/javis-ui/plugin.py) - đường này vẫn tra.
  - Bộ não GIỌNG NÓI tự phát dòng `JAVIS_UI: open_page ...` rồi main.py gọi thẳng dashboard
    (đường tắt của Voice V2). Đường này trước đây đẩy nguyên chữ model viết ra, nên hễ model
    nói "công cụ" hay "kỹ năng" thay vì id tiếng Anh là dashboard trả "trang không tồn tại".

Thanh bên đã Việt hoá (Trợ lý, Kỹ năng, Quy trình, Công cụ), nên bí danh ở đây phải phủ ĐÚNG
những chữ người dùng nhìn thấy và đọc lên - thấy "Công cụ" mà nói "mở trang công cụ" thì phải
tới trang plugins.
"""
from __future__ import annotations

import unicodedata

# Trang hợp lệ = RAIL_ITEMS trong dashboard/console.js và PAGES trong dashboard/ui-actions.js.
# Thêm trang mới thì thêm ở cả ba chỗ.
PAGES = (
    "home", "chat", "settings", "workflows", "agents", "skills", "chatbots", "files",
    "terminal", "selfimprove", "learn", "kanban", "models", "channels", "mcp", "plugins",
    "packs", "logs", "account", "usage",
)

# Bí danh người dùng hay nói, ánh xạ về id trang. Thường hoá không dấu trước khi tra, nên viết
# khoá ở đây KHÔNG DẤU. Nhãn tiếng Việt đang hiện trên thanh bên phải có mặt trong bảng này.
ALIASES = {
    "viec": "kanban", "cong viec": "kanban", "bang viec": "kanban", "task": "kanban", "tasks": "kanban",
    "tep": "files", "tep tin": "files", "file": "files", "thu muc": "files", "brain": "files",
    "cai dat": "settings", "setting": "settings", "thiet lap": "settings",
    "mo hinh": "models", "model": "models", "bo nao": "models", "engine": "models",
    "ket noi": "mcp", "nguon": "mcp", "connect": "mcp", "nguon du lieu": "mcp",
    "goi": "packs", "kho": "packs", "store": "packs", "pack": "packs", "javis store": "packs",
    "kenh": "channels", "telegram": "channels", "zalo": "channels",
    "muc dung": "usage", "token": "usage", "chi phi": "usage",
    "tro chuyen": "chat", "hoi thoai": "chat", "trang chu": "home", "javis": "home",
    "tu hoc": "selfimprove", "self improve": "selfimprove", "hoc": "learn",
    "viec dinh ky": "selfimprove", "nhac hen": "selfimprove",
    "code": "terminal", "ma": "terminal", "nhat ky": "logs", "log": "logs",
    "cap nhat": "logs", "phien ban": "logs",
    "tai khoan": "account", "quy trinh": "workflows", "workflow": "workflows",
    "ky nang": "skills", "skill": "skills", "agent": "agents", "chatbot": "chatbots", "bot": "chatbots",
    # Nhãn thanh bên sau khi Việt hoá (0.57.6) - nói sao thấy vậy thì mở được.
    "tro ly": "agents", "tro ly rieng": "agents", "vai": "agents",
    "cong cu": "plugins", "plugin": "plugins", "tien ich": "plugins",
    "bot tra loi khach": "chatbots", "tra loi khach": "chatbots",
}

# Nhóm trên thanh bên = RAIL_GROUPS trong dashboard/console.js (khoá `id`) và GROUPS trong
# dashboard/ui-actions.js. Mở NHÓM khác mở TRANG: người dùng hay muốn bung phần đang gập để
# nhìn xem trong đó có gì, chứ chưa chọn trang nào.
GROUPS = ("tro_ly", "bo_nao", "code", "nang_luc", "viec", "ket_noi", "he_thong")

GROUP_ALIASES = {
    "tro ly": "tro_ly", "assistant": "tro_ly",
    "bo nao": "bo_nao", "second brain": "bo_nao", "brain": "bo_nao",
    "code": "code", "lap trinh": "code",
    "nang luc": "nang_luc", "kha nang": "nang_luc", "capability": "nang_luc",
    "viec": "viec", "cong viec": "viec", "task": "viec",
    "ket noi": "ket_noi", "connect": "ket_noi", "ket noi va model": "ket_noi",
    "he thong": "he_thong", "system": "he_thong", "cai dat chung": "he_thong",
}

# Tiền tố người nói hay kèm theo. Lột LẶP LẠI: "mở trang kỹ năng" có hai lớp, lột một lớp thì
# còn "trang ky nang" và bí danh hai chữ không bao giờ khớp (lỗi cũ trước 0.57.6).
_TIEN_TO_TRANG = ("trang ", "page ", "mo ", "open ", "muc ", "tab ", "cho xem ", "xem ", "vao ")
_TIEN_TO_NHOM = ("nhom ", "group ", "muc ", "phan ", "mo ", "open ", "bung ", "cho xem ", "xem ")


def khong_dau(s: str) -> str:
    s = str(s or "").strip().lower().replace("đ", "d")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in s)
    return " ".join(s.split())


def _lot_tien_to(t: str, tien_to) -> str:
    doi = True
    while doi:
        doi = False
        for tt in tien_to:
            if t.startswith(tt):
                t = t[len(tt):].strip()
                doi = True
    return t


def _tra(t: str, bang: dict, hop_le) -> str:
    """Tra cả cụm trước, rồi tới các cụm con dài nhất ("trang viec kanban" -> "kanban")."""
    if t in hop_le:
        return t
    if t in bang:
        return bang[t]
    tu = t.split()
    for n in range(len(tu) - 1, 0, -1):          # cụm dài trước, cụm ngắn sau
        for i in range(len(tu) - n + 1):
            cum = " ".join(tu[i:i + n])
            if cum in hop_le:
                return cum
            if cum in bang:
                return bang[cum]
    return ""


def resolve_page(target: str) -> str:
    """Trả id trang hợp lệ hoặc chuỗi rỗng."""
    return _tra(_lot_tien_to(khong_dau(target), _TIEN_TO_TRANG), ALIASES, PAGES)


def resolve_group(target: str) -> str:
    """Trả id nhóm thanh bên hợp lệ hoặc chuỗi rỗng."""
    t = _lot_tien_to(khong_dau(target), _TIEN_TO_NHOM)
    if t.replace(" ", "_") in GROUPS:
        return t.replace(" ", "_")
    return _tra(t, GROUP_ALIASES, GROUPS)


def normalize_target(action: str, target: str) -> str:
    """Đưa target về đúng thứ dashboard nhận (ui-actions.js chỉ chấp nhận id chuẩn)."""
    t = str(target or "").strip()
    if action == "open_page":
        return resolve_page(t)
    if action == "open_file":
        return t.replace("\\", "/").lstrip("./")
    if action == "scroll":
        return "top" if khong_dau(t) in ("top", "len", "dau", "len dau") else "bottom"
    if action == "open_group":
        return resolve_group(t)
    if action == "sidebar":
        return "close" if khong_dau(t) in ("close", "dong", "thu", "thu gon", "gap") else "open"
    return t
