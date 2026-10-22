"""A stdio MCP server still on its first start (npx downloading) must not be killed by a discovery
that gives up on it.

    python tests/run.py mcp_cold_install_not_killed      (no network; spawns a small Python server)

Field report 2026-10-13 (VPS, Docker): after a container rebuild the Google Search Console
connector (`npx -y mcp-server-gsc@latest`) failed on every start with MODULE_NOT_FOUND for three
and a half days. Its npx folder had `node_modules/ajv` and `node_modules/hono` without package.json.

Chain of cause:
  1. A rebuild empties the npm cache, so the first `npx -y` start downloads the package. A cold
     install of mcp-server-gsc measured 19.2 s on that VPS.
  2. The boot warm-up opens the session with a wide cap (180 s), but any chat turn, Codex job or
     health check that lists tools at the same time uses the SAME pooled session with the 20 s
     cap of `tran_dial`.
  3. When that cap fired, `discover_resolved` invalidated the session: SIGKILL on the whole
     process tree, npm included, in the middle of extracting packages.
  4. The next start found the half-extracted folder. npx treats it as installed, Node cannot load
     `ajv`, and Check only respawns npx on the same folder.

This file locks the session side: the handshake runs in its own task, a caller that stops waiting
leaves the process running, and the next caller gets the tools from the same process. It also keeps
the reason the invalidation exists: a server stuck in the middle of a request after its handshake
is still thrown away, and a handshake that never answers is still bounded.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import glob
import os
import sys
import tempfile
import time
from pathlib import Path

# Hard-set before importing server modules: mcp_orphans writes STATE_DIR, npx_cache reads HOME.
_TMP = Path(tempfile.mkdtemp(prefix="javis-cold-install-"))
os.environ["JAVIS_STATE_DIR"] = str(_TMP / "state")
os.environ["HOME"] = str(_TMP / "home")
for _d in ("state", "home"):
    (_TMP / _d).mkdir(parents=True, exist_ok=True)

import mcp_client  # noqa: E402

HELPER = str(Path(__file__).resolve().parent / "_slow_start_mcp_server.py")
fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def conn(i, marker, delay, *extra):
    return {"id": f"cold{i}", "connector_id": "custom", "label": f"slow source {i}", "slug": f"cold{i}",
            "namespace": f"cold{i}", "transport": "stdio", "url": "", "command": sys.executable,
            "args": [HELPER, "--delay", str(delay), "--marker", str(marker), *extra], "headers": {},
            "env": {}, "internal": "", "secrets": {}, "config": {}, "perm": "full", "deny_tools": [],
            "is_default": False, "auth": None, "connector": {}}


def markers(marker, kind):
    """Marker files in creation order (pid order breaks when the pid gains a digit)."""
    return sorted(glob.glob(os.path.join(str(marker), f"{kind}.*")), key=os.path.getmtime)


def alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    # A zombie still answers kill(0); read its state where /proc exists.
    try:
        return Path(f"/proc/{pid}/stat").read_text().split(")")[-1].split()[0] != "Z"
    except OSError:
        return True


def pid_of(path):
    return int(path.rsplit(".", 1)[1])


async def wait_until(pred, timeout=10.0, step=0.1):
    """Poll for something that must happen. A fixed short sleep turned red on a loaded CI box:
    a fresh Python process can need more than a second just to start."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        await asyncio.sleep(step)
    return bool(pred())


