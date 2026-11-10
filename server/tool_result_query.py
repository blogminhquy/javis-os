"""Read and compute over a stored tool result, so the data never has to pass through the model.

Three ways to look at one stored result (`tool_result_store`), all bounded and all whole-record:

  slice   chosen fields of records `offset .. offset+limit`
  sql     a read-only SQL query over ALL records, loaded into an in-memory SQLite database
  search  for text results: the lines that contain the words, or a line range

Why SQL: a month of shop orders cannot pass through any model's context (ten orders are already
99,000 characters), and a model adding numbers by eye on a truncated list is how a report goes
wrong. Here the code adds, and a small or a large model reads the same total.

Table layout for `sql`:
  records              one row per record. `_row` is its 1-based position. Nested objects become
                       `parent_child` columns; a list becomes a JSON text column (use json_each /
                       json_extract) plus `<name>_count`.
  records_<name>       one row per item of a list-of-objects field, `_record` = records._row.
Rows of plain lists (a spreadsheet range) become columns c1, c2, ... or the header row's names.

The database is in memory, built per call, and locked down with an authorizer: SELECT only, no
ATTACH, no PRAGMA, no extension loading, and a hard time limit.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from typing import Any, Optional

import tool_result_shaper as shaper

OUTPUT_CHARS_DEFAULT = 7000
OUTPUT_CHARS_MAX = 30_000
MAX_COLUMNS = 300
MAX_CHILD_TABLES = 8
MAX_ROWS_OUT = 500
SQL_TIMEOUT_S = 8.0
MAX_SQL_CHARS = 8000
DATASET_KEY = "javis_dataset"
_NAME_RE = re.compile(r"[^A-Za-z0-9_]+")


class QueryError(Exception):
    """A problem the model can fix by changing its call. The message is shown to it as is."""


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def clamp_chars(value, default: int = OUTPUT_CHARS_DEFAULT) -> int:
    try:
        return max(1000, min(OUTPUT_CHARS_MAX, int(value or default)))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- loading

def load(text: str, pointer: Optional[str] = None) -> dict:
    """{'kind': 'records'|'document'|'text', 'records', 'pointer', 'data', 'meta'} for a stored body."""
    parsed = shaper.parse_document(text)
    if parsed is None:
        return {"kind": "text", "text": text}
    data = parsed.data
    meta = {}
    if isinstance(data, dict) and isinstance(data.get(DATASET_KEY), dict) and isinstance(data.get("records"), list):
        meta = data[DATASET_KEY]
        if pointer in (None, "", "/", "/records"):
            return {"kind": "records", "records": data["records"], "pointer": "/records", "data": data, "meta": meta}
    if pointer not in (None, "", "/"):
        try:
            node = shaper.resolve_pointer(data, str(pointer))
        except (KeyError, IndexError, ValueError, TypeError):
            raise QueryError(f"path '{pointer}' does not exist in this result. Call without `path` to see where "
                             "the records are.")
        if not isinstance(node, list):
            raise QueryError(f"path '{pointer}' is not a list of records.")
        return {"kind": "records", "records": node, "pointer": str(pointer), "data": data, "meta": meta}
    found = shaper.find_records(data)
    if found is None:
        return {"kind": "document", "data": data, "meta": meta}
    return {"kind": "records", "records": found[1], "pointer": found[0] or "/", "data": data, "meta": meta}


# ---------------------------------------------------------------- slice

def _pick(record: Any, fields: Optional[list]) -> Any:
    if not fields or not isinstance(record, dict):
        return record
    out = {}
    for f in fields:
        if f in record:
            out[f] = record[f]
            continue
        # dotted path into nested objects: "customer.name"
        node, ok = record, True
        for part in str(f).split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                ok = False
                break
        if ok:
            out[f] = node
    return out


def slice_records(loaded: dict, ref: str, fields=None, offset=0, limit=50, max_chars=OUTPUT_CHARS_DEFAULT,
                  keep_empty: bool = False) -> str:
    """Whole records only: the page ends where the next record would not fit, and says where to resume."""
    records = loaded["records"]
    total = len(records)
    try:
        offset = max(0, int(offset or 0))
        limit = max(1, min(1000, int(limit or 50)))
    except (TypeError, ValueError):
        raise QueryError("offset and limit must be whole numbers.")
    if fields is not None and (not isinstance(fields, list) or not all(isinstance(f, str) for f in fields)):
        raise QueryError("fields must be a list of field names.")
    names, more = shaper.field_names(records)
    head = {"ref": ref, "records_at": loaded["pointer"], "total_records": total, "offset": offset}
    out, room = [], max_chars - 400
    unknown = [f for f in (fields or []) if names and f not in names and "." not in f]
    if unknown:
        head["unknown_fields"] = unknown
        head["fields"] = names
    for rec in records[offset:offset + limit]:
        item = _pick(rec, fields)
        if not keep_empty:
            item = shaper.lean_copy(item, True)
        size = len(_dumps(item)) + 1
        if size > room:
            if not out:
                # one record is larger than the whole page: show its outline rather than nothing
                item = shaper.outline(item)
                if len(_dumps(item)) + 1 > room:
                    item = shaper.outline(item, 0, 0, 80)
                head["shown_as"] = "outline"
                head["hint"] = "This record is too large to show whole. Pass `fields` to read the parts you need."
                out.append(item)
            break
        out.append(item)
        room -= size
    nxt = offset + len(out)
    head["returned"] = len(out)
    head["next_offset"] = nxt if nxt < total else None
    if not fields and names:
        head["fields"] = names
        if more:
            head["fields_not_listed"] = more
    return _dumps({"javis_query": head, "records": out})


# ---------------------------------------------------------------- text

def text_view(text: str, ref: str, search: str = "", offset=0, limit=80, max_chars=OUTPUT_CHARS_DEFAULT) -> str:
    lines = text.splitlines()
    room = max_chars - 300
    out = []
    if search:
        words = [w for w in re.findall(r"\w+", str(search).lower()) if len(w) > 1] or [str(search).lower()]
        hits = [i for i, ln in enumerate(lines) if all(w in ln.lower() for w in words)]
        mode = "all words"
        if not hits:
            hits = [i for i, ln in enumerate(lines) if any(w in ln.lower() for w in words)]
            mode = "any word"
        shown, last = 0, -2
        for i in hits:
            block = []
            for j in (i - 1, i, i + 1):
                if 0 <= j < len(lines) and j > last:
                    block.append(f"{j + 1}: {lines[j][:600]}")
                    last = j
            size = sum(len(b) + 1 for b in block)
            if size > room:
                break
            out += block
            room -= size
            shown += 1
        header = (f"[javis_query ref={ref} search={search!r} matched_lines={len(hits)} ({mode}) shown={shown} "
                  f"total_lines={len(lines)}]")
        return header + "\n" + "\n".join(out)
    try:
        offset = max(0, int(offset or 0))
        limit = max(1, min(5000, int(limit or 80)))
    except (TypeError, ValueError):
        raise QueryError("offset and limit must be whole numbers.")
    i = offset
    while i < min(len(lines), offset + limit):
        ln = lines[i]
        if len(ln) + 1 > room:
            if not out:
                out.append(ln[:room])
                i += 1
            break
        out.append(ln)
        room -= len(ln) + 1
        i += 1
    nxt = i if i < len(lines) else None
    header = f"[javis_query ref={ref} lines {offset + 1}-{i} of {len(lines)} next_offset={nxt}]"
    return header + "\n" + "\n".join(out)


# ---------------------------------------------------------------- sql

def _col(name: str, taken: set) -> str:
    base = _NAME_RE.sub("_", str(name)).strip("_") or "col"
    if base[0].isdigit():
        base = "c_" + base
    base = base[:60]
    out, n = base, 2
    while out.lower() in taken:
        out = f"{base}_{n}"
        n += 1
    taken.add(out.lower())
    return out


def _flatten(record: dict, prefix: str, depth: int, out: dict, children: dict) -> None:
    for k, v in record.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict) and depth < 3:
            _flatten(v, key + "_", depth + 1, out, children)
        elif isinstance(v, list):
            out[key] = _dumps(v) if v else None
            out[key + "_count"] = len(v)
            if depth == 0 and v and all(isinstance(x, dict) for x in v):
                children.setdefault(str(k), []).append(v)
        elif isinstance(v, dict):
            out[key] = _dumps(v)
        elif isinstance(v, bool):
            out[key] = int(v)
        else:
            out[key] = v


def _row_records(records: list) -> list:
    """Rows that are plain lists (a spreadsheet range) as objects: header names when the first row
    looks like a header, else c1..cN."""
    width = max((len(r) for r in records if isinstance(r, list)), default=0)
    first = records[0] if records and isinstance(records[0], list) else []
    header_ok = (len(records) > 1 and len(first) >= 2 and len(first) >= width * 0.6
                 and all(isinstance(x, str) and x.strip() and len(x) <= 60 for x in first)
                 and len({str(x).strip().lower() for x in first}) == len(first))
    names = [str(x).strip() for x in first] if header_ok else []
    names += [f"c{i + 1}" for i in range(len(names), width)]
    out = []
    for r in (records[1:] if header_ok else records):
        if isinstance(r, list):
            out.append({names[i]: (None if v == "" else v) for i, v in enumerate(r[:width])})
        elif isinstance(r, dict):
            out.append(r)
    return out


def _create(db, table: str, rows: list, lead: str) -> list:
    """Create `table` from flat dict rows. Returns [(column, original key)]."""
    keys, seen = [], set()
    for r in rows:
        for k in r:
            if k != "\x00lead" and k not in seen:
                seen.add(k)
                keys.append(k)
    extra = keys[MAX_COLUMNS:]
    keys = keys[:MAX_COLUMNS]
    taken = {lead.lower(), "_extra"}
    cols = [(_col(k, taken), k) for k in keys]
    ddl = ", ".join([f'"{lead}" INTEGER'] + [f'"{c}"' for c, _ in cols] + (['"_extra"'] if extra else []))
    db.execute(f'CREATE TABLE "{table}" ({ddl})')
    marks = ",".join("?" * (1 + len(cols) + (1 if extra else 0)))

    def gen():
        for r in rows:
            vals = [r.get("\x00lead")]
            for _c, k in cols:
                v = r.get(k)
                vals.append(v if isinstance(v, (int, float, str)) or v is None else _dumps(v))
            if extra:
                rest = {k: r[k] for k in extra if r.get(k) is not None}
                vals.append(_dumps(rest) if rest else None)
            yield vals
    db.executemany(f'INSERT INTO "{table}" VALUES ({marks})', gen())
    return cols


def build_database(records: list) -> tuple:
    """(connection, schema) with the records loaded. schema = {table: [column names]}."""
    db = sqlite3.connect(":memory:", check_same_thread=False)
    if records and sum(1 for r in records[:50] if isinstance(r, list)) > len(records[:50]) / 2:
        records = _row_records(records)
    main, children = [], {}
    for i, rec in enumerate(records, 1):
        flat = {"\x00lead": i}
        kids = {}
        if isinstance(rec, dict):
            _flatten(rec, "", 0, flat, kids)
        else:
            flat["value"] = rec if isinstance(rec, (int, float, str)) or rec is None else _dumps(rec)
        for k, lists in kids.items():
            children.setdefault(k, []).extend((i, item) for item in lists[0])
        main.append(flat)
    schema = {}
    cols = _create(db, "records", main, "_row")
    schema["records"] = ["_row"] + [c for c, _ in cols]
    taken = {"records"}
    for name, items in sorted(children.items(), key=lambda kv: -len(kv[1]))[:MAX_CHILD_TABLES]:
        rows = []
        for parent, item in items:
            flat = {"\x00lead": parent}
            _flatten(item, "", 1, flat, {})
            rows.append(flat)
        table = "records_" + _col(name, taken)
        ccols = _create(db, table, rows, "_record")
        schema[table] = ["_record"] + [c for c, _ in ccols]
    db.commit()
    return db, schema


_ALLOWED = None


def _authorizer(action, arg1, arg2, dbname, source):
    global _ALLOWED
    if _ALLOWED is None:
        _ALLOWED = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
                    getattr(sqlite3, "SQLITE_RECURSIVE", 33)}
    if action == sqlite3.SQLITE_FUNCTION and str(arg2 or "").lower() in ("load_extension", "readfile",
                                                                          "writefile", "edit", "fts3_tokenizer"):
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK if action in _ALLOWED else sqlite3.SQLITE_DENY


def describe(schema: dict, db, max_chars: int = 2500) -> dict:
    """Tables and columns with one example value each, bounded."""
    out, room = {}, max_chars
    for table, cols in schema.items():
        n = db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        entry = {"rows": n, "columns": []}
        for c in cols:
            if room <= 0:
                entry["columns_not_listed"] = len(cols) - len(entry["columns"])
                break
            entry["columns"].append(c)
            room -= len(c) + 3
        out[table] = entry
    return out


def run_sql(loaded: dict, ref: str, sql: str, max_chars: int = OUTPUT_CHARS_DEFAULT) -> str:
    sql = str(sql or "").strip().rstrip(";").strip()
    if not sql:
        raise QueryError("sql is empty.")
    if len(sql) > MAX_SQL_CHARS:
        raise QueryError("sql is too long.")
    if ";" in sql:
        raise QueryError("one statement only (no ';').")
    if not re.match(r"(?is)^\s*(select|with)\b", sql):
        raise QueryError("only SELECT (or WITH ... SELECT) is allowed.")
    db, schema = build_database(loaded["records"])
    try:
        deadline = time.time() + SQL_TIMEOUT_S
        db.set_progress_handler(lambda: 1 if time.time() > deadline else 0, 20_000)
        db.set_authorizer(_authorizer)
        try:
            cur = db.execute(sql)
            names = [d[0] for d in (cur.description or [])]
            rows, room, truncated = [], max_chars - 500 - sum(len(n) + 3 for n in names), False
            for row in cur:
                item = list(row)
                size = len(_dumps(item)) + 1
                if size > room or len(rows) >= MAX_ROWS_OUT:
                    truncated = True
                    break
                rows.append(item)
                room -= size
        except sqlite3.Error as e:
            msg = str(e)
            db.set_authorizer(None)
            if "interrupted" in msg.lower():
                raise QueryError(f"the query ran longer than {int(SQL_TIMEOUT_S)} seconds; make it simpler.")
            if "not authorized" in msg.lower() or "prohibited" in msg.lower():
                raise QueryError("only reading is allowed here (SELECT over the tables below). "
                                 + _dumps({"tables": describe(schema, db)}))
            raise QueryError(f"SQL error: {msg}. " + _dumps({"tables": describe(schema, db)}))
        head = {"ref": ref, "total_records": len(loaded["records"]), "row_count": len(rows)}
        if truncated:
            head["truncated"] = True
            head["hint"] = "More rows exist than fit. Aggregate (GROUP BY), select fewer columns, or add LIMIT/OFFSET."
        return _dumps({"javis_query": head, "columns": names, "rows": rows})
    finally:
        db.close()


def schema_view(loaded: dict, ref: str, max_chars: int = OUTPUT_CHARS_DEFAULT) -> str:
    db, schema = build_database(loaded["records"])
    try:
        return _dumps({"javis_query": {"ref": ref, "total_records": len(loaded["records"]),
                                       "records_at": loaded["pointer"]},
                       "tables": describe(schema, db, max_chars - 400)})
    finally:
        db.close()


# ---------------------------------------------------------------- datasets (several pages as one result)

def records_of_page(text: str, pointer: Optional[str] = None) -> tuple:
    """(records, envelope, pointer) of one raw page; ([], None, pointer) when it holds no record list."""
    parsed = shaper.parse_document(text)
    if parsed is None:
        return [], None, pointer
    data = parsed.data
    if pointer not in (None, "", "/"):
        try:
            node = shaper.resolve_pointer(data, pointer)
        except (KeyError, IndexError, ValueError, TypeError):
            return [], data, pointer
        return (node if isinstance(node, list) else []), data, pointer
    found = shaper.find_records(data)
    if found is None:
        return [], data, pointer
    return found[1], data, (found[0] or "/")


def page_info(envelope: Any) -> dict:
    """Paging markers found in a page's envelope: {'total_pages', 'page', 'total', 'next_cursor', 'has_more'}."""
    out = {}
    if not isinstance(envelope, dict):
        return out
    stack = [(envelope, 0)]
    alias = {"total_pages": "total_pages", "totalpages": "total_pages", "pages": "total_pages",
             "page_number": "page", "page": "page", "current_page": "page", "pagenumber": "page",
             "total_entries": "total", "total": "total", "total_count": "total", "totalcount": "total",
             "next_cursor": "next_cursor", "nextcursor": "next_cursor",
             "next_page_token": "next_cursor", "nextpagetoken": "next_cursor",
             "has_more": "has_more", "hasmore": "has_more", "has_next": "has_more"}
    while stack:
        node, depth = stack.pop()
        for k, v in node.items():
            name = alias.get(str(k).lower().replace("-", "_"))
            if name and name not in out and isinstance(v, (int, str, bool)) and not isinstance(v, float):
                out[name] = v
            if isinstance(v, dict) and depth < 2:
                stack.append((v, depth + 1))
    return out


def make_dataset(records: list, meta: dict) -> str:
    return _dumps({DATASET_KEY: meta, "records": records})
