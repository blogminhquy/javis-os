"""Sổ lượt chat ĐANG CHẠY theo brain: để tool giao việc biết người đang hỏi là ai (0.64.49).

Vì sao cần: việc nền giao từ chat (tool `javis_task`) báo kết quả về đúng khung chat nhờ trường
`chat_id`. Trường đó trước đây hoàn toàn trông vào model tự chép từ khối "KÊNH HỘI THOẠI HIỆN
TẠI". Model quên (chuyện thường với model nhỏ, hay khi lượt dài) là kết quả rơi về ID Telegram
đầu tiên, máy chưa đấu Telegram thì mất hút. Audit 2026-09-24 ghi đây là lỗi số một khiến người
dùng "giao việc rồi không thấy gì".

Tool chạy qua hub, có khi trong một tiến trình khác (Claude Code / Codex gọi /hub/mcp qua HTTP),
nên không có cách nào đọc biến ngữ cảnh của lượt. Nhưng máy chủ biết lượt nào đang chạy trên
brain nào. Nên: lượt chat ghi tên vào sổ lúc bắt đầu, gạch lúc xong; tool thiếu `chat_id` thì
hỏi sổ. Chỉ điền khi CHẮC: đúng một khung chat đang chạy trên brain đó. Hai khung cùng chạy thì
không đoán, giữ cảnh báo cũ.

Thuần bộ nhớ, không khoá: mọi lời gọi đều trên cùng event loop của máy chủ.
"""
from __future__ import annotations

import os
import time
import uuid
from typing import Dict

_DANG: Dict[str, dict] = {}
# Sổ SỐNG riêng cho vòng đời lượt (review mã bàn giao vòng 2, P2-1): chỉ `ket_thuc` (gọi trong finally của lượt) mới gỡ,
# KHÔNG dọn theo tuổi. _DANG ở trên dọn theo tuổi vì chỉ dùng để ĐOÁN người giao việc; tuổi bản ghi không chứng minh
# lượt đã dừng, nên không được dùng để quyết định quyền thực thi.
_SONG: Dict[str, dict] = {}
TUOI_TOI_DA = 3 * 3600      # lượt kẹt quá lâu (không ai gạch) thì coi như đã chết


def _chuan(vault) -> str:
    v = str(vault or "").strip()
    if not v:
        return ""
    try:
        return os.path.normcase(os.path.realpath(v))
    except Exception:
        return v


def bat_dau(chat_id: str, vault, msg_id: int = 0, user_text: str = "") -> str:
    """Ghi một lượt đang chạy. Trả khoá để `ket_thuc` gạch đúng lượt này.

    `msg_id` + `user_text` (Resonance M2): id tin nhắn người dùng trong kho phiên và đúng lời họ viết.
    Tool lập mục tiêu dùng id làm khoá chống trùng và dùng lời để kiểm câu căn cứ. Kênh chưa truyền
    id thì để 0, và tool đó từ chối tạo mục tiêu thay vì đoán."""
    khoa = uuid.uuid4().hex
    if str(chat_id or "").strip():
        _DANG[khoa] = {"chat_id": str(chat_id).strip(), "vault": _chuan(vault), "at": time.time(),
                       "msg_id": int(msg_id or 0), "user_text": str(user_text or "")}
        _SONG[khoa] = {"chat_id": str(chat_id).strip(), "msg_id": int(msg_id or 0)}
    return khoa


def ket_thuc(khoa: str) -> None:
    _DANG.pop(str(khoa or ""), None)
    _SONG.pop(str(khoa or ""), None)


def doan_chat_id(vault, now: float = 0.0) -> str:
    """chat_id của khung chat DUY NHẤT đang chạy trên brain này, không chắc thì ""."""
    now = now or time.time()
    for k in [k for k, v in _DANG.items() if now - v["at"] > TUOI_TOI_DA]:
        _DANG.pop(k, None)
    v = _chuan(vault)
    ung = {x["chat_id"] for x in _DANG.values() if not v or not x["vault"] or x["vault"] == v}
    return ung.pop() if len(ung) == 1 else ""


def doan_luot(vault, now: float = 0.0):
    """Lượt DUY NHẤT đang chạy trên brain này: {chat_id, msg_id, user_text}. Không chắc thì None.

    Chặt hơn `doan_chat_id`: phải đúng một lượt (không chỉ một khung chat), vì tool lập mục tiêu cần biết
    đúng TIN NHẮN nào chứ không chỉ khung chat nào."""
    now = now or time.time()
    for k in [k for k, x in _DANG.items() if now - x["at"] > TUOI_TOI_DA]:
        _DANG.pop(k, None)
    v = _chuan(vault)
    ung = [x for x in _DANG.values() if not v or not x["vault"] or x["vault"] == v]
    if len(ung) != 1:
        return None
    x = ung[0]
    return {"chat_id": x["chat_id"], "msg_id": int(x.get("msg_id") or 0), "user_text": x.get("user_text") or ""}


def dang_chay(chat_id: str, msg_id: int) -> bool:
    """Lượt của ĐÚNG tin nhắn này (khung chat + id tin) còn đang chạy trên tiến trình này không. Resonance dùng để biết
    lượt chat còn giữ quyền bàn giao (review mã bàn giao, P1-2 và vòng 2 P2-1). Đọc sổ SỐNG: chỉ gỡ khi lượt kết thúc
    thật (`ket_thuc` trong finally), không theo tuổi. Server khởi động lại thì sổ rỗng: không lượt nào của tiến trình
    cũ còn chạy."""
    cid, mid = str(chat_id or "").strip(), int(msg_id or 0)
    return bool(cid and mid) and any(x["chat_id"] == cid and x["msg_id"] == mid for x in _SONG.values())
