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
read tool of this very chat's bot turn returned (`note_tool_result`, called by the hub and the plugin host), or that
the documents looked up for this turn contain, and that no customer ever wrote: a history read hands a customer's own
words back as a tool result, so the inbox is checked too. A link the model made up is never fetched. The fetch goes to
a vetted public address on port 80 or 443 (pinned, so a DNS answer cannot change between the check and the connect;
every redirect vetted again), must answer an image of at most `MAX_BYTES` within `PICK_DEADLINE_S`, and lands in a
pruned cache under the state folder, not in the brain.
"""
from __future__ import annotations

import hashlib
import ipaddress
import os
import re
import secrets
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
               "a file in your documents (path from their root, e.g. attachments/product.jpg); a web image link written "
               "in the documents shown to you for this question; a web image link a tool of yours returned in this turn (a POS or product catalogue: "
               "search the product there and use its image link as returned). When asked for a picture and a tool "
               "could have one, look it up before answering. Never make up a path or a link, and never use a link the "
               "customer typed. If no source has a picture, say plainly that you cannot send one right now; never "
               "promise to send it later.")


REMOTE_TTL_S = 1800            # a link a tool returned stays sendable this long (a bot turn is far shorter)
REMOTE_MAX = 4000              # links remembered at most, all chats together
REMOTE_PER_RESULT = 200        # links taken from one tool result
REMOTE_SCAN_CHARS = 400_000    # characters of one tool result searched for links
FETCH_TIMEOUT_S = 15           # one connect or read
PICK_DEADLINE_S = 20           # every web image of one reply together: the customer is waiting for it
FETCH_REDIRECTS = 3
FETCH_PORTS = (None, 80, 443)  # no other port, so a link cannot knock on a service that only listens elsewhere
CACHE_MAX_FILES = 300
CACHE_MAX_AGE_S = 7 * 86400
_URL_RE = re.compile(r"https?://[^\s\"'<>()\[\]{}\\|^`]+", re.IGNORECASE)
_URL_TAIL = ".,;:!?*_~"
# JSON writers that escape what a link holds (PHP `\/`, Go `\u0026`): read the link as the model will write it.
_JSON_ESCAPES = (("\\/", "/"), ("\\u0026", "&"), ("\\u003d", "="), ("\\u003D", "="), ("\\u003f", "?"),
                 ("\\u003F", "?"))
_CT_EXT = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
_remote_lock = threading.Lock()
_remote: deque = deque(maxlen=REMOTE_MAX)     # (chat keys, url, time)


def _chat_keys(chat) -> frozenset:
    import delivery_ledger
    return delivery_ledger.chat_keys(chat)


def links_in(text, limit: int = REMOTE_PER_RESULT) -> List[str]:
    """The http(s) links in `text`, trailing punctuation dropped, in order, without repeats."""
    raw = str(text or "")[:REMOTE_SCAN_CHARS]
    for a, b in _JSON_ESCAPES:
        raw = raw.replace(a, b)
    out: List[str] = []
    for m in _URL_RE.finditer(raw):
        url = m.group(0).rstrip(_URL_TAIL)
        if len(url) > 2000 or url in out:
            continue
        out.append(url)
        if len(out) >= limit:
            break
    return out


def _args_text(args) -> str:
    try:
        import json
        return json.dumps(args, ensure_ascii=False, default=str)
    except Exception:       # noqa: BLE001
        return str(args)


def note_tool_result(result, args=None, turn: Optional[dict] = None) -> None:
    """Remember the links a READ tool returned in a dedicated bot's turn, for that turn's chat. The hub and the plugin
    host call it after each successful read. Never raises.

    What is not recorded, because a customer could have put it there:
      - a link that is also in the call's arguments (a search that echoes its query);
      - anything outside a bot's turn (`bot_id` is set by the host only for a bot turn, never by the model): the
        owner's own turns and jobs may return private links a bot answering strangers must not reach.
    Links of the customers' own messages, which a history or inbox read returns, are refused later by `pick`
    (`_customer_wrote`), wherever they were recorded."""
    try:
        if turn is None:
            import turn_context
            turn = turn_context.current()
        if not turn or turn.get("la_chu") or not turn.get("bot_id"):
            return
        keys = _chat_keys(turn.get("chat_id"))
        text = result if isinstance(result, str) else repr(result)
        if not keys or text.startswith("ERROR:"):
            return
        given = set(links_in(_args_text(args))) if args else set()
        urls = [u for u in links_in(text) if u not in given and not any(g and g in u for g in given)]
        if urls:
            now = time.time()
            with _remote_lock:
                for url in urls:
                    _remote.append((keys, url, now))
    except Exception:       # noqa: BLE001 - remembering must never cost the tool call
        pass


def remote_allowed(url: str, chat_id, extra: Iterable[str] = ()) -> bool:
    """True when a read tool of this chat's bot turn returned `url` within REMOTE_TTL_S, or `extra` (links of the
    documents looked up for this turn) holds it."""
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


def _link_forms(url: str) -> List[str]:
    """The forms one link takes in stored text: as written, HTML-unescaped, percent-decoded, and with the scheme and
    host in lower case (a read tool may hand a customer's link back in any of them)."""
    import html
    forms = [url, html.unescape(url), unquote(url), unquote(html.unescape(url))]
    try:
        p = urlsplit(url)
        if p.scheme and p.netloc:
            forms.append(p._replace(scheme=p.scheme.lower(), netloc=p.netloc.lower()).geturl())
    except ValueError:
        pass
    return [f for f in dict.fromkeys(forms) if f]


def _customer_wrote(url: str, turn_text: str = "") -> bool:
    """A customer wrote or sent this link: in the message being answered, or in any customer message of the inbox,
    text or metadata (a history read hands a customer's words and photos back as a tool result). Fails closed."""
    forms = _link_forms(url)
    said = str(turn_text or "")
    if any(f in said for f in forms) or any(f in unquote(said) for f in forms):
        return True
    try:
        import conversations
        return conversations.customer_wrote(*forms)
    except Exception:       # noqa: BLE001
        return True


def _public_ip(host: str, port: int) -> str:
    """The address to connect to when EVERY address `host` resolves to is public, else "". Connecting to exactly this
    address (`fetch_remote`) closes the gap a short-lived DNS answer would open between the check and the connect."""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError):
        return ""
    if not infos:
        return ""
    for info in infos:
        try:
            ip = ipaddress.ip_address(str(info[4][0]).split("%", 1)[0])
        except ValueError:
            return ""
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global:
            return ""
    return str(infos[0][4][0]).split("%", 1)[0]


