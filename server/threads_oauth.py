"""Log in to Threads (0.448.0): connect a Threads account from the Meta connection card.

Threads signs in on threads.net with its OWN app id and secret (App Dashboard, Use cases, Access the Threads API,
Settings: "Threads app ID" / "Threads app secret"), not the Meta app's. The flow, like `messenger_oauth`:

  1. `start(app_id, app_secret, redirect_uri)` checks the input and opens a pending login; the card opens the
     returned threads.net address in a new tab and polls `result(state)`.
  2. Threads sends the browser back to `/threads/oauth/callback`: `callback` turns the code into a short-lived token,
     exchanges it for a 60-day one (`th_exchange_token`), reads the account, and leaves the outcome under `state`.
  3. The callback route in main.py saves the account right away (there is nothing to pick: one login is one
     account); the bot refreshes the token from then on.

Nothing here returns a token to the dashboard.
"""
from __future__ import annotations

import secrets
import threading
import time
from typing import Any, Dict
from urllib.parse import urlencode

import httpx

import localefmt
from threads_bot import GRAPH, GRAPH_HOST, _err, whoami

CALLBACK_PATH = "/threads/oauth/callback"
UNINSTALL_PATH = "/threads/uninstall"
DELETE_PATH = "/threads/delete"
AUTHORIZE_URL = "https://threads.net/oauth/authorize"
TTL = 15 * 60
# Read the account, read and answer replies under its posts, publish (Javis can post to Threads when asked).
SCOPES = ("threads_basic", "threads_read_replies", "threads_manage_replies", "threads_content_publish")

_lock = threading.Lock()
_pending: Dict[str, Dict[str, Any]] = {}


def _c(vi: str, en: str) -> str:
    return localefmt.chu(vi, en)


def _purge(now: float = 0.0) -> None:
    now = now or time.time()
    with _lock:
        for k in [k for k, v in _pending.items() if now - v.get("created", 0) > TTL]:
            _pending.pop(k, None)


def check_input(app_id: str, app_secret: str) -> str:
    if not str(app_id or "").strip().isdigit():
        return _c("Threads App ID phải là dãy số.", "The Threads App ID must be digits.")
    if len(str(app_secret or "").strip()) != 32:
        return _c("Threads App secret phải đủ 32 ký tự.", "The Threads App secret must be 32 characters.")
    return ""


def login_url(app_id: str, redirect_uri: str, state: str) -> str:
    q = {"client_id": app_id, "redirect_uri": redirect_uri, "scope": ",".join(SCOPES), "response_type": "code",
         "state": state}
    return AUTHORIZE_URL + "?" + urlencode(q)


def start(app_id: str, app_secret: str, redirect_uri: str, brain: str = "", comments: str = "") -> dict:
    """Open a pending login. {"ok", "url", "state"} or {"ok": False, "error"}."""
    app_id, app_secret = str(app_id or "").strip(), str(app_secret or "").strip()
    bad = check_input(app_id, app_secret)
    if bad:
        return {"ok": False, "error": bad}
    if not str(redirect_uri or "").startswith("https://"):
        return {"ok": False, "error": _c(
            "Javis cần địa chỉ HTTPS (Cài đặt, Truy cập từ xa) và bạn phải mở Javis bằng địa chỉ đó.",
            "Javis needs an HTTPS address (Settings, Remote access) and you must open Javis through it.")}
    _purge()
    state = secrets.token_urlsafe(24)
    with _lock:
        _pending[state] = {"created": time.time(), "status": "pending", "app_id": app_id, "app_secret": app_secret,
                           "redirect_uri": redirect_uri, "brain": str(brain or ""), "comments": str(comments or ""),
                           "error": "", "account": {}}
    return {"ok": True, "state": state, "url": login_url(app_id, redirect_uri, state)}


def _set(state: str, **kw) -> None:
    with _lock:
        if state in _pending:
            _pending[state].update(kw)


async def callback(state: str, code: str, error: str = "", error_description: str = "", client=None) -> dict:
    """Threads sent the browser back. {"ok", "account"} or {"ok": False, "error"}; the card reads the same outcome
    through `result(state)`."""
    _purge()
    with _lock:
        p = dict(_pending.get(str(state or "")) or {})
    if not p:
        return {"ok": False, "error": _c("Phiên đăng nhập đã hết hạn. Quay lại Javis bấm Đăng nhập Threads lần nữa.",
                                         "This sign-in expired. Go back to Javis and click Log in to Threads again.")}
    if error or not code:
        msg = error_description or error or _c("Threads không trả mã đăng nhập.", "Threads returned no sign-in code.")
        if error == "access_denied":
            msg = _c("Bạn đã bấm Huỷ trên Threads.", "You cancelled on Threads.")
        _set(state, status="error", error=msg)
        return {"ok": False, "error": msg}
    own = client is None
    client = client or httpx.AsyncClient(timeout=25)
    try:
        r = await client.post(f"{GRAPH_HOST}/oauth/access_token", data={
            "client_id": p["app_id"], "client_secret": p["app_secret"], "grant_type": "authorization_code",
            "redirect_uri": p["redirect_uri"], "code": str(code).split("#")[0]})
        d = r.json() or {}
        short = str(d.get("access_token") or "")
        if not short:
            msg = _c("Không đổi được mã đăng nhập: ", "Could not exchange the sign-in code: ") + _err(d, "exchange failed")
            _set(state, status="error", error=msg)
            return {"ok": False, "error": msg}
        r = await client.get(f"{GRAPH_HOST}/access_token", params={
            "grant_type": "th_exchange_token", "client_secret": p["app_secret"], "access_token": short})
        ex = r.json() or {}
        token = str(ex.get("access_token") or "") or short
        expires = int(ex.get("expires_in") or 0)
        who = await whoami(client, token)
    except Exception as e:
        msg = _c(f"Không nối được Threads: {e}", f"Could not reach Threads: {e}")
        _set(state, status="error", error=msg)
        return {"ok": False, "error": msg}
    finally:
        if own:
            await client.aclose()
    if not who.get("ok"):
        _set(state, status="error", error=who.get("error", ""))
        return {"ok": False, "error": who.get("error", "")}
    acc = {"id": who["id"], "username": who.get("username", ""), "name": who.get("name", "")}
    _set(state, status="ready", account=acc, token=token, expires_in=expires)
    return {"ok": True, "account": acc}


def result(state: str) -> dict:
    """What the card polls: pending / ready / error and the account, never the token."""
    _purge()
    with _lock:
        p = _pending.get(str(state or ""))
        if not p:
            return {"ok": False, "status": "expired",
                    "error": _c("Phiên đăng nhập đã hết hạn, bấm Đăng nhập Threads lần nữa.",
                                "This sign-in expired, click Log in to Threads again.")}
        return {"ok": True, "status": p["status"], "error": p.get("error", ""), "account": dict(p.get("account") or {})}


def take(state: str) -> dict:
    """The credentials of a ready login, for the callback route that saves it. {} when missing or not ready."""
    _purge()
    with _lock:
        p = _pending.get(str(state or ""))
        return dict(p) if p and p.get("status") == "ready" else {}


def forget(state: str) -> None:
    with _lock:
        _pending.pop(str(state or ""), None)


__all__ = ["GRAPH", "SCOPES", "start", "callback", "result", "take", "forget", "login_url"]
