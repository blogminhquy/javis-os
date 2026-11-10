"""The `javis_query` tool: hub glue around `tool_result_query`.

One tool, two sources, three views:

  source  `ref`            a result the hub stored (the notice in a large result names it)
          `tool` + `args`  a read-only connection tool, called here page by page through the SAME
                           guarded route a direct call uses (permission, audit, rate limit), and
                           kept as one dataset under a new ref
  view    `sql` | `fields`/`offset`/`limit` | `search` (text) | `describe`

The tool is part of the core list (always visible, never behind the tool search), because a stored
result's notice names it and a model must be able to follow that notice in one step. Its schema is
small and fixed.

Only READ tools can be a source: paging a tool that writes would repeat the write.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

import tool_result_query as query
import tool_result_shaper as shaper
import tool_result_store as store

TOOL = shaper.QUERY_TOOL
_QUERY_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="javis-query")
PAGES_DEFAULT_MAX = 200           # measured: a shop source pages ten orders at a time, a month is hundreds of pages
FETCH_SECONDS = 240
DATASET_CHARS_MAX = 20_000_000
DATASET_RECORDS_MAX = 250_000

_PAGE_PARAMS = ("page_number", "page", "page_no", "pagenumber", "page_num", "pageno")
_OFFSET_PARAMS = ("offset", "skip", "start")
_CURSOR_PARAMS = ("cursor", "page_token", "pagetoken", "next_cursor", "after", "starting_after", "next_page_token")

# Shown on EVERY turn of a brain that has a connected source, so every character here is paid for each time:
# keep it short. The notice inside a stored result repeats the exact call to make.
DESCRIPTION = (
    "Read or compute over a LARGE tool result without loading it. Source: `ref` (from a stored-result notice) or "
    "`tool`+`args` (a read-only connection tool; `pages`=N reads N pages into one dataset and returns a ref; ask "
    "the source for big pages and only the fields you need). View: `sql` = one SQLite SELECT on table `records` "
    "(nested object -> parent_child columns; list-of-objects field -> table records_<field>, join _record = "
    "records._row) for every total, count, grouping or top-N; or `fields`+`offset`+`limit` to read records; "
    "`search` for a text result; `describe`=true lists columns.")

SCHEMA = {
    "type": "object",
    "properties": {
        "ref": {"type": "string"},
        "tool": {"type": "string"},
        "args": {"type": "object"},
        "pages": {"type": "integer"},
        "page_param": {"type": "string", "description": "the tool's page/offset/cursor argument, if not detected"},
        "path": {"type": "string", "description": "JSON pointer to the record list, e.g. /data"},
        "sql": {"type": "string"},
        "fields": {"type": "array", "items": {"type": "string"}},
        "offset": {"type": "integer"},
        "limit": {"type": "integer"},
        "search": {"type": "string"},
        "describe": {"type": "boolean"},
        "max_chars": {"type": "integer"},
    },
}


def max_pages() -> int:
    try:
        return max(1, min(500, int(os.getenv("JAVIS_QUERY_MAX_PAGES", "") or PAGES_DEFAULT_MAX)))
    except (TypeError, ValueError):
        return PAGES_DEFAULT_MAX


def _err(msg: str) -> str:
    return "ERROR: " + msg


def _expired(ref: str) -> str:
    return _err(f"ref '{ref}' is unknown or has expired (stored results live about {store.ttl_seconds() // 3600} "
                "hours). Call the source tool again to get a new one.")


def _get_arg(args: dict, dotted: str):
    node = args
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _set_arg(args: dict, dotted: str, value) -> dict:
    out = json.loads(json.dumps(args))
    node = out
    parts = dotted.split(".")
    for part in parts[:-1]:
        nxt = node.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            node[part] = nxt
        node = nxt
    node[parts[-1]] = value
    return out


def detect_paging(schema: dict, args: dict, explicit: str = "") -> tuple:
    """(style, param) with style in page | offset | cursor | "". Explicit name wins."""
    props = {}
    if isinstance(schema, dict) and isinstance(schema.get("properties"), dict):
        props = schema["properties"]
    known = {str(k).lower(): str(k) for k in list(props) + list(args or {})}

    def style_of(name: str) -> str:
        low = name.split(".")[-1].lower()
        if low in _OFFSET_PARAMS:
            return "offset"
        if low in _CURSOR_PARAMS:
            return "cursor"
        return "page"
    if explicit:
        return style_of(explicit), explicit
    for group, style in ((_PAGE_PARAMS, "page"), (_OFFSET_PARAMS, "offset"), (_CURSOR_PARAMS, "cursor")):
        for name in group:
            if name in known:
                return style, known[name]
    return "", ""


_READ_NAME_RE = re.compile(
    r"(^|[_\-.])(get|list|search|find|read|fetch|query|lookup|show|view|count|stats?|statistics?|analytics|report|"
    r"summary|describe|export|check|browse|history)([_\-.]|$)", re.I)


def is_plain_read(ent: dict, args: dict) -> bool:
    """Is this call a read that Javis may repeat BY ITSELF (paging, a recipe replay)?

    Stricter than the hub's permission class. `mcp_catalog.classify` answers "read" for any tool nobody
    described that has no write word in its name (`trigger_workflow`, `apply_migration`, `checkout`), which is the
    right default for a call a model makes once under the owner's eyes, and the wrong one for a call Javis makes
    again on its own. So on top of the hub's class, the read must be DECLARED: the catalogue lists the tool or
    this argument value as a read, or the tool's own name says so (get, list, search, report...)."""
    conn = ent.get("conn")
    tool = str(ent.get("tool") or "")
    if not conn or not tool:
        return False
    try:
        import mcp_catalog
        from fnmatch import fnmatch
        connector = mcp_catalog.get(conn.get("connector_id")) or {}
        if mcp_catalog.classify(connector, tool, args) != "read":
            return False
        meta = connector.get("tool_meta") or {}
        if any(fnmatch(tool.lower(), str(p).lower()) for p in (meta.get("read") or [])):
            return True
        rules = connector.get("arg_rules") or {}
        param = rules.get("param")
        if param and isinstance(args, dict) and args.get(param) is not None:
            return True                       # classify() said read, and only its declared read values can
        if mcp_catalog.call_rule(connector, tool) is not None:
            return True                       # a gateway tool: classify() judged every sub-action by its rules
        return bool(_READ_NAME_RE.search(tool))
    except Exception:  # noqa: BLE001 - cannot prove it is a read: refuse
        return False


