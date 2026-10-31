"""Read-only Google Calendar events for the Tasks page, tab "Mine" (0.427.0). Spec: docs/dev/2026-10-nhiem-vu-spec.md 6.

The events come from a calendar MCP the owner connected on the Connections page: the Google Calendar connector
(`google-calendar`), Google Workspace (`google-workspace`), or a custom connection whose name says calendar. Javis never
writes to the calendar from here; the page shows the events next to the owner's appointments and links to Google to edit.

Tool names and argument names differ per server, so the list tool and its time-window arguments are found from the
server's own tool list (`inputSchema`), and the answer is read as JSON when it is JSON, else as the plain lines that
workspace-mcp prints.
"""
from __future__ import annotations

import json
import re
from typing import Optional

CONNECTORS = ("google-calendar", "google-workspace")
TOOL_NAMES = ("list_events", "get_events", "events_list", "list_calendar_events", "googlecalendar_events_list",
              "googlecalendar_find_event", "search_events")
_START_KEYS = ("timeMin", "time_min", "start_time", "startTime", "time_start", "start", "from", "min_time")
_END_KEYS = ("timeMax", "time_max", "end_time", "endTime", "time_end", "end", "to", "max_time")
_CAL_KEYS = ("calendarId", "calendar_id")
_MAX_KEYS = ("maxResults", "max_results", "limit", "max_events")
_SINGLE_KEYS = ("singleEvents", "single_events")
_EMAIL_KEYS = ("user_google_email", "userGoogleEmail", "email")
MAX_EVENTS = 300


def is_calendar(conn: dict) -> bool:
    if conn.get("connector_id") in CONNECTORS:
        return True
    text = " ".join(str(conn.get(k) or "") for k in ("label", "slug", "name", "url")).lower()
    return conn.get("connector_id") == "custom" and ("calendar" in text or "gcal" in text)


def pick_tool(tools: list) -> Optional[dict]:
    """The tool that lists events: a known name first, else a read-looking tool about events."""
    by = {str(t.get("name") or "").lower(): t for t in tools or [] if isinstance(t, dict)}
    for n in TOOL_NAMES:
        if n in by:
            return by[n]
    for n, t in by.items():
        if "event" in n and any(w in n for w in ("list", "get", "search", "find")) \
                and not any(w in n for w in ("create", "update", "delete", "insert", "move", "patch", "respond")):
            return t
    return None


def build_args(tool: dict, start_iso: str, end_iso: str, conn: dict) -> Optional[dict]:
    """Arguments for the list tool from its schema. None when a required argument cannot be filled."""
    schema = tool.get("inputSchema") or tool.get("input_schema") or {}
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    args: dict = {}

    def first(keys):
        return next((k for k in keys if k in props), None)

    k = first(_START_KEYS)
    if k:
        args[k] = start_iso
    k = first(_END_KEYS)
    if k:
        args[k] = end_iso
    k = first(_CAL_KEYS)
    if k:
        args[k] = "primary"
    k = first(_MAX_KEYS)
    if k:
        args[k] = 100
    k = first(_SINGLE_KEYS)
    if k:
        args[k] = True
    k = first(_EMAIL_KEYS)
    if k:
        env = conn.get("env") or {}
        mail = env.get("USER_GOOGLE_EMAIL") or env.get("GOOGLE_EMAIL") or ""
        if mail:
            args[k] = mail
    if not required <= set(args):
        return None
    return args


def _when(v) -> tuple:
    """(iso string, all_day) from a Google start/end value: {"dateTime": ...} | {"date": ...} | "..."."""
    if isinstance(v, dict):
        if v.get("dateTime") or v.get("date_time"):
            return str(v.get("dateTime") or v.get("date_time")), False
        if v.get("date"):
            return str(v["date"]), True
        return "", False
    s = str(v or "").strip()
    return s, bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", s))