def _vet(url: str) -> str:
    """The vetted address to connect to for `url`, or "" when the link must not be fetched: http(s) only, ports 80
    and 443 only, no user name or password, a public address."""
    try:
        p = urlsplit(url)
        port = p.port
    except ValueError:
        return ""
    if p.scheme not in ("http", "https") or not p.hostname or p.username is not None or p.password is not None:
        return ""
    if port not in FETCH_PORTS:
        return ""
    return _public_ip(p.hostname, port or (443 if p.scheme == "https" else 80))


def cache_dir() -> Path:
    from config import STATE_DIR
    return Path(STATE_DIR) / "bot-image-cache"


CACHE_KEEP_YOUNG_S = 600       # a file this fresh is never pruned: a reply may be about to send it


def _prune_cache(d: Path) -> None:
    """Keep the cache to CACHE_MAX_FILES files and CACHE_MAX_AGE_S days. Leftover partial files go once they are
    stale; nothing younger than CACHE_KEEP_YOUNG_S is touched (another reply may be writing or sending it)."""
    try:
        now = time.time()
        files = sorted((p for p in d.iterdir() if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)
        for i, p in enumerate(files):
            age = now - p.stat().st_mtime
            if age < CACHE_KEEP_YOUNG_S:
                continue
            if i >= CACHE_MAX_FILES or age > CACHE_MAX_AGE_S or p.name.endswith(".part"):
                p.unlink(missing_ok=True)
    except OSError:
        pass


def fetch_remote(url: str, deadline: Optional[float] = None) -> str:
    """Download one web image into the cache and return its path, or "" when it is not a public image within
    MAX_BYTES or the time runs out (`deadline`, a `time.monotonic()` value). A link fetched before is reused."""
    import httpx
    import web_watch
    deadline = deadline if deadline is not None else time.monotonic() + PICK_DEADLINE_S
    d = cache_dir()
    stem = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
    for ext in set(_CT_EXT.values()):
        old = d / (stem + ext)
        if old.is_file() and old.stat().st_size > 0:
            try:
                os.utime(old)       # in use again: keep it out of the next prune
            except OSError:
                pass
            return str(old)
    cur = url
    try:
        with httpx.Client(timeout=FETCH_TIMEOUT_S, follow_redirects=False) as client:
            for _ in range(FETCH_REDIRECTS + 1):
                ip = _vet(cur)
                left = deadline - time.monotonic()
                if not ip or left <= 0:
                    return ""
                call, headers, ext_ = web_watch.pinned(cur, ip)
                headers = dict(headers, **{"User-Agent": "Mozilla/5.0 (Javis bot image)"})
                with client.stream("GET", call, headers=headers, extensions=ext_,
                                   timeout=min(FETCH_TIMEOUT_S, max(0.5, left))) as r:
                    if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                        cur = urljoin(cur, r.headers["location"])
                        continue
                    if r.status_code != 200:
                        return ""
                    ctype = str(r.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
                    ext = _CT_EXT.get(ctype)
                    if not ext:
                        return ""
                    try:
                        size = int(r.headers.get("content-length") or 0)
                    except ValueError:
                        size = 0
                    if size > MAX_BYTES:
                        return ""
                    buf = bytearray()
                    for chunk in r.iter_bytes():
                        buf.extend(chunk)
                        if len(buf) > MAX_BYTES or time.monotonic() > deadline:
                            return ""
                    if not buf:
                        return ""
                    d.mkdir(parents=True, exist_ok=True)
                    _prune_cache(d)
                    path = d / (stem + ext)
                    tmp = path.with_name(f"{path.name}.{secrets.token_hex(6)}.part")    # one per writer
                    try:
                        tmp.write_bytes(bytes(buf))
                        os.replace(tmp, path)
                    finally:
                        tmp.unlink(missing_ok=True)
                    return str(path)
    except Exception:       # noqa: BLE001 - an image that cannot be fetched is simply not sent
        return ""
    return ""


def has_web_image(text: str) -> bool:
    """The reply embeds at least one web image, so `pick` may download: only then is it worth a thread. Decided by
    the very parser `pick` uses, so a quoted or bracketed target cannot slip past and download on the event loop."""
    text = str(text or "")
    if "![" not in text or "://" not in text:
        return False
    for m in channel_context._MD_LINK_RE.finditer(text):
        if m.group(1) == "!" and re.match(r"^https?://", str(channel_context._md_link_target(m) or "").strip(),
                                          re.IGNORECASE):
            return True
    return False


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


def pick(text: str, brain_root: str, chat_id=None, doc_links: Iterable[str] = (),
         turn_text: str = "") -> Tuple[str, List[dict]]:
    """Split the images the Agent asked to send out of `text`.

    Returns `(text without those images, [{"path": absolute path, "caption": alt text}])`. A web image is taken only
    when `remote_allowed` (a read tool of this chat's turn returned it, or `doc_links` holds it), no customer wrote it
    (`turn_text` is the message being answered), and it downloads as an image. Images that fail a gate and links that are not images are left in the text untouched. A web image is
    fetched here, so call this off the event loop."""
    if not text or not brain_root or "![" not in text:
        return text or "", []
    files: List[dict] = []
    seen = set()
    docs = set(doc_links or ())
    deadline = time.monotonic() + PICK_DEADLINE_S

    def repl(m):
        if m.group(1) != "!" or len(files) >= MAX_IMAGES:
            return m.group(0)
        target = channel_context._md_link_target(m)
        if re.match(r"^https?://", str(target or "").strip(), re.IGNORECASE):
            url = str(target).strip()
            ok = remote_allowed(url, chat_id, docs) and not _customer_wrote(url, turn_text)
            path = fetch_remote(url, deadline) if ok else ""
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
