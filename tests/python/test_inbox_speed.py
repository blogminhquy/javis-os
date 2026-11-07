"""The Chatbot page stays quick on a big inbox (owner, 2026-11-07: "trang chatbot, hội thoại, bot và thống kê load rất
lâu").

  1. The messages store has the two time indexes every count by time relies on ("messages today" on the inbox and on each
     bot card, refreshed every 5 seconds, and the Stats tab), so none of them reads the whole table.
  2. "New chats" on the Stats tab means the same as before: a private chat whose very first message is in the period.
  3. The Stats tab cache: a period that has ended is counted once; the running period is counted again once its short
     cache ends; deleting a chat clears it.
  4. The inbox asks for the channel accounts and the conversation list at the same time, not one after the other.

    python tests/python/test_inbox_speed.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
import time
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-inbox-speed-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["JAVIS_SESSIONS_DB"] = str(Path(_STATE) / "sessions.db")
os.environ["BRAINS_DIR"] = str(Path(_STATE) / "brains")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import conversations  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


if _STATE not in str(conversations.DB_PATH):
    print(f"FAIL the inbox store is not in the temp dir: {conversations.DB_PATH}. STOP.")
    sys.exit(1)

# ---- 1. the time indexes --------------------------------------------------------------------------------------------------
db = conversations._conn()
idx = {r[1]: r[2] for r in db.execute("SELECT type, name, sql FROM sqlite_master WHERE type='index'").fetchall()}
check("messages are indexed by time", "ix_msg_time" in idx and "created_at" in str(idx.get("ix_msg_time")), idx.keys())
check("messages are indexed by chat then time", "ix_msg_conv_time" in idx
      and "conversation_id" in str(idx.get("ix_msg_conv_time")) and "created_at" in str(idx.get("ix_msg_conv_time")))
plan = " ".join(str(r[-1]) for r in db.execute(
    "EXPLAIN QUERY PLAN SELECT COUNT(*) FROM messages m WHERE m.created_at>=? AND m.sender_type='customer'", (0,)).fetchall())
check("counting messages since a time uses the index, not a full read", "ix_msg_time" in plan, plan)

# ---- 2. new chats ---------------------------------------------------------------------------------------------------------
DAY = 86400
T0 = time.time() - 40 * DAY


def put(chat, kind, ts, chat_type="private", text="hi"):
    conversations.ghi_su_kien({"channel": "telegram", "account_id": "acc1", "external_chat_id": chat, "chat_type": chat_type,
                               "sender_type": kind, "sender_id": "k" + chat, "sender_name": "Khách", "text": text,
                               "created_at": ts})


put("old", "customer", T0 + 1 * DAY)          # wrote long before the period
put("old", "customer", T0 + 31 * DAY)
put("new", "customer", T0 + 31 * DAY)         # first message inside the period
put("new", "ai", T0 + 31 * DAY + 60)
put("grp", "customer", T0 + 31 * DAY, chat_type="group")   # a group is never a "new chat"
put("late", "customer", T0 + 35 * DAY)        # first message after the period
since, until = T0 + 30 * DAY, T0 + 33 * DAY
st = conversations.insights(since, until)
check("a private chat whose first message is in the period is new, an older one or a group is not", st["new_chats"] == 1, st["new_chats"])
check("the period counts the customer messages in it", st["customer"] == 3 and st["ai"] == 1, (st["customer"], st["ai"]))
check("the A.I. answer is one wait of 60 seconds", st["waits"] == 1 and st["wait_avg"] == 60.0, (st["waits"], st["wait_avg"]))
check("an account filter keeps only that account", conversations.insights(since, until, "telegram:other")["customer"] == 0)

# ---- 3. the Stats tab cache -----------------------------------------------------------------------------------------------
conversations._insights_cache.clear()
now = T0 + 40 * DAY
closed = conversations.insights_cached(since, until, now=now)
put("new2", "customer", T0 + 32 * DAY)        # e.g. a history import into an ended period
check("an ended period is counted once and kept", conversations.insights_cached(since, until, now=now)["customer"] == closed["customer"])
check("the cache hands out copies", conversations.insights_cached(since, until, now=now) is not conversations.insights_cached(since, until, now=now))

run_since = T0 + 34 * DAY
first = conversations.insights_cached(run_since, now, now=now)
put("late", "customer", T0 + 36 * DAY)
check("the running period is kept a few seconds", conversations.insights_cached(run_since, now + 5, now=now + 5)["customer"] == first["customer"])
later = now + conversations.INSIGHTS_KEEP_OPEN + 1
check("then counted again, with the new message", conversations.insights_cached(run_since, later, now=later)["customer"] == first["customer"] + 1)

cid = conversations.conversation_id_of("telegram", "acc1", "new2")
conversations.delete_conversation(cid)
check("deleting a chat clears the cache", not conversations._insights_cache)
check("so the ended period is right again", conversations.insights_cached(since, until, now=now)["customer"] == closed["customer"])

for i in range(conversations.INSIGHTS_CACHE_MAX + 5):
    conversations.insights_cached(T0 + i, T0 + i + 1, now=now)
check("the cache stays small", len(conversations._insights_cache) <= conversations.INSIGHTS_CACHE_MAX, len(conversations._insights_cache))

# ---- 4. the inbox asks in parallel ----------------------------------------------------------------------------------------
js = (Path(ROOT) / "dashboard" / "conversations.js").read_text(encoding="utf-8")
body = js[js.index("function renderInbox("):js.index("function filterState(")]
check("the inbox does not wait for the accounts before asking for the list",
      "tai(false, tk)" in body and ".then(function () { paintHead(); tai();" not in body)

# ---- the routes still answer ----------------------------------------------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

cl = TestClient(main.app)
r = cl.get("/conversations?limit=40")
d = r.json()
check("GET /conversations still answers with the list and its counts",
      r.status_code == 200 and d.get("ok") and isinstance(d.get("items"), list) and "facets" in d and "stats" in d
      and "who_counts" in d and "tags" in d and "channels" in d and "phone_lookup" in d, d)
check("every row is named and flagged", all("bot_name" in it and "need_reply" in it and "who" in it for it in d["items"]))
r2 = cl.get("/conversations?limit=1&offset=1")
check("the next page carries only rows", r2.status_code == 200 and set(r2.json()) == {"ok", "items"}, r2.json().keys())
r3 = cl.get("/conversations/insights?days=7")
check("GET /conversations/insights still answers", r3.status_code == 200 and r3.json().get("ok") and "before" in r3.json(), r3.text[:200])

print("\n" + ("ALL OK" if not _fails else f"{len(_fails)} FAILED: {_fails}"))
sys.exit(1 if _fails else 0)
