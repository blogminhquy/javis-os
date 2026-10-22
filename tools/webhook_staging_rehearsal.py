"""webhook_staging_rehearsal.py - the staging pack's parts 1, 2 and 4 against the REAL host app, locally (0.274.0).

    .venv/bin/python tools/webhook_staging_rehearsal.py [--out report.json]

What it runs (docs/webhook-platform/staging-pilot-pack.md):
  - `main.app` under uvicorn in a CHILD process, a fresh temporary JAVIS_STATE_DIR, real HTTP sockets, real SQLite.
  - Local receivers on 127.0.0.1 (`allow_private` actions): one answers at once, one waits 6 s, one answers 500.
  - The child refuses every model path (run_task, run_workflow, incident triage): a call is written to a marker file
    and fails the run.
  - Real process kills: SIGKILL in the middle of a burst and in the middle of a slow delivery, then a restart on the
    same state folder.

What it does NOT cover (needs a real source, part 3 of the pack): POSCake, Apps Script (its address must be
script.google.com), plugins on a real thread, Stripe, GitHub, Shopify, Systeme.io. A pass here is not "production
verified" for any adapter.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import signal
import socket
import subprocess
import sys
import shutil
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"

CHILD = r'''
import os, sys, json
marker = os.environ["REHEARSAL_MODEL_MARKER"]
def boom(*a, **k):
    with open(marker, "a") as f:
        f.write("model path reached\n")
    raise RuntimeError("FAIL-FAST: a real model path was reached")
import main, uvicorn
main.webhook_feature.deps.run_task = boom
main.webhook_feature.deps.run_workflow = boom
main.incident_desk.deps.ask = boom
uvicorn.run(main.app, host="127.0.0.1", port=int(os.environ["REHEARSAL_PORT"]), log_level="warning", access_log=False)
'''

ORDER = {"shop_id": 7, "id": 1001, "status": 1, "bill_full_name": "Nguyen Lan", "bill_phone_number": "0912345678",
         "items": [{"name": "Nuoc mam"}, {"name": "Goi TRO LY AI JAVIS 12 thang"}]}
RULES = {"filter": {"all": [{"path": "status", "op": "eq", "value": 1},
                            {"path": "items[*].name", "op": "contains", "value": "TRO LY AI JAVIS",
                             "quantifier": "any", "case_sensitive": False, "reason": "product_not_found"}]},
         "dedup": {"policy_version": 1, "business_paths": ["shop_id", "id", "status"], "ttl_s": 604800,
                   "missing": "quarantine"},
         "correlation": "id"}
FINAL = ("done", "silent", "failed", "dead", "unknown", "waiting", "blocked", "cancelled", "filtered", "duplicate",
         "invalid")

results: list = []


def check(name: str, ok: bool, detail="") -> None:
    results.append({"step": name, "pass": bool(ok), "detail": detail if not ok else ""})
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f"  {str(detail)[:600]}"), flush=True)


# ── local receivers ──
LOG: list = []
LOG_LOCK = threading.Lock()


class Receiver(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(n) if n else b""
        did = self.headers.get("X-Javis-Delivery-Id") or self.headers.get("X-Javis-Event-Id") or ""
        with LOG_LOCK:
            LOG.append({"path": self.path, "delivery": did, "event": self.headers.get("X-Javis-Event-Id") or "",
                        "at": time.time(), "len": len(body)})
        if self.path.startswith("/slow"):
            time.sleep(6)
        code = 500 if self.path.startswith("/fail") else 200
        out = json.dumps({"ok": code == 200}).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(out)))
        self.end_headers()
        try:
            self.wfile.write(out)
        except (BrokenPipeError, ConnectionResetError):
            pass                     # the host was killed mid-call (part 1.2): that is the point


def hits(prefix: str) -> list:
    with LOG_LOCK:
        return [x for x in LOG if x["path"].startswith(prefix)]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Host:
    def __init__(self, state: Path, marker: Path):
        self.state, self.marker, self.port, self.proc = state, marker, free_port(), None
        self.base = f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        env = dict(os.environ, JAVIS_STATE_DIR=str(self.state), REHEARSAL_PORT=str(self.port),
                   REHEARSAL_MODEL_MARKER=str(self.marker), PYTHONPATH=str(SERVER), JAVIS_REQUIRE_LOGIN="0")
        self.proc = subprocess.Popen([sys.executable, "-c", CHILD], env=env, cwd=str(SERVER),
                                     stdout=subprocess.DEVNULL, stderr=open(self.state / "host.log", "ab"))
        for _ in range(300):
            try:
                if httpx.get(self.base + "/webhooks", timeout=2).status_code < 500:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        raise RuntimeError("the host did not start (see host.log)")

    def kill9(self) -> None:
        self.proc.send_signal(signal.SIGKILL)
        self.proc.wait(timeout=10)

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.kill9()

    def api(self, method: str, path: str, **kw):
        r = httpx.request(method, self.base + path, timeout=30, headers={"origin": self.base}, **kw)
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, r.text

    def hook(self, **cfg) -> tuple:
        code, d = self.api("POST", "/webhooks", json=dict({"target": "", "text": "", "level": "full"}, **cfg))
        assert code == 200 and d.get("ok"), (code, d)
        return d["hook"]["id"], d["token"]

    def send(self, hid: str, token: str, doc, key: str = "") -> tuple:
        h = {"X-Javis-Token": token, "content-type": "application/json"}
        if key:
            h["Idempotency-Key"] = key
        r = httpx.post(self.base + f"/hooks/{hid}", content=json.dumps(doc).encode(), headers=h, timeout=30)
        try:
            return r.status_code, r.json()
        except ValueError:
            return r.status_code, r.text

    def event(self, eid: str) -> dict:
        code, d = self.api("GET", f"/webhooks/events/{eid}")
        return d.get("event") if code == 200 and isinstance(d, dict) else {}

    def wait(self, eids, timeout=240.0, want=FINAL) -> dict:
        end, last = time.time() + timeout, {}
        while time.time() < end:
            last = {e: self.event(e) for e in eids}
            if all((v or {}).get("status") in want for v in last.values()):
                return last
            time.sleep(1)
        return last


def http_action(aid: str, path: str, rport: int, **kw) -> dict:
    return dict({"id": aid, "kind": "http", "url": f"http://127.0.0.1:{rport}{path}", "allow_private": True}, **kw)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    ap.add_argument("--keep", action="store_true", help="keep the state folder (SQLite, host.log) even when all pass")
    args = ap.parse_args()
    rport = free_port()
    srv = ThreadingHTTPServer(("127.0.0.1", rport), Receiver)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    state = Path(tempfile.mkdtemp(prefix="javis-rehearsal-"))
    marker = state / "model-calls.txt"
    host = Host(state, marker)
    t0 = time.time()
    try:
        host.start()

        # ── part 1.1: 20 events, the server killed (SIGKILL) after 10, then restarted on the same state ──
        hid, tok = host.hook(name="Burst", rules={"filter": {"all": [{"path": "n", "op": "exists"}]}},
                             actions=[http_action("fwd", "/ok", rport, retry="safe")])
        accepted = []
        for i in range(20):
            if i == 10:
                host.kill9()
                host.start()
            code, d = host.send(hid, tok, {"n": i})
            if code == 202:
                accepted.append(d["event_id"])
        evs = host.wait(accepted)
        not_final = {e: (v or {}).get("status") for e, v in evs.items() if (v or {}).get("status") not in FINAL}
        check("1.1 20 events, SIGKILL after 10 and a restart: every 202 has an event with a final or waiting state",
              len(accepted) == 20 and not not_final, {"accepted": len(accepted), "not_final": not_final})
        got = {x["event"] for x in hits("/ok")}
        check("1.1 every accepted event reached the receiver", set(accepted) <= got,
              sorted(set(accepted) - got)[:5])

        # ── part 1.2: SIGKILL while a slow delivery runs (manual_on_ambiguous): unknown after the restart ──
        hid2, tok2 = host.hook(name="Slow", actions=[http_action("slow", "/slow", rport)])
        code, d = host.send(hid2, tok2, {"n": "slow"})
        eid2 = d.get("event_id") if isinstance(d, dict) else ""
        end = time.time() + 30
        while time.time() < end and not hits("/slow"):
            time.sleep(0.1)
        host.kill9()
        host.start()
        ev = host.wait([eid2], timeout=400, want=("unknown", "done", "failed"))[eid2] or {}
        br = (ev.get("branches") or [{}])[0]
        check("1.2 SIGKILL during a slow delivery: after the restart it is unknown, sent once, never resent alone",
              code == 202 and br.get("status") == "unknown" and len(hits("/slow")) == 1,
              {"event": ev.get("status"), "delivery": br.get("status"), "detail": br.get("detail"),
               "sends": len(hits("/slow"))})
        told, end = [], time.time() + 60
        while time.time() < end and not told:
            with sqlite3.connect(state / "webhook_events.sqlite3") as db:
                told = db.execute("SELECT status, text FROM notifications WHERE event_id=?", (eid2,)).fetchall()
            time.sleep(1)
        check("1.2 the owner is told (a notice queued and sent for that event)",
              bool(told) and told[0][0] == "sent", told)

        # ── part 1.3: a 429, then the same Idempotency-Key once the window has room again ──
        hid3, tok3 = host.hook(name="Quota", limits={"per_minute": 1, "burst": 1},
                               actions=[http_action("fwd", "/ok", rport, retry="safe")])
        c1, _ = host.send(hid3, tok3, {"n": 1}, key="k-1")
        c2, _ = host.send(hid3, tok3, {"n": 2}, key="k-2")
        time.sleep(62)
        c3, d3 = host.send(hid3, tok3, {"n": 2}, key="k-2")
        check("1.3 a 429, then the same Idempotency-Key is received (202), not a duplicate",
              c1 == 202 and c2 == 429 and c3 == 202 and not (isinstance(d3, dict) and d3.get("duplicate")),
              {"first": c1, "second": c2, "resend": c3, "resend_body": d3})

        # ── part 2: rules ──
        hid4, tok4 = host.hook(name="POSCake-like", rules=RULES,
                               actions=[http_action("fwd", "/ok", rport, retry="safe")])
        code, sim = host.api("POST", "/webhooks/simulate", json={"id": hid4, "payload": json.dumps(ORDER)})
        c, d = host.send(hid4, tok4, ORDER, key="order-a")
        ev4 = host.wait([d["event_id"]])[d["event_id"]] or {}
        decision = (sim or {}).get("decision") if isinstance(sim, dict) else None
        check("2.1 the decision on receipt equals the simulation's (run)", code == 200 and decision == "run"
              and ev4.get("status") == "done", {"simulate": decision, "event": ev4.get("status")})
        c, d = host.send(hid4, tok4, ORDER, key="order-b")
        ev5 = host.wait([d["event_id"]])[d["event_id"]] or {}
        check("2.2 the same order with another idempotency key is a duplicate of the first",
              c in (200, 202) and ev5.get("status") == "duplicate", {"code": c, "event": ev5.get("status")})
        sent_before = len(hits("/ok"))
        bad = []
        for doc in (dict(ORDER, id=2001, status="1"), dict(ORDER, id=2002, items=[{"sku": "x"}])):
            c, d = host.send(hid4, tok4, doc)
            bad.append(host.wait([d["event_id"]])[d["event_id"]] or {})
        why = [(e.get("status"), e.get("reason") or e.get("error") or "") for e in bad]
        # Strict types: the text "1" is not the number 1, so the status condition fails (spec §5 names the reason
        # status_mismatch); an item list without a name fails the product condition (its own label).
        check("2.3 status as text, or an item without a name: ignored with its reason, never run",
              [s for s, _ in why] == ["filtered", "filtered"] and len(hits("/ok")) == sent_before
              and why[0][1] == "status_mismatch" and why[1][1] == "product_not_found", why)

        # ── part 4: operations ──
        hid6, tok6 = host.hook(name="Breaker", actions=[http_action("bad", "/fail", rport)])
        e6 = []
        for i in range(7):
            c, d = host.send(hid6, tok6, {"n": i})
            e6.append(d["event_id"])
            host.wait([d["event_id"]], timeout=60, want=FINAL + ("retry", "queued"))
        time.sleep(3)
        code, health = host.api("GET", "/webhooks/health")
        check("4.2 a receiver answering 500: after 5 failures sending pauses, no sends during the pause",
              len(hits("/fail")) == 5, {"sends": len(hits("/fail")), "health": str(health)[:300]})

        hid7, tok7 = host.hook(name="AI zero", target="task", text="Ghi chu don", ai_per_hour=0,
                               actions=[{"id": "ai", "kind": "ai"}])
        c, d = host.send(hid7, tok7, {"n": 1})
        ev7 = host.wait([d["event_id"]], timeout=60)[d["event_id"]] or {}
        check("4.3 ai_per_hour 0: the AI delivery is blocked before any model is called",
              ev7.get("status") == "blocked" and not marker.exists(), {"event": ev7.get("status")})

        code, csv = host.api("GET", f"/webhooks/events/export?hook={hid4}&format=csv")
        txt = csv if isinstance(csv, str) else json.dumps(csv)
        cells = [c.strip('"') for line in txt.splitlines()[1:] for c in line.split(",")]
        check("4.4 CSV export: customer phone masked, no cell starts a formula",
              code == 200 and "0912345678" not in txt and not [c for c in cells if c[:1] in ("=", "+", "@")],
              txt[:300])
        code, _ = host.api("GET", f"/webhooks/events/export?hook={hid4}&format=csv&raw=1&body=1")
        _, audit = host.api("GET", "/webhooks/audit")
        check("4.4 raw=1 export is written to the audit log", code == 200 and "export_raw" in json.dumps(audit), "")

        shots = state / "ui"
        shots.mkdir()
        ui = subprocess.run(["node", str(ROOT / "tools" / "webhook_ui_narrow_check.mjs"), host.base, str(shots)],
                            capture_output=True, text=True, timeout=180,
                            env=dict(os.environ, CHROMIUM_PATH=os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")))
        check("4.5 UI at 390 px: no sideways scroll, nothing under 16px, no page error", ui.returncode == 0,
              (ui.stdout + ui.stderr)[-500:])

        check("no model path reached in the whole run", not marker.exists(),
              marker.read_text() if marker.exists() else "")
    finally:
        host.stop()
        srv.shutdown()
    rep = {"sha": subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True,
                                 text=True).stdout.strip(),
           "seconds": round(time.time() - t0), "state_dir": str(state), "results": results}
    if args.out:
        Path(args.out).write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    bad = [r["step"] for r in results if not r["pass"]]
    if not (bad or args.keep):
        shutil.rmtree(state, ignore_errors=True)       # a failed run keeps its state folder to read host.log
    print(f"\n{len(results) - len(bad)} of {len(results)} passed in {rep['seconds']} s" + (f"; FAILED: {bad}" if bad else "")
          + (f"; state kept in {state}" if bad or args.keep else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
