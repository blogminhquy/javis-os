"""Team jobs that wait for the owner show up in the owner's own tasks ("Việc của tôi").

A team that needs the owner (an approval request, an acceptance review, a cap reached) used to leave only a card in
the team chat and a bell notification. `sync` keeps one open item in `my-tasks.json` per such job, and ticks it done
when the job no longer waits for the owner (decided, cancelled, edited, expired). It is a reconciler, not an event
hook: every path that blocks or unblocks a job is covered, and a restart loses nothing.

`wanted` is a list of {key, title, notes}; `key` identifies one wait (job + reason). The item carries it as `team_ref`.
Call under the MyTasks `_io` lock.
"""
from __future__ import annotations

import time

OWNER_KINDS = ("waiting_user", "acceptance_review", "cap_reached")
TAG = "nhom"


def sync(mt, brain: str, wanted: list, today: str = "") -> dict:
    data = mt.load(brain)
    tasks = data.get("tasks", [])
    keys = {w["key"] for w in wanted}
    have = {t.get("team_ref"): t for t in tasks if t.get("team_ref")}
    now = time.time()
    created = closed = 0
    for w in wanted:
        if w["key"] in have:      # already there (open, or ticked by the owner: never reopened)
            continue
        res = mt.create(brain, {"title": w["title"], "notes": w["notes"], "date": today or None, "from_javis": True,
                                "tags": [TAG]})
        if not res.get("ok"):
            continue
        data = mt.load(brain)
        for t in data["tasks"]:
            if t.get("id") == res["task"]["id"]:
                t["team_ref"] = w["key"]
        mt.save(brain, data)
        created += 1
    data = mt.load(brain)
    dirty = False
    for t in data["tasks"]:
        ref = t.get("team_ref")
        if ref and ref not in keys and t.get("status") != "done":
            t["status"], t["done_at"], t["done_by"], t["updated_at"] = "done", now, "javis", now
            closed += 1
            dirty = True
    if dirty:
        mt.save(brain, data)
    return {"created": created, "closed": closed}


def wanted_for(tasks: list, team_of) -> dict:
    """{brain_id: [wanted]} from team_blocked jobs; `team_of(team_id)` returns the team dict or None."""
    out: dict = {}
    for t in tasks:
        if t.get("block_kind") not in OWNER_KINDS:
            continue
        team = team_of(t.get("team_id"))
        if not team or team.get("status") == "archived":
            continue
        reason = str(t.get("block_reason") or "")
        out.setdefault(team["brain_id"], []).append({
            "key": f"{t['id']}|{t['block_kind']}|{reason[:80]}",
            "title": f"Nhóm \"{team.get('name') or ''}\" cần anh: {t.get('title') or ''}"[:300],
            "notes": f"{reason}\nMở trang Nhóm, vào nhóm \"{team.get('name') or ''}\" để xử lý. "
                     f"Xử lý xong việc này tự tick."[:5000]})
    return out
