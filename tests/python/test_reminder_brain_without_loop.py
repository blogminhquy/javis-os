"""Regression: a reminder fires in a brain that has no loop (field report 0.270, Code 3).

The reminder scheduler took its brain list from the loop scheduler, which only knows the
default brain and brains where a loop was once created or toggled. A notify reminder in a
brain with no loop stayed "pending" past its time forever, while the same reminder in a
brain holding one disabled loop fired on the next tick.

Covers:
- a due reminder in a BRAINS_DIR brain with no loop fires on the next tick;
- a due reminder in a brain folder OUTSIDE BRAINS_DIR fires too, and that folder stays
  known to the scheduler (registered on create, so a restart does not lose it);
- the default brain, reachable both as "brain" and by its path, is ticked once.

Run:
    python tests/python/test_reminder_brain_without_loop.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path (see tests/python/_paths.py)
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

# BRAINS_DIR and STATE_DIR must point at temp folders BEFORE main is imported (read at import).
_STATE = tempfile.mkdtemp(prefix="javis-rem-noloop-state-")
_BRAINS = tempfile.mkdtemp(prefix="javis-rem-noloop-brains-")
os.environ["JAVIS_STATE_DIR"] = _STATE
os.environ["BRAINS_DIR"] = _BRAINS

import main  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


sent = []


async def fake_send(chat_id, text, *args, **kwargs):
    sent.append((chat_id, text))
    return True, ""


feature = main.reminders_feature
feature.deps.send_telegram = fake_send
feature.deps.make_voice = None
feature.deps.send_file = None


def status_of(brain, rid):
    data = json.loads((Path(brain) / "Javis" / "reminders.json").read_text(encoding="utf-8"))
    return next(r for r in data["reminders"] if r["id"] == rid)["status"]


def make_due(brain, text):
    rem = feature._create(brain, text, due_at=main.time.time() + 60, allow_no_channel=True)
    data = feature._load(brain)
    for r in data["reminders"]:
        if r["id"] == rem["id"]:
            r["due_at"] = main.time.time() - 5     # already due
    feature._save(brain, data)
    return rem["id"]


# A brain inside BRAINS_DIR with no loop folder at all.
no_loop = Path(_BRAINS) / "TEST-NoLoop"
(no_loop / "Javis").mkdir(parents=True)
check("setup: the loop-free brain has no loop", not main.loop_feature.list_loops(str(no_loop)))

# A brain folder outside BRAINS_DIR, also with no loop.
outside = Path(tempfile.mkdtemp(prefix="javis-rem-noloop-outside-"))
(outside / "Javis").mkdir(parents=True)

rid_in = make_due(str(no_loop), "call the supplier")
rid_out = make_due(str(outside), "pay the rent")
rid_def = make_due("brain", "drink water")

asyncio.run(feature.tick())
asyncio.run(feature.cho_viec_nen())

check("a due reminder in a BRAINS_DIR brain without loops fires",
      status_of(str(no_loop), rid_in) != "pending")
check("a due reminder in an outside brain without loops fires",
      status_of(str(outside), rid_out) != "pending")
check("a due reminder in the default brain still fires",
      status_of(main._brain_root("brain"), rid_def) != "pending")
check("each reminder is delivered exactly once",
      sum("call the supplier" in t for _c, t in sent) == 1
      and sum("pay the rent" in t for _c, t in sent) == 1
      and sum("drink water" in t for _c, t in sent) == 1)

roots = {str(Path(main._brain_root(b)).resolve()) for b in main._background_brains()}
check("the outside brain stays on the scheduler list after creating a reminder",
      str(outside.resolve()) in roots)
check("a BRAINS_DIR brain is not written to the loop registry",
      str(no_loop.resolve()) not in
      {str(Path(main._brain_root(b)).resolve()) for b in main.loop_feature.scheduler_brains()})
ticked = [str(Path(main._brain_root(b)).resolve()) for b in feature._tick_brains()]
check("one tick visits each brain root once", len(ticked) == len(set(ticked)))

print()
if fails:
    print(f"FAILED {len(fails)}: {fails}")
    sys.exit(1)
print("all passed")
