"""Team replay snapshots stay out of usage.json (customer report 2026-11-13: pages lost their connection while a Team
was busy).

    python tests/python/test_usage_team_snapshots.py

Before this, every team model call added one snapshot to usage.json, kept 30 days, and every record() re-read, filtered
and rewrote the whole file on the event loop. The file grew with Team use and each model call froze the server longer.

Self-contained: JAVIS_STATE_DIR points at a temp dir. No network, no model.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import hashlib
import json
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="javis-usage-team-snap-"))
os.environ["JAVIS_STATE_DIR"] = str(_TMP / "state")
(_TMP / "state").mkdir(parents=True, exist_ok=True)

import usage_store as us  # noqa: E402

fails = []
USAGE = _TMP / "state" / "usage.json"


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:300]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def on_disk():
    return json.loads(USAGE.read_text(encoding="utf-8")) if USAGE.exists() else {}


def team_execution(execution_id, turn="tu_1"):
    return {"team_id": "tm_1", "task_id": "t_1", "step_id": "st_1", "turn_id": turn, "attempt": 1, "job_revision": 1,
            "role": "work", "purpose": "work", "execution_id": execution_id}


def bucket(doc, key="deepseek|deepseek-flash"):
    return (doc.get("total") or {}).get(key) or {}


# ===== 1. a team model call counts once and leaves no snapshot in the file =====
ex = team_execution("a" * 32)
for i in range(40):
    us.record("deepseek", "deepseek-flash", 1000, 100, execution=ex, event_id=f"ev-{i}", request_id=f"rq-{i}")
doc = on_disk()
check("40 team calls: 40 turns and their tokens in the totals",
      bucket(doc).get("turns") == 40 and bucket(doc).get("in") == 40_000 and bucket(doc).get("out") == 4_000, bucket(doc))
check("no team snapshot is written to usage.json", not (doc.get("event_snapshots") or {}), doc.get("event_snapshots"))
size_40 = USAGE.stat().st_size

for i in range(40, 400):
    us.record("deepseek", "deepseek-flash", 1000, 100, execution=ex, event_id=f"ev-{i}", request_id=f"rq-{i}")
check("usage.json does not grow with the number of team calls", USAGE.stat().st_size <= size_40 + 64,
      (size_40, USAGE.stat().st_size))

# ===== 2. the same observation recorded again replaces its first figures (no double count) =====
before = bucket(on_disk())
us.record("deepseek", "deepseek-flash", 1000, 100, execution=ex, event_id="ev-7", request_id="rq-7")
check("an identical replay changes nothing", bucket(on_disk()) == before, (before, bucket(on_disk())))
us.record("deepseek", "deepseek-flash", 1500, 250, execution=ex, event_id="ev-7", request_id="rq-7")
after = bucket(on_disk())
check("a corrected replay moves the totals by the difference only, and adds no turn",
      after.get("in") == before["in"] + 500 and after.get("out") == before["out"] + 150
      and after.get("turns") == before["turns"], (before, after))

# ===== 3. another run of the same turn is a new observation =====
us.record("deepseek", "deepseek-flash", 1000, 100, execution=team_execution("b" * 32), event_id="ev-7", request_id="rq-7")
check("the same event id under another execution id counts as a new call",
      bucket(on_disk()).get("turns") == after["turns"] + 1, bucket(on_disk()))

# ===== 4. the snapshots kept in memory are bounded, oldest out first =====
old_cap = us._TEAM_SNAPSHOTS_MAX
us._TEAM_SNAPSHOTS_MAX = 50
try:
    ex2 = team_execution("c" * 32, turn="tu_2")
    for i in range(120):
        us.record("deepseek", "deepseek-flash", 10, 1, execution=ex2, event_id=f"cap-{i}", request_id=f"cap-{i}")
    check("memory holds at most the cap", len(us._TEAM_SNAPSHOTS) == 50, len(us._TEAM_SNAPSHOTS))
    turns = bucket(on_disk()).get("turns")
    us.record("deepseek", "deepseek-flash", 10, 1, execution=ex2, event_id="cap-119", request_id="cap-119")
    check("a recent observation is still recognised as a replay", bucket(on_disk()).get("turns") == turns)
finally:
    us._TEAM_SNAPSHOTS_MAX = old_cap

# ===== 5. a file written by an earlier version: team snapshots go, everything else stays =====
us._TEAM_SNAPSHOTS.clear()
day = us._today()
legacy = {hashlib.sha256(str(i).encode()).hexdigest(): {"day": day, "in": 1200, "out": 300, "cost": 0.0}
          for i in range(5000)}
improvement = {"improvement:" + "f" * 64: {"day": day, "in": 5, "out": 6, "cost": 0.0, "turns": 1, "observations": {}}}
kept_execution = {us._EXECUTION_PREFIX + "e" * 64: {"day": day, "in": 7, "out": 8, "cost": 0.0}}
totals = {"deepseek|deepseek-flash": {"in": 6_000_000, "out": 1_500_000, "turns": 5000, "cost": 1.25}}
USAGE.write_text(json.dumps({"days": {day: dict(totals)}, "total": dict(totals),
                             "event_snapshots": {**legacy, **improvement, **kept_execution}}), encoding="utf-8")
big = USAGE.stat().st_size
check("summary() reads the totals of an old file unchanged",
      us.summary()["all_time"]["total"]["turns"] == 5000 and us.summary()["today"]["total"]["in"] == 6_000_000)
dropped = us.compact()
doc = on_disk()
check("compact() removes exactly the old team snapshots", dropped == 5000, dropped)
check("improvement and execution snapshots are kept",
      set(doc.get("event_snapshots") or {}) == set(improvement) | set(kept_execution), list(doc.get("event_snapshots") or {})[:4])
check("totals and days are untouched by compact()", doc.get("total") == totals and doc.get("days") == {day: totals})
check("the file is small again", USAGE.stat().st_size < big / 50, (big, USAGE.stat().st_size))
check("a second compact() finds nothing to do", us.compact() == 0)

# ===== 6. without compact(), the first record() cleans the old file the same way =====
USAGE.write_text(json.dumps({"days": {day: dict(totals)}, "total": dict(totals), "event_snapshots": dict(legacy)}),
                 encoding="utf-8")
us.record("anthropic-cli", "opus", 900, 200)
doc = on_disk()
check("a plain chat turn rewrites the old file without the team snapshots",
      not (doc.get("event_snapshots") or {}) and USAGE.stat().st_size < big / 50, USAGE.stat().st_size)
check("and still counts itself on top of the old totals",
      bucket(doc, "anthropic-cli|opus").get("turns") == 1 and bucket(doc).get("turns") == 5000, doc.get("total"))

# ===== 7. an execution that is not a team run keeps its snapshot in the file, as before =====
# Never produced by the app today (improvement work records as anthropic-cli and takes its own path); the fall-through
# must keep working because those execution ids are the same after a restart.
trial = {"experiment_id": "exp1", "trial_id": "tr1", "case_id": "c1", "variant": "candidate", "repeat": 1, "attempt": 1,
         "execution_id": "improvement_trial:tr1", "role": "solver", "purpose": "improve_probe", "learning_origin": "trial"}
us.record("deepseek", "deepseek-flash", 300, 30, execution=trial, event_id="trial-ev", request_id="trial-rq")
snaps = on_disk().get("event_snapshots") or {}
check("a non-team execution snapshot is persisted under its own prefix",
      len(snaps) == 1 and next(iter(snaps)).startswith(us._EXECUTION_PREFIX), list(snaps))
turns = bucket(on_disk()).get("turns")
us._TEAM_SNAPSHOTS.clear()   # as after a restart: the file alone must stop the double count
us.record("deepseek", "deepseek-flash", 300, 30, execution=trial, event_id="trial-ev", request_id="trial-rq")
check("its replay after a restart is still not counted twice", bucket(on_disk()).get("turns") == turns)
check("and it survives compact()", us.compact() == 0 and len(on_disk().get("event_snapshots") or {}) == 1)

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    raise SystemExit(1)
print("ALL OK")
