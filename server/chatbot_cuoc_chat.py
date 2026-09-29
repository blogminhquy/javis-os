"""Danh sách cuộc chat cho ô "chọn người và nhóm" của form bot (0.64.85).

Chủ muốn chọn bot trả lời ai mà không phải dán id. Nguồn tên là Hộp thư (`conversations`): mọi cuộc
chat bot đã thấy đều có ở đó kèm tên hiển thị. Ba loại dòng được gộp lại thành MỘT danh sách để form
chỉ vẽ một chỗ:

  - cuộc chat có trong Hộp thư của các tài khoản kênh của bot;
  - cuộc chat đang CHỜ DUYỆT (bot đã thấy nhưng chủ chưa cho phép) mà Hộp thư chưa có, ví dụ nhóm
    Telegram bot vừa được mời vào chưa ai nhắn;
  - id đã khai tay từ trước (`groups`/`people`) mà Hộp thư không biết: vẫn phải hiện ra để chủ bỏ
    tick được, không thì một id mồ côi nằm trong dữ liệu mà không giao diện nào chạm tới.

Chờ duyệt xếp lên đầu: đó là thứ chủ cần thấy trước.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import conversations


def _khop(danh_sach: Any, chat_id: str) -> bool:
    cid = str(chat_id or "").strip()
    return bool(cid) and cid in {str(x).strip() for x in (danh_sach or [])}


def danh_sach(accounts: List[dict], q: str = "", limit: int = 60,
              cho: Optional[List[dict]] = None, bot: Optional[dict] = None) -> List[Dict[str, Any]]:
    """Các cuộc chat đã biết của `accounts` (bản công khai của tài khoản kênh, có `id` và `channel`).

    `cho`: hàng đợi duyệt của bot (`chatbot_runtime.nhom_cho`). `bot`: bản ghi bot, để đánh dấu
    `da_chon` (nằm trong `groups`/`people`). Trả các dòng {id, loai, ten, kenh, luc, da_chon, cho}.
    """
    q = str(q or "").strip()
    n = max(1, min(int(limit or 60), 200))
    groups = (bot or {}).get("groups") or []
    people = (bot or {}).get("people") or []
    out: Dict[str, Dict[str, Any]] = {}

    def _them(cid, loai, ten, kenh, luc, cho_duyet):
        d = out.get(cid)
        if d is None:
            d = out[cid] = {"id": cid, "loai": loai, "ten": ten, "kenh": kenh, "luc": luc or 0,
                            "da_chon": _khop(groups if loai == "group" else people, cid),
                            "cho": False}
        d["cho"] = d["cho"] or bool(cho_duyet)
        if ten and not d.get("ten"):
            d["ten"] = ten

    for a in accounts or []:
        kenh = str((a or {}).get("channel") or "")
        aid = str((a or {}).get("id") or "")
        if not (kenh and aid):
            continue
        try:
            ds = conversations.cuoc_chat_cua_tai_khoan(kenh, aid, q, n)
        except Exception:
            ds = []
        for c in ds:
            cid = str(c.get("external_chat_id") or "")
            if not cid:
                continue
            loai = "group" if c.get("chat_type") == "group" else "private"
            ten = str(c.get("title") or c.get("customer_name") or cid)
            _them(cid, loai, ten, kenh, c.get("last_message_at") or c.get("updated_at"), False)

    hom = q.lower()
    for g in (cho or []):
        cid = str(g.get("chat_id") or "")
        ten = str(g.get("ten") or "")
        if not cid or (hom and hom not in ten.lower() and hom not in cid.lower() and cid not in out):
            continue
        loai = "private" if g.get("loai") == "private" else "group"
        _them(cid, loai, ten or cid, "", g.get("ts"), True)
        out[cid]["cho"] = True

    for loai, ds in (("group", groups), ("private", people)):
        for cid in ds:
            cid = str(cid).strip()
            if cid and cid not in out and (not hom or hom in cid.lower()):
                _them(cid, loai, cid, "", 0, False)

    dong = list(out.values())
    dong.sort(key=lambda d: (not d["cho"], -float(d.get("luc") or 0)))
    return dong[:n]
