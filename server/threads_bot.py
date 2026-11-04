"""Threads (Meta) gateway, 0.448.0: replies under the owner's Threads posts land in the inbox and the bot can
answer them publicly. Same shape as `messenger_bot`: Threads POSTs every new reply to a webhook, Javis never polls
(owner, 2026-11-04: "anh không muốn làm kiểu vài phút hỏi 1 lần").

Two halves:
  - `ThreadsBot`: the transport, same contract as `TelegramBot` (start/stop/send_text/send_file). `start()` opens no
    connection; it checks the token, refreshes it when due and registers the bot under the Threads user id.
  - `handle_webhook(payload)`: called by `/threads/webhook` in main.py once the signature has been checked. It hands
    each `replies` notification to the bot registered for the account it is about.

What the platform allows, and so what this does:
  - Threads has NO private messages in its API. Only replies (comments) under the owner's posts are handled.
  - Every top-level reply under a post is its own conversation, keyed by that reply's id; a reply under a reply joins
    its parent's conversation. Javis answers with a reply to that id (create a TEXT container with `reply_to_id`,
    then publish it). A reply holds 500 characters; longer answers are split.
  - The bot's own replies come back on the webhook and are skipped, so it never answers itself.
  - Moderation: a reply can be hidden (`/manage_reply`), not deleted (only the author can delete their reply).
  - Tokens: the long-lived user token lasts 60 days and is refreshed (`th_refresh_token`) once it is a few weeks
    old, from the bot's own hourly loop, so a connected account does not die after two months.

Credentials of one account, as the channel-account store keeps them: "<threads user id> <access token> <app secret>".
The account meta carries `username`, `app_id`, `comments` ("off" / "inbox" / "reply") and `token_at` (when the token
was last issued or refreshed).
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import time
from collections import deque

import httpx

import localefmt
from bot_gateway import HangLuot, dong_vet, parse_chat_ids, ten_tool
from whatsapp_bot import verify_signature  # noqa: F401  - same Meta signature scheme, re-exported

GRAPH_HOST = os.getenv("JAVIS_THREADS_GRAPH", "https://graph.threads.net")
GRAPH = f"{GRAPH_HOST}/v1.0"
MAX_REPLY = 490               # Threads takes 500 characters per post
MAX_DEDUPE = 4000
COMMENT_MODES = ("off", "inbox", "reply")
COMMENT_MODE_DEFAULT = "inbox"
REPLIES_FIELD = "replies"
REFRESH_AFTER = 20 * 86400    # refresh a token once it is 20 days old (it lasts 60, Meta wants it at least a day old)

# Threads user id -> ThreadsBot running for it.
_REGISTRY: dict = {}


def registered() -> dict:
    return dict(_REGISTRY)


def split_credentials(raw) -> dict:
    """"<user id> <access token> <app secret>" -> its parts. Tolerates extra spaces and any order of the last two
    (the app secret is 32 hex characters, the token is longer)."""
    parts = [p for p in re.split(r"\s+", str(raw or "").strip()) if p]
    out = {"user_id": "", "access_token": "", "app_secret": ""}
    for p in parts:
        if p.isdigit() and not out["user_id"]:
            out["user_id"] = p
        elif re.fullmatch(r"[0-9a-fA-F]{32}", p) and not out["app_secret"]:
            out["app_secret"] = p
        elif not out["access_token"]:
            out["access_token"] = p
    return out


def join_credentials(user_id: str, token: str, app_secret: str) -> str:
    return f"{user_id} {token} {app_secret}"


def md_to_plain(text: str) -> str:
    import messenger_bot
    return messenger_bot.md_to_plain(text)


def _chunks(text: str, size: int = MAX_REPLY) -> list:
    text = str(text or "").strip()
    out = []
    while len(text) > size:
        cut = text.rfind("\n", 0, size)
        if cut < size // 2:
            cut = text.rfind(" ", 0, size)
        if cut < size // 2:
            cut = size
        out.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        out.append(text)
    return out


def comment_mode(account_id: str) -> str:
    try:
        import channel_accounts
        m = str(((channel_accounts.get_account(str(account_id or "")) or {}).get("meta") or {}).get("comments") or "")
    except Exception:
        m = ""
    return m if m in COMMENT_MODES else COMMENT_MODE_DEFAULT


def comment_note(post: str = "") -> str:
    """What the model is told before answering: the reply is public. Model prompt, so Vietnamese only."""
    post = str(post or "").strip()
    return ("[Đây là BÌNH LUẬN CÔNG KHAI trên Threads, dưới một bài của tài khoản"
            + (f' (bài: "{post[:300]}")' if post else "")
            + ". Câu trả lời của bạn hiện công khai ngay dưới bình luận này, ai cũng đọc được, tối đa 500 ký tự: trả "
              "lời ngắn gọn, lịch sự, không nêu số điện thoại, địa chỉ hay thông tin riêng của khách. Threads không có "
              "tin nhắn riêng, cần trao đổi riêng thì mời khách nhắn qua kênh khác của shop.]")


def reply_event(value: dict, own_username: str = "", own_id: str = ""):
    """One `replies` notification value -> the reply it carries, or None.

    Skips the account's own replies (every answer Javis sends comes back here). A top-level reply (its parent is the
    root post) opens its own conversation; a reply under a reply joins its parent's."""
    v = value or {}
    rid = str(v.get("id") or "")
    if not rid:
        return None
    who = str(v.get("username") or "")
    if own_username and who and who.lower() == str(own_username).lower():
        return None
    if own_id and str((v.get("from") or {}).get("id") or "") == str(own_id):
        return None
    root_post = str((v.get("root_post") or {}).get("id") or "")
    parent = str((v.get("replied_to") or {}).get("id") or "")
    thread = rid if (not parent or parent == root_post) else parent
    return {"reply_id": rid, "thread_id": thread, "post_id": root_post, "username": who,
            "text": str(v.get("text") or "").strip(), "permalink": str(v.get("permalink") or ""),
            "media_type": str(v.get("media_type") or "")}


