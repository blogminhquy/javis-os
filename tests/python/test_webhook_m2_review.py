"""0.274.0: fixes from the independent review of webhook platform M2 (rules, business keys), each red before the fix.

    python tests/run.py webhook_m2_review      (no network, no model)

P1-1 a huge exponent (1e999999) stalled the event loop and answered 500 for good;
P1-2 a payload that broke the evaluator (overflow, deep nesting) ran UNFILTERED;
P2-1 a retried event that may have acted gave its business key back when it later died; a retried dead event ran
     without its key;
P2-2 mapped fields over 16 000 characters were cut mid-JSON and silently became {};
P2-3 several processes upgrading one old store at once: one failed with "duplicate column";
P2-4 inf/NaN broke the JSON routes; big numbers collided as business keys;
P3   unchecked business_key.field, cut long keys, TTL ending before the holder ran, idempotency key kept for ignored
     events, ignored events evicted last, card history flooded, simulate probing another brain, schema marker
     lowered, ttl_s 0, required null, rule size in bytes, Test button text.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

STATE = Path(tempfile.mkdtemp(prefix="javis-wh-m2r-"))
os.environ["JAVIS_STATE_DIR"] = str(STATE)
os.environ["JAVIS_NO_REAL_JUDGE_ENGINE"] = "1"
os.environ["JAVIS_WH_NO_NETWORK"] = "1"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import webhook_rules as wr  # noqa: E402
import webhook_store as ws  # noqa: E402
import webhook_triggers as wt  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


def refused(rules) -> str:
    try:
        wr.validate(rules)
        return ""
    except wr.RuleError as e:
        return str(e) or "refused"


def ingest_pre(st, hook, body, ct, idem, pre=None, now=None):
    """Spec §4.2: an event is stored first (202), its rules decided after the commit (triage). This replays the old
    "decided at ingest" calls through the two real steps; 200 = it will not run (ignored or duplicate)."""
    code, info = st.ingest(hook, body, ct, ("h:" + idem) if idem else "", now=now)
    if code != 202:
        return code, info
    p = dict(pre or {"decision": "run"})
    b = p.get("business_key")
    if b and "scope" in b:
        p["business_key"] = {"shared": b["scope"], "policy": 1, "hash": b["key"], "ttl_s": b["ttl_s"]}
    out = st.triage_commit(info["event_id"], p, [], now=now)
    return (202 if out == "queued" else 200), dict(info, status=out)


def ev(rules, body, ct="application/json"):
    return wr.evaluate(wr.validate(rules), body if isinstance(body, bytes) else body.encode(), ct)


# ---- P1-1 ----
t0 = time.perf_counter()
r = ev({"mapping": {"total": {"path": "total", "type": "integer"}, "t2": {"path": "total", "transform": "integer"}},
        "business_key": {"entity": "o", "path": "total", "type": "integer"}}, '{"total": 1e999999}')
dt = time.perf_counter() - t0
check("P1-1: 1e999999 is evaluated at once (stays text, not a million-digit int)", dt < 0.2, dt)
check("P1-1: and gives a clean decision (type error -> invalid), JSON-safe", r["decision"] == "invalid"
      and json.dumps(r, allow_nan=False), r["reason"])
t0 = time.perf_counter()
r = ev({"mapping": {"n": {"path": "n", "type": "integer"}}}, '{"n": ' + "9" * 5000 + "}")
check("P1-1: a 5000-digit integer literal is not parsed as a number", time.perf_counter() - t0 < 0.2 and r["decision"] == "invalid")

# ---- P1-2 ----
filt = {"filter": {"path": "event", "op": "eq", "value": "order.paid"}}
_ov = ev(filt, '{"event": 1e1000000}')
check("P1-2: an overflowing number in the filtered field is never run (quarantined as number_out_of_range, spec §5)",
      _ov["decision"] == "invalid" and _ov["reason"] == "number_out_of_range", _ov)
deep = '{"event":' + "[" * 1200 + "]" * 1200 + ',"id":"A1"}'
r = ev(dict(filt, business_key={"entity": "o", "path": "id"}), deep)
check("P1-2: JSON nested 1200 deep is invalid, never run unfiltered", r["decision"] == "invalid" and "deeper" in r["reason"], r)
check("P1-2: without rules a deep body is only text (nothing to bypass)", wr.evaluate({}, deep.encode(), "application/json")["decision"] == "run")
try:
    wr._parse_float("1e1000000")
    _raised = False
except wr._NumberOutOfRange:
    _raised = True
check("P1-2: an overflowing literal is refused by the parser (never kept as text), and _plain never overflows",
      _raised and wr._plain(__import__("decimal").Decimal("1E+400")) == "1E+400")

# ---- P2-4 ----
r = ev({"filter": {"path": "total", "op": "gte", "value": 100}, "mapping": {"t": "total"}}, '{"total": 1e400}')
check("P2-4: 1e400 is never run as a number (quarantined: number_out_of_range), and the result is valid JSON",
      r["decision"] == "invalid" and r["reason"] == "number_out_of_range" and json.dumps(r, allow_nan=False))
r = ev({"mapping": {"a": "a", "b": "b"}}, '{"a": NaN, "b": Infinity}')
check("P2-4: NaN/Infinity literals are not numbers nor text: quarantined, valid JSON",
      r["decision"] == "invalid" and r["reason"] == "number_out_of_range" and json.dumps(r, allow_nan=False))
bk = {"business_key": {"entity": "o", "path": "id"}}
k = lambda v: ev(bk, '{"id": ' + v + "}")["business_key"]["hash"]  # noqa: E731
check("P2-4: 12345678901234567.5 and .7 are two keys", k("12345678901234567.5") != k("12345678901234567.7"),
      (k("12345678901234567.5"), k("12345678901234567.7")))
check("P2-4: 1e50 and 1e60 are two keys", k("1e50") != k("1e60"))

# ---- P2-2 ----
items = [{"sku": f"SKU-{i}", "name": "Nước mắm cá cơm " * 3, "qty": i} for i in range(200)]
body = json.dumps({"id": "A1", "items": items}, ensure_ascii=False)
r = ev({"mapping": {"order_id": "id", "items": "items"}}, body)
check("P2-2: a mapped object over the field cap is invalid with the reason, not silently dropped",
      r["decision"] == "invalid" and "items" in r["reason"] and "larger" in r["reason"], r["reason"])
r = ev({"mapping": {"order_id": "id", "first": "items[0]"}}, body)
check("P2-2: a small part of it maps fine", r["decision"] == "run" and r["fields"]["first"]["sku"] == "SKU-0")
st = ws.Store(Path(tempfile.mkdtemp(prefix="m2r-")) / "e.sqlite3")
big_fields = {f"f{i}": "x" * 1900 for i in range(30)}
code, info = ingest_pre(st, {"id": "wh_a", "brain": "/b"}, b"{}", "", "", pre={"decision": "run", "fields": big_fields})
check("P2-2: stored fields are never cut mid-JSON (57 KB of fields kept whole)", st.get(info["event_id"])["fields"] == big_fields)
check("P2-2: an unstorable value becomes a marker, never broken JSON", json.loads(ws._dumps({"x": float("inf")})) == {"_unstorable": True}
      and json.loads(ws._dumps({"x": "y" * 70000})).get("_truncated") is True)

# ---- P2-1 ----
H = {"id": "wh_r", "brain": "/b"}


def key(k):
    return {"decision": "run", "business_key": {"scope": "shop", "key": k, "ttl_s": 3600}}


s1 = ws.Store(Path(tempfile.mkdtemp(prefix="m2r-k-")) / "e.sqlite3")
c, i = ingest_pre(s1, H, b"1", "", "a", pre=key("order:7"))
w = s1.claim("W"); s1.mark_dispatched(w["id"], w["fence"]); s1.finish(w["id"], w["fence"], "failed", "", "boom")
s1.retry(i["event_id"])
w = s1.claim("W"); s1.finish(w["id"], w["fence"], "dead", "", "hook switched off")
c2, _ = ingest_pre(s1, H, b"1", "", "b", pre=key("order:7"))
check("P2-1: failed, retried, then dead: the key stays (the first attempt may have acted)", c2 == 200, c2)
c, i = ingest_pre(s1, H, b"1", "", "c", pre=key("order:8"))
w = s1.claim("W"); s1.mark_dispatched(w["id"], w["fence"]); s1.finish(w["id"], w["fence"], "failed", "", "boom")
s1.retry(i["event_id"])
s1.forget_hook(H["id"])
c2, _ = ingest_pre(s1, dict(H, id="wh_r2"), b"1", "", "d", pre=key("order:8"))
check("P2-1: failed, retried, then hook deleted: the key stays", c2 == 200)
c, i9 = ingest_pre(s1, dict(H, id="wh_r3"), b"1", "", "e", pre=key("order:9"))
w = s1.claim("W"); s1.finish(w["id"], w["fence"], "dead", "", "hook switched off")
check("P2-1: dead without ever running: the key is given back",
      s1._db.execute("SELECT COUNT(*) FROM biz_keys WHERE bkey='order:9'").fetchone()[0] == 0)
ok, why = s1.retry(i9["event_id"])
c3, _ = ingest_pre(s1, dict(H, id="wh_r4"), b"1", "", "f", pre=key("order:9"))
check("P2-1: retrying that dead event takes the key back, so a new copy is a duplicate", ok and c3 == 200, (ok, why, c3))
s1b = ws.Store(Path(tempfile.mkdtemp(prefix="m2r-k2-")) / "e.sqlite3")
c, i10 = ingest_pre(s1b, dict(H, id="wh_r5"), b"1", "", "g", pre=key("order:10"))
w = s1b.claim("W"); s1b.finish(w["id"], w["fence"], "dead", "", "off")
c4, i11 = ingest_pre(s1b, dict(H, id="wh_r6"), b"1", "", "h", pre=key("order:10"))
check("P2-1: retry refused while another copy holds the key", c4 == 202 and s1b.retry(i10["event_id"]) == (False, "key_taken"))

# ---- P2-3: concurrent upgrade of one old file ----
MIG = ("import webhook_store as ws, sys\n"
       "try:\n"
       "    ws.Store(sys.argv[1]).close(); print('OK')\n"
       "except Exception as e:\n"
       "    print('ERR', type(e).__name__, e)\n")
bad = 0
for trial in range(6):
    d = Path(tempfile.mkdtemp(prefix="m2r-mig-")) / "e.sqlite3"
    c = sqlite3.connect(str(d))
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(ws._SCHEMA.split("CREATE TABLE IF NOT EXISTS biz_keys")[0])
    c.execute("INSERT INTO meta(k, v) VALUES('schema_version', '1')")
    c.commit(); c.close()
    ps = [subprocess.Popen([sys.executable, "-c", MIG, str(d)], env=dict(os.environ, PYTHONPATH=str(SERVER)),
                           stdout=subprocess.PIPE, text=True) for _ in range(6)]
    outs = [p.communicate(timeout=60)[0].strip() for p in ps]
    bad += sum(1 for o in outs if o != "OK")
check("P2-3: 6 processes x 6 trials upgrading one v1 file at once: none fails", bad == 0, bad)
d = Path(tempfile.mkdtemp(prefix="m2r-ver-")) / "e.sqlite3"
ws.Store(d).close()
c = sqlite3.connect(str(d)); c.execute("UPDATE meta SET v='9' WHERE k='schema_version'"); c.commit(); c.close()
check("P3: an older build opening a newer file does not lower the schema marker", ws.Store(d).schema_version() == 9)

# cross-process business key: 5 processes, 5 hooks, one key
BK = ("import webhook_store as ws, sys\n"
      "st = ws.Store(sys.argv[1])\n"
      "pre = {'decision': 'run', 'business_key': {'shared': 'shop', 'policy': 1, 'hash': 'order:P', 'ttl_s': 3600}}\n"
      "code, info = st.ingest({'id': 'wh_' + sys.argv[2], 'brain': '/b'}, b'1', '', 'h:k' + sys.argv[2])\n"
      "print(202 if st.triage_commit(info['event_id'], pre, []) == 'queued' else 200)\n")
d = Path(tempfile.mkdtemp(prefix="m2r-bk-")) / "e.sqlite3"
ws.Store(d).close()
ps = [subprocess.Popen([sys.executable, "-c", BK, str(d), str(n)], env=dict(os.environ, PYTHONPATH=str(SERVER)),
                       stdout=subprocess.PIPE, text=True) for n in range(5)]
codes = sorted(p.communicate(timeout=60)[0].strip() for p in ps)
check("5 processes, 5 hooks, one shared business key decided at once: exactly one runs", codes == ["200"] * 4 + ["202"],
      codes)

# ---- P3 ----
check("P3: business_key.field must name a mapped field", "not a mapped field" in refused(
    {"mapping": {"order_id": "id"}, "business_key": {"entity": "order", "field": "order_idd"}}))
long_a, long_b = "A" * 250 + "1", "A" * 250 + "2"
ka = ev(bk, json.dumps({"id": long_a}))["business_key"]["hash"]
kb = ev(bk, json.dumps({"id": long_b}))["business_key"]["hash"]
check("P3: two long ids sharing 200 characters stay two keys (hashed, not cut)", ka != kb and len(ka) == 64, (ka, kb))
check("P3: ttl_s 0 is an error, not the 30-day default", "ttl_s" in refused({"business_key": {"entity": "o", "path": "id", "ttl_s": 0}}))
check("P3: a required mapped field that is null is missing", ev({"mapping": {"x": {"path": "x", "required": True}}},
                                                                '{"x": null}')["decision"] == "invalid")
check("P3: the rules size cap counts bytes (Vietnamese text)", "larger" in refused(
    {"mapping": {f"f{i}": {"value": "ệ" * 140} for i in range(40)}}))

# make_room: ignored events go first
s2 = ws.Store(Path(tempfile.mkdtemp(prefix="m2r-room-")) / "e.sqlite3")
old = ws.DB_MAX_BYTES
ws.DB_MAX_BYTES = 3 * 1024 * 1024
try:
    big = b"x" * 30000
    for n in range(12):
        ingest_pre(s2, {"id": f"wh_real{n}", "brain": "/b"}, big, "", f"r{n}")
        w = s2.claim("W"); s2.mark_dispatched(w["id"], w["fence"]); s2.finish(w["id"], w["fence"], "failed", "", "x")
        s2.mark_notified(w["id"])
    for n in range(150):
        ingest_pre(s2, {"id": f"wh_ign{n % 20}", "brain": "/b"}, big, "", "", pre={"decision": "filtered"})
    real = s2._db.execute("SELECT COUNT(*) FROM events WHERE status='failed' AND length(body)>0").fetchone()[0]
    check("P3: under disk pressure ignored events are evicted before real (failed) runs and their bodies", real == 12, real)
finally:
    ws.DB_MAX_BYTES = old


# feature: card history, simulate scope, Test text, loop not stalled
FEAT = Path(tempfile.mkdtemp(prefix="m2r-feat-"))
calls = []


async def run_task(brain, text, level):
    calls.append(text)
    return "ok", ""


async def nop(*a, **k):
    return "", "", False


async def send(*a, **k):
    return True, ""


async def main():
    f = wt.WebhookFeature(wt.WebhookDeps(state_dir=lambda: FEAT, run_task=run_task, run_workflow=nop, send=send,
                                         base_url=lambda _r: ""))
    h, tok, _ = f.create("/b1", name="Lọc", target="task", text="x", level="full",
                         rules={"filter": {"path": "event", "op": "eq", "value": "order.paid"},
                                "mapping": {"total": {"path": "total", "type": "integer"}, "id": "id"},
                                "business_key": {"entity": "order", "field": "id"}})
    ticks = []

    async def ticker():
        for _ in range(40):
            ticks.append(time.perf_counter())
            await asyncio.sleep(0.01)
    tk = asyncio.get_running_loop().create_task(ticker())
    code, resp = await f.accept(h["id"], tok, b'{"event":"order.paid","total": 1e999999, "id": "A1"}', "application/json", "x1")
    await tk
    gaps = max(b - a for a, b in zip(ticks, ticks[1:]))
    await f.wait_idle()
    check("P1-1 end to end: answered 202 (stored), quarantined by the worker, and the event loop never stalled",
          code == 202 and f.store().get(resp["event_id"])["status"] == "invalid" and gaps < 0.25, (code, gaps))
    code, resp = await f.accept(h["id"], tok, deep.replace('"event":', '"event":"order.paid","x":').encode(), "application/json", "x2")
    await f.wait_idle()
    check("P1-2 end to end: a deep payload is stored and quarantined, never run", code == 202
          and f.store().get(resp["event_id"])["status"] == "invalid" and not calls)
    for n in range(30):
        await f.accept(h["id"], tok, json.dumps({"event": "other", "id": n}).encode(), "application/json", f"o{n}")
    await f.accept(h["id"], tok, b'{"event":"order.paid","total":5,"id":"A2"}', "application/json", "real")
    await f.wait_idle()
    hist = f.view(f._find(f._load(), h["id"]))["history"]
    check("P3: the card history shows real runs, not the flood of filtered events",
          hist and all(x["status"] not in ("filtered", "invalid", "duplicate") for x in hist), [x["status"] for x in hist][:5])
    code, sim = f.simulate({"brain": "/b1", "rules": {"business_key": {"entity": "order", "path": "id"}},
                            "payload": {"id": "A2"}})
    check("P3: simulate without a hook does not look up any brain's keys", code == 200 and sim["decision"] == "run"
          and "duplicate_of" not in sim)
    code, sim = f.simulate({"id": h["id"], "payload": {"event": "order.paid", "total": 1, "id": "A2"}})
    check("simulate with the hook still sees its own brain's key", sim["decision"] == "duplicate")
    code, sim = f.simulate({"id": h["id"], "payload": '{"event": 1e400, "total": 1}'})
    from starlette.responses import JSONResponse
    check("P2-4: simulate on 1e400 answers JSON (no inf)", code == 200 and JSONResponse(sim).body)

asyncio.run(main())

js = subprocess.run(["node", "-e", """
const W = require(process.argv[1]);
console.log(JSON.stringify([W.testText({ok: true, ignored: 'filtered'}), W.testText({ok: true, accepted: true}),
  W.testText({ok: false, error: 'invalid', reason: 'schema: id: missing'}), W.testText({ok: true, duplicate: true, reason: 'business_key'})]));
""", str(ROOT / "dashboard" / "webhooks.js")], capture_output=True, text=True)
out = json.loads(js.stdout or "[]")
check("P3: the Test button says when the rules stopped the sample", out == ["wh.st_filtered", "wh.test_sent",
                                                                          "wh.st_invalid: schema: id: missing", "wh.st_duplicate"], out)

if fails:
    print(f"\nFAIL {len(fails)}: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_webhook_m2_review: all pass")
