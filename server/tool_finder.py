"""Find the right tool in a large pool from a short request, in Vietnamese or English.

The lazy tier of the hub (mcp_hub) hides hundreds of tool schemas behind one search tool, so a turn pays for a
tool only when it needs one. That saving is worth nothing when the search comes back with the wrong tools: the
model searches again, every round carries the whole context, and after two misses it gives up and says the
source cannot do it. Measured on a real brain (778 tools, 55 everyday requests) the old word count found the
right tool for 20 of them.

Why it missed, and what this module does about each:

  - The request is Vietnamese, the tool descriptions are English. "doanh thu", "lịch sử tin nhắn", "chi phí"
    never appear in a description, so nothing matched, or only the tools of a source whose LABEL happened to
    contain one of the syllables ("thu" of "doanh thu" matched the account "Ngọc Thu"). CONCEPTS below maps
    the common business words of both languages to the English words tool authors use. A phrase the map knows
    is consumed whole, so its syllables cannot match anything on their own.
  - Every word counted the same. "list" and "get" are in half the pool; "history" is in a handful. Words are
    weighted by how rare they are in this pool (BM25), and a word in the tool's own name counts three times.
  - Long descriptions won by being long. BM25 normalises by length, so the skill loader, whose description
    lists dozens of skills, stops coming first for every request.
  - Naming a source did little. A request that names a source ("zalo", "Làng Chài Xưa", "google ads") now
    ranks that source's tools first and only shows other sources when they match the request better.
  - Several accounts of one kind (three POS shops, three Zalo accounts) carry identical tools, so a search
    returned the same tool three times and the useful second and third tools fell off the list. Identical
    tools are grouped: shown once, with the other accounts named next to it.
  - A request that only names a source, or matches nothing, returned nothing useful. The first now lists the
    source's tools by name; the second retries with spelling-corrected words before giving up.

Pure functions over plain dicts: no I/O, no hub state, so tests feed it a pool directly.
"""
from __future__ import annotations

import difflib
import math
import re
import unicodedata
from collections import Counter, defaultdict

# ---------------------------------------------------------------------------------------------------------------
# Text normalisation
# ---------------------------------------------------------------------------------------------------------------
_SPLIT_RE = re.compile(r"[^0-9a-z]+")
_CAMEL_RE = re.compile(r"([a-z0-9])([A-Z])")


def fold(text: str) -> str:
    """Lowercase, no diacritics, đ -> d. "Làng Chài Xưa" and "lang chai xua" fold to the same string."""
    text = str(text or "").replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.lower()


def stem(word: str) -> str:
    """Plural to singular, the only inflection that matters for tool names (orders/order, posts/post)."""
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def words(text: str) -> list:
    """Folded, stemmed words of 2+ characters. Splits snake_case, kebab-case and camelCase."""
    text = _CAMEL_RE.sub(r"\1 \2", str(text or ""))
    return [stem(w) for w in _SPLIT_RE.split(fold(text)) if len(w) >= 2]


