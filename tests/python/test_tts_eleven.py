"""ElevenLabs voice (0.255.0): a model that speaks Vietnamese, the account's voices by name, voice notes.

    python tests/python/test_tts_eleven.py

Owner, 2026-10-20: "đang thiếu mất ElevenLabs để làm giọng của Javis". No network: httpx is replaced
by a fake client that records what would be sent to api.elevenlabs.io.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-eleven-"))

import httpx  # noqa: E402

import tts_eleven as te  # noqa: E402

_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or not extra else "  " + str(extra)))
    if not cond:
        _fails.append(name)


class FakeResp:
    def __init__(self, status=200, content=b"", data=None):
        self.status_code, self.content, self._data = status, content, data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=None, response=None)

    def json(self):
        return self._data


class FakeClient:
    calls = []
    post_resp = FakeResp(200, b"ID3eleven")
    get_resp = FakeResp(200, data={"voices": []})

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None, params=None):
        FakeClient.calls.append(("post", url, headers, json, params))
        return FakeClient.post_resp

    async def get(self, url, headers=None):
        FakeClient.calls.append(("get", url, headers))
        r = FakeClient.get_resp
        if isinstance(r, Exception):
            raise r
        return r


httpx.AsyncClient = FakeClient
run = asyncio.run

# ---- model: Vietnamese never goes to a model without Vietnamese ----
check("default model is Flash v2.5 and it speaks Vietnamese", te.DEFAULT_MODEL == "eleven_flash_v2_5" and te.MODELS[te.DEFAULT_MODEL])
check("Multilingual v2 is marked without Vietnamese", te.MODELS["eleven_multilingual_v2"] is False)
check("saved Multilingual v2 + Vietnamese text -> Flash v2.5",
      te.effective_model("eleven_multilingual_v2", "Chào anh, hôm nay doanh thu tăng") == "eleven_flash_v2_5")
check("saved Multilingual v2 + English text stays v2", te.effective_model("eleven_multilingual_v2", "Good morning") == "eleven_multilingual_v2")
check("Eleven v3 is kept for Vietnamese", te.effective_model("eleven_v3", "Xin chào") == "eleven_v3")
check("empty or unknown model -> default", te.effective_model("", "x") == te.DEFAULT_MODEL and te.effective_model("eleven_bogus", "x") == te.DEFAULT_MODEL)

# ---- synth: what is sent ----
cfg = {"voice": {"tts_provider": "elevenlabs", "elevenlabs_key": " sk_1 ", "elevenlabs_voice": "", "elevenlabs_model": "eleven_multilingual_v2"}}
audio = run(te.synth("Dạ, em chào anh", cfg))
_, url, headers, payload, params = FakeClient.calls[-1]
check("synth returns the audio", audio == b"ID3eleven")
check("synth: default voice when none saved, key trimmed, mp3",
      url.endswith("/v1/text-to-speech/" + te.DEFAULT_VOICE) and headers["xi-api-key"] == "sk_1" and params["output_format"].startswith("mp3"))
check("synth: Vietnamese text sent with Flash v2.5, the text untouched",
      payload == {"text": "Dạ, em chào anh", "model_id": "eleven_flash_v2_5"}, payload)
try:
    run(te.synth("x", {"voice": {"elevenlabs_key": ""}}))
    check("synth without key raises", False)
except RuntimeError:
    check("synth without key raises", True)
check("chosen(): only with provider elevenlabs AND a key",
      te.chosen(cfg) and not te.chosen({"voice": {"tts_provider": "edge", "elevenlabs_key": "k"}})
      and not te.chosen({"voice": {"tts_provider": "elevenlabs", "elevenlabs_key": ""}}))

# ---- voices by name ----
FakeClient.get_resp = FakeResp(200, data={"voices": [
    {"voice_id": "p2", "name": "Rachel", "category": "premade", "labels": {"gender": "female", "accent": "american"}},
    {"voice_id": "c1", "name": "Quý clone", "category": "cloned", "labels": {}},
    {"voice_id": "p1", "name": "Adam", "category": "premade", "labels": {"gender": "male"}},
    {"name": "no id"},
]})
res = run(te.list_voices("sk_1"))
check("list_voices: own voices first, then premade by name, rows without id dropped",
      res["ok"] and [v["id"] for v in res["voices"]] == ["c1", "p1", "p2"], res)
check("list_voices: gender and accent carried", res["voices"][2] == {"id": "p2", "name": "Rachel", "category": "premade", "gender": "female", "accent": "american"})
check("list_voices: key sent in xi-api-key", FakeClient.calls[-1][2] == {"xi-api-key": "sk_1"})
check("list_voices: no key -> no_key, no call", run(te.list_voices("")) == {"ok": False, "reason": "no_key"})
FakeClient.get_resp = FakeResp(401, data={})
check("list_voices: 401 -> bad_key", run(te.list_voices("sk_bad")) == {"ok": False, "reason": "bad_key"})
FakeClient.get_resp = httpx.ConnectError("down")
check("list_voices: network error -> network", run(te.list_voices("sk_1")) == {"ok": False, "reason": "network"})

# ---- the route and the settings save ----
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app, base_url="http://127.0.0.1")
_read = main.cfgmod.read_settings
main.cfgmod.read_settings = lambda: {"voice": {"elevenlabs_key": ""}, "model": {}}
d = client.get("/voice/elevenlabs/voices").json()
check("route: no key -> ok false with a readable reason", d["ok"] is False and d["reason"] == "no_key" and d["error"])
main.cfgmod.read_settings = _read

src = open(os.path.join(SERVER, "main.py"), encoding="utf-8").read()
check("settings save accepts only a known ElevenLabs model",
      'if str(patch.get("elevenlabs_model") or "").strip() in tts_eleven.MODELS:' in src)
check("/voice/options carries the saved model and the model list",
      '"elevenlabs_model": v.get("elevenlabs_model") or "",' in src and '"elevenlabs_models": _eleven_models(),' in src)

# ---- voice notes speak with ElevenLabs when chosen, fall back to Edge ----
import voice_note  # noqa: E402

FakeClient.post_resp = FakeResp(200, b"ID3note")
main.cfgmod.read_settings = lambda: cfg
vault = tempfile.mkdtemp(prefix="javis-eleven-vault-")
r = run(voice_note.make(vault, "Nhắc anh: 3 giờ chiều họp với nhà cung cấp"))
check("voice note: ElevenLabs chosen -> the note is ElevenLabs audio",
      r["ok"] and open(os.path.join(vault, r["rel_path"]), "rb").read() == b"ID3note", r)


async def _fake_edge(text, voice):
    return b"ID3edge"

voice_note._edge = _fake_edge
FakeClient.post_resp = FakeResp(429, b"")
r = run(voice_note.make(vault, "Nhắc anh họp"))
check("voice note: ElevenLabs fails -> Edge, the note is still made",
      r["ok"] and open(os.path.join(vault, r["rel_path"]), "rb").read() == b"ID3edge", r)
main.cfgmod.read_settings = lambda: {"voice": {"tts_provider": "edge"}}
r = run(voice_note.make(vault, "Nhắc anh họp"))
check("voice note: Edge chosen -> Edge", r["ok"] and open(os.path.join(vault, r["rel_path"]), "rb").read() == b"ID3edge")
main.cfgmod.read_settings = _read

for f in ("tts_eleven.py",):
    t = open(os.path.join(SERVER, f), encoding="utf-8").read()
    check(f"{f}: no em or en dash", "—" not in t and "–" not in t)

print()
if _fails:
    print(f"FAIL {len(_fails)} test")
    sys.exit(1)
print("TẤT CẢ PASS")
