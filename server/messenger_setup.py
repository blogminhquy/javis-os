"""Messenger setup wizard and health check (0.311.0).

The Messenger channel itself lives in `messenger_bot` and `channels/messenger`. What owners got
stuck on was everything AROUND it, all of it done by hand on developers.facebook.com:

  - pasting a USER token where a PAGE token is needed (Graph error 100 on check, error 210 when
    the bot subscribes the Page or sends a reply);
  - a short-lived token that dies within the hour;
  - an app webhook saved without the `messages` field ticked, so Meta never calls Javis and
    the bot looks healthy while hearing nothing;
  - a token without `pages_read_engagement` / `pages_manage_metadata`.

This module turns those steps into API calls. `connect()` takes the four things an owner can
copy from Meta (Page id, App id, App secret, any user or Page token from Graph API Explorer),
derives a non-expiring Page token, registers the app webhook with the right fields, subscribes
the Page and returns the same checklist `check()` produces. `check()` reruns that checklist on
a saved account, so the dashboard card and the `messenger_check` tool share one source of truth.

Nothing here prints or returns a token. Results carry ids, names, scopes and dates only.
"""
from __future__ import annotations

import time
from typing import Optional

import httpx

import localefmt
from messenger_bot import (FEED_FIELD, GRAPH, SUBSCRIBED_FIELDS, _explain_error, appsecret_proof, subscribe_page,
                           whoami)

WEBHOOK_PATH = "/messenger/webhook"
# What the bot needs at run time. `pages_show_list` is only needed while deriving the Page token,
# so it is not part of the run-time check.
REQUIRED_SCOPES = ("pages_messaging", "pages_manage_metadata", "pages_read_engagement")
WEBHOOK_FIELDS = tuple(SUBSCRIBED_FIELDS.split(","))
# Page comments (0.434.0): reading them and replying under them. Optional, so a warning when missing.
COMMENT_SCOPES = ("pages_read_user_content", "pages_manage_engagement")
# Posting through the Facebook Pages tools on this same connection (0.438.0). Optional, a warning when missing.
POST_SCOPES = ("pages_manage_posts",)


def _app_token(app_id: str, app_secret: str) -> str:
    return f"{app_id}|{app_secret}"


def _err(d: dict, fallback: str = "") -> str:
    e = (d or {}).get("error") or {}
    return _explain_error(e.get("code"), e.get("message") or fallback, e.get("error_subcode"))


async def _get(client, path: str, params: dict) -> dict:
    try:
        r = await client.get(f"{GRAPH}/{path}", params=params)
        return r.json() or {}
    except Exception as e:
        return {"error": {"message": f"{type(e).__name__}: {e}"}}


async def _post(client, path: str, params: dict) -> dict:
    try:
        r = await client.post(f"{GRAPH}/{path}", params=params)
        return r.json() or {}
    except Exception as e:
        return {"error": {"message": f"{type(e).__name__}: {e}"}}


async def debug_token(client, token: str, app_id: str = "", app_secret: str = "") -> dict:
    """Graph's own view of a token: type, app, Page, scopes, expiry. Uses the app token when the
    app credentials are known, otherwise the token inspects itself."""
    inspector = _app_token(app_id, app_secret) if app_id and app_secret else token
    d = await _get(client, "debug_token", {"input_token": token, "access_token": inspector})
    data = d.get("data") or {}
    if d.get("error") or not data:
        return {"ok": False, "error": _err(d, "debug_token failed")}
    return {
        "ok": True,
        "valid": bool(data.get("is_valid")),
        "type": str(data.get("type") or "").upper(),
        "app_id": str(data.get("app_id") or ""),
        "profile_id": str(data.get("profile_id") or ""),
        "user_id": str(data.get("user_id") or ""),
        "scopes": [str(s) for s in (data.get("scopes") or [])],
        "expires_at": int(data.get("expires_at") or 0),
        "data_access_expires_at": int(data.get("data_access_expires_at") or 0),
    }


