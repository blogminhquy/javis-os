"""Sổ đăng ký KÊNH của Hộp thư hội thoại: nơi DUY NHẤT trong lõi biết một kênh là gì.

Trước 0.61.0, "kiến thức về một kênh" (tên, logo, lấy token ở đâu, có nhóm không, gửi file
được không, lớp vận chuyển nào, ghi tin vào kho ra sao) nằm rải ở tám chỗ: `chatbot_store`,
`chatbot_runtime`, `conversations`, `GET /chatbots` trong main.py, route `/conversations/channels`,
`icons.js`, `chatbots.js`, `conversations.js`. Thêm Zalo OA hay Facebook là sửa cả tám, và Zalo
cá nhân thành một "trường hợp đặc biệt" trong mỗi chỗ. Chủ dự án yêu cầu (2026-09-21) mọi kênh
được đối xử NHƯ NHAU và thêm kênh về sau không phải đụng lõi.

Cách làm: mỗi kênh là MỘT module trong gói này, khai một `KenhSpec` và một bộ hàm theo đúng
khế ước dưới đây. Lõi (kho bot, bộ giám sát, route, giao diện) chỉ đọc sổ; giao diện KHÔNG
được đoán theo id kênh mà vẽ theo `logo`, `nhan`, `nang_luc` server trả về.

Khế ước một module kênh (hàm thiếu = năng lực đó không có, sổ tự điền False):

    SPEC: KenhSpec                                   bắt buộc
    async verify_token(token) -> dict                kind="bot": hỏi nền tảng token này là bot nào.
                                                     Trả {"ok", "username", "bot_name", ...} hoặc
                                                     {"ok": False, "error"}.
    Transport: class                                 kind="bot": lớp long-polling (khế ước TelegramBot)
    tai_khoan() -> list[dict]                        kind="account": tài khoản đang có (id, label,
                                                     theo_doi, lan_cuoi, loi, so_tin)
    bat(account_id, on) -> dict                      kind="account": bật/tắt ghi vào hộp thư
    async gui(tk: dict, chat_id, text, chat_type)    gửi MỘT tin chữ từ tài khoản `tk` tới cuộc
                                                     chat. Trả (ok, loi). Có hàm này = kênh có
                                                     năng lực "trả lời từ Javis".

Ba LOẠI kênh (`kind`), khác nhau ở cách có tài khoản chứ không ở cách hiện ra:
    bot      - tài khoản là một TOKEN bot (Telegram Bot API, Zalo Bot API). Lưu ở
               `channel_accounts`, long-poll bằng `Transport`.
    account  - tài khoản là một PHIÊN đăng nhập sẵn có ở nơi khác (Zalo cá nhân qua MCP). Module
               tự liệt kê qua `tai_khoan()`, có công tắc ghi.
    webhook  - nền tảng GỌI NGƯỢC vào Javis (Zalo OA, Facebook Messenger: chưa có, chừa chỗ).

Thêm một kênh = thêm một file ở đây + một dòng trong `_MODULES` + một logo trong icons.js.
Không sửa gì khác.
"""
from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

KIND = ("bot", "account", "webhook")

# Năng lực mà lõi và giao diện hỏi. Khoá thiếu trong spec thì là False.
NANG_LUC_MAC_DINH = {
    "nhom": False,            # bot đứng được trong nhóm
    "gui_chu": False,         # gửi được chữ ra ngoài
    "gui_file": False,        # gửi được ảnh/tài liệu ra ngoài
    "tra_loi_tu_javis": False,   # chủ trả lời khách ngay từ Hộp thư (cần hàm `gui`)
    "bot": False,             # gắn được một Bot chuyên trách (kind == "bot")
    "ghi_theo_cong_tac": False,  # ghi vào hộp thư khi chủ BẬT (kind == "account")
}


@dataclass
class KenhSpec:
    id: str                     # id kho hiểu: telegram | zalo | zalo_personal | ...
    nhan: str                   # tên hiện ra: "Telegram", "Zalo Bot", "Zalo cá nhân"
    kind: str                   # bot | account | webhook
    logo: str = ""              # khoá logo trong icons.js (Icons.kenh): "telegram", "zalo"
    mau: str = ""               # màu thương hiệu, cho giao diện tô chip
    lay_token: str = ""         # kind=bot: hướng dẫn lấy token, một câu
    nang_luc: Dict[str, bool] = field(default_factory=dict)
    # Một câu tóm tắt cho ô chọn kênh (ai nhắn được, kênh này KHÔNG làm được gì).
    tom_tat: str = ""
    # Tên tài khoản phía nền tảng có tiền tố "@" không (Telegram có, Zalo không).
    tien_to_ten: str = ""

    def nl(self, khoa: str) -> bool:
        return bool(self.nang_luc.get(khoa, NANG_LUC_MAC_DINH.get(khoa, False)))


