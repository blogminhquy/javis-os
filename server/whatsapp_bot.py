"""WhatsApp gateway over the official WhatsApp Business Cloud API (Meta), 0.71.0.

Unlike Telegram, Zalo and Slack, WhatsApp has no way for Javis to pull messages: Meta POSTs
every inbound message to a webhook. So this module has two halves:

  - `WhatsAppBot`: the transport, same contract as `TelegramBot` (start/stop/status/send_text/
    send_file). Its `start()` does not open any connection; it registers the bot under its
    phone number id so the webhook can hand it messages.
  - `handle_webhook(payload)`: called by the `/whatsapp/webhook` route in main.py once the
    signature has been checked. It routes each message to the bot registered for the phone
    number it was sent to. One URL serves the owner's control number and every customer bot.

Credentials for one number (from developers.facebook.com, app -> WhatsApp -> API Setup):
  - phone number id (digits, NOT the phone number itself)
  - access token (a permanent System User token; the temporary one dies after 24 hours)
  - app secret (App settings -> Basic), used only to verify `X-Hub-Signature-256`

Rules of the platform that shape the code, not just the docs:
  1. The 24-hour window. A business may send free-form text only within 24 hours of the
     user's last message; outside it only pre-approved templates go through (error 131047).
     Background results routed here can therefore fail when the owner has been quiet for a
     day. `_explain_error` says exactly that instead of a raw code.
  2. No editing and no deleting messages, so no status message: the owner gets a typing
     indicator (sent with the read receipt) and the tool trail rides on the answer.
  3. Formatting is WhatsApp's own: *bold*, _italic_, ~strike~, ```mono```. 4096 chars max.
  4. Private chats only through this API; groups are not supported here.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
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

# Graph API versions are retired about two years after release. Pin a recent one and let an
# environment variable move it without a release when Meta retires it.
GRAPH_VERSION = os.getenv("JAVIS_WHATSAPP_GRAPH_VERSION", "v23.0")
GRAPH = f"https://graph.facebook.com/{GRAPH_VERSION}"

MAX_MSG = 4000
MAX_DEDUPE = 4000
MAX_DOWNLOAD_MB = 20
TYPING_EVERY = 20.0          # the indicator lasts up to 25 s or until the next message

# phone_number_id -> WhatsAppBot currently running for it.
_REGISTRY: dict = {}


def split_credentials(raw) -> dict:
    """"<phone number id> <access token> <app secret>" in any order -> dict.

    One string because the channel-account store keeps one encrypted secret per account.
    The three parts are told apart by shape: the phone number id is all digits, the app
    secret is 32 hex characters, the access token is the long remaining one (EAA...).
    """
    out = {"phone_number_id": "", "access_token": "", "app_secret": ""}
    for part in re.split(r"[\s,;|]+", str(raw or "").strip()):
        if not part:
            continue
        if re.fullmatch(r"\d{6,25}", part):
            out["phone_number_id"] = part
        elif re.fullmatch(r"[0-9a-fA-F]{32}", part):
            out["app_secret"] = part
        elif len(part) > 40:
            out["access_token"] = part
    return out


def md_to_whatsapp(text: str) -> str:
    """Markdown -> WhatsApp formatting. Code blocks are left untouched."""
    parts = re.split(r"(```.*?```)", str(text or ""), flags=re.S)
    out = []
    for i, p in enumerate(parts):
        if i % 2 == 1:
            out.append(p)
            continue
        p = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r"\1", p)
        p = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"\1 (\2)", p)
        p = re.sub(r"^#{1,6}\s+(.+?)\s*#*$", r"*\1*", p, flags=re.M)
        p = re.sub(r"\*\*(.+?)\*\*", r"*\1*", p)
        p = re.sub(r"__(.+?)__", r"*\1*", p)
        p = re.sub(r"~~(.+?)~~", r"~\1~", p)
        out.append(p)
    return "".join(out)


def _chunks(text: str, size: int = MAX_MSG) -> list:
    text = str(text or "")
    if len(text) <= size:
        return [text]
    out = []
    while len(text) > size:
        cut = text.rfind("\n", 0, size)
        if cut < size // 2:
            cut = size
        out.append(text[:cut].rstrip())
        text = text[cut:].lstrip("\n")
    if text.strip():
        out.append(text)
    return out


def verify_signature(raw_body: bytes, header: str, secrets_list) -> bool:
    """True when `X-Hub-Signature-256` matches the body under ANY known app secret.

    The webhook URL is public, so this is the only thing standing between the internet and a
    fake "message from the owner". Constant-time compare; an empty secret never matches.
    """
    sig = str(header or "")
    if not sig.startswith("sha256="):
        return False
    got = sig[len("sha256="):].strip()
    for s in secrets_list or []:
        s = str(s or "")
        if not s:
            continue
        want = hmac.new(s.encode(), raw_body or b"", hashlib.sha256).hexdigest()
        if hmac.compare_digest(want, got):
            return True
    return False


def registered() -> dict:
    return dict(_REGISTRY)


async def handle_webhook(payload: dict) -> int:
    """Route a verified webhook payload to the bots it is for. Returns how many messages were
    handed over. Statuses (sent/delivered/read) are ignored; failures among them are logged."""
    n = 0
    for entry in (payload or {}).get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            pid = str((value.get("metadata") or {}).get("phone_number_id") or "")
            bot = _REGISTRY.get(pid)
            for st in value.get("statuses") or []:
                if st.get("status") == "failed":
                    err = ((st.get("errors") or [{}])[0])
                    print(f"[whatsapp] delivery failed to {st.get('recipient_id')}: "
                          f"{err.get('code')} {err.get('title')}", file=sys.stderr)
                    if bot:
                        bot.last_error = _explain_error(err.get("code"), err.get("title"))
            if not bot:
                if value.get("messages"):
                    print(f"[whatsapp] message for phone number id {pid} but no bot runs for it",
                          file=sys.stderr)
                continue
            contacts = {str(c.get("wa_id")): ((c.get("profile") or {}).get("name") or "")
                        for c in value.get("contacts") or []}
            for msg in value.get("messages") or []:
                asyncio.create_task(bot._safe_message(msg, contacts))
                n += 1
    return n


class WhatsAppBot(HangLuot):
    def __init__(self, token, chat_id, answer_fn, command_fn=None, callback_fn=None,
                 download_dir=None, commands=None, precheck_fn=None, event_fn=None,
                 giau_trang_thai=False, stt_fn=None, **_ignored):
        creds = split_credentials(token) if not isinstance(token, dict) else dict(token)
        self.phone_number_id = str(creds.get("phone_number_id") or "")
        self.token = str(creds.get("access_token") or "")
        self.app_secret = str(creds.get("app_secret") or "")
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
        self.bot_id = self.phone_number_id
        self.bot_username = ""
        self.loi_danh_tinh = ""
        self.doc_moi_tin_nhom = False
        self.last_inbound = 0.0       # time of the last message from anyone (24 h window)
        self._seen = set()
        self._seen_order = deque()
        self._client = None

    # ---- HTTP -------------------------------------------------------------------------
    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    async def _post_json(self, client, path, payload):
        try:
            r = await client.post(f"{GRAPH}/{path}", json=payload, headers=self._headers())
            try:
                d = r.json() or {}
            except Exception:
                d = {}
            if r.status_code >= 300 or d.get("error"):
                e = d.get("error") or {}
                return {"ok": False, "code": e.get("code") or r.status_code,
                        "error": _explain_error(e.get("code"), e.get("message") or f"HTTP {r.status_code}")}
            d["ok"] = True
            return d
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}", "net_error": True}

    async def _send_one(self, client, to, text):
        return await self._post_json(client, f"{self.phone_number_id}/messages", {
            "messaging_product": "whatsapp", "recipient_type": "individual", "to": str(to),
            "type": "text", "text": {"preview_url": False, "body": md_to_whatsapp(text)}})

    async def _send(self, client, chat, text, reply_markup=None):
        if not str(text or "").strip() and self.giau_trang_thai:
            return
        text = text or localefmt.chu("(không có nội dung)", "(no content)")
        for chunk in _chunks(text):
            d = await self._send_one(client, chat, chunk)
            if not d.get("ok"):
                self.last_error = d.get("error", "")
                print(f"[whatsapp send] {d.get('error')}", file=sys.stderr)
                break

    async def send_text(self, chat, text):
        text = str(text or "").strip()
        if not text:
            return False, "empty message"
        if not (self.token and self.phone_number_id):
            return False, localefmt.chu("thiếu access token hoặc phone number id WhatsApp",
                                        "missing WhatsApp access token or phone number id")
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            for chunk in _chunks(text):
                d = await self._send_one(client, chat, chunk)
                if not d.get("ok"):
                    return False, d.get("error", "")
        return True, ""

    async def send_file(self, path, caption="", chat=None):
        """Upload the file to Meta's media store, then send it by id. Returns (ok, error)."""
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
        kind = "image" if mime in ("image/jpeg", "image/png") else "document"
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as c:
            try:
                r = await c.post(f"{GRAPH}/{self.phone_number_id}/media", headers=self._headers(),
                                 data={"messaging_product": "whatsapp", "type": mime},
                                 files={"file": (p.name, data, mime)})
                d = r.json() or {}
            except Exception as e:
                return False, f"{type(e).__name__}: {e}"
            if not d.get("id"):
                e = d.get("error") or {}
                return False, _explain_error(e.get("code"), e.get("message") or "upload failed")
            body = {"id": d["id"]}
            if caption:
                body["caption"] = md_to_whatsapp(str(caption))[:1000]
            if kind == "document":
                body["filename"] = p.name
            res = await self._post_json(c, f"{self.phone_number_id}/messages", {
                "messaging_product": "whatsapp", "to": str(chat), "type": kind, kind: body})
            return (True, "") if res.get("ok") else (False, res.get("error", ""))

    async def _read_and_type(self, client, message_id):
        """Read receipt plus typing indicator in one call (Cloud API, 2025)."""
        if not message_id:
            return
        await self._post_json(client, f"{self.phone_number_id}/messages", {
            "messaging_product": "whatsapp", "status": "read", "message_id": message_id,
            "typing_indicator": {"type": "text"}})

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

    async def _download_media(self, client, media_id) -> tuple:
        d = await client.get(f"{GRAPH}/{media_id}", headers=self._headers())
        info = d.json() or {}
        url = info.get("url")
        if not url:
            raise RuntimeError("no media url")
        if int(info.get("file_size") or 0) > MAX_DOWNLOAD_MB * 1024 * 1024:
            raise RuntimeError(f"larger than {MAX_DOWNLOAD_MB}MB")
        r = await client.get(url, headers=self._headers(), timeout=httpx.Timeout(180.0))
        r.raise_for_status()
        return r.content, str(info.get("mime_type") or "")

    async def _message_text(self, client, msg, chat) -> str:
        mtype = msg.get("type")
        if mtype == "text":
            return str((msg.get("text") or {}).get("body") or "").strip()
        if mtype == "interactive":
            it = msg.get("interactive") or {}
            rep = it.get("button_reply") or it.get("list_reply") or {}
            return str(rep.get("title") or "").strip()
        if mtype == "button":
            return str((msg.get("button") or {}).get("text") or "").strip()
        if mtype in ("image", "document", "audio", "video", "sticker"):
            media = msg.get(mtype) or {}
            caption = str(media.get("caption") or "").strip()
            if mtype == "sticker":
                return localefmt.chu("[Người dùng gửi một sticker WhatsApp.]",
                                     "[The user sent a WhatsApp sticker.]")
            try:
                data, mime = await self._download_media(client, media.get("id"))
            except Exception as e:
                return (f"[{mtype}: {type(e).__name__}: {e}]\n" + caption).strip()
            if mtype == "audio":
                if not self.stt_fn:
                    return stt.loi_thanh_dong("thieu_key")
                try:
                    kq = await self.stt_fn(data, f"whatsapp_{int(time.time())}.ogg")
                except Exception as e:
                    kq = {"ok": False, "noi_voi_javis": stt.loi_thanh_dong("loi", f"{type(e).__name__}: {e}")}
                if not (kq or {}).get("ok"):
                    return (kq or {}).get("noi_voi_javis") or stt.loi_thanh_dong("loi")
                return stt.khoi_thoai(kq.get("text"), "WhatsApp")
            ddir = self.download_dir(chat) if callable(self.download_dir) else self.download_dir
            d = Path(ddir) if ddir else Path("whatsapp-inbox")
            d.mkdir(parents=True, exist_ok=True)
            ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
                   "application/pdf": ".pdf"}.get(mime, "")
            name = str(media.get("filename") or f"whatsapp_{int(time.time())}{ext}")
            dest = d / re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
            dest.write_bytes(data)
            note = localefmt.chu(f"[Người dùng gửi file qua WhatsApp, đã tải về: {dest}]",
                                 f"[The user sent a file on WhatsApp, downloaded to: {dest}]")
            return (note + ("\n" + caption if caption else "")).strip()
        if mtype == "location":
            loc = msg.get("location") or {}
            return f"[location: {loc.get('latitude')}, {loc.get('longitude')} {loc.get('name') or ''}]".strip()
        return ""

    async def _safe_message(self, msg, contacts):
        try:
            await self._on_message(msg, contacts)
        except Exception as e:
            print(f"[whatsapp message] {type(e).__name__}: {e}", file=sys.stderr)

    async def _on_message(self, msg, contacts):
        if self._stop or self._seen_before(msg.get("id")):
            return
        chat = str(msg.get("from") or "")
        if not chat:
            return
        self.last_inbound = time.time()
        client = self._client or httpx.AsyncClient(timeout=httpx.Timeout(60.0))
        self._client = client
        name = contacts.get(chat, "")
        meta = {
            "platform": "whatsapp", "chat_id": chat, "chat_type": "private", "chat_title": "",
            "user_name": name, "username": name, "user_id": chat,
            "message_id": msg.get("id"), "bot_username": self.bot_username,
            "mentioned": False, "reply_to_bot": bool(msg.get("context")),
        }
        if self.chat_ids and chat not in self.chat_ids:
            await self._send(client, chat, localefmt.chu(
                "Bạn không có quyền dùng bot Javis này.", "You are not allowed to use this Javis bot."))
            return
        text = await self._message_text(client, msg, chat)
        if not text:
            return
        await self._read_and_type(client, msg.get("id"))
        meta["_wa_mid"] = msg.get("id")
        await self._dispatch(client, chat, text, meta)

    # ---- One turn ---------------------------------------------------------------------
    async def _keep_typing(self, client, mid):
        while True:
            await asyncio.sleep(TYPING_EVERY)
            await self._read_and_type(client, mid)

    async def _handle_turn(self, client, chat, text, meta=None):
        files = []
        tools = []
        t0 = time.monotonic()
        keep = asyncio.create_task(self._keep_typing(client, (meta or {}).get("_wa_mid")))

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
                print(f"[whatsapp turn failed] {type(e).__name__}: {e}", file=sys.stderr)
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
        finally:
            keep.cancel()

    # ---- Lifecycle --------------------------------------------------------------------
    async def _watch(self):
        """No connection to hold: the webhook pushes. This task only exists so supervisors that
        judge liveness by `_task` see the bot as running, and to check the credentials once."""
        if not (self.token and self.phone_number_id):
            self.status = "error"
            self.last_error = localefmt.chu(
                "Thiếu phone number id hoặc access token.", "Missing the phone number id or access token.")
            return
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as c:
            info = await whoami(c, self.phone_number_id, self.token)
        if not info.get("ok"):
            self.status = "error"
            self.last_error = info.get("error", "")
            self.loi_danh_tinh = self.last_error
            return
        self.bot_username = info.get("username", "")
        old = _REGISTRY.get(self.phone_number_id)
        if old is not None and old is not self:
            print(f"[whatsapp] phone number id {self.phone_number_id} was served by another bot; "
                  "the newest one takes over", file=sys.stderr)
        _REGISTRY[self.phone_number_id] = self
        self.status = "polling"
        self.last_error = ""
        try:
            while not self._stop:
                await asyncio.sleep(3600)
        finally:
            if _REGISTRY.get(self.phone_number_id) is self:
                _REGISTRY.pop(self.phone_number_id, None)

    def start(self):
        self._stop = False
        self.status = "starting"
        if not self._task or self._task.done():
            self._task = asyncio.create_task(self._watch())

    def stop(self):
        self._stop = True
        self.status = "stopped"
        if _REGISTRY.get(self.phone_number_id) is self:
            _REGISTRY.pop(self.phone_number_id, None)
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


