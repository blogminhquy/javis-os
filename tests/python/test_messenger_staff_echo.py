"""Messenger staff replies typed outside Javis reach the inbox (message echoes).

    python tests/run.py messenger_staff_echo

No network. A person who answers a customer in Facebook, Meta Business Suite or the Instagram app makes the Page send
an echo to the webhook. What is guarded:

  1. The Page webhook subscribes to `message_echoes`, but the health check still only requires the two fields the bot
     cannot work without, so an older webhook is not reported broken.
  2. Echoes are routed to the Page's bot as echoes (Facebook and Instagram), never as a customer turn.
  3. An echo carrying this app's id is Javis's own send (the bot or the Javis inbox) and is dropped; another app's echo
     becomes a turn-less call with `staff_echo` addressed to the customer (the echo's recipient). Meta retries count once.
  4. The runtime stores it as a staff ("human") message without unread count, never as a customer message, and does
     not store a second copy of a sentence Javis itself sent a moment ago (Instagram echoes carry no app id).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-messenger-echo-")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_runtime  # noqa: E402
import conversations  # noqa: E402
import messenger_bot  # noqa: E402
import messenger_setup  # noqa: E402

_fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  [{detail}]"))
    if not ok:
        _fails.append(name)


PAGE = "1234567890123"
IG = "17841400000000001"
OUR_APP = "1163825912872755"
INBOX_APP = "263902037430900"
TOKEN = "EAA" + "y" * 60
SECRET = "b" * 32

# ============================================================
# 1. Subscription fields
# ============================================================
check("the Page webhook subscribes to message echoes",
      "message_echoes" in messenger_bot.SUBSCRIBED_FIELDS.split(","), messenger_bot.SUBSCRIBED_FIELDS)
check("the health check still requires only messages and postbacks",
      tuple(messenger_setup.WEBHOOK_FIELDS) == ("messages", "messaging_postbacks"), messenger_setup.WEBHOOK_FIELDS)


# ============================================================
# 2. Routing
# ============================================================
class Probe(messenger_bot.MessengerBot):
    def __init__(self):
        super().__init__({"page_id": PAGE, "access_token": TOKEN, "app_secret": SECRET}, "", None,
                         giau_trang_thai=True)
        self.got = []

    async def _safe_event(self, ev, instagram=False):
        self.got.append(("event", instagram, ev["message"]["mid"]))

    async def _safe_echo(self, ev, instagram=False):
        self.got.append(("echo", instagram, ev["message"]["mid"]))


def echo(mid, text="Dạ shop gửi mẫu ạ", app_id=INBOX_APP, customer="555", page=PAGE, **extra):
    m = {"mid": mid, "text": text, "is_echo": True}
    if app_id:
        m["app_id"] = app_id
    m.update(extra)
    return {"sender": {"id": page}, "recipient": {"id": customer}, "timestamp": 1794830000000, "message": m}


async def _route():
    b = Probe()
    messenger_bot._REGISTRY.clear()
    messenger_bot._IG_REGISTRY.clear()
    messenger_bot._REGISTRY[PAGE] = b
    messenger_bot._IG_REGISTRY[IG] = b
    n_fb = await messenger_bot.handle_webhook({"object": "page", "entry": [{"id": PAGE, "messaging": [
        {"sender": {"id": "555"}, "recipient": {"id": PAGE}, "message": {"mid": "c1", "text": "giá sao shop"}},
        echo("e1"), echo("e2", is_deleted=True)]}]})
    n_ig = await messenger_bot.handle_webhook({"object": "instagram", "entry": [{"id": IG, "messaging": [
        echo("e3", app_id="", customer="900", page=IG)]}]})
    await asyncio.sleep(0)
    messenger_bot._REGISTRY.clear()
    messenger_bot._IG_REGISTRY.clear()
    return n_fb, n_ig, b.got

n_fb, n_ig, got = asyncio.run(_route())
check("a Page echo is handed over as an echo, the customer message as an event, a deleted echo not at all",
      n_fb == 2 and got[:2] == [("event", False, "c1"), ("echo", False, "e1")], (n_fb, got))
check("an Instagram echo is handed over as an Instagram echo", n_ig == 1 and got[2:] == [("echo", True, "e3")], got)


# ============================================================
# 3. The transport: own sends dropped, staff replies passed on without a turn
# ============================================================
async def _transport():
    calls = []

    async def answer(text, meta, progress):
        calls.append((text, dict(meta)))
        return {"text": "", "files": [], "im_lang": True}

    bot = messenger_bot.MessengerBot({"page_id": PAGE, "access_token": TOKEN, "app_secret": SECRET}, "",
                                     answer, giau_trang_thai=True)
    bot.account_id = "acc_test"
    bot.ig_id = IG
    sent = []

    async def fake_post(client, path, payload):
        sent.append(path)
        return {"ok": True}

    bot._post_json = fake_post
    real = messenger_bot.app_id_of
    messenger_bot.app_id_of = lambda aid: OUR_APP if aid == "acc_test" else ""
    real_ig = messenger_bot.instagram_of
    messenger_bot.instagram_of = lambda aid: {"id": IG, "username": "shop", "on": True}
    try:
        await bot._on_echo(echo("own", app_id=OUR_APP))                       # the bot or the Javis inbox sent it
        await bot._on_echo(echo("s1", text="Dạ size XL còn ạ"))              # staff in Meta Business Suite
        await bot._on_echo(echo("s1", text="Dạ size XL còn ạ"))              # Meta retry
        await bot._on_echo(echo("s2", text="", attachments=[{"type": "image", "payload": {"url": "https://x/y.jpg"}}]))
        await bot._on_echo(echo("s3", app_id="", customer="900", page=IG), instagram=True)
        await bot._on_echo(echo("s4", customer=PAGE))                          # no customer to file it under
    finally:
        messenger_bot.app_id_of = real
        messenger_bot.instagram_of = real_ig
    return calls, sent

calls, sent = asyncio.run(_transport())
mids = [m["message_id"] for _, m in calls]
check("this app's own echo is dropped, a retry counts once, an echo to the Page itself is dropped",
      mids == ["s1", "s2", "s3"], mids)
check("every call is flagged staff_echo and addressed to the customer",
      all(m.get("staff_echo") for _, m in calls) and [m["chat_id"] for _, m in calls] == ["555", "555", "ig:900"],
      [m.get("chat_id") for _, m in calls])
check("an attachment echo is described, not downloaded", "[" in calls[1][0] and calls[1][1]["message_id"] == "s2",
      calls[1][0])
check("nothing is ever sent back to Facebook for an echo", sent == [], sent)


# ============================================================
# 4. The runtime stores it as a staff message
# ============================================================
CFG = {"id": "bot_echo", "name": "Shop", "accounts": ["acc_test"]}


def meta(mid, chat="555", at=1794830000.0):
    return {"account_id": "acc_test", "_kenh": "messenger", "chat_id": chat, "chat_type": "private",
            "message_id": mid, "staff_echo": True, "echo_app_id": INBOX_APP, "sent_at": at}


def stored(chat="555"):
    with conversations._lock:
        rows = conversations._conn().execute(
            "SELECT m.sender_type, m.text, m.external_message_id, c.unread_count, c.last_sender_type FROM messages m"
            " JOIN conversations c ON c.id=m.conversation_id WHERE c.external_chat_id=? ORDER BY m.id",
            (chat,)).fetchall()
    return [dict(r) for r in rows]


r1 = chatbot_runtime.store_staff_echo(CFG, meta("s1"), "Dạ size XL còn ạ")
r2 = chatbot_runtime.store_staff_echo(CFG, meta("s1"), "Dạ size XL còn ạ")
rows = stored()
check("a staff echo is stored once, as a staff message", r1 == "stored" and r2 == "duplicate" and len(rows) == 1
      and rows[0]["sender_type"] == "human" and rows[0]["external_message_id"] == "s1", (r1, r2, rows))
check("it adds no unread count and marks the chat answered",
      rows and rows[0]["unread_count"] == 0 and rows[0]["last_sender_type"] == "human", rows)

# Javis sent this sentence itself (bot answer, stored without a channel id); its echo arrives without an app id.
conversations.ghi_su_kien({"channel": "messenger", "account_id": "acc_test", "account_name": "Shop", "bot_id": "bot_echo",
                           "external_chat_id": "ig:900", "chat_type": "private", "sender_type": "ai",
                           "text": "Dạ mẫu này còn màu đen ạ", "created_at": 1794830100.0})
r3 = chatbot_runtime.store_staff_echo(CFG, meta("ig_e1", chat="ig:900", at=1794830105.0), "Dạ mẫu này còn màu đen ạ")
rows = stored("ig:900")
check("the echo of a sentence Javis sent is not stored twice, the stored one gets the channel id",
      r3 == "duplicate" and len(rows) == 1 and rows[0]["sender_type"] == "ai" and rows[0]["external_message_id"] == "ig_e1",
      (r3, rows))


async def _answer_path():
    chatbot_runtime._deps["answer"] = None
    real = chatbot_runtime.chatbot_store.get_bot
    chatbot_runtime.chatbot_store.get_bot = lambda bid: dict(CFG, muc_quyen="read_docs")
    try:
        fn = chatbot_runtime._make_answer_fn("bot_echo")
        return await fn("Dạ shop gửi tracking ạ", dict(meta("s9", chat="777")), None)
    finally:
        chatbot_runtime.chatbot_store.get_bot = real

out = asyncio.run(_answer_path())
rows = stored("777")
check("through the bot's answer function the echo is stored and nothing is answered",
      out.get("im_lang") and not out.get("text") and [r["sender_type"] for r in rows] == ["human"], (out, rows))

if _fails:
    print(f"\n{len(_fails)} FAILED")
    sys.exit(1)
print("\nall ok")
