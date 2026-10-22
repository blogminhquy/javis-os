"""webhook_auth.py - who may send to a hook, and how a provider's signature is checked (0.274.0, webhook platform M4).

Spec §10. Two locks, in this order, before anything is stored:

1. The Javis token. `Authorization: Bearer <token>` or a header the owner names (`X-Javis-Token` by default). The query
   string `?token=` is accepted only for hooks created before 0.274.0 (their senders were set up that way); the
   dashboard warns that a token in a URL ends up in access logs. Only a SHA-256 of the token is stored.
2. A provider profile (`verify`), checked on the RAW body:

    {"provider": "stripe",  "secret": ref}       Stripe-Signature t=..,v1=.. (several v1 accepted, 5 min window)
    {"provider": "github",  "secret": ref}       X-Hub-Signature-256: sha256=<hex>; id X-GitHub-Delivery
    {"provider": "shopify", "secret": ref}       X-Shopify-Hmac-Sha256: <base64>; id X-Shopify-Event-Id (else Webhook-Id)
    {"provider": "systeme_io", "secret": ref}    X-Webhook-Signature, see SYSTEME_IO (NOT production verified)
    {"provider": "hmac_sha256", "secret": ref, "header": "X-Signature", "encoding": "hex"|"base64", "prefix": "",
     "timestamp_header": "", "tolerance_s": 300}  any sender that signs the raw body
    {"provider": "none"}                          the Javis token only (the default)

   The payload never chooses the algorithm, the header or the secret: they are the hook's. A signing secret can be
   rotated with a bounded overlap: the previous secret keeps working until `previous_until` (spec §10: two keys, a
   finite overlap); the key that matched (`current` / `previous`) and the time are stored with the event.

POSCake: its webhook contract (signature header, event names, payload) is NOT known to this code and is not guessed.
Use `none` (the Javis token) or `hmac_sha256` once the contract is confirmed against a real POSCake account; see
docs/webhook-platform/poscake-migration.md.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets as _rand
import time
from typing import Any, Optional
from urllib.parse import parse_qs

PROVIDERS = ("none", "hmac_sha256", "stripe", "github", "shopify", "systeme_io")
# `spec` = built from the provider's published documentation and checked against its documented example or scheme;
# `unverified` = the documented scheme could not be checked from here (docs host unreachable, no real delivery).
# NOTHING here is "production verified": that needs a real delivery from the provider (staging pack).
ADAPTER_STATUS = {"none": "spec", "hmac_sha256": "spec", "stripe": "spec", "github": "spec", "shopify": "spec",
                  "systeme_io": "unverified"}
STRIPE_TOLERANCE_S = 300
OVERLAP_DEFAULT_H = 24
OVERLAP_MAX_H = 168
DEFAULT_TOKEN_HEADER = "x-javis-token"
# Systeme.io (spec §10, [S5]): signature header `X-Webhook-Signature`, HMAC-SHA256 hex over the JSON as Systeme
# normalises it (Unicode and slash escaping), dedup on `X-Webhook-Message-Id` (stable across retries), never the attempt
# id. The exact normalisation could not be read from developer.systeme.io from this environment, so the check accepts
# the raw body and the two PHP json_encode forms (default escaping, and JSON_UNESCAPED_UNICODE|JSON_UNESCAPED_SLASHES),
# and records which one matched: the staging run decides, and the adapter stays `unverified` until then.
SYSTEME_IO = {"sig": "x-webhook-signature", "event": "x-webhook-event", "id": "x-webhook-message-id"}
SYSTEME_FORMS = ("raw", "php_default", "php_unescaped")
# Request headers kept with an event (spec §4.1 "headers allowed to be stored"): never credentials or signatures.
STORED_HEADERS = ("content-type", "user-agent", "x-github-event", "x-github-delivery", "x-github-hook-id",
                  "x-shopify-topic", "x-shopify-webhook-id", "x-shopify-event-id", "x-shopify-triggered-at",
                  "x-shopify-shop-domain", "x-shopify-api-version", "x-webhook-event", "x-webhook-message-id",
                  "x-webhook-attempt-id", "x-request-id", "idempotency-key")


class VerifyError(ValueError):
    """The verify config itself is wrong (shown when saving)."""


# ── the Javis token ──
def hash_token(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def new_token() -> str:
    return _rand.token_urlsafe(24)


def token_header_name(name: Any) -> str:
    """The owner's token header, validated (letters, digits, -; not a header that carries something else)."""
    n = str(name or "").strip().lower()
    if not n:
        return DEFAULT_TOKEN_HEADER
    if len(n) > 64 or not all(c.isalnum() or c == "-" for c in n) or n in (
            "authorization", "cookie", "content-length", "host", "x-forwarded-for") or n in STORED_HEADERS:
        # A header Javis stores with the event (or uses as the delivery key) would put the token in the log and exports.
        raise VerifyError("the token header is a plain header name (letters, digits and -) that Javis does not "
                          "store or use for anything else")
    return n


