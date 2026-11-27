"""Find the skill a request needs from the WHOLE text of every skill, in any language (2026-11-27).

Owner, 27/11/2026: the skill list in the prompt cut every description at 150 characters and, past about twenty
skills, left the rest out altogether: a brain with 44 skills showed 21 and hid 23, and the hidden ones could only be
loaded by a model that already knew their name. The search tool did not help either, because inside it every skill
was one entry (`javis_use_skill`) whose description was that same cut list. So skills are now found in four layers:

  1. The system prompt names every skill (slug only, by group; `main_prompt_rendering.render_skill_router`). It is
     stable, so the provider's prompt cache keeps holding it.
  2. Each turn Javis ranks every skill against the request and the last turns, and the few that fit ride at the head
     of the turn with their WHOLE description (`turn_block`). A turn nothing fits gets nothing, so a plain question
     costs less than the old list did.
  3. On demand: `javis_search_tools`, `javis_use_skill(find=...)` and `find_skills()` inside `javis_code` all search
     this same index (`search`).
  4. It learns (`note_suggested`, `note_load`): a request that ended in a skill the suggestions missed is remembered
     for that skill, so the next request worded the same way finds it; a skill suggested again and again and never
     loaded weighs a little less.

Why ranking here and not by the model writing code over the list (code mode): the hard part of using a skill is
noticing that one exists, and a model does not search for what it does not know is there. A ranking that costs no
round and puts the right few in front of the model, who then judges them, does better and costs less than a search
round. The search is still there for what the ranking missed.

What one skill is indexed by: its slug and name (weigh most), its whole description, the "When to use" part of its
body, its headings, its group, and the requests learned for it. Ranking is BM25 with tool_finder's concept table (a
Vietnamese request reaches an English description), pairs of words for phrases ("cham soc", "khach hang"), and
scripts written without spaces cut into pairs of characters (section_select.words). Scores are measured in units of
"one word only this skill has", so the same thresholds hold for a brain with three skills and one with three hundred.

Never raises into a chat turn: a broken skill file, a corrupt sidecar or an unreadable brain only means no suggestion.
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import tempfile
import threading
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import section_select
import skill_router
import tool_finder

# ---------------------------------------------------------------------------------------------------------------
# Tuning (2026-11-27), measured with tools/skill_routing_bench.py on two sets: the synthetic 44-skill brain of
# tests/fixtures/skill_routing_cases.json (62 requests) and a real 58-skill set, mostly written in English, asked in
# Vietnamese (50 requests, kept out of the repo). The right skill is among the suggestions for 96% and 95% of the
# requests that have one (the old router list showed it for 53% and 23%, the old Phase 8 selector picked it for 64%
# and 30%); a request no skill fits gets a suggestion 2 times in 8 and 0 in 8; a body is preloaded for the wrong
# skill once in 112 requests.
# ---------------------------------------------------------------------------------------------------------------
SUGGEST_MAX = 3              # skills in one turn's suggestions
SUGGEST_CHARS = 3600         # the whole suggestions block, in characters
SUGGEST_MIN_UNITS = 2.5      # about two words or a phrase that few skills have
SUGGEST_MIN_COVERAGE = 0.15  # share of the request's meaning (idf-weighted) the skill covers; a long request is
                             # mostly about its content, so this stays low and the score does the work
SUGGEST_RELATIVE = 0.3       # a second or third skill must score at least this share of the first
LOAD_MIN_UNITS = 5.0         # confident enough to load the body before the model asks (Phase 8 lazy skill)
LOAD_MIN_COVERAGE = 0.5
LOAD_MARGIN = 1.35           # ... and this far ahead of the runner-up among ALL skills
SEARCH_MIN_UNITS = 1.0       # an explicit search shows weaker matches too: the model asked
RECENT_WEIGHTS = (0.4, 0.25)  # the previous user messages, newest first, against 1.0 for this one

_K1 = 1.2
_B = 0.75
_W_NAME = 2.0                # flat bonus for a word of the skill's slug or name (as in tool_finder)
_W_DESC = 1.0
_W_WHEN = 0.8
_W_LEARNED = 1.0
_W_GROUP = 0.6
_W_HEAD = 0.3
_READ_MAX = 65536            # bytes of one SKILL.md read for the index
_WHEN_MAX = 1500             # characters of the "When to use" part indexed
_HEADS_MAX = 40

# Headings of the part that says when to use a skill, folded. A row per language, like section_select's tables.
_WHEN_RE = re.compile(
    r"\b(when to use|use when|when should|triggers?|khi nao dung|dung khi nao|khi nao kich hoat|kich hoat khi|"
    r"cuando usar|quando usar|quand utiliser|wann verwenden|wann nutzen|когда использовать|"
    r"kapan menggunakan|kapan digunakan)\b")
_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_HEAD_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_WS_RE = re.compile(r"\s+")


# ---------------------------------------------------------------------------------------------------------------
# Words
#
# Vietnamese needs two things a plain word index gets wrong:
#   - Its accents carry meaning. Folded, "bán" (sell) is "ban" like "bạn" (you, a stop word), "thời tiết" (weather)
#     shares "thoi" with "thói quen" (habit), "quý" (quarter) is "quy" of "quy trình". So a word written with its
#     marks is indexed twice: as written, which matches fully, and folded, which matches at half weight (someone
#     typing without marks still finds it).
#   - Its meaning lives in pairs of syllables ("khách hàng", "quá hạn", "bán hàng"). Pairs count as much as single
#     words, so a skill that has the phrase beats one that has its syllables scattered.
# Other Latin languages simply have fewer marked words; scripts without spaces go through section_select.words.
# ---------------------------------------------------------------------------------------------------------------
_LATIN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_FOLDED_WEIGHT = 0.5         # a folded alternative of a word typed with its marks
_EXPANSION_WEIGHT = 0.8      # an English word a Vietnamese skill concept stands for (_SKILL_CONCEPT_ROWS)
_BUSINESS_EXPANSION_WEIGHT = 0.4  # tool_finder.CONCEPTS: broader ("doanh thu" -> report, total...), so weaker

# Stop words written with their marks: a folded stop list would also drop "bán" for "bạn", "quá hạn" for "quá".
_MARKED_STOP = frozenset("""
hôm nay qua ngày mai tuần này trước tháng năm giờ phút của cho các những trong ngoài trên dưới vào ra từ đến về
với và hoặc là có không được nào đang đã sẽ lên xuống bằng theo này kia đó một hai ba tôi anh em mình chị bạn
giúp giùm dùm hãy nhé nha nhá đi thì mà như rất quá cần muốn dùng cái con người việc gì sao thế bao nhiêu làm
ạ ơi vậy rồi nữa đây đấy luôn thêm hộ
""".split())


# What people ask a skill for, in the words skill authors use (tool_finder.CONCEPTS covers business data; these are
# the deliverables skills make). Many brains run skills written in English (the Anthropic set: docx, pptx, xlsx,
# pdf...) for an owner who asks in Vietnamese. Key: phrases as typed, folded; value: English words. Generic only.
_SKILL_CONCEPT_ROWS = [
    # documents and files
    ("thuyet trinh|trinh chieu|bai trinh bay|slide|slides", "presentation slide deck pptx powerpoint"),
    ("bang tinh|excel|google sheet", "spreadsheet excel xlsx sheet formula"),
    ("cong thuc", "formula"),
    ("van ban|tai lieu word|file word|word|muc luc", "document docx word"),
    ("hop dong", "contract agreement document"),
    ("doc file|mo file|file dinh kem|tep", "file read upload"),
    ("trich xuat|boc tach", "extract"),
    ("gop|ghep", "merge combine"),
    ("tach file|chia file", "split"),
    ("dien form|dien mau|dien don|to khai|giay to|thu tuc|ho chieu", "form fill paperwork application passport"),
    # writing and content
    ("viet|soan|soan thao", "write draft compose"),
    ("tom tat|tom luoc", "summary summarize summarise brief"),
    ("dich|ban dich|phien dich", "translate translation"),
    ("kich ban", "script"),
    ("giong van|van phong|cach viet|giong cua anh|giong cua toi", "writing style voice tone"),
    ("thong bao|thong bao noi bo", "announcement communication update"),
    ("noi bo", "internal company"),
    ("cong ty|doanh nghiep", "company business"),
    ("ban tin|ban tin sang|dau ngay|buoi sang", "morning brief briefing"),
    ("trang ban hang|trang dich|landing page", "sales page landing"),
    ("cam on", "thank thanks"),
    # images, video, design
    ("hinh anh|anh minh hoa|tao anh", "image picture illustration"),
    ("ve|ve tranh|tranh", "draw paint painting art illustration"),
    ("mau nuoc", "watercolor watercolour"),
    ("nghe thuat", "art artistic"),
    ("anh dong|hinh dong|gif", "gif animated animation"),
    ("video|clip", "video"),
    ("thiet ke|giao dien", "design interface ui frontend"),
    ("dep|dep mat|chuyen nghiep", "beautiful polished aesthetic"),
    ("khac biet|doc dao", "distinctive unique"),
    ("thuong hieu", "brand"),
    ("phong chu|font chu", "font typography"),
    ("trang web|website", "website web site page"),
    # building and code
    ("tao|tao ra|tao moi|xay dung|lam moi", "create build generate new"),
    ("moi", "new"),
    ("sua|chinh sua|bien tap|cai thien", "edit modify improve"),
    ("lap trinh|ma nguon", "code programming"),
    ("loi", "bug error"),
    ("ra soat|danh gia|kiem tra", "review audit check"),
    ("bao mat|lo hong", "security vulnerability"),
    ("may chu", "server"),
    ("ket noi|tich hop", "connect integration connector mcp"),
    ("nhap|nhap vao|chuyen sang|chuyen tu", "import"),
    ("bo nho|ky uc", "memory"),
    # learning and research
    ("nghien cuu", "research"),
    ("so sanh", "compare comparison"),
    ("nguon|trich dan|dan nguon", "source citation"),
    ("doi thu|canh tranh", "competitor competitive"),
    ("hoc|tim hieu|hieu", "learn understand"),
    ("giai thich|vi sao|tai sao", "explain why understanding"),
    ("huong dan|day", "guide teach tutorial"),
    # money
    ("tinh|tinh toan|tinh thu|uoc tinh", "calculate calculation estimate"),
    ("vay|khoan vay|tra gop|vay mua nha", "loan mortgage"),
    ("lai suat|lai kep|lai", "interest rate compound"),
    ("huu tri|nghi huu", "retirement"),
    ("thue", "tax"),
    ("hoan ung|thanh toan lai|chung tu chi", "reimbursement expense"),
    ("phap ly|luat", "legal law"),
    # errands and life
    ("huy|huy bo|ngung", "cancel unsubscribe stop"),
    ("goi dang ky|thue bao|goi thanh vien", "subscription membership"),
    ("tra hang", "return item"),
    ("hoan tien", "refund"),
    ("dat|dat cho|dat ban|dat lich|dat truoc", "book booking reservation appointment"),
    ("do an|mon an|dat do an|goi do an", "food meal order restaurant delivery"),
    ("di cho|mua do|mua sam|thuc pham", "grocery groceries shopping"),
    ("goi dien|cuoc goi|dien thoai", "call phone"),
    ("thue nguoi|tim nguoi|thue tho|tho", "hire service provider help"),
    ("don nha|don dep|ve sinh", "cleaning clean"),
    ("chuyen nha", "moving"),
    ("sua chua|sua nha", "repair handyman"),
    ("sinh nhat|dam cuoi|tiec|bua tiec|su kien|to chuc", "event party birthday wedding planning"),
    ("nha hang", "restaurant"),
    ("khach san", "hotel"),
    ("ve may bay|chuyen bay", "flight"),
    ("thuoc|don thuoc|nha thuoc", "prescription pharmacy medication refill"),
    ("bac si|kham benh", "doctor appointment"),
    # plans, people, places
    ("ke hoach|len ke hoach", "plan planner planning"),
    ("lich trinh|du lich", "itinerary travel trip"),
    ("tap luyen|tap gym|the duc", "workout exercise fitness"),
    ("thuc don|nau an", "meal recipe menu"),
    ("nang suat|quan ly thoi gian", "productivity time"),
    ("thoi quen", "habit"),
    ("tuyen dung", "hiring recruiting job"),
    ("phong van", "interview"),
    ("giong doc|doc thanh tieng|long tieng", "voice tts speech audio"),
    ("ghi chu", "note"),
]


def _stem(word: str) -> str:
    """tool_finder.stem (plural s) plus the English plurals in -es and -ies: "speeches" -> "speech",
    "boxes" -> "box", "summaries" -> "summary"."""
    if len(word) > 4 and word.endswith(("ches", "shes", "sses", "xes", "zes")):
        return word[:-2]
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    return tool_finder.stem(word)


def _build_skill_concepts() -> dict:
    table = {}
    for keys, expands in _SKILL_CONCEPT_ROWS:
        words = tuple(dict.fromkeys(_stem(w) for w in expands.split()))
        for k in keys.split("|"):
            k = " ".join(_stem(w) for w in tool_finder.fold(k).split())
            if k:
                table[k] = table.get(k, ()) + words
    return table


_SKILL_CONCEPTS = _build_skill_concepts()
_SKILL_CONCEPT_LEN = max(len(k.split()) for k in _SKILL_CONCEPTS)


def _skill_concept_spans(toks: list) -> list:
    """[(start, length, English words)] for the skill concepts a token sequence names, longest phrase first. A
    one-word concept must not be a stop word: folded, "về" (about) is "ve" like "vẽ" (draw)."""
    folded = [f for _m, f in toks]
    out, i = [], 0
    while i < len(folded):
        for n in range(min(_SKILL_CONCEPT_LEN, len(folded) - i), 0, -1):
            hit = _SKILL_CONCEPTS.get(" ".join(folded[i:i + n]))
            if hit and not (n == 1 and _is_stop(toks[i])):
                out.append((i, n, hit))
                i += n
                break
        else:
            i += 1
    return out


def _tokens(text: str) -> list:
    """[(as written or "", folded)] of the Latin words of a text, in order. "as written" is set only for a word with
    marks ("bán"); folded words are stemmed ("orders" -> "order"); snake/kebab names are split."""
    out = []
    for tok in _LATIN_RE.findall(unicodedata.normalize("NFC", str(text or "").lower())):
        f = tool_finder.fold(tok)
        if not f.isascii():
            continue                     # another script: section_select.words below
        if len(f) < 2 and not f.isdigit():
            continue
        out.append((tok if tok != f else "", _stem(f)))
    return out


def _is_stop(tok: tuple) -> bool:
    marked, folded = tok
    return (marked in _MARKED_STOP) if marked else (folded in tool_finder._STOP)


def _other_script(text: str) -> list:
    """Words of scripts that are not Latin (character pairs for scripts without spaces)."""
    return [w for w in section_select.words(text) if not w.isascii()]


def _doc_terms(text: str) -> list:
    """Every index word of a text: words folded and as written, pairs folded and as written, other scripts."""
    toks = _tokens(text)
    out = []
    for marked, folded in toks:
        out.append(folded)
        if marked:
            out.append(marked)
    for a, b in zip(toks, toks[1:]):
        if _is_stop(a) and _is_stop(b):
            continue
        out.append(a[1] + " " + b[1])
        if a[0] or b[0]:
            out.append((a[0] or a[1]) + " " + (b[0] or b[1]))
    out.extend(_other_script(text))
    return out


def _terms(text: str) -> list:
    """Folded words only (used where a rough count of what a text says is enough)."""
    return [f for _m, f in _tokens(text)] + _other_script(text)


def _query_groups(text: str, weight: float) -> list:
    """[(alternatives, weight, core)] for one message, alternatives being ((word, weight), ...).

    One group per meaningful word (as written, then folded at half weight), one per pair of words, one per word of
    another script. A skill concept the message names ("đồ ăn", "vẽ", "thuyết trình") adds its English words as
    further alternatives of the SAME group, so a skill written in English covers that meaning as a Vietnamese one
    does; the syllables of a phrase concept then have no group of their own ("đồ", "ăn" alone mean little). The
    business concepts of tool_finder ("doanh thu" -> revenue, report, total...) are broader and only add a little
    to the score (core=False: they do not count in how much of the request a skill covers)."""
    text = str(text or "")
    if not text.strip():
        return []
    toks = _tokens(text)
    literal = {f for _m, f in toks}
    on_word, on_pair, covered = {}, {}, set()
    for start, n, words in _skill_concept_spans(toks):
        extra = [w for w in words if w not in literal]
        if n == 1:
            on_word.setdefault(start, []).extend(extra)
        else:
            on_pair.setdefault(start, []).extend(extra)
            covered.update(range(start, start + n))
    out = []

    def word_alts(tok):
        marked, folded = tok
        if marked:
            return ((marked, 1.0),) + (() if folded in tool_finder._STOP else ((folded, _FOLDED_WEIGHT),))
        return ((folded, 1.0),)

    for i, tok in enumerate(toks):
        if i in covered or _is_stop(tok) or tok[1].isdigit():
            continue
        out.append((word_alts(tok) + tuple((w, _EXPANSION_WEIGHT) for w in on_word.get(i, ())), weight, True))
    for i, (a, b) in enumerate(zip(toks, toks[1:])):
        if (_is_stop(a) and _is_stop(b) and i not in on_pair) or a[1].isdigit() or b[1].isdigit():
            continue
        folded = a[1] + " " + b[1]
        if a[0] or b[0]:
            alts = (((a[0] or a[1]) + " " + (b[0] or b[1]), 1.0), (folded, _FOLDED_WEIGHT))
        else:
            alts = ((folded, 1.0),)
        out.append((alts + tuple((w, _EXPANSION_WEIGHT) for w in on_pair.get(i, ())), weight, True))
    for w in _other_script(text):
        out.append((((w, 1.0),), weight, True))
    groups, _loose = tool_finder.parse_query(text)
    for g in groups:
        extra = tuple((w, _BUSINESS_EXPANSION_WEIGHT) for w in g if w not in literal)
        if extra:
            out.append((extra, weight, False))
    return out


def _clean(text: str, limit: int) -> str:
    return _WS_RE.sub(" ", str(text or "")).strip()[:limit]


# ---------------------------------------------------------------------------------------------------------------
# One skill
# ---------------------------------------------------------------------------------------------------------------
@dataclass
class SkillDoc:
    slug: str
    name: str
    group: str
    description: str
    when: str = ""
    headings: tuple = ()
    learned: tuple = ()
    tf: Counter = field(default_factory=Counter)
    name_words: frozenset = frozenset()
    length: float = 1.0
    exact: tuple = ()            # folded slug and name, for a request that names the skill outright
    whole: tuple = ()            # folded slug and name of any length, for a request that is nothing but the name


def _body_parts(body: str) -> tuple:
    """(the "When to use" text, the headings) of a skill body, code blocks skipped."""
    heads, when, cur_when, in_fence = [], [], None, False
    for line in str(body or "").splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _HEAD_RE.match(line)
        if m:
            title = m.group(2).strip()
            if len(heads) < _HEADS_MAX:
                heads.append(title)
            level = len(m.group(1))
            if cur_when is not None and level <= cur_when:
                cur_when = None
            if cur_when is None and _WHEN_RE.search(tool_finder.fold(title)):
                cur_when = level
            continue
        if cur_when is not None:
            when.append(line)
    return _clean("\n".join(when), _WHEN_MAX), tuple(heads)


def _read_body(path: str) -> str:
    try:
        with open(path, "rb") as fh:
            raw = fh.read(_READ_MAX)
    except (OSError, TypeError, ValueError):
        return ""
    _meta, body = skill_router.split_frontmatter(raw.decode("utf-8", errors="replace"))
    return body


def _make_doc(meta: dict, body: str, learned: tuple) -> SkillDoc:
    slug = str(meta.get("slug") or "").strip()
    name = _clean(meta.get("name") or slug, 200)
    group = _clean(meta.get("group") or "", 120)
    desc = _clean(meta.get("description") or "", skill_router.SKILL_DESC_MAX)
    when, heads = _body_parts(body)
    doc = SkillDoc(slug=slug, name=name, group=group, description=desc, when=when, headings=heads,
                   learned=tuple(learned))
    doc.name_words = frozenset(_doc_terms(slug.replace("-", " ")) + _doc_terms(name))
    tf = Counter()

    def add(text, weight):
        for t in _doc_terms(text):
            tf[t] += weight

    add(slug.replace("-", " "), _W_DESC)
    add(name, _W_DESC)
    add(desc, _W_DESC)
    add(when, _W_WHEN)
    add(group, _W_GROUP)
    for h in heads:
        add(h, _W_HEAD)
    for phrase in learned:
        add(phrase, _W_LEARNED)
    doc.tf = tf
    doc.length = max(1.0, sum(tf.values()))
    # Only a name of two words or more counts as naming the skill outright: "notes" or "learn" in a request is an
    # ordinary word, "thu-tay-email-sequence" is not.
    names = {" ".join(re.split(r"[^0-9a-z]+", tool_finder.fold(v))).strip() for v in (slug, name)}
    doc.exact = tuple(sorted(x for x in names if len(x.split()) >= 2 and len(x) >= 8))
    doc.whole = tuple(sorted(x for x in names if x))
    return doc


# ---------------------------------------------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------------------------------------------
@dataclass
class Match:
    slug: str
    name: str
    group: str
    description: str
    score: float          # in units of "one word only this skill has"
    coverage: float       # share of the request (idf-weighted) this skill covers
    margin: float = 0.0   # first match only: its score over the runner-up's among ALL skills (0 = no runner-up)

    def as_dict(self) -> dict:
        return {"slug": self.slug, "name": self.name, "group": self.group, "description": self.description,
                "score": round(self.score, 3), "coverage": round(self.coverage, 3)}


class SkillIndex:
    def __init__(self, docs: list):
        self.docs = [d for d in docs if d.slug]
        n = max(1, len(self.docs))
        df = Counter()
        for d in self.docs:
            for w in set(d.tf) | set(d.name_words):
                df[w] += 1
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}
        self.unit = math.log(1 + (n - 0.5) / 1.5)     # idf of a word one skill alone has
        self.avg_len = (sum(d.length for d in self.docs) / len(self.docs)) if self.docs else 1.0

    def __len__(self):
        return len(self.docs)

    def _score(self, doc: SkillDoc, groups: list) -> tuple:
        norm = _K1 * (1 - _B + _B * doc.length / self.avg_len)
        score = got = possible = 0.0
        for alts, wt, primary in groups:
            best = best_idf = top_idf = 0.0
            for w, aw in alts:
                idf = self.idf.get(w)
                if not idf:
                    continue
                top_idf = max(top_idf, aw * idf)
                tf = doc.tf.get(w, 0.0)
                v = aw * idf * ((_W_NAME if w in doc.name_words else 0.0)
                                + (tf * (_K1 + 1) / (tf + norm) if tf else 0.0))
                if v > best:
                    best, best_idf = v, aw * idf
            score += wt * best
            if primary:
                possible += wt * top_idf
                got += wt * best_idf
        return score, (got / possible if possible else 0.0)

    def rank(self, query: str, recent=()) -> list:
        """Every skill that matches at all, best first, as [Match]. `recent`: the previous user messages, newest
        first; they count for less and only fill in when this message says little ("ok, do it")."""
        groups = list(_query_groups(query, 1.0))
        # This message carries the request when its words say something the skills know about; a short follow-up
        # ("ok, làm tiếp đi") does not, and then the previous messages are judged too.
        strength = sum(max((aw * self.idf.get(x, 0.0) for x, aw in a), default=0.0)
                       for a, w, core in groups if core)
        says_enough = strength >= 1.5 * self.unit
        for text, wt in zip(list(recent or ())[:len(RECENT_WEIGHTS)], RECENT_WEIGHTS):
            groups.extend((a, w, core and not says_enough) for a, w, core in _query_groups(text, wt))
        if not groups or not self.docs:
            return []
        folded = " " + " ".join(re.split(r"[^0-9a-z]+", tool_finder.fold(query))) + " "
        whole = folded.strip()
        out = []
        for d in self.docs:
            s, cov = self._score(d, groups)
            if any(" " + e + " " in folded for e in d.exact) or whole in d.whole:
                # Named outright ("dùng skill thu-tay-email-sequence"): that is the one.
                s, cov = s + 4 * self.unit, 1.0
            if s > 0:
                out.append(Match(d.slug, d.name, d.group, d.description, s / self.unit if self.unit else s, cov))
        out.sort(key=lambda m: (-m.score, m.slug))
        return out


_CACHE: dict = {}
_CACHE_LOCK = threading.Lock()
_CACHE_MAX = 16


def _signature(root: Path, learned: dict) -> tuple:
    """What the index depends on: the skill files (stat only) and the learned requests. Not the shown/used
    counters, which change on most turns and do not change the index."""
    digest = hash(tuple(sorted((k, v) for k, v in learned.items() if v)))
    return (skill_router.skill_manifest_signature(root), digest)


def index_for(root, lang: str = "", descriptions: dict | None = None) -> SkillIndex:
    """The index of the enabled skills of one brain, rebuilt only when a skill file or the learned requests change.
    `descriptions`: owner-applied routing descriptions (improvement_routing, {slug: text}) scored instead of the
    file's own for those skills. Never raises: an unreadable brain is an empty index."""
    try:
        root = Path(root)
        scoped = skill_router._task_metadata(root, lang)
        key = (str(root.resolve()).casefold(), str(lang or ""))
        learned = _learned_phrases(root)
        sig = None if scoped is not None else _signature(root, learned)
        with _CACHE_LOCK:
            hit = _CACHE.get(key)
        if hit and sig is not None and hit[0] == sig and not descriptions:
            return hit[1]
        metas = scoped if scoped is not None else skill_router.list_enabled_meta(root, lang)
        docs = []
        for m in metas:
            slug = str(m.get("slug") or "")
            # A bound improvement task works on a frozen projection of the skills: rank it by that projection's
            # descriptions only, never by the live files on disk.
            body = "" if scoped is not None else _read_body(m.get("path") or "")
            meta = dict(m)
            if descriptions and slug in descriptions:
                meta["description"] = descriptions[slug]
            docs.append(_make_doc(meta, body, learned.get(slug, ())))
        idx = SkillIndex(docs)
        if sig is not None and not descriptions:
            with _CACHE_LOCK:
                if len(_CACHE) >= _CACHE_MAX:
                    _CACHE.pop(next(iter(_CACHE)))
                _CACHE[key] = (sig, idx)
        return idx
    except Exception as exc:  # noqa: BLE001 - finding a skill never breaks a turn
        print(f"[skill_finder] index: {type(exc).__name__}: {exc}", file=sys.stderr)
        return SkillIndex([])


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


