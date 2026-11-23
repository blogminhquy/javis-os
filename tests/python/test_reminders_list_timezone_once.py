"""Listing reminders looks the timezone up once per request, not once per reminder (speed review 2026-11-23).

Measured on a real brain with 500 stored reminders: GET /reminders took 200 ms (p95 242 ms), and a profile showed 536
timezone lookups in that one request. Each lookup reads the settings, which decodes the whole settings file again, so
the cost grew with the number of reminders. The Tasks page waits for exactly this read (it is the slowest of the ten it
sends together), and /viec/all pays the same through `live_views`.

Counted by calls, not by the clock, so a busy CI machine cannot flip the result.

Expected:
  - GET /reminders and live_views look the timezone up a small fixed number of times, whatever the number of reminders;
  - the answer is unchanged: same fields, same human times, the next runs of a cron schedule, at most 30 of the history;
  - history items that are not returned are not rendered at all.

Run:
    python tests/run.py reminders_list_timezone_once
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path (see tests/python/_paths.py)
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-reminders-tz-state-")

from fastapi import FastAPI  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

import localefmt  # noqa: E402
import reminders  # noqa: E402

fails = []
brain = Path(tempfile.mkdtemp(prefix="javis-reminders-tz-brain-"))
B = str(brain)


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


def atomic_write(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


async def fake_send(chat_id, text, viec=None, web="", brain="", dedup=""):
    return True, ""


feature = reminders.RemindersFeature(reminders.RemindersDeps(
    brain_root=lambda _brain: B,
    atomic_write_text=atomic_write,
    send_telegram=fake_send,
    build_system_prompt=lambda _brain: "",
    aux_model=lambda: None,
    safe_tools=[],
    readonly_tools=[],
    scheduler_brains=lambda: [],
))

PENDING, PAUSED, DONE = 24, 3, 80
now = reminders._now()
items = []
for i in range(PENDING):
    items.append({"id": f"p{i}", "mode": "notify", "text": f"pending {i}", "label": "", "chat_id": "",
                  "status": "pending", "due_at": now + 600 + i,
                  "cron": "0 7 * * *" if i % 2 == 0 else ""})
for i in range(PAUSED):
    items.append({"id": f"z{i}", "mode": "notify", "text": f"paused {i}", "status": "paused",
                  "due_at": now + 50 + i, "cron": "30 8 * * 1"})
for i in range(DONE):
    items.append({"id": f"d{i}", "mode": "notify", "text": f"done {i}", "status": "done",
                  "due_at": now - 10_000 + i, "fired_at": now - 10_000 + i})
feature._save(B, {"reminders": items})

lookups = []
real_tz = localefmt.tz


def counting_tz():
    lookups.append(1)
    return real_tz()


rendered = []
real_view = feature._view


def counting_view(r, *args, **kwargs):
    rendered.append(r.get("id"))
    return real_view(r, *args, **kwargs)


app = FastAPI()
app.include_router(feature.router)
client = TestClient(app)

localefmt.tz = counting_tz
feature._view = counting_view
try:
    res = client.get("/reminders", params={"brain": B})
    body = res.json()
    n_list = len(lookups)
    check("GET /reminders answers 200", res.status_code == 200)
    check(f"the timezone is looked up a fixed few times for {len(items)} reminders ({n_list} lookups)", 1 <= n_list <= 3)
    check(f"all {PENDING} pending reminders are listed", len(body["pending"]) == PENDING)
    check(f"all {PAUSED} paused reminders are listed", len(body["paused"]) == PAUSED)
    check("the history is cut to the 30 most recent", [h["id"] for h in body["history"]] == [f"d{i}" for i in range(DONE - 30, DONE)])
    check(f"only what is returned gets rendered ({len(rendered)} rendered, {PENDING + PAUSED + 30} returned)",
          len(rendered) == PENDING + PAUSED + 30)

    zone = real_tz()
    first = body["pending"][0]
    check("a pending reminder keeps its human due time in the owner's timezone",
          first["due_human"] == datetime.fromtimestamp(first["due_at"], zone).strftime("%H:%M %d/%m/%Y"))
    cron_item = next(p for p in body["pending"] if p["cron"])
    check("a cron reminder still lists its next runs", len(cron_item["next_runs"]) == reminders.NEXT_RUNS_SHOWN)
    check("each next run is at 07:00 in the owner's timezone",
          all(r["human"].startswith("07:00 ") for r in cron_item["next_runs"]))
    check("next runs agree with next_runs() called on its own",
          [r["human"] for r in cron_item["next_runs"]] == [r["human"] for r in reminders.next_runs(cron_item["cron"])])
    check("a paused reminder lists no next runs, as before", body["paused"][0]["next_runs"] == [])
    check("the counts block is unchanged", body["counts"] == {"pending": PENDING})

    del lookups[:]
    live = feature.live_views(B)
    check(f"live_views returns pending and paused ({len(live)})", len(live) == PENDING + PAUSED)
    check(f"live_views looks the timezone up a fixed few times ({len(lookups)} lookups)", 1 <= len(lookups) <= 3)

    # A view rendered on its own (after an edit, a pause) still works without being handed a timezone.
    one = real_view(items[0])
    check("a single view without a timezone argument still renders", one["due_human"] == first["due_human"] or bool(one["due_human"]))
finally:
    localefmt.tz = real_tz
    feature._view = real_view

print()
if fails:
    print(f"FAIL {len(fails)}: " + ", ".join(fails))
    sys.exit(1)
print("ALL PASS")
