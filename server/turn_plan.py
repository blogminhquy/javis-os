"""The task plan an engine keeps while it works through a turn, for the plan card in the chat.

Owner, 08/11/2026: Claude's own app shows a "Plan" checklist beside a long task (what is done, what runs now, what is
left) and Javis showed nothing. The engines already make that list: Claude Code calls `TodoWrite` (or `TaskCreate` /
`TaskUpdate` in newer builds), Codex sends `turn/plan/updated` (app-server) or a `todo_list` item (`codex exec`), Grok
Build calls `todo_write`. main.py used to keep only one line of the call for the step block ("Update task list"), so
the list itself was thrown away.

`plan_op(ev)` reads a `tool_call` event and returns what changed in the plan, or None for any other tool:

  {"op": "set", "items": [{"text", "status"}]}      the whole list (TodoWrite, update_plan, todo_list...)
  {"op": "add", "text"}                             one new item (TaskCreate; its id comes in the tool result)
  {"op": "update", "id", "status"?, "text"?}        one item changed (TaskUpdate); status "deleted" removes it

`status` is always one of "pending", "active", "done". `fields(ev)` puts the op in a WebSocket frame under
`plan`. The dashboard (chat-steps.js) merges the ops into the turn's step state and draws the checklist.

No model call, no extra tokens: this only reads what the engine already sent. Read-only and never raises.
"""
import json
import re

MAX_ITEMS = 30     # a plan longer than this is a log, not a checklist
MAX_TEXT = 200     # one line in the chat

# Tools that send the WHOLE list each time. Names as the engines spell them; the short name after "mcp__x__" counts.
_SET_TOOLS = re.compile(r"^(todowrite|todo_write|write_todos|update_todos|todo_update|update_plan|todo_list|javis_plan)$")
_ADD_TOOLS = re.compile(r"^(taskcreate|task_create)$")
_UPDATE_TOOLS = re.compile(r"^(taskupdate|task_update)$")

# Keys that may hold the list, then keys that may hold one item's words.
_LIST_KEYS = ("todos", "plan", "items", "tasks", "steps")
_TEXT_KEYS = ("content", "step", "text", "title", "subject", "description", "task", "name")

_ACTIVE = {"in_progress", "inprogress", "in-progress", "active", "running", "doing", "started", "current"}
_DONE = {"completed", "complete", "done", "finished", "success", "succeeded", "cancelled", "canceled", "skipped"}


def _short_name(name) -> str:
    n = str(name or "").strip()
    m = re.match(r"^mcp__.+?__(.+)$", n)
    return (m.group(1) if m else n).lower()


def _as_dict(v):
    if isinstance(v, str) and v.strip()[:1] == "{":
        try:
            v = json.loads(v)
        except Exception:
            return None
    return v if isinstance(v, dict) else None


def _status(item: dict) -> str:
    if item.get("completed") is True or item.get("done") is True:
        return "done"
    s = str(item.get("status") or item.get("state") or "").strip().lower().replace(" ", "_")
    if s in _ACTIVE:
        return "active"
    if s in _DONE:
        return "done"
    return "pending"


def _one_line(s) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= MAX_TEXT else s[:MAX_TEXT - 1].rstrip() + "…"


def _text(item: dict) -> str:
    for k in _TEXT_KEYS:
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return _one_line(v)
    return ""


def _payloads(ev: dict):
    """Every dict that may carry the tool's arguments, nearest first."""
    out = []
    for k in ("input", "arguments", "parameters", "args"):
        d = _as_dict(ev.get(k))
        if d is not None:
            out.append(d)
    it = ev.get("item")
    if isinstance(it, dict):
        out.append(it)    # Codex exec todo_list: {"type": "todo_list", "items": [...]}
        for k in ("input", "arguments", "parameters", "args"):
            d = _as_dict(it.get(k))
            if d is not None:
                out.append(d)
    return out


def _items(ev: dict):
    for d in _payloads(ev):
        for k in _LIST_KEYS:
            v = d.get(k)
            if not isinstance(v, list):
                continue
            items = []
            for x in v:
                if isinstance(x, str) and x.strip():
                    items.append({"text": _one_line(x), "status": "pending"})
                elif isinstance(x, dict):
                    t = _text(x)
                    if t:
                        items.append({"text": t, "status": _status(x)})
            if items:
                return items[:MAX_ITEMS]
    return None


def _first(ev: dict, keys):
    for d in _payloads(ev):
        for k in keys:
            v = d.get(k)
            if isinstance(v, (str, int)) and str(v).strip():
                return str(v).strip()
    return ""


def plan_op(ev):
    """The plan change carried by one `tool_call` event, or None when the tool is not a plan tool."""
    try:
        if not isinstance(ev, dict):
            return None
        name = _short_name(ev.get("name") or ev.get("tool") or (ev.get("item") or {}).get("type"))
        if _SET_TOOLS.match(name):
            items = _items(ev)
            return {"op": "set", "items": items} if items else None
        if _ADD_TOOLS.match(name):
            t = _one_line(_first(ev, ("subject", "title", "content", "description")))
            return {"op": "add", "text": t} if t else None
        if _UPDATE_TOOLS.match(name):
            tid = _first(ev, ("taskId", "task_id", "id"))
            if not tid:
                return None
            op = {"op": "update", "id": tid}
            raw = _first(ev, ("status",)).lower()
            if raw == "deleted":
                op["status"] = "deleted"
            elif raw:
                op["status"] = _status({"status": raw})
            t = _one_line(_first(ev, ("subject", "title")))
            if t:
                op["text"] = t
            return op
    except Exception:
        pass
    return None


def fields(ev) -> dict:
    """{"plan": op} for a plan tool, else {}: spread into a `tool_call` frame with `**turn_plan.fields(ev)`."""
    op = plan_op(ev)
    return {"plan": op} if op else {}


def from_codex_notification(params: dict):
    """A Codex app-server `turn/plan/updated` notification as a `tool_call` event named update_plan, or None.

    Params: {"explanation": str|None, "plan": [{"step": str, "status": "pending"|"inProgress"|"completed"}]}."""
    try:
        plan = (params or {}).get("plan")
        if not isinstance(plan, list) or not plan:
            return None
        return {"type": "tool_call", "name": "update_plan", "input": {"plan": plan}}
    except Exception:
        return None
