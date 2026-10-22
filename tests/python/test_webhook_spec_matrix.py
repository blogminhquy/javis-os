"""0.274.0: the test matrix of the webhook spec (§15) and its acceptance criteria (§16), row by row.

    python tests/run.py webhook_spec_matrix

Spec of record: docs/superpowers/specs/2026-10-19-webhook-event-platform-design.md. Every row of §15 is a section below
whose checks are named "§15 <group>: ...". Everything runs through the real feature and its router (and, at the end,
the real host app with its login gate), against temporary SQLite files, with a fake HTTP transport, fake plugins, a fake
tool dispatcher and fake model runners. A FAIL-FAST GUARD makes every real model path raise (the reminder/workflow
runners, incident triage), and the model counter must stay at zero on every non-AI path. Crash cases run in child
processes and synchronise on files (a barrier), never by closing a connection in the same process.

Rows that need the owner's real data (POSCake payloads, a deployed Apps Script, a real Systeme.io delivery) are proven
here with fakes and stay open in docs/webhook-platform/staging-pilot-pack.md.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import base64
import hashlib
import hmac
import json
import os
import random
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

STATE = Path(tempfile.mkdtemp(prefix="javis-wh-matrix-"))
os.environ["JAVIS_STATE_DIR"] = str(STATE)
os.environ["JAVIS_NO_REAL_JUDGE_ENGINE"] = "1"      # incident triage raises instead of building an engine
for k in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(k, None)                         # the pinned transport is only used without an outgoing proxy
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx  # noqa: E402
import webhook_actions as wa  # noqa: E402
import webhook_auth as wau  # noqa: E402
import webhook_rules as wr  # noqa: E402
import webhook_store as ws  # noqa: E402
import webhook_triggers as wt  # noqa: E402
import webhook_worker as ww  # noqa: E402

fails = []
PY = sys.executable


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


# ---- the harness: fakes for every outside system, a guard on every model path ----
MODEL = {"calls": 0, "answer": ("Đã xử lý.", ""), "wf": ("ok", "", False)}
SENT, HITS, PLUGIN_JOBS, TOOL_CALLS, INCIDENTS = [], [], {}, [], []
HTTP = {"code": 200, "by_host": {}}


async def run_task(brain, text, level):
    MODEL["calls"] += 1
    a = MODEL["answer"]
    if a == "SLOW":
        await asyncio.sleep(30)
        return "late", ""
    return a


async def run_workflow(brain, slug, text, level):
    MODEL["calls"] += 1
    return MODEL["wf"]


async def send(chat_id, text, viec=None, web="", brain="", dedup=""):
    SENT.append({"text": text, "dedup": dedup, "kind": (viec or {}).get("status")})
    return True, ""


def handler(req):
    HITS.append({"host": req.url.host, "url": str(req.url), "headers": dict(req.headers), "body": req.content,
                 "method": req.method})
    code = HTTP["by_host"].get(req.url.host, HTTP["code"])
    if isinstance(code, list):
        code = code.pop(0) if len(code) > 1 else code[0]
    return httpx.Response(code, headers={"Retry-After": "0"})


def plugin_handler(brain, slug, name):
    """A fake plugin that keeps its jobs by delivery id (the §8.2 contract): a second copy returns the same job."""
    if brain != "/b1" or slug != "poscake-zalo":
        return None
    if name == "order_received":
        def h(env, ctx):
            did = env["delivery_id"]
            job = PLUGIN_JOBS.setdefault(did, f"job-{len(PLUGIN_JOBS) + 1}")
            if HTTP.get("plugin_fail"):
                return {"status": "retryable_error", "detail": "zalo busy"}
            return {"status": "accepted", "ref": job, "detail": "scheduled in 15 minutes"}
        return {"handler": h, "ctx": None, "min_mode": "safe", "schema": None, "ai": False, "idempotent": True}
    if name == "typed":
        return {"handler": lambda e, c: {"status": "completed"}, "ctx": None, "min_mode": "readonly",
                "schema": wr._v_schema({"fields": {"fields.order_id": {"type": "string", "required": True}}}),
                "ai": False, "idempotent": True}
    return None


async def call_tool(brain, level, name, args):
    TOOL_CALLS.append({"brain": brain, "level": level, "name": name, "args": args})
    return "ok"


def make(state=None, **kw):
    deps = dict(state_dir=lambda: state or STATE, run_task=run_task, run_workflow=run_workflow, send=send,
                base_url=lambda _r: "https://javis.example", workflow_exists=lambda b, s: True,
                incident_hook=lambda *a, **k: INCIDENTS.append(a), plugin_handler=plugin_handler,
                http_transport=httpx.MockTransport(handler), resolve=lambda h: ["93.184.216.34"], call_tool=call_tool,
                brain_exists=lambda b: True)
    deps.update(kw)
    return wt.WebhookFeature(wt.WebhookDeps(**deps))


async def drain(f, rounds=15):
    """Let time pass for deliveries waiting for a later attempt (instead of sleeping minutes)."""
    for _ in range(rounds):
        await f.wait_idle()
        st = f.store()
        if not st._db.execute("SELECT 1 FROM events WHERE status IN ('queued','received')").fetchone():
            return
        st._db.execute("UPDATE deliveries SET next_at=0 WHERE status='retry'")
        st._db.execute("UPDATE events SET next_at=0 WHERE status IN ('queued','received')")
        f._kick()


def child(code: str, state: Path, env_extra=None) -> subprocess.CompletedProcess:
    env = dict(os.environ, JAVIS_STATE_DIR=str(state), PYTHONPATH=str(SERVER), **(env_extra or {}))
    return subprocess.run([PY, "-c", code], env=env, capture_output=True, text=True, timeout=120)


ORDER = {"shop_id": 7, "id": 1001, "status": 1, "bill_full_name": "Nguyễn Lan", "bill_phone_number": "0912345678",
         "items": [{"name": "Nước mắm"}, {"name": "Gói TRỢ LÝ AI JAVIS 12 tháng"}]}
SPEC_RULES = {"filter": {"all": [{"path": "status", "op": "eq", "value": 1},
                                 {"path": "items[*].name", "op": "contains", "value": "TRỢ LÝ AI JAVIS",
                                  "quantifier": "any", "case_sensitive": False, "reason": "product_not_found"}]},
              "dedup": {"policy_version": 1, "business_paths": ["shop_id", "id", "status"], "ttl_s": 604800,
                        "missing": "quarantine"},
              "correlation": "id"}
SCRIPT = "https://script.google.com/macros/s/AKfycbx_MATRIX_DEPLOYMENT_1/exec"
POSCAKE_ACTIONS = [{"id": "to_apps_script", "type": "http_forward", "url": SCRIPT, "body_mode": "raw",
                    "redirect_profile": "google_apps_script", "retry_safety": "manual_on_ambiguous",
                    "delivery_ref": "query"},
                   {"id": "to_poscake_zalo", "type": "plugin", "plugin": "poscake-zalo", "handler": "order_received"}]


def next_digest(minute: int) -> float:
    """The next digest moment after now (DIGEST_HOUR:minute, local time): today's if still ahead, else tomorrow's. A fixed
    "tomorrow at 08:xx" lands more than a day after the events when the test runs between midnight and 08:00."""
    t = wt._local(time.time()).replace(hour=ww.DIGEST_HOUR, minute=minute, second=0, microsecond=0).timestamp()
    return t if t > time.time() else t + 86400


def body_of(d):
    return json.dumps(d, ensure_ascii=False).encode()


# ================================================================================================================
async def matrix():
    f = make()
    st = f.store()

    # ---- §15 Lưu bền: kill after commit, before the 202 ----
    sd = Path(tempfile.mkdtemp(prefix="mx-durable-"))
    f0 = make(sd)
    h0, t0, _ = f0.create("/b1", name="Bền", target="task", text="x")
    code = ("import asyncio, os, webhook_triggers as wt\nfrom pathlib import Path\nS = Path(os.environ['JAVIS_STATE_DIR'])\n"
            "async def nop(*a, **k): return 'ok', ''\nasync def snd(*a, **k): return True, ''\n"
            "f = wt.WebhookFeature(wt.WebhookDeps(state_dir=lambda: S, run_task=nop, run_workflow=nop, send=snd,"
            " base_url=lambda r: ''))\n"
            "async def go():\n"
            f"    c, r = await f.accept({h0['id']!r}, {t0!r}, b'{{\"o\": 1}}', 'application/json', 'dur-1')\n"
            "    print('ACK', c, flush=True)\n"
            "asyncio.run(go())\n")
    f0.store().close()
    f0._store = None
    r = child(code, sd, {"JAVIS_WH_CRASH_AT": "after_commit"})
    f1 = make(sd)
    rows = f1.store()._db.execute("SELECT id, status FROM events").fetchall()
    c2, rr = await f1.accept(h0["id"], t0, b'{"o": 1}', "application/json", "dur-1")
    await f1.wait_idle()
    check("§15 Lưu bền: killed after the commit and before the 202, the sender's retry gets the SAME event, nothing lost",
          r.returncode == 77 and "ACK" not in r.stdout and len(rows) == 1 and c2 == 200
          and rr["event_id"] == rows[0][0] and f1.store().get(rows[0][0])["status"] == "done", (r.returncode, rows, rr))

    # ---- §15 Lưu bền: kill before the commit, or the store is full ----
    sd2 = Path(tempfile.mkdtemp(prefix="mx-durable2-"))
    f2 = make(sd2)
    h2, t2, _ = f2.create("/b1", name="Trước commit", target="task", text="x")
    f2.store().close()
    f2._store = None
    code2 = code.replace(repr(h0["id"]), repr(h2["id"])).replace(repr(t0), repr(t2))
    r = child(code2, sd2, {"JAVIS_WH_CRASH_AT": "before_commit"})
    db2 = sqlite3.connect(str(sd2 / "webhook_events.sqlite3"))
    ev_n = db2.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    key_n = db2.execute("SELECT COUNT(*) FROM dedup").fetchone()[0]
    db2.close()
    check("§15 Lưu bền: killed before the commit: no 202, no event, no delivery key", r.returncode == 77
          and "ACK" not in r.stdout and ev_n == 0 and key_n == 0, (r.returncode, ev_n, key_n))
    old_res = ws.DISK_RESERVE
    ws.DISK_RESERVE = 1 << 62
    try:
        hf, tf, _ = f.create("/b1", name="Đầy", target="task", text="x")
        cf, rf = await f.accept(hf["id"], tf, b"{}", "application/json", "full-1")
    finally:
        ws.DISK_RESERVE = old_res
    check("§15 Lưu bền: store full (disk reserve): 503 with a safe code and Retry-After, no event, no key kept",
          cf == 503 and rf["code"] == "store_full" and rf["retry_after"] and not st._db.execute(
              "SELECT 1 FROM dedup WHERE idem_key='h:full-1'").fetchone())

    # ---- §15 Phục hồi: restart with pending / retry_wait / running; no two workers on one delivery ----
    sr = Path(tempfile.mkdtemp(prefix="mx-recover-"))
    fr = make(sr)
    hr, tr, _ = fr.create("/b1", name="Phục hồi", target="", text="", level="full",
                          actions=[{"id": "crm", "kind": "http", "url": "https://crm.example/a",
                                    "retry_safety": "idempotent"},
                                   {"id": "sheet", "kind": "http", "url": "https://sheet.example/a"}])
    str_ = fr.store()
    ids = []
    for i in range(3):
        c, x = await asyncio.gather(fr.accept(hr["id"], tr, b"{}", "application/json", f"rc{i}"), asyncio.sleep(0))
        ids.append(c[1]["event_id"])
    await fr.wait_idle()
    # Put them back into the three states a crash leaves: pending, retry_wait, and running (dispatched, lease expired).
    now = time.time()
    str_._db.execute("UPDATE events SET status='queued', next_at=0, finished_at=0 WHERE id=?", (ids[0],))
    str_._db.execute("UPDATE deliveries SET status='pending', dispatched_at=0, tries=0 WHERE event_id=?", (ids[0],))
    str_._db.execute("UPDATE events SET status='queued', next_at=0, finished_at=0 WHERE id=?", (ids[1],))
    str_._db.execute("UPDATE deliveries SET status='retry', next_at=0, tries=1 WHERE event_id=?", (ids[1],))
    str_._db.execute("UPDATE events SET status='running', lease_until=?, dispatched_at=?, finished_at=0 WHERE id=?",
                     (now - 1, now - 5, ids[2]))
    str_._db.execute("UPDATE deliveries SET status='running', dispatched_at=? WHERE event_id=?", (now - 5, ids[2]))
    str_._db.execute("UPDATE deliveries SET safe=1 WHERE event_id=? AND action_id='crm'", (ids[2],))
    fr.store().close()
    HITS.clear()
    fa, fb = make(sr), make(sr)
    await asyncio.gather(fa.sweep(), fb.sweep())
    await asyncio.gather(fa.wait_idle(), fb.wait_idle())
    sa = fa.store()
    per = {}
    for hit in HITS:
        per[hit["host"]] = per.get(hit["host"], 0) + 1
    e2 = sa.get(ids[2])
    check("§15 Phục hồi: after a restart pending and retry_wait run once each; a running delivery with an expired lease "
          "is resent only when retry-safe (crm), else unknown (sheet); two workers never ran one delivery twice",
          sa.get(ids[0])["status"] == "done" and sa.get(ids[1])["status"] == "done"
          and {b["action_id"]: b["status"] for b in e2["branches"]} == {"crm": "completed", "sheet": "unknown"}
          and per.get("crm.example") == 3 and per.get("sheet.example") == 2, (per, e2["branches"]))

    # ---- §15 Chống trùng: 429 then the same key ----
    hq, tq, _ = f.create("/b1", name="429", target="task", text="x", limits={"per_minute": 1})
    c1, _ = await f.accept(hq["id"], tq, b"{}", "application/json", "first")
    c2, r2 = await f.accept(hq["id"], tq, b'{"o":2}', "application/json", "k-429")
    st._db.execute("UPDATE events SET received_at=received_at-120 WHERE hook_id=?", (hq["id"],))
    c3, r3 = await f.accept(hq["id"], tq, b'{"o":2}', "application/json", "k-429")
    await f.wait_idle()
    check("§15 Chống trùng: the 429 case of the old bug: the retry after the limit is received for real (202), not a "
          "duplicate", c1 == 202 and c2 == 429 and c3 == 202 and st.get(r3["event_id"])["status"] == "done", (c2, c3, r3))

    # ---- §15 Chống trùng: two requests at once with the same event id ----
    hc, tc, _ = f.create("/b1", name="Đồng thời", target="", text="", level="full", actions=POSCAKE_ACTIONS[1:])
    res = await asyncio.gather(*[f.accept(hc["id"], tc, b"{}", "application/json", "same-id") for _ in range(10)])
    await f.wait_idle()
    eid = next(x[1]["event_id"] for x in res if x[0] == 202)
    check("§15 Chống trùng: ten concurrent requests with one event id: one event, one set of deliveries",
          sorted(x[0] for x in res) == [200] * 9 + [202] and len({x[1]["event_id"] for x in res}) == 1
          and st._db.execute("SELECT COUNT(*) FROM deliveries WHERE event_id=?", (eid,)).fetchone()[0] == 1)

    # ---- §15 Chống trùng: composite typed key, missing part, TTL, other hook, other status, update same status ----
    hk, tk, _ = f.create("/b1", name="Khoá", target="task", text="x", rules=SPEC_RULES)
    hk2, tk2, _ = f.create("/b1", name="Khoá 2", target="task", text="x", rules=SPEC_RULES)

    async def send_order(h, t, o, key):
        c, r = await f.accept(h["id"], t, body_of(o), "application/json", key)
        await f.wait_idle()
        return st.get(r["event_id"])
    a = await send_order(hk, tk, ORDER, "o1")
    b = await send_order(hk, tk, dict(ORDER, note="resend"), "o2")
    c = await send_order(hk2, tk2, ORDER, "o3")
    d = await send_order(hk, tk, dict(ORDER, status=2, items=ORDER["items"]), "o4")
    e = await send_order(hk, tk, {k: v for k, v in ORDER.items() if k != "id"}, "o5")
    sh = await send_order(hk, tk, dict(ORDER, shop_id="7"), "o6")
    check("§15 Chống trùng: same (shop, order, status) at the same hook is a duplicate; at another hook it is not; a "
          "missing key part is quarantined; a typed \"7\" is not 7",
          a["status"] == "done" and b["status"] == "duplicate" and c["status"] == "done" and e["state"] == "quarantined"
          and e["reasons"] == ["missing_key_field"] and sh["status"] == "done", (a["status"], b["status"], c["status"],
                                                                                 e["state"], sh["status"]))
    check("§15 Chống trùng: another status of the same order is another key, but the spec filter (status 1) ignores it",
          d["status"] == "filtered" and d["reasons"] == ["status_mismatch"])
    hv, tv, _ = f.create("/b1", name="Phiên bản", target="task", text="x",
                         rules={"dedup": {"business_paths": ["id", "status", "version"], "ttl_s": 600}})
    v1 = await send_order(hv, tv, dict(ORDER, version=1), "v1")
    v2 = await send_order(hv, tv, dict(ORDER, version=2), "v2")
    st._db.execute("UPDATE biz_keys SET expires_at=? WHERE hook_id=?", (time.time() - 1, hv["id"]))
    v3 = await send_order(hv, tv, dict(ORDER, version=2), "v3")
    check("§15 Chống trùng: a valid update with the same status runs when the key holds the source version; after the "
          "TTL the same key runs again", v1["status"] == "done" and v2["status"] == "done" and v3["status"] == "done")

    # ---- §15 Filter: number/string, item match/no match, empty array, null/missing, Unicode, JSON too deep ----
    hfl, tfl, _ = f.create("/b1", name="Lọc", target="task", text="x", rules={"filter": SPEC_RULES["filter"]})
    MODEL["calls"] = 0
    cases = {"match": (ORDER, "done"), "string status": (dict(ORDER, status="1"), "filtered"),
             "no item": (dict(ORDER, items=[{"name": "Nước mắm"}]), "filtered"), "empty array": (dict(ORDER, items=[]),
                                                                                                "filtered"),
             "null status": (dict(ORDER, status=None), "filtered"),
             "missing status": ({k: v for k, v in ORDER.items() if k != "status"}, "filtered"),
             "unicode case": (dict(ORDER, items=[{"name": "trợ lý ai javis"}]), "done")}
    got = {}
    for n, (o, _) in cases.items():
        got[n] = (await send_order(hfl, tfl, o, "")).get("status")
    deep = b'{"status": 1, "x": ' + b"[" * 70 + b"]" * 70 + b"}"
    cdp, rdp = await f.accept(hfl["id"], tfl, deep, "application/json", "")
    await f.wait_idle()
    check("§15 Filter: status number vs string, item match / no match, empty array, null and missing, Unicode with case "
          "folding asked, JSON deeper than 64", got == {n: v[1] for n, v in cases.items()}
          and st.get(rdp["event_id"])["state"] == "quarantined", got)
    check("§16.2: data that does not match costs no model call (only the 2 matching orders ran)", MODEL["calls"] == 2,
          MODEL["calls"])

    # ---- §15 Filter: a wrong rule is never match-all; ignored opens no AI / tool / plugin ----
    _, _, err = f.create("/b1", name="Sai", target="task", text="x",
                         rules={"filter": {"path": "items[*].name", "op": "contains", "value": "x"}})
    hb_, tb_, e_ = f.create("/b1", name="Mảng", target="task", text="x", level="full",
                           rules={"filter": {"path": "tags", "op": "contains", "value": "vip"}},
                           actions=POSCAKE_ACTIONS + [{"id": "tool", "kind": "tool", "tool": "zalo_send_message",
                                                        "approve": False}, {"id": "ai", "kind": "ai"}])
    MODEL["calls"] = 0
    HITS.clear()
    TOOL_CALLS.clear()
    n_jobs = len(PLUGIN_JOBS)
    assert hb_, e_
    cw, rw = await f.accept(hb_["id"], tb_, body_of({"tags": ["vip"]}), "application/json", "")
    ci, ri = await f.accept(hb_["id"], tb_, body_of({"tags": "regular"}), "application/json", "")
    await f.wait_idle()
    check("§15 Filter: a wrong rule is refused at save; at run time a rule that cannot apply quarantines (never "
          "match-all); ignored and quarantined events open no AI, tool, plugin or HTTP",
          "quantifier" in err and st.get(rw["event_id"])["state"] == "quarantined"
          and st.get(ri["event_id"])["state"] == "ignored" and MODEL["calls"] == 0 and not HITS and not TOOL_CALLS
          and len(PLUGIN_JOBS) == n_jobs, (err, st.get(rw["event_id"])["state"]))

    # ---- §15 Nhận body: streaming over the cap, fake / missing Content-Length, non-UTF-8 body, legacy form ----
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(f.router)
    cl = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    hbd, tbd, _ = f.create("/b1", name="Body", target="", text="", level="full", limits={"body_kb": 4},
                           actions=[{"id": "raw", "kind": "http", "url": "https://raw.example/in", "body": "raw"}])
    auth = {"Authorization": f"Bearer {tbd}"}

    async def chunks(n):
        for _ in range(n):
            yield b"x" * 1024
    r1 = await cl.post(f"/hooks/{hbd['id']}", content=chunks(8), headers=auth)
    r2 = await cl.post(f"/hooks/{hbd['id']}", content=b"x" * 8000, headers=dict(auth, **{"content-length": "10"}))
    r3 = await cl.post(f"/hooks/{hbd['id']}", content=chunks(2), headers=dict(auth, **{"content-type": "text/plain"}))
    latin = "Lan đã mua".encode("latin-1", "replace") + b"\xff"
    r4 = await cl.post(f"/hooks/{hbd['id']}", content=latin, headers=dict(auth, **{"content-type": "text/plain"}))
    r5 = await cl.post(f"/hooks/{hbd['id']}", content=b"name=Lan&phone=0912", headers=dict(auth, **{
        "content-type": "application/x-www-form-urlencoded"}))
    HITS.clear()
    await f.wait_idle()
    raw_hit = [x for x in HITS if x["host"] == "raw.example"]
    check("§15 Nhận body: a stream over the cap is cut at the cap (413); a false Content-Length does not let it through; "
          "no Content-Length is fine",
          r1.status_code == 413 and r2.status_code in (400, 413) and r3.status_code == 202, (r1.status_code, r2.status_code,
                                                                                            r3.status_code))
    check("§15 Nhận body: a non-UTF-8 body and a legacy form are stored as received and forwarded byte for byte",
          r4.status_code == 202 and r5.status_code == 202 and bytes(st.get(r4.json()["event_id"], True)["body"]) == latin
          and any(x["body"] == latin for x in raw_hit) and any(x["body"] == b"name=Lan&phone=0912" for x in raw_hit),
          [x["body"][:20] for x in raw_hit])

    # ---- §15 Xác thực: wrong/missing header, one byte off, key rotation, old timestamp, constant-time compare ----
    SEC = "gh-matrix-secret-1"
    hg, tg, _ = f.create("/b1", name="GitHub", target="task", text="x", verify={"provider": "github", "secret": SEC})
    body = b'{"zen":"ok"}'
    sig = "sha256=" + hmac.new(SEC.encode(), body, hashlib.sha256).hexdigest()
    bad1 = sig[:-1] + ("0" if sig[-1] != "0" else "1")
    ca, _ = await f.accept(hg["id"], tg, body, "application/json", "", headers={})
    cb, _ = await f.accept(hg["id"], tg, body, "application/json", "", headers={"x-hub-signature-256": bad1})
    cc, rc = await f.accept(hg["id"], tg, body, "application/json", "", headers={"x-hub-signature-256": sig,
                                                                                 "x-github-delivery": "gd-1"})
    f.update(hg["id"], {"verify": {"provider": "github", "secret": "gh-matrix-secret-2", "overlap_h": 1}})
    cd, rd = await f.accept(hg["id"], tg, body, "application/json", "", headers={"x-hub-signature-256": sig,
                                                                                 "x-github-delivery": "gd-2"})
    hv_ = f._find_hook(hg["id"])
    st._db.execute("UPDATE hooks SET config=? WHERE id=?", (json.dumps(dict(st._config_of(hv_), verify=dict(
        hv_["verify"], previous_until=time.time() - 1))), hg["id"]))
    ce, _ = await f.accept(hg["id"], tg, body, "application/json", "", headers={"x-hub-signature-256": sig,
                                                                                "x-github-delivery": "gd-3"})
    sig2 = "sha256=" + hmac.new(b"gh-matrix-secret-2", body, hashlib.sha256).hexdigest()
    cf_, rf_ = await f.accept(hg["id"], tg, body, "application/json", "", headers={"x-hub-signature-256": sig2,
                                                                                   "x-github-delivery": "gd-4"})
    await f.wait_idle()
    src = (SERVER / "webhook_auth.py").read_text(encoding="utf-8")
    check("§15 Xác thực: missing header and a signature one byte off: 401; rotation keeps the previous key for its "
          "bounded overlap only, and records which key matched",
          ca == 401 and cb == 401 and cc == 202 and cd == 202 and ce == 401 and cf_ == 202
          and st.get(rd["event_id"])["key_version"] == "previous" and st.get(rf_["event_id"])["key_version"] == "current"
          and st.get(rc["event_id"])["verified_at"] > 0, (ca, cb, cc, cd, ce, cf_))
    ts_old = str(int(time.time()) - 3600)
    sbody = b'{"id":"evt_m1","type":"invoice.paid"}'
    ssig = hmac.new(b"whsec_matrix", ts_old.encode() + b"." + sbody, hashlib.sha256).hexdigest()
    check("§15 Xác thực: an old Stripe timestamp is refused; comparisons are constant-time (hmac.compare_digest)",
          not wau.verify({"provider": "stripe"}, "whsec_matrix", {"stripe-signature": f"t={ts_old},v1={ssig}"}, sbody)[0]
          and "hmac.compare_digest" in src and "== got" not in src)

    # ---- §15 Provider ----
    sh = base64.b64encode(hmac.new(b"shp", b"raw body", hashlib.sha256).digest()).decode()
    tnow = str(int(time.time()))
    s1 = hmac.new(b"whsec_matrix", tnow.encode() + b"." + sbody, hashlib.sha256).hexdigest()
    forms = wau.systeme_forms('{"n": "Trợ lý", "u": "https://a/b"}'.encode())
    ss = hmac.new(b"sys", forms["php_default"], hashlib.sha256).hexdigest()
    check("§15 Provider: GitHub hex with sha256= prefix; Shopify base64 over the raw body; Stripe with several v1 "
          "signatures; Systeme.io Unicode/slash normalisation (the matched form recorded)",
          wau.verify({"provider": "github"}, "k" * 8, {"x-hub-signature-256": "sha256=" + hmac.new(
              b"k" * 8, b"x", hashlib.sha256).hexdigest()}, b"x")[0]
          and not wau.verify({"provider": "github"}, "k" * 8, {"x-hub-signature-256": hmac.new(
              b"k" * 8, b"x", hashlib.sha256).hexdigest()}, b"x")[0]
          and wau.verify({"provider": "shopify"}, "shp", {"x-shopify-hmac-sha256": sh}, b"raw body")[0]
          and not wau.verify({"provider": "shopify"}, "shp", {"x-shopify-hmac-sha256": sh}, b"raw body ")[0]
          and wau.verify({"provider": "stripe"}, "whsec_matrix", {"stripe-signature": f"t={tnow},v1=00,v1={s1}"}, sbody)[0]
          and wau.verify_ex({"provider": "systeme_io"}, "sys", {"x-webhook-signature": ss},
                            '{"n": "Trợ lý", "u": "https://a/b"}'.encode())[3] == "php_default"
          and b"\\u1ee3" in forms["php_default"] and b"\\/" in forms["php_default"])

    # ---- §15 Chuyển tiếp: raw bytes unchanged, no cookie/token forwarded, DNS / redirect to private refused ----
    hfw, tfw, _ = f.create("/b1", name="Chuyển", target="", text="", level="full",
                           actions=[{"id": "fw", "kind": "http", "url": "https://fw.example/in", "body": "raw"}])
    HITS.clear()
    raw = '{"a": "Trợ lý", "b":[1,2]}'.encode()
    rr = await cl.post(f"/hooks/{hfw['id']}", content=raw, headers={"Authorization": f"Bearer {tfw}",
                                                                     "Cookie": "session=OWNER", "content-type":
                                                                         "application/json; charset=utf-8"})
    await f.wait_idle()
    fw = [x for x in HITS if x["host"] == "fw.example"][0]
    check("§15 Chuyển tiếp: raw bytes and their content type forwarded unchanged; the sender's cookie and token never "
          "forwarded", rr.status_code == 202 and fw["body"] == raw and fw["headers"]["content-type"].startswith(
              "application/json") and "cookie" not in fw["headers"] and tfw not in json.dumps(fw["headers"])
          and fw["headers"]["x-javis-event-id"] == rr.json()["event_id"], fw["headers"])
    act = wa.validate([{"id": "x", "kind": "http", "url": "https://rebind.example/h"}])[0]
    ctx = {"event_id": "ev_m", "hook_id": "wh_m", "action_id": "x", "received_at": 1.0, "delivery_id": "dlv_m",
           "fields": {}, "payload": {}, "body": b"{}", "content_type": "application/json"}
    answers = iter([["93.184.216.34"], ["127.0.0.1"]])
    o1 = await wa.run_http(act, ctx, None, lambda h: next(answers))
    o2 = await wa.run_http(act, ctx, httpx.MockTransport(handler), lambda h: ["169.254.169.254"])
    HITS.clear()
    o3 = await wa.run_http(act, ctx, httpx.MockTransport(lambda r: httpx.Response(302, headers={
        "Location": "http://10.0.0.1/admin"})), lambda h: ["93.184.216.34"])
    def no_dns(h):
        raise OSError("temporary failure in name resolution")
    o4 = await wa.run_http(act, ctx, httpx.MockTransport(handler), no_dns)
    check("§8: a name that does not resolve (DNS outage) is retried, nothing was sent; a private address stays refused",
          o4.status == "retry" and not o4.maybe_acted and o2.status == "failed", o4)
    check("§15 Chuyển tiếp: a name that answers public to the check and private to the connection (DNS rebinding) gets "
          "nowhere; a metadata address is refused; a redirect to a private address is not followed",
          o1.status == "failed" and "private" in o1.detail and o2.status == "failed" and o3.status == "unknown"
          and not HITS, (o1, o2, o3))

    # ---- §15 Apps Script ----
    rows_gas = {}

    def gas(req):
        if req.url.host == "script.google.com":
            q = dict(httpx.QueryParams(req.url.query))
            did = q.get("javis_delivery")
            dup = did in rows_gas
            rows_gas.setdefault(did, len(rows_gas) + 1)
            echo = "https://script.googleusercontent.com/macros/echo?k=" + ("dup" if dup else "new") + "&d=" + str(did)
            if GAS["mode"] == "lose" and not dup:
                return httpx.Response(302, headers={"Location": echo + "&lose=1"})
            if GAS["mode"] == "login":
                return httpx.Response(302, headers={"Location": "https://accounts.google.com/ServiceLogin?continue=x"})
            return httpx.Response(302, headers={"Location": echo})
        q = dict(httpx.QueryParams(req.url.query))
        if q.get("lose"):
            raise httpx.ReadTimeout("receipt lost")
        if GAS["mode"] == "html":
            return httpx.Response(200, text="<html>Lỗi: TypeError in doPost</html>")
        if GAS["mode"] == "refuse":
            return httpx.Response(200, json={"ok": False, "error": "sheet locked"})
        return httpx.Response(200, json={"ok": True, "delivery_id": q.get("d"), "duplicate": q.get("k") == "dup"})
    GAS = {"mode": "ok"}
    fg = make(http_transport=httpx.MockTransport(gas))
    hgs, tgs, _ = fg.create("/b1", name="Sheet", target="", text="", level="full", actions=POSCAKE_ACTIONS[:1])
    outs = {}
    for mode in ("ok", "login", "refuse", "lose", "html"):
        GAS["mode"] = mode
        c, r = await fg.accept(hgs["id"], tgs, body_of(ORDER), "application/json", "")
        await fg.wait_idle()
        outs[mode] = (fg.store().get(r["event_id"])["branches"][0], r["event_id"])
    GAS["mode"] = "ok"
    lost_eid = outs["lose"][1]
    rows_before = len(rows_gas)
    ok, _ = fg.store().retry(lost_eid)
    fg._kick()
    await fg.wait_idle()
    after = fg.store().get(lost_eid)["branches"][0]
    check("§15 Apps Script: a valid redirect with its receipt succeeds; Google's sign-in blocks; HTTP 200 with ok:false "
          "is dead; a POST that ran but lost its receipt, or whose echo page is not a receipt, is unknown and is not resent "
          "by itself",
          outs["ok"][0]["status"] == "completed" and outs["login"][0]["status"] == "blocked"
          and outs["refuse"][0]["status"] == "failed" and "sheet locked" in outs["refuse"][0]["detail"]
          and outs["lose"][0]["status"] == "unknown"
          and outs["html"][0]["status"] == "unknown", {k: v[0]["status"] for k, v in outs.items()})
    check("§15 Apps Script: the owner's retry sends the same delivery id (in the query, which doPost can read), the "
          "script answers duplicate: no second order row", ok and after["status"] == "completed"
          and "had it already" in after["detail"] and len(rows_gas) == rows_before == 5, (after, rows_gas))

    # ---- §15 Retry: fake clock and RNG, 1/5/30 min, jitter, Retry-After, out of attempts, unknown not resent ----
    fq = make()
    fq.rng = random.Random(7)
    cfg = {"retry": {}}
    t_now = 1_000_000.0
    waits = [fq._backoff(n, cfg, 0, 0, t_now) - t_now for n in (1, 2, 3)]
    check("§15 Retry: 1, 5 and 30 minutes with +-20 % jitter (fake RNG), then no 5th call (4 in all)",
          48 <= waits[0] <= 72 and 240 <= waits[1] <= 360 and 1440 <= waits[2] <= 2160
          and fq._backoff(4, cfg, 0, 0, t_now) == 0, waits)
    fq.rng = random.Random(1)
    j0 = fq._backoff(1, {"retry": {"jitter_ratio": 0}}, 0, 0, t_now) - t_now
    ra = fq._backoff(1, {"retry": {"jitter_ratio": 0}}, 900, 0, t_now) - t_now
    dl = fq._backoff(1, {"retry": {"jitter_ratio": 0}}, 900, t_now + 600, t_now)
    check("§15 Retry: a valid Retry-After stretches the wait, never past the delivery's deadline", j0 == 60 and ra == 900
          and dl == 0, (j0, ra, dl))
    HTTP["by_host"]["amb.example"] = 504
    hamb, tamb, _ = f.create("/b1", name="Mơ hồ", target="", text="", level="full",
                             actions=[{"id": "x", "kind": "http", "url": "https://amb.example/h"}])
    HITS.clear()
    c, r = await f.accept(hamb["id"], tamb, b"{}", "application/json", "")
    await drain(f)
    check("§15 Retry: a 5xx at a receiver not declared idempotent is unknown and is NOT resent by itself",
          st.get(r["event_id"])["branches"][0]["status"] == "unknown"
          and sum(1 for x in HITS if x["host"] == "amb.example") == 1)
    HTTP["by_host"]["busy.example"] = 429
    hbz, tbz, _ = f.create("/b1", name="Bận", target="", text="", level="full",
                           actions=[{"id": "x", "kind": "http", "url": "https://busy.example/h"}])
    HITS.clear()
    c, r = await f.accept(hbz["id"], tbz, b"{}", "application/json", "")
    await drain(f)
    bz = st.get(r["event_id"])["branches"][0]
    check("§15 Retry: a receiver that keeps answering 429 gets 4 calls in all, then the delivery is dead",
          bz["status"] == "failed" and bz["tries"] == 4 and sum(1 for x in HITS if x["host"] == "busy.example") == 4, bz)

    # ---- §15 Fan-out: forward succeeded + plugin failed: only the plugin is retried ----
    HTTP["plugin_fail"] = True
    hfo, tfo, _ = f.create("/b1", name="Hai nhánh", target="", text="", level="full",
                           actions=[{"id": "fw", "kind": "http", "url": "https://fo.example/h"}, POSCAKE_ACTIONS[1]])
    HITS.clear()
    c, r = await f.accept(hfo["id"], tfo, body_of(ORDER), "application/json", "")
    await f.wait_idle()
    mid = {b["action_id"]: b["status"] for b in st.get(r["event_id"])["branches"]}
    HTTP["plugin_fail"] = False
    await drain(f)
    fin = {b["action_id"]: b["status"] for b in st.get(r["event_id"])["branches"]}
    check("§15 Fan-out: forward succeeded and the plugin failed: only the plugin is retried, the forward is not repeated",
          mid == {"fw": "completed", "to_poscake_zalo": "retry"} and fin == {"fw": "completed", "to_poscake_zalo": "accepted"}
          and sum(1 for x in HITS if x["host"] == "fo.example") == 1, (mid, fin))

    # ---- §15 Plugin: the job committed, then a crash before the receipt: same delivery, same job, no second job ----
    sp = Path(tempfile.mkdtemp(prefix="mx-plugin-"))
    fp = make(sp)
    hp_, tp_, _ = fp.create("/b1", name="Plugin", target="", text="", level="full", actions=[POSCAKE_ACTIONS[1]])
    fp.store().close()
    fp._store = None
    jobs = sp / "jobs.json"
    code = ("import asyncio, os, json, webhook_triggers as wt\nfrom pathlib import Path\n"
            "S = Path(os.environ['JAVIS_STATE_DIR'])\nJ = S / 'jobs.json'\n"
            "def h(env, ctx):\n"
            "    jobs = json.loads(J.read_text()) if J.exists() else {}\n"
            "    job = jobs.setdefault(env['delivery_id'], 'job-%d' % (len(jobs) + 1))\n"
            "    J.write_text(json.dumps(jobs))              # the plugin COMMITS its job...\n"
            "    (S / 'barrier').write_text('committed')\n"
            "    return {'status': 'accepted', 'ref': job}\n"
            "def ph(brain, slug, name):\n"
            "    return {'handler': h, 'ctx': None, 'min_mode': 'safe', 'schema': None, 'ai': False, 'idempotent': True}\n"
            "async def nop(*a, **k): return 'ok', ''\nasync def snd(*a, **k): return True, ''\n"
            "f = wt.WebhookFeature(wt.WebhookDeps(state_dir=lambda: S, run_task=nop, run_workflow=nop, send=snd,"
            " base_url=lambda r: '', plugin_handler=ph))\n"
            "async def go():\n"
            f"    c, r = await f.accept({hp_['id']!r}, {tp_!r}, b'{{}}', 'application/json', 'pj')\n"
            "    print('ACK', c, r['event_id'], flush=True)\n"
            "    await f.wait_idle()\n"
            "asyncio.run(go())\n")
    r = child(code, sp, {"JAVIS_WH_CRASH_AT": "after_dispatch"})
    eid = [ln.split()[2] for ln in r.stdout.splitlines() if ln.startswith("ACK")][0]
    first = json.loads(jobs.read_text())
    seen_after = {}

    def h2(env, ctx):
        j = json.loads(jobs.read_text())
        job = j.setdefault(env["delivery_id"], f"job-{len(j) + 1}")
        jobs.write_text(json.dumps(j))
        seen_after["job"] = job
        return {"status": "accepted", "ref": job}
    fp2 = make(sp, plugin_handler=lambda b, s, n: {"handler": h2, "ctx": None, "min_mode": "safe", "schema": None,
                                                   "ai": False, "idempotent": True})
    fp2.store()._db.execute("UPDATE events SET lease_until=0 WHERE id=?", (eid,))
    await fp2.sweep()
    await drain(fp2)
    b = fp2.store().get(eid)["branches"][0]
    check("§15 Plugin: the plugin committed its job, the worker died before the receipt; after recovery the SAME "
          "delivery is handed over again (idempotent contract) and the plugin answers the SAME job, no second job",
          r.returncode == 77 and (sp / "barrier").exists() and len(first) == 1 and len(json.loads(jobs.read_text())) == 1
          and seen_after.get("job") == list(first.values())[0] and b["status"] == "accepted"
          and b["receipt"]["ref"] == seen_after.get("job"), (r.returncode, first, seen_after, b))

    # ---- §15 Plugin: disabled/uninstalled, wrong schema, callback timeout, another brain; never broadcast ----
    hpl, tpl, _ = f.create("/b1", name="Plugin lỗi", target="", text="", level="full",
                           actions=[{"id": "gone", "kind": "plugin", "plugin": "not-installed", "handler": "x"},
                                    {"id": "typed", "kind": "plugin", "plugin": "poscake-zalo", "handler": "typed"}])
    c, r = await f.accept(hpl["id"], tpl, b"{}", "application/json", "")
    await f.wait_idle()
    bs = {b["action_id"]: b for b in st.get(r["event_id"])["branches"]}
    hob, tob, _ = f.create("/b2", name="Brain khác", target="", text="", level="full", actions=[POSCAKE_ACTIONS[1]])
    n_jobs = len(PLUGIN_JOBS)
    c, r2 = await f.accept(hob["id"], tob, b"{}", "application/json", "")
    await f.wait_idle()
    check("§15 Plugin: uninstalled or off -> blocked; an event that does not fit the handler's schema -> dead, the "
          "handler never called; a plugin of another brain is never found, nothing is broadcast",
          bs["gone"]["status"] == "blocked" and bs["typed"]["status"] == "failed" and "schema" in bs["typed"]["detail"]
          and st.get(r2["event_id"])["branches"][0]["status"] == "blocked" and len(PLUGIN_JOBS) == n_jobs)
    import threading
    gate = threading.Event()
    calls_slow = []

    def slow(env, ctx):
        calls_slow.append(env["delivery_id"])
        gate.wait(10)
        return {"status": "completed"}
    old_t = wa.PLUGIN_TIMEOUT_S
    wa.PLUGIN_TIMEOUT_S = 0.2
    fs = make(plugin_handler=lambda b, s, n: {"handler": slow, "ctx": None, "min_mode": "readonly", "schema": None,
                                              "ai": False, "idempotent": False})
    hsl, tsl, _ = fs.create("/b1", name="Chậm", target="", text="", level="full",
                            actions=[{"id": "p", "kind": "plugin", "plugin": "poscake-zalo", "handler": "slow"}])
    c, r = await fs.accept(hsl["id"], tsl, b"{}", "application/json", "")
    await fs.wait_idle()
    st_s = fs.store()
    b1 = st_s.get(r["event_id"])["branches"][0]
    st_s.retry(r["event_id"])
    fs._kick()
    await fs.wait_idle()
    b2 = st_s.get(r["event_id"])["branches"][0]
    gate.set()
    wa.PLUGIN_TIMEOUT_S = old_t
    await asyncio.sleep(0.3)
    check("§15 Plugin: a callback that times out is unknown; the owner's retry does not start beside the old call "
          "still running (one call in flight per delivery)", b1["status"] == "unknown" and len(calls_slow) == 1
          and b2["status"] == "retry" and "still running" in b2["detail"], (b1["status"], b2, calls_slow))

    # ---- §15 Tool: schema, min_mode and readiness through the dispatcher; the payload chooses neither tool nor level ----
    htl, ttl, _ = f.create("/b1", name="Tool", target="", text="", level="auto",
                           actions=[{"id": "zalo", "kind": "tool", "tool": "zalo_send_message", "approve": False,
                                     "args": {"threadId": "{{payload.thread}}", "message": "Đơn {{payload.id}} đã nhận",
                                              "items": "{{payload.items}}"}}])
    TOOL_CALLS.clear()
    c, r = await f.accept(htl["id"], ttl, body_of({"thread": "t-1", "id": 55, "items": [1, 2], "tool": "javis_run_tool",
                                                   "level": "full"}), "application/json", "")
    c2, r2 = await f.accept(htl["id"], ttl, body_of({"id": 56}), "application/json", "")
    await f.wait_idle()
    bad_meta = ""
    try:
        wa.validate([{"id": "t", "kind": "tool", "tool": "javis_run_tool", "args": {"name": "{{payload.tool}}"}}])
    except wa.ActionError as e:
        bad_meta = str(e)
    check("§15 Tool: called through the dispatcher at the hook's level; arguments from {{payload.x}} keep their type; a "
          "missing field stops the call; the payload cannot choose the tool or raise the level; meta-tools refused",
          len(TOOL_CALLS) == 1 and TOOL_CALLS[0]["name"] == "zalo_send_message" and TOOL_CALLS[0]["level"] == "auto"
          and TOOL_CALLS[0]["args"] == {"threadId": "t-1", "message": "Đơn 55 đã nhận", "items": [1, 2]}
          and st.get(r2["event_id"])["branches"][0]["status"] == "failed" and "name the tool itself" in bad_meta,
          (TOOL_CALLS, st.get(r2["event_id"])["branches"]))

    # ---- §15 AI: quota waits; a lost dispatch is not run twice; a partial result with an error is not done ----
    hai, tai, _ = f.create("/b1", name="AI", target="task", text="x", ai_per_hour=1)
    MODEL["calls"] = 0
    c, r1 = await f.accept(hai["id"], tai, b"{}", "application/json", "")
    c, r2 = await f.accept(hai["id"], tai, b"{}", "application/json", "")
    await f.wait_idle()
    b2 = st.get(r2["event_id"])["branches"][0]
    check("§15 AI / §16.4: past the AI quota the event waits (accepted, not lost, not a model call)",
          MODEL["calls"] == 1 and b2["status"] == "retry" and b2["dispatched_at"] == 0
          and st.get(r2["event_id"])["state"] == "processing")
    MODEL["answer"] = ("Đã làm một nửa", "engine stopped")
    hpart, tpart, _ = f.create("/b1", name="Một phần", target="task", text="x")
    c, rp = await f.accept(hpart["id"], tpart, b"{}", "application/json", "")
    await f.wait_idle()
    MODEL["answer"] = ("Đã xử lý.", "")
    check("§15 AI: a partial result with an error is not done (unknown: the owner decides)",
          st.get(rp["event_id"])["status"] == "unknown" and "partial" in st.get(rp["event_id"])["branches"][0]["detail"])
    # A dispatch whose worker died: the AI branch was handed to the engine, the lease ran out. Two workers recover it at
    # once: neither starts a second task (an AI run is never retry-safe), the branch waits for the owner as unknown.
    sai = Path(tempfile.mkdtemp(prefix="mx-ai-lost-"))
    fai = make(sai)
    hal, tal, _ = fai.create("/b1", name="AI mất", target="task", text="x")
    c, ral = await fai.accept(hal["id"], tal, b"{}", "application/json", "ai-lost")
    await fai.wait_idle()
    now = time.time()
    sx = fai.store()
    sx._db.execute("UPDATE events SET status='running', lease_until=?, dispatched_at=?, finished_at=0 WHERE id=?",
                   (now - 1, now - 5, ral["event_id"]))
    sx._db.execute("UPDATE deliveries SET status='running', dispatched_at=? WHERE event_id=?", (now - 5, ral["event_id"]))
    sx.close()
    calls0 = MODEL["calls"]
    fa2, fb2 = make(sai), make(sai)
    await asyncio.gather(fa2.sweep(), fb2.sweep())
    await asyncio.gather(fa2.wait_idle(), fb2.wait_idle())
    c_dup, r_dup = await fa2.accept(hal["id"], tal, b"{}", "application/json", "ai-lost")
    await fa2.wait_idle()
    bl = fa2.store().get(ral["event_id"])["branches"][0]
    check("§15 AI: a lost dispatch recovered by two workers at once, and the sender's retry with the same key, never "
          "start a second task: the branch is unknown for the owner", MODEL["calls"] == calls0 and bl["status"] == "unknown"
          and c_dup == 200 and r_dup["event_id"] == ral["event_id"], (MODEL["calls"] - calls0, bl, c_dup))

    # ---- §15 Chờ chủ ----
    MODEL["wf"] = ("Anh chọn mẫu A hay B?", "", True)
    hwq, twq, _ = f.create("/b1", name="Hỏi", target="workflow", workflow="wf")
    c, rq = await f.accept(hwq["id"], twq, b"{}", "application/json", "")
    hap, tap, _ = f.create("/b1", name="Duyệt", target="", text="", level="full",
                           actions=[{"id": "zalo", "kind": "tool", "tool": "zalo_send_message", "args": {"m": "hi"}}])
    TOOL_CALLS.clear()
    c, ra = await f.accept(hap["id"], tap, b"{}", "application/json", "")
    await f.wait_idle()
    MODEL["wf"] = ("ok", "", False)
    check("§15 Chờ chủ: a workflow that needs a decision waits (never done); a tool that needs approval waits, not run",
          st.get(rq["event_id"])["status"] == "waiting" and st.get(rq["event_id"])["state"] == "waiting"
          and st.get(ra["event_id"])["branches"][0]["state"] == "waiting_approval" and not TOOL_CALLS)

    # ---- §15 Không AI / §16.2: filter + forward/plugin, with errors and the digest: zero model calls ----
    MODEL["calls"] = 0
    INCIDENTS.clear()
    HTTP["by_host"]["down.example"] = 500
    hna, tna, _ = f.create("/b1", name="POSCake", target="", text="", level="full", rules=SPEC_RULES,
                           notify="daily_digest",
                           actions=[{"id": "fw", "kind": "http", "url": "https://down.example/h"}, POSCAKE_ACTIONS[1]])
    for i, o in enumerate((ORDER, dict(ORDER, id=1002), dict(ORDER, status=3))):
        await f.accept(hna["id"], tna, body_of(o), "application/json", f"na{i}")
    await f.wait_idle()
    _nd = next_digest(30)
    f.clock = lambda: _nd
    await f._digest()
    await f.deliver_notifications()
    f.clock = time.time
    check("§15 Không AI / §16.2: filter, forward and plugin with failures and the daily digest: no model call, no "
          "incident triage (the hook has no AI action and triage is off)", MODEL["calls"] == 0 and not INCIDENTS
          and any("POSCake" in m["text"] and m["kind"] == "digest" for m in SENT), (MODEL["calls"], INCIDENTS))

    # ---- §15 Replay ----
    HTTP["by_host"]["rp.example"] = 200
    HTTP["by_host"]["rp2.example"] = 500
    hrp, trp, _ = f.create("/b1", name="Replay", target="", text="", level="full",
                           actions=[{"id": "a", "kind": "http", "url": "https://rp.example/h"},
                                    {"id": "b", "kind": "http", "url": "https://rp2.example/h"}])
    HITS.clear()
    c, r = await f.accept(hrp["id"], trp, b'{"o": 1}', "application/json", "")
    await f.wait_idle()
    HTTP["by_host"]["rp2.example"] = 200
    st.retry(r["event_id"])
    f._kick()
    await f.wait_idle()
    n_a = sum(1 for x in HITS if x["host"] == "rp.example")
    f.update(hrp["id"], {"level": "suggest"})
    code, prev = f.replay_preview(r["event_id"])
    f.update(hrp["id"], {"level": "full", "actions": [{"id": "a", "kind": "http", "url": "https://rp.example/h"}]})
    code2, prev2 = f.replay_preview(r["event_id"])
    code3, conf = f.replay_confirm(r["event_id"])
    await f.wait_idle()
    ev = st.get(r["event_id"])
    check("§15 Replay: retry never re-runs the action that succeeded; replay with the new configuration shows the new "
          "generation, the current permission level and which actions would act again, then runs under new delivery ids",
          n_a == 1 and code == 200 and prev["level"] == "suggest" and prev["generation"] == 2
          and prev2["may_repeat"] == ["a"] and code3 == 200 and ev["generation"] == 2
          and ev["branches"][0]["delivery_id"] == wa.delivery_id(r["event_id"], "a", 2)
          and sum(1 for x in HITS if x["host"] == "rp.example") == 2, (prev, prev2, conf))

    # ---- §15 UI (API side): two tabs, masked customer data, pagination, simulate without side effects ----
    hui, tui, _ = f.create("/b1", name="Hai tab", target="task", text="x")
    rev = f._find_hook(hui["id"])["revision"]
    ra_ = await cl.post("/webhooks/update", json={"id": hui["id"], "name": "Tab 1", "revision": rev})
    rb_ = await cl.post("/webhooks/update", json={"id": hui["id"], "name": "Tab 2", "revision": rev})
    c, rm = await f.accept(hui["id"], tui, body_of(ORDER), "application/json", "")
    await f.wait_idle()
    det = (await cl.get(f"/webhooks/events/{rm['event_id']}")).json()["event"]
    n_ev = st._db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    sim = (await cl.post("/webhooks/simulate", json={"id": hk["id"], "payload": ORDER})).json()
    check("§15 UI: two tabs editing one hook: the second save is refused (409), nothing overwritten; customer data "
          "masked in the event view; simulate has no side effect", ra_.status_code == 200 and rb_.status_code == 409
          and f._find_hook(hui["id"])["name"] == "Tab 1" and "Nguyễn Lan" not in det["payload"]
          and "0912345678" not in det["payload"] and st._db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == n_ev
          and sim["ok"], (ra_.status_code, rb_.status_code))

    # ---- §15 Thông báo ----
    fail_send = {"n": 0}

    async def flaky_send(chat_id, text, viec=None, web="", brain="", dedup=""):
        fail_send["n"] += 1
        return (False, "down") if fail_send["n"] <= 2 else (True, "")
    fnt = make(send=flaky_send)
    HTTP["by_host"]["nt.example"] = 400
    hnt, tnt, _ = fnt.create("/b1", name="Báo lỗi", target="", text="", level="full",
                             actions=[{"id": "x", "kind": "http", "url": "https://nt.example/h"}])
    HITS.clear()
    c, r = await fnt.accept(hnt["id"], tnt, b"{}", "application/json", "")
    await fnt.wait_idle()
    for i in range(4):
        fnt.clock = (lambda v: (lambda: v))(time.time() + 4000 * (i + 1))
        await fnt.sweep()
    fnt.clock = time.time
    check("§15 Thông báo: a notice that fails is retried alone; the action is never run again for it",
          sum(1 for x in HITS if x["host"] == "nt.example") == 1 and fail_send["n"] == 3
          and fnt.store().notifications(event_id=r["event_id"])[0]["status"] == "sent")
    sdg = Path(tempfile.mkdtemp(prefix="mx-digest-"))
    fd1 = make(sdg)
    hdg, tdg, _ = fd1.create("/b1", name="Tóm tắt", target="task", text="x", notify="daily_digest")
    await fd1.accept(hdg["id"], tdg, b"{}", "application/json", "")
    await fd1.wait_idle()
    later = next_digest(10)
    SENT.clear()
    fd1.clock = lambda: later
    await fd1._digest()
    fd1.store().close()
    fd2 = make(sdg)
    fd2.clock = lambda: later + 60
    await fd2._digest()
    await fd2.deliver_notifications()
    fd2._store and fd2.store().meta_del(f"digest_day:{hdg['id']}")   # even with the day marker lost
    await fd2._digest()
    await fd2.deliver_notifications()
    check("§15 Thông báo: a restart does not send two digests for one period (one outbox key per day)",
          sum(1 for m in SENT if m["kind"] == "digest" and "Tóm tắt" in m["text"]) == 1, SENT)

    # ---- §15 Tải: a blocked hook does not starve others; backlog and byte quota; SQL busy; disk full; retention ----
    gate2 = asyncio.Event()

    async def slow_task(brain, text, level):
        MODEL["calls"] += 1
        if "SLOWHOOK" in text:
            await gate2.wait()
        return "ok", ""
    fl = make(run_task=slow_task)
    hsl1, tsl1, _ = fl.create("/b1", name="Chậm", target="task", text="SLOWHOOK")
    hsl2, tsl2, _ = fl.create("/b1", name="Nhanh", target="task", text="fast")
    for i in range(3):
        await fl.accept(hsl1["id"], tsl1, b"{}", "application/json", "")
    t_start = time.monotonic()
    fast = [await fl.accept(hsl2["id"], tsl2, b"{}", "application/json", "") for _ in range(5)]
    for _ in range(100):
        if all(fl.store().get(x[1]["event_id"])["status"] == "done" for x in fast):
            break
        await asyncio.sleep(0.02)
    starved = time.monotonic() - t_start
    gate2.set()
    await fl.wait_idle()
    check("§15 Tải: a hook stuck on a slow run does not starve another hook (its 5 events done while the first waits)",
          all(fl.store().get(x[1]["event_id"])["status"] == "done" for x in fast) and starved < 2, starved)
    hbq, tbq, _ = f.create("/b1", name="Byte", target="task", text="x", limits={"backlog_mb": 1}, )
    f.pause(hbq["id"], True)
    codes = [(await f.accept(hbq["id"], tbq, b"x" * 200_000, "text/plain", ""))[0] for _ in range(7)]
    f.pause(hbq["id"], False)
    await f.wait_idle()
    check("§15 Tải: the byte quota of the backlog refuses with 429 before anything is stored", codes[:5] == [202] * 5
          and 429 in codes, codes)
    lock = sqlite3.connect(str(STATE / "webhook_events.sqlite3"), timeout=1, isolation_level=None)
    lock.execute("BEGIN EXCLUSIVE")
    t_b = time.monotonic()
    cbz, rbz = await f.accept(hbq["id"], tbq, b"{}", "application/json", "busy-1")
    lock.execute("ROLLBACK")
    lock.close()
    check("§15 Tải: SQL busy past the finite timeout answers 503 (retry later), nothing stored",
          cbz == 503 and rbz["code"] == "store_busy" and time.monotonic() - t_b < 15
          and not st._db.execute("SELECT 1 FROM dedup WHERE idem_key='h:busy-1'").fetchone(), (cbz, rbz))
    sp2 = ws.Store(Path(tempfile.mkdtemp(prefix="mx-ret-")) / "e.sqlite3")
    old_t2 = time.time() - 400 * 86400
    for s_ in ("queued", "unknown", "waiting", "blocked", "received", "done"):
        sp2._db.execute("INSERT INTO events(id, hook_id, received_at, body, body_sha, status, finished_at) VALUES(?,?,?,?,"
                        "?,?,?)", (f"ev_{s_}", "wh_r", old_t2, b"x", "", s_, old_t2 if s_ == "done" else 0))
    sp2.prune(keep_days={"wh_r": 1})
    left = sorted(r[0] for r in sp2._db.execute("SELECT status FROM events"))
    check("§15 Tải: retention never deletes pending, unknown, waiting or blocked events", left == sorted(
        ["queued", "unknown", "waiting", "blocked", "received"]), left)

    # ---- §15 Tương thích ----
    smg = Path(tempfile.mkdtemp(prefix="mx-migrate-"))
    legacy = {"hooks": [{"id": "wh_legacy", "name": "Lead cũ", "brain": "/b1", "target": "task", "text": "Gọi lại",
                         "level": "suggest", "chat_id": "web:1", "enabled": True, "token_hash": wt.hash_token("legacy-tok"),
                         "created_at": 1, "seen_keys": ["k-old"], "history": [{"run_id": "x", "status": "done"}]}]}
    (smg / "webhooks.json").write_text(json.dumps(legacy), encoding="utf-8")
    fm = make(smg)
    h1 = fm._find_hook("wh_legacy")
    rev1 = h1["revision"]
    fm.store().meta_del("hooks_migrated")
    (smg / "webhooks.json").write_text(json.dumps(legacy), encoding="utf-8")
    fm._store.close()
    fm._store = None
    fm2 = make(smg)
    h2_ = fm2._find_hook("wh_legacy")
    MODEL["calls"] = 0
    cq, rq_ = await fm2.accept("wh_legacy", "legacy-tok", b'{"a":1}', "application/json", "")
    await fm2.wait_idle()
    app2 = FastAPI()
    app2.include_router(fm2.router)
    cl2 = httpx.AsyncClient(transport=httpx.ASGITransport(app=app2), base_url="http://t")
    rq2 = await cl2.post("/hooks/wh_legacy?token=legacy-tok", content=b"{}")
    await fm2.wait_idle()
    check("§15 Tương thích: migrating twice keeps the id, token, brain, level, chat and history; an old hook keeps "
          "working (its ?token= URL too) and stays one AI action with no filter added",
          h1["token_hash"] == h2_["token_hash"] == wt.hash_token("legacy-tok") and h2_["brain"] == "/b1"
          and h2_["level"] == "suggest" and h2_["chat_id"] == "web:1" and h2_["revision"] == rev1
          and cq == 202 and rq2.status_code == 202 and MODEL["calls"] == 2 and not h2_.get("rules")
          and (await fm2.accept("wh_legacy", "legacy-tok", b"{}", "application/json", "k-old"))[0] == 200)
    hnew, tnew, _ = fm2.create("/b1", name="Mới", target="task", text="x")
    rq3 = await cl2.post(f"/hooks/{hnew['id']}?token={tnew}", content=b"{}")
    check("§10: a NEW hook does not accept the token in the URL (only older hooks keep ?token=)", rq3.status_code == 401)
    r_list = await cl2.get("/webhooks")
    check("§15 Tương thích: the old admin API still answers (list, update, rotate, test)", r_list.status_code == 200
          and (await cl2.post("/webhooks/rotate", json={"id": "wh_legacy"})).status_code == 200
          and (await cl2.post("/webhooks/test", json={"id": "wh_legacy"})).status_code == 200)
    await cl2.aclose()
    import webhook_rollback as rb
    fm2.store()._db.execute("UPDATE events SET status='running', lease_until=? WHERE id=?", (time.time() + 600,
                                                                                            rq_["event_id"]))
    refused = rb.run(smg)
    fm2.store()._db.execute("UPDATE events SET status='unknown', lease_until=0 WHERE id=?", (rq_["event_id"],))
    fm2._store.close()
    fm2._store = None
    done_rb = rb.run(smg)
    leg = json.loads((smg / "webhooks.json").read_text(encoding="utf-8"))
    fm3 = make(smg)
    check("§15 Tương thích / §13: the rollback tool refuses while a lease is live; with the server stopped it backs the "
          "store up, exports the backlog, writes the legacy webhooks.json (a hook using new features switched off), and "
          "the next start migrates it again; the new build never runs the old config beside its store",
          not refused["ok"] and done_rb["ok"] and Path(done_rb["backup"]).exists()
          and (Path(done_rb["out_dir"]) / "backlog.jsonl").read_text().count(rq_["event_id"]) == 1
          and any(x["id"] == "wh_legacy" and x["enabled"] for x in leg["hooks"])
          and fm3._find_hook("wh_legacy") is not None and not (smg / "webhooks.json").exists(), (refused, done_rb))

    # ---- §16.1 / §16.5: every accepted event found after a restart with a clear state; the timeline explains ----
    accepted = [r[0] for r in st._db.execute("SELECT event_id FROM receipts WHERE result='accepted'")]
    f.store().close()
    f._store = None
    fz = make()
    known = ("received", "queued", "running", "done", "silent", "waiting", "blocked", "failed", "unknown", "dead",
             "cancelled", "filtered", "invalid", "duplicate")
    lost = [e for e in accepted if (fz.store().get(e) or {}).get("status") not in known]
    check("§16.1: every event answered 202 is found after a restart, each with a final or waiting state",
          len(accepted) > 50 and not lost, (len(accepted), lost[:5]))
    pev = fz.store().get(next(x for x in fz.store().page(hook_id=hfo["id"])["items"])["id"])
    tl = wt.timeline(pev)
    check("§16.5: the timeline says why it ran and which handler took it (with its job id)",
          any(t["step"] == "received" for t in tl) and any(t["step"] == "receipt" and "job-" in t["detail"] for t in tl)
          and any(t["step"] == "result" for t in tl), tl)
    await cl.aclose()


# ---- §16.7: the real host app: the public door is /hooks/ only; admin, raw and replay need the login ----
os.environ["JAVIS_REQUIRE_LOGIN"] = "1"
import main  # noqa: E402


async def host():
    guard = {"n": 0}

    def no_model(*a, **k):
        guard["n"] += 1
        raise AssertionError("FAIL-FAST: a real model path was reached")
    main.webhook_feature.deps.run_task = no_model
    main.webhook_feature.deps.run_workflow = no_model
    main.incident_desk.deps.ask = no_model
    t = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=t, base_url="http://127.0.0.1:8000") as c:
        hooks = await c.get("/webhooks")
        raw = await c.get("/webhooks/events/ev_x", params={"raw": 1})
        rep = await c.post("/webhooks/events/replay", json={"id": "ev_x", "confirm": True})
        exp = await c.get("/webhooks/events/export", params={"body": 1, "raw": 1})
        pub = await c.post("/hooks/wh_unknown", content=b"{}")
    check("§16.7: with the login gate on, the admin, raw view, replay and export routes refuse an anonymous caller; the "
          "public /hooks/ door answers (401 for an unknown hook), with no model path reached",
          hooks.status_code in (401, 403) and raw.status_code in (401, 403) and rep.status_code in (401, 403)
          and exp.status_code in (401, 403) and pub.status_code == 401 and guard["n"] == 0,
          (hooks.status_code, raw.status_code, rep.status_code, exp.status_code, pub.status_code))

if __name__ == "__main__":
    asyncio.run(matrix())
    asyncio.run(host())
    if fails:
        print(f"\nFAIL {len(fails)}: " + ", ".join(fails))
        sys.exit(1)
    print("\nOK - test_webhook_spec_matrix: all pass")
