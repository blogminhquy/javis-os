"""Shape what a connected source returns before any model reads it.

Measured on a real install (2026-11-10): ten shop orders are 99,000 to 183,000 characters, ten
website posts 242,000. About a third of the bytes are indentation, two thirds of the rest are
repeated key names, a third are empty fields. API engines cut every result at 8,000 characters and
kept the head and the tail, so the model saw a total ("2,738 orders") and not one whole order. CLI
engines received everything and paid for it in context.

This module is the one place that decides what leaves the hub, for every engine:

  1. An error is returned word for word.
  2. A small result is returned word for word.
  3. JSON that fits is re-serialised without indentation and nothing else: every field survives.
  4. A result that is still large is stored in full (`tool_result_store`). If its records fit once
     their key names are written a single time (a table), ALL of them are shown that way. Otherwise
     it is replaced by a view: the envelope (totals, paging markers), the field names, as many
     WHOLE records as fit, and a reference. Nothing is cut in the middle of a record, and
     `javis_query` reads the rest.
  5. Large text that is not JSON gets whole first and last lines plus the same reference.

Every step fails open: anything unexpected returns the original text, and the caller behaves as it
did before this module existed.
"""
from __future__ import annotations

import contextvars
import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Optional

import tool_result_store

INLINE_MAX_DEFAULT = 8000        # the API engines' own cap for a connection result (engine._clip_tool_result)
PREVIEW_BUDGET_DEFAULT = 6000
MIN_SHAPE_CHARS = 1200           # below this nothing is touched: the saving is not worth any risk
MAX_PARSE_CHARS = 30_000_000
_PREFIX_MAX = 240                # "HTTP 200 OK\n---\n" style headers some servers put before the JSON
_FIELD_NAMES_MAX = 120
_FIELD_NAMES_CHARS = 1500
_ENVELOPE_CHARS = 1200
QUERY_TOOL = "javis_query"

# Who reads the result of the tool call running in this context:
#   ""       an internal caller (a workflow runner, a dashboard widget): untouched, as before
#   "model"  a model's tool loop: shaped
#   "raw"    javis_query reading whole pages for itself, inside a model's turn: untouched
_audience = contextvars.ContextVar("javis_tool_result_audience", default="")
_settings_cache = {"ts": 0.0, "on": True, "inline": INLINE_MAX_DEFAULT, "budget": PREVIEW_BUDGET_DEFAULT}


@contextmanager
def for_model():
    """Inside this block a connection tool's result is shaped for a model to read."""
    token = _audience.set("model")
    try:
        yield
    finally:
        _audience.reset(token)


@contextmanager
def raw_results():
    """Inside this block the hub returns results untouched (javis_query reads whole pages itself)."""
    token = _audience.set("raw")
    try:
        yield
    finally:
        _audience.reset(token)


def audience() -> str:
    return _audience.get()


@dataclass(frozen=True)
class Shaped:
    text: str
    raw_chars: int
    # internal | raw | error | off | small | same | compact | table | preview | text_preview
    kind: str
    ref: str = ""

    @property
    def sent_chars(self) -> int:
        return len(self.text)


CHANGED_KINDS = frozenset({"compact", "table", "preview", "text_preview"})   # the text differs from the tool's own
MODEL_KINDS = frozenset({"error", "off", "small", "same"}) | CHANGED_KINDS  # a model read this result


@dataclass(frozen=True)
class Parsed:
    prefix: str
    data: Any
    multi: bool = False


def _env_flag(name: str) -> Optional[bool]:
    v = (os.getenv(name) or "").strip().lower()
    if v in ("1", "true", "on", "yes"):
        return True
    if v in ("0", "false", "off", "no"):
        return False
    return None


def _env_int(name: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(os.getenv(name, "") or default)))
    except (TypeError, ValueError):
        return default


