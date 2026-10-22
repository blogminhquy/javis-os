"""0.274.0: fixes from the independent review of webhook platform M3 (actions, branches), each red before the fix.

    python tests/run.py webhook_m3_review      (no network: httpx.MockTransport; no model: fake runners)

P1 a stored header key followed its action to a NEW address (waiting event, or a masked view saved back);
P2 hung plain-function plugin handlers used up the shared thread pool and froze the server;
P2 a waiting event's AI branch was cancelled (and the event reported done) when the owner edited the actions;
P2 Apps Script timed out after 15 s (doc: 30); a deployment asking to sign in was "unknown" instead of failed;
P2 an unknown branch stopped a busy sibling's resend; Mark done then turned the event failed;
P2 a 302/303 after a POST (Post/Redirect/Get) counted as "certainly refused";
P3 late outcome kept; a run given up on is stopped; [SILENT] text not sent; owner retry gets fresh tries; HTTP-date
   Retry-After; "allow_private": "false"; non-ASCII header values; header case; test events flagged; capped reads;
   refused-before-dispatch branches release the business key.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

STATE = Path(tempfile.mkdtemp(prefix="javis-wh-m3r-"))
os.environ["JAVIS_STATE_DIR"] = str(STATE)
os.environ["JAVIS_NO_REAL_JUDGE_ENGINE"] = "1"
os.environ["JAVIS_WH_NO_NETWORK"] = "1"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx  # noqa: E402
import webhook_actions as wa  # noqa: E402
import webhook_store as ws  # noqa: E402
import webhook_triggers as wt  # noqa: E402

fails = []


def admit(st):
    for r in st.triage_candidates(1000, now=time.time() + 10 ** 6):
        st.triage_commit(r["id"], {"decision": "run"}, [])


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


PUBLIC = lambda h: ["93.184.216.34"]  # noqa: E731
SCRIPT = "https://script.google.com/macros/s/AKfycbx_TEST_DEPLOYMENT_123/exec"
CTX = {"event_id": "ev_1", "hook_id": "wh_1", "action_id": "a", "received_at": 1.0, "delivery_id": "dlv_x",
       "fields": {}, "payload": {}, "body": b"{}", "content_type": "application/json", "brain": "/b"}

# ---- validation-level fixes ----
check("P2: Apps Script waits 30 s by default", wa.validate([{"id": "s", "kind": "apps_script", "url": SCRIPT}])[0]["timeout_s"] == 30.0)
try:
    wa.validate([{"id": "a", "kind": "http", "url": "http://10.0.0.1/x", "allow_private": "false"}])
    ap = "accepted"
except wa.ActionError as e:
    ap = str(e)
check("P3: allow_private must be the boolean true", "https" in ap, ap)
check("P3: allow_private true still works", wa.validate([{"id": "a", "kind": "http", "url": "http://10.0.0.1/x",
                                                          "allow_private": True}])[0]["allow_private"] is True)
for bad in ("clé-é", "a\tb", "x\x00"):
    try:
        wa.validate([{"id": "a", "kind": "http", "url": "https://x.vn", "headers": {"X-K": bad}}])
        r = "accepted"
    except wa.ActionError as e:
        r = str(e)
    check(f"P3: header value {bad!r} refused at save (it could not be sent)", "ASCII" in r, r)
h = wa._headers({"headers": {"content-type": "application/vnd.x+json", "user-agent": "Mine"}}, CTX, "application/json")
check("P3: the owner's Content-Type / User-Agent are not duplicated in another case",
      [k.lower() for k in h].count("content-type") == 1 and [k.lower() for k in h].count("user-agent") == 1
      and h["content-type"] == "application/vnd.x+json")
old = [{"id": "crm", "kind": "http", "url": "https://old.example/h", "allow_private": False, "headers": {"X-K": {"$secret": "s"}}}]
try:
    wa.merge_secrets(wa.validate([{"id": "crm", "kind": "http", "url": "https://attacker.example/h", "headers": {"X-K": "••••"}}]), old)
    mr = "kept"
except wa.ActionError as e:
    mr = str(e)
check("P1: saving the masked view with a NEW address does not carry the stored key", "enter header X-K again" in mr, mr)
kept = wa.merge_secrets(wa.validate([{"id": "crm", "kind": "http", "url": "https://old.example/h", "headers": {"X-K": "••••"}}]), old)
check("P1: same address: the stored key is kept", kept[0]["headers"]["X-K"] == {"$secret": "s"})


# ---- HTTP / Apps Script classification ----
def http(handler, **a):
    act = wa.validate([dict({"id": "a", "kind": "http", "url": "https://crm.example/h"}, **a)])[0]
    return asyncio.run(wa.run_http(act, CTX, httpx.MockTransport(handler), PUBLIC))


for code in (301, 302, 303):
    check(f"P2: {code} after a POST is unknown, not refused", http(lambda r, c=code: httpx.Response(c, headers={"Location": "https://x/"})).status == "unknown")
check("P2: 308 is unknown too (any redirect after the POST may have been done; spec §7)",
      http(lambda r: httpx.Response(308, headers={"Location": "https://x/"})).status == "unknown")
date = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(time.time() + 120))
o = http(lambda r: httpx.Response(429, headers={"Retry-After": date}))
check("P3: Retry-After as an HTTP date", o.status == "retry" and 100 <= o.retry_after <= 121, o.retry_after)
big = "x" * (2 * 1024 * 1024)
o = http(lambda r: httpx.Response(200, text=big))
check("P3: a huge answer is read only up to the cap", o.status == "completed" and len(o.receipt["body"]) <= wa.RESPONSE_KEEP + 1)


def gas(location):
    calls = []

    def h(req):
        calls.append(str(req.url))
        return httpx.Response(302, headers={"Location": location})
    act = wa.validate([{"id": "s", "kind": "apps_script", "url": SCRIPT}])[0]
    return asyncio.run(wa.run_apps_script(act, dict(CTX, action_id="s"), httpx.MockTransport(h), PUBLIC)), calls


o, calls = gas("https://accounts.google.com/ServiceLogin?continue=https://script.google.com/x")
check("P2: Apps Script redirecting to Google sign-in: blocked (the script did not run; fix the deployment), not followed",
      o.status == "blocked" and "Anyone" in o.detail and len(calls) == 1, (o, calls))


# ---- plugin thread pool ----
async def pool_case():
    import threading
    stop = threading.Event()
    old_t = wa.PLUGIN_TIMEOUT_S
    wa.PLUGIN_TIMEOUT_S = 0.2

    def hang(d, c):
        stop.wait(10)
        return {"status": "completed"}
    found = {"handler": hang, "ctx": None, "min_mode": "readonly"}
    act = {"id": "p", "kind": "plugin", "plugin": "x", "handler": "h"}
    outs = []
    for _ in range(wa.PLUGIN_THREADS + 2):
        outs.append((await wa.run_plugin(act, CTX, found, "full")).status)
    t0 = time.perf_counter()
    v = await asyncio.wait_for(asyncio.to_thread(lambda: 42), 2)
    quick = time.perf_counter() - t0
    stop.set()
    wa.PLUGIN_TIMEOUT_S = old_t
    await asyncio.sleep(0.3)
    return outs, v, quick

outs, v, quick = asyncio.run(pool_case())
check("P2: a hung plugin holds at most PLUGIN_PER_SLUG threads of its own pool; its extra calls are not sent (retry "
      "later), so other plugins keep their turn", outs[:wa.PLUGIN_PER_SLUG] == ["unknown"] * wa.PLUGIN_PER_SLUG
      and outs[wa.PLUGIN_PER_SLUG:] == ["retry"] * (len(outs) - wa.PLUGIN_PER_SLUG), outs)
check("P2: the shared thread pool (store calls, ingest) still answers at once", v == 42 and quick < 0.5, quick)

# ---- store: unknown vs retry, resolve, late outcome, retry tries ----
rows = [{"status": "unknown", "next_at": 0}, {"status": "retry", "next_at": 5}]
check("P2: summarize lets a due resend run before deciding unknown", ws.Store.summarize(rows) == ("queued", 5))
check("P2: unknown once nothing is left to run", ws.Store.summarize([{"status": "unknown", "next_at": 0},
                                                                    {"status": "completed", "next_at": 0}])[0] == "unknown")
st = ws.Store(Path(tempfile.mkdtemp(prefix="m3r-")) / "e.sqlite3")
c, i = st.ingest({"id": "wh_x", "brain": "/b"}, b"{}", "", "k1")
admit(st)
w = st.claim("W")
st.branches_init(w["id"], w["fence"], [{"id": "crm", "kind": "http"}, {"id": "sheet", "kind": "apps_script"}], wa.delivery_id)
st.branch_dispatch(w["id"], w["fence"], "crm"); st.branch_finish(w["id"], w["fence"], "crm", "unknown", "HTTP 500")
st.branch_dispatch(w["id"], w["fence"], "sheet"); st.branch_finish(w["id"], w["fence"], "sheet", "retry", "HTTP 503", next_at=time.time() + 999)
st.finish(w["id"], w["fence"], "unknown", "", "x")          # as an older build would have left it
ok, _ = st.resolve(w["id"], "done", "checked")
ev = st.get(w["id"])
check("P2: Mark done with a sibling still to resend: the event goes back to the queue, not failed",
      ok and ev["status"] == "queued" and {b["action_id"]: b["status"] for b in ev["branches"]} == {"crm": "completed", "sheet": "retry"}, ev["status"])
st.branch_late(w["id"], "crm", "completed", "HTTP 200", {"id": "CRM-991"}, "")
check("P3: a late outcome is kept next to the branch", "CRM-991" in [b for b in st.get(w["id"])["branches"] if b["action_id"] == "crm"][0]["detail"])
c, i2 = st.ingest({"id": "wh_y", "brain": "/b"}, b"{}", "", "k2")
admit(st)
w = st.claim("W")
while w and w["id"] != i2["event_id"]:
    st.finish(w["id"], w["fence"], "done"); w = st.claim("W")
st.branches_init(w["id"], w["fence"], [{"id": "crm", "kind": "http"}], wa.delivery_id)
for _ in range(3):
    st._db.execute("UPDATE deliveries SET status='retry' WHERE event_id=?", (w["id"],))
    st.branch_dispatch(w["id"], w["fence"], "crm")
st.branch_finish(w["id"], w["fence"], "crm", "failed", "HTTP 503 x3")
st.finish(w["id"], w["fence"], "failed", "", "x")
st.retry(w["id"])
check("P3: the owner's retry gives a branch fresh tries", st.get(w["id"])["branches"][0]["tries"] == 0)

# a branch refused before dispatch (permission) does not hold the business key once the event dies
st2 = ws.Store(Path(tempfile.mkdtemp(prefix="m3r-k-")) / "e.sqlite3")
pre = {"decision": "run", "business_key": {"shared": "s", "policy": 1, "hash": "order:1", "ttl_s": 3600}}
c, i3 = st2.ingest({"id": "wh_k", "brain": "/b"}, b"{}", "", "h:kk")
st2.triage_commit(i3["event_id"], pre, [])
w = st2.claim("W")
st2.branches_init(w["id"], w["fence"], [{"id": "crm", "kind": "http"}], wa.delivery_id)
st2.branch_finish(w["id"], w["fence"], "crm", "failed", "needs level full")
st2.finish(w["id"], w["fence"], "failed", "", "needs level full")
st2.retry(w["id"])
w = st2.claim("W")
st2.finish(w["id"], w["fence"], "dead", "", "hook switched off")
c2, i4 = st2.ingest({"id": "wh_k2", "brain": "/b"}, b"{}", "", "h:kk2")
check("P3: refused before dispatch, then dead: the business key is given back",
      st2.triage_commit(i4["event_id"], pre, []) == "queued")

# ---- through the feature ----
FEAT = Path(tempfile.mkdtemp(prefix="m3r-feat-"))
ai_calls, sent, hits = [], [], []
ai_answer = {"v": ("Đã ghi.", "")}


async def run_task(brain, text, level):
    ai_calls.append(level)
    if ai_answer["v"] == "SLOW":
        try:
            await asyncio.sleep(3)
        except asyncio.CancelledError:
            ai_calls.append("CANCELLED")
            raise
        return "late", ""
    return ai_answer["v"]


async def no_wf(*a, **k):
    return "", "", False


async def send(chat_id, text, viec=None, web="", brain="", dedup=""):
    sent.append(text)
    return True, ""


answers = {}


def handler(req):
    body = json.loads(req.content or b"{}") if req.method == "POST" else {}
    hits.append((req.url.host, req.headers.get("x-k"), body.get("_javis", {}).get("test")))
    seq = answers.get(req.url.host, [200])
    code = seq.pop(0) if len(seq) > 1 else seq[0]
    return httpx.Response(code, headers={"Retry-After": "0"})


def make():
    return wt.WebhookFeature(wt.WebhookDeps(state_dir=lambda: FEAT, run_task=run_task, run_workflow=no_wf, send=send,
                                            base_url=lambda _r: "", workflow_exists=lambda b, s: True,
                                            http_transport=httpx.MockTransport(handler), resolve=PUBLIC))


async def drain(f, rounds=12):
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

    # P1: waiting event, owner moves the action to a new address with a new key
    h, tok, _ = f.create("/b1", name="CRM", target="", text="", level="full",
                         actions=[{"id": "crm", "kind": "http", "url": "https://old.example/h", "headers": {"X-K": "OLD-KEY"}}])
    f._kick = lambda: None
    code, r = await f.accept(h["id"], tok, b"{}", "application/json", "p1")
    _, err, _ = f.update(h["id"], {"actions": [{"id": "crm", "kind": "http", "url": "https://new.example/h", "headers": {"X-K": "NEW-KEY"}}]})
    del f._kick
    hits.clear()
    f._kick()
    await f.wait_idle()
    ev = st.get(r["run_id"])
    check("P1: the waiting event is NOT sent (old address with the new key, or at all): cancelled",
          not err and not hits and ev["branches"][0]["status"] == "cancelled", (err, hits, ev["branches"]))
    _, err, _ = f.update(h["id"], {"actions": [{"id": "crm", "kind": "http", "url": "https://attacker.example/h", "headers": {"X-K": "••••"}}]})
    check("P1: the masked view saved back with another address is refused", "enter header X-K again" in err, err)
    code, r = await f.accept(h["id"], tok, b"{}", "application/json", "p1b")
    await f.wait_idle()
    check("P1: new events go to the new address with the new key only", hits == [("new.example", "NEW-KEY", None)], hits)

    # P2: AI branch identity
    h2, tok2, _ = f.create("/b1", name="AI", target="task", text="Ghi", level="full")
    f._kick = lambda: None
    code, r = await f.accept(h2["id"], tok2, b"{}", "application/json", "a1")
    f.update(h2["id"], {"actions": [{"id": "ai", "kind": "ai"}, {"id": "crm", "kind": "http", "url": "https://c.example/h"}]})
    del f._kick
    ai_calls.clear()
    f._kick()
    await f.wait_idle()
    ev = st.get(r["run_id"])
    check("P2: an event that arrived before actions were added still runs its AI task", ai_calls == ["full"]
          and ev["status"] == "done" and ev["branches"][0]["status"] == "completed", (ai_calls, ev["branches"]))
    f._kick = lambda: None
    code, r = await f.accept(h2["id"], tok2, b"{}", "application/json", "a2")
    f.update(h2["id"], {"actions": []})
    del f._kick
    ai_calls.clear()
    f._kick()
    await f.wait_idle()
    ev = st.get(r["run_id"])
    check("P2: actions removed (back to a plain task): the AI still runs, the HTTP action is cancelled",
          ai_calls == ["full"] and {b["action_id"]: b["status"] for b in ev["branches"]} == {"ai": "completed", "crm": "cancelled"},
          ev["branches"])

    # P2: unknown sibling does not stop a resend
    answers.update({"u.example": [500], "b.example": [429, 200]})
    h3, tok3, _ = f.create("/b1", name="Hai", target="", text="", level="full",
                           actions=[{"id": "crm", "kind": "http", "url": "https://u.example/h"},
                                    {"id": "sheet", "kind": "http", "url": "https://b.example/h"}])
    hits.clear()
    code, r = await f.accept(h3["id"], tok3, b"{}", "application/json", "u1")
    await drain(f)
    ev = st.get(r["run_id"])
    check("P2: the busy sibling is resent even though another branch is unknown; then the event is unknown",
          sum(1 for x in hits if x[0] == "b.example") == 2 and ev["status"] == "unknown"
          and {b["action_id"]: b["status"] for b in ev["branches"]} == {"crm": "unknown", "sheet": "completed"}, (hits, ev["branches"]))

    # P3: [SILENT] text not sent with actions
    ai_answer["v"] = ("[SILENT] không có gì", "")
    h4, tok4, _ = f.create("/b1", name="Im", target="task", text="x", level="full",
                           actions=[{"id": "ai", "kind": "ai"}, {"id": "crm", "kind": "http", "url": "https://c.example/h"}])
    sent.clear()
    await f.accept(h4["id"], tok4, b"{}", "application/json", "s1")
    await f.wait_idle()
    check("P3: a [SILENT] AI result is not in the notice", sent and not any("[SILENT]" in m for m in sent), sent)
    ai_answer["v"] = ("Đã ghi.", "")

    # P3: test events are flagged
    hits.clear()
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(f.router)
    cl = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    await cl.post("/webhooks/test", json={"id": h["id"], "confirm": True})
    await f.wait_idle()
    await cl.aclose()
    check("P3: an event sent from the dashboard Test button is flagged _javis.test", hits and hits[-1][2] is True, hits)

    # P3: a run given up on (lease lost) is stopped
    old_hb = ws.HEARTBEAT_S
    ws.HEARTBEAT_S = 0.1
    ai_answer["v"] = "SLOW"
    h5, tok5, _ = f.create("/b1", name="Chậm", target="task", text="x", level="full")
    ai_calls.clear()
    code, r = await f.accept(h5["id"], tok5, b"{}", "application/json", "slow")
    await asyncio.sleep(0.3)
    await asyncio.to_thread(st.recover, time.time() + ws.LEASE_S + 5)
    await asyncio.sleep(0.5)
    await f.wait_idle()
    ws.HEARTBEAT_S = old_hb
    ai_answer["v"] = ("Đã ghi.", "")
    check("P3: when recovery takes the event over, the old run is stopped (no two runs at once)",
          "CANCELLED" in ai_calls and st.get(r["run_id"])["status"] == "unknown", (ai_calls, st.get(r["run_id"])["status"]))


asyncio.run(main())

src = (SERVER / "main.py").read_text(encoding="utf-8")
check("P3: a brain folder that is gone looks up no brain's vault plugins (not the default brain's)",
      "else None), slug, name)" in src)

if fails:
    print(f"\nFAIL {len(fails)}: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_webhook_m3_review: all pass")
