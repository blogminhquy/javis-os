"""Regression: the DeepSeek provider is wired through every layer, and its thinking mode
cannot break a chat turn.

Wiring: adding a provider touches many separate tables (PROVIDER_DEFS, config defaults, the
encrypted-secret list, _api_stream, _api_stream_mcp, aux_engine, the dashboard KEYFIELD and
MCP_PROVIDERS). Missing one fails silently: the card shows on the Models page but chat falls
through to another provider, or the key is written to disk in plaintext.

Thinking mode is where DeepSeek differs from every other OpenAI-compatible provider here:
  - it is ON by default, so "off" must send `thinking: {type: disabled}` explicitly;
  - with `tools`, every earlier assistant message must carry `reasoning_content`, else 400;
  - a forced tool_choice (named or "required") is a 400 in thinking mode.
The fake server below enforces those three rules the way the DeepSeek docs describe them.

Run:
    .venv/Scripts/python.exe tests/python/test_deepseek_provider.py
"""
import asyncio
import inspect
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-deepseek-test-"))

from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path

import aux_engine  # noqa: E402
import config as cfgmod  # noqa: E402
import engine  # noqa: E402
import main  # noqa: E402
import resonance  # noqa: E402
import vision_input  # noqa: E402

CONSOLE_JS = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")

fails = []


def check(name: str, condition: bool) -> None:
    print(("PASS: " if condition else "FAIL: ") + name)
    if not condition:
        fails.append(name)


# ─────────── 1. Wiring ───────────
_defs = {p["id"]: p for p in main.PROVIDER_DEFS}
check("in PROVIDER_DEFS", "deepseek" in _defs)
_d = _defs.get("deepseek") or {}
check("kind=api", _d.get("kind") == "api")
check("key_field is deepseek_api_key", _d.get("key_field") == "deepseek_api_key")
check("offline default models exist", len(_d.get("default_models") or []) > 0)
check("retired model ids are not offered",
      not {"deepseek-chat", "deepseek-reasoner"} & set(_d.get("default_models") or []))
check("default model is in the offline list", engine.DEEPSEEK_DEFAULT_MODEL in _d.get("default_models", []))

check("config has deepseek_api_key", "deepseek_api_key" in cfgmod._DEFAULT["model"])
check("config has a deepseek catalog", "deepseek" in cfgmod._DEFAULT["model"]["catalog"])
check("key is in the ENCRYPTED list (otherwise it lands on disk in plaintext)",
      "model.deepseek_api_key" in cfgmod._SECRET_PATHS)
check("key is saved/masked through PROVIDER_DEFS", "deepseek_api_key" in main._PROVIDER_KEY_FIELDS)

check("aux_engine treats deepseek as an API provider", "deepseek" in aux_engine.API_PROVIDERS)
check("aux_engine maps the key field", aux_engine._KEY_FIELD.get("deepseek") == "deepseek_api_key")
_ok, _why = aux_engine.availability({"provider": "deepseek"}, {"model": {}})
check("background work without a key says so up front", _ok is False and bool(_why))
_ok, _ = aux_engine.availability({"provider": "deepseek"}, {"model": {"deepseek_api_key": "sk-x"}})
check("background work with a key is available", _ok is True)
check("agents can run on deepseek", "deepseek" in main.AGENT_PROVIDERS)

check("dashboard knows the key field", '"deepseek": "deepseek_api_key"' in CONSOLE_JS)
check("dashboard does not show the 'no tools' banner for deepseek",
      '"groq", "deepseek", "ollama"' in CONSOLE_JS)
check("image input allowed (fallback drops images for text-only models)",
      vision_input.supported("deepseek"))
check("Resonance can set goals on deepseek", resonance.engine_support("deepseek")["goal"] is True)

check("_api_label is human-readable", main._api_label("deepseek") == "DeepSeek")
_cfg = {"model": {}}
main._set_main_model(_cfg, "deepseek", "deepseek-flash")
check("_set_main_model writes engine + main", _cfg["model"]["engine"] == "deepseek"
      and _cfg["model"]["main"] == {"provider": "deepseek", "model": "deepseek-flash"})

# The owner chat path, the bot path and the tool-less path must all name DeepSeek explicitly.
# `_api_stream_mcp`'s last branch is Ollama and `_api_stream_goc`'s is Anthropic: a missing
# branch sends a DeepSeek key and model name to the wrong company.
_DISPATCH = 'if prov == "deepseek":\n'
for _fn in (main._api_stream_mcp, main._bot_stream_co_tool):
    _src = inspect.getsource(_fn)
    _at = _src.find(_DISPATCH)
    check(f"{_fn.__name__} has its own deepseek branch calling deepseek_chat_with_mcp",
          _at >= 0 and _src[_at:_at + 200].find("engine.deepseek_chat_with_mcp(") > 0)
