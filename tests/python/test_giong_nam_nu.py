"""The voice picked in Settings is the voice you hear (0.298.0).

    python tests/run.py giong_nam_nu      (no network, Edge never called)

Owner report 23/10/2026: "cài đặt là nữ nhưng khi nói là giọng nói nam, lưu thế nào cũng không cài được". The Edge
voice lived only in one browser's localStorage, so a voice picked on the laptop never reached the phone, nor the voice
notes Javis records for Telegram and Zalo. Checks:
  1. POST /settings keeps `edge_voice` (an Edge name or "auto"), refuses anything else, /voice/options returns it;
  2. voice notes use that voice when it can read the text, and the language default when it cannot;
  3. every live voice the server offers has male/female in dashboard/voice-catalog.js (only alloy is neutral), so
     the Settings list never shows a bare name again.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import re
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-gioi-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from fastapi.testclient import TestClient   # noqa: E402
import config as c   # noqa: E402
import main          # noqa: E402
import voice_live    # noqa: E402
import voice_note    # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


cl = TestClient(main.app, base_url="http://127.0.0.1:7777")


def luu(data):
    return cl.post("/settings", data={"section": "voice", "data": json.dumps(data)})


# ---- 1. edge_voice is saved on the server ----
r = luu({"tts_provider": "edge", "edge_voice": "vi-VN-HoaiMyNeural"})
check("saving an Edge voice answers ok", r.status_code == 200 and r.json().get("ok") is True)
check("the Edge voice is kept in settings", (c.read_settings().get("voice") or {}).get("edge_voice") == "vi-VN-HoaiMyNeural")
luu({"edge_voice": "<script>"})
check("a value that is not an Edge voice is refused", (c.read_settings().get("voice") or {}).get("edge_voice") == "vi-VN-HoaiMyNeural")
luu({"edge_voice": "auto"})
check("'auto' (follow the language) is accepted", (c.read_settings().get("voice") or {}).get("edge_voice") == "auto")
luu({"edge_voice": "en-US-AvaMultilingualNeural"})
o = cl.get("/voice/options?brains=0").json()
check("/voice/options returns the saved Edge voice to the Settings card", (o.get("tts") or {}).get("edge_voice") == "en-US-AvaMultilingualNeural")
check("GET /settings carries it too (the dashboard syncs this browser from it)",
      (cl.get("/settings").json().get("voice") or {}).get("edge_voice") == "en-US-AvaMultilingualNeural")

# ---- 2. voice notes follow the chosen voice when it can read the text ----
VI = "Chào chị, đơn hàng đã giao xong."
EN = "Your order has been delivered."
P = voice_note.pick_voice
check("a voice named by the tool still wins", P(VI, "vi-VN-NamMinhNeural", "en-US-AvaMultilingualNeural") == "vi-VN-NamMinhNeural")
check("a multilingual chosen voice reads Vietnamese", P(VI, "", "en-US-AvaMultilingualNeural") == "en-US-AvaMultilingualNeural")
check("a multilingual chosen voice reads English", P(EN, "", "en-US-AndrewMultilingualNeural") == "en-US-AndrewMultilingualNeural")
check("a Vietnamese chosen voice reads Vietnamese", P(VI, "", "vi-VN-NamMinhNeural") == "vi-VN-NamMinhNeural")
check("a Vietnamese-only voice does not read English: language default", P(EN, "", "vi-VN-HoaiMyNeural") == voice_note.DEFAULT_VOICE)
check("'auto' or nothing chosen keeps the old behaviour", P(VI, "", "auto") == voice_note.VI_VOICE and P(VI) == voice_note.VI_VOICE)
check("make() reads the chosen voice from settings", voice_note._chosen_edge_voice() == "en-US-AvaMultilingualNeural")

# ---- 3. every live voice carries male/female ----
cat = (ROOT / "dashboard" / "voice-catalog.js").read_text(encoding="utf-8")
known = {k.lower(): g for k, g in re.findall(r'"?([A-Za-z-]+)"?:\s*"([fmn])"', cat)}
offered = set()
for p in voice_live.PROVIDERS.values():
    offered.update(v.lower() for v in p.get("voices") or [])
missing = sorted(v for v in offered if v not in known)
check("every live voice the server offers has a gender in voice-catalog.js", not missing, missing)
neutral = sorted(v for v in offered if known.get(v) == "n")
check("only alloy is neutral", neutral == ["alloy"], neutral)
cs = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
tts_voices = re.search(r"OPENAI_TTS_VOICES = \[([^\]]*)\]", cs).group(1)
miss_tts = [v for v in re.findall(r'"([a-z]+)"', tts_voices) if v not in known]
check("every OpenAI reading voice has a gender", not miss_tts, miss_tts)
html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
edge = re.search(r'<select id="voiceSel".*?</select>', html, re.S).group(0)
miss_edge = [v for v in re.findall(r'value="([^"]+)"', edge) if v.lower() not in known]
check("every Edge voice in the list has a gender", not miss_edge, miss_edge)

for f in ("server/voice_note.py", "dashboard/voice-catalog.js", "tests/python/test_giong_nam_nu.py"):
    src = (ROOT / f).read_text(encoding="utf-8")
    check("no em or en dash in " + f, chr(0x2014) not in src and chr(0x2013) not in src)

if _fails:
    print(f"\n{len(_fails)} FAIL")
    sys.exit(1)
print("\nPASS")
