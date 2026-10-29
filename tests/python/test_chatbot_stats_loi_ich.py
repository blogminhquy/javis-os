"""Stats tab benefit numbers (0.399.0; owner, 2026-10-29: "thêm được chỉ số nào cho người dùng cảm thấy được nhiều lợi ích
nhất khi sử dụng chatbot của javis").

    python tests/python/test_chatbot_stats_loi_ich.py

Covers `conversations.insights`: the typical (median) wait when the A.I. answered first and when the owner did, A.I.
answers while the owner rests (21:00 to 07:00 in the brain's time zone), chats a customer wrote in, private chats that
are new in the period (an old chat with a new message is not), and customer messages per hour. No network, no model.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-stats-loi-ich-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["JAVIS_SESSIONS_DB"] = str(Path(_STATE) / "sessions.db")
os.environ["BRAINS_DIR"] = str(Path(_STATE) / "brains")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import conversations  # noqa: E402
import localefmt  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


if _STATE not in str(conversations.DB_PATH):
    print(f"FAIL the inbox store is not in the temp dir: {conversations.DB_PATH}. STOP.")
    sys.exit(1)

TZ = localefmt.tz()


def luc(d, h, m=0, s=0):
    """A timestamp at day `d` of a fixed month, hh:mm:ss in the brain's time zone."""
    return datetime(2026, 10, d, h, m, s, tzinfo=TZ).timestamp()


n = 0


def put(chat, kind, ts, ctype="private", acc="acc1"):
    global n
    n += 1
    r = conversations.ghi_su_kien({"channel": "telegram", "account_id": acc, "external_chat_id": chat, "chat_type": ctype,
                                   "sender_type": kind, "sender_id": "k" + chat, "sender_name": "Khách", "text": "tin " + str(n),
                                   "external_message_id": "m" + str(n), "created_at": ts})
    assert r.get("ok"), r


# An old chat from before the period: it must not count as new when it writes again.
put("cu", "customer", luc(1, 10))
put("cu", "human", luc(1, 10, 5))
# The period: 20 to 26 October.
put("cu", "customer", luc(21, 9))                   # old chat, new message: a chat served, not a new one
put("cu", "human", luc(21, 9, 10))                  # owner answers after 10 minutes
put("a", "customer", luc(22, 23))                   # a new chat at 23:00
put("a", "ai", luc(22, 23, 0, 20))                  # A.I. answers after 20 seconds, while the owner rests
put("b", "customer", luc(23, 6, 30))                # a new chat at 06:30
put("b", "customer", luc(23, 6, 31))                # same waiting run: one wait, two customer messages
put("b", "ai", luc(23, 6, 31, 40))                  # A.I. after 100 seconds from the first message, still rest time
put("c", "customer", luc(24, 14))                   # a new chat in the afternoon
put("c", "ai", luc(24, 14, 0, 30))                  # A.I. after 30 seconds, working hours
put("c", "customer", luc(24, 15))
put("c", "human", luc(24, 15, 30))                  # owner after 30 minutes
put("g", "customer", luc(25, 20), ctype="group")    # a group is never a "new customer"
put("g", "ai", luc(25, 21, 30), ctype="group")      # 21:30 counts as rest time

st = conversations.insights(luc(20, 0), luc(27, 0))
check("counts: A.I., owner, customer messages", (st["ai"], st["human"], st["customer"]) == (4, 2, 7), st)
check("the A.I.'s typical first-answer wait is the median of its waits (20, 30, 100 s and the group's 90 min)",
      st["waits_ai"] == 4 and st["wait_ai"] == (30 + 100) / 2, (st["wait_ai"], st["waits_ai"]))
check("the owner's typical first-answer wait (10 and 30 minutes)", st["waits_human"] == 2 and st["wait_human"] == 1200.0,
      (st["wait_human"], st["waits_human"]))
check("A.I. answers while the owner rests: 23:00, 06:31 and 21:30, not 14:00", st["ai_rest"] == 3, st["ai_rest"])
check("chats a customer wrote in, old ones included", st["chats"] == 5, st["chats"])
check("new chats: private ones whose first message is in the period, not the old one, not the group", st["new_chats"] == 3,
      st["new_chats"])
check("customer messages per hour, in the brain's time zone", len(st["hours"]) == 24 and st["hours"][6] == 2 and st["hours"][23] == 1 and
      st["hours"][9] == 1 and st["hours"][14] == 1 and st["hours"][15] == 1 and st["hours"][20] == 1 and sum(st["hours"]) == 7,
      st["hours"])
check("the old average stays for the 'before' comparison", st["waits"] == 6 and st["wait_avg"] is not None, st)
empty = conversations.insights(luc(2, 0), luc(3, 0))
check("an empty period: zeros and no medians", empty["ai"] == 0 and empty["wait_ai"] is None and empty["wait_human"] is None and
      empty["ai_rest"] == 0 and empty["chats"] == 0 and empty["new_chats"] == 0 and sum(empty["hours"]) == 0, empty)
check("rest hours are 21:00 to 07:00", (conversations.NGHI_TU, conversations.NGHI_DEN) == (21, 7))

# 0.401.0 (owner, 2026-10-29: "ở nick Javis Vũ anh không trả lời tý nào mà nó tính 45% câu do A.I. lo"): a second account
# answered by hand must not lower the first account's A.I. share.
put("x", "customer", luc(22, 10), acc="acc2")
put("x", "human", luc(22, 10, 1), acc="acc2")
put("x", "human", luc(22, 10, 2), acc="acc2")
put("y", "customer", luc(23, 11), acc="acc2")
put("y", "ai", luc(23, 11, 0, 10), acc="acc2")
tat_ca = conversations.insights(luc(20, 0), luc(27, 0))
check("every account together: both accounts' answers", (tat_ca["ai"], tat_ca["human"], tat_ca["customer"]) == (5, 4, 9),
      (tat_ca["ai"], tat_ca["human"], tat_ca["customer"]))
check("per account: each account its own A.I., hand and customer counts",
      tat_ca["by_account"].get("telegram:acc1") == {"customer": 7, "ai": 4, "human": 2} and
      tat_ca["by_account"].get("telegram:acc2") == {"customer": 2, "ai": 1, "human": 2}, tat_ca["by_account"])
mot = conversations.insights(luc(20, 0), luc(27, 0), "telegram:acc2")
check("one account: only its messages, chats, new chats and waits", (mot["ai"], mot["human"], mot["customer"], mot["chats"], mot["new_chats"]) ==
      (1, 2, 2, 2, 2) and mot["waits_human"] == 1 and mot["waits_ai"] == 1 and list(mot["by_account"]) == ["telegram:acc2"],
      (mot["ai"], mot["human"], mot["customer"], mot["chats"], mot["new_chats"], mot["by_account"]))
check("the account picker lists every inbox account by name", {a["id"] for a in conversations.stats_accounts()} >=
      {"telegram:acc1", "telegram:acc2"})

print()
if _fails:
    raise SystemExit(f"FAIL {len(_fails)}: " + "; ".join(_fails[:5]))
print("TẤT CẢ PASS")
