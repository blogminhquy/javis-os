"""Fix misheard words while the owner speaks, for the faded live bubble (2026-11-06).

Two passes, in order:
  1. Rules (nghe_sua.sua): known cases (Jarvis -> Javis, Javis OS, Groq/Grok...). Free, instant, and
     always there even with no model at all.
  2. Model: reads the sentence after the rules and fixes words the rules do not know, guided by the
     vocabulary. The model is picked in this order:
       - a Groq key is set: Groq (fast, cheap, already has a field on the Models page);
       - no Groq key: the BACKGROUND model (`model.auxiliary`), when it is an API with a key
         (OpenAI, OpenRouter, Gemini, DeepSeek, Groq);
       - the background model is Claude Code, Codex or another CLI: it cannot take a small one-off
         call like this, so the rules alone are used.

Safety rules of the model pass (a wrong fix is worse than a mishearing):
  - The model may only fix, not rewrite: the word count moves by at most a third, never empty.
  - Network error, timeout (3 seconds), odd answer: fall back to the rules, no error on screen.
  - Results are cached, the same sentence never calls the model twice.
  - Logs carry only measurements (length, source), never the owner's words.
"""
from __future__ import annotations

import sys

import httpx

import aux_engine
import model_routing
import nghe_sua

TIMEOUT_S = 3.0
_CACHE_MAX = 200
_cache: dict = {}

# chat/completions endpoint of each OpenAI-compatible API (same as engine.py).
_URLS = {
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    "deepseek": "https://api.deepseek.com/chat/completions",
}
_DEFAULT_MODELS = {
    "groq": "llama-3.3-70b-versatile",
    "openai": "gpt-4o-mini",
    "openrouter": "openai/gpt-4o-mini",
    "gemini": "gemini-2.5-flash",
    "deepseek": "deepseek-flash",
}

# Sent to the model, so it stays in the language the owner speaks.
SYSTEM_PROMPT = (
    "Bạn sửa lỗi máy nghe giọng nói, câu thường là tiếng Việt xen tiếng Anh. Chỉ sửa những từ bị "
    "nghe thành từ gần âm nhưng sai, ưu tiên tên riêng và thuật ngữ trong danh sách được cho. Giữ "
    "nguyên mọi chữ khác: không thêm, không bớt, không viết lại câu, không giải thích, không đổi "
    "dấu câu. Nếu không chắc thì giữ nguyên. Chỉ trả về đúng câu đã sửa."
)


def pick_model(cfg: dict):
    """(provider, api_key, model, url) of the fixing model, or None for rules only."""
    m = (cfg or {}).get("model") or {}
    if m.get("groq_api_key"):
        return ("groq", m["groq_api_key"], _DEFAULT_MODELS["groq"], _URLS["groq"])
    spec = model_routing.background_spec(m)
    provider = spec.get("provider") or ""
    if provider not in _URLS:
        return None
    key = m.get(aux_engine._KEY_FIELD.get(provider, "")) or ""
    if not key:
        return None
    return (provider, key, spec.get("model") or _DEFAULT_MODELS.get(provider, ""), _URLS[provider])


def is_safe_fix(original: str, fixed: str) -> bool:
    """The model output is only a fix: not empty, and the word count moves by at most a third."""
    if not fixed:
        return False
    n_orig = len(original.split())
    n_fixed = len(fixed.split())
    return abs(n_fixed - n_orig) <= max(1, n_orig // 3)


def _clean(text: str) -> str:
    t = (text or "").strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'“”":
        t = t[1:-1].strip()
    return " ".join(t.split())


async def _ask_model(pick, sentence: str, terms: list) -> str:
    provider, key, model, url = pick
    user = "Danh sách tên và thuật ngữ đúng chính tả: " + ", ".join(terms) + "\nCâu nghe được: " + sentence
    body = {
        "model": model,
        "temperature": 0,
        "max_tokens": min(400, 3 * len(sentence.split()) + 30),
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}],
    }
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
        r = await client.post(url, json=body, headers={"Authorization": "Bearer " + key})
        r.raise_for_status()
        return _clean(r.json()["choices"][0]["message"]["content"])


async def fix_transcript(cfg: dict, text) -> dict:
    """Return {"text": fixed sentence, "source": "rules" | <provider>, "ai": bool}.

    Never raises: any trouble falls back to the result of the rules.
    """
    original = str(text or "").strip()
    if not original:
        return {"text": "", "source": "rules", "ai": False}
    terms = nghe_sua.fix_vocabulary(cfg or {})
    by_rules = nghe_sua.sua(original, terms)
    pick = pick_model(cfg or {})
    if pick is None:
        return {"text": by_rules, "source": "rules", "ai": False}
    cache_key = (by_rules, pick[0], pick[2])
    if cache_key in _cache:
        return dict(_cache[cache_key])
    try:
        fixed = await _ask_model(pick, by_rules, terms)
    except Exception as e:  # network, timeout, bad key, odd JSON: never break the bubble
        print(f"[transcript_fix] model {pick[0]} failed: {type(e).__name__}", file=sys.stderr)
        return {"text": by_rules, "source": "rules", "ai": False}
    if not is_safe_fix(by_rules, fixed):
        print(f"[transcript_fix] model {pick[0]} rewrote the sentence, kept the rules ({len(by_rules)} chars)",
              file=sys.stderr)
        return {"text": by_rules, "source": "rules", "ai": False}
    result = {"text": fixed, "source": pick[0], "ai": True}
    if len(_cache) >= _CACHE_MAX:
        _cache.clear()
    _cache[cache_key] = result
    return dict(result)