def _event(e: dict) -> Optional[dict]:
    if not isinstance(e, dict) or str(e.get("status") or "").lower() == "cancelled":
        return None
    start, all_day = _when(e.get("start") or e.get("start_time") or e.get("startTime"))
    end, _ = _when(e.get("end") or e.get("end_time") or e.get("endTime"))
    title = str(e.get("summary") or e.get("title") or e.get("name") or "").strip()
    if not start or not title:
        return None
    return {"id": str(e.get("id") or e.get("event_id") or f"{start}|{title}")[:200], "title": title[:300],
            "start": start, "end": end, "all_day": all_day, "location": str(e.get("location") or "")[:300],
            "link": str(e.get("htmlLink") or e.get("html_link") or e.get("link") or e.get("url") or "")[:500]}


def _find_list(d, depth: int = 0):
    if depth > 4:
        return None
    if isinstance(d, list):
        if any(isinstance(x, dict) and ("start" in x or "summary" in x) for x in d):
            return d
        for x in d:
            got = _find_list(x, depth + 1)
            if got:
                return got
        return None
    if isinstance(d, dict):
        for k in ("items", "events", "data", "results", "result", "response_data"):
            if k in d:
                got = _find_list(d[k], depth + 1)
                if got:
                    return got
        for v in d.values():
            if isinstance(v, (list, dict)):
                got = _find_list(v, depth + 1)
                if got:
                    return got
    return None


# workspace-mcp prints: - "Title" (Starts: 2026-10-31T09:00:00+07:00, Ends: 2026-10-31T10:00:00+07:00) ID: abc | Link: https://...
_LINE = re.compile(r'"(?P<t>[^"]+)"\s*\(Starts:\s*(?P<s>[^,]+),\s*Ends:\s*(?P<e>[^)]+)\)'
                   r'(?:[^\n]*?ID:\s*(?P<id>[^\s|]+))?(?:[^\n]*?Link:\s*(?P<l>\S+))?')


def parse_events(raw: str) -> list:
    text = str(raw or "").strip()
    data = None
    try:
        data = json.loads(text)
    except Exception:
        m = re.search(r"[\[{][\s\S]*[\]}]", text)
        if m:
            try:
                data = json.loads(m.group(0))
            except Exception:
                data = None
    out = []
    if data is not None:
        for e in _find_list(data) or []:
            ev = _event(e)
            if ev:
                out.append(ev)
    else:
        for m in _LINE.finditer(text):
            ev = _event({"summary": m.group("t"), "start": m.group("s").strip(), "end": m.group("e").strip(),
                         "id": m.group("id") or "", "htmlLink": m.group("l") or ""})
            if ev:
                out.append(ev)
    return out[:MAX_EVENTS]


async def events(brain: str, start_iso: str, end_iso: str, conns=None, pool=None, spec_of=None) -> dict:
    """{ok, connected, events, sources, error}. `conns`, `pool`, `spec_of` are for tests; by default the enabled
    connections from mcp_store and the shared mcp_client pool."""
    if conns is None:
        import mcp_store
        conns = mcp_store.resolved(enabled_only=True)
    cal = [c for c in conns or [] if is_calendar(c)]
    if not cal:
        return {"ok": True, "connected": False, "events": [], "sources": []}
    if pool is None or spec_of is None:
        import mcp_client
        pool = pool or mcp_client.pool
        spec_of = spec_of or mcp_client._conn_spec
    found, sources, errors = [], [], []
    for c in cal:
        name = str(c.get("label") or c.get("slug") or c.get("connector_id") or "calendar")
        try:
            spec = spec_of(c)
            tool = pick_tool(await pool.list_tools(spec))
            if not tool:
                errors.append(f"{name}: no tool that lists events")
                continue
            args = build_args(tool, start_iso, end_iso, c)
            if args is None:
                errors.append(f"{name}: {tool.get('name')} needs arguments Javis cannot fill")
                continue
            raw = await pool.call_tool(spec, tool["name"], args)
            if isinstance(raw, str) and raw.startswith("ERROR:"):
                errors.append(f"{name}: {raw[6:].strip()[:200]}")
                continue
            evs = parse_events(raw)
            for e in evs:
                e["source"] = name
            found += evs
            sources.append(name)
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}: {str(e)[:160]}")
    found.sort(key=lambda e: e["start"])
    return {"ok": bool(sources) or not errors, "connected": True, "events": found[:MAX_EVENTS], "sources": sources,
            "error": "; ".join(errors)[:600]}
