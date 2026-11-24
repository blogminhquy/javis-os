"""A message Javis itself sent is not a manual reply (issue #1775).

    python tests/run.py javis_sent_not_manual      (no network: fake channel, fake MCP)

Report (Javis 0.631.0): on a personal Zalo account nobody operates by hand, the Stats tab of the Chatbot page showed
82 "manual replies" against 52 A.I. in 7 days. All 82 were sent by Javis: scheduled Zalo scans, admin chat turns,
reports to staff and suppliers. Two paths, both guarded here:
  1. Stats (`conversations.insights`): a `human` row marked `tu_javis` with a machine `via` (inbox_reply records
     "tool") counts as A.I., per account too, but not for the chat's bot. `tu_javis` without `via` (the owner pressing
     Send in the inbox) and a plain hand-typed row stay manual. An odd stored metadata value does not break the query.
  2. End to end: a reply through the `inbox_reply` plugin counts as A.I.; a reply typed in the inbox stays manual.
  3. Zalo tools through the hub (`mcp_hub._guard`): the send is noted BEFORE it goes out (javis-zalo can push the echo
     before the call returns), so the echo is filed as Javis's, counted as A.I., and the bot does not step aside. A
     failed send is forgotten: the same words typed later are the owner's again. Zalo's message id matches too.
  4. A pack tool (`plugins_host._make_call`, e.g. `zalo_send_image`): same, matching the chat on any account; images
     match by kind, one per image sent. The history catch-up path uses the same ledger.
  5. The ledger is bounded (time window, per-chat cap, chat cap) and ignores what puts nothing in a chat.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import time

_STATE = tempfile.mkdtemp(prefix="javis-sent-not-manual-")
os.environ["JAVIS_STATE_DIR"] = _STATE
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channels  # noqa: E402
import conversations  # noqa: E402
import mcp_client  # noqa: E402
import mcp_hub  # noqa: E402
import plugins_host  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402
import zalo_sent_ledger as ledger  # noqa: E402
from routes.conversations import owner_reply  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:400] + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


if _STATE not in str(conversations.DB_PATH):
    print(f"FAIL the inbox store is not in the temp dir: {conversations.DB_PATH}. STOP.")
    sys.exit(1)

T0 = time.time()
counter = iter(range(1, 10_000))


def put(chat, kind, meta=None, acc="acc1", bot="", channel="telegram", at=None):
    n = next(counter)
    r = conversations.ghi_su_kien({"channel": channel, "account_id": acc, "external_chat_id": chat, "chat_type": "private",
                                   "bot_id": bot, "sender_type": kind, "sender_id": "k" + chat, "sender_name": "Lan",
                                   "text": "message " + str(n), "external_message_id": "m" + str(n),
                                   "created_at": T0 - 3600 + n if at is None else at, "metadata": meta or {}})
    assert r.get("ok"), r
    return r


def stats(account=""):
    return conversations.insights(T0 - 7200, time.time() + 60, account)


# ============================================================
# 1. The stats rule
# ============================================================
put("a", "customer", bot="bot-1")
put("a", "human", {"tu_javis": True, "via": "tool"}, bot="bot-1")       # inbox_reply from an engine
put("a", "customer", bot="bot-1")
put("a", "human", {"tu_javis": True}, bot="bot-1")                      # the owner pressed Send in the inbox
put("a", "customer", bot="bot-1")
put("a", "human", bot="bot-1")                                          # typed on the phone
put("a", "customer", bot="bot-1")
put("a", "ai", bot="bot-1")                                             # the bot's own answer
put("a", "human", {"tu_javis": False, "via": "tool"}, bot="bot-1")      # not marked as Javis's: a person
put("a", "human", {"via": "phone", "tu_javis": True}, bot="bot-1")      # an unknown via is not a machine path
st = stats()
check("a human row Javis sent with a tool counts as A.I.; the inbox Send, a hand-typed row and unknown marks stay manual",
      (st["ai"], st["human"], st["customer"]) == (2, 4, 4), (st["ai"], st["human"], st["customer"]))
check("per account too", st["by_account"].get("telegram:acc1") == {"customer": 4, "ai": 2, "human": 4}, st["by_account"])
check("the chat's bot gets only its own answer, not Javis's tool message", st["by_bot"] == {"bot-1": 1}, st["by_bot"])
check("a customer answered by Javis's tool counts as an A.I. first answer", st["waits_ai"] == 2 and st["waits_human"] == 2,
      (st["waits_ai"], st["waits_human"]))

# A stored metadata value that is not JSON (or not an object) must not fail the whole Stats query.
bad = put("b", "human", {"tu_javis": True, "via": "tool"})
with conversations._lock:
    db = conversations._conn()
    db.execute("UPDATE messages SET metadata_json=? WHERE id=?", ('{"via": "tool", broken', bad["message_id"]))
    db.commit()
bad2 = put("b", "human", {"tu_javis": True, "via": "tool"})
with conversations._lock:
    db = conversations._conn()
    db.execute("UPDATE messages SET metadata_json=? WHERE id=?", ('["via"]', bad2["message_id"]))
    db.commit()
try:
    st = stats()
    check("odd stored metadata is counted as manual, the query still runs", (st["ai"], st["human"]) == (2, 6),
          (st["ai"], st["human"]))
except Exception as e:      # noqa: BLE001
    check("odd stored metadata is counted as manual, the query still runs", False, repr(e))
check("the machine paths the stats know", conversations.JAVIS_SENT_VIA == ("tool",), conversations.JAVIS_SENT_VIA)
check("the Zalo ledger marks its echoes exactly like inbox_reply's rows",
      ledger.MARK == {"tu_javis": True, "via": "tool"}, ledger.MARK)

# ============================================================
# 2. End to end through inbox_reply and the inbox route
# ============================================================
SENT = []


async def fake_gui(kenh, tk, chat_id, text, chat_type="private", **extra):
    SENT.append({"kenh": kenh, "chat": chat_id, "text": text})
    return True, ""


channels.gui = fake_gui
spec = importlib.util.spec_from_file_location("inbox_reply_plugin", ROOT / "system/plugins/inbox-reply/plugin.py")
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)


class Ctx:
    def __init__(self):
        self.tools = {}

    def register_tool(self, name, handler, min_mode, **kw):
        self.tools[name] = handler


pctx = Ctx()
plugin.register(pctx)
conv = conversations.ghi_su_kien({"channel": "messenger", "account_id": "page-9", "account_name": "Shop",
                                  "external_chat_id": "u77", "chat_type": "private", "sender_type": "customer",
                                  "sender_id": "u77", "sender_name": "Hoa", "text": "Còn hàng không ạ"})["conversation_id"]
out = json.loads(asyncio.run(pctx.tools["inbox_reply"]({"conversation_id": conv, "text": "Dạ còn ạ"}, None)))
check("inbox_reply sent", out.get("ok") is True and len(SENT) == 1, out)
r = asyncio.run(owner_reply(conv, "Chị ghé shop nhé"))
check("an inbox reply typed by the owner sent", r.get("ok") is True and len(SENT) == 2, r)
st = stats("messenger:page-9")
check("inbox_reply counts as A.I., the owner's inbox reply as manual", (st["ai"], st["human"]) == (1, 1),
      (st["ai"], st["human"], st["by_account"]))

# ============================================================
# 3. Zalo tools through the hub
# ============================================================
CONN = {"id": "zalo-1", "label": "Shop Hoa", "connector_id": "zalo", "perm": "full"}
NAMES = {"u1": {"name": "Anh Nam", "type": "dm"}, "u2": {"name": "Chị Mai", "type": "dm"},
         "u3": {"name": "Chú Ba", "type": "dm"}}
msg_ids = iter(range(1, 10_000))


def own(thread, text="", kind="text", mid=None, **more):
    m = {"threadId": thread, "threadType": "dm", "senderId": "me", "senderName": "Shop Hoa", "isSelf": True,
         "type": kind, "text": text, "id": mid or "z" + str(next(msg_ids)), "timestamp": int(time.time() * 1000)}
    m.update(more)
    return m


def read(*msgs):
    return zc._ghi_lo(dict(CONN), list(msgs), NAMES)


def stored(thread):
    with conversations._lock:
        rows = conversations._conn().execute(
            "SELECT m.sender_type, m.text, m.metadata_json FROM messages m JOIN conversations c ON c.id=m.conversation_id"
            " WHERE c.channel_account_id=? AND c.external_chat_id=? ORDER BY m.id",
            ("zalo_personal:zalo-1", thread)).fetchall()
    return [(r[0], r[1], json.loads(r[2] or "{}")) for r in rows]


CALLS = []
RESULT = {"v": '{"success": true, "messageId": "z-sent-1"}'}
PUSH_FIRST = {"msg": None}


async def fake_call_route(route, fn, args):
    CALLS.append((fn, dict(args or {})))
    if PUSH_FIRST["msg"] is not None:
        # javis-zalo pushed the echo before the tool call returned: the read loop files it right now.
        read(PUSH_FIRST["msg"])
        PUSH_FIRST["msg"] = None
    return RESULT["v"]


mcp_client.call_route = fake_call_route
send = mcp_hub._guard({"conn": dict(CONN), "tool": "zalo_send_message", "spec": {"key": "zalo-1"}},
                      "zalo_send_message", "full")

report = "Báo cáo quét Zalo 7h: 3 khách mới, 1 đơn chờ xác nhận"
PUSH_FIRST["msg"] = own("u1", report)
res = asyncio.run(send({"threadId": "u1", "threadType": 0, "text": report}))
check("the hub let the send through", len(CALLS) == 1 and "success" in str(res), (CALLS, res))
rows = stored("u1")
check("the echo that came back first is in the inbox, marked as Javis's",
      len(rows) == 1 and rows[0][0] == "human" and rows[0][2].get("tu_javis") is True and rows[0][2].get("via") == "tool",
      rows)
check("the bot does not step aside for it", not zc.chu_vua_nhan_tay("zalo-1", "u1") and ("zalo-1", "u1") not in zc._TAY,
      zc._TAY)

# The echo arrives after the call returned, with words Zalo changed but the id it gave the send.
RESULT["v"] = '{"success": true, "messageId": "z-sent-2"}'
asyncio.run(send({"threadId": "u1", "threadType": 0, "text": "Nhắc anh Nam: mai giao hàng"}))
read(own("u1", "(tin đã được chỉnh sửa)", mid="z-sent-2"))
check("matched by Zalo's message id", stored("u1")[-1][2].get("via") == "tool" and ("zalo-1", "u1") not in zc._TAY,
      stored("u1"))

# A send Zalo refused is forgotten: the same words typed by hand later are the owner's.
RESULT["v"] = "ERROR: Zalo refused the message"
asyncio.run(send({"threadId": "u2", "threadType": 0, "text": "Em gửi chị bảng giá tháng 12"}))
read(own("u2", "Em gửi chị bảng giá tháng 12"))
rows = stored("u2")
check("after a failed send, the owner's own message is manual and the bot steps aside",
      rows and "via" not in rows[-1][2] and zc.chu_vua_nhan_tay("zalo-1", "u2"), (rows, zc._TAY))
RESULT["v"] = '{"success": false, "error": "blocked"}'
asyncio.run(send({"threadId": "u2", "threadType": 0, "text": "Chị xem giúp em đơn này"}))
read(own("u2", "Chị xem giúp em đơn này"))
check("success: false is a failed send too", "via" not in stored("u2")[-1][2], stored("u2"))

# A message the owner types by hand, with nothing sent by Javis, is still the owner's.
read(own("u3", "Chú ơi mai con qua lấy hàng nhé"))
check("an own message nobody noted is the owner's (manual, bot steps aside)",
      "via" not in stored("u3")[-1][2] and zc.chu_vua_nhan_tay("zalo-1", "u3"), stored("u3"))
# "Typing..." puts nothing in a chat: never noted.
typing = mcp_hub._guard({"conn": dict(CONN), "tool": "zalo_send_typing", "spec": {"key": "zalo-1"}},
                        "zalo_send_typing", "full")
RESULT["v"] = '{"success": true}'
asyncio.run(typing({"threadId": "u3"}))
check("zalo_send_typing is not a message", not ledger._sent.get("u3"), ledger._sent.get("u3"))

st = stats("zalo_personal:zalo-1")
check("Stats for the Zalo account: Javis's two sends are A.I., the owner's three messages manual",
      (st["ai"], st["human"]) == (2, 3), (st["ai"], st["human"]))

# ============================================================
# 4. A pack tool through the plugin host, and the history catch-up
# ============================================================
HANDLED = []


async def send_image(args, ctx):
    HANDLED.append(dict(args))
    return {"ok": True, "sent": len(args.get("paths") or [])}


img_tool = plugins_host._make_call({"name": "zalo_send_image", "handler": send_image, "min_mode": "full"}, None, "full")
out = asyncio.run(img_tool({"threadId": "u4", "threadType": 0, "paths": ["a.jpg", "b.jpg"], "caption": ""}))
check("the pack tool ran", len(HANDLED) == 1 and '"ok": true' in out, out)
NAMES["u4"] = {"name": "Kho", "type": "dm"}
read(own("u4", kind="photo", attachment={"type": "photo", "url": "https://zalo.test/a.jpg"}),
     own("u4", kind="photo", attachment={"type": "photo", "url": "https://zalo.test/b.jpg"}),
     own("u4", kind="photo", attachment={"type": "photo", "url": "https://zalo.test/c.jpg"}))
rows = stored("u4")
check("both images Javis sent are its own, the third image is the owner's",
      [r[2].get("via") for r in rows] == ["tool", "tool", None] and zc.chu_vua_nhan_tay("zalo-1", "u4"), rows)

# History catch-up (a message the live feed missed) uses the same ledger.
NAMES["u5"] = {"name": "NCC Phúc", "type": "dm"}
put("u5", "customer", channel="zalo_personal", acc="zalo-1", at=time.time() - 600)
zc._TT.setdefault("zalo-1", {})["first_read"] = time.time() - 3600
zc._TT["zalo-1"]["ten"] = NAMES
RESULT["v"] = '{"success": true, "messageId": "z-sent-9"}'
asyncio.run(send({"threadId": "u5", "threadType": 0, "text": "Anh Phúc ơi em chốt 50 thùng nhé"}))
written = zc.catch_up(dict(CONN), [own("u5", "Anh Phúc ơi em chốt 50 thùng nhé", mid="h-1", timestamp=int((time.time() - 120) * 1000)),
                                   own("u5", "Anh gửi hoá đơn giúp em", mid="h-2", timestamp=int((time.time() - 100) * 1000))])
rows = stored("u5")
check("catch-up: Javis's message recovered as its own, the owner's as manual",
      written == 2 and [r[2].get("via") for r in rows[1:]] == ["tool", None] and zc.chu_vua_nhan_tay("zalo-1", "u5"),
      (written, rows))

# ============================================================
# 5. The ledger itself
# ============================================================
ledger.clear()
check("not a send tool: nothing noted", ledger.note("zalo-1", "zalo_get_messages", {"threadId": "x"}) is None)
check("no chat named: nothing noted", ledger.note("zalo-1", "zalo_send_message", {"text": "hi"}) is None)
e = ledger.note("zalo-1", "zalo_send_message", {"threadId": "t1", "text": "Họp lúc **9h** nhé mọi người"})
check("text is compared as Zalo shows it (Markdown stars dropped)",
      ledger.take("zalo-1", {"external_chat_id": "t1", "text": "Họp lúc 9h nhé mọi người"}), e)
ledger.note("zalo-1", "zalo_send_message", {"threadId": "t1", "text": "Chào cả nhà"})
check("another account's own message does not use it up",
      not ledger.take("zalo-2", {"external_chat_id": "t1", "text": "Chào cả nhà"}))
check("an entry is gone after its time window",
      not ledger.take("zalo-1", {"external_chat_id": "t1", "text": "Chào cả nhà"}, now=time.time() + ledger.ECHO_TTL + 1))
ledger.note("", "zalo_send_mention", {"threadId": "t2", "text": "mai họp sớm 30 phút nhé"})
check("a tag added in front of the words still matches, on any account (pack tool)",
      ledger.take("zalo-7", {"external_chat_id": "t2", "text": "@Minh Quý mai họp sớm 30 phút nhé"}))
ledger.note("zalo-1", "zalo_send_link", {"threadId": "t3", "url": "https://shop.test/sale/", "text": "Xem nhé"})
check("a link card matches by its link",
      ledger.take("zalo-1", {"external_chat_id": "t3", "text": "Sale cuối năm\nhttps://shop.test/sale",
                             "metadata": {"link_card": {"url": "https://shop.test/sale"}}}))
ledger.note("zalo-1", "zalo_send_link", {"threadId": "t6", "url": "https://shop.test/b", "text": "Xem link"})
check("a photo the owner sends long after a link card is not taken for that card",
      not ledger.take("zalo-1", {"external_chat_id": "t6", "message_type": "image", "text": "[ảnh]"},
                      now=time.time() + ledger.LINK_BLIND + 1))
check("a card that came back as a non-text message right away is matched",
      ledger.take("zalo-1", {"external_chat_id": "t6", "message_type": "image", "text": "[ảnh]"}))
ledger.note("zalo-1", "zalo_send_message", {"threadId": "t7", "text": "Gửi anh số tài khoản"})
check("a text send never covers a photo", not ledger.take("zalo-1", {"external_chat_id": "t7", "message_type": "image"}))
for i in range(ledger.PER_CHAT + 5):
    ledger.note("zalo-1", "zalo_send_message", {"threadId": "t4", "text": f"tin số {i}"})
check("a chat keeps at most PER_CHAT entries, the newest", len(ledger._sent["t4"]) == ledger.PER_CHAT
      and ledger._sent["t4"][-1]["text"] == f"tin số {ledger.PER_CHAT + 4}", len(ledger._sent["t4"]))
for i in range(ledger.MAX_CHATS + 50):
    ledger.note("zalo-1", "zalo_send_message", {"threadId": f"c{i}", "text": "x"})
check("at most MAX_CHATS chats are held", len(ledger._sent) <= ledger.MAX_CHATS, len(ledger._sent))
check("a broken event never raises", ledger.take("zalo-1", None) is False and ledger.take("zalo-1", {}) is False)


async def boom(a):
    raise RuntimeError("socket closed")

try:
    asyncio.run(ledger.sending("zalo-1", "zalo_send_message", {"threadId": "t5", "text": "lỗi giữa chừng"}, boom))
    check("an exception from the send is raised again", False)
except RuntimeError:
    check("an exception from the send is raised again, and the note is dropped", not ledger._sent.get("t5"),
          ledger._sent.get("t5"))

print()
if _fails:
    raise SystemExit(f"FAIL {len(_fails)}: " + "; ".join(_fails[:5]))
print("ALL PASS")
