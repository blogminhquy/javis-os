"""Internal API channel (0.451.0): a server you run asks ONE dedicated Chatbot over HTTP.

Built for a staff web app (the first caller is the Go backend of Lạc Lạc's "Manager"): staff ask about their work
inside that app, and its backend forwards the question here and shows the reply.

Why a channel and not the existing API token: a `chat`-scope API token runs `/chat` AS THE OWNER, with every tool,
every brain and the shell. This channel runs a Chatbot instead, so every fence a Chatbot already has still holds:
it sees only its own brain, runs no shell command and reaches no data source at the low level. The two doors never
share anything: a key of this channel opens `TURN_PATH` and nothing else, and an API token does not open `TURN_PATH`.

The account secret is a KEY Javis generates (`new_key`), shown to the owner exactly once. The channel-account store
keeps one encrypted secret per account; here that secret is the SHA-256 of the key, so nothing on disk can give the
key back. A call finds its account by hashing the key and comparing in constant time (`account_for_key`); the
account then names exactly one bot. The caller never says which bot.

Rules enforced here in code, not by instructions to the model:
  1. Permission ceiling: the bot runs at "Chỉ đọc" (suggest) or "Đọc tài liệu" (read_docs) only. Higher, or a per-chat
     exception raising it higher, answers 403 and the bot card turns red with the reason. `chatbot_runtime` checks
     `PERMISSION_CEILING` a second time inside the turn, so a future caller that skips this module still cannot pass.
  2. `scopes` from the caller is TRUSTED (it comes with the key) and opens private documents: a file under
     `rieng-theo-nhom/<scope>/` or with `chat_scope` naming any of them. `conversation_id` is NEVER a scope.
  3. `context` is UNTRUSTED data: it reaches the model inside a fenced data block (`chatbot_runtime.attached_data_block`)
     and never the inbox. `text` at most 4,000 characters, `context` at most 8,000.
  4. Rate limits per conversation and per account, set on the account form.
  5. Callers only from `JAVIS_CHATBOT_API_ALLOW` (CIDR list; default loopback and Docker's private range), and never
     through a proxy or tunnel (a forwarding header means the request came from outside).
  6. Nothing about the machine leaks: the bot runs with `giau_trang_thai`, and a failure answers a generic sentence
     while the detail goes to the server log.
  7. Key guessing: the same per-IP counter and `auth_audit.jsonl` as the API token (10 misses in 5 minutes, 15 minutes
     banned, only the first 12 characters logged).
"""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import os
import re
import secrets
import sys
import time
from collections import deque
from typing import Optional

import localefmt
from channels import KenhSpec

SPEC = KenhSpec(
    id="api", nhan="API nội bộ", kind="bot", logo="api", mau="#475569",
    lay_token=("Javis tự sinh khoá khi bạn bấm Lưu và chỉ hiện đúng một lần. Dán khoá đó vào máy chủ sẽ gọi bot "
               "(header Authorization: Bearer)."),
    tom_tat=("Cho một máy chủ của bạn (vd web nội bộ) hỏi bot qua HTTP. Bot chỉ chạy ở mức Chỉ đọc hoặc Đọc tài liệu, "
             "không gửi tin ra ngoài."),
    nang_luc={"nhom": False, "gui_chu": False, "gui_file": False},
    en={
        "nhan": "Internal API",
        "lay_token": ("Javis generates a key when you click Save and shows it exactly once. Put that key on the server "
                      "that calls the bot (header Authorization: Bearer)."),
        "tom_tat": ("Lets one of your servers (an internal web app, say) ask the bot over HTTP. The bot runs at Read "
                    "only or Read documents, and sends nothing out."),
    },
)

TURN_PATH = "/chatbot-api/v1/turn"
# The add-account form asks for no token: Javis makes the key (routes/channels.py reads this flag).
GENERATED_KEY = True
# The highest permission level a bot may run at on this channel (chatbot_runtime reads it inside every turn).
PERMISSION_CEILING = "read_docs"
ALLOWED_LEVELS = ("suggest", "read_docs")
GUIDE = {"vi": "25-chatbot.md", "en": "25-chatbots.md"}

