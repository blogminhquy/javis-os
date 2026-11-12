"""javis_scout: a read-only run on the background model that returns only its findings.

    python tests/run.py scout

What must hold, whatever the prompt says:
  - the main model decides when and what, never which model (the owner's background model runs);
  - the scout is built read-only (the `suggest` level, an allowlist of read tools);
  - a scout cannot send a scout, scouts at once are capped, a run is time-boxed;
  - unavailable, busy, slow, broken or empty: one line telling the main model to do the reading
    itself, which is what it did before this tool existed;
  - a customer bot never gets the tool.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-scout-"))

import aux_engine  # noqa: E402
import config  # noqa: E402
import mcp_client  # noqa: E402
import mcp_hub  # noqa: E402
import mcp_store  # noqa: E402
import scout  # noqa: E402
import tool_result_store as store  # noqa: E402
import turn_context  # noqa: E402

_fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        _fails.append(name)


def run(coro):
    return asyncio.run(coro)


TASK = "Read the orders of shop Seego for 2026-10-01 to 2026-10-31 and return revenue per day and the total."
BRAIN = tempfile.mkdtemp(prefix="scout-brain-")
_seen = []


async def good_runner(vault_root, prompt, tag, wall_s):
    _seen.append({"vault": vault_root, "prompt": prompt, "tag": tag, "wall": wall_s,
                  "job": (turn_context.current() or {}).get("job")})
    return {"text": "FINDINGS: revenue 12,300,000 VND (pos_statistics)\nREFS: tr_x\nGAPS: none", "error": "",
            "model": "openrouter test/model", "usage": {"input": 5000, "output": 300}}


# ============================================================
# 1. Off until the host hands over a runner
# ============================================================
scout.configure(None)
check("no runner: not available", not scout.available())
out = run(scout.run(BRAIN, TASK))
check("no runner: the main model is told to read for itself", out.startswith("ERROR:") and "yourself" in out, out)

# ============================================================
# 2. A normal run
# ============================================================
scout.configure(good_runner)
check("a runner makes it available", scout.available())
out = run(scout.run(BRAIN, TASK))
check("the findings come back", "revenue 12,300,000 VND" in out and not out.startswith("ERROR:"), out)
check("the answer says which model read the data and what it cost",
      "model=openrouter test/model" in out and "tokens in=5000 out=300" in out, out[:200])
check("the runner gets the brain, the limit and the careful tag by default",
      _seen[-1]["vault"] == BRAIN and _seen[-1]["tag"] == "scout" and _seen[-1]["wall"] == scout.wall_seconds())
check("the task reaches the scout whole", TASK in _seen[-1]["prompt"])
check("the run is marked as a scout job for the hub", str(_seen[-1]["job"]).startswith("scout:"))
check("the mark is gone once the run ends", turn_context.current() is None)
run(scout.run(BRAIN, TASK, effort="quick"))
check("effort=quick asks for the light tier", _seen[-1]["tag"] == "scout-quick")
check("quick scouts run on the light pick, careful ones on the mid pick",
      aux_engine.tier_for_tag("scout-quick") == "light" and aux_engine.tier_for_tag("scout") == "mid")
check("a brief that cannot stand alone is refused before any model runs",
      run(scout.run(BRAIN, "sales?")).startswith("ERROR:") and "too short" in run(scout.run(BRAIN, "sales?")))

# the owner's turn identity is kept, only the job changes
tok = turn_context.bind(turn_context.make("dashboard", chat_id="web:abc", la_chu=True, session_id="s1"))
run_inside = None


async def identity_runner(vault_root, prompt, tag, wall_s):
    global run_inside
    run_inside = turn_context.current()
    return {"text": "FINDINGS: ok"}

scout.configure(identity_runner)
try:
    asyncio.run(scout.run(BRAIN, TASK))
finally:
    turn_context.reset(tok)
check("the caller's turn is kept, with the scout job added",
      run_inside and run_inside["kenh"] == "dashboard" and run_inside["la_chu"] is True
      and run_inside["job"].startswith("scout:"), run_inside)


# ============================================================
# 3. Limits
# ============================================================
async def nesting_runner(vault_root, prompt, tag, wall_s):
    return {"text": await scout.run(vault_root, TASK)}

scout.configure(nesting_runner)
out = run(scout.run(BRAIN, TASK))
check("a scout cannot send a scout", "a scout cannot send another scout" in out, out)

gate = None
running = 0
peak = 0


async def slow_runner(vault_root, prompt, tag, wall_s):
    global running, peak
    running += 1
    peak = max(peak, running)
    await gate.wait()
    running -= 1
    return {"text": "FINDINGS: done"}


async def many():
    global gate
    gate = asyncio.Event()
    tasks = [asyncio.create_task(scout.run(BRAIN, TASK)) for _ in range(5)]
    await asyncio.sleep(0.05)
    gate.set()
    return await asyncio.gather(*tasks)

scout.configure(slow_runner)
outs = run(many())
check("scouts at once are capped",
      peak == scout.max_parallel() and sum(1 for o in outs if "already running" in o) == 5 - scout.max_parallel(),
      (peak, [o[:60] for o in outs]))
check("the cap frees itself", scout._active == 0)


async def broken_runner(vault_root, prompt, tag, wall_s):
    raise RuntimeError("engine exploded")


async def empty_runner(vault_root, prompt, tag, wall_s):
    return {"text": "", "error": "plan limit reached"}


async def hanging_runner(vault_root, prompt, tag, wall_s):
    await asyncio.sleep(3600)

scout.configure(broken_runner)
out = run(scout.run(BRAIN, TASK))
check("a broken engine falls back to the main model", out.startswith("ERROR:") and "engine exploded" in out and "yourself" in out, out)
scout.configure(empty_runner)
out = run(scout.run(BRAIN, TASK))
check("an empty report falls back with the engine's reason", out.startswith("ERROR:") and "plan limit reached" in out, out)
os.environ["JAVIS_SCOUT_MAX_WALL_S"] = "30"
scout.configure(hanging_runner)
_real_wait = asyncio.wait_for


async def quick_wait(aw, timeout=None):
    return await _real_wait(aw, timeout=0.05)

asyncio.wait_for = quick_wait
try:
    out = run(scout.run(BRAIN, TASK))
finally:
    asyncio.wait_for = _real_wait
    os.environ.pop("JAVIS_SCOUT_MAX_WALL_S")
check("a scout that never finishes is given up on", out.startswith("ERROR:") and "still working" in out, out)
check("no slot leaks after failures", scout._active == 0)


async def long_runner(vault_root, prompt, tag, wall_s):
    return {"text": "\n".join(f"FINDING {i}: " + "detail " * 30 for i in range(200))}

scout.configure(long_runner)
out = run(scout.run(BRAIN, TASK))
check("a long report is stored whole and shown as a view",
      len(out) <= scout.ANSWER_CHARS + 800 and "javis_stored_result ref=tr_" in out and "FINDING 0:" in out, len(out))
ref = out.split("ref=")[1].split()[0]
check("the whole report is readable by its reference, from the same brain only",
      "FINDING 199:" in (store.get(ref, BRAIN) or {}).get("text", "") and store.get(ref, "/other") is None)

os.environ["JAVIS_SCOUT"] = "0"
check("JAVIS_SCOUT=0 switches it off", not scout.available() and run(scout.run(BRAIN, TASK)).startswith("ERROR:"))
os.environ.pop("JAVIS_SCOUT")
_real_read = config.read_settings
config.read_settings = lambda: {"mcp": {"scout": False}}
check("mcp.scout=false switches it off", not scout.enabled())
config.read_settings = _real_read

# ============================================================
# 4. The hub: listed for the owner, never for a customer bot
# ============================================================
mcp_store.resolved = lambda enabled_only=True: []


async def _no_tools(conns, bo_qua=None):
    return [], {}

mcp_client.discover_resolved = _no_tools
mcp_hub._builtin_tools = lambda *a, **k: ([], {})
config.read_settings = lambda: {"mcp": {"lazy_tools": "on"}}
scout.configure(good_runner)
mcp_hub._cache.clear()
tools, route = run(mcp_hub.discover_all("full", vault_root=BRAIN, include_plugins=False, force_refresh=True))
names = {t["fn"] for t in tools}
search = next(t for t in tools if t["fn"] == mcp_hub._LAZY_SEARCH)
check("behind the tool search the scout costs one line per turn, not a whole tool",
      "javis_scout" not in names and "javis_scout(task)" in search["description"], sorted(names))
hint = mcp_hub.SCOUT_HINT.format(run=mcp_hub._LAZY_RUN)
check("that line stays short", len(hint) < 160, len(hint))
found = json.loads(run(mcp_client.call_route(route, mcp_hub._LAZY_SEARCH, {"query": "javis_scout"})))
check("a search by its name returns the scout with its arguments",
      found["tools"][0]["name"] == "javis_scout" and "task" in found["tools"][0]["schema"]["properties"], found["tools"][0]["name"])
out = run(mcp_client.call_route(route, mcp_hub._LAZY_RUN, {"name": "javis_scout", "args": {"task": TASK, "effort": "quick"}}))
check("calling it through the hub runs a scout for that brain",
      "revenue 12,300,000 VND" in out and _seen[-1]["vault"] == BRAIN and _seen[-1]["tag"] == "scout-quick", out[:120])
check("a brain with no connected source carries no javis_query on every turn", "javis_query" not in names)
tools_s, route_s = run(mcp_hub.discover_all("suggest", vault_root=BRAIN, include_plugins=False, force_refresh=True))
out = run(mcp_client.call_route(route_s, mcp_hub._LAZY_RUN, {"name": "javis_scout", "args": {"task": TASK}}))
check("a read-only run may send a scout too (a scout only reads)", "revenue 12,300,000 VND" in out, out[:120])
tools_b, route_b = run(mcp_hub.discover_all("full", vault_root=BRAIN, include_plugins=False, force_refresh=True, for_bot=True))
bot_search = [t for t in tools_b if t["fn"] == mcp_hub._LAZY_SEARCH]
check("a customer bot never gets it: not listed, not hinted, not callable",
      "javis_scout" not in {t["fn"] for t in tools_b} and "javis_scout" not in route_b
      and all("javis_scout" not in t["description"] for t in bot_search)
      and (mcp_hub._LAZY_RUN not in route_b or run(mcp_client.call_route(
          route_b, mcp_hub._LAZY_RUN, {"name": "javis_scout", "args": {"task": TASK}})).startswith("ERROR:")))
config.read_settings = lambda: {"mcp": {"lazy_tools": "off"}}
mcp_hub._cache.clear()
tools_o, _ = run(mcp_hub.discover_all("full", vault_root=BRAIN, include_plugins=False, force_refresh=True))
spec = next(t for t in tools_o if t["fn"] == "javis_scout")
check("with the tool search off the scout is listed like any tool, small and fixed",
      len(json.dumps(spec, ensure_ascii=False)) < 1500, len(json.dumps(spec)))
scout.configure(None)
mcp_hub._cache.clear()
config.read_settings = lambda: {"mcp": {"lazy_tools": "on"}}
tools_n, _ = run(mcp_hub.discover_all("full", vault_root=BRAIN, include_plugins=False, force_refresh=True))
check("without a runner the tool is neither listed nor hinted",
      "javis_scout" not in {t["fn"] for t in tools_n} and all("javis_scout" not in t.get("description", "") for t in tools_n))
config.read_settings = _real_read

if _fails:
    raise SystemExit(f"{len(_fails)} FAIL: " + "; ".join(_fails))
print("All green")
