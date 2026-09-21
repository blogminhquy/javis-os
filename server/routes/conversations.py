"""Hộp thư hội thoại khách (Chatbot V2): đọc kho `conversations` cho trang Hội thoại.

Danh sách hội thoại, lịch sử tin, đánh dấu đã đọc, `mode` để người thật TIẾP QUẢN một cuộc
chat (bot im) và trả lại cho AI (phần chạy thật nằm ở `chatbot_runtime`, xem `che_do`), và từ
0.61.0 `reply`: chủ trả lời khách NGAY TỪ JAVIS qua năng lực gửi của kênh (sổ `channels`).

Kênh và tài khoản kênh có API riêng ở `routes/channels.py`; hai đường cũ
`/conversations/channels` và `/conversations/zalo/{id}/watch` giữ làm bí danh cho bookmark cũ.

Xác thực: như mọi route khác, đi qua `_auth_guard` của main.py (cookie phiên hoặc API token).
Không nhận `import main` - mọi thứ cần từ main đi qua `deps`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

import channel_accounts
import channels
import chatbot_store
import conversations
import routes.channels as channels_routes

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
                "channels": channels.cho_giao_dien()}

    @router.get("/conversations/stats")
    async def conversations_stats(bot_id: str = "", channel: str = "", account_id: str = ""):
        return {"ok": True, "stats": conversations.thong_ke(bot_id=bot_id, channel=channel,
                                                              account_id=account_id)}

    @router.get("/conversations/channels")
    async def conversations_channels():
        """Bí danh của GET /channels/accounts (0.61.0): mọi tài khoản kênh, một khuôn."""
        return {"ok": True, "accounts": channels_routes._tai_khoan_thong_nhat(),
                "channels": channels.cho_giao_dien()}

    @router.post("/conversations/zalo/{conn_id}/watch")
    async def conversations_zalo_watch(conn_id: str, on: str = Form("1")):
        """Bí danh cũ của POST /channels/accounts/{id}/watch cho Zalo cá nhân."""
        m = channels.module("zalo_personal")
        if not m:
            return JSONResponse({"ok": False, "error": "kênh Zalo cá nhân chưa có trong sổ"}, status_code=400)
        r = m.bat(conn_id, str(on).strip().lower() in ("1", "true", "on", "yes"))
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

    @router.post("/conversations/{conv_id}/reply")
    async def conversations_reply(conv_id: int, text: str = Form(...)):
        """Chủ trả lời khách ngay từ Hộp thư (Chatbot V2 bản V1.2).

        Gửi qua năng lực `gui` của kênh trong sổ đăng ký: bot Telegram/Zalo gửi bằng token của
        tài khoản, Zalo cá nhân gửi bằng MCP dưới danh tính chủ. Gửi được thì ghi vào kho như
        tin `human`, và nếu cuộc này có bot đang trực ở chế độ AI thì TIẾP QUẢN luôn (chuyển
        `human`): người vừa nhắn tay mà bot chen vào câu sau là khách đọc hai giọng một lúc.
        Trả `tiep_quan: true` để giao diện nói ra điều đó.
        """
        c = conversations.chi_tiet(conv_id)
        if not c:
            return _404()
        txt = str(text or "").strip()
        if not txt:
            return JSONResponse({"ok": False, "error": "tin rỗng"}, status_code=400)
        if len(txt) > conversations.MAX_CHU:
            return JSONResponse({"ok": False, "error": f"tin dài quá {conversations.MAX_CHU} ký tự"}, status_code=400)
        kenh = str(c.get("channel") or "")
        key = str(c.get("channel_account_id") or "")
        raw = key.split(":", 1)[1] if ":" in key else key
        s = channels.spec(kenh)
        if not s:
            return JSONResponse({"ok": False, "error": f"kênh '{kenh}' không có trong sổ đăng ký"}, status_code=400)
        tk = {"id": raw, "channel": kenh}
        if s.kind == "bot":
            a = channel_accounts.get_account(raw) or {}
            tk.update({k: a.get(k) for k in ("label", "external_id")})
            tk["token"] = channel_accounts.get_token(raw)
        ok, loi = await channels.gui(kenh, tk, str(c.get("external_chat_id") or ""), txt,
                                     str(c.get("chat_type") or "private"))
        if not ok:
            return JSONResponse({"ok": False, "error": loi or "không gửi được"}, status_code=400)
        r = conversations.ghi_su_kien({
            "channel": kenh, "account_id": raw, "account_name": c.get("account_name") or "",
            "bot_id": c.get("bot_id") or "",
            "external_chat_id": c.get("external_chat_id"), "chat_type": c.get("chat_type"),
            "chat_title": c.get("title") if c.get("chat_type") == "group" else "",
            "sender_type": "human", "sender_name": "Bạn", "message_type": "text", "text": txt,
            "metadata": {"tu_javis": True},
        })
        tiep_quan = False
        if c.get("bot_id") and str(c.get("mode") or "ai") == "ai":
            conversations.dat_che_do(conv_id, "human")
            tiep_quan = True
        return {"ok": True, "message_id": r.get("message_id"), "tiep_quan": tiep_quan,
                "conversation": conversations.chi_tiet(conv_id)}

    @router.post("/conversations/{conv_id}/mode")
    async def conversations_mode(conv_id: int, mode: str = Form(...)):
        """ai | human | waiting | closed. `human` = người thật tiếp quản, bot im ở cuộc chat đó."""
        ok, err = conversations.dat_che_do(conv_id, mode)
        if not ok:
            return JSONResponse({"ok": False, "error": err},
                                status_code=404 if "không có" in err else 400)
        return {"ok": True, "conversation": conversations.chi_tiet(conv_id)}

    app.include_router(router)
