"""Distinguish notifying the owner from executing an outbound channel action.

A notify reminder only echoes text to the reminder's chat_id. It must NEVER
pretend that a request inside that text (send to a Zalo group, etc.) executed.
This helper is intentionally conservative: explicit tool calls and clear
outbound channel instructions are routed to the task engine instead.
"""
from __future__ import annotations

import re
import unicodedata


_SEND_TOOL = re.compile(
    r"\b(?:[a-z0-9_-]+__)?(?:zalo_send_message|telegram_send_message|slack_post_message"
    r"|discord_send_message|whatsapp_send_message)\b", re.I
)
_SEND_AND_CHANNEL = re.compile(
    r"\b(?:gui|nhan|send|post|dang)\b.{0,180}"
    r"\b(?:nhom|group|kenh|channel|zalo|telegram|slack|discord|whatsapp|facebook)\b",
    re.S
)
_ONLY_REMIND_OWNER = re.compile(
    r"^\s*(?:nhac\s+(?:toi|minh|anh|chi|em)|remind\s+me)\b"
)


def outbound_action_requested(text: str) -> bool:
    """True when a scheduled prompt instructs Javis to send outside the owner chat.

    No automatic privilege escalation: callers must reject notify-mode jobs,
    not silently convert them to full-access tasks.
    """
    s = str(text or "")
    if _SEND_TOOL.search(s):
        return True
    folded = unicodedata.normalize("NFD", s.lower().replace("đ", "d"))
    folded = "".join(c for c in folded if unicodedata.category(c) != "Mn")
    if _ONLY_REMIND_OWNER.search(folded):
        return False
    return bool(_SEND_AND_CHANNEL.search(folded))
