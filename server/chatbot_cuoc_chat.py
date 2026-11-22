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


def _khoa_tk(accounts: List[dict]) -> List[str]:
    """Inbox account keys ("<channel>:<id>") of the channel accounts."""
    return [conversations._tai_khoan_id(str(a.get("channel") or ""), str(a.get("id") or ""))
            for a in (accounts or []) if isinstance(a, dict) and a.get("channel") and a.get("id")]


def ten_da_chon(accounts: List[dict], chat_ids: Any) -> Dict[str, str]:
    """`{chat_id: display name}` of the chats the form has ticked (or the bot saved), whatever the search box or the
    page size. The form uses it for a ticked row the current list does not hold, which it used to draw as a bare id
    (owner, 18/11/2026: "lúc thì hiện tên lúc chỉ hiện id"). Never raises."""
    try:
        return {cid: v["ten"] for cid, v in conversations.ten_theo_chat_id(_khoa_tk(accounts), list(chat_ids or [])).items()}
    except Exception:       # noqa: BLE001 - a name is a nicety, never a reason to fail the picker
        return {}


def danh_sach(accounts: List[dict], q: str = "", limit: int = 60,
              cho: Optional[List[dict]] = None, bot: Optional[dict] = None, *,
              chat_type: str = "") -> List[Dict[str, Any]]:
    """Các cuộc chat đã biết của `accounts` (bản công khai của tài khoản kênh, có `id` và `channel`).

    `cho`: hàng đợi duyệt của bot (`chatbot_runtime.nhom_cho`). `bot`: bản ghi bot, để đánh dấu
    `da_chon` (nằm trong `groups`/`people`). Trả các dòng {id, loai, ten, kenh, luc, da_chon, cho}.
    """
    q = str(q or "").strip()
    n = max(1, min(int(limit or 60), 200))
    chat_type = chat_type if chat_type in ("group", "private") else ""
    groups = (bot or {}).get("groups") or []
    people = (bot or {}).get("people") or []
    out: Dict[str, Dict[str, Any]] = {}

    def _them(cid, loai, ten, kenh, luc, cho_duyet, tk=""):
        d = out.get(cid)
        if d is None:
            # `tk`: the channel account the inbox saw this chat on (per-chat exceptions are scoped to it, 0.172.0);
            # empty for rows known only from the approval queue or the saved lists.
            d = out[cid] = {"id": cid, "loai": loai, "ten": ten, "kenh": kenh, "luc": luc or 0,
                            "da_chon": _khop(groups if loai == "group" else people, cid),
                            "cho": False, "tk": tk}
        d["cho"] = d["cho"] or bool(cho_duyet)
        if ten and not d.get("ten"):
            d["ten"] = ten

    for a in accounts or []:
        kenh = str((a or {}).get("channel") or "")
        aid = str((a or {}).get("id") or "")
        if not (kenh and aid):
            continue
        try:
            ds = conversations.cuoc_chat_cua_tai_khoan(kenh, aid, q, n, chat_type=chat_type)
        except Exception:
            ds = []
        for c in ds:
            cid = str(c.get("external_chat_id") or "")
            if not cid:
                continue
            loai = "group" if c.get("chat_type") == "group" else "private"
            ten = str(c.get("title") or c.get("customer_name") or cid)
            _them(cid, loai, ten, kenh, c.get("last_message_at") or c.get("updated_at"), False, aid)

    hom = q.lower()
    for g in (cho or []):
        loai = "private" if g.get("loai") == "private" else "group"
        if chat_type and loai != chat_type:
            continue
        cid = str(g.get("chat_id") or "")
        ten = str(g.get("ten") or "")
        if not cid or (hom and hom not in ten.lower() and hom not in cid.lower() and cid not in out):
            continue
        _them(cid, loai, ten or cid, "", g.get("ts"), True)
        out[cid]["cho"] = True

    # A saved id the page above did not bring (older than the `n` latest chats, or the search matched it only by name)
    # takes its name straight from the inbox, so it never shows as a bare id.
    saved_by_type = {"group": groups, "private": people}
    if chat_type:
        saved_by_type = {chat_type: saved_by_type[chat_type]}
    luu = [str(c).strip() for ids in saved_by_type.values() for c in ids
           if str(c).strip() and str(c).strip() not in out]
    try:
        biet = conversations.ten_theo_chat_id(_khoa_tk(accounts), luu) if luu else {}
    except Exception:       # noqa: BLE001
        biet = {}
    for loai, ds in saved_by_type.items():
        for cid in ds:
            cid = str(cid).strip()
            if not cid or cid in out:
                continue
            v = biet.get(cid) or {}
            ten = str(v.get("ten") or cid)
            if hom and hom not in cid.lower() and hom not in ten.lower():
                continue
            tk = str(v.get("tk") or "")
            _them(cid, loai, ten, tk.split(":", 1)[0] if tk else "", v.get("luc") or 0, False,
                  tk.split(":", 1)[1] if ":" in tk else "")

    dong = list(out.values())
    dong.sort(key=lambda d: (not d["cho"], -float(d.get("luc") or 0)))
    # Ticked rows are never cut by the page size: past it they would fall back to a bare id in the form.
    giu = {id(d) for d in dong[:n]} | {id(d) for d in dong if d["da_chon"]}
    return [d for d in dong if id(d) in giu]
