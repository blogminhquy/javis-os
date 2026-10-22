"""webhook_bench.py - the ingress benchmark of the webhook spec (§16), over a real HTTP socket (0.274.0).

    .venv/bin/python tools/webhook_bench.py                      # the spec target: 60 s, 20 req/s, 5 hooks, 10 KiB
    .venv/bin/python tools/webhook_bench.py --seconds 10 --slow 2   # shorter, every action waits 2 s at the receiver

Spec §16: "payload 10 KiB, 5 hooks, a total burst of 20 requests per second for 60 seconds; p95 ACK after the commit
under 250 ms, no accepted event lost and no model opened on a code-only branch. Measure ingress apart from slow actions
so receive latency and business latency are not mixed." This is a benchmark target on the machine it runs on, not a
promise about any VPS.

How it measures:
  - A CHILD process runs the real webhook feature (router, durable store, worker) under uvicorn on 127.0.0.1, with a
    temporary state folder. Every hook has one HTTP action to a fake receiver inside the child (no network) that
    answers after `--slow` seconds. Every model path raises and counts (a fail-fast guard): the count must stay 0.
  - The PARENT sends an open-loop schedule (request i leaves at i / rate, whether or not earlier ones answered) and
    times each request from send to answer: that is the ACK latency the sender sees, after the commit.
  - Afterwards it waits for processing to settle, then reads the store: every 202 must be an event with a final or
    waiting state, deliveries must match, and the guard count must be 0. Processing latency is reported apart.

Exit code 0 when every target holds, 1 otherwise. `run()` is also used by tests/python/test_webhook_bench_short.py.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "server"

CHILD = r'''
import asyncio, json, os, sys, time
from pathlib import Path
import httpx, uvicorn
from fastapi import FastAPI
import webhook_triggers as wt

S = Path(os.environ["JAVIS_STATE_DIR"])
SLOW = float(os.environ["BENCH_SLOW"])
GUARD = S / "model_calls.txt"

def guard(*a, **k):
    n = int(GUARD.read_text() or 0) + 1 if GUARD.exists() else 1
    GUARD.write_text(str(n))
    raise RuntimeError("benchmark: a model path was called")

async def run_task(*a, **k):
    guard()

async def run_workflow(*a, **k):
    guard()

async def send(*a, **k):
    return True, ""

async def receiver(req):
    if SLOW:
        await asyncio.sleep(SLOW)
    return httpx.Response(200, json={"ok": True})

f = wt.WebhookFeature(wt.WebhookDeps(state_dir=lambda: S, run_task=run_task, run_workflow=run_workflow, send=send,
                                     base_url=lambda r: "http://127.0.0.1", http_transport=httpx.MockTransport(receiver),
                                     resolve=lambda h: ["93.184.216.34"], incident_hook=lambda *a, **k: guard()))
hooks = []
for i in range(int(os.environ["BENCH_HOOKS"])):
    acts = [{"id": "crm", "kind": "http", "url": f"https://receiver{i}.example/in", "body": "raw",
             "retry_safety": "idempotent"}]
    ai = os.environ.get("BENCH_AI") == "1" and i == 0     # negative control: proves the guard counts
    h, tok, err = f.create("/bench", name=f"bench {i}", target="task" if ai else "", text="x" if ai else "",
                           level="full", notify="none", limits={"per_minute": 6000, "burst": 1000},
                           actions=acts + ([{"id": "ai", "kind": "ai"}] if ai else []))
    assert h, err
    hooks.append({"id": h["id"], "token": tok})
(S / "hooks.json").write_text(json.dumps(hooks))
app = FastAPI()
app.include_router(f.router)

@app.on_event("startup")
async def _start():
    f.start()

uvicorn.run(app, host="127.0.0.1", port=int(os.environ["BENCH_PORT"]), log_level="warning", access_log=False)
'''

FINAL_OR_WAITING = ("done", "silent", "failed", "dead", "unknown", "waiting", "blocked", "cancelled")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _pct(xs: list, p: float):
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(len(xs) * p))], 2)


async def _load(port: int, hooks: list, seconds: float, rate: float, size_kib: int) -> dict:
    import httpx
    pad = "x" * max(0, size_kib * 1024 - 200)
    lat, codes, errors = [], {}, []
    t0 = time.perf_counter()
    n = int(seconds * rate)
    limits = httpx.Limits(max_connections=200, max_keepalive_connections=50)
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", limits=limits, timeout=30, trust_env=False) as cl:
        async def one(i: int):
            await asyncio.sleep(max(0.0, t0 + i / rate - time.perf_counter()))
            h = hooks[i % len(hooks)]
            body = json.dumps({"id": i, "status": 1, "shop_id": 7, "pad": pad}).encode()
            s = time.perf_counter()
            try:
                r = await cl.post(f"/hooks/{h['id']}", content=body,
                                  headers={"X-Javis-Token": h["token"], "Content-Type": "application/json",
                                           "X-Javis-Event-Id": f"bench-{i}"})
                lat.append((time.perf_counter() - s) * 1000)
                codes[r.status_code] = codes.get(r.status_code, 0) + 1
            except Exception as e:                    # a refused or dropped connection counts as a failure
                errors.append(f"{type(e).__name__}: {e}")
        await asyncio.gather(*(one(i) for i in range(n)))
    return {"sent": n, "wall_s": round(time.perf_counter() - t0, 2), "codes": codes, "errors": errors[:5],
            "ack_ms": {"p50": _pct(lat, 0.5), "p95": _pct(lat, 0.95), "p99": _pct(lat, 0.99),
                       "max": round(max(lat), 2) if lat else None}}


def _settled(db: Path, sent: int, timeout: float) -> dict:
    end = time.time() + timeout
    while True:
        c = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        try:
            by = dict(c.execute("SELECT status, COUNT(*) FROM events GROUP BY status").fetchall())
            lat = [r[0] for r in c.execute("SELECT finished_at - received_at FROM events WHERE finished_at > 0")]
            dl = dict(c.execute("SELECT status, COUNT(*) FROM deliveries GROUP BY status").fetchall())
        finally:
            c.close()
        open_n = sum(v for k, v in by.items() if k not in FINAL_OR_WAITING)
        if open_n == 0 or time.time() > end:
            return {"events": by, "deliveries": dl, "open": open_n,
                    "processing_s": {"p50": _pct(lat, 0.5), "p95": _pct(lat, 0.95), "max": _pct(lat, 1.0)}}
        time.sleep(0.5)


def run(seconds: float = 60, rate: float = 20, hooks: int = 5, size_kib: int = 10, slow: float = 0.0,
        settle_s: float = 120, ai_control: bool = False) -> dict:
    """`ai_control` gives hook 0 an AI action: the guard must then count model calls (it proves the guard works)."""
    state = Path(tempfile.mkdtemp(prefix="javis-wh-bench-"))
    port = _free_port()
    env = dict(os.environ, JAVIS_STATE_DIR=str(state), PYTHONPATH=str(SERVER), BENCH_PORT=str(port),
               BENCH_HOOKS=str(hooks), BENCH_SLOW=str(slow), JAVIS_NO_REAL_JUDGE_ENGINE="1",
               BENCH_AI="1" if ai_control else "0")
    for k in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy", "ALL_PROXY", "all_proxy"):
        env.pop(k, None)
    proc = subprocess.Popen([sys.executable, "-c", CHILD], env=env, cwd=str(SERVER),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.time() + 60
        while not (state / "hooks.json").exists() or not _port_open(port):
            if proc.poll() is not None or time.time() > deadline:
                raise RuntimeError("benchmark server did not start: " + (proc.stdout.read() if proc.stdout else ""))
            time.sleep(0.2)
        hk = json.loads((state / "hooks.json").read_text())
        load = asyncio.run(_load(port, hk, seconds, rate, size_kib))
        # With slow receivers the backlog is EXPECTED to outlast the run (spec §11: one delivery at a time per hook),
        # so only a short wait: the point there is that ingress does not slow down and nothing is lost.
        settled = _settled(state / "webhook_events.sqlite3", load["sent"], min(settle_s, 15) if slow else settle_s)
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
    guard = int((state / "model_calls.txt").read_text() or 0) if (state / "model_calls.txt").exists() else 0
    accepted = load["codes"].get(202, 0)
    stored = sum(settled["events"].values())
    res = {"params": {"seconds": seconds, "rate": rate, "hooks": hooks, "size_kib": size_kib, "slow_s": slow},
           "load": load, "store": settled, "model_calls": guard, "state_dir": str(state)}
    queued_only = all(k in FINAL_OR_WAITING or k in ("received", "queued", "running") for k in settled["events"])
    # One delivery at a time per hook, inside a process-wide pool (spec §11): min(hooks, WORKER_MAX) run at once.
    sys.path.insert(0, str(SERVER))
    import webhook_worker
    res["throughput_limit_per_s"] = round(min(hooks, webhook_worker.WORKER_MAX) / slow, 2) if slow else None
    res["targets"] = {
        "every request answered 202": accepted == load["sent"] and not load["errors"],
        "p95 ACK under 250 ms": (load["ack_ms"]["p95"] or 1e9) < 250,
        "every 202 stored with a final or waiting state": stored == accepted and settled["open"] == 0,
    } if not slow else {
        "every request answered 202": accepted == load["sent"] and not load["errors"],
        "p95 ACK under 250 ms": (load["ack_ms"]["p95"] or 1e9) < 250,
        "every 202 stored durably; the rest waits in the queue, none dropped": stored == accepted and queued_only,
    }
    res["targets"].update({
        # With the AI control, hook 0 has two actions per event, so the count is checked only without it.
        "one delivery per event, none lost": ai_control or sum(settled["deliveries"].values()) == accepted,
        "no model call on the code-only path": guard == 0,
    })
    res["ok"] = all(res["targets"].values())
    return res


def _port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Webhook ingress benchmark (spec §16).")
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--rate", type=float, default=20, help="requests per second, all hooks together")
    ap.add_argument("--hooks", type=int, default=5)
    ap.add_argument("--size-kib", type=int, default=10)
    ap.add_argument("--slow", type=float, default=0.0, help="seconds the fake receiver waits before answering")
    ap.add_argument("--json", action="store_true", help="print the whole result as JSON")
    a = ap.parse_args(argv)
    res = run(a.seconds, a.rate, a.hooks, a.size_kib, a.slow)
    if a.json:
        print(json.dumps(res, indent=1, ensure_ascii=False))
    else:
        ld, st = res["load"], res["store"]
        print(f"sent {ld['sent']} in {ld['wall_s']} s, answers {ld['codes']}, errors {len(ld['errors'])}")
        print(f"ACK ms p50 {ld['ack_ms']['p50']}  p95 {ld['ack_ms']['p95']}  p99 {ld['ack_ms']['p99']}  max {ld['ack_ms']['max']}")
        print(f"processing s p50 {st['processing_s']['p50']}  p95 {st['processing_s']['p95']}  max {st['processing_s']['max']}")
        print(f"events {st['events']}  deliveries {st['deliveries']}  model calls {res['model_calls']}")
        if res["throughput_limit_per_s"]:
            print(f"processing limit (one delivery per hook, shared pool): {res['throughput_limit_per_s']} events/s")
        for k, v in res["targets"].items():
            print(("ok   " if v else "FAIL ") + k)
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
