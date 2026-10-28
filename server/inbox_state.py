"""Who is handling a customer conversation (Chatbot v5, docs/dev/2026-10-chatbot-v5-spec.md section 3).

One state per conversation that every part of the Chatbot page reads: the coloured edge of an inbox row, the bar
above the chat, the switch on the Channels tab and the counts on the tabs. The browser never works it out on its own,
so two places on the screen can never disagree about the same chat.

    who     colour   meaning
    you     yellow   "Needs you": a customer waits with nobody on it, someone called the A.I. in a chat the owner has
                     not allowed yet, or the A.I. wrote a draft that waits for approval
    ai      violet   "A.I. is handling it"
    owner   blue     "You are handling it" (the owner took the chat over, the customer is not waiting)
    log     grey     "Only logged": the A.I. does not answer here (not allowed, no bot, bot off) and nobody waits

`who_code` names the exact case so the screen can say one sentence about it.

Pure functions: the caller passes the bot record, whether the bot is running, the approval queue and whether the
customer waits (the inbox's existing "need reply" rule, `conversations.can_tra_loi`).
"""
from __future__ import annotations

from typing import Iterable, Optional

import chatbot_store

WHO = ("you", "ai", "owner", "log")


def raw_account(conv: dict) -> str:
    """The raw channel account id of a conversation row ("zalo_personal:zalo-1" -> "zalo-1")."""
    key = str((conv or {}).get("channel_account_id") or "")
    return key.split(":", 1)[1] if ":" in key else key


def state(conv: dict, bot: Optional[dict], running: bool, pending: Optional[dict] = None, waiting: bool = False,
          no_bot_wanted: bool = False) -> dict:
    """`{"who", "who_code", "ai_allowed", "pending", "draft"}` for one conversation row.

    `bot`: the record of the bot on duty in this chat (None when the chat has no bot). `running`: that bot is running.
    `pending`: {chat id: times someone called the bot there} from the bot's approval queue (only real calls count, a
    group the bot merely saw is not one). `waiting`: the customer is waiting for an answer.
    `no_bot_wanted`: the owner marked this channel account "No bot needed" (Channels tab)."""
    c = conv or {}
    chat_id = str(c.get("external_chat_id") or "")
    mode = str(c.get("mode") or "ai")
    meta = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
    draft = meta.get("draft") if isinstance(meta.get("draft"), dict) and str(meta["draft"].get("text") or "").strip() else None
    pending = int((pending or {}).get(chat_id) or 0)
    allowed = bool(bot) and chatbot_store.chat_allowed(bot, str(c.get("chat_type") or "private"), chat_id, raw_account(c))
    out = {"ai_allowed": allowed, "pending": pending, "draft": draft}
    if pending and not allowed:
        return dict(out, who="you", who_code="pending")
    if draft:
        # A reply the A.I. wrote waits for the owner, whatever the mode (drafts mode, or the owner's "A.I. reply").
        return dict(out, who="you", who_code="draft_ready")
    if not allowed:
        if waiting:
            return dict(out, who="you", who_code="waiting")
        return dict(out, who="log", who_code="not_allowed" if bot else ("no_bot_wanted" if no_bot_wanted else "no_bot"))
    if mode == "human":
        return dict(out, who="you", who_code="waiting_you") if waiting else dict(out, who="owner", who_code="you")
    if mode == "draft":
        return dict(out, who="ai", who_code="draft_mode")
    if not running:
        return dict(out, who="you", who_code="bot_off_waiting") if waiting else dict(out, who="log", who_code="bot_off")
    return dict(out, who="ai", who_code="ai")


def count(states: Iterable[dict]) -> dict:
    """How many conversations each `who` holds, for the quick filters and the tab badge."""
    out = {w: 0 for w in WHO}
    for s in states:
        w = (s or {}).get("who")
        if w in out:
            out[w] += 1
    return out
