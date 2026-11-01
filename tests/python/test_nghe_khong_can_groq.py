"""Voice messages and video sound are heard without Groq: OpenAI, Gemini, then the offline Whisper (0.435.0).

    python tests/run.py nghe_khong_can_groq      (no network: HTTP and the Whisper library are faked)

Owner, 2026-11-01: "anh muốn không cần groq mà vẫn nghe được", then "làm cả đường 1 và 2 luôn nhé, để không dùng được
cái này thì dùng cái khác". Until 0.434 only a Groq key could hear, and personal Zalo dropped voice messages outright.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-ear-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import channels  # noqa: E402,F401
import conversations  # noqa: E402,F401
import chatbot_runtime as cr  # noqa: E402
import local_stt  # noqa: E402
import optional_tools as ot  # noqa: E402
import stt  # noqa: E402
import zalo_attachments  # noqa: E402
import zalo_personal_channel as zc  # noqa: E402
from channels import zalo_personal as zp  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


def run(coro):
    return asyncio.run(coro)


# ============================================================
# 1. listen_any: every ear in turn
# ============================================================
CALLS = []
REPLIES = {}


def fake_ear(name):
    async def ear(data, ten_file, key, model="", ngon_ngu=None, hotwords=""):
        CALLS.append(name)
        return REPLIES.get(name) or {"ok": True, "text": f"nghe bằng {name}", "model": name}
    return ear


_real = (stt.groq_nghe, stt.openai_nghe, stt.gemini_nghe)
stt.groq_nghe, stt.openai_nghe, stt.gemini_nghe = fake_ear("groq"), fake_ear("openai"), fake_ear("gemini")


async def fake_local(data, ten_file, lang):
    CALLS.append("local")
    return REPLIES.get("local") or {"ok": True, "text": "nghe offline", "model": "whisper-small (offline)"}

ALL = {"groq": "g", "openai": "o", "gemini": "m"}
r = run(stt.listen_any(b"x", "a.ogg", ALL))
check("Groq first when its key is there", r.get("ear") == "groq" and CALLS == ["groq"], (r, CALLS))

CALLS.clear()
r = run(stt.listen_any(b"x", "a.ogg", {"openai": "o", "gemini": "m"}))
check("CANARY: no Groq key -> OpenAI hears it", r.get("ok") and r.get("ear") == "openai" and CALLS == ["openai"], CALLS)

CALLS.clear()
r = run(stt.listen_any(b"x", "a.ogg", {"gemini": "m"}))
check("only a Gemini key -> Gemini hears it", r.get("ear") == "gemini" and r.get("text") == "nghe bằng gemini", r)

CALLS.clear()
REPLIES["groq"] = {"ok": False, "ly_do": "loi", "noi_voi_javis": "x"}
REPLIES["openai"] = {"ok": False, "ly_do": "loi", "noi_voi_javis": "x"}
r = run(stt.listen_any(b"x", "a.ogg", ALL, local=fake_local))
check("CANARY: a failing ear hands over to the next (Groq, OpenAI down -> Gemini)",
      r.get("ear") == "gemini" and CALLS == ["groq", "openai", "gemini"], CALLS)

CALLS.clear()
REPLIES["gemini"] = {"ok": False, "ly_do": "qua_lon", "noi_voi_javis": "x"}
r = run(stt.listen_any(b"x", "a.ogg", ALL, local=fake_local))
check("every key failing -> the offline Whisper hears it", r.get("ear") == "local" and CALLS[-1] == "local", CALLS)

CALLS.clear()
REPLIES.clear()
REPLIES["groq"] = {"ok": False, "ly_do": "khong_nghe_ro", "noi_voi_javis": "x"}
r = run(stt.listen_any(b"x", "a.ogg", ALL, local=fake_local))
check("silence stays silence: 'nothing heard' does not try every other ear", CALLS == ["groq"]
      and r.get("ly_do") == "khong_nghe_ro", CALLS)

CALLS.clear()
REPLIES.clear()
r = run(stt.listen_any(b"x", "a.ogg", {}, local=fake_local))
check("no key at all but the offline ear installed -> it is used", r.get("ear") == "local" and r.get("ok"), r)
r = run(stt.listen_any(b"x", "a.ogg", {}))
check("no ear at all -> the 'missing ear' line", r.get("ly_do") == "thieu_key" and not r.get("ok"), r)

cau = stt.loi_thanh_dong("thieu_key")
check("the missing-ear line names every road: Groq, OpenAI, Gemini, the offline ear on the Tools page",
      all(w in cau for w in ("Groq", "OpenAI", "Gemini", "Models", "Công cụ", "Bộ nghe offline")), cau)
check("and still guards the customer role", "người thật" in cau and "đừng nhắc" in cau)
stt.groq_nghe, stt.openai_nghe, stt.gemini_nghe = _real

# ============================================================
# 2. gemini_nghe: the request, the answer, the formats
# ============================================================
SENT = []


class FakeResp:
    def __init__(self, code, body):
        self.status_code, self._b = code, body

    def json(self):
        return self._b


class FakeClient:
    reply = (200, {"candidates": [{"content": {"parts": [{"text": "máy giặt kêu tạch tạch rồi tắt"}]}}]})

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None, **k):
        SENT.append((url, headers, json))
        return FakeResp(*FakeClient.reply)


_httpx_client = stt.httpx.AsyncClient
stt.httpx.AsyncClient = FakeClient
try:
    r = run(stt.gemini_nghe(b"OggS-audio", "voice.ogg", "KEY", ngon_ngu="vi"))
    url, hdr, body = SENT[-1]
    part = body["contents"][0]["parts"][1]["inline_data"]
    check("CANARY: Gemini hears it", r.get("ok") and r.get("text") == "máy giặt kêu tạch tạch rồi tắt", r)
    check("the key goes in a header, never in the URL", hdr.get("x-goog-api-key") == "KEY" and "KEY" not in url, url)
    check("the default model takes audio", stt.GEMINI_STT_MODEL in url)
    check("the audio rides inline with its type", part["mime_type"] == "audio/ogg"
          and base64.b64decode(part["data"]) == b"OggS-audio", part["mime_type"])
    check("no thinking time spent on a transcript", body["generationConfig"]["thinkingConfig"]["thinkingBudget"] == 0)
    check("the language hint is passed", "vi" in body["contents"][0]["parts"][0]["text"])
    r = run(stt.gemini_nghe(b"x", "voice.ogg", ""))
    check("no Gemini key -> thieu_key (so the chain moves on)", r.get("ly_do") == "thieu_key")
    FakeClient.reply = (429, {"error": {"message": "Resource has been exhausted"}})
    r = run(stt.gemini_nghe(b"x", "voice.ogg", "KEY"))
    check("a Gemini error is 'loi' (the next ear gets a turn)", r.get("ly_do") == "loi", r)
    FakeClient.reply = (200, {"candidates": [{"content": {"parts": [{"text": '""'}]}}]})
    r = run(stt.gemini_nghe(b"x", "voice.ogg", "KEY"))
    check("an empty transcript is 'nothing heard'", r.get("ly_do") == "khong_nghe_ro", r)
    if shutil.which("ffmpeg"):
        tmp = Path(tempfile.mkdtemp())
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=1",
                        "-c:a", "aac", str(tmp / "v.m4a")], check=True)
        FakeClient.reply = (200, {"candidates": [{"content": {"parts": [{"text": "alo"}]}}]})
        r = run(stt.gemini_nghe((tmp / "v.m4a").read_bytes(), "voice.m4a", "KEY"))
        part = SENT[-1][2]["contents"][0]["parts"][1]["inline_data"]
        check("CANARY: a Zalo .m4a is turned into mp3 first (Gemini does not take m4a)",
              r.get("ok") and part["mime_type"] == "audio/mp3" and len(base64.b64decode(part["data"])) > 100, part["mime_type"])
        shutil.rmtree(tmp, ignore_errors=True)
finally:
    stt.httpx.AsyncClient = _httpx_client

# ============================================================
# 3. The offline ear: optional tool + the real worker with a fake Whisper library
# ============================================================
check("not installed -> not offered to the chain", not local_stt.installed())
r = run(local_stt.transcribe(b"x", "a.ogg", "vi"))
check("not installed -> thieu_key", r.get("ly_do") == "thieu_key", r)
ids = [d["id"] for d in ot.danh_sach()]
check("CANARY: the Tools page lists the offline ear next to the browser", ids[:2] == ["browser", "local_ear"], ids)
d = ot.trang_thai("local_ear")
check("its card says not installed, with a size hint", d["trang_thai"] == "chua_cai" and d.get("dung_luong_uoc"), d)
check("its card has both languages", local_stt.describe()["ten"])
argv = ot._lenh_cai("local_ear")[0]
check("install runs the worker in install mode into STATE_DIR",
      "--install" in argv and str(local_stt.LIB_DIR) in argv and argv[2].endswith("offline_ear/worker.py".replace("/", os.sep)), argv)
check("the worker sits alone in its folder (no server module can shadow a library)",
      sorted(p.name for p in local_stt.WORKER.parent.iterdir() if p.suffix == ".py") == ["worker.py"])

# A fake faster_whisper in LIB_DIR and a fake model: the REAL worker process runs end to end.
fw = local_stt.LIB_DIR / "faster_whisper"
fw.mkdir(parents=True)
(fw / "__init__.py").write_text(
    "class _S:\n    def __init__(s, t): s.text = t\n"
    "class _I:\n    language = 'vi'\n"
    "class WhisperModel:\n"
    "    def __init__(self, model, **kw): self.kw = kw\n"
    "    def transcribe(self, path, language=None, **kw):\n"
    "        data = open(path, 'rb').read()\n"
    "        return iter([_S(' alo shop '), _S('cho em hỏi giá ' + language)]), _I()\n", encoding="utf-8")
m = local_stt.MODEL_DIR / "models--x" / "snap"
m.mkdir(parents=True)
(m / "model.bin").write_bytes(b"0")
check("library + model on disk -> installed", local_stt.installed())
check("card: ready", ot.trang_thai("local_ear")["trang_thai"] == "san_sang")
r = run(local_stt.transcribe(b"audio-bytes", "voice.m4a", "vi"))
check("CANARY: the real worker process transcribes through the library", r.get("ok")
      and r.get("text") == "alo shop cho em hỏi giá vi" and "offline" in r.get("model", ""), r)
check("the temporary audio file is deleted", not list(local_stt.TMP_DIR.glob("*")))
(fw / "__init__.py").write_text("class WhisperModel:\n    def __init__(self, *a, **k): raise RuntimeError('bad model')\n",
                                encoding="utf-8")
r = run(local_stt.transcribe(b"audio-bytes", "voice.m4a", "vi"))
check("a broken model is 'loi', never a crash", r.get("ly_do") == "loi" and not r.get("ok"), r)
r = ot.go("local_ear")
check("Remove deletes everything Javis downloaded for it", r.get("ok") and not local_stt.ROOT.exists(), r)

# ============================================================
# 4. main wires the chain for every voice message and video
# ============================================================
src = (SERVER / "main.py").read_text(encoding="utf-8")
body = src[src.index("async def _stt_nghe("):]
body = body[:body.index("\n\n\n")]
check("CANARY: _stt_nghe uses every ear, not Groq only", "stt.listen_any(" in body and "openai_api_key" in body
      and "gemini_api_key" in body and "local_stt.transcribe if local_stt.installed()" in body)
check("keys are still read at the time of listening", "cfgmod.read_settings()" in body)

# ============================================================
# 5. Personal Zalo voice messages reach the bot, heard
# ============================================================
URL = "https://voice-aac-dl.zdn.vn/1234/voice.aac"
CONN = {"id": "zalo-1", "label": "Shop", "connector_id": "zalo"}
raw = {"id": "m1", "threadId": "t1", "threadType": "dm", "senderId": "t1", "senderName": "Khách", "text": URL,
       "timestamp": int(time.time() * 1000), "type": "chat.voice",
       "attachment": {"type": "chat.voice", "url": URL, "description": ""}}
e = zc.chuan_hoa_tin(CONN, raw, {"t1": {"name": "Khách", "type": "dm"}})
check("a javis-zalo voice message keeps its link", e and e["message_type"] == "audio"
      and e["metadata"].get("audio_url") == URL, e)


def ev(kind, text="", url="", i=[0]):
    i[0] += 1
    md = {"audio_url": url} if url else {}
    return {"chat_type": "private", "message_type": kind, "text": text or url, "external_chat_id": "t1",
            "sender_id": "t1", "sender_name": "Khách", "created_at": time.time(), "metadata": md,
            "external_message_id": f"a{i[0]}", "sender_type": "customer", "account_id": "zalo-1"}


g = zc.gop_tin([ev("audio", url=URL), ev("text", "anh ơi")])
check("CANARY: voice + text -> a text turn carrying the voice message", g["message_type"] == "text"
      and g["metadata"].get("audio_urls") == [URL] and URL not in g["text"], g)
g = zc.gop_tin([ev("audio", url=URL + str(k)) for k in range(5)])
check("a voice-only turn has kind 'audio', newest MAX_AUDIO_GOP kept", g["message_type"] == "audio"
      and len(g["metadata"]["audio_urls"]) == zc.MAX_AUDIO_GOP and g["metadata"]["audio_urls"][-1] == URL + "4", g)

FETCH = []


async def fake_fetch(info, inbox, max_bytes=0):
    FETCH.append((info["url"], max_bytes))
    if "expired" in info["url"]:
        return None, "máy chủ file trả HTTP 404 (link có thể đã hết hạn)"
    p = Path(inbox) / info["name"]
    p.write_bytes(b"aac-bytes")
    return p, ""

HEARD = []


async def fake_hear(data, name):
    HEARD.append((data, name))
    return {"ok": True, "text": "cho em hỏi máy này bảo hành bao lâu"}

zalo_attachments.fetch_file = fake_fetch
cr._deps["transcribe"] = fake_hear
n = run(cr.nghe_cho_bot({"audio_urls": [URL]}, {}))
check("CANARY: the bot gets what the voice message said", "bảo hành bao lâu" in n and "máy nghe chép lại" in n, n)
check("downloaded with the audio size cap", FETCH and FETCH[-1][1] == cr.AUDIO_MAX_BYTES and HEARD[-1][0] == b"aac-bytes")
cfg = {}
n = run(cr.nghe_cho_bot({"audio_urls": ["https://x.zdn.vn/expired.aac"]}, cfg))
check("a voice message that cannot be fetched -> honest line, no guess", "không nghe được" in n
      and "Đừng đoán" in n and "tin thoại" in str(cfg.get("_anh_loi")), n)


async def no_ear(data, name):
    return {"ok": False, "ly_do": "thieu_key", "noi_voi_javis": "x"}

cr._deps["transcribe"] = no_ear
n = run(cr.nghe_cho_bot({"audio_urls": [URL]}, {}))
check("no ear at all -> the bot asks the customer to type and never mentions settings to them",
      "gõ chữ" in n and "đừng nhắc" in n, n)
cr._deps["transcribe"] = fake_hear
text, paths = run(cr.anh_cho_bot(cr.AUDIO_TRON, {"chat_id": "t1", "audio_urls": [URL]}, {"id": "b", "brain": "x"}))
check("anh_cho_bot puts the heard words in front of the turn", text.startswith("(khách gửi tin thoại")
      and text.endswith(cr.AUDIO_TRON) and not paths, text)
m = cr.manual_meta({"channel_account_id": "zalo_personal:zalo-1", "external_chat_id": "t1", "chat_type": "private",
                    "channel": "zalo_personal"},
                   {"message_type": "audio", "metadata": {"audio_url": URL}, "external_message_id": "a1"})
check("the inbox 'A.I. reply' on a voice message hears it too", m.get("audio_urls") == [URL], m)

LUOT = []


async def fake_goi(conn, tool, args):
    return {"success": True} if tool == "zalo_send_message" else {}

zc._ket_noi = lambda: [dict(CONN)]
zc._goi = fake_goi
zc.start = lambda: True


async def _answer(text, meta, progress):
    LUOT.append((text, dict(meta)))
    return {"text": "Dạ em nghe rồi ạ.", "files": []}


async def live():
    tb = zp.Transport("zalo-1", [], _answer, cfg_fn=lambda: {"id": "bot-x", "reply_when": "mention"})
    tb.start()
    await tb.xu_ly(ev("audio", url=URL))
    check("CANARY: a private voice message alone reaches the bot (was dropped before)", len(LUOT) == 1, LUOT)
    t, mm = LUOT[0] if LUOT else ("", {})
    check("with its link, and a placeholder instead of the raw link", mm.get("audio_urls") == [URL]
          and t == cr.AUDIO_TRON, (t, mm))
    LUOT.clear()
    gv = ev("audio", url=URL)
    gv.update(chat_type="group", external_chat_id="g1", sender_id="u9")
    await tb.xu_ly(gv)
    check("a voice message in a group: unchanged, not answered", not LUOT, LUOT)
    tb.stop()

run(live())

for f in (Path(__file__), SERVER / "local_stt.py", SERVER / "offline_ear" / "worker.py", SERVER / "stt.py"):
    check(f"no em dash in {f.name}", chr(0x2014) not in f.read_text(encoding="utf-8"))

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("Tất cả xanh.")
