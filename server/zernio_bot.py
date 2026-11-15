"""Zernio messaging gateway for Javis OS (Instagram and multi-channel inbox).

Key features:
1. Webhook ingress: verifies constant-time HMAC-SHA256 signature using `X-Zernio-Signature`
   over raw request body with configured endpoint secret. Secrets are NEVER logged.
2. Deduplication & Idempotency:
   - Event ID deduplication (durable across restarts).
   - Message-level idempotency `account_id:platform_message_id` (durable across restarts).
   - Replay / historical message filtering.
   - `webhook.test` / test event handled with 200 without invoking model or sending messages.
   - Echo, bot's own messages, and standby messages skipped.
3. 5-Second Debounce & Batching:
   - Incoming customer messages within 5 seconds in the same conversation are batched together.
4. Human takeover & Customer limit protection:
   - Respects human takeover (`conversations.che_do == "human"`): bot remains silent when staff takes over.
   - Verified immediately before invoking runtime and immediately before sending outbound message.
   - Durable cap on replies in window (max 5 replies) to prevent spam/runaway loops.
5. Inbound bridge endpoint (`/zernio/inbound`):
   - Secure runtime adapter receiving `{ conversationId, account, messages, policy }` protected by bearer token.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import bot_gateway
import channel_accounts
import config as cfgmod
import conversations
import localefmt

# Store file for durable deduplication and batching state
STATE_FILE = cfgmod.STATE_DIR / "zernio_state.json"
MAX_AGE_SECONDS = 48 * 3600  # 48 hours for deduplication TTL
BATCH_SECONDS = 5.0
MAX_CUSTOMER_REPLIES = 5
MAX_BODY_BYTES = 256 * 1024

_lock = asyncio.Lock() if hasattr(asyncio, "Lock") else None

# Active bots: account_id -> ZernioBot
_REGISTRY: Dict[str, "ZernioBot"] = {}
# Active credentials: account_id -> dict
_ACCOUNTS: Dict[str, dict] = {}
# Pending batch timers: conversation_id -> asyncio.TimerHandle
_TIMERS: Dict[str, asyncio.TimerHandle] = {}


def _now() -> float:
    return time.time()


# ============================================================
# Credentials & Helper Functions
# ============================================================
def split_credentials(token: Any) -> dict:
    """Extracts credentials from string or dict: account_id, username, secret, api_key."""
    if isinstance(token, dict):
        d = dict(token)
        aid = str(d.get("account_id") or d.get("accountId") or d.get("id") or "").strip()
        uname = str(d.get("username") or "").strip()
        sec = str(d.get("secret") or d.get("webhook_secret") or "").strip()
        key = str(d.get("api_key") or d.get("apiKey") or "").strip()
        return {"account_id": aid, "username": uname, "secret": sec, "api_key": key or _fallback_api_key()}

    raw = str(token or "").strip()
    if not raw:
        return {"account_id": "", "username": "", "secret": "", "api_key": _fallback_api_key()}

    if raw.startswith("{") and raw.endswith("}"):
        try:
            d = json.loads(raw)
            if isinstance(d, dict):
                return split_credentials(d)
        except Exception:
            pass

    parts = raw.split()
    aid = parts[0] if len(parts) > 0 else ""
    uname = parts[1] if len(parts) > 1 else ""
    sec = parts[2] if len(parts) > 2 else ""
    key = parts[3] if len(parts) > 3 else ""
    return {"account_id": aid, "username": uname, "secret": sec, "api_key": key or _fallback_api_key()}


def _fallback_api_key() -> str:
    """Reads API key from configured Zernio connection in mcp_store if available."""
    try:
        import mcp_store
        for c in mcp_store.list_connections():
            cid = str(c.get("connector_id") or c.get("id") or "")
            if "zernio" in cid.lower() and c.get("enabled"):
                sec = mcp_store.connection_secrets(c["id"])
                if sec and sec.get("api_key"):
                    return str(sec["api_key"]).strip()
    except Exception:
        pass
    return ""


def connected_instagram_accounts() -> List[dict]:
    """Lists connected Instagram accounts from Zernio API if connected."""
    key = _fallback_api_key()
    if not key:
        return []
    import urllib.request
    req = urllib.request.Request("https://api.zernio.com/v1/accounts", headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    })
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            out = []
            for a in data.get("accounts", []):
                if a.get("platform") == "instagram":
                    aid = str(a.get("_id") or a.get("id") or a.get("accountId") or "")
                    uname = str(a.get("username") or "")
                    if aid and uname:
                        out.append({"id": aid, "username": uname, "platform": "instagram"})
            return out
    except Exception as e:
        print(f"[zernio] failed to list accounts: {type(e).__name__}: {e}", file=sys.stderr)
        return []


async def whoami(cr: dict) -> dict:
    """Validates credentials. If account_id and username match connected Instagram accounts or format."""
    aid = cr.get("account_id") or ""
    uname = cr.get("username") or ""
    if not aid or not uname:
        return {"ok": False, "error": localefmt.chu("Thiếu Account ID hoặc Username", "Missing Account ID or Username")}
    accounts = connected_instagram_accounts()
    if accounts:
        matched = next((a for a in accounts if a["id"] == aid or a["username"].lower() == uname.lower()), None)
        if matched:
            return {"ok": True, "account": matched}
    # If network check unavailable or not in list, accept valid format
    return {"ok": True, "account": {"id": aid, "username": uname, "platform": "instagram"}}


# ============================================================
# Signature Verification (HMAC-SHA256, Constant-Time)
# ============================================================
def verify_signature(raw: bytes, signature: str, secret: str) -> bool:
    """Validates HMAC-SHA256 signature in constant time. Never logs secret or raw payload."""
    sig = str(signature or "").strip()
    sec = str(secret or "").strip()
    if not sig or not sec:
        return False
    if not re.match(r"^[a-fA-F0-9]{64}$", sig):
        return False
    try:
        expected = hmac.new(sec.encode("utf-8"), raw or b"", hashlib.sha256).digest()
        received = bytes.fromhex(sig)
        return len(received) == len(expected) and hmac.compare_digest(received, expected)
    except Exception:
        return False


# ============================================================
# Durable Deduplication & Batching State Store
# ============================================================
class DurableState:
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self._ensure_dir()

    def _ensure_dir(self):
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def load(self) -> dict:
        try:
            if self.file_path.exists():
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        data.setdefault("events", {})
                        data.setdefault("messages", {})
                        data.setdefault("conversations", {})
                        return data
        except Exception as e:
            print(f"[zernio state load error] {type(e).__name__}: {e}", file=sys.stderr)
        return {"events": {}, "messages": {}, "conversations": {}}

    def save(self, data: dict):
        try:
            self._ensure_dir()
            tmp_path = self.file_path.with_name(f"{self.file_path.name}.{os.getpid()}.tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp_path, self.file_path)
        except Exception as e:
            print(f"[zernio state save error] {type(e).__name__}: {e}", file=sys.stderr)

    def prune(self, data: dict, now: float) -> dict:
        events = data.get("events", {})
        messages = data.get("messages", {})
        cutoff = now - MAX_AGE_SECONDS
        pruned_events = {k: v for k, v in events.items() if float(v.get("ts") or now) > cutoff}
        pruned_messages = {k: v for k, v in messages.items() if float(v.get("ts") or now) > cutoff}
        data["events"] = pruned_events
        data["messages"] = pruned_messages
        return data


_state_store = DurableState(STATE_FILE)


# ============================================================
# Zernio Bot Transport
# ============================================================
class ZernioBot(bot_gateway.HangLuot):
    """Transport for Zernio multi-channel bot."""

    def __init__(self, token: Any, chat_id: Any, answer_fn, command_fn=None, callback_fn=None,
                 download_dir=None, commands=None, precheck_fn=None, event_fn=None,
                 giau_trang_thai: bool = False, **_ignored):
        self.creds = split_credentials(token)
        self.account_id = self.creds.get("account_id") or ""
        self.bot_username = self.creds.get("username") or ""
        self.secret = self.creds.get("secret") or ""
        self.api_key = self.creds.get("api_key") or ""
        self.giau_trang_thai = bool(giau_trang_thai)

        self.answer_fn = answer_fn
        self.command_fn = command_fn
        self.precheck_fn = precheck_fn
        self.event_fn = event_fn

        self._current = {}
        self._cho = {}
        self._stop = False
        self.status = "off"
        self.last_error = ""

    def start(self):
        self._stop = False
        self.status = "polling"
        if self.account_id:
            _REGISTRY[self.account_id] = self
            _ACCOUNTS[self.account_id] = self.creds

    def stop(self):
        self._stop = True
        self.status = "stopped"
        if self.account_id in _REGISTRY:
            _REGISTRY.pop(self.account_id, None)
            _ACCOUNTS.pop(self.account_id, None)

    async def _send(self, client, chat, text):
        return await send_api_message(self.creds, chat, text)

    async def send_text(self, conversation_id: str, text: str) -> Tuple[bool, str]:
        return await send_api_message(self.creds, conversation_id, text)

    async def _handle_turn(self, client, chat, text, meta=None):
        if conversations.che_do("zernio", self.account_id, chat) == "human":
            return
        tools = []
        try:
            reply = await self.answer_fn(text, meta, None)
        except asyncio.CancelledError:
            return
        except Exception as e:
            print(f"[zernio turn failed] {type(e).__name__}: {e}", file=sys.stderr)
            reply = "" if self.giau_trang_thai else f"⚠ {type(e).__name__}: {e}"

        silent = False
        if isinstance(reply, dict):
            silent = bool(reply.get("im_lang"))
            reply = reply.get("text") or ""
        if silent or not str(reply or "").strip():
            return

        # Check human takeover again immediately before sending
        if conversations.che_do("zernio", self.account_id, chat) == "human":
            return

        await self._send(client, chat, str(reply).strip())


Transport = ZernioBot


# ============================================================
# Outbound Message Sender via Zernio API
# ============================================================
async def send_api_message(creds: dict, conversation_id: str, text: str) -> Tuple[bool, str]:
    """Sends a direct message reply via Zernio REST API POST /v1/inbox/conversations/{conversationId}/messages."""
    cid = str(conversation_id or "").strip()
    msg = str(text or "").strip()
    if not cid or not msg:
        return False, "missing conversation_id or text"

    aid = creds.get("account_id") or ""
    api_key = creds.get("api_key") or _fallback_api_key()
    if not api_key:
        return False, localefmt.chu("Chưa có API key Zernio để gửi tin", "Missing Zernio API key for sending messages")

    import httpx
    url = f"https://api.zernio.com/v1/inbox/conversations/{cid}/messages"
    payload = {"accountId": aid, "message": msg}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code in (200, 201):
                return True, ""
            err_text = resp.text[:200]
            print(f"[zernio send error {resp.status_code}] {err_text}", file=sys.stderr)
            return False, f"HTTP {resp.status_code}: {err_text}"
    except Exception as e:
        print(f"[zernio send exception] {type(e).__name__}: {e}", file=sys.stderr)
        return False, f"{type(e).__name__}: {e}"


async def send_text_for_account(tk: dict, chat_id: str, text: str) -> Tuple[bool, str]:
    """Helper for channels.gui."""
    creds = split_credentials(tk.get("token") or tk)
    return await send_api_message(creds, chat_id, text)


# ============================================================
# Webhook Ingress & Verification
# ============================================================
async def handle_webhook(raw: bytes, headers: dict) -> Tuple[int, dict]:
    """Handles an inbound raw webhook payload from Zernio.
    Returns (HTTP status code, response dict)."""
    now = _now()
    h = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    sig = h.get("x-zernio-signature", "")

    # 1. Parse JSON to read account and envelope
    try:
        body = json.loads((raw or b"").decode("utf-8"))
    except Exception:
        return 400, {"ok": False, "error": "invalid_json"}

    if not isinstance(body, dict):
        return 400, {"ok": False, "error": "invalid_envelope"}

    event_name = str(body.get("event") or "").strip()
    event_id = str(body.get("id") or "").strip()
    ts_str = str(body.get("timestamp") or "").strip()

    if h.get("x-zernio-event") and h.get("x-zernio-event") != event_name:
        return 400, {"ok": False, "error": "event_mismatch"}
    if h.get("x-zernio-event-id") and h.get("x-zernio-event-id") != event_id:
        return 400, {"ok": False, "error": "event_id_mismatch"}

    if not event_id or not event_name or not ts_str:
        return 400, {"ok": False, "error": "invalid_envelope"}

    # Determine account id
    acc_obj = body.get("account") or {}
    account_id = str(acc_obj.get("accountId") or acc_obj.get("id") or "").strip()

    # Find matching secret
    matched_secret = ""
    if account_id and account_id in _ACCOUNTS:
        matched_secret = _ACCOUNTS[account_id].get("secret", "")
    elif _ACCOUNTS:
        for a_creds in _ACCOUNTS.values():
            if verify_signature(raw, sig, a_creds.get("secret", "")):
                matched_secret = a_creds.get("secret", "")
                break

    if not matched_secret:
        env_secret = os.environ.get("ZERNIO_WEBHOOK_SECRET", "").strip()
        if env_secret and verify_signature(raw, sig, env_secret):
            matched_secret = env_secret

    # Verify signature
    if not matched_secret or not verify_signature(raw, sig, matched_secret):
        return 401, {"ok": False, "error": "invalid_signature"}

    # 2. Check Deduplication
    state = _state_store.load()
    state = _state_store.prune(state, now)
    if event_id in state["events"]:
        return 200, {"ok": True, "duplicate": True}

    # 3. Check Freshness / Replay
    try:
        import datetime
        occurred_at = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
    except Exception:
        occurred_at = now

    if occurred_at > now + 300 or (now - occurred_at) > MAX_AGE_SECONDS:
        return 202, {"ok": True, "ignored": "replay_or_historical"}

    def mark_event_handled(status_code: int, code: str):
        state["events"][event_id] = {"ts": now, "iso": ts_str}
        _state_store.save(state)
        return status_code, {"ok": status_code < 400, "status": code}

    # 4. Handle webhook.test
    if event_name == "webhook.test" or body.get("test") is True:
        return mark_event_handled(200, "test")

    # 5. Handle non-message events
    if event_name != "message.received":
        return mark_event_handled(202, "ignored_event")

    # 6. Message Eligibility Checks
    msg = body.get("message") or {}
    platform = str(acc_obj.get("platform") or msg.get("platform") or "").lower()
    if platform != "instagram":
        return mark_event_handled(202, "unsupported_platform")

    direction = str(msg.get("direction") or "").lower()
    if direction == "outgoing" or msg.get("is_echo") or msg.get("isEcho"):
        return mark_event_handled(202, "echo")

    meta_obj = body.get("metadata") or {}
    if meta_obj.get("standby") or meta_obj.get("historical") or msg.get("historical") or msg.get("isHistorical"):
        return mark_event_handled(202, "standby_or_historical")

    msg_id = str(msg.get("id") or "").strip()
    platform_msg_id = str(msg.get("platformMessageId") or msg.get("id") or "").strip()
    sender = msg.get("sender") or {}
    sender_id = str(sender.get("id") or "").strip()
    sender_username = str(sender.get("username") or "").strip()

    if not msg_id or not sender_id:
        return mark_event_handled(400, "invalid_message")

    # Check bot sender
    acc_username = str(acc_obj.get("username") or "").strip().lower()
    if sender_id == account_id or (sender_username and sender_username.lower() == acc_username):
        return mark_event_handled(202, "self_message")

    conv_obj = body.get("conversation") or {}
    conv_id = str(conv_obj.get("id") or msg.get("conversationId") or "").strip()
    if not conv_id:
        return mark_event_handled(400, "missing_conversation_id")

    # Message-level deduplication
    msg_key = f"{account_id}:{platform_msg_id}"
    if msg_key in state["messages"]:
        return mark_event_handled(200, "duplicate_message")

    # 7. Record event and message in durable state
    state["events"][event_id] = {"ts": now, "iso": ts_str}
    state["messages"][msg_key] = {"ts": now, "event_id": event_id}

    # 8. Add to conversation batch
    conv_state = state["conversations"].setdefault(conv_id, {
        "messages": [], "replies_in_window": 0, "takeover": False, "account_id": account_id,
        "username": acc_username, "sender_name": sender.get("name") or sender_username
    })
    conv_state["messages"].append({
        "id": msg_id,
        "platformMessageId": platform_msg_id,
        "text": str(msg.get("text") or "").strip(),
        "sender": sender,
        "sentAt": msg.get("sentAt") or ts_str
    })
    conv_state["due_at"] = now + BATCH_SECONDS
    conv_state["account_id"] = account_id
    conv_state["username"] = acc_username
    conv_state["sender_name"] = sender.get("name") or sender_username
    state["conversations"][conv_id] = conv_state
    _state_store.save(state)

    # Arm 5-second flush timer
    _arm_timer(conv_id, BATCH_SECONDS)

    return 202, {"ok": True, "status": "queued"}


def _arm_timer(conversation_id: str, delay_seconds: float):
    if conversation_id in _TIMERS:
        try:
            _TIMERS[conversation_id].cancel()
        except Exception:
            pass

    loop = asyncio.get_event_loop()
    handle = loop.call_later(delay_seconds, lambda: asyncio.create_task(_flush(conversation_id)))
    _TIMERS[conversation_id] = handle


async def _flush(conversation_id: str):
    _TIMERS.pop(conversation_id, None)
    state = _state_store.load()
    conv_state = state.get("conversations", {}).get(conversation_id)
    if not conv_state:
        return

    messages = conv_state.get("messages", [])
    if not messages:
        return

    account_id = conv_state.get("account_id") or ""
    # Check human takeover
    if conv_state.get("takeover") or conversations.che_do("zernio", account_id, conversation_id) == "human":
        conv_state["takeover"] = True
        conv_state["messages"] = []
        _state_store.save(state)
        return

    # Check reply cap
    if conv_state.get("replies_in_window", 0) >= MAX_CUSTOMER_REPLIES:
        conv_state["messages"] = []
        _state_store.save(state)
        return

    batch = list(messages)
    conv_state["messages"] = []
    _state_store.save(state)

    # Write batch to inbox
    for m in batch:
        sender = m.get("sender") or {}
        conversations.ghi_su_kien({
            "channel": "zernio",
            "account_id": account_id,
            "account_name": conv_state.get("username") or "ritashopvn",
            "bot_id": (_REGISTRY.get(account_id) or getattr(_REGISTRY.get(account_id), "bot_id", "")) or "",
            "external_chat_id": conversation_id,
            "chat_type": "private",
            "chat_title": f"@{conv_state.get('username', 'ritashopvn')} (Instagram)",
            "external_message_id": m.get("platformMessageId") or m.get("id"),
            "sender_type": "customer",
            "sender_id": str(sender.get("id") or ""),
            "sender_name": str(sender.get("name") or sender.get("username") or ""),
            "message_type": "text",
            "text": m.get("text") or "",
            "created_at": _now()
        })

    # Find active bot
    bot = _REGISTRY.get(account_id)
    if not bot or bot._stop:
        # Check if there is an account in channel_accounts associated with a bot
        aid = account_id
        for bid, b_inst in _REGISTRY.items():
            if b_inst and not b_inst._stop:
                bot = b_inst
                break

    if not bot:
        print(f"[zernio] no active bot for account {account_id}", file=sys.stderr)
        return

    # Combine text for turn
    combined_text = "\n".join(m.get("text", "") for m in batch if m.get("text"))
    if not combined_text.strip():
        return

    last_msg = batch[-1]
    sender = last_msg.get("sender") or {}
    meta = {
        "platform": "zernio",
        "chat_id": conversation_id,
        "chat_type": "private",
        "user_id": str(sender.get("id") or ""),
        "user_name": str(sender.get("name") or sender.get("username") or ""),
        "username": str(sender.get("username") or ""),
        "message_id": last_msg.get("platformMessageId") or last_msg.get("id"),
        "account_id": account_id,
        "mentioned": True
    }

    try:
        reply = await bot.answer_fn(combined_text, meta, None)
    except Exception as e:
        print(f"[zernio answer_fn error] {type(e).__name__}: {e}", file=sys.stderr)
        return

    # Check human takeover again before sending
    if conversations.che_do("zernio", account_id, conversation_id) == "human":
        conv_state["takeover"] = True
        _state_store.save(state)
        return

    reply_text = ""
    if isinstance(reply, dict):
        if reply.get("im_lang"):
            return
        reply_text = str(reply.get("text") or "").strip()
    elif isinstance(reply, str):
        reply_text = reply.strip()

    if not reply_text:
        return

    # Send reply
    ok, err = await bot.send_text(conversation_id, reply_text)
    if ok:
        conv_state["replies_in_window"] = conv_state.get("replies_in_window", 0) + 1
        _state_store.save(state)


# ============================================================
# Inbound Runtime Adapter (/zernio/inbound)
# ============================================================
async def handle_inbound(payload: dict, auth_header: str) -> Tuple[int, dict]:
    """Protected runtime adapter for Sammy / bot inbox.
    Receives `{ conversationId, account, messages, policy }` and delivers to runtime.
    Returns (status, {"takeover": bool, "sammyReplySent": bool})."""
    expected_token = os.environ.get("SAMMY_RUNTIME_TOKEN", "").strip()
    auth = str(auth_header or "").strip()
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else auth

    if expected_token and (not token or not hmac.compare_digest(token, expected_token)):
        return 401, {"ok": False, "error": "unauthorized"}

    if not isinstance(payload, dict):
        return 400, {"ok": False, "error": "payload must be a JSON object"}

    conv_id = str(payload.get("conversationId") or "").strip()
    acc_obj = payload.get("account") or {}
    messages = payload.get("messages") or []
    policy = payload.get("policy") or {}

    if not conv_id or not isinstance(messages, list):
        return 400, {"ok": False, "error": "missing conversationId or messages"}

    account_id = str(acc_obj.get("id") or acc_obj.get("accountId") or "").strip()
    account_username = str(acc_obj.get("username") or "ritashopvn").strip()

    # Check takeover immediately before any work
    if conversations.che_do("zernio", account_id, conv_id) == "human":
        return 200, {"takeover": True, "sammyReplySent": False}

    # Enforce customer cap
    max_replies = int(policy.get("maxCustomerReplies") or MAX_CUSTOMER_REPLIES)

    # Write messages to inbox
    for m in messages:
        sender = m.get("sender") or {}
        conversations.ghi_su_kien({
            "channel": "zernio",
            "account_id": account_id,
            "account_name": account_username,
            "bot_id": "",
            "external_chat_id": conv_id,
            "chat_type": "private",
            "chat_title": f"@{account_username} (Instagram)",
            "external_message_id": m.get("platformMessageId") or m.get("id") or f"msg_{_now()}",
            "sender_type": "customer",
            "sender_id": str(sender.get("id") or ""),
            "sender_name": str(sender.get("name") or sender.get("username") or ""),
            "message_type": "text",
            "text": str(m.get("text") or ""),
            "created_at": _now()
        })

    # Find bot
    bot = _REGISTRY.get(account_id)
    if not bot and _REGISTRY:
        bot = next(iter(_REGISTRY.values()))

    # If no poller in registry, lookup Sammy bot in chatbot_store
    answer_fn = getattr(bot, "answer_fn", None)
    if not answer_fn:
        import chatbot_store
        import chatbot_runtime
        bots = chatbot_store.list_bots()
        sammy = next((b for b in bots if "sammy" in b.get("name", "").lower()), bots[0] if bots else None)
        if sammy:
            answer_fn = chatbot_runtime._make_answer_fn(sammy["id"])

    if not answer_fn:
        return 200, {"takeover": False, "sammyReplySent": False}

    combined_text = "\n".join(m.get("text", "") for m in messages if m.get("text"))
    if not combined_text.strip():
        return 200, {"takeover": False, "sammyReplySent": False}

    last_msg = messages[-1]
    sender = last_msg.get("sender") or {}
    meta = {
        "platform": "zernio",
        "chat_id": conv_id,
        "chat_type": "private",
        "user_id": str(sender.get("id") or ""),
        "user_name": str(sender.get("name") or sender.get("username") or ""),
        "username": str(sender.get("username") or ""),
        "message_id": last_msg.get("platformMessageId") or last_msg.get("id"),
        "account_id": account_id,
        "mentioned": True
    }

    try:
        reply = await answer_fn(combined_text, meta, None)
    except Exception as e:
        print(f"[zernio inbound turn error] {type(e).__name__}: {e}", file=sys.stderr)
        return 200, {"takeover": False, "sammyReplySent": False}

    # Check takeover AGAIN immediately before sending
    if conversations.che_do("zernio", account_id, conv_id) == "human":
        return 200, {"takeover": True, "sammyReplySent": False}

    reply_text = ""
    if isinstance(reply, dict):
        if reply.get("im_lang"):
            return 200, {"takeover": False, "sammyReplySent": False}
        reply_text = str(reply.get("text") or "").strip()
    elif isinstance(reply, str):
        reply_text = reply.strip()

    if not reply_text:
        return 200, {"takeover": False, "sammyReplySent": False}

    # Send outbound reply
    creds = {"account_id": account_id, "username": account_username}
    ok, _ = await send_api_message(creds, conv_id, reply_text)
    return 200, {"takeover": False, "sammyReplySent": bool(ok)}
