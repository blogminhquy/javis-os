"""wait_idle() must not spin for ever on a task that has finished but is still in its task set (2026-11-21).

    python tests/run.py wait_idle_yields

What happened: test_webhook_spec_matrix was killed at the runner's 1200 second limit 6 times in about 830 CI runs,
always at the same place and without a line of output. The webhook worker keeps its pump and its runs in `_tasks`;
each leaves the set in its done callback, which runs one pass of the event loop after the task ends. `wait_idle`
waited for everything in the set with `asyncio.gather()`. Since Python 3.12 a gather over finished tasks returns a
future that is already done, and awaiting that never gives the loop a pass, so the callback never ran and the loop
span for ever. Python 3.11 gave the loop one pass there, which is why it only showed on 3.12 (CI and the Docker
image). The incident desk had the same loop.

The state is rare in a real run (the waiter has to wake in the same pass in which the task ends, behind it), so
this test builds it by hand: a task that is done and still in the set. Before the fix both waits below never came
back; a watchdog thread ends the process then, since a loop that never yields cannot be timed out from inside.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

STATE = Path(tempfile.mkdtemp(prefix="javis-wait-idle-"))
os.environ["JAVIS_STATE_DIR"] = str(STATE)
os.environ["JAVIS_NO_REAL_JUDGE_ENGINE"] = "1"

import incident_desk as idk  # noqa: E402
import webhook_triggers as wt  # noqa: E402

fails = []
WATCHDOG_S = 20
stage = {"now": "start"}


def check(name, cond, more=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{more}]" if more and not cond else ""), flush=True)
    if not cond:
        fails.append(name)


def watchdog():
    time.sleep(WATCHDOG_S)
    print(f"FAIL {stage['now']}: still waiting after {WATCHDOG_S} s (a loop that never gives the event loop a pass)",
          flush=True)
    os._exit(1)


threading.Thread(target=watchdog, daemon=True).start()


async def noop():
    return None


async def finished_but_still_listed(tasks: set):
    """A task that ended in this pass of the loop: done, and not yet taken out of `tasks` by its done callback."""
    t = asyncio.get_running_loop().create_task(noop())
    tasks.add(t)
    t.add_done_callback(tasks.discard)
    await asyncio.sleep(0)      # the task runs first, then this coroutine, in the same pass
    return t


async def ok(*a, **k):
    return "ok", ""


async def send(*a, **k):
    return True, ""


async def main():
    # ---- the webhook worker ----
    f = wt.WebhookFeature(wt.WebhookDeps(state_dir=lambda: STATE, run_task=ok, run_workflow=ok, send=send,
                                         base_url=lambda r: ""))
    f.store()
    stage["now"] = "webhook wait_idle with a finished task in the set"
    t = await finished_but_still_listed(f._tasks)
    check("the state under test: the task is done and still in the set", t.done() and t in f._tasks)
    await f.wait_idle()
    check("webhook wait_idle returns, and the finished task has left the set", t not in f._tasks)

    # It still waits for real work: an accepted event is run before wait_idle comes back.
    stage["now"] = "webhook wait_idle with a real event"
    ran = []

    async def run_task(brain, text, level):
        await asyncio.sleep(0.05)
        ran.append(text)
        return "done", ""
    f.deps.run_task = run_task
    hook, token, _ = f.create("/b1", name="Idle", target="task", text="x")
    code, r = await f.accept(hook["id"], token, b"{}", "application/json", "")
    await f.wait_idle()
    ev = f.store().get(r["event_id"])
    check("webhook wait_idle still waits for a run to finish", code == 202 and len(ran) == 1 and ev["status"] == "done"
          and not f._running(), (code, ran, ev["status"]))

    # A run that ends while the store is being asked starts the pump again: wait_idle waits for that pump too.
    stage["now"] = "webhook wait_idle with a pump started behind its back"
    real = f.store().has_claimable
    late = {}

    def has_claimable(*a, **k):
        if not late:
            late["task"] = asyncio.run_coroutine_threadsafe(_spawn(), loop).result()
        return real(*a, **k)

    async def slow():
        await asyncio.sleep(0.1)
        late["ended"] = True

    async def _spawn():
        t2 = loop.create_task(slow())
        f._tasks.add(t2)
        t2.add_done_callback(f._tasks.discard)
        return t2
    loop = asyncio.get_running_loop()
    f.store().has_claimable = has_claimable
    await f.wait_idle()
    f.store().has_claimable = real
    check("webhook wait_idle waits for a task that started while it asked the store", late.get("ended") is True)

    # ---- the incident desk ----
    desk = idk.IncidentDesk(idk.IncidentDeps(state_dir=lambda: STATE, ask=None, post=None, retry={},
                                             enabled=lambda: True))
    stage["now"] = "incident desk wait_idle with a finished task in the set"
    t = await finished_but_still_listed(desk._tasks)
    check("incident desk: the task is done and still in the set", t.done() and t in desk._tasks)
    await desk.wait_idle()
    check("incident desk wait_idle returns, and the finished task has left the set", not desk._tasks)
    stage["now"] = "incident desk wait_idle with a running task"
    seen = []

    async def work():
        await asyncio.sleep(0.05)
        seen.append(1)
    t3 = asyncio.get_running_loop().create_task(work())
    desk._tasks.add(t3)
    t3.add_done_callback(desk._tasks.discard)
    await desk.wait_idle()
    check("incident desk wait_idle still waits for a running task", seen == [1] and not desk._tasks)


asyncio.run(main())
print()
print("FAIL" if fails else "PASS", f"({len(fails)} failed)")
raise SystemExit(1 if fails else 0)
