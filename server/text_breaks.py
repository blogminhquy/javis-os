"""A paragraph break where a model's text picks up again after a tool call (2026-11-16).

Owner report, 16/11/2026: Claude Code's notes between tool calls reached the chat glued together ("... cần đăng
nhập.Xong mục 3", "... bộ nhớ Hồng Ngọc.Now the CEO ..."). Every engine sends the text written before a tool call and
the text written after it as separate pieces, and the chat adds the pieces up as they come. Codex already put a line
break between its messages; Claude Code, Grok Build and Antigravity did not.

`lead` is the one rule all of them use: a new stretch of text starts on a new paragraph, unless the break is already
there. It never touches the model's own words, only what goes between them.
"""
from __future__ import annotations

BREAK = "\n\n"


def _newlines_at_end(text: str) -> int:
    body = text.rstrip(" \t")
    return len(body) - len(body.rstrip("\n"))


def _newlines_at_start(text: str) -> int:
    body = text.lstrip(" \t")
    return len(body) - len(body.lstrip("\n"))


def lead(shown: str, piece: str) -> str:
    """What to put in front of `piece`, a new stretch of text, when the turn has shown `shown` so far.

    Only the end of `shown` matters, so a caller may pass just its last few characters. "" before the first text of a
    turn, for an empty piece, and when the two already meet at a blank line."""
    if not shown or not piece or not shown.strip(" \t"):
        return ""
    have = _newlines_at_end(shown) + _newlines_at_start(piece)
    return "\n" * max(0, len(BREAK) - have)


class Joiner:
    """One turn's text as it reaches the chat: remembers how it ends and whether a tool call came since."""

    def __init__(self):
        self.tail = ""
        self.gap = False

    def tool(self) -> None:
        """A tool call (or anything else that is not text) came between two stretches of text."""
        if self.tail:
            self.gap = True

    def text(self, piece: str) -> str:
        """`piece` as it should be shown: with a break in front when it starts a new stretch after a tool call."""
        if not piece:
            return piece
        before = lead(self.tail, piece) if self.gap else ""
        self.gap = False
        self.tail = (self.tail + before + piece)[-4:]
        return before + piece


def break_after_tool(pieces: list, start: int) -> None:
    """For the Grok Build and Antigravity readers, which collect text into a list of pieces: when a tool call came
    before the pieces added from `start` on, put the break in front of the first of them (in the list itself, so the
    live preview and the final text agree)."""
    if start <= 0 or start >= len(pieces):
        return
    first = next((p for p in pieces[start:] if p), "")
    br = lead("".join(pieces[max(0, start - 4):start])[-4:], first)
    if br:
        pieces.insert(start, br)
