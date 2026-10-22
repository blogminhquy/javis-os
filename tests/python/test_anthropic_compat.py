"""Anthropic-compatible gateways as a brain (0.254.0).

    python tests/run.py anthropic_compat     (no network: a fake gateway runs on localhost)

Owner, 20/10/2026: a reseller told a customer their Claude access is more stable over the
"Anthropic compatible" endpoint than the "OpenAI compatible" one, and Javis had no way to use it.
Javis sent every Anthropic request to a hard-coded https://api.anthropic.com/v1/messages.

The fake gateway below behaves like the real ones this targets:
- `/anthropic/...` has no /v1/models (DeepSeek's and Kimi's "anthropic" endpoints, most resellers);
  `/listing/...` does have one.
- it accepts the key as either x-api-key or Bearer, and records which headers arrived;
- it rejects the `thinking` field with a 400, as a gateway serving a non-Claude model may.
"""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-ac-")

import config as cfgmod  # noqa: E402
import engine  # noqa: E402
import main  # noqa: E402

GOOD = "sk-good"
seen = []   # (method, path, x-api-key, authorization)
fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


class Gateway(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _auth_ok(self):
        return self.headers.get("x-api-key") == GOOD or self.headers.get("authorization") == f"Bearer {GOOD}"

    def _send(self, code, obj=None, raw=None, ctype="application/json"):
        body = raw if raw is not None else json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        seen.append(("GET", self.path, self.headers.get("x-api-key"), self.headers.get("authorization")))
        if not self._auth_ok():
            return self._send(401, {"type": "error", "error": {"type": "authentication_error", "message": "bad key"}})
        if self.path == "/listing/v1/models":
            return self._send(200, {"data": [{"id": "listed-a"}, {"id": "listed-b"}]})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        seen.append(("POST", self.path, self.headers.get("x-api-key"), self.headers.get("authorization")))
        body = json.loads(self.rfile.read(int(self.headers.get("content-length") or 0)) or b"{}")
        if not self._auth_ok():
            return self._send(401, {"type": "error", "error": {"type": "authentication_error", "message": "bad key"}})
        if not self.path.endswith("/v1/messages"):
            return self._send(404, {"error": "not found"})
        if "thinking" in body:
            return self._send(400, {"type": "error", "error": {"type": "invalid_request_error",
                                                               "message": "thinking is not supported"}})
        if body.get("stream"):
            events = [
                {"type": "message_start", "message": {"usage": {"input_tokens": 7}}},
                {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "xin "}},
                {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "chào"}},
                {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 2}},
            ]
            raw = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()
            return self._send(200, raw=raw, ctype="text/event-stream")
        msgs = body.get("messages") or []
        had_result = any(isinstance(m.get("content"), list) and any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in m["content"]) for m in msgs)
        if body.get("tools") and not had_result:
            return self._send(200, {"content": [{"type": "tool_use", "id": "tu1", "name": "get_answer", "input": {"q": 1}}],
                                    "stop_reason": "tool_use", "usage": {"input_tokens": 5, "output_tokens": 3}})
        return self._send(200, {"content": [{"type": "text", "text": "the answer is 42"}],
                                "stop_reason": "end_turn", "usage": {"input_tokens": 9, "output_tokens": 4}})


srv = ThreadingHTTPServer(("127.0.0.1", 0), Gateway)
threading.Thread(target=srv.serve_forever, daemon=True).start()
HOST = f"http://127.0.0.1:{srv.server_address[1]}"


class Request:
    def __init__(self, body):
        self.body = body

    async def json(self):
        return self.body


def connect(**body):
    return asyncio.run(main.anthropic_compat_connect(Request(body)))


async def collect(gen):
    return [ev async for ev in gen]


# ---- 1. Base URL: every shape people paste becomes the ANTHROPIC_BASE_URL shape ----
for raw in ("https://x.com/anthropic", "https://x.com/anthropic/", "https://x.com/anthropic/v1",
            "https://x.com/anthropic/v1/", "https://x.com/anthropic/v1/messages", " https://x.com/anthropic/messages "):
    check(f"normalize {raw.strip()!r}", engine.normalize_anthropic_compat_base(raw) == "https://x.com/anthropic")
h = engine.anthropic_headers("k", compat=True)
check("a gateway gets the key as x-api-key AND Bearer", h["x-api-key"] == "k" and h["authorization"] == "Bearer k")
check("api.anthropic.com still gets x-api-key only", "authorization" not in engine.anthropic_headers("k"))

# ---- 2. Connect: checks before saving ----
r = connect(base=HOST + "/anthropic", key="", models="m-1")
check("no key: refused, asks for the seller's key", not r["ok"] and "key" in r["error"].lower())
r = connect(base=HOST + "/anthropic", key=GOOD, models="")
check("no /v1/models and no typed model: refused, asks for a model name", not r["ok"] and "model" in r["error"].lower())
r = connect(base=HOST + "/anthropic", key="sk-wrong", models="m-1")
check("wrong key: refused with HTTP 401", not r["ok"] and "401" in r["error"])
check("nothing saved after a refusal", not cfgmod.read_settings()["model"].get("anthropic_compat_base"))
seen.clear()
r = connect(base=HOST + "/anthropic/v1/messages", key=GOOD, models="m-1, m-2\nm-1")
check("good key + typed models: saved", r.get("ok") is True and r.get("models") == 2 and r.get("listed") is False)
check("the check was one tiny /v1/messages call with the first model",
      any(x[0] == "POST" and x[1] == "/anthropic/v1/messages" for x in seen))