check("_api_stream_mcp discovers hub tools for deepseek",
      '"groq", "deepseek", "ollama", "openai-compat"):\n        try:' in inspect.getsource(main._api_stream_mcp))
_gen = main._api_stream_goc("deepseek", "k", "m", [{"role": "user", "content": "x"}], "off")
check("_api_stream picks the DeepSeek generator", _gen.__qualname__.startswith("deepseek_stream"))

# ─────────── 2. Thinking switch ───────────
check("off sends thinking disabled explicitly (DeepSeek thinks by default)",
      engine._deepseek_thinking("off") == {"thinking": {"type": "disabled"}})
check("empty level counts as off", engine._deepseek_thinking("") == {"thinking": {"type": "disabled"}})
for lvl, want in (("low", "low"), ("medium", "high"), ("high", "high"), ("xhigh", "max"), ("ultra", "max")):
    got = engine._deepseek_thinking(lvl)
    check(f"{lvl} -> thinking enabled, effort {want}",
          got == {"thinking": {"type": "enabled"}, "reasoning_effort": want})


# ─────────── 3. Runs against a fake DeepSeek server ───────────
SEEN = []


def _thinking(body):
    return (body.get("thinking") or {}).get("type", "enabled") == "enabled"


class _Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append({"auth": self.headers.get("Authorization"), "body": body})
        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            chunks = [{"choices": [{"delta": {"reasoning_content": "hmm"}}]}] if _thinking(body) else []
            chunks += [{"choices": [{"delta": {"content": ch}}]} for ch in ("Xin ", "chào ", "từ DeepSeek")]
            for c in chunks:
                self.wfile.write(b"data: " + json.dumps(c).encode() + b"\n\n")
            self.wfile.write(b"data: [DONE]\n\n")
            return
        has_tools = bool(body.get("tools"))
        if _thinking(body) and has_tools:
            if body.get("tool_choice") not in (None, "auto", "none"):
                return self._json(400, {"error": {"message": "tool_choice is not supported in thinking mode"}})
            if any(m.get("role") == "assistant" and not m.get("reasoning_content") for m in body["messages"]):
                return self._json(400, {"error": {"message":
                                  "The reasoning_content in the thinking mode must be passed back to the API."}})
        first = has_tools and not any(m.get("role") == "tool" for m in body["messages"])
        msg = ({"role": "assistant", "content": "",
                "tool_calls": [{"id": "c1", "type": "function",
                                "function": {"name": "javis_connections", "arguments": "{}"}}]}
               if first else {"role": "assistant", "content": "Đã gọi tool xong"})
        if _thinking(body):
            msg["reasoning_content"] = "nghĩ một chút"
        self._json(200, {"choices": [{"message": msg, "finish_reason": "tool_calls" if first else "stop"}],
                         "usage": {"prompt_tokens": 10, "completion_tokens": 5}})


_srv = HTTPServer(("127.0.0.1", 0), _Fake)
threading.Thread(target=_srv.serve_forever, daemon=True).start()
engine.DEEPSEEK_URL = f"http://127.0.0.1:{_srv.server_address[1]}/chat/completions"

TOOLS = [{"fn": "javis_connections", "server": "javis", "name": "javis_connections",
          "description": "liệt kê nguồn", "schema": {"type": "object", "properties": {}, "required": []}}]


async def _call(_args):
    return "Kết nối: POS, Lịch"


ROUTE = {"javis_connections": {"call": _call}}


async def _collect(gen):
    evs = []
    async for ev in gen:
        evs.append(ev)
    return evs


def _text(evs):
    return "".join(e.get("content", "") for e in evs if e["type"] == "text")


