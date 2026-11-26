"""A bot answer sent as several short chat messages instead of one long block (0.281.0).

Owner request 2026-10-22: "khi nhắn tin bot có thể quyết định nhắn nhiều tin ngắn cho khách chứ không gom vào 1 tin dài
rất khó đọc, phần này bot tự quyết định được". The Agent decides: it writes a line holding only `SPLIT_MARK` between the
messages, the channel sends each part as its own message. Javis never splits on its own (a blank line inside one
message is normal writing), it only honours the marker.

Which channels send parts separately is the capability table `CHANNELS` (issue #1833: personal Zalo was the only
one, so Messenger, Zalo OA and Telegram customers got one long block). Everywhere else (and in the inbox, the bot log,
a draft for the owner, a public comment thread) the marker becomes a blank line, so it can never reach a customer as
text. The same table gates the prompt hint (`chatbot_runtime.build_bot_prompt`) and the join step of a turn
(`chatbot_runtime._make_answer_fn`), so the two can never disagree.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List

SPLIT_MARK = "[TACH_TIN]"
MAX_PARTS = 4                  # more than this reads like spam: the rest is joined into the last message
PART_PAUSE_S = 1.2             # seconds between two parts, so they arrive in order and read like a person typing
_MARK_RE = re.compile(r"\s*\[\s*tach_tin\s*\]\s*", re.I)


@dataclass(frozen=True)
class ChannelCaps:
    """What one channel's transport does with a bot answer.

    `split`: sends each part of an answer as its own message. `max_len`: the longest text one message carries; the
    transport cuts a longer part at a paragraph, line or space (each transport reads its limit from here). `markup`:
    how formatting shows: "zalo" (bold, italic, colour), "markdown" (Telegram MarkdownV2), "plain" (marks removed)."""
    split: bool
    max_len: int
    markup: str


CHANNELS: Dict[str, ChannelCaps] = {
    # 1500 leaves room for the "@Name" of a group tag; Zalo refuses a text near 2000 characters.
    "zalo_personal": ChannelCaps(True, 1500, "zalo"),
    "zalo_oa": ChannelCaps(True, 1900, "plain"),         # Zalo allows 2000 per text
    "messenger": ChannelCaps(True, 1900, "plain"),       # Messenger allows 2000, margin for multi-byte counting
    "telegram": ChannelCaps(True, 3500, "markdown"),     # 4096 minus room for MarkdownV2 escapes
}
# Public comment threads (Facebook `cmt:`, Instagram `igc:`, see messenger_bot): one answer is one reply under one
# comment, never a row of replies.
COMMENT_PREFIXES = ("cmt:", "igc:")
# Kept for callers from before the table: the channels that split at all.
SPLIT_CHANNELS = tuple(k for k, v in CHANNELS.items() if v.split)


def splits(channel: Any, chat_id: Any = "") -> bool:
    """Whether an answer on this channel, in this chat, goes out as several messages."""
    caps = CHANNELS.get(str(channel or ""))
    return bool(caps and caps.split) and not str(chat_id or "").startswith(COMMENT_PREFIXES)

PROMPT_HINT = f"""
## Nhắn nhiều tin ngắn

Khách đọc trên điện thoại. Khi câu trả lời có từ hai ý trở lên (ví dụ báo giá rồi gợi ý thêm), bạn được
tách thành nhiều tin ngắn như người thật nhắn: đặt một dòng chỉ có `{SPLIT_MARK}` giữa các tin, tối đa
{MAX_PARTS} tin. Mỗi tin một ý, vài câu. Câu trả lời chỉ có một ý thì gửi một tin, không cần tách.
"""


def has_mark(text: Any) -> bool:
    return bool(_MARK_RE.search(str(text or "")))


def parts(text: Any, max_parts: int = MAX_PARTS) -> List[str]:
    """The messages of one answer, empty parts dropped, at most `max_parts` (the overflow joins the last one)."""
    ds = [p.strip() for p in _MARK_RE.split(str(text or ""))]
    ds = [p for p in ds if p]
    if len(ds) > max_parts:
        ds = ds[:max_parts - 1] + ["\n\n".join(ds[max_parts - 1:])]
    return ds


def joined(text: Any) -> str:
    """The answer as ONE message: each marker becomes a blank line. For channels and records that do not split."""
    if not has_mark(text):
        return str(text or "")
    return "\n\n".join(parts(text, max_parts=10 ** 6))


def outgoing(text: Any, split: bool = True) -> List[str]:
    """The messages a bot transport sends for one answer: one per part when `split`, else ONE message with each marker
    turned into a blank line (a public comment thread). Either way no marker reaches a customer as text."""
    t = str(text or "")
    if not has_mark(t):
        return [t]
    return (parts(t) or [""]) if split else [joined(t)]