_is_read = is_plain_read


async def fetch_dataset(route: dict, specs: dict, name: str, args: dict, *, pages: int = 1, page_param: str = "",
                        path: str = "", scope: str = "") -> tuple:
    """Read up to `pages` pages of a read-only tool. Returns (error, loaded, ref, meta)."""
    import mcp_client
    ent = route.get(name)
    if not ent or name == TOOL:
        return _err(f"no tool named '{name}'. Use the exact name from the tool list or the tool search."), None, "", {}
    if not is_plain_read(ent, args):
        return (_err(f"'{name}' is not a tool {TOOL} may call by itself: it must be a connection tool that is clearly "
                     "a read. Call the tool directly; if its answer is large, the notice gives a ref to use here."),
                None, "", {})
    pages = max(1, min(max_pages(), int(pages or 1)))
    style, param = detect_paging((specs.get(name) or {}).get("schema") or {}, args, page_param)
    records, info, pointer, used = [], {}, (path or None), 0
    last_sig, note, complete, chars = "", "", False, 0
    total_seen = None
    cur_args = json.loads(json.dumps(args or {}))
    started = time.time()
    first_text = ""
    for n in range(pages):
        with shaper.raw_results():
            text = str(await mcp_client.call_route({name: ent}, name, cur_args))
        if text.lstrip().startswith("ERROR:"):
            if n == 0:
                return text, None, "", {}
            note = "stopped early: " + text.strip()[:300]
            break
        if n == 0:
            first_text = text
        recs, envelope, pointer = await asyncio.to_thread(query.records_of_page, text, pointer)
        info = query.page_info(envelope)       # this page's own markers, never the previous page's
        if isinstance(info.get("total"), int) and not isinstance(info.get("total"), bool):
            total_seen = info["total"]
        if not recs:
            if n == 0:
                break                      # not a record list: handled below as a plain stored result
            complete = True
            break
        sig = hashlib.sha256(json.dumps(recs[:3], sort_keys=True, default=str).encode()).hexdigest()
        if sig == last_sig:
            note = f"the tool returned the same page again: `{param}` is not its paging argument"
            break
        last_sig = sig
        used += 1
        # Kept without empty fields: a third of a real record is nulls, and a month of pages must fit in memory.
        recs = await asyncio.to_thread(shaper.lean_copy, recs, True)
        records.extend(recs)
        chars += sum(len(json.dumps(r, ensure_ascii=False, default=str)) for r in recs[:5]) * max(1, len(recs)) // max(1, len(recs[:5]))
        if len(records) >= DATASET_RECORDS_MAX or chars >= DATASET_CHARS_MAX:
            note = "stopped at the dataset size limit"
            break
        if time.time() - started > FETCH_SECONDS:
            note = "stopped at the time limit"
            break
        # where is the next page?
        if style == "page":
            cur = _get_arg(cur_args, param)
            if cur is None:                    # first call without the argument: the source says where it is
                reported = info.get("page")
                cur = reported if isinstance(reported, int) and not isinstance(reported, bool) else 1
            try:
                cur = int(cur)                 # 0 is a real page number on a zero-based source
            except (TypeError, ValueError):
                cur = 1
            total_pages = info.get("total_pages")
            if isinstance(total_pages, int) and not isinstance(total_pages, bool) and cur >= total_pages:
                complete = True                # checked against the reported total below
                break
            if info.get("has_more") is False:
                complete = True
                break
            cur_args = _set_arg(cur_args, param, cur + 1)
        elif style == "offset":
            total = info.get("total")
            if isinstance(total, int) and not isinstance(total, bool) and len(records) >= total:
                complete = True
                break
            if info.get("has_more") is False:
                complete = True
                break
            try:
                cur = int(_get_arg(cur_args, param) or 0)
            except (TypeError, ValueError):
                cur = 0
            cur_args = _set_arg(cur_args, param, cur + len(recs))
        elif style == "cursor":
            nxt = info.get("next_cursor")
            if not nxt or info.get("has_more") is False:
                complete = True
                break
            cur_args = _set_arg(cur_args, param, nxt)
        else:
            if pages > 1:
                note = ("only one page read: no paging argument was found in the tool's schema. Pass `page_param` "
                        "with its name")
            break
    if not records:
        # one answer without a record list (a report object, a text page): keep it as an ordinary stored result
        loaded = await asyncio.to_thread(query.load, first_text, None)
        ref = await asyncio.to_thread(store.put, first_text, scope=scope, tool=name,
                                      conn_id=str((ent.get("conn") or {}).get("id") or ""),
                                      kind="text" if loaded["kind"] == "text" else "json")
        return "", loaded, ref, {"source_tool": name, "pages_read": 1}
    total = total_seen
    if isinstance(total, int):
        # The source's own count has the last word: fewer records than it reports is never "complete".
        if len(records) >= total:
            complete = True
        elif complete:
            complete = False
            note = note or f"read {len(records)} of the {total} records the source reports"
    meta = {"source_tool": name, "pages_read": used, "records": len(records), "complete": bool(complete),
            "fetched_at": int(time.time())}
    if isinstance(total, int) and not isinstance(total, bool):
        meta["reported_total"] = total
    if note:
        meta["note"] = note
    if not complete and not note and used >= pages and pages > 0:
        meta["note"] = f"read {used} page(s) as asked; more may exist. Pass a larger `pages` to read on"
    body = await asyncio.to_thread(query.make_dataset, records, meta)
    ref = await asyncio.to_thread(store.put, body, scope=scope, tool=name,
                                  conn_id=str((ent.get("conn") or {}).get("id") or ""), kind="dataset", meta=meta)
    loaded = {"kind": "records", "records": records, "pointer": "/records", "data": None, "meta": meta}
    return "", loaded, ref, meta


