"""How long a chat turn waits for its first words, from this machine's own run history (speed review 2026-11-23).

    python docs/dev/2026-11-ra-soat-toc-do/chat_turn_wait.py                # every turn on record
    python docs/dev/2026-11-ra-soat-toc-do/chat_turn_wait.py --days 7

Not a test: no pass/fail, never picked up by CI. Opens `runtime.db` read-only and prints numbers only: no chat text,
no session id.

Where the numbers come from. Every owner turn writes one `engine.first_output` event with `ms`, counted from the
start of `_do_turn` (server/main.py) to the first thing the engine sends back, and `warm` (true when the turn took a
process the warm pool already had running). `task.started` and `task.finished` give the wait before `_do_turn` and
the length of the whole turn. Since 2026-11-23 a cold turn also carries `cold`, the reason it found no process
(`thread_rotated`, `idle_expired`, `new_chat`, `config_changed` with `cold_parts`...): the "why cold" table reads it.
Turns recorded before that have no reason and show as "(not recorded)".
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import statistics
import time
from collections import defaultdict
from pathlib import Path


def pct(values, q):
    s = sorted(values)
    if not s:
        return 0
    return s[min(len(s) - 1, max(0, -(-q * len(s) // 100) - 1))]


def line(label, values):
    if not values:
        print(f"  {label:<44} n=0")
        return
    print(f"  {label:<44} n={len(values):<4} p50 {statistics.median(values):>8.0f}  p75 {pct(values, 75):>8.0f}"
          f"  p95 {pct(values, 95):>8.0f}  max {max(values):>8.0f}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--days", type=float, default=0, help="only the last N days (0 = everything on record)")
    ap.add_argument("--db", default="")
    a = ap.parse_args(argv)
    db = Path(a.db or Path(os.environ.get("JAVIS_STATE_DIR") or ".") / "runtime.db")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    since = time.time() - a.days * 86400 if a.days else 0

    started, finished = {}, {}
    for task, kind, at in con.execute(
            "select task_id, event_type, created_at from runtime_events"
            " where event_type in ('task.started','task.finished')"):
        (started if kind == "task.started" else finished).setdefault(task, at)
    channel = dict(con.execute("select id, channel from runtime_tasks"))
    model = {}
    for task, step, m in con.execute("select task_id, id, model from runtime_steps"):
        model[step] = m or "?"

    rows = []
    for task, step, payload, at in con.execute(
            "select task_id, step_id, payload_json, created_at from runtime_events"
            " where event_type='engine.first_output' and created_at >= ? order by seq", (since,)):
        try:
            p = json.loads(payload)
        except ValueError:
            continue
        ms = float(p.get("ms") or 0)
        t_turn0 = at - ms / 1000
        rows.append({"engine": p.get("engine") or "?", "warm": bool(p.get("warm")), "ms": ms, "at": at,
                     "cold": p.get("cold") or "(not recorded)", "cold_parts": p.get("cold_parts") or [],
                     "ahead": bool(p.get("opened_ahead")),
                     "task": task, "channel": channel.get(task, "?"), "model": model.get(step, "?"),
                     "before_ms": (t_turn0 - started[task]) * 1000 if task in started else None,
                     "turn_s": finished[task] - started[task] if task in started and task in finished else None})
    if not rows:
        print("no engine.first_output events in range")
        return 0
    span = (time.strftime("%Y-%m-%d", time.localtime(rows[0]["at"])), time.strftime("%Y-%m-%d", time.localtime(rows[-1]["at"])))
    warm_n = sum(1 for r in rows if r["warm"])
    print(f"{len(rows)} turns with a first-output time, {span[0]} to {span[1]}; warm {warm_n} ({100 * warm_n // len(rows)}%)")
    print("channels:", dict(sorted(defaultdict(int, {c: sum(1 for r in rows if r['channel'] == c)
                                                      for c in {r['channel'] for r in rows}}).items())))

    print("\n== time to first output, ms (start of _do_turn to the engine's first event) ==")
    for eng in sorted({r["engine"] for r in rows}):
        for warm in (False, True):
            line(f"{eng}, {'warm' if warm else 'cold'}", [r["ms"] for r in rows if r["engine"] == eng and r["warm"] == warm])

    print("\n== why cold (share of ALL turns of the engine), ms ==")
    for eng in sorted({r["engine"] for r in rows}):
        sub = [r for r in rows if r["engine"] == eng]
        cold = [r for r in sub if not r["warm"]]
        for why in sorted({r["cold"] for r in cold}, key=lambda w: -sum(1 for r in cold if r["cold"] == w)):
            v = [r["ms"] for r in cold if r["cold"] == why]
            line(f"{eng}, {why} ({100 * len(v) / len(sub):.1f}%)", v)
        changed = defaultdict(int)
        for r in cold:
            for part in r["cold_parts"]:
                changed[part] += 1
        if changed:
            print("    parts that changed:", dict(sorted(changed.items(), key=lambda kv: -kv[1])))
        ahead = [r["ms"] for r in sub if r["warm"] and r["ahead"]]
        if ahead:
            line(f"{eng}, WARM on a thread opened ahead ({100 * len(ahead) / len(sub):.1f}%)", ahead)

    print("\n== by model, ms ==")
    for key in sorted({(r["engine"], r["model"]) for r in rows}):
        for warm in (False, True):
            v = [r["ms"] for r in rows if (r["engine"], r["model"]) == key and r["warm"] == warm]
            if len(v) >= 5:
                line(f"{key[0]} {key[1]}, {'warm' if warm else 'cold'}", v)

    print("\n== spread, all engines ==")
    edges = [(0, 3000, "under 3 s"), (3000, 6000, "3 to 6 s"), (6000, 10000, "6 to 10 s"), (10000, 20000, "10 to 20 s"),
             (20000, 1e12, "over 20 s")]
    for lo, hi, label in edges:
        n = sum(1 for r in rows if lo <= r["ms"] < hi)
        print(f"  {label:<12} {n:>4}  {100 * n / len(rows):4.1f}%")

    print("\n== wait before _do_turn starts (task.started to turn start), ms ==")
    line("all", [r["before_ms"] for r in rows if r["before_ms"] is not None and r["before_ms"] >= 0])

    print("\n== other turns running on the machine when this one started (any channel) ==")
    spans = sorted((s, finished.get(t, s + 600)) for t, s in started.items())
    def others(r):
        t0 = r["at"] - r["ms"] / 1000
        return sum(1 for s, e in spans if s < t0 < e) - 1
    buckets = [(0, 0, "0 others"), (1, 1, "1 other"), (2, 3, "2 to 3 others"), (4, 10 ** 6, "4 or more")]
    for eng in sorted({r["engine"] for r in rows}):
        for warm in (False, True):
            sub = [r for r in rows if r["engine"] == eng and r["warm"] == warm]
            if len(sub) < 20:
                continue
            for r in sub:
                r.setdefault("others", max(0, others(r)))
            for lo, hi, label in buckets:
                line(f"{eng} {'warm' if warm else 'cold'}, {label}", [r["ms"] for r in sub if lo <= r["others"] <= hi])

    print("\n== whole turn, seconds (task.started to task.finished) ==")
    for eng in sorted({r["engine"] for r in rows}):
        for warm in (False, True):
            line(f"{eng}, {'warm' if warm else 'cold'}",
                 [r["turn_s"] for r in rows if r["engine"] == eng and r["warm"] == warm and r["turn_s"] is not None])

    print("\n== what goes to the engine (payload.observed, owner turns: dashboard, telegram, cli) ==")
    own = {t for t, c in channel.items() if c in ("dashboard", "telegram", "cli")}
    sys_chars, est = [], []
    parts = defaultdict(list)
    for task, payload in con.execute(
            "select task_id, payload_json from runtime_events where event_type='payload.observed' and created_at >= ?",
            (since,)):
        if task not in own:
            continue
        try:
            p = json.loads(payload)
        except ValueError:
            continue
        sys_chars.append(p.get("system_chars") or 0)
        est.append(p.get("estimated_input_tokens_raw") or p.get("estimated_input_tokens") or 0)
        for k in ("core_contract_chars", "memory_index_chars", "skill_router_chars", "usage_hint_chars",
                  "capability_summary_chars", "agentic_contract_chars", "channel_contract_chars"):
            parts[k].append(p.get(k) or 0)
    line("system prompt, characters", sys_chars)
    line("estimated input tokens (uncalibrated)", est)
    for k, v in parts.items():
        line(k, v)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
