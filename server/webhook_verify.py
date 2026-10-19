"""webhook_verify.py - per-provider signature checks and event normalisation (0.229.0, webhook platform M4).

A hook may carry `verify`:

    {"provider": "stripe",  "secret": {"$secret": "<name>"}}            Stripe-Signature t=..,v1=.. (5 min window)
    {"provider": "github",  "secret": ...}                              X-Hub-Signature-256: sha256=<hex>
    {"provider": "shopify", "secret": ...}                              X-Shopify-Hmac-Sha256: <base64>
    {"provider": "systeme_io", "secret": ...}                           see SYSTEME_IO below (NOT production verified)
    {"provider": "hmac_sha256", "secret": ..., "header": "X-Signature", "encoding": "hex"|"base64", "prefix": "",
     "timestamp_header": "", "tolerance_s": 300}                        any sender that signs the raw body
    {"provider": "none"}                                                the Javis token only (the default)

The Javis token (Bearer / X-Javis-Token / ?token=) is ALWAYS checked first; a provider signature is a second lock,
checked on the RAW body before anything is stored. A failed check answers 401 and keeps nothing.

`normalize()` adds `_event` = {provider, type, id, occurred_at} next to the payload for the rules (M2): a filter can
say `{"path": "_event.type", "op": "eq", "value": "order.created"}` whatever the provider's own shape. `idem_key()`
gives the provider's own delivery id when the sender sent no Idempotency-Key, so a provider's retry is a duplicate.

POSCake: its webhook contract (signature header, event names, payload) is NOT known to this code and is not
guessed. Use `none` (the Javis token in the URL) or `hmac_sha256` once the contract is confirmed against a real
POSCake account; see docs/webhook-platform/poscake-migration.md.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Optional

PROVIDERS = ("none", "hmac_sha256", "stripe", "github", "shopify", "systeme_io")
# Status of each adapter. `spec` = built from the provider's published documentation and checked against its
# documented example; `unverified` = built from public descriptions only, never checked against a real delivery.
# NOTHING here is "production verified": that needs a real delivery from the provider (staging pack).
ADAPTER_STATUS = {"none": "spec", "hmac_sha256": "spec", "stripe": "spec", "github": "spec", "shopify": "spec",
                  "systeme_io": "unverified"}
STRIPE_TOLERANCE_S = 300
# Systeme.io (assumptions, to confirm on a real account before use, listed in the M4 doc):
#   signature header `X-Webhook-Signature`, hex HMAC-SHA256 of the raw body with the webhook's secret;
#   event name in header `X-Webhook-Event` (CONTACT_CREATED, CONTACT_TAG_ADDED, SALE_NEW...) or the body's `type`;
#   delivery id in header `X-Webhook-Id` when present.
SYSTEME_IO = {"sig": "x-webhook-signature", "event": "x-webhook-event", "id": "x-webhook-id"}


class VerifyError(ValueError):
    """The verify config itself is wrong (shown when saving)."""


def validate(cfg: Any) -> dict:
    """Normalised config (secret still as given: a plain string or a {"$secret"} reference), or VerifyError."""
    if cfg in (None, "", {}):
        return {}
    if not isinstance(cfg, dict):
        raise VerifyError("verify must be an object")
    prov = str(cfg.get("provider") or "none")
    if prov == "poscake":
        raise VerifyError("POSCake's webhook signature is not known yet: use provider none (the Javis token) or "
                          "hmac_sha256 once POSCake's contract is confirmed")
    if prov not in PROVIDERS:
        raise VerifyError(f"provider is one of {', '.join(PROVIDERS)}")
    if prov == "none":
        return {"provider": "none"}
    sec = cfg.get("secret")
    if not (isinstance(sec, str) and 8 <= len(sec) <= 500) and not (isinstance(sec, dict) and "$secret" in sec):
        raise VerifyError("verify needs the provider's signing secret (8 to 500 characters)")
    out = {"provider": prov, "secret": sec}
    if prov == "hmac_sha256":
        hdr = str(cfg.get("header") or "").strip()
        if not hdr or len(hdr) > 64 or not all(c.isalnum() or c == "-" for c in hdr):
            raise VerifyError("hmac_sha256 needs the signature header name")
        enc = str(cfg.get("encoding") or "hex")
        if enc not in ("hex", "base64"):
            raise VerifyError("encoding is hex or base64")
        out.update(header=hdr.lower(), encoding=enc, prefix=str(cfg.get("prefix") or "")[:20])
        ts = str(cfg.get("timestamp_header") or "").strip().lower()
        if ts:
            try:
                tol = int(cfg.get("tolerance_s") or 300)
            except (TypeError, ValueError):
                raise VerifyError("tolerance_s must be seconds")
            out.update(timestamp_header=ts, tolerance_s=max(30, min(tol, 3600)))
    return out


def _h(headers: Any, name: str) -> str:
    try:
        return str(headers.get(name) or headers.get(name.lower()) or "")
    except Exception:
        return ""


def _eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8", "replace"), b.encode("utf-8", "replace"))


def verify(cfg: dict, secret: str, headers: Any, body: bytes, now: Optional[float] = None) -> tuple:
    """(ok, reason). Never raises. `secret` is the resolved plain secret."""
    prov = (cfg or {}).get("provider") or "none"
    if prov == "none":
        return True, ""
    if not secret:
        return False, "signing secret not available"
    now = time.time() if now is None else now
    key = secret.encode("utf-8")
    body = bytes(body or b"")
    try:
        if prov == "stripe":
            parts = {}
            for item in _h(headers, "stripe-signature").split(","):
                k, _, v = item.strip().partition("=")
                parts.setdefault(k, []).append(v)
            ts = (parts.get("t") or [""])[0]
            if not ts.isdigit():
                return False, "Stripe-Signature missing or malformed"
            if abs(now - int(ts)) > STRIPE_TOLERANCE_S:
                return False, "Stripe signature too old (replay window)"
            want = hmac.new(key, ts.encode() + b"." + body, hashlib.sha256).hexdigest()
            return (any(_eq(want, v) for v in parts.get("v1", [])), "Stripe signature does not match")
        if prov == "github":
            got = _h(headers, "x-hub-signature-256")
            want = "sha256=" + hmac.new(key, body, hashlib.sha256).hexdigest()
            return (bool(got) and _eq(want, got), "GitHub signature does not match")
        if prov == "shopify":
            got = _h(headers, "x-shopify-hmac-sha256")
            want = base64.b64encode(hmac.new(key, body, hashlib.sha256).digest()).decode()
            return (bool(got) and _eq(want, got), "Shopify signature does not match")
        if prov == "systeme_io":
            got = _h(headers, SYSTEME_IO["sig"]).strip()
            want = hmac.new(key, body, hashlib.sha256).hexdigest()
            return (bool(got) and _eq(want, got.lower()), "Systeme.io signature does not match")
        if prov == "hmac_sha256":
            msg = body
            if cfg.get("timestamp_header"):
                ts = _h(headers, cfg["timestamp_header"]).strip()
                if not ts.isdigit() or abs(now - int(ts)) > int(cfg.get("tolerance_s") or 300):
                    return False, "signature timestamp missing or outside the replay window"
                msg = ts.encode() + b"." + body
            dig = hmac.new(key, msg, hashlib.sha256).digest()
            want = cfg.get("prefix", "") + (dig.hex() if cfg.get("encoding", "hex") == "hex" else base64.b64encode(dig).decode())
            got = _h(headers, cfg["header"]).strip()
            return (bool(got) and _eq(want, got), "signature does not match")
    except Exception as e:
        return False, f"signature check failed: {type(e).__name__}"
    return False, "unknown provider"


def normalize(provider: str, headers: Any, doc: Any) -> dict:
    """{provider, type, id, occurred_at} from the provider's own shape. Values the payload does not carry are ''."""
    d = doc if isinstance(doc, dict) else {}
    out = {"provider": provider or "none", "type": "", "id": "", "occurred_at": ""}
    if provider == "stripe":
        out.update(type=str(d.get("type") or ""), id=str(d.get("id") or ""), occurred_at=str(d.get("created") or ""))
    elif provider == "github":
        out.update(type=_h(headers, "x-github-event") + (("." + str(d["action"])) if d.get("action") else ""),
                   id=_h(headers, "x-github-delivery"))
    elif provider == "shopify":
        out.update(type=_h(headers, "x-shopify-topic"), id=_h(headers, "x-shopify-webhook-id"),
                   occurred_at=_h(headers, "x-shopify-triggered-at"))
    elif provider == "systeme_io":
        t = _h(headers, SYSTEME_IO["event"]) or str(d.get("type") or d.get("event") or "")
        out.update(type=t.strip().lower().replace("_", "."), id=_h(headers, SYSTEME_IO["id"]) or str(d.get("id") or ""),
                   occurred_at=str(d.get("created_at") or d.get("createdAt") or ""))
        contact = _systeme_contact(d)
        if contact:
            out["contact"] = contact
    return out


