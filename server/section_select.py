"""Load only the parts of a long skill that the current task needs, chosen by Javis before loading (2026-11-18).

Owner, 18/11/2026: worried that cutting what a model gets "mà không có cơ chế nào đó tìm thông tin nạp thông minh trước
khi nạp" would hurt answers. So the choice is made here, by Javis, before anything is loaded, and every doubt resolves
to loading everything, exactly as before:

0. Only skills built as a menu of alternatives, where one request needs one part (javis-builder: agent OR loop OR
   plugin...). A skill that is one procedure needs all of its parts for a general request: tried on seo-audit, a plain
   "audit my SEO" picked "On-Page" and left out crawlability, indexation and speed. So a skill is split only when it is
   on `MENU_SKILLS`, carries `sections: select` in its frontmatter, or is listed by the owner in settings
   (`context_runtime.skill_sections.skills`). Every other skill loads whole, as before.
1. Javis scores each section against the task (the request of this turn, plus what the model says it needs) with the
   same accent-free word matching Javis uses for memory: words in a section's heading weigh most, rare words more than
   common ones. Nothing is left out unless a word of the task is in the best section's own heading.
2. Sections that state rules are always loaded: the opening text, and every top-level section whose heading reads like
   rules, steps or safety ("Quy trình", "Rào an toàn", "Bắt buộc", "Lưu ý", "Rules", "Workflow", "Never"...).
3. Not sure, load all: no heading matches, too many sections match, or the selection would be nearly the whole skill.
   Skills under 12,000 characters are never split.
4. The model sees what was left out: the end lists every other part and how to read it in one call.
5. Javis learns from use: a part the model had to fetch after a selective load, in two different turns, is loaded from
   then on; a skill that needed two or more extra parts (or the whole) in two turns is loaded whole from then on. The
   record resets when the skill text changes.
6. It starts on a share of chat sessions only (10% by default, `context_runtime.skill_sections.allocation_basis_points`
   in settings.json; JAVIS_SKILL_SECTIONS=0|1 turns it off or on for every session), only in the owner's own turns,
   never for a customer-facing bot or a background job, and the Off saving level turns it off.

The savings go to the tool result meter (shape "sections"), so the Usage page counts them.
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import math
import os
import re
import threading
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

SKILL_MIN_CHARS = 12_000
# Skills built as a menu of alternatives (point 0 of the module docstring). Checked request by request in
# tests/python/test_section_select.py before a name goes here.
MENU_SKILLS = frozenset({"javis-builder"})
MIN_SCORE = 1.5          # below this nothing matches well enough: load everything
KEEP_RATIO = 0.6         # sections scoring at least this share of the best one are loaded too
MAX_SHARE = 0.85         # a selection this close to the whole text is not worth it
DEFAULT_BASIS_POINTS = 1000   # 10% of chat sessions
SALT = "skill-sections-v1"
LEARN_MIN_TURNS = 2      # a lesson needs this many different turns
OPEN_LOAD_TTL_S = 1800   # a fetch counts toward the selective load it follows within this time
LEARN_MAX_KEYS = 500

# The request of the turn being served (set by the API engines' tool loops from the last user message).
QUESTION: contextvars.ContextVar = contextvars.ContextVar("javis_turn_question", default="")

_ALWAYS_RE = re.compile(
    r"\b(quy trinh|quy tac|nguyen tac|luat|bat buoc|luu y|khong duoc|canh bao|rao|an toan|khi nao dung|"
    r"gioi han|chu y|nguyen ly|"
    r"rules?|required|requirements?|must|never|pitfalls?|gotchas?|important|safety|warnings?|constraints?|"
    r"principles?|anti.?patterns?|limits?|limitations?|"
    r"when to use|overview|tong quan|process|workflow|steps?|instructions?|checklist)\b")
_STOP = frozenset((
    "toi minh ban em anh chi cho giup mot cai cac nhung la va voi de thi co khong duoc nay do ra vao len xuong "
    "di den tu trong ngoai nua roi lam tao hay can muon the nao gi sao duoc khi neu "
    "luc gio moi bao sau truoc them vay nhu cung rat qua nhieu it het van dang se da bi boi theo tai cua "
    "the a an and or of to in on for with is are be by it this that as at from please make create help me my i "
    "you your we our can could would should will just some any all"
).split())
_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def fold(text: str) -> str:
    """Lowercase without accents ("Đơn hàng" -> "don hang")."""
    text = unicodedata.normalize("NFD", str(text or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn").lower()


def words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9_]+", fold(text)) if len(w) > 1 and w not in _STOP]


@dataclass
class Unit:
    title: str
    level: int
    start: int          # line index, inclusive
    end: int            # line index, exclusive
    parent: int = -1    # index of the level-2 unit a level-3 unit sits in
    always: bool = False
    has_children: bool = False


def parse(text: str) -> tuple[list[str], int, list[Unit]]:
    """(lines, end of the preamble, units). The preamble is everything before the first level-2 heading (frontmatter
    and title included). A level-2 section with level-3 children becomes its own intro plus one unit per child;
    headings inside code fences are text, as in the Markdown extractor of Graphify and of Javis's own notes."""
    lines = str(text or "").splitlines()
    heads: list[tuple[int, int, str]] = []
    fence = None
    start = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                start = i + 1
                break
    for i in range(start, len(lines)):
        m = _FENCE_RE.match(lines[i])
        if m:
            mark = m.group(1)[0]
            if fence is None:
                fence = mark
            elif fence == mark:
                fence = None
            continue
        if fence is not None:
            continue
        h = _HEADING_RE.match(lines[i])
        if h and len(h.group(1)) in (2, 3):
            heads.append((i, len(h.group(1)), h.group(2).strip()))
    first_h2 = next((i for i, lvl, _ in heads if lvl == 2), len(lines))
    heads = [h for h in heads if h[0] >= first_h2]
    units: list[Unit] = []
    h2_index = -1
    for n, (i, lvl, title) in enumerate(heads):
        nxt = heads[n + 1][0] if n + 1 < len(heads) else len(lines)
        if lvl == 2:
            units.append(Unit(title, 2, i, nxt))
            h2_index = len(units) - 1
            units[h2_index].always = bool(_ALWAYS_RE.search(fold(title)))
        else:
            if h2_index < 0:
                continue
            units[h2_index].has_children = True
            units.append(Unit(title, 3, i, nxt, parent=h2_index, always=units[h2_index].always))
    return lines, first_h2, units


