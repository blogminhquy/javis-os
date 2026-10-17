"""0.203.0: Javis calls you at a set time.

A reminder created with `call` keeps the flag, shows it, can be switched off, and when it fires its
JAVIS_VIEC block carries "call" so the open dashboard rings (dashboard/incoming-call.js). A failed run
or a script job never rings. The javis_schedule tool passes `call` on create and update.

Run:
    python tests/run.py scheduled_call
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-call-")
sys.path.insert(0, str(ROOT / "system" / "plugins" / "javis-schedule"))

import reminders  # noqa: E402
import plugin as sched  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


brain = Path(tempfile.mkdtemp(prefix="javis-call-brain-"))
sent = []


async def send(chat_id, text, viec=None, web=None, **kw):
    sent.append({"text": text, "viec": viec, "web": web})
    return True, ""


def atomic(p, t):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(t, encoding="utf-8")


feat = reminders.RemindersFeature(reminders.RemindersDeps(
    brain_root=lambda _b: str(brain), atomic_write_text=atomic, send_telegram=send,
    build_system_prompt=lambda _b: "", aux_model=lambda: None, safe_tools=[], readonly_tools=[],
    scheduler_brains=lambda: [str(brain)]))


async def main():
    rem = feat._create(str(brain), "đọc báo cáo doanh thu", delay_min=1, mode="notify", call=True,
                       allow_no_channel=True, label="Báo cáo sáng")
    check("call stored and shown", rem["call"] is True and feat._view(rem)["call"] is True)
    await feat._fire(str(brain), dict(rem, chat_id="123"))
    v = sent[-1]["viec"] or {}
    check("fired message marked as a call", v.get("kind") == "reminder" and v.get("call") == "1")
    plain = feat._create(str(brain), "uống nước", delay_min=1, mode="notify", allow_no_channel=True)
    await feat._fire(str(brain), dict(plain, chat_id="123"))
    check("plain reminder does not ring", "call" not in (sent[-1]["viec"] or {}))
    check("old records read as no call", feat._view({"id": "x"})["call"] is False)
    later = feat._create(str(brain), "họp", delay_min=30, mode="notify", allow_no_channel=True)
    upd = feat.update(str(brain), later["id"], call="true")
    check("update turns call on", upd["ok"] and upd["reminder"]["call"] is True)
    upd = feat.update(str(brain), later["id"], call="false")
    check("update turns call off", upd["ok"] and upd["reminder"]["call"] is False)

asyncio.run(main())

import main as app_main  # noqa: E402
blk = app_main.khoi_viec({"kind": "reminder", "status": "done", "title": "T", "id": "r", "call": "1"})
check("JAVIS_VIEC block keeps the call flag", '"call": "1"' in blk)
check("block without call stays as before", "call" not in app_main.khoi_viec({"kind": "reminder", "status": "done"}))

# javis_schedule tool: create and update pass `call`
captured = {}


async def fake_post(payload, brain_name=""):
    captured.clear()
    captured.update(payload)
    return "ok"


async def fake_update(vault_root, rid, fields):
    captured.clear()
    captured.update(fields)
    return "ok"


vault = tempfile.mkdtemp(prefix="javis-call-vault-")
real_post, real_upd = sched._post_reminder, sched._update_reminder
sched._post_reminder, sched._update_reminder = fake_post, fake_update
try:
    asyncio.run(sched._do_create(vault, {"name": "Gọi báo cáo", "prompt": "Đọc báo cáo doanh thu",
                                         "schedule": "7h sáng mai", "call": True}))
    check("tool create sends call", captured.get("call") is True)
    asyncio.run(sched._do_create(vault, {"name": "Nhắc", "prompt": "x", "schedule": "30 phut nua"}))
    check("tool create without call sends none", "call" not in captured)
    asyncio.run(sched._do_update(vault, {"id": "r_1", "call": False}))
    check("tool update can switch call alone", captured.get("call") == "false")
finally:
    sched._post_reminder, sched._update_reminder = real_post, real_upd
schema_src = (ROOT / "system" / "plugins" / "javis-schedule" / "plugin.py").read_text(encoding="utf-8")
check("tool schema documents call", '"call": {"type": "boolean"' in schema_src)

print()
print("FAIL" if fails else "PASS", f"({len(fails)} failed)")
raise SystemExit(1 if fails else 0)
