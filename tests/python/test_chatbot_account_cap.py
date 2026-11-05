"""How many channel accounts one bot may serve (owner 2026-11-04: a shop with 26 Fanpages wants ONE bot).

  1. The cap is per channel: Messenger (Facebook Pages, Instagram rides on the Page) takes 100, a channel that polls
     or holds a session per account (Telegram here) keeps 20.
  2. Over the cap is REFUSED with a message naming the channel. Before this the list was cut to its first 20 without a
     word, so ticking 26 Pages saved 20 and 6 Pages were left with no bot while the form said "saved".
  3. The Channels tab route (POST /channels/accounts/{id}/bot) follows the same per-channel cap.
  4. Creating a bot with a pasted token over the cap is refused BEFORE the account is created (no stray account).

    python tests/python/test_chatbot_account_cap.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-cbcap-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["JAVIS_SESSIONS_DB"] = str(Path(_STATE) / "sessions.db")
os.environ["BRAINS_DIR"] = str(Path(_STATE) / "brains")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channel_accounts  # noqa: E402
import channels  # noqa: E402
import chatbot_store  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


def page(i):
    aid, loi = channel_accounts.create_account({"channel": "messenger", "label": f"Fanpage {i}",
                                                "token": f"10000{i:03d} EAAtoken{i} secret{i}"})
    assert aid, loi
    return aid


def tele(i):
    aid, loi = channel_accounts.create_account({"channel": "telegram", "label": f"Bot {i}",
                                                "token": f"{900 + i}:tok{i}", "bot_username": f"b{i}_bot"})
    assert aid, loi
    return aid


# ---- 1. the cap per channel --------------------------------------------------------------------------------------------
check("Messenger declares 100", channels.max_accounts_per_bot("messenger") == 100)
check("Telegram keeps the default 20", channels.max_accounts_per_bot("telegram") == 20)
check("personal Zalo keeps the default 20", channels.max_accounts_per_bot("zalo_personal") == 20)
check("an unknown channel gets the default", channels.max_accounts_per_bot("nope") == 20)

pages = [page(i) for i in range(101)]
teles = [tele(i) for i in range(21)]

b, loi = chatbot_store.create_bot({"name": "Trợ lý trực 24/24", "agent_slug": "lan", "brain": "b",
                                   "account_ids": pages[:26]})
check("one bot takes all 26 Fanpages", b and len(chatbot_store.account_ids_of(chatbot_store.get_bot(b))) == 26, loi)
ok, loi = chatbot_store.update_bot(b, {"account_ids": pages[:100]})
check("and up to 100", ok and len(chatbot_store.account_ids_of(chatbot_store.get_bot(b))) == 100, loi)

# ---- 2. over the cap is refused, nothing is cut ------------------------------------------------------------------------
ok, loi = chatbot_store.update_bot(b, {"account_ids": pages[:101]})
check("101 Fanpages: refused, with the channel and the count in the message",
      not ok and "100" in loi and "101" in loi and "Messenger" in loi, loi)
check("the bot keeps its 100 Pages (nothing cut, nothing lost)",
      len(chatbot_store.account_ids_of(chatbot_store.get_bot(b))) == 100)
b2, loi = chatbot_store.create_bot({"name": "Quá tải", "agent_slug": "lan", "brain": "b", "account_ids": teles[:21]})
check("creating a bot with 21 Telegram bots: refused, not cut to 20", b2 is None and "21" in loi, loi)
ok, loi = chatbot_store.update_bot(b, {"account_ids": pages[:30] + teles[:20]})
check("30 Pages + 20 Telegram bots on one bot: each channel counted on its own", ok, loi)
ok, loi = chatbot_store.update_bot(b, {"account_ids": pages[:5] + teles[:21]})
check("21 Telegram bots: refused even though the bot has room for Pages", not ok and "20" in loi and "21" in loi, loi)
check("and the bot is left as it was", len(chatbot_store.account_ids_of(chatbot_store.get_bot(b))) == 50)

# ---- 3. the Channels tab route -----------------------------------------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
import routes.channels as ch_routes  # noqa: E402

ch_routes._DEPS.restart_bot = lambda bid: None
ch_routes._DEPS.stop_bot = lambda bid: None
cl = TestClient(main.app)

chatbot_store.update_bot(b, {"account_ids": pages[:20] + teles[:20]})
r = cl.post(f"/channels/accounts/{pages[20]}/bot", data={"bot_id": b})
check("the 21st Fanpage moves onto the bot from the Channels tab (the old 20 cap is gone)",
      r.status_code == 200 and r.json().get("ok") and pages[20] in chatbot_store.account_ids_of(chatbot_store.get_bot(b)),
      r.text)
r = cl.post(f"/channels/accounts/{teles[20]}/bot", data={"bot_id": b})
check("the 21st Telegram bot is refused with the channel's cap", r.status_code == 400 and "20" in r.text, r.text)
check("and stays off the bot", teles[20] not in chatbot_store.account_ids_of(chatbot_store.get_bot(b)))
chatbot_store.update_bot(b, {"account_ids": pages[:100]})
r = cl.post(f"/channels/accounts/{pages[100]}/bot", data={"bot_id": b})
check("the 101st Fanpage is refused", r.status_code == 400 and "100" in r.text, r.text)

# ---- 4. a pasted token over the cap leaves no stray account ------------------------------------------------------------
truoc = len(channel_accounts.list_accounts())
b3, loi = chatbot_store.create_bot({"name": "Token thừa", "agent_slug": "lan", "brain": "b", "account_ids": teles[:20],
                                    "channel": "telegram", "token": "999:moi", "bot_username": "moi_bot"})
check("20 Telegram bots ticked + a new token: refused", b3 is None and "20" in loi, loi)
check("and no account was created for that token", len(channel_accounts.list_accounts()) == truoc)

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("all ok")