def token_from_request(headers: Any, query: str, header: str = DEFAULT_TOKEN_HEADER, allow_query: bool = True) -> str:
    """Bearer first (keeps the secret out of access logs), then the hook's header, then ?token= when allowed."""
    raw = str(headers.get("authorization") or "")
    if raw[:7].lower() == "bearer ":
        return raw[7:].strip()
    tok = str(headers.get(header or DEFAULT_TOKEN_HEADER) or "").strip()
    if tok:
        return tok
    if header != DEFAULT_TOKEN_HEADER:
        tok = str(headers.get(DEFAULT_TOKEN_HEADER) or "").strip()
        if tok:
            return tok
    if not allow_query:
        return ""
    vals = parse_qs(query or "").get("token") or []
    return str(vals[0]).strip() if vals else ""


def token_ok(stored_hash: str, token: str) -> bool:
    return bool(token) and hmac.compare_digest(str(stored_hash or ""), hash_token(token))


def stored_headers(headers: Any) -> dict:
    out = {}
    for k in STORED_HEADERS:
        try:
            v = headers.get(k)
        except Exception:
            v = None
        if v:
            out[k] = str(v)[:300]
    return out


# ── provider profiles ──
def validate(cfg: Any) -> dict:
    """Normalised config (secrets still as given: a plain string or a {"$secret"} reference), or VerifyError."""
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
    try:
        ov = int(cfg.get("overlap_h") or OVERLAP_DEFAULT_H)
    except (TypeError, ValueError):
        raise VerifyError("overlap_h must be hours")
    if not 1 <= ov <= OVERLAP_MAX_H:
        raise VerifyError(f"overlap_h from 1 to {OVERLAP_MAX_H} hours")
    out["overlap_h"] = ov
    prev = cfg.get("previous_secret")
    if prev is not None:
        if not (isinstance(prev, dict) and "$secret" in prev) and not (isinstance(prev, str) and 8 <= len(prev) <= 500):
            raise VerifyError("previous_secret is set by Javis when the secret changes")
        out["previous_secret"] = prev
        try:
            out["previous_until"] = float(cfg.get("previous_until") or 0)
        except (TypeError, ValueError):
            raise VerifyError("previous_until must be a time")
        import math
        import time as _t
        if not math.isfinite(out["previous_until"]):
            raise VerifyError("previous_until must be a time")
        # Bounded overlap (spec §10): never past the longest overlap from now, whatever was stored.
        out["previous_until"] = min(out["previous_until"], _t.time() + OVERLAP_MAX_H * 3600)
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


class _Num(str):
    """A JSON number kept as its own text (so a re-serialisation writes exactly what was received)."""


def _php_dump(v: Any, unescaped: bool) -> str:
    """PHP json_encode of a decoded document: key order kept, compact, `\\/` and `\\uXXXX` escaping by default;
    with JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE slashes and UTF-8 stay as they are (U+2028/2029 still escaped,
    as PHP >= 7.1 does without JSON_UNESCAPED_LINE_TERMINATORS)."""
    if isinstance(v, _Num):
        return str(v)
    if v is True:
        return "true"
    if v is False:
        return "false"
    if v is None:
        return "null"
    if isinstance(v, str):
        s = json.dumps(v, ensure_ascii=not unescaped)
        if unescaped:
            return s.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
        return s.replace("/", "\\/")
    if isinstance(v, _Obj):
        return "{" + ",".join(_php_dump(k, unescaped) + ":" + _php_dump(x, unescaped) for k, x in v.pairs) + "}"
    if isinstance(v, list):
        return "[" + ",".join(_php_dump(x, unescaped) for x in v) + "]"
    return json.dumps(v)


class _Obj:
    __slots__ = ("pairs",)

    def __init__(self, pairs):
        self.pairs = pairs


def systeme_forms(body: bytes) -> dict:
    """{form: bytes} the Systeme.io signature may cover (see SYSTEME_IO)."""
    out = {"raw": bytes(body or b"")}
    try:
        doc = json.loads(bytes(body).decode("utf-8"), object_pairs_hook=_Obj, parse_float=_Num, parse_int=_Num,
                         parse_constant=_Num)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return out
    try:
        out["php_default"] = _php_dump(doc, False).encode("utf-8")
        out["php_unescaped"] = _php_dump(doc, True).encode("utf-8")
    except RecursionError:
        pass
    return out


