"""The staff contact ("Người phụ trách") is gone, and its store goes with it (owner, 28/11/2026).

    python tests/run.py staff_contact_removed      (no network)

The feature shipped for two days (2026-11-26 to 28): a bot asked one chosen chat when only a person knew the answer.
The owner found little value in it and removed it. What this file pins:

1. An old bot record that still holds `staff_contact` reads back without it, and the form field is not patchable.
2. The store of the removed feature (`staff_requests.sqlite3`, customers' questions and staff answers) is deleted on
   start, with its SQLite side files, and a missing store is not an error.
3. Nothing in the server or dashboard still offers or reads the feature (`ask_staff`, `staff_contact`).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path
import json
import os
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-staff-gone-")
os.environ["JAVIS_STATE_DIR"] = _STATE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_store  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


# 1. An old record keeps reading, without the key.
store = Path(_STATE) / "chatbots.json"
store.write_text(json.dumps({"bots": [{"id": "b1", "name": "Shop", "channel": "telegram", "accounts": [],
                                        "staff_contact": {"account_id": "a1", "chat_id": "c1", "chat_type": "private",
                                                          "name": "Lan"}}]}), encoding="utf-8")
bot = chatbot_store.get_bot("b1") or {}
check("an old record still reads", bot.get("name") == "Shop", bot)
check("its staff_contact is dropped on read", "staff_contact" not in bot, bot)
check("staff_contact is not patchable any more", "staff_contact" not in chatbot_store._PATCHABLE)

# 2. The removed feature's store is deleted, side files too; a missing one is fine.
for suffix in ("", "-wal", "-shm"):
    (Path(_STATE) / f"staff_requests.sqlite3{suffix}").write_bytes(b"customer words")
check("the store is removed on start", chatbot_store.drop_staff_request_store() is True)
check("with its SQLite side files", not any(Path(_STATE).glob("staff_requests.sqlite3*")),
      list(Path(_STATE).glob("staff_requests.sqlite3*")))
check("a missing store is not an error", chatbot_store.drop_staff_request_store() is False)
main_src = (SERVER / "main.py").read_text(encoding="utf-8")
check("main.py runs the cleanup at start-up",
      'async def _drop_staff_request_store' in main_src and "chatbot_store.drop_staff_request_store" in main_src)

# 3. No trace of the feature left in code that runs.
check("staff_requests.py is gone", not (SERVER / "staff_requests.py").exists())
for rel in ("server/mcp_hub.py", "server/chatbot_runtime.py", "server/main.py", "server/telegram_bot.py",
            "server/channels/zalo_personal.py", "dashboard/chatbots.js"):
    src = (ROOT / rel).read_text(encoding="utf-8")
    check(f"{rel} neither offers nor reads the feature",
          "ask_staff" not in src and "staff_requests" not in src and "staff_contact" not in src)

if fails:
    print(f"\nFAIL {len(fails)}: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_staff_contact_removed: all pass")
