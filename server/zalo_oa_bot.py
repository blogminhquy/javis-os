"""Zalo Official Account (OA) gateway over the official OA Open API v3 (0.412.0).

Same shape as `messenger_bot`: Javis cannot pull messages, Zalo POSTs every event a customer
sends to the OA to one webhook. Two halves:

  - `ZaloOABot`: the transport, same contract as `TelegramBot` (start/stop/status/send_text/
    send_file). `start()` opens no connection; it makes sure an access token works, reads which
    OA it is and registers the bot under that OA id.
  - `handle_webhook(payload)`: called by the `/zalo-oa/webhook` route in main.py once the
    signature has been checked. It routes each event to the bot registered for the OA it was
    sent to. One URL serves every OA.

Credentials of one OA (developers.zalo.me, the app the OA is linked to):
  - App ID (digits) and App secret key (Settings of the app), used to refresh the access token
  - OA secret key (Official Account -> Webhook settings), used ONLY to verify the webhook signature
  - Refresh token, from the OAuth v4 grant (API Explorer -> OA access token, or the app's own flow)

What makes Zalo OA different from Messenger, and shapes the code:
  1. Tokens ROTATE. An access token lives about 25 hours (`expires_in` 90000) and a refresh token
     about 3 months, and a refresh token works ONCE: each refresh returns a new pair and the old
     refresh token is dead. So the newest pair must be written back to the channel-account store
     the moment Zalo returns it, and two refreshes of one account must never run at the same time
     (`TokenKeeper`, one lock per account). Lose the newest refresh token and the owner has to
     grant the app again.
  2. Webhook signature: header `X-ZEvent-Signature: mac=<hex>` where
     hex = sha256(app_id + raw body + timestamp + OA secret key), `timestamp` being the field of
     the same JSON body. Community implementations also report an HMAC-SHA256 of the raw body
     keyed by the OA secret key; both need the secret, so both are accepted.
  3. Replies go out as "tin tư vấn" (consultation messages, `/v3.0/oa/message/cs`), which Zalo only
     allows within a window after the customer's last interaction. Outside it the send fails and
     `_explain_error` says so in words; the inbox still keeps the conversation.
  4. Zalo renders no markdown and caps a text at 2000 characters: plain text, split when longer.
  5. Private chats with the OA only (OA group chats are a separate product, not handled here).
  6. Zalo wants the webhook domain verified first (`zalo_verifier<code>.html`); main.py serves that
     file for the codes the owner saved (`site_verification_codes`).
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

import httpx

import localefmt
import stt
from bot_gateway import HangLuot, dong_vet, parse_chat_ids, ten_tool
from messenger_bot import _chunks, md_to_plain

OAUTH_URL = os.getenv("JAVIS_ZALO_OA_OAUTH", "https://oauth.zaloapp.com/v4/oa/access_token")
OPENAPI = os.getenv("JAVIS_ZALO_OA_OPENAPI", "https://openapi.zalo.me")

CHANNEL = "zalo_oa"
MAX_MSG = 1900               # Zalo allows 2000 per text; keep a margin
MAX_DEDUPE = 4000
MAX_DOWNLOAD_MB = 20
MAX_IMAGE_MB = 1             # upload/image refuses larger files
MAX_FILE_MB = 5              # upload/file: pdf, doc, docx only
REFRESH_MARGIN = 30 * 60     # refresh this long before the access token runs out
PENDING_TTL = 30 * 60

# oa_id -> ZaloOABot currently running for it.
_REGISTRY: dict = {}


# ---- Credentials ------------------------------------------------------------------------
_FIELDS = ("app_id", "app_secret", "oa_secret", "refresh_token", "access_token", "expires_at", "oa_id")


def split_credentials(raw) -> dict:
    """The stored secret of one OA -> dict with every key of `_FIELDS` (strings, `expires_at` float).

    Two forms. What the owner pastes: "<App ID> <App secret key> <OA secret key> <Refresh token>",
    told apart by shape: the App ID is all digits, the refresh token is the long one, and the two
    short keys are taken IN ORDER (app secret first). `key=value` parts are read by name, so
    "oa_secret=..." fixes the order when needed. What Javis writes back after a refresh: JSON.
    """
    out = {k: "" for k in _FIELDS}
    out["expires_at"] = 0.0
    s = str(raw or "").strip()
    if s.startswith("{"):
        try:
            d = json.loads(s)
        except Exception:
            d = {}
        for k in _FIELDS:
            if k in d and d[k] is not None:
                out[k] = d[k] if k == "expires_at" else str(d[k]).strip()
        try:
            out["expires_at"] = float(out["expires_at"] or 0)
        except Exception:
            out["expires_at"] = 0.0
        return out
    short = []
    for part in re.split(r"[\s,;|]+", s):
        if not part:
            continue
        if "=" in part[:20]:
            k, _, v = part.partition("=")
            k = k.strip().lower().replace("-", "_")
            k = {"secret_key": "app_secret", "app_secret_key": "app_secret", "oa_secret_key": "oa_secret",
                 "refresh": "refresh_token"}.get(k, k)
            if k in ("app_id", "app_secret", "oa_secret", "refresh_token"):
                out[k] = v.strip()
            continue
        if re.fullmatch(r"\d{6,25}", part) and not out["app_id"]:
            out["app_id"] = part
        elif len(part) >= 60:
            out["refresh_token"] = part
        elif re.fullmatch(r"[A-Za-z0-9_\-]{8,59}", part):
            short.append(part)
    for k in ("app_secret", "oa_secret"):
        if not out[k] and short:
            out[k] = short.pop(0)
    return out


def dump_credentials(cr: dict) -> str:
    return json.dumps({k: cr.get(k, "") for k in _FIELDS}, ensure_ascii=False)


def missing_parts(cr: dict) -> list:
    return [n for n, k in (("App ID", "app_id"), ("App secret key", "app_secret"),
                           ("OA secret key", "oa_secret"), ("Refresh token", "refresh_token"))
            if not cr.get(k)]


def _fingerprint(refresh_token: str) -> str:
    return hashlib.sha256(str(refresh_token or "").encode()).hexdigest()


# Pasted refresh token (fingerprint) -> (rotated credentials, time). Checking a pasted token has to
# refresh it to learn which OA it is, and that kills the pasted refresh token. The account is saved
# a moment later WITH the pasted string, so the newer pair waits here and `TokenKeeper.load` swaps it
# in (and writes it to the store) the first time that account is read. In memory only: a restart in
# that window means pasting a fresh refresh token, which the error message says.
_PENDING: dict = {}


def _remember_pending(old_refresh: str, cr: dict) -> None:
    now = time.time()
    for k in [k for k, (_, t) in _PENDING.items() if now - t > PENDING_TTL]:
        _PENDING.pop(k, None)
    _PENDING[_fingerprint(old_refresh)] = (dict(cr), now)


def _take_pending(refresh_token: str):
    hit = _PENDING.get(_fingerprint(refresh_token))
    if not hit:
        return None
    cr, t = hit
    if time.time() - t > PENDING_TTL:
        _PENDING.pop(_fingerprint(refresh_token), None)
        return None
    return dict(cr)


async def refresh_tokens(client, cr: dict) -> dict:
    """One OAuth v4 refresh. {"ok", "access_token", "refresh_token", "expires_at"} or {"ok": False, "error"}.

    The refresh token sent here is spent even when the answer is lost on the way back, so callers
    never retry this blindly."""
    try:
        r = await client.post(OAUTH_URL, headers={"secret_key": str(cr.get("app_secret") or "")},
                              data={"refresh_token": str(cr.get("refresh_token") or ""),
                                    "app_id": str(cr.get("app_id") or ""), "grant_type": "refresh_token"})
        try:
            d = r.json() or {}
        except Exception:
            d = {}
    except Exception as e:
        return {"ok": False, "net_error": True,
                "error": localefmt.chu(f"Không nối được Zalo: {e}", f"Could not reach Zalo: {e}")}
    if not d.get("access_token") or not d.get("refresh_token"):
        code = d.get("error") or d.get("error_name") or r.status_code
        why = str(d.get("error_description") or d.get("message") or d.get("error_reason") or "")
        return {"ok": False, "code": code, "error": localefmt.chu(
            "Zalo không làm mới được token (" + why + "). Refresh token sai, đã dùng một lần rồi hoặc "
            "đã hết hạn (khoảng 3 tháng), hoặc App ID và App secret key không khớp. Tạo refresh token "
            "mới cho OA rồi dán lại.",
            "Zalo could not refresh the token (" + why + "). The refresh token is wrong, was already "
            "used once or has expired (about 3 months), or the App ID and App secret key do not match. "
            "Create a new refresh token for the OA and paste it again.")}
    try:
        life = float(d.get("expires_in") or 90000)
    except Exception:
        life = 90000.0
    return {"ok": True, "access_token": str(d["access_token"]), "refresh_token": str(d["refresh_token"]),
            "expires_at": time.time() + life}


class TokenKeeper:
    """The only place that refreshes an OA token. One lock per account, and every new pair is
    saved to the channel-account store before anyone uses it (see rule 1 at the top)."""

    def __init__(self):
        self._locks: dict = {}

    def _lock(self, key: str) -> asyncio.Lock:
        lk = self._locks.get(key)
        if lk is None:
            lk = self._locks[key] = asyncio.Lock()
        return lk

    @staticmethod
    def _save(account_id: str, cr: dict) -> bool:
        if not account_id:
            return False
        try:
            import channel_accounts
            ok, loi = channel_accounts.update_account(account_id, {"token": dump_credentials(cr)})
            if not ok:
                print(f"[zalo_oa] could not save the new token of {account_id}: {loi}", file=sys.stderr)
            return bool(ok)
        except Exception as e:
            print(f"[zalo_oa] could not save the new token of {account_id}: {type(e).__name__}: {e}",
                  file=sys.stderr)
            return False

    def load(self, account_id: str, fallback=None) -> dict:
        """Newest credentials of an account: the store first, then a pending pair from a check."""
        raw = ""
        if account_id:
            try:
                import channel_accounts
                raw = channel_accounts.get_token(account_id)
            except Exception:
                raw = ""
        cr = split_credentials(raw or fallback or "")
        newer = _take_pending(cr.get("refresh_token", "")) if cr.get("refresh_token") else None
        if newer:
            for k in ("app_id", "app_secret", "oa_secret"):
                newer[k] = cr.get(k) or newer.get(k, "")
            if self._save(account_id, newer):
                _PENDING.pop(_fingerprint(cr["refresh_token"]), None)
            cr = newer
        return cr

    async def access_token(self, account_id: str, fallback=None, client=None, force: bool = False):
        """(token, credentials, error). Refreshes when the token is missing or close to expiry.

        Without an account id the rotated pair could not be saved, so no refresh happens: a still
        valid access token is used, otherwise the call fails and says why."""
        key = account_id or "_"
        async with self._lock(key):
            cr = self.load(account_id, fallback)
            fresh = cr.get("access_token") and float(cr.get("expires_at") or 0) - time.time() > REFRESH_MARGIN
            if fresh and not force:
                return cr["access_token"], cr, ""
            thieu = missing_parts(cr)
            if thieu:
                return "", cr, localefmt.chu("Còn thiếu: " + ", ".join(thieu), "Missing: " + ", ".join(thieu))
            if not account_id:
                if cr.get("access_token") and float(cr.get("expires_at") or 0) > time.time():
                    return cr["access_token"], cr, ""
                return "", cr, localefmt.chu("tài khoản Zalo OA này chưa được lưu nên chưa làm mới token được",
                                             "this Zalo OA account is not saved yet, so its token cannot be refreshed")
            own = client is None
            c = client or httpx.AsyncClient(timeout=httpx.Timeout(20.0))
            try:
                res = await refresh_tokens(c, cr)
            finally:
                if own:
                    await c.aclose()
            if not res.get("ok"):
                return "", cr, res.get("error", "")
            cr = {**cr, "access_token": res["access_token"], "refresh_token": res["refresh_token"],
                  "expires_at": res["expires_at"]}
            self._save(account_id, cr)
            return cr["access_token"], cr, ""


KEEPER = TokenKeeper()


# ---- Webhook ----------------------------------------------------------------------------
def verify_signature(raw_body: bytes, header: str, app_secrets) -> bool:
    """True when `X-ZEvent-Signature` matches the body under the OA secret key of an account whose
    App ID is the one in the body. `app_secrets` = [(app_id, oa_secret), ...].

    The webhook URL is public, so this is the only thing standing between the internet and a fake
    customer message. Constant-time compare; an empty secret never matches."""
    got = str(header or "").strip()
    if got.lower().startswith("mac="):
        got = got[4:].strip()
    got = got.lower()
    if not got or not raw_body:
        return False
    try:
        d = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return False
    if not isinstance(d, dict):
        return False
    app_id = str(d.get("app_id") or "")
    ts = str(d.get("timestamp") or "")
    body = raw_body.decode("utf-8")
    for aid, secret in app_secrets or []:
        secret = str(secret or "")
        if not secret or (aid and app_id and str(aid) != app_id):
            continue
        want = hashlib.sha256((app_id + body + ts + secret).encode("utf-8")).hexdigest()
        if hmac.compare_digest(want, got):
            return True
        want2 = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(want2, got):
            return True
    return False


def registered() -> dict:
    return dict(_REGISTRY)


def _oa_of(ev: dict) -> str:
    return str((ev.get("recipient") or {}).get("id") or ev.get("oa_id") or "")


async def handle_webhook(payload: dict) -> int:
    """Route a verified webhook event to the bot of its OA. Returns how many events were handed
    over. The OA's own outgoing messages (`oa_send_*`) and non-message events are skipped."""
    ev = payload or {}
    name = str(ev.get("event_name") or "")
    if not name.startswith("user_send_") and name != "user_submit_info":
        return 0
    oa = _oa_of(ev)
    bot = _REGISTRY.get(oa)
    if not bot:
        print(f"[zalo_oa] event for OA {oa} but no bot runs for it", file=sys.stderr)
        return 0
    asyncio.create_task(bot._safe_event(ev))
    return 1


