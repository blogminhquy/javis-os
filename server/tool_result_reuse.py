"""Leaner tool results inside one API-engine turn, without losing anything the model could need (2026-11-17).

Every tool result stays in the conversation and is sent again on every later round of the tool loop, so a byte saved
in a result is saved once per remaining round. Two savings live here, both borrowed from code-graph tools that measured
where agent tokens go (GitNexus: pretty-printed JSON was 45% larger than compact JSON; its "context ledger" exists so an
agent never pays twice for a result it already holds).

1. Repeated results (`RepeatResults`). A model in a long loop sometimes calls the same tool with the same arguments
   again: it re-reads a file it already has, or lists the same data twice. The call still RUNS, exactly as asked, so no
   answer can rest on stale data. Only when the fresh result is byte-identical to the result of an earlier call of the
   same tool with the same arguments in this turn, and that earlier copy is still whole in the conversation, the model
   gets a one-line reference instead of the same text again. If the loop later trims that earlier copy to keep a long
   turn inside the context window (engine._gon_ket_qua_cu), `after_trim` writes the full text back into the newest
   reference, so the model holds exactly what it would have held without this module.

2. Compact JSON (`compact_json`). A result that is JSON throughout is re-written without indentation and with real
   characters instead of \\uXXXX escapes (Vietnamese text escaped that way costs several tokens per letter). The data
   is the same value. Tools whose output is the content of something a model may copy or edit exactly (files, terminal
   output, web pages, skills) are never touched, because a reformatted view would make an exact edit miss.

3. CLI engines (`lean_for_cli`, 2026-11-17). Claude Code, Codex and the other CLI engines run their own tool loop, so
   Javis cannot see their conversation. What it does see is every call they make to Javis's tools and connections
   through the hub over HTTP, with the turn's X-Javis-Turn key. There the same compact JSON applies, and repeats are
   kept per turn (`CliRepeatResults`) with a rule that does not need to see the conversation: a repeat right after a
   reference always comes back whole, because a model that asks again may have lost the earlier copy, and the record
   of a turn is dropped when the engine compacts its conversation (Claude Code's PreCompact hook through
   claude_result_reuse, Codex's contextCompaction item). Not touched: Claude Code's in-process plugin tools (their
   result could only be replaced through a hook whose expected shape Javis cannot check), Claude Code's own re-read
   of an unchanged file (it already answers "File unchanged since last read"), and terminal output.

All of it follows the owner's saving level: choosing Off ("send everything") on the Usage page turns it off, like tool
result shaping. `mcp.result_repeat_refs` (true/false/"auto") and JAVIS_RESULT_REPEAT_REFS=0|1 switch the first one
alone, which is how an A/B run measures it (tools/quality_eval.py).
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# Results shorter than this are always handed over whole: a reference would save almost nothing.
REPEAT_MIN_CHARS = 800
# Below this a result is not re-serialised: the saving is not worth parsing it.
COMPACT_MIN_CHARS = 1200
# A compact copy is used only when it is at least this much shorter.
COMPACT_MIN_GAIN = 0.05

# The content of something the model may quote, copy or edit exactly. Never re-formatted.
CONTENT_TOOLS = frozenset({
    "javis_read_file", "javis_write_file", "javis_edit_file", "javis_search_files", "javis_terminal",
    "javis_process", "javis_run_command", "javis_web_fetch", "javis_web_search", "javis_use_skill",
    "javis_query",
})

REFERENCE_MARK = "[Javis: identical to another result"
REFERENCE = (REFERENCE_MARK + " of this same {tool} call (same arguments) in this turn, which is kept in full in "
             "this conversation. Not repeated, to save tokens: use that result.]")

# A CLI engine's own conversation is out of Javis's sight, so its reference also says how to get the text back.
CLI_REFERENCE = (REFERENCE_MARK + " of this same {tool} call (same arguments) in this turn. Not repeated, to save "
                 "tokens: use that earlier result. If it is no longer in your context, call again with the same "
                 "arguments and the full result comes back.]")
CLI_MAX_TURNS = 256      # turn records kept at once (oldest dropped first)
CLI_MAX_ENTRIES = 512    # distinct results remembered per turn
CLI_TURN_TTL_S = 6 * 3600

_LOG_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="javis-reuse-log")
# The turn of the hub request being served (set by mcp_hub.handle_http from the X-Javis-Turn header).
HUB_TURN: contextvars.ContextVar = contextvars.ContextVar("javis_hub_reuse_turn", default=None)
_switch_cache = {"ts": 0.0, "on": True}


def _flag(value) -> bool | None:
    s = str(value).strip().lower()
    if value is True or s in ("1", "true", "on", "yes", "always"):
        return True
    if value is False or s in ("0", "false", "off", "no", "never"):
        return False
    return None


def _shaping_on() -> bool:
    """The owner's master switch for result savings (Off saving level turns it off)."""
    try:
        import tool_result_shaper
        return bool(tool_result_shaper.settings().get("on"))
    except Exception:  # noqa: BLE001 - unreadable settings: keep the default
        return True


