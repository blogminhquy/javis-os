"""Ask the staff, then tell the customer (staff_requests.py, 2026-11-26).

    python tests/run.py staff_requests      (no network: the channel transport and the engine are fakes)

Locked here:
  1. The bot setting `staff_contact` is stored scoped to one channel account; empty or broken clears it.
  2. `ask_staff` is offered only to a bot turn with a staff contact on that turn's account, at hub mode "full" AND the
     bot's own level "full" for that chat. Never below, never inside the staff chat, never on a relay turn, never
     without a turn. The hub adds it after its cache (`discover_all`), and the call checks everything again.
  3. The question goes to the staff chat through the channel's normal transport, starting with a request code, and an
     open request is recorded with the customer chat and message. A chat cannot pile up more than a few.
  4. A staff message answers by code, by quoting the request, or (one request open) as a plain next message; the
     answer is passed on in a bot turn of the customer's chat and sent to that chat. Several open and no code: one
     "which request?" note, nothing passed on. A message in any other chat, or on another account, is left alone.
  5. Requests expire after 24 hours: marked expired, nothing sent.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-staffreq-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channel_accounts  # noqa: E402
import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import mcp_hub  # noqa: E402
import staff_requests as sr  # noqa: E402
import telegram_bot  # noqa: E402
import turn_context  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:400] + "]") if extra != "" and not cond else ""))
    if not cond:
        fails.append(name)


def run(c):
    return asyncio.run(c)


# ---- fixtures: one Telegram bot account, one personal Zalo connection (fake ids, never real people) ----
ZCONN = "zconn-test-1"
channel_accounts.tai_khoan_ao = lambda: [channel_accounts._ao_cua(ZCONN, "Shop Zalo")]
TG, err = channel_accounts.create_account({"channel": "telegram", "token": "123:fake", "label": "Shop TG",
                                           "external_id": "shop_test_bot"})
check("a Telegram account for the test", bool(TG), err)
TG2, _ = channel_accounts.create_account({"channel": "telegram", "token": "456:fake", "label": "Other TG",
                                          "external_id": "other_test_bot"})
STAFF = "900000001"          # the staff member's private chat with the bot
CUST1, CUST2, OTHER = "700000001", "700000002", "700000009"
VAULT = tempfile.mkdtemp(prefix="javis-staffreq-brain-")
contact = {"account_id": TG, "chat_id": STAFF, "chat_type": "private", "name": "Chị Lan"}

bot_id, err = chatbot_store.create_bot({"name": "Shop", "agent_slug": "ban-hang", "brain": VAULT,
                                        "account_ids": TG, "muc_quyen": "full", "xac_nhan_rui_ro": True,
                                        "staff_contact": json.dumps(contact)})
check("bot created with a staff contact", bool(bot_id), err)

# ============================================================
# 1. The setting
# ============================================================
b = chatbot_store.get_bot(bot_id)
check("the contact is stored scoped to its account", b["staff_contact"] == contact, b.get("staff_contact"))
check("a contact without an account id is no contact", chatbot_store.clean_staff_contact({"chat_id": "1"}) == {})
check("broken JSON is no contact", chatbot_store.clean_staff_contact("{oops") == {})
ok, err = chatbot_store.update_bot(bot_id, {"staff_contact": ""})
check("saving an empty value clears it", ok and chatbot_store.get_bot(bot_id)["staff_contact"] == {}, err)
chatbot_store.update_bot(bot_id, {"staff_contact": json.dumps(contact)})
old, _ = chatbot_store.create_bot({"name": "Old", "agent_slug": "x", "brain": VAULT})
check("an older bot reads as having no contact", chatbot_store.get_bot(old)["staff_contact"] == {})


# ============================================================
# 2. Who gets the tool
# ============================================================
def turn(chat=CUST1, account=TG, kenh="telegram", bid=None, **more):
    t = turn_context.make(kenh, sender_id="u-" + chat, chat_type="private", chat_id=chat)
    t.update(bot_id=bid or bot_id, account_id=account, chat_message_id="m-" + chat, user_name="Khách " + chat[-1])
    t.update(more)
    return t


def offered(t, mode="full"):
    tok = turn_context.bind(t)
    try:
        return sr.turn_tool(mode) is not None
    finally:
        turn_context.reset(tok)


check("full bot, contact on this account, customer chat: offered", offered(turn()))
check("the description stays short", len(sr.TOOL_DESCRIPTION) < 300, len(sr.TOOL_DESCRIPTION))
for lvl in ("suggest", "read_docs", "auto"):
    chatbot_store.update_bot(bot_id, {"muc_quyen": lvl, "xac_nhan_rui_ro": True})
    check(f"bot at '{lvl}': not offered", not offered(turn()))
chatbot_store.update_bot(bot_id, {"muc_quyen": "full", "xac_nhan_rui_ro": True})
check("hub mode 'auto' (a full bot still): not offered", not offered(turn(), "auto"))
check("hub mode 'read_docs': not offered", not offered(turn(), "read_docs"))
check("unknown hub mode: not offered", not offered(turn(), "write"))
check("inside the staff chat itself: not offered", not offered(turn(chat=STAFF)))
check("a turn on another account: not offered", not offered(turn(account=TG2)))
check("a relay turn: not offered", not offered(turn(staff_relay=True)))
check("the owner's own turn (no bot): not offered", not offered(turn(bid=" ")))
check("no turn bound: not offered", sr.turn_tool("full") is None)
chatbot_store.update_bot(bot_id, {"staff_contact": ""})
check("no contact: not offered", not offered(turn()))
chatbot_store.update_bot(bot_id, {"staff_contact": json.dumps(contact)})

# A per-chat exception raising ONE chat to full on a read-only bot: offered in that chat only.
chatbot_store.update_bot(bot_id, {"muc_quyen": "suggest",
                                  "ngoai_le": json.dumps([{"account_id": TG, "chat_id": CUST1, "muc_quyen": "full"}]),
                                  "xac_nhan_ngoai_le": True})
check("read-only bot, chat raised to full by an exception: offered there", offered(turn()))
check("... and not in another chat of that bot", not offered(turn(chat=CUST2)))
chatbot_store.update_bot(bot_id, {"muc_quyen": "full", "xac_nhan_rui_ro": True, "ngoai_le": "[]"})

# Through the hub: added after the cache, to that turn only.
mcp_hub._lazy_on = lambda n, chars=0: False


async def hub_names(t, mode="full"):
    tok = turn_context.bind(t) if t else None
    try:
        tools, route = await mcp_hub.discover_all(mode, vault_root=VAULT, for_bot=True)
        return {x["fn"] for x in tools}, route
    finally:
        if tok:
            turn_context.reset(tok)


names, route = run(hub_names(turn()))
check("the hub lists ask_staff for that turn", sr.TOOL in names and sr.TOOL in route)
check("its route is marked an outside action at full", route.get(sr.TOOL, {}).get("effect") == "danger"
      and route.get(sr.TOOL, {}).get("required_mode") == "full")
names2, route2 = run(hub_names(turn(chat=STAFF)))
check("the next turn (staff chat) gets the cached list without it", sr.TOOL not in names2 and sr.TOOL not in route2)
names3, _ = run(hub_names(turn(), "auto"))
check("hub mode auto never lists it", sr.TOOL not in names3)
names4, _ = run(hub_names(None))
check("no turn: the shared list has no ask_staff", sr.TOOL not in names4)

# ============================================================
# 3. Asking
# ============================================================
sent = []


async def fake_gui(kenh, tk, chat_id, text, chat_type="private", **extra):
    sent.append({"kenh": kenh, "tk": tk, "chat": str(chat_id), "text": text, "type": chat_type, "extra": extra})
    return True, ""

chatbot_runtime.channels.gui = fake_gui


async def ask_in(t, q, mode="full"):
    tok = turn_context.bind(t)
    try:
        _spec, entry = sr.turn_tool(mode)
        return await entry["call"]({"question": q})
    finally:
        turn_context.reset(tok)

res = run(ask_in(turn(), "Áo thun size M màu đen còn hàng không?"))
opens = sr.open_for_staff(bot_id, TG, STAFF)
req1 = opens[0] if opens else {}
check("the tool says what to tell the customer", res.startswith("Sent to the staff (request #") and
      "tell the customer" in res and "ERROR" not in res, res)
check("one open request recorded", len(opens) == 1, opens)
check("it remembers the customer chat, message and question",
      req1.get("customer_chat_id") == CUST1 and req1.get("customer_message_id") == "m-" + CUST1
      and req1.get("question") == "Áo thun size M màu đen còn hàng không?" and req1.get("channel") == "telegram",
      req1)
check("the code has the letter-digit-letter-digit shape", bool(sr.CODE_RE.fullmatch(req1.get("code") or "")),
      req1.get("code"))
msg = sent[-1] if sent else {}
check("the question went to the staff chat through the channel transport",
      msg.get("kenh") == "telegram" and msg.get("chat") == STAFF and msg.get("tk", {}).get("id") == TG
      and msg.get("tk", {}).get("token") == "123:fake", msg)
check("the staff message starts with the request code and holds the question",
      msg.get("text", "").startswith("#" + req1.get("code", "?")) and "Áo thun size M" in msg.get("text", ""), msg)

run(ask_in(turn(chat=CUST2), "Thứ 7 này còn lịch trống lúc 3 giờ chiều không?"))
check("a second customer's request is open too", len(sr.open_for_staff(bot_id, TG, STAFF)) == 2)
codes = {r["code"] for r in sr.open_for_staff(bot_id, TG, STAFF)}
check("two open requests never share a code", len(codes) == 2, codes)
for i in range(sr.OPEN_PER_CHAT_MAX):
    last = run(ask_in(turn(chat=OTHER), f"câu số {i}"))
over = run(ask_in(turn(chat=OTHER), "câu thừa"))
check("a chat cannot pile up more open requests than the cap", over.startswith("ERROR"), over)
check("empty question refused", run(ask_in(turn(), "   ")).startswith("ERROR"))


async def call_after_lowering():
    tok = turn_context.bind(turn())
    try:
        _spec, entry = sr.turn_tool("full")
        chatbot_store.update_bot(bot_id, {"muc_quyen": "auto", "xac_nhan_rui_ro": True})
        return await entry["call"]({"question": "giá sỉ?"})
    finally:
        turn_context.reset(tok)
        chatbot_store.update_bot(bot_id, {"muc_quyen": "full", "xac_nhan_rui_ro": True})

n_before = len(sent)
out = run(call_after_lowering())
check("a call after the bot was lowered is refused and sends nothing", out.startswith("ERROR") and len(sent) == n_before,
      out)

# Personal Zalo: the question is remembered as our own echo before it goes out.
echo = []
import zalo_personal_channel  # noqa: E402
zalo_personal_channel.ghi_da_gui = lambda aid, chat, text: echo.append((aid, chat, text))
zbot, err = chatbot_store.create_bot({"name": "ZShop", "agent_slug": "ban-hang", "brain": VAULT,
                                      "account_ids": ZCONN, "muc_quyen": "full", "xac_nhan_rui_ro": True,
                                      "staff_contact": json.dumps({"account_id": ZCONN, "chat_id": "g-staff-1",
                                                                   "chat_type": "group"})})
check("a personal Zalo bot with a staff group", bool(zbot), err)
zt = turn(chat="zcust-1", account=ZCONN, kenh="zalo_personal", bid=zbot)
check("personal Zalo: offered", offered(zt))
res = run(ask_in(zt, "Đơn 20 thùng giao thứ năm được không?"))
check("personal Zalo: sent to the staff group", sent[-1]["kenh"] == "zalo_personal" and sent[-1]["chat"] == "g-staff-1"
      and sent[-1]["type"] == "group", sent[-1])
check("personal Zalo: remembered as our echo first", any(c == "g-staff-1" for _a, c, _t in echo), echo)

# ============================================================
# 4. The staff answers
# ============================================================
engine_calls = []


async def fake_answer(text, meta, progress, channel="telegram", bot=None, **kw):
    engine_calls.append({"text": text, "meta": dict(meta or {}), "channel": channel, "bot": dict(bot or {})})
    ans = (bot or {}).get("_staff_answer") or {}
    return {"text": "Dạ em kiểm tra rồi ạ: " + str(ans.get("answer") or ""), "files": []}

chatbot_runtime._deps["answer"] = fake_answer
pre = chatbot_runtime._make_precheck_fn(bot_id)


async def staff_says(text, chat=STAFF, account=TG, **more):
    meta = {"chat_id": chat, "chat_type": "private", "account_id": account, "user_id": "u-staff",
            "user_name": "Lan", "message_id": f"s-{len(engine_calls)}-{time.time()}"}
    meta.update(more)
    r = pre(text, meta)
    await asyncio.sleep(0)
    if sr._TASKS:
        await asyncio.gather(*list(sr._TASKS))
    return r

r1 = sr.open_for_staff(bot_id, TG, STAFF)
by_chat = {r["customer_chat_id"]: r for r in r1}
c1, c2 = by_chat[CUST1], by_chat[CUST2]
n_sent = len(sent)
r = run(staff_says(f"#{c1['code']} còn 5 cái size M"))
check("a message with a code is taken, not answered as a customer", r == {}, r)
check("the answer ran a bot turn in the customer's chat", engine_calls and engine_calls[-1]["meta"]["chat_id"] == CUST1
      and engine_calls[-1]["meta"].get("staff_relay") is True, engine_calls[-1:] or "")
check("the bot turn got the staff answer, without the code",
      engine_calls[-1]["bot"].get("_staff_answer", {}).get("answer") == "còn 5 cái size M", engine_calls[-1]["bot"].get("_staff_answer"))
check("the bot's words went to the customer's chat", len(sent) == n_sent + 1 and sent[-1]["chat"] == CUST1
      and "còn 5 cái size M" in sent[-1]["text"], sent[-1:])
check("the request is answered", sr.get(c1["id"])["status"] == "answered")
check("the other request is still open", sr.get(c2["id"])["status"] == "open")

# Quoting the request message, no code typed: the quote names it. Open: c2 plus the OTHER chat's three.
n_sent = len(sent)
r = run(staff_says("còn trống lúc 3 giờ nhé", reply_to_text=f"#{c2['code']} Khách 2 hỏi: Thứ 7 này..."))
check("a reply quoting the request answers that request", r == {} and sr.get(c2["id"])["status"] == "answered"
      and sent[-1]["chat"] == CUST2, sent[-1:])

# Several open, no code, no quote: one note to the staff chat, nothing passed on.
n_sent, n_eng = len(sent), len(engine_calls)
r = run(staff_says("ok để chị xem"))
check("ambiguous: taken, nothing passed on", r == {} and len(engine_calls) == n_eng)
check("ambiguous: one note listing the codes goes to the staff chat", len(sent) == n_sent + 1
      and sent[-1]["chat"] == STAFF and "#" in sent[-1]["text"], sent[-1:])
run(staff_says("vẫn đang xem"))
check("the note is not repeated right away", len(sent) == n_sent + 1)

# Exactly one open: a plain next message counts.
for row in sr.open_for_staff(bot_id, TG, STAFF)[1:]:
    sr.set_failed(row["id"], "test")
only = sr.open_for_staff(bot_id, TG, STAFF)
check("one request left open", len(only) == 1, only)
r = run(staff_says("giá sỉ 120k một cái"))
check("one open: a plain message answers it", r == {} and sr.get(only[0]["id"])["status"] == "answered"
      and sent[-1]["chat"] == OTHER and "120k" in sent[-1]["text"], sent[-1:])

# Other chats are left alone.
run(ask_in(turn(), "Có giao hoả tốc không?"))
open_now = sr.open_for_staff(bot_id, TG, STAFF)
cfg = chatbot_store.get_bot(bot_id)
check("a message in another chat is not a staff answer",
      sr.on_staff_message(cfg, f"#{open_now[0]['code']} có", {"chat_id": CUST2, "account_id": TG}) is None)
check("the staff chat id on another account is not the staff chat",
      sr.on_staff_message(cfg, f"#{open_now[0]['code']} có", {"chat_id": STAFF, "account_id": TG2}) is None)
check("... and the request stays open", sr.get(open_now[0]["id"])["status"] == "open")
check("a bare photo placeholder is not an answer",
      sr.on_staff_message(cfg, "[Khách gửi một ảnh, không kèm lời nhắn]", {"chat_id": STAFF, "account_id": TG}) is None)

# The relay prompt carries the answer, in English, last.
p = chatbot_runtime.build_bot_prompt(dict(cfg, _staff_answer={"question": "Có giao hoả tốc không?", "answer": "Có, 30k"}))
check("the bot prompt carries the staff answer block", "STAFF ANSWER TO PASS ON" in p and "Có, 30k" in p
      and p.rstrip().endswith("or this note."))
check("no em or en dash in the new texts", not any(ch in (p + sr.TOOL_DESCRIPTION + sr.staff_message("A2B3", "x", "y"))
                                                    for ch in (chr(0x2014), chr(0x2013))))

# Telegram hands the quoted text to the bot.
check("Telegram meta carries the quoted text",
      telegram_bot.TelegramBot._reply_to_text({"reply_to_message": {"text": "#K7Q2 Khách hỏi"}}) == "#K7Q2 Khách hỏi")

# ============================================================
# 5. Expiry
# ============================================================
old_req = sr.create(bot_id=bot_id, channel="telegram", account_id=TG, customer_chat_id="700000077",
                    customer_chat_type="private", customer_user_id="", customer_name="", customer_message_id="",
                    staff_chat_id=STAFF, staff_chat_type="private", question="cũ",
                    now=time.time() - sr.TTL_S - 60)
n_sent = len(sent)
n = sr.expire_due()
check("a request older than 24 h expires", n >= 1 and sr.get(old_req["id"])["status"] == "expired", n)
check("expiry sends nothing", len(sent) == n_sent)
check("an expired request is never answered", all(r["id"] != old_req["id"] for r in sr.open_for_staff(bot_id, TG, STAFF)))

# Deleting the bot forgets its requests.
chatbot_store.delete_bot(bot_id)
check("deleting the bot deletes its requests", sr.get(old_req["id"]) is None and sr.get(c1["id"]) is None)

if fails:
    print(f"\n{len(fails)} FAIL")
    sys.exit(1)
print("\nall ok")
