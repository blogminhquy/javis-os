"""Private Zalo messages that never reached the live feed are caught up from the javis-zalo history.

    python tests/run.py zalo_history_catch_up      (no network, fake MCP)

Field report 08/11/2026 (owner): the inbox stopped a private chat at 09:28 while the phone went on until 09:53, messages
both ways, and `zalo_get_history` had all of them. `zalo_personal_channel.reconcile_history` writes what the inbox is
missing. This file guards its rules (see the comment block above it):
  1. private chats only, 2. only after a drained read and only messages older than RECONCILE_MIN_AGE,
  3. never handed to the bot, the owner's own message still counts as typing by hand,
  4. the account's own sentence already stored (no id yet) is not written twice and gets the id,
  5. stickers and short emoji stay out, 6. an unknown chat only takes messages from after the first read,
plus: a late message never becomes the conversation's last message, a second pass writes nothing, and an MCP without
the history tool neither raises nor retries every turn.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zcatch-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import conversations  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


NOW = time.time()
CONN = {"id": "zalo-1", "label": "Minh Quy", "connector_id": "zalo"}


def hist(mid, thread, text, minutes_ago, self_=False, ttype="dm", sender="u-xa", name="Xuan Anh", kind="text"):
    return {"msgId": str(mid), "threadId": thread, "threadType": ttype, "senderId": "me" if self_ else sender,
            "senderName": "Me" if self_ else name, "isSelf": self_, "text": text,
            "timestamp": int((NOW - minutes_ago * 60) * 1000), "type": kind}


def live(mid, thread, text, minutes_ago, sender_type="customer"):
    return {"channel": "zalo_personal", "account_id": "zalo-1", "account_name": "Minh Quy",
            "external_chat_id": thread, "chat_type": "private", "sender_type": sender_type,
            "sender_id": "u-xa" if sender_type == "customer" else "", "sender_name": "Xuan Anh",
            "message_type": "text", "text": text, "external_message_id": mid,
            "created_at": NOW - minutes_ago * 60}


# The inbox as the live feed left it: the chat stops at the poster talk (09:28 in the report).
conversations.ghi_su_kien(live("1", "xa", "E vac di chay ads luon ma", 30, "human"))
conversations.ghi_su_kien(live("2", "xa", "no lam qua poster xin the nhi", 29))
# The bot answered through the inbox, Zalo has not given its row an id yet.
conversations.ghi_su_kien(dict(live("", "xa", "Da, poster ben em lam bang AI a", 28, "ai"), sender_name="Bot"))

HISTORY = [
    hist(1, "xa", "E vac di chay ads luon ma", 30, self_=True),
    hist(2, "xa", "no lam qua poster xin the nhi", 29),
    hist(3, "xa", "Da, poster ben em lam bang AI a", 28, self_=True),          # the bot's own echo (rule 4)
    hist(4, "xa", "next version duoc release lien tuc a", 20),
    hist(5, "xa", "cai nay la update realtime theo khach hang", 19, self_=True),
    hist(6, "xa", "", 18, kind="chat.sticker"),                                 # rule 5
    hist(7, "xa", "\U0001F44D", 17),                                            # rule 5
    hist(8, "xa", "that nghiep thoi chu co sao dau e", 16),
    hist(9, "g1", "tin trong nhom", 15, ttype="group", sender="u-g"),           # rule 1
    hist(10, "xa", "vua nhan xong", 0.5),                                       # rule 2: too fresh
    hist(11, "new", "old chat before the first read", 50, sender="u-n", name="Khach N"),   # rule 6
    hist(12, "new", "new chat after the first read", 5, sender="u-n", name="Khach N"),
]
CALLS = []
BROKEN = {"v": False}


def _query(since, limit, before):
    rows = sorted((m for m in HISTORY if m["timestamp"] >= since), key=lambda m: m["timestamp"])
    if before:
        idx = next((i for i, m in enumerate(rows) if m["msgId"] == before), -1)
        rows = rows[:idx] if idx >= 0 else []
    page = rows[max(0, len(rows) - limit):]
    return {"count": len(page), "messages": [dict(m) for m in page],
            "cursor": page[0]["msgId"] if page else None, "hasMore": len(rows) > len(page)}


async def _fake_call(conn, tool, args):
    CALLS.append((tool, dict(args)))
    if tool == "zalo_search_history":
        if BROKEN["v"]:
            raise RuntimeError("Unknown tool: zalo_search_history")
        return _query(args.get("since") or 0, int(args.get("limit") or 50), args.get("before"))
    return {}


HANDED = []
zc._goi = _fake_call
zc._giao_cho_bot = lambda conn, ev: HANDED.append(ev)
zc.RECONCILE_PAGE = 3       # small pages so several are read
tt = zc._TT.setdefault("zalo-1", {})
tt["first_read"] = NOW - 10 * 60
tt["ten"] = {"xa": {"name": "Xuan Anh", "type": "dm"}, "g1": {"name": "Nhom", "type": "group"}}

r = asyncio.run(zc.reconcile_history(CONN, NOW))
check("the pass ran", isinstance(r, dict), r)
check("several history pages read (newest first, back with before)",
      sum(1 for t, _ in CALLS if t == "zalo_search_history") >= 3 and any(a.get("before") for _, a in CALLS), CALLS)
check("the pass looks back RECONCILE_WINDOW only",
      all(a["since"] >= int((NOW - zc.RECONCILE_WINDOW - 1) * 1000) for t, a in CALLS if t == "zalo_search_history"))

convs = {c["external_chat_id"]: c for c in conversations.danh_sach(limit=50)}
xa = convs.get("xa") or {}
msgs = conversations.tin_nhan(int(xa["id"]))
texts = [m["text"] for m in msgs]
check("the three missing messages of the chat were written",
      texts[-3:] == ["next version duoc release lien tuc a", "cai nay la update realtime theo khach hang",
                     "that nghiep thoi chu co sao dau e"], texts)
check("rule 4: the bot's sentence is not written a second time", texts.count("Da, poster ben em lam bang AI a") == 1, texts)
bot_row = next(m for m in msgs if m["text"].startswith("Da, poster"))
check("rule 4: the bot's row got Zalo's id", bot_row["external_message_id"] == "3", bot_row)
check("the owner's recovered message is a human message", msgs[-2]["sender_type"] == "human", msgs[-2])
check("the customer's recovered message is a customer message", msgs[-1]["sender_type"] == "customer", msgs[-1])
check("recovered messages are flagged", all((m.get("metadata") or {}).get("recovered") for m in msgs[-3:]), msgs[-3:])
check("rule 5: sticker and short emoji left out", not any(m["message_type"] == "sticker" or m["text"] == "\U0001F44D"
                                                          for m in msgs), texts)
check("rule 2: a message younger than RECONCILE_MIN_AGE is left to the live read", "vua nhan xong" not in texts, texts)
check("rule 1: group messages are not touched", "g1" not in convs, list(convs))
check("rule 3: nothing handed to the bot", HANDED == [], HANDED)
check("rule 3: the owner's recovered message counts as typing by hand",
      zc._TAY.get(("zalo-1", "xa"), 0) >= NOW - 19 * 60 - 1, zc._TAY)
check("recovered customer messages count as unread", int(xa.get("unread_count") or 0) >= 2, xa)
check("the conversation's last message is the newest one", xa.get("last_message", "").startswith("that nghiep"), xa)
new = convs.get("new") or {}
new_texts = [m["text"] for m in conversations.tin_nhan(int(new["id"]))] if new else []
check("rule 6: an unknown chat only takes messages from after the first read",
      new_texts == ["new chat after the first read"], new_texts)
check("the pass reports what it wrote", r.get("written") == 4, r)

# ---- A second pass writes nothing
r2 = asyncio.run(zc.reconcile_history(CONN, NOW))
check("a second pass writes nothing", r2.get("written") == 0, r2)

# ---- A late message never takes the place of the last message
conversations.ghi_su_kien(live("50", "xa", "newest live message", 1))
HISTORY.append(hist(51, "xa", "older message found late", 10))
asyncio.run(zc.reconcile_history(CONN, NOW))
xa = {c["external_chat_id"]: c for c in conversations.danh_sach(limit=50)}["xa"]
check("an older recovered message is written", "older message found late" in
      [m["text"] for m in conversations.tin_nhan(int(xa["id"]))])
check("an older recovered message does not become the last message", xa.get("last_message") == "newest live message", xa)

# ---- Live writes keep the old rule: the last written is the last message
conversations.ghi_su_kien(live("60", "xa", "live but stamped earlier", 3))
xa = {c["external_chat_id"]: c for c in conversations.danh_sach(limit=50)}["xa"]
check("a live message still becomes the last message whatever its time", xa.get("last_message") == "live but stamped earlier", xa)

# ---- The owner says the same words twice: the second one is a message of its own
conversations.ghi_su_kien(live("70", "xa", "ok", 4, "human"))
HISTORY.append(hist(70, "xa", "ok", 4, self_=True))
HISTORY.append(hist(71, "xa", "ok", 3.5, self_=True))
asyncio.run(zc.reconcile_history(CONN, NOW))
oks = [m for m in conversations.tin_nhan(int(xa["id"]), limit=200) if m["text"] == "ok"]
check("the same words typed twice by the owner are two messages", sorted(m["external_message_id"] for m in oks) ==
      ["70", "71"], oks)

# ---- When a pass is due
CALLS.clear()
t2 = {"drained": False}
asyncio.run(zc._reconcile_if_due(CONN, t2))
check("rule 2: no pass while the live buffer still holds messages", not CALLS, CALLS)
t2 = {"drained": True}
asyncio.run(zc._reconcile_if_due(CONN, t2))
check("a pass runs when due", CALLS, CALLS)
CALLS.clear()
asyncio.run(zc._reconcile_if_due(CONN, t2))
check("no second pass before RECONCILE_EVERY", not CALLS, CALLS)

# ---- An MCP without the history tool: no exception, no retry every turn
BROKEN["v"] = True
t3 = {"drained": True}
asyncio.run(zc._reconcile_if_due(CONN, t3))
check("an old javis-zalo does not break the read loop and waits long before retrying",
      t3.get("reconcile_at", 0) >= time.time() + zc.RECONCILE_UNSUPPORTED_WAIT - 5, t3)
BROKEN["v"] = False

# ---- The read loop calls the pass after a successful read
src = open(os.path.join(SERVER, "zalo_personal_channel.py"), encoding="utf-8").read()
check("the read loop runs the catch-up after each successful read", "await _reconcile_if_due(conn, tt)" in src)

check("no em dash", chr(0x2014) not in open(__file__, encoding="utf-8").read())

print()
if _fails:
    print(f"{len(_fails)} FAIL: " + ", ".join(_fails))
    sys.exit(1)
print("ALL PASS")
