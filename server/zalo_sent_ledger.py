"""Messages Javis itself sent into a personal Zalo chat through a Zalo tool (issue #1775).

An engine that calls `zalo_send_message` (or another `zalo_send_*` tool: a link card, a tag, a file, an image) sends
as the Zalo account itself, so the read loop gets the message back as one of the account's own. Before this, every such
message was filed as the owner typing by hand: the Stats tab of the Chatbot page counted scheduled Zalo scans, admin
chat turns and reports to staff as manual replies (82 "manual" against 52 A.I. on an account nobody types on), and the
bot on duty stepped aside in that chat as if the owner had stepped in (`nhuong_tay_phut`).

The send is noted here just BEFORE it goes out, since javis-zalo can push the echo before the tool call returns: by the
hub for a connection tool (`mcp_hub._guard`) and by the plugin host for a pack tool (`plugins_host._make_call`). A send
that failed is forgotten again. The read loop (`zalo_personal_channel`) asks `take` before treating one of the
account's own messages as the owner's: a match is written to the inbox marked `MARK` (counted as A.I. by
`conversations.insights`) and starts no "owner typed" clock.

Bounded: an entry lives ECHO_TTL seconds, a chat keeps its last PER_CHAT entries, at most MAX_CHATS chats are held.
Memory only: a restart forgets, and the worst case is one message filed as the owner's, as before. Like zalo_markup
(its only import), it stays free of heavy imports: it runs on every Zalo send a model makes.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

import zalo_markup

ECHO_TTL = 900          # seconds an entry waits for its echo (same as the bot's own echo memory)
PER_CHAT = 20
MAX_CHATS = 500
MIN_INSIDE = 12         # a sent text found INSIDE a longer echo ("@Lan " added by a tag) counts from this length on
LINK_BLIND = 120        # a link card that comes back as a non-text message without its link (as LINK_ECHO_BLIND)
# What the inbox row of such a message carries. The same mark `routes.conversations.owner_reply` puts on a message an
# engine sent with `inbox_reply`, so one rule in the stats covers both.
MARK = {"tu_javis": True, "via": "tool"}

_NOT_A_MESSAGE = ("zalo_send_typing",)      # "typing..." puts nothing in the chat
_THREAD_KEYS = ("threadId", "thread_id", "threadID", "thread", "chatId", "chat_id", "groupId", "group_id")
_MEDIA_KEYS = ("paths", "files", "images", "image_paths", "file_paths", "attachments",
               "path", "file", "image", "image_path", "file_path")
_URL_KEYS = ("url", "link")
_ID_KEYS = ("messageId", "msgId", "message_id", "msg_id", "globalMsgId")

_lock = threading.Lock()
_sent: Dict[str, List[dict]] = {}       # chat id -> entries, oldest first


def is_send_tool(name: Any) -> bool:
    """True for a Zalo tool that puts a message in a chat."""
    n = str(name or "")
    return n.startswith("zalo_send") and n not in _NOT_A_MESSAGE


def _norm(text: Any) -> str:
    """Compared as Zalo shows it, the same way as the bot's own echoes (`zalo_personal_channel._chuan`)."""
    return " ".join(zalo_markup.plain_text(zalo_markup.strip_mention_markup(str(text or ""))).split())


def _first(args: dict, keys) -> str:
    for k in keys:
        v = args.get(k)
        if isinstance(v, (str, int)) and not isinstance(v, bool) and str(v).strip():
            return str(v).strip()
    return ""


def _media_count(tool: str, args: dict) -> int:
    n = 0
    for k in _MEDIA_KEYS:
        v = args.get(k)
        if isinstance(v, (list, tuple)):
            n += len([x for x in v if x])
        elif isinstance(v, str) and v.strip():
            n += 1
    if not n and ("image" in tool or "file" in tool):
        n = 1
    return n


def _parsed(result: Any) -> Any:
    if isinstance(result, (dict, list)):
        return result
    s = str(result or "").strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except ValueError:
        pass
    a, b = s.find("{"), s.rfind("}")
    if 0 <= a < b:
        try:
            return json.loads(s[a:b + 1])
        except ValueError:
            return None
    return None


def failed(result: Any) -> bool:
    """True when the tool says nothing went out: an error, or javis-zalo's `success: false`."""
    if isinstance(result, str) and result.lstrip().startswith("ERROR:"):
        return True
    data = _parsed(result)
    return isinstance(data, dict) and data.get("success") is False


def _ids_in(data: Any, depth: int = 0) -> List[str]:
    """Zalo message ids a send result names (top level and two levels down)."""
    out: List[str] = []
    if depth > 2:
        return out
    if isinstance(data, dict):
        for k in _ID_KEYS:
            v = data.get(k)
            if isinstance(v, (str, int)) and not isinstance(v, bool) and str(v).strip():
                out.append(str(v).strip())
        for v in data.values():
            if isinstance(v, (dict, list)):
                out += _ids_in(v, depth + 1)
    elif isinstance(data, list):
        for v in data[:20]:
            out += _ids_in(v, depth + 1)
    return out[:20]


def _alive(entries: List[dict], now: float) -> List[dict]:
    return [e for e in entries if now - e["at"] < ECHO_TTL and (e["text"] or e["url"] or e["media"] > 0)]


