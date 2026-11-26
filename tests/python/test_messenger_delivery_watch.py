"""Messenger: warn when Meta delivers only messages from people with a role on the app or Page (25/11/2026).

    python tests/run.py messenger_delivery_watch      (no network: Graph and the inbox are faked)

Field report: a Meta app without Advanced Access for pages_messaging. Javis received the Page's own echoes and the
messages of people with a role on the app or Page; ordinary customers' messages never arrived and nobody noticed
for a day. Guarded:

  1. The pattern (`DeliveryWatch`): the Page wrote to 3+ people never heard from in 24 hours while someone else's
     messages still arrive, or none arrived for 12+ hours while the Page kept writing. Two silent people, or a Page
     that mostly writes to people it hears from, is no warning. Private replies to comments do not count.
  2. Wiring: echoes (`_on_staff`) and bot sends (`_send_one`) count as sent, `_on_event` as inbound; the warning shows
     on the bot card (`loi_danh_tinh`) next to the subscribe note, and goes away when an ordinary customer writes.
  3. The inbox rules out a customer who wrote before a restart. The owner's own Messenger channel is never watched.
     Nothing here ever costs a message.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-messenger-delivery-")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_runtime  # noqa: E402
import conversations  # noqa: E402
import messenger_bot as mb  # noqa: E402

_fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  [{detail}]"))
    if not ok:
        _fails.append(name)


H = 3600
T0 = 1_800_000_000.0
PAGE = "1234567890123"
TESTER = "24000000000001"           # a person with a role on the app: their messages arrive
CUSTOMERS = ["24000000000101", "24000000000102", "24000000000103", "24000000000104"]

# ============================================================
# 1. The pattern
# ============================================================
w = mb.DeliveryWatch(now=T0)
for i, c in enumerate(CUSTOMERS[:3]):
    w.inbound(c, T0 + i)
    w.sent(c, T0 + i + 1)
check("healthy Page: everyone the Page wrote to was heard first", w.suspects(T0 + 10) == [], w.suspects(T0 + 10))

w = mb.DeliveryWatch(now=T0)
w.inbound(TESTER, T0)
w.sent(TESTER, T0 + 1)
for i, c in enumerate(CUSTOMERS[:3]):
    w.sent(c, T0 + 10 + i)
got = w.suspects(T0 + 60)
check("only the tester's messages arrive: the 3 customers are suspects, newest first",
      got == list(reversed(CUSTOMERS[:3])), got)

w = mb.DeliveryWatch(now=T0)
w.inbound(TESTER, T0)
w.sent(CUSTOMERS[0], T0 + 1)
w.sent(CUSTOMERS[1], T0 + 2)
check("two silent people are not enough", w.suspects(T0 + 60) == [])

w = mb.DeliveryWatch(now=T0)
heard = [f"2400000000020{i}" for i in range(5)]
for i, p in enumerate(heard):
    w.inbound(p, T0 + i)
    w.sent(p, T0 + i + 1)
for i, c in enumerate(CUSTOMERS[:3]):
    w.sent(c, T0 + 20 + i)
check("a Page that mostly writes to people it hears from is no warning", w.suspects(T0 + 60) == [])

w = mb.DeliveryWatch(now=T0)
w.inbound(TESTER, T0)
for i, c in enumerate(CUSTOMERS[:3]):
    w.sent(c, T0 + 1 + i)
check("sends older than 24 hours drop out of the window", w.suspects(T0 + 25 * H) == [])

# No message in at all.
w = mb.DeliveryWatch(now=T0)
for i, c in enumerate(CUSTOMERS[:3]):
    w.sent(c, T0 + 13 * H + i)
check("nothing in for 13 hours while the Page keeps writing: suspects", len(w.suspects(T0 + 13 * H + 10)) == 3)
w = mb.DeliveryWatch(now=T0)
for i, c in enumerate(CUSTOMERS[:3]):
    w.sent(c, T0 + 60 + i)
check("nothing in yet, but the watch only started an hour ago: no suspects", w.suspects(T0 + H) == [])
w = mb.DeliveryWatch(now=T0)
for i, c in enumerate(CUSTOMERS[:3]):
    w.sent(c, T0 + 60 + i)
check("nothing in for 13 hours, but the Page stopped writing 12+ hours ago: no suspects",
      w.suspects(T0 + 13 * H) == [])
w = mb.DeliveryWatch(now=T0)
w.inbound(TESTER, T0 + 30 * H)                 # more than 24 hours before the sends: nothing is still arriving
for i, c in enumerate(CUSTOMERS[:3]):
    w.sent(c, T0 + 55 * H + i)
check("a message from more than 24 hours ago does not count as still arriving",
      len(w.suspects(T0 + 55 * H + 10)) == 3 and w.inbound_at == {}, w.inbound_at)

# Private replies to comments.
w = mb.DeliveryWatch(now=T0)
w.inbound(TESTER, T0)
w.sent(CUSTOMERS[0], T0 + 1)                   # echo came back before the private reply call returned
w.exempt(CUSTOMERS[0], T0 + 2)
w.sent(CUSTOMERS[0], T0 + 3)
w.exempt(CUSTOMERS[1], T0 + 4)
w.sent(CUSTOMERS[1], T0 + 5)
w.sent(CUSTOMERS[2], T0 + 6)
check("private replies to commenters never count as missing messages", w.suspects(T0 + 60) == [], w.sent_at)

# Warning and how it ends.
w = mb.DeliveryWatch(now=T0)
w.inbound(TESTER, T0)
for i, c in enumerate(CUSTOMERS[:3]):
    w.sent(c, T0 + 1 + i)
w.warn()
check("the tester writing again does not end the warning", w.inbound(TESTER, T0 + 10) is False and w.warned)
check("a customer writing ends it", w.inbound(CUSTOMERS[3], T0 + 11) is True and not w.warned)
check("and starts over: earlier sends no longer count", w.suspects(T0 + 12) == [] and w.sent_at == {})

big = mb.DeliveryWatch(now=T0)
for i in range(mb.DELIVERY_MAX_IDS + 50):
    big.sent(str(10 ** 13 + i), T0 + i)
check("memory stays bounded", len(big.sent_at) <= mb.DELIVERY_MAX_IDS, len(big.sent_at))

# ============================================================
# 2. Wiring in MessengerBot
# ============================================================
stored = {}        # psid -> time of a stored customer message (the inbox)
conversations.last_customer_message_at = lambda ch, aid, chat: stored.get(chat) if ch == "messenger" else None


def make_bot(account_id="acc-page"):
    posts, events = [], []

    async def post(client, path, payload):
        posts.append((path, payload))
        return {"ok": True, "message_id": "m.out", "recipient_id": "24000000000999"}

    async def name(client, psid, instagram=False):
        return ""

    async def event_fn(kind, tt):
        events.append((kind, tt))

    bot = mb.MessengerBot({"page_id": PAGE, "access_token": "EAA" + "x" * 60, "app_secret": "a" * 32}, "",
                          None, giau_trang_thai=True, event_fn=event_fn,
                          precheck_fn=lambda text, meta: {})      # silent turns: only the watch is under test
    bot.account_id = account_id
    bot._post_json, bot._name_of, bot._client = post, name, object()
    bot.delivery = mb.DeliveryWatch(now=time.time() - 2 * H)
    return bot, posts, events


def inbound_ev(psid, mid, text="alo"):
    return {"sender": {"id": psid}, "recipient": {"id": PAGE}, "timestamp": 1,
            "message": {"mid": mid, "text": text}}


def echo_ev(psid, mid, text="Dạ shop chào anh chị", tagged=False):
    msg = {"mid": mid, "is_echo": True, "text": text}
    if tagged:
        msg["metadata"] = mb.ECHO_TAG
    return {"sender": {"id": PAGE}, "recipient": {"id": psid}, "message": msg}


async def settle(bot, until):
    for _ in range(200):
        if until():
            return
        await asyncio.sleep(0.01)


async def wiring():
    out = {}
    bot, posts, events = make_bot()
    bot._subscribe_note = "SUB"
    bot._show_notes()
    await bot._on_event(inbound_ev(TESTER, "mid.t1"))
    await bot._send_one(None, TESTER, "Dạ em chào anh")                       # the bot answers the tester
    for i, c in enumerate(CUSTOMERS[:3]):
        await bot._on_staff(echo_ev(c, f"e{i}"))                              # the Page's automatic replies
    await settle(bot, lambda: bool(bot.delivery_warning))
    out["warning"] = bot.delivery_warning
    out["card"] = chatbot_runtime._trang_thai_poller(bot)["loi_danh_tinh"]
    out["staff_events"] = len(events)
    out["sent"] = sorted(bot.delivery.sent_at)
    await bot._on_event(inbound_ev(TESTER, "mid.t2"))
    out["after_tester"] = bot.delivery_warning
    await bot._on_event(inbound_ev(CUSTOMERS[0], "mid.c1"))
    out["after_customer"] = (bot.delivery_warning, bot.loi_danh_tinh)
    return out

o = asyncio.run(wiring())
check("echoes, bot sends and inbound messages reach the watch",
      o["sent"] == sorted([TESTER] + CUSTOMERS[:3]), o["sent"])
check("echoes still reach the inbox as before", o["staff_events"] == 3, o["staff_events"])
check("the warning is set and names the fix",
      "pages_messaging" in o["warning"] and "5.3" in o["warning"] and "3" in o["warning"], o["warning"])
check("the bot card shows it next to the subscribe note",
      o["card"].startswith("SUB ") and o["warning"] in o["card"], o["card"])
check("the tester writing again keeps the warning", o["after_tester"] == o["warning"], o["after_tester"])
check("a customer's message clears it, the subscribe note stays", o["after_customer"] == ("", "SUB"),
      o["after_customer"])
check("no em dash or en dash in the warning", not any(ch in o["warning"] for ch in "—–"), o["warning"])


async def restart_case():
    stored.clear()
    stored[CUSTOMERS[0]] = T0 - 30 * H        # wrote before Javis restarted: the inbox knows them
    bot, _p, _e = make_bot()
    await bot._on_event(inbound_ev(TESTER, "mid.r1"))
    for i, c in enumerate(CUSTOMERS[:3]):
        await bot._on_staff(echo_ev(c, f"r{i}"))
    got = await bot._check_delivery()
    stored.clear()
    return got, bot.delivery_warning, bot.delivery.warned

got, warning, warned = asyncio.run(restart_case())
check("a customer the inbox already heard from is ruled out (2 left: no warning)",
      got is False and warning == "" and not warned, (got, warning))


async def owner_channel():
    bot, _p, _e = make_bot(account_id="")
    await bot._on_event(inbound_ev(TESTER, "mid.o1"))
    for i, c in enumerate(CUSTOMERS[:3]):
        await bot._on_staff(echo_ev(c, f"o{i}", tagged=True))
    await asyncio.sleep(0.05)
    return bot.delivery.sent_at, bot.delivery_warning

sent, warning = asyncio.run(owner_channel())
check("the owner's own Messenger channel is never watched", sent == {} and warning == "", (sent, warning))


async def private_reply_case():
    bot, _p, _e = make_bot()
    r = await bot.private_reply("123_456", "Dạ em nhắn riêng anh nhé")
    return r, dict(bot.delivery.exempt_at)

r, exempt = asyncio.run(private_reply_case())
check("a private reply exempts its recipient", r.get("ok") and "24000000000999" in exempt, (r, exempt))


async def never_raises():
    bot, _p, events = make_bot()

    class Broken:
        def sent(self, *a, **k):
            raise RuntimeError("boom")
        inbound = sent

    bot.delivery = Broken()
    await bot._on_staff(echo_ev(CUSTOMERS[0], "x1"))
    await bot._on_event(inbound_ev(TESTER, "mid.x1"))
    d = await bot._send_one(None, TESTER, "ok")
    return len(events), d.get("ok"), await bot._check_delivery()

n_events, sent_ok, checked = asyncio.run(never_raises())
check("a broken watch never costs a message", n_events == 1 and sent_ok and checked is False,
      (n_events, sent_ok, checked))

print()
print("ALL OK" if not _fails else f"{len(_fails)} FAILED: {_fails}")
sys.exit(1 if _fails else 0)
