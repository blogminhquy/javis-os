"""Chatbot v5, phase 3 (docs/dev/2026-10-chatbot-v5-spec.md sections 7 and 9): the server side of the Channels and
Stats tabs.

  1. POST /channels/accounts/{id}/bot puts one bot on duty for an account: the account leaves the bot that had it (that
     bot is switched off when it was its last account), "" takes it off every bot, unknown ids are 404.
  2. POST /channels/no-bot marks an account "No bot needed": GET /channels/accounts says so, its chats read
     "logged only / no_bot_wanted" instead of "no bot", and putting a bot on it clears the mark.
  3. conversations.insights counts A.I., owner and customer messages per channel and per bot and the average wait for
     a first answer; GET /conversations/insights compares the period with the one before.

    python tests/python/test_chatbot_v5_channels.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-cbv5c-")
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
import routes.channels as ch_routes  # noqa: E402

RESTARTED, STOPPED = [], []
ch_routes._DEPS.restart_bot = lambda bid: RESTARTED.append(bid)
ch_routes._DEPS.stop_bot = lambda bid: STOPPED.append(bid)
cl = TestClient(main.app)

a1, e1 = channel_accounts.create_account({"channel": "telegram", "token": "111:aaa", "label": "Page Một", "bot_username": "mot_bot"})
a2, e2 = channel_accounts.create_account({"channel": "telegram", "token": "222:bbb", "label": "Page Hai", "bot_username": "hai_bot"})
check("(setup) two accounts", a1 and a2, (e1, e2))
b1, _ = chatbot_store.create_bot({"name": "Lan", "agent_slug": "lan", "brain": "b", "account_ids": [a1]})
b2, _ = chatbot_store.create_bot({"name": "Hoa", "agent_slug": "hoa", "brain": "b"})
chatbot_store.set_enabled(b1, True)
check("(setup) Lan serves Page Một", chatbot_store.account_ids_of(chatbot_store.get_bot(b1)) == [a1])

# ---- 1. one bot per account --------------------------------------------------------------------------------------------
r = cl.post(f"/channels/accounts/{a1}/bot", data={"bot_id": b2}).json()
check("moving Page Một to Hoa: ok", r.get("ok"), r)
check("Page Một is now Hoa's, and no longer Lan's", chatbot_store.account_ids_of(chatbot_store.get_bot(b2)) == [a1]
      and chatbot_store.account_ids_of(chatbot_store.get_bot(b1)) == [], (chatbot_store.get_bot(b1), chatbot_store.get_bot(b2)))
check("Lan lost its last account: switched off and its poller stopped, and the answer names it",
      r.get("bot_tat") == "Lan" and not chatbot_store.get_bot(b1).get("enabled") and b1 in STOPPED, (r, STOPPED))
r = cl.post(f"/channels/accounts/{a1}/bot", data={"bot_id": b2}).json()
check("the same bot again changes nothing", r.get("ok") and r.get("bot_tat") == "", r)
chatbot_store.set_enabled(b2, True)
chatbot_store.update_bot(b2, {"account_ids": [a1, a2]})
r = cl.post(f"/channels/accounts/{a2}/bot", data={"bot_id": b1}).json()
check("a bot keeping other accounts reloads its poller instead of stopping", r.get("ok") and b2 in RESTARTED and
      chatbot_store.get_bot(b2).get("enabled") and chatbot_store.account_ids_of(chatbot_store.get_bot(b2)) == [a1], (r, RESTARTED))
r = cl.post(f"/channels/accounts/{a2}/bot", data={"bot_id": ""}).json()
check("an empty bot takes the account off every bot", r.get("ok") and not chatbot_store.bots_using_account(a2), r)
check("unknown account: 404", cl.post("/channels/accounts/acc_nope/bot", data={"bot_id": b1}).status_code == 404)
check("unknown bot: 404, nothing moved", cl.post(f"/channels/accounts/{a1}/bot", data={"bot_id": "bot_nope"}).status_code == 404
      and chatbot_store.bots_using_account(a1)[0]["id"] == b2)

# ---- 2. "No bot needed" ------------------------------------------------------------------------------------------------
key2 = f"telegram:{a2}"
r = cl.post("/channels/no-bot", data={"account_key": key2, "on": "1"}).json()
check("mark Page Hai 'No bot needed'", r.get("ok") and r.get("no_bot") is True, r)
acc = {a["account_key"]: a for a in cl.get("/channels/accounts").json()["accounts"]}
check("GET /channels/accounts says so, and only for that account", acc[key2]["no_bot"] is True and acc[f"telegram:{a1}"]["no_bot"] is False,
      {k: v.get("no_bot") for k, v in acc.items()})
conversations.ghi_su_kien({"channel": "telegram", "account_id": a2, "external_chat_id": "-77", "chat_type": "group",
                           "chat_title": "Nhóm bạn bè", "sender_type": "customer", "sender_id": "u1", "sender_name": "Tú",
                           "text": "Chiều đi cà phê không"})
row = next(x for x in cl.get("/conversations?limit=50").json()["items"] if x["external_chat_id"] == "-77")
check("its chats read 'logged only' with no_bot_wanted (not 'no bot yet')", row["who"] == "log" and row["who_code"] == "no_bot_wanted", row)
check("unknown account key: 404", cl.post("/channels/no-bot", data={"account_key": "telegram:nope"}).status_code == 404)
cl.post(f"/channels/accounts/{a2}/bot", data={"bot_id": b1})
acc = {a["account_key"]: a for a in cl.get("/channels/accounts").json()["accounts"]}
check("putting a bot on it clears the mark", acc[key2]["no_bot"] is False, acc[key2])
row = next(x for x in cl.get("/conversations?limit=50").json()["items"] if x["external_chat_id"] == "-77")
check("its chats follow the bot now on duty (the per-chat A.I. switch works right away)", row["bot_id"] == b1, row)
check("switching the A.I. on in that chat works", cl.post(f"/conversations/{row['id']}/ai", data={"on": "1"}).json().get("ok"))
cl.post(f"/channels/accounts/{a2}/bot", data={"bot_id": ""})
row = next(x for x in cl.get("/conversations?limit=50").json()["items"] if x["external_chat_id"] == "-77")
check("taking the bot off the account takes it off its chats", row["bot_id"] == "" and row["who_code"] in ("no_bot", "waiting"), row)
cl.post(f"/channels/accounts/{a2}/bot", data={"bot_id": b1})

# ---- 3. stats ----------------------------------------------------------------------------------------------------------
import time  # noqa: E402

t0 = time.time()


def put(chat, kind, text, bot=""):
    conversations.ghi_su_kien({"channel": "telegram", "account_id": a1, "external_chat_id": chat, "chat_type": "private",
                               "sender_type": kind, "sender_id": "k" + chat, "sender_name": "Khách", "text": text, "bot_id": bot})


put("501", "customer", "Còn hàng không?")
put("501", "customer", "Shop ơi?")
put("501", "ai", "Dạ còn ạ", bot=b2)
put("502", "customer", "Giá sao?")
put("502", "human", "120k ạ")
st = conversations.insights(t0, time.time() + 1)
check("insights: A.I., owner and customer messages", st["ai"] == 1 and st["human"] == 1 and st["customer"] == 3, st)
check("insights: two waits answered (a run of customer messages is one wait)", st["waits"] == 2 and st["wait_avg"] is not None, st)
check("insights: per channel and per bot", st["by_channel"]["telegram"]["ai"] == 1 and st["by_bot"].get(b2) == 1, st)
check("insights: an empty period is all zeros, no average", conversations.insights(0, 1)["ai"] == 0 and conversations.insights(0, 1)["wait_avg"] is None)
r = cl.get("/conversations/insights?days=7").json()
check("GET /conversations/insights: this period, the one before, needs-you now, bot names", r.get("ok") and r["days"] == 7 and
      r["now"]["ai"] >= 1 and "before" in r and isinstance(r["needs_you"], int) and r["bot_names"].get(b2) == "Hoa", r)
check("GET /conversations/insights: an odd day count falls back to 7", cl.get("/conversations/insights?days=5").json()["days"] == 7)
check("GET /conversations/insights: today only", cl.get("/conversations/insights?days=1").json()["days"] == 1)
today = time.strftime("%Y-%m-%d")
r = cl.get(f"/conversations/insights?from={today}&to={today}").json()
check("GET /conversations/insights: a picked range (today) counts today's messages", r["days"] == 1 and r["now"]["ai"] >= 1, r)
r = cl.get("/conversations/insights?from=2001-01-01&to=2001-01-31").json()
check("GET /conversations/insights: an old range is empty, its 'before' is the 31 days before it", r["days"] == 31 and r["now"]["ai"] == 0, r)

# ---- 4. more inbox filters: time range, who wrote last, pinned ----------------------------------------------------------
ids = lambda q: {x["external_chat_id"] for x in cl.get("/conversations?limit=100" + q).json()["items"]}
check("from/to today keeps today's chats", {"501", "502"} <= ids(f"&from={today}&to={today}"))
check("an old range keeps nothing", ids("&from=2001-01-01&to=2001-01-02") == set())
check("ends given backwards are swapped, an unreadable end stays open", {"501", "502"} <= ids(f"&from={today}&to=2001-01-01") and
      {"501", "502"} <= ids("&from=xx"))
check("last message by the A.I. / by you / by the customer", "501" in ids("&last_by=ai") and "502" not in ids("&last_by=ai") and
      "502" in ids("&last_by=human") and "501" not in ids("&last_by=customer"))
check("an odd last_by is ignored", {"501", "502"} <= ids("&last_by=boss"))
c501 = next(x for x in cl.get("/conversations?limit=100").json()["items"] if x["external_chat_id"] == "501")
cl.post(f"/conversations/{c501['id']}/pin", data={"pinned": "1"})
check("pinned only", ids("&pinned=1") == {"501"}, ids("&pinned=1"))
r = cl.get("/conversations?limit=5&pinned=1&who=").json()
check("filters keep the picker and tab counts whole-inbox", r["who_counts"]["you_total"] >= r["who_counts"]["you"], r["who_counts"])

# ---- 5. paging an account's chats (Channels tab, owner 2026-10-28) -----------------------------------------------------
everything = cl.get("/conversations?limit=200").json()
p1 = cl.get("/conversations?limit=1").json()
p2 = cl.get("/conversations?limit=1&offset=1").json()
check("page 0 says how many match in all, later pages repeat nothing", p1["total"] == len(everything["items"]) >= 2 and
      p2.get("total") is None and p1["items"][0]["id"] != p2["items"][0]["id"], (p1["total"], len(everything["items"])))
check("the total follows the filters", cl.get("/conversations?limit=1&pinned=1").json()["total"] == 1)

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("all ok")