def _notifications(payload: dict) -> list:
    """Every (account id, field, value) a webhook payload carries. Threads sends one notification per request as
    {"app_id", "topic", "target_id", "values": {"field", "value"}}; the `entry` / `changes` shape the other Meta
    webhooks use is read too, so a change of envelope does not drop replies."""
    out = []
    p = payload or {}
    vals = p.get("values")
    for v in (vals if isinstance(vals, list) else [vals] if isinstance(vals, dict) else []):
        val = (v or {}).get("value") or {}
        target = str(p.get("target_id") or ((val.get("root_post") or {}).get("owner_id")) or "")
        out.append((target, str((v or {}).get("field") or ""), val))
    for entry in p.get("entry") or []:
        for ch in (entry or {}).get("changes") or []:
            out.append((str(entry.get("id") or ""), str((ch or {}).get("field") or ""), (ch or {}).get("value") or {}))
    return out


async def handle_webhook(payload: dict) -> int:
    """Hand each new reply to the bot of the account it is about. Returns how many were handed over."""
    n = 0
    for target, field, value in _notifications(payload):
        if field != REPLIES_FIELD:
            continue
        bot = _REGISTRY.get(target)
        if not bot:
            owner = str(((value or {}).get("root_post") or {}).get("owner_id") or "")
            bot = _REGISTRY.get(owner)
        if not bot:
            print(f"[threads] reply for account {target} but no bot runs for it", file=sys.stderr)
            continue
        asyncio.create_task(bot._safe_reply(value))
        n += 1
    return n


def _err(d: dict, fallback: str) -> str:
    e = (d or {}).get("error") or {}
    code = e.get("code")
    msg = str(e.get("message") or fallback)
    if str(code) == "190":
        return localefmt.chu("token Threads hết hạn hoặc bị thu hồi, đăng nhập Threads lại ở thẻ Kết nối Meta (190)",
                             "the Threads token expired or was revoked, log in to Threads again on the Meta card (190)")
    if str(code) in ("10", "200"):
        return localefmt.chu(f"app chưa có quyền này trên Threads ({code}): đăng nhập Threads lại và cấp đủ quyền",
                             f"the app lacks this Threads permission ({code}): log in to Threads again and grant all")
    return msg + (f" ({code})" if code else "")


async def whoami(client, token: str) -> dict:
    """{"ok", "id", "username", "name"} of the token's Threads account, or {"ok": False, "error"}."""
    try:
        r = await client.get(f"{GRAPH}/me", params={"fields": "id,username,name", "access_token": token})
        d = r.json() or {}
    except Exception as e:
        return {"ok": False, "error": localefmt.chu(f"Không nối được Threads: {e}", f"Could not reach Threads: {e}")}
    if d.get("error") or not d.get("id"):
        return {"ok": False, "error": _err(d, "invalid token")}
    return {"ok": True, "id": str(d["id"]), "username": str(d.get("username") or ""), "name": str(d.get("name") or "")}


