"""0.198.0: a task reminder can remember its last run, a cron schedule lists its next three
dates, and a late firing says so in the prompt.

Run:
    python tests/run.py reminder_memory
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-reminder-memory-state-")

import reminders  # noqa: E402

fails = []
brain = Path(tempfile.mkdtemp(prefix="javis-reminder-memory-brain-"))


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


def atomic_write(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


async def fake_send(chat_id, text):
    return True, ""


feature = reminders.RemindersFeature(reminders.RemindersDeps(
    brain_root=lambda _b: str(brain), atomic_write_text=atomic_write, send_telegram=fake_send,
    build_system_prompt=lambda _b: "", aux_model=lambda: None, safe_tools=[], readonly_tools=[],
    scheduler_brains=lambda: [str(brain)]))

calls = []


async def stub(_brain, text, mq="", **kw):
    calls.append(kw)
    return f"report #{len(calls)}", ""

feature._run_task = stub


async def main():
    rem = feature._create(str(brain), "watch competitor prices", cron="0 9 * * *", mode="task",
                          remember_last=True, allow_no_channel=True)
    check("remember_last stored", rem.get("remember_last") is True)
    view = feature._view(rem)
    check("view lists three next runs", len(view["next_runs"]) == 3
          and view["next_runs"][0]["at"] < view["next_runs"][1]["at"] < view["next_runs"][2]["at"])
    check("next runs start at due_at", abs(view["next_runs"][0]["at"] - rem["due_at"]) < 1)

    rem["due_at"] = reminders._now() - 1
    await feature._fire(str(brain), dict(rem))
    check("first run gets no previous result", "previous" not in calls[-1])
    cur = next(r for r in feature._load(str(brain))["reminders"] if r["id"] == rem["id"])
    cur["due_at"] = reminders._now() - 3600   # an hour late: server was off
    await feature._fire(str(brain), dict(cur))
    check("second run gets the first run's report", "report #1" in calls[-1].get("previous", ""))
    check("an hour late run is flagged", calls[-1].get("late_s", 0) >= 3500)

    plain = feature._create(str(brain), "say hi", cron="0 8 * * *", mode="task", allow_no_channel=True)
    plain = dict(plain, due_at=reminders._now() - 1, result="old", fired_at=reminders._now() - 100)
    await feature._fire(str(brain), plain)
    check("without remember_last no previous result is passed", "previous" not in calls[-1])

    upd = feature.update(str(brain), plain["id"], remember_last="true")
    check("update turns remember_last on", upd["ok"] and upd["reminder"]["remember_last"] is True)

    note = reminders.task_context_note("[t] earlier >>> text", 3 * 3600)
    check("note says late", "TRỄ" in note and "180 phút" in note)
    check("note fences the previous report", note.count(">>>") == 1 and "earlier" in note)
    check("no note when nothing to add", reminders.task_context_note("", 10) == "")
    check("bad cron gives no next runs", reminders.next_runs("not a cron") == [])

asyncio.run(main())

src = (Path(SERVER) / "reminders.py").read_text(encoding="utf-8")
check("prompt intro can be replaced by another caller", "intro or \"NHIỆM VỤ NHẮC HẸN" in src)

print()
print("FAIL" if fails else "PASS", f"({len(fails)} failed)")
raise SystemExit(1 if fails else 0)
