"""Zalo voice reminders: a reminder that tags the owner by name, "rings" them and speaks the note.

The owner (2026-11-16): when I book something by Zalo, tag my name at that time, make a virtual call with a
voice message saying what it is, repeat it as often as I asked, and learn how I write Vietnamese so you do not
misread my slips. Names: the one a person set FOR THEMSELVES on Zalo is the official one, never the nickname
(alias) the owner saved for them.

What this module owns (no network, no engine, so it is testable on its own):

* `canonical_name`  - which of Zalo's several names to use.
* the Vietnamese lexicon - built-in chat shorthand ("ko", "dc", "7h", "a Thế") plus what the owner taught,
  kept in the brain, so a voice note says "không" and not "ka-o".
* `repeat_preset`   - "nhẹ / vừa / gắt" turned into a repeat interval and a number of runs.
* `deliver`         - one firing: ring line (tag), voice note, written line. The senders are injected.

A real Zalo voice call is NOT possible: the unofficial Zalo API behind javis-zalo has no call tool. The
"virtual call" is a tagged ring message plus a spoken note, which still makes the phone buzz and say who is
calling. When javis-zalo gains a call tool, only `deliver` changes.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

LEXICON_FILE = Path("Javis") / "zalo_vi_lexicon.json"
MEMORY_FACT = Path("memory") / "facts" / "vi-speech-lexicon.md"
MEMORY_INDEX = Path("memory") / "MEMORY.md"
MAX_ENTRIES = 300
MAX_TOKEN = 40
MAX_NAME = 80

# Zalo names, most to least trusted. `zaloName` is what the person typed into their own profile; `displayName`
# is the same on every account we saw. `alias` is the nickname the VIEWER saved, so it is never the official one.
_SELF_SET_KEYS = ("zaloName", "zalo_name", "displayName", "display_name")
_ALIAS_KEYS = ("alias", "nickname", "contactName", "contact_name")


def _clean(s: Any, cap: int = MAX_NAME) -> str:
    return " ".join(str(s or "").split())[:cap]


def canonical_name(info: Any) -> str:
    """The name to use for a person: the one they set for themselves. The owner's own nickname for them
    (`alias`) only when nothing else exists, so a tag never stays empty."""
    d = info if isinstance(info, dict) else {}
    for k in _SELF_SET_KEYS:
        v = _clean(d.get(k))
        if v:
            return v
    for k in _ALIAS_KEYS:
        v = _clean(d.get(k))
        if v:
            return v
    return ""


# ── Vietnamese lexicon ────────────────────────────────────────────────────────────────────────────
# Shorthand people really type. Kept small and safe: each entry is a whole token that is never a normal word.
BUILTIN: Dict[str, str] = {
    "ko": "không", "hok": "không", "khum": "không", "hong": "không", "hông": "không",
    "dc": "được", "đc": "được", "dk": "được", "đk": "được",
    "j": "gì", "vs": "với", "mk": "mình", "ngta": "người ta", "bik": "biết", "ntn": "như thế nào",
    "bn": "bao nhiêu", "ae": "anh em", "trc": "trước", "tks": "cảm ơn", "thks": "cảm ơn",
    "nhe": "nhé", "zậy": "vậy", "zui": "vui", "zô": "vào", "mn": "mọi người", "đt": "điện thoại",
    "sdt": "số điện thoại", "cty": "công ty",
}

_VI_CHAR = re.compile(r"[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹáàãéèíìóòõúùýÁÀÃÉÈÍÌÓÒÕÚÙÝ]")
# "a Thế", "c Lan", "e Nam": one-letter pronoun in front of a capitalised name.
_PRONOUN = re.compile(r"(?<![\w@])([aceACE])(?=\s+[A-ZĐÀÁẢÃẠĂÂÈÉẺẼẸÊÌÍỈĨỊÒÓỎÕỌÔƠÙÚỦŨỤƯỲÝỶỸỴ][\wÀ-ỹ]*)")
_PRON_WORD = {"a": "anh", "c": "chị", "e": "em"}
_CLOCK = re.compile(r"\b(\d{1,2})\s?h(?:(\d{1,2})\b)?(?![\wÀ-ỹ])")


def _lex_path(root: str) -> Path:
    return Path(root) / LEXICON_FILE


def load(root: str) -> Dict[str, dict]:
    """The learned entries `{wrong: {right, count, updated}}`, {} when none or unreadable."""
    if not root:
        return {}
    try:
        d = json.loads(_lex_path(root).read_text(encoding="utf-8"))
        e = d.get("entries") if isinstance(d, dict) else None
        return {str(k): v for k, v in e.items() if isinstance(v, dict) and v.get("right")} if isinstance(e, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def learn(root: str, wrong: str, right: str) -> bool:
    """Remember that the owner's `wrong` means `right`. False when either side is unusable or they are the same."""
    w, r = _clean(wrong, MAX_TOKEN).lower(), _clean(right, MAX_TOKEN * 2)
    if not root or not w or not r or w == r.lower() or "\n" in w:
        return False
    entries = load(root)
    if w not in entries and len(entries) >= MAX_ENTRIES:
        return False
    cur = entries.get(w) or {}
    entries[w] = {"right": r, "count": int(cur.get("count") or 0) + 1, "updated": int(time.time())}
    _write_atomic(_lex_path(root), json.dumps({"entries": entries}, ensure_ascii=False, indent=2))
    sync_memory(root, entries)
    return True


