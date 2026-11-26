"""A bot remembers the whole private chat, and nothing reaches a chat twice (issues #1839, #1846, #1851).

    python tests/run.py bot_inbox_history_send_once      (NO network: engines, tools and channels are faked)

Issue #1839, confirmed on main: the bot answered as if it knew nothing.
  - Staff and Page/OA messages are stored as `human`; the history builder dropped every LEADING non-customer message,
    so a chat the staff (or the Page itself) opened read as empty.
  - The history was read from the inbox once, on the first turn after a restart, then lived in RAM: what the staff,
    the owner or the Page wrote after that never reached the bot.
Now the inbox is the source of truth on every turn (`chatbot_runtime.sync_private_history`), and a bot at full
access, which runs on the owner's engine thread, gets what that thread missed in front of its question.

Issues #1846 (idea from PR #1846 by tunganh0990) and #1851: a model sends a photo or its answer to the chat with a
tool, then the end of the turn sends the same photo or text again. PR #1846 matched tool NAMES; `delivery_ledger`
records what any tool call or send path delivered to a chat, by what its arguments name, and the end of the turn
(owner turns in `main._tg_answer`, bot turns in `chatbot_runtime`) leaves out what already arrived.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-bot-send-once-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import conversations  # noqa: E402
import delivery_ledger  # noqa: E402

fails = []


def check(name, cond, more=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(more) + "]") if more and not cond else ""))
    if not cond:
        fails.append(name)


NOW = time.time()
BOT = {"id": "bot_s", "name": "Shop bot", "brain": "brain-bot", "channel": "zalo",
       "agent": {"brain": "brain", "slug": "sales"}}
_seq = [0]


def record(chat, sender, text, mid="", chat_type="private", metadata=None):
    _seq[0] += 1
    return conversations.ghi_su_kien({
        "channel": "zalo", "account_id": "bot_s", "account_name": "Shop bot", "bot_id": "bot_s",
        "external_chat_id": chat, "chat_type": chat_type, "chat_title": "",
        "sender_type": sender, "sender_id": "u1" if sender == "customer" else "", "sender_name": "An",
        "text": text, "external_message_id": mid or f"{chat}-{_seq[0]}", "created_at": NOW - 5000 + _seq[0],
        "metadata": metadata or {}})


def meta(chat, mid="", chat_type="private"):
    return {"chat_id": chat, "chat_type": chat_type, "message_id": mid, "user_id": "u1", "user_name": "An"}


BRAIN = Path(tempfile.mkdtemp(prefix="brain-send-once-"))
chatbot_runtime.wire(answer=None, brain_root=lambda b: str(BRAIN),
                     read_agent=lambda brain, slug: ({"name": "Sales", "role": "Sells clothes."}, "Be brief."))
import main  # noqa: E402

SENT = []
REPLY = {"v": "Dạ mai giao ạ."}


def fake_stream(prov, key, model, messages, reasoning="off"):
    SENT.append([dict(m) for m in messages])

    async def gen():
        if REPLY["v"]:
            yield {"type": "text", "content": REPLY["v"]}
        yield {"type": "usage", "input": 10, "output": 5}
    return gen()


main._api_stream = fake_stream


def turn(sess, chat, text, mid):
    """One bot turn as chatbot_runtime runs it: the customer's message is in the inbox first, the reply after."""
    bot = {**BOT, "_tai_lieu": {"co": False, "khoi": "", "nguon": []}}
    out = asyncio.run(main._tg_answer_engine(
        text, meta(chat, mid), None, chat_id=chat, sess=sess, brain="brain-bot", mcfg={},
        prov="openrouter", kind="api", api_key="k", api_model="m", bot=bot))
    if isinstance(out, dict) and out.get("text"):
        record(chat, "ai", out["text"])
    return out


def sent_texts():
    return [m["content"] for m in SENT[-1] if m["role"] != "system"]


def in_order(text, *parts) -> bool:
    at = [text.find(x) for x in parts]
    return all(i >= 0 for i in at) and at == sorted(at)