# ---------------------------------------------------------------------------------------------------------------
# Search and suggestions
# ---------------------------------------------------------------------------------------------------------------
def search(root, query: str, limit: int = 5, lang: str = "", min_units: float = SEARCH_MIN_UNITS) -> list:
    """Skills for an explicit search (the model asked), as dicts, best first. Never raises."""
    try:
        ranked = index_for(root, lang).rank(query)
        return [m.as_dict() for m in ranked if m.score >= min_units][:max(1, int(limit or 5))]
    except Exception as exc:  # noqa: BLE001
        print(f"[skill_finder] search: {type(exc).__name__}: {exc}", file=sys.stderr)
        return []


def _weigh(root, session: str, ranked: list) -> list:
    """Learned weights: a skill loaded in this chat a moment ago counts a little more (a follow-up often needs it
    again), one suggested often and never loaded a little less."""
    stats = _stats(root)
    sticky = _loaded_recently(root, session)
    out = []
    for m in ranked:
        f = 1.0
        rec = stats.get(m.slug) or {}
        shown, used = int(rec.get("shown") or 0), int(rec.get("used") or 0)
        if shown >= 6 and used / shown < 0.15:
            f *= 0.8
        if m.slug in sticky:
            f *= 1.25
        out.append(Match(m.slug, m.name, m.group, m.description, m.score * f, m.coverage))
    out.sort(key=lambda m: (-m.score, m.slug))
    return out


