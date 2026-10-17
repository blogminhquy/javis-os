"""0.202.0: voice notes (tool + reminders that read their result aloud).

Run:
    python tests/run.py voice_note
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-voice-")

import reminders  # noqa: E402
import voice_note  # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


brain = Path(tempfile.mkdtemp(prefix="javis-voice-brain-"))
said = []


async def fake_synth(text, voice):
    said.append((text, voice))
    return b"ID3fakeaudio"


async def main():
    r = await voice_note.make(str(brain), "**Doanh thu** hôm nay [xem](https://x.y) 12 triệu", synth=fake_synth)
    check("note saved under attachments/voice", r["ok"] and r["rel_path"].startswith("attachments/voice/")
          and (brain / r["rel_path"]).read_bytes() == b"ID3fakeaudio")
    check("markdown and links not read aloud", "**" not in said[-1][0] and "https" not in said[-1][0] and "xem" in said[-1][0])
    check("Vietnamese text gets a Vietnamese voice", said[-1][1] == voice_note.VI_VOICE)
    check("named voice honoured", voice_note.pick_voice("hello", "en-GB-SoniaNeural") == "en-GB-SoniaNeural")
    check("odd voice name ignored", voice_note.pick_voice("hello", "../../etc") != "../../etc")
    check("too long refused", not (await voice_note.make(str(brain), "a " * 800, synth=fake_synth))["ok"])
    check("empty refused", not (await voice_note.make(str(brain), "   ", synth=fake_synth))["ok"])
    check("no brain refused", not (await voice_note.make("", "xin chào", synth=fake_synth))["ok"])

    sent, files = [], []

    async def send(chat_id, text, **kw):
        sent.append((chat_id, text, kw))
        return True, ""

    async def make_voice(b, text):
        return "attachments/voice/v1.mp3"

    async def send_file(chat_id, path, b):
        files.append((chat_id, path))
        return True, ""

    def atomic(p, t):
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        Path(p).write_text(t, encoding="utf-8")

    feat = reminders.RemindersFeature(reminders.RemindersDeps(
        brain_root=lambda _b: str(brain), atomic_write_text=atomic, send_telegram=send,
        build_system_prompt=lambda _b: "", aux_model=lambda: None, safe_tools=[], readonly_tools=[],
        scheduler_brains=lambda: [str(brain)], make_voice=make_voice, send_file=send_file))
    rem = feat._create(str(brain), "uống thuốc", delay_min=1, mode="notify", speak=True, allow_no_channel=True)
    check("speak stored", rem["speak"] is True and feat._view(rem)["speak"] is True)
    await feat._fire(str(brain), dict(rem, chat_id="123"))
    check("message carries the voice link", sent and "[🔊 Tin thoại](attachments/voice/v1.mp3)" in sent[-1][1])
    check("audio file sent to the chat", files == [("123", str(brain / "attachments/voice/v1.mp3"))])
    quiet = feat._create(str(brain), "không đọc", delay_min=1, mode="notify", allow_no_channel=True)
    n = len(files)
    await feat._fire(str(brain), dict(quiet, chat_id="123"))
    check("no voice unless asked", len(files) == n and "Tin thoại" not in sent[-1][1])
    scr = feat._create(str(brain), "x", delay_min=1, mode="notify", speak=True, allow_no_channel=True)
    upd = feat.update(str(brain), scr["id"], speak="false")
    check("update turns speak off", upd["ok"] and upd["reminder"]["speak"] is False)

asyncio.run(main())

y = (ROOT / "system" / "plugins" / "voice-note" / "plugin.yaml").read_text(encoding="utf-8")
check("plugin declared with safe min_mode", "javis_voice_note" in y and "min_mode: safe" in y)
js = (ROOT / "dashboard" / "chat-render.js").read_text(encoding="utf-8")
check("chat draws an audio player for audio links", "AUDIO_EXT_RE" in js and "<audio" in js)
tg = (ROOT / "server" / "telegram_bot.py").read_text(encoding="utf-8")
check("Telegram sends mp3 as audio", "sendAudio" in tg)

print()
print("FAIL" if fails else "PASS", f"({len(fails)} failed)")
raise SystemExit(1 if fails else 0)
