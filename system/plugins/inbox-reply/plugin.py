"""Bundled plugin: answer a customer from chat, on any channel the inbox holds.

The inbox (Hội thoại page) already lets the owner type a reply that goes out through the conversation's own channel
(`routes.conversations.owner_reply`: Messenger and Instagram through the Page's Send API, Telegram and Zalo bots with
their token, personal Zalo through its MCP). Before this plugin an engine had no tool for that path, so it told the
owner "there is no Messenger send tool" and asked them to paste drafts by hand. `inbox_find` locates the conversation
(read-only); `inbox_reply` sends into it, records the message as the owner's and takes the chat over from its bot,
like a reply typed in the inbox. Sending reaches a real customer, hence `min_mode: full`.

Safety (review of PR 1554):
- Both tools are OWNER-ONLY (`mcp_hub.OWNER_ONLY_TOOLS`): a customer chatting with a dedicated bot must never list,
  read or message the shop's other customers through them.
- Both stay inside the calling brain: conversations of channel accounts assigned to another brain are out of reach,
  by the same rule as the inbox list (`channel_accounts.keys_of_other_brains`, #1243).
- A message sent from chat does NOT take the conversation over from its bot (an inbox reply typed by hand does). The
  owner asked Javis to pass on one message; a bot that then fell silent for that customer until someone found the
  "hand back" button would be a surprise, not help.

Never returns a token.
"""
from __future__ import annotations

import json

_MAX_ROWS = 30


def _row(c: dict) -> dict:
    chat = str(c.get("external_chat_id") or "")
    return {
        "conversation_id": c.get("id"),
        "channel": c.get("channel"),
        "instagram": chat.startswith(("ig:", "igc:")),
        "comment_thread": chat.startswith(("cmt:", "igc:")),
        "account": c.get("account_name") or "",
        "customer": c.get("customer_name") or c.get("title") or "",
        "chat_type": c.get("chat_type"),
        "handled_by": "human" if str(c.get("mode") or "ai") == "human" else ("bot" if c.get("bot_id") else "nobody"),
        "unread": int(c.get("unread_count") or 0),
        "last_from": c.get("last_sender_type") or "",
        "last_message": str(c.get("last_message") or "")[:200],
    }


def _out(d) -> str:
    return json.dumps(d, ensure_ascii=False, default=str)


def _other_brain_accounts(ctx) -> list:
    """Account keys of the channel accounts assigned to another brain than the caller's ([] = no filter)."""
    brain = str(getattr(ctx, "vault_root", "") or "").strip()
    if not brain:
        return []
    import channel_accounts
    return channel_accounts.keys_of_other_brains(brain)


def _in_this_brain(c: dict, ctx) -> bool:
    return str(c.get("channel_account_id") or "") not in set(_other_brain_accounts(ctx))


async def _find(args, ctx):
    import conversations
    args = args or {}
    cid = int(args.get("conversation_id") or 0)
    if cid:
        c = conversations.chi_tiet(cid)
        if not c or not _in_this_brain(c, ctx):
            return "ERROR: no conversation with that id."
        n = max(1, min(int(args.get("limit") or 20), 100))
        msgs = conversations.tin_nhan(cid, limit=n)
        return _out({"ok": True, "conversation": _row(c), "messages": [
            {"from": m.get("sender_type"), "name": m.get("sender_name") or "", "text": str(m.get("text") or "")[:1000],
             "type": m.get("message_type"), "at": m.get("created_at")} for m in msgs]})
    status = str(args.get("status") or "").strip()
    rows = conversations.danh_sach(
        channel=str(args.get("channel") or "").strip(), q=str(args.get("q") or "").strip(),
        status=status if status in ("unread", "need_reply", "human") else "",
        limit=max(1, min(int(args.get("limit") or 15), _MAX_ROWS)), hidden="exclude",
        exclude_account_ids=_other_brain_accounts(ctx) or None)
    return _out({"ok": True, "count": len(rows), "conversations": [_row(c) for c in rows],
                 "hint": "Several matches for one name: ask the owner which one before inbox_reply."})


async def _reply(args, ctx):
    from routes.conversations import owner_reply
    args = args or {}
    cid = int(args.get("conversation_id") or 0)
    if not cid:
        return "ERROR: conversation_id is required; find it with inbox_find."
    import conversations
    c0 = conversations.chi_tiet(cid)
    if not c0 or not _in_this_brain(c0, ctx):
        return "ERROR: no conversation with that id."
    r = await owner_reply(cid, str(args.get("text") or ""), via="tool", take_over=False)
    if not r.get("ok"):
        return "ERROR: " + str(r.get("error") or "could not send")
    c = r.get("conversation") or {}
    return _out({"ok": True, "sent_to": _row(c) if c else {"conversation_id": cid},
                 "message_id": r.get("message_id")})


def register(ctx):
    ctx.register_tool(
        name="inbox_find",
        description=("Tìm hội thoại khách trên trang Hội thoại (Messenger, Instagram, Telegram, Zalo...) theo tên khách, "
                     "chữ trong tin, kênh hoặc trạng thái (need_reply, unread). Truyền conversation_id để đọc các tin gần "
                     "nhất của một cuộc. Trả conversation_id để dùng với inbox_reply."),
        handler=_find, min_mode="readonly",
        schema={"type": "object", "properties": {
            "q": {"type": "string", "description": "Tên khách, số điện thoại hoặc chữ trong tin."},
            "channel": {"type": "string", "description": "messenger | telegram | zalo | zalo_personal ... Trống = mọi kênh. "
                                                         "Instagram nằm trong kênh messenger."},
            "status": {"type": "string", "description": "need_reply | unread | human. Trống = tất cả."},
            "conversation_id": {"type": "integer", "description": "Đọc tin của hội thoại này."},
            "limit": {"type": "integer"}}},
    )
    ctx.register_tool(
        name="inbox_reply",
        description=("Gửi tin trả lời vào một hội thoại khách, đi đúng kênh của cuộc đó (Messenger và Instagram qua Page, "
                     "bot Telegram/Zalo, Zalo cá nhân), y như chủ gõ ở Hộp thư. Tin ghi là của chủ; bot của cuộc đó vẫn chạy "
                     "như cũ. Chỉ gửi khi chủ yêu cầu; lấy conversation_id từ inbox_find, trùng tên thì hỏi lại. "
                     "Messenger chỉ nhận tin trong 24 giờ kể từ tin cuối của khách."),
        handler=_reply, min_mode="full",
        schema={"type": "object", "properties": {
            "conversation_id": {"type": "integer"},
            "text": {"type": "string", "description": "Nội dung gửi khách, chữ thường (không markdown)."}},
            "required": ["conversation_id", "text"]},
    )
