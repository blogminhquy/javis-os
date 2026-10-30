"""Reminder controls for the Tasks page (0.422.0): pause/resume, skip next, run now, stop one run.

Expected:
  - a paused reminder is kept, listed as paused, skipped by the tick, still editable and cancellable;
  - resuming moves a due time that went by while paused to the next regular run from now;
  - skip moves a repeating reminder to the run after the next one; a one-shot refuses;
  - run now fires a live reminder at once with its own slot (not the next scheduled one);
  - stop ends the run that is going: no retry, nothing posted, a repeating one keeps its schedule,
    a one-shot ends cancelled; the engine of a reminder is tagged per id.

Run:
    python tests/python/test_reminder_controls_0422.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path (see tests/python/_paths.py)
import asyncio
import json
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-reminder-controls-state-")

import once_ledger  # noqa: E402
import reminders  # noqa: E402

once_ledger.configure(Path(tempfile.mkdtemp(prefix="javis-reminder-controls-ledger-")) / "ledger.sqlite3")

fails = []
sent = []
brain = Path(tempfile.mkdtemp(prefix="javis-reminder-controls-brain-"))


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


def atomic_write(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


async def fake_send(chat_id, text, viec=None, web="", brain="", dedup=""):
    sent.append({"chat_id": chat_id, "text": text, "dedup": dedup})
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
B = str(brain)


def stored(rid):
    data = json.loads((brain / "Javis" / "reminders.json").read_text(encoding="utf-8"))
    return next(r for r in data["reminders"] if r["id"] == rid)


def add(rid, **extra):
    rem = {"id": rid, "mode": "task", "text": "post the daily sales figure", "label": "Sales",
           "chat_id": "", "status": "pending", "due_at": reminders._now() + 3600, **extra}
    data = feature._load(B)
    data.setdefault("reminders", []).append(dict(rem))
    feature._save(B, data)
    return rem


async def run():
    now = reminders._now()

    # ── pause / resume ──
    add("r_rep", repeat_min=60, due_at=now - 30)
    r = feature.pause(B, "r_rep", True)
    check("pause answers ok", r.get("ok") and r["reminder"]["status"] == "paused")
    check("a paused reminder is in live_views", [v["id"] for v in feature.live_views(B)] == ["r_rep"])
    check("a paused reminder is not in pending_views", feature.pending_views(B) == [])
    ran = []

    async def fire_stub(_brain, rem):
        ran.append(rem["id"])

    real_fire = feature._fire
    feature._fire = fire_stub
    await feature._tick_brain(B)
    await feature.cho_viec_nen()
    check("the tick skips a paused reminder even when due", ran == [])
    feature._fire = real_fire
    check("a paused reminder can be edited",
          feature.update(B, "r_rep", label="Sales report").get("ok"))
    r = feature.pause(B, "r_rep", False)
    rec = stored("r_rep")
    check("resume makes it pending", r.get("ok") and rec["status"] == "pending")
    check("resume moves a passed due time to the next run from now",
          now < rec["due_at"] <= now + 3600 + 5)

    # ── skip ──
    add("r_cron", cron="0 7 * * *", due_at=reminders.cron_util.cron_next("0 7 * * *", now, reminders.VN_TZ()))
    before = stored("r_cron")["due_at"]
    r = feature.skip(B, "r_cron")
    after = stored("r_cron")["due_at"]
    check("skip moves a cron reminder one day on", r.get("ok") and 86400 - 5 <= after - before <= 86400 + 5)
    add("r_once")
    r = feature.skip(B, "r_once")
    check("skip refuses a one-shot reminder", not r.get("ok") and r.get("error"))

    # ── run now ──
    seen = []

    async def task_ok(_brain, _text, _mq="", **_kw):
        seen.append((reminders._RUN_RID.get(), once_ledger.current_job()))
        return "Sales today: 12 orders.", ""

    feature._run_task = task_ok
    due_before = stored("r_cron")["due_at"]
    r = await feature.run_now(B, "r_cron")
    await feature.cho_viec_nen()
    rec = stored("r_cron")
    check("run now answers ok", r.get("ok"))
    check("run now ran the engine once with the reminder id", len(seen) == 1 and seen[0][0] == "r_cron")
    check("run now used its own slot, not the next scheduled one",
          seen[0][1] != reminders.ledger_job("r_cron", due_before))
    check("run now delivered the answer", any("12 orders" in m["text"] for m in sent))
    check("a cron reminder keeps its schedule after run now", rec["status"] == "pending" and rec["due_at"] > now)
    r = await feature.run_now(B, "nope")
    check("run now refuses an unknown id", not r.get("ok"))

    # ── stop ──
    check("stop refuses a reminder that is not running", not feature.stop("r_cron").get("ok"))
    started = asyncio.Event()
    release = asyncio.Event()

    async def task_slow(_brain, _text, _mq="", **_kw):
        started.set()
        await release.wait()
        return "", "engine killed"

    feature._run_task = task_slow
    sent.clear()
    await feature.run_now(B, "r_cron")
    await started.wait()
    check("the view reports a running reminder", next(v for v in feature.live_views(B) if v["id"] == "r_cron")["running"])
    r = feature.stop("r_cron")
    check("stop answers ok while running", r.get("ok"))
    release.set()
    await feature.cho_viec_nen()
    rec = stored("r_cron")
    check("a stopped run posts nothing", sent == [])
    check("a stopped run is not retried", not rec.get("retry_of") and not rec.get("retry_count"))
    check("a stopped cron reminder keeps its schedule", rec["status"] == "pending" and rec["due_at"] > now)
    check("the stopped run is noted on the record", rec.get("error"))

    started.clear()
    release.clear()
    add("r_one", due_at=now + 7200)
    await feature.run_now(B, "r_one")
    await started.wait()
    feature.stop("r_one")
    release.set()
    await feature.cho_viec_nen()
    check("a stopped one-shot reminder ends cancelled", stored("r_one")["status"] == "cancelled")

    # ── cancel and clear keep their meaning with paused ──
    add("r_p")
    feature.pause(B, "r_p", True)
    check("a paused reminder can be cancelled", feature.cancel(B, "r_p") and stored("r_p")["status"] == "cancelled")

    # ── engine tag ──
    src = (Path(SERVER) / "reminders.py").read_text(encoding="utf-8")
    check("the reminder engine is tagged per id", src.count("tag=_engine_tag()") == 2)
    import aux_engine
    check("a per-id reminder tag still counts as scheduled background work",
          aux_engine.la_viec_nen_theo_lich("reminder:r_x") and aux_engine.la_viec_nen_theo_lich("reminder"))


asyncio.run(run())
print(f"\n{len(fails)} failed" if fails else "\nall passed")
raise SystemExit(1 if fails else 0)
