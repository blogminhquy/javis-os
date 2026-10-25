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


def _accounts(page: str = ""):
    import channel_accounts
    out = []
    for a in channel_accounts.list_accounts(channel="messenger"):
        if page and page not in (str(a.get("external_id") or ""), str(a.get("id") or ""),
                                 str(a.get("label") or "")):
            continue
        out.append(a)
    return out


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
    async with httpx.AsyncClient(timeout=25) as c:
        for a in accs:
            cr = messenger_bot.split_credentials(channel_accounts.get_token(a["id"]))
            meta = a.get("meta") or {}
            app_id = meta.get("app_id", "")
            if not app_id:
                info = await messenger_setup.debug_token(c, cr["access_token"])
                app_id = info.get("app_id", "") if info.get("ok") else ""
            url = meta.get("webhook_url", "")
            errs = []
            if repair:
                if not app_id or not verify:
                    errs.append("App id or verify token unknown; reconnect the Page from the Connections page.")
                else:
                    errs = (await messenger_setup.repair(c, cr["page_id"], cr["access_token"], app_id,
                                                         cr["app_secret"], url, verify)).get("errors", [])
            running = (cr["page_id"] in messenger_bot.registered()
                       or any(b.get("enabled") for b in chatbot_store.bots_using_account(a["id"])))
            chk = await messenger_setup.run_checks(c, cr["page_id"], cr["access_token"], cr["app_secret"],
                                                   app_id, url, running)
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
                     "trực. Dùng khi bot Messenger không trả lời khách. Trả từng dòng ok/FAIL/warn kèm cách sửa."),
        handler=_check, min_mode="readonly", schema=_SCHEMA,
    )
    ctx.register_tool(
        name="messenger_repair",
        description=("Sửa tự động kết nối Messenger: khai lại webhook của app Meta (messages, messaging_postbacks) và gắn "
                     "lại Trang vào app, rồi kiểm tra lại. Đổi cài đặt trên Meta. Chỉ gọi khi messenger_check báo dòng "
                     "webhook hoặc Trang gắn app bị FAIL."),
        handler=_repair, min_mode="full", schema=_SCHEMA,
    )
