"""Claude Code answers stream piece by piece, like ChatGPT (0.438.4).

Why: `claude_sdk_engine.map_message` only turns a COMPLETE AssistantMessage into a `text` event, so the dashboard got
a whole paragraph at once, while Codex sends every `item/agentMessage/delta` as its own small `text` event. The
engine already asks Claude Code for partial messages (`include_partial_messages`, turned on together with
`include_hook_events` for the completion watch), so the deltas arrive as StreamEvent and were simply dropped.

How: claude_sdk_engine.py is pinned by the native qualification evidence (see plan_limits.cai_vao_claude_sdk), so
it is not edited. This wraps its module-level `map_message` the same way the cache counter and the plan meter do:
- a root `text_delta` StreamEvent becomes a `text` event with just that piece;
- the complete AssistantMessage that follows drops the text it would repeat (exact match with what was streamed),
  or keeps only the part that never streamed (prefix match). Anything that does not match passes through as before,
  so a lost delta never loses words. Tool calls, results and the final event are untouched.
- sub-agent stream events (parent_tool_use_id set) are left alone: their AssistantMessage text passes as before.

Nothing changes when the binary sends no StreamEvent (old CLI, the bundled one): there is nothing to drop.
`JAVIS_CLAUDE_STREAM_TEXT=0` turns it off.

2026-11-16: a new text block after earlier text of the same turn starts a new paragraph (`text_breaks.lead`). The
text written before a tool call and the text written after it used to reach the chat glued together ("... cần đăng
nhập.Xong mục 3"). A block is new at its `content_block_start`, at its first delta when no start came, and when a
complete AssistantMessage brings text that never streamed. The rest of a block that streamed only in part is not.
"""
from __future__ import annotations

import os
import threading

import text_breaks

_LOCK = threading.Lock()
# session_id -> {"msg": message id of the root message streaming now, "blocks": {index: text so far},
#                 "tail": how this turn's text ends so far, "fresh": indexes started but with no text yet}
_STATE: dict = {}
_MAX_SESSIONS = 256


def bat() -> bool:
    return (os.environ.get("JAVIS_CLAUDE_STREAM_TEXT") or "1").strip().lower() not in ("0", "false", "off", "no")


def _state(sid: str) -> dict:
    st = _STATE.get(sid)
    if st is None:
        if len(_STATE) >= _MAX_SESSIONS:
            _STATE.pop(next(iter(_STATE)))
        st = _STATE[sid] = {"msg": None, "blocks": {}, "tail": "", "fresh": set()}
    return st


def _piece(st: dict, piece: str, new: bool) -> dict:
    """The text event for `piece`. A new block after earlier text of this turn starts on a new paragraph."""
    before = text_breaks.lead(st["tail"], piece) if new else ""
    st["tail"] = (st["tail"] + before + piece)[-4:]
    return {"type": "text", "content": before + piece}


def _on_stream(msg) -> list:
    if getattr(msg, "parent_tool_use_id", None):
        return []
    ev = getattr(msg, "event", None) or {}
    if not isinstance(ev, dict):
        return []
    kind = ev.get("type")
    sid = str(getattr(msg, "session_id", "") or "")
    out = []
    with _LOCK:
        if kind == "message_start":
            st = _state(sid)
            st["msg"] = (ev.get("message") or {}).get("id")
            st["blocks"] = {}
            st["fresh"] = set()
        elif kind == "content_block_start":
            block = ev.get("content_block") or {}
            if block.get("type") == "text":
                st = _state(sid)
                i = ev.get("index", 0)
                piece = str(block.get("text") or "")
                st["blocks"][i] = piece
                if piece:
                    out.append(_piece(st, piece, True))
                else:
                    st["fresh"].add(i)
        elif kind == "content_block_delta":
            delta = ev.get("delta") or {}
            if delta.get("type") == "text_delta":
                piece = str(delta.get("text") or "")
                if piece:
                    st = _state(sid)
                    blocks = st["blocks"]
                    i = ev.get("index", 0)
                    new = i in st["fresh"] or i not in blocks
                    st["fresh"].discard(i)
                    blocks[i] = blocks.get(i, "") + piece
                    out.append(_piece(st, piece, new))
    return out


def _on_assistant(msg, events: list) -> list:
    if getattr(msg, "parent_tool_use_id", None):
        return events
    sid = str(getattr(msg, "session_id", "") or "")
    with _LOCK:
        st = _STATE.get(sid)
        streamed = bool(st and st["blocks"])
        mid = getattr(msg, "message_id", None)
        if streamed and mid and st["msg"] and mid != st["msg"]:
            streamed = False     # a different message: what streamed belongs elsewhere
        st = st or _state(sid)
        pending = [st["blocks"][k] for k in sorted(st["blocks"])] if streamed else []
        pending = [p for p in pending if p]
        out = []
        for ev in events:
            if not (isinstance(ev, dict) and ev.get("type") == "text"):
                out.append(ev)
                continue
            content = str(ev.get("content") or "")
            hit = next((p for p in pending if content == p or content.startswith(p)), None)
            if hit is None:
                out.append({**ev, **_piece(st, content, True)})   # text that never streamed: a block of its own
                continue
            pending.remove(hit)
            rest = content[len(hit):]
            if rest:
                out.append({**ev, **_piece(st, rest, False)})    # the end of a block that streamed in part
        if streamed:
            # What was matched is consumed: Claude Code may send one AssistantMessage per block with the same id.
            st["blocks"] = {i: t for i, t in st["blocks"].items() if t in pending}
    return out


def _on_result(msg) -> None:
    sid = str(getattr(msg, "session_id", "") or "")
    with _LOCK:
        _STATE.pop(sid, None)


def _on_turn_start(msg) -> None:
    """A new turn begins (the `init` system message): nothing shown yet, so its first text needs no break."""
    data = getattr(msg, "data", None) or {}
    if getattr(msg, "subtype", "") == "init" and isinstance(data, dict):
        with _LOCK:
            _STATE.pop(str(data.get("session_id") or ""), None)


def cai_vao_claude_sdk() -> bool:
    """Install the wrapper on claude_sdk_engine.map_message. Idempotent across the whole wrapper chain."""
    import claude_sdk_engine as eng
    f = eng.map_message
    while f is not None:
        if getattr(f, "_stream_text", False):
            return True
        f = getattr(f, "__wrapped__", None)
    goc = eng.map_message

    def map_message(msg):
        out = goc(msg)
        try:
            name = type(msg).__name__
            if name == "SystemMessage":
                _on_turn_start(msg)
            elif name == "StreamEvent":
                # JAVIS_CLAUDE_STREAM_TEXT=0 stops the pieces; the paragraph breaks below still apply.
                return (out[0] + _on_stream(msg), out[1]) if bat() else out
            elif name == "AssistantMessage":
                return _on_assistant(msg, out[0]), out[1]
            elif name == "ResultMessage":
                _on_result(msg)
        except Exception:  # noqa: BLE001 - streaming is a nicety, never break a turn
            pass
        return out
    map_message._stream_text = True
    map_message.__wrapped__ = goc
    eng.map_message = map_message
    return True
