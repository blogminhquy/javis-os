"""What already reached a chat, so the end of a turn never sends it a second time (issues #1846 and #1851).

At the end of a turn the channel's transport sends the reply: its text, then the files it carries (the files a turn of
the owner wrote or named, `channel_context.collect_turn_files`; the images a bot's Agent embedded, `bot_images.pick`).
The turn may already have delivered some of that to the very same chat itself: a model that sends a photo with
`zalo_send_image` and then shows it in its reply, a model that sends its answer with `zalo_send_message` or
`inbox_reply` and then gives the same answer as its reply. The customer, or the owner, got everything twice.

PR #1846 (idea by tunganh0990) dropped, at the end of the turn, the paths given to tools NAMED like `zalo_send_image`.
This module does the same for every tool and every channel without knowing any tool by name. A delivery is recorded
where sends happen:

  - a tool call that may act outside (a hub tool not classed `read`, a plugin tool above `readonly`) and did not fail
    (`note_call`): the chat ids its arguments name (any short scalar value), the files they point to and the texts
    they carry. A call that names no chat is not a delivery to any chat;
  - the channel registry's `gui` / `send_file` (the inbox, the `inbox_reply` tool) and the Telegram send-file endpoint
    (`note`), which know their chat.

The end of a turn asks `trim_reply` for ITS chat and the time the turn started: a file already delivered (same file by
path, or the same bytes under another name) is left out, and a text identical to one already delivered (compared
the way a chat app shows it: no Markdown, no mention markup, spaces folded, case ignored) is not sent again.

Memory only and bounded: an entry lives TTL_S seconds and at most MAX_ENTRIES are kept. A restart forgets, and the
worst case is the old behaviour (one duplicate). Never raises: recording or checking must never cost a send.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Iterable, List, Optional, Tuple

TTL_S = 1800                 # a turn that runs longer than this does not exist in practice (tool timeouts are shorter)
MAX_ENTRIES = 2000
MAX_VALUES = 40              # chat ids, files or texts taken from one tool call
MAX_DEPTH = 3                # how deep the arguments of a tool call are searched
MAX_CHAT_ID = 200            # a value longer than this is not a chat id
MAX_HASH_BYTES = 50 * 1024 * 1024   # files above this are matched by path only

_lock = threading.Lock()
_entries: deque = deque(maxlen=MAX_ENTRIES)
_CONTROL = re.compile(r"<!--[\s\S]*?-->")
_SPLIT_MARK = re.compile(r"\[\s*tach_tin\s*\]", re.I)


def chat_keys(chat: Any) -> frozenset:
    """The forms one chat id takes: as given, and without the prefix Javis puts in front of it (`zalo:`, `slack:`, the
    page of a Messenger chat), since a tool names the chat by the platform's raw id."""
    s = str(chat if chat is not None else "").strip()
    if not s or len(s) > MAX_CHAT_ID or any(c.isspace() for c in s):
        return frozenset()
    out = {s}
    if ":" in s:
        out.add(s.split(":", 1)[1])
        out.add(s.rsplit(":", 1)[1])
    return frozenset(x for x in out if x)


def norm_text(text: Any) -> str:
    """A text the way a chat app shows it, for comparing two sends: no control block, no split marker, no Markdown,
    no Zalo mention markup, spaces folded, case ignored."""
    s = _SPLIT_MARK.sub("\n", _CONTROL.sub(" ", str(text or "")))
    try:
        import zalo_markup
        s = zalo_markup.plain_text(zalo_markup.strip_mention_markup(s))
    except Exception:      # noqa: BLE001 - compare the raw text rather than nothing
        pass
    return " ".join(s.split()).casefold()


def _text_key(text: Any) -> str:
    n = norm_text(text)
    return hashlib.sha256(n.encode("utf-8")).hexdigest() if n else ""


