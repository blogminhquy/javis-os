"""Time the plain reads behind the dashboard pages, on this machine's real data (speed review 2026-11-23).

    python docs/dev/2026-11-ra-soat-toc-do/api_read_bench.py                 # 7 runs per read
    python docs/dev/2026-11-ra-soat-toc-do/api_read_bench.py --runs 11 --json out.json

Not a test: no pass/fail, never picked up by CI.

How. The real `main.app` is loaded in THIS process and each read goes through it in memory (every middleware, the
route, the JSON encoding), with no network and no listening port. The sign-in gate is switched off for this process
only, which opens nothing to anyone: the process already reads the same files directly. No session, token or log line
is written, the start-up tasks of the server (schedulers, loops) never run, and only reads the server itself lists as
free of side effects are called (server/read_batch.py ALLOWED_PATHS), minus the ones that go out to the network.

Left out on purpose: /usage/summary and /usage/insights. They first rescan every engine's session files to refresh
the usage index (usage_index.refresh), the same work opening the Usage page does, and on a machine with many Codex
sessions that rescan ran for over 45 seconds. Time those in the browser, on the Usage page, instead.

What the numbers are: time inside the server for one read at a time, plus the size of the answer raw and gzipped as
the dashboard receives it. Over a 150 to 400 ms tunnel the round trip is added on top of each wave of reads.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sqlite3
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SERVER = ROOT / "server"


def p95(values):
    s = sorted(values)
    return s[min(len(s) - 1, max(0, -(-95 * len(s) // 100) - 1))]


def longest_chats():
    """(id, message count) of the longest chat and of a typical one, read straight from the store."""
    state = os.environ.get("JAVIS_STATE_DIR") or ""
    db = Path(state) / "conversations.db"
    if not db.exists():
        return []
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute("select session_id, count(*) n from messages group by session_id order by n desc").fetchall()
    finally:
        con.close()
    rows = [r for r in rows if len(r[0]) >= 8 and r[0].isalnum()]
    if not rows:
        return []
    return [("longest", rows[0][0], rows[0][1]), ("typical", rows[len(rows) // 2][0], rows[len(rows) // 2][1])]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", type=int, default=7)
    ap.add_argument("--brain", default="brain")
    ap.add_argument("--json", default="")
    a = ap.parse_args(argv)

    sys.path.insert(0, str(SERVER))
    os.chdir(SERVER)
    t0 = time.perf_counter()
    import main as app_main
    from starlette.testclient import TestClient
    print(f"import main: {(time.perf_counter() - t0) * 1000:.0f} ms", flush=True)

    app_main.cfgmod.gate_active = lambda: False      # this process only; see the note at the top
    client = TestClient(app_main.app, base_url="http://127.0.0.1:7777")   # no `with`: start-up tasks never run
    b = a.brain

    groups = [
        ("start-up", [
            "/settings", "/config", "/brains", f"/agents?brain={b}", f"/skills?brain={b}", f"/workflows?brain={b}",
            f"/sessions?brain={b}&limit=21", f"/projects?brain={b}", f"/files/list?brain={b}",
            f"/graph?source={b}&orphans=1", "/inbox?limit=40", "/notifications", "/ui/order", "/pet/menu",
            "/background", "/chat/route", f"/sessions/unread-summary?brain={b}", f"/teams/unread?brain={b}",
        ]),
        ("tasks page", [
            f"/kanban?brain={b}&history=40", "/viec/all", f"/reminders?brain={b}", f"/watch?brain={b}",
            "/incidents?limit=50", f"/loops/log?brain={b}&limit=60", f"/agents?brain={b}&prompt=0&system=1",
            f"/my-tasks?brain={b}", f"/tasks/bots?brain={b}",
        ]),
        ("customer chats and chatbot", [
            f"/conversations?limit=30&q=&brain={b}", f"/channels/accounts?brain={b}",
        ]),
        ("teams", [f"/teams?brain={b}"]),
    ]
    chat = []
    for label, sid, n in longest_chats():
        # labels carry the size of the chat, never its id: the output gets pasted into reports
        chat += [(f"/sessions/{sid}?limit=30&tools=0", f"open chat, {label} ({n} messages), last 30"),
                 (f"/sessions/{sid}/meta", f"chat meta, {label}")]
        if label == "longest":
            chat += [(f"/sessions/{sid}", f"whole chat, {label} ({n} messages)")]
    groups.insert(1, ("chat", chat))

    out = []
    for group, paths in groups:
        print(f"\n== {group} ==")
        for item in paths:
            path, label = item if isinstance(item, tuple) else (item, item)
            try:
                r = client.get(path)            # warm-up, not counted
                times = []
                for _ in range(a.runs):
                    t = time.perf_counter()
                    r = client.get(path)
                    times.append((time.perf_counter() - t) * 1000)
            except Exception as e:   # noqa: BLE001
                print(f"  {label:<58} ERROR {type(e).__name__}: {e}")
                continue
            raw = len(r.content)
            gz = len(gzip.compress(r.content, 5)) if raw >= 1400 else raw
            row = {"group": group, "read": label, "status": r.status_code, "median_ms": round(statistics.median(times), 1),
                   "p95_ms": round(p95(times), 1), "raw_kb": round(raw / 1024, 1), "gzip_kb": round(gz / 1024, 1)}
            out.append(row)
            show = label if len(label) <= 58 else label[:55] + "..."
            print(f"  {show:<58} {r.status_code}  median {row['median_ms']:8.1f} ms  p95 {row['p95_ms']:8.1f} ms"
                  f"  {row['raw_kb']:8.1f} KB raw  {row['gzip_kb']:7.1f} KB gzip")
    if a.json:
        Path(a.json).write_text(json.dumps({"runs": a.runs, "rows": out}, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
