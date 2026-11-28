"""Images a dedicated bot sends with its reply (0.84.3).

Before this, every bot turn returned `"files": []` (`main._bot_ket`), so no bot on any channel could send a picture,
even though the Telegram, Slack and WhatsApp transports already knew how to send `files`. Javis deliberately does
NOT auto-attach files the turn produced (`main._bot_tra_loi_co_tool`): with a stranger steering the model, "the file
that happened to appear" is a leak path.

So a bot sends an image only when its Agent ASKS for it, by writing a Markdown image `![caption](path)` in the reply,
and only when that path passes every gate here:

  - it resolves INSIDE the bot's own brain (symlinks resolved too), never another brain or the machine;
  - it is an existing image file (`IMAGE_EXTS`), not a document: a bot that may quote a document must still not
    hand out the raw file, and that is a separate decision from images;
  - it is at most `MAX_BYTES`, and at most `MAX_IMAGES` per reply.

A path that fails stays in the text as written, so the owner can see in the inbox what the Agent tried to send.

Web images from the bot's data sources (owner, 28/11/2026: "the chatbot must find a picture source such as the POS or a
related tool, and say it cannot send one when there is none"). A POS returns a product's photo as a link, never as a
file in the brain, so the bot could only say "I have no picture". A web link is now sent too, but only one that a
tool of this very chat's bot turn returned (`note_tool_result`, called by the hub after each call), or that the
documents looked up for this turn contain. A link the customer typed, or one the model made up, is never fetched. The
fetch is https or http to a public address only (every redirect checked again), the answer must be an image, at most
`MAX_BYTES`, and it lands in a cache under the state folder, not in the brain.
"""
from __future__ import annotations

import hashlib
import ipaddress
import os
import re
import socket
import threading
import time
from collections import deque
from pathlib import Path
from typing import Iterable, List, Optional, Tuple
from urllib.parse import unquote, urljoin, urlsplit

import channel_context
import channels

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
# Images per reply. 4 unless the machine sets JAVIS_BOT_MAX_IMAGES (issue #1634: a rental business needs more photos to
# show one room). Clamped to 1..MAX_IMAGES_CEILING: every image is one more message under the owner's name, and the
# personal Zalo channel remembers only the last 20 image echoes of a chat (`zalo_personal_channel.ghi_da_gui_anh`).
DEFAULT_MAX_IMAGES = 4
MAX_IMAGES_CEILING = 20


def max_images_from_env(raw=None) -> int:
    """The per-reply image cap from JAVIS_BOT_MAX_IMAGES (or `raw`): unset or not a number gives the default."""
    raw = os.environ.get("JAVIS_BOT_MAX_IMAGES", "") if raw is None else raw
    try:
        n = int(str(raw).strip())
    except (TypeError, ValueError):
        return DEFAULT_MAX_IMAGES
    return max(1, min(MAX_IMAGES_CEILING, n))


MAX_IMAGES = max_images_from_env()
MAX_BYTES = 10 * 1024 * 1024

# What the Agent reads so it knows the capability exists, and where a picture may come from.
PROMPT_HINT = ("\nSENDING IMAGES: to send a picture to the person you are talking to, put ![short caption](image) in "
               "your answer, at most " + str(MAX_IMAGES) + " per answer. Where a picture may come from, in this order: "
               "a file in your documents (path from their root, e.g. attachments/product.jpg); a web image link from "
               "your documents; a web image link a tool of yours returned in this turn (a POS or product catalogue: "
               "search the product there and use its image link as returned). When asked for a picture and a tool "
               "could have one, look it up before answering. Never make up a path or a link, and never use a link the "
               "customer typed. If no source has a picture, say plainly that you cannot send one right now; never "
               "promise to send it later.")