async def scenario_warmup_and_chat_turn():
    """Boot warm-up (wide cap) and a chat turn (short cap) on the same cold source."""
    marker = _TMP / "m1"
    marker.mkdir()
    c = conn(1, marker, 2.0)
    os.environ["JAVIS_MCP_WARM_TIMEOUT"] = "15"
    os.environ["JAVIS_MCP_DISCOVER_TIMEOUT"] = "0.4"
    warm = asyncio.ensure_future(mcp_client.warm_pool([c]))
    await asyncio.sleep(0.3)
    skipped = set()
    tools, _ = await mcp_client.discover_resolved([c], bo_qua=skipped)
    await asyncio.sleep(0.5)                 # the pool closes sessions in the background
    started = markers(marker, "started")
    check("chat turn during the cold start: source skipped this round, not served half-ready",
          tools == [] and skipped == {"cold1"}, (tools, skipped))
    check("the cold process is still alive after the chat turn gave up (this was the bug)",
          len(started) == 1 and alive(pid_of(started[0])), started)
    hot, cold = await warm
    check("boot warm-up finishes on that same process", hot == ["cold1"] and cold == [], (hot, cold))
    tools2, _ = await mcp_client.discover_resolved([c])
    check("next chat turn gets the tool", [t["name"] for t in tools2] == ["echo"], tools2)
    check("one spawn in total: no kill-and-respawn loop", len(markers(marker, "started")) == 1,
          markers(marker, "started"))
    await mcp_client.pool.close_all()


async def scenario_short_caps_only():
    """No warm-up at all: rounds of short-cap discovery from two callers (a chat turn and a
    background Codex job), the cold start longer than every single cap."""
    marker = _TMP / "m2"
    marker.mkdir()
    c = conn(2, marker, 1.5)
    os.environ["JAVIS_MCP_DISCOVER_TIMEOUT"] = "0.4"
    names = []
    deadline = time.time() + 8
    while time.time() < deadline:
        a, b = await asyncio.gather(mcp_client.discover_resolved([c]), mcp_client.discover_resolved([c]))
        names = [t["name"] for t in a[0]] + [t["name"] for t in b[0]]
        if "echo" in names:
            break
        await asyncio.sleep(0.2)
    check("short-cap callers only: the source comes up once the download is over",
          "echo" in names, names)
    check("and it was started exactly once (every round used to kill it again)",
          len(markers(marker, "started")) == 1, markers(marker, "started"))
    await mcp_client.pool.close_all()


async def scenario_stuck_request_still_discarded():
    """Reverse side: a server that finished its handshake and then hangs in tools/list is
    still thrown away, exactly as before."""
    marker = _TMP / "m3"
    marker.mkdir()
    c = conn(3, marker, 0.0, "--hang-list")
    os.environ["JAVIS_MCP_DISCOVER_TIMEOUT"] = "0.6"
    spec = mcp_client._conn_spec(c)
    await mcp_client.pool._get(spec)[1].ensure_init()      # handshake done
    skipped = set()
    tools, _ = await mcp_client.discover_resolved([c], bo_qua=skipped)
    await wait_until(lambda: not alive(pid_of(markers(marker, "started")[0])), timeout=10)
    started = markers(marker, "started")
    check("stuck in tools/list after the handshake: still skipped", tools == [] and skipped == {"cold3"},
          (tools, skipped))
    check("and the stuck process is still killed (the reason the invalidation exists)",
          len(started) == 1 and not alive(pid_of(started[0])), started)
    check("the pool forgot the stuck session", "cold3" not in mcp_client.pool._sessions)
    await mcp_client.pool.close_all()


async def scenario_handshake_still_bounded():
    """A handshake that never comes is bounded by the session's own budget, not by the caller,
    and the process that failed it is killed, never handed a second `initialize`."""
    marker = _TMP / "m4"
    marker.mkdir()
    c = conn(4, marker, 30.0)
    os.environ["JAVIS_MCP_INIT_TIMEOUT"] = "1"
    spec = mcp_client._conn_spec(c)
    sess = mcp_client.pool._get(spec)[1]
    t0 = time.time()
    err = None
    try:
        await sess.ensure_init()
    except Exception as e:      # noqa: BLE001
        err = e
    took = time.time() - t0
    first = markers(marker, "started")
    check("a handshake that never answers fails on the session's own timeout",
          isinstance(err, (asyncio.TimeoutError, TimeoutError)) and took < 5,
          (type(err).__name__ if err else None, round(took, 2)))
    check("and the session no longer counts as starting", not getattr(sess, "is_starting", lambda: True)())
    check("the process that failed its handshake is killed, not kept for a second try",
          len(first) == 1 and not alive(pid_of(first[0])), first)
    check("the failure is remembered for the health check", bool(getattr(sess, "last_init_error", "")))
    try:
        await asyncio.wait_for(sess.ensure_init(), timeout=0.3)
    except (asyncio.TimeoutError, TimeoutError):
        pass
    await wait_until(lambda: len(markers(marker, "started")) == 2)
    check("the next attempt starts a fresh process", len(markers(marker, "started")) == 2,
          markers(marker, "started"))
    os.environ.pop("JAVIS_MCP_INIT_TIMEOUT", None)
    await mcp_client.pool.close_all()