def note(account: str, tool: str, args: Any, now: Optional[float] = None) -> Optional[dict]:
    """Remember a send that is about to go out. `account` is the Zalo connection id, "" when the caller cannot tell
    (a pack tool): the entry then matches the chat on any account. Returns the entry (for `confirm`/`forget`), or None
    when this is not a message send or names no chat."""
    if not is_send_tool(tool) or not isinstance(args, dict):
        return None
    chat = _first(args, _THREAD_KEYS)
    if not chat:
        return None
    now = time.time() if now is None else float(now)
    text = _norm(next((args[k] for k in zalo_markup.TEXT_KEYS if isinstance(args.get(k), str) and args[k].strip()), ""))
    url = _first(args, _URL_KEYS).lower().rstrip("/")
    entry = {"at": now, "account": str(account or ""), "chat": chat,
             "text": text, "url": url, "media": _media_count(str(tool), args), "msg_ids": []}
    if not (entry["text"] or entry["url"] or entry["media"]):
        return None
    with _lock:
        entries = _alive(_sent.pop(chat, []), now)       # re-inserted last: the dict keeps the busiest chats
        entries.append(entry)
        _sent[chat] = entries[-PER_CHAT:]
        if len(_sent) > MAX_CHATS:
            for k in list(_sent)[:MAX_CHATS // 2]:
                _sent.pop(k, None)
    return entry


def forget(entry: Optional[dict]) -> None:
    """The send did not go out: drop what `note` remembered."""
    if not entry:
        return
    with _lock:
        entries = _sent.get(entry["chat"]) or []
        kept = [e for e in entries if e is not entry]
        if kept:
            _sent[entry["chat"]] = kept
        else:
            _sent.pop(entry["chat"], None)


def confirm(entry: Optional[dict], result: Any) -> None:
    """The send went out: keep the message ids Zalo gave it, the surest way to know its echo."""
    if not entry:
        return
    ids = _ids_in(_parsed(result))
    if ids:
        with _lock:
            entry["msg_ids"] = list(dict.fromkeys(entry["msg_ids"] + ids))


async def sending(account: str, tool: str, args: Any, call: Callable[[Any], Awaitable[Any]]) -> Any:
    """Run `call(args)`, a Zalo send, with its echo noted first and forgotten again when nothing went out. Any other
    tool is called straight through. Never changes what `call` returns or raises."""
    try:
        entry = note(account, tool, args)
    except Exception:      # noqa: BLE001 - the ledger must never cost the send itself
        entry = None
    if entry is None:
        return await call(args)
    try:
        result = await call(args)
    except BaseException:
        forget(entry)
        raise
    try:
        if failed(result):
            forget(entry)
        else:
            confirm(entry, result)
    except Exception:      # noqa: BLE001
        pass
    return result


def take(account: str, ev: dict, now: Optional[float] = None) -> bool:
    """True, and the matching part used up, when `ev` (one of the account's own messages, as the read loop normalised
    it) is the echo of something Javis sent with a Zalo tool. Matched by Zalo's message id, else by text (equal, or one
    starts with the other: a long text comes back cut), by the link of a link card, or, for an image or a file, by a
    send of that kind to the same chat. Never raises."""
    try:
        chat = str((ev or {}).get("external_chat_id") or "")
        if not chat:
            return False
        now = time.time() if now is None else float(now)
        account = str(account or "")
        kind = str(ev.get("message_type") or "text")
        msg_id = str(ev.get("external_message_id") or "")
        text = _norm(ev.get("text"))
        meta = ev.get("metadata") if isinstance(ev.get("metadata"), dict) else {}
        seen = (str(ev.get("text") or "") + " " + json.dumps(meta, ensure_ascii=False, default=str)).lower()
        with _lock:
            entries = _alive(_sent.get(chat) or [], now)
            hit = None
            for e in entries:
                if e["account"] not in ("", account):
                    continue
                if msg_id and msg_id in e["msg_ids"]:
                    hit = e
                elif kind != "text":
                    # An image or a file; a link card read as such only by its link, or just after it was sent.
                    if e["media"] > 0 or (e["url"] and (e["url"] in seen or now - e["at"] < LINK_BLIND)):
                        hit = e
                else:
                    t = e["text"]
                    if t and text and (t == text or text.startswith(t[:80]) or t.startswith(text[:80])
                                       or (len(t) >= MIN_INSIDE and t in text)):
                        hit = e
                    elif e["url"] and e["url"] in seen:
                        hit = e
                if hit is not None:
                    break
            if hit is None:
                if entries:
                    _sent[chat] = entries
                else:
                    _sent.pop(chat, None)
                return False
            if msg_id in hit["msg_ids"]:
                hit["msg_ids"].remove(msg_id)
            if kind == "text":
                hit["text"], hit["url"] = "", ""
            elif hit["media"] > 0:
                hit["media"] -= 1
            else:
                hit["url"] = ""         # a link card that came back as a non-text message
            entries = _alive(entries, now)
            if entries:
                _sent[chat] = entries
            else:
                _sent.pop(chat, None)
            return True
    except Exception:      # noqa: BLE001 - worst case the message is filed as the owner's, as before
        return False


def clear() -> None:
    """Forget everything (tests)."""
    with _lock:
        _sent.clear()
