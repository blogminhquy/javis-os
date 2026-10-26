"""A model overloaded on the provider's side reads as such, and Javis waits long enough between tries (0.335.0).

    python tests/run.py provider_overload      (no network)

Owner report 26/10/2026: a chat pinned to Gemini 3.8 Flash showed a raw block
`Gemini 503: [{"error": {"code": 503, "message": "This model is currently experiencing high demand...` after three
tries spent in a few seconds. The fault is Google's (the model was overloaded), but the owner could not tell that, nor
what to do next.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-overload-")

import engine  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:300] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


GEMINI_503 = ('[{\n  "error": {\n    "code": 503,\n    "message": "This model is currently experiencing high demand. '
              'Spikes in demand are usually temporary. Please try again later.",\n    "status": "UNAVAILABLE"\n  }\n}\n]')
check("Gemini's list-wrapped JSON gives its sentence",
      engine.provider_message(GEMINI_503).startswith("This model is currently experiencing high demand"))
check("OpenAI/Anthropic shape error.message",
      engine.provider_message('{"type":"error","error":{"type":"overloaded_error","message":"Overloaded"}}')
      == "Overloaded (overloaded_error)")
check("a bare message key", engine.provider_message('{"message":"Bad key"}') == "Bad key")
check("plain text and broken JSON pass through", engine.provider_message("upstream timeout") == "upstream timeout"
      and engine.provider_message("{not json") == "{not json")

ev = engine.ev_loi_http("Gemini", 503, GEMINI_503)
check("the chat line is the sentence plus Google's code, not the JSON block",
      ev["content"].startswith("Gemini 503: This model is currently") and ev["content"].endswith("(UNAVAILABLE)")
      and "{" not in ev["content"], ev["content"])
check("still marked for a retry", ev.get("tam_thoi") and ev.get("ma") == 503)

WAITS = []
engine._jittered_backoff = lambda attempt, **kw: (WAITS.append(kw), 0.001)[1]


def run(make):
    async def go():
        return [e async for e in engine.thu_lai_khi_tam_thoi(make, so_lan=3, nhan="Gemini")]
    return asyncio.run(go())


CALLS = []


async def always_503():
    CALLS.append(1)
    yield engine.ev_loi_http("Gemini", 503, GEMINI_503)

out = run(always_503)
last = out[-1] if out else {}
check("three tries, then one final error", len(CALLS) == 3 and len(out) == 1 and last.get("type") == "error",
      (CALLS, out))
check("an overload waits seconds between tries, not one", all(w.get("base") == 4.0 for w in WAITS), WAITS)
check("the final line says it is the provider's overload and what to do",
      ("quá tải phía nhà cung cấp" in last.get("content", "") or "overloaded on the provider" in last.get("content", ""))
      and ("chip model" in last.get("content", "") or "model chip" in last.get("content", "")), last.get("content"))
check("and keeps the try count", "3" in last.get("content", ""))

WAITS.clear()


async def bad_request():
    yield engine.ev_loi_http("Gemini", 400, '{"error":{"message":"API key not valid"}}')

out = run(bad_request)
check("a real error is not retried and not called an overload", not WAITS and len(out) == 1
      and "quá tải" not in out[0]["content"] and "overloaded" not in out[0]["content"]
      and out[0]["content"] == "Gemini 400: API key not valid", out)

check("no em dash in this file", chr(0x2014) not in open(__file__, encoding="utf-8").read())
if fails:
    print(f"\nFAIL - test_provider_overload: {len(fails)}: " + "; ".join(fails))
    raise SystemExit(1)
print("\nOK - test_provider_overload: all pass")
