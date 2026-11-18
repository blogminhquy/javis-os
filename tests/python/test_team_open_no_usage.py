"""Opening a team does not add up its model usage any more (owner, 18/11/2026: the team chat showed "Loading the
team's messages..." for a long time).

    python tests/run.py team_open_no_usage -v

The chat draws its messages only once GET /teams/{id} has answered. That route used to add up every model call the team
ever made (`quality_usage`), a cost that grows with the team's age, although the dashboard stopped showing those figures
on 17/11/2026. Now:

1. GET /teams/{id} answers without calling `team_usage.team_usage` and carries no `quality_usage`.
2. GET /teams/{id}/usage still gives the figures, through the shared cache (several readers add a team up once).
3. Nothing in the dashboard reads `quality_usage` from the team record.

Fake usage function, temp state and brain; no network, no model.
"""
from _paths import ROOT, SERVER  # noqa: F401
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-open-")
BRAIN = Path(tempfile.mkdtemp(prefix="javis-team-open-brain-"))
(BRAIN / "agents").mkdir()
for slug in ("lan", "minh"):
    (BRAIN / "agents" / f"{slug}.md").write_text(f"---\nname: {slug}\nrole: Helper\n---\nStay in scope.\n",
                                                encoding="utf-8", newline="\n")

import main  # noqa: E402
import team_api  # noqa: E402
import team_usage  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:300]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


main._TEAM_API.deps.spawn = lambda coro: coro.close() if hasattr(coro, "close") else None
main._TEAM_API.deps.notify = lambda *args: None
client = TestClient(main.app, base_url="http://127.0.0.1:8080")
q = f"?brain={BRAIN}"
made = client.post(f"/teams{q}", json={"name": "Shop", "members": ["lan", "minh"], "leader_slug": "lan"})
check("a team is created", made.status_code == 200, made.text)
tid = made.json()["team"]["team_id"]

calls = []


def counted_usage(team_id):
    calls.append(team_id)
    return {"team_id": team_id, "attempts": len(calls), "cost_behavior": "observe_only"}


team_api._usage_cache.clear()
team_api._usage_flights.clear()
with patch.object(team_usage, "team_usage", counted_usage):
    got = client.get(f"/teams/{tid}{q}")
    check("GET /teams/{id} answers", got.status_code == 200, got.text)
    check("and adds nothing up: the usage function is never called", calls == [], calls)
    check("and carries no usage block", "quality_usage" not in got.json().get("team", {}), list(got.json().get("team", {}))[:40])
    check("the rest of the record is still there (members, queue counts, pinned, typing)",
          got.json()["team"].get("members") and "counts" in got.json()["team"] and "pinned" in got.json()
          and "typing" in got.json(), got.text[:300])
    for _ in range(3):
        client.get(f"/teams/{tid}{q}")
    check("opening it again and again still adds nothing up", calls == [], calls)

    u1 = client.get(f"/teams/{tid}/usage{q}")
    check("GET /teams/{id}/usage gives the figures", u1.status_code == 200 and u1.json()["usage"]["attempts"] == 1, u1.text)
    u2 = client.get(f"/teams/{tid}/usage{q}")
    check("a second read within the cache's time reuses them (added up once)",
          u2.status_code == 200 and u2.json()["usage"]["attempts"] == 1 and calls == [tid], (u2.text, calls))

src = (Path(ROOT) / "server" / "team_api.py").read_text(encoding="utf-8")
check("source: GET /teams/{id} builds its answer without the usage block",
      'view["quality_usage"]' not in src and '"team": api.view(team), "typing": api.teams().active_turns(team_id)' in src)
dash = "".join(p.read_text(encoding="utf-8") for p in (Path(ROOT) / "dashboard").glob("*.js"))
check("dashboard: no page reads quality_usage from the team record", "quality_usage" not in dash)

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    raise SystemExit(1)
print("ALL OK")