def alternates(payload) -> bool:
    roles = [m["role"] for m in payload if m["role"] != "system"]
    return bool(roles) and roles[0] == "user" and roles[-1] == "user" and all(a != b for a, b in zip(roles, roles[1:]))


# ============================================================
# A1. A chat the staff (or the Page) opened is not empty to the bot
# ============================================================
record("s1", "human", "Chào chị, em là Lan bên shop, chị cần tư vấn mẫu nào ạ?")
record("s1", "human", "Báo giá áo khoác lông vũ: 350.000đ")
record("s1", "customer", "Giá đó còn áp dụng không em?", mid="s1-a")
sess1 = {"last": None, "sent": set()}
out = turn(sess1, "s1", "Giá đó còn áp dụng không em?", "s1-a")
check("A1 the turn answers", isinstance(out, dict) and out.get("text"), out)
joined = "\n".join(sent_texts())
check("A1 what the staff wrote before the customer's first message reaches the model",
      "350.000đ" in joined and "em là Lan" in joined, sent_texts())
check("A1 the history still opens with a customer (user) message and never repeats a role", alternates(SENT[-1]),
      [m["role"] for m in SENT[-1]])
check("A1 the question is the last thing the model reads", sent_texts()[-1].endswith("Giá đó còn áp dụng không em?"),
      sent_texts()[-1:])
h = chatbot_runtime.private_history(BOT, meta("s1", "s1-a"), 30)
check("A1 private_history keeps the staff's opening messages as a user note",
      len(h) == 1 and h[0]["role"] == "user" and "350.000đ" in h[0]["content"], h)

# ============================================================
# A2. A staff message written AFTER the first turn reaches the bot on the next one
# ============================================================
record("s2", "customer", "Shop còn áo size L không?", mid="s2-a")
sess2 = {"last": None, "sent": set()}
turn(sess2, "s2", "Shop còn áo size L không?", "s2-a")
record("s2", "human", "Em gửi chị mã giảm 10% nhé: GIAM10")        # typed in the OA app / Page inbox / Javis inbox
record("s2", "customer", "Mã đó dùng thế nào?", mid="s2-b")
turn(sess2, "s2", "Mã đó dùng thế nào?", "s2-b")
texts = sent_texts()
joined = "\n".join(texts)
check("A2 the staff message written after the first turn reaches the bot", joined.count("GIAM10") == 1, texts)
check("A2 the bot's own reply is not repeated from the inbox", joined.count("Dạ mai giao ạ.") == 1, texts)
check("A2 roles still alternate", alternates(SENT[-1]), [m["role"] for m in SENT[-1]])
check("A2 the staff message sits after the bot's reply and before the question",
      in_order(joined, "Dạ mai giao ạ.", "GIAM10", "Mã đó dùng thế nào?"), texts)

# A chat taken over, then handed back: what the customer and the staff said meanwhile, in order.
record("s2", "customer", "Còn màu đỏ không?")
record("s2", "human", "Dạ còn màu đỏ ạ")
record("s2", "customer", "Lấy 1 cái màu đỏ", mid="s2-c")
turn(sess2, "s2", "Lấy 1 cái màu đỏ", "s2-c")
joined = "\n".join(sent_texts())
check("A2 messages written while the chat was taken over reach the bot, in order",
      in_order(joined, "Còn màu đỏ không?", "Dạ còn màu đỏ ạ", "Lấy 1 cái màu đỏ"), sent_texts())

# A draft the owner rewrote before sending is stored as the bot's message but was never in RAM: it reaches the bot.
record("s2", "ai", "Chủ shop sửa: giao trong 2 giờ, miễn phí ship")
record("s2", "customer", "Ok shop", mid="s2-d")
turn(sess2, "s2", "Ok shop", "s2-d")
joined = "\n".join(sent_texts())
check("A2 a stored bot message the RAM history never held (a rewritten draft) reaches the bot",
      "miễn phí ship" in joined, sent_texts())
check("A2 nothing was added twice over four turns", joined.count("GIAM10") == 1 and joined.count("Dạ còn màu đỏ ạ") == 1,
      sent_texts())

