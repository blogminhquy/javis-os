"""Advanced API key: several gateways on the Anthropic-compatible route (owner 05/11/2026).

The owner asked for one place to plug in API keys of many sellers (Claude resellers, Kimi, MiniMax, the "anthropic"
endpoints of DeepSeek...), each with its own address, used through the Anthropic-compatible provider
('anthropic-compat'), without naming that route on screen. The Models page shows the card as "Advanced API key".

How it fits the code that already runs this provider (engine, aux_engine, main._provider_key all read
`model.anthropic_compat_base/_key/_models`): the list lives in `model.adv_keys`, each gateway's key in the encrypted
`model.account_keys` dict (same store as the other API cards, never sent to the browser), and the gateway in use is
MIRRORED into those three legacy fields. So every existing path keeps working unchanged and only ever sees one
gateway: the active one.

Rotation follows the other API cards (spec 6.4): a gateway that runs out of quota rests (model_routing.mark_rest) and
the next enabled gateway that is not resting becomes active. A machine from before this change, with one gateway in
the legacy fields and no list, reads that gateway as gateway 1.
"""
from __future__ import annotations

import hashlib
import time
from urllib.parse import urlparse

import model_routing

PROVIDER = "anthropic-compat"
FIELD = "adv_keys"
LEGACY_ID = "adv_main"


def _norm_base(base: str) -> str:
    import engine
    return engine.normalize_anthropic_compat_base(str(base or ""))


def new_id(seed: str = "") -> str:
    return "adv_" + hashlib.sha1(f"{seed}{time.time_ns()}".encode("utf-8")).hexdigest()[:10]


def host(base: str) -> str:
    """The part of the address people recognise: "api.moonshot.ai"."""
    try:
        return urlparse(base).netloc or base
    except Exception:
        return base


def _clean_models(models) -> list:
    out = []
    for x in models or []:
        x = str(x or "").strip()
        if x and x not in out:
            out.append(x)
    return out


def gateways(m: dict) -> list:
    """Gateways in order: [{id, label, base, key, models, enabled}]. Keys come from the encrypted store."""
    m = m or {}
    keys = m.get("account_keys") or {}
    lst = m.get(FIELD)
    if isinstance(lst, list) and lst:
        out = []
        for g in lst:
            if not isinstance(g, dict) or not g.get("id") or not g.get("base"):
                continue
            out.append({"id": str(g["id"]), "label": str(g.get("label") or "") or host(str(g["base"])),
                        "base": _norm_base(g["base"]), "key": str(keys.get(g["id"]) or ""),
                        "models": _clean_models(g.get("models")), "enabled": g.get("enabled") is not False})
        return out
    base = _norm_base(m.get("anthropic_compat_base") or "")
    if not base:
        return []
    return [{"id": LEGACY_ID, "label": host(base), "base": base, "key": str(m.get("anthropic_compat_key") or ""),
             "models": _clean_models(m.get("anthropic_compat_models")), "enabled": True}]


def active(m: dict, now: float = None):
    """The gateway chat runs on now: the first enabled one that is not resting, else None."""
    for g in gateways(m):
        if g["enabled"] and not model_routing.resting_until(PROVIDER, g["id"], now):
            return g
    return None


def _mirror(m: dict, g) -> bool:
    """Copy gateway `g` into the legacy fields every existing path reads. A card model the new gateway does not
    list moves to that gateway's first model, so a switch between sellers (kimi-k2 vs MiniMax-M2) keeps working."""
    if not g:
        return False
    changed = (m.get("anthropic_compat_base") or "") != g["base"]
    m["anthropic_compat_base"] = g["base"]
    m["anthropic_compat_key"] = g["key"]
    m["anthropic_compat_models"] = list(g["models"])
    if g["models"]:
        m.setdefault("catalog", {})[PROVIDER] = list(g["models"])
        prof = model_routing.profile(m, PROVIDER)
        if prof.get("model") and prof["model"] not in g["models"]:
            model_routing.set_profile(m, PROVIDER, model=g["models"][0])
    elif changed:
        m.setdefault("catalog", {}).pop(PROVIDER, None)   # another seller: its list is fetched live again
    return changed