KEY_PREFIX = "jvc_"
KEY_BYTES = 32
TEXT_MAX = 4_000
CONTEXT_MAX = 8_000
BODY_MAX = 64_000
TURN_TIMEOUT_S = 90
CONVERSATION_ID_MAX = 60       # "api:" + this stays within the 64 characters a chat id may have (chatbot_store._clean_ma)
SCOPES_MAX = 20
DEDUPE_MAX = 5_000
DEDUPE_TTL_S = 24 * 3600

ENV_ALLOW = "JAVIS_CHATBOT_API_ALLOW"
# Loopback plus 172.16.0.0/12, the range Docker gives its bridge and user networks. Anything else must be listed.
DEFAULT_ALLOW = "127.0.0.0/8,::1/128,172.16.0.0/12"
# Same list as main._FORWARD_HEADERS: a reverse proxy or tunnel adds one of these, a server calling directly does not.
# Nginx Proxy Manager runs in the same Docker network, so without this check the whole Internet would come in through
# it from an allowed address.
_FORWARD_HEADERS = ("x-forwarded-for", "x-real-ip", "forwarded", "cf-connecting-ip")

_CONV_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]*$")
_SCOPE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,79}$")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Rate limits, editable on the account form. Stored in the account's `meta`.
SETTINGS = (
    {"key": "conv_limit", "default": 20, "min": 1, "max": 1000,
     "vi": "Số lượt mỗi hội thoại", "en": "Turns per conversation"},
    {"key": "conv_window_min", "default": 10, "min": 1, "max": 1440,
     "vi": "trong (phút)", "en": "within (minutes)"},
    {"key": "account_per_hour", "default": 300, "min": 1, "max": 100_000,
     "vi": "Số lượt cả tài khoản mỗi giờ", "en": "Turns per hour, whole account"},
)

# account id -> ApiBot running for it. Filled by `ApiBot._watch`, read by `handle_http`.
_REGISTRY: dict = {}
# (account id, message id) -> {"ts", "fut"}: the first call with a message id runs, any later one gets its answer.
_DONE: dict = {}
# rate-limit key -> deque of turn times
_HITS: dict = {}


# ============================================================
# Key
# ============================================================
def key_hash(raw: str) -> str:
    return "sha256:" + hashlib.sha256(str(raw or "").encode("utf-8")).hexdigest()


def new_key() -> tuple:
    """(raw key, what the account store keeps). The raw key goes to the owner once and is never written anywhere."""
    raw = KEY_PREFIX + secrets.token_urlsafe(KEY_BYTES)
    return raw, key_hash(raw)


def key_meta(raw: str) -> dict:
    """What the account card may show about a key: its first 12 characters, like the API token."""
    return {"key_prefix": str(raw or "")[:12], "key_created_at": time.time()}


def account_for_key(raw: str) -> Optional[dict]:
    """The account of this channel whose key this is, or None. Constant-time compare of the hashes."""
    raw = str(raw or "").strip()
    if not raw.startswith(KEY_PREFIX):
        return None
    import channel_accounts
    want = key_hash(raw)
    found = None
    for a in channel_accounts.list_accounts(SPEC.id):
        stored = channel_accounts.get_token(a.get("id") or "")
        if stored and secrets.compare_digest(stored, want) and found is None:
            found = a
    return found


async def verify_token(token: str) -> dict:
    """kind="bot" contract. This channel takes no pasted token: the key is generated on Save."""
    return {"ok": False, "error": localefmt.chu("Kênh API nội bộ không dùng token dán vào: Javis tự sinh khoá khi lưu.",
                                                "The internal API channel takes no pasted token: Javis generates the key on Save.")}


# ============================================================
# Account settings (rate limits)
# ============================================================
def default_settings() -> dict:
    return {s["key"]: s["default"] for s in SETTINGS}


def settings_of(account: Optional[dict]) -> dict:
    meta = (account or {}).get("meta") or {}
    out = default_settings()
    for s in SETTINGS:
        try:
            v = int(meta.get(s["key"]))
        except (TypeError, ValueError):
            continue
        if s["min"] <= v <= s["max"]:
            out[s["key"]] = v
    return out


