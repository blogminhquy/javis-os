"""Muse as a model provider (owner 26/11/2026): a card on the Models page, connected by pasting a Muse account's
cookie, usable as a fallback and as the background model, through Muse Gateway (server/muse.py).

Run:
    python tests/python/test_muse_provider.py      (no network: a fake gateway on 127.0.0.1)

Locks:
1. Wiring: every table a provider must be in (PROVIDER_DEFS, config defaults, the encrypted-secret list, the chat,
   bot and tool-less paths, background work, agents, Telegram, the dashboard's lists, logo, both dictionaries).
2. Tools through text: the gateway gets no `tools` field and always a last message from the user; earlier calls and
   results come back as plain text; a <tool_calls> block (or fenced JSON) naming a real tool becomes an OpenAI call;
   a JSON sample in an ordinary answer, or a call to a tool that was not offered, never does.
3. The shared tool loop runs Muse end to end: Muse asks for a tool in text, Javis runs it, Muse answers.
4. The Models page routes: connect with a cookie puts Muse in the usage order, removing the last account or
   Disconnect takes it out, the gateway address must be a plain address, and neither the admin key nor a cookie ever
   comes back in /settings.
"""
import asyncio
import inspect
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from _paths import ROOT, SERVER  # noqa: E402,F401  - puts server/ on sys.path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-muse-test-"))
os.environ["JAVIS_API_STREAM_TOOLS"] = "0"
for _k in ("MUSE_GATEWAY_URL", "MUSE_ADMIN_KEY"):
    os.environ.pop(_k, None)
_GW_DIR = tempfile.mkdtemp(prefix="muse-gw-")
os.environ["MUSE_GATEWAY_CONFIG"] = os.path.join(_GW_DIR, "config.json")

import aux_engine  # noqa: E402
import config as cfgmod  # noqa: E402
import engine  # noqa: E402
import main  # noqa: E402
import muse  # noqa: E402

fails = []


def check(name: str, condition: bool, more="") -> None:
    print(("PASS: " if condition else "FAIL: ") + name + (f"  [{more}]" if more and not condition else ""))
    if not condition:
        fails.append(name)


CONSOLE_JS = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
LOGOS_JS = (ROOT / "dashboard" / "provider-logos.js").read_text(encoding="utf-8")
VI = json.loads((ROOT / "dashboard" / "i18n" / "vi.json").read_text(encoding="utf-8"))
EN = json.loads((ROOT / "dashboard" / "i18n" / "en.json").read_text(encoding="utf-8"))

# ─────────── 1. Wiring ───────────
_defs = {p["id"]: p for p in main.PROVIDER_DEFS}
_d = _defs.get("muse") or {}
check("in PROVIDER_DEFS as an API card", _d.get("kind") == "api" and _d.get("label") == "Muse")
check("one model, the gateway's", _d.get("default_models") == [muse.MODEL])
check("one gateway, not a list of keys", "muse" in main._ROUTING_SINGLE_KEY)
_dm = cfgmod._DEFAULT["model"]
check("config has the card's fields", all(k in _dm for k in ("muse_on", "muse_base", "muse_key")) and _dm["muse_on"] is False)
check("config has a muse catalog", _dm["catalog"].get("muse") == [muse.MODEL])
check("admin key is in the ENCRYPTED list", "model.muse_key" in cfgmod._SECRET_PATHS)
check("admin key is masked through PROVIDER_DEFS", "muse_key" in main._PROVIDER_KEY_FIELDS)
check("agents can run on Muse", "muse" in main.AGENT_PROVIDERS)
check("hub tools are loaded for Muse", "muse" in main._API_TOOL_PROVIDERS)
for _fn in (main._api_stream_mcp, main._bot_stream_co_tool):
    _src = inspect.getsource(_fn)
    _at = _src.find('if prov == "muse":\n')
    check(f"{_fn.__name__} has its own muse branch", _at >= 0 and "engine.muse_chat_with_mcp(" in _src[_at:_at + 200])