# ---- Transport --------------------------------------------------------------------------
class ZaloOABot(HangLuot):
    def __init__(self, token, chat_id, answer_fn, command_fn=None, callback_fn=None,
                 download_dir=None, commands=None, precheck_fn=None, event_fn=None,
                 giau_trang_thai=False, stt_fn=None, account_id="", **_ignored):
        self._raw = token if isinstance(token, str) else dump_credentials(token or {})
        cr = split_credentials(self._raw)
        self.oa_id = str(cr.get("oa_id") or "")
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
        self.bot_id = self.oa_id
        self.bot_username = ""
        self.loi_danh_tinh = ""
        self.doc_moi_tin_nhom = False
        self.last_inbound = 0.0
        self._seen = set()
        self._seen_order = deque()
        self._names: dict = {}
        self._client = None

    # ---- HTTP -------------------------------------------------------------------------
    async def _token(self, client=None, force=False):
        tok, cr, err = await KEEPER.access_token(self.account_id, self._raw, client=client, force=force)
        if cr.get("oa_id"):
            self.oa_id = cr["oa_id"]
        return tok, err

    async def _call(self, client, method, path, *, json_body=None, params=None, files=None, retry=True):
        """One OpenAPI call with a fresh access token. A token Zalo calls invalid (-216, -124) is
        refreshed once and the call repeated."""
        tok, err = await self._token(client)
        if not tok:
            return {"ok": False, "error": err}
        try:
            r = await client.request(method, f"{OPENAPI}{path}", headers={"access_token": tok},
                                     json=json_body, params=params, files=files)
            try:
                d = r.json() or {}
            except Exception:
                d = {}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}", "net_error": True}
        code = d.get("error")
        try:
            code = int(code or 0)
        except Exception:
            code = -1
        if code in (-216, -124) and retry:
            tok, err = await self._token(client, force=True)
            if not tok:
                return {"ok": False, "code": code, "error": err}
            return await self._call(client, method, path, json_body=json_body, params=params, files=files,
                                    retry=False)
        if r.status_code >= 300 or code:
            return {"ok": False, "code": code or r.status_code,
                    "error": _explain_error(code or r.status_code, d.get("message") or f"HTTP {r.status_code}")}
        d["ok"] = True
        return d

    async def _send_one(self, client, to, text):
        return await self._call(client, "POST", "/v3.0/oa/message/cs", json_body={
            "recipient": {"user_id": str(to)}, "message": {"text": text}})

    async def _send(self, client, chat, text, reply_markup=None):
        if not str(text or "").strip() and self.giau_trang_thai:
            return
        text = md_to_plain(text or localefmt.chu("(không có nội dung)", "(no content)"))
        for chunk in _chunks(text, MAX_MSG):
            d = await self._send_one(client, chat, chunk)
            if not d.get("ok"):
                self.last_error = d.get("error", "")
                print(f"[zalo_oa send] {d.get('error')}", file=sys.stderr)
                break

    async def send_text(self, chat, text):
        text = md_to_plain(str(text or "").strip())
        if not text:
            return False, "empty message"
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            for chunk in _chunks(text, MAX_MSG):
                d = await self._send_one(client, chat, chunk)
                if not d.get("ok"):
                    return False, d.get("error", "")
        return True, ""

    async def send_file(self, path, caption="", chat=None):
        """Images go as a media template, PDF/Word as a file attachment. Returns (ok, error)."""
        chat = chat or (self.chat_ids[0] if self.chat_ids else "")
        if not chat:
            return False, "no recipient"
        p = Path(str(path))
        try:
            if not p.is_file():
                return False, f"file not found: {path}"
            data = p.read_bytes()
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"
        import mimetypes
        mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        is_image = mime in ("image/jpeg", "image/png", "image/gif")
        is_doc = p.suffix.lower() in (".pdf", ".doc", ".docx")
        if not (is_image or is_doc):
            return False, localefmt.chu("Zalo OA chỉ gửi được ảnh JPG/PNG/GIF và file PDF, DOC, DOCX",
                                        "Zalo OA can only send JPG/PNG/GIF images and PDF, DOC, DOCX files")
        cap_mb = MAX_IMAGE_MB if is_image else MAX_FILE_MB
        if len(data) > cap_mb * 1024 * 1024:
            return False, localefmt.chu(f"file lớn hơn {cap_mb}MB, Zalo OA không nhận",
                                        f"file larger than {cap_mb}MB, Zalo OA refuses it")
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as c:
            up = await self._call(c, "POST", "/v2.0/oa/upload/image" if is_image else "/v2.0/oa/upload/file",
                                  files={"file": (p.name, data, mime)})
            if not up.get("ok"):
                return False, up.get("error", "")
            dd = up.get("data") or {}
            if is_image:
                att = {"type": "template", "payload": {"template_type": "media", "elements": [
                    {"media_type": "image", "attachment_id": str(dd.get("attachment_id") or "")}]}}
            else:
                att = {"type": "file", "payload": {"token": str(dd.get("token") or "")}}
            msg = {"attachment": att}
            if is_image and str(caption or "").strip():
                msg["text"] = md_to_plain(str(caption))[:MAX_MSG]
                caption = ""
            d = await self._call(c, "POST", "/v3.0/oa/message/cs",
                                 json_body={"recipient": {"user_id": str(chat)}, "message": msg})
            if not d.get("ok"):
                return False, d.get("error", "")
        if str(caption or "").strip():
            ok, err = await self.send_text(chat, caption)
            if not ok:
                return False, err
        return True, ""

    async def _name_of(self, client, uid) -> str:
        """Display name of a customer (user/detail). Empty when the OA may not read it."""
        if uid in self._names:
            return self._names[uid]
        d = await self._call(client, "GET", "/v3.0/oa/user/detail",
                             params={"data": json.dumps({"user_id": str(uid)})})
        name = str(((d.get("data") or {}).get("display_name")) or "").strip() if d.get("ok") else ""
        if len(self._names) > 2000:
            self._names.clear()
        self._names[uid] = name
        return name

    # ---- Inbound ----------------------------------------------------------------------
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

    async def _download(self, client, url) -> tuple:
        r = await client.get(url, timeout=httpx.Timeout(180.0), follow_redirects=True)
        r.raise_for_status()
        if len(r.content) > MAX_DOWNLOAD_MB * 1024 * 1024:
            raise RuntimeError(f"larger than {MAX_DOWNLOAD_MB}MB")
        return r.content, str(r.headers.get("content-type") or "").split(";")[0].strip()

    async def _attachment_text(self, client, att, chat) -> str:
        atype = str(att.get("type") or "")
        pl = att.get("payload") or {}
        url = str(pl.get("url") or "")
        if atype == "location":
            co = pl.get("coordinates") or {}
            return f"[location: {co.get('latitude')}, {co.get('longitude')}]"
        if atype == "sticker":
            return localefmt.chu("[Người dùng gửi một nhãn dán]", "[The user sent a sticker]")
        if atype == "link":
            return str(pl.get("url") or pl.get("description") or "").strip()
        if not url:
            return ""
        if atype in ("video", "gif"):
            return localefmt.chu(f"[Người dùng gửi một video qua Zalo OA: {url}]",
                                 f"[The user sent a video on Zalo OA: {url}]")
        try:
            data, mime = await self._download(client, url)
        except Exception as e:
            return f"[{atype}: {type(e).__name__}: {e}]"
        if atype in ("audio", "voice"):
            if not self.stt_fn:
                return stt.loi_thanh_dong("thieu_key")
            try:
                kq = await self.stt_fn(data, f"zalo_oa_{int(time.time())}.m4a")
            except Exception as e:
                kq = {"ok": False, "noi_voi_javis": stt.loi_thanh_dong("loi", f"{type(e).__name__}: {e}")}
            if not (kq or {}).get("ok"):
                return (kq or {}).get("noi_voi_javis") or stt.loi_thanh_dong("loi")
            return stt.khoi_thoai(kq.get("text"), "Zalo OA")
        ddir = self.download_dir(chat) if callable(self.download_dir) else self.download_dir
        d = Path(ddir) if ddir else Path("zalo-oa-inbox")
        d.mkdir(parents=True, exist_ok=True)
        ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp",
               "application/pdf": ".pdf"}.get(mime, "")
        if not ext:
            m = re.search(r"\.([A-Za-z0-9]{2,5})(?:\?|$)", str(pl.get("name") or url))
            ext = "." + m.group(1).lower() if m else ""
        dest = d / f"zalo_oa_{int(time.time() * 1000)}{ext}"
        dest.write_bytes(data)
        if atype == "image":
            return localefmt.chu(f"[Người dùng gửi ảnh qua Zalo OA, đã tải về: {dest}]",
                                 f"[The user sent an image on Zalo OA, downloaded to: {dest}]")
        return localefmt.chu(f"[Người dùng gửi file qua Zalo OA, đã tải về: {dest}]",
                             f"[The user sent a file on Zalo OA, downloaded to: {dest}]")

    async def _event_text(self, client, ev, chat) -> str:
        msg = ev.get("message") or {}
        if ev.get("event_name") == "user_submit_info":
            info = ev.get("info") or {}
            return "; ".join(f"{k}: {v}" for k, v in info.items() if v)
        parts = []
        for att in msg.get("attachments") or []:
            t = await self._attachment_text(client, att, chat)
            if t:
                parts.append(t)
        text = str(msg.get("text") or "").strip()
        if text:
            parts.append(text)
        return "\n".join(parts).strip()

    async def _safe_event(self, ev):
        try:
            await self._on_event(ev)
        except Exception as e:
            print(f"[zalo_oa event] {type(e).__name__}: {e}", file=sys.stderr)

    async def _on_event(self, ev):
        msg = ev.get("message") or {}
        mid = msg.get("msg_id") or ""
        if not mid:
            mid = f"{(ev.get('sender') or {}).get('id')}:{ev.get('timestamp')}:{ev.get('event_name')}"
        if self._stop or self._seen_before(mid):
            return
        chat = str((ev.get("sender") or {}).get("id") or ev.get("user_id") or "")
        if not chat or chat == self.oa_id:
            return
        self.last_inbound = time.time()
        client = self._client or httpx.AsyncClient(timeout=httpx.Timeout(60.0))
        self._client = client
        name = await self._name_of(client, chat)
        meta = {
            "platform": CHANNEL, "chat_id": chat, "chat_type": "private", "chat_title": "",
            "user_name": name, "username": name, "user_id": chat,
            "message_id": str(msg.get("msg_id") or ""), "bot_username": self.bot_username,
            "mentioned": False, "reply_to_bot": False,
        }
        if self.chat_ids and chat not in self.chat_ids:
            await self._send(client, chat, localefmt.chu(
                "Bạn không có quyền dùng bot Javis này.", "You are not allowed to use this Javis bot."))
            return
        text = await self._event_text(client, ev, chat)
        if not text:
            return
        await self._dispatch(client, chat, text, meta)

    # ---- One turn ---------------------------------------------------------------------
    async def _handle_turn(self, client, chat, text, meta=None):
        files = []
        tools = []
        t0 = time.monotonic()

        async def progress(txt):
            name = ten_tool(txt)
            if name and name not in tools:
                tools.append(name)

        try:
            reply = await self.answer_fn(text, meta, progress)
        except asyncio.CancelledError:
            return
        except Exception as e:
            print(f"[zalo_oa turn failed] {type(e).__name__}: {e}", file=sys.stderr)
            from telegram_bot import CAU_LOI_NGUOI_THAT
            reply = (CAU_LOI_NGUOI_THAT if self.giau_trang_thai else f"⚠ {type(e).__name__}: {e}")
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
        if str(reply or "").strip() or not files:
            await self._send(client, chat, reply)
        for f in files:
            fpath, fcap = (f.get("path"), f.get("caption", "")) if isinstance(f, dict) else (f, "")
            ok, err = await self.send_file(fpath, fcap, chat=chat)
            if not ok and not self.giau_trang_thai:
                await self._send(client, chat, f"⚠ {Path(str(fpath)).name}: {err}")

    # ---- Lifecycle --------------------------------------------------------------------
    async def _watch(self):
        """No connection to hold: the webhook pushes. Make sure a token works and learn the OA id,
        then stay registered, refreshing the token before it runs out."""
        cr = KEEPER.load(self.account_id, self._raw)
        if missing_parts(cr):
            # Without the OA secret key every webhook POST fails the signature check (401) and the bot
            # would look healthy while hearing nothing: refuse to start instead.
            self.status = "error"
            self.last_error = localefmt.chu("Còn thiếu: ", "Missing: ") + ", ".join(missing_parts(cr))
            return
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as c:
            info = await whoami(c, self)
        if not info.get("ok"):
            self.status = "error"
            self.last_error = info.get("error", "")
            self.loi_danh_tinh = self.last_error
            return
        self.oa_id = info.get("username", "") or self.oa_id
        self.bot_id = self.oa_id
        self.bot_username = info.get("bot_name", "")
        self.loi_danh_tinh = ""
        old = _REGISTRY.get(self.oa_id)
        if old is not None and old is not self:
            print(f"[zalo_oa] OA {self.oa_id} was served by another bot; the newest one takes over",
                  file=sys.stderr)
        _REGISTRY[self.oa_id] = self
        self.status = "polling"
        self.last_error = ""
        try:
            while not self._stop:
                cr = KEEPER.load(self.account_id, self._raw)
                left = float(cr.get("expires_at") or 0) - time.time() - REFRESH_MARGIN
                await asyncio.sleep(max(60.0, min(left, 3600.0)))
                if self._stop:
                    break
                tok, err = await self._token()
                if not tok:
                    # Keep listening: an access token that still works carries replies until it
                    # expires, and the owner sees why on the bot card.
                    self.last_error = err
                    print(f"[zalo_oa] token refresh for OA {self.oa_id}: {err}", file=sys.stderr)
                    await asyncio.sleep(600)
                else:
                    self.last_error = ""
        finally:
            if _REGISTRY.get(self.oa_id) is self:
                _REGISTRY.pop(self.oa_id, None)

    def start(self):
        self._stop = False
        self.status = "starting"
        if not self._task or self._task.done():
            self._task = asyncio.create_task(self._watch())

    def stop(self):
        self._stop = True
        self.status = "stopped"
        if _REGISTRY.get(self.oa_id) is self:
            _REGISTRY.pop(self.oa_id, None)
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


