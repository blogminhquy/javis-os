"""Instagram through the Page connection (0.447.0).

    python tests/run.py messenger_instagram      (no network: Graph is faked)

Guarded, in order of what would hurt most if it broke:

  1. `object: "instagram"` webhooks reach the bot of the linked Page, keyed by the Instagram account id; echoes,
     other fields and unknown accounts are dropped, and Facebook Page webhooks still route as before.
  2. A direct message becomes conversation `ig:<user>`, a comment `igc:<top-level comment>`; the account's own
     comments are skipped, a reply under a comment joins its thread.
  3. Sending: a direct message goes to `/<page>/messages` with the bare user id, a comment reply to
     `/<comment>/replies`, never `/comments`; a file under an Instagram comment is refused in words.
  4. Instagram off (or not linked) drops its events; Facebook is untouched.
  5. A private reply from an Instagram comment opens the `ig:` chat the person's answer will land in.
  6. The Instagram permissions are asked only when the owner ticks Instagram: a Meta app without the Instagram use
     case refuses the whole login over them.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
from urllib.parse import parse_qs, urlparse

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-messenger-ig-")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx  # noqa: E402

import channel_accounts  # noqa: E402
import conversations  # noqa: E402
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
IG = "17841400000000001"
SECRET = "c" * 32
TOKEN = "EAA" + "t" * 60

aid, err = channel_accounts.create_account({
    "channel": "messenger", "token": f"{PAGE} {TOKEN} {SECRET}", "external_id": PAGE, "label": "Shop",
    "meta": {"bot_name": "Shop", "ig_id": IG, "ig_username": "shop.vn", "instagram": "on"}})
check("an account with a linked Instagram", bool(aid), err)
check("instagram_of reads the link", messenger_bot.instagram_of(aid) == {"id": IG, "username": "shop.vn", "on": True},
      messenger_bot.instagram_of(aid))


def ig_comment(cid, parent="", who="900", text="Giá sao shop?"):
    v = {"id": cid, "text": text, "from": {"id": who, "username": "lan.nguyen"},
         "media": {"id": "1799", "media_product_type": "FEED"}}
    if parent:
        v["parent_id"] = parent
    return {"field": "comments", "value": v}


# ============================================================
# 1-2. Routing and ids
# ============================================================
top = messenger_bot.ig_comment_event(ig_comment("c1")["value"], IG)
rep = messenger_bot.ig_comment_event(ig_comment("c2", parent="c1")["value"], IG)
check("a top-level Instagram comment is its own thread", top and top["root_id"] == "c1" and top["instagram"], top)
check("a reply joins the top-level thread", rep and rep["root_id"] == "c1", rep)
check("the account's own comment is skipped", messenger_bot.ig_comment_event(ig_comment("c3", who=IG)["value"], IG) is None)
check("the commenter is named by username", top["from_name"] == "lan.nguyen", top)
check("ids: igc: is a comment, ig: is not, both are Instagram, raw ids strip the prefix",
      messenger_bot.is_comment_chat("igc:1") and not messenger_bot.is_comment_chat("ig:1")
      and messenger_bot.is_instagram_chat("ig:1") and messenger_bot.is_instagram_chat("igc:1")
      and not messenger_bot.is_instagram_chat("cmt:1") and messenger_bot.raw_chat_id("ig:42") == "42"
      and messenger_bot.raw_chat_id("igc:c1") == "c1" and messenger_bot.raw_chat_id("cmt:5") == "5"
      and messenger_bot.raw_chat_id("777") == "777")


async def _routing():
    got = []

    class B:
        async def _safe_comment(self, com):
            got.append(("c", com))

        async def _safe_event(self, ev, instagram=False):
            got.append(("m", instagram, ev))
    messenger_bot._IG_REGISTRY.clear()
    messenger_bot._REGISTRY.clear()
    messenger_bot._IG_REGISTRY[IG] = B()
    messenger_bot._REGISTRY[PAGE] = B()
    n = await messenger_bot.handle_webhook({"object": "instagram", "entry": [
        {"id": IG, "changes": [ig_comment("c1"), {"field": "mentions", "value": {}}],
         "messaging": [{"sender": {"id": "900"}, "recipient": {"id": IG}, "message": {"mid": "m1", "text": "hi"}},
                       {"sender": {"id": IG}, "recipient": {"id": "900"}, "message": {"mid": "m2", "text": "x",
                                                                                     "is_echo": True}}]},
        {"id": "999", "messaging": [{"sender": {"id": "1"}, "message": {"mid": "m3", "text": "y"}}]}]})
    n_fb = await messenger_bot.handle_webhook({"object": "page", "entry": [
        {"id": PAGE, "messaging": [{"sender": {"id": "77"}, "message": {"mid": "f1", "text": "fb"}}]}]})
    await asyncio.sleep(0)
    messenger_bot._IG_REGISTRY.clear()
    messenger_bot._REGISTRY.clear()
    return n, n_fb, got

n, n_fb, got = run(_routing())
check("Instagram comment and message reach the linked Page's bot; echoes, other fields, unknown accounts do not",
      n == 2 and [g[0] for g in got[:2]] == ["c", "m"] and got[1][1] is True, (n, got))
check("Facebook Page webhooks still route as before", n_fb == 1 and got[-1][0] == "m" and got[-1][1] is False, got)


# ============================================================
# 2-4. Bot turns
# ============================================================
def make_bot(answer):
    bot = messenger_bot.MessengerBot({"page_id": PAGE, "access_token": TOKEN, "app_secret": SECRET}, "", answer,
                                     giau_trang_thai=True)
    bot.account_id = aid
    bot.ig_id = IG
    return bot


async def _dm_turn():
    calls, seen = [], {}

    async def answer(text, meta, progress):
        seen.update(text=text, meta=dict(meta or {}))
        return {"text": "Dạ chào chị"}

    bot = make_bot(answer)

    async def fake_post(client, path, payload):
        calls.append((path, payload))
        return {"ok": True}

    async def fake_name(client, psid, instagram=False):
        return "Lan" if instagram else "?"
    bot._post_json = fake_post
    bot._name_of = fake_name
    try:
        await bot._on_event({"sender": {"id": "900"}, "message": {"mid": "m1", "text": "Còn hàng không?"}}, instagram=True)
        for task in list(bot._current.values()):
            await task
        await asyncio.sleep(0)
    finally:
        if bot._client:
            await bot._client.aclose()
    return calls, seen

calls, seen = run(_dm_turn())
m = seen.get("meta") or {}
check("an Instagram message runs a turn in conversation ig:<user>, named, marked Instagram",
      seen.get("text") == "Còn hàng không?" and m.get("chat_id") == "ig:900" and m.get("user_name") == "Lan"
      and m.get("instagram"), seen)
replies = [c for c in calls if (c[1] or {}).get("message")]
check("the answer goes to /<page>/messages with the bare Instagram user id",
      replies == [(f"{PAGE}/messages", {"recipient": {"id": "900"}, "messaging_type": "RESPONSE",
                                         "message": {"text": "Dạ chào chị"}})], calls)


async def _comment_turn(mode="reply", ig_on=True):
    calls, seen = [], {}

    async def answer(text, meta, progress):
        seen.update(text=text, meta=dict(meta or {}))
        return {"text": "Dạ 150k ạ"}

    bot = make_bot(answer)

    async def fake_post(client, path, payload):
        calls.append((path, payload))
        return {"ok": True, "id": "r1"}

    async def fake_post_text(client, post_id, instagram=False):
        return "Áo len mới về" if instagram else "?"
    bot._post_json = fake_post
    bot._post_text = fake_post_text
    o_mode, o_ig = messenger_bot.comment_mode, messenger_bot.instagram_of
    messenger_bot.comment_mode = lambda a: mode
    messenger_bot.instagram_of = lambda a: {"id": IG, "username": "shop.vn", "on": ig_on}
    try:
        await bot._on_comment(dict(rep))
        for task in list(bot._current.values()):
            await task
        await asyncio.sleep(0)
    finally:
        messenger_bot.comment_mode, messenger_bot.instagram_of = o_mode, o_ig
        if bot._client:
            await bot._client.aclose()
    return calls, seen

calls, seen = run(_comment_turn())
m = seen.get("meta") or {}
check("an Instagram comment runs in thread igc:<top-level>, told it is a public Instagram comment",
      m.get("chat_id") == "igc:c1" and "Instagram" in m.get("ghi_chu_dau", "") and "CÔNG KHAI" in m.get("ghi_chu_dau", "")
      and "Áo len" in m.get("chat_title", "") and m.get("instagram"), m)
check("the public answer goes to /<comment>/replies, never /comments",
      calls == [("c1/replies", {"message": "Dạ 150k ạ"})], calls)
calls, seen = run(_comment_turn(ig_on=False))
check("Instagram off: comments are dropped", not seen and not calls, (seen, calls))


async def _file_refused():
    bot = make_bot(None)
    p = os.path.join(os.environ["JAVIS_STATE_DIR"], "a.jpg")
    with open(p, "wb") as f:
        f.write(b"\xff\xd8\xff")
    return await bot.send_file(p, "", chat="igc:c1")

ok, err_ = run(_file_refused())
check("a file under an Instagram comment is refused in words", not ok and err_, (ok, err_))


# ============================================================
# 5. Private reply from an Instagram comment
# ============================================================
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

SENT = []


async def fake_post_json(self, client, path, payload):
    SENT.append((path, payload))
    return {"ok": True, "recipient_id": "900", "message_id": "m_priv"}

messenger_bot.MessengerBot._post_json = fake_post_json
conv = conversations.ghi_su_kien({"channel": "messenger", "account_id": aid, "external_chat_id": "igc:c1",
                                  "chat_type": "private", "chat_title": "Bình luận Instagram", "sender_type": "customer",
                                  "sender_id": "900", "sender_name": "lan.nguyen", "text": "Giá?",
                                  "external_message_id": "c1"})["conversation_id"]
r = TestClient(main.app).post(f"/conversations/{conv}/private-reply", data={"text": "Em gửi giá ạ"})
j = r.json()
check("a private reply from an Instagram comment is a Private Reply to that comment",
      r.status_code == 200 and SENT and SENT[0][1].get("recipient") == {"comment_id": "c1"}, (j, SENT))
dm = conversations.conversation_id_of("messenger", aid, "ig:900")
check("it opens the ig:<user> chat the person's answer lands in", dm and j.get("dm_conversation_id") == dm, (dm, j))

# ============================================================
# 6. Permissions only when ticked
# ============================================================
q = parse_qs(urlparse(messenger_oauth.login_url("1", "https://x/cb", "s")).query)
q_ig = parse_qs(urlparse(messenger_oauth.login_url("1", "https://x/cb", "s", instagram=True)).query)
check("no Instagram permission unless asked", "instagram" not in q["scope"][0], q["scope"])
check("ticked: instagram_basic, instagram_manage_messages, instagram_manage_comments",
      all(s in q_ig["scope"][0].split(",") for s in messenger_oauth.IG_SCOPES), q_ig["scope"])

print()
if _fails:
    print(f"ĐỎ: {len(_fails)}: " + "; ".join(_fails))
    sys.exit(1)
print("OK - test_messenger_instagram: all pass")