def suggest(root, query: str, recent=(), session: str = "", lang: str = "", exclude=(),
            descriptions: dict | None = None) -> list:
    """The skills worth putting in front of the model this turn, best first (at most SUGGEST_MAX). [] when nothing
    fits well enough. Never raises."""
    try:
        idx = index_for(root, lang, descriptions)
        if not len(idx):
            return []
        ranked = _weigh(root, session, idx.rank(query, recent))
        ranked = [m for m in ranked if m.slug not in set(exclude or ())]
        if not ranked:
            return []
        top = ranked[0].score
        out = [m for m in ranked
               if m.score >= SUGGEST_MIN_UNITS and m.coverage >= SUGGEST_MIN_COVERAGE
               and m.score >= SUGGEST_RELATIVE * top][:SUGGEST_MAX]
        if out and out[0] is ranked[0]:
            runner = ranked[1].score if len(ranked) > 1 else 0.0
            out[0] = Match(**{**out[0].__dict__, "margin": (top / runner) if runner else 0.0})
        return out
    except Exception as exc:  # noqa: BLE001
        print(f"[skill_finder] suggest: {type(exc).__name__}: {exc}", file=sys.stderr)
        return []


def confident(matches: list) -> bool:
    """True when the first match is clear enough to load its body before the model asks (Phase 8)."""
    if not matches:
        return False
    top = matches[0]
    return (top.score >= LOAD_MIN_UNITS and top.coverage >= LOAD_MIN_COVERAGE
            and (top.margin == 0.0 or top.margin >= LOAD_MARGIN))