async def whoami(client, bot: ZaloOABot) -> dict:
    """Ask Zalo which OA this token belongs to. {"ok", "username" (OA id), "bot_name"} or {"ok": False, "error"}."""
    d = await bot._call(client, "GET", "/v2.0/oa/getoa")
    if not d.get("ok"):
        return {"ok": False, "error": d.get("error", "")}
    info = d.get("data") or {}
    oa_id = str(info.get("oa_id") or "")
    if not oa_id:
        return {"ok": False, "error": localefmt.chu("Zalo không trả về OA nào cho token này",
                                                    "Zalo returned no OA for this token")}
    return {"ok": True, "username": oa_id, "bot_name": str(info.get("name") or ""),
            "account_type": str(info.get("package_name") or info.get("oa_type") or "")}


async def check_credentials(raw: str) -> dict:
    """For the Add account form: refresh once (that is the only way to learn whether the keys work
    and which OA it is), keep the rotated pair for the account about to be saved, read the OA."""
    cr = split_credentials(raw)
    thieu = missing_parts(cr)
    if thieu:
        return {"ok": False, "error": localefmt.chu("Còn thiếu: " + ", ".join(thieu),
                                                    "Missing: " + ", ".join(thieu))}
    pasted = cr["refresh_token"]
    newer = _take_pending(pasted)
    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as c:
        if newer is None:
            res = await refresh_tokens(c, cr)
            if not res.get("ok"):
                return {"ok": False, "error": res.get("error", "")}
            newer = {**cr, "access_token": res["access_token"], "refresh_token": res["refresh_token"],
                     "expires_at": res["expires_at"]}
        probe = ZaloOABot(dump_credentials(newer), "", None, giau_trang_thai=True)
        info = await whoami(c, probe)
    if info.get("ok"):
        newer["oa_id"] = info["username"]
    _remember_pending(pasted, newer)
    return info


