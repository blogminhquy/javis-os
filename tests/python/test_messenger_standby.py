"""Messenger standby: messages of a conversation another app holds still reach the Javis inbox.

    python tests/run.py messenger_standby

No network. When another app (Haravan Funnel, or the Page Inbox after a "talk to staff" button) holds a conversation,
Meta sends its messages to every other app only as `standby` events. What is guarded:

  1. The Page webhook subscribes to `standby`; the health check still requires only messages and postbacks.
  2. Standby entries are routed to the Page's bot flagged standby (Facebook and Instagram); echoes inside standby go
     the staff echo way; ordinary `messaging` events are not flagged.
  3. The transport records a standby message as a `log_only` call: no reply, no seen mark, nothing sent to Facebook.
  4. The stored conversation carries the `held_elsewhere` mark the inbox warns with; a message delivered to Javis itself
     clears it, and a retried copy of a standby message does not touch it.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-messenger-standby-")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import messenger_bot  # noqa: E402
import messenger_setup  # noqa: E402

_fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  [{detail}]"))
    if not ok:
        _fails.append(name)


PAGE = "1234567890123"
IG = "17841400000000001"
TOKEN = "EAA" + "y" * 60
SECRET = "b" * 32

# 1. Subscription fields
check("the Page webhook subscribes to standby",
      "standby" in messenger_bot.SUBSCRIBED_FIELDS.split(","), messenger_bot.SUBSCRIBED_FIELDS)
check("the health check still requires only messages and postbacks",
      tuple(messenger_setup.WEBHOOK_FIELDS) == ("messages", "messaging_postbacks"), messenger_setup.WEBHOOK_FIELDS)


# 2. Routing
class Probe(messenger_bot.MessengerBot):
    def __init__(self):
        super().__init__({"page_id": PAGE, "access_token": TOKEN, "app_secret": SECRET}, "", None,
                         giau_trang_thai=True)
        self.got = []

    async def _safe_event(self, ev, instagram=False, standby=False):
        self.got.append(("event", instagram, standby, ev["message"]["mid"]))

    async def _safe_echo(self, ev, instagram=False):
        self.got.append(("echo", instagram, ev["message"]["mid"]))


def customer(mid, sender="555", page=PAGE, text="chào shop"):
    return {"sender": {"id": sender}, "recipient": {"id": page}, "timestamp": 1794830000000,
            "message": {"mid": mid, "text": text}}


async def _route():
    b = Probe()
    messenger_bot._REGISTRY.clear()
    messenger_bot._IG_REGISTRY.clear()
    messenger_bot._REGISTRY[PAGE] = b
    messenger_bot._IG_REGISTRY[IG] = b
    echo = {"sender": {"id": PAGE}, "recipient": {"id": "555"},
            "message": {"mid": "e1", "text": "Dạ shop đây", "is_echo": True, "app_id": "363772567412181"}}
    n_fb = await messenger_bot.handle_webhook({"object": "page", "entry": [{
        "id": PAGE, "messaging": [customer("m1")], "standby": [customer("s1"), echo]}]})
    n_ig = await messenger_bot.handle_webhook({"object": "instagram", "entry": [{
        "id": IG, "standby": [customer("s2", sender="900", page=IG)]}]})
    await asyncio.sleep(0)
    messenger_bot._REGISTRY.clear()
    messenger_bot._IG_REGISTRY.clear()
    return n_fb, n_ig, b.got

n_fb, n_ig, got = asyncio.run(_route())
check("a messaging event is not flagged, a standby one is, a standby echo goes the echo way",
      n_fb == 3 and sorted(got[:3]) == sorted([("event", False, False, "m1"), ("event", False, True, "s1"),
                                               ("echo", False, "e1")]), (n_fb, got))
check("an Instagram standby message is handed over flagged standby",
      n_ig == 1 and got[3:] == [("event", True, True, "s2")], got)


# 3. The transport records it, sends nothing
async def _transport():
    calls, sent = [], []

    async def answer(text, meta, progress):
        calls.append((text, dict(meta), progress))
        return {"text": "should never be sent", "files": [], "im_lang": False}

    bot = messenger_bot.MessengerBot({"page_id": PAGE, "access_token": TOKEN, "app_secret": SECRET}, "",
                                     answer, giau_trang_thai=True)
    bot.account_id = "acc_test"

    async def fake_post(client, path, payload):
        sent.append((path, payload))
        return {"ok": True}

    async def fake_name(client, psid, instagram=False):
        return "Khách"

    bot._post_json = fake_post
    bot._name_of = fake_name
    await bot._on_event(customer("s1"), standby=True)
    await bot._on_event(customer("s1"), standby=True)     # Meta retry
    if bot._client:
        await bot._client.aclose()
    return calls, sent

calls, sent = asyncio.run(_transport())
check("a standby message is passed on once, flagged log_only and standby",
      len(calls) == 1 and calls[0][0] == "chào shop" and calls[0][1].get("log_only") and calls[0][1].get("standby")
      and calls[0][1].get("chat_id") == "555" and calls[0][2] is None, calls)
check("nothing is sent to Facebook for a standby message (no reply, no seen mark)", sent == [], sent)

# 4. The inbox mark
import chatbot_runtime  # noqa: E402
import conversations  # noqa: E402

cfg = {"id": "bot_standby", "name": "Bot", "channel": "messenger", "accounts": []}
base = {"platform": "messenger", "chat_id": "777", "chat_type": "private", "chat_title": "", "user_id": "777",
        "user_name": "Khách", "username": "Khách", "account_id": "acc_standby"}


def held():
    cid = conversations.conversation_id_of("messenger", "acc_standby", "777")
    return ((conversations.chi_tiet(cid) or {}).get("metadata") or {}).get(conversations.HELD_ELSEWHERE)


chatbot_runtime.ghi_tin_khach(cfg, dict(base, message_id="h1"), "chào shop")
check("a message delivered to Javis leaves no held mark", held() is None, held())
chatbot_runtime.ghi_tin_khach(cfg, dict(base, message_id="h2", standby=True, log_only=True), "còn hàng không")
mark = held()
check("a standby message marks the conversation as held by another app",
      isinstance(mark, dict) and mark.get("at", 0) > 0, mark)
chatbot_runtime.ghi_tin_khach(cfg, dict(base, message_id="h1"), "chào shop")
check("a retried copy of an older delivered message does not clear the mark", held() == mark, held())
chatbot_runtime.ghi_tin_khach(cfg, dict(base, message_id="h3"), "alo")
check("the next message delivered to Javis clears the mark", held() is None, held())
chatbot_runtime.ghi_tin_khach(cfg, dict(base, chat_id="c_1", message_id="h4", comment=True, standby=True), "giá?")
check("Page comments never carry the mark",
      ((conversations.chi_tiet(conversations.conversation_id_of("messenger", "acc_standby", "c_1")) or {})
       .get("metadata") or {}).get(conversations.HELD_ELSEWHERE) is None)

if _fails:
    print(f"\n{len(_fails)} FAILED")
    sys.exit(1)
print("\nall ok")
