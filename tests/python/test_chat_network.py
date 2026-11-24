"""The network a chat came from (#1633): one generic `network` field on each conversation.

    python tests/run.py chat_network      (no network access)

A channel can reach several social networks: Messenger answers Facebook and Instagram through one Page, and a Store
pack can bridge TikTok, LinkedIn and more. Guarded here:
1. An old store gains the column, and its Messenger chats are filled once from the chat id ("ig:" / "igc:" Instagram,
   the rest Facebook); other channels stay empty.
2. A new message stores the network the event names (cleaned), else the channel's `network_of_chat` hook; a later
   message without one never wipes it.
3. The bot runtime passes `meta["network"]` on, so a channel can name it per message.
4. GET /conversations filters by `network` and counts each network in `facets.networks`; a malformed value is ignored.
5. Messenger's hook agrees with messenger_bot's prefixes.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-chat-network-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import conversations  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:300] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


if _STATE not in str(conversations.DB_PATH):
    print(f"FAIL the inbox store is not in the temp dir: {conversations.DB_PATH}. STOP.")
    sys.exit(1)

# ---- 1. An old store, from before the column ----
conversations.close()
db = sqlite3.connect(str(conversations.DB_PATH))
db.executescript("""
CREATE TABLE channel_accounts(id TEXT PRIMARY KEY, channel TEXT NOT NULL, external_account_id TEXT NOT NULL DEFAULT '',
  display_name TEXT NOT NULL DEFAULT '', bot_id TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'active',
  metadata_json TEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE conversations(id INTEGER PRIMARY KEY AUTOINCREMENT, channel_account_id TEXT NOT NULL, customer_id INTEGER,
  bot_id TEXT NOT NULL DEFAULT '', external_chat_id TEXT NOT NULL, chat_type TEXT NOT NULL DEFAULT 'private',
  title TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'open', mode TEXT NOT NULL DEFAULT 'ai',
  last_message TEXT NOT NULL DEFAULT '', last_message_at REAL, last_sender_type TEXT NOT NULL DEFAULT '',
  unread_count INTEGER NOT NULL DEFAULT 0, message_count INTEGER NOT NULL DEFAULT 0,
  metadata_json TEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL, updated_at REAL NOT NULL,
  UNIQUE(channel_account_id, external_chat_id));
INSERT INTO channel_accounts(id, channel, created_at, updated_at) VALUES('messenger:p1','messenger',1,1),('telegram:b1','telegram',1,1);
INSERT INTO conversations(channel_account_id, external_chat_id, created_at, updated_at) VALUES
  ('messenger:p1','ig:100',1,1),('messenger:p1','igc:200',1,1),('messenger:p1','cmt:300',1,1),('messenger:p1','400',1,1),
  ('telegram:b1','500',1,1);
""")
db.commit()
db.close()
rows = {r["external_chat_id"]: r.get("network") for r in conversations.danh_sach(limit=50)}
check("1. the column is added and old Messenger chats are filled", rows.get("ig:100") == "instagram"
      and rows.get("igc:200") == "instagram" and rows.get("cmt:300") == "facebook" and rows.get("400") == "facebook", rows)
check("1. a channel without the hook stays empty", rows.get("500") == "", rows)

# ---- 2. Writing ----
w = conversations.ghi_su_kien({"channel": "telegram", "account_id": "b1", "external_chat_id": "600", "text": "hi",
                               "network": " TikTok "})
check("2. the event's network is stored, cleaned", conversations.danh_sach(ids=[w["conversation_id"]])[0]["network"] == "tiktok")
conversations.ghi_su_kien({"channel": "telegram", "account_id": "b1", "external_chat_id": "600", "text": "again"})
check("2. a later message without one keeps it", conversations.danh_sach(ids=[w["conversation_id"]])[0]["network"] == "tiktok")
w2 = conversations.ghi_su_kien({"channel": "messenger", "account_id": "p1", "external_chat_id": "ig:700", "text": "x"})
check("2. a new Messenger chat gets its network from the hook",
      conversations.danh_sach(ids=[w2["conversation_id"]])[0]["network"] == "instagram")
w3 = conversations.ghi_su_kien({"channel": "telegram", "account_id": "b1", "external_chat_id": "800", "text": "x",
                                "network": "<script>"})
check("2. a malformed network is dropped", conversations.danh_sach(ids=[w3["conversation_id"]])[0]["network"] == "")
check("2. clean_network", conversations.clean_network("LinkedIn") == "linkedin" and conversations.clean_network("a b") == ""
      and conversations.clean_network("x" * 40) == "")

# ---- 3. The bot runtime passes it on ----
import chatbot_runtime  # noqa: E402
ev = chatbot_runtime._bot_event({"id": "bot1", "channel": "telegram"}, {"chat_id": "9", "network": "linkedin"})
check("3. _bot_event carries meta['network']", ev.get("network") == "linkedin", ev)
check("3. and nothing when the channel names none", chatbot_runtime._bot_event({"id": "bot1"}, {"chat_id": "9"})["network"] == "")

# ---- 4. The list route ----
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
c = TestClient(main.app, base_url="http://127.0.0.1:8080")
r = c.get("/conversations?limit=50&network=instagram").json()
got = sorted(i["external_chat_id"] for i in r.get("items", []))
check("4. network=instagram keeps the Instagram chats only", got == ["ig:100", "ig:700", "igc:200"], got)
check("4. facets.networks counts each network", (r.get("facets") or {}).get("networks") ==
      {"instagram": 3, "facebook": 2, "tiktok": 1}, (r.get("facets") or {}).get("networks"))
n_all = len(c.get("/conversations?limit=50").json()["items"])
check("4. a malformed network filter is ignored", len(c.get("/conversations?limit=50&network=Tik%20Tok").json()["items"]) == n_all)
check("4. every row carries its network", all("network" in i for i in r.get("items", [])))

# ---- 5. Messenger's hook and messenger_bot agree ----
import messenger_bot  # noqa: E402
from channels import messenger as messenger_channel  # noqa: E402
check("5. the hook's prefixes are messenger_bot's", set(messenger_channel._INSTAGRAM_PREFIXES) ==
      {messenger_bot.IG_PREFIX, messenger_bot.IG_COMMENT_PREFIX})

print("\n" + ("ALL OK" if not fails else f"{len(fails)} FAIL: {fails}"))
raise SystemExit(1 if fails else 0)
