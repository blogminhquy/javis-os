"""A channel declares its account form as data (`TOKEN_FORM`), and only a safe shape reaches the dashboard.

    python tests/run.py channel_token_form

No server. Calls `channels._token_form` on stand-in modules, then reads conversations.js for the wiring.

Guarded here:
1. A well-formed form keeps its fields, labels resolve to one language, `webhook_params` only names real fields.
2. Option URLs must be /ext/ plugin routes: a core route, an absolute URL or a traversal drops that field.
3. Bad keys, unknown field types and odd attributes are dropped field by field; no fields = no form.
4. A broken TOKEN_FORM never takes the channel list down.
5. The dashboard draws the declared form on both the Add and Edit forms and posts ONE JSON token.
6. `generate` is kept only as exactly true on a text or password field.
"""
from _paths import ROOT, SERVER, DASHBOARD  # noqa: E402,F401
import os
import tempfile
import types

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-token-form-"))

import channels  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:400] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


def mod(form):
    m = types.ModuleType("stand_in")
    m.TOKEN_FORM = form
    return m


good = {
    "fields": [
        {"key": "connection_id", "type": "select", "label": {"vi": "Workspace", "en": "Workspace"},
         "options": {"url": "/ext/demo-pack/connections", "list": "connections", "value": "id",
                     "label": "{label}", "auto_single": True}},
        {"key": "api_key", "type": "password", "label": "API key", "required_unless": "connection_id",
         "hidden_when": "connection_id"},
        {"key": "account", "type": "select", "send": False, "label": "Account",
         "options": {"url": "/ext/demo-pack/accounts", "list": "accounts", "value": "id",
                     "label": "@{username}", "from": ["connection_id", "api_key"],
                     "fill": {"account_id": "id", "bad key!": "x"}}},
        {"key": "account_id", "type": "text", "label": "Account ID", "required": True, "initial": "meta.account_id"},
        {"key": "username", "type": "text", "label": "Username", "initial": "external_id"},
    ],
    "webhook_params": {"ws": "connection_id", "x": "not_a_field"},
}
f = channels._token_form(mod(good))
keys = [x["key"] for x in f.get("fields", [])]
check("1. fields kept in order", keys == ["connection_id", "api_key", "account", "account_id", "username"], keys)
check("1. dict label resolved to a string", isinstance(f["fields"][0]["label"], str) and f["fields"][0]["label"])
check("1. send flag", f["fields"][2]["send"] is False and f["fields"][1]["send"] is True)
check("1. dependencies kept", f["fields"][2]["options"]["from"] == ["connection_id", "api_key"])
check("1. fill drops a bad key", f["fields"][2]["options"]["fill"] == {"account_id": "id"}, f["fields"][2]["options"])
check("1. initial kept", f["fields"][3].get("initial") == "meta.account_id" and f["fields"][4].get("initial") == "external_id")
check("1. webhook_params only real fields", f["webhook_params"] == {"ws": "connection_id"}, f["webhook_params"])

for bad in ("/channels/accounts", "https://evil.example/x", "//evil.example/ext/a/b", "/ext/a/../../channels",
            "/ext/a", "/ext/a/b?x=1", "javascript:alert(1)"):
    r = channels._token_form(mod({"fields": [{"key": "s", "type": "select", "label": "S",
                                              "options": {"url": bad}}]}))
    check(f"2. option url refused: {bad}", r == {}, r)

r = channels._token_form(mod({"fields": [
    {"key": "Bad-Key", "type": "text", "label": "x"},
    {"key": "ok", "type": "textarea", "label": "x"},
    {"key": "fine", "type": "text", "label": "Fine", "initial": "token", "onclick": "alert(1)", "hidden_when": "a b"},
]}))
check("3. only the valid field survives", [x["key"] for x in r.get("fields", [])] == ["fine"], r)
check("3. unknown attributes dropped", set(r["fields"][0]) == {"key", "type", "label", "hint", "required", "send"}, r)
check("3. no fields = no form", channels._token_form(mod({"fields": [{"key": "1x", "type": "text"}]})) == {})
check("3. no TOKEN_FORM = no form", channels._token_form(types.ModuleType("x")) == {})
check("3. too many fields capped", len(channels._token_form(mod({"fields": [
    {"key": f"f{i}", "type": "text", "label": "x"} for i in range(30)]}))["fields"]) == 12)

check("4. broken form = no form", channels._token_form(mod({"fields": [{"key": "s", "type": "select", "label": "x",
                                                                         "options": {"url": "/ext/a/b", "from": 5}}]})) == {})
ui = channels.cho_giao_dien()
check("4. channel list carries token_form for every channel", ui and all("token_form" in k for k in ui))

js = (DASHBOARD / "conversations.js").read_text(encoding="utf-8")
gf = channels._token_form(mod({"fields": [
    {"key": "secret", "type": "password", "label": "S", "generate": True},
    {"key": "plain", "type": "text", "label": "P", "generate": "yes"},
    {"key": "pick", "type": "select", "label": "C", "generate": True,
     "options": {"url": "/ext/demo-pack/x/y", "list": "items"}}]}))
gk = {x["key"]: x for x in gf["fields"]}
check("6. generate kept on a password field", gk["secret"].get("generate") is True)
check("6. generate must be exactly true", "generate" not in gk["plain"])
check("6. generate ignored on a select", "generate" not in gk["pick"])
check("5. renderer exists", "function drawTokenForm(host, form, account, onChange, covered)" in js)
check("5. add form uses it", "tokenForm = fhost.hidden ? null : drawTokenForm(fhost, k.token_form, null" in js)
check("5. edit form uses it", "drawTokenForm(box.querySelector(\"#htFormTK\"), k.token_form, a, null, coveredNetworks())" in js)
check("5. both forms send the duplicate acknowledgement", js.count("dup_ack") >= 2)
check("5. one JSON token", "return JSON.stringify(out);" in js)
check("5. dependent list is a POST body", "await api(op.url, { method: \"POST\", body: fd(body) })" in js)
check("5. no Zernio branch in the dashboard", "zernio" not in js.lower())

print("\n" + ("ALL OK" if not fails else f"{len(fails)} FAIL: {fails}"))
raise SystemExit(1 if fails else 0)