def repeat_refs_on_cached() -> bool:
    """`repeat_refs_on`, re-read at most every few seconds: the hub asks on every tool call."""
    now = time.time()
    if now - _switch_cache["ts"] > 5:
        _switch_cache.update(ts=now, on=repeat_refs_on())
    return bool(_switch_cache["on"])


def repeat_refs_on() -> bool:
    """Whether repeated identical results become references in this turn."""
    env = _flag(os.getenv("JAVIS_RESULT_REPEAT_REFS", ""))
    if env is not None:
        return env
    try:
        import config
        own = _flag(((config.read_settings() or {}).get("mcp") or {}).get("result_repeat_refs", "auto"))
    except Exception:  # noqa: BLE001
        own = None
    return own if own is not None else _shaping_on()


def note_saving(kind: str, tool: str, raw_chars: int, sent_chars: int) -> None:
    """Add one saving to the hub's sizes log, the meter behind the Usage page line on tool results.

    Written on a worker thread: this runs inside the tool loop on the event loop."""
    rec = {"ts": datetime.now().isoformat(timespec="seconds"), "conn_id": "javis-turn",
           "label": "javis", "tool": str(tool or ""), "raw_chars": int(raw_chars), "sent_chars": int(sent_chars),
           "shape": kind}

    def write():
        try:
            import mcp_hub
            mcp_hub._sizes_append(rec)
        except Exception:  # noqa: BLE001 - a meter never fails a tool call
            pass
    try:
        _LOG_POOL.submit(write)
    except RuntimeError:   # interpreter shutting down
        pass


def compact_json(text: str, tool: str = "", on: bool | None = None) -> str:
    """`text` with its JSON re-written compactly, or `text` unchanged when that is not safe or not worth it."""
    if not isinstance(text, str) or len(text) < COMPACT_MIN_CHARS or tool in CONTENT_TOOLS:
        return text
    if on is None:
        on = _shaping_on()
    if not on:
        return text
    try:
        import tool_result_shaper
        parsed = tool_result_shaper.parse_document(text)
    except Exception:  # noqa: BLE001 - an optimisation never breaks a tool call
        return text
    if parsed is None:
        return text
    dumps = tool_result_shaper._dumps
    body = "\n".join(dumps(v) for v in parsed.data) if parsed.multi else dumps(parsed.data)
    compact = parsed.prefix + body
    if len(compact) > len(text) * (1 - COMPACT_MIN_GAIN):
        return text
    note_saving("compact", tool, len(text), len(compact))
    return compact