SUGGESTIONS_HEAD = ("[Skills that may fit this request, best first. Load one (javis_use_skill name=<slug>, or read its "
                    "SKILL.md) only if it really matches what is asked; otherwise ignore this list.")


def render_suggestions(matches: list, head: str = SUGGESTIONS_HEAD) -> str:
    """The suggestions block, in English like every prompt text. Descriptions are whole while the block fits."""
    if not matches:
        return ""
    lines, used = [head], len(head)
    for i, m in enumerate(matches):
        label = m.name if m.name and m.name != m.slug else ""
        if m.group:
            label = (label + " · " if label else "") + m.group
        desc = m.description or "(no description)"
        line = f"- `{m.slug}`" + (f" ({label})" if label else "") + f": {desc}"
        if used + len(line) > SUGGEST_CHARS and i:
            line = line[:max(200, SUGGEST_CHARS - used)].rstrip() + "…"
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines) + "]"


def strip_suggestions(text):
    """The message without the suggestions block at its head (for readers of the turn's request, such as
    section_select). The block is one paragraph (descriptions are single-line) closed by "]" and a blank line."""
    if not isinstance(text, str) or not text.startswith(SUGGESTIONS_HEAD):
        return text
    end = text.find("]\n\n")
    return text[end + 3:] if end >= 0 else text


