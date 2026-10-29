"""Regression: a mode=task reminder whose answer opens or closes with [SILENT] posts nothing.

Script jobs already went quiet on [SILENT]; task reminders pushed the empty "[SILENT] ..."
answer to Telegram / the web chat on every idle run of a 10-minute watcher. The answer must
still be saved on the reminder record so the run can be reviewed.

Run:
    python tests/run.py reminder_task_silent
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path (see tests/python/_paths.py)
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-reminder-silent-state-")

import reminders  # noqa: E402

fails = []
sent = []
brain = Path(tempfile.mkdtemp(prefix="javis-reminder-silent-brain-"))


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


def atomic_write(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


async def fake_send(chat_id, text):
    sent.append((chat_id, text))
    return True, ""


deps = reminders.RemindersDeps(
    brain_root=lambda _brain: str(brain),
    atomic_write_text=atomic_write,
    send_telegram=fake_send,
    build_system_prompt=lambda _brain: "",
    aux_model=lambda: None,
    safe_tools=[],
    readonly_tools=[],
    scheduler_brains=lambda: [],
)
feature = reminders.RemindersFeature(deps)


def stored(rid):
    data = json.loads((brain / "Javis" / "reminders.json").read_text(encoding="utf-8"))
    return next(r for r in data["reminders"] if r["id"] == rid)


async def fire_task(rid, answer, cron=None):
    rem = {"id": rid, "mode": "task", "text": "watch the incident inbox",
           "label": "Incident watcher", "chat_id": "web:abc", "status": "pending",
           "due_at": reminders._now() - 1}
    if cron:
        rem["cron"] = cron
    data = feature._load(str(brain))
    data["reminders"].append(dict(rem))
    feature._save(str(brain), data)

    async def task_stub(_brain, _text, _muc_quyen=""):
        return answer, ""

    feature._run_task = task_stub
    before = len(sent)
    await feature._fire(str(brain), rem)
    return sent[before:]


async def run():
    silent = "[SILENT] no new incident tickets"
    out = await fire_task("r_silent", silent, cron="*/10 7-22 * * *")
    check("task answering [SILENT] sends nothing", out == [])
    rec = stored("r_silent")
    check("silent task result is still saved on the record", rec.get("result") == silent)
    check("silent task records no error", rec.get("error") == "")
    check("silent cron task is rescheduled", rec.get("status") == "pending")

    out = await fire_task("r_silent_md", "  **[SILENT]** nothing to do")
    check("[SILENT] wrapped in markdown emphasis also stays quiet", out == [])

    normal = "Opened ticket su-co-42 and asked the staff group to confirm."
    out = await fire_task("r_normal", normal)
    check("ordinary task result is still sent", out == [("web:abc", normal)])
    check("ordinary task result is saved on the record", stored("r_normal").get("result") == normal)

    mention = "Found 1 ticket. Idle runs answer [SILENT], this one did not."
    out = await fire_task("r_mention", mention)
    check("[SILENT] mentioned mid-answer does not mute the result", out == [("web:abc", mention)])

    # 0.408.0, owner's screenshot 2026-10-29: the model wrote a sentence first and the flag LAST, and the bell got
    # a report "Tôi sẽ đọc quy trình và kiểm tra các lượt POSCake bị lỗi. [SILENT]".
    trailing = "Tôi sẽ đọc quy trình và kiểm tra các lượt POSCake bị lỗi.\n\n[SILENT]"
    out = await fire_task("r_trailing", trailing)
    check("[SILENT] closing the answer also stays quiet", out == [])
    check("trailing-flag result is still saved on the record", stored("r_trailing").get("result") == trailing)
    out = await fire_task("r_trailing_inline", "Không có lượt lỗi mới. **[SILENT]**")
    check("[SILENT] at the end of the last line stays quiet", out == [])


asyncio.run(run())

if fails:
    print(f"\nFAIL - test_reminder_task_silent: {len(fails)} failed: {fails}")
    sys.exit(1)
print("\nOK - test_reminder_task_silent: all pass")
