"""0.274.0: durable webhook events (webhook platform M1).

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
  9. keys remembered by a pre-0.274.0 hook stay duplicates; pruning keeps unknown events.
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


def admit(st):
    """Spec §4.2: rules run AFTER the commit. A hook without rules: triage only moves the event to the queue."""
    for r in st.triage_candidates(1000, now=time.time() + 10 ** 6):
        st.triage_commit(r["id"], {"decision": "run"}, [])


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
      r.returncode == 77 and rows(db2, "SELECT status FROM events") == [("received",)]
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
# Spec §11: ingress is limited per minute (300 by default, with a 10 s burst), no longer 30 per hour.
HR = dict(HOOK, limits={"per_minute": 30})
for i in range(30):
    st4._db.execute("INSERT INTO events(id, hook_id, received_at, body, body_sha, status) VALUES(?,?,?,?,?, 'done')",
                    (f"ev_r{i}", HOOK["id"], now - 30, b"", ""))
code, info = st4.ingest(HR, b"x", "", "k-rate", now=now)
check("over the ingress rate: 429 and nothing stored",
      code == 429 and info["reason"] == "rate" and st4._db.execute("SELECT COUNT(*) FROM dedup").fetchone()[0] == 0)
code, _ = st4.ingest(HR, b"x", "", "k-old", now=now + 61)
check("a minute later the same hook is accepted again", code == 202)
code, info = st4.ingest(dict(HOOK, id="wh_burst", limits={"burst": 2}), b"x", "", "", now=now)
code2, _ = st4.ingest(dict(HOOK, id="wh_burst", limits={"burst": 2}), b"x", "", "", now=now)
code3, info3 = st4.ingest(dict(HOOK, id="wh_burst", limits={"burst": 2}), b"x", "", "", now=now)
check("past the 10 s burst: 429 'burst' with a Retry-After", (code, code2, code3) == (202, 202, 429)
      and info3["reason"] == "burst" and info3["retry_after"] > 0)
h2 = dict(HOOK, id="wh_backlog", limits={"backlog": 6})
for i in range(6):
    st4.ingest(h2, b"x", "", f"b{i}", now=now - 300 + i)
code, info = st4.ingest(h2, b"x", "", "b-over", now=now)
check("backlog full: 429 'backlog' and the key is not kept", code == 429 and info["reason"] == "backlog"
      and st4._db.execute("SELECT 1 FROM dedup WHERE idem_key LIKE '%b-over'").fetchone() is None)
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
admit(a)
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
admit(a)
r1 = a.claim("A")
ok2 = a.ingest(HOOK, b"y", "", "fence-2")[0] == 202
admit(a)
check("one event per hook at a time: a second claim waits while the first holds its lease",
      ok2 and b.claim("B") is None)
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
check("attempt log shows the lost lease (with the stale run's late result kept on it) then the success",
      [x["outcome"] for x in att] == ["late:done", "done"] and att[0]["late_result"] == "stale", att)

# an exception inside a write must not leave the shared connection in an open transaction (it would lock the file)
a.ingest(dict(HOOK, id="wh_tx"), b"x", "", "tx-1")
admit(a)
rtx = a.claim("A")
a.mark_dispatched(rtx["id"], rtx["fence"])
try:
    a.requeue_before_dispatch(rtx["id"], rtx["fence"], "boom")
    check("requeue after dispatch is refused", False)
except ValueError:
    pass
import sqlite3 as _sq
other = _sq.connect(str(s5 / "e.sqlite3"), timeout=1, isolation_level=None)
try:
    other.execute("BEGIN IMMEDIATE"); other.execute("ROLLBACK")
    free = True
except _sq.OperationalError:
    free = False
check("a refused write rolls back: another process can write right after", free and not a._db.in_transaction)
check("and the refused event is untouched (still running, dispatched)",
      a.get(rtx["id"])["status"] == "running" and a.get(rtx["id"])["dispatched_at"] > 0)

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
    eid = st._db.execute("SELECT event_id FROM dedup WHERE idem_key='h:crash-1'").fetchone()[0]
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
    hp = st.ingest(feat2._find(feat2._load(), h["id"]), b'{"o":4}', "application/json", "pre-fail")[1]["event_id"]
    admit(st)
    real_find = feat2._find_hook
    boom = {"n": 0}

    def bad_find(hid):
        boom["n"] += 1
        raise OSError("disk read error")
    feat2._find_hook = bad_find
    t0 = time.time()
    for i in range(ws.MAX_AUTO_TRIES):
        row = st.claim(feat2.worker_id, now=t0 + 1000 * (i + 1))
        await feat2._run_event(st, row, row["id"], row["fence"])
    feat2._find_hook = real_find
    check("a failure before dispatch backs off and ends dead after MAX_AUTO_TRIES",
          st.get(hp)["status"] == "dead" and st.get(hp)["dispatched_at"] == 0 and boom["n"] == ws.MAX_AUTO_TRIES)
    check("and the runner was never called for it", not any('"o": 4' in c[3] for c in calls))

    # permissions of NOW: lowering the level applies to waiting events; disabling makes them dead
    feat3 = make_feat()
    h3, tok3, _ = feat3.create("/b", name="Hạ quyền", target="task", text="x", level="full")
    st3 = feat3.store()
    e_full = st3.ingest(feat3._find(feat3._load(), h3["id"]), b'{"o":5}', "application/json", "lv")[1]["event_id"]
    admit(st3)
    feat3.update(h3["id"], {"level": "suggest"})
    feat3._kick()
    await feat3.wait_idle()
    run = [c for c in calls if '"o": 5' in c[3]]
    check("an event received at 'full' runs at the hook's CURRENT lower level", run and run[-1][2] == "suggest", run)
    # Spec §12: two switches. "Stop receiving" refuses NEW requests; an event already accepted (202) still runs.
    # "Pause processing" keeps receiving and storing; nothing runs until it is resumed.
    e_off = st3.ingest(feat3._find(feat3._load(), h3["id"]), b'{"o":6}', "application/json", "off")[1]["event_id"]
    feat3.update(h3["id"], {"enabled": False})
    feat3._kick()
    await feat3.wait_idle()
    check("an event accepted before the hook stopped receiving still runs (it was promised with a 202)",
          st3.get(e_off)["status"] == "done" and any('"o": 6' in c[3] for c in calls))
    feat3.update(h3["id"], {"enabled": True})
    feat3.pause(h3["id"], True)
    e_pause = st3.ingest(feat3._find(feat3._load(), h3["id"]), b'{"o":61}', "application/json", "pz")[1]["event_id"]
    feat3._kick()
    await feat3.wait_idle()
    check("a paused hook still stores events, and does not run them", st3.get(e_pause)["status"] == "received"
          and not any('"o": 61' in c[3] for c in calls))
    feat3.pause(h3["id"], False)
    await feat3.wait_idle()
    check("resuming runs what waited", st3.get(e_pause)["status"] == "done")
    e_del = st3.ingest(feat3._find(feat3._load(), h3["id"]), b'{"o":7}', "application/json", "del")[1]["event_id"]
    st3._db.execute("UPDATE events SET next_at=? WHERE id=?", (time.time() + 3600, e_del))
    feat3.delete(h3["id"])
    check("deleting a hook cancels its waiting events (retention then removes them) and drops its keys",
          st3.get(e_del)["status"] == "cancelled" and st3._db.execute(
              "SELECT COUNT(*) FROM dedup WHERE hook_id=?", (h3["id"],)).fetchone()[0] == 0)

    # notice lost to a crash between commit and notice is resent with the same dedup key
    h4, tok4, _ = feat3.create("/b", name="Báo lại", target="task", text="x", chat_id="web:9")
    e4 = st3.ingest(feat3._find(feat3._load(), h4["id"]), b'{"o":8}', "", "nt")[1]["event_id"]
    admit(st3)
    row = st3.claim("X")
    st3.mark_dispatched(row["id"], row["fence"])
    st3.finish(row["id"], row["fence"], "done", "kết quả 8")
    await feat3.sweep()
    mine = [x for x in sent if x["dedup"] == f"wh:{h4['id']}:{e4}:{row['fence']}"]
    check("a finished event whose notice never went out is notified at the next sweep, with its own dedup key",
          len(mine) == 1 and "kết quả 8" in mine[0]["text"], mine)
    await feat3.sweep()
    check("and only once", len([x for x in sent if x["dedup"] == f"wh:{h4['id']}:{e4}:{row['fence']}"]) == 1)

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
    check("event detail shows the payload MASKED by default, with the attempts and a timeline",
          one["ok"] and '"s1' not in one["event"]["payload"] and "••••" in one["event"]["payload"]
          and one["event"]["masked"] and "attempts" in one["event"] and one["event"]["timeline"]
          and "hook_snapshot" not in one["event"])
    eid_pg = one["event"]["id"]
    rawv = (await c3.get("/webhooks/events/" + eid_pg, params={"raw": 1})).json()
    check("raw=1 shows it as received and is recorded in the audit log", '"secret": "s' in rawv["event"]["payload"]
          and any(a["action"] == "view_raw" and a["event_id"] == eid_pg for a in st3.audit_rows()))
    await feat3.wait_idle()

    # restart: queued events stored by a previous process run after the new one starts
    s_r = Path(tempfile.mkdtemp(prefix="wh-restart-"))
    f_a = wt.WebhookFeature(wt.WebhookDeps(state_dir=lambda: s_r, run_task=run_task, run_workflow=run_workflow,
                                           send=send, base_url=lambda _r: ""))
    hr, tr, _ = f_a.create("/b", name="Khởi động lại", target="task", text="x")
    eq = f_a.store().ingest(f_a._find(f_a._load(), hr["id"]), b'{"o":9}', "", "rs")[1]["event_id"]
    admit(f_a.store())
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
    # Spec §13: webhooks.json is migrated into the store, snapshotted first, then moved aside so an older build
    # never runs a stale copy beside this one (the rollback tool writes it back from the store).
    check("the migration snapshots webhooks.json and moves it aside",
          not (s_l / "webhooks.json").exists() and (s_l / "webhooks.json.migrated").exists()
          and any(p.name.startswith("webhooks.json.pre-0.241-") for p in s_l.iterdir())
          and "old-1" in (s_l / "webhooks.json.migrated").read_text(encoding="utf-8"))
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


# ---- review fixes (independent review of M1, P1/P2) ----
async def review():
    # P1-1: the size cap measures live data; pruning or eviction frees room at once, the store never locks up
    sc = Path(tempfile.mkdtemp(prefix="wh-cap-"))
    stc = ws.Store(sc / "e.sqlite3")
    old = ws.DB_MAX_BYTES
    ws.DB_MAX_BYTES = 2 * 1024 * 1024
    try:
        big = b"x" * 32 * 1024
        for i in range(40):
            hid = f"wh_c{i}"
            stc.ingest(dict(HOOK, id=hid), big, "", f"c{i}")
            admit(stc)
            r = stc.claim("W"); stc.mark_dispatched(r["id"], r["fence"]); stc.finish(r["id"], r["fence"], "done", "ok")
        code, _ = stc.ingest(dict(HOOK, id="wh_after"), big, "", "after")
        check("P1-1: past the cap, finished events are evicted and a new event is still accepted", code == 202,
              stc.size_bytes())
        check("P1-1: live size stays under the cap", stc.size_bytes() <= ws.DB_MAX_BYTES)
        for i in range(ws.BACKLOG_MAX):
            pass
        # only waiting events left and no room: refuse, never drop them
        stc._db.execute("UPDATE events SET status='queued', next_at=1e12")
        refused = False
        try:
            for i in range(200):
                stc.ingest(dict(HOOK, id=f"wh_q{i}"), big, "", f"q{i}")
        except ws.Busy:
            refused = True
        check("P1-1: when only waiting events fill the store it refuses (503) instead of dropping them", refused
              and stc._db.execute("SELECT COUNT(*) FROM events WHERE status='queued'").fetchone()[0] > 40)
    finally:
        ws.DB_MAX_BYTES = old

    # P3-b: eviction never removes a finished event whose notice has not gone out
    sce = Path(tempfile.mkdtemp(prefix="wh-cap2-"))
    ste = ws.Store(sce / "e.sqlite3")
    old2 = ws.DB_MAX_BYTES
    ws.DB_MAX_BYTES = 2 * 1024 * 1024
    try:
        for i in range(20):
            ste._db.execute("INSERT INTO events(id, hook_id, received_at, body, body_sha, status, finished_at,"
                            " notified_at) VALUES(?,?,?,?,?, 'failed', 1, 0)", (f"ev_un{i}", "wh_u", i, b"x" * 40000, ""))
        for i in range(40):
            ste._db.execute("INSERT INTO events(id, hook_id, received_at, body, body_sha, status, finished_at,"
                            " notified_at) VALUES(?,?,?,?,?, 'done', 1, 1)", (f"ev_ok{i}", "wh_u", 100 + i, b"x" * 40000, ""))
        ste.make_room()
        left = ste._db.execute("SELECT COUNT(*) FROM events WHERE id LIKE 'ev_un%' AND length(body)>0").fetchone()[0]
        check("P3-b: eviction keeps every failed event the owner was not yet told about (with its body)", left == 20)
    finally:
        ws.DB_MAX_BYTES = old2

    # P3-c: a heartbeat that comes after the lease time, with nobody else on the event, keeps the run
    shb = Path(tempfile.mkdtemp(prefix="wh-hb-"))
    sth = ws.Store(shb / "e.sqlite3")
    eh = sth.ingest(HOOK, b"x", "", "hb")[1]["event_id"]
    admit(sth)
    rh = sth.claim("W")
    sth.mark_dispatched(eh, rh["fence"])
    check("P3-c: a late heartbeat on an event still ours renews it", sth.heartbeat(eh, rh["fence"],
                                                                                   now=time.time() + ws.LEASE_S + 5))
    # P3-e: finishing an attempt resets the notice mark (a stale mark from the previous attempt cannot hide it)
    sth._db.execute("UPDATE events SET notified_at=123 WHERE id=?", (eh,))
    sth.finish(eh, rh["fence"], "done", "ok")
    check("P3-e: finish resets notified_at, so the new result is notified", sth.get(eh)["notified_at"] == 0)

    # P2-4: the database and its -wal/-shm are private
    sp = Path(tempfile.mkdtemp(prefix="wh-perm-"))
    old_mask = os.umask(0o022)
    try:
        stp = ws.Store(sp / "e.sqlite3")
        stp.ingest(HOOK, b'{"secret":"1"}', "", "p")
        modes = {f.name: oct(f.stat().st_mode & 0o777) for f in sp.iterdir()}
    finally:
        os.umask(old_mask)
    check("P2-4: database, -wal and -shm are all 0600", modes and all(m == "0o600" for m in modes.values()), modes)

    # P3: recover() does not requeue forever an event that keeps dying before dispatch
    sr = Path(tempfile.mkdtemp(prefix="wh-rec-"))
    str_ = ws.Store(sr / "e.sqlite3")
    eid = str_.ingest(HOOK, b"x", "", "rec")[1]["event_id"]
    admit(str_)
    t = time.time()
    for i in range(ws.MAX_AUTO_TRIES):
        str_.claim("W", now=t + i * 1000)
        str_.recover(now=t + i * 1000 + ws.LEASE_S + 1)
    check("an event lost before dispatch MAX_AUTO_TRIES times ends dead, not in an endless loop",
          str_.get(eid)["status"] == "dead")
    ok, _ = str_.retry(eid)
    r = str_.claim("W", now=t + 99999)
    check("owner retry of a dead event starts again from try 1", ok and r and r["tries"] == 1)

    # a stale lease cannot start the run even before recover() has looked at it
    eid2 = str_.ingest(dict(HOOK, id="wh_stale"), b"x", "", "st")[1]["event_id"]
    admit(str_)
    r2 = str_.claim("W")
    check("mark_dispatched on an expired (not yet recovered) lease is refused",
          not str_.mark_dispatched(eid2, r2["fence"], now=time.time() + ws.LEASE_S + 5))

    # dedup keys outlive pruned events
    str_._db.execute("UPDATE events SET status='done', finished_at=1, received_at=1 WHERE id=?", (eid2,))
    str_.prune()
    check("a key is still a duplicate after its event was pruned (keys kept by age)",
          str_.get(eid2) is None and str_.ingest(dict(HOOK, id="wh_stale"), b"x", "", "st")[0] == 200)

    # through the feature: retry notice, head-of-line, lost wake, heartbeat errors, notice failure
    fs = Path(tempfile.mkdtemp(prefix="wh-rf-"))
    got, started = [], {}
    gate = {"slow": asyncio.Event()}
    ans = {"v": ("", "boom")}

    async def rt(brain, text, level):
        if '"slow"' in text:
            started["slow"] = time.monotonic()
            await gate["slow"].wait()
            return "slow done", ""
        if '"fast"' in text:
            started["fast"] = time.monotonic()
        return ans["v"]

    async def nwf(*a, **k):
        return "", "", False

    async def snd(chat_id, text, viec=None, web="", brain="", dedup=""):
        got.append({"text": text, "dedup": dedup})
        return (False, "telegram down") if "DOWN" in text else (True, "")

    f = wt.WebhookFeature(wt.WebhookDeps(state_dir=lambda: fs, run_task=rt, run_workflow=nwf, send=snd,
                                         base_url=lambda _r: ""))
    ha, ta, _ = f.create("/b", name="A", target="task", text="x", chat_id="web:1")
    hb, tb, _ = f.create("/b", name="B", target="task", text="x", chat_id="web:1")
    # P1-2: the result of a Retry reaches the owner (new attempt, new dedup key)
    _, r1 = await f.accept(ha["id"], ta, b'{"k":1}', "application/json", "r1")
    await f.wait_idle()
    ans["v"] = ("order created #42", "")
    ok, _ = f.store().retry(r1["run_id"])
    f._kick()
    await f.wait_idle()
    texts = [g["text"] for g in got]
    check("P1-2: after a failed run and an owner Retry, the owner is told the retry's result",
          any("could not run" in x or "chưa chạy được" in x for x in texts) and any("order created #42" in x for x in texts),
          texts)
    check("P1-2: the two notices carry different dedup keys", len({g["dedup"] for g in got}) == len(got))

    # P2-1: one long run does not delay another hook
    t0 = time.monotonic()
    await f.accept(ha["id"], ta, b'{"slow":1}', "application/json", "slow")
    await asyncio.sleep(0.2)
    await f.accept(hb["id"], tb, b'{"fast":1}', "application/json", "fast")
    for _ in range(50):
        if "fast" in started:
            break
        await asyncio.sleep(0.02)
    check("P2-1: hook B starts while hook A's long run is still going", "fast" in started
          and "slow" in started and started["fast"] - t0 < 1.0, started)
    gate["slow"].set()
    await f.wait_idle()

    # P2-2: a kick that lands while a claim is in flight is not lost
    real_claim = f.store().claim
    hit = {"n": 0}

    def slow_claim(worker, now=None, avoid=None):
        hit["n"] += 1
        if hit["n"] == 1:
            time.sleep(0.4)
            return None              # nothing yet...
        return real_claim(worker, now, avoid)
    f.store().claim = slow_claim
    f._kick()
    await asyncio.sleep(0.1)         # ...the event arrives during that claim
    _, rw = await f.accept(hb["id"], tb, b'{"k":"wake"}', "application/json", "wake")
    for _ in range(100):
        if f.store().get(rw["run_id"])["status"] not in ("received", "queued", "running"):
            break
        await asyncio.sleep(0.02)
    f.store().claim = real_claim
    check("P2-2: an event accepted during an empty claim still runs at once (no 30 s wait for the sweep)",
          f.store().get(rw["run_id"])["status"] == "done")

    # P2-3: a heartbeat error does not kill the lease keeping; a refused finish keeps the run's result
    real_hb = f.store().heartbeat
    calls = {"n": 0}

    def flaky_hb(eid, fence, now=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise __import__("sqlite3").OperationalError("database is locked")
        return real_hb(eid, fence, now)
    f.store().heartbeat = flaky_hb
    old_hb = ws.HEARTBEAT_S
    ws.HEARTBEAT_S = 0.05
    gate["slow"] = asyncio.Event()
    _, rs = await f.accept(ha["id"], ta, b'{"slow":2}', "application/json", "slow2")
    await asyncio.sleep(0.3)
    check("P2-3: the heartbeat goes on after a failed renewal", calls["n"] >= 2, calls)
    gate["slow"].set()
    await f.wait_idle()
    ws.HEARTBEAT_S = old_hb
    f.store().heartbeat = real_hb
    check("P2-3: and the long run finishes as done", f.store().get(rs["run_id"])["status"] == "done")

    # notice delivery failure is retried at the sweep, at most NOTIFY_TRIES times
    ans["v"] = ("DOWN result", "")
    _, rd = await f.accept(hb["id"], tb, b'{"k":"down"}', "application/json", "down")
    await f.wait_idle()
    # The notice waits in the durable outbox and is tried again with a growing delay (fake clock here).
    t_n = time.time()
    for i in range(ws.NOTIFY_TRIES + 2):
        f.clock = (lambda v: (lambda: v))(t_n + 4000 * (i + 1))
        await f.sweep()
    f.clock = time.time
    n_down = sum(1 for g in got if "DOWN" in g["text"])
    rows_n = [n for n in f.store().notifications(event_id=rd["run_id"])]
    check("a notice the channel refused is tried again, but only NOTIFY_TRIES times, then kept as failed",
          n_down == ws.NOTIFY_TRIES and rows_n and rows_n[0]["status"] == "failed", (n_down, rows_n))
    await f.wait_idle()

    # API: the event detail keeps no worker host/pid, list results are short
    ev = f.store().get(r1["run_id"])
    check("event detail does not carry the worker host:pid", all("worker" not in a for a in ev["attempts"]))


asyncio.run(review())

src = (SERVER / "webhook_triggers.py").read_text(encoding="utf-8") + (SERVER / "webhook_store.py").read_text(encoding="utf-8")
check("no model is called by the webhook core (no engine imports)",
      not any(x in src for x in ("aux_engine", "claude_cli", "_reply_policy_sandbox_engine", "anthropic")))

if fails:
    print(f"\nFAIL {len(fails)}: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_webhook_store_m1: all pass")