def _check(prov: str, cfg: dict, key: bytes, headers: Any, body: bytes, now: float) -> tuple:
    """(ok, reason, scheme) for one secret."""
    if prov == "stripe":
        parts: dict = {}
        for item in _h(headers, "stripe-signature").split(","):
            k, _, v = item.strip().partition("=")
            parts.setdefault(k, []).append(v)
        ts = (parts.get("t") or [""])[0]
        if not ts.isdigit():
            return False, "Stripe-Signature missing or malformed", ""
        if abs(now - int(ts)) > STRIPE_TOLERANCE_S:
            return False, "Stripe signature too old (replay window)", ""
        want = hmac.new(key, ts.encode() + b"." + body, hashlib.sha256).hexdigest()
        return any(_eq(want, v) for v in parts.get("v1", [])), "Stripe signature does not match", "v1"
    if prov == "github":
        got = _h(headers, "x-hub-signature-256")
        want = "sha256=" + hmac.new(key, body, hashlib.sha256).hexdigest()
        return bool(got) and _eq(want, got), "GitHub signature does not match", "sha256"
    if prov == "shopify":
        got = _h(headers, "x-shopify-hmac-sha256")
        want = base64.b64encode(hmac.new(key, body, hashlib.sha256).digest()).decode()
        return bool(got) and _eq(want, got), "Shopify signature does not match", "base64"
    if prov == "systeme_io":
        got = _h(headers, SYSTEME_IO["sig"]).strip().lower()
        if not got:
            return False, "Systeme.io signature header missing", ""
        for form, data in systeme_forms(body).items():
            if _eq(hmac.new(key, data, hashlib.sha256).hexdigest(), got):
                return True, "", form
        return False, "Systeme.io signature does not match", ""
    if prov == "hmac_sha256":
        msg = body
        if cfg.get("timestamp_header"):
            ts = _h(headers, cfg["timestamp_header"]).strip()
            if not ts.isdigit() or abs(now - int(ts)) > int(cfg.get("tolerance_s") or 300):
                return False, "signature timestamp missing or outside the replay window", ""
            msg = ts.encode() + b"." + body
        dig = hmac.new(key, msg, hashlib.sha256).digest()
        want = cfg.get("prefix", "") + (dig.hex() if cfg.get("encoding", "hex") == "hex" else base64.b64encode(dig).decode())
        got = _h(headers, cfg["header"]).strip()
        if cfg.get("encoding", "hex") == "hex":
            want, got = want.lower(), got.lower()          # hex is case-insensitive (base64 is not)
        return bool(got) and _eq(want, got), "signature does not match", cfg.get("encoding", "hex")
    return False, "unknown provider", ""


def verify(cfg: dict, secret: Any, headers: Any, body: bytes, now: Optional[float] = None,
           previous: str = "") -> tuple:
    """(ok, reason) as before; see verify_ex for which key matched. Never raises."""
    ok, why, _, _ = verify_ex(cfg, secret, headers, body, now, previous)
    return ok, why


def verify_ex(cfg: dict, secret: Any, headers: Any, body: bytes, now: Optional[float] = None,
              previous: str = "") -> tuple:
    """(ok, reason, key_version, scheme). `secret` is the resolved current secret; `previous` the resolved previous
    one, tried only while `previous_until` has not passed (the bounded overlap of a rotation)."""
    prov = (cfg or {}).get("provider") or "none"
    if prov == "none":
        return True, "", "", ""
    now = time.time() if now is None else now
    body = bytes(body or b"")
    keys = []
    if secret:
        keys.append(("current", str(secret)))
    if previous and float(cfg.get("previous_until") or 0) > now:
        keys.append(("previous", str(previous)))
    if not keys:
        return False, "signing secret not available", "", ""
    why = ""
    for version, sec in keys:
        try:
            ok, why, scheme = _check(prov, cfg, sec.encode("utf-8"), headers, body, now)
        except Exception as e:
            return False, f"signature check failed: {type(e).__name__}", "", ""
        if ok:
            return True, "", version, scheme
    return False, why, "", ""


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
        out.update(type=_h(headers, "x-shopify-topic"),
                   id=_h(headers, "x-shopify-event-id") or _h(headers, "x-shopify-webhook-id"),
                   occurred_at=_h(headers, "x-shopify-triggered-at"))
    elif provider == "systeme_io":
        t = _h(headers, SYSTEME_IO["event"]) or str(d.get("type") or d.get("event") or "")
        out.update(type=t.strip().lower().replace("_", "."), id=_h(headers, SYSTEME_IO["id"]),
                   occurred_at=str(d.get("created_at") or d.get("createdAt") or ""))
        contact = _systeme_contact(d)
        if contact:
            out["contact"] = contact
    return out


TRACE_EVENT_KEYS = ("provider", "type", "id", "occurred_at", "signed_form")


def trace_event(ev: Optional[dict]) -> dict:
    """What of the normalised event may be STORED (the trace, spec §5: no customer data): ids and the type. The
    contact block is derived again from the body whenever the event runs (`run_event`)."""
    return {k: ev[k] for k in TRACE_EVENT_KEYS if isinstance(ev, dict) and k in ev}


def run_event(ev: Optional[dict], doc: Any) -> dict:
    """The event as rules and templates read it (`_event`): the stored part plus, for Systeme.io, the contact block
    taken from the body again (it is never stored in the trace)."""
    out = dict(ev or {})
    if out.get("provider") == "systeme_io" and "contact" not in out and isinstance(doc, dict):
        c = _systeme_contact(doc)
        if c:
            out["contact"] = c
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
    """The provider's own message id (stable across its retries), or '' when it has none."""
    if provider in ("none", "hmac_sha256", ""):
        return ""
    n = normalize(provider, headers, doc)
    return f"{provider}:{n['id']}"[:200] if n.get("id") else ""
