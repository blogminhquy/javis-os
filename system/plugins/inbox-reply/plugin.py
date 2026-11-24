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

Images and files (issue #1802): `inbox_reply` also takes `files`, paths of images or documents already in the brain
(a price list, a product photo). They go through `routes.conversations.owner_send_file`, the one send path of the
inbox + button, so the same refusals, size cap, platform rules (Messenger's 24-hour window) and history record apply.
Every path must resolve, symlinks included, to a file inside the calling brain and outside hidden folders, and every
file is checked before the first one is sent, so a bad path never leaves a customer with half a reply.

Never returns a token.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

_MAX_ROWS = 30
MAX_FILES = 10          # files per inbox_reply call


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


def _brain_files(raw_paths, brain: str):
    """Check the `files` of an inbox_reply call against the calling brain. Returns ([Path], "") or ([], error).

    Each path is relative to the brain root (or absolute inside it) and must resolve, symlinks included, to a non-empty
    file inside the brain, outside hidden folders, within the inbox's size cap. Blocking file checks: run in a thread."""
    from routes.conversations import MAX_SENT_FILE
    if not isinstance(raw_paths, list):
        raw_paths = [raw_paths]
    wanted = [str(x or "").strip() for x in raw_paths]
    if not any(wanted):
        return [], "files is empty; give paths inside the brain, e.g. attachments/price-list.png."
    if len(wanted) > MAX_FILES:
        return [], f"at most {MAX_FILES} files per call; send the rest in another call."
    if not brain:
        return [], "this call has no brain, so there is nowhere to take files from."
    try:
        root = Path(brain).resolve()
    except (OSError, ValueError, RuntimeError):
        return [], "the brain folder of this call cannot be read."
    out, seen = [], set()
    for raw in wanted:
        if not raw:
            return [], "one of the files is an empty path."
        cand = Path(raw)
        if not cand.is_absolute():
            cand = root / cand
        try:
            real = cand.resolve(strict=True)
        except (OSError, ValueError, RuntimeError):
            return [], f"'{raw}' was not found in the brain."
        try:
            rel = real.relative_to(root)
        except ValueError:
            return [], f"'{raw}' is outside the brain; only files inside the brain can be sent."
        if any(part.startswith(".") for part in rel.parts):
            return [], f"'{raw}' is in a hidden file or folder, which is never sent to customers."
        if not real.is_file():
            return [], f"'{raw}' is not a file."
        size = real.stat().st_size
        if size <= 0:
            return [], f"'{raw}' is empty."
        if size > MAX_SENT_FILE:
            return [], f"'{raw}' is larger than {MAX_SENT_FILE // 1048576} MB, the limit for a file sent to a customer."
        if real not in seen:
            seen.add(real)
            out.append(real)
    return out, ""


def _read_capped(path: Path, cap: int) -> bytes:
    """At most `cap + 1` bytes, so a file that grew after the check is still refused as too big."""
    with open(path, "rb") as f:
        return f.read(cap + 1)


async def _send_files(c: dict, files: list, text: str) -> dict:
    """Send `files` into conversation `c` one by one through the inbox's send path, `text` as the caption of the first
    (or after them, as its own message, when it is longer than a caption). Stops at the first failure and says what
    already went, so the model never sends a file twice."""
    from routes.conversations import MAX_CAPTION, MAX_SENT_FILE, owner_reply, owner_send_file
    caption = text if len(text) <= MAX_CAPTION else ""
    sent, ids = [], []
    for i, path in enumerate(files):
        data = await asyncio.to_thread(_read_capped, path, MAX_SENT_FILE)
        r = await owner_send_file(c["id"], path.name, data, caption if i == 0 else "", via="tool", take_over=False)
        if not r.get("ok"):
            done = f" Already sent, do not send again: {', '.join(sent)}." if sent else " Nothing was sent."
            left = [p.name for p in files[i + 1:]]
            more = f" Not sent: {', '.join(left)}." if left else ""
            words = " The text was not sent either." if text and (i == 0 or not caption) else ""
            why = str(r.get("error") or "could not send").rstrip(". ")
            return {"ok": False, "error": f"{path.name}: {why}.{done}{more}{words}"}
        sent.append(path.name)
        ids.append(r.get("message_id"))
    if text and not caption:
        r = await owner_reply(c["id"], text, via="tool", take_over=False)
        if not r.get("ok"):
            return {"ok": False, "error": f"the files went ({', '.join(sent)}; do not send them again) but the text "
                                          f"did not: {r.get('error') or 'could not send'}"}
        ids.append(r.get("message_id"))
    return {"ok": True, "files_sent": sent, "message_ids": ids}


async def _reply(args, ctx):
    """The model reads what this returns, so the errors of the send path (written for a screen in two languages)
    come back in English whatever the machine's screen language is."""
    import localefmt
    token = localefmt.dat_ngon_ngu_yeu_cau("en")
    try:
        return await _send_reply(args, ctx)
    finally:
        localefmt.bo_ngon_ngu_yeu_cau(token)


async def _send_reply(args, ctx):
    from routes.conversations import file_refusal, owner_reply
    args = args or {}
    cid = int(args.get("conversation_id") or 0)
    if not cid:
        return "ERROR: conversation_id is required; find it with inbox_find."
    import conversations
    c0 = conversations.chi_tiet(cid)
    if not c0 or not _in_this_brain(c0, ctx):
        return "ERROR: no conversation with that id."
    text = str(args.get("text") or "").strip()
    raw_files = args.get("files")
    if raw_files in (None, "", []):
        r = await owner_reply(cid, text, via="tool", take_over=False)
        if not r.get("ok"):
            return "ERROR: " + str(r.get("error") or "could not send")
        c = r.get("conversation") or {}
        return _out({"ok": True, "sent_to": _row(c) if c else {"conversation_id": cid},
                     "message_id": r.get("message_id")})
    if len(text) > conversations.MAX_CHU:
        return f"ERROR: text longer than {conversations.MAX_CHU} characters. Nothing was sent."
    files, why = await asyncio.to_thread(_brain_files, raw_files, str(getattr(ctx, "vault_root", "") or ""))
    if why:
        return f"ERROR: {why} Nothing was sent."
    for f in files:
        refused = file_refusal(c0, f.name)
        if refused:
            return f"ERROR: {f.name}: {str(refused.get('error')).rstrip('. ')}. Nothing was sent."
    r = await _send_files(c0, files, text)
    if not r.get("ok"):
        return "ERROR: " + str(r.get("error"))
    c = conversations.chi_tiet(cid) or {}
    return _out({"ok": True, "sent_to": _row(c) if c else {"conversation_id": cid},
                 "files_sent": r["files_sent"], "message_ids": r["message_ids"]})


def register(ctx):
    ctx.register_tool(
        name="inbox_find",
        description=("Find customer conversations in the inbox (Messenger, Instagram, Telegram, Zalo...) by customer "
                     "name, words in a message, channel or status (need_reply, unread). Pass conversation_id to read "
                     "that conversation's latest messages. Returns the conversation_id to use with inbox_reply."),
        handler=_find, min_mode="readonly",
        schema={"type": "object", "properties": {
            "q": {"type": "string", "description": "Customer name, phone number or words in a message."},
            "channel": {"type": "string", "description": "messenger | telegram | zalo | zalo_personal ... Empty = every "
                                                         "channel. Instagram is part of the messenger channel."},
            "status": {"type": "string", "description": "need_reply | unread | human. Empty = all."},
            "conversation_id": {"type": "integer", "description": "Read the messages of this conversation."},
            "limit": {"type": "integer"}}},
    )
    ctx.register_tool(
        name="inbox_reply",
        description=("Send a reply into one customer conversation on its own channel (Messenger and Instagram through "
                     "the Page, Telegram/Zalo bots, personal Zalo), as if the owner typed it in the inbox: text, images "
                     "or files already in the brain, or both. Recorded as the owner's message; the conversation's bot "
                     "keeps running. Send only when the owner asks; take conversation_id from inbox_find and ask back "
                     "when several match. Messenger only accepts messages within 24 hours of the customer's last one. "
                     "A Facebook comment takes images only, an Instagram comment text only."),
        handler=_reply, min_mode="full",
        schema={"type": "object", "properties": {
            "conversation_id": {"type": "integer"},
            "text": {"type": "string", "description": "What to send the customer, plain text (no markdown). Optional "
                                                      "when files are given: it then goes with the first file."},
            "files": {"type": "array", "items": {"type": "string"},
                      "description": (f"Optional, up to {MAX_FILES}: images or files inside this brain, as paths "
                                      "relative to its root (e.g. attachments/price-list.png). Sent in this order.")}},
            "required": ["conversation_id"]},
    )