# What the bot sent itself with a tool during its turn comes back as a `human` row marked `via: tool` (an
# `inbox_reply`, a Zalo send echo): the bot already holds those words and does not get them twice.
REPLY["v"] = "Dạ em gửi chị mã vận đơn VD123 ạ"
record("s2", "customer", "Mã vận đơn đâu em?", mid="s2-d2")
turn(sess2, "s2", "Mã vận đơn đâu em?", "s2-d2")
REPLY["v"] = "Dạ mai giao ạ."
record("s2", "human", "Dạ em gửi chị mã vận đơn VD123 ạ", metadata={"tu_javis": True, "via": "tool"})
record("s2", "customer", "Cảm ơn shop", mid="s2-e")
turn(sess2, "s2", "Cảm ơn shop", "s2-e")
check("A2 what the bot sent itself with a tool is not added a second time",
      "\n".join(sent_texts()).count("VD123") == 1, sent_texts())

# ============================================================
# A3. A burst of messages joined into one turn (personal Zalo) is not sent twice
# ============================================================
record("s3", "customer", "Thầy ơi")
record("s3", "customer", "cho em hỏi")
record("s3", "customer", "lớp 9 còn chỗ không ạ", mid="s3-c")
sess3 = {"last": None, "sent": set()}
turn(sess3, "s3", "Thầy ơi\ncho em hỏi\nlớp 9 còn chỗ không ạ", "s3-c")
joined = "\n".join(sent_texts())
check("A3 each message of the burst reaches the model once", joined.count("Thầy ơi") == 1, sent_texts())

# ============================================================
# A4. A failed turn: its question is not lost, and two customer messages never go in a row
# ============================================================
record("s4", "customer", "Hỏi A", mid="s4-a")
sess4 = {"last": None, "sent": set()}
turn(sess4, "s4", "Hỏi A", "s4-a")
record("s4", "customer", "Hỏi B", mid="s4-b")
REPLY["v"] = ""
failed = turn(sess4, "s4", "Hỏi B", "s4-b")
REPLY["v"] = "Dạ mai giao ạ."
check("A4 (setup) the turn failed", isinstance(failed, str), failed)
check("A4 a failed turn hands the history back to the inbox", sess4.get("bot") is None, sess4.get("bot"))
record("s4", "customer", "Hỏi C", mid="s4-c")
turn(sess4, "s4", "Hỏi C", "s4-c")
texts = sent_texts()
check("A4 the question of the failed turn reaches the next turn", any("Hỏi B" in t for t in texts), texts)
check("A4 unanswered and new question go as one user message", alternates(SENT[-1]) and texts[-1].endswith("Hỏi C"),
      [m["role"] for m in SENT[-1]])

# ============================================================
# A5. Groups keep their RAM history (the group context brings the inbox every turn)
# ============================================================
gsess = {"bot": [{"role": "user", "content": "x"}, {"role": "assistant", "content": "y"}]}
q = chatbot_runtime.sync_private_history(gsess, BOT, meta("g1", "m", "group"), "hỏi nhóm", 30)
check("A5 a group's RAM history and question are left alone",
      q == "hỏi nhóm" and len(gsess["bot"]) == 2 and chatbot_runtime.HISTORY_MARK not in gsess, gsess)

