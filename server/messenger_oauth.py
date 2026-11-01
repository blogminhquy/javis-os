"""Log in with Facebook to connect Pages to the Messenger channel (0.434.0).

The 0.311.0 wizard asked for four pasted things: Page ID, App ID, App secret and a token copied from
Graph API Explorer. The token was where owners got lost. This module replaces that step with the
standard Facebook Login redirect flow on the owner's OWN Meta app:

  1. `start()` checks the App ID and App secret (an app token call) and returns the Facebook
     login address. The owner adds this Javis's callback address to the app's Valid OAuth
     Redirect URIs once; the card shows it ready to copy.
  2. Facebook sends the browser back to `/messenger/oauth/callback`; `callback()` trades the code
     for a user token, makes it long-lived and lists the Pages the person manages.
  3. The dashboard polls `result()` for that list and the owner ticks Pages; `/messenger/oauth/finish`
     hands each ticked Page to `messenger_setup.connect`, which derives the non-expiring Page
     token, registers the webhook and subscribes the Page, exactly as the wizard did.

Why the owner's own app and not one shared "Javis OS" app: every Javis runs at its own address,
Meta wants each redirect URI registered in advance, its webhook takes one callback URL per app,
and the repo is public so it cannot carry an app secret. A shared app needs a central relay;
this flow needs nothing outside the owner's Javis.

Pending logins live in memory for 15 minutes and are keyed by an unguessable `state`. The user
token never leaves this module or the server; results carry Page ids, names and pictures only.
Endpoints are configurable (`JAVIS_FACEBOOK_WEB`) so tests can point the login address elsewhere.
"""
from __future__ import annotations

import os
import secrets
import threading
import time
from typing import Any, Dict
from urllib.parse import urlencode

import httpx

import localefmt
from messenger_bot import GRAPH, GRAPH_VERSION, _explain_error, appsecret_proof

CALLBACK_PATH = "/messenger/oauth/callback"
PRIVACY_PATH = "/messenger/privacy"
TTL = 15 * 60
# Messaging, the Page list, the webhook subscription, and Page comments (read, reply). `business_management`
# lets Pages owned through a Business portfolio show up in the list.
SCOPES = ("pages_show_list", "pages_messaging", "pages_manage_metadata", "pages_read_engagement",
          "pages_read_user_content", "pages_manage_engagement", "business_management")

_lock = threading.Lock()
_pending: Dict[str, Dict[str, Any]] = {}


def _c(vi: str, en: str) -> str:
    return localefmt.chu(vi, en)


def _web() -> str:
    return (os.environ.get("JAVIS_FACEBOOK_WEB") or "https://www.facebook.com").rstrip("/")


def _purge(now: float = 0.0) -> None:
    now = now or time.time()
    with _lock:
        for k in [k for k, v in _pending.items() if now - v.get("created", 0) > TTL]:
            _pending.pop(k, None)


def _err(d: dict, fallback: str) -> str:
    e = (d or {}).get("error") or {}
    return _explain_error(e.get("code"), e.get("message") or fallback, e.get("error_subcode"))


def check_input(app_id: str, app_secret: str) -> str:
    """'' when the App ID and App secret look right, else the error to show."""
    if not str(app_id or "").strip().isdigit():
        return _c("App ID phải là dãy số.", "The App ID must be digits.")
    if len(str(app_secret or "").strip()) != 32:
        return _c("App secret phải đủ 32 ký tự.", "The App secret must be 32 characters.")
    return ""


def login_url(app_id: str, redirect_uri: str, state: str) -> str:
    q = {"client_id": app_id, "redirect_uri": redirect_uri, "state": state, "response_type": "code",
         "scope": ",".join(SCOPES), "auth_type": "rerequest"}
    return f"{_web()}/{GRAPH_VERSION}/dialog/oauth?" + urlencode(q)


