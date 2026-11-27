"""Slack gateway over Socket Mode (0.71.0).

Why Socket Mode instead of the Events API webhook: Socket Mode makes Javis open the connection
OUT to Slack over a WebSocket, so it works on a laptop or behind NAT with no public URL, the
same way Telegram and Zalo long-polling do. The Events API would need a public HTTPS endpoint
and a signing secret for every install.

Two tokens, both from the same Slack app:
  - bot token `xoxb-...`: everything the bot says and reads (chat.postMessage, auth.test, files).
  - app-level token `xapp-...` with the `connections:write` scope: only to open the socket.

The class keeps the transport contract of `TelegramBot` / `ZaloBot` (see `bot_gateway`), so the
owner's control channel in main.py and the dedicated customer bots in `chatbot_runtime` drive it
without knowing which platform they hold.

Differences from Telegram that change behaviour, not just names:
  1. Every inbound envelope must be ACKed within 3 seconds or Slack redelivers it. The ack goes
     out before any work starts, and `_seen` drops redeliveries anyway.
  2. A mention in a channel arrives twice (`message` and `app_mention`) when the app subscribes
     to both. Dedupe is per (channel, ts), not per event id.
  3. In channels the bot only answers when mentioned or inside a thread it already replied in;
     in DMs it answers everything. Replies to a channel message go into its thread so the bot
     never floods a busy channel.
  4. No typing indicator exists for bots. The owner sees one status message that is edited as
     tools run, then becomes the tool-trail line; customer bots show nothing.
  5. Slack's markup is mrkdwn, not Markdown: `*bold*`, `_italic_`, `<url|text>`. `md_to_mrkdwn`
     converts the common cases; anything it misses still reads fine as plain text. Slack also
     escapes `&`, `<`, `>` in both directions: outbound text escapes them (a raw `<` would be read
     as a control sequence), inbound text is decoded by `inbound_text` so the model reads `a < b`,
     `@Kim` and `#sales` instead of `a &lt; b`, `<@U123>` and `<#C123|sales>`.

Audit of 2026-11-20 (parity with Telegram, Discord and Lark):
  - Each turn answers into the thread of ITS message (`meta["thread_ts"]`). A per-chat slot was
    overwritten by any newer message in another thread of the same channel, so a running answer
    could land in the wrong thread.
  - "Inside a thread the bot already replied in" survives a restart: an unknown thread is checked
    once with conversations.replies, so customers continuing an old thread are not ignored.
  - Channels have a name (`chat_title`, conversations.info) in the bot inbox and the group list,
    and the bot reports being added to or removed from a channel, like Telegram does.
  - A rate-limited call (HTTP 429) waits for Retry-After and tries again instead of dropping the
    answer.
  Scopes added for these (channels:read, groups:read, mpim:*) are optional: an app installed from
  the older manifest keeps working and simply has no channel names or join/leave events.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from collections import deque
from pathlib import Path

import httpx

import localefmt
import stt
from bot_gateway import HangLuot, dong_vet, parse_chat_ids, ten_tool, trace_wanted

SLACK_API = "https://slack.com/api/{method}"

# Slack accepts 40k characters per message, but a wall of text in a chat is unreadable and
# long messages get collapsed behind "Show more". Split at a size people actually read.
MAX_MSG = 3900
MAX_DEDUPE = 2000
MAX_DOWNLOAD_MB = 20
STATUS_EDIT_EVERY = 2.5     # seconds between edits of the owner's status message
RECONNECT_MAX = 60          # cap of the reconnect back-off, seconds

_RE_MENTION = re.compile(r"<@([A-Z0-9]+)(?:\|[^>]*)?>")
MAX_CACHE = 500             # names and thread checks kept per bot
RATE_LIMIT_RETRIES = 2
RATE_LIMIT_MAX_WAIT = 30    # seconds; a longer Retry-After is not worth holding a reply for


def split_tokens(raw) -> tuple:
    """"xoxb-... xapp-..." (any order, any whitespace or comma) -> (bot_token, app_token).

    One string because the channel-account store keeps exactly one encrypted secret per
    account; both tokens are secrets, so they travel together in that one field.
    """
    bot, app = "", ""
    for part in re.split(r"[\s,;]+", str(raw or "").strip()):
        if part.startswith("xoxb-"):
            bot = part
        elif part.startswith("xapp-"):
            app = part
    return bot, app


def escape(text: str) -> str:
    """Slack's three control characters. `>` at the start of a line stays raw: it is a quote."""
    t = str(text or "").replace("&", "&amp;").replace("<", "&lt;")
    return re.sub(r"(?<!^)(?<!\n)>", "&gt;", t)