def _path_key(path: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def _file_hash(path: str) -> str:
    try:
        p = Path(path)
        if not p.is_file() or p.stat().st_size > MAX_HASH_BYTES:
            return ""
        h = hashlib.sha256()
        with p.open("rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()
    except OSError:
        return ""


def _as_file(value: str, base_dir: Optional[str]) -> str:
    """The existing file a string argument points to (absolute, `file://`, or relative to `base_dir`), or ""."""
    s = str(value or "").strip()
    if not s or len(s) > 4096 or "\n" in s:
        return ""
    if s.startswith("file://"):
        s = s[len("file://"):]
    try:
        p = Path(s).expanduser()
        if not p.is_absolute():
            if not base_dir:
                return ""
            p = Path(base_dir) / p
        return os.path.abspath(str(p)) if p.is_file() else ""
    except (OSError, ValueError):
        return ""


def _scalars(value: Any, depth: int = 0) -> Iterable[str]:
    if depth > MAX_DEPTH:
        return
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (str, int)):
        yield str(value)
    elif isinstance(value, dict):
        for v in list(value.values())[:100]:
            yield from _scalars(v, depth + 1)
    elif isinstance(value, (list, tuple)):
        for v in list(value)[:100]:
            yield from _scalars(v, depth + 1)


def _entry(chats: Iterable[str], files: Iterable[str], texts: Iterable[str], at: Optional[float]) -> Optional[dict]:
    keys: set = set()
    for c in chats:
        keys |= chat_keys(c)
    paths, hashes = set(), set()
    for f in files:
        if f:
            paths.add(_path_key(f))
            h = _file_hash(f)
            if h:
                hashes.add(h)
    said = {k for k in (_text_key(t) for t in texts) if k}
    if not keys or not (paths or hashes or said):
        return None
    return {"at": time.time() if at is None else float(at), "chats": frozenset(keys),
            "paths": frozenset(paths), "hashes": frozenset(hashes), "texts": frozenset(said)}


def _keep(entry: Optional[dict]) -> None:
    if entry is None:
        return
    with _lock:
        _entries.append(entry)
        now = time.time()
        while _entries and now - _entries[0]["at"] > TTL_S:
            _entries.popleft()


def note(chat: Any, files: Iterable[str] = (), texts: Iterable[str] = (), at: Optional[float] = None) -> None:
    """Record that `files` (paths) and `texts` just reached `chat`. For a send path that knows its chat."""
    try:
        _keep(_entry([str(chat or "")], [str(f) for f in files or () if f], [str(t) for t in texts or () if t], at))
    except Exception:      # noqa: BLE001 - a record that fails only means the old behaviour
        pass


def failed(result: Any) -> bool:
    """True when a tool's result says nothing went out: `ERROR: ...`, or a JSON object with `ok`/`success` false or
    an `error`."""
    s = result if isinstance(result, str) else ""
    if s.lstrip().startswith("ERROR"):
        return True
    data = result
    if isinstance(result, str):
        t = result.strip()
        if not t.startswith("{"):
            return False
        try:
            data = json.loads(t)
        except ValueError:
            return False
    return isinstance(data, dict) and (data.get("ok") is False or data.get("success") is False
                                       or bool(data.get("error")) and data.get("ok") is not True)


def note_call(args: Any, result: Any = "", base_dir: Optional[str] = None, at: Optional[float] = None) -> None:
    """Record what one tool call that may act outside delivered, if it did not fail: every short scalar argument may
    be the chat it went to, every argument that points to an existing file is a file it carried, every text argument
    a text it carried. Read nothing into it beyond that: the end of a turn only drops a file or a text when the SAME
    chat the turn answers is among the arguments."""
    try:
        if failed(result) or not isinstance(args, dict):
            return
        values = list(_scalars(args))
        chats = [v.strip() for v in values if chat_keys(v)][:MAX_VALUES]
        files, texts = [], []
        for v in values:
            f = _as_file(v, base_dir)
            if f:
                files.append(f)
            elif v.strip():
                texts.append(v)       # a one-word reply ("ok") is chat-id shaped too: it counts as both
        _keep(_entry(chats, files[:MAX_VALUES], texts[:MAX_VALUES], at))
    except Exception:      # noqa: BLE001
        pass


def _since(chat: Any, since: float) -> Tuple[set, set, set]:
    keys = chat_keys(chat)
    paths, hashes, texts = set(), set(), set()
    if not keys:
        return paths, hashes, texts
    with _lock:
        for e in _entries:
            if e["at"] >= since and e["chats"] & keys:
                paths |= e["paths"]
                hashes |= e["hashes"]
                texts |= e["texts"]
    return paths, hashes, texts


def _file_path(f: Any) -> str:
    return str((f.get("path") if isinstance(f, dict) else f) or "")


def trim_reply(chat: Any, since: float, text: Any = "", files: Any = None) -> Tuple[bool, list]:
    """`(text_already_sent, files_left)` for the reply a turn that started at `since` is about to send to `chat`.

    `files` keeps its shape (paths or `{"path", ...}` dicts); a file goes when the same file, or the same bytes, was
    delivered to this chat since `since`. `text_already_sent` is True when the whole text was. Never raises: on an
    error everything is sent, as before."""
    items = list(files or [])
    try:
        paths, hashes, texts = _since(chat, float(since or 0))
        if not (paths or hashes or texts):
            return False, items
        left = []
        for f in items:
            p = _file_path(f)
            if p and (_path_key(p) in paths or (hashes and _file_hash(p) in hashes)):
                continue
            left.append(f)
        key = _text_key(text)
        return bool(key and key in texts), left
    except Exception:      # noqa: BLE001
        return False, items


def forget_all() -> None:
    """Tests."""
    with _lock:
        _entries.clear()
