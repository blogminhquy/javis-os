"""Each vendor's newest speech-to-text model is picked by asking the vendor, not by a name in the code (2026-11-08).

    python tests/run.py stt_models      (no network: the vendors' model lists are faked)

Owner: "pick the vendor's best Whisper by itself when they upgrade, no hand update in Javis". Locks:
  - the ranking per vendor on realistic lists: newest full-size model, never English-only, preview, diarize or lite;
  - a sentence never waits for the list (the default is used, the list is fetched in the background);
  - discovery is off in tests (JAVIS_NO_STT_MODEL_DISCOVERY) and a pinned model always wins;
  - a discovered model the vendor refuses is retried with the default, then left aside for a day;
  - Groq, OpenAI and Gemini ears really send the discovered model;
  - SELF-SCORING (stt_gate): a new model is scored against the one in use on the same sentences and taken only when
    it is not worse; the verdict survives a restart and a model that lost is not scored again for a month.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-stt-models-")

import stt  # noqa: E402
import stt_gate  # noqa: E402
import stt_models as sm  # noqa: E402

STATE = Path(os.environ["JAVIS_STATE_DIR"])
GATE = {"ok": True, "reason": "not_worse", "current": {}, "candidate": {}}
GATE_CALLS = []


REAL_COMPARE, REAL_CLIPS, REAL_TTS = stt_gate.compare, stt_gate.clips, stt_gate._tts


async def fake_compare(vendor, key, current, candidate):
    GATE_CALLS.append((vendor, current, candidate))
    return dict(GATE)

stt_gate.compare = fake_compare

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


def run(coro):
    return asyncio.run(coro)


check("tests never ask a vendor for its models", os.environ.get(sm.OFF_ENV) == "1")
check("the starting points are the models Javis used before",
      (stt.STT_MODEL_MAC_DINH, stt.OPENAI_STT_MODEL, stt.GEMINI_STT_MODEL)
      == ("whisper-large-v3", "gpt-4o-transcribe", "gemini-2.5-flash"))

# ============================================================
# 1. Ranking on the vendors' own lists
# ============================================================
GROQ = [{"id": "llama-3.3-70b-versatile", "created": 9}, {"id": "whisper-large-v3", "created": 1, "active": True},
        {"id": "whisper-large-v3-turbo", "created": 5, "active": True},
        {"id": "distil-whisper-large-v3-en", "created": 6, "active": True}, {"id": "meta-llama/llama-guard-4-12b"}]
check("Groq today: full-size whisper-large-v3 over the newer turbo and the English-only distil",
      sm.rank_groq(GROQ) == "whisper-large-v3", sm.rank_groq(GROQ))
check("Groq ships whisper-large-v4 -> picked by itself",
      sm.rank_groq(GROQ + [{"id": "whisper-large-v4", "created": 20, "active": True}]) == "whisper-large-v4")
check("a v4 turbo does not push out the full-size v3 (turbo heard Vietnamese worse)",
      sm.rank_groq(GROQ + [{"id": "whisper-large-v4-turbo", "created": 20}]) == "whisper-large-v3")
check("a model Groq switched off is never picked",
      sm.rank_groq(GROQ + [{"id": "whisper-large-v5", "active": False}]) == "whisper-large-v3")
check("only turbo left -> turbo rather than nothing",
      sm.rank_groq([{"id": "whisper-large-v3-turbo"}]) == "whisper-large-v3-turbo")
check("no ear model in the list -> nothing, the default stays", sm.rank_groq([{"id": "llama-3"}]) == "")

OPENAI = [{"id": "gpt-5.1", "created": 30}, {"id": "whisper-1", "created": 1},
          {"id": "gpt-4o-transcribe", "created": 10}, {"id": "gpt-4o-mini-transcribe", "created": 11},
          {"id": "gpt-4o-mini-transcribe-2025-12-15", "created": 25}, {"id": "gpt-4o-transcribe-diarize", "created": 26},
          {"id": "gpt-realtime", "created": 27}, {"id": "gpt-4o-mini-tts", "created": 12}]
check("OpenAI today: gpt-4o-transcribe (full size, not mini, not diarize, not whisper-1)",
      sm.rank_openai(OPENAI) == "gpt-4o-transcribe", sm.rank_openai(OPENAI))
check("OpenAI ships gpt-5-transcribe -> picked by itself",
      sm.rank_openai(OPENAI + [{"id": "gpt-5-transcribe", "created": 40}]) == "gpt-5-transcribe")
check("the undated alias (moved by OpenAI to its newest snapshot) beats a dated snapshot of the same model",
      sm.rank_openai(OPENAI + [{"id": "gpt-4o-transcribe-2026-03-01", "created": 50}]) == "gpt-4o-transcribe")
check("a preview transcribe model is not used",
      sm.rank_openai(OPENAI + [{"id": "gpt-6-transcribe-preview", "created": 60}]) == "gpt-4o-transcribe")
check("only whisper-1 -> whisper-1", sm.rank_openai([{"id": "whisper-1"}]) == "whisper-1")

GEM = [{"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
       {"name": "models/gemini-2.5-pro", "supportedGenerationMethods": ["generateContent"]},
       {"name": "models/gemini-2.5-flash-lite", "supportedGenerationMethods": ["generateContent"]},
       {"name": "models/gemini-3.8-flash-preview-09-2026", "supportedGenerationMethods": ["generateContent"]},
       {"name": "models/gemini-flash-latest", "supportedGenerationMethods": ["generateContent"]},
       {"name": "models/gemini-2.5-flash-preview-tts", "supportedGenerationMethods": ["generateContent"]},
       {"name": "models/gemini-2.0-flash-001", "supportedGenerationMethods": ["generateContent"]},
       {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]}]
check("Gemini today: stable 2.5 flash (preview, lite, latest alias, tts, pro left out)",
      sm.rank_gemini(GEM) == "gemini-2.5-flash", sm.rank_gemini(GEM))
GEM3 = GEM + [{"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"]},
              {"name": "models/gemini-3.8-flash-001", "supportedGenerationMethods": ["generateContent"]}]
check("Google makes 3.8 flash stable -> picked by itself, plain name before the -001 revision",
      sm.rank_gemini(GEM3) == "gemini-3.8-flash", sm.rank_gemini(GEM3))
check("a model that cannot generate content is not picked",
      sm.rank_gemini([{"name": "models/gemini-9-flash", "supportedGenerationMethods": ["embedContent"]}]) == "")

# ============================================================
# 2. best(): never waits, follows the cache, a pin wins
# ============================================================
sm._CACHE.clear()
sm._BAD.clear()
check("nothing known yet -> the default, at once", sm.best("groq", "gsk") == "whisper-large-v3")
check("no key -> the default", sm.best("openai", "") == "gpt-4o-transcribe")
check("a pinned model always wins", sm.best("groq", "gsk", "whisper-large-v3-turbo") == "whisper-large-v3-turbo")


async def no_spawn():
    sm.best("groq", "gsk")
    return len(sm._TASKS)

check("discovery off -> no background call is started", run(no_spawn()) == 0)

LISTS = {"groq": {"data": GROQ + [{"id": "whisper-large-v4", "created": 20}]},
         "openai": {"data": OPENAI + [{"id": "gpt-5-transcribe", "created": 40}]},
         "gemini": {"models": GEM3}}
ASKED = []
STATUS = {"code": 200}


class FakeResponse:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


class FakeClient:
    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None, params=None):
        vendor = "groq" if "groq" in url else "openai" if "openai.com" in url else "gemini"
        ASKED.append((vendor, headers or {}))
        return FakeResponse(STATUS["code"], LISTS[vendor])


_real_client = stt.httpx.AsyncClient
stt.httpx.AsyncClient = FakeClient
try:
    for vendor, want in (("groq", "whisper-large-v4"), ("openai", "gpt-5-transcribe"), ("gemini", "gemini-3.8-flash")):
        got = run(sm.refresh(vendor, "key-" + vendor))
        check(f"{vendor}: the newest ear model is scored against the one in use, then kept", got == want
              and sm.best(vendor, "key-" + vendor) == want and GATE_CALLS[-1] == (vendor, sm.DEFAULTS[vendor], want),
              (got, GATE_CALLS[-1:]))
    check("each vendor is asked with its own key",
          ASKED[0][1].get("Authorization") == "Bearer key-groq" and ASKED[2][1].get("x-goog-api-key") == "key-gemini")
    check("another key of the same vendor uses the model already scored for that vendor (no second scoring)",
          sm.best("groq", "other-key") == "whisper-large-v4")
    check("current() reports the models in use", sm.current().get("openai") == "gpt-5-transcribe")

    STATUS["code"] = 503
    sm._CACHE[("groq", sm._fp("key-groq"))]["next"] = 0
    got = run(sm.refresh("groq", "key-groq"))
    check("the list is down -> the last pick stays", got == "whisper-large-v4" and sm.best("groq", "key-groq")
          == "whisper-large-v4")
    STATUS["code"] = 200

    # ---- the ears really send the discovered model ----
    SENT = []
    REPLY = {}

    class EarClient(FakeClient):
        async def post(self, url, headers=None, data=None, files=None, json=None):
            model = (data or {}).get("model") or url.split("/models/")[-1].split(":")[0]
            SENT.append(model)
            code, body = REPLY.get(model, (200, {"text": "Mở Facebook Ads giúp anh",
                                                 "candidates": [{"content": {"parts": [{"text": "Mở Facebook Ads"}]}}]}))
            return FakeResponse(code, body)

    stt.httpx.AsyncClient = EarClient
    res = run(stt.groq_nghe(b"OggS" + b"\0" * 64, "v.ogg", "key-groq", "", "vi"))
    check("Groq ear sends the discovered whisper-large-v4", SENT[-1:] == ["whisper-large-v4"] and res.get("ok")
          and res.get("model") == "whisper-large-v4", (SENT, res))
    run(stt.openai_nghe(b"OggS" + b"\0" * 64, "v.ogg", "key-openai", "", "vi"))
    check("OpenAI ear sends the discovered gpt-5-transcribe", SENT[-1:] == ["gpt-5-transcribe"], SENT)
    run(stt.gemini_nghe(b"OggS" + b"\0" * 64, "v.ogg", "key-gemini", "", "vi"))
    check("Gemini ear sends the discovered gemini-3.8-flash", SENT[-1:] == ["gemini-3.8-flash"], SENT)
    run(stt.groq_nghe(b"OggS" + b"\0" * 64, "v.ogg", "key-groq", "whisper-large-v3-turbo", "vi"))
    check("the owner's pin (voice.stt_model) is sent as is", SENT[-1:] == ["whisper-large-v3-turbo"], SENT)

    # ---- a new model the vendor refuses ----
    SENT.clear()
    REPLY["whisper-large-v4"] = (400, {"error": {"message": "model does not support this request"}})
    res = run(stt.groq_nghe(b"OggS" + b"\0" * 64, "v.ogg", "key-groq", "", "vi"))
    check("refused new model -> the same sentence is heard by the default",
          SENT == ["whisper-large-v4", "whisper-large-v3"] and res.get("ok") and res.get("model") == "whisper-large-v3",
          (SENT, res))
    check("... and the new model is left aside for a day", sm.best("groq", "key-groq") == "whisper-large-v3"
          and sm.is_bad("groq", "whisper-large-v4"))
    SENT.clear()
    run(stt.groq_nghe(b"OggS" + b"\0" * 64, "v.ogg", "key-groq", "", "vi"))
    check("next sentence goes straight to the default, no wasted call", SENT == ["whisper-large-v3"], SENT)

    SENT.clear()
    REPLY["gpt-5-transcribe"] = (500, {"error": {"message": "down"}})
    REPLY["gpt-4o-transcribe"] = (500, {"error": {"message": "down"}})
    res = run(stt.openai_nghe(b"OggS" + b"\0" * 64, "v.ogg", "key-openai", "", "vi"))
    check("vendor down for every model -> not blamed on the new model, the next ear takes over",
          not res.get("ok") and res.get("ly_do") == "loi" and not sm.is_bad("openai", "gpt-5-transcribe"), (SENT, res))
    SENT.clear()
    REPLY["whisper-large-v3-turbo"] = (400, {"error": {"message": "bad"}})
    run(stt.groq_nghe(b"OggS" + b"\0" * 64, "v.ogg", "key-groq", "whisper-large-v3-turbo", "vi"))
    check("a pinned model that fails is not swapped behind the owner's back", SENT == ["whisper-large-v3-turbo"], SENT)
finally:
    stt.httpx.AsyncClient = _real_client
    sm._CACHE.clear()
    sm._BAD.clear()

# ============================================================
# 3. Self-scoring: a new model is taken only when it is not worse
# ============================================================
# ---- the verdict (pure) ----
same = {"wer": 0.10, "terms": 20, "terms_total": 22, "answered": 13, "clips": 13}
check("not worse (equal) -> the newer model wins", stt_gate.verdict(same, dict(same)) == (True, "not_worse"))
check("a little noise in WER is tolerated", stt_gate.verdict(same, dict(same, wer=0.11))[0] is True)
check("clearly more word errors -> keep the model in use",
      stt_gate.verdict(same, dict(same, wer=0.18)) == (False, "more_word_errors"))
check("two more command terms lost -> keep", stt_gate.verdict(same, dict(same, terms=18)) == (False, "fewer_terms"))
check("the new model fails on several clips -> keep",
      stt_gate.verdict(same, dict(same, answered=9)) == (False, "candidate_fails"))
check("the model in use no longer answers (retired) -> the working one wins",
      stt_gate.verdict(dict(same, answered=0, wer=1.0), same) == (True, "current_fails"))

# ---- scoring real rows: an English-tuned model that translates the English terms loses ----
ITEMS = [{"id": c[0], "text": c[2], "terms": c[3], "data": b"x", "name": c[0] + ".mp3"} for c in stt_gate.SENTENCES]
ANSWERS = {}


async def fake_transcribe_with(vendor, data, name, key, model, lang=None):
    cid = name.split(".")[0]
    text = next(i["text"] for i in ITEMS if i["id"] == cid)
    a = ANSWERS.get(model, {})
    if a == "down":
        return {"ok": False, "ly_do": "loi"}
    return {"ok": True, "text": a.get(cid, text), "model": model}

_real_tw, _real_gap = stt.transcribe_with, dict(stt_gate.GAP_S)
stt.transcribe_with = fake_transcribe_with
stt_gate.GAP_S.update({"groq": 0, "openai": 0, "gemini": 0})


async def fixed_clips():
    return list(ITEMS)

stt_gate.clips = fixed_clips
stt_gate.compare = REAL_COMPARE
gate_mod = stt_gate
try:
    ANSWERS["new-en"] = {"m1": "Mở bảng điều khiển quảng cáo Facebook rồi báo cáo lợi nhuận tuần này",
                         "m3": "Javis ơi kiểm tra hàng tồn kho của sản phẩm bulong",
                         "m4": "Tạo một quy trình mới tên là báo cáo hằng ngày",
                         "m10": "Tăng ngân sách của chiến dịch tiếp thị lại lên hai triệu"}
    r = run(gate_mod.compare("groq", "k", "whisper-large-v3", "new-en"))
    check("a new model that translates the English terms into Vietnamese loses the score",
          r["ok"] is False and r["candidate"]["terms"] < r["current"]["terms"], r)
    ANSWERS["new-good"] = {}
    ANSWERS["whisper-large-v3"] = {"m5": "Kết nối MC của Pancake bót"}
    r = run(gate_mod.compare("groq", "k", "whisper-large-v3", "new-good"))
    check("a new model that hears the terms the old one missed wins",
          r["ok"] is True and r["candidate"]["wer"] < r["current"]["wer"], r)
    ANSWERS["retired"] = "down"
    r = run(gate_mod.compare("groq", "k", "retired", "new-good"))
    check("the model in use answers nothing any more -> the new one wins", r["ok"] is True
          and r["reason"] == "current_fails", r)

    # ---- the clips: made once with the Edge voice, then read from disk ----
    gate_mod.clips = REAL_CLIPS
    TTS = []

    async def fake_tts(text, voice):
        TTS.append(voice)
        return b"ID3" + b"\0" * 2000

    gate_mod._tts = fake_tts
    got = run(gate_mod.clips())
    check("every sentence becomes a clip, English ones read by an English voice",
          len(got) == len(gate_mod.SENTENCES) and TTS.count(gate_mod.EN_VOICE) == 2, (len(got), TTS[:3]))
    check("the clips are kept in the state folder", (STATE / "stt_gate" / "m1.mp3").is_file())
    TTS.clear()
    run(gate_mod.clips())
    check("the second time nothing is synthesised again", TTS == [])

    real = STATE / "stt_bench" / "real"
    real.mkdir(parents=True, exist_ok=True)
    (real / "anh.ogg").write_bytes(b"OggS" + b"\0" * 100)
    (real / "refs.tsv").write_text("# file\tsentence\tterms\nanh.ogg\tMở Zalo OA cho anh\tZalo OA\n", encoding="utf-8")
    got = run(gate_mod.clips())
    check("the owner's own recordings (stt_bench/real/refs.tsv) join the set",
          any(c["id"] == "real:anh.ogg" and c["terms"] == ("Zalo OA",) for c in got), [c["id"] for c in got][-2:])

    for f in (STATE / "stt_gate").glob("*.mp3"):
        f.unlink()

    async def no_tts(text, voice):
        raise OSError("no network")

    gate_mod._tts = no_tts
    check("no Edge voice reachable -> no clips, nothing is decided", run(gate_mod.clips()) == []
          and run(gate_mod.compare("groq", "k", "a", "b"))["ok"] is None)
finally:
    stt.transcribe_with = _real_tw
    stt_gate.clips, stt_gate._tts = REAL_CLIPS, REAL_TTS
    stt_gate.GAP_S.clear()
    stt_gate.GAP_S.update(_real_gap)

# ---- refresh() with the score ----
stt_gate.compare = fake_compare
sm._CACHE.clear()
sm._VERDICTS.clear()
sm._LOADED[0] = False
(STATE / "stt_models.json").unlink(missing_ok=True)   # the verdicts section 2 wrote
LIST = {"data": [{"id": "whisper-large-v3"}, {"id": "whisper-large-v4"}]}


class ListClient(FakeClient):
    async def get(self, url, headers=None, params=None):
        return FakeResponse(200, LIST)

stt.httpx.AsyncClient = ListClient
try:
    GATE.update(ok=False, reason="more_word_errors")
    GATE_CALLS.clear()
    got = run(sm.refresh("groq", "kg"))
    check("new model scored worse -> the model in use stays", got == "whisper-large-v3"
          and sm.best("groq", "kg") == "whisper-large-v3" and len(GATE_CALLS) == 1)
    saved = json.loads((STATE / "stt_models.json").read_text(encoding="utf-8"))
    check("... the verdict is written down with its reason",
          "whisper-large-v4" in saved["groq"]["rejected"] and saved["groq"]["last"]["result"] == "keep"
          and saved["groq"]["last"]["reason"] == "more_word_errors", saved.get("groq"))
    sm._CACHE.clear()
    run(sm.refresh("groq", "kg"))
    check("the model that lost is not scored again (a month)", len(GATE_CALLS) == 1, GATE_CALLS)

    sm._VERDICTS.clear()
    (STATE / "stt_models.json").unlink()
    sm._CACHE.clear()
    GATE.update(ok=True, reason="not_worse")
    got = run(sm.refresh("groq", "kg"))
    check("new model not worse -> switched", got == "whisper-large-v4")
    sm._CACHE.clear()
    sm._VERDICTS.clear()
    sm._LOADED[0] = False
    check("after a restart the scored model is used at once, read from disk",
          sm.best("groq", "kg") == "whisper-large-v4" and sm.accepted("groq") == "whisper-large-v4")
    GATE_CALLS.clear()
    run(sm.refresh("groq", "kg"))
    check("... and the same model is not scored again", GATE_CALLS == [])

    sm._VERDICTS.clear()
    (STATE / "stt_models.json").unlink()
    sm._CACHE.clear()
    GATE.update(ok=None, reason="no_clips")
    got = run(sm.refresh("groq", "kg"))
    slot = sm._CACHE[("groq", sm._fp("kg"))]
    check("nothing could be measured -> the model in use stays, scored again in an hour",
          got == "whisper-large-v3" and slot["next"] - sm.time.time() <= sm.GATE_RETRY + 5)
    LIST["data"] = [{"id": "whisper-large-v4"}]
    sm._CACHE.clear()
    got = run(sm.refresh("groq", "kg"))
    check("nothing measured but the vendor dropped the model in use -> the listed one is taken",
          got == "whisper-large-v4" and sm.accepted("groq") == "whisper-large-v4")
finally:
    stt.httpx.AsyncClient = _real_client
    sm._CACHE.clear()
    sm._VERDICTS.clear()

if _fails:
    print("\nFAIL:", len(_fails), _fails)
    raise SystemExit(1)
print("\nOK - stt_models")
