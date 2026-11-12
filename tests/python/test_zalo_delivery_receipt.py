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
          conversations.set_zalo_delivery(cancel_id, "cancelled", reason="superseded"))
    check("cancelled state stays in inbox", latest_state(cancel_id).get("state") == "cancelled")
    check("the reason is a code the inbox translates, not a sentence",
          latest_state(cancel_id).get("reason") == "superseded" and latest_state(cancel_id).get("error") == "")

    odd_id, _ = save_ai("Odd reason")
    conversations.set_zalo_delivery(odd_id, "cancelled", reason="A sentence written in one language.")
    check("a reason outside the known codes is dropped", latest_state(odd_id).get("reason") == "")

    # The transport passes codes, never prose: every code it uses is one the store keeps and the inbox translates.
    import re
    src = (SERVER / "channels" / "zalo_personal.py").read_text(encoding="utf-8")
    used = set(re.findall(r'_set_delivery\([^)]*reason="([a-z_]+)"', src))
    check("the transport uses reason codes (%s)" % ", ".join(sorted(used)),
          used and used <= set(conversations.ZALO_DELIVERY_REASONS))
    check("the transport no longer writes English sentences into a receipt",
          not re.search(r'_set_delivery\(receipt_row, "[a-z]+", "[A-Z]', src))
    js = (ROOT / "dashboard" / "conversations.js").read_text(encoding="utf-8")
    import json
    for lang in ("vi", "en"):
        words = json.loads((ROOT / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
        for code in conversations.ZALO_DELIVERY_REASONS + ("stale",):
            key = "ht.zalo_why." + code
            check(f"{lang}: reason '{code}' has words and the inbox maps it", bool(words.get(key)) and key in js)
        check(f"{lang}: no line for a reply that went out", "ht.zalo_accepted" not in words)
    check("the inbox draws nothing for an accepted reply", "ht.zalo_accepted" not in js)

    # Partial and uncertain sends, in both languages of `gui`.
    check("a timeout is uncertain", zp.send_uncertain("MCP call timed out") and zp.send_uncertain("hết giờ chờ Zalo"))
    check("part 2 of 3 failing is uncertain (part 1 arrived)",
          zp.send_uncertain("part 2/3: Zalo refused") and zp.send_uncertain("đoạn 2/3: Zalo từ chối"))
    check("part 1 failing with a clear refusal is a plain failure",
          not zp.send_uncertain("part 1/3: Zalo refused") and not zp.send_uncertain("đoạn 1/3: Zalo từ chối"))
    check("a refusal that merely contains the word 'part' is a plain failure",
          not zp.send_uncertain("You are not part of this group"))

    # A reply left on "sending" (server stopped mid-send, transport never ran) must not say "sending" for ever.
    stuck_id, _ = save_ai("Stuck answer")
    check("a fresh pending reply still reads as sending", latest_state(stuck_id).get("state") == "sending")
    with conversations._lock:
        db = conversations._conn()
        db.execute("UPDATE messages SET created_at=created_at-? WHERE id=?",
                   (conversations.ZALO_SENDING_STALE + 5, stuck_id))
        db.commit()
    st = latest_state(stuck_id)
    check("after ZALO_SENDING_STALE it reads as unknown with reason 'stale'",
          st.get("state") == "unknown" and st.get("reason") == "stale")
    check("a transport that settles late still wins", asyncio.run(run_send(stuck_id, accepted)) is True
          and latest_state(stuck_id).get("state") == "accepted")
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
check("only a pending reply inside the refreshed window keeps the second request going",
      '_msgs.slice(-30).some(' in frontend)

if fail:
    sys.exit(1)
print("ALL PASS")
