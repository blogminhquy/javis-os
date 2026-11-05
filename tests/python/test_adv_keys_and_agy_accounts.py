"""Gateway cards (several addresses + keys each) and extra Antigravity accounts.

    python tests/run.py adv_keys_and_agy_accounts     (no network, no real `agy`)

Owner, 05/11/2026:
1. 0.477.0 put "Advanced API key" on the Anthropic-compatible route and the "Claude Compatible" card vanished. The
   owner asked for "Claude Compatible" back, the advanced keys on their OWN route in the OpenAI format (which lists
   the seller's models; NVIDIA Build could not list any on the Claude route), and several keys on BOTH cards
   ("OpenAI Compatible" and "Claude Compatible"). Both cards hold a list of gateways; every existing code path reads the legacy fields (`<prefix>_base/_key/_models`), so the
   active gateway is mirrored there; a gateway out of quota rests and the next one takes over.
2. "A way to rotate Antigravity": an extra Google account runs `agy` with its own HOME and file storage (Linux only).
"""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-adv-")

import config as cfgmod  # noqa: E402
import model_routing  # noqa: E402
import adv_keys  # noqa: E402
import plan_accounts  # noqa: E402
import main  # noqa: E402

fails = []
AC, OA = adv_keys.ANTHROPIC, adv_keys.OPENAI


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


# ---- 1. an old machine: one gateway in the legacy fields reads as gateway 1, on each card ----
m = {"anthropic_compat_base": "https://api.moonshot.ai/anthropic/v1", "anthropic_compat_key": "sk-old-1111",
     "anthropic_compat_models": ["kimi-k2"],
     "openai_compat_base": "https://integrate.api.nvidia.com/v1/chat/completions", "openai_compat_key": "nvapi-9z",
     "catalog": {"openai-compat": ["meta/llama-3.3-70b-instruct"]}}
g = adv_keys.gateways(m, AC)
check("legacy Claude Compatible gateway reads as gateway 1", len(g) == 1 and g[0]["id"] == adv_keys.legacy_id(AC)
      and g[0]["base"] == "https://api.moonshot.ai/anthropic" and g[0]["key"] == "sk-old-1111", g)
check("its name is the host people recognise", g[0]["label"] == "api.moonshot.ai")
go = adv_keys.gateways(m, OA)
check("legacy OpenAI gateway reads as gateway 1 of Advanced API key, chat URL trimmed, catalog kept",
      len(go) == 1 and go[0]["id"] == adv_keys.legacy_id(OA) and go[0]["base"] == "https://integrate.api.nvidia.com/v1"
      and go[0]["key"] == "nvapi-9z" and go[0]["models"] == ["meta/llama-3.3-70b-instruct"], go)

# ---- 2. add a second gateway: the first stays active, keys go to the encrypted store ----
m = {}
a = adv_keys.add(m, AC, "Kimi", "https://api.moonshot.ai/anthropic", "sk-kimi-4c1e", ["kimi-k2"])
b = adv_keys.add(m, AC, "MiniMax", "https://api.minimax.io/anthropic/v1/messages", "sk-mm-90ab", ["MiniMax-M2"])
check("two gateways, in the order added", [x["label"] for x in adv_keys.gateways(m, AC)] == ["Kimi", "MiniMax"])
check("keys live in account_keys, never in the list", "key" not in m["adv_keys"][0]
      and m["account_keys"][a["id"]] == "sk-kimi-4c1e")
check("the address is normalised (/v1/messages dropped)", adv_keys.gateways(m, AC)[1]["base"] == "https://api.minimax.io/anthropic")
check("the first gateway is mirrored into the legacy fields", m["anthropic_compat_base"] == "https://api.moonshot.ai/anthropic"
      and m["anthropic_compat_key"] == "sk-kimi-4c1e" and m["anthropic_compat_models"] == ["kimi-k2"])
v = adv_keys.view(m, AC)
check("the page sees the last 4 characters only", v[0]["key"] == "••••4c1e" and "sk-kimi" not in str(v), v)

# The two cards never share a list or a key.
n1 = adv_keys.add(m, OA, "NVIDIA", "https://integrate.api.nvidia.com/v1/", "nvapi-1111", ["meta/llama-3.3-70b-instruct"])
n2 = adv_keys.add(m, OA, "Local", "http://127.0.0.1:1234/v1", "", ["qwen3"])
check("OpenAI Compatible keeps its own list", [x["label"] for x in adv_keys.gateways(m, OA)] == ["NVIDIA", "Local"]
      and len(adv_keys.gateways(m, AC)) == 2 and n1["id"].startswith("advo_"))
check("OpenAI Compatible mirrors into the OpenAI fields only", m["openai_compat_base"] == "https://integrate.api.nvidia.com/v1"
      and m["openai_compat_key"] == "nvapi-1111" and m["anthropic_compat_key"] == "sk-kimi-4c1e")
