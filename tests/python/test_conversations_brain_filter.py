"""Chatbot > Conversations shows the open brain's chats, like the Channels tab (#1243).

    python tests/run.py conversations_brain_filter      (no network)

The bug: GET /conversations had no `brain`. With "All channels" the dashboard sent no `account_ids`, so the default brain
still listed the chats of two Pages the owner had moved, with their bot, to another brain. The Channels tab already
filtered accounts by brain; only the list, its counts and its facets did not.

Pinned here:
  1. with `brain`, the chats of accounts assigned to ANOTHER brain are left out (list, total, who counts, facets, stats)
  2. the brain's own accounts, accounts with no brain, Zalo personal chats and chats of a deleted account stay
  3. the other brain sees its own chats, in either spelling of its key
  4. without `brain` every chat comes back, as before (internal callers, "all brains")
  5. the dashboard sends the open brain unless the Channels tab's "every brain" switch is on
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-conv-brain-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["JAVIS_SESSIONS_DB"] = str(Path(_STATE) / "sessions.db")
os.environ["BRAINS_DIR"] = str(Path(_STATE) / "brains")
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channel_accounts  # noqa: E402
import conversations  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:300] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


if _STATE not in str(conversations.DB_PATH):
    print(f"FAIL the inbox store is not in the temp dir: {conversations.DB_PATH}. STOP.")
    sys.exit(1)

from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402

cl = TestClient(main.app)
brains = Path(os.environ["BRAINS_DIR"])
davis = brains / "Brain Davis Looptours"
davis.mkdir(parents=True, exist_ok=True)

mine, _ = channel_accounts.create_account({"channel": "telegram", "token": "111:aaa", "label": "Shop chính",
                                           "bot_username": "chinh_bot", "brain": "brain"})
moved, _ = channel_accounts.create_account({"channel": "telegram", "token": "222:bbb", "label": "Fanpage Davis",
                                            "bot_username": "davis_bot", "brain": str(davis)})
loose, _ = channel_accounts.create_account({"channel": "telegram", "token": "333:ccc", "label": "Chưa gán",
                                            "bot_username": "loose_bot"})
check("(setup) three accounts", mine and moved and loose)


def say(channel, account_id, chat, text):
    conversations.ghi_su_kien({"channel": channel, "account_id": account_id, "external_chat_id": chat,
                               "chat_type": "private", "sender_type": "customer", "sender_id": "k" + chat,
                               "sender_name": "Khách " + chat, "text": text})


say("telegram", mine, "c-mine", "Shop còn hàng không?")
say("telegram", moved, "c-davis", "Tour Đà Lạt giá bao nhiêu?")
say("telegram", loose, "c-loose", "Xin chào")
say("zalo_personal", "zp_conn1", "c-zalo", "Anh ơi")
say("telegram", "acc_deleted", "c-gone", "Tin cũ")


def chats(url):
    d = cl.get(url).json()
    return {x["external_chat_id"] for x in d.get("items", [])}, d


everything = {"c-mine", "c-davis", "c-loose", "c-zalo", "c-gone"}

# 4. no brain: as before
got, d_all = chats("/conversations?limit=50")
check("4. without brain every chat comes back", everything <= got, got)

# 1 + 2. default brain
got, d = chats("/conversations?limit=50&brain=brain")
check("1. the default brain no longer lists the moved Page's chat", "c-davis" not in got, got)
check("2. it keeps its own, the unassigned account, Zalo personal and a deleted account's chat",
      {"c-mine", "c-loose", "c-zalo", "c-gone"} <= got, got)
check("1. total counts the same chats as the list", d.get("total") == len(got), (d.get("total"), got))
check("1. the facets leave the moved Page out", d["facets"]["tong"] == d_all["facets"]["tong"] - 1,
      (d["facets"]["tong"], d_all["facets"]["tong"]))
check("1. the head stats leave it out too", d["stats"]["chua_doc"] == d_all["stats"]["chua_doc"] - 1,
      (d["stats"], d_all["stats"]))
you = d["who_counts"].get("you_by_account") or {}
check("1. 'needs you' per account does not count the moved Page", f"telegram:{moved}" not in you, you)
got_who, _ = chats("/conversations?limit=50&brain=brain&who=you")
check("1. the 'needs you' filter leaves it out as well", "c-davis" not in got_who, got_who)

# 3. the other brain
got, _ = chats("/conversations?limit=50&brain=" + str(davis))
check("3. Brain Davis lists its Page's chat", "c-davis" in got, got)
check("3. and not the default brain's own account", "c-mine" not in got, got)
got2, _ = chats("/conversations?limit=50&brain=path:" + str(davis))
check("3. the 'path:' spelling of the same brain gives the same list", got2 == got, (got2, got))

# helper
check("helper: other brains' keys for the default brain", channel_accounts.keys_of_other_brains("brain") == [f"telegram:{moved}"],
      channel_accounts.keys_of_other_brains("brain"))
check("helper: empty brain means no filter", channel_accounts.keys_of_other_brains("") == [])

# 5. dashboard
js = (ROOT / "dashboard" / "conversations.js").read_text(encoding="utf-8")
check("5. the list URL carries the open brain", "brainParam()" in js and 'function brainParam() { return _tkMoiBrain ? "" : "&brain="' in js)
check("5. the 'needs you' refresh carries it too", 'api("/conversations?limit=1" + brainParam())' in js)

for rel in ("server/conversations.py", "server/channel_accounts.py", "server/routes/conversations.py",
            "dashboard/conversations.js", "tests/python/test_conversations_brain_filter.py"):
    s = (ROOT / rel).read_text(encoding="utf-8")
    check(f"{rel} has no long dash", chr(0x2014) not in s and chr(0x2013) not in s)

if fails:
    raise SystemExit(f"{len(fails)} check(s) failed: {fails}")
print("all ok")
