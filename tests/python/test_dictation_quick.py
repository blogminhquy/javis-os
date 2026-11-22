"""Stop gives the text back at once when a speech model heard it (2026-11-22).

    python tests/run.py dictation_quick

Owner, 2026-11-22: "chức năng viết lại lời của Javis đang bị quá chậm", ChatGPT and Claude transcribe with their own
model and are fast on stop. No network: the models are fakes. Pins:
  - `quick` (the ear heard the text) never starts the main brain's subscription CLI;
  - with no model that answers in a second, `quick` gives the word rules back at once;
  - a main brain on an API key still polishes in `quick`, and so does the quick API key;
  - without `quick` (the browser's own words) the CLI stays the last resort, as before;
  - POST /stt/fix passes `quick` on;
  - a Gemini key is an ear of the dashboard mic: after the others, first for a Gemini main brain, heard by gemini_nghe.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-dictation-quick-"))

import main  # noqa: E402
import stt  # noqa: E402
import transcript_fix  # noqa: E402
import voice_ear  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app, base_url="http://127.0.0.1")
_fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  ({extra})" if extra and not cond else ""))
    if not cond:
        _fails.append(name)


CLI = {"model": {"main": {"provider": "anthropic-cli"}}}
CLI_GROQ = {"model": {"main": {"provider": "anthropic-cli"}, "groq_api_key": "gsk"}}
API = {"model": {"main": {"provider": "openrouter", "model": "x"}, "openrouter_key": "or"}}
HEARD = "anh kiểm tra giúp em cái phần chép lời trên điện thoại nhé"

real_ask, real_quick = transcript_fix._ASK, transcript_fix._ask_quick_api
calls = []


async def fake_main(prompt):
    calls.append("main")
    return "Anh kiểm tra giúp em cái phần chép lời trên điện thoại nhé."


async def fake_quick(pick, prompt, sentence):
    calls.append(pick[0])
    return "Anh kiểm tra giúp em cái phần chép lời trên điện thoại nhé!"


transcript_fix._ASK = fake_main
transcript_fix._ask_quick_api = fake_quick


def rewrite(cfg, quick):
    transcript_fix._rewrite_cache.clear()
    calls.clear()
    return asyncio.run(transcript_fix.rewrite_transcript(cfg, HEARD, ["ngữ cảnh"], quick=quick))


try:
    # ---- the order of the tries ----
    check("quick, CLI main brain, no key: nothing to ask", transcript_fix.rewrite_tries(CLI, quick=True) == [])
    check("quick, CLI main brain, Groq key: only Groq", transcript_fix.rewrite_tries(CLI_GROQ, quick=True) == ["groq"])
    check("quick, main brain on an API key: the main brain still polishes",
          transcript_fix.rewrite_tries(API, quick=True)[0] == "main")
    check("not quick, CLI main brain, Groq key: Groq, then the CLI as before",
          transcript_fix.rewrite_tries(CLI_GROQ) == ["groq", "main"])
    check("not quick, CLI main brain, no key: the CLI", transcript_fix.rewrite_tries(CLI) == ["main"])

    # ---- what really runs ----
    res = rewrite(CLI, quick=True)
    check("quick with only a CLI: the CLI is never started", calls == [], calls)
    check("... and the words come back as heard, by the rules", res["source"] == "rules" and not res["ai"]
          and res["text"].startswith("anh kiểm tra"), res)
    res = rewrite(CLI_GROQ, quick=True)
    check("quick with a Groq key: Groq polishes, the CLI is not asked", calls == ["groq"] and res["source"] == "groq",
          calls)
    res = rewrite(CLI, quick=False)
    check("the browser's own words: the CLI rewrites them, as before", calls == ["main"] and res["source"] == "main",
          calls)

    # ---- POST /stt/fix passes `quick` on ----
    seen = {}
    real_rewrite = transcript_fix.rewrite_transcript

    async def spy(cfg, text, ctx, quick=False):
        seen["quick"] = quick
        return {"text": text, "source": "rules", "ai": False}

    transcript_fix.rewrite_transcript = spy
    try:
        client.post("/stt/fix", json={"text": "xin chào", "final": True, "quick": True, "context": []})
        check("/stt/fix: quick true reaches the rewrite", seen.get("quick") is True, seen)
        client.post("/stt/fix", json={"text": "xin chào", "final": True, "context": []})
        check("/stt/fix: a page from before (no quick) gets the full rewrite", seen.get("quick") is False, seen)
    finally:
        transcript_fix.rewrite_transcript = real_rewrite
finally:
    transcript_fix._ASK, transcript_fix._ask_quick_api = real_ask, real_quick

# ---- the Gemini ear ----
GEM = {"gemini_api_key": "AIza"}
GPT = {"openai_oauth": {"access_token": "tok"}}


def cfg(*parts):
    m = {}
    for p in parts:
        m.update(p)
    return {"model": m, "voice": {}}


check("a Gemini key is an ear of the dashboard mic", voice_ear.availability(cfg(GEM)).get("gemini") is True)
r = voice_ear.select_ear(cfg(GEM), "anthropic-cli")
check("only a Gemini key: the Gemini ear, upload kind", r["provider"] == "gemini" and r["kind"] == "upload", r)
r = voice_ear.select_ear(cfg(GEM, GPT), "anthropic-cli")
check("Gemini comes after the ChatGPT plan", r["provider"] == "chatgpt" and r["fallbacks"] == ["gemini"], r)
r = voice_ear.select_ear(cfg(GEM, GPT), "gemini")
check("a Gemini main brain hears with its own model first", r["provider"] == "gemini"
      and r["reason"] == voice_ear.REASON_SAME_VENDOR, r)
check("'gemini' is not a settings choice: auto picks it", "gemini" not in voice_ear.CHOICES)

sent = {}


async def fake_gemini(data, ten_file, api_key, model="", ngon_ngu=None, hotwords=""):
    sent.update(key=api_key, lang=ngon_ngu, hotwords=hotwords)
    return {"ok": True, "text": "mở trang Models giúp anh", "model": "gemini"}


real_gemini = stt.gemini_nghe
stt.gemini_nghe = fake_gemini
try:
    out = asyncio.run(voice_ear.transcribe_upload(cfg(GEM), b"x" * 3000, "voice.webm", "auto", "", provider="gemini"))
    check("the Gemini ear hears the upload with the Gemini key", out.get("ok") and sent.get("key") == "AIza"
          and out.get("text") == "mở trang Models giúp anh", (out, sent))
    check("... with the vocabulary hint, the language left to the model", sent.get("lang") == ""
          and "Javis" in (sent.get("hotwords") or ""), sent)
finally:
    stt.gemini_nghe = real_gemini

if _fails:
    print(f"\nFAIL - test_dictation_quick: {len(_fails)}")
    raise SystemExit(1)
print("\nOK - test_dictation_quick: all pass")