# Error codes the owner can act on (OA Open API v3). Unknown codes keep Zalo's own message.
_WINDOW = ("khách đã lâu không nhắn cho OA nên Zalo không cho gửi tin tư vấn nữa. Khách nhắn lại là "
           "mở lại khung trả lời",
           "the customer has not written to the OA for too long, so Zalo no longer allows a consultation "
           "message. The window reopens when they write again")
_ERRORS = {
    -216: ("access token Zalo OA không hợp lệ. Javis đã thử làm mới; nếu vẫn lỗi, tạo refresh token mới rồi dán lại",
           "the Zalo OA access token is invalid. Javis tried to refresh it; if it still fails, create a new "
           "refresh token and paste it again"),
    -124: ("access token Zalo OA đã hết hạn", "the Zalo OA access token has expired"),
    -213: ("người này chưa quan tâm OA hoặc đã bỏ quan tâm", "this person does not follow the OA (or unfollowed it)"),
    -230: _WINDOW,
    -224: ("gói dịch vụ của OA chưa cho dùng tính năng này qua API. Kiểm tra gói OA ở oa.zalo.me",
           "the OA's service package does not allow this through the API. Check the OA package on oa.zalo.me"),
    -14029: ("app trên developers.zalo.me chưa được duyệt hoặc chưa được cấp quyền cho OA này",
             "the app on developers.zalo.me is not approved or not granted access to this OA"),
    -201: ("tham số sai, thường là user id không thuộc OA này", "invalid parameter, usually a user id that does not belong to this OA"),
    -32: ("vượt hạn mức gọi API của Zalo, thử lại sau", "Zalo API rate limit reached, try again later"),
}