async def refresh_token(client, token: str) -> dict:
    """A fresh 60-day token from a long-lived one. {"ok", "access_token", "expires_in"} or {"ok": False, "error"}."""
    try:
        r = await client.get(f"{GRAPH_HOST}/refresh_access_token",
                             params={"grant_type": "th_refresh_token", "access_token": token})
        d = r.json() or {}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    if d.get("error") or not d.get("access_token"):
        return {"ok": False, "error": _err(d, "refresh failed")}
    return {"ok": True, "access_token": str(d["access_token"]), "expires_in": int(d.get("expires_in") or 0)}


class ThreadsBot(HangLuot):
    def __init__(self, token, chat_id, answer_fn, command_fn=None, callback_fn=None,
                 download_dir=None, commands=None, precheck_fn=None, event_fn=None,
                 giau_trang_thai=False, stt_fn=None, **_ignored):
        creds = split_credentials(token) if not isinstance(token, dict) else dict(token)
        self.user_id = str(creds.get("user_id") or "")
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
        self._task = None
        self._current = {}
        self._cho = {}
        self._stop = False
        self.status = "off"
        self.last_error = ""
        self.bot_id = self.user_id
        self.bot_username = ""
        self.loi_danh_tinh = ""
        self.doc_moi_tin_nhom = False
        self.last_inbound = 0.0
        self._seen = set()
        self._seen_order = deque()
        self._posts: dict = {}
        self._client = None
        self.account_id = ""

    # ---- HTTP -------------------------------------------------------------------------
    async def _post(self, client, path, params) -> dict:
        try:
            r = await client.post(f"{GRAPH}/{path}", params={**params, "access_token": self.token})
            try:
                d = r.json() or {}
            except Exception:
                d = {}
            if r.status_code >= 300 or d.get("error"):
                return {"ok": False, "code": ((d.get("error") or {}).get("code") or r.status_code),
                        "error": _err(d, f"HTTP {r.status_code}")}
            d["ok"] = True
            return d
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    async def _reply(self, client, to, text) -> dict:
        """Publish one TEXT reply under post or reply `to`: create the container, then publish it."""
        c = await self._post(client, f"{self.user_id}/threads",
                             {"media_type": "TEXT", "text": text, "reply_to_id": str(to)})
        if not c.get("ok"):
            return c
        if not c.get("id"):
            return {"ok": False, "error": localefmt.chu("Threads không trả mã bài", "Threads returned no container id")}
        return await self._post(client, f"{self.user_id}/threads_publish", {"creation_id": str(c["id"])})

    async def hide_reply(self, reply_id, hide: bool = True) -> dict:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            return await self._post(client, f"{reply_id}/manage_reply", {"hide": "true" if hide else "false"})

    async def _send(self, client, chat, text, reply_markup=None):
        if not str(text or "").strip() and self.giau_trang_thai:
            return
        text = md_to_plain(text or localefmt.chu("(không có nội dung)", "(no content)"))
        for chunk in _chunks(text):
            d = await self._reply(client, chat, chunk)
            if not d.get("ok"):
                self.last_error = d.get("error", "")
                print(f"[threads send] {d.get('error')}", file=sys.stderr)
                break

    async def send_text(self, chat, text):
        text = md_to_plain(str(text or "").strip())
        if not text:
            return False, "empty message"
        if not (self.token and self.user_id):
            return False, localefmt.chu("thiếu tài khoản hoặc token Threads", "missing the Threads account or token")
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            for chunk in _chunks(text):
                d = await self._reply(client, chat, chunk)
                if not d.get("ok"):
                    return False, d.get("error", "")
        return True, ""

    async def send_file(self, path, caption="", chat=None):
        return False, localefmt.chu("Javis chỉ trả lời bình luận Threads bằng chữ", "Javis answers Threads replies with text only")

    async def _post_text(self, client, post_id) -> str:
        """The first words of the post a reply sits under, for the inbox title and for the bot. Cached."""
        if not post_id:
            return ""
        if post_id in self._posts:
            return self._posts[post_id]
        txt = ""
        try:
            r = await client.get(f"{GRAPH}/{post_id}", params={"fields": "text", "access_token": self.token})
            txt = re.sub(r"\s+", " ", str((r.json() or {}).get("text") or "")).strip()
        except Exception:
            txt = ""
        if len(self._posts) > 500:
            self._posts.clear()
        self._posts[post_id] = txt
        return txt

    # ---- Inbound ----------------------------------------------------------------------
    def _seen_before(self, rid) -> bool:
        rid = str(rid or "")
        if not rid:
            return False
        if rid in self._seen:
            return True
        self._seen.add(rid)
        self._seen_order.append(rid)
        while len(self._seen_order) > MAX_DEDUPE:
            self._seen.discard(self._seen_order.popleft())
        return False

    async def _safe_reply(self, value):
        try:
            await self._on_reply(value)
        except Exception as e:
            print(f"[threads reply] {type(e).__name__}: {e}", file=sys.stderr)

    async def _on_reply(self, value):
        ev = reply_event(value, self.bot_username, self.user_id)
        if not ev or self._stop or self._seen_before(ev["reply_id"]):
            return
        mode = comment_mode(self.account_id)
        if mode == "off" or not ev["text"]:
            return
        self.last_inbound = time.time()
        client = self._client or httpx.AsyncClient(timeout=httpx.Timeout(60.0))
        self._client = client
        post = await self._post_text(client, ev["post_id"])
        short = (post[:60] + "...") if len(post) > 60 else post
        name = ("@" + ev["username"]) if ev["username"] else ""
        meta = {
            "platform": "threads", "chat_id": ev["thread_id"], "chat_type": "private",
            "chat_title": localefmt.chu("Bình luận Threads", "Threads reply") + (f": {short}" if short else ""),
            "user_name": name, "username": ev["username"], "user_id": ev["username"] or ev["thread_id"],
            "message_id": ev["reply_id"], "bot_username": self.bot_username, "mentioned": False,
            "reply_to_bot": False, "comment": True, "post_id": ev["post_id"],
            "ghi_chu_dau": comment_note(post),
        }
        if mode == "inbox":
            meta["log_only"] = True
            await self.answer_fn(ev["text"], meta, None)
            return
        await self._dispatch(client, ev["thread_id"], ev["text"], meta)

    # ---- One turn ---------------------------------------------------------------------
    async def _handle_turn(self, client, chat, text, meta=None):
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
            print(f"[threads turn failed] {type(e).__name__}: {e}", file=sys.stderr)
            from telegram_bot import CAU_LOI_NGUOI_THAT
            reply = (CAU_LOI_NGUOI_THAT if self.giau_trang_thai else f"⚠ {type(e).__name__}: {e}")
        silent = False
        if isinstance(reply, dict):
            silent = bool(reply.get("im_lang"))
            reply = reply.get("text") or ""
        if silent and not str(reply or "").strip():
            return
        if not self.giau_trang_thai:
            trail = dong_vet(tools, time.monotonic() - t0)
            reply = ((str(reply or "").rstrip() + "\n\n") if str(reply or "").strip() else "") + trail
        if str(reply or "").strip():
            await self._send(client, chat, reply)

    # ---- Lifecycle --------------------------------------------------------------------
    async def _maybe_refresh(self, client) -> None:
        """Refresh the 60-day token once it is REFRESH_AFTER old, and store the new one."""
        try:
            import channel_accounts
            a = channel_accounts.get_account(self.account_id) or {}
        except Exception:
            return
        meta = a.get("meta") or {}
        if time.time() - float(meta.get("token_at") or 0) < REFRESH_AFTER:
            return
        r = await refresh_token(client, self.token)
        if not r.get("ok"):
            print(f"[threads refresh] {r.get('error')}", file=sys.stderr)
            return
        self.token = r["access_token"]
        channel_accounts.update_account(self.account_id, {
            "token": join_credentials(self.user_id, self.token, self.app_secret),
            "meta": {**meta, "token_at": time.time(), "token_expires": time.time() + (r.get("expires_in") or 0)}})

    async def _watch(self):
        """No connection to hold: Threads pushes. Check the token, then stay registered until stopped, refreshing the
        token when it is due."""
        if not (self.token and self.user_id):
            self.status = "error"
            self.last_error = self.loi_danh_tinh = localefmt.chu("thiếu token Threads", "missing the Threads token")
            return
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as c:
            await self._maybe_refresh(c)
            info = await whoami(c, self.token)
        if not info.get("ok"):
            self.status = "error"
            self.last_error = self.loi_danh_tinh = info.get("error", "")
            return
        self.bot_username = info.get("username", "")
        self.loi_danh_tinh = ""
        old = _REGISTRY.get(self.user_id)
        if old is not None and old is not self:
            print(f"[threads] account {self.user_id} was served by another bot; the newest one takes over", file=sys.stderr)
        _REGISTRY[self.user_id] = self
        self.status = "polling"
        self.last_error = ""
        try:
            while not self._stop:
                await asyncio.sleep(3600)
                async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as c:
                    await self._maybe_refresh(c)
        finally:
            if _REGISTRY.get(self.user_id) is self:
                _REGISTRY.pop(self.user_id, None)

    def start(self):
        self._stop = False
        self.status = "starting"
        if not self._task or self._task.done():
            self._task = asyncio.create_task(self._watch())

    def stop(self):
        self._stop = True
        self.status = "stopped"
        if _REGISTRY.get(self.user_id) is self:
            _REGISTRY.pop(self.user_id, None)
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