async def start(app_id: str, app_secret: str, redirect_uri: str, brain: str = "", label: str = "",
                client=None) -> dict:
    """Check the app credentials, open a pending login. {"ok", "url", "state"} or {"ok": False, "error"}."""
    app_id, app_secret = str(app_id or "").strip(), str(app_secret or "").strip()
    bad = check_input(app_id, app_secret)
    if bad:
        return {"ok": False, "error": bad}
    if not str(redirect_uri or "").startswith("https://"):
        return {"ok": False, "error": _c(
            "Javis cần địa chỉ HTTPS (Cài đặt, Truy cập từ xa) và bạn phải mở Javis bằng địa chỉ đó.",
            "Javis needs an HTTPS address (Settings, Remote access) and you must open Javis through it.")}
    own = client is None
    client = client or httpx.AsyncClient(timeout=20)
    try:
        r = await client.get(f"{GRAPH}/{app_id}", params={"fields": "id,name",
                                                           "access_token": f"{app_id}|{app_secret}"})
        d = r.json() or {}
    except Exception as e:
        return {"ok": False, "error": _c(f"Không nối được Meta: {e}", f"Could not reach Meta: {e}")}
    finally:
        if own:
            await client.aclose()
    if d.get("error") or str(d.get("id") or "") != app_id:
        return {"ok": False, "error": _c("App ID hoặc App secret không đúng. Chép lại cả hai ở Cài đặt ứng dụng, "
                                         "Thông tin cơ bản của app Meta.",
                                         "The App ID or App secret is wrong. Copy both again from App settings, "
                                         "Basic of the Meta app.")}
    _purge()
    state = secrets.token_urlsafe(24)
    with _lock:
        _pending[state] = {"created": time.time(), "status": "pending", "app_id": app_id, "app_secret": app_secret,
                           "app_name": str(d.get("name") or ""), "redirect_uri": redirect_uri,
                           "brain": str(brain or ""), "label": str(label or ""), "pages": [], "error": ""}
    return {"ok": True, "state": state, "url": login_url(app_id, redirect_uri, state)}


def _set(state: str, **kw) -> None:
    with _lock:
        if state in _pending:
            _pending[state].update(kw)


async def callback(state: str, code: str, error: str = "", error_description: str = "", client=None) -> dict:
    """Facebook sent the browser back. {"ok", "pages"} or {"ok": False, "error"}; the dashboard
    reads the same outcome through `result(state)`."""
    _purge()
    with _lock:
        p = dict(_pending.get(str(state or "")) or {})
    if not p:
        return {"ok": False, "error": _c("Phiên đăng nhập đã hết hạn. Quay lại Javis bấm Đăng nhập Facebook lần nữa.",
                                         "This sign-in expired. Go back to Javis and click Log in with Facebook again.")}
    if error or not code:
        msg = error_description or error or _c("Facebook không trả mã đăng nhập.", "Facebook returned no sign-in code.")
        if error == "access_denied":
            msg = _c("Bạn đã bấm Huỷ trên Facebook.", "You cancelled on Facebook.")
        _set(state, status="error", error=msg)
        return {"ok": False, "error": msg}
    own = client is None
    client = client or httpx.AsyncClient(timeout=25)
    try:
        r = await client.get(f"{GRAPH}/oauth/access_token", params={
            "client_id": p["app_id"], "client_secret": p["app_secret"], "redirect_uri": p["redirect_uri"],
            "code": code})
        d = r.json() or {}
        short = str(d.get("access_token") or "")
        if not short:
            msg = _c("Không đổi được mã đăng nhập: ", "Could not exchange the sign-in code: ") + _err(d, "exchange failed")
            _set(state, status="error", error=msg)
            return {"ok": False, "error": msg}
        r = await client.get(f"{GRAPH}/oauth/access_token", params={
            "grant_type": "fb_exchange_token", "client_id": p["app_id"], "client_secret": p["app_secret"],
            "fb_exchange_token": short})
        user_token = str((r.json() or {}).get("access_token") or "") or short
        r = await client.get(f"{GRAPH}/me/accounts", params={
            "fields": "id,name,picture{url}", "limit": 100, "access_token": user_token,
            "appsecret_proof": appsecret_proof(user_token, p["app_secret"])})
        d = r.json() or {}
    except Exception as e:
        msg = _c(f"Không nối được Meta: {e}", f"Could not reach Meta: {e}")
        _set(state, status="error", error=msg)
        return {"ok": False, "error": msg}
    finally:
        if own:
            await client.aclose()
    if d.get("error"):
        msg = _err(d, "page list failed")
        _set(state, status="error", error=msg)
        return {"ok": False, "error": msg}
    pages = [{"id": str(x.get("id") or ""), "name": str(x.get("name") or ""),
              "picture": str(((x.get("picture") or {}).get("data") or {}).get("url") or "")}
             for x in (d.get("data") or []) if str(x.get("id") or "").isdigit()]
    if not pages:
        msg = _c("Tài khoản này không quản lý Fanpage nào, hoặc bạn chưa tick Trang nào lúc đăng nhập. Bấm Đăng nhập "
                 "Facebook lại và chọn đúng Trang.",
                 "This account manages no Page, or no Page was ticked while signing in. Log in with Facebook again "
                 "and pick the right Pages.")
        _set(state, status="error", error=msg)
        return {"ok": False, "error": msg}
    _set(state, status="ready", pages=pages, user_token=user_token)
    return {"ok": True, "pages": pages}