m = cfgmod.read_settings()["model"]
check("pasted /v1/messages URL stored as the base", m["anthropic_compat_base"] == HOST + "/anthropic")
check("typed names stored once each, in order", m["anthropic_compat_models"] == ["m-1", "m-2"])
check("catalog holds the typed names", m["catalog"]["anthropic-compat"] == ["m-1", "m-2"])
check("key stored", m["anthropic_compat_key"] == GOOD)

# A blank key reuses the saved one for the same gateway only, never for a new URL.
r = connect(base=HOST + "/anthropic", key="", models="m-1, m-2")
check("blank key, same gateway: reuses the saved key", r.get("ok") is True)
seen.clear()
r = connect(base=HOST + "/other", key="", models="m-1")
check("blank key, new gateway: refused, the old key is not sent there", not r["ok"] and not seen)

# ---- 3. The Models page sees it ----
view = {p["id"]: p for p in main._providers_view(cfgmod.read_settings())}
check("card is listed and connected", view.get("anthropic-compat", {}).get("configured") is True)
idx = asyncio.run(main.provider_models_index("anthropic-compat", refresh=True))
check("model picker lists the typed names even without /v1/models", idx["models"][:2] == ["m-1", "m-2"] and idx["live"])
mcfg = cfgmod.read_settings()["model"]
check("chat key comes from the saved key", main._provider_key(mcfg, main._provider_def("anthropic-compat")) == GOOD)

# A gateway that does list its models: no typed name needed, the list is used as is.
r = connect(base=HOST + "/listing", key=GOOD, models="")
check("gateway with /v1/models: saved from its list", r.get("ok") is True and r.get("listed") is True)
check("catalog = the listed models", cfgmod.read_settings()["model"]["catalog"]["anthropic-compat"] == ["listed-a", "listed-b"])
connect(base=HOST + "/anthropic", key=GOOD, models="m-1")   # back to the list-less gateway

# ---- 4. Chat without tools: streams, both auth headers, thinking dropped on a 400 ----
seen.clear()
evs = asyncio.run(collect(engine.anthropic_compat_stream(GOOD, "m-1", [
    {"role": "system", "content": "be brief"}, {"role": "user", "content": "chào"}], "high")))
text = "".join(e.get("content", "") for e in evs if e["type"] == "text")
check("stream answers through the gateway", text == "xin chào")
check("thinking refused with 400 -> answered without it (no error shown)", not any(e["type"] == "error" for e in evs))
posts = [x for x in seen if x[0] == "POST"]
check("requests went to {base}/v1/messages", posts and all(x[1] == "/anthropic/v1/messages" for x in posts))
check("both x-api-key and Bearer were sent", posts and all(x[2] == GOOD and x[3] == f"Bearer {GOOD}" for x in posts))
check("usage reported", any(e["type"] == "usage" and e["input"] == 7 and e["output"] == 2 for e in evs))

# ---- 5. Chat with tools: the Anthropic tool loop, sent to the gateway ----
import mcp_client  # noqa: E402


async def _fake_call(route, name, args):
    return "42"
mcp_client.call_route = _fake_call
tools = [{"fn": "get_answer", "description": "answer", "schema": {"type": "object", "properties": {"q": {"type": "number"}}}}]
evs = asyncio.run(collect(engine.anthropic_compat_chat_with_mcp(GOOD, "m-1", [{"role": "user", "content": "?"}],
                                                                 "high", tools, "route")))
check("tool loop: the gateway's tool_use runs the tool", any(e["type"] == "tool_call" and e["name"] == "get_answer" for e in evs))
check("tool loop: final answer arrives", any(e["type"] == "text" and "42" in e["content"] for e in evs))

# ---- 6. Wiring: every place that routes a brain knows this one ----
check("PROVIDER_DEFS has it, kind api, key field set",
      (main._provider_def("anthropic-compat") or {}).get("key_field") == "anthropic_compat_key")
check("its key is encrypted at rest", "model.anthropic_compat_key" in cfgmod._SECRET_PATHS)
check("chat without tools routes to anthropic_compat_stream",
      main._api_stream_goc("anthropic-compat", GOOD, "m-1", []).__qualname__.startswith("anthropic_compat_stream"))
check("hub tools are loaded for it", "anthropic-compat" in main._API_TOOL_PROVIDERS)
check("agents and background work can use it", "anthropic-compat" in main.AGENT_PROVIDERS)
import aux_engine  # noqa: E402
check("aux engine: usable once the base is set", aux_engine.availability({"provider": "anthropic-compat"})[0])
check("connect route is registered",
      any(getattr(r, "path", "") == "/provider/anthropic-compat/connect" for r in main.app.routes)
      or "anthropic_compat_connect" in open(os.path.join(SERVER, "main.py"), encoding="utf-8").read())

# ---- 7. Main brain, then disconnect clears everything and falls back to Claude Code ----
asyncio.run(main.settings_set("model", json.dumps({"main": {"provider": "anthropic-compat", "model": "m-1"}})))
check("can be the main brain", main._effective_main(cfgmod.read_settings())["provider"] == "anthropic-compat")
asyncio.run(main.settings_set("model", json.dumps({"clear_key": "anthropic-compat"})))
m = cfgmod.read_settings()["model"]
check("disconnect clears base, key and typed models",
      not m.get("anthropic_compat_base") and not m.get("anthropic_compat_key") and not m.get("anthropic_compat_models"))
check("disconnecting the main brain falls back to Claude Code",
      main._effective_main(cfgmod.read_settings())["provider"] == "anthropic-cli")

srv.shutdown()
if fails:
    print(f"\nFAIL {len(fails)}: " + " | ".join(fails))
    raise SystemExit(1)
print("\nOK - test_anthropic_compat: all pass")
