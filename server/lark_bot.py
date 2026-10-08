"""Lark / Feishu gateway for the owner's control channel (0.85.0).

Why the long connection (长连接) instead of the event webhook: Javis opens the WebSocket OUT to
Lark, so it works on a laptop or behind NAT with no public URL and no encrypt key to configure,
the same way Telegram long-polling and Slack Socket Mode do. In the Lark developer console the owner
picks "Receive events through persistent connection" and subscribes `im.message.receive_v1`.

Two credentials from the same custom app: App ID (`cli_...`) and App Secret. One setting picks the
cloud: Feishu (open.feishu.cn, mainland China) or Lark (open.larksuite.com, international). They are
separate platforms; an app made on one does not exist on the other.

The wire format is Lark's own: binary protobuf frames (`pbbp2.Frame`) over the socket. The official
SDK hides it, but pulling in `lark-oapi` (and its own event loop in a thread) for six fields is not
worth it, so `encode_frame` / `decode_frame` below implement exactly the message Lark sends:

    Frame  { 1 SeqID uint64, 2 LogID uint64, 3 service int32, 4 method int32,
             5 headers repeated Header, 6 payload_encoding string, 7 payload_type string,
             8 payload bytes, 9 LogIDNew string }
    Header { 1 key string, 2 value string }

method 0 = control (ping/pong), 1 = data. A data frame carries headers `type` (event/card),
`message_id`, `sum`/`seq` (a large event is split across frames) and must be answered with the same
frame whose payload is `{"code": 200}`, or Lark redelivers it.

The class keeps the transport contract of `TelegramBot` / `SlackBot` (see `bot_gateway`).
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from collections import deque
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

import localefmt
import stt
from bot_gateway import HangLuot, dong_vet, parse_chat_ids, ten_tool

DOMAINS = {"feishu": "https://open.feishu.cn", "lark": "https://open.larksuite.com"}

MAX_MSG = 3800
MAX_DEDUPE = 2000
MAX_DOWNLOAD_MB = 20
RECONNECT_MAX = 120
PING_DEFAULT = 120.0

METHOD_CONTROL = 0
METHOD_DATA = 1


# ============================================================
# pbbp2.Frame, by hand
# ============================================================
def _varint(n: int) -> bytes:
    n &= (1 << 64) - 1
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _read_varint(buf: bytes, i: int):
    shift = n = 0
    while True:
        if i >= len(buf):
            raise ValueError("truncated varint")
        b = buf[i]
        i += 1
        n |= (b & 0x7F) << shift
        if not b & 0x80:
            return n, i
        shift += 7
        if shift > 70:
            raise ValueError("varint too long")


def _field(num: int, wire: int) -> bytes:
    return _varint((num << 3) | wire)


def _bytes_field(num: int, data: bytes) -> bytes:
    return _field(num, 2) + _varint(len(data)) + data


def encode_frame(f: dict) -> bytes:
    out = bytearray()
    out += _field(1, 0) + _varint(int(f.get("seq_id") or 0))
    out += _field(2, 0) + _varint(int(f.get("log_id") or 0))
    out += _field(3, 0) + _varint(int(f.get("service") or 0))
    out += _field(4, 0) + _varint(int(f.get("method") or 0))
    for k, v in (f.get("headers") or {}).items():
        h = _bytes_field(1, str(k).encode()) + _bytes_field(2, str(v).encode())
        out += _bytes_field(5, h)
    if f.get("payload_encoding"):
        out += _bytes_field(6, str(f["payload_encoding"]).encode())
    if f.get("payload_type"):
        out += _bytes_field(7, str(f["payload_type"]).encode())
    if f.get("payload") is not None:
        out += _bytes_field(8, bytes(f["payload"]))
    if f.get("log_id_new"):
        out += _bytes_field(9, str(f["log_id_new"]).encode())
    return bytes(out)


def _parse_fields(buf: bytes):
    i = 0
    while i < len(buf):
        key, i = _read_varint(buf, i)
        num, wire = key >> 3, key & 7
        if wire == 0:
            val, i = _read_varint(buf, i)
        elif wire == 2:
            ln, i = _read_varint(buf, i)
            val, i = buf[i:i + ln], i + ln
        elif wire == 1:
            val, i = buf[i:i + 8], i + 8
        elif wire == 5:
            val, i = buf[i:i + 4], i + 4
        else:
            raise ValueError(f"unsupported wire type {wire}")
        yield num, val


def decode_frame(buf: bytes) -> dict:
    f = {"seq_id": 0, "log_id": 0, "service": 0, "method": 0, "headers": {}, "payload": b"",
         "payload_encoding": "", "payload_type": "", "log_id_new": ""}
    names = {1: "seq_id", 2: "log_id", 3: "service", 4: "method"}
    for num, val in _parse_fields(bytes(buf)):
        if num in names:
            f[names[num]] = val
        elif num == 5:
            h = dict(_parse_fields(val))
            f["headers"][bytes(h.get(1, b"")).decode("utf-8", "replace")] = \
                bytes(h.get(2, b"")).decode("utf-8", "replace")
        elif num == 6:
            f["payload_encoding"] = bytes(val).decode("utf-8", "replace")
        elif num == 7:
            f["payload_type"] = bytes(val).decode("utf-8", "replace")
        elif num == 8:
            f["payload"] = bytes(val)
        elif num == 9:
            f["log_id_new"] = bytes(val).decode("utf-8", "replace")
    return f


# ============================================================
# Text helpers
# ============================================================
def _chunks(text: str, size: int = MAX_MSG) -> list:
    text = str(text or "")
    if len(text) <= size:
        return [text]
    out = []
    while len(text) > size:
        cut = text.rfind("\n\n", 0, size)
        if cut < size // 2:
            cut = text.rfind("\n", 0, size)
        if cut < size // 2:
            cut = size
        out.append(text[:cut].rstrip())
        text = text[cut:].lstrip("\n")
    if text.strip():
        out.append(text)
    return out


def card_content(md: str) -> str:
    """A message card with one markdown element: the one Lark message type that renders the
    Markdown engines write (bold, italics, links, lists, code). Plain `text` would show the stars."""
    return json.dumps({"config": {"wide_screen_mode": True},
                       "elements": [{"tag": "markdown", "content": md}]}, ensure_ascii=False)


def receive_id_type(target: str) -> str:
    """Lark ids carry their kind in the prefix: oc_ chat, ou_ open_id, on_ union_id."""
    t = str(target or "")
    if t.startswith("ou_"):
        return "open_id"
    if t.startswith("on_"):
        return "union_id"
    return "chat_id"


class LarkBot(HangLuot):
    """Same contract as `TelegramBot`: start(), stop(), status, last_error, _task, send_text,
    send_file, plus the attributes `bot_gateway.HangLuot` needs."""

    def __init__(self, token, chat_id, answer_fn, command_fn=None, callback_fn=None,
                 download_dir=None, commands=None, precheck_fn=None, event_fn=None,
                 giau_trang_thai=False, stt_fn=None, **_ignored):
        cred = token if isinstance(token, dict) else {}
        self.app_id = str(cred.get("app_id") or "").strip()
        self.app_secret = str(cred.get("app_secret") or "").strip()
        self.domain = cred.get("domain") if cred.get("domain") in DOMAINS else "lark"
        self.base = DOMAINS[self.domain]
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
        self.status = "off"           # off | starting | polling | error | stopped
        self.last_error = ""
        self.bot_id = ""              # the bot's open_id, what mentions point at
        self.bot_username = ""
        self.loi_danh_tinh = ""
        self.doc_moi_tin_nhom = False
        self._seen = set()
        self._seen_order = deque()
        self._reply_to = {}           # chat -> message id to reply to (groups)
        self._token = ""
        self._token_exp = 0.0
        self._parts = {}              # message_id -> {seq: bytes} for split events
        self._ping_every = PING_DEFAULT
        self._service_id = 0

    # ---- Auth and HTTP ----------------------------------------------------------------
    async def _tenant_token(self, client) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        try:
            r = await client.post(self.base + "/open-apis/auth/v3/tenant_access_token/internal",
                                  json={"app_id": self.app_id, "app_secret": self.app_secret})
            d = r.json() or {}
        except Exception as e:
            raise RuntimeError(f"{type(e).__name__}: {e}")
        if d.get("code") != 0 or not d.get("tenant_access_token"):
            raise RuntimeError(_explain(d))
        self._token = str(d["tenant_access_token"])
        self._token_exp = time.time() + float(d.get("expire") or 3600)
        return self._token

    async def _api(self, client, method, path, **kw):
        """One Open API call. Always returns a dict; failures carry `code` != 0."""
        try:
            tok = await self._tenant_token(client)
        except Exception as e:
            return {"code": -1, "msg": str(e)}
        headers = {"Authorization": f"Bearer {tok}"}
        try:
            r = await client.request(method, self.base + path, headers=headers, **kw)
        except Exception as e:
            return {"code": -1, "msg": f"{type(e).__name__}: {e}"}
        try:
            d = r.json()
        except Exception:
            return {"code": r.status_code or -1, "msg": f"HTTP {r.status_code}", "raw": r.content}
        return d if isinstance(d, dict) else {"code": -1, "msg": "bad response"}

    async def _post(self, client, chat, text, reply_to=None):
        """Send one chunk as a markdown card; if the card is refused, as plain text."""
        for msg_type, content in (("interactive", card_content(text)),
                                  ("text", json.dumps({"text": text}, ensure_ascii=False))):
            if reply_to:
                d = await self._api(client, "POST", f"/open-apis/im/v1/messages/{reply_to}/reply",
                                    json={"msg_type": msg_type, "content": content})
            else:
                d = await self._api(client, "POST", "/open-apis/im/v1/messages",
                                    params={"receive_id_type": receive_id_type(chat)},
                                    json={"receive_id": chat, "msg_type": msg_type, "content": content})
            if d.get("code") == 0:
                return d
        return d

    async def _send(self, client, chat, text, reply_markup=None):
        if not str(text or "").strip() and self.giau_trang_thai:
            return
        text = text or localefmt.chu("(không có nội dung)", "(no content)")
        reply_to = self._reply_to.get(chat)
        for i, chunk in enumerate(_chunks(text)):
            d = await self._post(client, chat, chunk, reply_to if i == 0 else None)
            if d.get("code") != 0:
                print(f"[lark send] {_explain(d)}", file=sys.stderr)

    async def send_text(self, chat, text):
        """Send ONE message outside a turn. `chat` is a chat id (oc_) from a turn or an open_id
        (ou_) from the allow-list. Returns (ok, error)."""
        text = str(text or "").strip()
        if not text:
            return False, "empty message"
        if not (self.app_id and self.app_secret):
            return False, localefmt.chu("thiếu App ID hoặc App Secret của Lark",
                                        "missing Lark App ID or App Secret")
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            for chunk in _chunks(text):
                d = await self._post(client, chat, chunk)
                if d.get("code") != 0:
                    return False, _explain(d)
        return True, ""

    async def send_file(self, path, caption="", chat=None):
        """Upload then send: images as `image`, everything else as `file`. Returns (ok, error)."""
        chat = chat or (self.chat_ids[0] if self.chat_ids else "")
        if not chat:
            return False, "no chat to send to"
        p = Path(str(path))
        try:
            if not p.is_file():
                return False, f"file not found: {path}"
            data = p.read_bytes()
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"
        is_img = p.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as c:
            if is_img:
                d = await self._api(c, "POST", "/open-apis/im/v1/images",
                                    data={"image_type": "message"}, files={"image": (p.name, data)})
                key = ((d.get("data") or {}).get("image_key") or "")
                msg_type, content = "image", {"image_key": key}
            else:
                d = await self._api(c, "POST", "/open-apis/im/v1/files",
                                    data={"file_type": "stream", "file_name": p.name},
                                    files={"file": (p.name, data)})
                key = ((d.get("data") or {}).get("file_key") or "")
                msg_type, content = "file", {"file_key": key}
            if d.get("code") != 0 or not key:
                return False, _explain(d)
            d = await self._api(c, "POST", "/open-apis/im/v1/messages",
                                params={"receive_id_type": receive_id_type(chat)},
                                json={"receive_id": chat, "msg_type": msg_type,
                                      "content": json.dumps(content)})
            if d.get("code") != 0:
                return False, _explain(d)
            if caption:
                await self._post(c, chat, str(caption))
        return True, ""

    # ---- Inbound ----------------------------------------------------------------------
    def _seen_before(self, key) -> bool:
        if not key:
            return False
        if key in self._seen:
            return True
        self._seen.add(key)
        self._seen_order.append(key)
        while len(self._seen_order) > MAX_DEDUPE:
            self._seen.discard(self._seen_order.popleft())
        return False

    def _mentioned(self, msg) -> bool:
        for m in msg.get("mentions") or []:
            if self.bot_id and str(((m or {}).get("id") or {}).get("open_id") or "") == self.bot_id:
                return True
        return False

    @staticmethod
    def _strip_mentions(text, msg) -> str:
        for m in msg.get("mentions") or []:
            k = str((m or {}).get("key") or "")
            if k:
                text = text.replace(k, "")
        return re.sub(r"\s{2,}", " ", text).strip()

    def build_meta(self, ev) -> dict:
        sender = ev.get("sender") or {}
        sid = sender.get("sender_id") or {}
        msg = ev.get("message") or {}
        private = str(msg.get("chat_type") or "") == "p2p"
        return {
            "platform": "lark",
            "chat_id": str(msg.get("chat_id") or ""),
            "chat_type": "private" if private else "group",
            "chat_title": "",
            "user_name": "",
            "username": "",
            "user_id": str(sid.get("open_id") or ""),
            "message_id": str(msg.get("message_id") or ""),
            "bot_username": self.bot_username,
            "mentioned": self._mentioned(msg),
            "reply_to_bot": False,
        }

    async def _download(self, client, message_id, key, kind) -> bytes:
        tok = await self._tenant_token(client)
        r = await client.get(self.base + f"/open-apis/im/v1/messages/{message_id}/resources/{key}",
                             params={"type": kind}, headers={"Authorization": f"Bearer {tok}"},
                             timeout=httpx.Timeout(180.0))
        r.raise_for_status()
        if len(r.content) > MAX_DOWNLOAD_MB * 1024 * 1024:
            raise ValueError(f"> {MAX_DOWNLOAD_MB}MB")
        return r.content

    async def message_text(self, client, msg, meta) -> str:
        """The text of a message, with files downloaded and voice transcribed."""
        mtype = str(msg.get("message_type") or "")
        try:
            content = json.loads(msg.get("content") or "{}")
        except Exception:
            content = {}
        if mtype == "text":
            return self._strip_mentions(str(content.get("text") or ""), msg)
        if mtype == "post":
            # Rich text: {"title", "content": [[{"tag":"text","text":...}, ...], ...]}
            body = content.get("content") if "content" in content else next(iter(content.values()), {}).get("content", [])
            parts = [str(content.get("title") or "")]
            for line in body or []:
                parts.append("".join(str(el.get("text") or el.get("href") or "") for el in line or []
                                     if isinstance(el, dict)))
            return self._strip_mentions("\n".join(p for p in parts if p), msg)
        mid = str(msg.get("message_id") or "")
        if mtype in ("image", "file", "audio", "media"):
            key = content.get("image_key") if mtype == "image" else content.get("file_key")
            name = str(content.get("file_name") or f"{mtype}_{int(time.time())}")
            if mtype == "image" and "." not in name:
                name += ".jpg"
            if mtype == "audio" and "." not in name:
                name += ".opus"
            try:
                data = await self._download(client, mid, key, "image" if mtype == "image" else "file")
            except Exception as e:
                return f"[{name}: download failed, {type(e).__name__}]"
            if mtype == "audio":
                if not self.stt_fn:
                    return stt.loi_thanh_dong("thieu_key")
                try:
                    kq = await self.stt_fn(data, name)
                except Exception as e:
                    kq = {"ok": False, "noi_voi_javis": stt.loi_thanh_dong("loi", f"{type(e).__name__}: {e}")}
                return (stt.khoi_thoai(kq.get("text"), "Lark") if (kq or {}).get("ok")
                        else ((kq or {}).get("noi_voi_javis") or stt.loi_thanh_dong("loi")))
            chat = meta.get("chat_id", "")
            ddir = self.download_dir(chat) if callable(self.download_dir) else self.download_dir
            d = Path(ddir) if ddir else Path("lark-inbox")
            d.mkdir(parents=True, exist_ok=True)
            dest = d / re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", f"lark_{int(time.time())}_{name}")
            dest.write_bytes(data)
            return localefmt.chu(f"[Người dùng gửi file qua Lark, đã tải về: {dest}]",
                                 f"[The user sent a file on Lark, downloaded to: {dest}]")
        return ""

    async def _on_event(self, client, envelope):
        header = envelope.get("header") or {}
        if header.get("event_type") != "im.message.receive_v1":
            return
        ev = envelope.get("event") or {}
        if str((ev.get("sender") or {}).get("sender_type") or "") not in ("", "user"):
            return            # the bot's own messages and other apps
        meta = self.build_meta(ev)
        msg = ev.get("message") or {}
        chat = meta["chat_id"]
        if not chat or self._seen_before(meta["message_id"] or header.get("event_id")):
            return
        if meta["chat_type"] != "private" and not meta["mentioned"] and not self.giau_trang_thai:
            return            # a group: only when @mentioned
        if self.chat_ids and meta["user_id"] not in self.chat_ids and chat not in self.chat_ids:
            await self._send(client, chat, localefmt.chu(
                "Bạn không có quyền dùng bot Javis này.", "You are not allowed to use this Javis bot."))
            return
        text = await self.message_text(client, msg, meta)
        if text.startswith("!") and len(text) > 1 and text[1].isalpha():
            text = "/" + text[1:]
        if not text:
            return
        self._reply_to[chat] = meta["message_id"] if meta["chat_type"] != "private" else None
        await self._dispatch(client, chat, text, meta)

    # ---- One turn ---------------------------------------------------------------------
    async def _handle_turn(self, client, chat, text, meta=None):
        files = []
        tools = []
        t0 = time.monotonic()
        reaction = None
        mid = (meta or {}).get("message_id")
        if mid and not self.giau_trang_thai:
            # Lark has no typing indicator for bots; a reaction on the question says "on it".
            d = await self._api(client, "POST", f"/open-apis/im/v1/messages/{mid}/reactions",
                                json={"reaction_type": {"emoji_type": "OnIt"}})
            reaction = ((d.get("data") or {}).get("reaction_id")) if d.get("code") == 0 else None

        async def progress(txt):
            name = ten_tool(txt)
            if name and name not in tools:
                tools.append(name)

        try:
            reply = await self.answer_fn(text, meta, progress)
        except asyncio.CancelledError:
            return
        except Exception as e:
            print(f"[lark turn failed] {type(e).__name__}: {e}", file=sys.stderr)
            from telegram_bot import CAU_LOI_NGUOI_THAT
            reply = (CAU_LOI_NGUOI_THAT if self.giau_trang_thai else f"⚠ {type(e).__name__}: {e}")
        finally:
            if reaction:
                await self._api(client, "DELETE", f"/open-apis/im/v1/messages/{mid}/reactions/{reaction}")
        silent = False
        if isinstance(reply, dict):
            files = reply.get("files") or []
            silent = bool(reply.get("im_lang"))
            reply = reply.get("text") or ""
        if silent and not str(reply or "").strip() and not files:
            return
        if tools and not self.giau_trang_thai:
            reply = f"{reply}\n\n<font color='grey'>{dong_vet(tools, time.monotonic() - t0)}</font>"
        if str(reply or "").strip() or not files:
            await self._send(client, chat, reply)
        for f in files:
            fpath, fcap = (f.get("path"), f.get("caption", "")) if isinstance(f, dict) else (f, "")
            ok, err = await self.send_file(fpath, fcap, chat=chat)
            if not ok:
                print(f"[lark send file] {fpath}: {err}", file=sys.stderr)
                if not self.giau_trang_thai:
                    await self._send(client, chat, f"⚠ {Path(str(fpath)).name}: {err}")

    # ---- Long connection --------------------------------------------------------------
    async def _whoami(self, client) -> bool:
        d = await self._api(client, "GET", "/open-apis/bot/v3/info")
        bot = d.get("bot") or {}
        if d.get("code") == 0 and bot.get("open_id"):
            self.bot_id = str(bot["open_id"])
            self.bot_username = str(bot.get("app_name") or "")
            self.loi_danh_tinh = ""
            return True
        self.loi_danh_tinh = localefmt.chu(f"Lark từ chối App ID / App Secret ({_explain(d)}).",
                                           f"Lark refused the App ID / App Secret ({_explain(d)}).")
        return False

    async def _endpoint(self, client) -> str:
        r = await client.post(self.base + "/callback/ws/endpoint",
                              json={"AppID": self.app_id, "AppSecret": self.app_secret},
                              headers={"locale": "zh"})
        try:
            d = r.json() or {}
        except Exception:
            d = {"code": r.status_code, "msg": f"HTTP {r.status_code}"}
        data = d.get("data") or {}
        if d.get("code") != 0 or not data.get("URL"):
            raise RuntimeError(_explain(d))
        cc = data.get("ClientConfig") or {}
        if cc.get("PingInterval"):
            self._ping_every = float(cc["PingInterval"])
        url = str(data["URL"])
        try:
            self._service_id = int((parse_qs(urlparse(url).query).get("service_id") or ["0"])[0])
        except ValueError:
            self._service_id = 0
        return url

    def _ping_frame(self) -> bytes:
        return encode_frame({"service": self._service_id, "method": METHOD_CONTROL,
                             "headers": {"type": "ping"}})

    async def _pinger(self, ws):
        try:
            while True:
                await ws.send(self._ping_frame())
                await asyncio.sleep(self._ping_every)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    def ack_frame(self, frame: dict, started: float) -> bytes:
        """The answer Lark waits for: the same frame, payload {"code": 200}."""
        h = dict(frame.get("headers") or {})
        h["biz_rt"] = str(int((time.monotonic() - started) * 1000))
        return encode_frame(dict(frame, headers=h, payload=json.dumps({"code": 200}).encode()))

    def assemble(self, frame: dict):
        """Join a split event (`sum` > 1). Returns the full payload, or None while parts are missing."""
        h = frame.get("headers") or {}
        try:
            total = int(h.get("sum") or 1)
            seq = int(h.get("seq") or 0)
        except ValueError:
            total, seq = 1, 0
        if total <= 1:
            return frame.get("payload") or b""
        mid = h.get("message_id") or ""
        parts = self._parts.setdefault(mid, {})
        parts[seq] = frame.get("payload") or b""
        if len(parts) < total:
            if len(self._parts) > 100:
                self._parts.pop(next(iter(self._parts)), None)
            return None
        self._parts.pop(mid, None)
        return b"".join(parts[i] for i in sorted(parts))

    async def _session(self, client, url: str):
        import websockets
        async with websockets.connect(url, max_size=16 * 1024 * 1024, ping_interval=None) as ws:
            self.status = "polling"
            self.last_error = ""
            print(f"[lark] connected as {self.bot_username} ({self.domain})", file=sys.stderr)
            pinger = asyncio.create_task(self._pinger(ws))
            try:
                async for raw in _frames(ws):
                    if self._stop:
                        break
                    if not isinstance(raw, (bytes, bytearray)):
                        continue
                    try:
                        frame = decode_frame(raw)
                    except Exception as e:
                        print(f"[lark frame] {type(e).__name__}: {e}", file=sys.stderr)
                        continue
                    h = frame["headers"]
                    if frame["method"] == METHOD_CONTROL:
                        if h.get("type") == "pong" and frame["payload"]:
                            try:
                                cc = json.loads(frame["payload"])
                                if cc.get("PingInterval"):
                                    self._ping_every = float(cc["PingInterval"])
                            except Exception:
                                pass
                        continue
                    started = time.monotonic()
                    payload = self.assemble(frame)
                    # Only events are answered, like the official SDK (card callbacks are not
                    # ours to acknowledge).
                    if payload is None or h.get("type") != "event":
                        continue
                    # Ack first: an engine turn takes far longer than Lark waits.
                    await ws.send(self.ack_frame(frame, started))
                    try:
                        envelope = json.loads(payload)
                    except Exception:
                        continue
                    asyncio.create_task(self._safe_event(client, envelope))
            finally:
                pinger.cancel()

    async def _loop(self):
        backoff = 2
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            if not (self.app_id and self.app_secret):
                self.status = "error"
                self.last_error = localefmt.chu("Cần đủ App ID và App Secret.", "Both App ID and App Secret are needed.")
                return
            try:
                ok = await self._whoami(client)
            except Exception as e:
                ok, self.loi_danh_tinh = False, f"{type(e).__name__}: {e}"
            if not ok:
                self.status = "error"
                self.last_error = self.loi_danh_tinh
                return
            while not self._stop:
                try:
                    url = await self._endpoint(client)
                    await self._session(client, url)
                    backoff = 2
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    if self._stop:
                        break
                    self.status = "error"
                    self.last_error = (handshake_error(e) or f"{type(e).__name__}: {e}")[:300]
                    print(f"[lark socket] {self.last_error}", file=sys.stderr)
                if self._stop:
                    break
                await asyncio.sleep(backoff)
                backoff = min(RECONNECT_MAX, backoff * 2)
        print("[lark] stopped", file=sys.stderr)

    async def _safe_event(self, client, envelope):
        try:
            await self._on_event(client, envelope)
        except Exception as e:
            print(f"[lark event] {type(e).__name__}: {e}", file=sys.stderr)

    def start(self):
        self._stop = False
        self.status = "starting"
        if not self._task or self._task.done():
            self._task = asyncio.create_task(self._loop())

    def stop(self):
        self._stop = True
        self.status = "stopped"
        for t in list(self._current.values()):
            if t and not t.done():
                t.cancel()
        self._current.clear()
        self._cho.clear()
        if self._task:
            self._task.cancel()
            self._task = None


def handshake_error(e) -> str:
    """Lark refuses a socket with headers `handshake-status` / `handshake-msg` (for example too many
    connections for one app: each app allows a few, and a second Javis with the same app counts).
    Returns that message for the owner, or "" when the error is something else."""
    headers = getattr(e, "headers", None)
    if headers is None:
        headers = getattr(getattr(e, "response", None), "headers", None)
    if headers is None:
        return ""
    try:
        status, msg = headers.get("handshake-status"), headers.get("handshake-msg")
    except Exception:
        return ""
    if not status:
        return ""
    return localefmt.chu(f"Lark từ chối kết nối ({status}): {msg or ''}",
                         f"Lark refused the connection ({status}): {msg or ''}").strip()


async def _frames(ws):
    """Iterate a socket's messages and end quietly on any close (see discord_bot._frames)."""
    import websockets
    try:
        async for raw in ws:
            yield raw
    except websockets.exceptions.ConnectionClosed:
        return


# Lark error codes the owner can act on, in words.
_ERRORS = {
    10003: ("App ID hoặc App Secret sai", "wrong App ID or App Secret"),
    10014: ("App Secret sai", "wrong App Secret"),
    99991663: ("token hết hạn hoặc sai", "expired or invalid token"),
    99991672: ("app thiếu quyền, thêm quyền im:message trong console rồi phát hành phiên bản mới",
               "the app lacks a permission: add im:message in the console and publish a new version"),
    230002: ("bot không ở trong nhóm này", "the bot is not in this chat"),
    230013: ("người này chưa thấy được bot (app chưa phát hành tới họ)",
             "this user cannot see the bot (the app is not available to them)"),
}


def _explain(d) -> str:
    d = d if isinstance(d, dict) else {}
    code = d.get("code")
    if code in _ERRORS:
        vi, en = _ERRORS[code]
        return localefmt.chu(f"{vi} ({code})", f"{en} ({code})")
    msg = str(d.get("msg") or d.get("message") or "")[:200]
    return f"{code}: {msg}" if code not in (None, 0) else (msg or "unknown error")
