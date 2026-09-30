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

import time
from dataclasses import dataclass
from typing import Callable, Optional

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
    # Chủ nhờ bot trả lời từ Hộp thư (0.65.5): `manual_answer(conv, msgs, draft)` chạy Agent, `manual_done(conv, msgs, text, meta)`
    # ghi và dạy sau khi đã gửi. Không import chatbot_runtime ở đây: route đi qua deps như mọi route khác.
    manual_answer: Callable = None
    manual_done: Callable = None


_DEPS: "ConversationsDeps" = None   # type: ignore


def _404(msg: str = "không có hội thoại nào id đó"):
    return JSONResponse({"ok": False, "error": msg}, status_code=404)


def register(app, deps: ConversationsDeps):
    global _DEPS
    _DEPS = deps

    def _tk_goc(c: dict) -> str:
        key = str(c.get("channel_account_id") or "")
        return key.split(":", 1)[1] if ":" in key else key

    async def _gui_tin(c: dict, txt: str, tieng_vong: bool = False, reply_to: Optional[dict] = None):
        """Gửi một tin chữ vào cuộc chat qua năng lực `gui` của kênh. Trả (ok, lỗi). Dùng chung cho chủ gõ tay và cho lượt
        nhờ bot trả lời (0.65.5), để hai đường không lệch nhau ở cách dựng tài khoản gửi.

        `tieng_vong=True` (câu của BOT): trên Zalo cá nhân phải nhớ câu vừa gửi TRƯỚC khi gửi, y như `Transport._gui`, không thì vòng
        đọc thấy nó quay về như tin của chính chủ (bot tưởng chủ vừa nhắn tay nên im cả quãng) hoặc như tin của một khách (bot tự
        trả lời chính mình trong nhóm).

        `reply_to` (tin khách bot đang trả lời): trong nhóm Zalo cá nhân, câu của bot tag đúng người gửi tin đó, y như bot tự trả lời."""
        kenh = str(c.get("channel") or "")
        raw = _tk_goc(c)
        if tieng_vong and kenh == "zalo_personal":
            try:
                import zalo_personal_channel as zc
                zc.ghi_da_gui(raw, str(c.get("external_chat_id") or ""), txt)
            except Exception:      # noqa: BLE001 - không nhớ được tiếng vọng thì vẫn gửi, tệ nhất là một dòng trùng trong Hộp thư
                pass
        s = channels.spec(kenh)
        if not s:
            return False, f"kênh '{kenh}' không có trong sổ đăng ký"
        tk = {"id": raw, "channel": kenh}
        if s.kind == "bot":
            a = channel_accounts.get_account(raw) or {}
            tk.update({k: a.get(k) for k in ("label", "external_id")})
            tk["token"] = channel_accounts.get_token(raw)
        extra = {}
        if tieng_vong and kenh == "zalo_personal" and reply_to and str(c.get("chat_type") or "") == "group":
            extra["mention"] = {"uid": reply_to.get("sender_id"), "name": reply_to.get("sender_name")}
        return await channels.gui(kenh, tk, str(c.get("external_chat_id") or ""), txt, str(c.get("chat_type") or "private"), **extra)

    def _hesitant() -> list:
        """Nhóm bot vừa cân nhắc nói rồi im trong 24 giờ qua (kho bộ phán xử). Kho hỏng hay chưa có thì rỗng: bộ lọc
        chỉ mất phần nhóm chứ không sập hòm thư."""
        try:
            import chatbot_reply_policy_store as rps
            return rps.hesitant_chats(time.time() - 86400)
        except Exception:      # noqa: BLE001
            return []

    def _bot_silence(conv: dict, msgs: list):
        """Vì sao bot im ở tin khách CUỐI của cuộc chat này, nếu bộ phán xử có ghi. Chỉ khi cuộc chat đang ở chế độ AI, tin
        cuối là của khách, và quyết định gần nhất là `silent` cho đúng tin đó (mốc giờ lệch không quá 60 giây, vì quyết định ghi
        theo giờ tin). Người thật đang tiếp quản thì bot im là hiển nhiên, không cần nói."""
        try:
            bot_id = str(conv.get("bot_id") or "")
            if not bot_id or str(conv.get("mode") or "ai") != "ai" or not msgs or msgs[-1].get("sender_type") != "customer":
                return None
            import chatbot_reply_policy_store as rps
            d = rps.last_decision(bot_id, str(conv.get("external_chat_id") or ""))
            if not d or d.get("verdict") != "silent":
                return None
            if float(d.get("ts") or 0) < float(msgs[-1].get("created_at") or 0) - 60:
                return None
            return {"decision_id": d.get("id"), "code": d.get("silence_code") or "", "reason": d.get("reason") or "",
                    "score": d.get("score"), "threshold": d.get("threshold")}
        except Exception:      # noqa: BLE001 - dòng phụ này hỏng không được làm hỏng việc đọc hội thoại
            return None

    def _ten_bot(bot_id: str) -> str:
        """Tên bot để hiện trên hàng hội thoại và ở dropdown lọc. Bot đã xoá thì báo thẳng, không lòi id thô."""
        if not bot_id:
            return ""
        b = chatbot_store.get_bot(bot_id)
        return str((b or {}).get("name") or "") or "Bot đã xoá"

    @router.get("/conversations")
    async def conversations_list(channel: str = "", bot_id: str = "", account_id: str = "",
                                 q: str = "", mode: str = "", limit: int = 50, offset: int = 0,
                                 status: str = "", chat_type: str = ""):
        """Danh sách hội thoại mới nhất trước, kèm vài con số đầu trang (cùng bộ lọc).

        0.65.3: thêm `status` (unread | need_reply | human) và `chat_type` (group | private); mỗi hàng có `bot_name`;
        `facets` là số hội thoại cho từng lựa chọn dropdown (toàn hòm thư, không theo bộ lọc) và `bots` là danh sách bot
        có hội thoại kèm tên, cho dropdown Bot."""
        hesitant = _hesitant()
        items = conversations.danh_sach(channel=channel, bot_id=bot_id, account_id=account_id,
                                        q=q, mode=mode, limit=limit, offset=offset,
                                        status=status, chat_type=chat_type, hesitant=hesitant)
        if offset > 0:
            # Trang thứ hai trở đi (0.65.11, cuộn xuống thì tải thêm) chỉ cần các dòng: số đếm, bộ lọc và danh sách bot đã có từ trang
            # đầu, tính lại cho mỗi trang là tốn công vô ích.
            for it in items:
                it["bot_name"] = _ten_bot(str(it.get("bot_id") or ""))
                it["need_reply"] = conversations.can_tra_loi(it, hesitant)
            return {"ok": True, "items": items}
        facets = conversations.dem_bo_loc(hesitant)
        ten = {bid: _ten_bot(bid) for bid in facets["bots"] if bid}
        for it in items:
            it["bot_name"] = ten.get(str(it.get("bot_id") or "")) or _ten_bot(str(it.get("bot_id") or ""))
            it["need_reply"] = conversations.can_tra_loi(it, hesitant)
        return {"ok": True, "items": items,
                "stats": conversations.thong_ke(bot_id=bot_id, channel=channel, account_id=account_id),
                "facets": facets,
                "bots": [{"id": bid, "name": ten[bid], **facets["bots"][bid]} for bid in ten],
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
    async def conversations_messages(conv_id: int, limit: int = 100, before: int = 0, after: int = 0):
        """Tin của một hội thoại, cũ trước mới sau.

        Mặc định lấy `limit` tin MỚI NHẤT; `before=<id>` lấy các tin cũ hơn id đó (kéo lên để xem thêm); `after=<id>` (0.65.11) chỉ lấy tin MỚI
        hơn id đó, dành cho nhịp làm mới 5 giây. `has_more` cho biết còn tin cũ hơn tin đầu của phần trả về hay không."""
        d = conversations.chi_tiet(conv_id)
        if not d:
            return _404()
        moi = after > 0
        msgs = conversations.tin_nhan(conv_id, limit=limit, before_id=before, after_id=after)
        d["bot_name"] = _ten_bot(str(d.get("bot_id") or ""))
        bot_id = str(d.get("bot_id") or "")
        # Lý do bot im gắn với tin khách CUỐI của cuộc chat, không phải cuối phần trả về: nhịp chỉ hỏi tin mới có thể trả rỗng, và
        # kéo lên xem tin cũ thì phần trả về không chứa tin cuối.
        cuoi = msgs if (not moi and not before) else conversations.tin_nhan(conv_id, limit=1)
        # `bot_running`: giao diện cần biết bot có đang chạy để bật hay nói lý do tắt nút "Trả lời giúp tin này".
        return {"ok": True, "conversation": d, "messages": msgs, "bot_silence": _bot_silence(d, cuoi),
                "has_more": (False if moi else (bool(msgs) and conversations.co_tin_cu(conv_id, msgs[0]["id"]))),
                "bot_running": bool(bot_id and (_DEPS.bot_status(bot_id) or {}).get("running"))}

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
        ok, loi = await _gui_tin(c, txt)
        if not ok:
            return JSONResponse({"ok": False, "error": loi or "không gửi được"}, status_code=400)
        raw = _tk_goc(c)
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

    @router.post("/conversations/{conv_id}/ai-reply")
    async def conversations_ai_reply(conv_id: int, mode: str = Form("send")):
        """Chủ nhờ BOT trả lời ngay từ Hộp thư (0.65.5). `mode=send`: bot trả lời tin khách cuối và câu đó được gửi luôn; cuộc chat
        vẫn ở chế độ Tự động. `mode=draft`: bot chỉ soạn, trả chữ về để đổ vào ô nhập, không gửi và không để lại dấu vết.

        Chỉ đúng chế độ mới chạy, và trả `code` để giao diện nói được lý do: `human` (đang tiếp quản), `bot_off` (bot đang tắt),
        `no_bot`, `already_answered` (tin cuối không phải của khách), `busy`, `no_message`, `send_failed`, `engine`."""
        if mode not in ("send", "draft"):
            return JSONResponse({"ok": False, "code": "bad_mode", "error": "mode phải là send hoặc draft"}, status_code=400)
        if _DEPS.manual_answer is None:
            return JSONResponse({"ok": False, "code": "unavailable", "error": "Chưa nối bot vào Hộp thư"}, status_code=503)
        c = conversations.chi_tiet(conv_id)
        if not c:
            return _404()
        bot_id = str(c.get("bot_id") or "")
        if not bot_id:
            return JSONResponse({"ok": False, "code": "no_bot", "error": "Cuộc chat này không có bot trực"}, status_code=400)
        msgs = conversations.tin_nhan(conv_id, limit=30)
        send = mode == "send"
        if send:
            # Tin cuối phải là của khách: bot đã đáp (hay bạn đã đáp) rồi thì "trả lời giúp" là nói lần hai.
            if not msgs or msgs[-1].get("sender_type") != "customer":
                return JSONResponse({"ok": False, "code": "already_answered", "error": "Tin cuối không phải của khách"}, status_code=409)
            if str(c.get("mode") or "ai") != "ai":
                return JSONResponse({"ok": False, "code": "human", "error": "Bạn đang tiếp quản cuộc chat này"}, status_code=409)
            if not (_DEPS.bot_status(bot_id) or {}).get("running"):
                return JSONResponse({"ok": False, "code": "bot_off", "error": "Bot đang tắt"}, status_code=409)
        r = await _DEPS.manual_answer(c, msgs, not send)
        if not r.get("ok"):
            status = 409 if r.get("code") == "busy" else 400 if r.get("code") in ("no_bot", "no_message") else 502
            return JSONResponse({"ok": False, "code": r.get("code") or "engine", "error": r.get("error") or "Bot không soạn được"},
                                status_code=status)
        if r.get("silent"):
            return {"ok": True, "silent": True, "text": ""}
        if not send:
            return {"ok": True, "silent": False, "text": r["text"], "draft": True}
        ok, loi = await _gui_tin(c, r["text"], tieng_vong=True, reply_to=msgs[-1])
        if not ok:
            # Không gửi được thì trả chữ đã soạn để chủ dán vào ô nhập gửi tay, khỏi mất công soạn lại.
            return JSONResponse({"ok": False, "code": "send_failed", "error": loi or "không gửi được", "text": r["text"]},
                                status_code=400)
        done = _DEPS.manual_done(c, msgs, r["text"], r["meta"]) if _DEPS.manual_done else {}
        return {"ok": True, "silent": False, "text": r["text"], "taught": bool((done or {}).get("taught")),
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
