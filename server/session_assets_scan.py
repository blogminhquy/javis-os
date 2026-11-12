"""Files and links mentioned in one conversation, read once and kept (2026-11-12).

Why it exists. `GET /sessions/{id}/assets` (the Info tab of a team, the documents drawer of a chat) used to read every
message of the conversation and run the path and link patterns over all of it on every call. Since 0.518.0 a team opens
with its Info tab showing, so every open of a team on a wide screen did that. Measured on a team with 3,000 messages
(9 million characters): 1.5 s per call, and while it ran the first page of messages took 370 ms instead of 7 ms, because
the scan is pure Python and holds the interpreter. A customer read it as "Team loads very slowly".

How. One entry per (conversation, brain root) keeps what the messages mention, plus the fingerprint of the messages it
was made from (`SessionStore.messages_fingerprint`: how many, the highest id, the newest message and a checksum of its
text; two index lookups and one message, so asking costs the same for a chat of ten messages or of fifty thousand).
A call compares the fingerprint first:

- the same: nothing is read again;
- only new messages after the highest id (the usual case): only those are read;
- anything else (a message deleted, edited or rewound): the conversation is read again from the start.

What is kept is what the TEXT says. Whether a file exists is asked on every call, by the route: a file made, moved or
deleted after its message must show the truth of now.

The order rules of the route are kept exactly: a file's label is the one of its first mention, its time the one of its
last, a link belongs to whoever sent it first. Each mention carries a key (ts, id, position in the message), so the
result is the same whether the messages came in one read or in many.
"""
from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

import channel_context

MAX_SESSIONS = 24          # entries kept; the one used longest ago goes first
# A full read of a long conversation is a second or more of pure Python on a worker thread. It holds the interpreter
# between its own steps, so every other request waited for it (measured on 3,000 messages: the first page of messages
# took up to 640 ms instead of 8 ms while the read ran). Every YIELD_EVERY messages the read sleeps YIELD_S, which
# hands the interpreter to whoever is waiting.
YIELD_EVERY = 25
YIELD_S = 0.003

_LOCK = threading.Lock()   # one scan at a time: three opens of a long team used to run three full scans side by side
_CACHE: "OrderedDict[Tuple[str, str], _Entry]" = OrderedDict()
_STATS = {"hits": 0, "appends": 0, "full": 0}


class _Entry:
    __slots__ = ("fp", "linked", "bare", "links")

    def __init__(self):
        self.fp = (0, 0, 0, 0)              # SessionStore.messages_fingerprint of the messages this was made from
        self.linked: Dict[str, dict] = {}   # markdown link targets: kept even when the file is gone
        self.bare: Dict[str, dict] = {}     # absolute paths in the prose: shown only while the file exists
        self.links: Dict[str, dict] = {}    # http(s) links


def _absorb(ent: _Entry, rows, broot: Path, in_brain: Callable[[Path, Path], Optional[Path]]) -> None:
    """Add the mentions of `rows` (id, role, content, ts) to `ent`. Adding a row twice changes nothing."""
    root = str(broot)
    seen: Dict[Tuple[str, str], Optional[Path]] = {}    # the same path comes back many times in a long conversation

    def resolve(kind: str, raw: str) -> Optional[Path]:
        k = (kind, raw)
        if k not in seen:
            if kind == "md":
                cand = channel_context._vault_markdown_candidate(raw, root)
                seen[k] = in_brain(broot, Path(cand)) if cand else None
            else:
                seen[k] = in_brain(broot, Path(raw))
        return seen[k]

    for n, r in enumerate(rows):
        if n and n % YIELD_EVERY == 0:
            time.sleep(YIELD_S)
        text = r[2] or ""
        if not text:
            continue
        mid, role, ts = int(r[0]), r[1] or "", r[3] or 0
        pos = 0
        for tg in channel_context.markdown_targets(text):
            pos += 1
            raw = tg["raw"]
            if "://" in raw or raw.startswith(("#", "mailto:", "data:", "tel:")):
                continue
            rp = resolve("md", raw)
            if not rp:
                continue
            key = (ts, mid, pos)
            cur = ent.linked.get(os.path.normcase(str(rp)))
            if cur is None:
                ent.linked[os.path.normcase(str(rp))] = {"p": rp, "first": key, "label": tg["nhan"],
                                                         "image": tg["hinh"], "last": key}
                continue
            if key < cur["first"]:
                cur.update(first=key, label=tg["nhan"], image=tg["hinh"])
            if key > cur["last"]:
                cur["last"] = key
        for raw in channel_context.extract_paths(text):
            pos += 1
            rp = resolve("bare", raw)
            if not rp:
                continue
            key = (ts, mid, pos)
            cur = ent.bare.get(os.path.normcase(str(rp)))
            if cur is None:
                ent.bare[os.path.normcase(str(rp))] = {"p": rp, "first": key, "last": key}
                continue
            if key < cur["first"]:
                cur["first"] = key
            if key > cur["last"]:
                cur["last"] = key
        for u in channel_context.extract_urls(text):
            pos += 1
            key = (ts, mid, pos)
            cur = ent.links.get(u)
            if cur is None or key < cur["first"]:
                ent.links[u] = {"url": u, "first": key, "ts": ts, "role": role}


def mentions(store: Any, session_id: str, broot: Path,
             in_brain: Callable[[Path, Path], Optional[Path]]) -> _Entry:
    """What the messages of `session_id` mention, for the brain rooted at `broot`. Reads only what changed.

    `store` gives `messages_fingerprint(session_id, upto_id=None)` and `messages_after(session_id, after_id)`;
    `in_brain(broot, path)` returns the normalized path when it lies inside the brain, else None."""
    key = (str(session_id), os.path.normcase(str(broot)))
    with _LOCK:
        ent = _CACHE.get(key)
        fp = tuple(store.messages_fingerprint(session_id))
        if ent is not None and ent.fp == fp:
            _STATS["hits"] += 1
        else:
            grown = (ent is not None and fp[0] >= ent.fp[0] and fp[1] >= ent.fp[1]
                     and tuple(store.messages_fingerprint(session_id, ent.fp[1])) == ent.fp)
            if not grown:
                ent = _Entry()
            _STATS["appends" if grown else "full"] += 1
            _absorb(ent, store.messages_after(session_id, ent.fp[1]), broot, in_brain)
            # The fingerprint taken BEFORE the read: a message that landed in between was read too, and is simply read
            # once more by the next call (see _absorb), instead of being missed.
            ent.fp = fp
            _CACHE[key] = ent
        _CACHE.move_to_end(key)
        while len(_CACHE) > MAX_SESSIONS:
            _CACHE.popitem(last=False)
        # A copy: the caller reads it outside the lock while another request may be adding to the entry.
        out = _Entry()
        out.fp = ent.fp
        out.linked = {k: dict(v) for k, v in ent.linked.items()}
        out.bare = {k: dict(v) for k, v in ent.bare.items()}
        out.links = {k: dict(v) for k, v in ent.links.items()}
        return out


def stats() -> dict:
    return dict(_STATS, sessions=len(_CACHE))


def forget(session_id: Optional[str] = None) -> None:
    """Drop the kept mentions of one conversation, or of all (tests)."""
    with _LOCK:
        if session_id is None:
            _CACHE.clear()
            return
        for k in [k for k in _CACHE if k[0] == str(session_id)]:
            del _CACHE[k]