_gen = main._api_stream_goc("muse", "k", "m", [{"role": "user", "content": "x"}], "off")
check("tool-less path picks muse_stream", _gen.__qualname__.startswith("muse_stream"))
_cfg = {"model": {}}
main._set_main_model(_cfg, "muse", muse.MODEL)
check("_set_main_model writes engine muse", _cfg["model"]["engine"] == "muse")
check("_api_label", main._api_label("muse") == "Muse")
check("Telegram knows the card", main._tg_prov_label("muse") == "Muse"
      and main._tg_prov_ready("muse", {"muse_on": True}) and not main._tg_prov_ready("muse", {}))

check("background work: API provider with a key field", "muse" in aux_engine.API_PROVIDERS
      and aux_engine._KEY_FIELD.get("muse") == "muse_key")
_ok, _why = aux_engine.availability({"provider": "muse"}, {"model": {}})
check("background work before connecting says so", _ok is False and "Muse" in _why)
check("background work once connected", aux_engine.availability({"provider": "muse"}, {"model": {"muse_on": True}})[0])
check("background key: none until connected",
      aux_engine.api_key_for("muse", {"model": {}}) == "" and aux_engine.api_key_for("muse", {"model": {"muse_on": True}}))
check("route ready only when connected", not main._route_ready({}, "muse") and main._route_ready({"muse_on": True}, "muse"))
check("chat key: the admin key saved on the page", main._provider_key({"muse_on": True, "muse_key": "k1"}, _d) == "k1")
check("chat key: empty when not connected", main._provider_key({"muse_key": "k1"}, _d) == "")

check("dashboard: no 'no tools' banner for Muse", '"anthropic-compat", "muse"];' in CONSOLE_JS)
check("dashboard: the Muse card is drawn", 'if (p.id === "muse") return museCard(p, ord);' in CONSOLE_JS)
check("dashboard: Muse has no Effort chip", 'p.id === "muse" ? "" : effChip(' in CONSOLE_JS)
check("dashboard: the card's routes", all(r in CONSOLE_JS for r in ("/provider/muse/connect", "/provider/muse/account",
                                                                     "/provider/muse/gateway", "/provider/muse/status")))
check("logo: a real file, mapped", '"muse": "muse"' in LOGOS_JS and (ROOT / "dashboard" / "logos" / "muse.png").is_file())
_keys = [k for k in VI if k.startswith("models.muse_")] + ["models.tag_muse"]
check("every Muse string in both languages", len(_keys) > 15 and all(k in EN for k in _keys),
      [k for k in _keys if k not in EN])
_used = set(__import__("re").findall(r't\("(models\.muse_[a-z0-9_]+)"', CONSOLE_JS))
check("every Muse key the page uses exists", _used and _used <= set(VI), sorted(_used - set(VI)))

# ─────────── 2. Tools through text ───────────
TOOLS_OAI = [{"type": "function", "function": {"name": "javis_read_file", "description": "Read a file in the brain",
                                               "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}},
             {"type": "function", "function": {"name": "javis_connections", "description": "List connections",
                                               "parameters": {"type": "object", "properties": {}}}}]
NAMES = muse.tool_names(TOOLS_OAI)
p = muse.tools_prompt(TOOLS_OAI, "required")
check("prompt lists the tools and the block", "javis_read_file" in p and "<tool_calls>" in p and "MUST call" in p)
msgs = muse.gateway_messages([
    {"role": "system", "content": "You are Javis."},
    {"role": "user", "content": "Read a.md"},
    {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "type": "function",
                                                         "function": {"name": "javis_read_file",
                                                                      "arguments": "{\"path\": \"a.md\"}"}}]},
    {"role": "tool", "tool_call_id": "c1", "content": "hello"},
    {"role": "system", "content": "Note from Javis"},
], TOOLS_OAI, None)
check("tools prompt goes first", msgs[0]["role"] == "system" and "TOOLS" in msgs[0]["content"])
check("no tool role reaches the gateway", all(m["role"] in ("system", "user", "assistant") for m in msgs))
check("an earlier call is written as the block", any(m["role"] == "assistant" and "<tool_calls>" in m["content"]
                                                     and "a.md" in m["content"] for m in msgs))