def clean_settings(data) -> tuple:
    """Validate settings from the account form. Returns (dict, "") or (None, reason). Never clamps quietly."""
    if isinstance(data, str):
        try:
            data = json.loads(data or "{}")
        except ValueError:
            return None, localefmt.chu("Cài đặt không đọc được.", "The settings cannot be read.")
    if not isinstance(data, dict):
        return None, localefmt.chu("Cài đặt không đọc được.", "The settings cannot be read.")
    out = {}
    for s in SETTINGS:
        if s["key"] not in data:
            continue
        try:
            v = int(str(data[s["key"]]).strip())
        except (TypeError, ValueError):
            v = None
        if v is None or not s["min"] <= v <= s["max"]:
            return None, localefmt.chu(f"\"{s['vi']}\" phải từ {s['min']} đến {s['max']}.",
                                       f"\"{s['en']}\" must be {s['min']} to {s['max']}.")
        out[s["key"]] = v
    return out, ""


def account_settings_spec() -> list:
    """The fields of the account form, labelled in the interface language (channels.cho_giao_dien sends this)."""
    return [{"key": s["key"], "nhan": localefmt.chu(s["vi"], s["en"]), "min": s["min"], "max": s["max"],
             "default": s["default"]} for s in SETTINGS]


# ============================================================
# Permission ceiling
# ============================================================
def ceiling_problem(cfg: Optional[dict], meta: Optional[dict] = None) -> str:
    """Why this bot may not answer on this channel ("" when it may). `meta` applies the per-chat exception of the turn:
    an exception may lower a chat, never raise it above the ceiling."""
    if not cfg:
        return ""
    import chatbot_store
    eff = chatbot_store.ap_ngoai_le(cfg, meta) if meta else cfg
    level = str(eff.get("muc_quyen") or chatbot_store.MUC_QUYEN_DEFAULT)
    if level in ALLOWED_LEVELS:
        return ""
    if eff is not cfg and str(cfg.get("muc_quyen") or "") in ALLOWED_LEVELS:
        return localefmt.chu("Ngoại lệ của cuộc chat này nâng bot lên quá mức Đọc tài liệu. Kênh API nội bộ chỉ chạy "
                             "Chỉ đọc hoặc Đọc tài liệu: hạ ngoại lệ đó trên trang Chatbot.",
                             "This chat's exception raises the bot above Read documents. The internal API channel only "
                             "runs Read only or Read documents: lower that exception on the Chatbot page.")
    return localefmt.chu("Bot đang ở mức quyền cao hơn Đọc tài liệu. Kênh API nội bộ chỉ chạy Chỉ đọc hoặc Đọc tài liệu: "
                         "hạ mức quyền của bot trên trang Chatbot thì kênh mới trả lời.",
                         "The bot runs above Read documents. The internal API channel only runs Read only or Read "
                         "documents: lower the bot's level on the Chatbot page and the channel answers again.")


def _bot_of(account_id: str) -> Optional[dict]:
    import chatbot_store
    bots = chatbot_store.bots_using_account(account_id)
    return next((b for b in bots if b.get("enabled")), bots[0] if bots else None)


# ============================================================
# Source address
# ============================================================
def allowed_networks() -> list:
    """Parsed `JAVIS_CHATBOT_API_ALLOW`. A bad entry is logged and skipped; an empty result allows nobody."""
    raw = os.environ.get(ENV_ALLOW)
    raw = DEFAULT_ALLOW if raw is None else raw
    nets = []
    for part in re.split(r"[\s,;]+", raw.strip()):
        if not part:
            continue
        try:
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            print(f"[chatbot-api] {ENV_ALLOW}: skipping a non-CIDR entry: {part!r}", file=sys.stderr)
    return nets


def source_allowed(ip: str, headers: Optional[dict] = None) -> bool:
    h = {str(k).lower(): v for k, v in (headers or {}).items()}
    if any(h.get(x) for x in _FORWARD_HEADERS):
        return False
    try:
        addr = ipaddress.ip_address(str(ip or "").strip())
    except ValueError:
        return False
    if getattr(addr, "ipv4_mapped", None):
        addr = addr.ipv4_mapped
    return any(addr.version == n.version and addr in n for n in allowed_networks())


# ============================================================
# Rate limits and duplicate messages
# ============================================================
def _room(key: tuple, limit: int, window_s: float, now: float) -> bool:
    q = _HITS.get(key)
    if q is None:
        return True
    while q and now - q[0] >= window_s:
        q.popleft()
    if not q:
        _HITS.pop(key, None)
        return True
    return len(q) < limit


