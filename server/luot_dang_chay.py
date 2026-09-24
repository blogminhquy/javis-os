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
TUOI_TOI_DA = 3 * 3600      # lượt kẹt quá lâu (không ai gạch) thì coi như đã chết


def _chuan(vault) -> str:
    v = str(vault or "").strip()
    if not v:
        return ""
    try:
        return os.path.normcase(os.path.realpath(v))
    except Exception:
        return v


def bat_dau(chat_id: str, vault) -> str:
    """Ghi một lượt đang chạy. Trả khoá để `ket_thuc` gạch đúng lượt này."""
    khoa = uuid.uuid4().hex
    if str(chat_id or "").strip():
        _DANG[khoa] = {"chat_id": str(chat_id).strip(), "vault": _chuan(vault), "at": time.time()}
    return khoa


def ket_thuc(khoa: str) -> None:
    _DANG.pop(str(khoa or ""), None)


def doan_chat_id(vault, now: float = 0.0) -> str:
    """chat_id của khung chat DUY NHẤT đang chạy trên brain này, không chắc thì ""."""
    now = now or time.time()
    for k in [k for k, v in _DANG.items() if now - v["at"] > TUOI_TOI_DA]:
        _DANG.pop(k, None)
    v = _chuan(vault)
    ung = {x["chat_id"] for x in _DANG.values() if not v or not x["vault"] or x["vault"] == v}
    return ung.pop() if len(ung) == 1 else ""
