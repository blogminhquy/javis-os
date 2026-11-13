"""The usage block of a team stays cheap however much the team has worked (customer report 2026-11-13: pages lose their
connection when a Team is used a lot).

    python tests/python/test_team_usage_scale.py

1. `usage_execution._attempts` gives the same selection as the version before it, on random histories (shared CLI
   sessions, ambiguous sessions, request details, repeated request ids), and no longer rescans every event for every
   attempt: that was 59 s for one open of a team of 3,000 turns.
2. `team_api._team_usage_cached`: calls that arrive while a team is being added up do not start the same work again,
   and figures that took long to add up are kept longer.

Self-contained: JAVIS_STATE_DIR points at a temp dir. No network, no model.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import random
import tempfile
import threading
import time
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

_TMP = Path(tempfile.mkdtemp(prefix="javis-team-usage-scale-"))
os.environ["JAVIS_STATE_DIR"] = str(_TMP / "state")
os.environ["JAVIS_NO_REAL_TEAM_ENGINE"] = "1"
(_TMP / "state").mkdir(parents=True, exist_ok=True)

import team_api  # noqa: E402
import team_usage  # noqa: E402
import usage_execution as ue  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:300]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def attempts_before(events, details=()):
    """`usage_execution._attempts` as it was before 2026-11-13, kept here as the reference."""
    groups = defaultdict(list)
    for event in events:
        groups[ue._attempt_key(event)].append(event)
    for key, group in groups.items():
        fallback = [e for e in group if e.get("event_kind") == "cli_fallback"]
        requests = [e for e in group if e.get("event_kind") in ("request", "cli_detail")]
        anchor = (fallback or requests or group)[-1]
        ex = anchor.get("execution") or {}
        sid = ex.get("cli_session_id")
        same_session = {ue._attempt_key(e) for e in events
                        if e.get("execution", {}).get("cli_session_id") == sid}
        ambiguous = bool(sid and (len(same_session) > 1 or any(
            d.get("session_id") == sid and d.get("ambiguous_session") for d in details)))
        raw = [d for d in details if d.get("session_id") == sid] if (
            sid and ex.get("cli_session_new") and not ambiguous) else []
        for detail in raw:
            requests.append({**detail, "event_kind": "cli_detail", "execution": ex,
                "provider": anchor.get("provider"), "raw_observation": True,
                "in": detail["input"] + detail["cache_read"] + detail["cache_create"],
                "out": detail["output"], "tokens_known": True})
        identified, anonymous = {}, []
        for request in requests:
            if request.get("request_id"):
                identity = (request.get("provider"), (request.get("execution") or {}).get("cli_session_id") or sid,
                            request["request_id"])
                prior = identified.get(identity)
                if prior and not request.get("raw_observation") and not prior.get("raw_observation"):
                    request = {**request, "ts": prior.get("ts"), "day": prior.get("day")}
                identified[identity] = request
            else:
                anonymous.append(request)
        yield {"key": key, "group": group, "fallback": fallback,
               "requests": anonymous + list(identified.values()), "raw": raw, "ambiguous_session": ambiguous}


def history(rng, turns):
    """A random team history: API turns (several requests, no CLI session) and CLI turns (one summary, a session that is
    its own, shared with another turn, or flagged ambiguous by the index), with request details for some sessions."""
    events, details = [], []
    for i in range(turns):
        turn = f"tu_{i}"
        ex = {"team_id": "tm_1", "task_id": f"t_{i % 7}", "turn_id": turn, "execution_id": f"ex_{i}", "attempt": 1,
              "role": rng.choice(["work", "plan", "leader_reply"])}
        if rng.random() < 0.5:
            for k in range(rng.randint(1, 6)):
                rid = f"rq_{i}_{rng.randint(0, 3)}" if rng.random() < 0.8 else None     # repeats: a corrected request
                events.append({"provider": "deepseek", "event_kind": "request", "event_id": f"ev_{i}_{k}",
                               "request_id": rid, "execution": dict(ex), "tokens_known": True, "in": 100 + k, "out": 10,
                               "ts": 1000 + i * 10 + k, "day": "2026-11-13"})
            if rng.random() < 0.7:
                events.append({"provider": "deepseek", "event_kind": "execution", "event_id": f"x_{i}",
                               "execution": dict(ex), "tokens_known": False, "expected_requests": rng.randint(0, 6),
                               "status": "completed", "ts": 1000 + i * 10 + 9})
        else:
            shared = rng.random() < 0.15 and i > 0
            sid = f"sess_{i - 1}" if shared else f"sess_{i}"
            ex.update(cli_session_id=sid, cli_session_new=rng.random() < 0.8)
            events.append({"provider": "anthropic-cli", "event_kind": "cli_fallback", "event_id": f"s_{i}",
                           "execution": ex, "tokens_known": rng.random() < 0.9, "in": 900, "out": 90,
                           "status": "completed", "ts": 1000 + i * 10})
            if rng.random() < 0.6:
                for k in range(rng.randint(1, 4)):
                    details.append({"session_id": sid, "request_id": f"cli_{i}_{k}", "input": 300, "output": 30,
                                    "cache_read": 5, "cache_create": 1, "ts": 1000 + i * 10 + k})
            if rng.random() < 0.05:
                details.append({"session_id": sid, "ambiguous_session": True})
    rng.shuffle(details)
    return events, details


# ===== 1. same selection as before, on random histories =====
same, total = 0, 0
for seed in range(60):
    rng = random.Random(seed)
    events, details = history(rng, rng.randint(1, 60))
    total += 1
    if list(ue._attempts(events, details)) == list(attempts_before(events, details)):
        same += 1
    if ue._aggregate(events, details) != ue._aggregate(events, details):   # and it is stable across calls
        same -= 1
check("the attempt selection is the same as before on 60 random team histories", same == total, (same, total))
check("no events: no attempts", list(ue._attempts([], [])) == [] and list(ue._attempts([])) == [])
check("an event whose execution is null does not break the selection",
      len(list(ue._attempts([{"event_kind": "request", "event_id": "a", "execution": None}]))) == 1)
gen = (d for d in [{"session_id": "sess_0", "request_id": "r", "input": 1, "output": 1, "cache_read": 0, "cache_create": 0}])
ev = [{"provider": "anthropic-cli", "event_kind": "cli_fallback", "event_id": "s",
       "execution": {"team_id": "tm", "execution_id": "e", "attempt": 1, "cli_session_id": "sess_0", "cli_session_new": True}}]
check("details given as a one-pass iterator are still all read", len(list(ue._attempts(ev, gen))[0]["raw"]) == 1)

# ===== 2. the work no longer grows with the square of the history =====
rng = random.Random(7)
events, details = history(rng, 1500)
calls = {"n": 0}
real_key = ue._attempt_key


def counting_key(event):
    calls["n"] += 1
    return real_key(event)


with patch.object(ue, "_attempt_key", counting_key):
    n_attempts = len(list(ue._attempts(events, details)))
check("one identity lookup per event, not one per event per attempt", calls["n"] <= 2 * len(events),
      (calls["n"], len(events), n_attempts))

# ===== 3. one call adds a team up at a time; the others reuse its figures =====
computed = []
gate = threading.Event()


def slow_usage(team_id):
    computed.append(team_id)
    gate.wait(5)
    return {"team_id": team_id, "n": len(computed)}


team_api._usage_cache.clear()
team_api._usage_flights.clear()
results = []
with patch.object(team_usage, "team_usage", slow_usage):
    threads = [threading.Thread(target=lambda: results.append(team_api._team_usage_cached("tm_a"))) for _ in range(8)]
    for t in threads:
        t.start()
    time.sleep(0.3)
    started = len(computed)
    gate.set()
    for t in threads:
        t.join(10)
check("8 opens of the same team at once start ONE computation", started == 1 and len(computed) == 1, computed)
check("and all 8 get its figures", len(results) == 8 and all(r == {"team_id": "tm_a", "n": 1} for r in results), results[:3])

# Figures past their time while a refresh is already running: the last ones are returned at once.
with team_api._usage_lock:
    at, val, ttl = team_api._usage_cache["tm_a"]
    team_api._usage_cache["tm_a"] = (at - ttl - 1, val, ttl)
gate.clear()
computed.clear()
with patch.object(team_usage, "team_usage", slow_usage):
    refresher = threading.Thread(target=lambda: team_api._team_usage_cached("tm_a"))
    refresher.start()
    time.sleep(0.2)
    t0 = time.monotonic()
    stale = team_api._team_usage_cached("tm_a")
    waited = time.monotonic() - t0
    gate.set()
    refresher.join(10)
check("a refresh in flight: another call gets the last figures without waiting", waited < 0.15 and stale == val,
      (round(waited, 3), stale))
check("and does not start a second refresh", computed == ["tm_a"], computed)
with patch.object(team_usage, "team_usage", slow_usage):
    fresh = team_api._team_usage_cached("tm_a")
check("after the refresh the new figures are served from the cache", fresh["n"] == 1 and computed == ["tm_a"], fresh)

# A computation that raises must not leave the team locked.
team_api._usage_cache.clear()


def broken_usage(team_id):
    raise RuntimeError("boom")


try:
    with patch.object(team_usage, "team_usage", broken_usage):
        team_api._team_usage_cached("tm_b")
    raised = False
except RuntimeError:
    raised = True
check("an error while adding up leaves no call marked as running", raised and "tm_b" not in team_api._usage_flights,
      dict(team_api._usage_flights))

# ===== 4. figures that took long to add up are kept longer =====
check("a quick team is refreshed every 15 s as before", team_api._usage_ttl(0.02) == team_api._USAGE_TTL_S == 15.0)
check("a team that takes 2 s to add up is refreshed every 40 s", team_api._usage_ttl(2.0) == 40.0, team_api._usage_ttl(2.0))
check("never kept longer than 10 minutes", team_api._usage_ttl(3600.0) == team_api._USAGE_TTL_MAX_S == 600.0)

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    raise SystemExit(1)
print("ALL OK")
