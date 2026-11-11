"""Bundled plugin (0.311.0): Messenger health check for every engine.

When a Page's bot goes silent the cause is almost always on Meta's side: a user token where a
Page token belongs, a missing permission, an app webhook without the `messages` field, or the
Page not subscribed to the app. `messenger_check` runs the same checklist as the Connections
page card (`messenger_setup.run_checks`); `messenger_repair` re-registers the webhook and the
Page subscription, which changes settings on Meta, hence `min_mode: full`.

Never returns a token or an app secret.
"""
from __future__ import annotations

import json
from urllib.parse import urlsplit, urlunsplit


def _expected_webhook_url(stored: str) -> str:
    """Follow the active quick tunnel while retaining the receiver selected for this account."""
    try:
        old = urlsplit(stored)
        if (old.scheme != "https" or not old.hostname
                or not old.hostname.endswith(".trycloudflare.com")
                or old.username or old.password):
            return stored
        import remote_tunnel
        state = remote_tunnel.MANAGER.status()
        live = urlsplit(str(state.get("url") or ""))
        if (state.get("enabled") is not True or state.get("mode") != "quick"
                or state.get("state") != "running" or live.scheme != "https"
                or not live.hostname or not live.hostname.endswith(".trycloudflare.com")
                or live.username or live.password or live.port not in (None, 443)
                or live.path not in ("", "/") or live.query or live.fragment):
            return stored
        return urlunsplit((live.scheme, live.netloc, old.path, old.query, old.fragment))
    except (ImportError, AttributeError, TypeError, ValueError):
        return stored


async def _webhook_reachable(client, url: str) -> dict:
    """An unsigned GET must reach the receiver. Its normal verification failure is HTTP 403."""
    import httpx
    if not url.startswith("https://"):
        return {"ok": False, "detail": "HTTPS callback required"}
    try:
        response = await client.get(url, timeout=8, follow_redirects=False)
    except httpx.RequestError:
        return {"ok": False, "detail": "HTTPS callback unreachable (DNS, TLS or network)"}
    status = response.status_code
    return {"ok": status in (200, 400, 403, 405), "detail": f"HTTP {status}; no verification token or message sent"}


def _accounts(page: str = ""):
    import channel_accounts
    out = []
    for a in channel_accounts.list_accounts(channel="messenger"):
        if page and page not in (str(a.get("external_id") or ""), str(a.get("id") or ""),
                                 str(a.get("label") or "")):
            continue
        out.append(a)
    return out


async def _standby_check(client, page_id, page_token, app_id, app_secret):
    """An opt-in receive-only account needs standby at both subscription levels."""
    import messenger_setup
    wh = await messenger_setup.app_webhook(client, app_id, app_secret)
    ps = await messenger_setup.page_subscription(client, page_id, page_token, app_id)
    ok = bool(wh.get("ok") and wh.get("active") and ps.get("ok") and ps.get("found")
              and "standby" in wh.get("fields", []) and "standby" in ps.get("fields", []))
    detail = ("app=" + ("subscribed" if "standby" in wh.get("fields", []) else "missing")
              + "; page=" + ("subscribed" if "standby" in ps.get("fields", []) else "missing"))
    if not wh.get("ok") or not ps.get("ok"):
        detail = "Could not read app/Page standby subscriptions"
    return {"label": "Webhook nhận kênh dự phòng", "ok": ok, "detail": detail,
            "fix": "Bấm Sửa tự động để đăng ký standby; quyền xem kênh dự phòng được quản lý trên Meta."}


async def _repair_standby(client, page_id, page_token, app_id, app_secret, url, verify):
    """Preserve existing fields when adding standby. Never take conversation ownership or send."""
    import messenger_bot
    import messenger_setup
    if not url.startswith("https://"):
        return {"errors": ["HTTPS callback required"]}
    wh = await messenger_setup.app_webhook(client, app_id, app_secret)
    ps = await messenger_setup.page_subscription(client, page_id, page_token, app_id)
    if not wh.get("ok") or not ps.get("ok"):
        return {"errors": ["Cannot preserve subscription fields because the current configuration could not be read."]}
    required = {"messages", "messaging_postbacks", "standby"}

    async def update(path, token, data, label):
        try:
            response = await client.post(f"{messenger_bot.GRAPH}/{path}",
                                         headers={"Authorization": "Bearer " + token}, data=data)
            body = response.json()
            if response.is_success and isinstance(body, dict) and body.get("success") is True:
                return ""
            # Raw request/exception/error text may contain credentials. Do not return it.
            return f"{label} failed (HTTP {response.status_code})"
        except Exception:
            return f"{label} failed (network or invalid response)"

    error = await update(f"{app_id}/subscriptions", f"{app_id}|{app_secret}", {
        "object": "page", "callback_url": url, "verify_token": verify, "include_values": "true",
        "fields": ",".join(sorted(required | set(wh.get("fields") or [])))}, "App standby subscription")
    if error:
        return {"errors": [error]}
    error = await update(f"{page_id}/subscribed_apps", page_token, {
        "subscribed_fields": ",".join(sorted(required | set(ps.get("fields") or [])))}, "Page standby subscription")
    return {"errors": [error] if error else []}


