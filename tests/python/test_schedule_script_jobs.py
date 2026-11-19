"""Script jobs from chat, the whole last result kept, skipped runs counted (issues 1563 and 1480).

    python tests/run.py schedule_script_jobs

Issue 1563: `javis_schedule` could not create a script job (the model had to call POST /reminders by hand), and a
run's result was cut to 2,000 characters on disk and silently again before the next run saw it.
Issue 1480: a repeating job that fired late skipped the slots that passed meanwhile and nothing recorded it, so
"every minute" could quietly turn into every few minutes.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import os
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-script-jobs-"))

import reminders  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


spec = importlib.util.spec_from_file_location("javis_schedule_plugin",
                                              ROOT / "system/plugins/javis-schedule/plugin.py")
sched = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sched)

# ---- 1563.1: javis_schedule creates a script job ----
sent = []


async def fake_post(payload, brain_name=""):
    sent.append(dict(payload))
    return "ok (id fake)"


sched._post_reminder = fake_post
vault = tempfile.mkdtemp(prefix="javis-script-vault-")

out = asyncio.run(sched._do_create(vault, {"name": "Canh don", "script": "check_shop.py", "schedule": "1m"}))
p = sent[-1] if sent else {}
check("script job goes to the reminder store as mode script", p.get("mode") == "script"
      and p.get("script") == "check_shop.py", p)
check("a one-minute interval repeats every minute (no 5-minute floor for a script)", p.get("repeat_min") == 1
      and p.get("delay_min") == 1, p)
check("no prompt needed for a script job", "ERROR" not in out, out)

asyncio.run(sched._do_create(vault, {"name": "Canh don 2", "script": "check.sh", "schedule": "mỗi 2 tiếng"}))
check("'mỗi 2 tiếng' repeats every 120 minutes", sent[-1].get("repeat_min") == 120, sent[-1])
asyncio.run(sched._do_create(vault, {"name": "Bao cao", "script": "report.py", "schedule": "0 7 * * *"}))
check("a cron schedule stays a cron", sent[-1].get("cron") == "0 7 * * *" and "repeat_min" not in sent[-1], sent[-1])
n_before = len(sent)
err = asyncio.run(sched._do_create(vault, {"script": "x.py", "schedule": "1m"}))
check("a script job without a name is refused before reaching the server", err.startswith("ERROR")
      and len(sent) == n_before, err)
asyncio.run(sched._do_create(vault, {"name": "Viec thuong", "prompt": "lam gi do", "schedule": "30 phut nua"}))
check("without `script` a job is still a model task", sent[-1].get("mode") == "task" and "script" not in sent[-1],
      sent[-1])

# ---- the reminder store, real ----
brain = Path(tempfile.mkdtemp(prefix="javis-script-brain-"))
(brain / "Javis" / "scripts").mkdir(parents=True)
(brain / "Javis" / "scripts" / "check_shop.py").write_text("print('ok')\n", encoding="utf-8")


def atomic_write(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


async def fake_send(chat_id, text):
    return True, ""


feature = reminders.RemindersFeature(reminders.RemindersDeps(
    brain_root=lambda _b: str(brain), atomic_write_text=atomic_write, send_telegram=fake_send,
    build_system_prompt=lambda _b: "", aux_model=lambda: None, safe_tools=[], readonly_tools=[],
    scheduler_brains=lambda: [str(brain)]))

LONG = "x" * 7000


async def fake_script(_brain, _script):
    return LONG, "", 0

feature._run_script = fake_script


def stored(rid):
    return next(r for r in feature._load(str(brain))["reminders"] if r["id"] == rid)


async def main():
    rem = feature._create(str(brain), "", mode="script", script="check_shop.py", repeat_min=1, delay_min=1)
    check("the store accepts the script job", rem.get("mode") == "script" and rem.get("script") == "check_shop.py")

    # 1480: the firing of 10:00 ran at 10:03:30 -> the 10:01, 10:02 and 10:03 slots were skipped.
    now = reminders._now()
    slot = now - 210
    await feature._fire(str(brain), dict(rem, due_at=slot))
    cur = stored(rem["id"])
    check("skipped slots are counted on the job", cur.get("missed_last") == 3 and cur.get("missed_total") == 3, cur)
    check("the next run is still set from now", cur["due_at"] > reminders._now())
    view = feature._view(cur)
    check("the job view carries the count", view.get("missed_total") == 3)

    await feature._fire(str(brain), dict(cur, due_at=reminders._now() - 1))
    cur = stored(rem["id"])
    check("an on-time run adds nothing", cur.get("missed_total") == 3, cur)

    # 1563.2: the whole result is kept (up to RESULT_KEEP), not 2,000 characters
    check("a 7,000-character result is kept whole", len(cur.get("result") or "") == 7000, len(cur.get("result") or ""))


asyncio.run(main())

prev = reminders.previous_result_text(LONG)
check("the next run sees at most PREVIOUS_RESULT_CAP, with a line saying it was cut",
      prev.startswith("x" * reminders.PREVIOUS_RESULT_CAP) and "5000 more characters" in prev)
check("a short result is passed as is", reminders.previous_result_text("short") == "short")

# missed_slots: cron and edge cases
check("cron: three daily slots skipped over three days late",
      reminders.missed_slots({"cron": "0 7 * * *"}, 1_700_000_000.0, 1_700_000_000.0 + 3 * 86400 + 60) == 3)
check("one-shot job: nothing skipped", reminders.missed_slots({}, 100.0, 10_000.0) == 0)
check("no slot: nothing skipped", reminders.missed_slots({"repeat_min": 1}, 0, 10_000.0) == 0)
check("the count is capped", reminders.missed_slots({"repeat_min": 1}, 1.0, 1e9) == reminders.MISSED_COUNT_CAP)

print()
print("FAIL" if fails else "PASS", f"({len(fails)} failed)")
raise SystemExit(1 if fails else 0)