check("a gateway with no key is allowed on the OpenAI route", adv_keys.gateways(m, OA)[1]["key"] == "")
adv_keys.save_list(m, AC, [{"id": a["id"]}, {"id": b["id"]}])
check("saving the Claude list leaves the OpenAI keys alone", m["account_keys"].get(n1["id"]) == "nvapi-1111")
sw = adv_keys.rest_and_rotate(m, OA, "nvapi-1111", 600)
check("quota on NVIDIA moves OpenAI Compatible to the next gateway, even one with no key",
      sw and m["openai_compat_base"] == "http://127.0.0.1:1234/v1" and m["openai_compat_key"] == "")
check("a keyless gateway is found by the 'none' key the route sends", adv_keys.account_no(m, OA, "none") == (2, "Local"))
model_routing.clear_rest(OA, n1["id"])
adv_keys.forget(m, OA)
check("Disconnect on OpenAI Compatible forgets its gateways only", adv_keys.gateways(m, OA) == [] and not m["openai_compat_base"]
      and n1["id"] not in m["account_keys"] and len(adv_keys.gateways(m, AC)) == 2)

# ---- 3. out of quota: the gateway rests, the next one takes over, its model follows ----
model_routing.set_profile(m, AC, model="kimi-k2")
switched = adv_keys.rest_and_rotate(m, AC, "sk-kimi-4c1e", 600)
check("quota on Kimi switches to MiniMax", switched and m["anthropic_compat_key"] == "sk-mm-90ab"
      and m["anthropic_compat_base"] == "https://api.minimax.io/anthropic")
check("the card's model moves to a model MiniMax lists", model_routing.profile(m, AC)["model"] == "MiniMax-M2")
check("the resting gateway shows until when", adv_keys.view(m, AC)[0]["resting_until"] > time.time())
adv_keys.rest_and_rotate(m, AC, "sk-mm-90ab", 600)
check("all gateways resting: no active gateway (the route is not ready)", adv_keys.active(m, AC) is None)
model_routing.clear_rest(AC, a["id"])
model_routing.clear_rest(AC, b["id"])

# ---- 4. the page's list: order, on/off, names, removal ----
adv_keys.save_list(m, AC, [{"id": b["id"]}, {"id": a["id"], "enabled": False, "label": "Kimi cũ"}])
gs = adv_keys.gateways(m, AC)
check("reorder and switch off", [x["id"] for x in gs] == [b["id"], a["id"]] and gs[1]["enabled"] is False
      and gs[1]["label"] == "Kimi cũ")
check("the new first gateway is mirrored", m["anthropic_compat_key"] == "sk-mm-90ab")
adv_keys.save_list(m, AC, [{"id": b["id"]}])
check("a gateway missing from a stale page is kept", len(adv_keys.gateways(m, AC)) == 2)
adv_keys.save_list(m, AC, [{"id": b["id"]}], removed=[a["id"]])
check("a removed gateway goes with its key", len(adv_keys.gateways(m, AC)) == 1 and a["id"] not in m["account_keys"])
check("edit keeps the key when none is typed", adv_keys.update(m, AC, b["id"], label="MM", base=None, key="", models=None)
      and adv_keys.gateways(m, AC)[0]["key"] == "sk-mm-90ab" and adv_keys.gateways(m, AC)[0]["label"] == "MM")

# ---- 5. server wiring: card names, settings view, route readiness, quota rotation on disk ----
with cfgmod._SETTINGS_LOCK:
    cfg = cfgmod.read_settings()
    adv_keys.add(cfg["model"], AC, "Kimi", "https://api.moonshot.ai/anthropic", "sk-kimi-4c1e", ["kimi-k2"])
    adv_keys.add(cfg["model"], AC, "MiniMax", "https://api.minimax.io/anthropic", "sk-mm-90ab", ["MiniMax-M2"])
    adv_keys.add(cfg["model"], OA, "NVIDIA", "https://integrate.api.nvidia.com/v1", "nvapi-2222", ["meta/llama-3.3-70b-instruct"])
    cfgmod.write_settings(cfg)
mc = cfgmod.read_settings()["model"]
cards = {p["id"]: p for p in main._providers_view(cfgmod.read_settings())}
check("the Anthropic route is its own card again, named Claude Compatible",
      cards[AC]["configured"] is True and cards[AC]["label"] == "Claude Compatible", cards[AC]["label"])
check("the OpenAI route keeps its card, OpenAI Compatible, now with several keys",
      cards[OA]["configured"] is True and cards[OA]["label"] == "OpenAI Compatible", cards[OA]["label"])
check("route ready while a gateway can run", main._route_ready(mc, AC) is True and main._route_ready(mc, OA) is True)
main._note_api_limit(mc, AC, "sk-kimi-4c1e", "429 rate limit", 600)
mc2 = cfgmod.read_settings()["model"]
check("a quota error in chat moves the saved route to the next gateway", mc2["anthropic_compat_key"] == "sk-mm-90ab")
nxt = main._chat_next_route(mc, AC, "sk-kimi-4c1e", [])
check("the same turn reruns on the next gateway before the next card",
      nxt.get("route", ("",))[0] == AC and nxt["route"][2] == "sk-mm-90ab", nxt)
