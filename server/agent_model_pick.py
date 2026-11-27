"""agent_model_pick.py - pick a model for a NEW assistant from the models this machine can run (owner, 27/11/2026).

Owner: "nếu mà tự tạo agent hoặc là cài đặt agent vào thì hãy tự lựa chọn theo các mô hình có sẵn ở trong máy để mà
cài đặt cho phù hợp". Before, an assistant made from chat, installed from the Store or learned by Javis was left on
"Default", so it ran whatever the main card ran, whatever its work.

Two steps, both plain rules so the result is the same every time and says why:

1. `tier_of`: how heavy the assistant's work is, read from its name, role, group, tags, skills and the start of its
   instructions. "deep" for code, security, data, finance, law, research; "light" for customer care, translation,
   notes, reminders; "standard" for everything else (marketing, writing, sales, customer care: what a customer
   reads decides a sale, so customer care is not put on the lightest line).
2. `pick`: the first card in the owner's usage order that an assistant can run on, then the model of that tier on it.
   - Claude has one model line per tier (Opus, Sonnet, Haiku), the CLI's own aliases, so the tier picks the line.
   - Every other card (ChatGPT through Codex, Antigravity, Grok Build, API keys) uses the two picks the main brain
     made from that account's OWN model list (`model.auto_background`, auto_background.py): "light" for light work,
     "mid" for standard work. Heavy work runs the model the owner set on the card. Owner, 27/11/2026: the same for
     Codex, Antigravity and Grok Build, not only Claude Code. No model name is written here for these cards: their
     names change faster than Javis ships (the rule auto_background.py already follows).
   - A card with no picks yet keeps the model set on it for every tier; the tier still sets the thinking level.
   The usage order is never changed.

This module never imports main; main hands it the cards (`main._agent_model_cards`).
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

TIERS = ("deep", "standard", "light")

# Groups the Store and Javis use for assistants. A group says more than a word in the text, so it decides on its own.
GROUP_TIER = {
    "lập trình": "deep", "bảo mật": "deep", "kiểm thử": "deep", "làm game": "deep", "bản đồ gis": "deep",
    "điện toán không gian": "deep", "học thuật": "deep", "tài chính": "deep", "y tế": "deep", "nghiên cứu": "deep",
    "ai": "deep", "dữ liệu": "deep", "pháp lý": "deep",
    "chăm sóc khách hàng": "standard", "cskh": "standard",
    "marketing": "standard", "thiết kế": "standard", "bán hàng": "standard", "quảng cáo trả phí": "standard",
    "quản lý dự án": "standard", "sản phẩm": "standard", "vận hành": "standard", "nội dung": "standard",
}

DEEP_WORDS = (
    "code", "coding", "coder", "developer", "engineer", "engineering", "programmer", "programming", "software",
    "backend", "frontend", "full-stack", "devops", "database", "sql", "api", "architect", "architecture",
    "security", "pentest", "penetration", "vulnerability", "debug", "refactor", "code review", "reviewer",
    "data", "analyst", "analytics", "machine learning", "statistics", "statistician", "research", "researcher",
    "finance", "financial", "accounting", "accountant", "tax", "audit", "legal", "lawyer", "contract", "compliance",
    "strategy", "strategist", "investment", "medical", "clinical", "scientist", "math",
    "lập trình", "kỹ sư", "kiến trúc", "bảo mật", "lỗ hổng", "dữ liệu", "phân tích", "thống kê", "nghiên cứu",
    "tài chính", "kế toán", "thuế", "kiểm toán", "pháp lý", "luật sư", "hợp đồng", "tuân thủ", "chiến lược",
    "đầu tư", "y khoa", "khoa học", "review code", "sửa lỗi code", "viết code",
)
LIGHT_WORDS = (
    "translator", "translate", "translation", "reminder", "note taker", "note-taking", "faq", "scheduling",
    "appointment", "meeting notes",
    "phiên dịch", "dịch thuật", "nhắc việc", "nhắc lịch", "ghi chú", "biên bản", "đặt lịch", "hỏi đáp", "tóm tắt tin",
)

# Claude's model lines per tier: aliases the Claude Code binary understands, always the newest of each line.
CLAUDE_CLI_TIER = {"deep": "opus", "standard": "sonnet", "light": "haiku"}
CLAUDE_FAMILY = CLAUDE_CLI_TIER
# Thinking level per tier, written only when the assistant has none of its own ("standard" keeps the default).
TIER_REASONING = {"deep": "high", "light": "low"}

HEAD_WEIGHT = 3      # a word in the name, role, group, tags or skills counts three times a word in the instructions
BODY_CHARS = 1500    # only the start of the instructions is read: that is where an assistant says what it is
MIN_SCORE = 3


def _words_re(words: Iterable[str]) -> re.Pattern:
    alts = sorted({w.strip().lower() for w in words if w.strip()}, key=len, reverse=True)
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(w) for w in alts) + r")(?!\w)")


_DEEP_RE = _words_re(DEEP_WORDS)
_LIGHT_RE = _words_re(LIGHT_WORDS)


def _as_list(v) -> list:
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v if x is not None]
    return [str(v)] if v else []


def tier_of(meta: Optional[dict], body: str = "") -> str:
    """'deep', 'standard' or 'light' for one assistant. Read only, no model call."""
    meta = meta or {}
    group = str(meta.get("group") or "").strip().lower()
    groups = [group] + [t.strip().lower() for t in _as_list(meta.get("tags"))]
    for g in groups:
        if g in GROUP_TIER:
            return GROUP_TIER[g]
    head = " \n".join([str(meta.get("name") or ""), str(meta.get("role") or ""), str(meta.get("description") or ""),
                       group] + _as_list(meta.get("tags")) + _as_list(meta.get("skills"))).lower()
    text = str(body or "")[:BODY_CHARS].lower()
    deep = HEAD_WEIGHT * len(_DEEP_RE.findall(head)) + len(_DEEP_RE.findall(text))
    light = HEAD_WEIGHT * len(_LIGHT_RE.findall(head)) + len(_LIGHT_RE.findall(text))
    if deep >= MIN_SCORE and deep > light:
        return "deep"
    if light >= MIN_SCORE and light > deep:
        return "light"
    return "standard"


def _family_model(models, family: str) -> str:
    """First model id of a Claude line in a card's list (newest first in the lists Javis ships)."""
    for m in models or ():
        s = str(m or "")
        if family in s.lower():
            return s
    return ""