REMOTE_TTL_S = 1800            # a link a tool returned stays sendable this long (a bot turn is far shorter)
REMOTE_MAX = 4000              # links remembered at most, all chats together
REMOTE_PER_RESULT = 200        # links taken from one tool result
REMOTE_SCAN_CHARS = 400_000    # characters of one tool result searched for links
FETCH_TIMEOUT_S = 15
FETCH_REDIRECTS = 3
_URL_RE = re.compile(r"https?://[^\s\"'<>()\[\]{}\\|^`]+", re.IGNORECASE)
_URL_TAIL = ".,;:!?*_~"
_CT_EXT = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
_remote_lock = threading.Lock()
_remote: deque = deque(maxlen=REMOTE_MAX)     # (chat keys, url, time)


def _chat_keys(chat) -> frozenset:
    import delivery_ledger
    return delivery_ledger.chat_keys(chat)


def links_in(text, limit: int = REMOTE_PER_RESULT) -> List[str]:
    """The http(s) links in `text`, trailing punctuation dropped, in order, without repeats."""
    out: List[str] = []
    for m in _URL_RE.finditer(str(text or "")[:REMOTE_SCAN_CHARS]):
        url = m.group(0).rstrip(_URL_TAIL)
        if len(url) > 2000 or url in out:
            continue
        out.append(url)
        if len(out) >= limit:
            break
    return out


def note_tool_result(result, turn: Optional[dict] = None) -> None:
    """Remember the links a tool returned in a dedicated bot's turn, for that turn's chat. Called by the hub after
    every successful call. The owner's own turns are not recorded: their tools may return private links that a bot
    answering strangers must not be able to fetch. Never raises."""
    try:
        if turn is None:
            import turn_context
            turn = turn_context.current()
        if not turn or turn.get("la_chu"):
            return
        keys = _chat_keys(turn.get("chat_id"))
        text = result if isinstance(result, str) else repr(result)
        if not keys or text.startswith("ERROR:"):
            return
        now = time.time()
        urls = links_in(text)
        if urls:
            with _remote_lock:
                for url in urls:
                    _remote.append((keys, url, now))
    except Exception:       # noqa: BLE001 - remembering must never cost the tool call
        pass


def remote_allowed(url: str, chat_id, extra: Iterable[str] = ()) -> bool:
    """True when a tool of this chat's bot turn returned `url` within REMOTE_TTL_S, or `extra` (links of the documents
    looked up for this turn) holds it."""
    url = str(url or "").strip()
    if not url:
        return False
    if url in set(extra or ()):
        return True
    keys = _chat_keys(chat_id)
    if not keys:
        return False
    cutoff = time.time() - REMOTE_TTL_S
    with _remote_lock:
        return any(u == url and t >= cutoff and (k & keys) for k, u, t in _remote)


def forget_remote() -> None:
    """Tests only: drop every remembered link."""
    with _remote_lock:
        _remote.clear()


def _public_host(host: str, port: int) -> bool:
    """Every address `host` resolves to is a public one (no loopback, LAN, link-local...)."""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError):
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(str(info[4][0]).split("%", 1)[0])
        except ValueError:
            return False
        if not ip.is_global:
            return False
    return True


def _url_ok(url: str) -> bool:
    try:
        p = urlsplit(url)
        port = p.port or (443 if p.scheme == "https" else 80)
    except ValueError:
        return False
    if p.scheme not in ("http", "https") or not p.hostname or p.username is not None or p.password is not None:
        return False
    return _public_host(p.hostname, port)


def cache_dir() -> Path:
    from config import STATE_DIR
    return Path(STATE_DIR) / "bot-image-cache"


