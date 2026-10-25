"""Zalo's tag markup must never reach a chat as text.

Zalo writes a tag as `<a_mention href="zm://Profile/110413987_mention">@Minh</a_mention>`. Zalo on a computer hides
that markup, Zalo on a phone shows it as code. A model copies it from the messages it reads, sometimes whole and
sometimes broken (field report 2026-10-25: `@Hotline Gsmsuppliershref="zm://Profile/102631062_mention">@Trinh
Tran</a_mention>` on a phone). Only the "@Name" part is kept; the real tag is added by the send path (`--mention`).

Kept free of other imports so the MCP pool can call it on every Zalo send without loading the channel module.
"""
from __future__ import annotations

import re

# `</a_mention>` directly followed by another tag: two names would end up glued ("@A@B").
_ADJACENT = re.compile(r"</a_mention\s*>\s*(?=<a_mention\b)", re.IGNORECASE)
_OPEN = re.compile(r"<a_mention\b[^>]*>", re.IGNORECASE)
_CLOSE = re.compile(r"</a_mention\s*>", re.IGNORECASE)
# What is left when the start of an opening tag was lost: `href="zm://Profile/..._mention">`, often glued to the
# previous name. `zm://` keeps it specific to Zalo's own links.
_ORPHAN_HREF = re.compile(r"""\s*href\s*=\s*["']zm://[^"'>]*["']\s*>""", re.IGNORECASE)
# Tags cut off before their ">" (the "@Name" that follows stays).
_CUT = re.compile(r"</?a_mention\b[^>@]*", re.IGNORECASE)

# MCP tools that send text into a Zalo chat, and the argument keys that carry that text.
SEND_TOOLS = ("zalo_send_message", "zalo_send_mention")
TEXT_KEYS = ("text", "message", "content", "caption")


def _space_if_glued(m: "re.Match") -> str:
    s = m.string
    before = s[m.start() - 1] if m.start() > 0 else ""
    after = s[m.end()] if m.end() < len(s) else ""
    return " " if before and not before.isspace() and after and not after.isspace() else ""


def strip_mention_markup(text: str) -> str:
    """`text` without Zalo's tag markup, whole or broken; the "@Name" between the tags stays."""
    s = str(text or "")
    low = s.lower()
    if "a_mention" not in low and "zm://" not in low:
        return s
    s = _ADJACENT.sub("</a_mention> ", s)
    s = _OPEN.sub("", s)
    s = _CLOSE.sub("", s)
    s = _ORPHAN_HREF.sub(_space_if_glued, s)
    return _CUT.sub("", s)


def clean_send_args(tool: str, args):
    """Arguments of a Zalo send tool with the markup removed from the text; anything else is returned as is."""
    if not isinstance(args, dict) or str(tool or "") not in SEND_TOOLS:
        return args
    out = dict(args)
    for k in TEXT_KEYS:
        if isinstance(out.get(k), str):
            out[k] = strip_mention_markup(out[k])
    return out