# ---------------------------------------------------------------------------------------------------------------
# Concepts: what people ask for, in the words tool authors use
# ---------------------------------------------------------------------------------------------------------------
# Key: a phrase as people type it, folded (no diacritics). Value: English words found in tool names and
# descriptions. Longest phrase wins, so "don hang" is read before "hang" and "lich su" before "lich".
# Keep entries generic (business, messaging, content, files, web): a brain can connect any source.
_CONCEPT_ROWS = [
    # sales and reporting
    ("doanh thu|doanh so|ban duoc|revenue|sale|sales|turnover", "revenue sale statistic analytic report total"),
    ("bao cao|thong ke|so lieu|chi so|report|statistic|statistics|analytics|metric|metrics",
     "report statistic analytic metric"),
    ("loi nhuan|lai lo|profit", "profit revenue report"),
    ("chi phi|chi tieu|tieu bao nhieu|ngan sach|cost|spend|budget", "cost spend budget metric report"),
    ("don hang|don|order|orders", "order"),
    ("chot don|len don|tao don", "order create"),
    ("chua giao|dang giao|giao hang|van chuyen|ship|shipping|delivery", "shipping delivery shipment status order"),
    ("tra hang|hoan hang|hoan tien|refund|return", "refund return"),
    ("khach hang|khach|nguoi mua|customer|buyer|client", "customer contact"),
    ("lien he|danh ba|contact|contacts", "contact"),
    ("san pham|mat hang|hang hoa|product|item|sku", "product item variation"),
    ("ton kho|kho hang|kho|inventory|stock|warehouse", "inventory stock warehouse"),
    ("chuyen kho|transfer", "transfer warehouse"),
    ("kiem kho|kiem ke|stocktake|stocktaking", "stocktaking inventory"),
    ("nhap hang|mua hang|nha cung cap|purchase|supplier|vendor", "purchase supplier"),
    ("gia ban|gia|price|pricing", "price"),
    ("khuyen mai|giam gia|uu dai|promotion|discount", "promotion discount coupon"),
    ("ma giam gia|voucher|coupon", "voucher coupon promotion"),
    ("doi soat|cong no|thu chi|so quy|giao dich|reconciliation|transaction|debt|payment|thanh toan",
     "reconciliation transaction payment debt"),
    ("hoa don dien tu|e invoice|einvoice", "invoice e_invoice"),
    ("hoa don|invoice|bill", "invoice"),
    ("combo|bundle", "combo bundle"),
    ("livestream|live", "livestream live"),
    ("san thuong mai dien tu|shopee|lazada|tiktok shop|marketplace", "commerce marketplace"),
    # people and conversations
    ("tin nhan|nhan tin|message|messages|chat|inbox", "message conversation chat inbox"),
    ("lich su|history|qua khu", "history"),
    ("cuoc tro chuyen|hoi thoai|thread|conversation", "thread conversation chat"),
    ("nhom|group", "group thread"),
    ("ban be|ket ban|friend", "friend"),
    ("thanh vien|member", "member"),
    ("binh luan|comment|comments", "comment"),
    ("tra loi|phan hoi|reply|respond", "reply"),
    ("nhac den|mention", "mention"),
    ("cam xuc|tha tim|reaction|react", "reaction"),
    ("nguoi theo doi|follower|followers", "follower"),
    ("email|e mail|thu dien tu|mail|gmail", "email mail message"),
    ("ban tin|newsletter", "newsletter"),
    ("goi dien|cuoc goi|call", "call"),
    # content and publishing
    ("bai dang|bai viet|post|posts|article", "post article"),
    ("dang bai|dang len|publish", "post / publish create"),
    ("len lich|hen gio|dat lich|schedule", "schedule scheduled"),
    ("bi loi|that bai|loi|failed|error", "failed error"),
    ("gio dang tot nhat|gio tot nhat|thoi diem tot nhat|best time", "best time"),
    ("hinh anh|buc anh|image|photo|picture", "image photo media"),
    ("video|clip", "video media"),
    ("tep|file|tai lieu|document", "file document"),
    ("blog", "post blog"),
    ("viet bai|soan bai|tao bai|viet blog|write post|write article", "post / create write"),
    ("wordpress", "wp wordpress"),
    ("woocommerce|woo", "wc woocommerce"),
    ("trang web|website|web site", "website site web page"),
    ("trang|page", "page"),
    ("danh muc|chuyen muc|category", "category"),
    ("the tag|gan the|tag|nhan dan|label", "tag label"),
    # marketing
    ("quang cao|ads|advert|advertising", "ad ads campaign"),
    ("chien dich|campaign", "campaign"),
    ("pheu|funnel", "funnel"),
    ("khoa hoc|course", "course"),
    ("bai hoc|lecture|lesson", "lecture"),
    ("tu dong|tu dong hoa|automation|workflow", "automation workflow rule"),
    ("tu khoa|keyword", "keyword"),
    ("tu choi|bi chan|vi pham|disapproved|issue|issues", "issue disapproved status problem"),
    # web, files, accounts
    ("chup man hinh|screenshot|anh chup", "screenshot"),
    ("trinh duyet|browser", "browser"),
    ("mo trang|vao trang|truy cap|navigate|open url", "navigate browser"),
    ("bam|click", "click"),
    ("dien form|dien bieu mau|form", "form fill"),
    ("tim tren web|tim kiem web|tren mang|internet|google search|web search", "web search"),
    ("duong link|lien ket|url|link", "url fetch link"),
    ("bang tinh|spreadsheet|sheet|excel", "sheet spreadsheet"),
    ("dong|row|rows", "row"),
    ("cot|column", "column"),
    ("cell|o tinh", "cell"),
    ("bieu do|chart", "chart"),
    ("ten mien|domain|dns", "domain dns"),
    ("hosting|may chu|server|vps", "hosting server"),
    ("tai khoan|account|accounts", "account"),
    ("ket noi|nguon|connection|connector|source", "connection source"),
    ("ky nang|skill|skills", "skill"),
    ("lich|calendar|cuoc hen|appointment|event", "calendar event"),
    ("cai dat|thiet lap|setting|settings|config", "setting config"),
    ("nguoi dung|user", "user"),
    ("webhook", "webhook"),
    ("xuat file|export", "export"),
    # actions
    ("xem|doc|lay|kiem tra|get|read|fetch|show|view|check", "get read fetch show view"),
    ("liet ke|danh sach|tat ca|list|all", "list"),
    ("tim|tim kiem|tra cuu|search|find|lookup", "search find"),
    ("tao|them|tao moi|create|add|new", "create add"),
    ("sua|cap nhat|doi|chinh|update|edit|change|modify", "update edit"),
    ("xoa|go|huy|delete|remove|cancel", "delete remove cancel"),
    ("gui|send", "send"),
    ("nap|dung|su dung|load|use", "use load"),
    ("ghi|ghi them|ghi vao|write|append|insert", "write add update append"),
    ("chia se|share", "share"),
    ("tai len|upload", "upload"),
    ("tai ve|tai xuong|download", "download"),
    ("phan tich|analyze|analyse", "analyze analytic"),
    ("so sanh|compare", "compare"),
    ("dang ky|subscribe|sign up", "subscribe"),
    ("theo ten|bang ten|by name", "name"),
]


