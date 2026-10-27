"""model_routing.py - provider order, per-card model/effort, several accounts per provider (0.350.0).

Spec: docs/dev/2026-10-model-routing-spec.md. Everything here reads and writes the `model` section of
settings.json (passed in as a plain dict), so it never imports main and stays testable on its own.

Data it owns (all under settings["model"]):

    order            ["anthropic-cli", "openai-oauth", ...]   usage order, [0] is MAIN
    profiles         {provider: {"model", "reasoning"}}       what each card runs for chat
    defaults         {provider: {"model", "reasoning"}}       the provider's own starting config
    accounts         {provider: [{"id", "label", "enabled"}]} order of accounts / keys in a card
    account_keys     {account_id: key}                        encrypted at rest ("model.account_keys.*")
    telegram_chats   {chat_key: {"provider", "model"}}        a pin set by /model inside that chat
    routing_version  1

Legacy fields stay in sync so the ~150 places that read them keep working: `main` always mirrors
order[0] and its profile, `reasoning` mirrors MAIN's effort, and each API provider's old key field
holds the key of its first enabled account.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time

import config as cfgmod

LEVELS = ("off", "low", "medium", "high", "xhigh", "ultra")
ROUTING_VERSION = 1
OFF_PROFILE = {"model": "", "reasoning": "off"}


# ---------------------------------------------------------------- effort

def nearest_effort(level: str, supported) -> str:
    """The level a model really runs at: the chosen one when it has it, else the nearest level it
    has (ties go to the lower one). "off" means no reasoning parameter at all, and a model without
    any reasoning levels always runs as "off". The saved choice is never rewritten by this."""
    want = level if level in LEVELS else "off"
    have = [x for x in (supported or ()) if x in LEVELS and x != "off"]
    if want == "off" or not have:
        return "off"
    if want in have:
        return want
    wi = LEVELS.index(want)
    return min(have, key=lambda x: (abs(LEVELS.index(x) - wi), LEVELS.index(x)))


# ---------------------------------------------------------------- order and profiles

def _uniq(ids) -> list:
    out = []
    for x in ids or []:
        x = str(x or "").strip()
        if x and x not in out:
            out.append(x)
    return out


def _legacy_main(m: dict) -> dict:
    """{'provider','model'} from `main` or the pre-`main` engine fields (same rule as main._effective_main)."""
    main = m.get("main") or {}
    if main.get("provider"):
        return {"provider": main["provider"], "model": main.get("model") or ""}
    eng = m.get("engine")
    if eng == "openrouter":
        return {"provider": "openrouter", "model": m.get("openrouter_model") or ""}
    if eng == "anthropic-api":
        return {"provider": "anthropic-api", "model": m.get("claude_model") or ""}
    if eng and eng != "cli":
        return {"provider": eng, "model": ""}
    return {"provider": "anthropic-cli", "model": m.get("claude_model") or ""}


def stored_order(m: dict) -> list:
    return _uniq((m or {}).get("order"))


def order(m: dict, connected=None) -> list:
    """Usage order for routing. Stored order first (only providers still connected when the list of
    `connected` provider ids is given), then any connected provider the stored order does not know
    yet, at the end. With no stored order (settings from before 0.350.0) MAIN alone leads."""
    base = stored_order(m) or [_legacy_main(m)["provider"]]
    if connected is None:
        return base
    conn = _uniq(connected)
    ok = [p for p in base if p in conn]
    return ok + [p for p in conn if p not in ok]


def main_provider(m: dict) -> str:
    o = stored_order(m)
    return o[0] if o else _legacy_main(m)["provider"]


def default_profile(m: dict, provider: str) -> dict:
    d = ((m or {}).get("defaults") or {}).get(provider) or {}
    return {"model": str(d.get("model") or ""), "reasoning": d.get("reasoning") if d.get("reasoning") in LEVELS else "off"}


def profile(m: dict, provider: str) -> dict:
    """Model and effort a card runs for chat. A card never edited falls back to MAIN's legacy fields
    (when it is MAIN) or to the provider's starting config."""
    p = ((m or {}).get("profiles") or {}).get(provider)
    if isinstance(p, dict):
        return {"model": str(p.get("model") or ""),
                "reasoning": p.get("reasoning") if p.get("reasoning") in LEVELS else "off"}
    lm = _legacy_main(m)
    if lm["provider"] == provider:
        r = m.get("reasoning")
        return {"model": lm["model"], "reasoning": r if r in LEVELS else "off"}
    return default_profile(m, provider)


