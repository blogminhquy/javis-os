"""The model list of the two gateway cards (OpenAI Compatible, Claude Compatible) always has something to pick.

    python tests/run.py compat_model_list     (a fake gateway on 127.0.0.1, no outside network)

A user's picker showed "Could not load the model list" under OpenAI Compatible (13/11/2026) with no reason and no
way out. Running both cards against fake gateways found these, each pinned below:

1. A gateway that answers its list in another envelope (a bare list, {"models": [...]}, rows named by "name")
   connected fine but read as "no list" afterwards.
2. A Base URL typed without /v1 never found the list that sits at {base}/v1/models, and a machine that saved such an
   address before Javis checked addresses had an empty picker for good.
3. A model name the owner typed vanished from the picker as soon as the gateway listed other models.
4. The reason shown was a raw exception, or a sentence with the placeholder "{base}" left in it.
5. Remembering a list wrote back settings read BEFORE the gateway was asked, undoing a key saved meanwhile.
6. A gateway whose website answers every path with a page (HTTP 200) passed the connect check with a wrong address.
"""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-compat-list-")
os.environ["NO_PROXY"] = os.environ["no_proxy"] = "127.0.0.1,localhost"

import config as cfgmod  # noqa: E402
import adv_keys  # noqa: E402
import main  # noqa: E402

fails = []
OA, AC = adv_keys.OPENAI, adv_keys.ANTHROPIC


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra}]" if extra != "" and not cond else ""))
    if not cond:
        fails.append(name)


# ---- a fake gateway: each port behaves one way ----
MODE = {}       # port -> behaviour
SEEN = {}       # port -> paths asked


class Gateway(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        port = self.server.server_port
        mode = MODE[port]
        SEEN.setdefault(port, []).append(self.path)
        if self.path == "/v1/models":
            if mode == "refuses_key":
                return self._send(401, {"error": "bad key"})
            if mode == "openai":
                return self._send(200, {"object": "list", "data": [{"id": "zeta"}, {"id": "alpha"}]})
            if mode == "bare":
                return self._send(200, [{"id": "m-a"}, {"id": "m-b"}])
            if mode == "named":
                return self._send(200, {"models": [{"name": "models/g-1"}, {"name": "g-2"}, "g-3"]})
            if mode == "site":
                return self._send(200, {"data": [{"id": "site-1"}]})
        if mode in ("site", "site_only"):   # the seller's website answers every other path with a page
            return self._send(200, b"<!doctype html><html>dashboard</html>", "text/html")
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        port = self.server.server_port
        mode = MODE[port]
        self.rfile.read(int(self.headers.get("content-length") or 0))
        SEEN.setdefault(port, []).append("POST " + self.path)
        if mode in ("site", "site_only") and not self.path.startswith("/v1/"):
            return self._send(200, b"<!doctype html><html>dashboard</html>", "text/html")
        if self.path.endswith(("/chat/completions", "/messages")):
            return self._send(200, {"choices": [{"message": {"content": "x"}}], "content": []})
        return self._send(404, {"error": "not found"})


def gateway(mode):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Gateway)
    MODE[srv.server_port] = mode
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_port}"


def port_of(base):
    return int(base.rsplit(":", 1)[1].split("/")[0])


class Req:
    def __init__(self, body):
        self.body = body

    async def json(self):
        return self.body


def reset():
    cfg = cfgmod.read_settings()
    m = cfg["model"]
    for prov in adv_keys.PROVIDERS:
        adv_keys.forget(m, prov)
        m.get("catalog", {}).pop(prov, None)
    cfgmod.write_settings(cfg)
    main._PROV_MODELS_CACHE.clear()


def model():
    return cfgmod.read_settings()["model"]


async def listed(prov):
    main._PROV_MODELS_CACHE.clear()
    return await main.provider_models_index(prov)


# ---- 1. every envelope a seller answers with is read ----
check("OpenAI envelope {data: [{id}]}", main._model_ids({"data": [{"id": "a"}, {"id": "b"}]}) == ["a", "b"])
check("a bare list of rows", main._model_ids([{"id": "a"}, {"id": "b"}]) == ["a", "b"])
check("{models: [...]} with rows named by `name`, Google's models/ prefix cut, plain strings",
      main._model_ids({"models": [{"name": "models/g-1"}, {"name": "g-2"}, "g-3"]}) == ["g-1", "g-2", "g-3"])