# Thứ tự ở đây là thứ tự hiện trên giao diện. KHÔNG có kênh nào "chính": Zalo đứng đầu vì
# khách Việt Nam dùng nhiều nhất, không phải vì nó được ưu ái trong mã.
_MODULES = ("channels.zalo_bot", "channels.zalo_personal", "channels.telegram")

_DS: Optional[Dict[str, KenhSpec]] = None
_MOD: Dict[str, object] = {}


def _nap() -> Dict[str, KenhSpec]:
    global _DS
    if _DS is not None:
        return _DS
    ds: Dict[str, KenhSpec] = {}
    for ten in _MODULES:
        try:
            m = importlib.import_module(ten)
        except Exception as e:      # một kênh hỏng KHÔNG được kéo cả sổ chết
            print(f"[channels] không nạp được {ten}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        spec: KenhSpec = getattr(m, "SPEC", None)
        if not isinstance(spec, KenhSpec) or spec.kind not in KIND or not spec.id:
            print(f"[channels] {ten} không có SPEC hợp lệ, bỏ qua", file=sys.stderr)
            continue
        nl = dict(NANG_LUC_MAC_DINH)
        nl.update(spec.nang_luc or {})
        # Hai năng lực suy ra từ chính module, không tin lời khai: có hàm mới có năng lực.
        nl["tra_loi_tu_javis"] = bool(nl.get("gui_chu")) and callable(getattr(m, "gui", None))
        nl["bot"] = spec.kind == "bot" and getattr(m, "Transport", None) is not None
        nl["ghi_theo_cong_tac"] = spec.kind == "account" and callable(getattr(m, "bat", None))
        spec.nang_luc = nl
        if not spec.logo:
            spec.logo = spec.id
        ds[spec.id] = spec
        _MOD[spec.id] = m
    _DS = ds
    return ds


def danh_sach() -> List[KenhSpec]:
    return list(_nap().values())


def ids() -> tuple:
    return tuple(_nap().keys())


def spec(kenh: str) -> Optional[KenhSpec]:
    return _nap().get(str(kenh or "").strip().lower())


def module(kenh: str):
    _nap()
    return _MOD.get(str(kenh or "").strip().lower())


def bot_ids() -> tuple:
    """Kênh gắn được Bot chuyên trách (có Transport). Thứ tự = thứ tự sổ."""
    return tuple(k for k, s in _nap().items() if s.nl("bot"))


def nhan(kenh: str) -> str:
    s = spec(kenh)
    return s.nhan if s else str(kenh or "")


def logo(kenh: str) -> str:
    s = spec(kenh)
    return s.logo if s else ""


def nhan_theo_id() -> Dict[str, str]:
    return {k: s.nhan for k, s in _nap().items()}


def cho_giao_dien() -> List[dict]:
    """Bản cho giao diện: đủ để vẽ ô chọn kênh, chip, form thêm tài khoản, KHÔNG đoán gì thêm."""
    out = []
    for s in danh_sach():
        out.append({
            "id": s.id, "nhan": s.nhan, "kind": s.kind, "logo": s.logo, "mau": s.mau,
            "lay_token": s.lay_token, "tom_tat": s.tom_tat, "tien_to_ten": s.tien_to_ten,
            "nang_luc": dict(s.nang_luc),
            # Hai cờ cũ giao diện Chatbot đang đọc; giữ để không đổi hai chỗ cùng lúc.
            "co_nhom": s.nl("nhom"), "gui_tai_lieu": s.nl("gui_file"),
        })
    return out


async def gui(kenh: str, tk: dict, chat_id: str, text: str, chat_type: str = "private"):
    """Gửi một tin chữ qua kênh. Trả (ok, lỗi). Kênh không có năng lực -> (False, lý do)."""
    s = spec(kenh)
    m = module(kenh)
    if not s or not m:
        return False, f"kênh '{kenh}' không có trong sổ đăng ký"
    if not s.nl("tra_loi_tu_javis"):
        return False, f"{s.nhan} chưa gửi được tin từ Javis"
    try:
        return await m.gui(tk, str(chat_id), str(text or ""), chat_type or "private")
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def reset_cho_test() -> None:
    """Chỉ cho test: nạp lại sổ (sau khi monkeypatch một module kênh)."""
    global _DS
    _DS = None
    _MOD.clear()
