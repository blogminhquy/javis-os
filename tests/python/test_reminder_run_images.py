"""A scheduled `task` reminder sends the pictures its run made to the chat that asked (#1285).

A report drawn as an image (an ads summary on a fixed template) reached the owner's Zalo bot as text only: chat
replies sent images with `sendPhoto`, the reminder path sent text and nothing else, so the picture stayed in the brain.

Contract:
  1. images the answer names AND that were written during this run are sent to the reminder's chat;
  2. an old picture, a file that is not an image, an oversized one, and anything past RUN_IMAGES_MAX are not sent;
  3. a `notify` reminder and a failed run send no picture;
  4. a failed image never fails the reminder (the text has gone out);
  5. `zalo:<id>` goes through the Zalo bot's own allow-list (main._zalo_send_file_to).

    python tests/run.py reminder_run_images      (no network)
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-rem-img-")

import reminders  # noqa: E402

fails = []


def check(name, cond, extra=None):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or extra is None else f"  [{extra}]"))
    if not cond:
        fails.append(name)


brain = Path(tempfile.mkdtemp(prefix="javis-rem-img-brain-"))
(brain / "attachments").mkdir()
old = brain / "attachments" / "old.png"
old.write_bytes(b"\x89PNG old")
os.utime(old, (time.time() - 3600, time.time() - 3600))


def atomic(p, t):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(t, encoding="utf-8")


async def main():
    sent, files = [], []
    answer = {"text": "", "err": ""}
    file_result = {"value": (True, "")}

    async def send(chat_id, text, **kw):
        sent.append((chat_id, text))
        return True, ""

    async def send_file(chat_id, path, b):
        files.append((chat_id, Path(path).name))
        r = file_result["value"]
        if isinstance(r, Exception):
            raise r
        return r

    feat = reminders.RemindersFeature(reminders.RemindersDeps(
        brain_root=lambda _b: str(brain), atomic_write_text=atomic, send_telegram=send,
        build_system_prompt=lambda _b: "", aux_model=lambda: None, safe_tools=[], readonly_tools=[],
        scheduler_brains=lambda: [str(brain)], send_file=send_file))

    async def fake_run(b, text, muc_quyen="", **kw):
        # The run writes its pictures now, as a real engine would during the turn.
        for name in ("report.png", "chart.jpg", "big.png", "notes.pdf", "a.png", "b.png", "c.png"):
            (brain / "attachments" / name).write_bytes(b"x" * (reminders.RUN_IMAGE_MAX_BYTES + 1 if name == "big.png" else 64))
        return answer["text"], answer["err"]

    feat._run_task = fake_run
    rem = feat._create(str(brain), "báo cáo ads", delay_min=1, mode="task", allow_no_channel=True)

    answer["text"] = ("Báo cáo hôm nay:\n\n![report](attachments/report.png)\n\n![chart](attachments/chart.jpg)\n\n"
                      "![cũ](attachments/old.png) [ghi chú](attachments/notes.pdf) ![to](attachments/big.png)")
    await feat._fire(str(brain), dict(rem, chat_id="zalo:777"))
    check("the text went out first", sent and sent[-1][0] == "zalo:777" and "Báo cáo hôm nay" in sent[-1][1], sent)
    check("the two pictures of this run are sent to the same chat",
          sorted(files) == [("zalo:777", "chart.jpg"), ("zalo:777", "report.png")], files)
    check("an old picture, a PDF and an oversized image are not sent",
          not any(n in ("old.png", "notes.pdf", "big.png") for _c, n in files), files)

    files.clear()
    answer["text"] = " ".join(f"![x](attachments/{n})" for n in ("report.png", "chart.jpg", "a.png", "b.png", "c.png"))
    await feat._fire(str(brain), dict(rem, chat_id="123"))
    check("at most RUN_IMAGES_MAX pictures per run", len(files) == reminders.RUN_IMAGES_MAX, files)

    files.clear()
    answer["text"], answer["err"] = "", "engine down"
    await feat._fire(str(brain), dict(rem, chat_id="123"))
    check("a failed run sends no picture", files == [], files)

    answer["text"], answer["err"] = "![report](attachments/report.png)", ""
    for bad in ((False, "sendPhoto HTTP 400"), RuntimeError("network")):
        files.clear()
        n = len(sent)
        file_result["value"] = bad
        await feat._fire(str(brain), dict(rem, chat_id="zalo:777"))
        check(f"a failed image ({type(bad).__name__}) does not fail the reminder", len(sent) == n + 1 and len(files) == 1)
    file_result["value"] = (True, "")

    files.clear()
    note = feat._create(str(brain), "![report](attachments/report.png)", delay_min=1, mode="notify", allow_no_channel=True)
    (brain / "attachments" / "report.png").write_bytes(b"fresh")
    await feat._fire(str(brain), dict(note, chat_id="123"))
    check("a plain `notify` reminder sends no picture", files == [], files)

asyncio.run(main())

src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
fn = src[src.index("async def _send_voice_file("):src.index("import my_tasks as my_tasks_mod")]
check("a zalo: chat goes to the Zalo bot, not to Telegram",
      'if cid.startswith("zalo:"):' in fn and "_zalo_send_file_to(cid[len(\"zalo:\"):], path)" in fn)
check("the Zalo path keeps the bot's allow-list", "if not cid or (ids and cid not in ids):" in fn
      and 'z.get("enabled") and z.get("token")' in fn)
check("the web chat still gets no file (it shows the embedded image)", 'cid.startswith("web:")' in fn)

print()
print("FAIL" if fails else "PASS", f"({len(fails)} failed)")
raise SystemExit(1 if fails else 0)