# ============================================================
# A6. A bot at full access: what its engine thread missed rides in front of the question
# ============================================================
record("f1", "customer", "Có áo len không?")
record("f1", "ai", "Dạ có ạ, giá 200k.")
record("f1", "human", "Em gửi thêm: hôm nay giảm 20% (mã LEN20)")
record("f1", "customer", "Mua 2 cái", mid="f1-a")
fsess = {}
q = chatbot_runtime.full_turn_catch_up(fsess, BOT, meta("f1", "f1-a"), "Mua 2 cái", 30)
check("A6 the first full turn hears the staff message after the bot's last reply", "LEN20" in q, q)
check("A6 ...but not what its thread already holds", "Có áo len không?" not in q and "200k" not in q, q)
check("A6 the question stays last", q.endswith("Mua 2 cái"), q)
record("f1", "human", "Ship trong 2 giờ")
record("f1", "customer", "Ok", mid="f1-b")
q = chatbot_runtime.full_turn_catch_up(fsess, BOT, meta("f1", "f1-b"), "Ok", 30)
check("A6 the next full turn hears only what is new", "Ship trong 2 giờ" in q and "LEN20" not in q, q)
q = chatbot_runtime.full_turn_catch_up(fsess, BOT, meta("f1", "f1-x"), "Hỏi tiếp", 30)
check("A6 nothing new: the question as it is", q == "Hỏi tiếp", q)
check("A6 the stored question still counts as this turn's question in the engine bootstrap",
      main._is_turn_question("Mua 2 cái", "[Said in this private chat ...]\nMua 2 cái")
      and not main._is_turn_question("", "x"))

# ============================================================
# B1. delivery_ledger: by what the arguments name, never by the tool's name
# ============================================================
IMG = BRAIN / "attachments" / "ao-do.png"
IMG.parent.mkdir(parents=True, exist_ok=True)
IMG.write_bytes(b"\x89PNG\r\n\x1a\n" + b"red coat" * 64)
COPY = BRAIN / "tmp-copy.png"
shutil.copy(IMG, COPY)
OTHER = BRAIN / "attachments" / "ao-xanh.png"
OTHER.write_bytes(b"\x89PNG\r\n\x1a\n" + b"blue coat" * 64)

t0 = time.time()
delivery_ledger.note_call({"threadId": "T1", "threadType": 0, "paths": [str(IMG)], "caption": "Áo đỏ"},
                          '{"success": true, "messageId": "1"}')
said, left = delivery_ledger.trim_reply("T1", t0, "", [str(IMG), str(OTHER)])
check("B1 a file a tool sent to the chat is left out, another one stays", left == [str(OTHER)], left)
said, left = delivery_ledger.trim_reply("T1", t0, "", [{"path": str(COPY), "caption": "x"}])
check("B1 the same bytes under another name are left out too (dicts keep their shape)", left == [], left)
said, left = delivery_ledger.trim_reply("T2", t0, "", [str(IMG)])
check("B1 another chat still gets the file", left == [str(IMG)], left)
said, left = delivery_ledger.trim_reply("T1", time.time() + 1, "", [str(IMG)])
check("B1 what was sent before the turn started does not count", left == [str(IMG)], left)
delivery_ledger.note_call({"threadId": "T3", "paths": [str(IMG)]}, "ERROR: Zalo refused the image")
check("B1 a send that failed is not a delivery", delivery_ledger.trim_reply("T3", t0, "", [str(IMG)])[1] == [str(IMG)])
delivery_ledger.note_call({"threadId": "T4", "success": False, "paths": [str(IMG)]}, '{"success": false}')
check("B1 success: false is not a delivery", delivery_ledger.trim_reply("T4", t0, "", [str(IMG)])[1] == [str(IMG)])

delivery_ledger.note_call({"to": "T1", "message": "**Dạ** áo đỏ còn size L ạ"}, "sent")
check("B1 the same text, Markdown and spaces aside, counts as sent",
      delivery_ledger.trim_reply("T1", t0, "Dạ  áo đỏ còn size L ạ", [])[0])
check("B1 a different text is sent", not delivery_ledger.trim_reply("T1", t0, "Dạ áo đỏ hết size L rồi ạ", [])[0])
check("B1 the chat id with Javis's prefix matches the raw id a tool names",
      delivery_ledger.trim_reply("zalo:T1", t0, "dạ áo đỏ còn size l ạ", [])[0])

# ============================================================
# B2. Every send path records: a plugin tool of any name, a hub tool of any name, the inbox's channel registry
# ============================================================
import plugins_host  # noqa: E402

HANDLED = []


async def post_photo(args, ctx):
    HANDLED.append(dict(args))
    return {"ok": True}