class RepeatResults:
    """One tool loop's memory of the results it handed a model (see the module docstring, part 1).

    Per call: `text_for` picks the text to send for a fresh result, the caller puts it into a conversation cell (a
    dict and a key), then `remember` records that cell. After every trim of old results, `after_trim`."""

    def __init__(self, enabled: bool | None = None):
        self.enabled = repeat_refs_on() if enabled is None else bool(enabled)
        # (tool, args key, digest of the text) -> {"cell": dict, "key": str, "text": str, "refs": [(dict, key, ref)]}
        # Keyed by the text too: when the same call later returns something else, the references to the earlier
        # text must keep pointing at that text, never at the newer one.
        self._entries: dict[tuple[str, str, str], dict] = {}
        self._pending = None   # the entry the last reference handed out points to, for `remember`
        self.reused = 0
        self.saved_chars = 0
        self.restored = 0

    @staticmethod
    def args_key(args) -> str:
        try:
            return json.dumps(args if args is not None else {}, sort_keys=True, ensure_ascii=False,
                              separators=(",", ":"), default=str)
        except (TypeError, ValueError):
            return repr(args)

    @classmethod
    def _key(cls, tool, args, text: str) -> tuple[str, str, str]:
        return (str(tool or ""), cls.args_key(args), hashlib.sha1(text.encode("utf-8", "replace")).hexdigest())

    @staticmethod
    def _whole(entry: dict) -> bool:
        current = entry["cell"].get(entry["key"])
        return isinstance(current, str) and current.startswith(entry["text"])

    def text_for(self, tool: str, args, text: str) -> str:
        """`text` itself, or a reference when an identical earlier result of this call is still whole."""
        self._pending = None
        if not self.enabled or not isinstance(text, str) or len(text) < REPEAT_MIN_CHARS:
            return text
        k = self._key(tool, args, text)
        entry = self._entries.get(k)
        if entry is None or entry["text"] != text or not self._whole(entry):
            return text
        self._pending = k
        ref = REFERENCE.format(tool=tool)
        self.reused += 1
        self.saved_chars += len(text) - len(ref)
        note_saving("repeat", tool, len(text), len(ref))
        return ref

    def remember(self, tool: str, args, cell: dict, key: str) -> None:
        """Record the conversation cell that now holds this call's result (call right after putting it there)."""
        if not self.enabled or not isinstance(cell, dict):
            return
        text = cell.get(key)
        if not isinstance(text, str):
            return
        if text.startswith(REFERENCE_MARK):
            entry = self._entries.get(self._pending) if self._pending else None
            self._pending = None
            if entry is not None:
                entry["refs"].append((cell, key, text))
            return
        self._pending = None
        if len(text) >= REPEAT_MIN_CHARS:
            self._entries[self._key(tool, args, text)] = {"cell": cell, "key": key, "text": text, "refs": []}

    def after_trim(self) -> int:
        """Give back the full text where a trim cut an original that references point to. Returns how many."""
        if not self.enabled:
            return 0
        restored = 0
        for entry in self._entries.values():
            if not entry["refs"] or self._whole(entry):
                continue
            cell, key, ref = entry["refs"].pop()   # the newest reference holds the full text from now on
            # Older references sit before the restored copy, where a later trim would cut it again: restoring into
            # them would only move the text back and forth. Without this module those copies would be cut too.
            entry["refs"].clear()
            current = cell.get(key)
            if not isinstance(current, str) or not current.startswith(ref):
                continue
            cell[key] = entry["text"] + current[len(ref):]
            entry.update(cell=cell, key=key)
            restored += 1
        self.restored += restored
        return restored