def sync_main(m: dict) -> None:
    """`main` and `reasoning` mirror order[0] and its profile. The one place that writes them."""
    o = stored_order(m)
    if not o:
        return
    pr = profile(m, o[0])
    m["main"] = {"provider": o[0], "model": pr["model"]}
    m["reasoning"] = pr["reasoning"]


def set_profile(m: dict, provider: str, model=None, reasoning=None) -> None:
    cur = profile(m, provider)
    if model is not None:
        cur["model"] = str(model or "")
    if reasoning is not None:
        cur["reasoning"] = reasoning if reasoning in LEVELS else "off"
    m.setdefault("profiles", {})[provider] = cur
    if main_provider(m) == provider:
        sync_main(m)


def set_order(m: dict, ids) -> None:
    """Save a new usage order. Profiles of the cards are kept; MAIN follows the new top card."""
    ids = _uniq(ids)
    if not ids:
        return
    for p in ids:          # pin each card's current profile before MAIN moves, so nothing jumps
        m.setdefault("profiles", {}).setdefault(p, profile(m, p))
    m["order"] = ids
    sync_main(m)


def promote(m: dict, provider: str, model=None) -> None:
    """Make `provider` MAIN (the composer's model chip and old callers of _set_main_model). The other
    cards keep their relative order, the old MAIN becomes fallback 1."""
    o = stored_order(m) or [_legacy_main(m)["provider"]]
    for p in o:
        m.setdefault("profiles", {}).setdefault(p, profile(m, p))
    o = [provider] + [p for p in o if p != provider]
    m["order"] = o
    if model is not None:
        m.setdefault("profiles", {}).setdefault(provider, profile(m, provider))["model"] = str(model or "")
    m.setdefault("profiles", {}).setdefault(provider, profile(m, provider))
    sync_main(m)


def add_to_order(m: dict, provider: str) -> None:
    """A newly connected provider goes to the END of the order (spec 2.1.5)."""
    o = stored_order(m)
    if provider and provider not in o:
        m["order"] = o + [provider]
        if not o:
            sync_main(m)


def drop_from_order(m: dict, provider: str) -> None:
    """A provider that lost its last login leaves the order. MAIN moves to the next card."""
    o = stored_order(m)
    if provider in o and len(o) > 1:
        m["order"] = [p for p in o if p != provider]
        sync_main(m)


# ---------------------------------------------------------------- accounts

def _account_id(seed: str) -> str:
    return "acc_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]


def new_account_id() -> str:
    return _account_id(f"{time.time_ns()}")


def accounts(m: dict, provider: str, key_field: str = "") -> list:
    """Accounts of a card, in order: [{"id", "label", "enabled", "key"}]. An API provider from before
    0.350.0 with a key in its old field and no list yet shows that key as account 1."""
    lst = ((m or {}).get("accounts") or {}).get(provider)
    keys = (m or {}).get("account_keys") or {}
    if isinstance(lst, list) and lst:
        out = []
        for a in lst:
            if isinstance(a, dict) and a.get("id"):
                out.append({"id": str(a["id"]), "label": str(a.get("label") or ""),
                            "enabled": a.get("enabled") is not False, "key": str(keys.get(a["id"]) or "")})
        return out
    if key_field and (m or {}).get(key_field):
        return [{"id": _account_id(provider), "label": "Key 1", "enabled": True, "key": str(m[key_field])}]
    return []


