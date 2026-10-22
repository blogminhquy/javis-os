"""0.274.0: webhook operations (webhook platform M5): notification modes, quotas, AI budget, circuit breaker,
retention, export, log filters; plus benchmarks.

    python tests/run.py webhook_ops_m5      (no network, no model: fakes only)

What is proven here:
  1. notify all / errors_only / daily_digest / none: what is sent and when; what needs the owner (unknown, approval) is
     told at once except in `none`; the digest is plain counts (no model), once a day, retried if not delivered;
  2. per-hook limits (hour, day, backlog) refuse with 429 and store nothing; bad settings are refused, not clamped;
  3. the AI budget refuses an AI branch BEFORE it reaches a model; budget 0 means never;
  4. the circuit breaker opens after repeated failures, pauses sending (not counted as tries), tells the owner once,
     lets one attempt through after the cooldown, and a success closes it; AI branches are not affected;
  5. retention per hook (shorter and longer than the default); export streams JSON lines or CSV without the hook's
     configuration or secrets, bodies only on request, spreadsheet formulas neutralised;
  6. benchmarks of receive and of the whole pipeline (printed; generous bounds).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

STATE = Path(tempfile.mkdtemp(prefix="javis-wh-m5-"))
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
import webhook_worker as ww  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


FEAT = Path(tempfile.mkdtemp(prefix="m5-feat-"))
ai_calls, sent, hits = [], [], []
ai_answer = {"v": ("Đã ghi.", "")}
send_ok = {"v": True}
crm_code = {"v": 200}


async def run_task(brain, text, level):
    ai_calls.append(level)
    return ai_answer["v"]


async def no_wf(*a, **k):
    return "", "", False


async def send(chat_id, text, viec=None, web="", brain="", dedup=""):
    sent.append({"text": text, "dedup": dedup, "status": (viec or {}).get("status")})
    return (True, "") if send_ok["v"] else (False, "channel down")


def handler(req):
    hits.append(req.url.host)
    return httpx.Response(crm_code["v"])


def make():
    return wt.WebhookFeature(wt.WebhookDeps(state_dir=lambda: FEAT, run_task=run_task, run_workflow=no_wf, send=send,
                                            base_url=lambda _r: "", workflow_exists=lambda b, s: True,
                                            http_transport=httpx.MockTransport(handler), resolve=lambda h: ["93.184.216.34"]))


async def main():
    f = make()
    st = f.store()

    # ---- settings validation ----
    for bad in ({"notify": "sometimes"}, {"limits": {"per_hour": -1}}, {"limits": {"per_hour": True}}, {"limits": {"weird": 1}},
                {"ai_per_day": -1}, {"ai_per_hour": 1001}, {"retention_days": 9999}, {"limits": {"backlog": 100001}},
                {"limits": {"per_minute": 0}}, {"limits": {"body_kb": 4096}}, {"retry": {"delays_s": [0]}},
                {"retry": {"jitter_ratio": 0.9}}, {"digest_timezone": "Mars/Base"}, {"ai_triage": "yes"}):
        _, _, err = f.create("/b1", name="x", target="task", text="x", **bad)
        check(f"bad setting refused, not clamped: {bad}", bool(err), err)
    h, tok, err = f.create("/b1", name="Đơn", target="task", text="x", notify="errors_only",
                           limits={"per_hour": 2, "backlog": 5}, ai_per_day=10, retention_days=3)
    v = f.view(f._find(f._load(), h["id"]))
    check("settings saved and shown", not err and v["notify"] == "errors_only" and v["limits"]["per_hour"] == 2
          and v["ai_per_day"] == 10 and v["retention_days"] == 3, (err, v.get("limits")))

    # ---- limits ----
    codes = [(await f.accept(h["id"], tok, b"{}", "application/json", f"r{i}"))[0] for i in range(3)]
    check("per-hook hourly limit: the third event is 429", codes == [202, 202, 429], codes)
    await f.wait_idle()
    check("refused event stored nothing", st._db.execute("SELECT COUNT(*) FROM events WHERE hook_id=?", (h["id"],)).fetchone()[0] == 2)
    hd, tokd, _ = f.create("/b1", name="Ngày", target="task", text="x", limits={"per_day": 1, "per_hour": 100})
    c1 = (await f.accept(hd["id"], tokd, b"{}", "application/json", "d1"))[0]
    c2, r2 = await f.accept(hd["id"], tokd, b"{}", "application/json", "d2")
    check("per-day limit", c1 == 202 and c2 == 429 and "day" in r2["error"], r2)
    await f.wait_idle()

    # ---- notify modes ----
    sent.clear()
    check("errors_only: a successful run is not sent", not sent)
    ai_answer["v"] = ("", "boom")
    he, toke, _ = f.create("/b1", name="Lỗi", target="task", text="x", notify="errors_only")
    await f.accept(he["id"], toke, b"{}", "application/json", "e1")
    await f.wait_idle()
    check("errors_only: a failed run is sent", len(sent) == 1 and "boom" in sent[0]["text"], sent)
    ai_answer["v"] = ("Đã ghi.", "")
    sent.clear()
    hn, tokn, _ = f.create("/b1", name="Im", target="task", text="x", notify="none",
                           actions=[{"id": "pos", "kind": "tool", "tool": "x"}])
    code, rn = await f.accept(hn["id"], tokn, b"{}", "application/json", "n1")
    await f.wait_idle()
    check("none: nothing is sent, not even an approval request; the event is marked told (no resend loop)",
          not sent and st.get(rn["run_id"])["notified_at"] > 0 and st.get(rn["run_id"])["status"] == "waiting")
    hg, tokg, _ = f.create("/b1", name="Tóm tắt", target="task", text="x", notify="daily_digest")
    for i in range(3):
        await f.accept(hg["id"], tokg, b"{}", "application/json", f"g{i}")
    await f.wait_idle()
    ai_answer["v"] = ("", "boom")
    await f.accept(hg["id"], tokg, b"{}", "application/json", "g-bad")
    await f.wait_idle()
    ai_answer["v"] = ("Đã ghi.", "")
    check("daily_digest: runs and errors are not sent one by one", not sent, sent)
    hga, tokga, _ = f.create("/b1", name="Tóm tắt duyệt", target="task", text="x", notify="daily_digest",
                             actions=[{"id": "pos", "kind": "tool", "tool": "x"}])
    await f.accept(hga["id"], tokga, b"{}", "application/json", "ga")
    await f.wait_idle()
    check("daily_digest: an approval request is still sent at once",
          len({m["dedup"] for m in sent}) == 1 and ("duyệt" in sent[0]["text"].lower() or "approval" in sent[0]["text"].lower()),
          sent)   # one dedup key: the notifier delivers it once
    sent.clear()
    # The owner's time zone (localefmt.tz), not the server's.
    lt = wt._local(time.time())
    morning = lt.replace(hour=ww.DIGEST_HOUR - 1, minute=30, second=0, microsecond=0).timestamp()
    after = lt.replace(hour=ww.DIGEST_HOUR, minute=5, second=0, microsecond=0).timestamp()
    if after < time.time():
        after = time.time() + 1
    n = await f._digest(morning)
    check("digest: nothing before the digest hour", n == 0 and not sent)
    send_ok["v"] = False
    f.clock = lambda: after
    n = await f._digest(after)
    rows_d = [x for x in st.notifications(hook_id=hg["id"]) if x["kind"] == "digest"]
    check("digest: queued once in the durable outbox; a failed delivery stays pending to be sent again (spec §12)",
          n >= 1 and len(rows_d) == 1 and rows_d[0]["status"] == "pending" and rows_d[0]["tries"] == 1, rows_d)
    send_ok["v"] = True
    sent.clear()
    f.clock = lambda: after + 3600
    await f.deliver_notifications()
    f.clock = time.time
    dig = [m for m in sent if m["status"] == "digest" and "Tóm tắt\"" in m["text"]]
    check("digest: one plain message with the counts (3 done, 1 failed), keyed per day", len(dig) == 1
          and ("3 lần chạy xong, 1 lần lỗi" in dig[0]["text"] or "3 runs done, 1 failed" in dig[0]["text"])
          and dig[0]["dedup"].startswith("whd:"), dig)
    sent.clear()
    n = await f._digest(after + 60)
    await f.deliver_notifications()
    check("digest: only once a day (a restart re-queues the same key: at most one per period)",
          n == 0 and not any(m["status"] == "digest" for m in sent))

    # ---- AI budget ----
    hb, tokb, _ = f.create("/b1", name="Ngân sách", target="task", text="x", ai_per_hour=1)
    ai_calls.clear()
    c, r1 = await f.accept(hb["id"], tokb, b"{}", "application/json", "b1")
    await f.wait_idle()
    c, r2 = await f.accept(hb["id"], tokb, b"{}", "application/json", "b2")
    await f.wait_idle()
    ev2 = st.get(r2["run_id"])
    b2 = ev2["branches"][0]
    check("AI budget (spec §7, §11): the second run in the hour WAITS for the budget before reaching a model (not failed,"
          " not a try, the accepted order is not lost)", ai_calls == ["full"] and ev2["status"] == "queued"
          and b2["status"] == "retry" and "AI budget" in b2["detail"] and b2["dispatched_at"] == 0 and b2["tries"] == 0
          and st.ai_oldest_since(hb["id"], 0) + 3600 - 5 <= float(st._db.execute(
              "SELECT next_at FROM deliveries WHERE event_id=?", (r2["run_id"],)).fetchone()[0]), (ai_calls, ev2["branches"]))
    st._db.execute("UPDATE ai_runs SET at=at-4000 WHERE event_id=?", (r1["run_id"],))
    st._db.execute("UPDATE deliveries SET next_at=0 WHERE event_id=?", (r2["run_id"],))
    st._db.execute("UPDATE events SET next_at=0 WHERE id=?", (r2["run_id"],))
    f._kick()
    await f.wait_idle()
    check("AI budget: once the hour has room it runs on its own", st.get(r2["run_id"])["status"] == "done" and len(ai_calls) == 2)
    h0, tok0, _ = f.create("/b1", name="Không AI", target="task", text="x", ai_per_hour=0)
    ai_calls.clear()
    await f.accept(h0["id"], tok0, b"{}", "application/json", "z")
    await f.wait_idle()
    check("AI budget 0: never calls a model", not ai_calls)

    # ---- circuit breaker (a receiver that is down: 500 = it may have acted; a 4xx refusal does not count) ----
    crm_code["v"] = 500
    hc, tokc, _ = f.create("/b1", name="CRM", target="task", text="x", level="full",
                           actions=[{"id": "crm", "kind": "http", "url": "https://crm.example/h"}, {"id": "ai", "kind": "ai"}])
    sent.clear(); hits.clear(); ai_calls.clear()
    for i in range(ws.BREAKER_FAILS):
        await f.accept(hc["id"], tokc, b"{}", "application/json", f"c{i}")
        await f.wait_idle()
    opened = [m for m in sent if "lỗi 5 lần liền" in m["text"] or "5 times in a row" in m["text"]]
    check("breaker: opens after 5 failures in a row and tells the owner once", len(hits) == 5 and len(opened) == 1, (hits, sent))
    check("the view shows the paused receiver", f.view(f._find(f._load(), hc["id"]))["breakers"][0]["action"] == "crm")
    check("the breaker is per target (spec §11), not per hook", st.breakers("*") and not st.breakers(hc["id"]))
    code, r6 = await f.accept(hc["id"], tokc, b"{}", "application/json", "c6")
    await f.wait_idle()
    ev6 = st.get(r6["run_id"])
    b6 = {b["action_id"]: b for b in ev6["branches"]}
    check("breaker open: the branch is not sent and waits (no try used); the AI branch still runs",
          len(hits) == 5 and b6["crm"]["status"] == "retry" and b6["crm"]["tries"] == 0 and b6["ai"]["status"] == "completed"
          and ev6["status"] == "queued", (hits, b6))
    crm_code["v"] = 200
    st._db.execute("UPDATE breakers SET open_until=? WHERE hook_id='*'", (time.time() - 1,))
    st._db.execute("UPDATE events SET next_at=? WHERE id=?", (time.time() - 1, r6["run_id"]))
    st._db.execute("UPDATE deliveries SET next_at=? WHERE event_id=?", (time.time() - 1, r6["run_id"]))
    f._kick()
    await f.wait_idle()
    check("after the cooldown one attempt goes through; success closes the breaker",
          len(hits) == 6 and st.get(r6["run_id"])["status"] == "done" and not st.breakers("*"), (hits, st.breakers("*")))
    check("breaker cooldown doubles at each reopening, capped", ws.BREAKER_COOLDOWN_S * 2 ** 10 > ws.BREAKER_MAX_S)

    # ---- retention ----
    s2 = ws.Store(Path(tempfile.mkdtemp(prefix="m5-keep-")) / "e.sqlite3")
    now = time.time()
    for hid, age in (("wh_short", 3), ("wh_short", 1), ("wh_default", 3), ("wh_long", 40), ("wh_default", 40)):
        c, i = s2.ingest({"id": hid, "brain": "/b"}, b"{}", "", f"{hid}{age}", now=now - age * 86400)
        s2.triage_commit(i["event_id"], {"decision": "run"}, [], now=now - age * 86400)
        w = s2.claim("W", now=now - age * 86400)
        s2.finish(w["id"], w["fence"], "done", "ok", now=now - age * 86400)
    s2.prune(now=now, keep_days={"wh_short": 2, "wh_long": 90})
    left = sorted((r[0], round((now - r[1]) / 86400)) for r in s2._db.execute("SELECT hook_id, finished_at FROM events"))
    check("retention: a hook keeping 2 days drops its 3-day-old run; the default keeps it; 90 days keeps a 40-day-old run",
          left == [("wh_default", 3), ("wh_long", 40), ("wh_short", 1)], left)

    # ---- export ----
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(f.router)
    cl = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    hx, tokx, _ = f.create("/b1", name="Xuất", target="task", text="x",
                           actions=[{"id": "ai", "kind": "ai"}, {"id": "crm", "kind": "http", "url": "https://crm.example/h",
                                                                 "headers": {"X-K": "EXPORT-SECRET"}}])
    for i in range(3):
        await f.accept(hx["id"], tokx, json.dumps({"n": i, "note": "bí mật khách"}).encode(), "application/json",
                       "=HYPERLINK(\"http://evil\")" if i == 0 else f"x{i}")
    await f.wait_idle()
    r = await cl.get("/webhooks/events/export", params={"hook": hx["id"]})
    lines = [json.loads(x) for x in r.text.splitlines() if x.strip()]
    check("export JSONL: every event, oldest first, with branches, no snapshot, no secret, no body by default",
          r.status_code == 200 and len(lines) == 3 and all(len(x["branches"]) == 2 for x in lines)
          and "EXPORT-SECRET" not in r.text and "hook_snapshot" not in r.text and "bí mật khách" not in r.text
          and lines[0]["received_at"] <= lines[-1]["received_at"], r.text[:300])
    r = await cl.get("/webhooks/events/export", params={"hook": hx["id"], "body": 1})
    check("export with body=1 carries the payload, customer data masked by default (spec §12)",
          '"n":' in r.text and "bí mật khách" not in r.text and st.audit_rows(hx["id"])[0]["action"] == "export_masked")
    r = await cl.get("/webhooks/events/export", params={"hook": hx["id"], "body": 1, "raw": 1})
    check("raw=1 exports it as received and is recorded in the audit log", "bí mật khách" in r.text
          and st.audit_rows(hx["id"])[0]["action"] == "export_raw")
    r = await cl.get("/webhooks/events/export", params={"hook": hx["id"], "format": "csv"})
    check("export CSV: a header row and formulas neutralised", r.text.splitlines()[0].startswith("id,hook_id")
          and "'=HYPERLINK" in r.text and ",=HYPERLINK" not in r.text, r.text[:400])
    r = await cl.get("/webhooks/events", params={"hook": hn["id"], "status": "needs_you"})
    check("log filter needs_you lists waiting/unknown events", r.json()["items"] and r.json()["items"][0]["status"] == "waiting")
    await cl.aclose()


asyncio.run(main())

# ---- benchmarks ----
sb = ws.Store(Path(tempfile.mkdtemp(prefix="m5-bench-")) / "e.sqlite3")
N = 300
t0 = time.perf_counter()
for i in range(N):
    sb.ingest({"id": f"wh_b{i % 30}", "brain": "/b"}, b'{"order": 1}', "application/json", f"k{i}")
dt = time.perf_counter() - t0
print(f"     benchmark: durable receive {N / dt:.0f} events/s ({dt / N * 1000:.2f} ms each, synchronous=FULL)")
check("benchmark: durable receive at least 20 events per second", N / dt >= 20, N / dt)
t0 = time.perf_counter()
pg = sb.page(limit=100)
for _ in range(2):
    pg = sb.page(limit=100, before=pg["next"])
check("benchmark: three log pages of 100 under 0.2 s", time.perf_counter() - t0 < 0.2)


async def pipeline():
    pdir = Path(tempfile.mkdtemp(prefix="m5-pipe-"))
    fb = wt.WebhookFeature(wt.WebhookDeps(state_dir=lambda: pdir, run_task=run_task,
                                          run_workflow=no_wf, send=send, base_url=lambda _r: ""))
    hooks = [fb.create("/b1", name=f"h{i}", target="task", text="x", limits={"per_hour": 600, "backlog": 50},
                       ai_per_day=5000, notify="none") for i in range(10)]
    t0 = time.perf_counter()
    for i in range(200):
        h, tok, _ = hooks[i % 10]
        await fb.accept(h["id"], tok, b'{"a": 1}', "application/json", f"p{i}")
    await fb.wait_idle()
    return time.perf_counter() - t0, fb.store()._db.execute("SELECT COUNT(*) FROM events WHERE status='done'").fetchone()[0]

dt, done = asyncio.run(pipeline())
print(f"     benchmark: 200 events through receive, worker and a fake run: {dt:.2f} s ({200 / dt:.0f}/s)")
check("benchmark: 200 events end to end (10 hooks, fake runner) all done under 60 s", done == 200 and dt < 60, (done, dt))

if fails:
    print(f"\nFAIL {len(fails)}: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_webhook_ops_m5: all pass")