async def whoami(client, phone_number_id, token) -> dict:
    """Ask Graph which number this id is. {"ok", "username", "bot_name"} or {"ok": False, "error"}."""
    try:
        r = await client.get(f"{GRAPH}/{phone_number_id}",
                             params={"fields": "display_phone_number,verified_name"},
                             headers={"Authorization": f"Bearer {token}"})
        d = r.json() or {}
    except Exception as e:
        return {"ok": False, "error": localefmt.chu(f"Không nối được Meta: {e}", f"Could not reach Meta: {e}")}
    if d.get("error") or not d.get("display_phone_number"):
        e = d.get("error") or {}
        return {"ok": False, "error": _explain_error(e.get("code"), e.get("message") or "invalid credentials")}
    return {"ok": True, "username": str(d.get("display_phone_number") or ""),
            "bot_name": str(d.get("verified_name") or "")}


# Error codes the owner can act on. https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes
_ERRORS = {
    131047: ("quá 24 giờ kể từ tin cuối người đó nhắn, WhatsApp chỉ cho gửi tin mẫu (template). "
             "Nhắn cho số bot một câu bất kỳ để mở lại cửa sổ 24 giờ",
             "more than 24 hours since this person last wrote, so WhatsApp only allows template "
             "messages. Send the bot any message to reopen the 24-hour window"),
    190: ("access token hết hạn hoặc sai. Dùng token vĩnh viễn của System User, không dùng token "
          "tạm 24 giờ", "the access token expired or is wrong. Use a permanent System User token, "
          "not the temporary 24-hour one"),
    131030: ("số người nhận chưa được thêm vào danh sách thử nghiệm của app",
             "the recipient is not in the app's test number list"),
    131026: ("không gửi được tới số này (chưa có WhatsApp hoặc chặn)",
             "could not deliver to this number (no WhatsApp, or blocked)"),
    100: ("tham số sai, thường là phone number id không đúng", "invalid parameter, usually a wrong phone number id"),
    80007: ("vượt hạn mức gửi của WhatsApp, thử lại sau", "WhatsApp rate limit reached, try again later"),
}


def _explain_error(code, fallback="") -> str:
    try:
        code_i = int(code)
    except Exception:
        code_i = None
    vi_en = _ERRORS.get(code_i)
    if vi_en:
        return localefmt.chu(f"{vi_en[0]} ({code_i})", f"{vi_en[1]} ({code_i})")
    return f"{fallback or 'error'}" + (f" ({code})" if code else "")