async def _run(args, repair: bool):
    import httpx
    import channel_accounts
    import chatbot_store
    import config as cfgmod
    import messenger_bot
    import messenger_setup
    accs = _accounts(str((args or {}).get("page") or "").strip())
    if not accs:
        return json.dumps({"ok": False, "error": "No Messenger account matches. Connect a Page on the Connections page "
                                                 "(card Facebook Messenger) first."}, ensure_ascii=False)
    verify = str((cfgmod.read_settings().get("messenger") or {}).get("verify_token") or "")
    results = []
    reachability = {}
    async with httpx.AsyncClient(timeout=25) as c:
        for a in accs:
            cr = messenger_bot.split_credentials(channel_accounts.get_token(a["id"]))
            meta = a.get("meta") or {}
            app_id = meta.get("app_id", "")
            if not app_id:
                info = await messenger_setup.debug_token(c, cr["access_token"])
                app_id = info.get("app_id", "") if info.get("ok") else ""
            stored_url = str(meta.get("webhook_url") or "")
            url = _expected_webhook_url(stored_url)
            standby = meta.get("webhook_standby") is True
            errs = []
            if repair:
                if not app_id or not verify:
                    errs.append("App id or verify token unknown; reconnect the Page from the Connections page.")
                else:
                    repair_fn = _repair_standby if standby else messenger_setup.repair
                    errs = (await repair_fn(c, cr["page_id"], cr["access_token"], app_id,
                                            cr["app_secret"], url, verify)).get("errors", [])
            running = (cr["page_id"] in messenger_bot.registered()
                       or any(b.get("enabled") for b in chatbot_store.bots_using_account(a["id"])))
            chk = await messenger_setup.run_checks(c, cr["page_id"], cr["access_token"], cr["app_secret"],
                                                   app_id, url, running)
            if standby:
                item = await _standby_check(c, cr["page_id"], cr["access_token"], app_id, cr["app_secret"])
                chk.setdefault("items", []).append(item)
                if item["ok"] is not True:
                    chk["ok"] = False
            if url not in reachability:
                reachability[url] = await _webhook_reachable(c, url)
            reach = reachability[url]
            chk.setdefault("items", []).append({
                "label": "Đường HTTPS webhook truy cập được", "ok": reach["ok"],
                "detail": reach["detail"],
                "fix": "Kiểm tra tunnel hoặc tên miền, rồi kiểm lại trước khi sửa đăng ký Meta."})
            if reach["ok"] is not True:
                chk["ok"] = False
            if repair and not errs and chk.get("ok") is True and url != stored_url:
                saved, _ = channel_accounts.update_account(a["id"], {"meta": {"webhook_url": url}})
                if not saved:
                    errs.append("Meta callback updated, but the expected callback could not be saved locally.")
                    chk["ok"] = False
            results.append({"account": a.get("label"), "page_id": cr["page_id"], "page_name": chk.get("page_name"),
                            "ok": chk.get("ok"), "repair_errors": errs,
                            "items": [{"check": i["label"], "status": {True: "ok", False: "FAIL", None: "warn"}[i["ok"]],
                                       "detail": i["detail"], "fix": i["fix"] if i["ok"] is not True else ""}
                                      for i in chk.get("items", [])]})
    return json.dumps({"ok": True, "pages": results}, ensure_ascii=False)


async def _check(args, ctx):
    return await _run(args, repair=False)


async def _repair(args, ctx):
    return await _run(args, repair=True)


_SCHEMA = {"type": "object", "properties": {
    "page": {"type": "string", "description": "Page ID, account id or account label. Empty = every Messenger account."}}}


def register(ctx):
    ctx.register_tool(
        name="messenger_check",
        description=("Kiểm tra kết nối bot Messenger của Fanpage: token có phải token Trang, đủ quyền, hết hạn chưa, "
                     "App secret khớp, webhook của app trỏ về Javis và có nhận messages, Trang đã gắn app, có bot đang "
                     "trực, và đường HTTPS còn truy cập được. Link nhanh dùng địa chỉ tunnel đang chạy, giữ đường dẫn nhận tin. "
                     "Dùng khi bot Messenger không trả lời khách. Trả từng dòng ok/FAIL/warn kèm cách sửa."),
        handler=_check, min_mode="readonly", schema=_SCHEMA,
    )
    ctx.register_tool(
        name="messenger_repair",
        description=("Sửa tự động kết nối Messenger: khai lại webhook của app Meta (messages, messaging_postbacks) và gắn "
                     "lại Trang vào app, rồi kiểm tra lại. Đổi cài đặt trên Meta. Chỉ gọi khi messenger_check báo dòng "
                     "webhook hoặc Trang gắn app bị FAIL."),
        handler=_repair, min_mode="full", schema=_SCHEMA,
    )