def forget(root: str, wrong: str) -> bool:
    entries = load(root)
    if _clean(wrong, MAX_TOKEN).lower() not in entries:
        return False
    entries.pop(_clean(wrong, MAX_TOKEN).lower())
    _write_atomic(_lex_path(root), json.dumps({"entries": entries}, ensure_ascii=False, indent=2))
    sync_memory(root, entries)
    return True


# The owner writes "A" is "B" in quotes to teach a meaning: `"ko" là "không"`, `ý anh là "mai", không phải "may"`.
_TEACH = re.compile(r"[\"“'‘]([^\"”'’\n]{1,40})[\"”'’]\s*(?:là|nghĩa là|tức là|ý là|=|->|→)\s*[\"“'‘]([^\"”'’\n]{1,80})[\"”'’]", re.I)
_TEACH_NOT = re.compile(r"ý\s+(?:anh|tôi|mình)\s+là\s+[\"“'‘]([^\"”'’\n]{1,80})[\"”'’][\s,;]*(?:chứ\s+)?(?:không|chứ không)\s+phải\s+[\"“'‘]([^\"”'’\n]{1,40})[\"”'’]", re.I)


def detect_correction(text: str) -> List[Tuple[str, str]]:
    """`[(wrong, right)]` the owner just taught in one message. Needs quotes, so ordinary speech never teaches by accident."""
    out: List[Tuple[str, str]] = []
    t = str(text or "")
    for m in _TEACH_NOT.finditer(t):
        out.append((m.group(2).strip(), m.group(1).strip()))
    for m in _TEACH.finditer(t):
        pair = (m.group(1).strip(), m.group(2).strip())
        if pair not in out:
            out.append(pair)
    return out


def normalize(text: str, root: str = "") -> str:
    """The owner's text with shorthand spelled out, for the voice and for the written line. Learned entries win over the
    built-in ones. Text with no Vietnamese in it (and no learned hit) is returned as it came."""
    t = str(text or "")
    if not t:
        return t
    table = dict(BUILTIN)
    for k, v in load(root).items():
        table[k] = str(v.get("right") or "")
    viet = bool(_VI_CHAR.search(t)) or any(re.search(rf"(?<![\w]){re.escape(k)}(?![\w])", t, re.I) for k in table)
    if not viet:
        return t

    def word(m: "re.Match") -> str:
        tok = m.group(0)
        return table.get(tok.lower(), tok)

    if table:
        keys = sorted(table, key=len, reverse=True)
        t = re.sub(r"(?<![\w@/.\-])(" + "|".join(re.escape(k) for k in keys) + r")(?![\w])", word, t, flags=re.I)
    t = _PRONOUN.sub(lambda m: _PRON_WORD[m.group(1).lower()], t)
    t = _CLOCK.sub(lambda m: f"{m.group(1)} giờ" + (f" {int(m.group(2))}" if m.group(2) else ""), t)
    return t


def sync_memory(root: str, entries: Optional[Dict[str, dict]] = None) -> None:
    """Mirror the lexicon as a memory fact, so the model reads it with the rest of the brain memory. Best effort."""
    try:
        entries = load(root) if entries is None else entries
        fact = Path(root) / MEMORY_FACT
        idx = Path(root) / MEMORY_INDEX
        line = "- [Cách anh gõ tiếng Việt](facts/vi-speech-lexicon.md) - từ gõ tắt hoặc gõ sai và nghĩa đúng, đọc trước khi hiểu lệnh Zalo"
        if not entries:
            fact.unlink(missing_ok=True)
            if idx.exists():
                keep = [x for x in idx.read_text(encoding="utf-8").splitlines() if "vi-speech-lexicon.md" not in x]
                _write_atomic(idx, "\n".join(keep) + "\n")
            return
        rows = "\n".join(f"- \"{k}\" nghĩa là \"{v['right']}\"" for k, v in sorted(entries.items()))
        body = ("---\ntype: preference\ncreated: " + time.strftime("%Y-%m-%d") + "\nupdated: " + time.strftime("%Y-%m-%d") +
                "\n---\nCách chủ viết tiếng Việt (gõ tắt, gõ sai) và nghĩa đúng. Dùng khi hiểu lệnh, hẹn giờ và tin thoại.\n\n" +
                rows + "\n\n**Vì sao:** chủ dặn Javis học cách chủ nói để không hiểu sai nghĩa.\n"
                "**Áp dụng:** đổi theo bảng này trước khi hiểu câu; chủ chỉnh thêm thì ghi tiếp.\n")
        _write_atomic(fact, body)
        text = idx.read_text(encoding="utf-8") if idx.exists() else ""
        if "vi-speech-lexicon.md" not in text:
            _write_atomic(idx, (text.rstrip("\n") + "\n" if text.strip() else "") + line + "\n")
    except OSError:
        pass


