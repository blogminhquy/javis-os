"""Facebook Messenger gateway over the official Messenger Platform (Meta), 0.134.0.

Same shape as `whatsapp_bot` because the platform works the same way: Javis cannot pull
messages, Meta POSTs every inbound message to a webhook. Two halves:

  - `MessengerBot`: the transport, same contract as `TelegramBot` (start/stop/status/send_text/
    send_file). `start()` opens no connection; it checks the credentials, subscribes the Page
    to the app's webhook and registers the bot under its Page id.
  - `handle_webhook(payload)`: called by the `/messenger/webhook` route in main.py once the
    signature has been checked. It routes each message to the bot registered for the Page it
    was sent to. One URL serves every Page.

Credentials for one Page (developers.facebook.com, app -> Messenger -> API settings):
  - Page id (digits)
  - Page access token (long-lived; generated for the Page in the app dashboard)
  - App secret (App settings -> Basic), used only to verify `X-Hub-Signature-256`

Rules of the platform that shape the code:
  1. The 24-hour window. A Page may reply freely only within 24 hours of the person's last
     message; after that the send fails (error 10 / 2018278, or 1545041). `_explain_error`
     says so in words. The inbox still keeps the conversation.
  2. Messenger renders no markdown, so answers go out as plain text (`md_to_plain`).
  3. 2000 characters per text message; longer answers are split.
  4. Private conversations with a Page only; there are no groups.
  5. Until the app passes Meta's App Review for `pages_messaging`, only people with a role on
     the app (admin, developer, tester) get replies. Error 200/10 on send says exactly that.

Page comments (0.434.0), handled the way Pancake shows them: every top-level comment under a Page
post is its own conversation in the inbox, every reply under it joins that conversation, and
whatever Javis sends there goes out as a reply under that top-level comment. The conversation id
is `cmt:<top-level comment id>`, so a reply needs no stored state and still works after a
restart. They arrive as `feed` changes on the same webhook. Each account picks a mode in its
meta (`comments`): "off", "inbox" (shown in the inbox, the owner answers; the default) or
"reply" (the bot answers them too, publicly).
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
from whatsapp_bot import verify_signature  # noqa: F401  - same Meta signature scheme, re-exported

GRAPH_VERSION = os.getenv("JAVIS_MESSENGER_GRAPH_VERSION", os.getenv("JAVIS_WHATSAPP_GRAPH_VERSION", "v23.0"))
GRAPH = f"https://graph.facebook.com/{GRAPH_VERSION}"

MAX_MSG = 1900               # Messenger allows 2000; keep a margin for multi-byte counting
MAX_DEDUPE = 4000
MAX_DOWNLOAD_MB = 20
TYPING_EVERY = 15.0          # typing_on lasts about 20 s or until the next message
SUBSCRIBED_FIELDS = "messages,messaging_postbacks"
FEED_FIELD = "feed"           # Page comments (0.434.0); optional, the bot works without it
COMMENT_PREFIX = "cmt:"       # conversation id of a comment thread: cmt:<top-level comment id>
COMMENT_MODES = ("off", "inbox", "reply")
COMMENT_MODE_DEFAULT = "inbox"
MAX_COMMENT = 7900            # a comment takes 8000 characters

# page_id -> MessengerBot currently running for it.
_REGISTRY: dict = {}


def split_credentials(raw) -> dict:
    """"<page id> <page access token> <app secret>" in any order -> dict.

    One string because the channel-account store keeps one encrypted secret per account. The
    parts are told apart by shape: the Page id is all digits, the app secret is 32 hex
    characters, the access token is the long remaining one (EAA...).
    """
    out = {"page_id": "", "access_token": "", "app_secret": ""}
    for part in re.split(r"[\s,;|]+", str(raw or "").strip()):
        if not part:
            continue
        if re.fullmatch(r"\d{5,25}", part):
            out["page_id"] = part
        elif re.fullmatch(r"[0-9a-fA-F]{32}", part):
            out["app_secret"] = part
        elif len(part) > 40:
            out["access_token"] = part
    return out


def md_to_plain(text: str) -> str:
    """Markdown -> plain text Messenger shows as written. Code fences lose their markers only."""
    t = str(text or "")
    t = re.sub(r"```[a-zA-Z0-9_-]*\n?(.*?)```", r"\1", t, flags=re.S)
    t = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r"\1", t)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"\1 (\2)", t)
    t = re.sub(r"^#{1,6}\s+(.+?)\s*#*$", r"\1", t, flags=re.M)
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = re.sub(r"__(.+?)__", r"\1", t)
    t = re.sub(r"~~(.+?)~~", r"\1", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])", r"\1", t)
    t = re.sub(r"`([^`\n]+)`", r"\1", t)
    t = re.sub(r"^(\s*)[-*]\s+", r"\1• ", t, flags=re.M)
    return t


def _chunks(text: str, size: int = MAX_MSG) -> list:
    text = str(text or "")
    if len(text) <= size:
        return [text]
    out = []
    while len(text) > size:
        cut = text.rfind("\n", 0, size)
        if cut < size // 2:
            cut = text.rfind(" ", 0, size)
        if cut < size // 2:
            cut = size
        out.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text.strip():
        out.append(text)
    return out


def registered() -> dict:
    return dict(_REGISTRY)


def is_comment_chat(chat) -> bool:
    return str(chat or "").startswith(COMMENT_PREFIX)


def comment_event(value: dict, page_id: str):
    """One `feed` change -> the new comment it carries, or None.

    Only new comments count (`item` comment, `verb` add); edits, removals, reactions and posts are
    skipped, and so are the Page's own comments, which include every reply Javis sends. A reply
    under a reply still belongs to the top-level comment: `parent_id` is the post id for a
    top-level comment and the parent comment id otherwise."""
    v = value or {}
    if v.get("item") != "comment" or v.get("verb") != "add":
        return None
    cid = str(v.get("comment_id") or "")
    if not cid:
        return None
    who = v.get("from") or {}
    from_id = str(who.get("id") or "")
    if from_id and from_id == str(page_id):
        return None
    post_id = str(v.get("post_id") or "")
    parent = str(v.get("parent_id") or "")
    root = cid if (not parent or parent == post_id) else parent
    return {"comment_id": cid, "root_id": root, "post_id": post_id, "from_id": from_id,
            "from_name": str(who.get("name") or ""), "message": str(v.get("message") or "").strip(),
            "photo": str(v.get("photo") or ""), "video": str(v.get("video") or ""),
            "permalink": str((v.get("post") or {}).get("permalink_url") or "")}


def comment_note(post: str = "") -> str:
    """What the model is told before answering a comment: it is public. Model prompt, so Vietnamese only."""
    post = str(post or "").strip()
    return ("[Đây là BÌNH LUẬN CÔNG KHAI dưới một bài viết của Fanpage"
            + (f' (bài viết: "{post[:300]}")' if post else "")
            + ". Câu trả lời của bạn hiện công khai ngay dưới bình luận này, ai cũng đọc được: trả lời ngắn gọn, "
              "lịch sự, không nêu số điện thoại, địa chỉ hay thông tin riêng của khách; cần trao đổi riêng thì mời "
              "khách nhắn tin cho Page.]")


def comment_mode(account_id: str) -> str:
    """The comment mode of a Messenger account, from its meta. Unknown or missing -> the default."""
    try:
        import channel_accounts
        a = channel_accounts.get_account(str(account_id or "")) or {}
        m = str((a.get("meta") or {}).get("comments") or "").strip()
    except Exception:
        m = ""
    return m if m in COMMENT_MODES else COMMENT_MODE_DEFAULT


async def handle_webhook(payload: dict) -> int:
    """Route a verified webhook payload to the bots it is for. Returns how many events were
    handed over. Echoes (the Page's own outgoing messages), reads and deliveries are skipped."""
    if (payload or {}).get("object") not in (None, "page"):
        return 0
    n = 0
    for entry in (payload or {}).get("entry") or []:
        pid = str(entry.get("id") or "")
        bot = _REGISTRY.get(pid)
        events = entry.get("messaging") or []
        changes = [c for c in (entry.get("changes") or []) if (c or {}).get("field") == FEED_FIELD]
        if not bot:
            if events:
                print(f"[messenger] event for Page {pid} but no bot runs for it", file=sys.stderr)
            continue
        for ch in changes:
            com = comment_event(ch.get("value") or {}, pid)
            if com:
                asyncio.create_task(bot._safe_comment(com))
                n += 1
        for ev in events:
            msg = ev.get("message") or {}
            if msg.get("is_echo"):
                continue
            if not msg and not ev.get("postback"):
                continue
            asyncio.create_task(bot._safe_event(ev))
            n += 1
    return n


class MessengerBot(HangLuot):
    def __init__(self, token, chat_id, answer_fn, command_fn=None, callback_fn=None,
                 download_dir=None, commands=None, precheck_fn=None, event_fn=None,
                 giau_trang_thai=False, stt_fn=None, **_ignored):
        creds = split_credentials(token) if not isinstance(token, dict) else dict(token)
        self.page_id = str(creds.get("page_id") or "")
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
        self.bot_id = self.page_id
        self.bot_username = ""
        self.loi_danh_tinh = ""
        self.doc_moi_tin_nhom = False
        self.last_inbound = 0.0
        self._seen = set()
        self._seen_order = deque()
        self._names: dict = {}
        self._posts: dict = {}
        self._client = None
        self.account_id = ""
        self.feed_on = False

    # ---- HTTP -------------------------------------------------------------------------
    def _params(self):
        return {"access_token": self.token}

    async def _post_json(self, client, path, payload):
        try:
            r = await client.post(f"{GRAPH}/{path}", json=payload, params=self._params())
            try:
                d = r.json() or {}
            except Exception:
                d = {}
            if r.status_code >= 300 or d.get("error"):
                e = d.get("error") or {}
                return {"ok": False, "code": e.get("code") or r.status_code,
                        "error": _explain_error(e.get("code"), e.get("message") or f"HTTP {r.status_code}",
                                                e.get("error_subcode"))}
            d["ok"] = True
            return d
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}", "net_error": True}

    async def _send_one(self, client, to, text):
        if is_comment_chat(to):
            d = await self._post_json(client, f"{str(to)[len(COMMENT_PREFIX):]}/comments", {"message": text})
            if not d.get("ok") and str(d.get("code")) in ("10", "200"):
                d["error"] = localefmt.chu(
                    "app chưa có quyền trả lời bình luận. Đăng nhập Facebook lại ở thẻ Messenger và cấp quyền "
                    f"pages_manage_engagement ({d.get('code')})",
                    "the app may not reply to comments yet. Log in with Facebook again on the Messenger card and "
                    f"grant pages_manage_engagement ({d.get('code')})")
            return d
        return await self._post_json(client, f"{self.page_id}/messages", {
            "recipient": {"id": str(to)}, "messaging_type": "RESPONSE",
            "message": {"text": text}})

    async def _send(self, client, chat, text, reply_markup=None):
        if not str(text or "").strip() and self.giau_trang_thai:
            return
        text = md_to_plain(text or localefmt.chu("(không có nội dung)", "(no content)"))
        for chunk in _chunks(text, MAX_COMMENT if is_comment_chat(chat) else MAX_MSG):
            d = await self._send_one(client, chat, chunk)
            if not d.get("ok"):
                self.last_error = d.get("error", "")
                print(f"[messenger send] {d.get('error')}", file=sys.stderr)
                break

    async def send_text(self, chat, text):
        text = md_to_plain(str(text or "").strip())
        if not text:
            return False, "empty message"
        if not (self.token and self.page_id):
            return False, localefmt.chu("thiếu Page id hoặc Page access token Messenger",
                                        "missing the Messenger Page id or Page access token")
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            for chunk in _chunks(text, MAX_COMMENT if is_comment_chat(chat) else MAX_MSG):
                d = await self._send_one(client, chat, chunk)
                if not d.get("ok"):
                    return False, d.get("error", "")
        return True, ""

    async def send_file(self, path, caption="", chat=None):
        """Upload the file with the message (multipart `filedata`). Returns (ok, error)."""
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
        if len(data) > 25 * 1024 * 1024:
            return False, localefmt.chu("file lớn hơn 25MB, Messenger không nhận", "file larger than 25MB, Messenger refuses it")
        import mimetypes
        mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        kind = ("image" if mime.startswith("image/") else "video" if mime.startswith("video/")
                else "audio" if mime.startswith("audio/") else "file")
        if is_comment_chat(chat):
            return await self._comment_photo(str(chat)[len(COMMENT_PREFIX):], p.name, data, mime, kind, caption)
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as c:
            try:
                r = await c.post(f"{GRAPH}/{self.page_id}/messages", params=self._params(), data={
                    "recipient": json.dumps({"id": str(chat)}),
                    "messaging_type": "RESPONSE",
                    "message": json.dumps({"attachment": {"type": kind, "payload": {"is_reusable": False}}}),
                }, files={"filedata": (p.name, data, mime)})
                d = r.json() or {}
            except Exception as e:
                return False, f"{type(e).__name__}: {e}"
            if d.get("error") or not d.get("message_id"):
                e = d.get("error") or {}
                return False, _explain_error(e.get("code"), e.get("message") or "upload failed", e.get("error_subcode"))
        if str(caption or "").strip():
            ok, err = await self.send_text(chat, caption)
            if not ok:
                return False, err
        return True, ""

    async def _comment_photo(self, root, name, data, mime, kind, caption=""):
        """A reply under a comment carrying one image (`source`). A comment takes no other file type."""
        if kind != "image":
            return False, localefmt.chu("bình luận chỉ đính kèm được ảnh", "a comment can only carry an image")
        form = {"message": md_to_plain(str(caption or "").strip())[:MAX_COMMENT]} if str(caption or "").strip() else {}
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as c:
            try:
                r = await c.post(f"{GRAPH}/{root}/comments", params=self._params(), data=form,
                                 files={"source": (name, data, mime)})
                d = r.json() or {}
            except Exception as e:
                return False, f"{type(e).__name__}: {e}"
        if d.get("error") or not d.get("id"):
            e = d.get("error") or {}
            return False, _explain_error(e.get("code"), e.get("message") or "upload failed", e.get("error_subcode"))
        return True, ""

    async def _action(self, client, chat, action):
        """Sender action: mark_seen, typing_on or typing_off. Failures are not worth a log line.
        A comment thread has no typing indicator."""
        if is_comment_chat(chat):
            return
        await self._post_json(client, f"{self.page_id}/messages",
                              {"recipient": {"id": str(chat)}, "sender_action": action})

    async def _name_of(self, client, psid) -> str:
        """Display name of a person (User Profile API). Empty when the app may not read it."""
        if psid in self._names:
            return self._names[psid]
        name = ""
        try:
            r = await client.get(f"{GRAPH}/{psid}", params={"fields": "first_name,last_name,name",
                                                            "access_token": self.token})
            d = r.json() or {}
            name = str(d.get("name") or " ".join(x for x in (d.get("first_name"), d.get("last_name")) if x)).strip()
        except Exception:
            name = ""
        if len(self._names) > 2000:
            self._names.clear()
        self._names[psid] = name
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
        url = str((att.get("payload") or {}).get("url") or "")
        if atype == "location":
            co = (att.get("payload") or {}).get("coordinates") or {}
            return f"[location: {co.get('lat')}, {co.get('long')}]"
        if atype == "fallback" or not url:
            return str(att.get("title") or (url and f"[link: {url}]") or "").strip()
        if atype in ("video", "reel", "ig_reel"):
            return localefmt.chu(f"[Người dùng gửi một video qua Messenger: {url}]",
                                 f"[The user sent a video on Messenger: {url}]")
        try:
            data, mime = await self._download(client, url)
        except Exception as e:
            return f"[{atype}: {type(e).__name__}: {e}]"
        if atype == "audio":
            if not self.stt_fn:
                return stt.loi_thanh_dong("thieu_key")
            try:
                kq = await self.stt_fn(data, f"messenger_{int(time.time())}.mp4")
            except Exception as e:
                kq = {"ok": False, "noi_voi_javis": stt.loi_thanh_dong("loi", f"{type(e).__name__}: {e}")}
            if not (kq or {}).get("ok"):
                return (kq or {}).get("noi_voi_javis") or stt.loi_thanh_dong("loi")
            return stt.khoi_thoai(kq.get("text"), "Messenger")
        ddir = self.download_dir(chat) if callable(self.download_dir) else self.download_dir
        d = Path(ddir) if ddir else Path("messenger-inbox")
        d.mkdir(parents=True, exist_ok=True)
        ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp",
               "application/pdf": ".pdf"}.get(mime, "")
        if not ext:
            m = re.search(r"\.([A-Za-z0-9]{2,5})(?:\?|$)", url)
            ext = "." + m.group(1).lower() if m else ""
        dest = d / f"messenger_{int(time.time() * 1000)}{ext}"
        dest.write_bytes(data)
        if atype == "image":
            return localefmt.chu(f"[Người dùng gửi ảnh qua Messenger, đã tải về: {dest}]",
                                 f"[The user sent an image on Messenger, downloaded to: {dest}]")
        return localefmt.chu(f"[Người dùng gửi file qua Messenger, đã tải về: {dest}]",
                             f"[The user sent a file on Messenger, downloaded to: {dest}]")

    async def _event_text(self, client, ev, chat) -> str:
        pb = ev.get("postback")
        if pb:
            return str(pb.get("title") or pb.get("payload") or "").strip()
        msg = ev.get("message") or {}
        qr = (msg.get("quick_reply") or {}).get("payload")
        parts = []
        for att in msg.get("attachments") or []:
            t = await self._attachment_text(client, att, chat)
            if t:
                parts.append(t)
        text = str(msg.get("text") or "").strip()
        if text:
            parts.append(text)
        elif qr and not parts:
            parts.append(str(qr))
        return "\n".join(parts).strip()

    async def _safe_event(self, ev):
        try:
            await self._on_event(ev)
        except Exception as e:
            print(f"[messenger event] {type(e).__name__}: {e}", file=sys.stderr)

    async def _on_event(self, ev):
        msg = ev.get("message") or {}
        mid = msg.get("mid") or (ev.get("postback") or {}).get("mid") or ""
        if self._stop or self._seen_before(mid):
            return
        chat = str((ev.get("sender") or {}).get("id") or "")
        if not chat or chat == self.page_id:
            return
        self.last_inbound = time.time()
        client = self._client or httpx.AsyncClient(timeout=httpx.Timeout(60.0))
        self._client = client
        name = await self._name_of(client, chat)
        meta = {
            "platform": "messenger", "chat_id": chat, "chat_type": "private", "chat_title": "",
            "user_name": name, "username": name, "user_id": chat,
            "message_id": mid, "bot_username": self.bot_username,
            "mentioned": False, "reply_to_bot": bool(msg.get("reply_to")),
        }
        if self.chat_ids and chat not in self.chat_ids:
            await self._send(client, chat, localefmt.chu(
                "Bạn không có quyền dùng bot Javis này.", "You are not allowed to use this Javis bot."))
            return
        text = await self._event_text(client, ev, chat)
        if not text:
            return
        await self._action(client, chat, "mark_seen")
        await self._dispatch(client, chat, text, meta)

    # ---- Page comments (0.434.0) -------------------------------------------------------
    async def _safe_comment(self, com):
        try:
            await self._on_comment(com)
        except Exception as e:
            print(f"[messenger comment] {type(e).__name__}: {e}", file=sys.stderr)

    async def _post_text(self, client, post_id) -> str:
        """The first words of the post a comment sits under, for the inbox title and for the bot.
        Cached; empty when the token may not read it."""
        if not post_id:
            return ""
        if post_id in self._posts:
            return self._posts[post_id]
        txt = ""
        try:
            r = await client.get(f"{GRAPH}/{post_id}", params={"fields": "message", "access_token": self.token})
            txt = re.sub(r"\s+", " ", str((r.json() or {}).get("message") or "")).strip()
        except Exception:
            txt = ""
        if len(self._posts) > 500:
            self._posts.clear()
        self._posts[post_id] = txt
        return txt

    async def _on_comment(self, com):
        if self._stop or self._seen_before("c" + com["comment_id"]):
            return
        mode = comment_mode(getattr(self, "account_id", ""))
        if mode == "off":
            return
        chat = COMMENT_PREFIX + com["root_id"]
        self.last_inbound = time.time()
        client = self._client or httpx.AsyncClient(timeout=httpx.Timeout(60.0))
        self._client = client
        parts = []
        if com.get("photo"):
            parts.append(await self._attachment_text(client, {"type": "image", "payload": {"url": com["photo"]}}, chat))
        if com.get("video"):
            parts.append(localefmt.chu(f"[Người dùng gắn một video vào bình luận: {com['video']}]",
                                       f"[The user attached a video to the comment: {com['video']}]"))
        if com.get("message"):
            parts.append(com["message"])
        text = "\n".join(x for x in parts if x).strip()
        if not text:
            return
        post = await self._post_text(client, com.get("post_id"))
        short = (post[:60] + "...") if len(post) > 60 else post
        title = localefmt.chu("Bình luận", "Comment") + (f": {short}" if short else "")
        meta = {
            "platform": "messenger", "chat_id": chat, "chat_type": "private", "chat_title": title,
            "user_name": com.get("from_name", ""), "username": com.get("from_name", ""),
            "user_id": com.get("from_id") or chat, "message_id": com["comment_id"],
            "bot_username": self.bot_username, "mentioned": False, "reply_to_bot": False,
            "comment": True, "comment_id": com["comment_id"], "post_id": com.get("post_id", ""),
            # For the model only, never the inbox (see `ghi_chu_dau` in chatbot_runtime).
            "ghi_chu_dau": comment_note(post),
        }
        if mode == "inbox":
            # Shown in the inbox only: the answer function records the comment and stays silent.
            meta["log_only"] = True
            await self.answer_fn(text, meta, None)
            return
        await self._dispatch(client, chat, text, meta)

    # ---- One turn ---------------------------------------------------------------------
    async def _keep_typing(self, client, chat):
        while True:
            await asyncio.sleep(TYPING_EVERY)
            await self._action(client, chat, "typing_on")

    async def _handle_turn(self, client, chat, text, meta=None):
        files = []
        tools = []
        t0 = time.monotonic()
        await self._action(client, chat, "typing_on")
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
                print(f"[messenger turn failed] {type(e).__name__}: {e}", file=sys.stderr)
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
            try:
                await self._action(client, chat, "typing_off")
            except Exception:
                pass

    # ---- Lifecycle --------------------------------------------------------------------
    async def _watch(self):
        """No connection to hold: the webhook pushes. Check the credentials, make sure the Page
        sends its messages to this app, then stay registered until stopped."""
        if not (self.token and self.page_id and self.app_secret):
            # Without the app secret every webhook POST fails the signature check (401) and the
            # bot would look healthy while hearing nothing: refuse to start instead.
            self.status = "error"
            self.last_error = localefmt.chu("Thiếu Page id, Page access token hoặc App secret.",
                                            "Missing the Page id, Page access token or App secret.")
            return
        sub = {"ok": True}
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as c:
            info = await whoami(c, self.page_id, self.token, self.app_secret)
            if info.get("ok"):
                sub = await subscribe_page(c, self.page_id, self.token)
        if not info.get("ok"):
            self.status = "error"
            self.last_error = info.get("error", "")
            self.loi_danh_tinh = self.last_error
            return
        # Subscribing needs pages_manage_metadata, which many Page tokens lack. A Page subscribed by
        # hand in the Meta app still delivers, so a failed subscribe is a warning, not a dead bot.
        self.loi_danh_tinh = "" if sub.get("ok") else localefmt.chu(
            "Javis chưa tự gắn được Page vào webhook (" + sub.get("error", "") + "). Nếu Page đã được gắn tay "
            "trong app Meta (Messenger, Webhooks, Add Subscriptions) thì bot vẫn nghe; chưa thì gắn tay ở đó.",
            "Javis could not subscribe the Page to the webhook (" + sub.get("error", "") + "). If the Page was "
            "subscribed by hand in the Meta app (Messenger, Webhooks, Add Subscriptions) the bot still hears; "
            "otherwise subscribe it there.")
        self.bot_username = info.get("username", "")
        self.feed_on = bool(sub.get("feed"))
        old = _REGISTRY.get(self.page_id)
        if old is not None and old is not self:
            print(f"[messenger] Page {self.page_id} was served by another bot; the newest one takes over",
                  file=sys.stderr)
        _REGISTRY[self.page_id] = self
        self.status = "polling"
        self.last_error = ""
        try:
            while not self._stop:
                await asyncio.sleep(3600)
        finally:
            if _REGISTRY.get(self.page_id) is self:
                _REGISTRY.pop(self.page_id, None)

    def start(self):
        self._stop = False
        self.status = "starting"
        if not self._task or self._task.done():
            self._task = asyncio.create_task(self._watch())

    def stop(self):
        self._stop = True
        self.status = "stopped"
        if _REGISTRY.get(self.page_id) is self:
            _REGISTRY.pop(self.page_id, None)
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


