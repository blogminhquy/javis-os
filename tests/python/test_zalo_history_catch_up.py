"""Private Zalo messages that never reached the live feed are caught up from the javis-zalo history file.

    python tests/run.py zalo_history_catch_up      (no network, no MCP)

Field report 08/11/2026 (owner): the inbox stopped a private chat at 09:28 while the phone went on until 09:53, messages
both ways, and `zalo_get_history` had all of them. Owner, same day: no schedule, only work where there is a signal.
So `zalo_personal_channel` watches javis-zalo's `history.jsonl`: an unchanged file costs one stat call, new lines are
queued, and `catch_up` writes the ones the inbox is missing. This file guards (see the comment block in the module):
  the signal (nothing done while the file does not grow, only new lines read, a half-written line waits, a rewrite is
  survived), 1. private chats only, 2. a new line waits RECONCILE_MIN_AGE and a drained read,
  3. never handed to the bot, the owner's own message still counts as typing by hand,
  4. the account's own sentence already stored (no id yet) is not written twice and gets the id,
  5. stickers and short emoji stay out, 6. old messages only fill holes of chats the inbox follows,
plus: a late message never becomes the conversation's last message, and the same words typed twice are two messages.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
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
HOME = tempfile.mkdtemp(prefix="javis-zhome-")
CONN = dict(CONN, env={"HOME": HOME})
PATH = zc.history_path(CONN)
os.makedirs(os.path.dirname(PATH), exist_ok=True)


def append(*msgs, partial=""):
    with open(PATH, "a", encoding="utf-8") as f:
        for m in msgs:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
        f.write(partial)


HANDED = []
zc._giao_cho_bot = lambda conn, ev: HANDED.append(ev)
tt = zc._TT.setdefault("zalo-1", {})
tt["first_read"] = NOW - 10 * 60
tt["drained"] = True
tt["ten"] = {"xa": {"name": "Xuan Anh", "type": "dm"}, "g1": {"name": "Nhom", "type": "group"}}

# ---- The signal: a file that does not change costs nothing
append(*HISTORY[:3])
check("first look at an existing file queues its recent private messages", zc.watch_history(CONN, NOW) == 3)
check("an unchanged file: nothing read, nothing queued", zc.watch_history(CONN, NOW) == 0)
opened = {"n": 0}
real_open = open


def counting_open(*a, **k):
    if a and str(a[0]) == PATH:
        opened["n"] += 1
    return real_open(*a, **k)


zc.open = counting_open      # the module's `open` (builtins otherwise)
for _ in range(50):
    zc._history_turn(CONN, tt, NOW)
check("a whole idle day of read turns never opens the file", opened["n"] == 0, opened)
check("a whole idle day of read turns queues nothing more", len(tt.get("history_pending") or []) == 3,
      tt.get("history_pending"))

# ---- New lines arrive; a line still being written waits
half = json.dumps(HISTORY[11])
append(*HISTORY[3:11], partial=half[:20])
n = zc.watch_history(CONN, NOW)
check("only the new complete private lines are queued (not the group one, not the half line)", n == 7, n)
check("the file was opened once for those lines", opened["n"] == 1, opened)
with real_open(PATH, "a", encoding="utf-8") as f:
    f.write(half[20:] + "\n")
check("the rest of the half line is picked up next time", zc.watch_history(CONN, NOW) == 1)

# ---- Rule 2: nothing is written before RECONCILE_MIN_AGE, nor while the buffer is not drained
zc._history_turn(CONN, tt, NOW + 10)
xa = {c["external_chat_id"]: c for c in conversations.danh_sach(limit=50)}["xa"]
check("rule 2: queued lines wait RECONCILE_MIN_AGE", int(xa["message_count"]) == 3, xa)
tt["drained"] = False
zc._history_turn(CONN, tt, NOW + zc.RECONCILE_MIN_AGE + 1)
xa = {c["external_chat_id"]: c for c in conversations.danh_sach(limit=50)}["xa"]
check("rule 2: nothing released while the live buffer still holds messages", int(xa["message_count"]) == 3, xa)
tt["drained"] = True
zc._history_turn(CONN, tt, NOW + zc.RECONCILE_MIN_AGE + 1)

convs = {c["external_chat_id"]: c for c in conversations.danh_sach(limit=50)}
xa = convs.get("xa") or {}
msgs = conversations.tin_nhan(int(xa["id"]))
texts = [m["text"] for m in msgs]
check("the missing messages of the chat were written",
      texts[-4:] == ["next version duoc release lien tuc a", "cai nay la update realtime theo khach hang",
                     "that nghiep thoi chu co sao dau e", "vua nhan xong"], texts)
check("rule 4: the bot's sentence is not written a second time", texts.count("Da, poster ben em lam bang AI a") == 1, texts)
bot_row = next(m for m in msgs if m["text"].startswith("Da, poster"))
check("rule 4: the bot's row got Zalo's id", bot_row["external_message_id"] == "3", bot_row)
own = next(m for m in msgs if m["text"].startswith("cai nay la update"))
check("the owner's recovered message is a human message", own["sender_type"] == "human", own)
check("the customer's recovered message is a customer message", msgs[-1]["sender_type"] == "customer", msgs[-1])
check("recovered messages are flagged", all((m.get("metadata") or {}).get("recovered") for m in msgs[-4:]), msgs[-4:])
check("rule 5: sticker and short emoji left out", not any(m["message_type"] == "sticker" or m["text"] == "\U0001F44D"
                                                          for m in msgs), texts)
check("rule 1: group messages are not touched", "g1" not in convs, list(convs))
check("rule 3: nothing handed to the bot", HANDED == [], HANDED)
check("rule 3: the owner's recovered message counts as typing by hand",
      zc._TAY.get(("zalo-1", "xa"), 0) >= NOW - 19 * 60 - 1, zc._TAY)
check("recovered customer messages count as unread", int(xa.get("unread_count") or 0) >= 2, xa)
check("the conversation's last message is the newest one", xa.get("last_message", "") == "vua nhan xong", xa)
new = convs.get("new") or {}
new_texts = [m["text"] for m in conversations.tin_nhan(int(new["id"]))] if new else []
check("rule 6: an unknown chat only takes messages from after the first read",
      new_texts == ["new chat after the first read"], new_texts)
check("the queue is empty once released", not tt.get("history_pending"), tt.get("history_pending"))

# ---- The same lines again (javis-zalo rewrote the file): nothing written twice
before = int(xa["message_count"])
with real_open(PATH, "rb") as f:
    content = f.read()
os.remove(PATH)
with real_open(PATH, "wb") as f:
    f.write(content.split(b"\n", 1)[1])      # compaction: a shorter file with the same recent lines
zc.watch_history(CONN, NOW)
zc._history_turn(CONN, tt, NOW + zc.RECONCILE_MIN_AGE + 1)
xa = {c["external_chat_id"]: c for c in conversations.danh_sach(limit=50)}["xa"]
check("a rewritten file is read again without writing anything twice", int(xa["message_count"]) == before, xa)

# ---- A late message never takes the place of the last message
conversations.ghi_su_kien(live("50", "xa", "newest live message", 1))
append(hist(51, "xa", "older message found late", 10))
zc._history_turn(CONN, tt, NOW)
zc._history_turn(CONN, tt, NOW + zc.RECONCILE_MIN_AGE + 1)
xa = {c["external_chat_id"]: c for c in conversations.danh_sach(limit=50)}["xa"]
check("an older recovered message is written", "older message found late" in
      [m["text"] for m in conversations.tin_nhan(int(xa["id"]), limit=200)])
check("an older recovered message does not become the last message", xa.get("last_message") == "newest live message", xa)

# ---- Live writes keep the old rule: the last written is the last message
conversations.ghi_su_kien(live("60", "xa", "live but stamped earlier", 3))
xa = {c["external_chat_id"]: c for c in conversations.danh_sach(limit=50)}["xa"]
check("a live message still becomes the last message whatever its time", xa.get("last_message") == "live but stamped earlier", xa)

# ---- The owner says the same words twice: the second one is a message of its own
conversations.ghi_su_kien(live("70", "xa", "ok", 4, "human"))
append(hist(70, "xa", "ok", 4, self_=True), hist(71, "xa", "ok", 3.5, self_=True))
zc._history_turn(CONN, tt, NOW)
zc._history_turn(CONN, tt, NOW + zc.RECONCILE_MIN_AGE + 1)
oks = [m for m in conversations.tin_nhan(int(xa["id"]), limit=200) if m["text"] == "ok"]
check("the same words typed twice by the owner are two messages", sorted(m["external_message_id"] for m in oks) ==
      ["70", "71"], oks)

# ---- Messages older than RECONCILE_WINDOW (an old replay) are never written
append(hist(80, "xa", "a replay from yesterday", 24 * 60))
zc._history_turn(CONN, tt, NOW)
zc._history_turn(CONN, tt, NOW + zc.RECONCILE_MIN_AGE + 1)
check("a replayed message older than RECONCILE_WINDOW is left out", "a replay from yesterday" not in
      [m["text"] for m in conversations.tin_nhan(int(xa["id"]), limit=200)])

# ---- No history file at all: no error
check("no history file: nothing happens", zc.watch_history(dict(CONN, id="other", env={"HOME": tempfile.mkdtemp()}), NOW) == 0)

# ---- No MCP call and no schedule: the read loop only runs the turn after each successful read
src = real_open(os.path.join(SERVER, "zalo_personal_channel.py"), encoding="utf-8").read()
check("the read loop runs the history turn after each successful read, on a worker thread",
      "await asyncio.to_thread(_history_turn, conn, tt)" in src)
check("the catch-up never calls the MCP", "zalo_search_history" not in src[src.index("# Catching up from the history"):
                                                                          src.index("# Vòng đọc\n")])

check("no em dash", chr(0x2014) not in open(__file__, encoding="utf-8").read())

print()
if _fails:
    print(f"{len(_fails)} FAIL: " + ", ".join(_fails))
    sys.exit(1)
print("ALL PASS")