@dataclass
class Selection:
    text: str
    full_chars: int
    sent_chars: int
    loaded: list[str]
    left_out: list[tuple[str, int, int]]   # (title, first line, last line), 1-based


def _unit_text(lines: list[str], u: Unit) -> str:
    return "\n".join(lines[u.start:u.end])


def select(text: str, query: str, min_chars: int, learned: tuple[bool, set] | None = None) -> Selection | None:
    """The sections of `text` the query needs, or None to load everything (see the module docstring)."""
    text = str(text or "")
    if len(text) < min_chars:
        return None
    full_now, extra_titles = learned or (False, set())
    if full_now:
        return None
    q = list(dict.fromkeys(words(query)))
    if not q:
        return None
    lines, pre_end, units = parse(text)
    cands = [n for n, u in enumerate(units) if not u.always and not (u.level == 2 and u.has_children)]
    if len(cands) < 2:
        return None
    bodies = {n: words(_unit_text(lines, units[n])) for n in cands}
    heads = {n: set(words(units[n].title)) for n in cands}
    df: dict[str, int] = {}
    for n in cands:
        for w in set(bodies[n]):
            df[w] = df.get(w, 0) + 1

    def score(n: int) -> float:
        sc = 0.0
        for w in q:
            idf = math.log(1 + len(cands) / (1 + df.get(w, 0)))
            if w in heads[n]:
                sc += 3 * idf
            sc += idf * min(3, bodies[n].count(w)) / 3
        return sc

    scores = {n: score(n) for n in cands}
    best_n = max(cands, key=lambda n: scores[n])
    best = scores[best_n]
    if best < MIN_SCORE:
        return None
    # The strongest signal is a word of the task in a section's own heading. Words that only turn up somewhere in the
    # text ("lúc", "mỗi", a date) are not enough to leave anything out: load everything.
    if not any(w in heads[best_n] for w in q):
        return None
    picked = {n for n in cands if scores[n] > 0 and scores[n] >= KEEP_RATIO * best}
    if len(picked) > max(2, len(cands) // 2):
        return None
    learned_titles = {fold(t) for t in extra_titles}
    picked |= {n for n in cands if fold(units[n].title) in learned_titles}
    keep = set(picked)
    for n, u in enumerate(units):
        if u.always:
            keep.add(n)
    for n in list(keep):
        if units[n].parent >= 0:
            keep.add(units[n].parent)     # the intro of the section a picked part sits in
    out = ["\n".join(lines[:pre_end])] + [_unit_text(lines, units[n]) for n in sorted(keep)]
    body = "\n".join(x for x in out if x)
    if len(body) >= MAX_SHARE * len(text):
        return None
    left = [(units[n].title, units[n].start + 1, units[n].end) for n in cands if n not in keep]
    return Selection(body, len(text), len(body), [units[n].title for n in sorted(keep)], left)


def _match(units: list[Unit], title: str) -> Unit | None:
    want = fold(title).strip(" #")
    if not want:
        return None
    for test in (lambda t: t == want, lambda t: t.startswith(want), lambda t: want in t):
        for u in units:
            if test(fold(u.title)):
                return u
    return None


def resolve_title(text: str, title: str) -> str | None:
    """The full heading a model's `section=` names (accent and case free; exact, then prefix, then contained)."""
    u = _match(parse(text)[2], title)
    return u.title if u else None


def find_section(text: str, title: str) -> str | None:
    """The text of one section by its heading, matched like `resolve_title`. A top-level section comes with
    everything under it."""
    lines, _pre, units = parse(text)
    u = _match(units, title)
    if u is None:
        return None
    if u.level == 2 and u.has_children:
        end = next((v.start for v in units if v.level == 2 and v.start > u.start), len(lines))
        return "\n".join(lines[u.start:end])
    return _unit_text(lines, u)


def section_titles(text: str) -> list[str]:
    return [u.title for u in parse(text)[2]]


# ───────────────────────── who gets it ─────────────────────────
def _flag(value) -> bool | None:
    s = str(value).strip().lower()
    if s in ("1", "true", "on", "yes"):
        return True
    if s in ("0", "false", "off", "no"):
        return False
    return None


def session_key() -> str:
    """The owner's chat session of this turn, or "" (no turn, a bot answering a customer, a background job)."""
    try:
        import turn_context
        turn = turn_context.current() or {}
    except Exception:  # noqa: BLE001
        return ""
    if not turn.get("la_chu"):
        return ""
    return str(turn.get("session_id") or turn.get("chat_id") or "")


def assigned(key: str) -> bool:
    """Whether this chat session gets selective loading (the canary share, the switches)."""
    env = _flag(os.getenv("JAVIS_SKILL_SECTIONS", ""))
    if env is False:
        return False
    try:
        import tool_result_shaper
        if not tool_result_shaper.settings().get("on"):
            return False
    except Exception:  # noqa: BLE001
        pass
    if not key:
        return False
    if env is True:
        return True
    bps = DEFAULT_BASIS_POINTS
    try:
        import config
        raw = ((config.read_settings() or {}).get("context_runtime") or {}).get("skill_sections") or {}
        if isinstance(raw, dict) and raw.get("allocation_basis_points") is not None:
            bps = max(0, min(10_000, int(raw.get("allocation_basis_points"))))
    except Exception:  # noqa: BLE001
        pass
    digest = hashlib.sha256(f"{SALT}|{key}".encode("utf-8", errors="replace")).digest()
    return int.from_bytes(digest[:8], "big") % 10_000 < bps


_OPT_IN_RE = re.compile(r"^sections:\s*[\"']?select[\"']?\s*$", re.M)


def opted_in(name: str, text: str) -> bool:
    """A skill Javis may split (point 0 of the module docstring)."""
    if str(name or "") in MENU_SKILLS:
        return True
    head = str(text or "")
    if head.startswith("---"):
        end = head.find("\n---", 3)
        if end > 0 and _OPT_IN_RE.search(head[:end]):
            return True
    try:
        import config
        raw = ((config.read_settings() or {}).get("context_runtime") or {}).get("skill_sections") or {}
        listed = raw.get("skills") if isinstance(raw, dict) else None
        return isinstance(listed, list) and str(name or "") in {str(x) for x in listed}
    except Exception:  # noqa: BLE001
        return False


# ───────────────────────── learning from use ─────────────────────────
_LOCK = threading.Lock()
_OPEN: dict[tuple, dict] = {}


def _store_path() -> Path:
    try:
        from config import STATE_DIR
        return Path(STATE_DIR) / "section_learning.json"
    except Exception:  # noqa: BLE001
        return Path(os.getenv("JAVIS_STATE_DIR") or ".") / "section_learning.json"


def _load_store() -> dict:
    try:
        d = json.loads(_store_path().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_store(d: dict) -> None:
    if len(d) > LEARN_MAX_KEYS:
        for k in sorted(d, key=lambda k: d[k].get("ts", 0))[: len(d) - LEARN_MAX_KEYS]:
            d.pop(k, None)
    p = _store_path()
    try:
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        pass


def text_key(kind: str, name: str, text: str) -> str:
    return f"{kind}:{name}:{hashlib.sha1(str(text).encode('utf-8', 'replace')).hexdigest()[:12]}"


def learned(key: str) -> tuple[bool, set]:
    """(load whole from now on, titles to load up front) for one text."""
    with _LOCK:
        e = _load_store().get(key) or {}
    extra = {t for t, n in (e.get("extra") or {}).items() if int(n) >= LEARN_MIN_TURNS}
    return bool(e.get("full")), extra


def note_load(kind: str, name: str, key: str, session: str) -> None:
    with _LOCK:
        d = _load_store()
        e = d.setdefault(key, {"loads": 0, "extra": {}, "heavy": 0, "full": False})
        e["loads"] = int(e.get("loads") or 0) + 1
        e["ts"] = time.time()
        _save_store(d)
        now = time.time()
        for k in [k for k, v in _OPEN.items() if now - v["ts"] > OPEN_LOAD_TTL_S]:
            _OPEN.pop(k, None)
        _OPEN[(kind, name, session)] = {"key": key, "titles": set(), "ts": now, "heavy": False}


def note_fetch(kind: str, name: str, session: str, title: str) -> None:
    """The model asked for more after a selective load in this session: one section (`title`) or everything ("*")."""
    with _LOCK:
        o = _OPEN.get((kind, name, session))
        if o is None or time.time() - o["ts"] > OPEN_LOAD_TTL_S:
            return
        t = "*" if title == "*" else str(title or "").strip()
        if not t or t in o["titles"]:
            return
        o["titles"].add(t)
        d = _load_store()
        e = d.setdefault(o["key"], {"loads": 0, "extra": {}, "heavy": 0, "full": False})
        if t != "*":
            e["extra"][t] = int(e["extra"].get(t) or 0) + 1
        if not o["heavy"] and (t == "*" or len(o["titles"]) >= 2):
            o["heavy"] = True
            e["heavy"] = int(e.get("heavy") or 0) + 1
            if e["heavy"] >= LEARN_MIN_TURNS:
                e["full"] = True
        e["ts"] = time.time()
        _save_store(d)


# ───────────────────────── the two callers ─────────────────────────
def _meter(tool: str, sel: Selection) -> None:
    try:
        import tool_result_reuse
        tool_result_reuse.note_saving("sections", tool, sel.full_chars, sel.sent_chars)
    except Exception:  # noqa: BLE001
        pass


def for_skill(name: str, text: str, task: str = "", question: str | None = None, session: str | None = None,
              tool: str = "javis_use_skill") -> str | None:
    """The selected parts of a skill with a header and the list of what was left out, or None to load it whole."""
    session = session_key() if session is None else session
    if not opted_in(name, text) or not assigned(session):
        return None
    query = " ".join(x for x in (str(task or ""), str(QUESTION.get() if question is None else question)) if x)
    key = text_key("skill", name, text)
    sel = select(text, query, SKILL_MIN_CHARS, learned(key))
    if sel is None:
        return None
    note_load("skill", name, key, session)
    _meter(tool, sel)
    head = (f"[Javis loaded the parts of skill `{name}` that match this task ({sel.sent_chars:,} of "
            f"{sel.full_chars:,} characters): its rules and steps, plus the sections the task names. The other parts "
            f"are listed at the end.]\n\n")
    tail = ("\n\n[Other parts of this skill, not loaded: "
            + "; ".join(f'"{t}"' for t, _a, _b in sel.left_out)
            + f'. If the task needs one, call javis_use_skill(name="{name}", section="<title>"), or full=true for '
              "the whole skill.]")
    return head + sel.text + tail
