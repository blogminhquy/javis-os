"""Short freezes of the event loop are found, and the Kanban dispatcher no longer causes them (2026-11-08).

Owner, 2026-11-08: "load các trang, load lịch sử chuyển từ hội thoại này sang hội thoại khác bị delay mấy giây".
Measured on a test server: the Kanban dispatcher (every 5 s and on every wake) wrote SQLite on the event loop, so the
whole server froze 0.3-1.2 s whenever another writer held the Kanban file; a 7 ms request took 1.2 s. The model list
of Claude Code (a scan of the 200 MB binary) froze it 3 s. loop_watch only reported freezes of 2 s or more.

  1. loop_watch counts a 0.5 s freeze as a slow spot, named after the Javis function it was stuck in, without
     turning it into a 2 s incident; GET /health/loop shows it.
  2. One dispatcher pass, the 30-second tick and the nudge route do their Kanban reads and writes off the loop thread.
  3. Claude Code's model list is read in a worker thread by the updater and by /voice/options.

    python tests/run.py loop_slow_spots
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-slowspots-"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import loop_watch  # noqa: E402
from tasks import TasksDeps, TasksFeature  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


# ---- 1. a short freeze is a slow spot, named --------------------------------------------------------------------------
def stuck_in_here():
    time.sleep(0.5)    # synchronous work on the loop, shorter than an incident


async def watch():
    loop_watch.start()
    await asyncio.sleep(0.2)
    stuck_in_here()
    await asyncio.sleep(0.3)
    stuck_in_here()
    await asyncio.sleep(0.3)
    return loop_watch.report()


rep = asyncio.run(watch())
top = rep.get("slow_top") or []
spot = top[0] if top else {}
check("the report carries the slow-spot threshold", rep.get("slow_s") == loop_watch.SLOW_S, rep)
check("a 0.5 s freeze is not a 2 s incident", rep.get("incidents") == [], rep.get("incidents"))
check("both freezes are counted against one place", len(top) == 1 and spot.get("count") == 2, top)
check("the place names the function the loop was stuck in", "stuck_in_here" in spot.get("where", ""), spot)
check("its time is measured", 0.4 <= spot.get("max_s", 0) <= 1.0 and spot.get("total_s", 0) >= 0.8, spot)
check("a sample stack comes with it", any("stuck_in_here" in ln for ln in spot.get("stack", [])), spot)
check("the latest freezes are listed newest first", len(rep.get("slow_recent") or []) == 2
      and rep["slow_recent"][0]["at"] >= rep["slow_recent"][1]["at"], rep.get("slow_recent"))

# ---- 2. the Kanban dispatcher works off the loop ----------------------------------------------------------------------
TMP = Path(tempfile.mkdtemp(prefix="javis-slowspots-brain-"))
BRAIN = TMP / "Brain X"
BRAIN.mkdir(parents=True, exist_ok=True)


def _atomic(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


async def _workflow(*_a, **_k):
    if False:
        yield {}


feat = TasksFeature(TasksDeps(
    brain_root=lambda v: str(BRAIN),
    atomic_write_text=_atomic,
    execute_workflow=_workflow,
    workflows_dir=lambda b: BRAIN / "workflows",
    build_system_prompt=lambda b: "system",
    aux_model=lambda: None,
    safe_tools=["Read"],
    state_dir=TMP / "state",
    scheduler_brains=lambda: [str(BRAIN)],
))
seen = {}
for name in ("reclaim_stale", "promote_dependencies", "archive_old_terminal", "board_mode", "next_candidate"):
    real = getattr(feat.store, name)

    def spy(*a, _real=real, _name=name, **k):
        seen.setdefault(_name, set()).add(threading.get_ident())
        return _real(*a, **k)
    setattr(feat.store, name, spy)


async def one_pass():
    loop_thread = threading.get_ident()
    await feat._dispatch_available()
    after_pass = {k: set(v) for k, v in seen.items()}
    seen.clear()
    await feat.tick([str(BRAIN)])
    after_tick = {k: set(v) for k, v in seen.items()}
    return loop_thread, after_pass, after_tick


loop_thread, after_pass, after_tick = asyncio.run(one_pass())
check("a dispatcher pass reaches the store", {"reclaim_stale", "board_mode"} <= set(after_pass), after_pass)
check("a dispatcher pass never touches the store on the loop thread",
      all(loop_thread not in ids for ids in after_pass.values()), after_pass)
check("the 30-second tick does its housekeeping off the loop thread",
      "reclaim_stale" in after_tick and all(loop_thread not in ids for ids in after_tick.values()), after_tick)

tasks_src = (ROOT / "server" / "tasks.py").read_text(encoding="utf-8")
check("claiming a job runs in a worker thread", "claimed = await asyncio.to_thread(_claim)" in tasks_src)
check("the heartbeat writes in a worker thread",
      "await asyncio.to_thread(self.store.heartbeat, task_id, worker_id, LEASE_SECONDS)" in tasks_src)
check("the nudge route scans in a worker thread", "candidate = await asyncio.to_thread(_scan)" in tasks_src)
check("a finished job's snapshot leaves the loop", "create_task(self._asnapshot(root))" in tasks_src)

# ---- 3. Claude Code's model list ----------------------------------------------------------------------------------------
main_src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
up = main_src.split("async def _cap_nhat_claude", 1)[1].split("\n\n\n", 1)[0]
check("the Claude updater reads the model list in a worker thread",
      "await asyncio.to_thread(claude_cli.list_models)" in up and "set(claude_cli.list_models()" not in up, up[:300])
vo = main_src.split('@app.get("/voice/options")', 1)[1].split("\n\n\n", 1)[0]
check("/voice/options reads the CLI model lists in a worker thread",
      "asyncio.to_thread(_cli_models)" in vo and "_models_items(claude_cli.list_models()" not in vo
      and "_models_items(grok_cli.list_models()" not in vo)

for name in ("server/loop_watch.py", "server/tasks.py", "tests/python/test_loop_slow_spots.py"):
    src = (ROOT / name).read_text(encoding="utf-8")
    check(f"{name} has no long dash", chr(0x2014) not in src and chr(0x2013) not in src)

print()
print(("FAIL - " + str(len(fails)) + " check(s)") if fails else "PASS - test_loop_slow_spots")
raise SystemExit(1 if fails else 0)