t0 = time.time()
acme = plugins_host._make_call({"name": "acme_chat_post", "handler": post_photo, "min_mode": "full"}, None, "full")
asyncio.run(acme({"conversation": "P1", "attachment": str(IMG), "body": "Mẫu áo đỏ đây ạ"}))
said, left = delivery_ledger.trim_reply("P1", t0, "Mẫu áo đỏ đây ạ", [str(IMG)])
check("B2 a plugin tool nobody named delivers: its file and text are not sent again", said and left == [], (said, left))
peek = plugins_host._make_call({"name": "acme_chat_peek", "handler": post_photo, "min_mode": "readonly"}, None, "full")
asyncio.run(peek({"conversation": "P2", "attachment": str(IMG)}))
check("B2 a read-only plugin tool delivers nothing", delivery_ledger.trim_reply("P2", t0, "", [str(IMG)])[1] == [str(IMG)])

import mcp_catalog  # noqa: E402
import mcp_client  # noqa: E402
import mcp_hub  # noqa: E402

CLS = {"v": "write"}


async def fake_route(route, fn, args):
    return '{"ok": true}'


mcp_client.call_route = fake_route
mcp_catalog.get = lambda cid: {}
mcp_catalog.classify = lambda c, t, a: CLS["v"]
mcp_catalog.allowed = lambda *a, **k: (True, "")
mcp_hub._audit_append = lambda rec: None
hub_tool = mcp_hub._guard({"conn": {"id": "c1", "connector_id": "x", "label": "Shop"}, "tool": "push_media",
                           "spec": {}}, "shop__push_media", "full")
asyncio.run(hub_tool({"recipient": "H1", "file": str(IMG)}))
check("B2 a hub tool that acts outside delivers", delivery_ledger.trim_reply("H1", t0, "", [str(IMG)])[1] == [])
CLS["v"] = "read"
asyncio.run(hub_tool({"recipient": "H2", "file": str(IMG)}))
check("B2 a hub read delivers nothing", delivery_ledger.trim_reply("H2", t0, "", [str(IMG)])[1] == [str(IMG)])

import channels  # noqa: E402


class _FakeChannel:
    @staticmethod
    async def gui(tk, chat_id, text, chat_type="private", **extra):
        return True, ""

    @staticmethod
    async def send_file(tk, chat_id, path, caption="", chat_type="private"):
        return True, ""


_spec = channels.KenhSpec(id="fakech", nhan="Fake", kind="webhook",
                          nang_luc={"tra_loi_tu_javis": True, "gui_file": True})
_orig_spec, _orig_module = channels.spec, channels.module
channels.spec = lambda k: _spec if k == "fakech" else _orig_spec(k)
channels.module = lambda k: _FakeChannel if k == "fakech" else _orig_module(k)
asyncio.run(channels.gui("fakech", {}, "C1", "Dạ shop gửi chị bảng giá ạ"))
asyncio.run(channels.send_file("fakech", {}, "C1", str(IMG)))
said, left = delivery_ledger.trim_reply("C1", t0, "Dạ shop gửi chị bảng giá ạ", [str(IMG)])
check("B2 what the inbox (or inbox_reply through it) sent is not sent again", said and left == [], (said, left))
channels.spec, channels.module = _orig_spec, _orig_module

# ============================================================
# B3. A bot turn: a photo and the answer a tool already sent are not sent again
# ============================================================
ENGINE = {"thread": "u9", "send_image": True, "send_text": False}
ANSWER = "Dạ mẫu áo đỏ còn size L ạ"


async def bot_engine(text, meta_, progress, *, channel="", bot=None, **kw):
    # The model used a send tool during its turn (any name), then wrote its reply with the same photo embedded.
    if ENGINE["send_image"]:
        delivery_ledger.note_call({"thread": ENGINE["thread"], "images": ["attachments/ao-do.png"]}, "ok",
                                  base_dir=str(BRAIN))
    if ENGINE["send_text"]:
        delivery_ledger.note_call({"thread": ENGINE["thread"], "text": ANSWER}, "ok")
    return {"text": ANSWER + "\n![Áo đỏ](attachments/ao-do.png)", "files": []}