async def scenario_hung_at_startup_not_kept_forever():
    """Review finding: a server that hangs at startup must not read as "starting" forever.
    Discovery keeps it only for its own handshake budget; then it is killed and replaced."""
    marker = _TMP / "m6"
    marker.mkdir()
    c = conn(6, marker, 60.0)
    os.environ["JAVIS_MCP_INIT_TIMEOUT"] = "1"
    os.environ["JAVIS_MCP_DISCOVER_TIMEOUT"] = "0.3"
    spec = mcp_client._conn_spec(c)
    deadline = time.time() + 20
    while time.time() < deadline:
        await mcp_client.discover_resolved([c])
        await asyncio.sleep(0.4)
        done = markers(marker, "started")
        if len(done) >= 2 and all(not alive(pid_of(p)) for p in done[:-1]):
            break
    started = markers(marker, "started")
    check("a server hung at startup is replaced after its handshake budget (not kept for good)",
          len(started) >= 2 and all(not alive(pid_of(p)) for p in started[:-1]), started)
    init_error = getattr(mcp_client.pool, "init_error", lambda spec: "")
    check("and health no longer calls it a first start", bool(init_error(spec)))
    os.environ.pop("JAVIS_MCP_INIT_TIMEOUT", None)
    await mcp_client.pool.close_all()


async def scenario_deferred_invalidation():
    """A connection edit (mcp_hub.invalidate_cache) while a source is downloading: the process
    finishes its install, is closed right after its handshake, and the next use starts fresh
    (the edit may have changed its credentials)."""
    marker = _TMP / "m7"
    marker.mkdir()
    c = conn(7, marker, 1.2)
    spec = mcp_client._conn_spec(c)
    sess = mcp_client.pool._get(spec)[1]
    try:
        await asyncio.wait_for(sess.ensure_init(), timeout=0.2)
    except (asyncio.TimeoutError, TimeoutError):
        pass
    try:
        mcp_client.pool.invalidate("cold7", defer_if_starting=True)
    except TypeError:            # a tree without the fix: plain invalidate
        mcp_client.pool.invalidate("cold7")
    await asyncio.sleep(0.4)
    first = markers(marker, "started")
    check("connection edit during the download: the downloading process is not killed",
          len(first) == 1 and alive(pid_of(first[0])), first)
    await wait_until(lambda: len(markers(marker, "ready")) == 1 and not mcp_client.pool.is_starting_key("cold7")
                     if hasattr(mcp_client.pool, "is_starting_key") else len(markers(marker, "ready")) == 1)
    check("it finished its handshake (its install completed)", len(markers(marker, "ready")) == 1,
          markers(marker, "ready"))
    tools = await mcp_client.pool.list_tools(spec)
    await wait_until(lambda: len(markers(marker, "started")) == 2 and not alive(pid_of(markers(marker, "started")[0])))
    started = markers(marker, "started")
    check("then the next use runs on a fresh process (the edit applies)",
          len(started) == 2 and not alive(pid_of(started[0])) and [t["name"] for t in tools] == ["echo"],
          (started, tools))
    await mcp_client.pool.close_all()


