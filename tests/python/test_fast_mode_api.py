"""Fast mode on the API brains (0.164.0): the right parameter per provider when the bolt is on,
nothing when it is off, and one retry without it when the provider refuses.

    python tests/run.py fast_mode_api

No network: engine.httpx.AsyncClient is replaced by a fake that records every request.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
# 0.438.5: vòng tool mặc định gọi model dạng stream. File này thử logic vòng tool trên đường non-stream
# (giả lập client.post / máy chủ trả JSON), đường đó vẫn là đường lui. Đường stream: test_api_stream_vong.py.
os.environ["JAVIS_API_STREAM_TOOLS"] = "0"
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-fastapi-"))
import engine  # noqa: E402
import fast_mode  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


class _Resp:
    def __init__(self, status, body="", data=None, lines=None):
        self.status_code = status
        self.text = body
        self._data = data
        self._lines = lines or []
        self.headers = {}

    async def aread(self):
        return self.text.encode("utf-8")

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    def json(self):
        return self._data if self._data is not None else json.loads(self.text or "{}")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _Client:
    """Fake httpx.AsyncClient: pops one scripted response per request and records the request."""
    queue = []
    sent = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def stream(self, method, url, headers=None, json=None, **k):
        _Client.sent.append({"url": url, "headers": dict(headers or {}), "json": dict(json or {})})
        return _Client.queue.pop(0)

    async def post(self, url, headers=None, json=None, **k):
        _Client.sent.append({"url": url, "headers": dict(headers or {}), "json": dict(json or {})})
        return _Client.queue.pop(0)


engine.httpx.AsyncClient = _Client


async def _drain(gen):
    out = []
    async for ev in gen:
        out.append(ev)
    return out


def run(gen_factory, responses, on):
    _Client.queue = list(responses)
    _Client.sent = []
    tok = fast_mode.use(on)
    try:
        events = asyncio.run(_drain(gen_factory()))
    finally:
        fast_mode.CURRENT.reset(tok)
    return events, list(_Client.sent)


MSG = [{"role": "user", "content": "hi"}]
SSE_DONE = ["data: [DONE]"]

# 1. Anthropic API (no tools): beta header + speed when on; refusal retries without them.
ev, sent = run(lambda: engine.anthropic_stream("k", "claude-opus-5-5", MSG),
               [_Resp(400, "This model does not support the `speed` parameter."), _Resp(200, lines=[])], True)
check("Anthropic: first request carries speed and the beta header",
      sent and sent[0]["json"].get("speed") == "fast" and sent[0]["headers"].get("anthropic-beta") == fast_mode.ANTHROPIC_BETA, sent[:1])
check("Anthropic: refused, so one retry without speed and without the beta header",
      len(sent) == 2 and "speed" not in sent[1]["json"] and "anthropic-beta" not in sent[1]["headers"], sent)
check("Anthropic: the refusal is not shown as an error", not any(e.get("type") == "_fast_refused" for e in ev))
check("Anthropic: the fallback is remembered for the tooltip", fast_mode.states().get("anthropic-api", {}).get("state") == "fallback")
ev, sent = run(lambda: engine.anthropic_stream("k", "claude-opus-5-5", MSG), [_Resp(200, lines=[])], False)
check("Anthropic: bolt off sends neither", len(sent) == 1 and "speed" not in sent[0]["json"] and "anthropic-beta" not in sent[0]["headers"])
ev, sent = run(lambda: engine.anthropic_stream("k", "claude-sonnet-5-5", MSG), [_Resp(200, lines=[])], True)
check("Anthropic: unsupported model sends neither", "speed" not in sent[0]["json"])

ev, sent = run(lambda: engine.anthropic_stream("k", "", MSG), [_Resp(200, lines=[])], True)
check("Anthropic: empty model falls back to Sonnet, so no speed is sent", "speed" not in sent[0]["json"], sent[0]["json"].get("model"))

# 2. OpenAI-compatible streams.
ev, sent = run(lambda: engine.openai_stream("k", "gpt-6-sol", MSG),
               [_Resp(400, '{"error": {"message": "Unsupported value: service_tier"}}'), _Resp(200, lines=SSE_DONE)], True)
check("OpenAI: service_tier fast, then one retry without it after a refusal",
      sent[0]["json"].get("service_tier") == "fast" and len(sent) == 2 and "service_tier" not in sent[1]["json"], sent)
ev, sent = run(lambda: engine.gemini_stream("k", "gemini-4-argon", MSG), [_Resp(200, lines=SSE_DONE)], True)
check("Gemini: service_tier priority", sent[0]["json"].get("service_tier") == "priority", sent)
ev, sent = run(lambda: engine.openrouter_stream("k", "openai/gpt-6", MSG), [_Resp(200, lines=SSE_DONE)], True)
check("OpenRouter: service_tier priority", sent[0]["json"].get("service_tier") == "priority", sent)
ev, sent = run(lambda: engine.openai_stream("k", "gpt-6-sol", MSG), [_Resp(200, lines=SSE_DONE)], False)
check("OpenAI: bolt off sends no service_tier", "service_tier" not in sent[0]["json"])
ev, sent = run(lambda: engine.groq_stream("k", "llama", MSG), [_Resp(200, lines=SSE_DONE)], True)
check("Groq has no Fast mode: nothing sent", "service_tier" not in sent[0]["json"])

# 3. ChatGPT OAuth (Responses API).
ev, sent = run(lambda: engine.openai_responses_stream("tok", "acc", "gpt-6.1-sol", MSG),
               [_Resp(400, "service_tier not allowed for this account"), _Resp(200, lines=[])], True)
check("ChatGPT OAuth: service_tier priority, retry without after a refusal",
      sent[0]["json"].get("service_tier") == "priority" and len(sent) == 2 and "service_tier" not in sent[1]["json"], sent)

# 4. Tool loops (non-streaming rounds).
ANTH_OK = {"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn", "usage": {"input_tokens": 1, "output_tokens": 1}}
ev, sent = run(lambda: engine.anthropic_chat_with_mcp("k", "claude-opus-4-8", MSG, "off", [], {}),
               [_Resp(400, "does not support the `speed` parameter"), _Resp(200, data=ANTH_OK)], True)
check("Anthropic tool loop: speed first, retry without after a refusal",
      sent[0]["json"].get("speed") == "fast" and len(sent) == 2 and "speed" not in sent[1]["json"]
      and "anthropic-beta" not in sent[1]["headers"], sent)
CC_OK = {"choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}], "usage": {}}
ev, sent = run(lambda: engine.openai_chat_with_mcp("k", "gpt-6-sol", MSG, "off", [], {}),
               [_Resp(400, "invalid service_tier"), _Resp(200, data=CC_OK)], True)
check("OpenAI tool loop: service_tier fast, retry without after a refusal",
      sent[0]["json"].get("service_tier") == "fast" and len(sent) == 2 and "service_tier" not in sent[1]["json"], sent)
fast_mode.remember("openai", "fallback", "old")
ev, sent = run(lambda: engine.openai_chat_with_mcp("k", "gpt-6-sol", MSG, "off", [], {}), [_Resp(200, data=CC_OK)], True)
check("a successful fast round in a tool loop records 'on', clearing an old fallback",
      fast_mode.states().get("openai", {}).get("state") == "on", fast_mode.states())
fast_mode.remember("anthropic-api", "fallback", "old")
ev, sent = run(lambda: engine.anthropic_chat_with_mcp("k", "claude-opus-4-8", MSG, "off", [], {}), [_Resp(200, data=ANTH_OK)], True)
check("Anthropic tool loop success records 'on'", fast_mode.states().get("anthropic-api", {}).get("state") == "on", fast_mode.states())
ev, sent = run(lambda: engine.gemini_chat_with_mcp("k", "gemini-4-argon", MSG, "off", [], {}), [_Resp(200, data=CC_OK)], True)
check("Gemini tool loop: service_tier priority", sent[0]["json"].get("service_tier") == "priority", sent)
ev, sent = run(lambda: engine.responses_with_mcp("tok", "acc", "gpt-6.1-sol", MSG, "off", [], {}),
               [_Resp(400, "service_tier rejected"), _Resp(200, lines=[])], True)
check("ChatGPT OAuth tool loop: service_tier priority, retry without after a refusal",
      sent[0]["json"].get("service_tier") == "priority" and len(sent) >= 2 and "service_tier" not in sent[1]["json"], sent)

if fails:
    print("\nFAIL - test_fast_mode_api: %d" % len(fails))
    sys.exit(1)
print("\nOK - test_fast_mode_api: all pass")
