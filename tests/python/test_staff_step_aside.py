"""The bot steps aside for a while after a staff member answers from the channel's own app (issue #1693).

    python tests/run.py staff_step_aside      (no network)

A message a staff member writes in the Zalo OA app or the Page inbox was recorded, but the chat stayed with the bot, so
the customer's next message was answered by the bot over the staff member. Now the bot stays out of that chat for its
"step aside after you type" time (`nhuong_tay_phut`), counted from the staff member's last message, and answers again
by itself afterwards. The chat stays in "ai" mode. Off unless the owner sets a number: blank or 0 = never (owner,
2026-11-22).

What the channel sends by itself (a welcome message, an automatic reply seconds after the customer's message) must not
count, or the bot would go quiet for every new customer.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-staff-aside-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_runtime as rt  # noqa: E402
import chatbot_store  # noqa: E402
import conversations  # noqa: E402

fails = []


def check(name, cond, more=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(more)[:300] + "]") if more and not cond else ""))
    if not cond:
        fails.append(name)


def run(coro):
    return asyncio.run(coro)


BRAIN = Path(tempfile.mkdtemp(prefix="javis-staff-aside-brain-"))
ENGINE_CALLS = []


async def engine(text, meta=None, progress=None, channel="telegram", bot=None):
    ENGINE_CALLS.append(text)
    return {"text": "Dạ em chào chị ạ", "files": []}


rt.wire(answer=engine, brain_root=lambda b: str(BRAIN), read_agent=lambda b, s: ({"name": "Hoa"}, ""))
bot_id, _err = chatbot_store.create_bot({"name": "Shop bot", "agent_slug": "cskh", "brain": "b", "token": "1:staff",
                                         "nhuong_tay_phut": "10"})
answer = rt._make_answer_fn(bot_id)
CFG = chatbot_store.get_bot(bot_id)
T0 = time.time()


def meta_of(chat, **more):
    return dict({"chat_id": chat, "chat_type": "private", "user_name": "Lan", "user_id": chat}, **more)


def staff(chat, text="Em gửi chị báo giá ạ", mid="", ts=None, files=None):
    return run(rt.record_staff_message(bot_id, {
        "chat_id": chat, "account_id": "", "message_id": mid, "text": text, "platform": "zalo_oa",
        "files": files or [], "ts": T0 if ts is None else ts}))


def customer_row(chat, text, at, mid):
    ev = rt._bot_event(CFG, meta_of(chat), sender_type="customer", sender_name="Lan", text=text,
                         external_message_id=mid)
    ev["created_at"] = at
    return conversations.ghi_su_kien(ev)


def turn(chat, text, **more):
    before = len(ENGINE_CALLS)
    out = run(answer(text, meta_of(chat, **more)))
    return out, len(ENGINE_CALLS) - before


def mode_of(chat):
    aid, kenh = rt._tai_khoan_cua(CFG, meta_of(chat))
    return conversations.che_do(kenh, aid, chat)


# ============================================================
# 1. The step-aside time comes from the bot's own setting
# ============================================================
check("blank setting: the bot never steps aside for staff (owner's default)",
      rt.staff_yield_seconds({}) == 0 and rt.staff_yield_seconds({"nhuong_tay_phut": ""}) == 0
      and rt.staff_yield_seconds({"nhuong_tay_phut": None}) == 0)
check("a number of minutes is used", rt.staff_yield_seconds({"nhuong_tay_phut": 3}) == 180
      and rt.staff_yield_seconds({"nhuong_tay_phut": "5"}) == 300)
check("0 = never step aside", rt.staff_yield_seconds({"nhuong_tay_phut": 0}) == 0)

# ============================================================
# 2. A staff member answers: the bot stays out, the chat stays "ai", the customer's message is kept
# ============================================================
A = "chat-a"
customer_row(A, "Cho em xin báo giá", T0 - 120, "a1")
n = staff(A, mid="oa-1")
check("the staff message is recorded", n == 1, n)
out, calls = turn(A, "Còn hàng không shop?", received_at=T0 + 30)
check("the bot stays quiet for the customer's next message", out.get("im_lang") is True and not out.get("text") and calls == 0,
      (out, calls))
rows = conversations.tin_gan_day(*reversed(rt._tai_khoan_cua(CFG, meta_of(A))), A, 10)
check("the customer's message is still in the inbox", any(r["text"] == "Còn hàng không shop?" for r in rows), rows)
check("the chat stays in ai mode: nothing to hand back", mode_of(A) == "ai", mode_of(A))

# The window passed: the bot answers again by itself.
rt._STAFF_AT[rt._staff_key(CFG, meta_of(A))] = time.time() - 601
out, calls = turn(A, "Shop ơi?")
check("after the step-aside time the bot answers again", calls == 1 and out.get("text"), (out, calls))
check("and the mark is gone", rt._staff_key(CFG, meta_of(A)) not in rt._STAFF_AT)

# The same staff message delivered twice does not start the time again.
again = staff(A, mid="oa-1", ts=time.time())
check("a repeated message id is not recorded and does not step aside again",
      again == 0 and rt._staff_key(CFG, meta_of(A)) not in rt._STAFF_AT, again)

# ============================================================
# 3. What the channel sends by itself is not a staff member
# ============================================================
B = "chat-b"
n = staff(B, text="Cảm ơn bạn đã quan tâm OA!", mid="oa-w")
out, calls = turn(B, "Chào shop", received_at=T0 + 60)
check("a welcome message (the customer never wrote) is recorded but the bot still answers",
      n == 1 and calls == 1 and out.get("text"), (n, out, calls))

C = "chat-c"
customer_row(C, "user_submit_info", T0 - 3, "c1")
n = staff(C, text="Hãy bấm QUAN TÂM để nhận tin", mid="oa-auto")
out, calls = turn(C, "Shop có ship không?", received_at=T0 + 60)
check("an automatic reply 3 seconds after the customer's message does not silence the bot",
      n == 1 and calls == 1, (n, out, calls))

# The automatic reply can be recorded BEFORE the customer's own turn reaches the runtime (the turn waits for a name
# lookup or a download). The customer's message arrived within seconds of it: still automatic, and forgotten.
D = "chat-d"
customer_row(D, "Hôm qua em có hỏi", T0 - 86400, "d1")
n = staff(D, text="Shop sẽ trả lời bạn sớm nhất", mid="oa-auto2", ts=T0)
check("the automatic reply was taken for a person at first", rt._staff_key(CFG, meta_of(D)) in rt._STAFF_AT)
out, calls = turn(D, "Cho em hỏi giá", received_at=T0 - 2)
check("the message that triggered it is answered", calls == 1 and out.get("text"), (out, calls))
out, calls = turn(D, "Em cần gấp ạ", received_at=T0 + 40)
check("and so is the next one: the mark was dropped", calls == 1, (out, calls))

E = "chat-e"
customer_row(E, "Cho em hỏi", T0 - 90, "e1")
n = staff(E, text="Dạ chị cần gì ạ?", mid="oa-p")
out, calls = turn(E, "Em muốn đặt 2 chai", received_at=T0 + 20)
check("a person answering 90 seconds later does make the bot step aside", n == 1 and calls == 0 and out.get("im_lang"),
      (n, out, calls))

# ============================================================
# 4. Events with nothing in them, bots set to 0, groups
# ============================================================
F = "chat-f"
customer_row(F, "Alo", T0 - 90, "f1")
check("an empty event is not recorded and does not step aside",
      staff(F, text="", mid="oa-empty") == 0 and rt._staff_key(CFG, meta_of(F)) not in rt._STAFF_AT)

G = "chat-g"
customer_row(G, "Alo", T0 - 90, "g1")
staff(G, mid="oa-g")
real_get = chatbot_store.get_bot
chatbot_store.get_bot = lambda bid: dict(real_get(bid) or {}, nhuong_tay_phut=0) if bid == bot_id else real_get(bid)
try:
    out, calls = turn(G, "Còn hàng không?", received_at=T0 + 30)
finally:
    chatbot_store.get_bot = real_get
check("a bot set to 0 minutes never steps aside", calls == 1 and out.get("text"), (out, calls))

H = "chat-h"
customer_row(H, "Alo", T0 - 90, "h1")
staff(H, mid="oa-h")
chatbot_store.get_bot = lambda bid: dict(real_get(bid) or {}, nhuong_tay_phut=None) if bid == bot_id else real_get(bid)
try:
    out, calls = turn(H, "Còn hàng không?", received_at=T0 + 30)
finally:
    chatbot_store.get_bot = real_get
check("a bot with the setting left blank never steps aside either (the default)", calls == 1 and out.get("text"),
      (out, calls))

check("a group chat is never held back by a staff mark",
      rt.staff_yielding(CFG, dict(meta_of(E), chat_type="group"), T0 + 20) is False
      and rt.staff_yielding(CFG, meta_of(E, received_at=T0 + 20), T0 + 20) is True)

# The store of marks cannot grow without end.
for i in range(rt._STAFF_AT_MAX + 50):
    rt.note_staff_message(CFG, meta_of(f"many-{i}"), T0 + i, T0 - 100)
check("old marks are dropped when there are too many", len(rt._STAFF_AT) <= rt._STAFF_AT_MAX, len(rt._STAFF_AT))

print()
if fails:
    print(f"{len(fails)} FAILED:")
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("OK - test_staff_step_aside: all pass")
