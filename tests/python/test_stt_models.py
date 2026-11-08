"""Each vendor's newest speech-to-text model is picked by asking the vendor, not by a name in the code (2026-11-08).

    python tests/run.py stt_models      (no network: the vendors' model lists are faked)

Owner: "pick the vendor's best Whisper by itself when they upgrade, no hand update in Javis". Locks:
  - the ranking per vendor on realistic lists: newest full-size model, never English-only, preview, diarize or lite;
  - a sentence never waits for the list (the default is used, the list is fetched in the background);
  - discovery is off in tests (JAVIS_NO_STT_MODEL_DISCOVERY) and a pinned model always wins;
  - a discovered model the vendor refuses is retried with the default, then left aside for a day;
  - Groq, OpenAI and Gemini ears really send the discovered model.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os

import stt  # noqa: E402
import stt_models as sm  # noqa: E402

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
        check(f"{vendor}: the list is read and the newest ear model kept", got == want
              and sm.best(vendor, "key-" + vendor) == want, got)
    check("each vendor is asked with its own key",
          ASKED[0][1].get("Authorization") == "Bearer key-groq" and ASKED[2][1].get("x-goog-api-key") == "key-gemini")
    check("another key is another account: its own answer",
          sm.best("groq", "other-key") == "whisper-large-v3")
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

if _fails:
    print("\nFAIL:", len(_fails), _fails)
    raise SystemExit(1)
print("\nOK - stt_models")
