"""Chatbot v5 "Needs you" and the bot of a logged chat (owner, 2026-10-28).

  1. A chat leaves "Needs you" once the owner opens it (it is read); a new customer message brings it back.
  2. A friend-request notice ("X đã đồng ý kết bạn", "Bạn vừa kết bạn với X") is not a customer waiting.
  3. A chat the channel logged without a bot (Zalo "record chats") belongs to the bot on duty for its account, at
     ingest and, for chats logged before, through `fill_missing_bots`. So the bar offers "Allow here", never
     "Create an A.I. for this channel", on a nick that has one.

    python tests/python/test_chatbot_v5_needs_you.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-cbv5n-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["JAVIS_SESSIONS_DB"] = str(Path(_STATE) / "sessions.db")
os.environ["BRAINS_DIR"] = str(Path(_STATE) / "brains")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channel_accounts  # noqa: E402
import chatbot_store  # noqa: E402
import conversations  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


if _STATE not in str(conversations.DB_PATH):
    print(f"FAIL the inbox store is not in the temp dir: {conversations.DB_PATH}. STOP.")
    sys.exit(1)

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

cl = TestClient(main.app)

a1, e1 = channel_accounts.create_account({"channel": "telegram", "token": "111:aaa", "label": "Page Một", "bot_username": "mot_bot"})
check("(setup) an account", a1, e1)
b1, _ = chatbot_store.create_bot({"name": "Lan", "agent_slug": "lan", "brain": "b", "account_ids": [a1]})


def put(chat, kind, text, bot=""):
    return conversations.ghi_su_kien({"channel": "telegram", "account_id": a1, "external_chat_id": chat, "chat_type": "private",
                                      "sender_type": kind, "sender_id": "k" + chat, "sender_name": "Khách", "text": text,
                                      "bot_id": bot})


def row(chat):
    items = cl.get("/conversations?limit=100").json()["items"]
    return next(x for x in items if x["external_chat_id"] == chat)


# ---- 3. a logged chat gets the account's bot -----------------------------------------------------------------------------
put("701", "customer", "Shop ơi còn hàng không?")
check("a chat logged without a bot takes the bot on duty for its account", row("701")["bot_id"] == b1, row("701")["bot_id"])
conversations.set_account_bot("telegram:" + a1, "")
check("(setup) an older chat left without a bot", row("701")["bot_id"] == "")
check("fill_missing_bots gives it back the account's bot", conversations.fill_missing_bots() >= 1 and row("701")["bot_id"] == b1)
check("fill_missing_bots changes nothing the second time", conversations.fill_missing_bots() == 0)
r = row("701")
check("the bar knows the bot, so it never offers Create an A.I. on this account", r["bot_id"] == b1 and r["bot_name"] == "Lan", r)

# ---- 1. read leaves "Needs you" ------------------------------------------------------------------------------------------
check("an unread customer message with nobody on it (bot off): Needs you", r["who"] == "you" and r["who_code"] == "bot_off_waiting", r["who_code"])
cl.post(f"/conversations/{r['id']}/read")
r = row("701")
check("opened (read): out of Needs you, logged only", r["who"] == "log", r["who_code"])
put("701", "customer", "Alo shop?")
check("a new customer message brings it back", row("701")["who"] == "you")

# ---- 2. friend-request notices ------------------------------------------------------------------------------------------
put("702", "customer", "Linh Nguyễn đã đồng ý kết bạn")
put("703", "customer", "Bạn vừa kết bạn với Y Tran")
check("'đã đồng ý kết bạn' is not a customer waiting", row("702")["who"] != "you", row("702")["who_code"])
check("'Bạn vừa kết bạn với' is not a customer waiting", row("703")["who"] != "you", row("703")["who_code"])
check("a real question after it is", put("703", "customer", "Cho em hỏi giá") and row("703")["who"] == "you")
check("the rule itself", conversations.la_tin_ket_ban("Uyen Le đã đồng ý kết bạn") and
      not conversations.la_tin_ket_ban("Kết bạn với shop thì có giảm giá không?"))
counts = cl.get("/conversations?limit=1").json()["who_counts"]
check("the Needs you count follows the same rule", counts["you"] == 2, counts)

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("all ok")
