"""0.274.0: webhook actions (webhook platform M3): HTTP forward, Apps Script with receipt, plugin handlers,
independent branches with stable delivery ids, retry of the failed branch only.

    python tests/run.py webhook_actions_m3      (no network: every HTTP call goes to an httpx.MockTransport, every
                                                 plugin is a fake, every model runner raises if called)

What is proven here:
  1. actions are validated when saved (https only, Apps Script address shape, no cookie/host/idempotency headers, no
     header injection, at most one AI action) and header values never leave the server (masked in the view);
  2. HTTP outcomes are classified without guessing: 2xx completed, 202 accepted, 429/503/not-sent retried with the
     SAME delivery id, a timeout or 5xx after sending is unknown (re-sent only when the action says the receiver
     dedups), 4xx failed, redirects not followed; private and metadata addresses are refused;
  3. Apps Script: one POST, the 302 is read with a GET on Google's echo host and its JSON is the receipt; a sign-in
     page, a refusal or another delivery's receipt is not a success; the POST is never repeated;
  4. plugin handlers answer completed/accepted, get a stable delivery id, are found only for the hook's brain, are
     held to their min_mode against the hook's CURRENT level, and a hung plugin is unknown, not retried;
  5. branches are independent: one failing does not stop the others; a retry (automatic or by the owner) runs only
     the branches that are not done; a crash mid-branch leaves that branch unknown and nothing is re-run on its own;
  6. an action removed since the event arrived does not run; lowering the level applies to waiting events;
  7. a hook without an AI action never calls a model, not even through incident triage.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

STATE = Path(tempfile.mkdtemp(prefix="javis-wh-m3-"))
os.environ["JAVIS_STATE_DIR"] = str(STATE)
os.environ["JAVIS_NO_REAL_JUDGE_ENGINE"] = "1"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx  # noqa: E402
import webhook_actions as wa  # noqa: E402
import webhook_store as ws  # noqa: E402
import webhook_triggers as wt  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


def refused(actions) -> str:
    try:
        wa.validate(actions)
        return ""
    except wa.ActionError as e:
        return str(e) or "refused"


PUBLIC = lambda host: ["93.184.216.34"]      # noqa: E731  fake DNS: every name is public
SCRIPT = "https://script.google.com/macros/s/AKfycbx_TEST_DEPLOYMENT_123/exec"

# ---- 1. validation ----
check("valid list normalised", wa.validate([{"id": "crm", "kind": "http", "url": "https://x.vn/h"}])[0]
      == {"id": "crm", "kind": "http", "url": "https://x.vn/h", "body": "fields", "headers": {}, "timeout_s": 15.0,
          "retry": "never", "retry_safety": "manual_on_ambiguous", "allow_private": False, "delivery_ref": "header"})
sp = wa.validate([{"id": "to_apps_script", "type": "http_forward", "url": SCRIPT, "body_mode": "raw",
                   "redirect_profile": "google_apps_script", "retry_safety": "manual_on_ambiguous", "depends_on": []},
                  {"id": "to_poscake_zalo", "type": "plugin", "plugin": "poscake-zalo", "handler": "order_received",
                   "depends_on": []}])
check("the spec's own action format (§9) is read: type, body_mode, redirect_profile, retry_safety",
      sp[0]["kind"] == "apps_script" and sp[0]["body"] == "raw" and sp[0]["retry"] == "never"
      and sp[1]["kind"] == "plugin")
check("plain http refused", "https" in refused([{"id": "a", "kind": "http", "url": "http://x.vn"}]))
check("credentials in the address refused", "bad address" in refused([{"id": "a", "kind": "http", "url": "https://u:p@x.vn"}]))
check("Apps Script must be a /exec web app", "/exec" in refused([{"id": "a", "kind": "apps_script", "url": "https://evil.com/macros/s/x/exec"}])
      and not refused([{"id": "a", "kind": "apps_script", "url": SCRIPT}]))
for hname in ("Cookie", "Host", "Idempotency-Key", "X-Javis-Delivery", "Content-Length"):
    check(f"header {hname} cannot be set by the owner", "not allowed" in refused(
        [{"id": "a", "kind": "http", "url": "https://x.vn", "headers": {hname: "v"}}]))
check("header injection refused", "one line" in refused([{"id": "a", "kind": "http", "url": "https://x.vn",
                                                           "headers": {"X-A": "v\r\nCookie: s=1"}}]))
check("duplicate ids, unknown kind, too many, two AI actions refused",
      "twice" in refused([{"id": "a", "kind": "ai"}, {"id": "a", "kind": "ai"}])
      and "kind" in refused([{"id": "a", "kind": "shell"}])
      and "at most" in refused([{"id": f"a{i}", "kind": "http", "url": "https://x.vn"} for i in range(11)])
      and not refused([{"id": f"a{i}", "kind": "http", "url": "https://x.vn"} for i in range(10)])
      and "one ai" in refused([{"id": "a", "kind": "ai"}, {"id": "b", "kind": "ai"}]))
check("plugin action needs slug and handler", "needs" in refused([{"id": "a", "kind": "plugin", "plugin": "x"}]))
v = wa.view([{"id": "a", "kind": "http", "url": "https://x.vn", "headers": {"X-Api-Key": "sk-SECRET"}}])
check("the view masks header values", v[0]["headers"] == {"X-Api-Key": "••••"} and "sk-SECRET" not in json.dumps(v))
merged = wa.merge_secrets(wa.validate([{"id": "a", "kind": "http", "url": "https://x.vn", "headers": {"X-Api-Key": "••••", "X-New": "n"}}]),
                          [{"id": "a", "kind": "http", "url": "https://x.vn", "allow_private": False, "headers": {"X-Api-Key": "sk-SECRET"}}])
check("saving the masked view keeps the stored secret", merged[0]["headers"] == {"X-Api-Key": "sk-SECRET", "X-New": "n"})
check("delivery id: stable per (event, action), different across actions",
      wa.delivery_id("ev_1", "crm") == wa.delivery_id("ev_1", "crm") != wa.delivery_id("ev_1", "sheet")
      and wa.delivery_id("ev_1", "crm").startswith("dlv_"))


async def addr(ip, allow=False):
    return await wa.check_address("https://h.example/x", allow, lambda h: [ip])

for ip in ("127.0.0.1", "10.0.0.5", "192.168.1.2", "169.254.169.254", "::1", "::ffff:127.0.0.1", "100.64.1.1", "0.0.0.0", "fd00::1"):
    check(f"address {ip} refused", any(w in asyncio.run(addr(ip)) for w in ("private", "metadata")), asyncio.run(addr(ip)))
check("a cloud metadata address is refused even when the action allows private addresses",
      "metadata" in asyncio.run(addr("169.254.169.254", True)) and asyncio.run(addr("10.0.0.5", True)) == "")
check("public address allowed; private allowed only when the action says so",
      asyncio.run(addr("93.184.216.34")) == "" and asyncio.run(addr("10.0.0.5", True)) == "")
check("a name that resolves to ANY private address is refused", "private" in asyncio.run(
    wa.check_address("https://h/x", False, lambda h: ["93.184.216.34", "10.0.0.1"])))

CTX = {"event_id": "ev_1", "hook_id": "wh_1", "action_id": "crm", "received_at": 1.0, "delivery_id": wa.delivery_id("ev_1", "crm"),
       "fields": {"order_id": "A1"}, "payload": {"x": 1}, "body": b'{"x":1}', "content_type": "application/json", "brain": "/b"}
b, ct = wa.build_body({"body": "fields"}, CTX)
check("body `fields`: mapped fields plus _javis with the delivery id", json.loads(b) == {"order_id": "A1", "_javis": {
    "delivery_id": CTX["delivery_id"], "event_id": "ev_1", "hook_id": "wh_1", "action_id": "crm", "received_at": 1.0}}
      and ct == "application/json")
check("body `raw`: the original body unchanged", wa.build_body({"body": "raw"}, CTX) == (b'{"x":1}', "application/json"))


# ---- 2. HTTP outcomes ----
seen = []


def transport(handler):
    def h(req):
        seen.append(req)
        return handler(req)
    return httpx.MockTransport(h)


def http(handler, **a):
    act = wa.validate([dict({"id": "crm", "kind": "http", "url": "https://crm.example/h"}, **a)])[0]
    return asyncio.run(wa.run_http(act, CTX, transport(handler), PUBLIC))


def raise_(exc):
    def h(req):
        raise exc
    return h


seen.clear()
o = http(lambda r: httpx.Response(200, text="ok"), headers={"X-Api-Key": "k"})
req = seen[-1]
check("200 -> completed, receipt kept", o.status == "completed" and o.receipt["status"] == 200)
check("delivery id sent as Idempotency-Key and X-Javis-Delivery; owner header sent; no cookie or auth forwarded",
      req.headers["idempotency-key"] == CTX["delivery_id"] == req.headers["x-javis-delivery"] and req.headers["x-api-key"] == "k"
      and "cookie" not in req.headers and "authorization" not in req.headers)
check("202 -> accepted", http(lambda r: httpx.Response(202)).status == "accepted")
o = http(lambda r: httpx.Response(429, headers={"Retry-After": "40"}))
check("429 -> retry with Retry-After", o.status == "retry" and o.retry_after == 40)
check("503 -> unknown: a 5xx after sending may have acted (spec §7), not re-sent blindly",
      http(lambda r: httpx.Response(503)).status == "unknown")
check("503 at a receiver declared idempotent -> retry_wait", http(lambda r: httpx.Response(503),
                                                                  retry_safety="idempotent").status == "retry")
check("401 / 403 -> blocked (fix the credential), never retried in a loop",
      http(lambda r: httpx.Response(401)).status == "blocked" and http(lambda r: httpx.Response(403)).status == "blocked")
seen.clear()
http(lambda r: httpx.Response(200))
check("the event id rides along as X-Javis-Event-Id", seen[-1].headers["x-javis-event-id"] == "ev_1")
check("500 -> unknown (it may have been done)", http(lambda r: httpx.Response(500)).status == "unknown")
check("500 with retry=safe -> retry (the receiver dedups on the delivery id)",
      http(lambda r: httpx.Response(500), retry="safe").status == "retry")
check("400 -> failed", http(lambda r: httpx.Response(400)).status == "failed")
seen.clear()
o = http(lambda r: httpx.Response(302, headers={"Location": "http://169.254.169.254/"}))
check("302 after a POST -> unknown (Post/Redirect/Get: it may have been done), redirect not followed",
      o.status == "unknown" and len(seen) == 1)
check("307 -> unknown (the receiver may have taken the body before redirecting; spec §7), not followed",
      http(lambda r: httpx.Response(307, headers={"Location": "https://x/"})).status == "unknown")
check("connect error -> retry (never sent)", http(raise_(httpx.ConnectError("refused"))).status == "retry")
check("read timeout -> unknown", http(raise_(httpx.ReadTimeout("slow"))).status == "unknown")
check("dropped connection -> unknown", http(raise_(httpx.RemoteProtocolError("eof"))).status == "unknown")
seen.clear()
act = wa.validate([{"id": "crm", "kind": "http", "url": "https://crm.example/h"}])[0]
o = asyncio.run(wa.run_http(act, CTX, transport(lambda r: httpx.Response(200)), lambda h: ["10.1.2.3"]))
check("an address resolving to a private IP is refused before any request", o.status == "failed" and not seen)
os.environ["JAVIS_WH_NO_NETWORK"] = "1"
o = asyncio.run(wa.run_http(act, CTX, None, PUBLIC))
check("JAVIS_WH_NO_NETWORK: the default transport refuses (tests cannot reach the network)",
      o.status == "retry" and "not sent" in o.detail, o)

# ---- 3. Apps Script ----
ECHO = "https://script.googleusercontent.com/macros/echo?user_content_key=abc&lib=x"


def gas(receipt_text, echo_status=200, location=ECHO, first_status=302):
    calls = []

    def h(req):
        calls.append((req.method, str(req.url), req.content, dict(req.headers)))
        if req.url.host == "script.google.com":
            if first_status == 302:
                return httpx.Response(302, headers={"Location": location})
            return httpx.Response(first_status, text=receipt_text)
        return httpx.Response(echo_status, text=receipt_text)
    act = wa.validate([{"id": "sheet", "kind": "apps_script", "url": SCRIPT, "headers": {"X-Secret": "s"}}])[0]
    ctx = dict(CTX, action_id="sheet", delivery_id=wa.delivery_id("ev_1", "sheet"))
    return asyncio.run(wa.run_apps_script(act, ctx, httpx.MockTransport(h), PUBLIC)), calls, ctx["delivery_id"]


did = wa.delivery_id("ev_1", "sheet")
o, calls, _ = gas(json.dumps({"ok": True, "delivery_id": did, "row": 12}))
check("Apps Script: POST once, then GET the echo page; receipt ok -> completed",
      o.status == "completed" and [c[0] for c in calls] == ["POST", "GET"] and calls[1][2] == b""
      and "x-secret" not in {k.lower() for k in calls[1][3]} and o.receipt["receipt"]["row"] == 12, (o, calls))
o, _, _ = gas(json.dumps({"ok": True, "delivery_id": did, "duplicate": True}))
check("Apps Script: a receipt saying it had this delivery already is completed", o.status == "completed")
o, _, _ = gas(json.dumps({"ok": False, "error": "sheet locked"}))
check("Apps Script: ok false -> failed with its reason", o.status == "failed" and "sheet locked" in o.detail)
o, _, _ = gas("<html>accounts.google.com sign in</html>", first_status=200)
check("Apps Script: a sign-in page is not a receipt, and says how to fix it", o.status == "failed" and "Anyone" in o.detail)
o, _, _ = gas("<html>TypeError in doPost</html>")
check("Apps Script: a page that is not a receipt AFTER the echo hop is unknown (doPost already ran), never a failure "
      "the owner would retry into a second row", o.status == "unknown" and o.maybe_acted is True, o)
o, _, _ = gas(json.dumps({"ok": True, "delivery_id": "dlv_other"}), first_status=200)
check("Apps Script: a receipt naming another delivery is not ours", o.status == "failed")
o, _, _ = gas(json.dumps({"ok": True, "delivery_id": "dlv_other"}))
check("Apps Script: the same through the echo hop is unknown (the script ran, under what id is unclear)",
      o.status == "unknown")
o, calls, _ = gas("{}", location="https://evil.example/steal")
check("Apps Script: redirect to another host -> unknown, not followed", o.status == "unknown" and len(calls) == 1)
o, _, _ = gas("{}", echo_status=500)
check("Apps Script: the receipt page fails -> unknown (the script ran)", o.status == "unknown")
o, calls, _ = gas(json.dumps({"ok": True}), first_status=200)
check("Apps Script: a direct 200 with a receipt -> completed", o.status == "completed" and len(calls) == 1)
o, _, _ = gas("", first_status=429)
check("Apps Script: 429 -> retry", o.status == "retry")


# ---- 4. plugin handlers ----
async def plug(handler, level="full", min_mode="safe"):
    act = {"id": "ship", "kind": "plugin", "plugin": "giao-hang", "handler": "new_order"}
    return await wa.run_plugin(act, dict(CTX, action_id="ship"), {"handler": handler, "ctx": None, "min_mode": min_mode}, level)

got = []
o = asyncio.run(plug(lambda d, c: got.append(d) or {"status": "completed", "ref": "VD-9"}))
check("plugin completed with its ref; it receives the delivery id, fields and level",
      o.status == "completed" and o.receipt["ref"] == "VD-9" and got[0]["delivery_id"] == CTX["delivery_id"]
      and got[0]["fields"] == {"order_id": "A1"} and got[0]["level"] == "full")


async def acc(d, c):
    return {"status": "accepted", "ref": "job-1"}

check("plugin accepted (it keeps its own scheduling)", asyncio.run(plug(acc)).status == "accepted")
check("plugin raising -> unknown (it may have acted mid-way)", asyncio.run(plug(lambda d, c: 1 / 0)).status == "unknown")
check("plugin answering anything else -> unknown (contract broken)", asyncio.run(plug(lambda d, c: "done")).status
      == "unknown")
check("plugin results map to the spec's states", [asyncio.run(plug(lambda d, c, s=s: {"status": s})).status for s in
                                                  ("retryable_error", "permanent_error", "unknown", "waiting_approval")]
      == ["retry", "failed", "unknown", "waiting"])
old_t = wa.PLUGIN_TIMEOUT_S
wa.PLUGIN_TIMEOUT_S = 0.2


async def slow(d, c):
    await asyncio.sleep(5)

check("plugin hanging -> unknown (it may have acted), not retried", asyncio.run(plug(slow)).status == "unknown")
check("a slow plain-function plugin also times out without blocking the loop",
      asyncio.run(plug(lambda d, c: time.sleep(1))).status == "unknown")
wa.PLUGIN_TIMEOUT_S = old_t
o = asyncio.run(plug(acc, level="auto", min_mode="full"))
check("plugin min_mode full at hook level auto -> blocked (permission)", o.status == "blocked" and "higher level" in o.detail)
check("plugin not installed or switched off -> blocked", asyncio.run(wa.run_plugin(
    {"id": "s", "kind": "plugin", "plugin": "p", "handler": "h"}, CTX, None, "full")).status == "blocked")

# the real plugin host: register_webhook_handler + find_webhook_handler, scoped by brain
import plugins_host  # noqa: E402
pdir = Path(plugins_host.global_plugins_dir()) / "wh-test"
pdir.mkdir(parents=True, exist_ok=True)
(pdir / "plugin.yaml").write_text("name: WH test\nslug: wh-test\nenabled: true\nmin_mode: readonly\n", encoding="utf-8")
(pdir / "plugin.py").write_text(
    "def register(ctx):\n"
    "    ctx.register_webhook_handler('new_order', lambda d, c: {'status': 'completed', 'ref': d['delivery_id']},"
    " min_mode='safe', description='test')\n", encoding="utf-8")
vault_a = Path(tempfile.mkdtemp(prefix="brain-a-"))
vpd = vault_a / "plugins" / "only-a"
vpd.mkdir(parents=True)
(vpd / "plugin.yaml").write_text("name: Only A\nslug: only-a\nenabled: true\n", encoding="utf-8")
(vpd / "plugin.py").write_text("def register(ctx):\n    ctx.register_webhook_handler('h', lambda d, c: {'status': 'completed'})\n",
                               encoding="utf-8")
vault_b = Path(tempfile.mkdtemp(prefix="brain-b-"))
plugins_host.invalidate()
f1 = plugins_host.find_webhook_handler(str(vault_a), "wh-test", "new_order")
check("plugin host: a global plugin's webhook handler is found with its min_mode", f1 and f1["min_mode"] == "safe", f1)
check("plugin host: a brain's own plugin handler is found for that brain only",
      plugins_host.find_webhook_handler(str(vault_a), "only-a", "h") is not None
      and plugins_host.find_webhook_handler(str(vault_b), "only-a", "h") is None)
check("plugin host: handler listing for the dashboard",
      any(x["plugin"] == "wh-test" and x["handler"] == "new_order" for x in plugins_host.webhook_handlers(str(vault_a))))
check("plugin host: a bad handler name is refused at registration", "register_webhook_handler" in
      (SERVER / "plugins_host.py").read_text(encoding="utf-8") and plugins_host._TOOL_RE.match("Bad-Name") is None)
del os.environ["JAVIS_WH_NO_NETWORK"]

# ---- 5..7 through the feature ----
FEAT = Path(tempfile.mkdtemp(prefix="wh-m3-feat-"))
calls_ai, sent, incidents, plugin_calls, http_calls = [], [], [], [], []
crm = {"answers": [200]}


async def run_task(brain, text, level):
    calls_ai.append(("task", brain, level))
    return "Đã ghi chú đơn.", ""


async def run_workflow(brain, slug, text, level):
    calls_ai.append(("wf", brain, level))
    return "ok", "", False


async def send(chat_id, text, viec=None, web="", brain="", dedup=""):
    sent.append(text)
    return True, ""


def handler(req):
    http_calls.append((req.url.host, req.headers.get("idempotency-key"), req.method))
    if req.url.host == "crm.example":
        code = crm["answers"].pop(0) if len(crm["answers"]) > 1 else crm["answers"][0]
        return httpx.Response(code, headers={"Retry-After": "0"})
    if req.url.host == "script.google.com":
        return httpx.Response(302, headers={"Location": ECHO})
    if req.url.host == "script.googleusercontent.com":
        return httpx.Response(200, text=json.dumps({"ok": True}))
    return httpx.Response(404)


def plugin_handler(brain, slug, name):
    if brain != "/b1" or slug != "giao-hang":
        return None

    def h(d, c):
        plugin_calls.append(d["delivery_id"])
        return {"status": "accepted", "ref": "VD-" + d["event_id"][-4:]}
    return {"handler": h, "ctx": None, "min_mode": "safe"}


def make(**kw):
    deps = dict(state_dir=lambda: FEAT, run_task=run_task, run_workflow=run_workflow, send=send,
                base_url=lambda _r: "https://x", workflow_exists=lambda b, s: True,
                incident_hook=lambda *a, **k: incidents.append(a), plugin_handler=plugin_handler,
                http_transport=httpx.MockTransport(handler), resolve=PUBLIC)
    deps.update(kw)
    return wt.WebhookFeature(wt.WebhookDeps(**deps))


ACTIONS = [{"id": "crm", "kind": "http", "url": "https://crm.example/h", "headers": {"X-Api-Key": "sk-SECRET"}},
           {"id": "sheet", "kind": "apps_script", "url": SCRIPT},
           {"id": "ship", "kind": "plugin", "plugin": "giao-hang", "handler": "new_order"},
           {"id": "ai", "kind": "ai"}]


async def drain(f, rounds=12):
    """wait_idle, then let time pass for deliveries that wait for a later attempt (instead of sleeping minutes)."""
    for _ in range(rounds):
        await f.wait_idle()
        st_ = f.store()
        if not st_._db.execute("SELECT 1 FROM events WHERE status='queued'").fetchone():
            return
        st_._db.execute("UPDATE deliveries SET next_at=0 WHERE status='retry'")
        st_._db.execute("UPDATE events SET next_at=0 WHERE status='queued'")
        f._kick()


async def main():
    f = make()
    st = f.store()
    h, tok, err = f.create("/b1", name="Đơn", target="task", text="Ghi chú đơn", level="full", chat_id="web:1",
                           actions=ACTIONS)
    check("create: hook with four actions", not err and len(f._find(f._load(), h["id"])["actions"]) == 4, err)
    check("create: the view masks the API key", "sk-SECRET" not in json.dumps(f.view(h)))

    code, r1 = await f.accept(h["id"], tok, b'{"order":"A1"}', "application/json", "e1")
    await f.wait_idle()
    ev = st.get(r1["run_id"])
    br = {b["action_id"]: b for b in ev["branches"]}
    check("all four branches ran once, the event is done", code == 202 and ev["status"] == "done"
          and {k: v["status"] for k, v in br.items()} == {"crm": "completed", "sheet": "completed", "ship": "accepted",
                                                         "ai": "completed"}, {k: v["status"] for k, v in br.items()})
    check("each branch carries its own stable delivery id, sent to the receiver",
          br["crm"]["delivery_id"] == wa.delivery_id(r1["run_id"], "crm")
          and ("crm.example", br["crm"]["delivery_id"], "POST") in http_calls
          and plugin_calls == [br["ship"]["delivery_id"]])
    check("the plugin's ref is kept as its receipt", br["ship"]["receipt"]["ref"].startswith("VD-"))
    check("the notice lists the deliveries in the spec's words, never the API key", sent and "crm: succeeded" in sent[-1]
          and "sk-SECRET" not in "".join(sent) and "sk-SECRET" not in json.dumps(ev, default=str), (sent, ev.get("hook_snapshot")))
    n_ai = len(calls_ai)

    # one branch unknown (500): the others are done; the owner's retry runs ONLY that branch
    crm["answers"] = [500, 200]
    http_calls.clear(); plugin_calls.clear()
    code, r2 = await f.accept(h["id"], tok, b'{"order":"A2"}', "application/json", "e2")
    await f.wait_idle()
    ev = st.get(r2["run_id"])
    check("crm 500 -> its branch unknown, the event unknown, the other branches done",
          ev["status"] == "unknown" and {b["action_id"]: b["status"] for b in ev["branches"]}
          == {"crm": "unknown", "sheet": "completed", "ship": "accepted", "ai": "completed"})
    check("nothing is re-sent on its own", sum(1 for c in http_calls if c[0] == "crm.example") == 1)
    ok, _ = st.retry(r2["run_id"])
    f._kick()
    await f.wait_idle()
    ev = st.get(r2["run_id"])
    check("owner retry: only the unknown branch runs again, with the SAME delivery id",
          ok and ev["status"] == "done" and sum(1 for c in http_calls if c[0] == "crm.example") == 2
          and len({c[1] for c in http_calls if c[0] == "crm.example"}) == 1
          and sum(1 for c in http_calls if c[0] == "script.google.com") == 1 and len(plugin_calls) == 1
          and len(calls_ai) == n_ai + 1, (ev["status"], http_calls, plugin_calls))
    check("a completed event cannot be retried", st.retry(r2["run_id"]) == (False, "not_retryable"))

    # 429 then 200: automatic retry of that branch only (the receiver said it did not process it)
    crm["answers"] = [429, 200]
    http_calls.clear(); plugin_calls.clear()
    n_ai = len(calls_ai)
    code, r3 = await f.accept(h["id"], tok, b'{"order":"A3"}', "application/json", "e3")
    await drain(f)
    ev = st.get(r3["run_id"])
    crm_b = [b for b in ev["branches"] if b["action_id"] == "crm"][0]
    check("429 -> that branch re-sent by itself with the same delivery id; the others ran once",
          ev["status"] == "done" and crm_b["tries"] == 2 and sum(1 for c in http_calls if c[0] == "crm.example") == 2
          and len(plugin_calls) == 1 and len(calls_ai) == n_ai + 1, (ev["status"], crm_b, http_calls))
    crm["answers"] = [429]
    code, r4 = await f.accept(h["id"], tok, b'{"order":"A4"}', "application/json", "e4")
    await drain(f)
    ev = st.get(r4["run_id"])
    crm_b = [b for b in ev["branches"] if b["action_id"] == "crm"][0]
    check("still busy after 4 attempts (spec §7) -> dead (certainly not processed); the event partly failed",
          ev["status"] == "failed" and ev["state"] == "partial_failed" and crm_b["status"] == "failed"
          and crm_b["state"] == "dead" and crm_b["tries"] == wa.MAX_BRANCH_TRIES == 4, crm_b)
    crm["answers"] = [200]

    # level lowered: outside branches are refused at run time, the AI branch runs at the lower level
    f.update(h["id"], {"level": "auto"})
    code, r6 = await f.accept(h["id"], tok, b'{"order":"A6"}', "application/json", "e6")
    await f.wait_idle()
    ev = st.get(r6["run_id"])
    bs = {b["action_id"]: b for b in ev["branches"]}
    check("at level auto: HTTP and Apps Script blocked (they send data out), plugin `safe` runs, AI runs at auto",
          bs["crm"]["status"] == "blocked" and "level full" in bs["crm"]["detail"] and bs["sheet"]["status"] == "blocked"
          and bs["ship"]["status"] == "accepted" and calls_ai[-1][2] == "auto", {k: (v["status"], v["detail"]) for k, v in bs.items()})
    http_calls.clear()
    n_ai6, n_pl6 = len(calls_ai), len(plugin_calls)
    f.update(h["id"], {"level": "full"})
    await drain(f)
    ev = st.get(r6["run_id"])
    check("restoring the level runs the blocked deliveries again, the done ones not (spec §7: blocked waits for the fix)",
          ev["status"] == "done" and {b["action_id"]: b["status"] for b in ev["branches"]}["crm"] == "completed"
          and len(calls_ai) == n_ai6 and len(plugin_calls) == n_pl6
          and sum(1 for c in http_calls if c[0] == "crm.example") == 1, (ev["status"], ev["branches"]))

    # an action removed since the event arrived does not run
    f2 = make()
    h2, tok2, _ = f2.create("/b1", name="Gỡ", target="task", text="x", level="full",
                            actions=[{"id": "crm", "kind": "http", "url": "https://crm.example/h"}, {"id": "ai", "kind": "ai"}])
    old_kick = f2._kick
    f2._kick = lambda: None          # hold the event in the queue while the owner edits the hook
    code, r7 = await f2.accept(h2["id"], tok2, b"{}", "application/json", "e7")
    h2v, err, _ = f2.update(h2["id"], {"actions": [{"id": "ai", "kind": "ai"}]})
    f2._kick = old_kick
    http_calls.clear()
    f2._kick()
    await f2.wait_idle()
    ev = f2.store().get(r7["run_id"])
    check("an action removed before the event ran is cancelled, not run", not err and
          {b["action_id"]: b["status"] for b in ev["branches"]} == {"crm": "cancelled", "ai": "completed"}
          and not http_calls and ev["status"] == "done", ev["branches"])

    # a key rotated while the event waits: the run uses the hook's key of NOW; the event store never held it
    keys_seen = []

    def kh(req):
        keys_seen.append(req.headers.get("x-api-key"))
        return httpx.Response(200)
    f5 = make(http_transport=httpx.MockTransport(kh))
    h5, tok5, _ = f5.create("/b1", name="Khoá", target="", text="", level="full",
                            actions=[{"id": "crm", "kind": "http", "url": "https://crm.example/h", "headers": {"X-Api-Key": "old-KEY"}}])
    f5._kick = lambda: None
    code, r10 = await f5.accept(h5["id"], tok5, b"{}", "application/json", "e10")
    f5.update(h5["id"], {"actions": [{"id": "crm", "kind": "http", "url": "https://crm.example/h", "headers": {"X-Api-Key": "new-KEY"}}]})
    del f5._kick
    f5._kick()
    await f5.wait_idle()
    raw = f5.store()._db.execute("SELECT hook_snapshot FROM events WHERE id=?", (r10["run_id"],)).fetchone()[0]
    raw += json.dumps([tuple(r) for r in f5.store()._db.execute("SELECT config FROM hook_revisions")])
    check("a rotated key applies to a waiting event; the event store and the revisions never hold the key",
          keys_seen == ["new-KEY"] and "old-KEY" not in raw and "new-KEY" not in raw, (keys_seen, raw[:200]))

    # a hook without an AI action never reaches a model, not even incident triage
    async def no_model(*a, **k):
        raise AssertionError("a model runner was called for a non-AI hook")
    f3 = make(run_task=no_model, run_workflow=no_model)
    h3, tok3, err = f3.create("/b1", name="Chuyển", target="", text="", level="full",
                              actions=[{"id": "crm", "kind": "http", "url": "https://crm.example/h"}])
    check("create: a hook with only outside actions needs no task text", not err, err)
    crm["answers"] = [400]
    incidents.clear()
    code, r8 = await f3.accept(h3["id"], tok3, b"{}", "application/json", "e8")
    await f3.wait_idle()
    ev = f3.store().get(r8["run_id"])
    check("non-AI hook: failed branch, no model call, no incident triage", ev["status"] == "failed" and not incidents)
    crm["answers"] = [200]

    # a plugin handler of another brain is not found from this brain
    f4 = make()
    h4, tok4, _ = f4.create("/b2", name="Khác brain", target="task", text="x", level="full",
                            actions=[{"id": "ship", "kind": "plugin", "plugin": "giao-hang", "handler": "new_order"}])
    code, r9 = await f4.accept(h4["id"], tok4, b"{}", "application/json", "e9")
    await f4.wait_idle()
    b9 = f4.store().get(r9["run_id"])["branches"][0]
    check("a plugin visible to another brain only is not run from this brain (blocked, not broadcast)",
          b9["status"] == "blocked" and "not installed" in b9["detail"])

    # route: event detail shows branches (no header values)
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(f.router)
    cl = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    r = await cl.get(f"/webhooks/events/{r1['run_id']}")
    check("event detail lists the branches with delivery ids and receipts, no secret",
          r.status_code == 200 and len(r.json()["event"]["branches"]) == 4 and "sk-SECRET" not in r.text)
    r = await cl.post("/webhooks/update", json={"id": h["id"], "actions": f.view(f._find(f._load(), h["id"]))["actions"]})
    check("saving the actions back from the dashboard keeps the stored API key",
          r.status_code == 200 and f._secret(f._find(f._load(), h["id"])["actions"][0]["headers"]["X-Api-Key"]) == "sk-SECRET")
    await cl.aclose()


asyncio.run(main())

# ---- crash in the middle of a branch: child process ----
CRASH_STATE = Path(tempfile.mkdtemp(prefix="wh-m3-crash-"))
CHILD = (
    "import asyncio, os, json, httpx, webhook_triggers as wt, webhook_store as ws\n"
    "from pathlib import Path\n"
    "S = Path(os.environ['JAVIS_STATE_DIR'])\n"
    "async def h(req):\n"
    "    await asyncio.sleep(1.0)   # let the AI branch be dispatched first, so the crash finds both dispatched\n"
    "    (S / 'effects.txt').open('a').write(req.url.host + '\\n')\n"
    "    return httpx.Response(200)\n"
    "async def run_task(b, t, l):\n"
    "    await asyncio.sleep(30)\n"
    "    return 'late', ''\n"
    "async def nop(*a, **k): return '', '', False\n"
    "async def send(*a, **k): return True, ''\n"
    "f = wt.WebhookFeature(wt.WebhookDeps(state_dir=lambda: S, run_task=run_task, run_workflow=nop, send=send,"
    " base_url=lambda r: '', http_transport=httpx.MockTransport(h), resolve=lambda host: ['93.184.216.34']))\n"
    "async def go():\n"
    "    h_, tok, err = f.create('/b', name='C', target='task', text='x', level='full', actions=["
    "{'id': 'crm', 'kind': 'http', 'url': 'https://crm.example/h'}, {'id': 'ai', 'kind': 'ai'}])\n"
    "    print('HOOK', h_['id'], tok, flush=True)\n"
    "    code, resp = await f.accept(h_['id'], tok, b'{}', 'application/json', 'c1')\n"
    "    print('ACK', code, resp['run_id'], flush=True)\n"
    "    await f.wait_idle()\n"
    "asyncio.run(go())\n")
r = subprocess.run([sys.executable, "-c", CHILD], env=dict(os.environ, JAVIS_STATE_DIR=str(CRASH_STATE), PYTHONPATH=str(SERVER),
                                                     JAVIS_WH_CRASH_AT="after_dispatch"),
                   capture_output=True, text=True, timeout=90)
eff = (CRASH_STATE / "effects.txt").read_text().splitlines() if (CRASH_STATE / "effects.txt").exists() else []
check("child: the HTTP branch reached the receiver once, then the process died mid-event",
      r.returncode == 77 and eff == ["crm.example"], (r.returncode, r.stdout, r.stderr[-400:]))
eid = [ln.split()[2] for ln in r.stdout.splitlines() if ln.startswith("ACK")][0]
st = ws.Store(CRASH_STATE / "webhook_events.sqlite3")
rec = st.recover(now=time.time() + ws.LEASE_S + 1)
ev = st.get(eid)
check("recovery: both dispatched branches unknown (one finished its effect, one was mid-run), event unknown",
      ev["status"] == "unknown" and {b["action_id"]: b["status"] for b in ev["branches"]} == {"crm": "unknown", "ai": "unknown"},
      ev["branches"])
check("recovery re-sends nothing", len((CRASH_STATE / "effects.txt").read_text().splitlines()) == 1)
ok, _ = st.resolve(eid, "done", "checked the CRM: order is there")
check("owner reconciles: unknown branches marked done, the event done", ok and st.get(eid)["status"] == "done"
      and all(b["status"] == "completed" for b in st.get(eid)["branches"]))

src = (SERVER / "webhook_actions.py").read_text(encoding="utf-8")
check("no model in the actions module", not any(x in src for x in ("aux_engine", "claude_cli", "anthropic", "run_task")))

if fails:
    print(f"\nFAIL {len(fails)}: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_webhook_actions_m3: all pass")