def turn_block(root, query: str, recent=(), session: str = "", lang: str = "") -> str:
    """The suggestions of one owner turn, ready to put at the head of the turn ("" when nothing fits), and noted
    for learning. Never raises."""
    try:
        matches = suggest(root, query, recent, session, lang)
        note_suggested(root, session, [m.slug for m in matches], query)
        return render_suggestions(matches)
    except Exception as exc:  # noqa: BLE001
        print(f"[skill_finder] turn: {type(exc).__name__}: {exc}", file=sys.stderr)
        return ""


# ---------------------------------------------------------------------------------------------------------------
# Learning. Sidecar <brain>/Javis/skill-routing.json, next to skill-usage.json and for the same reason: runtime
# state the server owns, never written into the person's SKILL.md.
#   {"version": 1, "skills": {slug: {"learned": [{"text", "n", "at"}], "shown": int, "used": int}}}
# ---------------------------------------------------------------------------------------------------------------
LEARNED_MAX = 12             # requests remembered per skill (most used, then newest, win)
LEARNED_CHARS = 240
_PENDING_TTL = 3 * 3600      # a suggestion still counts for the load that follows within this time
_STICKY_TTL = 2 * 3600
_FLUSH_EVERY = 120           # seconds between writes of the shown/used counters alone
_LOCK = threading.Lock()
_PENDING: dict = {}          # (root, session) -> {"slugs": set, "query": str, "at": float}
_LOADED: dict = {}           # (root, session) -> {slug: at}
_STATE: dict = {}            # root -> {"data": dict, "dirty": bool, "flushed": float, "sig": tuple}