def fetch_remote(url: str) -> str:
    """Download one web image into the cache and return its path, or "" when it is not a public image within
    MAX_BYTES. A file fetched before (same link) is reused."""
    import httpx
    d = cache_dir()
    stem = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
    for ext in set(_CT_EXT.values()):
        old = d / (stem + ext)
        if old.is_file() and old.stat().st_size > 0:
            return str(old)
    cur = url
    try:
        with httpx.Client(timeout=FETCH_TIMEOUT_S, follow_redirects=False,
                          headers={"User-Agent": "Mozilla/5.0 (Javis bot image)"}) as client:
            for _ in range(FETCH_REDIRECTS + 1):
                if not _url_ok(cur):
                    return ""
                with client.stream("GET", cur) as r:
                    if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                        cur = urljoin(cur, r.headers["location"])
                        continue
                    if r.status_code != 200:
                        return ""
                    ctype = str(r.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
                    ext = _CT_EXT.get(ctype)
                    if not ext:
                        return ""
                    size = int(r.headers.get("content-length") or 0)
                    if size > MAX_BYTES:
                        return ""
                    buf = bytearray()
                    for chunk in r.iter_bytes():
                        buf.extend(chunk)
                        if len(buf) > MAX_BYTES:
                            return ""
                    if not buf:
                        return ""
                    d.mkdir(parents=True, exist_ok=True)
                    path = d / (stem + ext)
                    tmp = path.with_suffix(ext + ".part")
                    tmp.write_bytes(bytes(buf))
                    os.replace(tmp, path)
                    return str(path)
    except Exception:       # noqa: BLE001 - an image that cannot be fetched is simply not sent
        return ""
    return ""


def channel_sends_files(channel: str) -> bool:
    """Whether the channel's transport sends a reply's `files` (`nang_luc.gui_file`)."""
    spec = channels.spec(str(channel or ""))
    return bool(spec and spec.nl("gui_file"))


def _resolve(raw: str, brain_root: str) -> str:
    """Absolute path of an allowed image for one Markdown target, else ""."""
    raw = str(raw or "").strip()
    if not raw:
        return ""
    if raw.lower().startswith("file:"):
        raw = re.sub(r"^file:(//[^/]*)?", "", raw, flags=re.IGNORECASE)
        if re.match(r"^/[A-Za-z]:[\\/]", raw):
            raw = raw[1:]
    try:
        root = Path(brain_root).resolve()
    except (OSError, ValueError):
        return ""
    for variant in dict.fromkeys((raw, unquote(raw))):
        cand = channel_context._vault_markdown_candidate(variant, str(root))
        if not cand:
            continue
        try:
            p = Path(cand).resolve()
            p.relative_to(root)                 # a symlink pointing outside the brain fails here
        except (OSError, ValueError):
            continue
        if p.suffix.lower() not in IMAGE_EXTS or not p.is_file():
            continue
        try:
            if p.stat().st_size > MAX_BYTES:
                continue
        except OSError:
            continue
        return str(p)
    return ""


def pick(text: str, brain_root: str, chat_id=None, doc_links: Iterable[str] = ()) -> Tuple[str, List[dict]]:
    """Split the images the Agent asked to send out of `text`.

    Returns `(text without those images, [{"path": absolute path, "caption": alt text}])`. A web image is taken only
    when `remote_allowed` (a tool of this chat's turn returned it, or `doc_links` holds it) and it downloads as an
    image. Images that fail a gate and links that are not images are left in the text untouched. A web image is
    fetched here, so call this off the event loop."""
    if not text or not brain_root or "![" not in text:
        return text or "", []
    files: List[dict] = []
    seen = set()
    docs = set(doc_links or ())

    def repl(m):
        if m.group(1) != "!" or len(files) >= MAX_IMAGES:
            return m.group(0)
        target = channel_context._md_link_target(m)
        if re.match(r"^https?://", str(target or "").strip(), re.IGNORECASE):
            url = str(target).strip()
            path = fetch_remote(url) if remote_allowed(url, chat_id, docs) else ""
        else:
            path = _resolve(target, brain_root)
        if not path:
            return m.group(0)
        key = os.path.normcase(path)
        if key not in seen:
            seen.add(key)
            files.append({"path": path, "caption": (m.group(2) or "").strip()[:200]})
        return ""

    cleaned = channel_context._MD_LINK_RE.sub(repl, text)
    if not files:
        return text, []
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip(), files