async def page_token_from(client, token: str, page_id: str, app_id: str, app_secret: str) -> dict:
    """Any token the owner pasted -> a Page token for `page_id`.

    A Page token for the right Page is used as is. A user token is first exchanged for a
    long-lived one (`fb_exchange_token`); the Page token read from a long-lived user token does
    not expire, which is what a bot that runs for months needs."""
    info = await debug_token(client, token, app_id, app_secret)
    if not info.get("ok"):
        return {"ok": False, "error": info.get("error")}
    if not info.get("valid"):
        return {"ok": False, "error": localefmt.chu(
            "Token đã hết hạn hoặc bị thu hồi. Bấm Generate Access Token trong Graph API Explorer để lấy token mới.",
            "The token expired or was revoked. Click Generate Access Token in Graph API Explorer for a new one.")}
    if info.get("app_id") and info["app_id"] != str(app_id):
        return {"ok": False, "error": localefmt.chu(
            f"Token này được tạo trong app {info['app_id']}, không phải app {app_id}. Chọn đúng app trong Graph API Explorer rồi tạo lại token.",
            f"This token was made in app {info['app_id']}, not app {app_id}. Pick the right app in Graph API Explorer and generate it again.")}
    if info.get("type") == "PAGE":
        if info.get("profile_id") and info["profile_id"] != str(page_id):
            return {"ok": False, "error": localefmt.chu(
                f"Đây là token của Trang {info['profile_id']}, không phải Trang {page_id}.",
                f"This is a token for Page {info['profile_id']}, not Page {page_id}.")}
        return {"ok": True, "page_token": token, "source": "page"}
    if info.get("type") != "USER":
        return {"ok": False, "error": localefmt.chu(
            f"Cần token người dùng hoặc token Trang, đây là token loại {info.get('type') or '?'}.",
            f"A user or Page token is needed, this one is of type {info.get('type') or '?'}.")}
    ex = await _get(client, "oauth/access_token", {
        "grant_type": "fb_exchange_token", "client_id": app_id, "client_secret": app_secret,
        "fb_exchange_token": token})
    long_user = str(ex.get("access_token") or "")
    if not long_user:
        return {"ok": False, "error": localefmt.chu("Không đổi được sang token dài hạn: ", "Could not get a long-lived token: ")
                + _err(ex, "exchange failed")}
    pg = await _get(client, str(page_id), {
        "fields": "name,access_token", "access_token": long_user,
        "appsecret_proof": appsecret_proof(long_user, app_secret)})
    page_token = str(pg.get("access_token") or "")
    if not page_token:
        if pg.get("error"):
            return {"ok": False, "error": _err(pg, "page lookup failed")}
        return {"ok": False, "error": localefmt.chu(
            "Tài khoản này không lấy được token của Trang. Khi bấm Generate Access Token, hãy tick đúng Trang và "
            "cấp quyền pages_show_list, pages_messaging, pages_manage_metadata, pages_read_engagement.",
            "This account could not get the Page's token. When you click Generate Access Token, tick the right Page "
            "and grant pages_show_list, pages_messaging, pages_manage_metadata, pages_read_engagement.")}
    return {"ok": True, "page_token": page_token, "source": "user", "page_name": str(pg.get("name") or "")}


async def app_webhook(client, app_id: str, app_secret: str) -> dict:
    """The `page` subscription of the app: callback URL, active flag, fields. {} when none."""
    d = await _get(client, f"{app_id}/subscriptions", {"access_token": _app_token(app_id, app_secret)})
    if d.get("error"):
        return {"ok": False, "error": _err(d, "subscriptions read failed")}
    for s in d.get("data") or []:
        if s.get("object") == "page":
            fields = [str(f.get("name") if isinstance(f, dict) else f) for f in (s.get("fields") or [])]
            return {"ok": True, "found": True, "callback_url": str(s.get("callback_url") or ""),
                    "active": bool(s.get("active")), "fields": fields}
    return {"ok": True, "found": False, "callback_url": "", "active": False, "fields": []}