def save_accounts(m: dict, provider: str, lst: list, key_field: str = "") -> None:
    """Write a card's account list (order, labels, on/off, keys) and keep the old key field equal to
    the first enabled account's key. Keys of accounts no longer listed are deleted."""
    keys = m.setdefault("account_keys", {})
    before = {a["id"] for a in accounts(m, provider, key_field)}
    clean = []
    for a in lst or []:
        if not isinstance(a, dict) or not a.get("id"):
            continue
        aid = str(a["id"])
        clean.append({"id": aid, "label": str(a.get("label") or "")[:60], "enabled": a.get("enabled") is not False})
        if a.get("key"):
            keys[aid] = str(a["key"])
    m.setdefault("accounts", {})[provider] = clean
    for gone in before - {a["id"] for a in clean}:
        keys.pop(gone, None)
        clear_rest(provider, gone)
    if key_field:
        # From the saved list itself: accounts() would fall back to the old field for an empty list.
        first = next((a for a in clean if a["enabled"] and keys.get(a["id"])), None)
        m[key_field] = keys[first["id"]] if first else ""


# ---------------------------------------------------------------- rest state (out of quota)

_REST: dict = {}          # "provider:account" -> epoch it may be tried again
_PERSIST: set = set()     # keys whose reset time the provider stated: these survive a restart
_REST_LOCK = threading.Lock()
_REST_LOADED = False


def _rest_path():
    return cfgmod.STATE_DIR / "account_rest.json"


def _load_rest() -> None:
    global _REST_LOADED
    if _REST_LOADED:
        return
    _REST_LOADED = True
    try:
        data = json.loads(_rest_path().read_text(encoding="utf-8"))
        now = time.time()
        for k, v in (data or {}).items():
            if float(v) > now:
                _REST[str(k)] = float(v)
                _PERSIST.add(str(k))
    except Exception:  # noqa: BLE001 - no file or a bad file: start with nothing resting
        pass


def _save_rest() -> None:
    now = time.time()
    keep = {k: v for k, v in _REST.items() if v > now and k in _PERSIST}
    try:
        _rest_path().write_text(json.dumps(keep), encoding="utf-8")
    except Exception:  # noqa: BLE001 - losing the file only means one extra failed call after a restart
        pass


def rest_key(provider: str, account_id: str) -> str:
    return f"{provider}:{account_id or '-'}"


def mark_rest(provider: str, account_id: str, seconds: float = 0, until: float = 0, persist: bool = False) -> None:
    """Put one account to rest. `persist` only when the provider said when it resets, so a restart
    does not send every job to an account known to be empty (spec 3)."""
    when = float(until or 0) or (time.time() + max(1.0, float(seconds or 0)))
    with _REST_LOCK:
        _load_rest()
        k = rest_key(provider, account_id)
        _REST[k] = when
        if persist:
            _PERSIST.add(k)
            _save_rest()
        elif k in _PERSIST:
            _PERSIST.discard(k)
            _save_rest()


def clear_rest(provider: str, account_id: str) -> None:
    with _REST_LOCK:
        _load_rest()
        k = rest_key(provider, account_id)
        if _REST.pop(k, None) is not None and k in _PERSIST:
            _PERSIST.discard(k)
            _save_rest()


def resting_until(provider: str, account_id: str, now: float = None) -> float:
    with _REST_LOCK:
        _load_rest()
        until = _REST.get(rest_key(provider, account_id), 0.0)
    return until if until > (time.time() if now is None else now) else 0.0


def usable_accounts(m: dict, provider: str, key_field: str = "", now: float = None) -> list:
    return [a for a in accounts(m, provider, key_field)
            if a["enabled"] and (a["key"] or not key_field) and not resting_until(provider, a["id"], now)]


def active_account(m: dict, provider: str, key_field: str = "", now: float = None):
    """First enabled account that is not resting; when all are resting, the first enabled one (the
    caller then hits the provider's own error instead of an empty key). None when there is none."""
    usable = usable_accounts(m, provider, key_field, now)
    if usable:
        return usable[0]
    return next((a for a in accounts(m, provider, key_field) if a["enabled"] and (a["key"] or not key_field)), None)


def account_for_key(m: dict, provider: str, key: str, key_field: str = ""):
    return next((a for a in accounts(m, provider, key_field) if key and a["key"] == key), None)


# ---------------------------------------------------------------- background chain

def background_spec(m: dict) -> dict:
    """{'provider','model','reasoning'} of the background model. Unset = Claude Code (pre-0.350.0 rule)."""
    aux = (m or {}).get("auxiliary") or {}
    r = aux.get("reasoning")
    return {"provider": aux.get("provider") or "anthropic-cli", "model": aux.get("model") or "",
            "reasoning": r if r in LEVELS else "off"}