def _store(m: dict, lst: list) -> None:
    keys = m.setdefault("account_keys", {})
    m[FIELD] = [{"id": g["id"], "label": g["label"], "base": g["base"], "models": g["models"],
                 "enabled": g["enabled"]} for g in lst]
    ids = {g["id"] for g in lst}
    for g in lst:
        if g.get("key"):
            keys[g["id"]] = g["key"]
    for k in [k for k in keys if k.startswith("adv_") and k not in ids]:
        keys.pop(k, None)


def sync(m: dict) -> None:
    """Mirror the active gateway (or the first enabled one when all rest); clear the legacy fields when none is left."""
    lst = gateways(m)
    g = active(m) or next((x for x in lst if x["enabled"]), None)
    if g:
        _mirror(m, g)
    elif not lst:
        m["anthropic_compat_base"] = ""
        m["anthropic_compat_key"] = ""
        m["anthropic_compat_models"] = []


def add(m: dict, label: str, base: str, key: str, models=()) -> dict:
    """Append a checked gateway; it becomes active when it is the first one that can run."""
    lst = gateways(m)
    g = {"id": new_id(base), "label": str(label or "").strip() or host(_norm_base(base)), "base": _norm_base(base),
         "key": str(key or ""), "models": _clean_models(models), "enabled": True}
    lst.append(g)
    _store(m, lst)
    sync(m)
    return g


def update(m: dict, gid: str, label=None, base=None, key=None, models=None) -> bool:
    lst = gateways(m)
    for g in lst:
        if g["id"] == gid:
            if label is not None:
                g["label"] = str(label).strip() or g["label"]
            if base is not None:
                g["base"] = _norm_base(base)
            if key:
                g["key"] = str(key)
            if models is not None:
                g["models"] = _clean_models(models)
            _store(m, lst)
            sync(m)
            return True
    return False


def save_list(m: dict, items: list, removed=()) -> None:
    """Order, on/off and names from the page. A gateway missing from `items` (a stale page) is kept unless it is
    named in `removed`, the same rule as model_routing accounts."""
    old = {g["id"]: g for g in gateways(m)}
    gone = set(removed or ())
    lst = []
    for it in items or []:
        g = old.get(str((it or {}).get("id") or ""))
        if not g or g["id"] in gone:
            continue
        g = dict(g)
        if "enabled" in it:
            g["enabled"] = it["enabled"] is not False
        if it.get("label"):
            g["label"] = str(it["label"]).strip() or g["label"]
        lst.append(g)
    seen = {g["id"] for g in lst}
    lst += [g for gid, g in old.items() if gid not in seen and gid not in gone]
    _store(m, lst)
    sync(m)


def rest_and_rotate(m: dict, key: str, seconds: float) -> bool:
    """A chat turn on gateway `key` ran out of quota: that gateway rests and the next one becomes active.
    True when another gateway took over (the caller saves the settings)."""
    cur = next((g for g in gateways(m) if g["key"] == key and g["base"] == _norm_base(m.get("anthropic_compat_base"))),
               None) or next((g for g in gateways(m) if g["key"] == key), None)
    if not cur:
        return False
    model_routing.mark_rest(PROVIDER, cur["id"], seconds=max(1.0, float(seconds or 0)))
    nxt = active(m)
    if nxt and nxt["id"] != cur["id"]:
        _mirror(m, nxt)
        return True
    return False


def view(m: dict, now: float = None) -> list:
    """What the Models page draws: no key, only its last 4 characters."""
    out = []
    for g in gateways(m):
        out.append({"id": g["id"], "label": g["label"], "host": host(g["base"]), "base": g["base"],
                    "key": ("••••" + g["key"][-4:]) if g["key"] and g["key"] != "none" else "",
                    "models": g["models"], "enabled": g["enabled"],
                    "resting_until": model_routing.resting_until(PROVIDER, g["id"], now)})
    return out