def _explain_error(code, fallback="") -> str:
    try:
        ci = int(code)
    except Exception:
        ci = None
    vi_en = _ERRORS.get(ci) if ci is not None else None
    if vi_en:
        return localefmt.chu(f"{vi_en[0]} ({ci})", f"{vi_en[1]} ({ci})")
    return f"{fallback or 'error'}" + (f" ({code})" if code else "")


# ---- Domain verification ----------------------------------------------------------------
def parse_site_code(raw: str) -> str:
    """The code Zalo gives for domain verification, from whatever the owner pasted: the file name
    `zalo_verifier<code>.html`, the meta tag, or the bare code."""
    s = str(raw or "").strip()
    m = re.search(r"zalo_verifier([A-Za-z0-9_\-]{6,80})\.html", s)
    if m:
        return m.group(1)
    m = re.search(r"zalo-platform-site-verification[^>]*content\s*=\s*[\"']([A-Za-z0-9_\-]{6,80})[\"']", s)
    if m:
        return m.group(1)
    return s if re.fullmatch(r"[A-Za-z0-9_\-]{6,80}", s) else ""


def verifier_html(code: str) -> str:
    return ("<!DOCTYPE html>\n<html><head>\n"
            f"<meta name=\"zalo-platform-site-verification\" content=\"{code}\" />\n"
            "</head><body>There Is No Limit To What You Can Accomplish Using Zalo!</body></html>\n")
