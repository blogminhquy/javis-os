"""0.229.0: durable webhook events (webhook platform M1).

    python tests/run.py webhook_store_m1      (no network, no model: every runner is a fake)

What is proven here, against a real temporary SQLite file and real child processes:
  1. the 202 comes only after the event AND its idempotency key are committed together; a crash before the
     commit keeps neither, a crash after it keeps both (and the event still runs after restart);
  2. concurrent copies of one key, from threads and from separate processes, are accepted exactly once;
  3. limits (rate, backlog, disk) refuse without storing anything;
  4. two workers never run the same event; a worker whose lease was taken over cannot write its result (fence);
  5. a crash after the runner was called leaves the event `unknown`, it is NOT run again by itself, and the owner
     can retry or resolve it; a lease lost before dispatch runs the event again, once;
  6. failures before dispatch back off and end `dead`; a deleted or disabled hook makes waiting events `dead`;
     lowering a hook's level applies to events already waiting;
  7. the owner notice is resent after a crash between commit and notice, under the same dedup key;
  8. the event log API paginates, never lists bodies, and retry/resolve work through the routes;
  9. keys remembered by a pre-0.229.0 hook stay duplicates; pruning keeps unknown events.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

STATE = Path(tempfile.mkdtemp(prefix="javis-wh-m1-"))
os.environ["JAVIS_STATE_DIR"] = str(STATE)
os.environ["JAVIS_NO_REAL_JUDGE_ENGINE"] = "1"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import webhook_store as ws  # noqa: E402
import webhook_triggers as wt  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


PY = sys.executable
HOOK = {"id": "wh_test", "name": "Lead", "brain": "/b", "target": "task", "text": "Gọi lại", "level": "full"}


def child(code: str, env_extra: dict, state: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, JAVIS_STATE_DIR=str(state), PYTHONPATH=str(SERVER), **env_extra)
    return subprocess.run([PY, "-c", code], env=env, capture_output=True, text=True, timeout=60)


def rows(db: Path, sql: str, args=()) -> list:
    import sqlite3
    c = sqlite3.connect(str(db))
    try:
        return c.execute(sql, args).fetchall()
    finally:
        c.close()


# ---- 1. ACK only after commit: crash before and after the commit, in a child process ----
INGEST = (
    "import webhook_store as ws, json, sys, os\n"
    "st = ws.Store(os.path.join(os.environ['JAVIS_STATE_DIR'], 'e.sqlite3'))\n"
    "h = json.loads(sys.argv[1]) if len(sys.argv) > 1 else " + repr(HOOK) + "\n"
    "code, info = st.ingest(h, b'{\"order\": 1}', 'application/json', 'key-1')\n"
    "print('ACK', code)\n")
s1 = Path(tempfile.mkdtemp(prefix="wh-crash-"))
r = child(INGEST, {"JAVIS_WH_CRASH_AT": "before_commit"}, s1)
check("crash before commit: the process dies before answering", r.returncode == 77 and "ACK" not in r.stdout, r)
db = s1 / "e.sqlite3"
check("crash before commit: no event and no key were kept",
      rows(db, "SELECT COUNT(*) FROM events")[0][0] == 0 and rows(db, "SELECT COUNT(*) FROM dedup")[0][0] == 0)
r = child(INGEST, {}, s1)
check("the sender's retry after that crash is accepted (202), not a duplicate", "ACK 202" in r.stdout, r.stdout + r.stderr)

s2 = Path(tempfile.mkdtemp(prefix="wh-crash-"))
r = child(INGEST, {"JAVIS_WH_CRASH_AT": "after_commit"}, s2)
db2 = s2 / "e.sqlite3"
check("crash after commit, before the ACK: the event and its key are both stored",
      r.returncode == 77 and rows(db2, "SELECT status FROM events") == [("queued",)]
      and rows(db2, "SELECT COUNT(*) FROM dedup")[0][0] == 1)
r = child(INGEST, {}, s2)
check("the sender's retry is then a duplicate pointing at the stored event", "ACK 200" in r.stdout
      and rows(db2, "SELECT COUNT(*) FROM events")[0][0] == 1, r.stdout)

# ---- 2. concurrent duplicates: threads and processes ----
s3 = Path(tempfile.mkdtemp(prefix="wh-conc-"))
st3 = ws.Store(s3 / "e.sqlite3")
res = []
ths = [threading.Thread(target=lambda: res.append(st3.ingest(HOOK, b"x", "text/plain", "same")[0])) for _ in range(8)]
[t.start() for t in ths]
[t.join() for t in ths]
check("8 threads, one key: exactly one 202", sorted(res) == [200] * 7 + [202], res)
procs = [subprocess.Popen([PY, "-c", INGEST.replace("key-1", "proc-key")],
                          env=dict(os.environ, JAVIS_STATE_DIR=str(s3), PYTHONPATH=str(SERVER)),
                          stdout=subprocess.PIPE, text=True) for _ in range(5)]
outs = [p.communicate(timeout=60)[0] for p in procs]
codes = sorted(o.strip().split()[-1] for o in outs)
check("5 processes, one key: exactly one 202", codes == ["200"] * 4 + ["202"], outs)

# ---- 3. limits store nothing ----
s4 = Path(tempfile.mkdtemp(prefix="wh-lim-"))
st4 = ws.Store(s4 / "e.sqlite3")
now = time.time()
for i in range(ws.RATE_PER_HOUR):
    st4._db.execute("INSERT INTO events(id, hook_id, received_at, body, body_sha, status) VALUES(?,?,?,?,?, 'done')",
                    (f"ev_r{i}", HOOK["id"], now - 10, b"", ""))
code, info = st4.ingest(HOOK, b"x", "", "k-rate")
check("over the hourly rate: 429 and nothing stored",
      code == 429 and info["reason"] == "rate" and st4._db.execute("SELECT COUNT(*) FROM dedup").fetchone()[0] == 0)
code, _ = st4.ingest(HOOK, b"x", "", "k-old", now=now + 3700)
check("an hour later the same hook is accepted again", code == 202)
h2 = dict(HOOK, id="wh_backlog")
for i in range(ws.BACKLOG_MAX):
    st4.ingest(h2, b"x", "", f"b{i}", now=now)
code, info = st4.ingest(h2, b"x", "", "b-over", now=now)
check("backlog full: 429 'backlog' and the key is not kept", code == 429 and info["reason"] == "backlog"
      and st4._db.execute("SELECT 1 FROM dedup WHERE idem_key='b-over'").fetchone() is None)
old_cap = ws.DB_MAX_BYTES
ws.DB_MAX_BYTES = 1
try:
    st4.ingest(dict(HOOK, id="wh_disk"), b"x", "", "d1")
    check("store over its disk cap refuses (Busy)", False)
except ws.Busy:
    check("store over its disk cap refuses (Busy) and keeps nothing",
          st4._db.execute("SELECT COUNT(*) FROM events WHERE hook_id='wh_disk'").fetchone()[0] == 0)
ws.DB_MAX_BYTES = old_cap

# ---- 4. two workers, leases and fencing ----
s5 = Path(tempfile.mkdtemp(prefix="wh-work-"))
a = ws.Store(s5 / "e.sqlite3")
b = ws.Store(s5 / "e.sqlite3")
for i in range(3):
    a.ingest(dict(HOOK, id=f"wh_h{i}"), b"x", "", f"w{i}")
got, lock = [], threading.Lock()


def worker(st, name):
    while True:
        row = st.claim(name)
        if row is None:
            return
        with lock:
            got.append(row["id"])
        st.mark_dispatched(row["id"], row["fence"])
        st.finish(row["id"], row["fence"], "done", "ok")


t1 = threading.Thread(target=worker, args=(a, "A"))
t2 = threading.Thread(target=worker, args=(b, "B"))
t1.start(); t2.start(); t1.join(); t2.join()
check("two workers: every event claimed exactly once", sorted(got) == sorted(set(got)) and len(got) == 3, got)

a.ingest(HOOK, b"x", "", "fence-1")
r1 = a.claim("A")
check("one event per hook at a time: a second claim waits while the first holds its lease",
      a.ingest(HOOK, b"y", "", "fence-2")[0] == 202 and b.claim("B") is None)
later = time.time() + ws.LEASE_S + 1
rec = b.recover(now=later)
check("expired lease before dispatch goes back to the queue", rec["requeued"] == 1)
r2 = b.claim("B", now=later)
check("the new owner holds a higher fence", r2 is not None and r2["id"] == r1["id"] and r2["fence"] == r1["fence"] + 1)
check("the old owner cannot start (dispatch refused)", not a.mark_dispatched(r1["id"], r1["fence"]))
check("the old owner cannot write a result", not a.finish(r1["id"], r1["fence"], "done", "stale"))
check("the old owner cannot renew the lease", not a.heartbeat(r1["id"], r1["fence"]))
check("the new owner finishes normally", b.mark_dispatched(r2["id"], r2["fence"])
      and b.finish(r2["id"], r2["fence"], "done", "fresh") and b.get(r2["id"])["result"] == "fresh")
att = b.get(r2["id"])["attempts"]
check("attempt log shows the lost lease then the success",
      [x["outcome"] for x in att] == ["lease_expired", "done"], att)

# ---- 5..9 through the real feature (host routes, fake runners, fake notifier) ----
FEAT_STATE = Path(tempfile.mkdtemp(prefix="wh-feat-"))
sent, calls = [], []
answer = {"v": ("Đã gọi khách.", "")}


async def run_task(brain, text, level):
    calls.append(("task", brain, level, text))
    return answer["v"]


async def run_workflow(brain, slug, text, level):
    calls.append(("wf", brain, level, slug))
    return "xong", "", False


async def send(chat_id, text, viec=None, web="", brain="", dedup=""):
    sent.append({"text": text, "dedup": dedup, "status": (viec or {}).get("status")})
    return True, ""


def make_feat():
    return wt.WebhookFeature(wt.WebhookDeps(state_dir=lambda: FEAT_STATE, run_task=run_task, run_workflow=run_workflow,
                                            send=send, base_url=lambda _r: "https://x",
                                            workflow_exists=lambda b, s: True))


async def main():
    feat = make_feat()
    h, tok, _ = feat.create("/b", name="Đơn", target="task", text="Ghi đơn", level="full", chat_id="web:1")

    # crash after the runner was called, before its result was written: child process
    code = (
        "import asyncio, os, json, webhook_triggers as wt\n"
        "from pathlib import Path\n"
        "S = Path(os.environ['JAVIS_STATE_DIR'])\n"
        "async def run_task(b, t, l):\n"
        "    (S / 'effects.txt').open('a').write('ran\\n')\n"
        "    return 'ok', ''\n"
        "async def nop(*a, **k): return '', '', False\n"
        "async def send(*a, **k): return True, ''\n"
        "f = wt.WebhookFeature(wt.WebhookDeps(state_dir=lambda: S, run_task=run_task, run_workflow=nop, send=send,"
        " base_url=lambda r: ''))\n"
        "async def go():\n"
        "    code, resp = await f.accept(" + repr(h["id"]) + ", " + repr(tok) + ", b'{\"o\":1}', 'application/json', 'crash-1')\n"
        "    print('ACK', code, flush=True)\n"
        "    await f.wait_idle()\n"
        "asyncio.run(go())\n")
    r = child(code, {"JAVIS_WH_CRASH_AT": "after_dispatch"}, FEAT_STATE)
    eff = (FEAT_STATE / "effects.txt").read_text().count("ran") if (FEAT_STATE / "effects.txt").exists() else 0
    check("child: accepted, ran the outside effect once, then died before writing the result",
          "ACK 202" in r.stdout and r.returncode == 77 and eff == 1, (r.returncode, r.stdout, r.stderr[-300:]))
    feat2 = make_feat()
    st = feat2.store()
    eid = st._db.execute("SELECT event_id FROM dedup WHERE idem_key='crash-1'").fetchone()[0]
    check("after the crash the event is still 'running' with dispatch recorded",
          st.get(eid)["status"] == "running" and st.get(eid)["dispatched_at"] > 0)
    rec = st.recover(now=time.time() + ws.LEASE_S + 1)
    check("restart recovery: a dispatched event whose lease expired becomes unknown", rec["unknown"] == 1
          and st.get(eid)["status"] == "unknown")
    n_calls = len(calls)
    await feat2.sweep()
    await feat2.wait_idle()
    check("an unknown event is NOT run again by itself", len(calls) == n_calls)
    check("the owner is told it is unknown", any(x["status"] == "unknown" for x in sent))
    code2, resp2 = await feat2.accept(h["id"], tok, b'{"o":1}', "application/json", "crash-1")
    check("the sender's retry of the same key is a duplicate (no second order)", code2 == 200 and resp2["duplicate"])

    from fastapi import FastAPI
    import httpx
    # Same event loop as the feature (not TestClient, whose own loop would kill the worker it starts).
    app = FastAPI()
    app.include_router(feat2.router)
    cl = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    r = await cl.post("/webhooks/events/resolve", json={"id": eid, "outcome": "done", "note": "checked in the shop"})
    check("owner resolves the unknown event as done", r.status_code == 200 and st.get(eid)["status"] == "done")
    r = await cl.post("/webhooks/events/resolve", json={"id": eid, "outcome": "done"})
    check("resolving twice is refused", r.status_code == 409)

    # a lease lost BEFORE dispatch: the event runs again, once
    code3, resp3 = await feat2.accept(h["id"], tok, b'{"o":2}', "application/json", "pre-1")
    await feat2.wait_idle()
    ev3 = resp3["run_id"]
    check("normal event runs once and is done", st.get(ev3)["status"] == "done"
          and sum(1 for c in calls if '"o": 2' in c[3]) == 1)

    # retry of a failed run is the owner's call; the failed run is not retried alone
    answer["v"] = ("", "engine timeout")
    _, rf = await feat2.accept(h["id"], tok, b'{"o":3}', "application/json", "fail-1")
    await feat2.wait_idle()
    check("a run that returned an error is failed, not retried alone",
          st.get(rf["run_id"])["status"] == "failed" and sum(1 for c in calls if '"o": 3' in c[3]) == 1)
    answer["v"] = ("ổn rồi", "")
    r = await cl.post("/webhooks/events/retry", json={"id": rf["run_id"]})
    await feat2.wait_idle()
    check("owner retry runs it again and it is done", r.status_code == 200 and st.get(rf["run_id"])["status"] == "done"
          and sum(1 for c in calls if '"o": 3' in c[3]) == 2)
    check("retrying a done event is refused", (await cl.post("/webhooks/events/retry", json={"id": rf["run_id"]})).status_code == 409)

    # pre-dispatch failure backs off then ends dead
    real_find = feat2._find
    feat2._find = lambda data, hid: (_ for _ in ()).throw(OSError("disk read error"))
    _, rp = await feat2.accept(h["id"], tok, b'{"o":4}', "application/json", "pre-fail") if False else (None, None)
    feat2._find = real_find
    hp = st.ingest(feat2._find(feat2._load(), h["id"]), b'{"o":4}', "application/json", "pre-fail")[1]["event_id"]
    feat2._load_real = feat2._load
    boom = {"n": 0}

    def bad_load():
        boom["n"] += 1
        raise OSError("disk read error")
    feat2._load = bad_load
    t0 = time.time()
    for i in range(ws.MAX_AUTO_TRIES):
        row = st.claim(feat2.worker_id, now=t0 + 1000 * (i + 1))
        await feat2._run_event(st, row, row["id"], row["fence"])
    feat2._load = feat2._load_real
    check("a failure before dispatch backs off and ends dead after MAX_AUTO_TRIES",
          st.get(hp)["status"] == "dead" and st.get(hp)["dispatched_at"] == 0 and boom["n"] == ws.MAX_AUTO_TRIES)
    check("and the runner was never called for it", not any('"o": 4' in c[3] for c in calls))

    # permissions of NOW: lowering the level applies to waiting events; disabling makes them dead
    feat3 = make_feat()
    h3, tok3, _ = feat3.create("/b", name="Hạ quyền", target="task", text="x", level="full")
    st3 = feat3.store()
    e_full = st3.ingest(feat3._find(feat3._load(), h3["id"]), b'{"o":5}', "application/json", "lv")[1]["event_id"]
    feat3.update(h3["id"], {"level": "suggest"})
    feat3._kick()
    await feat3.wait_idle()
    run = [c for c in calls if '"o": 5' in c[3]]
    check("an event received at 'full' runs at the hook's CURRENT lower level", run and run[-1][2] == "suggest", run)
    e_off = st3.ingest(feat3._find(feat3._load(), h3["id"]), b'{"o":6}', "application/json", "off")[1]["event_id"]
    feat3.update(h3["id"], {"enabled": False})
    feat3._kick()
    await feat3.wait_idle()
    check("an event of a hook switched off before it ran is dead, never run",
          st3.get(e_off)["status"] == "dead" and not any('"o": 6' in c[3] for c in calls))
    feat3.update(h3["id"], {"enabled": True})
    e_del = st3.ingest(feat3._find(feat3._load(), h3["id"]), b'{"o":7}', "application/json", "del")[1]["event_id"]
    st3._db.execute("UPDATE events SET next_at=? WHERE id=?", (time.time() + 3600, e_del))
    feat3.delete(h3["id"])
    check("deleting a hook makes its waiting events dead and drops its keys",
          st3.get(e_del)["status"] == "dead" and st3._db.execute(
              "SELECT COUNT(*) FROM dedup WHERE hook_id=?", (h3["id"],)).fetchone()[0] == 0)

    # notice lost to a crash between commit and notice is resent with the same dedup key
    h4, tok4, _ = feat3.create("/b", name="Báo lại", target="task", text="x", chat_id="web:9")
    e4 = st3.ingest(feat3._find(feat3._load(), h4["id"]), b'{"o":8}', "", "nt")[1]["event_id"]
    row = st3.claim("X")
    st3.mark_dispatched(row["id"], row["fence"])
    st3.finish(row["id"], row["fence"], "done", "kết quả 8")
    await feat3.sweep()
    mine = [x for x in sent if x["dedup"] == f"wh:{h4['id']}:{e4}"]
    check("a finished event whose notice never went out is notified at the next sweep, with its own dedup key",
          len(mine) == 1 and "kết quả 8" in mine[0]["text"], mine)
    await feat3.sweep()
    check("and only once", len([x for x in sent if x["dedup"] == f"wh:{h4['id']}:{e4}"]) == 1)

    # event log API: pagination, no bodies
    # 25 finished events (straight into the store: the hook's own rate and backlog limits would refuse them)
    for i in range(25):
        st3._db.execute("INSERT INTO events(id, hook_id, received_at, content_type, body, body_sha, status,"
                        " finished_at, notified_at) VALUES(?,?,?,?,?,?, 'done', ?, ?)",
                        (f"ev_pg{i:02d}", h4["id"], time.time() - 100 + i, "application/json",
                         json.dumps({"secret": f"s{i}"}).encode(), "", time.time(), time.time()))
    app3 = FastAPI()
    app3.include_router(feat3.router)
    c3 = httpx.AsyncClient(transport=httpx.ASGITransport(app=app3), base_url="http://t")
    p1 = (await c3.get("/webhooks/events", params={"hook": h4["id"], "limit": 10})).json()
    p2 = (await c3.get("/webhooks/events", params={"hook": h4["id"], "limit": 10, "before": p1["next"]})).json()
    ids1, ids2 = [x["id"] for x in p1["items"]], [x["id"] for x in p2["items"]]
    check("event log: pages of 10, newest first, no overlap, cursor to the next page",
          len(ids1) == 10 and len(ids2) == 10 and not set(ids1) & set(ids2) and p1["next"])
    check("event log never lists bodies", "secret" not in json.dumps(p1) and all("body" not in x for x in p1["items"]))
    one = (await c3.get("/webhooks/events/" + next(i for i in ids1 + ids2 if i.startswith("ev_pg")))).json()
    check("event detail shows the payload as text and the attempts", one["ok"] and "secret" in one["event"]["payload"]
          and "attempts" in one["event"] and "hook_snapshot" not in one["event"])
    await feat3.wait_idle()

    # restart: queued events stored by a previous process run after the new one starts
    s_r = Path(tempfile.mkdtemp(prefix="wh-restart-"))
    f_a = wt.WebhookFeature(wt.WebhookDeps(state_dir=lambda: s_r, run_task=run_task, run_workflow=run_workflow,
                                           send=send, base_url=lambda _r: ""))
    hr, tr, _ = f_a.create("/b", name="Khởi động lại", target="task", text="x")
    eq = f_a.store().ingest(f_a._find(f_a._load(), hr["id"]), b'{"o":9}', "", "rs")[1]["event_id"]
    f_a.store().close()
    f_b = wt.WebhookFeature(wt.WebhookDeps(state_dir=lambda: s_r, run_task=run_task, run_workflow=run_workflow,
                                           send=send, base_url=lambda _r: ""))
    await f_b.sweep()
    await f_b.wait_idle()
    check("an event stored before a restart runs after it", f_b.store().get(eq)["status"] == "done"
          and sum(1 for c in calls if '"o": 9' in c[3]) == 1)

    # legacy keys from webhooks.json stay duplicates
    s_l = Path(tempfile.mkdtemp(prefix="wh-legacy-"))
    (s_l / "webhooks.json").write_text(json.dumps({"hooks": [{
        "id": "wh_old", "name": "cũ", "brain": "/b", "target": "task", "text": "x", "level": "full", "enabled": True,
        "token_hash": wt.hash_token("t0k"), "seen_keys": ["old-1", "old-2"]}]}), encoding="utf-8")
    f_l = wt.WebhookFeature(wt.WebhookDeps(state_dir=lambda: s_l, run_task=run_task, run_workflow=run_workflow,
                                           send=send, base_url=lambda _r: ""))
    c_old, r_old = await f_l.accept("wh_old", "t0k", b"{}", "application/json", "old-1")
    check("a key remembered before the upgrade is still a duplicate", c_old == 200 and r_old["duplicate"])
    check("the JSON keeps its keys (rollback to the old version still knows them)",
          "old-1" in (s_l / "webhooks.json").read_text(encoding="utf-8"))
    await f_l.wait_idle()

    # pruning keeps unknown events
    stp = f_l.store()
    stp._db.execute("INSERT INTO events(id, hook_id, received_at, body, body_sha, status, finished_at) VALUES"
                    " ('ev_oldd','wh_old',1,x'','', 'done', 1), ('ev_oldu','wh_old',1,x'','', 'unknown', 1)")
    stp.prune()
    check("pruning drops old finished events but keeps unknown ones until resolved",
          stp.get("ev_oldd") is None and stp.get("ev_oldu") is not None)
    check("schema version recorded", stp.schema_version() == ws.SCHEMA_VERSION)


asyncio.run(main())

src = (SERVER / "webhook_triggers.py").read_text(encoding="utf-8") + (SERVER / "webhook_store.py").read_text(encoding="utf-8")
check("no model is called by the webhook core (no engine imports)",
      not any(x in src for x in ("aux_engine", "claude_cli", "_reply_policy_sandbox_engine", "anthropic")))

if fails:
    print(f"\nFAIL {len(fails)}: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_webhook_store_m1: all pass")
