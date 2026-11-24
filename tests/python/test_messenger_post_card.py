"""The post a comment thread sits under, shown as a card at the top of the thread (2026-11-24).

    python tests/run.py messenger_post_card

A user asked why Javis answered a Facebook comment without showing which post it was under, while Pancake shows the
post's picture, its first words and a link to it. No network: Graph is faked. Guarded:

  1. Reading the card: a Facebook post gives its words, link and picture; a post with no words of its own takes its
     attachment's title; Instagram takes the caption, the link and the thumbnail of a video. The post id comes from the
     webhook, else from the comment id `<post>_<comment>`; a post the token may not read still gets the comment's link.
  2. A new comment keeps its card on the conversation (both comment modes), and the model is still told the post.
  3. The inbox store merges `conversation_metadata` into the conversation and leaves the rest of it alone.
  4. Opening an older thread fills its card in the background once; a card older than Meta's image links is read
     again; a read that came back empty is not retried on every open.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-post-card-")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx  # noqa: E402

import conversations  # noqa: E402
import messenger_bot  # noqa: E402

_fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  [{detail}]"))
    if not ok:
        _fails.append(name)


def run(coro):
    return asyncio.run(coro)


PAGE = "1234567890123"
TOKEN = "EAA" + "t" * 60
POST = f"{PAGE}_555"
TOP = "555_100"


def make_bot(answer=None):
    return messenger_bot.MessengerBot({"page_id": PAGE, "access_token": TOKEN, "app_secret": ""}, "", answer,
                                      giau_trang_thai=True)


# ============================================================
# 1. Reading the card
# ============================================================
check("the post id comes from a Page comment id", messenger_bot.post_id_of_comment(TOP, PAGE) == POST)
check("an id of another shape gives no post id",
      messenger_bot.post_id_of_comment("abc", PAGE) == "" and messenger_bot.post_id_of_comment("1_2_3", PAGE) == ""
      and messenger_bot.post_id_of_comment(TOP, "") == "")

c = messenger_bot.post_card_of({"id": POST, "message": "Tour Đà Lạt\n\n3 ngày 2 đêm",
                                "permalink_url": "https://www.facebook.com/x/posts/555", "full_picture": "https://scontent/x.jpg"})
check("a Facebook post gives its words on one line, its link and its picture",
      c == {"id": POST, "url": "https://www.facebook.com/x/posts/555", "text": "Tour Đà Lạt 3 ngày 2 đêm",
            "image": "https://scontent/x.jpg"}, c)
c = messenger_bot.post_card_of({"id": POST, "attachments": {"data": [{"title": "Video giới thiệu tour"}]}})
check("a post with no words takes its attachment's title", c.get("text") == "Video giới thiệu tour", c)
c = messenger_bot.post_card_of({"id": "m1", "caption": "Áo len", "permalink": "https://www.instagram.com/p/x/",
                                "media_type": "VIDEO", "media_url": "https://v.mp4", "thumbnail_url": "https://t.jpg"}, True)
check("an Instagram video shows its thumbnail, never the video file",
      c == {"id": "m1", "url": "https://www.instagram.com/p/x/", "text": "Áo len", "image": "https://t.jpg"}, c)
check("long words are cut", len(messenger_bot.post_card_of({"message": "a" * 2000})["text"]) == messenger_bot.MAX_POST_TEXT)


async def _read_card(routes, chat, post_id="", permalink=""):
    seen = []

    def graph(req):
        seen.append((req.url.path, req.url.params.get("fields")))
        body = routes.get(req.url.path.rsplit("/", 1)[-1])
        if body is None:
            return httpx.Response(400, json={"error": {"code": 10, "message": "no permission"}})
        return httpx.Response(200, json=body)
    bot = make_bot()
    async with httpx.AsyncClient(transport=httpx.MockTransport(graph)) as client:
        card = await bot._post_card(client, chat, post_id, permalink)
        again = await bot._post_card(client, "cmt:555_777", post_id, permalink) if chat.startswith("cmt:") else None
    return card, again, seen


post_body = {"id": POST, "message": "Tour Đà Lạt", "permalink_url": "https://www.facebook.com/x/posts/555",
             "full_picture": "https://scontent/x.jpg"}
card, again, seen = run(_read_card({POST: post_body}, "cmt:" + TOP))
check("with no post id from the webhook, the post is found from the comment id",
      card.get("id") == POST and card.get("text") == "Tour Đà Lạt" and card.get("url", "").endswith("/555")
      and card.get("at"), card)
check("a second thread under the same post reads nothing again", len(seen) == 1 and again.get("text") == "Tour Đà Lạt", seen)

card, _, seen = run(_read_card({TOP: {"permalink_url": "https://www.facebook.com/x/posts/555?comment_id=100"}}, "cmt:" + TOP))
check("a post the token may not read still gets the comment's own link",
      card.get("url", "").endswith("comment_id=100") and not card.get("text"), (card, seen))

card, _, seen = run(_read_card({}, "cmt:" + TOP, "", "https://www.facebook.com/x/posts/555"))
check("the webhook's link is used when Graph gives nothing", card.get("url") == "https://www.facebook.com/x/posts/555", card)

card, _, seen = run(_read_card({}, "cmt:" + TOP))
check("nothing readable gives no card", card == {}, card)

ig_body = {"id": "c1", "media": {"id": "m1", "caption": "Áo len mới về", "permalink": "https://www.instagram.com/p/x/",
                                 "media_type": "IMAGE", "media_url": "https://i.jpg"}}
card, _, seen = run(_read_card({"c1": ig_body}, "igc:c1"))
check("an Instagram comment thread reads its media through the comment",
      card.get("text") == "Áo len mới về" and card.get("image") == "https://i.jpg"
      and len(seen) == 1 and seen[0][0].endswith("/c1") and seen[0][1] == messenger_bot.IG_MEDIA_FIELDS, (card, seen))


# ============================================================
# 2. A new comment keeps its card on the conversation
# ============================================================
async def _comment(mode):
    seen = {}

    async def answer(text, meta, progress):
        seen.update(meta=dict(meta or {}))
        return {"text": ""}
    bot = make_bot(answer)

    async def fake_card(client, chat, post_id="", permalink=""):
        seen["asked"] = (chat, post_id, permalink)
        return {"id": post_id, "url": permalink, "text": "Tour Đà Lạt 3 ngày 2 đêm", "at": 1.0}

    async def fake_post(client, path, payload):
        return {"ok": True, "id": "x"}
    bot._post_card = fake_card
    bot._post_json = fake_post
    orig = messenger_bot.comment_mode
    messenger_bot.comment_mode = lambda aid: mode
    try:
        await bot._on_comment({"comment_id": TOP, "root_id": TOP, "post_id": POST, "from_id": "9", "from_name": "Lan",
                               "message": "ib", "photo": "", "video": "", "permalink": "https://www.facebook.com/x/posts/555"})
        for task in list(bot._current.values()):
            await task
        await asyncio.sleep(0)
    finally:
        messenger_bot.comment_mode = orig
        if bot._client:
            await bot._client.aclose()
    return seen


for mode in ("inbox", "reply"):
    s = run(_comment(mode))
    m = s.get("meta") or {}
    check(f"{mode} mode: the card rides on the turn for the conversation, from the webhook's post id and link",
          (m.get("conversation_metadata") or {}).get("post", {}).get("text") == "Tour Đà Lạt 3 ngày 2 đêm"
          and s.get("asked") == ("cmt:" + TOP, POST, "https://www.facebook.com/x/posts/555"), s)
    check(f"{mode} mode: the model is still told which post", "Tour Đà Lạt" in m.get("ghi_chu_dau", ""), m)


# ============================================================
# 3. The inbox store merges conversation metadata
# ============================================================
base = {"channel": "messenger", "account_id": "acc1", "external_chat_id": "cmt:" + TOP, "sender_type": "customer",
        "sender_id": "9", "sender_name": "Lan", "text": "ib"}
r = conversations.ghi_su_kien(dict(base, external_message_id="m1",
                                   conversation_metadata={"post": {"id": POST, "text": "Tour Đà Lạt", "at": 1.0}}))
cid = r.get("conversation_id")
conversations._set_meta_key(cid, "blocked", False)
conversations.ghi_su_kien(dict(base, external_message_id="m2", text="giá sao ạ"))
meta = (conversations.chi_tiet(cid) or {}).get("metadata") or {}
check("the card is kept on the conversation, and a later message without one leaves it",
      meta.get("post", {}).get("text") == "Tour Đà Lạt" and "blocked" in meta, meta)
conversations.ghi_su_kien(dict(base, external_message_id="m3",
                               conversation_metadata={"post": {"id": POST, "text": "Tour Đà Lạt mới", "at": 2.0}}))
meta = (conversations.chi_tiet(cid) or {}).get("metadata") or {}
check("a newer card replaces the old one, other keys stay", meta.get("post", {}).get("text") == "Tour Đà Lạt mới"
      and "blocked" in meta, meta)
check("set_post_card ignores an empty card", conversations.set_post_card(cid, {}) is False
      and (conversations.chi_tiet(cid) or {}).get("metadata", {}).get("post", {}).get("text") == "Tour Đà Lạt mới")


# ============================================================
# 4. Older threads get their card when opened
# ============================================================
import routes.conversations as rc  # noqa: E402

old = conversations.ghi_su_kien(dict(base, external_chat_id="cmt:555_200", external_message_id="o1"))["conversation_id"]
conv = conversations.chi_tiet(old)
check("an older comment thread with no card is due", rc._post_card_due(conv), conv.get("metadata"))
check("a Messenger chat, a fresh card, and a thread being read are not due",
      not rc._post_card_due(dict(conv, external_chat_id="123"))
      and not rc._post_card_due(dict(conv, metadata={"post": {"text": "x", "at": 1000.0}}), now=2000.0)
      and rc._post_card_due(dict(conv, metadata={"post": {"text": "x", "at": 1.0}}), now=1.0 + messenger_bot.POST_CARD_TTL))

calls = []


async def fake_card(self, chat, post_id="", permalink=""):
    calls.append(chat)
    return {"id": POST, "text": "Tour Đà Lạt", "url": "https://www.facebook.com/x/posts/555", "at": 5.0} if len(calls) == 1 else {}
orig_card = messenger_bot.MessengerBot.post_card
messenger_bot.MessengerBot.post_card = fake_card
try:
    run(rc._fill_post_card(conv))
    filled = (conversations.chi_tiet(old) or {}).get("metadata", {}).get("post") or {}
    check("opening it fills the card in the background", filled.get("text") == "Tour Đà Lạt" and calls == ["cmt:555_200"],
          (filled, calls))
    other = conversations.ghi_su_kien(dict(base, external_chat_id="cmt:555_300", external_message_id="p1"))["conversation_id"]
    oc = conversations.chi_tiet(other)
    run(rc._fill_post_card(oc))
    check("a read that comes back empty is not tried again on the next open", not rc._post_card_due(oc), rc._POST_MISSED)
finally:
    messenger_bot.MessengerBot.post_card = orig_card

if _fails:
    print(f"\nFAIL - test_messenger_post_card: {len(_fails)} failed")
    sys.exit(1)
print("\nOK - test_messenger_post_card: all pass")