def routing_path(root) -> Path:
    return Path(root) / "Javis" / "skill-routing.json"


def _rkey(root) -> str:
    try:
        return str(Path(root).resolve()).casefold()
    except (OSError, RuntimeError, ValueError):
        return str(root)


def _load_state(root) -> dict:
    """The sidecar of one brain, read once and kept; an edited or corrupt file is read again or starts empty."""
    key = _rkey(root)
    path = routing_path(root)
    try:
        st = path.stat()
        sig = (st.st_mtime_ns, st.st_size)
    except OSError:
        sig = None
    cur = _STATE.get(key)
    if cur is not None and (cur["dirty"] or cur["sig"] == sig):
        return cur
    data = {}
    if sig is not None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
    if not isinstance(data, dict) or not isinstance(data.get("skills"), dict):
        data = {"version": 1, "skills": {}}
    cur = {"data": data, "dirty": False, "flushed": time.time(), "sig": sig}
    _STATE[key] = cur
    return cur


def _flush(root, cur: dict, force: bool = False) -> None:
    if not cur["dirty"] or (not force and time.time() - cur["flushed"] < _FLUSH_EVERY):
        return
    path = routing_path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".skill-routing-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(cur["data"], fh, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        st = path.stat()
        cur.update(dirty=False, flushed=time.time(), sig=(st.st_mtime_ns, st.st_size))
    except Exception as exc:  # noqa: BLE001 - learning is best effort
        print(f"[skill_finder] write: {type(exc).__name__}: {exc}", file=sys.stderr)


