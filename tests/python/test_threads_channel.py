"""Threads channel (0.448.0): replies under the owner's posts by webhook, answered by the bot.

    python tests/run.py threads_channel      (no network: Threads is faked)

Guarded, in order of what would hurt most if it broke:

  1. Nothing is polled: replies arrive only through the signed webhook. A bad signature is refused before parsing;
     the verify handshake echoes the challenge only with the right token.
  2. The bot never answers itself: its own replies coming back on the webhook are skipped, and a Meta retry of the
     same reply runs once.
  3. Threads: a top-level reply opens its own conversation; a reply under a reply joins its parent's. The answer is
     published as a reply to that conversation id (create container with reply_to_id, then publish), split at 500.
  4. Modes per account: "reply" runs a turn told the answer is public, "inbox" only records, "off" drops.
  5. Login: Threads' own app id and secret, threads.net authorize address with the right scopes, the code turned into
     a 60-day token and the account, the account saved without any token reaching the dashboard.
  6. The token refreshes itself once it is old enough, and the new one is stored.
  7. The channel is in the registry with the Meta card as its way in; Delete hides a reply (only authors delete).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
from urllib.parse import parse_qs, urlparse

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-threads-")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx  # noqa: E402

import channel_accounts  # noqa: E402
import channels  # noqa: E402
import threads_bot  # noqa: E402
import threads_oauth  # noqa: E402

_fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  [{detail}]"))
    if not ok:
        _fails.append(name)


def run(coro):
    return asyncio.run(coro)


UID = "26000000000001"
SECRET = "d" * 32
TOKEN = "THAA" + "t" * 60
POST = "1790000000000000"


def reply_value(rid, parent=POST, user="lan.nguyen", text="Giá bao nhiêu ạ?"):
    return {"id": rid, "username": user, "text": text, "media_type": "TEXT_POST",
            "replied_to": {"id": parent}, "root_post": {"id": POST, "owner_id": UID, "username": "shop"}}


def notif(value):
    return {"app_id": "1", "topic": "moderate", "target_id": UID, "time": int(time.time()),
            "values": {"field": "replies", "value": value}}


# ============================================================
# 3. Threads ids and own replies
# ============================================================
top = threads_bot.reply_event(reply_value("r1"), "shop", UID)
sub = threads_bot.reply_event(reply_value("r2", parent="r1"), "shop", UID)
check("a top-level reply opens its own conversation", top and top["thread_id"] == "r1", top)
check("a reply under a reply joins its parent's conversation", sub and sub["thread_id"] == "r1", sub)
check("the account's own reply is skipped (it comes back on the webhook)",
      threads_bot.reply_event(reply_value("r3", user="Shop"), "shop", UID) is None)
check("credentials split by shape", threads_bot.split_credentials(f"{UID} {TOKEN} {SECRET}") ==
      {"user_id": UID, "access_token": TOKEN, "app_secret": SECRET})
check("long answers split at the 500-character limit",
      all(len(c) <= 500 for c in threads_bot._chunks("chữ " * 400)) and len(threads_bot._chunks("chữ " * 400)) > 1)
check("both webhook envelopes are read",
      threads_bot._notifications(notif(reply_value("r1")))[0][:2] == (UID, "replies")
      and threads_bot._notifications({"entry": [{"id": UID, "changes": [{"field": "replies", "value": {}}]}]})[0][:2]
      == (UID, "replies"))


async def _routing():
    got = []

    class B:
        async def _safe_reply(self, value):
            got.append(value)
    threads_bot._REGISTRY.clear()
    threads_bot._REGISTRY[UID] = B()
    n = await threads_bot.handle_webhook(notif(reply_value("r1")))
    n2 = await threads_bot.handle_webhook({"values": {"field": "mentions", "value": {}}, "target_id": UID})
    n3 = await threads_bot.handle_webhook({"values": {"field": "replies", "value": reply_value("x")}, "target_id": "999"})
    await asyncio.sleep(0)
    threads_bot._REGISTRY.clear()
    return n, n2, got, n3

n, n2, got, n3 = run(_routing())
check("a replies notification reaches the account's bot; other fields do not",
      n == 1 and n2 == 0 and got[0]["id"] == "r1", (n, n2, got))
check("an unknown account still finds its bot through the root post's owner", n3 == 1, n3)


# ============================================================
# 2-4. Turns
# ============================================================
aid, err = channel_accounts.create_account({"channel": "threads", "token": f"{UID} {TOKEN} {SECRET}",
                                            "external_id": UID, "label": "@shop",
                                            "meta": {"username": "shop", "comments": "reply", "token_at": time.time()}})
check("a Threads account", bool(aid), err)


async def _turn(mode):
    calls, seen = [], {}

    async def answer(text, meta, progress):
        seen.update(text=text, meta=dict(meta or {}))
        return {"text": "**Dạ** 150k ạ"}

    bot = threads_bot.ThreadsBot(f"{UID} {TOKEN} {SECRET}", "", answer, giau_trang_thai=True)
    bot.account_id = aid
    bot.bot_username = "shop"

    async def fake_post(client, path, params):
        calls.append((path, dict(params)))
        return {"ok": True, "id": "c1" if path.endswith("/threads") else "p1"}

    async def fake_post_text(client, post_id):
        return "Áo len mới về"
    bot._post = fake_post
    bot._post_text = fake_post_text
    channel_accounts.update_account(aid, {"meta": {"username": "shop", "comments": mode, "token_at": time.time()}})
    try:
        await bot._on_reply(reply_value("r2", parent="r1"))
        await bot._on_reply(reply_value("r2", parent="r1"))       # Meta retry
        for task in list(bot._current.values()):
            await task
        await asyncio.sleep(0)
    finally:
        if bot._client:
            await bot._client.aclose()
    return calls, seen

calls, seen = run(_turn("reply"))
m = seen.get("meta") or {}
check("reply mode: one turn in the thread's conversation, told it is public, titled by the post",
      seen.get("text") == "Giá bao nhiêu ạ?" and m.get("chat_id") == "r1" and "CÔNG KHAI" in m.get("ghi_chu_dau", "")
      and "Áo len" in m.get("chat_title", "") and m.get("user_name") == "@lan.nguyen", seen)
check("the answer is published as a reply to the conversation, plain text, once",
      calls == [(f"{UID}/threads", {"media_type": "TEXT", "text": "Dạ 150k ạ", "reply_to_id": "r1"}),
                (f"{UID}/threads_publish", {"creation_id": "c1"})], calls)
calls, seen = run(_turn("inbox"))
check("inbox mode: recorded as log-only, nothing published", (seen.get("meta") or {}).get("log_only") and not calls, (seen, calls))
calls, seen = run(_turn("off"))
check("off mode: nothing recorded, nothing published", not seen and not calls, (seen, calls))


async def _file():
    bot = threads_bot.ThreadsBot(f"{UID} {TOKEN} {SECRET}", "", None)
    return await bot.send_file("/x.png", "", chat="r1")

ok, e = run(_file())
check("a file is refused in words (Threads replies are text here)", not ok and e, (ok, e))


# ============================================================
# 6. Token refresh
# ============================================================
async def _refresh(age):
    seen = []

    def graph(req):
        seen.append(str(req.url))
        return httpx.Response(200, json={"access_token": "THAA" + "n" * 60, "expires_in": 5184000})
    channel_accounts.update_account(aid, {"token": f"{UID} {TOKEN} {SECRET}",
                                          "meta": {"username": "shop", "token_at": time.time() - age}})
    bot = threads_bot.ThreadsBot(f"{UID} {TOKEN} {SECRET}", "", None)
    bot.account_id = aid
    async with httpx.AsyncClient(transport=httpx.MockTransport(graph)) as c:
        await bot._maybe_refresh(c)
    return seen, bot.token

seen, tok = run(_refresh(3600))
check("a fresh token is not refreshed", not seen and tok == TOKEN, seen)
seen, tok = run(_refresh(25 * 86400))
stored = threads_bot.split_credentials(channel_accounts.get_token(aid))
check("an old token is refreshed with th_refresh_token and the new one stored",
      seen and "th_refresh_token" in seen[0] and tok.startswith("THAAn") and stored["access_token"] == tok
      and stored["app_secret"] == SECRET, (seen, stored))

# ============================================================
# 5. Login
# ============================================================
u = urlparse(threads_oauth.login_url("1234", "https://x/threads/oauth/callback", "S"))
q = parse_qs(u.query)
check("the login opens threads.net with the Threads app id, redirect, state and scopes",
      u.netloc == "threads.net" and q["client_id"] == ["1234"] and q["state"] == ["S"]
      and set(q["scope"][0].split(",")) >= {"threads_basic", "threads_read_replies", "threads_manage_replies"}, q)
check("bad input refused before anything", not threads_oauth.start("abc", SECRET, "https://x/cb").get("ok")
      and not threads_oauth.start("1234", "short", "https://x/cb").get("ok")
      and not threads_oauth.start("1234", SECRET, "http://x/cb").get("ok"))
st = threads_oauth.start("1234", SECRET, "https://x/threads/oauth/callback", "", "reply")
check("a good start opens a pending login", st.get("ok") and threads_oauth.result(st["state"])["status"] == "pending", st)


async def _callback():
    def graph(req):
        p = req.url.path
        if p.endswith("/oauth/access_token"):
            return httpx.Response(200, json={"access_token": "THAAshort" + "s" * 40, "user_id": UID})
        if p.endswith("/access_token"):
            return httpx.Response(200, json={"access_token": "THAAlong" + "l" * 40, "expires_in": 5184000})
        if p.endswith("/me"):
            return httpx.Response(200, json={"id": UID, "username": "shop", "name": "Shop"})
        return httpx.Response(404, json={})
    async with httpx.AsyncClient(transport=httpx.MockTransport(graph)) as c:
        return await threads_oauth.callback(st["state"], "CODE#_", client=c)

res = run(_callback())
r = threads_oauth.result(st["state"])
check("the code becomes a 60-day token and the account; the dashboard never sees the token",
      res.get("ok") and r["status"] == "ready" and r["account"]["username"] == "shop" and "token" not in json.dumps(r)
      and threads_oauth.take(st["state"]).get("token", "").startswith("THAAlong"), (res, r))

# ============================================================
# 1, 7. Routes and registry
# ============================================================
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

cl = TestClient(main.app)
p = threads_oauth.take(st["state"])
saved, loi = main._th_save(p)
a = channel_accounts.get_account(saved) or {}
check("saving the login updates the account: new token, username, comment mode kept",
      saved == aid and threads_bot.split_credentials(channel_accounts.get_token(aid))["access_token"].startswith("THAAlong")
      and a["meta"].get("username") == "shop", (saved, loi, a.get("meta")))
setup = cl.get("/threads/setup").json()
check("setup lists the addresses to paste and the account, never a token",
      setup.get("ok") and setup["webhook_url"].endswith("/threads/webhook") and setup["redirect_url"].endswith(threads_oauth.CALLBACK_PATH)
      and setup["accounts"] and "THAA" not in json.dumps(setup), setup)
vt = setup["verify_token"]
check("verify handshake: echoes only with the right token",
      cl.get("/threads/webhook", params={"hub.mode": "subscribe", "hub.verify_token": vt, "hub.challenge": "42"}).text == "42"
      and cl.get("/threads/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "no", "hub.challenge": "42"}).status_code == 403)
body = json.dumps(notif(reply_value("r9"))).encode()
check("an unsigned webhook is refused", cl.post("/threads/webhook", content=body, headers={"x-hub-signature-256": "sha256=00"}).status_code == 401)
sig = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
r = cl.post("/threads/webhook", content=body, headers={"x-hub-signature-256": sig})
check("a signed webhook is accepted and marks that Threads called",
      r.status_code == 200 and (channel_accounts.get_account(aid)["meta"].get("last_webhook") or 0) > 0, r.text)
for path in ("/threads/webhook", "/threads/oauth/callback", "/threads/uninstall", "/threads/delete"):
    check(f"{path} is reachable without a session (Meta calls it)", path in main._AUTH_PUBLIC_EXACT)
s = channels.spec("threads")
check("Threads is a bot channel in the registry, text only, connected from the Meta card",
      s and s.kind == "bot" and s.logo == "threads" and s.nl("gui_chu") and not s.nl("gui_file")
      and getattr(channels.module("threads"), "CONNECT_CARD", False))

import conversation_actions as ca  # noqa: E402
check("Delete on a Threads reply hides it; profile links to threads.net",
      ca.capabilities({"channel": "threads", "external_chat_id": "r1"}) == ["delete_remote", "profile"])
pr = run(ca.profile({"channel": "threads", "external_chat_id": "r1", "customer_name": "@lan.nguyen"}))
check("Threads profile link", pr.get("url") == "https://www.threads.net/@lan.nguyen", pr)

print()
if _fails:
    print(f"ĐỎ: {len(_fails)}: " + "; ".join(_fails))
    sys.exit(1)
print("OK - test_threads_channel: all pass")
