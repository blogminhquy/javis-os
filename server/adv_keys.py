"""Gateway lists for the two "bring your own address" cards (owner 05/11/2026).

Each card holds several gateways (a seller's address plus its key), used top to bottom:

- "OpenAI Compatible" ('openai-compat') carries the advanced API keys. Owner 05/11/2026: the advanced keys are their
  own route, on the OpenAI format because almost every seller speaks it (NVIDIA Build, Kimi, OpenRouter clones,
  LiteLLM) and it lists its models at {base}/models, so the owner picks a model instead of typing one.
- "Claude Compatible" ('anthropic-compat'): Claude resellers and the "anthropic" endpoints of Kimi, MiniMax,
  DeepSeek. Version 0.477.0 had renamed this card "Advanced API key"; the owner asked for it back on 05/11/2026.

How it fits the code that already runs these providers (engine, aux_engine, main._provider_key read
`model.<prefix>_base/_key/_models`): the list lives in `model.<field>`, each gateway's key in the encrypted
`model.account_keys` dict (same store as the other API cards, never sent to the browser), and the gateway in use is
MIRRORED into those legacy fields. So every existing path keeps working unchanged and only ever sees one gateway:
the active one.

Rotation follows the other API cards (spec 6.4): a gateway that runs out of quota rests (model_routing.mark_rest) and
the next enabled gateway that is not resting becomes active. A machine from before this change, with one gateway in
the legacy fields and no list, reads that gateway as gateway 1.
"""
from __future__ import annotations

import hashlib
import time
from urllib.parse import urlparse

import model_routing

OPENAI = "openai-compat"
ANTHROPIC = "anthropic-compat"
ADVANCED = OPENAI            # the card that carries the advanced API keys
PROVIDERS = (OPENAI, ANTHROPIC)

# field: where the list is saved; legacy: prefix of the three mirrored fields; idp: prefix of a gateway id (and of its
# key in model.account_keys). "adv_keys" stays the Anthropic list so gateways saved by 0.477.0-0.481.x keep working.
_SPEC = {
    OPENAI: {"field": "adv_keys_openai", "legacy": "openai_compat", "idp": "advo_", "legacy_id": "advo_main"},
    ANTHROPIC: {"field": "adv_keys", "legacy": "anthropic_compat", "idp": "adv_", "legacy_id": "adv_main"},
}
FIELDS = tuple(s["field"] for s in _SPEC.values())


def field(prov: str) -> str:
    return _SPEC[prov]["field"]


def legacy_id(prov: str) -> str:
    return _SPEC[prov]["legacy_id"]


def norm_base(prov: str, base: str) -> str:
    base = str(base or "").strip()
    if prov == ANTHROPIC:
        import engine
        return engine.normalize_anthropic_compat_base(base)
    base = base.rstrip("/")
    if base.endswith("/chat/completions"):   # people paste the chat URL instead of the base
        base = base[: -len("/chat/completions")].rstrip("/")
    return base


def new_id(prov: str, seed: str = "") -> str:
    return _SPEC[prov]["idp"] + hashlib.sha1(f"{seed}{time.time_ns()}".encode("utf-8")).hexdigest()[:10]


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


def gateways(m: dict, prov: str) -> list:
    """Gateways in order: [{id, label, base, key, models, enabled}]. Keys come from the encrypted store."""
    m = m or {}
    sp = _SPEC[prov]
    keys = m.get("account_keys") or {}
    lst = m.get(sp["field"])
    if isinstance(lst, list) and lst:
        out = []
        for g in lst:
            if not isinstance(g, dict) or not g.get("id") or not g.get("base"):
                continue
            out.append({"id": str(g["id"]), "label": str(g.get("label") or "") or host(str(g["base"])),
                        "base": norm_base(prov, g["base"]), "key": str(keys.get(g["id"]) or ""),
                        "models": _clean_models(g.get("models")), "enabled": g.get("enabled") is not False})
        return out
    base = norm_base(prov, m.get(sp["legacy"] + "_base") or "")
    if not base:
        return []
    models = m.get(sp["legacy"] + "_models")
    if prov == OPENAI and not models:
        models = (m.get("catalog") or {}).get(OPENAI)   # the old OpenAI card kept its list in the catalog
    return [{"id": sp["legacy_id"], "label": host(base), "base": base, "key": str(m.get(sp["legacy"] + "_key") or ""),
             "models": _clean_models(models), "enabled": True}]


def active(m: dict, prov: str, now: float = None):
    """The gateway chat runs on now: the first enabled one that is not resting, else None."""
    for g in gateways(m, prov):
        if g["enabled"] and not model_routing.resting_until(prov, g["id"], now):
            return g
    return None


def _mirror(m: dict, prov: str, g) -> bool:
    """Copy gateway `g` into the legacy fields every existing path reads. A card model the new gateway does not
    list moves to that gateway's first model, so a switch between sellers (kimi-k2 vs MiniMax-M2) keeps working."""
    if not g:
        return False
    lg = _SPEC[prov]["legacy"]
    changed = (m.get(lg + "_base") or "") != g["base"]
    m[lg + "_base"] = g["base"]
    m[lg + "_key"] = g["key"]
    m[lg + "_models"] = list(g["models"])
    if g["models"]:
        m.setdefault("catalog", {})[prov] = list(g["models"])
        prof = model_routing.profile(m, prov)
        if prof.get("model") and prof["model"] not in g["models"]:
            model_routing.set_profile(m, prov, model=g["models"][0])
    elif changed:
        m.setdefault("catalog", {}).pop(prov, None)   # another seller: its list is fetched live again
    return changed


