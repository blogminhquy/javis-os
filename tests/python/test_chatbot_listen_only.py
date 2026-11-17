"""Chatbot listen-only mode (`listen_only`).

    python tests/run.py chatbot_listen_only      (no network)

An owner wants Javis to READ a Page's (or any channel's) customer inbox without the bot ever answering. Before this
mode the only way was active hours squeezed to one minute a day, and the bot still answered in that minute. Guarded:

  1. STORE. Off by default and for old records; create and update set it; it is in the edit whitelist.
  2. THE GATE. `_ly_do_im` says "listen_only" at every hour, after the audience rules.
  3. THE INBOX. A customer message is written to the inbox, the engine is never reached, the try panel reports it.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from datetime import datetime

_STATE = tempfile.mkdtemp(prefix="javis-listen-only-")
os.environ["JAVIS_STATE_DIR"] = _STATE
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_runtime  # noqa: E402
import chatbot_store  # noqa: E402
import conversations  # noqa: E402
import localefmt  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        _fails.append(name)


if _STATE not in str(chatbot_store.STORE_PATH):
    print(f"FAIL store is not in the temp folder: {chatbot_store.STORE_PATH}. STOP.")
    sys.exit(1)


def at(h, m=0):
    return datetime(2026, 11, 16, h, m, tzinfo=localefmt.tz())


# ============================================================
# 1. Store
# ============================================================
check("listen_only is in the edit whitelist", "listen_only" in chatbot_store._PATCHABLE)
check("CANARY: an old record without the key answers as before",
      chatbot_store._public({"id": "x"}).get("listen_only") is False)
bid, err = chatbot_store.create_bot({"name": "Page Donnan", "agent_slug": "cskh", "brain": "b",
                                     "listen_only": "1"})
check("create with listen only", not err and chatbot_store.get_bot(bid)["listen_only"] is True, err)
b0, err = chatbot_store.create_bot({"name": "Normal", "agent_slug": "x", "brain": "b"})
check("create without it = off", not err and chatbot_store.get_bot(b0)["listen_only"] is False, err)
ok, err = chatbot_store.update_bot(b0, {"listen_only": "1"})
check("update turns it on", ok and chatbot_store.get_bot(b0)["listen_only"] is True, err)
ok, err = chatbot_store.update_bot(b0, {"listen_only": "0"})
check("update turns it off", ok and chatbot_store.get_bot(b0)["listen_only"] is False, err)
ok, err = chatbot_store.update_bot(bid, {"name": "Page Donnan 2"})
check("a patch without the key leaves it alone", ok and chatbot_store.get_bot(bid)["listen_only"] is True, err)

# ============================================================
# 2. The gate
# ============================================================
cfg = chatbot_store.get_bot(bid)
private = {"chat_type": "private", "chat_id": "p1"}
for h in (3, 10, 15, 23):
    check(f"private message at {h:02d}:00 -> listen_only", chatbot_runtime._ly_do_im(cfg, private, at(h)) == "listen_only")
check("the same bot with it off answers",
      chatbot_runtime._ly_do_im(dict(cfg, listen_only=False), private, at(10)) == "")
check("unknown group keeps its own code (approval queue still works)",
      chatbot_runtime._ly_do_im(cfg, {"chat_type": "group", "chat_id": "g-x", "mentioned": True}, at(10))
      == "nhom_chua_bat")
check("_nen_tra_loi is False (second layer in the answer path)", chatbot_runtime._nen_tra_loi(cfg, private) is False)


async def _engine_forbidden(*a, **k):
    raise AssertionError("engine called in listen-only mode")


chatbot_runtime.wire(answer=_engine_forbidden, brain_root=lambda b: _STATE, read_agent=lambda br, slug: ({}, ""))

# ============================================================
# 3. Precheck: silent, message in the inbox. Try panel reports the code.
# ============================================================
chan = chatbot_runtime._make_precheck_fn(bid)
meta = {"chat_type": "private", "chat_id": "khach-1", "user_id": "khach-1", "user_name": "Khách A",
        "message_id": "m-1"}
r = chan("Áo polo size M còn màu nào?", dict(meta))
check("precheck blocks silently ({}: no reply)", r == {}, r)
aid, kenh = chatbot_runtime._tai_khoan_cua(chatbot_store.get_bot(bid), meta)
msgs = conversations.tin_gan_day(kenh, aid, "khach-1")
check("the customer message is in the inbox",
      any(m.get("sender_type") == "customer" and "polo" in (m.get("text") or "") for m in msgs), msgs)
check("... and nothing was sent back", not any(m.get("sender_type") == "ai" for m in msgs), msgs)

r = asyncio.run(chatbot_runtime.try_message(bid, "Cho em hỏi giá"))
check("try panel says the gate code listen_only",
      r.get("ok") and r.get("stage") == "gate" and r.get("code") == "listen_only"
      and not r.get("would_reply") and bool(r.get("reason")), r)

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("ALL PASS")