def _rec(cur: dict, slug: str) -> dict:
    skills = cur["data"].setdefault("skills", {})
    rec = skills.get(slug)
    if not isinstance(rec, dict):
        rec = skills[slug] = {"learned": [], "shown": 0, "used": 0}
    return rec


def _stats(root) -> dict:
    try:
        with _LOCK:
            return {s: dict(r) for s, r in (_load_state(root)["data"].get("skills") or {}).items()
                    if isinstance(r, dict)}
    except Exception:  # noqa: BLE001
        return {}


def _learned_phrases(root) -> dict:
    out = {}
    for slug, rec in _stats(root).items():
        items = rec.get("learned") if isinstance(rec.get("learned"), list) else []
        out[slug] = tuple(str(x.get("text") or "") for x in items if isinstance(x, dict) and x.get("text"))
    return out


def learned(root, slug: str) -> list:
    """The requests remembered for one skill, most used first."""
    rec = _stats(root).get(str(slug or "")) or {}
    items = [x for x in (rec.get("learned") or []) if isinstance(x, dict) and x.get("text")]
    return sorted(items, key=lambda x: (-int(x.get("n") or 0), -float(x.get("at") or 0)))


def _loaded_recently(root, session: str) -> set:
    if not session:
        return set()
    now = time.time()
    with _LOCK:
        got = _LOADED.get((_rkey(root), session)) or {}
        return {s for s, at in got.items() if now - at < _STICKY_TTL}