def _build_concepts():
    """phrase -> groups. An expansion is one group of synonyms, or several separated by "/" when the phrase asks
    for two things at once ("dang bai" = a post AND publishing it)."""
    table = {}
    for keys, expands in _CONCEPT_ROWS:
        out = tuple(tuple(dict.fromkeys(stem(w) for w in part.split())) for part in expands.split("/") if part.strip())
        for k in keys.split("|"):
            k = " ".join(stem(w) for w in fold(k).split())
            if k:
                table[k] = table.get(k, ()) + out
    return table


CONCEPTS = _build_concepts()
_MAX_PHRASE = max(len(k.split()) for k in CONCEPTS)

# Words that carry no intent: time, filler, pronouns, in both languages. Folded and stemmed.
_STOP = {stem(w) for w in fold(
    "hom nay hom qua ngay mai tuan nay tuan truoc thang nay thang truoc nam nay ngay tuan thang nam gio phut "
    "cua cho cac nhung trong ngoai tren duoi vao ra tu den ve voi va hoac la co khong duoc nao dang da se "
    "len xuong bang theo nay kia do mot hai ba toi anh em minh chi ban giup hay nhe di thi ma nhu rat qua "
    "can muon dung cai con nguoi viec gi sao the nao bao nhieu "
    "the a an of for to in on at by with and or is are be this that these last next today yesterday "
    "tomorrow week month year day days hour please me my our your it its from into about"
).split()}

# Names of the meta tools themselves: never results.
META = {"javis_search_tools", "javis_run_tool"}