def settings(force: bool = False) -> dict:
    """{'on', 'inline', 'budget'}, re-read at most every few seconds.

    `mcp.result_shaping`: "auto" (default) | true | false. Auto is on unless the owner chose the Off
    saving level themselves ("Full mode: send everything"). JAVIS_TOOL_RESULT_SHAPING=0|1 wins."""
    now = time.time()
    if not force and now - _settings_cache["ts"] < 5:
        return _settings_cache
    on = True
    try:
        import config
        cfg = config.read_settings()
        mcp = cfg.get("mcp") or {}
        v = mcp.get("result_shaping", "auto")
        s = str(v).strip().lower()
        if v is False or s in ("false", "off", "0", "never"):
            on = False
        elif v is True or s in ("true", "on", "1", "always"):
            on = True
        else:
            choice = ((cfg.get("context_runtime") or {}).get("preset_choice") or {})
            on = not (str(choice.get("source") or "") == "user" and str(choice.get("level") or "") == "off")
    except Exception:  # noqa: BLE001 - unreadable settings: keep the default
        pass
    env = _env_flag("JAVIS_TOOL_RESULT_SHAPING")
    if env is not None:
        on = env
    inline = _env_int("JAVIS_TOOL_RESULT_INLINE_CHARS", INLINE_MAX_DEFAULT, 2000, 200_000)
    budget = min(_env_int("JAVIS_TOOL_RESULT_PREVIEW_CHARS", PREVIEW_BUDGET_DEFAULT, 1500, 100_000), inline - 500)
    _settings_cache.update(ts=now, on=on, inline=inline, budget=budget)
    return _settings_cache


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def parse_document(text: str) -> Optional[Parsed]:
    """The text as ONE JSON value (optionally after a short header), or as several JSON values in a
    row (some servers print one object per item). None when it is anything else."""
    if not isinstance(text, str) or len(text) > MAX_PARSE_CHARS:
        return None
    start = -1
    for i, ch in enumerate(text[:_PREFIX_MAX]):
        if ch in "{[":
            start = i
            break
    if start < 0:
        return None
    decoder = json.JSONDecoder()
    values = []
    pos = start
    n = len(text)
    try:
        while pos < n:
            value, end = decoder.raw_decode(text, pos)
            values.append(value)
            pos = end
            while pos < n and text[pos] in " \t\r\n":
                pos += 1
            if len(values) > 5000:
                return None
    except (ValueError, RecursionError):
        return None
    if not values or not all(isinstance(v, (dict, list)) for v in values):
        return None
    if len(values) == 1:
        return Parsed(text[:start], values[0], False)
    return Parsed(text[:start], values, True)


