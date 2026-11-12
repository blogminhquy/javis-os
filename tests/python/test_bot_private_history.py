"""A bot remembers a private chat: 30 messages, and the history survives a server restart.

    python tests/run.py bot_private_history      (NO network)

The owner, 12/11/2026: the Zalo bot answers customers on far too little context. Reading the code showed why:

  - a bot kept only the last 20 messages (10 exchanges) of a private chat, cut hard;
  - that history lived in RAM only. Every server restart (each update is one) emptied it, and unlike the owner's
    Telegram chat nothing read it back, so a returning customer was met as a stranger.

Now the ceiling is 30 messages (with a character ceiling for chats that are not short), and the first turn after a
restart reads the private chat back from the inbox, which keeps every message of it, the owner's hand-typed replies
included.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-bot-history-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_runtime  # noqa: E402
import conversations  # noqa: E402

fails = []


def check(name, cond, more=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(more) + "]") if more and not cond else ""))
    if not cond:
        fails.append(name)


NOW = time.time()
BOT = {"id": "bot_h", "name": "Shop bot", "brain": "brain-bot", "channel": "zalo",
       "agent": {"brain": "brain", "slug": "sales"}}
_seq = [0]


def record(chat, sender, text, mid="", chat_type="private"):
    _seq[0] += 1
    return conversations.ghi_su_kien({
        "channel": "zalo", "account_id": "bot_h", "account_name": "Shop bot", "bot_id": "bot_h",
        "external_chat_id": chat, "chat_type": chat_type, "chat_title": "",
        "sender_type": sender, "sender_id": "u1" if sender == "customer" else "", "sender_name": "An",
        "text": text, "external_message_id": mid or f"{chat}-{_seq[0]}", "created_at": NOW - 5000 + _seq[0]})


def meta(chat, mid="", chat_type="private"):
    return {"chat_id": chat, "chat_type": chat_type, "message_id": mid, "user_id": "u1", "user_name": "An"}


# ============================================================
# 1. private_history: what the inbox hands back
# ============================================================
record("c1", "customer", "Shop còn áo size L không?")
record("c1", "ai", "Dạ còn ạ, áo size L màu đen và trắng.")
record("c1", "customer", "Lấy cho mình 2 áo đen")
record("c1", "human", "Shop gửi anh mã giảm 10% nhé")       # the owner answered by hand in the inbox
record("c1", "customer", "Bao giờ giao hàng?", mid="m-now")  # the message being answered

h = chatbot_runtime.private_history(BOT, meta("c1", "m-now"), 100)
check("history is read back from the inbox", len(h) == 4, h)
check("customer -> user, bot -> assistant, in order",
      [x["role"] for x in h] == ["user", "assistant", "user", "assistant"], [x["role"] for x in h])
check("what the owner typed by hand is in it", "mã giảm 10%" in h[3]["content"], h)
check("the message being answered is left out", all("Bao giờ giao hàng" not in x["content"] for x in h))

h_noid = chatbot_runtime.private_history(BOT, meta("c1"), 100)
check("without a message id the last customer message is the one left out", h_noid == h, h_noid)

# Neighbours of one role are joined, and the list opens with a customer message.
record("c2", "ai", "Chào anh, shop có thể giúp gì ạ?")       # the bot spoke first: cannot open the history
record("c2", "customer", "Cho hỏi")
record("c2", "customer", "giá áo khoác")
record("c2", "ai", "Dạ 350.000đ ạ.")
record("c2", "customer", "ok", mid="m2")
h2 = chatbot_runtime.private_history(BOT, meta("c2", "m2"), 100)
check("history opens with a customer message", h2 and h2[0]["role"] == "user", h2)
check("two customer messages in a row become one turn",
      len(h2) == 2 and h2[0]["content"] == "Cho hỏi\ngiá áo khoác", h2)

# The limit counts stored messages, newest kept.
for i in range(30):
    record("c3", "customer", f"hỏi {i}")
    record("c3", "ai", f"đáp {i}")
record("c3", "customer", "tin đang hỏi", mid="m3")
h3 = chatbot_runtime.private_history(BOT, meta("c3", "m3"), 10)
check("the limit is respected", len(h3) == 10, len(h3))
check("the newest messages are the ones kept", h3[-1] == {"role": "assistant", "content": "đáp 29"}, h3[-1])
check("limit 0 gives nothing", chatbot_runtime.private_history(BOT, meta("c3", "m3"), 0) == [])

# Groups get their context from `ngu_canh_nhom` on every turn: no second copy here.
record("g1", "customer", "tin trong nhóm", chat_type="group")
record("g1", "customer", "@Bot giá?", mid="mg", chat_type="group")
check("a group chat gets no private history",
      chatbot_runtime.private_history(BOT, meta("g1", "mg", "group"), 100) == [])
check("an unknown chat gives an empty history", chatbot_runtime.private_history(BOT, meta("nobody"), 100) == [])
check("a broken call never raises", chatbot_runtime.private_history(None, None, 100) == [])

# Hidden characters (a zero-width joiner hiding an instruction) are stripped as on the live path.
record("c4", "customer", "xin​ chào")
record("c4", "customer", "hỏi tiếp", mid="m4")
h4 = chatbot_runtime.private_history(BOT, meta("c4", "m4"), 100)
check("hidden characters are stripped", h4 == [{"role": "user", "content": "xin chào"}], h4)

# ============================================================
# 2. A real bot turn after a restart sends that history to the model
# ============================================================
chatbot_runtime.wire(answer=None, brain_root=lambda b: "/tmp/not-used",
                     read_agent=lambda brain, slug: ({"name": "Sales", "role": "Sells clothes."}, "Be brief."))
import main  # noqa: E402

sent = []


def fake_stream(prov, key, model, messages, reasoning="off"):
    sent.append([dict(m) for m in messages])

    async def gen():
        yield {"type": "text", "content": "Dạ mai giao ạ."}
        yield {"type": "usage", "input": 10, "output": 5}
    return gen()


main._api_stream = fake_stream


def turn(sess, chat, text, mid="", level=""):
    bot = {**BOT, "_tai_lieu": {"co": False, "khoi": "", "nguon": []}}
    if level:
        bot["muc_quyen"] = level
    return asyncio.run(main._tg_answer_engine(
        text, meta(chat, mid), None, chat_id=chat, sess=sess, brain="brain-bot", mcfg={},
        prov="openrouter", kind="api", api_key="k", api_model="m", bot=bot))


check("the ceiling is 30 messages", main.BOT_HISTORY_MAX_MESSAGES == 30, main.BOT_HISTORY_MAX_MESSAGES)

# A fresh RAM session is what a restart leaves behind.
sess = {"last": None, "sent": set()}
out = turn(sess, "c1", "Bao giờ giao hàng?", "m-now")
check("the turn answers", isinstance(out, dict) and out.get("text"), out)
payload = sent[-1]
texts = [m["content"] for m in payload if m["role"] != "system"]
check("after a restart the model gets the earlier messages of the chat",
      any("size L không" in t for t in texts) and any("mã giảm 10%" in t for t in texts), texts)
check("the question is sent once, last", texts[-1] == "Bao giờ giao hàng?" and texts.count("Bao giờ giao hàng?") == 1,
      texts)
check("the first message after the system prompt is the customer's", payload[1]["role"] == "user", payload[1])

# The inbox is read ONCE: later turns run on the RAM history, which now holds this turn too.
before = len(sess["bot"])
turn(sess, "c1", "Cảm ơn shop", "m-next")
check("the next turn builds on RAM, not on a second read", len(sess["bot"]) == before + 2, (before, len(sess["bot"])))

# The draft undo (inbox "Suggest a reply") must not leave an EMPTY history where there was none: the next real
# turn would then start blank instead of reading the inbox.
key = "bot:bot_h:c2"
sid, keep = main._manual_session_probe(key)
check("nothing in RAM yet for this chat", keep == 0, keep)
turn(main._tg_session(key), "c2", "ok", "m2")
check("the draft turn loaded the history", len(main._tg_session(key)["bot"]) > 2)
main._manual_session_undo(key, keep)
check("undo of a draft goes back to 'not loaded'", main._tg_session(key).get("bot") is None,
      main._tg_session(key).get("bot"))
sid2, keep2 = main._manual_session_probe("bot:bot_h:c1x")
main._tg_session("bot:bot_h:c1x")["bot"] = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
main._manual_session_undo("bot:bot_h:c1x", 2)
check("undo keeps a history that was there before the draft", len(main._tg_session("bot:bot_h:c1x")["bot"]) == 2)

# ============================================================
# 3. Trimming: the message ceiling, a character ceiling, never an assistant first
# ============================================================
hist = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(131)]
main._trim_bot_history(hist)
check("more messages than the ceiling are cut to it", len(hist) <= main.BOT_HISTORY_MAX_MESSAGES, len(hist))
check("the newest message stays", hist[-1]["content"] == "m130", hist[-1])
check("the cut never leaves an assistant message first", hist[0]["role"] == "user", hist[0])

big = "x" * 8000
hist = [{"role": "user" if i % 2 == 0 else "assistant", "content": big} for i in range(40)]
main._trim_bot_history(hist)
total = sum(len(m["content"]) for m in hist)
check("very long messages are cut by characters, oldest first", total <= main.BOT_HISTORY_MAX_CHARS, total)
check("a normal chat of short messages is NOT cut by the character ceiling",
      main.BOT_HISTORY_MAX_MESSAGES * 400 <= main.BOT_HISTORY_MAX_CHARS)
one = [{"role": "user", "content": "y" * (main.BOT_HISTORY_MAX_CHARS + 5)}]
main._trim_bot_history(one)
check("the message being answered is never dropped, however long", len(one) == 1)

if fails:
    print(f"\nFAIL {len(fails)}: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_bot_private_history: all pass")
