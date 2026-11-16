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
   - No channel-specific reply cap; shared runtime policy applies.
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
import random
import sys
import time
from contextlib import contextmanager
import sqlite3
from urllib.parse import quote, urlencode
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import bot_gateway
import channel_accounts
import config as cfgmod
import conversations
import localefmt
from zernio_delivery import classify_delivery, retry_delay

# Store file for durable deduplication and batching state
STATE_FILE = cfgmod.STATE_DIR / "zernio_state.json"
MAX_AGE_SECONDS = 48 * 3600  # 48 hours for deduplication TTL
BATCH_SECONDS = 5.0
API_BASE = "https://zernio.com/api/v1"
MAX_BODY_BYTES = 256 * 1024



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
        return {"account_id": aid, "username": uname, "secret": sec, "api_key": key or (connection_api_key(str(d["connection_id"])) if d.get("connection_id") else _fallback_api_key())}

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


def available_connections() -> List[dict]:
    """Return only public identifiers for enabled Zernio connections."""
    import mcp_store
    return [{"id": c["id"], "label": c.get("label") or c["id"]}
            for c in mcp_store.list_connections()
            if "zernio" in str(c.get("connector_id") or c.get("id") or "").lower()
            and c.get("enabled")]


def connection_api_key(connection_id: str = "") -> str:
    """Resolve an explicit connection, or the unique default, entirely on the server."""
    import mcp_store
    matches = available_connections()
    if connection_id:
        matches = [c for c in matches if c["id"] == connection_id]
    if len(matches) != 1:
        return ""
    return str((mcp_store.connection_secrets(matches[0]["id"]) or {}).get("api_key") or "").strip()


def _fallback_api_key() -> str:
    try:
        return connection_api_key()
    except Exception:
        return ""


