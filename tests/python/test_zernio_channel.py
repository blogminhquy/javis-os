"""Zernio channel and bot test suite:
Verifies HMAC-SHA256 signature verification, deduplication, 5s batching,
webhook.test handling, human takeover, customer cap, echo filtering,
inbound bridge API, and channel registry integration.

Run with:
    python tests/run.py zernio_channel
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import datetime
import hashlib
import hmac
import json
import os
import sys
import tempfile
import time

_tmp_dir = tempfile.mkdtemp(prefix="javis-zernio-")
os.environ["JAVIS_STATE_DIR"] = _tmp_dir
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
os.environ["SAMMY_RUNTIME_TOKEN"] = "test_sammy_token_secret_123"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channels
import channel_accounts
import conversations
import zernio_bot

_fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  [{detail}]"))
    if not ok:
        _fails.append(name)


def run(coro):
    return asyncio.run(coro)


ACCOUNT_ID = "6af71a1e56dde30cef9c79ce"
USERNAME = "ritashopvn"
WEBHOOK_SECRET = "zernio_sec_test_hmac_abc123"
API_KEY = "sk_test_zernio_live_key_xyz"

# Configure state store to test temp directory
zernio_bot.STATE_FILE = zernio_bot.Path(_tmp_dir) / "zernio_state.json"
zernio_bot._state_store = zernio_bot.DurableState(zernio_bot.STATE_FILE)


def sign_payload(raw: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()


def make_event(
    event_id="evt_001",
    event_name="message.received",
    text="Giá sản phẩm bao nhiêu?",
    sender_id="cust_999",
    sender_username="hiep35453",
    platform_msg_id="pmsg_001",
    conv_id="conv_rita_01",
    account_id=ACCOUNT_ID,
    username=USERNAME,
    platform="instagram",
    direction="incoming",
    standby=False,
    historical=False,
    timestamp=None,
    test=False
):
    if timestamp is None:
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return {
        "id": event_id,
        "event": event_name,
        "timestamp": timestamp,
        "test": test,
        "account": {
            "id": account_id,
            "accountId": account_id,
            "platform": platform,
            "username": username
        },
        "conversation": {
            "id": conv_id,
            "platformConversationId": conv_id,
            "status": "active"
        },
        "message": {
            "id": f"msg_{event_id}",
            "platformMessageId": platform_msg_id,
            "text": text,
            "sentAt": timestamp,
            "direction": direction,
            "platform": platform,
            "sender": {
                "id": sender_id,
                "username": sender_username,
                "name": "Hiep Nguyen"
            }
        },
        "metadata": {
            "standby": standby,
            "historical": historical
        }
    }


# ============================================================
# 1. Channel Registry & Token Splitting
# ============================================================
spec = channels.spec("zernio")
check("zernio is registered in channels", spec is not None and spec.id == "zernio")
check("zernio has gui_chu and bot capabilities", spec.nl("gui_chu") and spec.nl("bot"))
check("zernio webhook path is /webhooks/zernio", getattr(channels.module("zernio"), "WEBHOOK_PATH", "") == "/webhooks/zernio")

cr_space = zernio_bot.split_credentials(f"{ACCOUNT_ID} {USERNAME} {WEBHOOK_SECRET} {API_KEY}")
check("split_credentials parses space-separated string",
      cr_space["account_id"] == ACCOUNT_ID and cr_space["username"] == USERNAME and cr_space["secret"] == WEBHOOK_SECRET and cr_space["api_key"] == API_KEY)

cr_json = zernio_bot.split_credentials(json.dumps({"account_id": ACCOUNT_ID, "username": USERNAME, "secret": WEBHOOK_SECRET}))
check("split_credentials parses JSON string",
      cr_json["account_id"] == ACCOUNT_ID and cr_json["username"] == USERNAME and cr_json["secret"] == WEBHOOK_SECRET)

token_verify = run(channels.module("zernio").verify_token(f"{ACCOUNT_ID} {USERNAME} {WEBHOOK_SECRET}"))
check("verify_token succeeds with valid credentials", token_verify.get("ok") is True and token_verify.get("username") == USERNAME)

bad_token = run(channels.module("zernio").verify_token(f"{ACCOUNT_ID}"))
check("verify_token rejects incomplete credentials", bad_token.get("ok") is False)


# ============================================================
# 2. Signature Verification (HMAC-SHA256, Constant-Time)
# ============================================================
raw_sample = b'{"hello":"world"}'
valid_sig = sign_payload(raw_sample)
check("verify_signature accepts correct HMAC-SHA256", zernio_bot.verify_signature(raw_sample, valid_sig, WEBHOOK_SECRET))
check("verify_signature rejects wrong signature", not zernio_bot.verify_signature(raw_sample, "0" * 64, WEBHOOK_SECRET))
check("verify_signature rejects missing signature", not zernio_bot.verify_signature(raw_sample, "", WEBHOOK_SECRET))
check("verify_signature rejects malformed signature length", not zernio_bot.verify_signature(raw_sample, "abc", WEBHOOK_SECRET))
check("verify_signature rejects wrong secret", not zernio_bot.verify_signature(raw_sample, valid_sig, "wrong_secret"))


# Register active mock bot in zernio_bot
received_turns = []


async def fake_answer(text, meta, progress):
    received_turns.append({"text": text, "meta": meta})
    return {"text": f"Sammy phản hồi: {text}", "files": []}


mock_bot = zernio_bot.ZernioBot(
    token={"account_id": ACCOUNT_ID, "username": USERNAME, "secret": WEBHOOK_SECRET, "api_key": API_KEY},
    chat_id="",
    answer_fn=fake_answer
)
mock_bot.start()
check("mock_bot is registered under ACCOUNT_ID", zernio_bot._REGISTRY.get(ACCOUNT_ID) is mock_bot)


# ============================================================
# 3. Webhook Authentication & Envelope Tests
# ============================================================
async def test_webhook_auth():
    ev = make_event(event_id="auth_001")
    raw = json.dumps(ev).encode("utf-8")

    # Missing signature -> 401
    status, res = await zernio_bot.handle_webhook(raw, {})
    check("webhook rejects missing signature with 401", status == 401)

    # Bad signature -> 401
    status, res = await zernio_bot.handle_webhook(raw, {"x-zernio-signature": "f" * 64})
    check("webhook rejects invalid signature with 401", status == 401)

    # Valid signature -> 202 queued
    status, res = await zernio_bot.handle_webhook(raw, {"x-zernio-signature": sign_payload(raw)})
    check("webhook accepts valid signature with 202 queued", status == 202 and res.get("status") == "queued")

    # Bad JSON -> 400
    status, res = await zernio_bot.handle_webhook(b"{not json", {"x-zernio-signature": valid_sig})
    check("webhook rejects bad JSON with 400", status == 400)


run(test_webhook_auth())


# ============================================================
# 4. Deduplication & Replay Tests
# ============================================================
async def test_deduplication():
    # Duplicate event ID
    ev = make_event(event_id="auth_001")  # already processed above
    raw = json.dumps(ev).encode("utf-8")
    status, res = await zernio_bot.handle_webhook(raw, {"x-zernio-signature": sign_payload(raw)})
    check("duplicate event ID returns 200 duplicate", status == 200 and res.get("duplicate") is True)

    # Deduplication survives restart by re-reading state
    zernio_bot._state_store = zernio_bot.DurableState(zernio_bot.STATE_FILE)
    status, res = await zernio_bot.handle_webhook(raw, {"x-zernio-signature": sign_payload(raw)})
    check("event deduplication survives restart", status == 200 and res.get("duplicate") is True)

    # Replay of message with same platformMessageId in a new event envelope
    ev_retry = make_event(event_id="evt_new_envelope_999", platform_msg_id="pmsg_001")  # pmsg_001 seen in auth_001
    raw_retry = json.dumps(ev_retry).encode("utf-8")
    status, res = await zernio_bot.handle_webhook(raw_retry, {"x-zernio-signature": sign_payload(raw_retry)})
    check("message platformMessageId deduplication rejects duplicate message",
          status == 200 and res.get("status") == "duplicate_message")

    # Stale replay (older than MAX_AGE_SECONDS)
    old_ts = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=3)).isoformat()
    ev_old = make_event(event_id="evt_old_111", timestamp=old_ts)
    raw_old = json.dumps(ev_old).encode("utf-8")
    status, res = await zernio_bot.handle_webhook(raw_old, {"x-zernio-signature": sign_payload(raw_old)})
    check("stale historical message rejected as replay_or_historical",
          status == 202 and res.get("ignored") == "replay_or_historical")


run(test_deduplication())


# ============================================================
# 5. Special Events & Message Filtering
# ============================================================
async def test_special_events_and_filtering():
    # webhook.test -> 200 test, no turn invoked
    turn_count_before = len(received_turns)
    ev_test = make_event(event_id="evt_test_ping", event_name="webhook.test")
    raw_test = json.dumps(ev_test).encode("utf-8")
    status, res = await zernio_bot.handle_webhook(raw_test, {"x-zernio-signature": sign_payload(raw_test)})
    check("webhook.test returns 200 without calling model",
          status == 200 and res.get("status") == "test" and len(received_turns) == turn_count_before)

    # Ignored non-message event (e.g. comment.received)
    ev_comment = make_event(event_id="evt_comm_01", event_name="comment.received")
    raw_comment = json.dumps(ev_comment).encode("utf-8")
    status, res = await zernio_bot.handle_webhook(raw_comment, {"x-zernio-signature": sign_payload(raw_comment)})
    check("non-message event returns 202 ignored_event", status == 202 and res.get("status") == "ignored_event")

    # Echo message (outgoing)
    ev_echo = make_event(event_id="evt_echo_01", direction="outgoing")
    raw_echo = json.dumps(ev_echo).encode("utf-8")
    status, res = await zernio_bot.handle_webhook(raw_echo, {"x-zernio-signature": sign_payload(raw_echo)})
    check("outgoing echo message returns 202 echo", status == 202 and res.get("status") == "echo")

    # Bot's own message
    ev_self = make_event(event_id="evt_self_01", sender_id=ACCOUNT_ID, sender_username=USERNAME)
    raw_self = json.dumps(ev_self).encode("utf-8")
    status, res = await zernio_bot.handle_webhook(raw_self, {"x-zernio-signature": sign_payload(raw_self)})
    check("bot own message returns 202 self_message", status == 202 and res.get("status") == "self_message")

    # Standby takeover message
    ev_standby = make_event(event_id="evt_sb_01", standby=True)
    raw_sb = json.dumps(ev_standby).encode("utf-8")
    status, res = await zernio_bot.handle_webhook(raw_sb, {"x-zernio-signature": sign_payload(raw_sb)})
    check("standby message returns 202 standby_or_historical", status == 202 and res.get("status") == "standby_or_historical")


run(test_special_events_and_filtering())


# ============================================================
# 6. 5-Second Debounce & Message Batching
# ============================================================
async def test_batching():
    conv_batch = "conv_batch_test_01"
    ev1 = make_event(event_id="evt_b_01", conv_id=conv_batch, platform_msg_id="pmsg_b1", text="Chào shop")
    ev2 = make_event(event_id="evt_b_02", conv_id=conv_batch, platform_msg_id="pmsg_b2", text="Cho em hỏi giá")
    ev3 = make_event(event_id="evt_b_03", conv_id=conv_batch, platform_msg_id="pmsg_b3", text="Có giao hỏa tốc không?")

    for ev in (ev1, ev2, ev3):
        raw = json.dumps(ev).encode("utf-8")
        await zernio_bot.handle_webhook(raw, {"x-zernio-signature": sign_payload(raw)})

    state = zernio_bot._state_store.load()
    c_state = state.get("conversations", {}).get(conv_batch, {})
    check("3 messages queued in conversation batch", len(c_state.get("messages", [])) == 3)

    # Manually flush the batch
    turn_count_before = len(received_turns)
    await zernio_bot._flush(conv_batch)

    check("flush triggers exactly one combined bot turn", len(received_turns) == turn_count_before + 1)
    combined = received_turns[-1]["text"]
    check("combined text contains all 3 messages in order",
          "Chào shop" in combined and "Cho em hỏi giá" in combined and "Có giao hỏa tốc không?" in combined)


run(test_batching())


# ============================================================
# 7. Human Takeover & Customer Limit Protection
# ============================================================
async def test_takeover_and_limits():
    conv_takeover = "conv_human_takeover_01"

    # Set mode to human in conversations database
    conversations.ghi_su_kien({
        "channel": "zernio", "account_id": ACCOUNT_ID, "account_name": USERNAME,
        "bot_id": "bot_cf54086df7", "external_chat_id": conv_takeover, "chat_type": "private",
        "chat_title": "@hiep35453", "external_message_id": "msg_pre_takeover", "sender_type": "customer",
        "sender_id": "cust_takeover", "sender_name": "Hiep", "message_type": "text", "text": "Alo",
        "created_at": time.time()
    })
    cid = conversations.conversation_id_of("zernio", ACCOUNT_ID, conv_takeover)
    conversations.dat_che_do(cid, "human")
    check("conversation mode is human", conversations.che_do("zernio", ACCOUNT_ID, conv_takeover) == "human")

    # Queue message
    ev = make_event(event_id="evt_to_01", conv_id=conv_takeover, platform_msg_id="pmsg_to1", text="Em cần tư vấn thêm")
    raw = json.dumps(ev).encode("utf-8")
    await zernio_bot.handle_webhook(raw, {"x-zernio-signature": sign_payload(raw)})

    turn_count_before = len(received_turns)
    await zernio_bot._flush(conv_takeover)
    check("bot stays silent when human takeover is active", len(received_turns) == turn_count_before)

    # Customer reply cap (5 replies limit)
    conv_cap = "conv_cap_test_01"
    state = zernio_bot._state_store.load()
    state["conversations"][conv_cap] = {
        "messages": [{"id": "m_cap", "platformMessageId": "p_cap", "text": "Tin thứ 6", "sender": {"id": "c1"}}],
        "replies_in_window": 5,  # Cap reached!
        "takeover": False,
        "account_id": ACCOUNT_ID,
        "username": USERNAME
    }
    zernio_bot._state_store.save(state)

    turn_count_before = len(received_turns)
    await zernio_bot._flush(conv_cap)
    check("customer reply cap at 5 prevents further replies", len(received_turns) == turn_count_before)


run(test_takeover_and_limits())


# ============================================================
# 8. Inbound Bridge Endpoint (/zernio/inbound)
# ============================================================
async def test_inbound_bridge():
    conv_inbound = "conv_inbound_test_01"
    payload = {
        "conversationId": conv_inbound,
        "account": {"id": ACCOUNT_ID, "username": USERNAME, "platform": "instagram"},
        "messages": [
            {"id": "in_msg_1", "platformMessageId": "p_in_1", "text": "Tin qua bridge adapter", "sender": {"id": "u1", "username": "hiep35453"}}
        ],
        "policy": {"batchMs": 5000, "maxCustomerReplies": 5, "requireTakeoverCheck": True}
    }

    # Missing / bad token -> 401
    status, res = await zernio_bot.handle_inbound(payload, "Bearer wrong_token")
    check("inbound adapter rejects wrong bearer token with 401", status == 401)

    # Valid token -> 200 with takeover and sammyReplySent booleans
    status, res = await zernio_bot.handle_inbound(payload, "Bearer test_sammy_token_secret_123")
    check("inbound adapter responds 200 with required booleans",
          status == 200 and "takeover" in res and "sammyReplySent" in res)
    check("inbound takeover is boolean and sammyReplySent is boolean",
          isinstance(res["takeover"], bool) and isinstance(res["sammyReplySent"], bool))


run(test_inbound_bridge())


mock_bot.stop()

print("\n" + "=" * 50)
if _fails:
    print(f"FAILED ({len(_fails)} tests failed)")
    sys.exit(1)
else:
    print("ALL TESTS PASSED")