def parse_query(query: str):
    """(groups, source_words).

    groups: [(word, ...)] one tuple per thing asked for; the words of a tuple are alternatives (synonyms), so a
    tool scores for the best of them, not for each, and a long description that happens to say both
    "create" and "add" does not count the request twice.
    source_words: words that may name a source: words outside any concept phrase, plus a concept that is a
    single word ("ads", "website", "sheet"). The syllables of a longer phrase never name a source, so the
    "thu" of "doanh thu" cannot pick the account "Ngọc Thu"."""
    toks = [stem(w) for w in _SPLIT_RE.split(fold(query)) if w]
    groups = []
    loose = []
    i = 0
    while i < len(toks):
        hit = None
        for n in range(min(_MAX_PHRASE, len(toks) - i), 0, -1):
            phrase = " ".join(toks[i:i + n])
            if phrase in CONCEPTS:
                hit = (n, phrase)
                break
        if hit:
            n, phrase = hit
            cgroups = [list(g) for g in CONCEPTS[phrase]]
            if n > 1:
                # The phrase's own words too: many tools (local plugins) describe themselves in Vietnamese, and
                # "doanh thu" must still reach a description that says "doanh thu". Alternatives of the first
                # group, so they never count twice and never name a source.
                cgroups[0].extend(w for w in toks[i:i + n] if len(w) >= 2 and w not in cgroups[0])
            if n == 1 and len(phrase) >= 3:
                # The word itself, when it is a word a tool can carry verbatim ("order", "ads").
                if not any(phrase in g for g in cgroups):
                    cgroups[0].append(phrase)
                loose.append(phrase)
            groups.extend(tuple(g) for g in cgroups)
            i += n
            continue
        w = toks[i]
        i += 1
        if len(w) < 2 or w in _STOP or w.isdigit():
            continue
        loose.append(w)
        groups.append((w,))
    # A word counts once: "viet bai blog" asks for a post twice ("bai", "blog") but means one post.
    seen = set()
    out = []
    for g in groups:
        g = tuple(w for w in g if w not in seen)
        if g:
            seen.update(g)
            out.append(g)
    return out, loose


# ---------------------------------------------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------------------------------------------
_K1 = 1.2
_B = 0.75
# A named source with at most this many distinct tools is listed whole after its hits: a request that names a
# small source then never misses its tool, whatever words it used.
_SMALL_SCOPE = 16
# A source whose tools' descriptions mostly say a word nobody else says ("wordpress") is hinted by it: its tools
# get this boost when the request has the word but names no source outright.
_KEYWORD_BOOST = 1.3
_W_NAME = 2.0      # flat bonus for a word in the tool's own name, against at most 2.2 from the description
_DESC_HEAD = 1500  # the part of a description that says what the tool does; the rest is argument detail


def _is_email(s: str) -> bool:
    return "@" in str(s or "")


