"""Messenger: Log in with Facebook and Page comments in the inbox (0.434.0).

    python tests/run.py messenger_comments

No network: Graph is faked. Guarded, in order of what would hurt most if it broke:

  1. Comments are threads like Pancake shows them: a top-level comment opens conversation
     `cmt:<comment id>`, a reply under it joins that same conversation, the Page's own comments
     (every reply Javis sends) are skipped, so the bot never answers itself.
  2. Sending to a comment conversation posts a reply under the top-level comment, never a
     Messenger message, and shows no typing indicator.
  3. Modes: "reply" runs a bot turn told the comment is public, "inbox" only records it,
     "off" drops it. The inbox-only answer function records and stays silent.
  4. `feed` is optional: when Meta refuses it the Page is still subscribed for messages.
  5. Log in with Facebook: bad input refused before any call, a wrong app secret refused, the
     login address carries the redirect, state and scopes, the callback turns the code into the
     Page list, and nothing the dashboard reads ever carries a token.
  6. Routes: the callback and the privacy page are public, finish saves each ticked Page with its
     comment mode, the comment mode can be changed afterwards.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
from urllib.parse import parse_qs, urlparse

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-messenger-cmt-")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx  # noqa: E402

import messenger_bot  # noqa: E402
import messenger_oauth  # noqa: E402

_fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  [{detail}]"))
    if not ok:
        _fails.append(name)


def run(coro):
    return asyncio.run(coro)


PAGE = "1234567890123"
SECRET = "c" * 32
TOKEN = "EAA" + "t" * 60
POST = f"{PAGE}_555"
TOP = "555_100"
REPLY = "555_101"


def change(cid, parent, msg="Giá bao nhiêu shop?", who="777", verb="add", item="comment"):
    return {"field": "feed", "value": {"item": item, "verb": verb, "comment_id": cid, "post_id": POST,
                                       "parent_id": parent, "message": msg,
                                       "from": {"id": who, "name": "Chị Lan"}}}


# ============================================================
# 1. Comment threads
# ============================================================
top = messenger_bot.comment_event(change(TOP, POST)["value"], PAGE)
rep = messenger_bot.comment_event(change(REPLY, TOP)["value"], PAGE)
check("a top-level comment is its own thread", top and top["root_id"] == TOP, top)
check("a reply under it joins that thread", rep and rep["root_id"] == TOP, rep)
check("the Page's own comment (a reply Javis sent) is skipped",
      messenger_bot.comment_event(change("555_102", TOP, who=PAGE)["value"], PAGE) is None)
check("an edited comment is skipped", messenger_bot.comment_event(change(TOP, POST, verb="edited")["value"], PAGE) is None)
check("a reaction or a post is skipped",
      messenger_bot.comment_event(change(TOP, POST, item="reaction")["value"], PAGE) is None)
check("conversation id prefix", messenger_bot.is_comment_chat("cmt:1") and not messenger_bot.is_comment_chat("555"))


async def _routing():
    got = []

    class B:
        async def _safe_comment(self, com):
            got.append(com)

        async def _safe_event(self, ev):
            got.append(("msg", ev))
    messenger_bot._REGISTRY.clear()
    messenger_bot._REGISTRY[PAGE] = B()
    n = await messenger_bot.handle_webhook({"object": "page", "entry": [
        {"id": PAGE, "changes": [change(TOP, POST), change("x", POST, verb="remove"), {"field": "ratings", "value": {}}]},
        {"id": "999", "changes": [change(TOP, POST)]}]})
    await asyncio.sleep(0)
    messenger_bot._REGISTRY.clear()
    return n, got

n, got = run(_routing())
check("feed changes reach the Page's bot, other changes and Pages do not",
      n == 1 and len(got) == 1 and got[0]["comment_id"] == TOP, (n, got))


# ============================================================
# 2-3. Bot turn on a comment, by mode
# ============================================================
async def _comment_turn(mode, com):
    calls, seen = [], {}

    async def answer(text, meta, progress):
        seen.update(text=text, meta=dict(meta or {}))
        return {"text": "**Dạ** 150k ạ, chị nhắn Page để em tư vấn thêm nhé."}

    bot = messenger_bot.MessengerBot({"page_id": PAGE, "access_token": TOKEN, "app_secret": SECRET}, "",
                                     answer, giau_trang_thai=True)

    async def fake_post(client, path, payload):
        calls.append((path, payload))
        return {"ok": True, "id": "555_900"}

    async def fake_post_text(client, post_id):
        return "Áo thun cotton mùa hè, giảm 20% hôm nay"
    bot._post_json = fake_post
    bot._post_text = fake_post_text
    orig = messenger_bot.comment_mode
    messenger_bot.comment_mode = lambda aid: mode
    try:
        await bot._on_comment(com)
        await bot._on_comment(com)      # Meta retry
        for task in list(bot._current.values()):
            await task
        await asyncio.sleep(0)
    finally:
        messenger_bot.comment_mode = orig
        if bot._client:
            await bot._client.aclose()
    return calls, seen

calls, seen = run(_comment_turn("reply", rep))
m = seen.get("meta") or {}
check("reply mode: the bot gets the comment text in the thread's conversation",
      seen.get("text") == "Giá bao nhiêu shop?" and m.get("chat_id") == "cmt:" + TOP and m.get("comment")
      and m.get("user_name") == "Chị Lan" and m.get("message_id") == REPLY, seen)
check("reply mode: the model is told the reply is public, the inbox title names the post",
      "CÔNG KHAI" in m.get("ghi_chu_dau", "") and "Áo thun" in m.get("chat_title", ""), m)
check("reply mode: the answer goes under the top-level comment as plain text, once",
      calls == [(f"{TOP}/comments", {"message": "Dạ 150k ạ, chị nhắn Page để em tư vấn thêm nhé."})], calls)
check("reply mode: no seen marker or typing on a comment", not any(c[1].get("sender_action") for c in calls), calls)

calls, seen = run(_comment_turn("inbox", top))
check("inbox mode: recorded through the answer function as log-only, nothing sent",
      (seen.get("meta") or {}).get("log_only") and not calls, (seen, calls))
calls, seen = run(_comment_turn("off", top))
check("off mode: nothing recorded, nothing sent", not seen and not calls, (seen, calls))


async def _send_text():
    sent = []

    def graph(req):
        sent.append((req.method, req.url.path, json.loads(req.content or b"{}")))
        return httpx.Response(200, json={"id": "555_901"})
    bot = messenger_bot.MessengerBot({"page_id": PAGE, "access_token": TOKEN, "app_secret": SECRET}, "", None)
    orig = httpx.AsyncClient

    class C(orig):
        def __init__(self, *a, **kw):
            kw["transport"] = httpx.MockTransport(graph)
            super().__init__(*a, **kw)
    httpx.AsyncClient = C
    try:
        ok = await bot.send_text("cmt:" + TOP, "Dạ em gửi chị bảng giá ạ")
    finally:
        httpx.AsyncClient = orig
    return ok, sent

ok, sent = run(_send_text())
check("a reply typed in the inbox goes under the comment",
      ok == (True, "") and sent and sent[0][1].endswith(f"/{TOP}/comments")
      and sent[0][2] == {"message": "Dạ em gửi chị bảng giá ạ"}, (ok, sent))


async def _photo_refused():
    bot = messenger_bot.MessengerBot({"page_id": PAGE, "access_token": TOKEN, "app_secret": SECRET}, "", None)
    p = os.path.join(os.environ["JAVIS_STATE_DIR"], "bang-gia.pdf")
    with open(p, "wb") as f:
        f.write(b"%PDF-1.4")
    return await bot.send_file(p, "", chat="cmt:" + TOP)

ok, err = run(_photo_refused())
check("a non-image file is refused for a comment with a reason", not ok and err, (ok, err))


# ============================================================
# 4. `feed` is optional when subscribing
# ============================================================
async def _subscribe(refuse_feed):
    asked = []

    def graph(req):
        f = dict(req.url.params).get("subscribed_fields", "")
        asked.append(f)
        if refuse_feed and "feed" in f:
            return httpx.Response(200, json={"error": {"code": 200, "message": "needs pages_read_user_content"}})
        return httpx.Response(200, json={"success": True})
    async with httpx.AsyncClient(transport=httpx.MockTransport(graph)) as c:
        return await messenger_bot.subscribe_page(c, PAGE, TOKEN), asked

r, asked = run(_subscribe(False))
check("subscribe asks for messages, postbacks and feed", r == {"ok": True, "feed": True}
      and asked == ["messages,messaging_postbacks,feed"], (r, asked))
r, asked = run(_subscribe(True))
check("feed refused: the Page is still subscribed for messages",
      r.get("ok") and r.get("feed") is False and asked[-1] == "messages,messaging_postbacks", (r, asked))

import messenger_setup  # noqa: E402
item = messenger_setup.comments_item(["pages_messaging"], ["messages"])
check("comments row is a warning naming what is missing, never red",
      item["ok"] is None and "pages_manage_engagement" in item["detail"] and "feed" in item["detail"], item)
item = messenger_setup.comments_item(list(messenger_setup.COMMENT_SCOPES), ["messages", "feed"])
check("comments row green when permissions and feed are there", item["ok"] is True, item)
# 0.438.0: one login also posts (Facebook Pages tools reuse the Messenger connection).
check("login asks for the posting permission", "pages_manage_posts" in messenger_oauth.SCOPES)
check("posting row: warning when pages_manage_posts is missing, green when present",
      messenger_setup.posts_item(["pages_messaging"])["ok"] is None
      and messenger_setup.posts_item(["pages_manage_posts"])["ok"] is True)


# ============================================================
# 5. Log in with Facebook
# ============================================================
APP = "987654321098765"
APP_SECRET = "d" * 32
REDIRECT = "https://javis.example.com/messenger/oauth/callback"
USER_SHORT = "EAAshort" + "s" * 50
USER_LONG = "EAAlong" + "l" * 50


def fb(req):
    p = req.url.path.split("/", 2)[-1]
    q = dict(req.url.params)
    if p == APP:
        if q.get("access_token") == f"{APP}|{APP_SECRET}":
            return httpx.Response(200, json={"id": APP, "name": "Shop App"})
        return httpx.Response(400, json={"error": {"code": 190, "message": "Invalid OAuth access token"}})
    if p == "oauth/access_token":
        if q.get("code") == "good" and q.get("redirect_uri") == REDIRECT and q.get("client_secret") == APP_SECRET:
            return httpx.Response(200, json={"access_token": USER_SHORT})
        if q.get("fb_exchange_token") == USER_SHORT:
            return httpx.Response(200, json={"access_token": USER_LONG})
        return httpx.Response(400, json={"error": {"code": 100, "message": "Invalid verification code"}})
    if p == "me/accounts":
        if q.get("access_token") != USER_LONG or not q.get("appsecret_proof"):
            return httpx.Response(400, json={"error": {"code": 190, "message": "bad"}})
        return httpx.Response(200, json={"data": [
            {"id": PAGE, "name": "Shop Áo", "access_token": "EAApage" + "p" * 50,
             "picture": {"data": {"url": "https://x/p.jpg"}}},
            {"id": "222333444555", "name": "Shop Giày", "access_token": "EAApage2" + "q" * 50}]})
    return httpx.Response(404, json={"error": {"message": "unexpected " + p}})


async def with_fb(fn):
    async with httpx.AsyncClient(transport=httpx.MockTransport(fb)) as c:
        return await fn(c)

r = run(with_fb(lambda c: messenger_oauth.start("abc", APP_SECRET, REDIRECT, client=c)))
check("start refuses a non-numeric App ID", not r["ok"] and r["error"], r)
r = run(with_fb(lambda c: messenger_oauth.start(APP, "short", REDIRECT, client=c)))
check("start refuses a short App secret", not r["ok"], r)
r = run(with_fb(lambda c: messenger_oauth.start(APP, APP_SECRET, "http://1.2.3.4:8000/messenger/oauth/callback", client=c)))
check("start refuses plain HTTP (Meta wants an HTTPS redirect)", not r["ok"] and "HTTPS" in r["error"], r)
r = run(with_fb(lambda c: messenger_oauth.start(APP, "e" * 32, REDIRECT, client=c)))
check("start refuses an App secret that is not this app's", not r["ok"] and "App secret" in r["error"], r)
r = run(with_fb(lambda c: messenger_oauth.start(APP, APP_SECRET, REDIRECT, brain="shop", client=c)))
q = parse_qs(urlparse(r.get("url", "")).query)
check("start returns the Facebook login address with redirect, state and scopes",
      r["ok"] and urlparse(r["url"]).netloc == "www.facebook.com" and q.get("client_id") == [APP]
      and q.get("redirect_uri") == [REDIRECT] and q.get("state") == [r["state"]]
      and "pages_messaging" in q["scope"][0] and "pages_manage_engagement" in q["scope"][0], r)
state = r["state"]
check("before the callback the login is pending", messenger_oauth.result(state)["status"] == "pending")

r = run(with_fb(lambda c: messenger_oauth.callback(state, "bad", client=c)))
check("a bad code reads as an error, also through result()",
      not r["ok"] and messenger_oauth.result(state)["status"] == "error", r)

r = run(with_fb(lambda c: messenger_oauth.start(APP, APP_SECRET, REDIRECT, client=c)))
state = r["state"]
r = run(with_fb(lambda c: messenger_oauth.callback(state, "good", client=c)))
res = messenger_oauth.result(state)
check("the callback lists the Pages the person manages",
      r["ok"] and res["status"] == "ready" and [p["id"] for p in res["pages"]] == [PAGE, "222333444555"]
      and res["pages"][0]["picture"] == "https://x/p.jpg", res)
blob = json.dumps(res) + json.dumps(r)
check("no token or secret in anything the dashboard reads",
      all(t not in blob for t in (USER_SHORT, USER_LONG, APP_SECRET, "EAApage")), blob[:200])
check("take() hands the long-lived user token to the server side only",
      messenger_oauth.take(state).get("user_token") == USER_LONG)

r = run(with_fb(lambda c: messenger_oauth.start(APP, APP_SECRET, REDIRECT, client=c)))
r2 = run(messenger_oauth.callback(r["state"], "", "access_denied", "Permissions error"))
check("cancelling on Facebook says so", not r2["ok"] and messenger_oauth.result(r["state"])["status"] == "error", r2)
check("an unknown state reads as expired", messenger_oauth.result("nope")["status"] == "expired")
check("take() refuses a login that is not ready", messenger_oauth.take(r["state"]) == {})
messenger_oauth._purge(now=10 ** 12)
check("logins expire", messenger_oauth.result(state)["status"] == "expired")

html = messenger_oauth.privacy_html("Shop OS", ["Shop <Áo>"])
check("privacy page: both languages, deletion instructions, names escaped",
      "Chính sách quyền riêng tư" in html and "Privacy policy" in html and "delete my data" in html
      and "Shop &lt;Áo&gt;" in html and "<Áo>" not in html)


# ============================================================
# 3b. The chatbot answer function: log-only records and stays silent
# ============================================================
import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402

recorded = []
orig = (chatbot_store.get_bot, chatbot_store.ap_ngoai_le, chatbot_runtime.ghi_tin_khach)
chatbot_store.get_bot = lambda bid: {"id": bid, "name": "Bot", "brain": "x"}
chatbot_store.ap_ngoai_le = lambda cfg, meta: cfg
chatbot_runtime.ghi_tin_khach = lambda cfg, meta, text: recorded.append((meta.get("chat_id"), text))
try:
    out = run(chatbot_runtime._make_answer_fn("b1")("Còn size M không?", {"chat_id": "cmt:1", "log_only": True}, None))
finally:
    chatbot_store.get_bot, chatbot_store.ap_ngoai_le, chatbot_runtime.ghi_tin_khach = orig
check("log-only turn records the comment and stays silent",
      out.get("im_lang") and recorded == [("cmt:1", "Còn size M không?")], (out, recorded))

meta = chatbot_runtime.manual_meta({"channel": "messenger", "channel_account_id": "messenger:acc1",
                                    "external_chat_id": "cmt:" + TOP, "chat_type": "private"},
                                   {"sender_id": "777", "sender_name": "Chị Lan", "external_message_id": REPLY})
check("asking the bot from the inbox on a comment tells the model it is public",
      "CÔNG KHAI" in meta.get("ghi_chu_dau", ""), meta)


# ============================================================
# 6. Routes
# ============================================================
import channel_accounts  # noqa: E402
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# Behind the owner's HTTPS proxy, as on a VPS: the request arrives on localhost with forwarded headers.
client = TestClient(main.app, base_url="http://localhost",
                    headers={"x-forwarded-proto": "https", "x-forwarded-host": "javis.example.com"})
check("callback and privacy page are public paths",
      "/messenger/oauth/callback" in main._AUTH_PUBLIC_EXACT and "/messenger/privacy" in main._AUTH_PUBLIC_EXACT)
r = client.get("/messenger/privacy")
check("privacy page served as HTML", r.status_code == 200 and "Privacy policy" in r.text, r.status_code)
r = client.get("/messenger/setup")
d = r.json()
check("setup gives the redirect address and the privacy address to paste into Meta",
      d.get("oauth_redirect") == "https://javis.example.com/messenger/oauth/callback"
      and d.get("privacy_url") == "https://javis.example.com/messenger/privacy", d)
r = client.get("/messenger/oauth/callback", params={"state": "nope", "code": "x"})
check("callback with an unknown state shows an error page, not a crash",
      r.status_code == 200 and "⚠" in r.text, r.status_code)

# A ready login, then finish with a faked connect.
messenger_oauth._pending["st-ready"] = {
    "created": __import__("time").time(), "status": "ready", "app_id": APP, "app_secret": APP_SECRET,
    "redirect_uri": REDIRECT, "brain": "", "label": "", "user_token": USER_LONG, "error": "",
    "pages": [{"id": PAGE, "name": "Shop Áo", "picture": ""}, {"id": "222333444555", "name": "Shop Giày", "picture": ""}]}
seen_connect = []


async def fake_connect(page_id, app_id, app_secret, token, webhook_url, verify_token, client=None):
    seen_connect.append((page_id, token, webhook_url))
    if page_id == "222333444555":
        return {"ok": False, "error": "lỗi 210", "step": "token"}
    return {"ok": True, "page_token": "EAApagetok" + "z" * 50, "page_name": "Shop Áo",
            "check": {"ok": True, "items": []}, "repair_errors": []}

orig_connect = main.messenger_setup.connect
main.messenger_setup.connect = fake_connect
try:
    r = client.post("/messenger/oauth/finish", json={"state": "st-ready", "page_ids": [PAGE, "222333444555", "666"],
                                                    "comments": "reply"})
finally:
    main.messenger_setup.connect = orig_connect
d = r.json()
res = {x["page_id"]: x for x in d.get("results", [])}
check("finish connects only Pages from the login, with the long-lived user token",
      [c[0] for c in seen_connect] == [PAGE, "222333444555"] and seen_connect[0][1] == USER_LONG
      and seen_connect[0][2] == "https://javis.example.com/messenger/webhook", seen_connect)
check("finish reports each Page on its own", d.get("ok") and res[PAGE]["ok"] and not res["222333444555"]["ok"]
      and res["222333444555"]["error"] == "lỗi 210", d)
acc = channel_accounts.owner_of(PAGE, "messenger") or {}
check("the Page is saved with its comment mode", (acc.get("meta") or {}).get("comments") == "reply"
      and res[PAGE]["account"]["comments"] == "reply", acc.get("meta"))
check("no token in the finish response", "EAApagetok" not in json.dumps(d) and USER_LONG not in json.dumps(d))
check("the login is kept while a Page failed, so it can be retried", messenger_oauth.take("st-ready") != {})

r = client.post("/messenger/comments", json={"account_id": acc.get("id"), "mode": "off"})
check("comment mode can be changed afterwards", r.status_code == 200 and r.json()["account"]["comments"] == "off"
      and messenger_bot.comment_mode(acc.get("id")) == "off", r.text)
r = client.post("/messenger/comments", json={"account_id": acc.get("id"), "mode": "loud"})
check("an unknown comment mode is refused", r.status_code == 400, r.status_code)
r = client.post("/messenger/oauth/finish", json={"state": "gone", "page_ids": [PAGE]})
check("finish on an expired login is refused", r.status_code == 400, r.status_code)

print()
if _fails:
    print(f"{len(_fails)} FAILED")
    sys.exit(1)
print("all ok")