# ── Repetition ────────────────────────────────────────────────────────────────────────────────────
# (repeat every N minutes, number of runs). One run is a plain reminder.
PRESETS: Dict[str, Tuple[int, int]] = {
    "nhe": (0, 1), "light": (0, 1),
    "vua": (10, 3), "medium": (10, 3),
    "gat": (5, 6), "urgent": (5, 6), "khan": (3, 10),
}


def _fold(s: str) -> str:
    import unicodedata
    s = str(s or "").strip().lower().replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def repeat_preset(level: Any) -> Tuple[int, int]:
    """`(repeat_min, max_runs)` for a level word ("nhẹ", "vừa", "gắt", "khẩn", or English). Unknown: one run."""
    return PRESETS.get(_fold(level), (0, 1))


# ── Target and delivery ───────────────────────────────────────────────────────────────────────────
def clean_target(z: Any) -> Optional[dict]:
    """The Zalo target stored on a reminder, or None when it cannot be delivered (no thread id)."""
    if not isinstance(z, dict):
        return None
    thread = re.sub(r"\D", "", str(z.get("thread") or z.get("threadId") or ""))[:25]
    if len(thread) < 3:
        return None
    t = 1 if str(z.get("type") if z.get("type") is not None else z.get("threadType", 0)).strip() in ("1", "group") else 0
    uid = re.sub(r"\D", "", str(z.get("uid") or ""))[:25]
    return {"conn": _clean(z.get("conn") or z.get("connection"), 80), "thread": thread, "type": t, "uid": uid,
            "name": canonical_name(z) or _clean(z.get("name")),
            "voice": z.get("voice") is not False, "ring": z.get("ring") is not False,
            "remind": z.get("remind") is not False}


def spoken_line(name: str, text: str, root: str = "") -> str:
    """What the voice note says: the name first, then the note with shorthand spelled out."""
    body = normalize(text, root).strip().rstrip(".")
    return (f"{name} ơi, " if name else "") + (body[:1].lower() + body[1:] if body else "tới giờ rồi")


def ring_line(name: str, group: bool) -> str:
    """The virtual call line. In a group the name becomes a real Zalo tag (the sender adds `@name`), in a private chat the name is plain text."""
    who = f"@{name}" if (group and name) else name
    return (who + " " if who else "") + "📞 Javis đang gọi, nghe tin thoại bên dưới nhé"


Send = Callable[..., Awaitable[Tuple[bool, str]]]


def reminder_title(text: str, root: str = "") -> str:
    """The title of the reminder that appears in the Zalo chat: the note, spelled out, one line, never starting with a
    dash (the CLI would read it as a flag)."""
    t = " ".join(normalize(text, root).split()).lstrip("-– ")
    return t[:120] or "Nhắc hẹn"


async def deliver(target: dict, text: str, *, send_text: Send, send_voice: Optional[Send] = None,
                  make_voice: Optional[Callable[[str], Awaitable[str]]] = None, root: str = "",
                  send_reminder: Optional[Callable[[str], Awaitable[Tuple[bool, str]]]] = None) -> Tuple[bool, str]:
    """One firing. `send_text(text, mention=None)`, `send_voice(path)`, `make_voice(text) -> path or ""` and
    `send_reminder(title)` (the reminder entry inside the Zalo chat) are injected.

    Order: ring line (tag), voice note, written line, Zalo reminder entry. The ring line and the written line carry
    the message, so a failure of either is a failure; a missing voice note or Zalo reminder only adds a warning,
    the reminder still arrived."""
    tg = clean_target(target)
    if not tg:
        return False, "no Zalo thread to send to"
    group = tg["type"] == 1
    name = tg["name"]
    mention = {"uid": tg["uid"], "name": name} if group and tg["uid"] and name else None
    notes: List[str] = []
    if tg["ring"]:
        ok, err = await send_text(ring_line(name, group), mention)
        if not ok:
            return False, f"ring: {err}"
    if tg["voice"] and make_voice and send_voice:
        path = ""
        line = spoken_line(name, text, root)
        for attempt in range(3):    # the free voice service sometimes answers with no audio; ask again
            try:
                path = await make_voice(line)
                notes = []
            except Exception as e:      # noqa: BLE001 - a voice failure must not lose the reminder
                path, notes = "", [f"voice: {type(e).__name__}: {e}"[:160]]
            if path:
                break
            if attempt < 2:
                await asyncio.sleep(1.5)
        if path:
            vok, verr = await send_voice(path)
            if not vok:
                notes.append(f"voice not sent: {verr}"[:160])
        elif not notes:
            notes.append("voice: no audio")
    ok, err = await send_text("⏰ " + normalize(text, root).strip(), None if tg["ring"] else mention)
    if not ok:
        return False, f"text: {err}"
    if tg["remind"] and send_reminder:
        try:
            rok, rerr = await send_reminder(reminder_title(text, root))
        except Exception as e:      # noqa: BLE001 - the reminder entry is an extra
            rok, rerr = False, f"{type(e).__name__}: {e}"
        if not rok:
            notes.append(f"zalo reminder not created: {rerr}"[:160])
    return True, "; ".join(notes)