async def _run():
    # Plain stream, thinking off: answer only, explicit disabled switch, no effort field.
    SEEN.clear()
    evs = await _collect(engine.deepseek_stream("sk-test", "deepseek-flash",
                                                [{"role": "user", "content": "chào"}], "off"))
    check(f"plain stream yields the answer (got {_text(evs)!r})", _text(evs) == "Xin chào từ DeepSeek")
    b = SEEN[0]["body"]
    check("plain stream off: thinking disabled, no reasoning_effort",
          b.get("thinking") == {"type": "disabled"} and "reasoning_effort" not in b)
    check("key goes in a Bearer header", SEEN[0]["auth"] == "Bearer sk-test")

    # Plain stream, thinking on: reasoning_content is NOT leaked into the answer.
    SEEN.clear()
    evs = await _collect(engine.deepseek_stream("sk-test", "deepseek-flash",
                                                [{"role": "user", "content": "chào"}], "high"))
    check("thinking stream hides reasoning_content", _text(evs) == "Xin chào từ DeepSeek")
    check("thinking stream sends enabled + effort",
          SEEN[0]["body"].get("thinking") == {"type": "enabled"}
          and SEEN[0]["body"].get("reasoning_effort") == "high")

    # Tool loop, thinking off.
    SEEN.clear()
    evs = await _collect(engine.deepseek_chat_with_mcp("sk-test", "deepseek-flash",
                                                       [{"role": "user", "content": "có nguồn nào"}],
                                                       "off", TOOLS, ROUTE))
    check("tool loop off: tool called", [e.get("name") for e in evs if e["type"] == "tool_call"]
          == ["javis_connections"])
    check("tool loop off: final text", _text(evs) == "Đã gọi tool xong")
    check("tool loop off: EVERY request says thinking disabled",
          len(SEEN) == 2 and all(s["body"].get("thinking") == {"type": "disabled"} for s in SEEN))

    # Tool loop, thinking on, fresh conversation: reasoning_content must be passed back.
    SEEN.clear()
    evs = await _collect(engine.deepseek_chat_with_mcp("sk-test", "deepseek-v4-pro",
                                                       [{"role": "user", "content": "có nguồn nào"}],
                                                       "high", TOOLS, ROUTE))
    check("tool loop thinking: no error", not [e for e in evs if e["type"] == "error"])
    check("tool loop thinking: final text", _text(evs) == "Đã gọi tool xong")
    check("tool loop thinking: stayed in thinking mode (2 requests, no fallback)",
          len(SEEN) == 2 and all(_thinking(s["body"]) for s in SEEN))
    asst = [m for m in SEEN[1]["body"]["messages"] if m.get("role") == "assistant"]
    check("tool loop thinking: assistant tool-call message carries reasoning_content back",
          asst and asst[-1].get("reasoning_content") == "nghĩ một chút")

    # Tool loop, thinking on, history from an earlier turn has no reasoning_content (Javis
    # never stored it). DeepSeek says 400; Javis must drop to normal mode, not fail the turn.
    SEEN.clear()
    history = [{"role": "user", "content": "chào"}, {"role": "assistant", "content": "Chào anh"},
               {"role": "user", "content": "có nguồn nào"}]
    evs = await _collect(engine.deepseek_chat_with_mcp("sk-test", "deepseek-flash", history,
                                                       "high", TOOLS, ROUTE))
    check("old history: no error event", not [e for e in evs if e["type"] == "error"])
    check("old history: says it switched to normal mode",
          any(e.get("name") == "javis_thinking_off" for e in evs if e["type"] == "tool_call"))
    check("old history: still answers with the tool result", _text(evs) == "Đã gọi tool xong")
    check("old history: requests after the 400 have thinking disabled",
          all(s["body"].get("thinking") == {"type": "disabled"} for s in SEEN[1:]))
    check("old history: caller's history is not mutated", history[1] == {"role": "assistant", "content": "Chào anh"})

    # A turn that must force a tool runs with thinking off from the start.
    SEEN.clear()
    evs = await _collect(engine.deepseek_chat_with_mcp(
        "sk-test", "deepseek-flash", [{"role": "user", "content": "kiểm tra doanh thu hôm nay trên POS"}],
        "high", TOOLS, ROUTE))
    check("forced tool: first request already has thinking off + tool_choice",
          SEEN and SEEN[0]["body"].get("thinking") == {"type": "disabled"}
          and SEEN[0]["body"].get("tool_choice") is not None)
    check("forced tool: no error", not [e for e in evs if e["type"] == "error"])

    # Single forced-tool planner: thinking off regardless of the user's level.
    SEEN.clear()
    spec = {"type": "function", "function": {"name": "javis_connections", "description": "x",
                                             "parameters": {"type": "object", "properties": {}}}}
    res = await engine.single_tool_plan("deepseek", "sk-test", "deepseek-flash",
                                        [{"role": "user", "content": "x"}], "high", spec)
    check(f"single_tool_plan works on deepseek (status {res.get('status')!r})", res.get("status") == "ok")
    check("single_tool_plan sends thinking disabled",
          SEEN and SEEN[0]["body"].get("thinking") == {"type": "disabled"}
          and "reasoning_effort" not in SEEN[0]["body"])


asyncio.run(_run())

if fails:
    raise SystemExit(f"\nFAIL - test_deepseek_provider: {len(fails)} lỗi")
print("\nOK - test_deepseek_provider: tất cả pass")