class Index:
    """BM25 over one pool, built once per pool and reused by every search of it."""

    def __init__(self, pool, source_desc=None):
        # A meta tool may come with a source prefix ("javis__javis_search_tools"): judged by its tool part.
        self.pool = [t for t in pool if str(t.get("fn") or "").split("__")[-1] not in META]
        source_desc = source_desc or {}
        self.docs = []
        df = Counter()
        lengths = []
        self.sources = {}            # namespace -> {"words": set, "label": str}
        for t in self.pool:
            ns = str(t.get("namespace") or t.get("server") or "")
            name = str(t.get("name") or t.get("fn") or "")
            fn = str(t.get("fn") or "")
            name_w = Counter(words(name))
            # fn may carry a shortened namespace prefix; its tool part is the name again.
            for w in words(fn.split("__")[-1]):
                name_w.setdefault(w, 1)
            desc_w = Counter(words(str(t.get("description") or "")[:_DESC_HEAD]))
            self.docs.append((t, name_w, desc_w, ns))
            for w in set(name_w) | set(desc_w):
                df[w] += 1
            lengths.append(sum(desc_w.values()) + sum(name_w.values()))
            if ns not in self.sources:
                label = str(t.get("label") or "")
                sw = set(words(ns.replace("-", " ")))
                if label and not _is_email(label):
                    sw |= set(words(label))
                self.sources[ns] = {"words": sw, "label": label or ns,
                                    "desc": set(words(source_desc.get(ns) or t.get("group_desc") or ""))}
        self.n = max(1, len(self.docs))
        self.avg_len = (sum(lengths) / len(lengths)) if lengths else 1.0
        self.idf = {w: math.log(1 + (self.n - c + 0.5) / (c + 0.5)) for w, c in df.items()}
        # Words a source is named by, and how many sources share each one ("zalo" names three accounts).
        self.source_df = Counter(w for s in self.sources.values() for w in s["words"])
        self.vocab = set(df) | set(self.source_df)
        # Words that mark a source without naming it: in at least 40% of its tools (3 or more tools) and
        # almost nowhere else.
        per_ns = defaultdict(Counter)
        ns_size = Counter()
        for _t, name_w, desc_w, ns in self.docs:
            ns_size[ns] += 1
            for w in set(name_w) | set(desc_w):
                per_ns[ns][w] += 1
        for ns, cnt in per_ns.items():
            keys = set()
            for w, c in cnt.items():
                if c >= 3 and c >= 0.4 * ns_size[ns] and c >= 0.8 * df[w] and w not in _STOP and len(w) >= 3:
                    keys.add(w)
            self.sources[ns]["keys"] = keys

    # --- scoring -----------------------------------------------------------------------------------------------
    def _tool_score(self, doc, groups):
        """(score, groups matched). Each group scores its best word: idf x (a flat bonus when the word is in
        the tool's own name + saturated BM25 over the description). The name bonus is flat on purpose: under
        BM25 saturation a word repeated in a long description would otherwise outweigh the name."""
        _t, name_w, desc_w, _ns = doc
        dl = sum(desc_w.values())
        norm = _K1 * (1 - _B + _B * dl / self.avg_len)
        score = 0.0
        matched = 0
        for alts in groups:
            best = 0.0
            for w in alts:
                idf = self.idf.get(w)
                if not idf:
                    continue
                tf = desc_w.get(w, 0)
                v = idf * ((_W_NAME if w in name_w else 0.0) + (tf * (_K1 + 1) / (tf + norm) if tf else 0.0))
                if v > best:
                    best = v
            if best:
                matched += 1
                score += best
        return score, matched

    def named_sources(self, loose):
        """Namespaces the request names, best first: {ns: score}. A word shared by many sources ("google")
        counts for less than one that names a single source ("ads"), and a word that also appears in many
        tool descriptions counts for little at all."""
        if not loose:
            return {}
        out = {}
        for ns, s in self.sources.items():
            sc = 0.0
            for w in loose:
                if w in s["words"]:
                    sc += 1.0 / self.source_df[w]
            if sc:
                out[ns] = sc
        if not out:
            return {}
        best = max(out.values())
        return {ns: sc for ns, sc in out.items() if sc >= best - 1e-9}

    def _correct(self, loose):
        """Spelling-corrected words of the request ("zlao" -> "zalo"), only those that changed."""
        fixed = {}
        vocab = sorted(self.vocab)
        for w in loose:
            if w in self.vocab or len(w) < 4:
                continue
            m = difflib.get_close_matches(w, vocab, n=1, cutoff=0.8)
            if m:
                fixed[w] = m[0]
        return fixed

    def search(self, query: str):
        """Ranked result for one request: dict(hits=[(tool, score)], scope=[ns], browse=bool, other=[...]).
        hits are in-scope tools that match the request; browse=True means the request only named a source,
        so hits are that source's tools in their own order; other are better matches outside the scope."""
        q = str(query or "").strip()
        if not q:
            return {"hits": [], "scope": [], "browse": False, "other": []}
        # Asked for by exact name (full fn, or the tool name alone): those first, nothing else needed.
        fq = q.lower()
        exact = [d[0] for d in self.docs if fq in (str(d[0].get("fn") or "").lower(),
                                                    str(d[0].get("name") or "").lower())]
        if exact:
            return {"hits": [(t, 100.0) for t in exact], "scope": [], "browse": False, "other": []}

        groups, loose = parse_query(q)
        scope = self.named_sources(loose)
        if not scope:
            fixed = self._correct(loose)
            if fixed:
                loose = [fixed.get(w, w) for w in loose]
                groups = [tuple(fixed.get(w, w) for w in g) for g in groups]
                scope = self.named_sources(loose)
        # Words that only named the source do not also score tools: "zalo" is in every Zalo tool and says
        # nothing about which one.
        src_words = set()
        for ns in scope:
            src_words |= self.sources[ns]["words"]
        tool_groups = [g for g in (tuple(w for w in g if w not in src_words) for g in groups) if g]

        hinted = set()
        if not scope:
            lw = set(loose)
            hinted = {ns for ns, src in self.sources.items() if lw & src.get("keys", set())}
        scored = []
        for doc in self.docs:
            s, m = self._tool_score(doc, tool_groups) if tool_groups else (0.0, 0)
            if s > 0:
                if doc[3] in hinted:
                    s *= _KEYWORD_BOOST
                scored.append((s, m, doc))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

        if scope:
            inside = [(d[0], s) for s, m, d in scored if d[3] in scope]
            if not inside:
                # The request named a source and nothing else that matches: show what that source has.
                listing = [(d[0], 0.0) for d in self.docs if d[3] in scope]
                return {"hits": listing, "scope": list(scope), "browse": True, "other": []}
            best_in = inside[0][1]
            other = [(d[0], s) for s, m, d in scored if d[3] not in scope and s > best_in * 1.25][:3]
            hits = _cut(inside)
            rest = []
            in_scope = [d[0] for d in self.docs if d[3] in scope]
            if len({group_key(t) for t in in_scope}) <= _SMALL_SCOPE:
                shown = {id(t) for t, _s in hits}
                rest = [(t, 0.0) for t in in_scope if id(t) not in shown]
            return {"hits": hits, "scope": list(scope), "browse": False, "other": other, "rest": rest}

        hits = [(d[0], s) for s, m, d in scored]
        if not hits and groups:
            # Nothing in the tools: maybe a source's own description knows the words ("doanh thu" for a POS).
            by_desc = {}
            for ns, s in self.sources.items():
                k = sum(1 for g in groups if any(w in s["desc"] for w in g))
                if k:
                    by_desc[ns] = k
            if by_desc:
                top = max(by_desc.values())
                scope = [ns for ns, k in by_desc.items() if k == top]
                listing = [(d[0], 0.0) for d in self.docs if d[3] in scope]
                return {"hits": listing, "scope": scope, "browse": True, "other": []}
        return {"hits": _cut(hits), "scope": [], "browse": False, "other": []}