def appsecret_proof(token: str, app_secret: str) -> str:
    """HMAC-SHA256 of the access token keyed by the app secret, as Graph expects it."""
    return hmac.new(str(app_secret).encode(), str(token).encode(), hashlib.sha256).hexdigest()


async def whoami(client, page_id, token, app_secret: str = "") -> dict:
    """Ask Graph which Page this is. {"ok", "username", "bot_name"} or {"ok": False, "error"}.

    With `app_secret` the call carries `appsecret_proof`, which Graph validates whenever it is
    sent: a secret that does not belong to the app the token was made in fails here, at connect
    time, instead of silently failing every webhook signature later."""
    params = {"fields": "id,name", "access_token": token}
    if app_secret:
        params["appsecret_proof"] = appsecret_proof(token, app_secret)
    try:
        r = await client.get(f"{GRAPH}/{page_id}", params=params)
        d = r.json() or {}
    except Exception as e:
        return {"ok": False, "error": localefmt.chu(f"Không nối được Meta: {e}", f"Could not reach Meta: {e}")}
    if d.get("error") or str(d.get("id") or "") != str(page_id):
        e = d.get("error") or {}
        if "appsecret_proof" in str(e.get("message") or ""):
            return {"ok": False, "error": localefmt.chu(
                "App secret không khớp với app đã tạo Page access token này. Lấy lại App secret ở "
                "App settings, Basic của ĐÚNG app đó.",
                "The App secret does not belong to the app this Page access token was made in. Copy the "
                "App secret again from App settings, Basic of THAT app.")}
        return {"ok": False, "error": _explain_error(e.get("code"), e.get("message") or "invalid credentials",
                                                     e.get("error_subcode"))}
    return {"ok": True, "username": str(d.get("id") or ""), "bot_name": str(d.get("name") or "")}