def _view(loaded: dict, ref: str, args: dict, source: Optional[dict], scope: str = "") -> str:
    max_chars = query.clamp_chars(args.get("max_chars"))
    kind = loaded["kind"]
    if kind == "text":
        if args.get("sql") or args.get("fields"):
            raise query.QueryError("this result is plain text, not records: use `search` or `offset`/`limit` (lines).")
        out = query.text_view(loaded["text"], ref, search=str(args.get("search") or ""),
                              offset=args.get("offset") or 0, limit=args.get("limit") or 80, max_chars=max_chars)
        return out
    if kind == "document":
        if args.get("sql"):
            raise query.QueryError("this result has no list of records to query. Pass `path` to a list inside it, "
                                   "or read it without `sql`.")
        doc = loaded["data"]
        for depth, text_max in ((6, 2000), (4, 600), (3, 200), (2, 120), (1, 80)):
            text = json.dumps({"javis_query": {"ref": ref, "shown_as": "document" if depth == 6 else "outline"},
                               "document": shaper.outline(shaper.lean_copy(doc, True), 0, depth, text_max)},
                              ensure_ascii=False, separators=(",", ":"), default=str)
            if len(text) <= max_chars:
                return text
        return text[:max_chars]
    # the next question on the same stored result reuses its database (scope in the key: a ref is per brain)
    cache_key = f"{store.norm_scope(scope)}|{ref}|{loaded.get('pointer')}" if ref else ""
    if args.get("sql"):
        out = query.run_sql(loaded, ref, args["sql"], max_chars=max_chars, cache_key=cache_key)
    elif args.get("describe"):
        out = query.schema_view(loaded, ref, max_chars=max_chars, cache_key=cache_key)
    else:
        out = query.slice_records(loaded, ref, fields=args.get("fields"), offset=args.get("offset") or 0,
                                  limit=args.get("limit") or 50, max_chars=max_chars)
    if source:
        doc = json.loads(out)
        doc["javis_query"]["source"] = source
        out = json.dumps(doc, ensure_ascii=False, separators=(",", ":"), default=str)
    return out


