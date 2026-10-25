"""Issue #798: re-checking a Team job after the owner saves new acceptance criteria stayed stuck in acceptance_checking.

    python tests/run.py team_spawn_worker_798

Route bodies run in a worker thread (`TeamApi.io` -> run_io). `PUT /teams/{id}/tasks/{task}/acceptance` scheduled the
recheck from there with `api._spawn(api.runner().recheck(task_id))`, and `_spawn` used `asyncio.ensure_future`, which
needs an event loop in the CALLING thread: "RuntimeError: There is no current event loop in thread 'asyncio_0'". The job
had already moved to acceptance_checking, so it stayed there. `_spawn` now hands work from a worker thread to the main
loop. This test goes through `io` the same way the route does.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-team-spawn-798-"))

import team_api  # noqa: E402

fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  {extra}"))
    if not cond:
        fails.append(name)


def make_api():
    return team_api.TeamApi(team_api.TeamApiDeps(
        brain_key=str, session_store=lambda: None, task_store=lambda: None, resonance_store=lambda: None,
        agents_meta=lambda root: [], agent_info=lambda root, key: None, engine_for=lambda *a: None))


async def from_worker():
    api = make_api()
    ran = asyncio.Event()

    async def recheck():
        ran.set()

    def route_body():
        api._spawn(recheck())     # what teams_acceptance_put does inside `io`
        return {"ok": True}

    out = await api.io(route_body)
    try:
        await asyncio.wait_for(ran.wait(), 2)
    except asyncio.TimeoutError:
        pass
    await asyncio.sleep(0)
    return out, ran.is_set(), len(api._bg)


out, ran, held = asyncio.run(from_worker())
check("a recheck scheduled from a route body (worker thread) really runs", out == {"ok": True} and ran, (out, ran))
check("the scheduled job is released once it finished", held == 0, held)


async def on_loop():
    api = make_api()
    api._loop = asyncio.get_running_loop()
    import threading
    api._loop_thread = threading.get_ident()
    ran = asyncio.Event()

    async def job():
        ran.set()
    api._spawn(job())
    await asyncio.wait_for(ran.wait(), 2)
    return ran.is_set()


check("scheduling on the loop thread itself still works as before", asyncio.run(on_loop()))

src = (SERVER / "team_api.py").read_text(encoding="utf-8")
put = src[src.index("async def teams_acceptance_put("):src.index("async def teams_acceptance_decide(")]
check("the acceptance route still schedules the recheck inside its io body",
      "api._spawn(api.runner().recheck(task_id))" in put and "return await api.io(_do)" in put)
check("_spawn hands work from another thread to the main loop",
      "loop.call_soon_threadsafe(self._spawn, value)" in src)

if fails:
    raise SystemExit(f"{len(fails)} FAIL")
print("\nPASS - test_team_spawn_worker_798")
