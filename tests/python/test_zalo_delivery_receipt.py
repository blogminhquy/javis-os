"""Zalo bot replies must not look delivered merely because the model wrote text.

Run: python tests/python/test_zalo_delivery_receipt.py
No network, no Zalo messages sent.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zalo-receipt-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import conversations  # noqa: E402
import chatbot_runtime  # noqa: E402
import channels.zalo_personal as zp  # noqa: E402

fail = []


def check(label, ok):
    print(("ok   " if ok else "FAIL ") + label)
    if not ok:
        fail.append(label)


cfg = {"id": "bot_mika", "name": "Mika", "channel": "zalo_personal",
       "accounts": [{"id": "zalo-test"}]}
meta = {"account_id": "zalo-test", "_kenh": "zalo_personal",
        "chat_id": "group-123", "chat_type": "group", "user_id": "alice", "user_name": "Alice"}


def save_ai(text="Dạ em kiểm tra rồi"):
    rid = chatbot_runtime.ghi_tin_bot(cfg, meta, text, zalo_sending=True)
    c = conversations.conversation_id_of("zalo_personal", "zalo-test", "group-123")
    row = next((m for m in conversations.tin_nhan(c, limit=50) if m["id"] == rid), None)
    return rid, row


def latest_state(rid):
    c = conversations.conversation_id_of("zalo_personal", "zalo-test", "group-123")
    row = next((m for m in conversations.tin_nhan(c, limit=50) if m["id"] == rid), None)
    return (row or {}).get("metadata", {}).get("zalo_delivery", {})


rid, row = save_ai()
check("model output persisted as SENDING, not delivered",
      rid > 0 and row["metadata"]["zalo_delivery"]["state"] == "sending")
check("cannot settle with invalid status", not conversations.set_zalo_delivery(rid, "delivered_to_human"))

# Exercise the actual Zalo Transport._gui, mocking only the external gateway.
transport = object.__new__(zp.Transport)
transport.conn_id = "zalo-test"
transport.last_error = ""
transport.cfg_fn = lambda: cfg
real_gui = zp.gui


async def accepted(*_args, **_kw):
    return True, ""


async def failed(*_args, **_kw):
    return False, "Zalo refused: not a member"


async def uncertain(*_args, **_kw):
    return False, "không rõ tin có tag đã đi chưa (timeout)"


async def run_send(rid, send):
    zp.gui = send
    return await transport._gui("group-123", "Dạ em kiểm tra rồi", "group",
                                {"user_id": "alice", "user_name": "Alice"}, receipt_row=rid)


try:
    check("fake provider accepts a message", asyncio.run(run_send(rid, accepted)) is True)
    check("accepted means provider accepted, NOT recipient read",
          latest_state(rid).get("state") == "accepted")
    check("settled send cannot be overwritten as failed",
          not conversations.set_zalo_delivery(rid, "failed", "late error") and latest_state(rid).get("state") == "accepted")

    bad_id, _ = save_ai("Other answer")
    check("fake provider rejects message", asyncio.run(run_send(bad_id, failed)) is False)
    check("channel refusal visible in the inbox",
          latest_state(bad_id).get("state") == "failed" and "not a member" in latest_state(bad_id).get("error", ""))

    unk_id, _ = save_ai("Uncertain answer")
    check("uncertain timeout not retried automatically", asyncio.run(run_send(unk_id, uncertain)) is False)
    check("timeout shows UNKNOWN rather than falsely delivered or safely retryable",
          latest_state(unk_id).get("state") == "unknown")

    cancel_id, _ = save_ai("Superseded answer")
    check("old turn cancelled without calling provider",
          conversations.set_zalo_delivery(cancel_id, "cancelled"))
    check("cancelled state stays in inbox", latest_state(cancel_id).get("state") == "cancelled")
finally:
    zp.gui = real_gui

other = conversations.ghi_su_kien({
    "channel": "telegram", "account_id": "tg-test", "bot_id": "bot_t",
    "external_chat_id": "user", "chat_type": "private", "sender_type": "ai",
    "sender_name": "Other", "text": "hi",
    "metadata": {"zalo_delivery": {"state": "sending"}}})
check("cannot settle a different channel's message",
      not conversations.set_zalo_delivery(other["message_id"], "accepted"))

frontend = (ROOT / "dashboard" / "conversations.js").read_text(encoding="utf-8")
check("inbox renders receipts", "zalo_delivery" in frontend and "deliveryHtml" in frontend)
check("poll refreshes metadata on existing message IDs", 'messages?limit=30' in frontend)

if fail:
    sys.exit(1)
print("ALL PASS")
