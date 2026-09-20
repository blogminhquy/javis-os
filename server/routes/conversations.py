"""Hộp thư hội thoại khách (Chatbot V2): đọc kho `conversations` cho trang Hội thoại.

V1 là TRÌNH XEM: danh sách hội thoại, lịch sử tin, đánh dấu đã đọc, bật/tắt ghi cho từng tài
khoản Zalo cá nhân. Thêm một đường `mode` để người thật TIẾP QUẢN một cuộc chat (bot im) và trả
lại cho AI - phần chạy thật của tiếp quản nằm ở `chatbot_runtime` (xem `che_do` ở đó).

Xác thực: như mọi route khác, đi qua `_auth_guard` của main.py (cookie phiên hoặc API token).
Không nhận `import main` - mọi thứ cần từ main đi qua `deps`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

import chatbot_store
import conversations
import zalo_personal_channel

router = APIRouter()


@dataclass
class ConversationsDeps:
    # Trạng thái sống của một bot (chatbot_runtime.status) - để mục Kênh nói bot đang chạy hay không.
    bot_status: Callable[[str], dict]


_DEPS: "ConversationsDeps" = None   # type: ignore


def _404(msg: str = "không có hội thoại nào id đó"):
    return JSONResponse({"ok": False, "error": msg}, status_code=404)


def register(app, deps: ConversationsDeps):
    global _DEPS
    _DEPS = deps

    @router.get("/conversations")
    async def conversations_list(channel: str = "", bot_id: str = "", account_id: str = "",
                                 q: str = "", mode: str = "", limit: int = 50, offset: int = 0):
        """Danh sách hội thoại mới nhất trước, kèm vài con số đầu trang (cùng bộ lọc)."""
        items = conversations.danh_sach(channel=channel, bot_id=bot_id, account_id=account_id,
                                        q=q, mode=mode, limit=limit, offset=offset)
        return {"ok": True, "items": items,
                "stats": conversations.thong_ke(bot_id=bot_id, channel=channel, account_id=account_id),
                "channels": [{"id": k, "nhan": v} for k, v in conversations.KENH_NHAN.items()]}

    @router.get("/conversations/stats")
    async def conversations_stats(bot_id: str = "", channel: str = "", account_id: str = ""):
        return {"ok": True, "stats": conversations.thong_ke(bot_id=bot_id, channel=channel,
                                                              account_id=account_id)}

    @router.get("/conversations/channels")
    async def conversations_channels():
        """Mục Kênh của trang Hội thoại: bot chuyên trách (tự ghi) và tài khoản Zalo cá nhân
        (ghi khi chủ bật). Kèm số hội thoại đã có của từng tài khoản kênh."""
        da_co = {a["id"]: a for a in conversations.tai_khoan()}
        bots = []
        for b in chatbot_store.list_bots():
            kenh = "zalo" if str(b.get("channel") or "") == "zalo" else "telegram"
            tk = da_co.get(f"{kenh}:{b['id']}") or {}
            st = {}
            try:
                st = _DEPS.bot_status(b["id"]) if _DEPS else {}
            except Exception:
                st = {}
            bots.append({
                "id": b["id"], "name": b.get("name") or "", "icon": b.get("icon") or "headset",
                "channel": kenh, "channel_label": conversations.KENH_NHAN.get(kenh, kenh),
                "brain": b.get("brain") or "", "enabled": bool(b.get("enabled")),
                "state": (st or {}).get("state") or "off",
                "account_id": f"{kenh}:{b['id']}",
                "so_hoi_thoai": int(tk.get("so_hoi_thoai") or 0),
                "chua_doc": int(tk.get("chua_doc") or 0),
            })
        zalo = []
        for z in zalo_personal_channel.tai_khoan():
            tk = da_co.get(f"{zalo_personal_channel.KENH}:{z['id']}") or {}
            z = dict(z)
            z["channel_label"] = conversations.KENH_NHAN.get(zalo_personal_channel.KENH)
            z["account_id"] = f"{zalo_personal_channel.KENH}:{z['id']}"
            z["so_hoi_thoai"] = int(tk.get("so_hoi_thoai") or 0)
            z["chua_doc"] = int(tk.get("chua_doc") or 0)
            zalo.append(z)
        return {"ok": True, "bots": bots, "zalo_personal": zalo,
                "zalo_dang_doc": zalo_personal_channel.trang_thai().get("dang_chay", False),
                "channels": [{"id": k, "nhan": v} for k, v in conversations.KENH_NHAN.items()]}

    @router.post("/conversations/zalo/{conn_id}/watch")
    async def conversations_zalo_watch(conn_id: str, on: str = Form("1")):
        """Bật/tắt ghi hội thoại của một tài khoản Zalo cá nhân vào Hộp thư."""
        r = zalo_personal_channel.bat(conn_id, str(on).strip().lower() in ("1", "true", "on", "yes"))
        return r if r.get("ok") else JSONResponse(r, status_code=400)

    @router.get("/conversations/{conv_id}")
    async def conversations_detail(conv_id: int):
        d = conversations.chi_tiet(conv_id)
        return {"ok": True, "conversation": d} if d else _404()

    @router.get("/conversations/{conv_id}/messages")
    async def conversations_messages(conv_id: int, limit: int = 100, before: int = 0):
        d = conversations.chi_tiet(conv_id)
        if not d:
            return _404()
        return {"ok": True, "conversation": d,
                "messages": conversations.tin_nhan(conv_id, limit=limit, before_id=before)}

    @router.post("/conversations/{conv_id}/read")
    async def conversations_read(conv_id: int):
        return {"ok": True} if conversations.danh_dau_da_doc(conv_id) else _404()

    @router.post("/conversations/{conv_id}/mode")
    async def conversations_mode(conv_id: int, mode: str = Form(...)):
        """ai | human | waiting | closed. `human` = người thật tiếp quản, bot im ở cuộc chat đó."""
        ok, err = conversations.dat_che_do(conv_id, mode)
        if not ok:
            return JSONResponse({"ok": False, "error": err},
                                status_code=404 if "không có" in err else 400)
        return {"ok": True, "conversation": conversations.chi_tiet(conv_id)}

    app.include_router(router)
