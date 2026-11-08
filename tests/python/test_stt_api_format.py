"""Groq and OpenAI get audio they accept: a Zalo voice message (bare ADTS AAC) is turned into mp3 first.

    python tests/run.py stt_api_format      (no network: HTTP is faked, ffmpeg makes the sample clips)

2026-11-07, a real Zalo voice message (type chat.voice, a .aac file): the bot said it could not hear it. OpenAI
answered "Unsupported file format aac" for the .aac name and "Audio file might be corrupted or unsupported" when it
was renamed .m4a, because the file is raw AAC with no container. The same audio as mp3 came back as "Alo em nghe
hiểu không?". The fix sits in `stt._api_transcribe`, so every channel (Zalo, Telegram, the web chat) gets it.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import stt  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


def run(coro):
    return asyncio.run(coro)


# ============================================================
# 1. Sniffing the format from the first bytes (no ffmpeg needed)
# ============================================================
ADTS = bytes([0xFF, 0xF1, 0x50, 0x80, 0x02, 0x1F, 0xFC]) + b"\x00" * 40
MP3 = bytes([0xFF, 0xFB, 0x90, 0x64]) + b"\x00" * 40
check("CANARY: a bare ADTS AAC stream is recognised as .aac (what OpenAI refuses)", stt._sniff_audio(ADTS) == ".aac")
check("an MPEG audio frame is .mp3", stt._sniff_audio(MP3) == ".mp3")
check("an ID3 tag followed by an mp3 frame is .mp3", stt._sniff_audio(b"ID3\x04\x00\x00\x00\x00\x00\x00" + MP3) == ".mp3")
check("an ID3 tag followed by ADTS is still .aac", stt._sniff_audio(b"ID3\x04\x00\x00\x00\x00\x00\x00" + ADTS) == ".aac")
check("an mp4/m4a container is .m4a", stt._sniff_audio(b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 30) == ".m4a")
check("a Telegram voice note is .ogg", stt._sniff_audio(b"OggS\x00\x02" + b"\x00" * 30) == ".ogg")
check("wav, flac, webm", stt._sniff_audio(b"RIFF\x00\x00\x00\x00WAVEfmt ") == ".wav"
      and stt._sniff_audio(b"fLaC\x00") == ".flac" and stt._sniff_audio(b"\x1aE\xdf\xa3\x00") == ".webm")
check("garbage is unknown", stt._sniff_audio(b"fake audio") == "" and stt._sniff_audio(b"") == "")

# A known format goes untouched; only a wrong extension is corrected (the vendors read the name).
ogg = b"OggS\x00\x02" + b"\x00" * 30
d, n = run(stt._api_ready(ogg, "voice.ogg"))
check("a Telegram .ogg goes as is, same name", d is ogg and n == "voice.ogg", n)
d, n = run(stt._api_ready(ogg, "voice.opus"))
check(".opus is an ogg name the vendors take: kept", d is ogg and n == "voice.opus", n)
m4a = b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 30
d, n = run(stt._api_ready(m4a, "voice0.aac"))
check("a real m4a under a wrong name goes as is, renamed .m4a", d is m4a and n == "voice0.m4a", n)
d, n = run(stt._api_ready(ogg, ""))
check("no name at all gets one from the format", n == "voice.ogg", n)

# ============================================================
# 2. The real thing: an ADTS clip made by ffmpeg reaches the vendor as mp3
# ============================================================
SENT = []


class FakeResp:
    def __init__(self, code, body):
        self.status_code, self._b = code, body

    def json(self):
        return self._b


class FakeClient:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, data=None, files=None, **k):
        SENT.append((url, data, files))
        return FakeResp(200, {"text": "Alo em nghe hiểu không?"})


_httpx_client = stt.httpx.AsyncClient
stt.httpx.AsyncClient = FakeClient
try:
    if shutil.which("ffmpeg"):
        tmp = Path(tempfile.mkdtemp())
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=1",
                        "-c:a", "aac", "-f", "adts", str(tmp / "v.aac")], check=True)
        raw = (tmp / "v.aac").read_bytes()
        check("the sample really is bare ADTS", stt._sniff_audio(raw) == ".aac")
        for name, ear in (("voice0.m4a", stt.openai_nghe), ("voice.aac", stt.groq_nghe)):
            SENT.clear()
            r = run(ear(raw, name, "KEY"))
            fname, body = SENT[-1][2]["file"] if SENT else ("", b"")
            check(f"CANARY: a Zalo voice message named {name} reaches {ear.__name__} as mp3 and is heard",
                  r.get("ok") and fname.endswith(".mp3") and stt._sniff_audio(body) == ".mp3", (fname, r))
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        print("skip ffmpeg part: ffmpeg not installed")

    # Without a usable ffmpeg the file still goes as before: the vendor's own error is the useful report.
    _real_mp3 = stt._as_mp3

    async def _no_ffmpeg(data, name):
        return b""
    stt._as_mp3 = _no_ffmpeg
    SENT.clear()
    r = run(stt.openai_nghe(ADTS, "voice0.m4a", "KEY"))
    check("no ffmpeg -> the original bytes and name go unchanged",
          SENT and SENT[-1][2]["file"] == ("voice0.m4a", ADTS), SENT[-1][2]["file"][0] if SENT else "")
    stt._as_mp3 = _real_mp3
finally:
    stt.httpx.AsyncClient = _httpx_client

check("no em dash in stt.py", chr(0x2014) not in (SERVER / "stt.py").read_text(encoding="utf-8"))

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("Tất cả xanh.")