class _FakeSession:
    """Stands in for a pooled session: `is_starting` is set by the test, `close` is recorded."""

    def __init__(self, name):
        self.name = name
        self.starting = False
        self.closed = False

    def is_starting(self):
        return self.starting

    async def close(self):
        self.closed = True


async def scenario_stale_session_waits_for_running_tool_call():
    """A session marked stale (`invalidate(defer_if_starting=True)`) whose handshake is over must
    not be closed by `_get` while a tool call is still running on it (`ban`): closing a stdio
    session kills its process tree and the call with it. Once the call ends, the next `_get`
    closes it and hands out a fresh session."""
    pool = mcp_client.SessionPool()
    made = []

    def fake_make(spec):
        made.append(_FakeSession(f"s{len(made) + 1}"))
        return made[-1]

    pool._make = fake_make
    spec = {"key": "fakeban", "transport": "http", "url": "http://127.0.0.1:9/mcp", "headers": {}}
    key, first = pool._get(spec)
    first.starting = True
    release = asyncio.Event()

    async def tool_call(sess):
        await release.wait()
        return "done"

    call = asyncio.create_task(pool._chay(key, first, tool_call, True))
    await asyncio.sleep(0)
    pool.invalidate(key, defer_if_starting=True)
    check("a starting session is only marked stale", pool._sessions[key].get("stale") is True)
    first.starting = False              # handshake over, the tool call still holds `ban`
    _, again = pool._get(spec)
    await asyncio.sleep(0)
    check("stale but a tool call is running: _get keeps the same session",
          again is first and not first.closed, (getattr(again, "name", again), first.closed))
    check("and the tool call is not cut", not call.done())
    release.set()
    check("the tool call finishes on that session", await call == "done")
    _, fresh = pool._get(spec)
    await asyncio.sleep(0)
    check("once the call is over, the next _get closes the stale session",
          first.closed, first.closed)
    check("and hands out a fresh one", fresh is not first and len(made) == 2,
          (getattr(fresh, "name", fresh), len(made)))


async def scenario_cancelled_waiter_keeps_handshake():
    """The mechanism itself: cancelling a waiter does not cancel the handshake task."""
    marker = _TMP / "m5"
    marker.mkdir()
    c = conn(5, marker, 1.0)
    spec = mcp_client._conn_spec(c)
    sess = mcp_client.pool._get(spec)[1]
    try:
        await asyncio.wait_for(sess.ensure_init(), timeout=0.3)
    except (asyncio.TimeoutError, TimeoutError):
        pass
    # Read with getattr so this file still runs (and turns red) on a tree without the fix.
    sess_starting = getattr(sess, "is_starting", lambda: False)
    pool_starting = getattr(mcp_client.pool, "is_starting", lambda spec: False)
    check("a waiter that gave up leaves the session starting", sess_starting())
    check("the pool reports it as starting", pool_starting(spec))
    tools = await sess.list_tools()
    check("the next waiter gets the tools from the same process",
          [t["name"] for t in tools] == ["echo"] and len(markers(marker, "started")) == 1, tools)
    check("starting is over once the handshake is done", not pool_starting(spec))
    await mcp_client.pool.close_all()


async def main():
    await scenario_warmup_and_chat_turn()
    await scenario_short_caps_only()
    await scenario_stuck_request_still_discarded()
    await scenario_handshake_still_bounded()
    await scenario_hung_at_startup_not_kept_forever()
    await scenario_deferred_invalidation()
    await scenario_stale_session_waits_for_running_tool_call()
    await scenario_cancelled_waiter_keeps_handshake()


asyncio.run(main())
for k in ("JAVIS_MCP_WARM_TIMEOUT", "JAVIS_MCP_DISCOVER_TIMEOUT"):
    os.environ.pop(k, None)

print()
if fails:
    print(f"RED {len(fails)}: " + "; ".join(fails[:4]))
    raise SystemExit(1)
print("All green.")