def build(route_ref: dict, specs_ref: dict, scope: str) -> tuple:
    """(tool spec, route entry) of javis_query for one discovered tool list.

    `route_ref` / `specs_ref` are filled by the hub AFTER every other tool is in place, so the
    closure dispatches through the final guarded routes."""

    async def _call(args):
        args = args if isinstance(args, dict) else {}
        ref = str(args.get("ref") or "").strip()
        name = str(args.get("tool") or "").strip()
        try:
            source = None
            if ref:
                got = await asyncio.to_thread(store.get, ref, scope)
                if not got:
                    return _expired(ref)
                loaded = await asyncio.to_thread(query.load, got["text"], args.get("path") or None)
                if got.get("kind") == "dataset" and loaded.get("meta"):
                    m = loaded["meta"]
                    source = {k: m[k] for k in ("source_tool", "pages_read", "complete", "reported_total", "note")
                              if k in m}
            elif name:
                targs = args.get("args")
                if isinstance(targs, str):
                    try:
                        targs = json.loads(targs)
                    except ValueError:
                        targs = {}
                err, loaded, ref, meta = await fetch_dataset(
                    route_ref, specs_ref, name, targs if isinstance(targs, dict) else {},
                    pages=args.get("pages") or 1, page_param=str(args.get("page_param") or ""),
                    path=str(args.get("path") or ""), scope=scope)
                if err:
                    return err
                source = {k: meta[k] for k in ("source_tool", "pages_read", "complete", "reported_total", "note")
                          if k in meta}
                if not ref:
                    source["ref_unavailable"] = "this dataset could not be stored; repeat `tool`+`args` to query again"
            else:
                return _err("pass `ref` (a stored result) or `tool`+`args` (a read-only connection tool).")
            # SQL runs in its own small pool: a slow query waits behind other queries, never in front of the
            # server's general worker threads.
            answer = await asyncio.get_running_loop().run_in_executor(
                _QUERY_POOL, _view, loaded, ref, args, source, scope)
            try:
                import mcp_hub
                await asyncio.to_thread(mcp_hub.note_query_answer, name or TOOL, len(answer))
                # part of a recurring job's read chain (job_recipes.py): recorded like any other read call
                import job_recipes
                import turn_context
                job = str((turn_context.current() or {}).get("job") or "")
                if job and shaper.audience() == "model":
                    job_recipes.note_call(job, TOOL, args, ok=True, ref=ref)
            except Exception:  # noqa: BLE001 - the meter and the recorder must never fail the answer
                pass
            return answer
        except query.QueryError as e:
            return _err(str(e))
        except Exception as e:  # noqa: BLE001 - a tool must answer, not raise
            return _err(f"{TOOL} failed: {type(e).__name__}: {e}")

    spec = {"fn": TOOL, "server": "javis", "name": TOOL, "namespace": "javis", "description": DESCRIPTION,
            "schema": SCHEMA}
    entry = {"call": _call, "hat_nhan": True, "source_type": "builtin", "source_id": "javis",
             "effect": "read", "required_mode": "readonly", "health": "healthy"}
    return spec, entry
