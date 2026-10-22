"""0.274.0: fixes from the independent WHOLE-CHAIN review of the webhook platform (M1-M5 together), each red before
the fix.

    python tests/run.py webhook_chain_review      (no network, no model)

P1 a client could pair the hook's own sealed reference with a NEW address (bypassing the mask rule);
P2 a workflow question left an event `waiting` forever (no owner action, never pruned, no cap: the shared store could
   fill and every hook of every brain answer 503);
P2 the M1 poison guard (stop after MAX_AUTO_TRIES losses before dispatch) no longer worked once events had branches;
P2 a read error on webhooks.json turned accepted events into "hook deleted" and let create() wipe the other hooks;
P2 the AI branch of a hook whose brain folder is gone ran in the default brain;
P3 incident triage from a pass where only non-AI branches ran; header values with surrounding spaces; approval asked
   only after a sibling's resend, and an approved branch waiting for the sibling's time; failed events whose business
   key still blocks resends pruned; 4xx refusals opening the breaker; receivers echoing the decrypted key into the
   log; an unbounded body read before the size check.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

STATE = Path(tempfile.mkdtemp(prefix="javis-wh-chain-"))
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


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


FEAT = Path(tempfile.mkdtemp(prefix="chain-feat-"))
hits, ai_calls, incidents, sent = [], [], [], []
answer = {"crm": 200, "echo": False, "ai": ("ok", "")}


def handler(req):
    hits.append((req.url.host, req.headers.get("x-api-key")))
    if answer["echo"]:
        return httpx.Response(200, json={"you_sent": dict(req.headers)})
    return httpx.Response(answer["crm"], headers={"Retry-After": "0"})


async def run_task(brain, text, level):
    ai_calls.append(brain)
    return answer["ai"]


async def run_wf(brain, slug, text, level):
    return "Anh chọn mẫu nào?", "", True


async def send(chat_id, text, viec=None, web="", brain="", dedup=""):
    sent.append({"text": text, "dedup": dedup})
    return True, ""


def make(**kw):
    deps = dict(state_dir=lambda: FEAT, run_task=run_task, run_workflow=run_wf, send=send, base_url=lambda _r: "",
                workflow_exists=lambda b, s: True, incident_hook=lambda *a, **k: incidents.append(a),
                http_transport=httpx.MockTransport(handler), resolve=lambda h: ["93.184.216.34"],
                brain_exists=lambda b: b != "/gone")
    deps.update(kw)
    return wt.WebhookFeature(wt.WebhookDeps(**deps))


async def main():
    f = make()
    st = f.store()

    # P1: own reference + new address
    h, tok, _ = f.create("/b", name="CRM", target="", text="", level="full",
                         actions=[{"id": "crm", "kind": "http", "url": "https://crm.example/h", "headers": {"X-Api-Key": "TOPSECRET-123"}}])
    ref = f._find(f._load(), h["id"])["actions"][0]["headers"]["X-Api-Key"]
    _, err, _ = f.update(h["id"], {"actions": [{"id": "crm", "kind": "http", "url": "https://evil.example/x", "headers": {"X-Api-Key": ref}}]})
    check("P1: the hook's own reference paired with a new address is refused", "enter header X-Api-Key again" in err, err)
    _, err, _ = f.update(h["id"], {"actions": [{"id": "crm", "kind": "http", "url": "https://crm.example/h", "allow_private": True,
                                                "headers": {"X-Api-Key": ref}}]})
    check("P1: same reference with allow_private switched on is refused too", "enter header" in err, err)
    _, err, _ = f.update(h["id"], {"actions": [{"id": "crm", "kind": "http", "url": "https://crm.example/h", "headers": {"X-Api-Key": ref}}]})
    check("P1: same reference, same target: kept", not err and f._secret(f._find(f._load(), h["id"])["actions"][0]["headers"]["X-Api-Key"],
                                                                         f"{h['id']}/a/crm/X-Api-Key") == "TOPSECRET-123", err)
    hits.clear()
    await f.accept(h["id"], tok, b"{}", "application/json", "p1")
    await f.wait_idle()
    check("P1: nothing ever went to evil.example", all(x[0] != "evil.example" for x in hits) and hits, hits)

    # P3: a receiver echoing headers does not write the key into the log
    answer["echo"] = True
    code, r = await f.accept(h["id"], tok, b"{}", "application/json", "echo")
    await f.wait_idle()
    answer["echo"] = False
    ev = st.get(r["run_id"])
    check("P3: the decrypted key echoed by a receiver is redacted from the receipt", "TOPSECRET-123" not in json.dumps(ev, default=str)
          and "••••" in json.dumps(ev["branches"][0]["receipt"], ensure_ascii=False), ev["branches"][0]["receipt"])

    # P2: a workflow question can be closed by the owner, and owed events are capped per hook
    hw, tokw, _ = f.create("/b", name="Hỏi", target="workflow", workflow="wf", notify="none")
    code, r = await f.accept(hw["id"], tokw, b"{}", "application/json", "w1")
    await f.wait_idle()
    check("(a workflow question leaves the event waiting)", st.get(r["run_id"])["status"] == "waiting")
    ok, why = st.resolve(r["run_id"], "done", "answered by phone")
    check("P2: the owner can close a waiting event (Mark done)", ok and st.get(r["run_id"])["status"] == "done", (ok, why))
    # Spec §11: events the owner still owes count toward the hook's backlog (10 000 by default; 3 here).
    f.update(hw["id"], {"limits": {"backlog": 3}})
    codes = []
    for i in range(5):
        codes.append((await f.accept(hw["id"], tokw, b"{}", "application/json", f"o{i}"))[0])
        await f.wait_idle()
    check("P2: past the backlog of unsettled events, only that hook refuses (429)", codes == [202, 202, 202, 429, 429], codes)
    code, _ = await f.accept(h["id"], tok, b"{}", "application/json", "other-hook")
    check("... another hook still accepts", code == 202)
    await f.wait_idle()

    # P2: brain folder gone: the AI branch does not run elsewhere
    hg, tokg, _ = f.create("/gone", name="Mất brain", target="task", text="x")
    ai_calls.clear()
    code, r = await f.accept(hg["id"], tokg, b"{}", "application/json", "g1")
    await f.wait_idle()
    check("P2: a hook whose brain folder is gone never runs its AI branch (in the default brain or anywhere)",
          not ai_calls and "brain folder" in st.get(r["run_id"])["branches"][0]["detail"])

    # P3: incident only for an AI branch dispatched in this pass
    # Spec §12: incident triage (it may use a model) runs only when the hook turned ai_triage on.
    hi, toki, _ = f.create("/b", name="Sự cố", target="task", text="x", level="full", ai_triage=True,
                           actions=[{"id": "ai", "kind": "ai"}, {"id": "crm", "kind": "http", "url": "https://crm.example/h", "approve": True}])
    answer["ai"] = ("", "boom")
    incidents.clear()
    code, r = await f.accept(hi["id"], toki, b"{}", "application/json", "i1")
    await f.wait_idle()
    n1 = len(incidents)
    st.approve(r["run_id"], "crm", "approve")
    f._kick()
    await f.wait_idle()
    answer["ai"] = ("ok", "")
    check("P3: approving the HTTP branch later does not raise a second incident (no AI ran in that pass)",
          n1 == 1 and len(incidents) == 1, (n1, len(incidents)))

    # P3: approval asked at once even while a sibling waits to resend; an approved branch runs at once
    answer["crm"] = 429
    hp, tokp, _ = f.create("/b", name="Duyệt sớm", target="", text="", level="full",
                           actions=[{"id": "crm", "kind": "http", "url": "https://crm.example/h"},
                                    {"id": "pos", "kind": "tool", "tool": "pos_x"}])
    sent.clear()
    code, r = await f.accept(hp["id"], tokp, b"{}", "application/json", "ap")
    await f.wait_idle()
    check("P3: the approval request goes out at once while the sibling waits for its resend",
          st.get(r["run_id"])["status"] == "queued" and any("duyệt" in m["text"].lower() for m in sent), sent)
    st.approve(r["run_id"], "pos", "approve")
    check("P3: approving a queued event brings it forward (not at the sibling's resend time)",
          st.get(r["run_id"])["next_at"] <= time.time() + 1)
    answer["crm"] = 200

    # P3: 4xx refusals do not open the breaker
    answer["crm"] = 400
    hb, tokb, _ = f.create("/b", name="400", target="", text="", notify="none",
                           actions=[{"id": "crm", "kind": "http", "url": "https://crm.example/h"}])
    for i in range(ws.BREAKER_FAILS + 1):
        await f.accept(hb["id"], tokb, b"{}", "application/json", f"x{i}")
        await f.wait_idle()
    answer["crm"] = 200
    check("P3: repeated 4xx refusals (a bad payload) do not pause the receiver",
          st.breaker_open_until("*", wa.target_key(f._find_hook(hb["id"])["actions"][0])) == 0)

    # P3: body size checked before reading it
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(f.router)
    cl = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    r = await cl.post(f"/hooks/{h['id']}", content=b"x" * (wt.BODY_MAX_BYTES + 10))
    check("spec §4.2: without a valid token the request is refused (401) and its body is never stored",
          r.status_code == 401)
    r = await cl.post(f"/hooks/{h['id']}", content=b"x" * (wt.BODY_MAX_BYTES + 10), headers={"Authorization": f"Bearer {tok}"})
    check("P3: an oversized body is refused (413) from its Content-Length, before it is read", r.status_code == 413)

    # P2: the hook configuration unreadable for a moment (the store's hook rows; webhooks.json since 0.274.0 moved in)
    import sqlite3 as _sq
    n_hooks = len(st.hooks_all())
    f._kick = lambda: None
    code, r = await f.accept(h["id"], tok, b"{}", "application/json", "held")
    real_get, real_ins = st.hook_get, st.hook_insert

    def broken(*a, **k):
        raise _sq.OperationalError("disk I/O error")
    st.hook_get, st.hook_insert = broken, broken
    del f._kick
    f._kick()
    await asyncio.sleep(0.5)
    ev = st.get(r["run_id"])
    check("P2: an unreadable hook configuration does not kill an accepted event (it waits, not 'hook deleted')",
          ev["status"] in ("received", "queued", "running") and "deleted" not in (ev["error"] or ""), (ev["status"], ev["error"]))
    rr = await cl.post(f"/hooks/{h['id']}", content=b"{}", headers={"Authorization": f"Bearer {tok}"})
    check("P2: while unreadable the receive route answers 503 with Retry-After (sender retries), nothing stored",
          rr.status_code == 503 and rr.headers.get("retry-after"))
    try:
        f.create("/b", name="Mới", target="task", text="x")
        created = True
    except (OSError, ValueError, _sq.OperationalError):
        created = False
    st.hook_get, st.hook_insert = real_get, real_ins
    check("P2: create() refuses and no other hook is touched", not created and len(st.hooks_all()) == n_hooks)
    st._db.execute("UPDATE events SET next_at=0 WHERE id=?", (r["run_id"],))
    f._kick()
    await f.wait_idle()
    check("... and once readable again the event runs", st.get(r["run_id"])["status"] == "done", st.get(r["run_id"])["status"])
    await cl.aclose()


asyncio.run(main())

# P2: the poison guard with branches
s = ws.Store(Path(tempfile.mkdtemp(prefix="chain-poison-")) / "e.sqlite3")
c, i = s.ingest({"id": "wh_p", "brain": "/b"}, b"{}", "", "p")
s.triage_commit(i["event_id"], {"decision": "run"}, [])
t = time.time()
for n in range(6):
    w = s.claim("W", now=t)
    if w is None:
        break
    s.branches_init(w["id"], w["fence"], [{"id": "main", "kind": "ai"}], wa.delivery_id)   # then the worker dies
    t += ws.LEASE_S + 1
    s.recover(now=t)
ev = s.get(i["event_id"])
check("P2: an event that kills the worker before any dispatch stops after MAX_AUTO_TRIES (dead), no crash loop",
      ev["status"] == "dead" and n < 5, (ev["status"], n, ev["tries"]))

# P3: prune keeps a failed event whose business key is live
s2 = ws.Store(Path(tempfile.mkdtemp(prefix="chain-key-")) / "e.sqlite3")
old = time.time() - 40 * 86400
pre = {"decision": "run", "business_key": {"shared": "s", "policy": 1, "hash": "order:9", "ttl_s": 366 * 86400}}
c, i = s2.ingest({"id": "wh_k", "brain": "/b"}, b"{}", "", "k", now=old)
s2.triage_commit(i["event_id"], pre, [], now=old)
w = s2.claim("W", now=old)
s2.branches_init(w["id"], w["fence"], [{"id": "main", "kind": "ai"}], wa.delivery_id)
s2.branch_dispatch(w["id"], w["fence"], "main", now=old)
s2.branch_finish(w["id"], w["fence"], "main", "failed", "boom", now=old)
s2.settle(w["id"], w["fence"], lambda r: ("", "boom"), now=old)
s2.prune(keep_days={"wh_k": 1})
check("P3: a failed event whose business key still blocks resends is kept (so the owner can still retry it)",
      s2.get(w["id"]) is not None)

try:
    wa.validate([{"id": "a", "kind": "http", "url": "https://x.vn", "headers": {"X-K": " v "}}])
    r = "accepted"
except wa.ActionError as e:
    r = str(e)
check("P3: a header value with surrounding spaces is refused at save", "ASCII" in r, r)

if fails:
    print(f"\nFAIL {len(fails)}: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_webhook_chain_review: all pass")
