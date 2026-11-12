"""A plan card that lost its sign-in: the text detector and the retry window.

Owner's report, 12/11/2026, with a customer's screenshot: a bot whose agent runs on ChatGPT lost the ChatGPT sign-in at
11:13 and every turn after that failed, while another model was signed in on the same machine. A turn that ran out of
QUOTA already moved to the next account or the next card (spec 6.4, docs/dev/2026-10-model-routing-spec.md); a turn
refused because the plan was signed out did not, on any path.

This module only answers "is this text a sign-in failure". The mark it leads to lives in main.py (`_SIGNED_OUT`,
`_note_signin_lost`) next to the out-of-quota mark, because routing reads both the same way.

Kept free of imports from the app so it can be tested alone, like aux_engine's own pattern list.
"""
import re

# How long a card stays marked signed out before one turn tries it again. A sign-in does not come back by itself, but
# a refused turn is not always a lost sign-in (two processes racing for one refresh token, a short outage of the
# sign-in service), so the mark must lift without the owner. A card that is still signed out refuses before writing a
# word and the turn moves on at once, so trying again costs one quick refusal per window.
RETRY_S = 600.0

# What the plan CLIs and the ChatGPT backend say when the sign-in is gone. Lower case, matched inside one line.
# The first group mirrors connect_health._ENGINE_AUTH_PATTERNS and aux_engine._AUTH_FINAL_PATTERNS (synced by hand:
# those modules must stay importable alone); API-key wording is left out, a key is not a sign-in.
_PATTERNS = (
    "failed to authenticate", "oauth session expired", "oauth token has expired", "please run /login",
    "not logged in", "could not be refreshed", "refresh token was already used", "log out and sign in again",
    # Codex CLI and the ChatGPT backend
    "401 unauthorized", "token_invalidated", "token has been invalidated", "sign in again", "signing in again",
    "refresh token has expired", "refresh token was revoked",
    # Grok Build
    "not authenticated",
    # Antigravity CLI (antigravity_cli._la_loi_chua_dang_nhap; with no session it opens its sign-in menu instead)
    "not signed in", "login required", "unauthenticated", "select login method",
    # Javis's own sentences for a ChatGPT turn with no usable token (engine.py, the bot paths in main.py)
    "chưa đăng nhập được chatgpt", "chưa đăng nhập chatgpt", "not signed in to chatgpt",
)
# The ChatGPT backend's refusal as engine.ev_loi_http writes it: "ChatGPT 401: ...".
_HTTP_401 = re.compile(r"^\W*chatgpt 401\b")
# A line about an MCP server is that server's sign-in, never the plan's: Codex prints the last lines of its log with
# an error, and a connector answering 401 must not send the whole card to rest.
_NOT_THE_PLAN = ("mcp",)

ANSWER_MAX_CHARS = 400      # a sign-in refusal printed as the answer is one short line; a long answer is real content
ERROR_SCAN_CHARS = 2000


def is_signin_error(text, answer: bool = False) -> bool:
    """Whether `text` says the plan's sign-in is gone.

    `answer=False`: the text is an engine's own error (an `error` event, a failed final), so any line of it may say so.
    `answer=True`: the text came out as the model's answer (Claude Code prints "Not logged in · Please run /login" that
    way); it only counts when it is nothing but a short error line, so an answer that quotes these words is left alone.
    """
    raw = str(text or "").strip()
    if not raw:
        return False
    if answer and (len(raw) > ANSWER_MAX_CHARS or raw.count("\n") > 2):
        return False
    for line in raw[:ERROR_SCAN_CHARS].lower().splitlines():
        if any(skip in line for skip in _NOT_THE_PLAN):
            continue
        if _HTTP_401.search(line) or any(p in line for p in _PATTERNS):
            return True
    return False