def _cut(hits):
    """Drop the long tail: a hit under a quarter of the best one was only there because the list had room."""
    if not hits:
        return hits
    floor = hits[0][1] / 4
    return [h for h in hits if h[1] >= floor]


# ---------------------------------------------------------------------------------------------------------------
# Grouping identical tools of several accounts
# ---------------------------------------------------------------------------------------------------------------
def group_key(t):
    return (str(t.get("name") or ""), str(t.get("description") or "")[:400])


def group_hits(hits):
    """[(tool, score)] -> [[tool, ...]] keeping order: tools with the same name and description from
    several accounts become one group whose first member is the best ranked one."""
    groups = {}
    order = []
    for t, _s in hits:
        k = group_key(t)
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(t)
    return [groups[k] for k in order]


def suggest_names(name: str, fns, labels=None, limit=5):
    """Tool names close to a name that does not exist, for javis_run_tool. Matches the tool part of the
    name first ("zalo_get_history" -> every account's "<ns>__zalo_get_history"), then spelling."""
    labels = labels or {}
    n = str(name or "").strip()
    if not n:
        return []
    tail = n.split("__")[-1].lower()
    same = [f for f in fns if f.lower().split("__")[-1] == tail]
    if same:
        return same[:limit]
    close = difflib.get_close_matches(n, list(fns), n=limit, cutoff=0.6)
    if close:
        return close
    tails = defaultdict(list)
    for f in fns:
        tails[f.lower().split("__")[-1]].append(f)
    out = []
    for m in difflib.get_close_matches(tail, list(tails), n=limit, cutoff=0.6):
        out.extend(tails[m])
    return out[:limit]