async def set_app_webhook(client, app_id: str, app_secret: str, callback_url: str, verify_token: str) -> dict:
    """Register (or overwrite) the app's `page` webhook with the fields the bot needs. Meta calls
    `callback_url` with the verify token while this request is open, so Javis must be reachable
    at that address for it to succeed."""
    params = {"object": "page", "callback_url": callback_url, "fields": SUBSCRIBED_FIELDS + "," + FEED_FIELD,
              "include_values": "true", "verify_token": verify_token,
              "access_token": _app_token(app_id, app_secret)}
    d = await _post(client, f"{app_id}/subscriptions", params)
    if not d.get("error") and d.get("success"):
        return {"ok": True, "feed": True}
    # `feed` (comments) is optional: never lose the message webhook over it.
    d = await _post(client, f"{app_id}/subscriptions", {**params, "fields": SUBSCRIBED_FIELDS})
    if d.get("error") or not d.get("success"):
        return {"ok": False, "error": _err(d, "webhook setup failed")}
    return {"ok": True, "feed": False}


async def page_subscription(client, page_id: str, page_token: str, app_id: str) -> dict:
    d = await _get(client, f"{page_id}/subscribed_apps", {"access_token": page_token})
    if d.get("error"):
        return {"ok": False, "error": _err(d, "subscribed_apps read failed")}
    for a in d.get("data") or []:
        if str(a.get("id") or "") == str(app_id):
            return {"ok": True, "found": True, "fields": [str(f) for f in (a.get("subscribed_fields") or [])]}
    return {"ok": True, "found": False, "fields": []}


def _item(cid: str, ok, label: tuple, detail: str = "", fix: tuple = ("", ""), auto: bool = False) -> dict:
    """One row of the checklist. `ok` is True, False, or None for a warning that does not stop
    the bot. `auto` marks problems the Repair button can fix by itself."""
    return {"id": cid, "ok": ok, "label": localefmt.chu(*label), "detail": detail,
            "fix": localefmt.chu(*fix) if fix[0] else "", "auto": auto}


def _date(ts: int) -> str:
    try:
        return time.strftime("%Y-%m-%d", time.localtime(int(ts)))
    except Exception:
        return ""


def comments_item(scopes, page_fields) -> dict:
    """Warning row for Page comments: the permissions and the `feed` subscription. Never red, the
    inbox and the bot work without comments."""
    lack = [x for x in COMMENT_SCOPES if x not in (scopes or [])]
    if FEED_FIELD not in (page_fields or []):
        lack.append(FEED_FIELD)
    return _item("comments", True if not lack else None, ("Nhận bình luận Trang", "Receives Page comments"),
                 ", ".join(lack) if lack else "",
                 ("Đăng nhập Facebook lại ở thẻ Messenger, cấp đủ quyền, rồi bấm Sửa tự động.",
                  "Log in with Facebook again on the Messenger card, grant every permission, then click Repair."))


def posts_item(scopes) -> dict:
    """Warning row for posting to the Page with the Facebook Pages tools. Never red."""
    lack = [x for x in POST_SCOPES if x not in (scopes or [])]
    return _item("posts", True if not lack else None, ("Đăng bài lên Trang", "Can post to the Page"),
                 ", ".join(lack),
                 ("Đăng nhập Facebook lại ở thẻ Messenger và đồng ý quyền đăng bài.",
                  "Log in with Facebook again on the Messenger card and accept the posting permission."))


