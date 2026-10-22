"""0.274.0: fixes from the independent review of webhook platform M5 (operations), each red before the fix.

    python tests/run.py webhook_m5_review      (no network, no model)

P2 an approval request whose first notice failed was dropped in errors_only/daily_digest (resend without branches);
P2 a workflow that stopped to ask the owner was silenced in errors_only/daily_digest;
P2 after the cooldown the breaker let BREAKER_FAILS attempts through, not one;
P2 retention deleted (and emptied the body of) events still waiting for approval;
P2 per_day and ai_per_day were undercounted after the hourly prune (cap of 500 rows);
P2 the digest hour and the AI-budget midnight followed the server's time zone, not the owner's;
P2 an AI-budget refusal (even ai_per_day 0) went to incident triage, which may call a model;
P2 one failing receiver filled the backlog and made the whole hook refuse events;
P3 budget counted rows not runs; breaker kept after the target changed; breaker notice ignored `none` and was lost on a
   failed send; one hook's digest error stopped the others, retried without cap, counted weeks; needs_you not
   paginated, Failed without dead, Filtered without invalid/duplicate; CSV formulas after tab/CR/spaces.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

STATE = Path(tempfile.mkdtemp(prefix="javis-wh-m5r-"))
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


FEAT = Path(tempfile.mkdtemp(prefix="m5r-feat-"))
sent, hits, incidents, ai_calls = [], [], [], []
send_ok = {"v": True}
crm = {"v": 200}
wf_answer = {"v": ("Cần anh chọn mẫu A hay B?", "", True)}


async def run_task(brain, text, level):
    ai_calls.append(level)
    return "ok", ""


async def run_wf(brain, slug, text, level):
    return wf_answer["v"]


async def send(chat_id, text, viec=None, web="", brain="", dedup=""):
    sent.append({"text": text, "status": (viec or {}).get("status"), "dedup": dedup})
    return (True, "") if send_ok["v"] else (False, "down")


def handler(req):
    hits.append(req.url.host)
    return httpx.Response(crm["v"])


def make():
    return wt.WebhookFeature(wt.WebhookDeps(state_dir=lambda: FEAT, run_task=run_task, run_workflow=run_wf, send=send,
                                            base_url=lambda _r: "", workflow_exists=lambda b, s: True,
                                            incident_hook=lambda *a, **k: incidents.append(a),
                                            http_transport=httpx.MockTransport(handler), resolve=lambda h: ["93.184.216.34"]))


async def main():
    f = make()
    st = f.store()

    # P2-1: approval request resent after a failed delivery, errors_only
    ha, toka, _ = f.create("/b", name="Duyệt", target="", text="", notify="errors_only",
                           actions=[{"id": "pos", "kind": "tool", "tool": "pos_x"}])
    send_ok["v"] = False
    code, r = await f.accept(ha["id"], toka, b"{}", "application/json", "a1")
    await f.wait_idle()
    send_ok["v"] = True
    sent.clear()
    f.clock = lambda: time.time() + 4000          # the outbox resends after its backoff
    await f.sweep()
    f.clock = time.time
    check("P2: the approval request is resent at the next sweep, as an approval request",
          any("duyệt" in m["text"].lower() or "approval" in m["text"].lower() for m in sent)
          and st.get(r["run_id"])["notified_at"] > 0, sent)

    # P2-2: a workflow question in errors_only
    hw, tokw, _ = f.create("/b", name="Hỏi", target="workflow", workflow="wf", notify="errors_only")
    sent.clear()
    code, r = await f.accept(hw["id"], tokw, b"{}", "application/json", "w1")
    await f.wait_idle()
    check("P2: a workflow that stops to ask the owner is told in errors_only", st.get(r["run_id"])["status"] == "waiting"
          and any("mẫu A" in m["text"] for m in sent), sent)

    # P2-7: AI budget refusal is not an incident
    h0, tok0, _ = f.create("/b", name="Không AI", target="task", text="x", ai_per_hour=0)
    incidents.clear()
    for i in range(3):
        await f.accept(h0["id"], tok0, b"{}", "application/json", f"z{i}")
    await f.wait_idle()
    check("P2: an AI-budget refusal never goes to incident triage (which may use a model)", not incidents, incidents)

    # P2-3: half-open breaker
    crm["v"] = 500
    hb, tokb, _ = f.create("/b", name="CRM", target="", text="", notify="none",
                           actions=[{"id": "crm", "kind": "http", "url": "https://crm.example/h"}])
    hits.clear()
    for i in range(ws.BREAKER_FAILS):
        await f.accept(hb["id"], tokb, b"{}", "application/json", f"b{i}")
        await f.wait_idle()
    for i in range(5):
        await f.accept(hb["id"], tokb, b"{}", "application/json", f"p{i}")
    await f.wait_idle()
    tk = wa.target_key(f._find_hook(hb["id"])["actions"][0])
    st._db.execute("UPDATE breakers SET open_until=? WHERE hook_id='*' AND action_id=?", (time.time() - 1, tk))
    st._db.execute("UPDATE events SET next_at=? WHERE hook_id=? AND status='queued'", (time.time() - 1, hb["id"]))
    st._db.execute("UPDATE deliveries SET next_at=? WHERE event_id IN (SELECT id FROM events WHERE hook_id=?)",
                   (time.time() - 1, hb["id"]))
    before = len(hits)
    f._kick()
    await f.wait_idle()
    check("P2: after the cooldown ONE attempt goes to a receiver still down, then the breaker reopens",
          len(hits) - before == 1 and st.breaker_open_until("*", tk) > time.time(), (len(hits) - before))

    # P2-8: a paused receiver does not fill the backlog
    hc, tokc, _ = f.create("/b", name="Hai nhánh", target="task", text="x", notify="none", limits={"backlog": 3, "per_hour": 100},
                           actions=[{"id": "crm", "kind": "http", "url": "https://crm.example/h"}, {"id": "ai", "kind": "ai"}])
    codes = []
    for i in range(ws.BREAKER_FAILS + 8):
        codes.append((await f.accept(hc["id"], tokc, b"{}", "application/json", f"c{i}"))[0])
        await f.wait_idle()
    # Spec §11: the backlog counts every event not settled, a paused receiver's included; past it the sender gets 429
    # with a Retry-After (nothing accepted is lost, the sender sends again later). The default is 10 000 events.
    ev_c = st.page(hook_id=hc["id"], limit=100)["items"]
    check("P2 (spec §11): with the CRM paused, the AI delivery of each accepted event still runs; once the backlog is "
          "reached the sender is refused with 429 (not lost)", 429 in codes and codes[:3] == [202] * 3
          and all(next(d for d in e["deliveries"] if d["action_id"] == "ai")["state"] == "succeeded" for e in ev_c), codes)
    crm["v"] = 200

    # P3-10: breaker reset when the target changes
    f.update(hc["id"], {"actions": [{"id": "crm", "kind": "http", "url": "https://crm2.example/h"}, {"id": "ai", "kind": "ai"}]})
    check("P3: pointing the action elsewhere clears its breaker", st.breaker_open_until(
        "*", wa.target_key({"id": "crm", "kind": "http", "url": "https://crm.example/h", "headers": {}})) == 0)

    # P3-11: breaker notice respects `none`; a failed send is retried
    sent.clear()
    await f._breaker_notice({"id": "wh_q", "name": "Q", "notify": "none"}, "crm", "x")
    check("P3: no breaker notice in notify none", not sent)
    send_ok["v"] = False
    hn, tokn, _ = f.create("/b", name="Báo", target="task", text="x")
    await f._breaker_notice(f._find(f._load(), hn["id"]), "crm", "HTTP 500")
    send_ok["v"] = True
    sent.clear()
    f.clock = lambda: time.time() + 4000
    await f.sweep()
    f.clock = time.time
    check("P3: a breaker notice that could not be sent is sent at the next sweep",
          any("crm" in m["text"] for m in sent), sent)

    # P3-13: needs_you paginates; Failed includes dead
    for i in range(25):
        st._db.execute("INSERT INTO events(id, hook_id, received_at, body, body_sha, status, finished_at) VALUES(?,?,?,?,?,?,?)",
                       (f"ev_n{i:02d}", "wh_page", 1000 + i, b"", "", "unknown" if i % 2 else "waiting", 1000 + i))
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(f.router)
    cl = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    p1 = (await cl.get("/webhooks/events", params={"hook": "wh_page", "status": "needs_you", "limit": 20})).json()
    p2 = (await cl.get("/webhooks/events", params={"hook": "wh_page", "status": "needs_you", "limit": 20, "before": p1["next"]})).json()
    check("P3: the needs_you filter pages (25 events: 20 then 5)", len(p1["items"]) == 20 and p1["next"] and len(p2["items"]) == 5,
          (len(p1["items"]), p1.get("next"), len(p2["items"])))
    st._db.execute("INSERT INTO events(id, hook_id, received_at, body, body_sha, status) VALUES('ev_dead','wh_page',5,x'','','dead')")
    r = (await cl.get("/webhooks/events", params={"hook": "wh_page", "status": "failed,dead"})).json()
    check("P3: the Failed filter includes dead events", any(x["id"] == "ev_dead" for x in r["items"]))

    # P3-14: CSV formulas after tab, CR, spaces
    hx, tokx, _ = f.create("/b", name="CSV", target="task", text="x", notify="none")
    for k in ("\t=1+1", "\r=1+1", "  =1+1", " @SUM(A1)"):
        await f.accept(hx["id"], tokx, b"{}", "application/json", k)
    await f.wait_idle()
    r = await cl.get("/webhooks/events/export", params={"hook": hx["id"], "format": "csv"})
    import csv
    import io
    rows = list(csv.DictReader(io.StringIO(r.text)))
    check("P3: CSV cells starting with tab/CR or spaces before = @ are neutralised",
          all(str(wt._csv_safe(v)).startswith("'") for v in ("\t=1+1", "\r=1+1", "  =1+1", " @SUM(A1)", "-2+3"))
          and wt._csv_safe("Đã ghi.") == "Đã ghi." and rows and all(x["idem_key"].startswith("'") for x in rows),
          [x["idem_key"] for x in rows])
    check("CSV carries the trace column too", "trace" in rows[0])
    await cl.aclose()


asyncio.run(main())

# ---- store-level cases ----
# P2-4: retention keeps waiting events (and their body)
s = ws.Store(Path(tempfile.mkdtemp(prefix="m5r-keep-")) / "e.sqlite3")
now = time.time()
old = now - 10 * 86400            # within APPROVAL_TTL_DAYS, far past the hook's 1-day retention
c, i = s.ingest({"id": "wh_w", "brain": "/b"}, b'{"order": 1}', "application/json", "w", now=old)
s.triage_commit(i["event_id"], {"decision": "run"}, [], now=old)
w = s.claim("W", now=old)
s.branches_init(w["id"], w["fence"], [{"id": "pos", "kind": "tool"}], wa.delivery_id)
s.branch_finish(w["id"], w["fence"], "pos", "approval", "waiting", now=old)
s.settle(w["id"], w["fence"], lambda rows: ("", ""), now=old)
s.prune(now=now, keep_days={"wh_w": 1})
ev = s.get(w["id"], True)
check("P2: an event waiting for approval survives retention, with its body", ev is not None and ev["status"] == "waiting"
      and bytes(ev["body"]) == b'{"order": 1}', ev and ev["status"])
s.prune(now=now + (ws.APPROVAL_TTL_DAYS - 10 + 1) * 86400)
ev = s.get(w["id"])
check("whole chain: an approval nobody answers expires after APPROVAL_TTL_DAYS (settled, never stuck)",
      ev["status"] == "failed" and "nobody answered" in ev["error"] and ev["branches"][0]["status"] == "cancelled", ev["status"])

# P2-5: day quota and AI budget not undercounted after prune
s2 = ws.Store(Path(tempfile.mkdtemp(prefix="m5r-q-")) / "e.sqlite3")
H = {"id": "wh_q", "brain": "/b", "limits": {"per_day": 700, "per_hour": 600, "backlog": 50}}
now = time.time()
for n in range(700):
    s2._db.execute("INSERT INTO events(id, hook_id, received_at, body, body_sha, status, finished_at) VALUES(?,?,?,?,?,?,?)",
                   (f"ev_q{n}", "wh_q", now - 7200 - n * 60, b"", "", "done", now - 7200 - n * 60))
    s2._db.execute("INSERT INTO ai_runs(hook_id, event_id, at) VALUES(?,?,?)", ("wh_q", f"ev_q{n}", now - 7200 - n * 60))
code1, _ = s2.ingest(H, b"{}", "", "x1", now=now)
s2.prune(now=now)
code2, _ = s2.ingest(H, b"{}", "", "x2", now=now)
check("P2: the day quota still refuses after the hourly prune (no cap-prune of the last 25 h)", code1 == 429 and code2 == 429,
      (code1, code2))
check("P2: the AI budget still counts all 700 runs after prune", s2.ai_runs_since("wh_q", now - 86400) == 700)

# P3-9: budget counts runs (dispatches), not rows
s3 = ws.Store(Path(tempfile.mkdtemp(prefix="m5r-ai-")) / "e.sqlite3")
c, i = s3.ingest({"id": "wh_ai", "brain": "/b"}, b"{}", "", "k")
s3.triage_commit(i["event_id"], {"decision": "run"}, [])
for _ in range(3):
    w = s3.claim("W")
    s3.branches_init(w["id"], w["fence"], [{"id": "main", "kind": "ai"}], wa.delivery_id)
    s3.branch_dispatch(w["id"], w["fence"], "main", ai=True)
    s3.branch_finish(w["id"], w["fence"], "main", "failed", "boom")
    s3.settle(w["id"], w["fence"], lambda rows: ("", "boom"))
    s3.retry(w["id"])
check("P3: three runs of one event count three against the AI budget", s3.ai_runs_since("wh_ai", 0) == 3)

# P2-6: the owner's time zone
import localefmt  # noqa: E402
from datetime import datetime  # noqa: E402
ts = datetime(2026, 10, 19, 2, 30, tzinfo=__import__("datetime").timezone.utc).timestamp()   # 09:30 in Vietnam
check("P2: the digest hour and the day start follow the owner's zone (09:30 Vietnam = 02:30 UTC)",
      str(localefmt.tz()) in ("Asia/Ho_Chi_Minh", "Asia/Saigon") and wt._local(ts).hour == 9
      and datetime.fromtimestamp(wt._day_start(ts), localefmt.tz()).hour == 0, (str(localefmt.tz()), wt._local(ts)))

# P3-12: one hook's digest failure does not stop the others
D = Path(tempfile.mkdtemp(prefix="m5r-dg-"))
calls = []


async def send_boom(chat_id, text, viec=None, web="", brain="", dedup=""):
    calls.append(dedup)
    if len(calls) == 1:
        raise RuntimeError("channel crashed")
    return True, ""


async def dg():
    f = wt.WebhookFeature(wt.WebhookDeps(state_dir=lambda: D, run_task=run_task, run_workflow=run_wf, send=send_boom,
                                         base_url=lambda _r: ""))
    st = f.store()
    ids = []
    for n in range(2):
        h, tok, _ = f.create("/b", name=f"D{n}", target="task", text="x", notify="daily_digest")
        ids.append(h["id"])
        await f.accept(h["id"], tok, b"{}", "application/json", f"d{n}")
    await f.wait_idle()
    after = wt._local(time.time()).replace(hour=__import__("webhook_worker").DIGEST_HOUR, minute=10).timestamp()
    after = max(after, time.time() + 1)
    await f._digest(after)
    return st, ids, after

st, ids, after = asyncio.run(dg())
check("P3: a digest that raises for one hook does not stop the next hook's digest", len(calls) == 2
      and st.meta_get(f"digest_day:{ids[1]}") != "", calls)

if fails:
    print(f"\nFAIL {len(fails)}: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_webhook_m5_review: all pass")