def _take(key: tuple, now: float) -> None:
    _HITS.setdefault(key, deque()).append(now)


def rate_check(account: dict, conversation_id: str, now: Optional[float] = None) -> str:
    """"" when the turn may run (and it is counted), else "conversation" or "account"."""
    now = time.time() if now is None else now
    st = settings_of(account)
    aid = account.get("id") or ""
    k_conv, k_acc = ("conv", aid, conversation_id), ("acc", aid)
    if not _room(k_conv, st["conv_limit"], st["conv_window_min"] * 60, now):
        return "conversation"
    if not _room(k_acc, st["account_per_hour"], 3600, now):
        return "account"
    _take(k_conv, now)
    _take(k_acc, now)
    return ""


def _prune_done(now: float) -> None:
    for k in [k for k, v in _DONE.items() if now - v["ts"] > DEDUPE_TTL_S]:
        _DONE.pop(k, None)
    while len(_DONE) > DEDUPE_MAX:
        _DONE.pop(next(iter(_DONE)), None)


def reset_for_test() -> None:
    _REGISTRY.clear()
    _DONE.clear()
    _HITS.clear()


# ============================================================
# HTTP
# ============================================================
def _err(status: int, code: str, vi: str, en: str, **more) -> tuple:
    return status, {"ok": False, "code": code, "error": localefmt.chu(vi, en), **more}


def _clean_line(v, n: int) -> str:
    return " ".join(_CTRL_RE.sub(" ", str(v or "")).split())[:n]