class CredentialsError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _rest_accounts(key: str) -> List[dict]:
    """Read real accounts with cursor pagination, returning public identity fields only."""
    if not key:
        raise CredentialsError("missing_api_key")
    import urllib.request
    import urllib.error
    out, cursor, seen = [], "", set()
    while True:
        params = {"platform": "instagram", "limit": 100}
        if cursor:
            params["cursor"] = cursor
        req = urllib.request.Request(API_BASE + "/accounts?" + urlencode(params), headers={
            "Authorization": f"Bearer {key}", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            raise CredentialsError("invalid_api_key" if exc.code in (401, 403) else "provider_unavailable") from None
        except Exception:
            raise CredentialsError("provider_unavailable") from None
        if not isinstance(data, dict) or not isinstance(data.get("accounts"), list):
            raise CredentialsError("invalid_provider_response")
        for account in data["accounts"]:
            if not isinstance(account, dict) or account.get("platform") != "instagram":
                continue
            aid = str(account.get("_id") or account.get("id") or account.get("accountId") or "")
            username = str(account.get("username") or "").lstrip("@")
            if aid and username:
                out.append({"id": aid, "username": username, "platform": "instagram"})
        cursor = (data.get("pagination") or {}).get("nextCursor")
        if not cursor:
            return out
        if cursor in seen:
            raise CredentialsError("invalid_provider_response")
        seen.add(cursor)


def connected_instagram_accounts(connection_id: str = "", api_key: str = "") -> List[dict]:
    return _rest_accounts(api_key or connection_api_key(connection_id))


async def whoami(cr: dict) -> dict:
    try:
        accounts = await asyncio.to_thread(_rest_accounts, cr.get("api_key") or "")
    except CredentialsError as exc:
        return {"ok": False, "error": exc.code}
    matched = next((a for a in accounts if a["id"] == cr.get("account_id")), None)
    if not matched:
        return {"ok": False, "error": "account_not_found"}
    if matched["username"].casefold() != str(cr.get("username") or "").lstrip("@").casefold():
        return {"ok": False, "error": "account_username_mismatch"}
    return {"ok": True, "account": matched}


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
    """Transactional SQLite journal. Import legacy JSON once; never discard corrupt data.

    A separate SQLite write lock per conversation serializes model/send work across
    processes without holding the shared journal transaction over a network await.
    OS closes those locks automatically after a worker crash.
    """
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.db_path = file_path.with_suffix(".sqlite3")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS journal (id INTEGER PRIMARY KEY, data TEXT NOT NULL)")
            row = db.execute("SELECT id FROM journal WHERE id=1").fetchone()
            if not row:
                data = json.loads(file_path.read_text()) if file_path.exists() else {}
                for key in ("events", "messages", "conversations"):
                    data.setdefault(key, {})
                data["messages"] = {json.dumps(k.split(":", 1), separators=(",", ":")) if ":" in k and not k.startswith("[") else k: v
                                    for k, v in data["messages"].items()}
                db.execute("INSERT OR IGNORE INTO journal VALUES(1, ?)", (json.dumps(data),))
        os.chmod(self.db_path, 0o600)

    def _connect(self):
        return sqlite3.connect(self.db_path, timeout=10)

    @contextmanager
    def transaction(self):
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            data = json.loads(db.execute("SELECT data FROM journal WHERE id=1").fetchone()[0])
            yield data
            db.execute("UPDATE journal SET data=? WHERE id=1", (json.dumps(data),))
            db.commit()
        finally:
            db.close()

    def load(self) -> dict:
        with self._connect() as db:
            return json.loads(db.execute("SELECT data FROM journal WHERE id=1").fetchone()[0])

    def save(self, data: dict):
        # Compatibility helper for migration/tests. Production uses transaction().
        with self.transaction() as current:
            current.clear()
            current.update(data)

    def conversation_lock(self, key):
        digest = hashlib.sha256(key.encode()).hexdigest()
        directory = self.db_path.parent / "zernio-locks"
        directory.mkdir(exist_ok=True, mode=0o700)
        db = sqlite3.connect(directory / (digest + ".sqlite3"), timeout=0)
        try:
            db.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError:
            db.close()
            return None
        return db

    def prune(self, data: dict, now: float) -> dict:
        for key in ("events", "messages"):
            data[key] = {k: v for k, v in data[key].items() if float(v.get("ts") or now) > now - MAX_AGE_SECONDS}
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
        self.provider_account_id = self.creds.get("account_id") or ""
        self.account_id = ""  # Javis channel account ID, assigned by runtime
        self.bot_id = ""
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

    @property
    def webhook_active(self):
        return not self._stop and _REGISTRY.get(self.provider_account_id) is self

    def start(self):
        if not self.provider_account_id or not self.account_id or not self.bot_id:
            raise ValueError("Zernio requires provider, Javis account and bot IDs")
        existing = _REGISTRY.get(self.provider_account_id)
        if existing and existing is not self:
            raise ValueError("Zernio provider account already assigned")
        self._stop = False
        self.status = "polling"
        _REGISTRY[self.provider_account_id] = self
        _ACCOUNTS[self.provider_account_id] = self.creds
        try:
            resume_pending(self.provider_account_id)
        except Exception:
            self.stop()
            raise

    def stop(self):
        self._stop = True
        self.status = "stopped"
        if _REGISTRY.get(self.provider_account_id) is self:
            _REGISTRY.pop(self.provider_account_id, None)
            _ACCOUNTS.pop(self.provider_account_id, None)

    async def _send(self, client, chat, text):
        return await send_api_message(self.creds, chat, text)

    async def send_text(self, conversation_id: str, text: str, idempotency_key: str = "") -> Tuple[bool, str]:
        return await send_api_message(self.creds, conversation_id, text, idempotency_key)

    async def send_delivery(self, conversation_id, text, idempotency_key):
        return await send_api_delivery(self.creds, conversation_id, text, idempotency_key)

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
async def send_api_message(creds: dict, conversation_id: str, text: str, idempotency_key: str = "") -> Tuple[bool, str]:
    """Keep the legacy tuple contract for public callers."""
    result = await send_api_delivery(creds, conversation_id, text, idempotency_key)
    return result["kind"] == "accepted", result["code"]


async def send_api_delivery(creds: dict, conversation_id: str, text: str, idempotency_key: str = "") -> dict:
    """Return a sanitized structured result for durable delivery."""
    cid = str(conversation_id or "").strip()
    msg = str(text or "").strip()
    if not cid or not msg:
        return {"kind": "blocked", "code": "missing conversation_id or text", "retry_after_seconds": None}

    aid = creds.get("account_id") or ""
    api_key = creds.get("api_key") or _fallback_api_key()
    if not api_key:
        return {"kind": "blocked", "code": "missing_api_key", "retry_after_seconds": None}

    import httpx
    url = API_BASE + f"/inbox/conversations/{quote(cid, safe='')}/messages"
    payload = {"accountId": aid, "message": msg}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            return classify_delivery(resp.status_code, getattr(resp, "headers", {}).get("Retry-After"), _now())
    except Exception:
        return classify_delivery(None, None, _now())


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
    if len(raw) > MAX_BODY_BYTES:
        return 413, {"ok": False, "error": "body_too_large"}
    with _state_store.transaction() as state:
        return _receive_webhook(raw, headers, state)


def _receive_webhook(raw, headers, state):
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
    if not isinstance(acc_obj, dict):
        return 400, {"ok": False, "error": "invalid_account"}
    account_id = str(acc_obj.get("accountId") or acc_obj.get("id") or "").strip()

    # An account event must be signed by THAT account's configured secret.
    if account_id:
        bot = _REGISTRY.get(account_id)
        if not bot or bot._stop:
            return 404, {"ok": False, "error": "account_unmapped"}
        if not verify_signature(raw, sig, bot.secret):
            return 401, {"ok": False, "error": "invalid_signature"}
    elif event_name == "webhook.test":
        if not any(verify_signature(raw, sig, cr.get("secret", "")) for cr in _ACCOUNTS.values()):
            return 401, {"ok": False, "error": "invalid_signature"}
    else:
        return 400, {"ok": False, "error": "missing_account"}

    # 2. Check Deduplication
    state = _state_store.prune(state, now)
    if event_id in state["events"]:
        return 200, {"ok": True, "duplicate": True}

    # 3. Check Freshness / Replay
    try:
        import datetime
        occurred_at = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 400, {"ok": False, "error": "invalid_timestamp"}

    if occurred_at > now + 300 or (now - occurred_at) > MAX_AGE_SECONDS:
        return 202, {"ok": True, "ignored": "replay_or_historical"}

    def mark_event_handled(status_code: int, code: str):
        state["events"][event_id] = {"ts": now, "iso": ts_str}
        return status_code, {"ok": status_code < 400, "status": code}

    # 4. Handle webhook.test
    if event_name == "webhook.test" or body.get("test") is True:
        return mark_event_handled(200, "test")

    # 5. Handle non-message events
    if event_name != "message.received":
        return mark_event_handled(202, "ignored_event")

    # 6. Message Eligibility Checks
    msg = body.get("message") or {}
    if not isinstance(msg, dict):
        return 400, {"ok": False, "error": "invalid_message"}
    platform = str(acc_obj.get("platform") or msg.get("platform") or "").lower()
    if acc_obj.get("username") and str(acc_obj["username"]).lstrip("@").casefold() != bot.bot_username.lstrip("@").casefold():
        return 400, {"ok": False, "error": "account_username_mismatch"}
    if platform != "instagram":
        return mark_event_handled(202, "unsupported_platform")

    direction = str(msg.get("direction") or "").lower()
    if direction != "incoming" or msg.get("is_echo") or msg.get("isEcho"):
        return mark_event_handled(202, "echo")

    meta_obj = body.get("metadata") or {}
    if not isinstance(meta_obj, dict):
        return 400, {"ok": False, "error": "invalid_metadata"}
    if meta_obj.get("standby") or meta_obj.get("historical") or msg.get("historical") or msg.get("isHistorical"):
        return mark_event_handled(202, "standby_or_historical")

    msg_id = str(msg.get("id") or "").strip()
    platform_msg_id = str(msg.get("platformMessageId") or msg.get("id") or "").strip()
    sender = msg.get("sender") or {}
    if not isinstance(sender, dict):
        return 400, {"ok": False, "error": "invalid_sender"}
    sender_id = str(sender.get("id") or "").strip()
    sender_username = str(sender.get("username") or "").strip()

    if not msg_id or not platform_msg_id or not sender_id:
        return mark_event_handled(400, "invalid_message")

    # Check bot sender
    acc_username = bot.bot_username.lstrip("@").casefold()
    if sender_id == account_id or (sender_username and sender_username.lower() == acc_username):
        return mark_event_handled(202, "self_message")

    conv_obj = body.get("conversation") or {}
    if not isinstance(conv_obj, dict):
        return 400, {"ok": False, "error": "invalid_conversation"}
    conv_id = str(conv_obj.get("id") or msg.get("conversationId") or "").strip()
    if not conv_id:
        return mark_event_handled(400, "missing_conversation_id")

    # Message-level deduplication
    msg_key = _batch_key(account_id, platform_msg_id)
    if msg_key in state["messages"]:
        return mark_event_handled(200, "duplicate_message")

    _enqueue(state, bot, conv_id, [msg], now)
    state["events"][event_id] = {"ts": now, "iso": ts_str}
    return 202, {"ok": True, "status": "queued"}


def _batch_key(provider_id, conversation_id):
    return json.dumps([provider_id, conversation_id], separators=(",", ":"))


def _record_inbox(bot, conversation_id, message):
    sender = message.get("sender") or {}
    result = conversations.ghi_su_kien({
        "channel": "zernio", "account_id": bot.account_id,
        "account_name": bot.bot_username, "bot_id": str(bot.bot_id),
        "external_chat_id": conversation_id, "chat_type": "private",
        "chat_title": str(sender.get("name") or sender.get("username") or sender.get("id") or conversation_id),
        "external_message_id": message.get("platformMessageId") or message.get("id"),
        "sender_type": "customer", "sender_id": str(sender.get("id") or ""),
        "sender_name": str(sender.get("name") or sender.get("username") or ""),
        "message_type": "text", "text": str(message.get("text") or ""),
        "metadata": {"attachments": message.get("attachments") or [], "provider_account_id": bot.provider_account_id},
        "created_at": _now()})
    if not result.get("ok"):
        raise RuntimeError("inbox_write_failed")


def _enqueue(state, bot, conversation_id, messages, now):
    key = _batch_key(bot.provider_account_id, conversation_id)
    current = state["conversations"].setdefault(key, {
        "messages": [], "account_id": bot.provider_account_id, "conversation_id": conversation_id,
        "javis_account_id": bot.account_id, "bot_id": bot.bot_id})
    # Reassignment must never cause an old pending batch to run under another bot.
    if current.get("javis_account_id") != bot.account_id or current.get("bot_id") != bot.bot_id:
        state.setdefault("quarantined_batches", []).append(dict(current, reason="assignment_changed"))
        current = {"messages": [], "account_id": bot.provider_account_id, "conversation_id": conversation_id,
                   "javis_account_id": bot.account_id, "bot_id": bot.bot_id}
        state["conversations"][key] = current
    added = False
    for message in messages:
        msg_id = str(message.get("platformMessageId") or message["id"])
        msg_key = _batch_key(bot.provider_account_id, msg_id)
        if msg_key in state["messages"]:
            continue
        # Inbox commits first. A crash before journal commit is safe: inbox has unique message IDs.
        _record_inbox(bot, conversation_id, message)
        current["messages"].append(message)
        state["messages"][msg_key] = {"ts": now}
        added = True
    if added:
        current["due_at"] = now + BATCH_SECONDS
        _arm_timer(key, BATCH_SECONDS)


def _arm_timer(key, delay_seconds):
    previous = _TIMERS.pop(key, None)
    if previous:
        previous.cancel()
    loop = asyncio.get_running_loop()
    _TIMERS[key] = loop.call_later(max(0, delay_seconds), lambda: asyncio.create_task(_flush(key)))


def resume_pending(provider_id):
    # Old JSON batches used only the conversation ID and had no Javis assignment.
    # Bind only to the exact registered provider account, preserving messages and inbox.
    bot = _REGISTRY[provider_id]
    with _state_store.transaction() as state:
        for old_key, current in list(state["conversations"].items()):
            if current.get("account_id") != provider_id or current.get("conversation_id"):
                continue
            key = _batch_key(provider_id, old_key)
            if key in state["conversations"]:
                raise ValueError("legacy_batch_collision")
            for message in current.get("messages", []):
                _record_inbox(bot, old_key, message)
            current.update(conversation_id=old_key, javis_account_id=bot.account_id, bot_id=bot.bot_id)
            current.pop("takeover", None)
            current.pop("replies_in_window", None)
            state["conversations"][key] = state["conversations"].pop(old_key)
    for key, current in _state_store.load()["conversations"].items():
        if current.get("account_id") == provider_id:
            if current.get("handoff_pending"):
                _arm_timer(key, 0)
            elif current.get("messages") or current.get("processing"):
                due = current.get("next_retry_at") if current.get("processing") else current.get("due_at")
                _arm_timer(key, max(0, (due or _now()) - _now()))


async def _flush(key):
    _TIMERS.pop(key, None)
    guard = _state_store.conversation_lock(key)
    if guard is None:
        _arm_timer(key, 1)
        return
    try:
        await _flush_locked(key)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # Keep journaled batch for retry; do not include payloads or provider responses in logs.
        print(f"[zernio flush] {type(exc).__name__}", file=sys.stderr)
        _arm_timer(key, BATCH_SECONDS)
    finally:
        guard.close()


def delivery_issues(account_id: str) -> list:
    """Only public metadata for the requested Javis account, never batch contents."""
    result = []
    for current in _state_store.load()["conversations"].values():
        issue = current.get("delivery_issue")
        if current.get("javis_account_id") != account_id or not issue:
            continue
        public = {k: issue.get(k) for k in
                  ("id", "revision", "reason", "attempts", "next_retry_at", "created_at")}
        public["conversation_id"] = conversations.conversation_id_of(
            "zernio", account_id, current["conversation_id"])
        result.append(public)
    return result


def resolve_delivery_issue(account_id: str, issue_id: str, revision: int) -> int:
    """CAS under the same cross-process conversation lock as flush. No sending."""
    import chatbot_store
    snapshot = _state_store.load()
    key = next((key for key, c in snapshot["conversations"].items()
                if c.get("javis_account_id") == account_id and
                ((c.get("delivery_issue") or {}).get("id") == issue_id or
                 any(h["issue"]["id"] == issue_id for h in c.get("delivery_history", [])))), None)
    if key is None:
        return 404
    guard = _state_store.conversation_lock(key)
    if guard is None:
        return 409
    try:
        with _state_store.transaction() as state:
            current = state["conversations"].get(key) or {}
            issue = current.get("delivery_issue") or {}
            assigned = chatbot_store.bots_using_account(account_id)
            if (current.get("javis_account_id") != account_id or issue.get("id") != issue_id
                    or issue.get("revision") != revision or not current.get("delivery_batch")
                    or current.get("handoff_pending") or len(assigned) != 1
                    or assigned[0].get("id") != current.get("bot_id")):
                return 409
            current.setdefault("delivery_history", []).append({
                "issue": dict(issue, revision=revision + 1), "batch": current.pop("delivery_batch"),
                "resolution": "handled_by_staff", "resolved_at": _now()})
            current.pop("delivery_issue")
            # These messages already exist in the inbox. Recovery must not enqueue
            # them or enable AI; only future incoming messages can form a new batch.
            current["messages"] = []
        return 200
    finally:
        guard.close()


def _block_delivery(current, reason):
    """Commit handoff intent and evidence before touching the inbox database."""
    current["delivery_batch"] = {field: current.pop(field) for field in
        ("processing", "reply", "reply_created_at", "send_key", "attempts", "next_retry_at") if field in current}
    batch = current["delivery_batch"]
    previous = current.get("delivery_issue") or {}
    current["delivery_issue"] = {
        "id": batch["send_key"], "revision": previous.get("revision", 0) + 1, "reason": reason,
        "created_at": previous.get("created_at", _now()),
        "attempts": batch.get("attempts", 0), "next_retry_at": None}
    current["handoff_pending"] = True
    current.pop("blocked_reason", None)


def _complete_handoff(key, bot):
    current = _state_store.load()["conversations"][key]
    if not current.get("handoff_pending"):
        return
    cid = conversations.conversation_id_of("zernio", bot.account_id, current["conversation_id"])
    ok, _ = conversations.dat_che_do(cid, "human")
    if not ok:
        raise RuntimeError("delivery_handoff_failed")
    with _state_store.transaction() as state:
        state["conversations"][key]["handoff_pending"] = False


async def _flush_locked(key):
    with _state_store.transaction() as state:
        current = state["conversations"].get(key)
        if not current:
            return
        bot = _REGISTRY.get(current["account_id"])
        if not bot or bot._stop or current.get("javis_account_id") != bot.account_id or current.get("bot_id") != bot.bot_id:
            return
        conversation_id = current["conversation_id"]
        handoff_pending = current.get("handoff_pending")
    if handoff_pending:
        _complete_handoff(key, bot)
    with _state_store.transaction() as state:
        current = state["conversations"][key]
        if current.get("delivery_batch"):
            # New messages already live in the inbox; never retry the archived batch.
            current["messages"] = []
            return
        if not current.get("processing"):
            delay = current.get("due_at", 0) - _now()
            if delay > 0:
                _arm_timer(key, delay)
                return
            if not current.get("messages"):
                return
            current["processing"] = current["messages"]
            current["messages"] = []
        batch = current["processing"]
        assignment = (current["javis_account_id"], current["bot_id"])
        reply = current.get("reply")
        send_key = current.setdefault("send_key", "zernio-" + hashlib.sha256((key + json.dumps([m.get("platformMessageId") or m["id"] for m in batch])).encode()).hexdigest())

        # This channel has no media reader. Preserve the whole batch for staff
        # before any model call, including captions and albums.
        unsupported_media = any(message.get("attachments") for message in batch)
        if unsupported_media:
            _block_delivery(current, "unsupported_media")

    if unsupported_media:
        _complete_handoff(key, bot)
        return

    def owns_batch(current):
        return current and (current.get("javis_account_id"), current.get("bot_id")) == assignment and current.get("processing") == batch

    def active():
        return (bot.account_id, bot.bot_id) == assignment and _REGISTRY.get(bot.provider_account_id) is bot and not bot._stop and conversations.che_do(
            "zernio", bot.account_id, conversation_id) != "human"

    if active():
        if reply is None:
            text = "\n".join(str(m.get("text") or "") for m in batch).strip()
            sender = batch[-1].get("sender") or {}
            meta = {"platform": "zernio", "chat_id": conversation_id, "chat_type": "private",
                    "account_id": bot.account_id, "provider_account_id": bot.provider_account_id,
                    "user_id": str(sender.get("id") or ""),
                    "user_name": str(sender.get("name") or sender.get("username") or ""),
                    "username": str(sender.get("username") or ""), "mentioned": True,
                    "message_id": batch[-1].get("platformMessageId") or batch[-1]["id"],
                    "_defer_zernio_delivery": True}
            result = await bot.answer_fn(text, meta, None) if text else ""
            reply = "" if isinstance(result, dict) and result.get("im_lang") else str(
                result.get("text") or "") if isinstance(result, dict) else str(result or "")
            with _state_store.transaction() as state:
                if not owns_batch(state["conversations"].get(key)):
                    return
                state["conversations"][key]["reply"] = reply
                state["conversations"][key]["reply_created_at"] = _now()
        if reply.strip() and active():
            with _state_store.transaction() as state:
                current = state["conversations"][key]
                if not owns_batch(current):
                    return
                expired = _now() >= current.get("reply_created_at", 0) + 23 * 3600
                if expired:
                    _block_delivery(current, "idempotency_window_expired")
                else:
                    delay = current.get("next_retry_at", 0) - _now()
                    if delay > 0:
                        _arm_timer(key, delay)
                        return
                    attempt = current.get("attempts", 0)
                    current["attempts"] = attempt + 1
                    # Persist a retry guard before HTTP too, including crash during send.
                    current["next_retry_at"] = min(
                        _now() + retry_delay(attempt, None, random.random()),
                        current["reply_created_at"] + 23 * 3600)
            if expired:
                _complete_handoff(key, bot)
                return
            result = await bot.send_delivery(conversation_id, reply.strip(), send_key)
            if result["kind"] != "accepted":
                with _state_store.transaction() as state:
                    current = state["conversations"].get(key)
                    if not owns_batch(current):
                        return
                    next_retry = _now() + retry_delay(attempt, result["retry_after_seconds"], random.random())
                    reason = result["code"] if result["kind"] == "blocked" else (
                        "idempotency_window_expired" if next_retry >= current["reply_created_at"] + 23 * 3600 else "")
                    if reason:
                        _block_delivery(current, reason)
                    else:
                        current["next_retry_at"] = next_retry
                        previous = current.get("delivery_issue") or {}
                        current["delivery_issue"] = {
                            "id": send_key, "revision": previous.get("revision", 0) + 1,
                            "reason": result["code"], "created_at": previous.get("created_at", _now()),
                            "attempts": current["attempts"], "next_retry_at": next_retry}
                if reason:
                    _complete_handoff(key, bot)
                else:
                    _arm_timer(key, next_retry - _now())
                return
            receipt = conversations.ghi_su_kien({
                "channel": "zernio", "account_id": bot.account_id, "bot_id": str(bot.bot_id),
                "account_name": bot.bot_username, "external_chat_id": conversation_id,
                "chat_type": "private", "external_message_id": send_key,
                "sender_type": "ai", "sender_name": bot.bot_username,
                "message_type": "text", "text": reply.strip(),
                "metadata": {"provider_account_id": bot.provider_account_id, "delivery": "accepted"},
                "created_at": _now()})
            if not receipt.get("ok"):
                raise RuntimeError("outbound_inbox_write_failed")
    with _state_store.transaction() as state:
        current = state["conversations"][key]
        if not owns_batch(current):
            return
        current.pop("processing", None)
        current.pop("reply", None)
        current.pop("reply_created_at", None)
        for field in ("send_key", "attempts", "next_retry_at", "delivery_issue"):
            current.pop(field, None)
        if current.get("messages"):
            _arm_timer(key, max(0, current.get("due_at", _now()) - _now()))


async def handle_inbound(payload: dict, auth_header: str) -> Tuple[int, dict]:
    """Legacy adapter, authenticated and pinned to one provider account by server configuration.

    It durably enqueues through the same inbox/debounce path as the public webhook.
    Client-supplied bot IDs, limits and policy cannot change server routing or behavior.
    """
    expected = os.environ.get("ZERNIO_ADAPTER_TOKEN", "").strip()
    provider_id = os.environ.get("ZERNIO_ADAPTER_ACCOUNT_ID", "").strip()
    auth = str(auth_header or "")
    if not expected or not provider_id or not auth.startswith("Bearer ") or not hmac.compare_digest(auth[7:], expected):
        return 401, {"ok": False, "error": "unauthorized"}
    if not isinstance(payload, dict) or not isinstance(payload.get("account"), dict):
        return 400, {"ok": False, "error": "invalid_payload"}
    account = payload["account"]
    if str(account.get("accountId") or account.get("id") or "") != provider_id:
        return 403, {"ok": False, "error": "account_scope_mismatch"}
    bot = _REGISTRY.get(provider_id)
    if not bot or bot._stop:
        return 404, {"ok": False, "error": "account_unmapped"}
    if account.get("platform", "instagram") != "instagram":
        return 400, {"ok": False, "error": "unsupported_platform"}
    if payload.get("bot_id") or payload.get("botId"):
        return 400, {"ok": False, "error": "client_routing_forbidden"}
    conversation_id = payload.get("conversationId")
    messages = payload.get("messages")
    if not isinstance(conversation_id, str) or not conversation_id.strip() or not isinstance(messages, list) or not messages:
        return 400, {"ok": False, "error": "invalid_messages"}
    for message in messages:
        if not isinstance(message, dict) or not message.get("id") or not isinstance(message.get("sender"), dict) or not message["sender"].get("id"):
            return 400, {"ok": False, "error": "invalid_message"}
        if str(message["sender"].get("id")) == provider_id or str(message["sender"].get("username") or "").lstrip("@").casefold() == bot.bot_username.lstrip("@").casefold():
            return 400, {"ok": False, "error": "self_message"}
        if message.get("direction", "incoming") != "incoming" or message.get("isEcho") or message.get("is_echo") or message.get("historical"):
            return 400, {"ok": False, "error": "ineligible_message"}
    with _state_store.transaction() as state:
        _state_store.prune(state, _now())
        _enqueue(state, bot, conversation_id, messages, _now())
    return 202, {"ok": True, "status": "queued", "takeover": conversations.che_do(
        "zernio", bot.account_id, conversation_id) == "human", "replySent": False,
        "sammyReplySent": False}
