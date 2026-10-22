"""Regression (field report 0.270, code 26): a task-mode reminder that fails on a network error.

Reminder r_e55f930afd ran on catch-up right after the machine woke, failed with
"DeepSeek lỗi: getaddrinfo failed" (the Claude fallback crashed too), and was stored as status
"done" with an error, never tried again. Expected:
  - a failed run is stored "failed", not "done";
  - a network error schedules a bounded retry of the SAME firing a few minutes later;
  - the retry runs under the same once-only ledger key, so an outside action that went through in
    the first attempt is not sent again, and one with an unknown outcome blocks the retry;
  - repeating (cron) reminders still schedule their next run;
  - the failure still reaches the owner (one message, not one per retry), the answer of a
    successful retry gets its own inbox key.

Run:
    python tests/python/test_reminder_network_retry.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path (see tests/python/_paths.py)
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-reminder-retry-state-")

import once_ledger  # noqa: E402
import reminders  # noqa: E402

once_ledger.configure(Path(tempfile.mkdtemp(prefix="javis-reminder-retry-ledger-")) / "ledger.sqlite3")

fails = []
sent = []
incidents = []
brain = Path(tempfile.mkdtemp(prefix="javis-reminder-retry-brain-"))
NET_ERR = "DeepSeek lỗi: getaddrinfo failed | Claude CLI exit code 3221226505"


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


def atomic_write(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


async def fake_send(chat_id, text, viec=None, web="", brain="", dedup=""):
    sent.append({"chat_id": chat_id, "text": text, "viec": viec, "dedup": dedup})
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
    incident_hook=lambda *a, **kw: incidents.append((a, kw)),
)
feature = reminders.RemindersFeature(deps)


def stored(rid):
    data = json.loads((brain / "Javis" / "reminders.json").read_text(encoding="utf-8"))
    return next(r for r in data["reminders"] if r["id"] == rid)


def add(rid, **extra):
    rem = {"id": rid, "mode": "task", "text": "send the daily report to the staff group",
           "label": "Daily report", "chat_id": "", "status": "pending",
           "due_at": reminders._now() - 1, **extra}
    data = feature._load(str(brain))
    data.setdefault("reminders", []).append(dict(rem))
    feature._save(str(brain), data)
    return rem


def stub(results, outside=None):
    """Engine stand-in: each call pops (answer, error); `outside` simulates one hub write call."""
    seen = []

    async def task_stub(_brain, _text, _muc_quyen="", **_kw):
        seen.append(once_ledger.current_job())
        if outside is not None:
            await outside()
        return results.pop(0)

    feature._run_task = task_stub
    return seen


async def run():
    # ── is_transient_error ──
    check("getaddrinfo is a network error", reminders.is_transient_error(NET_ERR))
    check("connection refused is a network error",
          reminders.is_transient_error("httpx.ConnectError: [Errno 111] Connection refused"))
    check("an engine wall-clock cap is not retried",
          not reminders.is_transient_error("Fork went over the 3600s limit - stopped (background wall-clock cap)."))
    check("a missing sign-in is not retried even with a network word",
          not reminders.is_transient_error("Not logged in. Network error while refreshing the API key"))
    check("a plan limit is not retried", not reminders.is_transient_error("You've hit your limit · resets 1:50am"))

    # ── one-shot: network error -> retry scheduled, one warning sent ──
    rem = add("r_net")
    seen = stub([("", NET_ERR)])
    t0 = reminders._now()
    await feature._fire(str(brain), rem)
    rec = stored("r_net")
    check("network failure keeps the reminder pending for a retry", rec["status"] == "pending")
    check("retry is a few minutes later",
          t0 + reminders.RETRY_DELAYS_S[0] - 5 <= rec["due_at"] <= t0 + reminders.RETRY_DELAYS_S[0] + 5)
    check("retry remembers the slot it repeats", rec.get("retry_of") == rem["due_at"] and rec.get("retry_count") == 1)
    check("error is recorded on the record", "getaddrinfo" in rec.get("error", ""))
    check("the run carried the reminder's ledger job",
          seen == [reminders.ledger_job("r_net", rem["due_at"])])
    check("one warning went to Javis Core (empty chat id) saying it will retry",
          len(sent) == 1 and sent[0]["chat_id"] == ""
          and ("try again" in sent[0]["text"].lower() or "thử lại" in sent[0]["text"]))
    check("the chat card of the warning is failed", sent[0]["viec"]["status"] == "failed")
    check("no incident is opened while a retry is scheduled", incidents == [])
    first_dedup = sent[0]["dedup"]

    # ── retry 1 fails again: quiet, next retry scheduled ──
    sent.clear()
    seen = stub([("", NET_ERR)])
    await feature._fire(str(brain), stored("r_net"))
    rec = stored("r_net")
    check("second failure is quiet", sent == [])
    check("second retry scheduled", rec["status"] == "pending" and rec.get("retry_count") == 2)
    check("retry keeps the original firing's ledger key", seen == [reminders.ledger_job("r_net", rem["due_at"])])

    # ── retry 2 succeeds: answer delivered with its own inbox key, status done ──
    seen = stub([("Report sent to the staff group.", "")])
    await feature._fire(str(brain), stored("r_net"))
    rec = stored("r_net")
    check("successful retry marks the reminder done", rec["status"] == "done")
    check("retry fields are cleared", "retry_of" not in rec and "retry_count" not in rec)
    check("the answer is delivered", len(sent) == 1 and sent[0]["text"] == "Report sent to the staff group.")
    check("the answer has its own inbox key (not swallowed as a duplicate)", sent[0]["dedup"] != first_dedup)

    # ── retries used up: failed, final message, incident ──
    sent.clear()
    incidents.clear()
    rem = add("r_dead")
    for _ in range(len(reminders.RETRY_DELAYS_S) + 1):
        stub([("", NET_ERR)])
        await feature._fire(str(brain), stored("r_dead"))
    rec = stored("r_dead")
    check("after the last retry a one-shot reminder is failed (not done)", rec["status"] == "failed")
    check("bounded: exactly 1 warning + 1 final message", len(sent) == 2)
    n = len(reminders.RETRY_DELAYS_S)
    check("final message says it was retried",
          f"after {n} retries" in sent[-1]["text"] or f"thử lại {n} lần" in sent[-1]["text"])
    check("an incident is opened once, on the final failure", len(incidents) == 1)

    # ── a non-network error: failed at once, no retry (the root bug: it used to say done) ──
    sent.clear()
    rem = add("r_plain")
    stub([("", "Claude CLI is not installed")])
    await feature._fire(str(brain), rem)
    rec = stored("r_plain")
    check("a failed run is stored failed, not done", rec["status"] == "failed")
    check("no retry for a non-network error", "retry_count" not in rec)

    # ── cron: a retry still leaves the schedule intact ──
    # A daily slot 12 hours away, so the next regular run never falls inside the retry delay.
    far = (reminders._vnow().hour + 12) % 24
    daily = f"0 {far} * * *"
    rem = add("r_cron", cron=daily)
    stub([("", NET_ERR)])
    await feature._fire(str(brain), rem)
    rec = stored("r_cron")
    check("cron reminder retries the missed firing first", rec.get("retry_count") == 1 and rec["status"] == "pending")
    stub([("Done.", "")])
    await feature._fire(str(brain), stored("r_cron"))
    rec = stored("r_cron")
    nxt = reminders.cron_util.cron_next(daily, reminders._now(), reminders.VN_TZ())
    check("after the retry the cron schedules its next run", rec["status"] == "pending"
          and abs(rec["due_at"] - nxt) < 2 and "retry_of" not in rec)

    # ── cron whose next slot comes before the retry: no retry, next run kept ──
    rem = add("r_cron_soon", cron="*/5 * * * *")
    stub([("", NET_ERR)])
    await feature._fire(str(brain), rem)
    rec = stored("r_cron_soon")
    check("no retry when the next regular run is as soon", "retry_count" not in rec and rec["status"] == "pending")

    # ── once-only: an outside action of the first attempt is not repeated by the retry ──
    calls = []

    async def outside():
        async def really_send(_args):
            calls.append(1)
            return "sent"
        await once_ledger.run("zalo_send_message", {"threadId": "g1", "message": "daily report"}, really_send)

    rem = add("r_once")
    stub([("", NET_ERR)], outside=outside)
    await feature._fire(str(brain), rem)
    check("retry scheduled after the send went through", stored("r_once").get("retry_count") == 1)
    stub([("Report sent.", "")], outside=outside)
    await feature._fire(str(brain), stored("r_once"))
    check("the send ran exactly once across the two attempts", calls == [1])

    # ── once-only: an outside action with an unknown outcome blocks the retry ──
    async def outside_unknown():
        async def cut(_args):
            return "ERROR: ReadError: connection reset while sending"
        await once_ledger.run("zalo_send_message", {"threadId": "g2", "message": "hi"}, cut)

    sent.clear()
    rem = add("r_unsure")
    stub([("", NET_ERR)], outside=outside_unknown)
    await feature._fire(str(brain), rem)
    rec = stored("r_unsure")
    check("unknown outside action: no automatic retry", "retry_count" not in rec and rec["status"] == "failed")
    check("the owner is told why it was not retried", "g2" in rec.get("error", "") and len(sent) == 1)

    # ── view exposes the retry for the Work page ──
    rem = add("r_view")
    stub([("", NET_ERR)])
    await feature._fire(str(brain), rem)
    v = feature._view(stored("r_view"))
    check("view carries retry_count and retry_max",
          v["retry_count"] == 1 and v["retry_max"] == len(reminders.RETRY_DELAYS_S))
    upd = feature.update(str(brain), "r_view", delay_min=30)
    check("editing the time clears a pending retry", upd["ok"] and "retry_count" not in stored("r_view"))


asyncio.run(run())

if fails:
    print(f"\nFAIL - test_reminder_network_retry: {len(fails)} failed: {fails}")
    sys.exit(1)
print("\nOK - test_reminder_network_retry: all pass")
