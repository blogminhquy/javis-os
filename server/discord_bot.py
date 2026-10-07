"""Discord gateway for the owner's control channel (0.85.0).

Why the Gateway (a WebSocket Javis opens OUT to Discord) instead of an Interactions webhook: it
works on a laptop or behind NAT with no public URL, the same way Telegram long-polling and Slack
Socket Mode do, and it receives ordinary messages, not only slash commands.

One credential: the bot token from the Developer Portal (Bot tab). No privileged intent is needed.
Javis asks for GUILDS + GUILD_MESSAGES + DIRECT_MESSAGES only, and Discord still delivers the TEXT of
the messages Javis answers without MESSAGE_CONTENT: direct messages, and server messages that
@mention the bot. Those are exactly the turns the control channel takes, so the owner never has to
switch on a privileged intent (which also needs review once a bot is in 100+ servers).

The class keeps the transport contract of `TelegramBot` / `SlackBot` (see `bot_gateway`), so
`owner_channels` drives it without knowing which platform it holds.

Differences from Slack that change behaviour, not just names:
  1. The connection is ours to keep alive: Discord sends a heartbeat interval in HELLO and drops a
     client that misses beats. A beat whose ACK never came means a zombie socket, so we reconnect.
  2. Reconnects RESUME the session (op 6) when Discord allows it, so messages sent during a short
     drop are replayed instead of lost; otherwise a fresh IDENTIFY.
  3. 2000 characters per message, hard limit. Longer answers are split.
  4. Discord renders Markdown itself (bold, italics, code, lists, headings), so text goes out as is.
  5. A DM to a user needs a DM channel first (POST /users/@me/channels), which is how background
     results reach an owner whose allow-list entry is a user id.
"""
from __future__ import annotations

import asyncio
import json
import random
import re
import sys
import time
from collections import deque
from pathlib import Path

import httpx

import localefmt
import stt
from bot_gateway import HangLuot, dong_vet, parse_chat_ids, ten_tool

API = "https://discord.com/api/v10"
GATEWAY_QS = "/?v=10&encoding=json"

# GUILDS (1<<0) + GUILD_MESSAGES (1<<9) + DIRECT_MESSAGES (1<<12). No privileged intent.
INTENTS = (1 << 0) | (1 << 9) | (1 << 12)

MAX_MSG = 1900              # Discord's hard limit is 2000; leave room for a split marker
MAX_DEDUPE = 2000
MAX_DOWNLOAD_MB = 20
MAX_UPLOAD_MB = 10          # what a server without boosts accepts
TYPING_EVERY = 8.0          # Discord's typing indicator lasts about 10 seconds
RECONNECT_MAX = 60

# Close codes after which reconnecting cannot help: the owner has to fix something.
_FATAL_CLOSE = {
    4004: ("Discord từ chối bot token (token sai hoặc đã đổi).",
           "Discord rejected the bot token (wrong or regenerated token)."),
    4010: ("Discord báo shard không hợp lệ.", "Discord reported an invalid shard."),
    4011: ("Bot đã ở quá nhiều server, cần chia shard.", "The bot is in too many servers and needs sharding."),
    4012: ("Phiên bản Gateway không hợp lệ.", "Invalid Gateway version."),
    4013: ("Intent không hợp lệ.", "Invalid intents."),
    4014: ("Bot đang xin một intent chưa được bật trong Developer Portal.",
           "The bot asks for an intent that is not enabled in the Developer Portal."),
}

_RE_MENTION = re.compile(r"<@!?(\d+)>")


def _chunks(text: str, size: int = MAX_MSG) -> list:
    """Split on paragraph or line breaks when possible, never inside a word, and keep a ``` code
    block balanced across the cut so the second half still renders as code."""
    text = str(text or "")
    if len(text) <= size:
        return [text]
    out = []
    while len(text) > size:
        cut = text.rfind("\n\n", 0, size)
        if cut < size // 2:
            cut = text.rfind("\n", 0, size)
        if cut < size // 2:
            cut = text.rfind(" ", 0, size)
        if cut < size // 2:
            cut = size
        head, text = text[:cut].rstrip(), text[cut:].lstrip("\n")
        if head.count("```") % 2 == 1:
            head += "\n```"
            text = "```\n" + text
        out.append(head)
    if text.strip():
        out.append(text)
    return out