check("no duplicates, empty rows dropped", main._model_ids({"data": [{"id": "a"}, {"id": "a"}, {}, None, {"id": ""}]}) == ["a"])
check("a reply that is no list reads as no models", main._model_ids({"error": "x"}) == [] and main._model_ids("<html>") == [])
check("a versioned base is asked once, an unversioned one also under /v1",
      [u for u, _ in main._openai_list_urls("https://x.io/v1")] == ["https://x.io/v1/models"]
      and [u for u, _ in main._openai_list_urls("https://x.io/api/paas/v4")] == ["https://x.io/api/paas/v4/models"]
      and main._openai_list_urls("https://x.io") == [("https://x.io/models", "https://x.io"),
                                                    ("https://x.io/v1/models", "https://x.io/v1")])


async def run():
    # ---- 2. OpenAI Compatible: envelopes other than OpenAI's connect AND list afterwards ----
    for mode, want in (("openai", ["alpha", "zeta"]), ("bare", ["m-a", "m-b"]), ("named", ["g-1", "g-2", "g-3"])):
        reset()
        b = gateway(mode)
        r = await main.openai_compat_connect(Req({"base": b + "/v1", "key": "k", "add": True}))
        check(f"OpenAI Compatible connects to a gateway answering the {mode!r} shape", r.get("ok") and r.get("listed"), r)
        d = await listed(OA)
        check(f"...and the picker lists its models ({mode})", d["models"] == want and d.get("live"), d)

    # ---- 3. a Base URL typed without /v1: the list is found under /v1 and THAT address is saved ----
    reset()
    b = gateway("openai")
    r = await main.openai_compat_connect(Req({"base": b, "key": "k", "add": True}))
    check("a Base URL without /v1 connects without asking for a model name", r.get("ok") and r.get("listed"), r)
    check("the saved address is the one chat needs ({base}/v1)", model()["openai_compat_base"] == b + "/v1",
          model()["openai_compat_base"])
    d = await listed(OA)
    check("the picker lists the models found under /v1", d["models"] == ["alpha", "zeta"], d)

    # a refused key is never sent to a second path
    reset()
    b = gateway("refuses_key")
    MODE[port_of(b)] = "refuses_key"
    r = await main.openai_compat_connect(Req({"base": b + "/v1", "key": "bad", "add": True}))
    check("a refused key says so and saves nothing", not r.get("ok") and "401" in r.get("error", "")
          and not adv_keys.gateways(model(), OA), r)

    # ---- 4. a machine that saved an address before Javis checked it (three old fields, nothing else) ----
    reset()
    b = gateway("openai")
    cfg = cfgmod.read_settings()
    cfg["model"]["openai_compat_base"] = b          # saved blind, version left off
    cfg["model"]["openai_compat_key"] = "k"
    cfgmod.write_settings(cfg)
    d = await listed(OA)
    check("an old machine with the version left off gets its list", d["models"] == ["alpha", "zeta"], d)
    check("...and its address is repaired so the picked model can chat", model()["openai_compat_base"] == b + "/v1",
          model()["openai_compat_base"])

    # ---- 5. nothing to list: the reason is a sentence that names the host and says what to do ----
    for prov, v1 in ((OA, "/v1"), (AC, "")):
        reset()
        b = gateway("silent")
        cfg = cfgmod.read_settings()
        lg = adv_keys._SPEC[prov]["legacy"]
        cfg["model"][lg + "_base"] = b + v1
        cfg["model"][lg + "_key"] = "k"
        cfgmod.write_settings(cfg)
        d = await listed(prov)
        err = d.get("error") or ""
        check(f"{prov}: an empty list comes with a reason", d["models"] == [] and bool(err), d)
        check(f"{prov}: the reason names the gateway and the card, with the cause", adv_keys.host(b) in err
              and main._card_label(main._provider_def(prov)) in err and "HTTP 404" in err, err)
        check(f"{prov}: no raw exception and no placeholder left in it",
              "{" not in err and "Error" not in err and "Traceback" not in err, err)

    reset()
    b = gateway("refuses_key")
    cfg = cfgmod.read_settings()
    cfg["model"]["openai_compat_base"] = b + "/v1"
    cfg["model"]["openai_compat_key"] = "bad"
    cfgmod.write_settings(cfg)
    d = await listed(OA)
    check("a refused key is named as the cause", "401" in (d.get("error") or "") and "key" in d["error"].lower(), d)
    check("...and the key went to one path only", SEEN.get(port_of(b)) == ["/v1/models"], SEEN.get(port_of(b)))

    # ---- 6. a typed model name stays in the picker next to the gateway's own list ----
    reset()
    b = gateway("openai")
    r = await main.openai_compat_connect(Req({"base": b + "/v1", "key": "k", "add": True, "models": "my-private-model"}))
    d = await listed(OA)
    check("OpenAI Compatible keeps a typed model first, then the gateway's list",
          r.get("ok") and d["models"] == ["my-private-model", "alpha", "zeta"], d)
    MODE[port_of(b)] = "silent"   # the gateway stops listing: what was saved is still there to pick
    d = await listed(OA)
    check("a gateway that stops listing still shows the saved models", d["models"] == ["my-private-model", "alpha", "zeta"], d)

    # a seller that lists nothing: the typed name is the list
    reset()
    b = gateway("silent")
    r = await main.openai_compat_connect(Req({"base": b + "/v1", "key": "k", "add": True}))
    check("a seller with no list asks for a model name", not r.get("ok") and r.get("need_models"), r)
    r = await main.openai_compat_connect(Req({"base": b + "/v1", "key": "k", "add": True, "models": "only-one"}))
    d = await listed(OA)
    check("...and the typed name is what the picker shows", r.get("ok") and d["models"] == ["only-one"], d)

    # ---- 7. Claude Compatible: same envelopes, typed names kept ----
    for mode, want in (("openai", ["zeta", "alpha"]), ("bare", ["m-a", "m-b"]), ("named", ["g-1", "g-2", "g-3"])):
        reset()
        b = gateway(mode)
        r = await main.anthropic_compat_connect(Req({"base": b, "key": "k", "add": True}))
        check(f"Claude Compatible connects to a gateway answering the {mode!r} shape", r.get("ok") and r.get("listed"), r)
        d = await listed(AC)
        check(f"...and the picker lists its models ({mode})", d["models"] == want, d)
    reset()
    b = gateway("silent")
    r = await main.anthropic_compat_connect(Req({"base": b, "key": "k", "add": True, "models": "claude-x"}))
    d = await listed(AC)
    check("Claude Compatible with no list shows the typed model", r.get("ok") and d["models"] == ["claude-x"], d)

    # ---- 8. a website that answers every path with a page is not an API ----
    reset()
    b = gateway("site_only")
    r = await main.openai_compat_connect(Req({"base": b, "key": "k", "add": True, "models": "typed"}))
    check("OpenAI Compatible refuses an address where only a web page answers", not r.get("ok")
          and not adv_keys.gateways(model(), OA) and "/v1" in r.get("error", ""), r)
    r = await main.anthropic_compat_connect(Req({"base": b + "/panel", "key": "k", "add": True, "models": "typed"}))
    check("Claude Compatible refuses it too", not r.get("ok") and not adv_keys.gateways(model(), AC), r)
    reset()
    b = gateway("site")   # the API is under /v1, the website everywhere else
    r = await main.openai_compat_connect(Req({"base": b, "key": "k", "add": True}))
    check("a site with its API under /v1 connects there", r.get("ok") and model()["openai_compat_base"] == b + "/v1", r)

    # ---- 9. remembering a list never undoes what was saved while the gateway was being asked ----
    reset()
    b = gateway("openai")
    await main.openai_compat_connect(Req({"base": b + "/v1", "key": "k", "add": True}))
    stale = cfgmod.read_settings()                       # read before "the network call"
    fresh = cfgmod.read_settings()
    fresh["model"]["groq_api_key"] = "saved-meanwhile"   # the owner saves a key on another card meanwhile
    cfgmod.write_settings(fresh)
    main._remember_catalog(stale, main._provider_def(OA), ["new-1", "new-2"])
    m = model()
    check("the list is remembered", m["catalog"][OA] == ["new-1", "new-2"], m["catalog"].get(OA))
    check("what was saved meanwhile is still there", m.get("groq_api_key") == "saved-meanwhile", m.get("groq_api_key"))

    # the card moved to another gateway while the first was being asked: its list is not kept under the new one
    reset()
    b1, b2 = gateway("openai"), gateway("bare")
    await main.openai_compat_connect(Req({"base": b1 + "/v1", "key": "k1", "add": True}))
    real = main._fetch_provider_models

    async def slow(provider, m):
        ids = await real(provider, m)
        cfg = cfgmod.read_settings()   # meanwhile the owner removes gateway 1 and connects gateway 2
        adv_keys.forget(cfg["model"], OA)
        adv_keys.add(cfg["model"], OA, "two", b2 + "/v1", "k2", ["m-a", "m-b"])
        cfgmod.write_settings(cfg)
        return ids

    main._fetch_provider_models = slow
    try:
        main._PROV_MODELS_CACHE.clear()
        await main.provider_models_index(OA)
    finally:
        main._fetch_provider_models = real
    check("a list fetched for the gateway before is not kept for the new one",
          OA not in main._PROV_MODELS_CACHE and model()["catalog"].get(OA) == ["m-a", "m-b"], model()["catalog"].get(OA))
    d = await main.provider_models_index(OA)
    check("the next ask lists the new gateway", d["models"] == ["m-a", "m-b"], d)


asyncio.run(run())

if fails:
    print(f"\n{len(fails)} FAILED:")
    for f in fails:
        print("  - " + f)
    raise SystemExit(1)
print("\nAll green.")
