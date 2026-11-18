"""Load only the parts of a long skill that the current task needs, chosen by Javis before loading (2026-11-18).

Owner, 18/11/2026: worried that cutting what a model gets "mà không có cơ chế nào đó tìm thông tin nạp thông minh trước
khi nạp" would hurt answers. So the choice is made here, by Javis, before anything is loaded, and every doubt resolves
to loading everything, exactly as before:

0. Only skills built as a menu of alternatives, where one request needs one part (javis-builder: agent OR loop OR
   plugin...). A skill that is one procedure needs all of its parts for a general request: tried on seo-audit, a plain
   "audit my SEO" picked "On-Page" and left out crawlability, indexation and speed. So a skill is split only when it is
   on `MENU_SKILLS`, carries `sections: select` in its frontmatter, or is listed by the owner in settings
   (`context_runtime.skill_sections.skills`). Every other skill loads whole, as before.
1. Javis scores each section against the task (the request of this turn, plus what the model says it needs), in any
   language (see "language-neutral text handling" below): words in a section's heading weigh most, rare words more
   than common ones. Nothing is left out unless a word of the task is in the best section's own heading.
2. Sections that state rules are always loaded: the opening text and, when the alternatives sit under one section,
   every other top-level section (the frame around the menu: when to use, steps, safety). A skill with no such
   structure has its rule sections found by heading words in 19 languages ("Quy trình", "Rules", "Reglas", "Regeln",
   "Правила", "ルール", "规则"...).
2b. A part that says another part's thing must exist first brings that part along: javis-builder's Workflow says
   "Nếu workflow tham chiếu agent chưa tồn tại -> TẠO agent đó trước", so a workflow request loads the Agent template
   too. Found in the real-model A/B: without it the model wrote the new agents from memory, with `description:` where
   the template has `role:`.
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

_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")

# ───────────────────────── language-neutral text handling ─────────────────────────
# Owner, 18/11/2026: "chúng ta làm javis cho toàn thế giới dùng chứ không chỉ tiếng việt ... cần phải có bộ khung để bất
# kỳ ngôn ngữ nào dùng trải nghiệm cũng tốt ngang nhau". So nothing below depends on one language:
#   - words are cut by Unicode category, in any script; scripts written without spaces (Chinese, Japanese, Thai, Lao,
#     Khmer, Myanmar) are cut into overlapping pairs of characters, as search engines index them;
#   - only Latin, Greek and Cyrillic accents are folded away ("Đơn" = "don", "Café" = "cafe"); the marks other scripts
#     need to spell a word (Devanagari vowel signs, Japanese voicing marks, Arabic letters) stay;
#   - filler words ("create", "please", "tạo", "crea", "作って") are found from the skill itself: a word in most of its
#     parts cannot tell them apart, so it cannot choose one. No stopword list per language;
#   - the shared frame of a menu skill is found from its structure (point 2), and the rule-heading and "make it first"
#     word tables below are data, one row per language, folded the same way as the text they are matched against;
#   - a request in another language than the skill reaches it through the model, which passes `task` in the skill's
#     language (javis_use_skill's description asks for that). With neither a matching task nor a matching request,
#     the skill loads whole: a language the tables miss loses some of the saving, never quality.
_ACCENTS_RE = re.compile("[\u0300-\u036f]")   # combining accents of Latin, Greek and Cyrillic letters
_NO_SPACE = (
    "\u0e00-\u0eff"     # Thai, Lao
    "\u1000-\u109f"     # Myanmar
    "\u1780-\u17ff"     # Khmer
    "\u3040-\u30ff"     # Hiragana, Katakana
    "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"   # Chinese characters (Japanese kanji, Korean hanja)
    "\uac00-\ud7af"     # Korean syllables: spaced, but particles stick to the noun (루프를 = 루프 + 를), so pairs match
)
_NO_SPACE_RE = re.compile(f"[{_NO_SPACE}]+")
_SPLIT_RE = re.compile(f"[{_NO_SPACE}]+|[^{_NO_SPACE}]+")


def fold(text: str) -> str:
    """Lowercase without Latin/Greek/Cyrillic accents ("Đơn hàng" -> "don hang"); other scripts are kept as written."""
    text = unicodedata.normalize("NFD", str(text or "").replace("đ", "d").replace("Đ", "D"))
    return unicodedata.normalize("NFC", _ACCENTS_RE.sub("", text)).casefold()


def _tokens(folded: str) -> list[str]:
    out, cur = [], []
    for ch in folded:
        if ch == "_" or unicodedata.category(ch)[0] in "LNM":
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return out


def words(text: str) -> list[str]:
    """The words of a text in any language: whole words where words have spaces between them, overlapping character
    pairs where they do not ("作成する" -> 作成, 成す, する)."""
    out: list[str] = []
    for tok in _tokens(fold(text)):
        for part in _SPLIT_RE.findall(tok):
            if _NO_SPACE_RE.fullmatch(part):
                out.extend([part] if len(part) == 1 else [part[i:i + 2] for i in range(len(part) - 1)])
            elif len(part) > 1:
                out.append(part)
    return out


def same_word(a: str, b: str) -> bool:
    """One word in two forms: equal, or one is the other plus a short ending ("loops", "agente", "цикла",
    "Schleifen", "döngüyü"), so languages that inflect nouns match a heading in its plain form."""
    if a == b:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 4 and long_.startswith(short) and len(long_) - len(short) <= 3


_HEAD_NOTES_RE = re.compile(r"`[^`]*`|\([^)]*\)|\[[^\]]*\]|\S*[=/]\S*")


def head_words(title: str) -> list[str]:
    """The words that name what a part is about: its heading without code, paths, settings and notes in brackets
    ("Plugin -> tool `javis_plugin` op=write (never hand over a zip)" -> plugin, tool). Markdown is the same in every
    language, so this is too."""
    return words(_HEAD_NOTES_RE.sub(" ", str(title or "")))


def _table_re(rows: dict[str, str]) -> re.Pattern:
    """One pattern from a word table: each row is a language, its terms split by "|", folded like the text. A term
    in a script with spaces must stand as a whole word; one in a script without spaces is matched anywhere."""
    alts = []
    for terms in rows.values():
        for term in terms.split("|"):
            term = fold(term.strip())
            if not term:
                continue
            esc = re.escape(term).replace("\\ ", r"\s+")
            alts.append(esc if _NO_SPACE_RE.search(term) else rf"(?<!\w){esc}(?!\w)")
    return re.compile("|".join(sorted(alts, key=len, reverse=True)))


# Headings that state rules, steps or safety, in each language: such a section is loaded with every selection. Only
# needed when a skill has no menu container (point 2); add a row for a language, never a list in code.
RULE_HEADINGS = {
    "en": "rule|rules|required|requirement|requirements|must|never|pitfall|pitfalls|gotcha|gotchas|important|safety|"
          "warning|warnings|constraint|constraints|principle|principles|anti-pattern|anti-patterns|antipatterns|"
          "limit|limits|limitation|limitations|when to use|overview|process|workflow|step|steps|instruction|"
          "instructions|checklist",
    "vi": "quy trình|quy tắc|nguyên tắc|luật|bắt buộc|lưu ý|không được|cảnh báo|rào|an toàn|khi nào dùng|giới hạn|"
          "chú ý|nguyên lý|tổng quan|các bước",
    "es": "regla|reglas|requisitos|obligatorio|importante|seguridad|advertencia|advertencias|restricciones|principios|"
          "límites|cuándo usar|resumen|proceso|pasos|instrucciones|nunca|prohibido",
    "pt": "regra|regras|requisitos|obrigatório|importante|segurança|aviso|avisos|restrições|princípios|limites|"
          "quando usar|visão geral|processo|passos|etapas|instruções|nunca|proibido",
    "fr": "règle|règles|exigences|obligatoire|important|sécurité|avertissement|avertissements|contraintes|principes|"
          "limites|quand utiliser|aperçu|processus|étapes|instructions|jamais|interdit",
    "de": "regel|regeln|anforderungen|pflicht|wichtig|sicherheit|warnung|warnungen|hinweise|einschränkungen|"
          "prinzipien|grenzen|wann verwenden|überblick|ablauf|prozess|schritte|anleitung|niemals|verboten",
    "it": "regola|regole|requisiti|obbligatorio|importante|sicurezza|avvertenze|vincoli|principi|limiti|quando usare|"
          "panoramica|processo|passi|passaggi|istruzioni|vietato",
    "nl": "regel|regels|vereisten|verplicht|belangrijk|veiligheid|waarschuwing|waarschuwingen|beperkingen|principes|"
          "wanneer gebruiken|overzicht|proces|stappen|instructies|nooit",
    "id": "aturan|wajib|penting|keamanan|keselamatan|peringatan|batasan|prinsip|kapan digunakan|ringkasan|proses|"
          "langkah|langkah-langkah|petunjuk|instruksi|jangan|larangan",
    "tr": "kural|kurallar|zorunlu|önemli|güvenlik|uyarı|uyarılar|kısıtlamalar|ilkeler|ne zaman kullanılır|genel bakış|"
          "süreç|adımlar|talimatlar|asla|yasak",
    "pl": "zasady|wymagania|wymagane|ważne|bezpieczeństwo|ostrzeżenia|ograniczenia|kiedy używać|przegląd|proces|"
          "kroki|instrukcje|nigdy",
    "ru": "правило|правила|требования|обязательно|важно|безопасность|предупреждение|предупреждения|ограничения|"
          "принципы|когда использовать|обзор|процесс|шаги|инструкция|инструкции|никогда|запрещено",
    "uk": "правила|вимоги|обов'язково|важливо|безпека|попередження|обмеження|принципи|коли використовувати|огляд|"
          "процес|кроки|інструкції|ніколи",
    "ar": "قواعد|القواعد|إلزامي|مطلوب|مهم|تنبيه|تحذير|تحذيرات|الأمان|السلامة|قيود|مبادئ|متى تستخدم|نظرة عامة|خطوات|"
          "الخطوات|تعليمات|ممنوع",
    "hi": "नियम|अनिवार्य|ज़रूरी|महत्वपूर्ण|सावधानी|चेतावनी|सुरक्षा|सीमाएँ|सिद्धांत|कब उपयोग करें|अवलोकन|प्रक्रिया|"
          "चरण|निर्देश|कभी नहीं",
    "ko": "규칙|필수|중요|주의|경고|안전|제한|원칙|사용 시기|언제 사용|개요|절차|단계|지침|금지",
    "zh": "规则|規則|规范|規範|必须|必須|注意|注意事项|須知|警告|安全|限制|原则|原則|何时使用|使用场景|概述|流程|步骤|步驟|"
          "说明|說明|禁止|切勿",
    "ja": "ルール|規則|必須|注意|注意事項|警告|安全|制限|原則|使うとき|使用するタイミング|概要|手順|流れ|禁止",
    "th": "กฎ|ข้อบังคับ|สำคัญ|ข้อควรระวัง|คำเตือน|ความปลอดภัย|ข้อจำกัด|หลักการ|เมื่อใดควรใช้|ภาพรวม|ขั้นตอน|คำแนะนำ|ห้าม",
}
# A line that makes something a precondition (point 2b): a "make" word and a "first / missing" word on one line.
MAKE_WORDS = {
    "en": "create|make|write|build|add", "vi": "tạo|ghi|viết|thêm", "es": "crea|crear|cree|escribe|añade",
    "pt": "crie|criar|cria|escreva|adicione", "fr": "crée|créer|créez|écris|écrivez|ajoute|ajoutez",
    "de": "erstelle|erstellen|erstellt|lege|anlegen|schreibe|füge", "it": "crea|creare|scrivi|aggiungi",
    "nl": "maak|aanmaken|schrijf|voeg", "id": "buat|membuat|tulis|tambahkan", "tr": "oluştur|oluşturun|yaz|ekle",
    "pl": "utwórz|stwórz|napisz|dodaj", "ru": "создай|создайте|создать|напиши|добавь", "uk": "створи|створіть|створити",
    "ar": "أنشئ|إنشاء|اكتب|أضف", "hi": "बनाएं|बनाएँ|बनाओ|लिखें|जोड़ें", "ko": "만들|생성|작성|추가",
    "zh": "创建|建立|新建|編寫|编写|添加", "ja": "作成|作る|作って|追加", "th": "สร้าง|เขียน|เพิ่ม",
}
FIRST_WORDS = {
    "en": "first|before|beforehand|missing|does not exist|doesn't exist|not exist|not yet exist",
    "vi": "trước|chưa tồn tại|chưa có", "es": "primero|antes|no existe|falta", "pt": "primeiro|antes|não existe|falta",
    "fr": "d'abord|avant|n'existe pas|manquant", "de": "zuerst|vorher|existiert nicht|fehlt", "it": "prima|non esiste",
    "nl": "eerst|vooraf|bestaat niet|ontbreekt", "id": "dulu|terlebih dahulu|belum ada|tidak ada",
    "tr": "önce|yoksa|mevcut değil", "pl": "najpierw|wcześniej|nie istnieje", "ru": "сначала|заранее|не существует|нет",
    "uk": "спочатку|заздалегідь|не існує", "ar": "أولا|أولاً|قبل|غير موجود", "hi": "पहले|मौजूद नहीं",
    "ko": "먼저|미리|존재하지 않|없으면", "zh": "先|之前|不存在|还没有", "ja": "先に|事前に|存在しない|まだない|なければ",
    "th": "ก่อน|ยังไม่มี|ไม่มี",
}
_ALWAYS_RE = _table_re(RULE_HEADINGS)
_MAKE_RE = _table_re(MAKE_WORDS)
_FIRST_RE = _table_re(FIRST_WORDS)


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
    # The shared frame of a menu, found from structure in any language: when the alternatives sit as level-3 parts
    # under a level-2 section, every level-2 section with no parts of its own (when to use, steps, safety) frames all
    # of them and is loaded with every selection.
    if any(u.has_children for u in units if u.level == 2):
        for u in units:
            if u.level == 2 and not u.has_children:
                u.always = True
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
    lines, pre_end, units = parse(text)
    cands = [n for n, u in enumerate(units) if not u.always and not (u.level == 2 and u.has_children)]
    if len(cands) < 2:
        return None
    bodies = {n: words(_unit_text(lines, units[n])) for n in cands}
    heads = {n: set(head_words(units[n].title)) for n in cands}
    df: dict[str, int] = {}
    for n in cands:
        for w in set(bodies[n]):
            df[w] = df.get(w, 0) + 1
    # Filler words of any language ("create", "please", "tạo", "crea", "作って") are found from the skill itself: a word
    # in more than half of its parts tells them apart no better than chance, so it cannot choose one.
    q = [w for w in dict.fromkeys(words(query)) if df.get(w, 0) * 2 <= len(cands)]
    if not q:
        return None

    def score(n: int) -> float:
        sc = 0.0
        for w in q:
            idf = math.log(1 + len(cands) / (1 + df.get(w, 0)))
            if any(same_word(w, h) for h in heads[n]):
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
    if not any(same_word(w, h) for w in q for h in heads[best_n]):
        return None
    picked = {n for n in cands if scores[n] > 0 and scores[n] >= KEEP_RATIO * best}
    if len(picked) > max(2, len(cands) // 2):
        return None
    picked |= _needs(lines, units, cands, picked)
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


def _needs(lines: list[str], units: list[Unit], cands: list[int], picked: set[int]) -> set[int]:
    """Candidates a picked part needs made first (point 2b): a line of the picked part with a "make" word, a "first /
    missing" word and the subject of another part, the first word of that part's heading ("Agent -> ..." -> agent)."""
    subject = {}
    for n in cands:
        w = head_words(units[n].title) or words(units[n].title)
        if w:
            subject[n] = w[0]
    extra: set[int] = set()
    for p in picked:
        own = subject.get(p)
        for line in lines[units[p].start:units[p].end]:
            f = fold(line)
            if not (_FIRST_RE.search(f) and _MAKE_RE.search(f)):
                continue
            toks = set(words(line))
            extra |= {c for c, w in subject.items()
                      if c not in picked and w != own and any(same_word(w, t) for t in toks)}
    return extra


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