async def run_checks(client, page_id: str, page_token: str, app_secret: str, app_id: str = "",
                     webhook_url: str = "", bot_running: Optional[bool] = None) -> dict:
    """The full checklist for one Page. Returns {"ok", "app_id", "page_name", "items"}; "ok" is
    True only when no row is red."""
    items = []
    info = await debug_token(client, page_token, app_id, app_secret)
    if not info.get("ok"):
        items.append(_item("token", False, ("Token hợp lệ", "Token is valid"), info.get("error", ""),
                           ("Kết nối lại bằng một token mới.", "Connect again with a fresh token.")))
        return {"ok": False, "app_id": app_id, "page_name": "", "items": items}
    app_id = app_id or info.get("app_id", "")
    items.append(_item("token", info["valid"], ("Token hợp lệ", "Token is valid"), "",
                       ("Token hết hạn hoặc bị thu hồi. Kết nối lại bằng token mới.",
                        "The token expired or was revoked. Connect again with a new token.")))
    is_page = info["type"] == "PAGE"
    items.append(_item("token_type", is_page, ("Là token của Trang", "Is a Page token"), info["type"],
                       ("Đang là token người dùng, Meta sẽ báo lỗi 210 khi gửi tin. Kết nối lại để Javis tự đổi sang token Trang.",
                        "This is a user token, Meta answers error 210 when sending. Connect again and Javis derives the Page token.")))
    if is_page:
        same = not info["profile_id"] or info["profile_id"] == str(page_id)
        items.append(_item("token_page", same, ("Token đúng Trang", "Token matches the Page"), info["profile_id"],
                           ("Token thuộc Trang khác. Kết nối lại với đúng Trang.",
                            "The token belongs to another Page. Connect again with the right Page.")))
    missing = [s for s in REQUIRED_SCOPES if s not in info["scopes"]]
    items.append(_item("scopes", not missing, ("Đủ quyền", "Has the permissions"),
                       ", ".join(missing) if missing else ", ".join(s for s in REQUIRED_SCOPES),
                       ("Thiếu quyền " + ", ".join(missing) + ". Thêm quyền đó trong Graph API Explorer rồi kết nối lại.",
                        "Missing " + ", ".join(missing) + ". Add it in Graph API Explorer and connect again.")))
    exp = info["expires_at"]
    items.append(_item("expiry", True if not exp else None, ("Không hết hạn", "Does not expire"),
                       "" if not exp else _date(exp),
                       ("", "") if not exp else ("Token sẽ hết hạn. Kết nối lại để có token Trang không hết hạn.",
                                                  "The token will expire. Connect again for a non-expiring Page token.")))
    who = await whoami(client, page_id, page_token, app_secret)
    items.append(_item("secret", bool(who.get("ok")), ("App secret khớp", "App secret matches"),
                       "" if who.get("ok") else who.get("error", ""),
                       ("Lấy lại App secret ở Cài đặt ứng dụng, Thông tin cơ bản của đúng app.",
                        "Copy the App secret again from App settings, Basic of the right app.")))
    page_name = who.get("bot_name", "") if who.get("ok") else ""

    if app_id:
        wh = await app_webhook(client, app_id, app_secret)
        if not wh.get("ok"):
            items.append(_item("webhook", False, ("Webhook của app", "App webhook"), wh.get("error", ""),
                               ("Bấm Sửa tự động.", "Click Repair."), auto=True))
        else:
            url = wh.get("callback_url", "")
            url_ok = wh.get("found") and url.rstrip("/").endswith(WEBHOOK_PATH) and (
                not webhook_url or url.rstrip("/") == webhook_url.rstrip("/"))
            items.append(_item("webhook", bool(url_ok and wh.get("active")),
                               ("Webhook của app trỏ về Javis", "App webhook points at Javis"), url,
                               ("Bấm Sửa tự động để Javis khai lại webhook.", "Click Repair and Javis registers the webhook again."),
                               auto=True))
            lack = [f for f in WEBHOOK_FIELDS if f not in wh.get("fields", [])]
            items.append(_item("webhook_fields", wh.get("found") and not lack,
                               ("Webhook nhận tin nhắn", "Webhook receives messages"),
                               ", ".join(lack) if lack else ", ".join(WEBHOOK_FIELDS),
                               ("Meta chưa gửi tin sang Javis. Bấm Sửa tự động.", "Meta does not forward messages yet. Click Repair."),
                               auto=True))
        if is_page:
            ps = await page_subscription(client, page_id, page_token, app_id)
            lack = [f for f in WEBHOOK_FIELDS if f not in ps.get("fields", [])]
            items.append(_item("page_sub", bool(ps.get("ok") and ps.get("found") and not lack),
                               ("Trang gắn với app", "Page is subscribed to the app"),
                               ps.get("error", "") if not ps.get("ok") else ", ".join(ps.get("fields", [])),
                               ("Bấm Sửa tự động.", "Click Repair."), auto=True))
            items.append(comments_item(info["scopes"], ps.get("fields", []) if ps.get("ok") else []))
    items.append(posts_item(info["scopes"]))
    if bot_running is not None:
        items.append(_item("bot", None if not bot_running else True, ("Có bot đang trực", "A bot is answering"), "",
                           ("Vào Chatbot, Bot, tạo hoặc bật bot cho kênh này.",
                            "Open Chatbot, Bots and create or turn on a bot for this channel.")))
    return {"ok": all(i["ok"] is not False for i in items), "app_id": app_id, "page_name": page_name, "items": items}