class DiscordBot(HangLuot):
    """Same contract as `TelegramBot`: start(), stop(), status, last_error, _task, send_text,
    send_file, plus the attributes `bot_gateway.HangLuot` needs."""

    def __init__(self, token, chat_id, answer_fn, command_fn=None, callback_fn=None,
                 download_dir=None, commands=None, precheck_fn=None, event_fn=None,
                 giau_trang_thai=False, stt_fn=None, **_ignored):
        self.token = str(token or "").strip()
        if self.token.lower().startswith("bot "):
            self.token = self.token[4:].strip()
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
        self.bot_id = ""
        self.bot_username = ""
        self.loi_danh_tinh = ""
        self.doc_moi_tin_nhom = False
        self._seen = set()
        self._seen_order = deque()
        self._reply_to = {}           # channel -> message id to reply to (server channels only)
        self._bot_msgs = deque(maxlen=500)   # ids of messages the bot sent, for "reply to bot"
        self._dm = {}                 # user id -> DM channel id
        # Gateway session, for RESUME.
        self._seq = None
        self._session_id = ""
        self._resume_url = ""
        self._acked = True

    # ---- HTTP -------------------------------------------------------------------------
    def _headers(self) -> dict:
        return {"Authorization": f"Bot {self.token}",
                "User-Agent": "DiscordBot (https://github.com/blogminhquy/javis-os, 1.0)"}

    async def _api(self, client, method, path, **kw):
        """One REST call. Returns (status, json-or-{}). A 429 waits the time Discord asks for
        and retries once; network errors come back as status 0."""
        for attempt in range(2):
            try:
                r = await client.request(method, API + path, headers=self._headers(), **kw)
            except Exception as e:
                return 0, {"message": f"{type(e).__name__}: {e}"}
            if r.status_code == 429 and attempt == 0:
                try:
                    wait = float((r.json() or {}).get("retry_after") or 1)
                except Exception:
                    wait = 1.0
                await asyncio.sleep(min(wait, 10))
                continue
            try:
                body = r.json() if r.content else {}
            except Exception:
                body = {}
            return r.status_code, (body if isinstance(body, (dict, list)) else {})
        return 429, {"message": "rate limited"}

    async def _post_message(self, client, channel, text, reply_to=None):
        payload = {"content": text, "allowed_mentions": {"parse": []}}
        if reply_to:
            payload["message_reference"] = {"message_id": reply_to, "fail_if_not_exists": False}
        st, d = await self._api(client, "POST", f"/channels/{channel}/messages", json=payload)
        if st in (200, 201) and isinstance(d, dict) and d.get("id"):
            self._bot_msgs.append(str(d["id"]))
        return st, d

    async def _dm_channel(self, client, user_id) -> str:
        uid = str(user_id or "")
        if uid in self._dm:
            return self._dm[uid]
        st, d = await self._api(client, "POST", "/users/@me/channels", json={"recipient_id": uid})
        cid = str((d or {}).get("id") or "") if st in (200, 201) else ""
        if cid:
            self._dm[uid] = cid
        return cid

    async def _send(self, client, chat, text, reply_markup=None):
        """Send an answer split into chunks. `reply_markup` is accepted and ignored so
        `bot_gateway._dispatch` can call every channel the same way."""
        if not str(text or "").strip() and self.giau_trang_thai:
            return
        text = text or localefmt.chu("(không có nội dung)", "(no content)")
        reply_to = self._reply_to.get(chat)
        for i, chunk in enumerate(_chunks(text)):
            st, d = await self._post_message(client, chat, chunk, reply_to if i == 0 else None)
            if st not in (200, 201):
                print(f"[discord send] HTTP {st} {str((d or {}).get('message'))[:200]}", file=sys.stderr)

    async def send_text(self, chat, text):
        """Send ONE message outside a turn (background results, the test button). `chat` is a
        channel id from a turn, or a user id from the allow-list (opened as a DM). Returns
        (ok, error)."""
        text = str(text or "").strip()
        if not text:
            return False, "empty message"
        if not self.token:
            return False, localefmt.chu("thiếu bot token Discord", "missing Discord bot token")
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            target = str(chat or "")
            st, d = await self._post_message(client, target, _chunks(text)[0])
            if st == 404 or (st in (400, 403) and isinstance(d, dict) and d.get("code") in (10003, 50001)):
                # Not a channel this bot can post in: treat the id as a USER and open a DM.
                dm = await self._dm_channel(client, target)
                if not dm:
                    return False, localefmt.chu(
                        "không mở được tin nhắn riêng với người này (họ phải chung ít nhất một server "
                        "với bot, và không chặn tin nhắn riêng)",
                        "could not open a DM with this user (they must share a server with the bot "
                        "and allow direct messages)")
                target = dm
                st, d = await self._post_message(client, target, _chunks(text)[0])
            if st not in (200, 201):
                return False, _explain(st, d)
            for chunk in _chunks(text)[1:]:
                st, d = await self._post_message(client, target, chunk)
                if st not in (200, 201):
                    return False, _explain(st, d)
        return True, ""

    async def send_file(self, path, caption="", chat=None):
        """Upload a file as an attachment (multipart). Returns (ok, error)."""
        chat = chat or (self.chat_ids[0] if self.chat_ids else "")
        if not chat:
            return False, "no channel to send to"
        p = Path(str(path))
        try:
            if not p.is_file():
                return False, f"file not found: {path}"
            if p.stat().st_size > MAX_UPLOAD_MB * 1024 * 1024:
                return False, localefmt.chu(f"file lớn hơn {MAX_UPLOAD_MB}MB, Discord không nhận",
                                            f"file over {MAX_UPLOAD_MB}MB, Discord refuses it")
            data = p.read_bytes()
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"
        payload = {"content": str(caption or "")[:MAX_MSG], "allowed_mentions": {"parse": []},
                   "attachments": [{"id": 0, "filename": p.name}]}
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as c:
            st, d = await self._api(c, "POST", f"/channels/{chat}/messages",
                                    data={"payload_json": json.dumps(payload)},
                                    files={"files[0]": (p.name, data)})
        if st not in (200, 201):
            return False, _explain(st, d)
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

    def _is_mentioned(self, m) -> bool:
        if not self.bot_id:
            return False
        if any(str((u or {}).get("id")) == self.bot_id for u in (m.get("mentions") or [])):
            return True
        return self.bot_id in _RE_MENTION.findall(str(m.get("content") or ""))

    def _strip_mention(self, text) -> str:
        if not self.bot_id:
            return str(text or "").strip()
        return re.sub(rf"<@!?{re.escape(self.bot_id)}>", "", str(text or "")).strip()

    def _build_meta(self, m) -> dict:
        a = m.get("author") or {}
        private = not m.get("guild_id")
        name = str(a.get("global_name") or a.get("username") or "")
        ref = (m.get("message_reference") or {}).get("message_id")
        return {
            "platform": "discord",
            "chat_id": str(m.get("channel_id") or ""),
            "chat_type": "private" if private else "group",
            "chat_title": "",
            "user_name": name,
            "username": str(a.get("username") or ""),
            "user_id": str(a.get("id") or ""),
            "message_id": str(m.get("id") or ""),
            "bot_username": self.bot_username,
            "mentioned": self._is_mentioned(m),
            "reply_to_bot": bool(ref) and str(ref) in self._bot_msgs,
        }

    async def _ingest_files(self, client, m, meta) -> str:
        """Download attachments the user sent; voice messages go through speech-to-text."""
        notes = []
        for f in (m.get("attachments") or [])[:4]:
            name = str(f.get("filename") or "file")
            url = f.get("url")
            mime = str(f.get("content_type") or "")
            size = int(f.get("size") or 0)
            if not url:
                continue
            if size > MAX_DOWNLOAD_MB * 1024 * 1024:
                notes.append(f"[{name}: > {MAX_DOWNLOAD_MB}MB, not downloaded]")
                continue
            try:
                r = await client.get(url, timeout=httpx.Timeout(180.0), follow_redirects=True)
                r.raise_for_status()
                data = r.content
            except Exception as e:
                notes.append(f"[{name}: download failed, {type(e).__name__}]")
                continue
            if mime.startswith("audio/") or f.get("duration_secs") is not None:
                if not self.stt_fn:
                    notes.append(stt.loi_thanh_dong("thieu_key"))
                    continue
                try:
                    kq = await self.stt_fn(data, name)
                except Exception as e:
                    kq = {"ok": False, "noi_voi_javis": stt.loi_thanh_dong("loi", f"{type(e).__name__}: {e}")}
                notes.append(stt.khoi_thoai(kq.get("text"), "Discord") if (kq or {}).get("ok")
                             else ((kq or {}).get("noi_voi_javis") or stt.loi_thanh_dong("loi")))
                continue
            chat = meta.get("chat_id", "")
            ddir = self.download_dir(chat) if callable(self.download_dir) else self.download_dir
            d = Path(ddir) if ddir else Path("discord-inbox")
            d.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", f"discord_{int(time.time())}_{name}")
            dest = d / safe
            dest.write_bytes(data)
            notes.append(localefmt.chu(f"[Người dùng gửi file qua Discord, đã tải về: {dest}]",
                                       f"[The user sent a file on Discord, downloaded to: {dest}]"))
        return "\n".join(notes)

    async def _on_message(self, client, m):
        a = m.get("author") or {}
        if a.get("bot") or str(a.get("id") or "") == self.bot_id:
            return
        # Only ordinary messages (0) and replies (19) are turns; joins, pins, threads are not.
        if int(m.get("type") or 0) not in (0, 19):
            return
        chat = str(m.get("channel_id") or "")
        if not chat or self._seen_before(str(m.get("id") or "")):
            return
        meta = self._build_meta(m)
        if meta["chat_type"] != "private" and not (meta["mentioned"] or meta["reply_to_bot"]):
            if not self.giau_trang_thai:
                return       # people talking to each other in a server channel
        if self.chat_ids and meta["user_id"] not in self.chat_ids and chat not in self.chat_ids:
            await self._send(client, chat, localefmt.chu(
                "Bạn không có quyền dùng bot Javis này.", "You are not allowed to use this Javis bot."))
            return
        text = self._strip_mention(m.get("content"))
        # Discord owns "/" for registered slash commands, so "!stop", "!new"... stand in for the
        # bot commands the other channels type with a slash (same rule as Slack).
        if text.startswith("!") and len(text) > 1 and text[1].isalpha():
            text = "/" + text[1:]
        if m.get("attachments"):
            extra = await self._ingest_files(client, m, meta)
            text = (text + "\n" + extra).strip() if extra else text
        if not text:
            return
        self._reply_to[chat] = meta["message_id"] if meta["chat_type"] != "private" else None
        await self._dispatch(client, chat, text, meta)

    # ---- One turn ---------------------------------------------------------------------
    async def _typing_loop(self, client, chat):
        try:
            while True:
                await self._api(client, "POST", f"/channels/{chat}/typing")
                await asyncio.sleep(TYPING_EVERY)
        except asyncio.CancelledError:
            pass

    async def _handle_turn(self, client, chat, text, meta=None):
        files = []
        tools = []
        t0 = time.monotonic()
        typing = asyncio.create_task(self._typing_loop(client, chat))

        async def progress(txt):
            name = ten_tool(txt)
            if name and name not in tools:
                tools.append(name)

        try:
            reply = await self.answer_fn(text, meta, progress)
        except asyncio.CancelledError:
            typing.cancel()
            return
        except Exception as e:
            print(f"[discord turn failed] {type(e).__name__}: {e}", file=sys.stderr)
            from telegram_bot import CAU_LOI_NGUOI_THAT
            reply = (CAU_LOI_NGUOI_THAT if self.giau_trang_thai else f"⚠ {type(e).__name__}: {e}")
        finally:
            typing.cancel()
        silent = False
        if isinstance(reply, dict):
            files = reply.get("files") or []
            silent = bool(reply.get("im_lang"))
            reply = reply.get("text") or ""
        if silent and not str(reply or "").strip() and not files:
            return
        if tools and not self.giau_trang_thai:
            # The tool trail, proof of what Javis touched, as a small line above the answer.
            reply = f"-# {dong_vet(tools, time.monotonic() - t0)}\n{reply}"
        if str(reply or "").strip() or not files:
            await self._send(client, chat, reply)
        for f in files:
            fpath, fcap = (f.get("path"), f.get("caption", "")) if isinstance(f, dict) else (f, "")
            ok, err = await self.send_file(fpath, fcap, chat=chat)
            if not ok:
                print(f"[discord send file] {fpath}: {err}", file=sys.stderr)
                if not self.giau_trang_thai:
                    await self._send(client, chat, f"⚠ {Path(str(fpath)).name}: {err}")

    # ---- Gateway loop -----------------------------------------------------------------
    async def _whoami(self, client) -> bool:
        st, d = await self._api(client, "GET", "/users/@me")
        if st == 200 and isinstance(d, dict) and d.get("id"):
            self.bot_id = str(d["id"])
            self.bot_username = str(d.get("username") or "")
            self.loi_danh_tinh = ""
            return True
        self.loi_danh_tinh = (localefmt.chu("Discord từ chối bot token (token sai hoặc đã đổi).",
                                            "Discord rejected the bot token (wrong or regenerated token).")
                              if st == 401 else _explain(st, d))
        return False

    async def _gateway_url(self, client) -> str:
        st, d = await self._api(client, "GET", "/gateway/bot")
        if st == 200 and isinstance(d, dict) and d.get("url"):
            return str(d["url"])
        raise RuntimeError(_explain(st, d))

    async def _heartbeat(self, ws, interval_s: float):
        try:
            await asyncio.sleep(interval_s * random.random())
            while True:
                if not self._acked:
                    # The last beat was never acknowledged: the socket is a zombie.
                    await ws.close(code=4000)
                    return
                self._acked = False
                await ws.send(json.dumps({"op": 1, "d": self._seq}))
                await asyncio.sleep(interval_s)
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    def _identify(self) -> dict:
        return {"op": 2, "d": {"token": self.token, "intents": INTENTS,
                               "properties": {"os": sys.platform, "browser": "javis", "device": "javis"}}}

    def _resume(self) -> dict:
        return {"op": 6, "d": {"token": self.token, "session_id": self._session_id, "seq": self._seq}}

    async def _session(self, client, url: str):
        """One Gateway connection, until it closes. Raises on close so the loop reconnects."""
        import websockets
        hb = None
        code = None
        async with websockets.connect(url + GATEWAY_QS, max_size=16 * 1024 * 1024,
                                      ping_interval=None) as ws:
            try:
                async for raw in _frames(ws):
                    if self._stop:
                        break
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue
                    op = msg.get("op")
                    if msg.get("s") is not None:
                        self._seq = msg["s"]
                    if op == 10:                         # HELLO
                        self._acked = True
                        hb = asyncio.create_task(self._heartbeat(
                            ws, float((msg.get("d") or {}).get("heartbeat_interval") or 41250) / 1000))
                        await ws.send(json.dumps(self._resume() if self._session_id else self._identify()))
                    elif op == 11:                       # HEARTBEAT ACK
                        self._acked = True
                    elif op == 1:                        # server asks for a beat now
                        await ws.send(json.dumps({"op": 1, "d": self._seq}))
                    elif op == 7:                        # RECONNECT: resume on a fresh socket
                        await ws.close(code=4000)
                        break
                    elif op == 9:                        # INVALID SESSION
                        if not msg.get("d"):
                            self._session_id, self._seq, self._resume_url = "", None, ""
                        await asyncio.sleep(1 + random.random() * 4)
                        await ws.send(json.dumps(self._resume() if self._session_id else self._identify()))
                    elif op == 0:
                        t = msg.get("t")
                        d = msg.get("d") or {}
                        if t == "READY":
                            self._session_id = str(d.get("session_id") or "")
                            self._resume_url = str(d.get("resume_gateway_url") or "")
                            u = d.get("user") or {}
                            self.bot_id = str(u.get("id") or self.bot_id)
                            self.bot_username = str(u.get("username") or self.bot_username)
                            self.status = "polling"
                            self.last_error = ""
                            print(f"[discord] connected as @{self.bot_username}", file=sys.stderr)
                        elif t == "RESUMED":
                            self.status = "polling"
                            self.last_error = ""
                        elif t == "MESSAGE_CREATE":
                            asyncio.create_task(self._safe_message(client, d))
            finally:
                if hb:
                    hb.cancel()
            code = ws.close_code
        if code in _FATAL_CLOSE:
            raise _Fatal(localefmt.chu(*_FATAL_CLOSE[code]))
        if code in (4007, 4009):     # bad sequence / session timed out: start a new session
            self._session_id, self._seq, self._resume_url = "", None, ""

    async def _loop(self):
        backoff = 2
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            if not self.token:
                self.status = "error"
                self.last_error = localefmt.chu("Chưa có bot token Discord.", "No Discord bot token yet.")
                return
            if not await self._whoami(client):
                self.status = "error"
                self.last_error = self.loi_danh_tinh
                return
            while not self._stop:
                try:
                    url = self._resume_url if self._session_id and self._resume_url else await self._gateway_url(client)
                    await self._session(client, url)
                    backoff = 2
                except asyncio.CancelledError:
                    raise
                except _Fatal as e:
                    self.status = "error"
                    self.last_error = str(e)
                    print(f"[discord] {e}", file=sys.stderr)
                    return
                except Exception as e:
                    msg = f"{type(e).__name__}: {e}"
                    if self._stop:
                        break
                    self.status = "error"
                    self.last_error = msg[:300]
                    print(f"[discord gateway] {msg[:300]}", file=sys.stderr)
                if self._stop:
                    break
                await asyncio.sleep(backoff)
                backoff = min(RECONNECT_MAX, backoff * 2)
        print("[discord] stopped", file=sys.stderr)

    async def _safe_message(self, client, m):
        try:
            await self._on_message(client, m)
        except Exception as e:
            print(f"[discord message] {type(e).__name__}: {e}", file=sys.stderr)

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


