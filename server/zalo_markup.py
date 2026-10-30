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


# ---- Markdown -> Zalo text styles (0.413.0) ------------------------------------------------------------------------
# Zalo draws bold, italic, underline, strikethrough, four colours and two sizes when a message carries `styles`
# (`[{start, len, st}]`, zca-js TextStyle), but shows Markdown symbols as typed. A bot reply written in Markdown
# ("**85.000đ**") reached customers with the stars (owner, 30/10/2026: Hermes sent coloured, formatted messages and
# customers could not tell a bot from a person). `to_zalo` turns the reply into the plain text Zalo shows plus the
# styles to send with it. Positions count UTF-16 units like JavaScript: an emoji is 2.
#
# Besides Markdown, `{red:...}`, `{orange:...}`, `{yellow:...}`, `{green:...}`, `{big:...}` and `{small:...}` colour
# or resize a span, the same syntax as `javis-zalo msg send --md`. Names are those of `javis-zalo msg send --style`.
STYLE_NAMES = ("bold", "italic", "underline", "strikethrough", "red", "orange", "yellow", "green", "big", "small")
MAX_STYLES = 60

_INLINE = re.compile(
    r"\{(?P<cname>red|orange|yellow|green|big|small):(?P<cbody>[^{}\n]+?)\}"
    r"|\*\*(?P<b1>(?!\s).+?(?<!\s))\*\*"
    r"|__(?P<b2>(?!\s)[^_\n]+?(?<!\s))__"
    r"|~~(?P<s>(?!\s).+?(?<!\s))~~"
    r"|(?<![\w*])\*(?P<i1>(?!\s)[^*\n]+?(?<!\s))\*(?![\w*])"
    r"|(?<![\w_])_(?P<i2>(?!\s)[^_\n]+?(?<!\s))_(?![\w_])"
    r"|`(?P<code>[^`\n]+)`"
    r"|\[(?P<ltext>[^\]\n]+)\]\((?P<lurl>https?://[^)\s]+)\)")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+(?=\S)")
_FENCE = re.compile(r"^\s*```")
_STRAY = re.compile(r"\*\*|~~")


def _u16(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def _inline(text: str, base: int, out: list, styles: list) -> int:
    """Append the plain form of one line to `out`; styles get absolute UTF-16 positions from `base`. Returns the new
    position."""
    pos = base
    last = 0
    for m in _INLINE.finditer(text):
        lead = text[last:m.start()]
        out.append(lead)
        pos += _u16(lead)
        last = m.end()
        g = m.groupdict()
        if g["lurl"]:
            s = f"{g['ltext']} ({g['lurl']})"
            out.append(s)
            pos += _u16(s)
            continue
        if g["code"] is not None:
            out.append(g["code"])
            pos += _u16(g["code"])
            continue
        name, body = ((g["cname"], g["cbody"]) if g["cname"] else
                      ("bold", g["b1"] or g["b2"]) if (g["b1"] or g["b2"]) else
                      ("strikethrough", g["s"]) if g["s"] else ("italic", g["i1"] or g["i2"]))
        start = pos
        pos = _inline(body, pos, out, styles)      # styles nest: **{red:Giảm 50%}**
        if pos > start:
            styles.append((start, pos - start, name))
    tail = text[last:]
    out.append(tail)
    return pos + _u16(tail)


def to_zalo(text: str) -> tuple:
    """`(plain text, [(start, length, style name), ...])` for a Markdown reply. Text without Markdown comes back as is
    with no styles. Headings become a bold line, `- item` becomes `• item`, links become "text (url)", code fences and
    backticks are dropped; a `**` or `~~` left without its pair (a long reply cut in two) is removed."""
    s = str(text or "")
    if not any(c in s for c in "*_~`#[{-+"):
        return s, []
    out: list = []
    styles: list = []
    pos = 0
    lines = s.split("\n")
    for i, line in enumerate(lines):
        if _FENCE.match(line):
            line = ""
        h = _HEADING.match(line)
        if h:
            start = pos
            pos = _inline(h.group(1), pos, out, styles)
            if pos > start:
                styles.append((start, pos - start, "bold"))
        else:
            b = _BULLET.match(line)
            if b:
                lead = b.group(1) + "• "
                out.append(lead)
                pos += _u16(lead)
                line = line[b.end():]
            pos = _inline(line, pos, out, styles)
        if i < len(lines) - 1:
            out.append("\n")
            pos += 1
    plain = "".join(out)
    if _STRAY.search(plain):
        plain, styles = _drop_stray(plain, styles)
    styles.sort()
    return plain, styles[:MAX_STYLES]


def _drop_stray(plain: str, styles: list) -> tuple:
    """Remove unpaired `**`/`~~` from the converted text and move the styles that sit after or around them."""
    cuts = []                       # (UTF-16 position in `plain`, UTF-16 length removed)
    for m in _STRAY.finditer(plain):
        cuts.append((_u16(plain[:m.start()]), 2))

    def moved(p: int) -> int:
        return p - sum(n for at, n in cuts if at < p)

    fixed = []
    for start, ln, name in styles:
        a, b = moved(start), moved(start + ln)
        if b > a:
            fixed.append((a, b - a, name))
    return _STRAY.sub("", plain), fixed


def plain_text(text: str) -> str:
    """What Zalo shows for `text` once it went out through `to_zalo`."""
    return to_zalo(text)[0]