def md_to_mrkdwn(text: str) -> str:
    """Markdown as the engines write it -> Slack mrkdwn. Code blocks keep their content (only
    escaped, as Slack requires everywhere)."""
    parts = re.split(r"(```.*?```)", str(text or ""), flags=re.S)
    out = []
    for i, p in enumerate(parts):
        if i % 2 == 1:
            out.append(escape(p))
            continue
        p = escape(p)
        p = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r"\1", p)                 # images: keep the alt
        p = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"<\2|\1>", p)   # links
        p = re.sub(r"^#{1,6}\s+(.+?)\s*#*$", r"*\1*", p, flags=re.M)       # headings -> bold
        p = re.sub(r"\*\*(.+?)\*\*", r"*\1*", p)                           # **bold** -> *bold*
        p = re.sub(r"__(.+?)__", r"*\1*", p)
        p = re.sub(r"~~(.+?)~~", r"~\1~", p)
        out.append(p)
    return "".join(out)


_RE_ANGLE = re.compile(r"<([^<>\n]+)>")


def inbound_text(text: str, names=None) -> str:
    """Slack's wire format -> what a person typed. `names` maps user id -> display name.

    `<@U1>` -> `@Kim`, `<#C1|sales>` -> `#sales`, `<!here>` -> `@here`, `<url|label>` ->
    `label (url)`, `<url>` -> `url`, then `&lt; &gt; &amp;` back to `< > &`."""
    names = names or {}

    def _one(m):
        body = m.group(1)
        ref, _, label = body.partition("|")
        if ref.startswith("@"):
            return "@" + (label or names.get(ref[1:]) or ref[1:])
        if ref.startswith("#"):
            return "#" + (label or ref[1:])
        if ref.startswith("!"):
            if ref.startswith("!subteam^"):
                return label or "@team"
            return "@" + (label or ref[1:].split("^")[0])
        if ref.startswith("mailto:"):
            return label or ref[7:]
        if label and label != ref and label != re.sub(r"^https?://", "", ref):
            return f"{label} ({ref})"
        return ref

    t = _RE_ANGLE.sub(_one, str(text or ""))
    return t.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def _chunks(text: str, size: int = MAX_MSG) -> list:
    """Split on paragraph or line breaks when possible, so a message never ends mid-word."""
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


