"""Tool `inbox_find` / `inbox_reply` (bundled plugin inbox-reply): an engine answers a customer on the conversation's
own channel, the same path as the owner typing in the inbox.

    python tests/run.py inbox_reply_tool      (no network: the channel send is a fake)

Owner (2026-11-17): Javis told them "there is no Messenger send tool, paste the drafts yourself". Guards:
  1. inbox_find locates a Messenger and an Instagram chat by name and returns their conversation_id.
  2. inbox_reply sends through `channels.gui` with the Page account and the raw chat id, records a `human` message
     marked via=tool, and leaves the chat's bot running (a reply typed in the inbox still takes over).
  3. a failed send returns ERROR and records nothing; a missing conversation or empty text never reaches the channel.
  4. the inbox route POST /conversations/{id}/reply still works through the shared `owner_reply`.
  5. (review of PR 1554) both tools are owner-only, so a customer talking to a bot can never read or message the
     shop's other customers, and neither reaches a conversation of a channel account assigned to another brain.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import json
import os
import sys
import tempfile

_STATE = tempfile.mkdtemp(prefix="javis-inbox-reply-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channels  # noqa: E402
import conversations  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


if _STATE not in str(conversations.DB_PATH):
    print(f"FAIL the inbox store is not in the temp dir: {conversations.DB_PATH}. STOP.")
    sys.exit(1)

SENT = []
MODE = {"gui": "ok"}


async def fake_gui(kenh, tk, chat_id, text, chat_type="private", **extra):
    SENT.append({"kenh": kenh, "tk": dict(tk), "chat": chat_id, "text": text})
    if MODE["gui"] == "fail":
        return False, "Meta refused: outside the 24 hour window"
    return True, ""


channels.gui = fake_gui

spec = importlib.util.spec_from_file_location("inbox_reply_plugin", ROOT / "system/plugins/inbox-reply/plugin.py")
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)


class Ctx:
    def __init__(self):
        self.tools = {}

    def register_tool(self, name, handler, min_mode, **kw):
        self.tools[name] = (handler, min_mode)


ctx = Ctx()
plugin.register(ctx)
check("both tools registered", set(ctx.tools) == {"inbox_find", "inbox_reply"}, ctx.tools)
check("inbox_find is read-only", ctx.tools["inbox_find"][1] == "readonly")
check("inbox_reply needs full", ctx.tools["inbox_reply"][1] == "full")


def call(name, args):
    return asyncio.run(ctx.tools[name][0](args, None))


def seed(chat, name, text, bot="bot-donnan"):
    r = conversations.ghi_su_kien({
        "channel": "messenger", "account_id": "102322291424816", "account_name": "Donnan", "bot_id": bot,
        "external_chat_id": chat, "chat_type": "private", "sender_type": "customer", "sender_id": chat,
        "sender_name": name, "text": text})
    return r["conversation_id"]


fb = seed("2468", "Thu Trang", "Shop còn size M không ạ")
ig = seed("ig:9753", "minh.anh", "Giá bao nhiêu vậy shop")

# 1. find
r = json.loads(call("inbox_find", {"q": "Thu Trang"}))
ids = [c["conversation_id"] for c in r["conversations"]]
check("find by customer name", ids == [fb], r)
r = json.loads(call("inbox_find", {"q": "minh.anh"}))
check("Instagram chat is flagged", r["conversations"] and r["conversations"][0]["instagram"] is True, r)
r = json.loads(call("inbox_find", {"conversation_id": fb}))
check("read one conversation's messages", r["messages"][-1]["text"] == "Shop còn size M không ạ", r)

# 2. reply
out = call("inbox_reply", {"conversation_id": fb, "text": "Dạ size M còn ạ"})
d = json.loads(out)
check("reply ok", d.get("ok") is True, out)
check("sent once on messenger to the raw chat id", len(SENT) == 1 and SENT[0]["kenh"] == "messenger"
      and SENT[0]["chat"] == "2468" and SENT[0]["tk"]["id"] == "102322291424816", SENT)
last = conversations.tin_nhan(fb, limit=1)[-1]
check("recorded as the owner's message via tool", last["sender_type"] == "human"
      and (last.get("metadata") or {}).get("via") == "tool", last)
check("the chat's bot keeps running after a reply from chat", conversations.chi_tiet(fb)["mode"] == "ai"
      and "bot_paused" not in d, d)

SENT.clear()
call("inbox_reply", {"conversation_id": ig, "text": "Dạ 350k ạ"})
check("Instagram reply keeps the ig: chat id for the channel", SENT and SENT[0]["chat"] == "ig:9753", SENT)

# 3. failures
SENT.clear()
n_before = len(conversations.tin_nhan(fb, limit=100))
MODE["gui"] = "fail"
out = call("inbox_reply", {"conversation_id": fb, "text": "thử lại"})
check("failed send returns ERROR with the reason", out.startswith("ERROR:") and "24 hour" in out, out)
check("failed send records nothing", len(conversations.tin_nhan(fb, limit=100)) == n_before)
MODE["gui"] = "ok"
SENT.clear()
check("unknown conversation", call("inbox_reply", {"conversation_id": 99999, "text": "x"}).startswith("ERROR:"))
check("empty text", call("inbox_reply", {"conversation_id": fb, "text": "  "}).startswith("ERROR:"))
check("no conversation_id", call("inbox_reply", {"text": "x"}).startswith("ERROR:"))
check("nothing sent on bad input", SENT == [], SENT)

# 4. the inbox route still works through owner_reply
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
client = TestClient(main.app)
fb2 = seed("1357", "Hoa", "alo shop")
SENT.clear()
resp = client.post(f"/conversations/{fb2}/reply", data={"text": "Dạ em nghe"}, headers={"host": "testserver"})
if resp.status_code in (401, 403):
    print("skip route check: auth required in this environment")
else:
    check("route reply 200", resp.status_code == 200 and resp.json().get("ok") is True, resp.text)
    check("route sent once", len(SENT) == 1 and SENT[0]["chat"] == "1357", SENT)
resp = client.post("/conversations/99999/reply", data={"text": "x"})
if resp.status_code not in (401, 403):
    check("route unknown conversation is 404", resp.status_code == 404, resp.status_code)

check("a reply typed in the inbox still takes the chat over from its bot",
      conversations.chi_tiet(fb2)["mode"] == "human" or resp.status_code in (401, 403))

# 5. safety
import mcp_hub  # noqa: E402
check("both tools are owner-only (never reach a customer-facing bot)",
      {"inbox_find", "inbox_reply"} <= mcp_hub.OWNER_ONLY_TOOLS)

import channel_accounts  # noqa: E402
other = seed("8642", "Khach brain khac", "hello", bot="bot-khac")
mine = seed("9753x", "Khach brain nay", "xin chao")


class BrainCtx:
    vault_root = "/brains/shop-a"


_real_keys = channel_accounts.keys_of_other_brains
# The two seeded chats share one Page account here, so give the "other brain" chat its own account key.
with conversations._lock:
    conversations._conn().execute("UPDATE conversations SET channel_account_id=? WHERE id=?", ("messenger:OTHER", other))
    conversations._conn().commit()
channel_accounts.keys_of_other_brains = lambda brain: ["messenger:OTHER"] if brain == "/brains/shop-a" else []


def call_in(name, args):
    return asyncio.run(ctx.tools[name][0](args, BrainCtx()))


r = json.loads(call_in("inbox_find", {"q": "Khach brain"}))
found = {c["conversation_id"] for c in r["conversations"]}
check("find stays inside the calling brain", other not in found and mine in found, r)
check("find reading another brain's chat is refused",
      call_in("inbox_find", {"conversation_id": other}).startswith("ERROR:"))
SENT.clear()
out = call_in("inbox_reply", {"conversation_id": other, "text": "x"})
check("reply into another brain's chat is refused and nothing is sent", out.startswith("ERROR:") and SENT == [], out)
channel_accounts.keys_of_other_brains = _real_keys

if _fails:
    print(f"\nFAIL {len(_fails)}: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_inbox_reply_tool: all pass")
