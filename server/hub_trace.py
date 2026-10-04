"""Short in-memory trace of the MCP hub's startup requests (0.72.1).

When Claude Code starts it connects to the Javis hub (`/hub/mcp`) and asks `initialize` and
`tools/list` before it takes any work. If that startup times out, the question that decides
where to look is whether Claude ever reached the hub at all:

  - it never called: Claude is stuck before the hub (login, network, self-update), and no MCP
    source can be to blame;
  - it called and the hub answered late or not at all: the tool discovery is the culprit;
  - it called and the hub answered fast: the hub is fine, Claude is stuck on something else.

The hub runs in the same process as the engine, so a ring buffer is enough. No deps, no I/O.
"""
import collections
import time

# Only the two requests Claude makes before it accepts work. tools/call is not startup.
_TRACKED = ("initialize", "tools/list")
_EVENTS = collections.deque(maxlen=64)


def begin(method):
    """Record the start of a hub request. Returns a handle for `end`, or None if untracked."""
    if method not in _TRACKED:
        return None
    ev = {"t0": time.time(), "method": method, "dur": None}
    _EVENTS.append(ev)
    return ev


def end(ev):
    """Close a request opened by `begin`. Safe to call with None."""
    if ev is not None and ev["dur"] is None:
        ev["dur"] = time.time() - ev["t0"]


def since(t_start):
    """Summary of the tracked requests that began at or after `t_start` (epoch seconds).

    {"called": bool, "init_s": float|None, "list_s": float|None,
     "pending": "initialize"|"tools/list"|None, "pending_s": float}

    `*_s` is the slowest finished duration for that method. `pending` is the oldest request
    still unanswered, with how long it has been waiting.
    """
    out = {"called": False, "init_s": None, "list_s": None, "pending": None, "pending_s": 0.0}
    now = time.time()
    for ev in list(_EVENTS):
        if ev["t0"] < t_start:
            continue
        out["called"] = True
        if ev["dur"] is None:
            age = now - ev["t0"]
            if out["pending"] is None or age > out["pending_s"]:
                out["pending"], out["pending_s"] = ev["method"], age
            continue
        key = "init_s" if ev["method"] == "initialize" else "list_s"
        if out[key] is None or ev["dur"] > out[key]:
            out[key] = ev["dur"]
    return out