chatbot_runtime.wire(answer=bot_engine, brain_root=lambda b: str(BRAIN),
                     read_agent=lambda br, slug: ({"name": "Lan", "role": "Bán áo"}, "Trả lời ngắn."),
                     session_probe=lambda key: ("sid", 0), session_undo=lambda key, keep: None)
bid, err = chatbot_store.create_bot({"name": "Lan", "agent_slug": "lan", "brain": "b", "muc_quyen": "suggest",
                                     "audience": "all", "xac_nhan_rui_ro": True})
check("B3 (setup) bot created", bool(bid) and not err, err)
answer = chatbot_runtime._make_answer_fn(bid)


def zmeta(chat, n):
    return {"chat_id": chat, "chat_type": "private", "user_id": chat, "user_name": "Chị Hoa", "message_id": f"{chat}-{n}",
            "account_id": "zl-1", "platform": "zalo_personal", "_kenh": "zalo_personal"}


ENGINE.update(thread="u8", send_image=False, send_text=False)
r = asyncio.run(answer("Còn áo đỏ không em?", zmeta("u8", 1)))
check("B3 (control) without a tool send the embedded photo goes out with the reply",
      r.get("text") == ANSWER and len(r.get("files") or []) == 1, r)

ENGINE.update(thread="u9", send_image=True, send_text=False)
r = asyncio.run(answer("Còn áo đỏ không em?", zmeta("u9", 1)))
check("B3 the photo a tool already sent is not sent again; the words still go",
      r.get("text") == ANSWER and not r.get("files"), r)

ENGINE.update(thread="u10", send_image=True, send_text=True)
r = asyncio.run(answer("Còn áo đỏ không em?", zmeta("u10", 1)))
check("B3 everything already delivered: the turn stays quiet (nothing sent twice)",
      r.get("im_lang") and not r.get("text") and not r.get("files"), r)
stored = [x for x in conversations.tin_gan_day("zalo_personal", "zl-1", "u10", 10) if x.get("sender_type") == "ai"]
check("B3 ...and the inbox does not get the answer a second time", stored == [], stored)

ENGINE.update(thread="someone-else", send_image=True, send_text=True)
r = asyncio.run(answer("Còn áo đỏ không em?", zmeta("u11", 1)))
check("B3 a send to ANOTHER chat does not count for this one",
      r.get("text") == ANSWER and len(r.get("files") or []) == 1, r)

# ============================================================
# B4. An owner turn (Telegram, Zalo Bot, Slack...): the end of the turn sends only what did not arrive yet
# ============================================================
OWNER = {"text": "Báo cáo doanh thu tuần đã gửi anh", "files": [str(IMG), str(OTHER)]}


async def owner_engine(text, meta_, progress, **kw):
    delivery_ledger.note_call({"chat_id": "T7", "document": str(IMG)}, "ok")
    return dict(OWNER)


main._tg_answer_engine = owner_engine
out = asyncio.run(main._tg_answer("Gửi anh báo cáo", {"chat_id": "zalo:T7", "user_id": "T7", "chat_type": "private"},
                                  None, channel="zalo", ghi_kho=False))
check("B4 an owner turn leaves out the file a tool already delivered to the same chat",
      out.get("files") == [str(OTHER)] and out.get("text") == OWNER["text"], out)


async def owner_engine_all(text, meta_, progress, **kw):
    delivery_ledger.note_call({"chat_id": "T8", "text": OWNER["text"], "files": [str(IMG), str(OTHER)]}, "ok")
    return dict(OWNER)


main._tg_answer_engine = owner_engine_all
out = asyncio.run(main._tg_answer("Gửi anh báo cáo", {"chat_id": "T8", "user_id": "T8", "chat_type": "private"},
                                  None, channel="telegram", ghi_kho=False))
check("B4 everything already delivered: an owner turn is quiet, not an empty message",
      out.get("im_lang") and not out.get("text") and not out.get("files"), out)

if fails:
    print(f"\nFAIL {len(fails)}: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_bot_inbox_history_send_once: all pass")