def _systeme_contact(d: dict) -> dict:
    """Best effort: the contact block appears under different keys in public examples (data.contact, contact,
    data.customer). Only plain fields are taken."""
    for path in (("data", "contact"), ("contact",), ("data", "customer"), ("customer",), ("data",)):
        cur: Any = d
        for k in path:
            cur = cur.get(k) if isinstance(cur, dict) else None
        if isinstance(cur, dict) and (cur.get("email") or cur.get("fields")):
            out = {"email": str(cur.get("email") or "")}
            fields = cur.get("fields")
            if isinstance(fields, list):           # [{"slug": "first_name", "value": "Lan"}, ...]
                for f in fields[:30]:
                    if isinstance(f, dict) and f.get("slug") in ("first_name", "surname", "last_name", "phone_number"):
                        out[str(f["slug"])] = str(f.get("value") or "")
            for k in ("first_name", "last_name", "phone", "phone_number"):
                if isinstance(cur.get(k), (str, int)):
                    out[k] = str(cur[k])
            return out
    return {}


def idem_key(provider: str, headers: Any, doc: Any) -> str:
    """The provider's own delivery/event id, used when the sender sent no Idempotency-Key."""
    if provider in ("none", "hmac_sha256", ""):
        return ""
    n = normalize(provider, headers, doc)
    return f"{provider}:{n['id']}"[:200] if n.get("id") else ""
