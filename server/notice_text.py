"""Readable notices: a short headline and one summary line for every bell item (owner, 2026-11-19).

Why this file exists
====================
The owner compared Javis's bell with the activity cards of another assistant: "theirs are short and easy to read,
ours are hard to read and people skip them". Two causes, both fixed here:

1. The bell took the FIRST line of a background run as its title. A model that works with tools often opens with a
   line about what it is about to do ("Em kiểm tra hướng dẫn và lượt nhắc đến hạn, rồi đối chiếu..."), so the card
   said what Javis was going to do, never what it found. `headline` skips those lines.
2. Nobody wrote a headline at all. A background run can now end with one hidden block,
   `<!-- JAVIS_NOTIFY: {"title": "...", "line": "...", "act": true} -->`, written by the model that did the work and
   knows what matters. `split_block` takes it out of the text (channels never show it) and the bell uses it.
   `act` is the model saying the owner has to do or decide something; only then does a scheduled run ring, and only
   with a `why` from URGENT_WHY (push_policy.act_check, 2026-11-23). `line` is the owner's next step, or empty.

Pure functions, no I/O: reminders.py, tasks.py and main.py call them.
"""
from __future__ import annotations

import json
import re

TITLE_MAX = 90
LINE_MAX = 160
# The reasons an "act" (urgent) claim may give (owner, 2026-11-23); any other claim is lowered to important.
URGENT_WHY = ("error", "money", "customer", "question", "deadline")

_BLOCK_RE = re.compile(r"<!--\s*JAVIS_NOTIFY\s*:\s*(\{.*?\})\s*-->", re.S)

# The instruction a background run gets (English, one copy for every language: the model writes the title and line in
# the language of the job). Kept short: it rides on every scheduled run.
PROMPT = (
    "At the very end of your answer add one hidden line for the owner's notification bell, exactly like this:\n"
    '<!-- JAVIS_NOTIFY: {"title": "...", "line": "...", "act": false, "why": ""} -->\n'
    "- title: at most 8 words, the RESULT with its key number, in the job's language "
    "(\"Order #1234 cancelled, 1.2M lost\"), never what you were going to do (\"Checking the list...\").\n"
    "- line: the one thing the owner should do now, at most 10 words (\"Call the customer back before 5 pm\"), "
    "or \"\" when there is nothing to do.\n"
    "- act: true ONLY when the owner must act now; then why is one of error, money, customer, question, deadline. "
    "Routine runs are false. A run that claims act on most runs loses it."
)

# Lines that narrate the work instead of reporting it. Vietnamese: a first person subject, then an optional
# "will / is / let me", then a working verb, with no "đã" (done) in between. English: the usual openers.
_NARRATION = re.compile(
    r"^(?:"
    r"(?:để|bây giờ|giờ|trước tiên|đầu tiên)?\s*(?:em|mình|tôi|tớ|javis)\s+"
    r"(?:sẽ|đang|xin phép|tiếp tục|cần|bắt đầu|thử)?\s*"
    r"(?:kiểm tra|kiểm|xem|xem lại|đọc|rà|rà soát|tìm|tra|tra cứu|đối chiếu|mở|lấy|soát|chạy|gọi|tải|"
    r"truy vấn|nạp|quét|liệt kê|lọc|so sánh|tổng hợp|phân tích|bắt đầu|tiến hành|thử)\b"
    r"|(?:i'll|i will|i'm going to|i am going to|let me|now i'll|first,? i'll|i'm checking|i am checking|"
    r"checking|looking|reading|fetching|loading)\b"
    r")",
    re.I,
)
_MARKUP = re.compile(r"\*\*|__|`")
# A markdown link or image, `[words](url)` / `![alt](url)`: a card line and the phone's lock screen show its words only.
# Owner, 22/11/2026: a reminder's "... là [Javis OS K8 Buổi 2](https://www.google.com/calendar/event?eid=...)" put the
# raw link in the bell card, and the unbroken URL ran past the card's edge.
_MD_LINK = re.compile(r"!?\[([^\]\n]+)\]\([^)\s]*\)")


def plain_links(s) -> str:
    """`[words](url)` -> `words` (images keep their alt text); other brackets stay."""
    return _MD_LINK.sub(r"\1", str(s or ""))
_LEAD = "#*->•⚠✅⏰ \t"


def split_block(text: str) -> tuple:
    """(text without the JAVIS_NOTIFY block, {"title", "line", "act"} or {}). A broken block is removed and ignored:
    it must never swallow the answer, nor show up raw in a chat."""
    raw = str(text or "")
    meta: dict = {}
    m = None
    for m in _BLOCK_RE.finditer(raw):
        pass
    if m is not None:
        try:
            d = json.loads(m.group(1))
        except ValueError:
            d = None
        if isinstance(d, dict):
            title = clean_line(d.get("title"))[:TITLE_MAX]
            line = clean_line(d.get("line"))[:LINE_MAX]
            act = d.get("act")
            why = str(d.get("why") or "").strip().lower()
            meta = {"title": title, "line": line,
                    "act": act is True or str(act).strip().lower() in ("true", "1", "yes"),
                    "why": why if why in URGENT_WHY else ""}
    cleaned = _BLOCK_RE.sub("", raw)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, meta


def clean_line(s) -> str:
    """One line for a card: markdown marks and leading bullets or status emoji removed, spaces collapsed."""
    s = plain_links(_MARKUP.sub("", str(s or ""))).strip().lstrip(_LEAD).strip()
    return " ".join(s.split())


def is_narration(line: str) -> bool:
    """True for a line that says what Javis is about to do rather than what it found."""
    return bool(_NARRATION.match(clean_line(line)))


def _lines(text: str):
    for raw in str(text or "").splitlines():
        s = clean_line(raw)
        if s and not s.startswith("<!--") and not s.startswith("[🔊"):
            yield s


def headline(text: str, fallback: str = "") -> str:
    """The first line of `text` that reports something. Only narration (or nothing) -> `fallback`."""
    for s in _lines(text):
        if not is_narration(s):
            return s[:TITLE_MAX]
    return str(fallback or "")[:TITLE_MAX]


def summary(text: str, title: str = "") -> str:
    """One line under the title: the next reporting line of `text` that is not the title itself, or ""."""
    t = clean_line(title).lower()
    for s in _lines(text):
        if is_narration(s):
            continue
        if t and (s.lower() == t or s.lower().startswith(t) or t.startswith(s.lower())):
            continue
        return s[:LINE_MAX]
    return ""


def short_name(label: str, limit: int = 48) -> str:
    """A job's name for a headline: its label, or the start of its prompt cut at a word."""
    s = clean_line(str(label or "").splitlines()[0] if label else "")
    if len(s) <= limit:
        return s
    cut = s[:limit].rsplit(" ", 1)[0].rstrip(",.;:")
    return (cut or s[:limit]) + "…"
