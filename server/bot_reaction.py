"""Emoji reactions on personal Zalo (0.334.0): read the ones customers put on messages, and let the bot put one.

Owner request 2026-10-26: "khách hàng đọc được emoji reaction trên zalo và javis thả được reaction vào". Decided the
same day: whether a reaction alone deserves an answer is learned by the judge, never hard-coded ("phần này tự học trong
bộ phán xử, đừng fix cứng"), and the bot reacts on the judge's say too ("bot được tự thả dựa theo bộ phán xử luôn").

javis-zalo 1.7.0 puts each reaction in the live feed as an entry of type "reaction" pointing at the message it was put
on, and adds the tool `zalo_add_reaction`. Here:
  - `describe` turns a reaction into the line the inbox, the judge and the Agent read;
  - `pick` takes the bot's own `[CAM_XUC:<name>]` marker out of an answer (Agent turns, private chats included);
  - `NAMES` is the one list both the judge and the Agent choose from.

Javis never decides on its own to answer or to react: the judge (group chats in "Tự đánh giá") or the Agent does.
"""
from __future__ import annotations

import re
from typing import Any, Optional, Tuple

import localefmt

MARK = "[CAM_XUC:<tên>]"
# Same names as javis-zalo `REACTIONS` (src/mcp/reactions.js). The first six are Zalo's quick row; the bot is offered
# only these, so it never picks an odd one. Any name javis-zalo knows is still shown when a customer uses it.
EMOJI = {
    "heart": "❤️", "like": "👍", "haha": "😆", "wow": "😮", "cry": "😭", "angry": "😡",
    "kiss": "😘", "tears_of_joy": "😂", "rose": "🌹", "broken_heart": "💔", "dislike": "👎", "love": "😍",
    "confused": "😕", "wink": "😉", "ok": "👌", "peace": "✌️", "thanks": "🙏", "pray": "🙏", "handclap": "👏",
    "sad": "😞", "big_laugh": "😄", "cool": "😎",
}
NAMES = ("heart", "like", "haha", "wow", "cry", "angry")
CHANNELS = ("zalo_personal",)       # channels whose transport can put a reaction (`channels.zalo_personal.Transport._tha`)
QUOTE_MAX = 80
_MARK_RE = re.compile(r"\[\s*cam_xuc\s*:\s*([a-z_]*)\s*\]", re.I)

PROMPT_HINT = f"""
## Thả cảm xúc vào tin khách

Bạn được thả một cảm xúc lên tin khách vừa nhắn, như người thật bấm giữ tin trên Zalo: thêm một dòng
`[CAM_XUC:<tên>]`, tên là một trong {", ".join(NAMES)}. Có thể vừa thả vừa trả lời, hoặc chỉ thả mà
không nhắn gì (viết đúng dòng đó và không viết gì khác). Tự cân nhắc theo hướng dẫn vai: đừng thả cho
mọi tin. Tin dạng "[... thả cảm xúc ...]" là khách thả cảm xúc lên một tin, không phải lời khách viết.
"""


def emoji_of(name: Any) -> str:
    return EMOJI.get(str(name or "").strip().lower(), "")


def pick(text: Any) -> Tuple[str, Optional[str]]:
    """(answer without the marker, the reaction name or None). Every marker is removed so none reaches a customer;
    the first one naming a reaction the bot may use wins."""
    s = str(text or "")
    chosen = None
    for m in _MARK_RE.finditer(s):
        name = m.group(1).lower()
        if chosen is None and name in NAMES:
            chosen = name
    if chosen is None and not _MARK_RE.search(s):
        return s, None
    clean = _MARK_RE.sub("", s)
    clean = re.sub(r"[ \t]+\n", "\n", clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    return clean, chosen


def _quote(text: Any) -> str:
    t = " ".join(str(text or "").split())
    return t if len(t) <= QUOTE_MAX else t[:QUOTE_MAX - 1].rstrip() + "…"


def describe(who: str, reaction: dict) -> str:
    """The line for one reaction, e.g. `[Lan thả cảm xúc ❤️ vào tin bên mình gửi: "Dạ giá 500k ạ"]`.

    Written for the inbox, the judge and the Agent alike, so it never names the bot (a name in it would read as the
    customer calling the bot). `reaction`: {emoji, name, removed, target_text, target_side} where target_side is
    "ours" (sent by this account: the bot or the owner), "self" (the reactor's own message), or a member's name."""
    r = reaction or {}
    who = str(who or "").strip() or localefmt.chu("Khách", "The customer")
    emoji = str(r.get("emoji") or "") or emoji_of(r.get("name")) or str(r.get("code") or "")
    if r.get("removed"):
        return localefmt.chu(f"[{who} bỏ cảm xúc {emoji}]", f"[{who} removed the reaction {emoji}]")
    quote = _quote(r.get("target_text"))
    side = str(r.get("target_side") or "")
    if not quote:
        return localefmt.chu(f"[{who} thả cảm xúc {emoji} vào một tin nhắn]", f"[{who} reacted {emoji} to a message]")
    if side == "ours":
        return localefmt.chu(f'[{who} thả cảm xúc {emoji} vào tin bên mình gửi: "{quote}"]',
                             f'[{who} reacted {emoji} to our message: "{quote}"]')
    if side and side != "self":
        return localefmt.chu(f'[{who} thả cảm xúc {emoji} vào tin của {side}: "{quote}"]',
                             f'[{who} reacted {emoji} to {side}\'s message: "{quote}"]')
    return localefmt.chu(f'[{who} thả cảm xúc {emoji} vào tin: "{quote}"]', f'[{who} reacted {emoji} to: "{quote}"]')
