"""WeChat Official Account gateway over the official Official Account API (api.weixin.qq.com).

Which WeChat this is, and why. WeChat has three official doors and one unofficial one:

  - Official Account (this module): the business account customers follow and write to. Anybody on
    WeChat can message it, so it is the one that fits a customer chatbot.
  - WeChat ClawBot (Tencent's iLink Bot API, 2026): QR login with a personal WeChat and a long poll,
    no domain needed, but ONLY the person who scanned the code can talk to the bot. A personal
    assistant, not a customer channel.
  - WeCom customer service: needs a verified WeCom company.
  - Unofficial personal-account protocols (pad, web, hooks): against WeChat's terms and get the
    account banned. Javis does not use them.

Same shape as `zalo_oa_bot`: Javis cannot pull messages, WeChat POSTs every message a follower sends
to one URL. Two halves:

  - `WeChatBot`: the transport, same contract as `TelegramBot` (start/stop/status/send_text/
    send_file). `start()` opens no connection; it makes sure an access token can be fetched and
    registers the bot under its AppID.
  - `handle_webhook(raw, query, token)`: called by the `/wechat/webhook` route in main.py. It checks
    the signature, decrypts when the account runs in Safe mode and hands the message to the bot of
    the account it was sent to. One URL serves every account.

Credentials of one account (WeChat Official Accounts Platform, Settings and Development, Basic
Configuration):
  - AppID (wx + 16 characters) and AppSecret (32 hex characters): fetch the access token
  - EncodingAESKey (43 characters), optional: decrypts messages in Safe mode
  - Original ID (gh_...), optional: tells accounts apart when several run in Plaintext mode
The `Token` field of WeChat's server configuration is NOT pasted here: Javis generates one for the
whole machine and shows it on the Add account form (`/channels/webhook-info`), because WeChat checks
the URL before any account exists in Javis.

Rules of the platform that shape the code:
  1. Five seconds. WeChat wants an answer to its POST within 5 seconds and retries three times, and
     no agent turn is that fast. So the route answers "success" at once and the reply goes out later
     through the customer service message API (`/cgi-bin/message/custom/send`).
  2. That API needs a VERIFIED account (or the sandbox test account). An unverified account gets
     48001 and `_explain_error` says so in words.
  3. The reply window: about 48 hours after the follower's last message, and a limited number of
     messages per incoming one (45015, 45047). Outside it nothing goes out.
  4. The signature of a plaintext message covers only (token, timestamp, nonce), not the body. So a
     replayed query string could carry a forged body. Safe mode closes that: the signature covers the
     ciphertext and the body is AES encrypted. An account that has an EncodingAESKey accepts
     encrypted messages only, and every request must carry a recent timestamp.
  5. The access token lives 2 hours and the caller's IP must be on the account's IP whitelist
     (40164). `stable_token` is used so Javis does not invalidate the token of another system
     working on the same account.
  6. Text only up to 2048 BYTES, no markdown. JSON must go out as raw UTF-8: WeChat shows
     \\uXXXX escapes literally.
  7. Follower names are not readable any more (WeChat removed nickname from user/info in 2021), so
     a customer is known by OpenID only.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import struct
import sys
import time
from collections import deque
from pathlib import Path
from xml.etree import ElementTree

import httpx

import localefmt
import stt
from bot_gateway import HangLuot, dong_vet, parse_chat_ids, ten_tool
from messenger_bot import md_to_plain

API = os.getenv("JAVIS_WECHAT_API", "https://api.weixin.qq.com").rstrip("/")

CHANNEL = "wechat"
MAX_BYTES = 2000             # WeChat allows 2048 bytes per text; keep a margin
MAX_DEDUPE = 4000
MAX_DOWNLOAD_MB = 20
MAX_IMAGE_MB = 10            # media/upload type=image
MAX_BODY = 256 * 1024        # a WeChat message is a few KB; anything larger is not from WeChat
MAX_SKEW = 15 * 60           # a request older (or newer) than this is refused, see rule 4
TOKEN_MARGIN = 5 * 60        # fetch a new access token this long before the old one runs out
TYPING_EVERY = 10.0

# app_id -> WeChatBot currently running for it.
_REGISTRY: dict = {}
# Original ID (gh_...) -> app_id, learned from plaintext messages or pasted with the credentials.
_ORIGINAL: dict = {}


# ---- Credentials ------------------------------------------------------------------------
_FIELDS = ("app_id", "app_secret", "aes_key", "original_id")
_KEY_ALIASES = {"appid": "app_id", "secret": "app_secret", "appsecret": "app_secret",
                "encodingaeskey": "aes_key", "encoding_aes_key": "aes_key", "aeskey": "aes_key",
                "gh": "original_id", "originalid": "original_id", "id": "original_id"}


def split_credentials(raw) -> dict:
    """"<AppID> <AppSecret> [EncodingAESKey] [gh_...]" in any order -> dict with every key of `_FIELDS`.

    One string because the channel-account store keeps one encrypted secret per account. The parts
    are told apart by shape: the AppID starts with "wx", the AppSecret is 32 hex characters, the
    EncodingAESKey is exactly 43 letters and digits, the Original ID starts with "gh_". `key=value`
    parts are read by name.
    """
    out = {k: "" for k in _FIELDS}
    for part in re.split(r"[\s,;|]+", str(raw or "").strip()):
        if not part:
            continue
        if "=" in part[:20]:
            k, _, v = part.partition("=")
            k = k.strip().lower().replace("-", "_")
            k = _KEY_ALIASES.get(k, k)
            if k in _FIELDS:
                out[k] = v.strip()
            continue
        if re.fullmatch(r"gh_[0-9A-Za-z]{6,40}", part):
            out["original_id"] = part
        elif re.fullmatch(r"wx[0-9A-Za-z]{14,20}", part) and not out["app_id"]:
            out["app_id"] = part
        elif re.fullmatch(r"[0-9a-fA-F]{32}", part) and not out["app_secret"]:
            out["app_secret"] = part
        elif re.fullmatch(r"[0-9A-Za-z]{43}", part):
            out["aes_key"] = part
    return out


def dump_credentials(cr: dict) -> str:
    return " ".join(str(cr.get(k) or "") for k in _FIELDS if cr.get(k))


def missing_parts(cr: dict) -> list:
    return [n for n, k in (("AppID", "app_id"), ("AppSecret", "app_secret")) if not cr.get(k)]


def aes_key_bytes(aes_key: str):
    """The 32 raw bytes of an EncodingAESKey, or None when it is not one."""
    try:
        key = base64.b64decode(str(aes_key or "") + "=")
    except Exception:
        return None
    return key if len(key) == 32 else None


# ---- Signature and encryption -----------------------------------------------------------
def _sha1_sorted(*parts) -> str:
    return hashlib.sha1("".join(sorted(str(p or "") for p in parts)).encode("utf-8")).hexdigest()


def check_signature(token: str, signature: str, timestamp: str, nonce: str, encrypt: str = "") -> bool:
    """True when `signature` is sha1 of the sorted (token, timestamp, nonce[, Encrypt]) joined.

    Without `encrypt` this is the `signature` of the URL check and of a plaintext message; with it,
    the `msg_signature` of an encrypted one. Constant-time compare; an empty token never matches."""
    token = str(token or "")
    got = str(signature or "").strip().lower()
    if not token or not got or not str(timestamp or "") or not str(nonce or ""):
        return False
    parts = [token, timestamp, nonce] + ([encrypt] if encrypt else [])
    return hmac.compare_digest(_sha1_sorted(*parts), got)


def fresh_timestamp(timestamp, now=None) -> bool:
    try:
        ts = int(str(timestamp or "").strip())
    except Exception:
        return False
    return abs((now if now is not None else time.time()) - ts) <= MAX_SKEW


def decrypt(aes_key: str, encrypted: str) -> tuple:
    """(xml text, app id) of one `Encrypt` value. Raises ValueError when it does not open.

    AES-256-CBC, key = base64(EncodingAESKey + "="), IV = first 16 bytes of the key, PKCS#7 padding
    to 32. Plaintext = 16 random bytes + 4-byte big-endian length + message + AppID."""
    key = aes_key_bytes(aes_key)
    if key is None:
        raise ValueError("bad EncodingAESKey")
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    try:
        blob = base64.b64decode(str(encrypted or ""), validate=False)
    except Exception as e:
        raise ValueError("bad base64") from e
    if not blob or len(blob) % 16:
        raise ValueError("bad ciphertext length")
    d = Cipher(algorithms.AES(key), modes.CBC(key[:16])).decryptor()
    plain = d.update(blob) + d.finalize()
    pad = plain[-1]
    if pad < 1 or pad > 32 or len(plain) < 20 + pad:
        raise ValueError("bad padding")
    body = plain[16:-pad]
    (n,) = struct.unpack(">I", body[:4])
    if n > len(body) - 4:
        raise ValueError("bad length")
    try:
        return body[4:4 + n].decode("utf-8"), body[4 + n:].decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError("bad plaintext") from e


def encrypt(aes_key: str, app_id: str, text: str, random16: bytes = None) -> str:
    """The reverse of `decrypt`. Javis never sends an encrypted reply (it answers "success" and uses
    the customer service API); this exists so the tests build the exact envelope WeChat sends."""
    key = aes_key_bytes(aes_key)
    if key is None:
        raise ValueError("bad EncodingAESKey")
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    msg = str(text or "").encode("utf-8")
    plain = (random16 or os.urandom(16)) + struct.pack(">I", len(msg)) + msg + str(app_id or "").encode("utf-8")
    pad = 32 - len(plain) % 32
    plain += bytes([pad]) * pad
    e = Cipher(algorithms.AES(key), modes.CBC(key[:16])).encryptor()
    return base64.b64encode(e.update(plain) + e.finalize()).decode("ascii")


def parse_xml(raw) -> dict:
    """The flat `<xml><Tag>value</Tag>...</xml>` WeChat sends -> {Tag: value}. {} when it is not that.

    The URL is public, so the parser never sees a DTD: a document that declares one (entity
    expansion, external entities) is refused before parsing. WeChat never sends one."""
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return {}
    s = str(raw or "").strip()
    if not s or len(s) > MAX_BODY or "<!DOCTYPE" in s.upper() or "<!ENTITY" in s.upper():
        return {}
    try:
        root = ElementTree.fromstring(s)
    except Exception:
        return {}
    if root.tag != "xml":
        return {}
    return {str(c.tag): (c.text or "").strip() for c in root if isinstance(c.tag, str)}


# ---- Access token -----------------------------------------------------------------------
class TokenCache:
    """Access tokens by AppID, in memory only: `stable_token` returns the same token until it is
    close to expiry, so a restart costs one call and nothing has to be stored."""

    def __init__(self):
        self._tokens: dict = {}      # app_id -> (token, expires_at, fingerprint of the secret it was fetched with)
        self._locks: dict = {}

    def _lock(self, key: str) -> asyncio.Lock:
        lk = self._locks.get(key)
        if lk is None:
            lk = self._locks[key] = asyncio.Lock()
        return lk

    @staticmethod
    def _fingerprint(cr: dict) -> str:
        return hashlib.sha256(str(cr.get("app_secret") or "").encode()).hexdigest()

    def drop(self, app_id: str) -> None:
        self._tokens.pop(str(app_id or ""), None)

    async def get(self, client, cr: dict, rejected: str = "", fresh: bool = False) -> tuple:
        """(token, error). `rejected` is a token WeChat just refused: it is not reused, and when
        WeChat hands the same one back a forced refresh is asked for once. `fresh` asks WeChat even
        when a token is cached (checking pasted credentials). A token fetched with another AppSecret
        is never served: an owner who corrects the secret must not be told the wrong one works."""
        app_id = str(cr.get("app_id") or "")
        thieu = missing_parts(cr)
        if thieu:
            return "", localefmt.chu("Còn thiếu: " + ", ".join(thieu), "Missing: " + ", ".join(thieu))
        fp = self._fingerprint(cr)
        async with self._lock(app_id):
            hit = self._tokens.get(app_id)
            if (hit and not fresh and hit[2] == fp and hit[0] != rejected
                    and hit[1] - time.time() > TOKEN_MARGIN):
                return hit[0], ""
            res = await fetch_token(client, cr)
            if res.get("ok") and rejected and res["access_token"] == rejected:
                res = await fetch_token(client, cr, force=True)
            if not res.get("ok"):
                return "", res.get("error", "")
            self._tokens[app_id] = (res["access_token"], res["expires_at"], fp)
            return res["access_token"], ""


async def fetch_token(client, cr: dict, force: bool = False) -> dict:
    """One `stable_token` call. {"ok", "access_token", "expires_at"} or {"ok": False, "code", "error"}."""
    try:
        r = await client.post(f"{API}/cgi-bin/stable_token", json={
            "grant_type": "client_credential", "appid": str(cr.get("app_id") or ""),
            "secret": str(cr.get("app_secret") or ""), "force_refresh": bool(force)})
        try:
            d = r.json() or {}
        except Exception:
            d = {}
    except Exception as e:
        return {"ok": False, "net_error": True,
                "error": localefmt.chu(f"Không nối được WeChat: {e}", f"Could not reach WeChat: {e}")}
    if not d.get("access_token"):
        code = d.get("errcode") or r.status_code
        return {"ok": False, "code": code,
                "error": _explain_error(code, d.get("errmsg") or f"HTTP {r.status_code}")}
    try:
        life = float(d.get("expires_in") or 7200)
    except Exception:
        life = 7200.0
    return {"ok": True, "access_token": str(d["access_token"]), "expires_at": time.time() + life}


TOKENS = TokenCache()

# Codes that mean "this access token is no good", so one new token is fetched and the call repeated.
_TOKEN_CODES = (40001, 40014, 41001, 42001)


# ---- Webhook ----------------------------------------------------------------------------
def registered() -> dict:
    return dict(_REGISTRY)


def _bot_for_plain(original_id: str):
    """The running bot a plaintext message for `original_id` belongs to, or (None, why).

    A plaintext message names the account by its Original ID only, which no API maps to an AppID.
    So the id is learned: it is known when pasted with the credentials, and otherwise the first
    message binds it to the one running account that does not know its id yet."""
    app_id = _ORIGINAL.get(original_id)
    if app_id and app_id in _REGISTRY:
        return _REGISTRY[app_id], ""
    unknown = [b for b in _REGISTRY.values() if not b.original_id]
    if len(unknown) == 1:
        bot = unknown[0]
        bot._learn_original(original_id)
        return bot, ""
    if not unknown:
        return None, "no account"
    for b in unknown:
        b.last_error = localefmt.chu(
            "Có nhiều tài khoản WeChat nên Javis không biết tin này của tài khoản nào. Thêm ID gốc "
            "(gh_...) vào cuối thông tin đăng nhập của từng tài khoản, hoặc bật Chế độ an toàn kèm "
            "EncodingAESKey.",
            "Several WeChat accounts run here, so Javis cannot tell which one this message is for. Add "
            "the Original ID (gh_...) at the end of each account's credentials, or turn on Safe mode "
            "with an EncodingAESKey.")
    return None, "ambiguous"


async def handle_webhook(raw: bytes, query: dict, token: str) -> tuple:
    """One POST from WeChat -> (HTTP status, body). Hands the message to the bot of its account.

    Nothing is trusted before the signature check. A valid request always gets "success", also when
    no bot runs for the account: any other answer makes WeChat tell the follower that the account's
    service is broken, and retry three times."""
    q = {k: str(v or "") for k, v in (query or {}).items()}
    ts, nonce = q.get("timestamp", ""), q.get("nonce", "")
    if not fresh_timestamp(ts):
        return 401, "stale"
    outer = parse_xml(raw)
    if not outer:
        return 400, "bad xml"
    enc = outer.get("Encrypt", "")
    bot, msg = None, {}
    if enc:
        if not check_signature(token, q.get("msg_signature", ""), ts, nonce, enc):
            return 401, "bad signature"
        for b in list(_REGISTRY.values()):
            if not b.aes_key:
                continue
            try:
                xml_text, app_id = decrypt(b.aes_key, enc)
            except ValueError:
                continue
            if app_id != b.app_id:
                continue
            bot, msg = b, parse_xml(xml_text)
            break
        if bot and msg.get("ToUserName"):
            bot._learn_original(msg["ToUserName"])
        if not bot and not outer.get("MsgType"):
            # Safe mode and no running account opens it: say so on the cards of the accounts it could be for.
            to = outer.get("ToUserName", "")
            for b in list(_REGISTRY.values()):
                if b.original_id in ("", to):
                    b.last_error = _key_mismatch() if b.aes_key else localefmt.chu(
                        "WeChat đang gửi tin đã mã hoá (Chế độ an toàn) nhưng tài khoản này chưa có "
                        "EncodingAESKey trong Javis. Sửa kênh, dán thêm EncodingAESKey.",
                        "WeChat is sending encrypted messages (Safe mode) but this account has no "
                        "EncodingAESKey in Javis. Edit the channel and add the EncodingAESKey.")
            print(f"[wechat] encrypted message for {to} but no running account has the EncodingAESKey "
                  "that opens it", file=sys.stderr)
            return 200, "success"
    if not bot:
        # Plaintext mode, or Compatible mode (WeChat sends both forms) for an account without a key.
        if not check_signature(token, q.get("signature", ""), ts, nonce):
            return 401, "bad signature"
        msg = outer
        bot, why = _bot_for_plain(msg.get("ToUserName", ""))
        if not bot:
            print(f"[wechat] message for {msg.get('ToUserName')} dropped: {why}", file=sys.stderr)
            return 200, "success"
        if bot.aes_key:
            # Rule 4: this account was given a key, so an unencrypted message is not accepted for it.
            bot.last_error = _key_mismatch() if enc else localefmt.chu(
                "WeChat đang gửi tin chưa mã hoá, trong khi tài khoản này có EncodingAESKey. Vào cấu "
                "hình máy chủ của WeChat chọn Chế độ an toàn (Safe mode), hoặc bỏ EncodingAESKey khỏi "
                "thông tin đăng nhập.",
                "WeChat is sending unencrypted messages while this account has an EncodingAESKey. In "
                "WeChat's server configuration choose Safe mode, or remove the EncodingAESKey from "
                "the credentials.")
            return 200, "success"
    if not msg or not msg.get("FromUserName"):
        return 200, "success"
    asyncio.create_task(bot._safe_message(msg))
    return 200, "success"


def _key_mismatch() -> str:
    return localefmt.chu(
        "EncodingAESKey trong Javis không mở được tin WeChat gửi tới. Chép lại đúng EncodingAESKey ở "
        "cấu hình máy chủ của WeChat rồi sửa kênh.",
        "The EncodingAESKey in Javis does not open the messages WeChat sends. Copy the EncodingAESKey "
        "from WeChat's server configuration again and edit the channel.")


def chunks_by_bytes(text: str, size: int = MAX_BYTES) -> list:
    """Split on a line break or a space where possible, never inside a character, each piece at
    most `size` UTF-8 bytes (WeChat counts bytes, and Vietnamese or Chinese takes 2 to 3 a letter)."""
    text = str(text or "")
    out = []
    while len(text.encode("utf-8")) > size:
        n = len(text.encode("utf-8")[:size].decode("utf-8", errors="ignore"))
        cut = text.rfind("\n", 0, n)
        if cut < n // 2:
            cut = text.rfind(" ", 0, n)
        if cut < n // 2:
            cut = n
        out.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text.strip() or not out:
        out.append(text)
    return out


# ---- Transport --------------------------------------------------------------------------
class WeChatBot(HangLuot):
    def __init__(self, token, chat_id, answer_fn, command_fn=None, callback_fn=None,
                 download_dir=None, commands=None, precheck_fn=None, event_fn=None,
                 giau_trang_thai=False, stt_fn=None, account_id="", **_ignored):
        cr = split_credentials(token) if not isinstance(token, dict) else {**{k: "" for k in _FIELDS}, **token}
        self._cr = cr
        self.app_id = str(cr.get("app_id") or "")
        self.aes_key = str(cr.get("aes_key") or "")
        self.original_id = str(cr.get("original_id") or "")
        self.account_id = str(account_id or "")
        self.giau_trang_thai = bool(giau_trang_thai)
        self.chat_ids = parse_chat_ids(chat_id)
        self.commands = list(commands or [])
        self.answer_fn = answer_fn
        self.command_fn = command_fn
        self.callback_fn = None
        self.precheck_fn = precheck_fn
        self.event_fn = event_fn
        self.download_dir = download_dir
        self.stt_fn = stt_fn
        self._task = None
        self._current = {}
        self._cho = {}
        self._stop = False
        self.status = "off"
        self.last_error = ""
        self.bot_id = self.app_id
        self.bot_username = self.app_id
        self.loi_danh_tinh = ""
        self.doc_moi_tin_nhom = False
        self.last_inbound = 0.0
        self._seen = set()
        self._seen_order = deque()
        self._client = None

    # ---- HTTP -------------------------------------------------------------------------
    async def _call(self, client, method, path, *, json_body=None, params=None, files=None, retry=True):
        """One API call with an access token. A token WeChat calls invalid is fetched again once
        and the call repeated. Returns the JSON plus "ok", or {"ok": False, "code", "error"}."""
        tok, err = await TOKENS.get(client, self._cr)
        if not tok:
            return {"ok": False, "error": err}
        kw = {"params": {**(params or {}), "access_token": tok}}
        if json_body is not None:
            # Rule 6: raw UTF-8, never \uXXXX escapes.
            kw["content"] = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            kw["headers"] = {"Content-Type": "application/json; charset=utf-8"}
        if files is not None:
            kw["files"] = files
        try:
            r = await client.request(method, f"{API}{path}", **kw)
            try:
                d = r.json() or {}
            except Exception:
                d = {}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}", "net_error": True}
        try:
            code = int(d.get("errcode") or 0)
        except Exception:
            code = -1
        if code in _TOKEN_CODES and retry:
            tok2, err = await TOKENS.get(client, self._cr, rejected=tok)
            if not tok2:
                return {"ok": False, "code": code, "error": err}
            return await self._call(client, method, path, json_body=json_body, params=params, files=files,
                                    retry=False)
        if r.status_code >= 300 or code:
            return {"ok": False, "code": code or r.status_code,
                    "error": _explain_error(code or r.status_code, d.get("errmsg") or f"HTTP {r.status_code}")}
        d["ok"] = True
        return d

    async def _send_one(self, client, to, text):
        return await self._call(client, "POST", "/cgi-bin/message/custom/send", json_body={
            "touser": str(to), "msgtype": "text", "text": {"content": text}})

    async def _send(self, client, chat, text, reply_markup=None):
        if not str(text or "").strip() and self.giau_trang_thai:
            return
        text = md_to_plain(text or localefmt.chu("(không có nội dung)", "(no content)"))
        for chunk in chunks_by_bytes(text):
            d = await self._send_one(client, chat, chunk)
            if not d.get("ok"):
                self.last_error = d.get("error", "")
                print(f"[wechat send] {d.get('error')}", file=sys.stderr)
                break

    async def send_text(self, chat, text):
        text = md_to_plain(str(text or "").strip())
        if not text:
            return False, "empty message"
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            for chunk in chunks_by_bytes(text):
                d = await self._send_one(client, chat, chunk)
                if not d.get("ok"):
                    return False, d.get("error", "")
        return True, ""

    async def send_file(self, path, caption="", chat=None):
        """Images only: the customer service API has no document message. Returns (ok, error)."""
        chat = chat or (self.chat_ids[0] if self.chat_ids else "")
        if not chat:
            return False, "no recipient"
        p = Path(str(path))
        import mimetypes
        mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        if mime not in ("image/jpeg", "image/png", "image/gif"):
            return False, localefmt.chu("WeChat chỉ gửi được ảnh JPG, PNG, GIF qua kênh này, không gửi được tài liệu",
                                        "WeChat can only send JPG, PNG and GIF images on this channel, not documents")

        def _read():
            return p.read_bytes() if p.is_file() else None
        try:
            data = await asyncio.to_thread(_read)      # disk work stays off the event loop
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"
        if data is None:
            return False, f"file not found: {path}"
        if len(data) > MAX_IMAGE_MB * 1024 * 1024:
            return False, localefmt.chu(f"ảnh lớn hơn {MAX_IMAGE_MB}MB, WeChat không nhận",
                                        f"image larger than {MAX_IMAGE_MB}MB, WeChat refuses it")
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as c:
            up = await self._call(c, "POST", "/cgi-bin/media/upload", params={"type": "image"},
                                  files={"media": (p.name, data, mime)})
            if not up.get("ok"):
                return False, up.get("error", "")
            d = await self._call(c, "POST", "/cgi-bin/message/custom/send", json_body={
                "touser": str(chat), "msgtype": "image", "image": {"media_id": str(up.get("media_id") or "")}})
            if not d.get("ok"):
                return False, d.get("error", "")
        if str(caption or "").strip():
            ok, err = await self.send_text(chat, caption)
            if not ok:
                return False, err
        return True, ""

    async def _typing(self, client, chat):
        await self._call(client, "POST", "/cgi-bin/message/custom/typing",
                         json_body={"touser": str(chat), "command": "Typing"})

    async def _keep_typing(self, client, chat):
        while True:
            try:
                await self._typing(client, chat)
            except Exception:      # noqa: BLE001 - the indicator is a courtesy, never a reason to fail a turn
                pass
            await asyncio.sleep(TYPING_EVERY)

    # ---- Inbound ----------------------------------------------------------------------
    def _learn_original(self, original_id: str) -> None:
        """Remember which Original ID (gh_...) this account is, here and in the stored credentials."""
        oid = str(original_id or "").strip()
        if not oid or not self.app_id:
            return
        _ORIGINAL[oid] = self.app_id
        if self.original_id == oid:
            return
        self.original_id = oid
        self._cr["original_id"] = oid
        if not self.account_id:
            return
        try:
            import channel_accounts
            channel_accounts.update_account(self.account_id, {"token": dump_credentials(self._cr)})
        except Exception as e:
            print(f"[wechat] could not save the Original ID of {self.app_id}: {type(e).__name__}: {e}",
                  file=sys.stderr)

    def _seen_before(self, mid) -> bool:
        mid = str(mid or "")
        if not mid:
            return False
        if mid in self._seen:
            return True
        self._seen.add(mid)
        self._seen_order.append(mid)
        while len(self._seen_order) > MAX_DEDUPE:
            self._seen.discard(self._seen_order.popleft())
        return False

    async def _download_media(self, client, media_id) -> tuple:
        """Bytes and content type of a temporary media the follower sent (kept by WeChat for 3 days)."""
        tok, err = await TOKENS.get(client, self._cr)
        if not tok:
            raise RuntimeError(err)
        r = await client.get(f"{API}/cgi-bin/media/get", params={"access_token": tok, "media_id": str(media_id)},
                             timeout=httpx.Timeout(180.0), follow_redirects=True)
        r.raise_for_status()
        mime = str(r.headers.get("content-type") or "").split(";")[0].strip()
        if mime in ("application/json", "text/plain"):
            try:
                d = r.json() or {}
            except Exception:
                d = {}
            raise RuntimeError(_explain_error(d.get("errcode"), d.get("errmsg") or "media not available"))
        if len(r.content) > MAX_DOWNLOAD_MB * 1024 * 1024:
            raise RuntimeError(f"larger than {MAX_DOWNLOAD_MB}MB")
        return r.content, mime

    def _save(self, chat, data: bytes, ext: str) -> Path:
        ddir = self.download_dir(chat) if callable(self.download_dir) else self.download_dir
        d = Path(ddir) if ddir else Path("wechat-inbox")
        d.mkdir(parents=True, exist_ok=True)
        dest = d / f"wechat_{int(time.time() * 1000)}{ext}"
        i = 1
        while dest.exists():
            dest = d / f"wechat_{int(time.time() * 1000)}_{i}{ext}"
            i += 1
        dest.write_bytes(data)
        return dest

    async def _message_text(self, client, msg, chat) -> str:
        mtype = msg.get("MsgType", "")
        if mtype == "text":
            return msg.get("Content", "").strip()
        if mtype == "image":
            try:
                data, mime = await self._download_media(client, msg.get("MediaId"))
            except Exception as e:
                return f"[image: {type(e).__name__}: {e}]"
            ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp"}.get(mime, ".jpg")
            dest = await asyncio.to_thread(self._save, chat, data, ext)
            return localefmt.chu(f"[Người dùng gửi ảnh qua WeChat, đã tải về: {dest}]",
                                 f"[The user sent an image on WeChat, downloaded to: {dest}]")
        if mtype == "voice":
            heard = msg.get("Recognition", "").strip()     # present when the account has voice recognition on
            if heard:
                return stt.khoi_thoai(heard, "WeChat")
            if not self.stt_fn:
                return stt.loi_thanh_dong("thieu_key")
            try:
                data, _mime = await self._download_media(client, msg.get("MediaId"))
                fmt = re.sub(r"[^a-z0-9]", "", msg.get("Format", "").lower()) or "amr"
                kq = await self.stt_fn(data, f"wechat_{int(time.time())}.{fmt}")
            except Exception as e:
                kq = {"ok": False, "noi_voi_javis": stt.loi_thanh_dong("loi", f"{type(e).__name__}: {e}")}
            if not (kq or {}).get("ok"):
                return (kq or {}).get("noi_voi_javis") or stt.loi_thanh_dong("loi")
            return stt.khoi_thoai(kq.get("text"), "WeChat")
        if mtype in ("video", "shortvideo"):
            return localefmt.chu("[Người dùng gửi một video qua WeChat]", "[The user sent a video on WeChat]")
        if mtype == "location":
            return (f"[location: {msg.get('Location_X')}, {msg.get('Location_Y')} "
                    f"{msg.get('Label') or ''}]").replace(" ]", "]")
        if mtype == "link":
            return "\n".join(x for x in (msg.get("Title", ""), msg.get("Description", ""), msg.get("Url", "")) if x)
        return ""      # events (follow, menu click, scan) and unknown types start no turn

    async def _safe_message(self, msg):
        try:
            await self._on_message(msg)
        except Exception as e:
            print(f"[wechat message] {type(e).__name__}: {e}", file=sys.stderr)

    async def _on_message(self, msg):
        chat = str(msg.get("FromUserName") or "")
        # WeChat repeats a message up to three times when the answer was slow: same MsgId, and for
        # the types without one the same sender and second.
        mid = msg.get("MsgId") or f"{chat}:{msg.get('CreateTime')}:{msg.get('MsgType')}:{msg.get('Event', '')}"
        if self._stop or not chat or self._seen_before(mid):
            return
        if msg.get("MsgType") == "event":
            return
        self.last_inbound = time.time()
        client = self._client or httpx.AsyncClient(timeout=httpx.Timeout(60.0))
        self._client = client
        meta = {
            "platform": CHANNEL, "chat_id": chat, "chat_type": "private", "chat_title": "",
            "user_name": "", "username": "", "user_id": chat,
            "message_id": str(msg.get("MsgId") or ""), "bot_username": self.bot_username,
            "mentioned": False, "reply_to_bot": False,
        }
        if self.chat_ids and chat not in self.chat_ids:
            await self._send(client, chat, localefmt.chu(
                "Bạn không có quyền dùng bot Javis này.", "You are not allowed to use this Javis bot."))
            return
        text = await self._message_text(client, msg, chat)
        if not text:
            return
        await self._dispatch(client, chat, text, meta)

    # ---- One turn ---------------------------------------------------------------------
    async def _handle_turn(self, client, chat, text, meta=None):
        files = []
        tools = []
        t0 = time.monotonic()
        keep = asyncio.create_task(self._keep_typing(client, chat))

        async def progress(txt):
            name = ten_tool(txt)
            if name and name not in tools:
                tools.append(name)

        try:
            try:
                reply = await self.answer_fn(text, meta, progress)
            except asyncio.CancelledError:
                return
            except Exception as e:
                print(f"[wechat turn failed] {type(e).__name__}: {e}", file=sys.stderr)
                # Human mode: a technical failure sends the customer nothing (owner, 2026-10-15).
                from telegram_bot import _im_khi_hong
                reply = (_im_khi_hong() if self.giau_trang_thai else f"⚠ {type(e).__name__}: {e}")
            silent = False
            if isinstance(reply, dict):
                files = reply.get("files") or []
                silent = bool(reply.get("im_lang"))
                reply = reply.get("text") or ""
            if silent and not str(reply or "").strip() and not files:
                return
            if not self.giau_trang_thai:
                trail = dong_vet(tools, time.monotonic() - t0)
                reply = ((str(reply or "").rstrip() + "\n\n") if str(reply or "").strip() else "") + trail
            keep.cancel()
            if str(reply or "").strip() or not files:
                await self._send(client, chat, reply)
            for f in files:
                fpath, fcap = (f.get("path"), f.get("caption", "")) if isinstance(f, dict) else (f, "")
                ok, err = await self.send_file(fpath, fcap, chat=chat)
                if not ok and not self.giau_trang_thai:
                    await self._send(client, chat, f"⚠ {Path(str(fpath)).name}: {err}")
        finally:
            keep.cancel()

    # ---- Lifecycle --------------------------------------------------------------------
    async def _watch(self):
        """No connection to hold: the webhook pushes. Make sure a token can be fetched (that proves
        the AppID, the AppSecret and the IP whitelist), then stay registered and keep the token fresh
        so a problem shows on the bot card before a customer writes."""
        thieu = missing_parts(self._cr)
        if thieu:
            self.status = "error"
            self.last_error = localefmt.chu("Còn thiếu: ", "Missing: ") + ", ".join(thieu)
            return
        if self.aes_key and aes_key_bytes(self.aes_key) is None:
            self.status = "error"
            self.last_error = localefmt.chu("EncodingAESKey không hợp lệ (phải đúng 43 ký tự).",
                                            "The EncodingAESKey is not valid (it must be exactly 43 characters).")
            return
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as c:
            tok, err = await TOKENS.get(c, self._cr)
        if not tok:
            self.status = "error"
            self.last_error = err
            self.loi_danh_tinh = err
            return
        self.loi_danh_tinh = ""
        old = _REGISTRY.get(self.app_id)
        if old is not None and old is not self:
            print(f"[wechat] account {self.app_id} was served by another bot; the newest one takes over",
                  file=sys.stderr)
        _REGISTRY[self.app_id] = self
        if self.original_id:
            _ORIGINAL[self.original_id] = self.app_id
        self.status = "polling"
        self.last_error = ""
        try:
            while not self._stop:
                await asyncio.sleep(1800)
                if self._stop:
                    break
                async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as c:
                    tok, err = await TOKENS.get(c, self._cr)
                if not tok:
                    self.last_error = err
                    print(f"[wechat] access token of {self.app_id}: {err}", file=sys.stderr)
        finally:
            if _REGISTRY.get(self.app_id) is self:
                _REGISTRY.pop(self.app_id, None)

    def start(self):
        self._stop = False
        self.status = "starting"
        if not self._task or self._task.done():
            self._task = asyncio.create_task(self._watch())

    def stop(self):
        self._stop = True
        self.status = "stopped"
        if _REGISTRY.get(self.app_id) is self:
            _REGISTRY.pop(self.app_id, None)
        for t in list(self._current.values()):
            if t and not t.done():
                t.cancel()
        self._current.clear()
        self._cho.clear()
        if self._task:
            self._task.cancel()
            self._task = None
        if self._client:
            c, self._client = self._client, None
            try:
                asyncio.get_event_loop().create_task(c.aclose())
            except Exception:
                pass


async def check_credentials(raw: str) -> dict:
    """For the Add account form: fetch one access token, which proves the AppID, the AppSecret and
    that this machine's IP is on the account's whitelist. {"ok", "username" (AppID), "bot_name",
    "account_type"} or {"ok": False, "error"}."""
    cr = split_credentials(raw)
    thieu = missing_parts(cr)
    if thieu:
        return {"ok": False, "error": localefmt.chu("Còn thiếu: " + ", ".join(thieu),
                                                    "Missing: " + ", ".join(thieu))}
    if cr["aes_key"] and aes_key_bytes(cr["aes_key"]) is None:
        return {"ok": False, "error": localefmt.chu("EncodingAESKey không hợp lệ (phải đúng 43 ký tự).",
                                                    "The EncodingAESKey is not valid (it must be exactly 43 characters).")}
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as c:
        tok, err = await TOKENS.get(c, cr, fresh=True)
    if not tok:
        return {"ok": False, "error": err}
    return {"ok": True, "username": cr["app_id"], "bot_name": cr["original_id"] or cr["app_id"],
            "account_type": "safe" if cr["aes_key"] else "plaintext"}


# Error codes the owner can act on. Unknown codes keep WeChat's own message.
_ERRORS = {
    40164: ("địa chỉ IP của máy chạy Javis chưa nằm trong danh sách IP được phép (IP whitelist) của "
            "tài khoản. Vào Cài đặt và Phát triển, Cấu hình cơ bản, thêm IP nêu trong lỗi",
            "the IP address of the machine running Javis is not on the account's IP whitelist. In "
            "Settings and Development, Basic Configuration, add the IP named in the error"),
    40001: ("AppSecret sai, hoặc access token không còn hợp lệ", "the AppSecret is wrong, or the access token is no longer valid"),
    40125: ("AppSecret sai", "the AppSecret is wrong"),
    40013: ("AppID sai", "the AppID is wrong"),
    40243: ("AppSecret đang bị đóng băng. Mở lại ở Cấu hình cơ bản của tài khoản",
            "the AppSecret is frozen. Unfreeze it in the account's Basic Configuration"),
    48001: ("tài khoản chưa được cấp quyền gửi tin chăm sóc khách hàng qua API. WeChat chỉ cấp cho "
            "tài khoản đã xác minh (và tài khoản thử nghiệm)",
            "the account may not send customer service messages through the API. WeChat grants that to "
            "verified accounts only (and to the sandbox test account)"),
    45015: ("khách đã quá 48 giờ không nhắn nên WeChat không cho trả lời nữa. Khách nhắn lại là mở "
            "lại khung trả lời",
            "the follower has not written for more than 48 hours, so WeChat no longer allows a reply. "
            "The window reopens when they write again"),
    45047: ("đã gửi hết số tin WeChat cho phép sau một tin của khách. Chờ khách nhắn tiếp",
            "the number of replies WeChat allows after one message of the follower is used up. Wait "
            "for their next message"),
    43004: ("người này chưa theo dõi tài khoản (hoặc đã bỏ theo dõi)", "this person does not follow the account (or unfollowed it)"),
    40003: ("OpenID sai, thường là người nhận không thuộc tài khoản này",
            "invalid OpenID, usually a recipient that does not belong to this account"),
    45002: ("tin dài quá giới hạn của WeChat", "the message is longer than WeChat allows"),
    45009: ("đã hết hạn mức gọi API trong ngày của WeChat", "the account's daily API quota is used up"),
    45011: ("gọi API quá dày, thử lại sau", "API calls are too frequent, try again later"),
    50002: ("tài khoản đang bị WeChat hạn chế", "the account is restricted by WeChat"),
    -1: ("máy chủ WeChat đang bận, thử lại sau", "WeChat's servers are busy, try again later"),
}


def _explain_error(code, fallback="") -> str:
    try:
        ci = int(code)
    except Exception:
        ci = None
    vi_en = _ERRORS.get(ci) if ci is not None else None
    if vi_en:
        # WeChat's own text is kept for 40164: it names the IP to put on the whitelist.
        tail = f": {fallback}" if ci == 40164 and fallback else ""
        return localefmt.chu(f"{vi_en[0]} ({ci}){tail}", f"{vi_en[1]} ({ci}){tail}")
    return f"{fallback or 'error'}" + (f" ({code})" if code else "")
