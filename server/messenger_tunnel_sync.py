"""Point Meta's webhook callback at the new quick-tunnel link after cloudflared restarts (2026-11-17).

A quick tunnel (https://<words>.trycloudflare.com) gets a new address on every restart, and remote_tunnel.py now
restarts it by itself when it loses its connection (after the Mac sleeps, for instance). Every Messenger account whose
saved `meta.webhook_url` sits on an old trycloudflare host would then stay registered at Meta on a dead address, and
customers' messages would vanish until the owner re-ran the wizard. remote_tunnel calls `on_quick_url` with each new
link; this module re-registers the app's `page` webhook (and the `instagram` one when the account has Instagram) on
the same path under the new host, then saves the new address on the account.

Only callbacks on *.trycloudflare.com are touched: a named tunnel or the owner's own domain keeps its address, and an
account registered there is not ours to move. Never logs a token or an app secret.
"""
from __future__ import annotations

import asyncio
import sys
import threading
import time
from urllib.parse import urlsplit, urlunsplit

QUICK_SUFFIX = ".trycloudflare.com"
# Seconds to wait before each attempt. Meta calls the new callback while the request is open, and a fresh quick
# hostname can take a little while to resolve everywhere, so the first try waits and later ones back off.
RETRY_DELAYS = (15, 45, 120, 300)

_lock = threading.Lock()


def _quick_host(url: str) -> str:
    try:
        u = urlsplit(str(url or ""))
    except ValueError:
        return ""
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not host.endswith(QUICK_SUFFIX) or u.username or u.password:
        return ""
    return host


def moved_url(stored: str, new_base: str) -> str:
    """`stored` with its host swapped for the one in `new_base`, keeping path and query. "" when it should stay."""
    old_host, new_host = _quick_host(stored), _quick_host(new_base)
    if not old_host or not new_host or old_host == new_host:
        return ""
    old = urlsplit(stored)
    return urlunsplit(("https", new_host, old.path or "/messenger/webhook", old.query, ""))


def plan(accounts, new_base: str) -> list:
    """[(account, new callback)] for the Messenger accounts still registered on an old quick link."""
    out = []
    for a in accounts or []:
        if a.get("channel", "messenger") != "messenger":
            continue
        url = moved_url(str((a.get("meta") or {}).get("webhook_url") or ""), new_base)
        if url:
            out.append((a, url))
    return out


async def sync(new_base: str, verify_token: str, client=None) -> dict:
    """Re-register Meta webhooks for every account `plan` picks. {"updated": [account ids], "errors": [text]}."""
    import channel_accounts
    import messenger_bot
    import messenger_setup
    todo = plan(channel_accounts.list_accounts(channel="messenger"), new_base)
    res = {"updated": [], "errors": []}
    if not todo:
        return res
    if not verify_token:
        res["errors"].append("no Messenger verify token saved")
        return res
    own = client is None
    if own:
        import httpx
        client = httpx.AsyncClient(timeout=25)
    done = {}  # (app_id, url, object) -> result; several Pages often share one Meta app
    try:
        for a, url in todo:
            aid = a.get("id", "")
            meta = a.get("meta") or {}
            cr = messenger_bot.split_credentials(channel_accounts.get_token(aid))
            app_id = str(meta.get("app_id") or "")
            if not app_id and cr.get("access_token"):
                info = await messenger_setup.debug_token(client, cr["access_token"])
                app_id = str(info.get("app_id") or "") if info.get("ok") else ""
            if not app_id or not cr.get("app_secret"):
                res["errors"].append(f"{a.get('label') or aid}: app id or app secret unknown")
                continue
            key = (app_id, url, "page")
            if key not in done:
                done[key] = await messenger_setup.set_app_webhook(client, app_id, cr["app_secret"], url, verify_token)
            r = done[key]
            if r.get("ok") and meta.get("ig_id"):
                key = (app_id, url, "instagram")
                if key not in done:
                    done[key] = await messenger_setup.set_instagram_webhook(client, app_id, cr["app_secret"], url,
                                                                            verify_token)
                ig = done[key]
                if not ig.get("ok"):
                    res["errors"].append(f"{a.get('label') or aid}: instagram: {ig.get('error', '')}")
            if not r.get("ok"):
                res["errors"].append(f"{a.get('label') or aid}: {r.get('error', '')}")
                continue
            ok, err = channel_accounts.update_account(aid, {"meta": {"webhook_url": url}})
            if ok:
                res["updated"].append(aid)
            else:
                res["errors"].append(f"{a.get('label') or aid}: saved at Meta, not locally: {err}")
    finally:
        if own:
            await client.aclose()
    return res


def follow(new_base: str, verify_token_fn, current_url_fn=None, delays=RETRY_DELAYS, sleep=time.sleep) -> dict:
    """Blocking: try `sync` after each delay until nothing is left to move. Gives up early when the tunnel has moved
    on again (`current_url_fn()` no longer returns `new_base`): the newer link's own run takes over."""
    last = {"updated": [], "errors": []}
    with _lock:
        for d in delays:
            sleep(d)
            if current_url_fn is not None and current_url_fn() != new_base:
                return last
            try:
                last = asyncio.run(sync(new_base, verify_token_fn()))
            except Exception as e:
                last = {"updated": [], "errors": [f"{type(e).__name__}: {e}"]}
            if last["updated"]:
                print(f"[messenger tunnel] callback moved to {new_base} for {len(last['updated'])} account(s)",
                      file=sys.stderr)
            if not last["errors"]:
                return last
            print(f"[messenger tunnel] {'; '.join(last['errors'])[:500]}", file=sys.stderr)
    return last


def on_quick_url(verify_token_fn):
    """A remote_tunnel URL listener bound to main's `_ms_verify_token`."""
    def listener(url: str):
        import remote_tunnel
        follow(url, verify_token_fn, current_url_fn=lambda: remote_tunnel.MANAGER.url)
    return listener
