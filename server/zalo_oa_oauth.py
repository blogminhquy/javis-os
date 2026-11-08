"""Grant Javis access to a Zalo OA with Zalo's OAuth v4 flow (authorization code + PKCE).

Before this, the owner pasted a refresh token copied from API Explorer on developers.zalo.me. Zalo
moved OA authorization to OAuth v4, where an app gets its first token pair through the standard
redirect flow with a PKCE code challenge. This module does that flow on the owner's OWN Zalo app:

  1. `start()` takes the App ID, App secret key and OA secret key (or reads them from the account
     being reconnected), makes a `code_verifier` and its S256 `code_challenge`, and returns the
     address of Zalo's permission page. The owner adds this Javis's callback address to the app
     once (Official Account, Callback URL); the form shows it ready to copy.
  2. The OA admin picks the OA and allows the app; Zalo sends the browser back to
     `/zalo-oa/oauth/callback?code=...&oa_id=...&state=...`. `callback()` trades the code and the
     verifier for an access token and a refresh token, then reads which OA it is.
  3. The dashboard polls `result()`; once ready, `/zalo-oa/oauth/finish` saves the account with the
     new pair (or replaces the pair of the account being reconnected).

Why the owner's own app: every Javis runs at its own address, Zalo wants the callback registered on
the app, and the repo is public so it cannot carry an app secret.

Pending grants live in memory for 15 minutes keyed by an unguessable `state`, and the code verifier
never leaves the server. The tokens stay in this module until `/finish` stores them encrypted;
`result()` returns the OA id and name only. A new refresh token works once, like any Zalo OA
refresh token, so it goes straight to the account store and nowhere else.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import threading
import time
from typing import Any, Dict
from urllib.parse import urlencode

import httpx

import localefmt
import zalo_oa_bot

CALLBACK_PATH = "/zalo-oa/oauth/callback"
PERMISSION_URL = os.getenv("JAVIS_ZALO_OA_PERMISSION", "https://oauth.zaloapp.com/v4/oa/permission")
TTL = 15 * 60

_lock = threading.Lock()
_pending: Dict[str, Dict[str, Any]] = {}


def _c(vi: str, en: str) -> str:
    return localefmt.chu(vi, en)


def _purge(now: float = 0.0) -> None:
    now = now or time.time()
    with _lock:
        for k in [k for k, v in _pending.items() if now - v.get("created", 0) > TTL]:
            _pending.pop(k, None)


def pkce_pair() -> tuple:
    """(code_verifier, code_challenge). The verifier is 43-128 unreserved characters (RFC 7636);
    the challenge is base64url(sha256(verifier)) without padding, the S256 method Zalo v4 expects."""
    verifier = secrets.token_urlsafe(48)[:64]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def permission_url(app_id: str, redirect_uri: str, challenge: str, state: str) -> str:
    q = {"app_id": app_id, "redirect_uri": redirect_uri, "code_challenge": challenge, "state": state}
    return PERMISSION_URL + "?" + urlencode(q)


def check_input(cr: dict) -> str:
    """'' when the three app keys look right, else the error to show."""
    if not str(cr.get("app_id") or "").isdigit():
        return _c("App ID phải là dãy số (trang Thông tin ứng dụng trên developers.zalo.me).",
                  "The App ID must be digits (the app's info page on developers.zalo.me).")
    if not cr.get("app_secret"):
        return _c("Còn thiếu App secret key.", "The App secret key is missing.")
    if not cr.get("oa_secret"):
        return _c("Còn thiếu OA secret key (mục Webhook của app). Thiếu nó Javis không kiểm được chữ ký tin "
                  "Zalo gửi tới, nên bot không chạy.",
                  "The OA secret key is missing (the app's Webhook section). Without it Javis cannot check the "
                  "signature of what Zalo sends, so the bot will not run.")
    return ""


def start(credentials, redirect_uri: str, brain: str = "", label: str = "", account_id: str = "",
          stored: str = "") -> dict:
    """Open a pending grant. {"ok", "url", "state", "redirect_uri"} or {"ok": False, "error"}.

    `credentials` is what the owner typed: "<App ID> <App secret key> <OA secret key>" in any form
    `zalo_oa_bot.split_credentials` reads. `stored` is the saved secret of the account being
    reconnected; whatever the owner left out is taken from it."""
    cr = zalo_oa_bot.split_credentials(credentials)
    old = zalo_oa_bot.split_credentials(stored) if stored else {}
    for k in ("app_id", "app_secret", "oa_secret"):
        cr[k] = cr.get(k) or old.get(k, "")
    bad = check_input(cr)
    if bad:
        return {"ok": False, "error": bad}
    if not str(redirect_uri or "").startswith("https://"):
        return {"ok": False, "error": _c(
            "Zalo chỉ trả về địa chỉ HTTPS. Mở Javis bằng tên miền HTTPS rồi bấm lại.",
            "Zalo only sends you back to an HTTPS address. Open Javis through its HTTPS domain and click again.")}
    _purge()
    state = secrets.token_urlsafe(24)
    verifier, challenge = pkce_pair()
    with _lock:
        _pending[state] = {"created": time.time(), "status": "pending", "app_id": cr["app_id"],
                           "app_secret": cr["app_secret"], "oa_secret": cr["oa_secret"], "verifier": verifier,
                           "redirect_uri": redirect_uri, "brain": str(brain or ""), "label": str(label or ""),
                           "account_id": str(account_id or ""), "error": "", "oa_id": "", "oa_name": "",
                           "credentials": {}}
    return {"ok": True, "state": state, "url": permission_url(cr["app_id"], redirect_uri, challenge, state),
            "redirect_uri": redirect_uri}


def _set(state: str, **kw) -> None:
    with _lock:
        if state in _pending:
            _pending[state].update(kw)


async def exchange_code(client, app_id: str, app_secret: str, code: str, verifier: str) -> dict:
    """Trade an authorization code for the first token pair. Same answer shape as
    `zalo_oa_bot.refresh_tokens`. A code works once and lives a few minutes, so no retry."""
    try:
        r = await client.post(zalo_oa_bot.OAUTH_URL, headers={"secret_key": str(app_secret or "")},
                              data={"code": str(code or ""), "app_id": str(app_id or ""),
                                    "grant_type": "authorization_code", "code_verifier": str(verifier or "")})
        try:
            d = r.json() or {}
        except Exception:
            d = {}
    except Exception as e:
        return {"ok": False, "error": _c(f"Không nối được Zalo: {e}", f"Could not reach Zalo: {e}")}
    if not d.get("access_token") or not d.get("refresh_token"):
        why = str(d.get("error_description") or d.get("message") or d.get("error_reason") or d.get("error")
                  or f"HTTP {r.status_code}")
        return {"ok": False, "error": _c(
            "Zalo không đổi được mã cấp quyền (" + why + "). Thường do App secret key không khớp App ID, hoặc mã "
            "đã quá hạn vài phút. Bấm Cấp quyền bằng Zalo lần nữa.",
            "Zalo could not exchange the grant code (" + why + "). Usually the App secret key does not match the "
            "App ID, or the code is a few minutes old. Click Grant access with Zalo again.")}
    try:
        life = float(d.get("expires_in") or 90000)
    except Exception:
        life = 90000.0
    return {"ok": True, "access_token": str(d["access_token"]), "refresh_token": str(d["refresh_token"]),
            "expires_at": time.time() + life}


async def callback(state: str, code: str, oa_id: str = "", error: str = "", error_description: str = "",
                   client=None) -> dict:
    """Zalo sent the browser back. {"ok", "oa_id", "oa_name"} or {"ok": False, "error"}; the dashboard
    reads the same outcome through `result(state)`."""
    _purge()
    state = str(state or "")
    with _lock:
        p = dict(_pending.get(state) or {})
    if not p:
        return {"ok": False, "error": _c("Phiên cấp quyền đã hết hạn. Quay lại Javis bấm Cấp quyền bằng Zalo lần nữa.",
                                         "This grant expired. Go back to Javis and click Grant access with Zalo again.")}
    if p.get("status") != "pending":
        return {"ok": p.get("status") == "ready", "oa_id": p.get("oa_id", ""), "oa_name": p.get("oa_name", ""),
                "error": p.get("error", "")}
    if error or not code:
        msg = error_description or error or _c("Zalo không trả mã cấp quyền. Có thể bạn đã bấm Huỷ.",
                                               "Zalo returned no grant code. You may have cancelled.")
        _set(state, status="error", error=msg)
        return {"ok": False, "error": msg}
    # One exchange per state: a refreshed callback page must not spend the code twice.
    _set(state, status="exchanging")
    own = client is None
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(20.0))
    try:
        res = await exchange_code(client, p["app_id"], p["app_secret"], code, p["verifier"])
        if not res.get("ok"):
            _set(state, status="error", error=res.get("error", ""))
            return {"ok": False, "error": res.get("error", "")}
        cr = {k: "" for k in zalo_oa_bot._FIELDS}
        cr.update({"app_id": p["app_id"], "app_secret": p["app_secret"], "oa_secret": p["oa_secret"],
                   "access_token": res["access_token"], "refresh_token": res["refresh_token"],
                   "expires_at": res["expires_at"], "oa_id": str(oa_id or "")})
        # No account id: the probe uses the fresh access token as it is and refreshes nothing.
        probe = zalo_oa_bot.ZaloOABot(zalo_oa_bot.dump_credentials(cr), "", None, giau_trang_thai=True)
        info = await zalo_oa_bot.whoami(client, probe)
    finally:
        if own:
            await client.aclose()
    if info.get("ok"):
        cr["oa_id"] = info["username"]
    if not cr["oa_id"]:
        msg = info.get("error") or _c("Zalo không cho biết OA nào vừa cấp quyền.", "Zalo did not say which OA was granted.")
        _set(state, status="error", error=msg)
        return {"ok": False, "error": msg}
    name = str(info.get("bot_name") or "")
    _set(state, status="ready", oa_id=cr["oa_id"], oa_name=name, credentials=cr,
         account_type=str(info.get("account_type") or ""))
    return {"ok": True, "oa_id": cr["oa_id"], "oa_name": name}


def result(state: str) -> dict:
    """What the dashboard polls: status pending / ready / error, the OA, never a token."""
    _purge()
    with _lock:
        p = _pending.get(str(state or ""))
        if not p:
            return {"ok": False, "status": "expired",
                    "error": _c("Phiên cấp quyền đã hết hạn, bấm Cấp quyền bằng Zalo lần nữa.",
                                "This grant expired, click Grant access with Zalo again.")}
        status = "pending" if p["status"] == "exchanging" else p["status"]
        return {"ok": True, "status": status, "error": p.get("error", ""), "app_id": p["app_id"],
                "oa_id": p.get("oa_id", ""), "oa_name": p.get("oa_name", "")}


def take(state: str) -> dict:
    """The pending grant once ready, for `/zalo-oa/oauth/finish`. {} when missing or not ready."""
    _purge()
    with _lock:
        p = _pending.get(str(state or ""))
        if not p or p.get("status") != "ready":
            return {}
        return dict(p)


def forget(state: str) -> None:
    with _lock:
        _pending.pop(str(state or ""), None)