def _store(m: dict, prov: str, lst: list) -> None:
    sp = _SPEC[prov]
    keys = m.setdefault("account_keys", {})
    m[sp["field"]] = [{"id": g["id"], "label": g["label"], "base": g["base"], "models": g["models"],
                       "enabled": g["enabled"]} for g in lst]
    ids = {g["id"] for g in lst}
    for g in lst:
        if g.get("key"):
            keys[g["id"]] = g["key"]
        else:
            keys.pop(g["id"], None)
    for k in [k for k in keys if k.startswith(sp["idp"]) and k not in ids]:
        keys.pop(k, None)
    if not lst:   # the last gateway went: the mirrored copy goes too, or it would read back as gateway 1
        for f in ("_base", "_key"):
            m[sp["legacy"] + f] = ""
        m[sp["legacy"] + "_models"] = []


def sync(m: dict, prov: str) -> None:
    """Mirror the active gateway (or the first enabled one when all rest); clear the legacy fields when none is left."""
    lst = gateways(m, prov)
    g = active(m, prov) or next((x for x in lst if x["enabled"]), None)
    if g:
        _mirror(m, prov, g)
    elif not lst:
        lg = _SPEC[prov]["legacy"]
        m[lg + "_base"] = ""
        m[lg + "_key"] = ""
        m[lg + "_models"] = []


def add(m: dict, prov: str, label: str, base: str, key: str, models=()) -> dict:
    """Append a checked gateway; it becomes active when it is the first one that can run."""
    lst = gateways(m, prov)
    b = norm_base(prov, base)
    g = {"id": new_id(prov, b), "label": str(label or "").strip() or host(b), "base": b,
         "key": str(key or ""), "models": _clean_models(models), "enabled": True}
    lst.append(g)
    _store(m, prov, lst)
    sync(m, prov)
    return g


def update(m: dict, prov: str, gid: str, label=None, base=None, key=None, models=None) -> bool:
    lst = gateways(m, prov)
    for g in lst:
        if g["id"] == gid:
            if label is not None:
                g["label"] = str(label).strip() or g["label"]
            if base is not None:
                nb = norm_base(prov, base)
                if nb != g["base"] and not key:
                    g["key"] = ""   # a saved key belongs to its old address: never carry it to a new one
                g["base"] = nb
            if key:
                g["key"] = str(key)
            if models is not None:
                g["models"] = _clean_models(models)
            _store(m, prov, lst)
            sync(m, prov)
            return True
    return False


def save_list(m: dict, prov: str, items: list, removed=()) -> None:
    """Order, on/off and names from the page. A gateway missing from `items` (a stale page) is kept unless it is
    named in `removed`, the same rule as model_routing accounts."""
    old = {g["id"]: g for g in gateways(m, prov)}
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
    _store(m, prov, lst)
    sync(m, prov)


def forget(m: dict, prov: str) -> None:
    """Disconnect: every gateway of the card goes, with its key."""
    save_list(m, prov, [], removed=[g["id"] for g in gateways(m, prov)])
    m[_SPEC[prov]["field"]] = []


def _same_key(a: str, b: str) -> bool:
    """A gateway with no key runs as "none" (an OpenAI-format server on the owner's own machine needs none)."""
    return (a or "none") == (b or "none")


def rest_and_rotate(m: dict, prov: str, key: str, seconds: float) -> bool:
    """A chat turn on gateway `key` ran out of quota: that gateway rests and the next one becomes active.
    True when another gateway took over (the caller saves the settings)."""
    lst = gateways(m, prov)
    cur_base = norm_base(prov, m.get(_SPEC[prov]["legacy"] + "_base"))
    cur = next((g for g in lst if _same_key(g["key"], key) and g["base"] == cur_base), None) \
        or next((g for g in lst if _same_key(g["key"], key)), None)
    if not cur:
        return False
    model_routing.mark_rest(prov, cur["id"], seconds=max(1.0, float(seconds or 0)))
    nxt = active(m, prov)
    if nxt and nxt["id"] != cur["id"]:
        _mirror(m, prov, nxt)
        return True
    return False


def account_no(m: dict, prov: str, key: str):
    """(number, label) of the gateway that holds `key`, or (0, "")."""
    lst = gateways(m, prov)
    i = next((n for n, g in enumerate(lst) if key and _same_key(g["key"], key)), None)
    return (i + 1, lst[i]["label"]) if i is not None else (0, "")


def view(m: dict, prov: str, now: float = None) -> list:
    """What the Models page draws: no key, only its last 4 characters."""
    out = []
    for g in gateways(m, prov):
        out.append({"id": g["id"], "label": g["label"], "host": host(g["base"]), "base": g["base"],
                    "key": ("••••" + g["key"][-4:]) if g["key"] and g["key"] != "none" else "",
                    "models": g["models"], "enabled": g["enabled"],
                    "resting_until": model_routing.resting_until(prov, g["id"], now)})
    return out