async def repair(client, page_id: str, page_token: str, app_id: str, app_secret: str,
                 webhook_url: str, verify_token: str) -> dict:
    """Fix what can be fixed without the owner: the app webhook and the Page subscription."""
    notes = []
    if webhook_url.startswith("https://"):
        r = await set_app_webhook(client, app_id, app_secret, webhook_url, verify_token)
        if not r.get("ok"):
            notes.append(r.get("error", ""))
    else:
        notes.append(localefmt.chu("Mở Javis bằng địa chỉ HTTPS rồi bấm lại, Meta chỉ gửi tin tới HTTPS.",
                                   "Open Javis over its HTTPS address and try again, Meta only calls HTTPS."))
    s = await subscribe_page(client, page_id, page_token)
    if not s.get("ok"):
        notes.append(s.get("error", ""))
    return {"ok": not notes, "errors": [n for n in notes if n]}


async def connect(page_id: str, app_id: str, app_secret: str, token: str, webhook_url: str,
                  verify_token: str, client=None) -> dict:
    """The whole wizard in one call. Returns {"ok", "page_token", "page_name", "check"} or
    {"ok": False, "error", "step"}. The caller stores the Page token; it is never shown."""
    page_id, app_id = str(page_id or "").strip(), str(app_id or "").strip()
    app_secret, token = str(app_secret or "").strip(), str(token or "").strip()
    if not page_id.isdigit() or not app_id.isdigit():
        return {"ok": False, "step": "input", "error": localefmt.chu("Page ID và App ID phải là dãy số.",
                                                                    "The Page ID and App ID must be digits.")}
    if len(app_secret) != 32:
        return {"ok": False, "step": "input", "error": localefmt.chu("App secret phải đủ 32 ký tự.",
                                                                    "The App secret must be 32 characters.")}
    if len(token) < 40:
        return {"ok": False, "step": "input", "error": localefmt.chu("Token quá ngắn, hãy chép lại cả chuỗi EAA...",
                                                                    "The token is too short, copy the whole EAA... string.")}
    if not str(webhook_url or "").startswith("https://"):
        return {"ok": False, "step": "https", "error": localefmt.chu(
            "Javis cần địa chỉ HTTPS (Cài đặt, Truy cập từ xa) và bạn phải mở Javis bằng địa chỉ đó.",
            "Javis needs an HTTPS address (Settings, Remote access) and you must open Javis through it.")}
    own = client is None
    client = client or httpx.AsyncClient(timeout=25)
    try:
        pt = await page_token_from(client, token, page_id, app_id, app_secret)
        if not pt.get("ok"):
            return {"ok": False, "step": "token", "error": pt.get("error", "")}
        page_token = pt["page_token"]
        who = await whoami(client, page_id, page_token, app_secret)
        if not who.get("ok"):
            return {"ok": False, "step": "token", "error": who.get("error", "")}
        rep = await repair(client, page_id, page_token, app_id, app_secret, webhook_url, verify_token)
        chk = await run_checks(client, page_id, page_token, app_secret, app_id, webhook_url)
        return {"ok": True, "page_token": page_token, "page_name": who.get("bot_name", ""),
                "repair_errors": rep.get("errors", []), "check": chk}
    finally:
        if own:
            await client.aclose()
