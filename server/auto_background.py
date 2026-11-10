"""Automatic background model (owner, 10/11/2026): pick the two models background work runs on.

Javis used to run every background job on the provider's default model, which on a plan is the
strongest and most expensive one. With `model.auxiliary.auto` on, two picks per provider replace it
(see model_routing.background_spec): `light` for the work Javis starts on its own, `mid` for the
work the owner handed over.

How the picks are made, and why this file holds no table of model names. Names change faster than
Javis ships: a rule keyed on a name was already wrong for the ChatGPT plan the day it was
proposed. So the choice is made from the list the PROVIDER gives this account (ids, plus its own
descriptions and prices when it sends them), read once by the main brain, which may answer "I do not
know" for either slot. No answer, or an id that is not in the list, means no pick, and background
work then runs MAIN's own model, exactly as it did before this file existed.

When it runs again: only when the provider's list changed (a new model, a plan that opens more
models, a model taken away), detected by `signature`. A choice the owner made by hand is never
replaced; `model_routing.background_auto` decides that, not this module.

Pure helpers plus one coroutine; the host (main.py) passes in how to fetch a list and how to ask the
main brain, so tests need neither a network nor an engine.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Awaitable, Callable, Optional

# A list longer than this is a marketplace (OpenRouter lists hundreds), not one vendor's line-up: too
# long to rank in one short call, and its owner pays per token and picks models knowingly.
MAX_MODELS = 60
DESCRIPTION_MAX = 200
TIERS = ("light", "mid")

# How often the provider's list is fetched again to look for a change (the fetch costs no tokens), and
# how soon a failed attempt is tried again.
RECHECK_S = 24 * 3600
RETRY_S = 3600


def normalize(models) -> list:
    """[{id, description, price}] from ids or dicts, order kept, duplicates and blanks dropped."""
    out, seen = [], set()
    for x in models or []:
        if isinstance(x, dict):
            mid = str(x.get("id") or "").strip()
            desc = str(x.get("description") or "").strip()
            price = str(x.get("price") or "").strip()
        else:
            mid, desc, price = str(x or "").strip(), "", ""
        if not mid or mid in seen:
            continue
        seen.add(mid)
        out.append({"id": mid, "description": " ".join(desc.split())[:DESCRIPTION_MAX], "price": price[:60]})
    return out


def signature(models) -> str:
    """Changes exactly when the list a pick was made from changes (ids, descriptions or prices)."""
    rows = sorted((m["id"], m["description"], m["price"]) for m in normalize(models))
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def build_prompt(provider_label: str, models, main_model: str) -> str:
    rows = []
    for m in normalize(models):
        line = "- " + m["id"]
        if m["description"]:
            line += " | " + m["description"]
        if m["price"]:
            line += " | price: " + m["price"]
        rows.append(line)
    return (
        "You are configuring an assistant app. Below is the list of models the provider \""
        + str(provider_label or "") + "\" offers to this account, exactly as the provider lists them "
        "(the id, then the provider's own description and price when it gives them).\n"
        "The main chat model is: " + (str(main_model or "").strip() or "(the provider's default)") + "\n\n"
        "First order the chat models of the list from lightest to heaviest, stopping at the main chat model "
        "(leave out anything heavier than it, and anything you cannot place). That is the \"ladder\": background "
        "jobs start low on it and climb only when a lighter model fails them.\n"
        "Then pick two starting points from the ladder:\n"
        "- \"light\": the lightest, cheapest model that still follows instructions and returns short JSON. "
        "It does small text jobs: turning a chat into memory notes, suggesting a next message, sorting an error.\n"
        "- \"mid\": a middle model, cheaper than the main chat model when the list has one, and reliable enough "
        "to carry out a multi-step job with tools on its own (a scheduled job that sends a message or files a "
        "report).\n\n"
        "Rules:\n"
        "- Use only ids from the list, copied exactly.\n"
        "- Judge by the provider's descriptions and prices first, then by what you reliably know about these "
        "models. Model names change often: if you do not recognise a name and nothing in the list tells you what "
        "it is, do not guess from how the name sounds.\n"
        "- When you are not sure for a slot, answer null for it, and leave a model you cannot place out of the "
        "ladder. A wrong pick is worse than no pick.\n"
        "- Never pick a model that is not for chat (image, audio, embedding, moderation).\n"
        "- \"mid\" must not be heavier than the main chat model, and \"light\" must not be heavier than \"mid\".\n\n"
        "Models:\n" + "\n".join(rows) + "\n\n"
        "Answer with one JSON object and nothing else: {\"ladder\": [\"<lightest id>\", \"...\", "
        "\"<heaviest id, at most the main chat model>\"], \"light\": \"<id or null>\", \"mid\": \"<id or null>\"}"
    )


def parse(answer: str, models) -> Optional[dict]:
    """{"light": id or "", "mid": id or "", "ladder": [ids]} from the brain's answer; None when it is not the
    JSON asked for.

    An id that is not in the list is dropped, never repaired: a name the provider did not list would fail
    every background job that used it. The ladder keeps the brain's order, without repeats. When the brain
    gave a ladder but no starting point, the starting points are read off the ladder (its first rung, and
    the rung in the middle); when it gave starting points but no ladder, they are the ladder."""
    ids = {m["id"] for m in normalize(models)}
    text = str(answer or "")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict) or not any(k in data for k in TIERS + ("ladder",)):
        return None
    out = {}
    for tier in TIERS:
        v = data.get(tier)
        v = v.strip() if isinstance(v, str) else ""
        out[tier] = v if v in ids else ""
    ladder = []
    for v in (data.get("ladder") if isinstance(data.get("ladder"), list) else []):
        v = v.strip() if isinstance(v, str) else ""
        if v in ids and v not in ladder:
            ladder.append(v)
    if not ladder:
        ladder = [v for v in (out["light"], out["mid"]) if v]
        ladder = list(dict.fromkeys(ladder))
    else:
        out["light"] = out["light"] if out["light"] in ladder else ladder[0]
        out["mid"] = out["mid"] if out["mid"] in ladder else ladder[len(ladder) // 2]
    if out["light"] and out["mid"] and out["light"] in ladder and out["mid"] in ladder \
            and ladder.index(out["light"]) > ladder.index(out["mid"]):
        out["light"] = out["mid"]          # "light" above "mid" is a contradiction: trust the ladder's order
    out["ladder"] = ladder
    return out


def due(state: dict, now: float) -> bool:
    """Is it time to look at this provider's list again?"""
    if not isinstance(state, dict) or not state.get("sig"):
        return now >= float((state or {}).get("retry_at") or 0)
    return now - float(state.get("checked") or 0) >= RECHECK_S


async def choose(provider_label: str, models, main_model: str,
                 ask: Callable[[str], Awaitable[str]]) -> Optional[dict]:
    """Ask the main brain once. {"light", "mid"} (either may be ""), or None when there was no usable answer.

    An empty list, or a marketplace-sized one, is answered without asking: nothing to pick from."""
    rows = normalize(models)
    if not rows:
        return None
    if len(rows) > MAX_MODELS:
        return {"light": "", "mid": "", "ladder": []}
    if len(rows) == 1:
        return {"light": "", "mid": "", "ladder": []}     # one model: MAIN's model is the only choice there is
    answer = await ask(build_prompt(provider_label, rows, main_model))
    return parse(answer, rows)


def changed(old: dict, new: dict) -> bool:
    return any(str((old or {}).get(t) or "") != str((new or {}).get(t) or "") for t in TIERS) \
        or list((old or {}).get("ladder") or []) != list((new or {}).get("ladder") or [])