check("a result is a user message naming the tool", any(m["role"] == "user" and
                                                        m["content"].startswith("[tool result: javis_read_file]")
                                                        for m in msgs))
check("the last message is the user's (trailing note folded in)", msgs[-1]["role"] == "user"
      and "Note from Javis" in msgs[-1]["content"])
check("a lone system message still ends with a user one", muse.gateway_messages([{"role": "system", "content": "x"}])[-1]["role"] == "user")

before, calls = muse.parse_tool_calls('Ok.\n<tool_calls>\n[{"name": "javis_read_file", "arguments": {"path": "b.md"}}]\n</tool_calls>', NAMES)
check("block parsed into a call", calls == [{"name": "javis_read_file", "arguments": {"path": "b.md"}}] and before == "Ok.")
_, calls = muse.parse_tool_calls('```json\n{"tool_calls": [{"name": "javis_connections", "arguments": "{}"}]}\n```', NAMES)
check("fenced JSON with a real tool is a call", calls == [{"name": "javis_connections", "arguments": {}}])
txt, calls = muse.parse_tool_calls('Here is a sample:\n```json\n{"name": "Ana", "age": 3}\n```', NAMES)
check("a JSON sample in an answer is not a call", calls == [] and "sample" in txt)
_, calls = muse.parse_tool_calls('<tool_calls>[{"name": "rm_rf", "arguments": {}}]</tool_calls>', NAMES)
check("a tool that was not offered is never called", calls == [])
txt, calls = muse.parse_tool_calls("<tool_calls>not json</tool_calls>", NAMES)
check("a broken block stays text", calls == [] and "not json" in txt)
r = muse.openai_reply({"choices": [{"message": {"content": '<tool_calls>[{"name": "javis_connections", "arguments": {}}]</tool_calls>'}}]}, NAMES)
m0 = r["choices"][0]
check("openai reply carries tool_calls", m0["finish_reason"] == "tool_calls"
      and m0["message"]["tool_calls"][0]["function"]["name"] == "javis_connections")
check("cookie check", muse.valid_cookie("datr=a; hatch_sess=XYZ") and muse.valid_cookie("wss://hatch.x/v1")
      and not muse.valid_cookie("hello"))
for bad in ("127.0.0.1:8080", "http://u:p@127.0.0.1:8080", "http://127.0.0.1:8080/admin", "javascript:x"):
    try:
        muse.clean_base(bad)
        check(f"address refused: {bad}", False)
    except muse.GatewayError:
        check(f"address refused: {bad}", True)
check("address with /v1 is trimmed", muse.clean_base("http://muse:8080/v1/") == "http://muse:8080")

# ─────────── fake gateway ───────────
KEY = "test-admin-key"
STATE = {"accounts": [], "n": 0, "chat": []}