def result(state: str) -> dict:
    """What the dashboard polls: status pending / ready / error, the Pages, never the token."""
    _purge()
    with _lock:
        p = _pending.get(str(state or ""))
        if not p:
            return {"ok": False, "status": "expired",
                    "error": _c("Phiên đăng nhập đã hết hạn, bấm Đăng nhập Facebook lần nữa.",
                                "This sign-in expired, click Log in with Facebook again.")}
        return {"ok": True, "status": p["status"], "error": p.get("error", ""), "app_id": p["app_id"],
                "app_name": p.get("app_name", ""), "pages": list(p.get("pages") or [])}


def take(state: str) -> dict:
    """The credentials of a ready login, for `/messenger/oauth/finish`. {} when missing or not ready.
    The login stays until `forget` so a Page that failed can be retried in the same session."""
    _purge()
    with _lock:
        p = _pending.get(str(state or ""))
        if not p or p.get("status") != "ready":
            return {}
        return dict(p)


def forget(state: str) -> None:
    with _lock:
        _pending.pop(str(state or ""), None)


def privacy_html(brand: str = "Javis OS", pages=()) -> str:
    """A plain privacy policy page Meta accepts as the app's Privacy Policy URL and User data deletion
    instructions URL, served by this Javis itself so the owner can switch the app to Live. Both
    languages on one page: Meta's reviewers and the Page's customers may read either."""
    import html as h
    b = h.escape(str(brand or "Javis OS"))
    names = ", ".join(h.escape(str(n)) for n in pages if str(n or "").strip())
    on_vi = f" của {names}" if names else ""
    on_en = f" of {names}" if names else ""
    return f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{b} - Privacy</title>
<style>body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;font-size:18px;line-height:1.65;
max-width:720px;margin:0 auto;padding:24px 16px;color:#1c1c1e;background:#fff}}h1{{font-size:26px}}
h2{{font-size:21px;margin-top:28px}}hr{{margin:36px 0;border:0;border-top:1px solid #ddd}}
@media (prefers-color-scheme:dark){{body{{color:#eee;background:#151517}}hr{{border-top-color:#333}}}}</style>
</head><body>
<h1>Chính sách quyền riêng tư</h1>
<p>Trang này áp dụng cho trợ lý trả lời tin nhắn và bình luận Fanpage{on_vi}, chạy bằng {b} trên máy chủ riêng của chủ Trang.</p>
<h2>Dữ liệu được dùng</h2>
<p>Khi bạn nhắn tin hoặc bình luận trên Trang, chúng tôi nhận tên hiển thị, nội dung tin, ảnh hay tệp bạn gửi. Dữ liệu chỉ dùng để trả lời bạn và để nhân viên của Trang đọc lại cuộc trò chuyện.</p>
<h2>Lưu trữ và chia sẻ</h2>
<p>Dữ liệu nằm trên máy chủ của chủ Trang. Chúng tôi không bán và không chia sẻ dữ liệu cho bên thứ ba. Để soạn câu trả lời, nội dung tin có thể được gửi tới dịch vụ AI mà chủ Trang chọn.</p>
<h2>Xoá dữ liệu</h2>
<p>Muốn xoá dữ liệu của bạn, hãy nhắn cho Trang câu "xoá dữ liệu của tôi". Nhân viên của Trang sẽ xoá cuộc trò chuyện của bạn khỏi hệ thống trong vòng 30 ngày.</p>
<hr>
<h1>Privacy policy</h1>
<p>This page covers the assistant that answers messages and comments on the Facebook Page{on_en}, run with {b} on the Page owner's own server.</p>
<h2>Data used</h2>
<p>When you message or comment on the Page we receive your display name, the content of your message and any image or file you send. It is used only to answer you and to let the Page's staff read the conversation again.</p>
<h2>Storage and sharing</h2>
<p>The data stays on the Page owner's server. We do not sell it or share it with third parties. To write a reply, message content may be sent to the AI service the Page owner chose.</p>
<h2>Deleting your data</h2>
<p>To have your data deleted, send the Page the message "delete my data". The Page's staff will remove your conversation within 30 days.</p>
</body></html>"""
