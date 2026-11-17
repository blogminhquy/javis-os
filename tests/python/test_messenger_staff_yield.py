"""Messenger: the bot steps aside in a chat right after the owner or staff replied in it.

    python tests/run.py messenger_staff_yield

No network. What is guarded:

  1. A person's reply (sender "human": a staff echo from Messenger/Business Suite, or the Javis inbox) makes the bot quiet
     in that private chat for the bot's `nhuong_tay_phut` minutes, default 10; afterwards it answers again.
  2. `nhuong_tay_phut = 0` never yields; other chats, other channels, Page comments and a turn the owner asked for from
     the inbox (`_kenh`) are never held.
  3. The bot's own replies ("ai") never make it yield.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-messenger-yield-")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_runtime  # noqa: E402
import conversations  # noqa: E402

_fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  [{detail}]"))
    if not ok:
        _fails.append(name)


ACC = "acc_yield"
cfg = {"id": "bot_yield", "name": "Bot", "channel": "messenger", "accounts": []}
base = {"platform": "messenger", "chat_id": "900", "chat_type": "private", "chat_title": "", "user_id": "900",
        "user_name": "Khách", "username": "Khách", "account_id": ACC}


def write(sender, text, mid, at, chat="900"):
    conversations.ghi_su_kien({
        "channel": "messenger", "account_id": ACC, "account_name": "Bot", "bot_id": "bot_yield",
        "external_chat_id": chat, "chat_type": "private", "sender_type": sender, "text": text,
        "external_message_id": mid, "created_at": at})


def held(c=None, meta=None, now=None, channel="messenger"):
    return chatbot_runtime.staff_yield_active(c or cfg, meta or base, channel, ACC, now=now)


t0 = time.time()
write("customer", "chào shop", "y1", t0 - 3600)
check("a chat no person replied in is answered", not held())

write("ai", "Dạ shop chào anh/chị", "y2", t0 - 60)
check("the bot's own reply never makes it step aside", not held())

write("human", "Dạ có nha", "y3", t0 - 120)
check("a staff reply 2 minutes ago holds the bot (default 10 minutes)", held())
check("after the default 10 minutes the bot answers again", not held(now=t0 + 9 * 60))
check("the bot's own minutes are used", held(dict(cfg, nhuong_tay_phut=30), now=t0 + 20 * 60)
      and not held(dict(cfg, nhuong_tay_phut=30), now=t0 + 29 * 60))
check("0 minutes never steps aside", not held(dict(cfg, nhuong_tay_phut=0)))
check("another chat is not held", not held(meta=dict(base, chat_id="901", user_id="901")))
check("a Page comment is not held", not held(meta=dict(base, comment=True)))
check("a turn the owner asked for from the inbox is not held", not held(meta=dict(base, _kenh="messenger")))
check("other channels keep their own rules", not held(channel="telegram"))

if _fails:
    print(f"\n{len(_fails)} FAILED")
    sys.exit(1)
print("\nall ok")