async def _subscribe(client, page_id, token, fields) -> dict:
    try:
        r = await client.post(f"{GRAPH}/{page_id}/subscribed_apps",
                              params={"subscribed_fields": fields, "access_token": token})
        d = r.json() or {}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    if d.get("error") or not d.get("success"):
        e = d.get("error") or {}
        return {"ok": False, "error": _explain_error(e.get("code"), e.get("message") or "subscribe failed",
                                                     e.get("error_subcode"))}
    return {"ok": True}


async def subscribe_page(client, page_id, token) -> dict:
    """Make the Page deliver `messages` and `messaging_postbacks` (and `feed`, for comments) to
    this app's webhook. {"ok", "feed", "error"}.

    Without this the app's webhook is set up but the Page never calls it, and the bot looks
    healthy while hearing nothing. Calling it again is harmless. `feed` needs permissions an older
    token may lack, and Meta refuses the whole call then, so it is tried first and dropped on
    failure: messages must never be lost over comments."""
    d = await _subscribe(client, page_id, token, SUBSCRIBED_FIELDS + "," + FEED_FIELD)
    if d.get("ok"):
        return {"ok": True, "feed": True}
    feed_err = d.get("error", "")
    d = await _subscribe(client, page_id, token, SUBSCRIBED_FIELDS)
    if d.get("ok"):
        return {"ok": True, "feed": False, "feed_error": feed_err}
    return {"ok": False, "feed": False, "error": d.get("error", "")}


