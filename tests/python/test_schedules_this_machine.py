"""Per-machine switch for scheduled work.

    python tests/python/test_schedules_this_machine.py      (no network)

Reminders and loops sync to every machine through the brain repo, so each machine running Javis fired them once.
The switch lives in settings.json (never synced): off on one machine, the others keep running the schedule.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-sched-here-")

import config as cfgmod   # noqa: E402
import main               # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


check("runs by default", main.schedules_run_here() is True)
r = asyncio.run(main.schedules_this_machine_set(runs="0"))
check("switch off answers runs=false", r == {"ok": True, "runs": False})
check("off is stored in local settings", cfgmod.read_settings().get("schedules_off_here") is True)
check("off is read back", asyncio.run(main.schedules_this_machine_get())["runs"] is False)
asyncio.run(main.schedules_this_machine_set(runs="1"))
check("switch back on", main.schedules_run_here() is True)

src = (SERVER / "main.py").read_text(encoding="utf-8")
check("reminder tick is gated", "if schedules_run_here():\n                        await reminders_feature.tick()" in src)
check("loop tick is gated", "if schedules_run_here():\n                        await loop_feature.tick()" in src)

if _fails:
    sys.exit(1)
print("ALL OK")