def note_suggested(root, session: str, slugs, query: str) -> None:
    """Remember what this turn suggested, so the load that follows can tell a hit from a miss. Never raises."""
    if not session:
        return
    try:
        slugs = [s for s in (slugs or []) if s]
        with _LOCK:
            key = (_rkey(root), session)
            _PENDING[key] = {"slugs": set(slugs), "query": _clean(query, LEARNED_CHARS), "at": time.time()}
            if len(_PENDING) > 2000:
                for k in sorted(_PENDING, key=lambda k: _PENDING[k]["at"])[:500]:
                    _PENDING.pop(k, None)
            if slugs:
                cur = _load_state(root)
                for s in slugs:
                    rec = _rec(cur, s)
                    rec["shown"] = int(rec.get("shown") or 0) + 1
                cur["dirty"] = True
                _flush(root, cur)
    except Exception as exc:  # noqa: BLE001
        print(f"[skill_finder] note_suggested: {type(exc).__name__}: {exc}", file=sys.stderr)


def note_load(root, slug: str, session: str) -> str:
    """A skill was loaded in an owner turn. Returns "hit" (it was suggested), "learned" (it was not, and the request
    is now remembered for it) or "" (nothing to learn from). Never raises."""
    slug = str(slug or "").strip()
    if not slug or not session:
        return ""
    try:
        now = time.time()
        with _LOCK:
            key = (_rkey(root), session)
            _LOADED.setdefault(key, {})[slug] = now
            if len(_LOADED) > 2000:
                _LOADED.pop(next(iter(_LOADED)))
            pending = _PENDING.get(key)
            if not pending or now - pending["at"] > _PENDING_TTL:
                return ""
            cur = _load_state(root)
            rec = _rec(cur, slug)
            if slug in pending["slugs"]:
                pending["slugs"].discard(slug)
                rec["used"] = int(rec.get("used") or 0) + 1
                cur["dirty"] = True
                _flush(root, cur, force=True)
                return "hit"
            text = pending.get("query") or ""
            if len(_terms(text)) < 2:
                return ""
            items = [x for x in (rec.get("learned") or []) if isinstance(x, dict) and x.get("text")]
            folded = tool_finder.fold(text)
            for x in items:
                if tool_finder.fold(x["text"]) == folded:
                    x["n"] = int(x.get("n") or 1) + 1
                    x["at"] = now
                    break
            else:
                items.append({"text": text, "n": 1, "at": now})
            items.sort(key=lambda x: (-int(x.get("n") or 0), -float(x.get("at") or 0)))
            rec["learned"] = items[:LEARNED_MAX]
            pending["query"] = ""        # one request teaches one skill
            cur["dirty"] = True
            _flush(root, cur, force=True)
            return "learned"
    except Exception as exc:  # noqa: BLE001
        print(f"[skill_finder] note_load: {type(exc).__name__}: {exc}", file=sys.stderr)
        return ""


def forget(root, slug: str, text: str = "") -> bool:
    """Drop one learned request of a skill (or all of them when `text` is empty). For the owner and for tests."""
    try:
        with _LOCK:
            cur = _load_state(root)
            rec = (cur["data"].get("skills") or {}).get(slug)
            if not isinstance(rec, dict):
                return False
            before = list(rec.get("learned") or [])
            folded = tool_finder.fold(text)
            rec["learned"] = [x for x in before if text and tool_finder.fold(str(x.get("text") or "")) != folded]
            cur["dirty"] = True
            _flush(root, cur, force=True)
            return len(rec["learned"]) != len(before)
    except Exception:  # noqa: BLE001
        return False


def reset_memory() -> None:
    """Forget the in-process state (tests)."""
    with _LOCK:
        _PENDING.clear()
        _LOADED.clear()
        _STATE.clear()
    clear_cache()
