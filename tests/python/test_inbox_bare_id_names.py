"""Chats the Page or the OA opened show the customer's name, not a bare id (25/11/2026).

    python tests/run.py inbox_bare_id_names      (no network)

Field report (Messenger, Tấn Minh Travel): rows like 29081869774809275 "Bạn: Làng nghỉ dưỡng..." in the inbox. Those
chats were opened by the Page itself (auto reply, greeting, an ad's message) before the customer wrote a word, and the
echo path never looked the customer up. Zalo OA had the same hole. Guarded:

  1. A Page / OA echo carries the customer's name (`customer_name`), and the runtime files it as the chat's title.
  2. `nameless_customers` also lists chats with no title and no named customer, never a comment thread.
  3. `set_customer_name` names such a chat by its id; a name the owner set is never replaced.
  4. The Messenger bot names those chats once at start.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-bare-id-")

import conversations  # noqa: E402
import chatbot_runtime  # noqa: E402
import messenger_bot  # noqa: E402
import zalo_oa_bot as zo  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{str(extra)[:300]}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def run(c):
    return asyncio.run(c)


PAGE, PSID, OA, UID = "1234567890123", "29081869774809275", "579745863508352884", "2512523625412515"

# ---- 1. Echoes carry the customer's name ----
mev = []


async def mev_fn(kind, tt):
    mev.append((kind, tt))
mb = messenger_bot.MessengerBot({"page_id": PAGE, "access_token": "EAA" + "x" * 60, "app_secret": "a" * 32}, "", None,
                                giau_trang_thai=True, event_fn=mev_fn, account_id="acc-page")


async def fake_name(client, psid, instagram=False):
    return {PSID: "Hoài Phạm"}.get(psid, "")
mb._name_of = fake_name
run(mb._on_staff({"sender": {"id": PAGE}, "recipient": {"id": PSID},
                  "message": {"mid": "e1", "is_echo": True, "text": "Làng nghỉ dưỡng mang hơi thở..."}}))
check("Messenger: the Page's own message carries the customer's name",
      len(mev) == 1 and mev[0][1].get("customer_name") == "Hoài Phạm", mev)

oev = []


async def oev_fn(kind, tt):
    oev.append((kind, tt))
ob = zo.ZaloOABot('{"oa_id": "%s"}' % OA, "", None, giau_trang_thai=True, account_id="acc-oa", event_fn=oev_fn)


async def fake_oa_name(client, uid):
    return {UID: "Chị Lan"}.get(uid, "")
ob._name_of = fake_oa_name
ob._client = object()
run(ob._on_staff({"event_name": "oa_send_text", "oa_id": OA, "sender": {"id": OA}, "recipient": {"id": UID},
                  "message": {"msg_id": "o1", "text": "Dạ chào chị"}}))
check("Zalo OA: the OA's own message carries the customer's name",
      len(oev) == 1 and oev[0][1].get("customer_name") == "Chị Lan", oev)

mb2 = messenger_bot.MessengerBot({"page_id": PAGE, "access_token": "EAA" + "x" * 60, "app_secret": "a" * 32}, "", None,
                                 giau_trang_thai=True, event_fn=mev_fn, account_id="acc-page")


async def broken_name(client, psid, instagram=False):
    raise RuntimeError("graph down")
mb2._name_of = broken_name
mev.clear()
run(mb2._on_staff({"sender": {"id": PAGE}, "recipient": {"id": "111"},
                   "message": {"mid": "e9", "is_echo": True, "text": "Xin chào"}}))
check("a failed lookup never costs the message", len(mev) == 1 and mev[0][1].get("customer_name") == "", mev)

# ---- 1b. The runtime files the name as the chat's title ----
BOT = {"id": "bot_m", "name": "Page bot", "brain": "b", "channel": "messenger",
       "accounts": [{"id": "acc-page", "channel": "messenger"}]}
chatbot_runtime.chatbot_store.get_bot = lambda bid: dict(BOT) if bid == "bot_m" else None
run(chatbot_runtime.record_staff_message("bot_m", {
    "chat_id": PSID, "account_id": "acc-page", "message_id": "e1", "text": "Làng nghỉ dưỡng...",
    "platform": "messenger", "customer_name": "Hoài Phạm"}))
rows = {r["external_chat_id"]: r for r in conversations.danh_sach(channel="messenger", limit=50)}
check("a chat the Page opened shows the customer's name in the inbox", rows.get(PSID, {}).get("title") == "Hoài Phạm",
      {k: v.get("title") for k, v in rows.items()})

# ---- 2. / 3. Bare-id chats are found and named ----
for cid in ("28423743810632959", "40214229228224642"):
    run(chatbot_runtime.record_staff_message("bot_m", {
        "chat_id": cid, "account_id": "acc-page", "message_id": "x" + cid, "text": "Green Pine Resort...",
        "platform": "messenger"}))
conversations.ghi_su_kien({"channel": "messenger", "account_id": "acc-page", "bot_id": "bot_m",
                           "external_chat_id": "c:123_456", "chat_type": "private", "sender_type": "customer",
                           "sender_id": "999", "sender_name": "", "text": "comment"})
ids = conversations.nameless_customers("messenger", "acc-page")
check("bare-id chats the Page opened are listed (no customer row needed)",
      "28423743810632959" in ids and "40214229228224642" in ids and PSID not in ids, ids)
check("a comment thread is never listed", "c:123_456" not in ids, ids)
check("set_customer_name names a chat by its id",
      conversations.set_customer_name("messenger", "acc-page", "28423743810632959", "Điệp Phan") is True)
rows = {r["external_chat_id"]: r for r in conversations.danh_sach(channel="messenger", limit=50)}
check("the inbox shows it", rows["28423743810632959"]["title"] == "Điệp Phan")
check("a name already there is never replaced",
      conversations.set_customer_name("messenger", "acc-page", PSID, "Khác") is False
      and {r["external_chat_id"]: r for r in conversations.danh_sach(channel="messenger", limit=50)}[PSID]["title"]
      == "Hoài Phạm")

# ---- 4. The Messenger bot names them at start ----
mb3 = messenger_bot.MessengerBot({"page_id": PAGE, "access_token": "EAA" + "x" * 60, "app_secret": "a" * 32}, "", None,
                                 giau_trang_thai=True, account_id="acc-page")


async def name_all(client, psid, instagram=False):
    return {"40214229228224642": "Nguyễn T. Thu Phương", "999": "Ai đó"}.get(psid, "")
mb3.account_id = "acc-page"   # set by the runtime after the bot is built (start_bot)
mb3._name_of = name_all
messenger_bot.BACKFILL_PAUSE_S = 0
n = run(mb3.backfill_names(client=object()))
rows = {r["external_chat_id"]: r for r in conversations.danh_sach(channel="messenger", limit=50)}
check("start-up backfill names the remaining bare-id chat",
      n >= 1 and rows["40214229228224642"]["title"] == "Nguyễn T. Thu Phương", (n, rows["40214229228224642"]["title"]))
from pathlib import Path  # noqa: E402
check("Messenger starts the backfill once the bot runs",
      "asyncio.create_task(self._safe_backfill())" in (Path(SERVER) / "messenger_bot.py").read_text(encoding="utf-8"))

print()
if fails:
    print(f"{len(fails)} FAIL")
    raise SystemExit(1)
print("all ok")