# Error codes the owner can act on. https://developers.facebook.com/docs/messenger-platform/error-codes
_WINDOW = ("đã quá 24 giờ kể từ tin cuối người này nhắn cho Page, Messenger không cho trả lời tự do nữa. "
           "Người đó nhắn lại là mở lại cửa sổ 24 giờ",
           "more than 24 hours since this person last wrote to the Page, so Messenger no longer allows a "
           "free reply. The window reopens when they write again")
_ERRORS = {
    1545041: _WINDOW,
    2018278: _WINDOW,
    551: ("người này hiện không nhận được tin (đã chặn Page hoặc tài khoản không còn)",
          "this person cannot receive messages right now (blocked the Page or the account is gone)"),
    190: ("Page access token hết hạn hoặc sai. Tạo lại token cho Page trong app Meta rồi dán lại",
          "the Page access token expired or is wrong. Generate a new one for the Page in the Meta app and paste it again"),
    200: ("app chưa có quyền nhắn tin cho người ngoài. Khi app còn ở chế độ phát triển, chỉ người có vai trò "
          "trong app (admin, developer, tester) nhận được trả lời: chuyển app sang Live, vẫn bị thì nộp xét duyệt "
          "pages_messaging",
          "the app may not message people outside it yet. While the app is in development mode only people with "
          "a role on it (admin, developer, tester) get replies: switch the app to Live, and if it persists submit "
          "pages_messaging for App Review"),
    10: ("app chưa đủ quyền cho việc này (thường là chưa qua xét duyệt pages_messaging, hoặc ngoài cửa sổ 24 giờ)",
         "the app lacks permission for this (usually pages_messaging not approved yet, or outside the 24-hour window)"),
    100: ("tham số sai, thường là Page id không đúng với token", "invalid parameter, usually a Page id that does not match the token"),
    613: ("vượt hạn mức gửi của Messenger, thử lại sau", "Messenger rate limit reached, try again later"),
}


def _explain_error(code, fallback="", subcode=None) -> str:
    for c in (subcode, code):
        try:
            ci = int(c)
        except Exception:
            continue
        vi_en = _ERRORS.get(ci)
        if vi_en:
            return localefmt.chu(f"{vi_en[0]} ({ci})", f"{vi_en[1]} ({ci})")
    return f"{fallback or 'error'}" + (f" ({code})" if code else "")