class _Fatal(Exception):
    """A close the owner has to fix (bad token, missing intent): stop instead of retrying."""


async def _frames(ws):
    """Iterate a socket's messages and end QUIETLY on any close. websockets raises
    ConnectionClosedError for codes like 4004; the caller reads `ws.close_code` afterwards, so one
    path handles a clean close and an error close alike."""
    import websockets
    try:
        async for raw in ws:
            yield raw
    except websockets.exceptions.ConnectionClosed:
        return


# Discord JSON error codes the owner can act on, in words.
_ERRORS = {
    10003: ("không tìm thấy kênh", "unknown channel"),
    10013: ("không tìm thấy người dùng", "unknown user"),
    50001: ("bot không có quyền vào kênh này", "the bot has no access to this channel"),
    50007: ("người này chặn tin nhắn riêng từ bot", "this user does not accept DMs from the bot"),
    50013: ("bot thiếu quyền (Send Messages / Attach Files) trong kênh này",
            "the bot lacks a permission (Send Messages / Attach Files) in this channel"),
}


def _explain(status, body) -> str:
    body = body if isinstance(body, dict) else {}
    code = body.get("code")
    if code in _ERRORS:
        vi, en = _ERRORS[code]
        return localefmt.chu(f"{vi} ({code})", f"{en} ({code})")
    if status == 401:
        return localefmt.chu("token Discord không hợp lệ (401)", "invalid Discord token (401)")
    msg = str(body.get("message") or "")[:200]
    return f"HTTP {status}" + (f": {msg}" if msg else "")