def parse_body(raw: bytes) -> tuple:
    """(turn dict, None) or (None, error tuple). Every rejected field is named; nothing is silently trimmed."""
    if len(raw or b"") > BODY_MAX:
        return None, _err(413, "too_large", "Nội dung gửi lên quá lớn.", "The request body is too large.")
    try:
        d = json.loads((raw or b"").decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None, _err(400, "bad_request", "Thân request phải là JSON.", "The request body must be JSON.")
    if not isinstance(d, dict):
        return None, _err(400, "bad_request", "Thân request phải là một object JSON.", "The request body must be a JSON object.")

    def bad(field_vi, field_en):
        return None, _err(400, "bad_request", f"Trường {field_vi} thiếu hoặc không hợp lệ.",
                          f"Field {field_en} is missing or invalid.", field=field_en)

    mid = d.get("message_id")
    if not isinstance(mid, str) or not mid.strip() or len(mid) > 200 or _CTRL_RE.search(mid):
        return bad("message_id", "message_id")
    conv = d.get("conversation_id")
    if not isinstance(conv, str) or not (1 <= len(conv) <= CONVERSATION_ID_MAX) or not _CONV_RE.match(conv):
        return bad("conversation_id", "conversation_id")
    user = d.get("user")
    if not isinstance(user, dict):
        return bad("user", "user")
    uid = user.get("id")
    if not isinstance(uid, (str, int)) or isinstance(uid, bool) or not str(uid).strip() or len(str(uid)) > 64:
        return bad("user.id", "user.id")
    uname = _clean_line(user.get("name"), 80)
    scopes = d.get("scopes", [])
    if not isinstance(scopes, list) or len(scopes) > SCOPES_MAX or not all(
            isinstance(s, str) and _SCOPE_RE.match(s) for s in scopes):
        return bad("scopes", "scopes")
    text = d.get("text")
    if not isinstance(text, str) or not text.strip():
        return bad("text", "text")
    if len(text) > TEXT_MAX:
        return None, _err(413, "too_large", f"text dài quá {TEXT_MAX} ký tự.", f"text is longer than {TEXT_MAX} characters.",
                          field="text")
    ctx = d.get("context", "")
    if ctx is None:
        ctx = ""
    if not isinstance(ctx, str):
        return bad("context", "context")
    if len(ctx) > CONTEXT_MAX:
        return None, _err(413, "too_large", f"context dài quá {CONTEXT_MAX} ký tự.",
                          f"context is longer than {CONTEXT_MAX} characters.", field="context")
    return {"message_id": mid.strip(), "conversation_id": conv, "user_id": str(uid).strip(), "user_name": uname,
            "scopes": list(dict.fromkeys(scopes)), "text": text.strip(), "context": ctx.strip()}, None


def build_meta(account_id: str, turn: dict) -> dict:
    """The `meta` every transport gives the bot. The chat id is namespaced so a caller can never land in the session of
    a Telegram or Zalo chat of the same bot by picking a matching conversation id."""
    return {
        "platform": SPEC.id, "chat_id": "api:" + turn["conversation_id"], "chat_type": "private", "chat_title": "",
        "user_id": turn["user_id"], "user_name": turn["user_name"], "username": "",
        "message_id": turn["message_id"], "mentioned": True, "reply_to_bot": False, "account_id": account_id,
        # Trusted: these come with the key. The document search and the doc tools read them instead of the chat id.
        "doc_scopes": list(turn["scopes"]),
        # Untrusted: the runtime fences it as data for the model only (chatbot_runtime.attached_data_block).
        "attached_data": turn["context"],
    }


def _bearer(header: str) -> str:
    h = str(header or "")
    return h[7:].strip() if h[:7].lower() == "bearer " else ""


async def handle_http(auth_header: str, client_ip: str, headers: Optional[dict], body: bytes) -> tuple:
    """One `POST TURN_PATH`. Returns (HTTP status, JSON body). Never raises."""
    turn_id = "turn_" + secrets.token_hex(8)
    try:
        return await _handle(auth_header, client_ip, headers, body, turn_id)
    except Exception as e:      # noqa: BLE001 - the caller gets a generic sentence, the log keeps the detail
        print(f"[chatbot-api {turn_id}] {type(e).__name__}: {e}", file=sys.stderr)
        return _err(500, "internal", "Javis gặp lỗi khi xử lý lượt này.", "Javis hit an error handling this turn.",
                    turn_id=turn_id)


async def _handle(auth_header, client_ip, headers, body, turn_id) -> tuple:
    import config as cfgmod
    if not source_allowed(client_ip, headers):
        print(f"[chatbot-api] refused source {client_ip} (outside {ENV_ALLOW} or through a proxy)", file=sys.stderr)
        return _err(403, "forbidden_source", "Nguồn gọi không được phép.", "This source may not call the API.")
    if cfgmod.token_ip_banned(client_ip):
        return _err(429, "banned", "Sai khoá quá nhiều lần, thử lại sau 15 phút.",
                    "Too many wrong keys, try again in 15 minutes.")
    raw = _bearer(auth_header)
    account = account_for_key(raw) if raw else None
    if not account:
        if raw:
            cfgmod.note_token_failure(client_ip, raw[:12])
        return _err(401, "unauthorized", "Khoá sai hoặc đã được xoay.", "Wrong or rotated key.")
    turn, bad = parse_body(body)
    if bad:
        return bad
    aid = account["id"]
    bot = _REGISTRY.get(aid)
    cfg = _bot_of(aid)
    if not bot or bot._stop or not cfg or not cfg.get("enabled"):
        return _err(403, "bot_off", "Chưa có bot nào đang bật trên tài khoản API này.",
                    "No bot is switched on for this API account.")
    meta = build_meta(aid, turn)
    problem = ceiling_problem(cfg, meta)
    if problem:
        bot.flag_ceiling(problem)
        return 403, {"ok": False, "code": "permission_ceiling", "error": problem}

    now = time.time()
    _prune_done(now)
    key = (aid, turn["message_id"])
    seen = _DONE.get(key)
    if seen is not None:
        status, out = await asyncio.shield(seen["fut"])
        if status == 200:
            return 409, dict(out, duplicate=True)
        return status, out
    why = rate_check(account, turn["conversation_id"], now)
    if why:
        if why == "conversation":
            return _err(429, "rate_limited", "Hội thoại này hỏi quá nhanh, thử lại sau ít phút.",
                        "This conversation is asking too fast, try again in a few minutes.", limit="conversation")
        return _err(429, "rate_limited", "Tài khoản API đã hết lượt trong giờ này.",
                    "The API account has used up its turns for this hour.", limit="account")
    fut = asyncio.get_running_loop().create_future()
    _DONE[key] = {"ts": now, "fut": fut}
    result = None
    try:
        result = await _run(bot, turn, meta, aid, turn_id)
    finally:
        if result is None:
            result = _err(500, "internal", "Javis gặp lỗi khi xử lý lượt này.", "Javis hit an error handling this turn.",
                          turn_id=turn_id)
        fut.set_result(result)
        if result[0] != 200:
            # A failed turn is not "already processed": the caller may retry the same message id.
            _DONE.pop(key, None)
    return result


async def _run(bot, turn, meta, aid, turn_id) -> tuple:
    try:
        out = await asyncio.wait_for(bot.run_turn(turn["text"], meta), TURN_TIMEOUT_S)
    except asyncio.TimeoutError:
        print(f"[chatbot-api {turn_id}] over {TURN_TIMEOUT_S} seconds", file=sys.stderr)
        return _err(504, "timeout", "Bot trả lời quá lâu, thử lại sau.", "The bot took too long, try again later.",
                    turn_id=turn_id)
    except Exception as e:      # noqa: BLE001
        print(f"[chatbot-api {turn_id}] {type(e).__name__}: {e}", file=sys.stderr)
        return _err(502, "turn_failed", "Bot chưa trả lời được lúc này.", "The bot could not answer right now.",
                    turn_id=turn_id)
    out = out if isinstance(out, dict) else {}
    if out.get("failed"):
        # The runtime already rang the owner's bell and wrote the bot log; the caller learns only that it failed.
        print(f"[chatbot-api {turn_id}] the bot turn failed (details in the bot log)", file=sys.stderr)
        return _err(502, "turn_failed", "Bot chưa trả lời được lúc này.", "The bot could not answer right now.",
                    turn_id=turn_id)
    text = str(out.get("text") or "").strip()
    res = {"ok": True, "reply": "" if out.get("im_lang") else text, "turn_id": turn_id}
    res["silent"] = not res["reply"]
    if res["silent"]:
        import conversations
        if conversations.che_do(SPEC.id, aid, meta["chat_id"]) == "human":
            res["handed_over"] = True
    return 200, res


# ============================================================
# Transport
# ============================================================
class ApiBot:
    """Transport contract of `TelegramBot` (start/stop/status). Holds no connection: `start` registers the bot under its
    account id so `handle_http` can hand it turns. The key never reaches it; the route finds the account by itself."""

    def __init__(self, token, chat_id, answer_fn, command_fn=None, callback_fn=None, download_dir=None,
                 commands=None, precheck_fn=None, event_fn=None, giau_trang_thai=False, **_ignored):
        self.answer_fn = answer_fn
        self.giau_trang_thai = bool(giau_trang_thai)
        self.account_id = ""
        self._task = None
        self._stop = False
        self.status = "off"
        self.last_error = ""
        self.bot_id = ""
        self.bot_username = ""
        self.loi_danh_tinh = ""
        self.doc_moi_tin_nhom = False

    def flag_ceiling(self, problem: str) -> None:
        """Show the ceiling problem on the bot card (state error) until the level is fixed."""
        self.status = "error" if problem else "polling"
        self.last_error = problem or ""

    def _recheck(self) -> None:
        self.flag_ceiling(ceiling_problem(_bot_of(self.account_id)))

    async def _watch(self):
        old = _REGISTRY.get(self.account_id)
        if old is not None and old is not self:
            print(f"[chatbot-api] account {self.account_id} moved to a new bot", file=sys.stderr)
        _REGISTRY[self.account_id] = self
        try:
            while not self._stop:
                try:
                    self._recheck()
                except Exception as e:      # noqa: BLE001 - a broken store read must not kill the registration
                    print(f"[chatbot-api] permission check failed: {type(e).__name__}: {e}", file=sys.stderr)
                await asyncio.sleep(60)
        finally:
            if _REGISTRY.get(self.account_id) is self:
                _REGISTRY.pop(self.account_id, None)

    def start(self):
        self._stop = False
        self.status = "polling"
        if not self._task or self._task.done():
            self._task = asyncio.create_task(self._watch())

    def stop(self):
        self._stop = True
        self.status = "stopped"
        if _REGISTRY.get(self.account_id) is self:
            _REGISTRY.pop(self.account_id, None)
        if self._task:
            self._task.cancel()
            self._task = None

    async def run_turn(self, text: str, meta: dict):
        return await self.answer_fn(text, meta, None)

    async def send_text(self, chat, text):
        return False, localefmt.chu("Kênh API nội bộ không gửi tin ra ngoài.", "The internal API channel sends nothing out.")


Transport = ApiBot