class _Gw(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _auth(self):
        if self.headers.get("Authorization") != "Bearer " + KEY:
            self._json(401, {"error": {"message": "bad key"}})
            return False
        return True

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if not self._auth():
            return
        if self.path == "/api/admin/accounts":
            return self._json(200, {"data": [{k: v for k, v in a.items() if k != "credential"}
                                              for a in STATE["accounts"]]})
        self._json(404, {"error": {"message": "nope"}})

    def do_POST(self):
        if not self._auth():
            return
        b = self._body()
        if self.path == "/api/admin/accounts":
            STATE["n"] += 1
            ok = "BAD" not in b["credential"]
            a = {"id": f"acc{STATE['n']}", "name": b["name"], "enabled": True, "credential": b["credential"],
                 "created_at": f"2026-11-26T00:00:{STATE['n']:02d}Z", "live": {"connected": ok},
                 "last_error": "" if ok else "session expired"}
            STATE["accounts"].append(a)
            return self._json(200, {"account": {"id": a["id"]}, "test": {"ok": ok, "error": a["last_error"]}})
        if self.path.endswith("/test"):
            return self._json(200, {"ok": True})
        if self.path == "/v1/chat/completions":
            STATE["chat"].append(b)
            seen_result = any("[tool result: javis_read_file]" in str(m.get("content")) for m in b["messages"])
            text = ("The file says: hello from the brain" if seen_result else
                    'Let me read it.\n<tool_calls>\n[{"name": "javis_read_file", "arguments": {"path": "notes/a.md"}}]\n</tool_calls>')
            return self._json(200, {"id": "x", "choices": [{"message": {"role": "assistant", "content": text},
                                                             "finish_reason": "stop"}]})
        self._json(404, {"error": {"message": "nope"}})

    def do_PATCH(self):
        if not self._auth():
            return
        a = next((x for x in STATE["accounts"] if x["id"] == self.path.rsplit("/", 1)[1]), None)
        if not a:
            return self._json(404, {"error": {"message": "no account"}})
        b = self._body()
        a.update({k: v for k, v in b.items() if k in ("enabled", "credential")})
        self._json(200, {"ok": True})

    def do_DELETE(self):
        if not self._auth():
            return
        STATE["accounts"] = [x for x in STATE["accounts"] if x["id"] != self.path.rsplit("/", 1)[1]]
        self._json(200, {"ok": True})


_srv = ThreadingHTTPServer(("127.0.0.1", 0), _Gw)
threading.Thread(target=_srv.serve_forever, daemon=True).start()
GW = f"http://127.0.0.1:{_srv.server_address[1]}"
with open(os.environ["MUSE_GATEWAY_CONFIG"], "w", encoding="utf-8") as f:
    json.dump({"admin_key": KEY}, f)
os.environ["MUSE_GATEWAY_URL"] = GW

# ─────────── 3. The shared tool loop on Muse ───────────
TOOLS = [{"fn": "javis_read_file", "server": "javis", "name": "javis_read_file", "description": "Read a file",
          "schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}]
CALLED = []


async def _read(args):
    CALLED.append(args)
    return "hello from the brain"


async def _collect(gen):
    return [ev async for ev in gen]


cfgmod.write_settings({**cfgmod.read_settings(), "model": {**(cfgmod.read_settings().get("model") or {}), "muse_on": True}})
evs = asyncio.run(_collect(engine.muse_chat_with_mcp(KEY, "", [{"role": "user", "content": "What is in notes/a.md?"}],
                                                     "off", TOOLS, {"javis_read_file": {"call": _read}})))
final = "".join(e.get("content", "") for e in evs if e.get("type") == "text")
check("Muse called the tool in text and Javis ran it", CALLED == [{"path": "notes/a.md"}], CALLED)
check("the turn shows the tool call", any(e.get("type") == "tool_call" and "javis_read_file" in str(e.get("name"))
                                          for e in evs), evs[:4])
check("Muse's final answer comes through", "hello from the brain" in final, final)
check("the gateway never got a tools field", STATE["chat"] and all("tools" not in b and "tool_choice" not in b
                                                                   for b in STATE["chat"]))
check("every gateway request ends with a user message", all(b["messages"][-1]["role"] == "user" for b in STATE["chat"]))
check("the second round carries the tool result", len(STATE["chat"]) >= 2
      and "[tool result: javis_read_file]" in json.dumps(STATE["chat"][1]["messages"], ensure_ascii=False))
check("Muse runs one model, unstreamed rounds", all(b["model"] == muse.MODEL and b["stream"] is False for b in STATE["chat"]))

# ─────────── 4. Models page routes ───────────
from fastapi.testclient import TestClient  # noqa: E402

c = TestClient(main.app, base_url="http://127.0.0.1:8080")
m = cfgmod.read_settings()
m["model"]["muse_on"] = False
cfgmod.write_settings(m)
r = c.post("/provider/muse/connect", json={"label": "Gmail", "cookie": "hello"}).json()
check("a text without hatch_sess is refused", r.get("ok") is False and "hatch_sess" in r.get("error", ""), r)
r = c.post("/provider/muse/connect", json={"label": "Gmail", "cookie": "datr=a; hatch_sess=SECRET_ONE"}).json()
check("connect with a cookie", r == {"ok": True, "error": ""}, r)
mm = cfgmod.read_settings()["model"]
check("the card is connected", mm.get("muse_on") is True)
view = next(p for p in main._providers_view(cfgmod.read_settings()) if p["id"] == "muse")
check("the card reports connected", view["configured"] is True)
check("Muse joins the usage order", "muse" in main._routing_order(mm, main._routing_connected_ids(cfgmod.read_settings())))
r = c.post("/provider/muse/account", json={"op": "add", "label": "Work", "cookie": "hatch_sess=BAD_TWO"}).json()
check("a dead cookie is added with a warning", r.get("ok") is True and "warn" in r, r)
st = c.get("/provider/muse/status").json()
check("status lists both accounts, nothing secret", [a["label"] for a in st["accounts"]] == ["Gmail", "Work"]
      and "SECRET_ONE" not in json.dumps(st) and KEY not in json.dumps(st), st)
r = c.post("/provider/muse/account", json={"op": "off", "id": "acc1"}).json()
check("switch an account off", r.get("ok") and STATE["accounts"][0]["enabled"] is False)
r = c.post("/provider/muse/account", json={"op": "cookie", "id": "acc2", "cookie": "hatch_sess=FRESH"}).json()
check("a fresh cookie for an account", r.get("ok") and STATE["accounts"][1]["credential"] == "hatch_sess=FRESH")
r = c.post("/provider/muse/gateway", json={"base": "http://u:p@evil:1", "key": "x"}).json()
check("a gateway address with a password is refused", r.get("ok") is False)
r = c.post("/provider/muse/gateway", json={"base": GW, "key": KEY}).json()
check("save the gateway address and key", r.get("ok") is True and r.get("key_from") == "page", r)
saved = cfgmod.read_settings()["model"]
check("the key is saved, the address too", saved.get("muse_key") == KEY and saved.get("muse_base") == GW)
s_txt = json.dumps(c.get("/settings").json(), ensure_ascii=False)
check("/settings never returns the admin key or a cookie", KEY not in s_txt and "SECRET_ONE" not in s_txt)
raw = (cfgmod.STATE_DIR / "settings.json").read_text(encoding="utf-8") if (cfgmod.STATE_DIR / "settings.json").is_file() else ""
check("the key is encrypted on disk", raw and KEY not in raw)
r = c.post("/provider/muse/gateway", json={"base": "http://127.0.0.1:1"}).json()
check("a new address drops the old key (it never follows a new host)", cfgmod.read_settings()["model"].get("muse_key") == "")
c.post("/provider/muse/gateway", json={"base": GW, "key": KEY})

c.post("/settings", data={"section": "model", "data": json.dumps({"clear_key": "muse"})})
after = cfgmod.read_settings()["model"]
check("Disconnect: the card leaves", after.get("muse_on") is False
      and "muse" not in main._routing_order(after, main._routing_connected_ids(cfgmod.read_settings())))
check("Disconnect keeps the gateway's address and key", after.get("muse_base") == GW and after.get("muse_key") == KEY)
r = c.post("/provider/muse/connect", json={}).json()
check("connect again without a cookie uses the gateway's accounts", r.get("ok") is True
      and cfgmod.read_settings()["model"].get("muse_on") is True, r)
for a in list(STATE["accounts"]):
    c.post("/provider/muse/account", json={"op": "remove", "id": a["id"]})
check("removing the last account disconnects the card", cfgmod.read_settings()["model"].get("muse_on") is False)
r = c.post("/provider/muse/connect", json={}).json()
check("connect without a cookie and no account asks for one", r.get("ok") is False and r.get("error"), r)

_srv.shutdown()
print()
if fails:
    print(f"FAIL {len(fails)}: " + "; ".join(fails))
    raise SystemExit(1)
print("ALL PASS")
