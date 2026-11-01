"""Sign in to GitHub with one button: the OAuth device flow of the "Javis OS" GitHub App (0.430.0).

Why the device flow and not the redirect flow Claude uses: every Javis runs at its own address (localhost, a VPS IP,
a tunnel), so there is no single callback URL to register, and the repo is public, so it cannot carry a client
secret. The device flow needs neither: Javis asks GitHub for a short code, the person types it at
github.com/login/device and presses Authorize, and Javis polls until GitHub hands over the token. It works the same on
a VPS with no browser.

Why a GitHub App and not an OAuth App: the person picks which repos Javis can see by installing the app on them
(github.com/apps/javis-os/installations/new), and the token only carries the app's fine-grained permissions
(Contents, Pull requests, Workflows read/write; Checks, Commit statuses, Actions read).

The app was registered with expiring user tokens turned off, so the token normally lasts until the person revokes
it. If GitHub still sends `expires_in` and a `refresh_token` (the setting was flipped later), they are kept and
`refresh()` tries to renew; when that fails the connection reads as signed out and the card asks to sign in again.

Pending sign-ins live in memory: a code expires in 15 minutes and a restart simply means pressing the button again.
Endpoints are configurable (`JAVIS_GITHUB_WEB`) so tests run against a local fake. Stdlib plus httpx, no FastAPI.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, Optional

import httpx

import localefmt

# Public identifiers of the "Javis OS" GitHub App (owner, 2026-11-01). A client id is not a secret: the device flow is
# built for apps that cannot keep one. Forks that register their own app override both through the environment.
CLIENT_ID = "Iv23limeL0BsyXptmTz2"
APP_SLUG = "javis-os"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
UA = "javis-os"
_lock = threading.Lock()
_pending: Dict[str, Any] = {}


class OAuthError(Exception):
    """A failure worth showing as is (already localized)."""


def _c(vi: str, en: str) -> str:
    return localefmt.chu(vi, en)


def client_id() -> str:
    return (os.environ.get("JAVIS_GITHUB_CLIENT_ID") or CLIENT_ID).strip()


def app_slug() -> str:
    return (os.environ.get("JAVIS_GITHUB_APP_SLUG") or APP_SLUG).strip()


def _web() -> str:
    return (os.environ.get("JAVIS_GITHUB_WEB") or "https://github.com").rstrip("/")


def install_url() -> str:
    """Where the person picks the repos Javis may see (install the app, or change an existing install)."""
    return f"https://github.com/apps/{app_slug()}/installations/new"


def _post(path: str, data: Dict[str, str]) -> Dict[str, Any]:
    """POST a form to github.com and return its JSON. GitHub answers device-flow errors with 200 and an `error` field."""
    try:
        r = httpx.post(_web() + path, data=data, timeout=20,
                       headers={"Accept": "application/json", "User-Agent": UA})
    except httpx.HTTPError as e:
        raise OAuthError(_c(f"Không gọi được GitHub ({type(e).__name__}). Kiểm tra mạng rồi thử lại.",
                            f"Could not reach GitHub ({type(e).__name__}). Check the network and try again."))
    if r.status_code >= 500:
        raise OAuthError(_c(f"GitHub đang lỗi phía họ ({r.status_code}). Thử lại sau ít phút.",
                            f"GitHub is having an error on their side ({r.status_code}). Try again in a few minutes."))
    try:
        d = r.json()
    except ValueError:
        raise OAuthError(_c(f"GitHub trả về nội dung lạ ({r.status_code}).",
                            f"GitHub sent an unexpected answer ({r.status_code})."))
    return d if isinstance(d, dict) else {}


def _error_text(code: str, desc: str = "") -> str:
    known = {
        "access_denied": _c("Bạn đã bấm từ chối trên GitHub. Bấm Đăng nhập lần nữa nếu muốn kết nối.",
                            "You pressed Cancel on GitHub. Press Sign in again to connect."),
        "expired_token": _c("Mã đã hết hạn. Bấm Đăng nhập lần nữa để lấy mã mới.",
                            "The code expired. Press Sign in again for a new one."),
        "device_flow_disabled": _c("GitHub App của Javis chưa bật Device Flow.",
                                   "The Javis GitHub App does not have Device Flow enabled."),
        "incorrect_client_credentials": _c("GitHub không nhận Client ID của Javis.",
                                           "GitHub does not recognise the Javis client id."),
    }
    return known.get(code) or _c(f"GitHub từ chối đăng nhập: {desc or code}", f"GitHub refused the sign-in: {desc or code}")


def start() -> Dict[str, Any]:
    """Ask GitHub for a device code. Returns what the card shows: the code, the page to type it on, how long it lasts."""
    d = _post("/login/device/code", {"client_id": client_id()})
    if d.get("error"):
        raise OAuthError(_error_text(str(d.get("error")), str(d.get("error_description") or "")))
    if not d.get("device_code") or not d.get("user_code"):
        raise OAuthError(_c("Không xin được mã đăng nhập từ GitHub.", "Could not get a sign-in code from GitHub."))
    interval = max(int(d.get("interval") or 5), 1)
    expires = int(d.get("expires_in") or 900)
    now = time.time()
    with _lock:
        _pending.clear()
        _pending.update(device_code=d["device_code"], interval=interval, expires_at=now + expires, next_at=now + interval)
    return {"user_code": d["user_code"], "verification_uri": d.get("verification_uri") or "https://github.com/login/device",
            "interval": interval, "expires_in": expires}


def poll() -> Dict[str, Any]:
    """One poll. Returns {status: pending} | {status: done, token: {...}} | {status: error, error}.

    The dashboard may poll faster than GitHub allows; a call before `next_at` answers pending without reaching GitHub,
    so Javis never earns a `slow_down`. The token dict stays inside the server (the route stores it and drops it)."""
    with _lock:
        p = dict(_pending)
    if not p:
        return {"status": "error", "error": _c("Chưa bắt đầu đăng nhập.", "Sign-in has not started.")}
    now = time.time()
    if now > p["expires_at"]:
        cancel()
        return {"status": "error", "error": _error_text("expired_token")}
    if now < p["next_at"]:
        return {"status": "pending"}
    try:
        d = _post("/login/oauth/access_token", {"client_id": client_id(), "device_code": p["device_code"],
                                                 "grant_type": DEVICE_GRANT})
    except OAuthError:
        # A network blip mid-wait is not the end of the sign-in; the next poll tries again.
        with _lock:
            if _pending.get("device_code") == p["device_code"]:
                _pending["next_at"] = now + p["interval"]
        return {"status": "pending"}
    err = str(d.get("error") or "")
    if err in ("authorization_pending", "slow_down"):
        with _lock:
            if _pending.get("device_code") == p["device_code"]:
                if err == "slow_down":
                    _pending["interval"] = int(d.get("interval") or p["interval"] + 5)
                _pending["next_at"] = now + _pending["interval"]
        return {"status": "pending"}
    if err:
        cancel()
        return {"status": "error", "error": _error_text(err, str(d.get("error_description") or ""))}
    if not d.get("access_token"):
        return {"status": "pending"}
    cancel()
    return {"status": "done", "token": _token_fields(d, now)}


def _token_fields(d: Dict[str, Any], now: float) -> Dict[str, Any]:
    exp = int(d.get("expires_in") or 0)
    return {"access_token": str(d["access_token"]), "refresh_token": str(d.get("refresh_token") or ""),
            "expires_at": (now + exp) if exp else 0}


def refresh(refresh_token: str) -> Optional[Dict[str, Any]]:
    """Renew an expiring user token. Returns the new token fields, or None when GitHub refuses (sign in again)."""
    if not refresh_token:
        return None
    try:
        d = _post("/login/oauth/access_token", {"client_id": client_id(), "grant_type": "refresh_token",
                                                 "refresh_token": refresh_token})
    except OAuthError:
        return None
    if d.get("error") or not d.get("access_token"):
        return None
    return _token_fields(d, time.time())


def cancel() -> None:
    with _lock:
        _pending.clear()


def pending() -> bool:
    with _lock:
        return bool(_pending)