src = (Path(SERVER) / "main.py").read_text(encoding="utf-8")
check("the settings page never receives gateway keys", 'safe["model"].pop(adv_keys.field(_gp), None)' in src
      and 'safe["model"].pop("account_keys", None)' in src)
check("Disconnect forgets every gateway of the card", "adv_keys.forget(m, patch[\"clear_key\"])" in src)


# ---- 5b. OpenAI Compatible connects and reads the seller's model list ----
class _Req:
    def __init__(self, body):
        self._b = body

    async def json(self):
        return self._b


class _Resp:
    def __init__(self, code, body):
        self.status_code, self._body, self.text = code, body, json.dumps(body)

    def json(self):
        return self._body


calls = []


class _Client:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None):
        calls.append(("GET", url, (headers or {}).get("Authorization")))
        if "nolist" in url:
            return _Resp(404, {"error": "no"})
        return _Resp(200, {"object": "list", "data": [{"id": "nvidia/llama-3.1-nemotron-70b-instruct"},
                                                       {"id": "deepseek-ai/deepseek-r1"}]})

    async def post(self, url, headers=None, json=None):
        calls.append(("POST", url, (json or {}).get("model")))
        return _Resp(200, {"choices": []})


import httpx  # noqa: E402
_real = httpx.AsyncClient
httpx.AsyncClient = _Client
try:
    r = asyncio.run(main.openai_compat_connect(_Req({"base": "https://integrate.api.nvidia.com/v1", "key": "nvapi-new",
                                                     "label": "NVIDIA Build", "add": True})))
    check("NVIDIA Build connects and its models are listed", r.get("ok") and r.get("models") == 2 and r.get("listed"), r)
    check("the list is read from {base}/models with a Bearer key",
          calls[0] == ("GET", "https://integrate.api.nvidia.com/v1/models", "Bearer nvapi-new"), calls)
    gw = [x for x in adv_keys.gateways(cfgmod.read_settings()["model"], OA) if x["label"] == "NVIDIA Build"]
    check("the gateway is saved on OpenAI Compatible with the seller's models",
          len(gw) == 1 and "deepseek-ai/deepseek-r1" in gw[0]["models"] and gw[0]["key"] == "nvapi-new", gw)
    r = asyncio.run(main.openai_compat_connect(_Req({"base": "https://nolist.example.com/v1", "key": "k", "add": True})))
    check("a seller with no list opens the model box instead of failing", r.get("need_models") is True and not r.get("ok"), r)
    r = asyncio.run(main.openai_compat_connect(_Req({"base": "https://nolist.example.com/v1", "key": "k", "add": True,
                                                     "models": "my-model"})))
    check("with a typed model it checks one tiny chat call and saves", r.get("ok") and calls[-1] == (
        "POST", "https://nolist.example.com/v1/chat/completions", "my-model"), (r, calls[-1:]))
finally:
    httpx.AsyncClient = _real

# ---- 6. Antigravity: extra Google accounts, Linux only ----
linux = sys.platform.startswith("linux")
check("Antigravity can hold extra accounts on Linux only", plan_accounts.available("antigravity-cli") == linux)
if linux:
    folder = plan_accounts.home("antigravity-cli", "acc_agy1")
    env = plan_accounts.env_for("antigravity-cli", folder)
    check("an extra account runs agy with its own HOME and file storage",
          env == {"HOME": str(folder), "GEMINI_FORCE_FILE_STORAGE": "true"}, env)
    check("not signed in before agy writes its token", plan_accounts.signed_in("antigravity-cli", "acc_agy1") is False)
    tok = folder / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"
    tok.parent.mkdir(parents=True, exist_ok=True)
    tok.write_text("x")
    check("signed in once the token file exists", plan_accounts.signed_in("antigravity-cli", "acc_agy1") is True)

    class _E:
        pass
    e = _E()
    plan_accounts.use(e, "antigravity-cli", "acc_agy1")
    check("the engine is pointed at the account's HOME", getattr(e, "agy_home", None) == str(folder))
    plan_accounts.use(e, "antigravity-cli", plan_accounts.MAIN)
    check("account 1 keeps the machine's own login", e.agy_home is None)
agy_src = (Path(SERVER) / "antigravity_cli.py").read_text(encoding="utf-8")
check("the agy process gets HOME and file storage for an extra account",
      'getattr(self, "agy_home", None)' in agy_src and '_env["GEMINI_FORCE_FILE_STORAGE"] = "true"' in agy_src)
check("the chat turn picks the Antigravity account to run",
      '_turn_acc["antigravity-cli"] = _plan_account_apply(acli, "antigravity-cli", mcfg)' in src)

print()
if fails:
    print(f"ĐỎ {len(fails)} mục")
    raise SystemExit(1)
print("Tất cả xanh.")