def lean_copy(value: Any, inside_list: bool = False) -> Any:
    """Copy without empty fields INSIDE records (anything reached through a list).

    The envelope (keys reached without crossing a list) keeps its empty values: `"data": []` is an
    answer, not noise. List items themselves are never removed, so row and cell positions hold."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            y = lean_copy(v, inside_list)
            if inside_list and (y is None or (isinstance(y, (str, list, dict)) and len(y) == 0)):
                continue
            out[k] = y
        return out
    if isinstance(value, list):
        return [lean_copy(v, True) for v in value]
    return value


def find_records(data: Any, max_depth: int = 4):
    """(json_pointer, list) of the largest list of records (objects or rows), or None.

    Only object keys are followed, never list items, so the pointer is always usable as is."""
    best = _find_records_sized(data, max_depth)
    return None if best is None else (best[1], best[2])


def _estimate_chars(items: list) -> int:
    """Serialised size of a list, from a sample: exact for a short list, proportional for a long one. A result of
    megabytes must not be serialised once per candidate list just to learn which list is the big one."""
    n = len(items)
    try:
        if n <= 24:
            return len(_dumps(items))
        step = max(1, n // 16)
        sample = items[::step][:16]
        return int(len(_dumps(sample)) * n / len(sample))
    except (TypeError, ValueError, RecursionError):
        return 0


def _find_records_sized(data: Any, max_depth: int = 4):
    """(estimated size, json_pointer, list) of the largest list of records, or None."""
    best = None
    stack = [("", data, 0)]
    while stack:
        pointer, node, depth = stack.pop()
        if isinstance(node, list):
            head = node[:200]
            if node and sum(1 for x in head if isinstance(x, (dict, list))) >= max(1, int(len(head) * 0.8)):
                size = _estimate_chars(node)
                if best is None or size > best[0]:
                    best = (size, pointer, node)
            continue
        if isinstance(node, dict) and depth < max_depth:
            for k, v in node.items():
                if isinstance(v, (dict, list)):
                    stack.append((pointer + "/" + str(k).replace("~", "~0").replace("/", "~1"), v, depth + 1))
    return best


def resolve_pointer(data: Any, pointer: str):
    """Value at an RFC 6901 pointer; raises KeyError/IndexError/ValueError when it does not exist."""
    node = data
    if not pointer:
        return node
    if not pointer.startswith("/"):
        raise ValueError("pointer must start with /")
    for part in pointer.split("/")[1:]:
        key = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            node = node[int(key)]
        elif isinstance(node, dict):
            node = node[key]
        else:
            raise KeyError(key)
    return node


def outline(value: Any, depth: int = 0, max_depth: int = 2, text_max: int = 160) -> Any:
    """A record with the same keys but long values summarised. Used when one record is too large to
    show whole: the model still sees every field name and every short value."""
    if isinstance(value, str):
        if len(value) > text_max:
            keep = max(20, text_max * 3 // 4)
            return f"{value[:keep]}... (+{len(value) - keep} chars)"
        return value
    if isinstance(value, dict):
        if depth >= max_depth:
            return f"<object, {len(value)} keys>"
        return {k: outline(v, depth + 1, max_depth, text_max) for k, v in value.items()}
    if isinstance(value, list):
        if not value:
            return value
        if all(not isinstance(x, (dict, list)) for x in value):
            try:
                if len(_dumps(value)) <= 200:
                    return value
            except (TypeError, ValueError):
                pass
            return f"<list, {len(value)} values>"
        if depth >= max_depth:
            return f"<list, {len(value)} items>"
        first = outline(value[0], depth + 1, max_depth, text_max)
        return [first] if len(value) == 1 else [first, f"<+{len(value) - 1} more items>"]
    return value


def field_names(records: list) -> tuple:
    """(key names of object records in first-seen order, how many more were left out)."""
    seen, out, used = set(), [], 0
    for rec in records[:500]:
        if not isinstance(rec, dict):
            continue
        for k in rec:
            if k in seen:
                continue
            seen.add(k)
            if len(out) < _FIELD_NAMES_MAX and used + len(str(k)) + 3 <= _FIELD_NAMES_CHARS:
                out.append(k)
                used += len(str(k)) + 3
    return out, max(0, len(seen) - len(out))


def _envelope(data: Any, pointer: str) -> Any:
    """Everything around the record list (totals, paging), summarised and bounded."""
    if not isinstance(data, dict) or not pointer:
        return None
    first = pointer.split("/")[1].replace("~1", "/").replace("~0", "~")
    rest = {k: v for k, v in data.items() if k != first}
    if pointer.count("/") > 1 and isinstance(data.get(first), dict):
        # records live deeper: keep the siblings on the way down, they often hold the paging block
        inner = _envelope(data[first], "/" + pointer.split("/", 2)[2])
        if inner:
            rest[first] = inner
    if not rest:
        return None
    env = outline(rest, 0, 2, 200)
    if len(_dumps(env)) <= _ENVELOPE_CHARS:
        return env
    env = {k: v for k, v in outline(rest, 0, 0, 80).items()}
    if len(_dumps(env)) <= _ENVELOPE_CHARS:
        return env
    return {"keys": list(rest)[:60]}


def _how_to(ref: str) -> str:
    return (f"Partial view. The FULL result is stored as ref {ref}. Read more with {QUERY_TOOL}(ref=\"{ref}\", "
            "fields=[...], offset=N, limit=N) or compute over ALL records with "
            f"{QUERY_TOOL}(ref=\"{ref}\", sql=\"SELECT ...\"). Do not call the source tool again for the same "
            "data. Empty fields are omitted.")


TABLE_FORMAT = ("table: `columns` once, then one row per record, values in column order. A dotted column is a "
                "nested field. null = empty or absent in that record.")
_TABLE_MAX_COLUMNS = 160
_TABLE_GAIN = 0.85               # use the table form only when it is at least 15% smaller than the records as objects
_TABLE_TRY_FACTOR = 12           # a result more than this many times the inline cap is never tried as a whole table


def _flat_record(rec: dict, prefix: str, depth: int, out: dict) -> bool:
    """Flatten into `out`. False when two different fields would land on the same dotted name (a key that itself
    contains a dot next to a nested object): a table could not tell them apart, so none is made."""
    for k, v in rec.items():
        key = prefix + str(k)
        if isinstance(v, dict) and v and depth < 2:
            if not _flat_record(v, key + ".", depth + 1, out):
                return False
        elif key in out:
            return False
        else:
            out[key] = v
    return True


def to_table(records: list) -> Optional[tuple]:
    """(columns, rows) for a list of object records, or None when a table would not help.

    Key names are two thirds of a compact record (measured). Written once as column names, the same data is
    much smaller, so far more WHOLE records fit in what a model is shown. Nothing is dropped: a nested object
    becomes dotted columns, a list stays a list inside its cell."""
    if not records or not all(isinstance(r, dict) for r in records):
        return None
    columns, flats = {}, []
    for rec in records:
        flat = {}
        if not _flat_record(rec, "", 0, flat):
            return None
        flats.append(flat)
        for k in flat:
            if k not in columns:
                columns[k] = None
                if len(columns) > _TABLE_MAX_COLUMNS:
                    return None
    names = list(columns)
    return names, [[flat.get(c) for c in names] for flat in flats]


def _swap_at(data: Any, pointer: str, value: Any) -> Any:
    """Shallow copy of `data` with the node at `pointer` replaced (only object keys are on the way)."""
    if not pointer:
        return value
    parts = [p.replace("~1", "/").replace("~0", "~") for p in pointer.split("/")[1:]]
    root = dict(data)
    node = root
    for part in parts[:-1]:
        node[part] = dict(node[part])
        node = node[part]
    node[parts[-1]] = value
    return root


def build_table(lean: Any, ref: str, raw_chars: int, limit: int, prefix: str = "") -> Optional[str]:
    """The WHOLE result with its record list as a table, or None when that is not smaller or does not fit.

    This is the step between "compact JSON fits" and "show a partial view": every record is still there, so
    the model needs no second call."""
    found = find_records(lean)
    if not found:
        return None
    pointer, records = found
    table = to_table(records)
    if table is None:
        return None
    columns, rows = table
    as_objects = len(_dumps(records))
    as_table = len(_dumps(columns)) + len(_dumps(rows))
    if as_table > as_objects * _TABLE_GAIN:
        return None
    head = {"ref": ref, "view": "complete", "original_chars": raw_chars, "records_at": pointer or "/",
            "records_in_result": len(records), "format": TABLE_FORMAT,
            "note": f"All records are shown. To compute over them use {QUERY_TOOL}(ref=\"{ref}\", sql=\"SELECT ...\")."}
    if prefix.strip():
        head["text_before_result"] = prefix.strip()[:_PREFIX_MAX]
    body = _swap_at(lean, pointer, {"columns": columns, "rows": rows})
    doc = {"javis_stored_result": head, "result": body}
    text = _dumps(doc)
    return text if len(text) <= limit else None


_PREVIEW_SAMPLE = 500            # records looked at to build a view: field names, the table test, the rows shown


def build_preview(parsed: Parsed, data: Any, ref: str, raw_chars: int, budget: int, total_size: int = 0) -> str:
    """The view a model reads in place of a large JSON result. Always valid JSON.

    `data` is the parsed result as it came. Only the first records are cleaned and looked at: the cost of a view
    must not grow with a result that is megabytes long. total_size: its compact size, when the caller has it."""
    head = {"ref": ref, "original_chars": raw_chars, "note": _how_to(ref)}
    if parsed.prefix.strip():
        head["text_before_result"] = parsed.prefix.strip()[:_PREFIX_MAX]
    sized = _find_records_sized(data)
    total_size = total_size or len(_dumps(data))
    lean = None
    if sized and sized[0] * 2 >= total_size:
        pointer, all_records = sized[1], sized[2]
        records = lean_copy(all_records[:_PREVIEW_SAMPLE], True)
        lean = data
        names, more = field_names(records)
        head.update({"records_at": pointer or "/", "records_in_result": len(all_records)})
        if names:
            head["fields"] = names
            if more:
                head["fields_not_listed"] = more
        doc = {"javis_stored_result": head}
        env = _envelope(lean, pointer)
        if env:
            doc["envelope"] = env
        doc["records"] = []
        room = budget - len(_dumps(doc)) - 40
        sizes = [len(_dumps(r)) for r in records[:50]]
        avg = sum(sizes) / max(1, len(sizes))
        shown, mode = [], "full"
        table = to_table(records)
        if table is not None and avg * 2 <= room:
            columns, rows = table
            sample = min(len(rows), 50)
            if (len(_dumps(columns)) + len(_dumps(rows[:sample]))) <= sum(sizes[:sample]) * _TABLE_GAIN:
                # Dense, regular records: as a table many more whole rows fit in the same space.
                left = room - len(_dumps(columns)) - 60 - len(TABLE_FORMAT)
                kept = []
                for row in rows:
                    size = len(_dumps(row)) + 1
                    if size > left:
                        break
                    kept.append(row)
                    left -= size
                if len(kept) >= 2:
                    head.pop("fields", None)
                    head.pop("fields_not_listed", None)
                    head["shown_records"] = len(kept)
                    head["shown_as"] = "table"
                    head["format"] = TABLE_FORMAT
                    doc.pop("records")
                    doc["columns"] = columns
                    doc["rows"] = kept
                    return _dumps(doc)
        if avg * 2 <= room:
            for rec in records:
                size = len(_dumps(rec)) + 1
                if size > room:
                    break
                shown.append(rec)
                room -= size
        if not shown:
            mode = "outline"
            for rec in records:
                o = outline(rec)
                size = len(_dumps(o)) + 1
                if size > room and not shown:
                    o = outline(rec, 0, 0, 80)
                    size = len(_dumps(o)) + 1
                if size > room and not shown and isinstance(rec, dict):
                    o = {"keys": list(rec)[:80]}
                    size = len(_dumps(o)) + 1
                if size > room:
                    break
                shown.append(o)
                room -= size
        head["shown_records"] = len(shown)
        head["shown_as"] = mode
        doc["records"] = shown
        return _dumps(doc)
    # No dominant record list: show the shape of the whole document.
    lean = lean_copy(data)
    for depth, text_max in ((3, 200), (2, 160), (1, 100), (0, 60)):
        doc = {"javis_stored_result": dict(head, shown_as="outline"), "document": outline(lean, 0, depth, text_max)}
        text = _dumps(doc)
        if len(text) <= budget:
            return text
    keys = list(lean)[:100] if isinstance(lean, dict) else f"<list, {len(lean)} items>"
    return _dumps({"javis_stored_result": dict(head, shown_as="keys"), "document": keys})


SOFT_LINE_CHARS = 1200


def soft_lines(text: str, width: int = SOFT_LINE_CHARS) -> list:
    """Lines of `text`, with any line longer than `width` split at a space near the limit.

    The preview and javis_query both number lines this way, so a result that is one enormous line (minified
    HTML, a JSON-less export) can still be read from start to end by line number."""
    out = []
    for line in text.splitlines():
        while len(line) > width:
            cut = line.rfind(" ", width // 2, width)
            cut = cut + 1 if cut > 0 else width
            out.append(line[:cut])
            line = line[cut:]
        out.append(line)
    return out


def build_text_preview(text: str, ref: str, budget: int) -> str:
    """Whole first and last lines of a large non-JSON result, plus the reference."""
    lines = soft_lines(text)
    header = (f"[javis_stored_result ref={ref} original_chars={len(text)} lines={len(lines)}] Partial view. "
              f"The FULL text is stored. Read more with {QUERY_TOOL}(ref=\"{ref}\", search=\"words\") or "
              f"{QUERY_TOOL}(ref=\"{ref}\", offset=LINE, limit=N). Do not call the source tool again for the "
              "same data.")
    room = max(400, budget - len(header) - 80)
    head_room, tail_room = int(room * 0.7), int(room * 0.3)
    head, used, i = [], 0, 0
    while i < len(lines) and used + len(lines[i]) + 1 <= head_room:
        head.append(lines[i])
        used += len(lines[i]) + 1
        i += 1
    if not head:                                   # cannot happen with soft lines; kept as a guard
        return header + "\n--- start ---\n" + text[:head_room] + "\n--- end ---\n" + text[-tail_room:]
    tail, used, j = [], 0, len(lines) - 1
    while j >= i and used + len(lines[j]) + 1 <= tail_room:
        tail.append(lines[j])
        used += len(lines[j]) + 1
        j -= 1
    tail.reverse()
    hidden = j - i + 1
    out = [header, f"--- lines 1-{len(head)} ---", *head]
    if hidden > 0:
        out.append(f"--- {hidden} lines not shown ---")
    if tail:
        out += [f"--- lines {j + 2}-{len(lines)} ---", *tail]
    return "\n".join(out)


def _has_error(data: Any) -> bool:
    try:
        from tool_result_view import _has_error as has
        return bool(has(data))
    except Exception:  # noqa: BLE001
        return False


def shape(result: Any, *, tool: str = "", conn_id: str = "", scope: str = "", can_read_back: bool = True) -> Shaped:
    """What the hub hands to the model for one tool result. Never raises.

    can_read_back=False (the caller has no javis_query in its tool list): the result is compacted
    but never replaced by a view, because a reference nobody can follow is a dead end."""
    text = result if isinstance(result, str) else str(result)
    raw_chars = len(text)
    try:
        if text.lstrip()[:6] == "ERROR:":
            return Shaped(text, raw_chars, "error")
        who = _audience.get()
        if who != "model":
            return Shaped(text, raw_chars, "raw" if who == "raw" else "internal")
        cfg = settings()
        if not cfg["on"]:
            return Shaped(text, raw_chars, "off")
        if raw_chars < MIN_SHAPE_CHARS:
            return Shaped(text, raw_chars, "small")
        inline, budget = int(cfg["inline"]), int(cfg["budget"])
        parsed = parse_document(text)
        if parsed is None:
            if raw_chars <= inline or not can_read_back:
                return Shaped(text, raw_chars, "same")
            ref = tool_result_store.put(text, scope=scope, tool=tool, conn_id=conn_id, kind="text")
            if not ref:
                return Shaped(text, raw_chars, "same")
            return Shaped(build_text_preview(text, ref, budget), raw_chars, "text_preview", ref)
        if raw_chars <= inline and _has_error(parsed.data):      # only a result that fits is ever walked for this
            return Shaped(text, raw_chars, "error")
        # A result that fits is only re-serialised without indentation: every field, empty or not, is still
        # there, so a document the model reads, edits and writes back (a workflow, a config) loses nothing.
        compact = parsed.prefix + _dumps(parsed.data)
        if len(compact) >= raw_chars:
            compact = text
        if len(compact) <= inline or not can_read_back:
            return Shaped(compact, raw_chars, "compact" if compact is not text else "same")
        ref = tool_result_store.put(text, scope=scope, tool=tool, conn_id=conn_id, kind="json")
        if not ref:
            return Shaped(compact, raw_chars, "compact")
        # Views (a table or a partial view) drop empty fields inside records and say so; the stored copy has them.
        # A table cannot shrink a result more than about tenfold, so a much larger one goes straight to a view.
        if len(compact) <= inline * _TABLE_TRY_FACTOR:
            whole = build_table(lean_copy(parsed.data), ref, raw_chars, inline, parsed.prefix)
            if whole is not None:
                return Shaped(whole, raw_chars, "table", ref)
        preview = build_preview(parsed, parsed.data, ref, raw_chars, budget, len(compact))
        if len(preview) > inline:                   # should not happen; never trade a cut for a cut
            tool_result_store.delete(ref)
            return Shaped(compact, raw_chars, "compact")
        return Shaped(preview, raw_chars, "preview", ref)
    except Exception as e:  # noqa: BLE001 - shaping is an optimisation: on any surprise, hand back the original
        import sys
        print(f"[tool results] shaping skipped for {tool}: {type(e).__name__}: {e}", file=sys.stderr)
        return Shaped(text, raw_chars, "same")