# ───────────────────────── CLI engines (part 3 of the module docstring) ─────────────────────────
class CliRepeatResults:
    """Repeats within one turn of an engine whose conversation Javis cannot see.

    Per result (same tool, same arguments, same text): the first copy goes out whole, a repeat becomes a reference,
    and a repeat right after a reference goes out whole again. So a model that lost the earlier copy (its engine
    compacted the conversation without telling us) gets it back with one more call, never a second reference."""

    def __init__(self):
        self._entries: "OrderedDict[tuple, str]" = OrderedDict()   # key -> "full" | "ref" (what went out last)
        self.reused = 0
        self.saved_chars = 0
        self.created = time.time()

    def text_for(self, tool: str, args, text: str) -> str:
        if not isinstance(text, str) or len(text) < REPEAT_MIN_CHARS:
            return text
        k = RepeatResults._key(tool, args, text)
        last = self._entries.get(k)
        self._entries[k] = "full" if last in (None, "ref") else "ref"
        self._entries.move_to_end(k)
        while len(self._entries) > CLI_MAX_ENTRIES:
            self._entries.popitem(last=False)
        if self._entries[k] == "full":
            return text
        ref = CLI_REFERENCE.format(tool=tool)
        self.reused += 1
        self.saved_chars += len(text) - len(ref)
        note_saving("repeat", tool, len(text), len(ref))
        return ref


_CLI_LEDGERS: "OrderedDict[str, CliRepeatResults]" = OrderedDict()
_CLI_LOCK = threading.Lock()


def turn_id_for_key(key) -> str | None:
    """One turn's identity from an X-Javis-Turn key: the key plus the expiry turn_context stamped when it gave the key
    to that turn. A warm engine keeps one lane key for its whole life and turn_lane re-attaches it to every new turn
    with a new stamp, so two turns of one warm process never share a record. None for a dead or unknown key."""
    k = str(key or "").strip()
    if not k:
        return None
    try:
        import turn_context as tc
        with tc._LOCK:
            ent = tc._KEYS.get(k)
    except Exception:  # noqa: BLE001
        return None
    if ent is None or ent[1] < time.time():
        return None
    return f"{k}:{ent[1]}"


def current_turn_ids() -> list[str]:
    """The identities of the turn running in this context, one per live key it issued or attached."""
    try:
        import turn_context as tc
        b = tc._CURRENT.get()
        keys = list(b.keys) if b is not None and b.alive else []
    except Exception:  # noqa: BLE001
        return []
    return [t for t in (turn_id_for_key(k) for k in keys) if t]


def current_turn_id() -> str | None:
    """The turn running in this context, as the hub names it from the key that turn sent (a compaction signal reads
    it to drop the right record)."""
    ids = current_turn_ids()
    return ids[0] if ids else None


def forget_turn(turn_id) -> bool:
    with _CLI_LOCK:
        return _CLI_LEDGERS.pop(str(turn_id or ""), None) is not None


def forget_current_turn() -> int:
    """The engine of the current turn compacted its conversation: earlier results may be gone, so forget them."""
    return sum(1 for t in current_turn_ids() if forget_turn(t))


def cli_text_for(turn_id, tool: str, args, text: str) -> str:
    """`text`, or a reference when this turn's record says the model holds an identical earlier copy."""
    if not turn_id or not repeat_refs_on_cached():
        return text
    now = time.time()
    with _CLI_LOCK:
        for old in [t for t, led in _CLI_LEDGERS.items() if now - led.created > CLI_TURN_TTL_S]:
            _CLI_LEDGERS.pop(old, None)
        led = _CLI_LEDGERS.get(turn_id)
        if led is None:
            led = _CLI_LEDGERS[turn_id] = CliRepeatResults()
        _CLI_LEDGERS.move_to_end(turn_id)
        while len(_CLI_LEDGERS) > CLI_MAX_TURNS:
            _CLI_LEDGERS.popitem(last=False)
        return led.text_for(tool, args, text)


def lean_for_cli(text, tool: str, args, turn_id=None) -> str:
    """What a CLI engine gets for one result of a Javis tool: compact JSON, then the per-turn repeat check.
    `turn_id` defaults to the turn of the hub request being served."""
    tool = str(tool or "")
    text = compact_json(str(text), tool)
    return cli_text_for(turn_id if turn_id is not None else HUB_TURN.get(), tool, args, text)