def background_chain(m: dict, connected=None, first: dict = None, once=()) -> list:
    """Background order (spec 2.4.3): background model (or `first`, e.g. an assistant's own model), then
    fallback 1, 2, ... each on its provider's starting config, then MAIN last on its starting config.
    Same provider + model only once; providers in `once` (plans, whose quota belongs to the account, not to
    the model) only once at all."""
    o = order(m, connected)
    steps = [dict(first or background_spec(m), step="background")]
    tail = o[1:] + o[:1]
    known = (m or {}).get("defaults") or {}
    for p in tail:
        # The provider's starting config; settings from before 0.350.0 never recorded one, so the card's own
        # profile stands in (an empty model would not run on an API card).
        d = default_profile(m, p) if p in known else profile(m, p)
        steps.append({"provider": p, "model": d["model"], "reasoning": d["reasoning"],
                      "step": "main" if o and p == o[0] else "fallback"})
    out, seen = [], set()
    for s in steps:
        k = (s["provider"], "" if s["provider"] in once else s["model"])
        if k not in seen:
            seen.add(k)
            out.append(s)
    return out


# ---------------------------------------------------------------- Telegram

def telegram_pin(m: dict, chat_key: str) -> dict:
    p = (((m or {}).get("telegram_chats") or {}).get(str(chat_key or "")) or {})
    return {"provider": p["provider"], "model": p.get("model") or ""} if p.get("provider") else {}


def set_telegram_pin(m: dict, chat_key: str, provider: str, model: str = "") -> None:
    chats = m.setdefault("telegram_chats", {})
    k = str(chat_key or "")
    if provider:
        chats[k] = {"provider": provider, "model": model or ""}
    else:
        chats.pop(k, None)


# ---------------------------------------------------------------- migration

def migrate(m: dict, *, connected_ids, defaults: dict, key_fields: dict, telegram_chat_keys=()) -> bool:
    """One-time move to the 0.350.0 layout (spec 4). Safe to run again: it does nothing once
    routing_version is set. Returns True when it changed something."""
    if int((m or {}).get("routing_version") or 0) >= ROUTING_VERSION:
        return False
    lm = _legacy_main(m)
    main_p = lm["provider"]
    o = [main_p] + [p for p in _uniq(connected_ids) if p != main_p]
    m["order"] = o
    dfl = m.setdefault("defaults", {})
    for p, d in (defaults or {}).items():
        dfl.setdefault(p, {"model": str((d or {}).get("model") or ""),
                           "reasoning": (d or {}).get("reasoning") if (d or {}).get("reasoning") in LEVELS else "off"})
    prof = m.setdefault("profiles", {})
    r = m.get("reasoning")
    prof.setdefault(main_p, {"model": lm["model"], "reasoning": r if r in LEVELS else "off"})
    for p in o[1:]:
        prof.setdefault(p, default_profile(m, p))
    # API keys become account 1 of their card (stable id, so a second run never duplicates them).
    accs = m.setdefault("accounts", {})
    keys = m.setdefault("account_keys", {})
    for p, field in (key_fields or {}).items():
        if field and m.get(field) and not accs.get(p):
            aid = _account_id(p)
            accs[p] = [{"id": aid, "label": "Key 1", "enabled": True}]
            keys.setdefault(aid, m[field])
    # Background model: keep an explicit choice; an unset one takes the first provider's starting config.
    aux = m.setdefault("auxiliary", {})
    if not (aux.get("provider") or aux.get("model")):
        d = default_profile(m, o[0])
        aux.update({"provider": o[0], "model": d["model"], "reasoning": d["reasoning"]})
    elif aux.get("reasoning") not in LEVELS:
        aux["reasoning"] = "off"
    # The shared Telegram pin becomes a pin of every Telegram chat Javis knows, then goes away.
    tg = m.get("telegram") or {}
    if tg.get("provider"):
        for k in _uniq(telegram_chat_keys):
            m.setdefault("telegram_chats", {}).setdefault(k, {"provider": tg["provider"], "model": tg.get("model") or ""})
        m["telegram"] = {"provider": "", "model": ""}
    m["routing_version"] = ROUTING_VERSION
    sync_main(m)
    return True