def _from_picks(tier: str, picks, models) -> str:
    """The pick for `tier` on a card that is not Claude: "light" (or "mid" when there is no light one) for light work,
    "mid" for standard work, "" for heavy work (the card's own model then). A pick no longer in the card's known list
    is not used: the list changed since it was made."""
    picks = picks if isinstance(picks, dict) else {}
    if tier == "light":
        want = [picks.get("light"), picks.get("mid")]
    elif tier == "standard":
        want = [picks.get("mid")]
    else:
        return ""
    known = {str(m) for m in (models or ())}
    for w in want:
        w = str(w or "").strip()
        if w and (not known or w in known):
            return w
    return ""


def pick(tier: str, cards) -> dict:
    """{provider, model, tier} on the first card that has a model for `tier`, or {} when no card can run it.

    `cards`: [{"provider", "model", "models", "picks"}] in the owner's usage order, only cards an assistant can run
    on; `model` is the model the card runs (its own setting, or the name of its default), `models` its known list,
    `picks` the {"light", "mid"} the main brain chose from that account's list (may be empty)."""
    tier = tier if tier in TIERS else "standard"
    for c in cards or ():
        prov = str((c or {}).get("provider") or "").strip()
        if not prov:
            continue
        if prov == "anthropic-cli":
            model = CLAUDE_CLI_TIER[tier]
        elif prov == "anthropic-api":
            model = _family_model(c.get("models"), CLAUDE_FAMILY[tier]) or str(c.get("model") or "")
        else:
            model = _from_picks(tier, c.get("picks"), c.get("models")) or str(c.get("model") or "")
        model = model.strip()
        if model:
            return {"provider": prov, "model": model, "tier": tier}
    return {}


def choose(meta: Optional[dict], body: str, cards) -> dict:
    """The frontmatter keys to add to a NEW assistant that has no model: {model, model_provider[, reasoning]}.

    {} when it already has a model (the owner's or the pack's choice is kept) or no card can run it (it stays on
    "Default", as before). A thinking level is added only when the assistant has none of its own."""
    meta = meta or {}
    if str(meta.get("model") or "").strip():
        return {}
    tier = tier_of(meta, body)
    got = pick(tier, cards)
    if not got:
        return {}
    out = {"model": got["model"], "model_provider": got["provider"]}
    if tier in TIER_REASONING and not str(meta.get("reasoning") or "").strip():
        out["reasoning"] = TIER_REASONING[tier]
    return out