class SlackBot(HangLuot):
    """Same contract as `TelegramBot`: start(), stop(), status, last_error, _task, send_text,
    send_file, plus the attributes `bot_gateway.HangLuot` needs."""

    def __init__(self, token, chat_id, answer_fn, command_fn=None, callback_fn=None,
                 download_dir=None, commands=None, precheck_fn=None, event_fn=None,
                 giau_trang_thai=False, stt_fn=None, **_ignored):
        self.token, self.app_token = split_tokens(token)
        self.giau_trang_thai = bool(giau_trang_thai)
        self.chat_ids = parse_chat_ids(chat_id)
        self.commands = list(commands or [])
        self.answer_fn = answer_fn
        self.command_fn = command_fn
        self.callback_fn = None       # interactive buttons would need an Interactivity URL
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
        self.bot_id = ""              # the bot's USER id (U...), what mentions point at
        self.bot_username = ""
        self.team = ""
        self.loi_danh_tinh = ""
        self.doc_moi_tin_nhom = False
        self._seen = set()
        self._seen_order = deque()
        self._thread = {}             # chat -> thread_ts to reply into
        self._threads_joined = set()  # (chat, thread_ts) the bot has replied in
        self._names = {}              # user id -> display name cache
        self._channel_names = {}      # channel id -> "#name" ("" when unknown or a DM)
        self._thread_checked = {}     # (chat, thread_ts) -> the bot has a reply in it

    # ---- HTTP -------------------------------------------------------------------------
    async def _request(self, client, method, token=None, json_body=None, form=None):
        """POST one Web API method. Always returns a dict; network errors become
        `{"ok": False, "error": ..., "net_error": True}` so callers handle one shape.

        HTTP 429 (Slack's rate limit, about one message per second per channel) waits for
        Retry-After and tries again: before, a burst of chunks or a busy channel lost the rest of
        the answer with only a log line."""
        headers = {"Authorization": f"Bearer {token or self.token}"}
        if json_body is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
        for attempt in range(RATE_LIMIT_RETRIES + 1):
            try:
                if json_body is not None:
                    r = await client.post(SLACK_API.format(method=method), json=json_body, headers=headers)
                else:
                    r = await client.post(SLACK_API.format(method=method), data=form or {}, headers=headers)
            except Exception as e:
                return {"ok": False, "error": f"{type(e).__name__}: {e}", "net_error": True}
            if r.status_code == 429 and attempt < RATE_LIMIT_RETRIES:
                try:
                    wait = int(r.headers.get("Retry-After") or 1)
                except (TypeError, ValueError):
                    wait = 1
                await asyncio.sleep(max(1, min(wait, RATE_LIMIT_MAX_WAIT)))
                continue
            try:
                return r.json() or {}
            except Exception:
                return {"ok": False, "error": "ratelimited" if r.status_code == 429 else f"HTTP {r.status_code}"}
        return {"ok": False, "error": "ratelimited"}

    async def _api(self, client, method, token=None, **payload):
        """Call a Web API method with a JSON body."""
        return await self._request(client, method, token=token, json_body=payload or {})

    async def _api_form(self, client, method, **data):
        """A few methods (users.info, conversations.*, files.getUploadURLExternal) only take form fields."""
        return await self._request(client, method, form=data)

    async def _post(self, client, chat, text, thread_ts=None):
        payload = {"channel": chat, "text": md_to_mrkdwn(text), "unfurl_links": False}
        if thread_ts:
            payload["thread_ts"] = thread_ts
        return await self._api(client, "chat.postMessage", **payload)

    async def _send(self, client, chat, text, reply_markup=None, thread_ts=None):
        """Send an answer, split into readable chunks. `reply_markup` is accepted and ignored
        so `bot_gateway._dispatch` can call every channel the same way. `thread_ts` is the thread
        of the turn being answered; without it, the thread of the chat's latest message."""
        if not str(text or "").strip() and self.giau_trang_thai:
            return
        text = text or localefmt.chu("(không có nội dung)", "(no content)")
        thread = thread_ts or self._thread.get(chat)
        for chunk in _chunks(text):
            d = await self._post(client, chat, chunk, thread)
            if d.get("ok") and thread:
                self._threads_joined.add((chat, thread))
            if not d.get("ok"):
                print(f"[slack send] {str(d.get('error'))[:200]}", file=sys.stderr)

    async def send_text(self, chat, text):
        """Send ONE message outside a turn (reminders, owner replies from the inbox).
        Returns (ok, error). Opens its own client, so no running socket is needed."""
        text = str(text or "").strip()
        if not text:
            return False, "empty message"
        if not self.token:
            return False, localefmt.chu("thiếu bot token Slack (xoxb-...)", "missing Slack bot token (xoxb-...)")
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            for chunk in _chunks(text):
                d = await self._post(client, chat, chunk)
                if not d.get("ok"):
                    return False, _explain_error(d.get("error"))
        return True, ""

    async def send_file(self, path, caption="", chat=None, thread_ts=None):
        """Upload a file with the current Slack flow: getUploadURLExternal -> PUT the bytes ->
        completeUploadExternal (files.upload was retired in 2025). Returns (ok, error)."""
        chat = chat or (self.chat_ids[0] if self.chat_ids else "")
        if not chat:
            return False, "no channel to send to"
        p = Path(str(path))
        try:
            if not p.is_file():
                return False, f"file not found: {path}"
            data = p.read_bytes()
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as c:
            d = await self._api_form(c, "files.getUploadURLExternal", filename=p.name,
                                     length=str(len(data)))
            if not d.get("ok"):
                return False, _explain_error(d.get("error"))
            try:
                up = await c.post(d["upload_url"], content=data)
                if up.status_code >= 300:
                    return False, f"upload HTTP {up.status_code}"
            except Exception as e:
                return False, f"{type(e).__name__}: {e}"
            payload = {"files": [{"id": d.get("file_id"), "title": p.name}], "channel_id": chat}
            if caption:
                payload["initial_comment"] = md_to_mrkdwn(str(caption))[:3000]
            thread = thread_ts or self._thread.get(chat)
            if thread:
                payload["thread_ts"] = thread
            d2 = await self._api(c, "files.completeUploadExternal", **payload)
            if not d2.get("ok"):
                return False, _explain_error(d2.get("error"))
        return True, ""

    # ---- Identity ---------------------------------------------------------------------
    async def _whoami(self, client) -> bool:
        d = await self._api(client, "auth.test")
        if d.get("ok"):
            self.bot_id = str(d.get("user_id") or "")
            self.bot_username = str(d.get("user") or "")
            self.team = str(d.get("team") or "")
            self.loi_danh_tinh = ""
            return True
        self.loi_danh_tinh = localefmt.chu(
            f"Slack từ chối bot token ({_explain_error(d.get('error'))}).",
            f"Slack refused the bot token ({_explain_error(d.get('error'))}).")
        return False

    async def _display_name(self, client, uid) -> str:
        uid = str(uid or "")
        if not uid:
            return ""
        if uid in self._names:
            return self._names[uid]
        d = await self._api_form(client, "users.info", user=uid)
        prof = ((d.get("user") or {}).get("profile") or {})
        name = (prof.get("display_name") or prof.get("real_name")
                or (d.get("user") or {}).get("name") or "")
        if len(self._names) > MAX_CACHE:
            self._names.clear()
        self._names[uid] = str(name)
        return self._names[uid]

    async def _channel_name(self, client, chat) -> str:
        """"#sales" for a channel, "" for a DM or when the app lacks channels:read/groups:read
        (an app made from the pre-2026-11-20 manifest). Cached, failures included, so a missing
        scope costs one call per channel, not one per message."""
        chat = str(chat or "")
        if not chat or chat.startswith("D"):
            return ""
        if chat in self._channel_names:
            return self._channel_names[chat]
        d = await self._api_form(client, "conversations.info", channel=chat)
        ch = d.get("channel") or {}
        name = ""
        # A group DM's name is machine-made ("mpdm-kim--an-1"): leave it out, the inbox shows people.
        if d.get("ok") and ch.get("name") and not ch.get("is_im") and not ch.get("is_mpim"):
            name = "#" + str(ch["name"])
        if len(self._channel_names) > MAX_CACHE:
            self._channel_names.clear()
        if d.get("ok") or not d.get("net_error"):
            self._channel_names[chat] = name
        return name

    async def _bot_in_thread(self, client, chat, thread) -> bool:
        """Has the bot replied inside this thread? Known threads answer from memory; an unknown
        one (the bot restarted since, or the thread is older) is read once with
        conversations.replies, so "continue a thread the bot answered" works after a restart."""
        key = (str(chat or ""), str(thread or ""))
        if not all(key):
            return False
        if key in self._threads_joined:
            return True
        if key in self._thread_checked:
            return self._thread_checked[key]
        d = await self._api_form(client, "conversations.replies", channel=key[0], ts=key[1], limit="200")
        found = bool(self.bot_id) and any(str(m.get("user") or "") == self.bot_id
                                          for m in (d.get("messages") or []))
        if found:
            self._threads_joined.add(key)
        if len(self._thread_checked) > MAX_CACHE:
            self._thread_checked.clear()
        if not d.get("net_error"):
            self._thread_checked[key] = found
        return found

    async def _inbound(self, client, text) -> str:
        """Message text as the person meant it (see `inbound_text`), other people's mentions by name."""
        names = {}
        for uid in set(_RE_MENTION.findall(str(text or ""))):
            if uid != self.bot_id:
                names[uid] = await self._display_name(client, uid)
        return inbound_text(text, names)

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

    def _is_mentioned(self, ev) -> bool:
        if ev.get("type") == "app_mention":
            return True
        return bool(self.bot_id) and self.bot_id in _RE_MENTION.findall(str(ev.get("text") or ""))

    def _strip_mention(self, text) -> str:
        if not self.bot_id:
            return str(text or "").strip()
        return re.sub(rf"<@{re.escape(self.bot_id)}(?:\|[^>]*)?>", "", str(text or "")).strip()

    async def _build_meta(self, client, ev) -> dict:
        ctype = str(ev.get("channel_type") or "")
        chat = str(ev.get("channel") or "")
        private = ctype == "im" or chat.startswith("D")
        uid = str(ev.get("user") or "")
        name = await self._display_name(client, uid)
        thread = str(ev.get("thread_ts") or "")
        mentioned = self._is_mentioned(ev)
        in_thread = False
        if thread and not private:
            in_thread = (chat, thread) in self._threads_joined
            if not in_thread and not mentioned:
                in_thread = await self._bot_in_thread(client, chat, thread)
        return {
            "platform": "slack",
            "chat_id": chat,
            "chat_type": "private" if private else "group",
            "chat_title": "" if private else await self._channel_name(client, chat),
            "user_name": name,
            "username": name,
            "user_id": uid,
            "message_id": str(ev.get("ts") or ""),
            "bot_username": self.bot_username,
            "mentioned": mentioned,
            "reply_to_bot": in_thread,
        }

    async def _ingest_files(self, client, ev, meta) -> str:
        """Download files the user attached; voice clips go through speech-to-text."""
        notes = []
        for f in (ev.get("files") or [])[:4]:
            name = str(f.get("name") or f.get("title") or "file")
            url = f.get("url_private_download") or f.get("url_private")
            mime = str(f.get("mimetype") or "")
            size = int(f.get("size") or 0)
            if not url:
                continue
            if size > MAX_DOWNLOAD_MB * 1024 * 1024:
                notes.append(f"[{name}: > {MAX_DOWNLOAD_MB}MB, not downloaded]")
                continue
            try:
                r = await client.get(url, headers={"Authorization": f"Bearer {self.token}"},
                                     timeout=httpx.Timeout(180.0), follow_redirects=True)
                r.raise_for_status()
                data = r.content
            except Exception as e:
                notes.append(f"[{name}: download failed, {type(e).__name__}]")
                continue
            if mime.startswith("audio/") or f.get("subtype") == "slack_audio":
                if not self.stt_fn:
                    notes.append(stt.loi_thanh_dong("thieu_key"))
                    continue
                try:
                    kq = await self.stt_fn(data, name)
                except Exception as e:
                    kq = {"ok": False, "noi_voi_javis": stt.loi_thanh_dong("loi", f"{type(e).__name__}: {e}")}
                notes.append(stt.khoi_thoai(kq.get("text"), "Slack") if (kq or {}).get("ok")
                             else ((kq or {}).get("noi_voi_javis") or stt.loi_thanh_dong("loi")))
                continue
            chat = meta.get("chat_id", "")
            ddir = self.download_dir(chat) if callable(self.download_dir) else self.download_dir
            d = Path(ddir) if ddir else Path("slack-inbox")
            d.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", f"slack_{int(time.time())}_{name}")
            dest = d / safe
            dest.write_bytes(data)
            notes.append(localefmt.chu(f"[Người dùng gửi file qua Slack, đã tải về: {dest}]",
                                       f"[The user sent a file on Slack, downloaded to: {dest}]"))
        return "\n".join(notes)

    async def _on_event(self, client, ev):
        etype = ev.get("type")
        if etype in ("member_joined_channel", "member_left_channel", "channel_left", "group_left"):
            await self._on_membership(client, ev)
            return
        if etype not in ("message", "app_mention"):
            return
        # Messages the bot itself posted, edits, deletes and joins all come through as
        # `message` with a subtype; only plain user messages (and file shares) are turns.
        if ev.get("bot_id") or ev.get("subtype") not in (None, "file_share", "thread_broadcast"):
            return
        if str(ev.get("user") or "") == self.bot_id:
            return
        chat = str(ev.get("channel") or "")
        if not chat or self._seen_before(f"{chat}:{ev.get('ts')}"):
            return
        meta = await self._build_meta(client, ev)
        if meta["chat_type"] != "private":
            await self._report_group(meta)
            # In a channel the bot speaks when called, or when the user continues a thread it
            # already answered. Everything else is people talking to each other.
            if not (meta["mentioned"] or meta["reply_to_bot"]):
                if not self.giau_trang_thai:
                    return
                # Customer bots decide for themselves (reply policy) whether to speak, so pass
                # the message on with the flags and let the precheck say no.
        if self.chat_ids and meta["user_id"] not in self.chat_ids and chat not in self.chat_ids:
            await self._send(client, chat, localefmt.chu(
                "Bạn không có quyền dùng bot Javis này.", "You are not allowed to use this Javis bot."))
            return
        text = await self._inbound(client, self._strip_mention(ev.get("text")))
        # Slack claims every message that starts with "/" as a slash command and refuses it
        # ("not a valid command") before Javis ever sees it. So "!stop", "!new"... stand in for
        # the bot commands the other channels type with a slash.
        if text.startswith("!") and len(text) > 1 and text[1].isalpha():
            text = "/" + text[1:]
        if ev.get("files"):
            extra = await self._ingest_files(client, ev, meta)
            text = (text + "\n" + extra).strip() if extra else text
        if not text:
            return
        thread = str(ev.get("thread_ts") or "")
        if meta["chat_type"] != "private":
            thread = thread or str(ev.get("ts") or "")
        self._thread[chat] = thread or None
        # The turn keeps ITS thread: `_thread[chat]` moves on as soon as someone writes in
        # another thread of the same channel, and the answer must not follow it there.
        meta["thread_ts"] = thread
        await self._dispatch(client, chat, text, meta)

    async def _report_group(self, meta, kind="thay_nhom"):
        if not self.event_fn:
            return
        try:
            await self.event_fn(kind, {"chat_id": meta.get("chat_id", ""),
                                       "chat_title": meta.get("chat_title", ""),
                                       "chat_type": meta.get("chat_type", ""), "chat_id_moi": ""})
        except Exception as e:
            print(f"[slack group event] {type(e).__name__}: {e}", file=sys.stderr)

    async def _on_membership(self, client, ev):
        """The bot was added to or removed from a channel (Telegram's `vao_nhom` / `roi_nhom`).
        Joining lists the channel on the Chatbot page right away, before anyone calls the bot;
        leaving clears it so the page stops offering a channel the bot is no longer in."""
        etype = ev.get("type")
        chat = str(ev.get("channel") or "")
        if not chat:
            return
        if etype in ("member_joined_channel", "member_left_channel"):
            if not self.bot_id or str(ev.get("user") or "") != self.bot_id:
                return      # someone else joined or left: not the bot's business
        kind = "vao_nhom" if etype == "member_joined_channel" else "roi_nhom"
        if kind == "roi_nhom":
            self._channel_names.pop(chat, None)
            self._threads_joined = {k for k in self._threads_joined if k[0] != chat}
            self._thread_checked = {k: v for k, v in self._thread_checked.items() if k[0] != chat}
            title = ""
        else:
            title = await self._channel_name(client, chat)
        await self._report_group({"chat_id": chat, "chat_title": title, "chat_type": "group"}, kind)

    # ---- One turn ---------------------------------------------------------------------
    async def _handle_turn(self, client, chat, text, meta=None):
        files = []
        tools = []
        t0 = time.monotonic()
        status_ts = None
        last_edit = 0.0
        thread = str((meta or {}).get("thread_ts") or "") or self._thread.get(chat)

        # Trail off (issue #1893): no status message at all, so nothing is left behind in the chat.
        if not self.giau_trang_thai and trace_wanted():
            d = await self._post(client, chat, localefmt.chu("⏳ Đang làm...", "⏳ Working..."), thread)
            status_ts = d.get("ts") if d.get("ok") else None

        async def progress(txt):
            nonlocal last_edit
            name = ten_tool(txt)
            if name and name not in tools:
                tools.append(name)
            if status_ts and time.monotonic() - last_edit > STATUS_EDIT_EVERY:
                last_edit = time.monotonic()
                await self._api(client, "chat.update", channel=chat, ts=status_ts,
                                text=("⏳ " + " · ".join(tools[-4:])) if tools else "⏳")

        try:
            reply = await self.answer_fn(text, meta, progress)
        except asyncio.CancelledError:
            if status_ts:
                await self._api(client, "chat.delete", channel=chat, ts=status_ts)
            return
        except Exception as e:
            print(f"[slack turn failed] {type(e).__name__}: {e}", file=sys.stderr)
            from telegram_bot import CAU_LOI_NGUOI_THAT
            reply = (CAU_LOI_NGUOI_THAT if self.giau_trang_thai else f"⚠ {type(e).__name__}: {e}")
        silent = False
        if isinstance(reply, dict):
            files = reply.get("files") or []
            silent = bool(reply.get("im_lang"))
            reply = reply.get("text") or ""
        if status_ts:
            # The status message becomes the tool trail: proof of what Javis touched, left in
            # the conversation the same way Telegram leaves it.
            await self._api(client, "chat.update", channel=chat, ts=status_ts,
                            text=escape(dong_vet(tools, time.monotonic() - t0)))
        if silent and not str(reply or "").strip() and not files:
            return
        if str(reply or "").strip() or not files:
            await self._send(client, chat, reply, thread_ts=thread)
        for f in files:
            fpath, fcap = (f.get("path"), f.get("caption", "")) if isinstance(f, dict) else (f, "")
            ok, err = await self.send_file(fpath, fcap, chat=chat, thread_ts=thread)
            if not ok:
                print(f"[slack send file] {fpath}: {err}", file=sys.stderr)
                if not self.giau_trang_thai:
                    await self._send(client, chat, f"⚠ {Path(str(fpath)).name}: {err}", thread_ts=thread)

    # ---- Socket Mode loop -------------------------------------------------------------
    async def _open_socket_url(self, client) -> str:
        d = await self._api(client, "apps.connections.open", token=self.app_token)
        if d.get("ok") and d.get("url"):
            return str(d["url"])
        raise RuntimeError(_explain_error(d.get("error")))

    async def _loop(self):
        import websockets
        backoff = 2
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            if not (self.token and self.app_token):
                self.status = "error"
                self.last_error = localefmt.chu(
                    "Cần đủ hai token: bot token (xoxb-...) và app token (xapp-...).",
                    "Both tokens are needed: the bot token (xoxb-...) and the app token (xapp-...).")
                return
            if not await self._whoami(client):
                self.status = "error"
                self.last_error = self.loi_danh_tinh
                return
            while not self._stop:
                try:
                    url = await self._open_socket_url(client)
                    async with websockets.connect(url, max_size=8 * 1024 * 1024,
                                                  ping_interval=30) as ws:
                        backoff = 2
                        async for raw in ws:
                            if self._stop:
                                break
                            try:
                                env = json.loads(raw)
                            except Exception:
                                continue
                            kind = env.get("type")
                            # Ack first: Slack redelivers anything not acked within 3 seconds,
                            # and an engine turn takes far longer than that.
                            if env.get("envelope_id"):
                                await ws.send(json.dumps({"envelope_id": env["envelope_id"]}))
                            if kind == "hello":
                                self.status = "polling"
                                self.last_error = ""
                                print(f"[slack] connected as @{self.bot_username} ({self.team})",
                                      file=sys.stderr)
                            elif kind == "disconnect":
                                break        # Slack rotates sockets; open a fresh one
                            elif kind == "events_api":
                                ev = ((env.get("payload") or {}).get("event") or {})
                                asyncio.create_task(self._safe_event(client, ev))
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    msg = f"{type(e).__name__}: {e}"
                    if self._stop:
                        break
                    self.status = "error"
                    self.last_error = msg[:300]
                    print(f"[slack socket] {msg[:300]}", file=sys.stderr)
                    await asyncio.sleep(backoff)
                    backoff = min(RECONNECT_MAX, backoff * 2)
        print("[slack] stopped", file=sys.stderr)

    async def _safe_event(self, client, ev):
        try:
            await self._on_event(client, ev)
        except Exception as e:
            print(f"[slack event] {type(e).__name__}: {e}", file=sys.stderr)

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


# Slack error codes the owner can act on, in words. Anything else is shown as the raw code.
_ERRORS = {
    "invalid_auth": ("token không hợp lệ", "invalid token"),
    "not_authed": ("thiếu token", "no token sent"),
    "account_inactive": ("app hoặc workspace đã bị gỡ", "the app or workspace was removed"),
    "token_revoked": ("token đã bị thu hồi", "the token was revoked"),
    "missing_scope": ("app thiếu quyền (scope), xem hướng dẫn cài app Slack",
                      "the app is missing a scope, see the Slack app setup guide"),
    "not_in_channel": ("bot chưa được mời vào kênh này (/invite @bot)",
                       "the bot is not in this channel (/invite @bot)"),
    "channel_not_found": ("không tìm thấy kênh, hoặc bot chưa được mời vào",
                          "channel not found, or the bot was not invited"),
    "ratelimited": ("Slack đang giới hạn tần suất, thử lại sau", "Slack is rate limiting, try again later"),
}


def _explain_error(code) -> str:
    code = str(code or "unknown_error")
    vi_en = _ERRORS.get(code)
    return localefmt.chu(f"{vi_en[0]} ({code})", f"{vi_en[1]} ({code})") if vi_en else code
