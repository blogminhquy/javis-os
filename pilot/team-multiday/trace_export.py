"""Read-only export of the Team trace for the multi-day pilot (0.210.0).

    python pilot/team-multiday/trace_export.py <STATE_DIR> [--team <team_id>] [--out trace.jsonl]

One JSON line per link, in time order, for every job of the pilot teams:

    mandate_version -> observation -> opportunity -> decision -> approval(s) -> job -> steps -> acceptance

It opens team.sqlite3 and kanban.sqlite3 read-only (`mode=ro`), changes nothing, and calls no model. Tables that an
older build never created are skipped, so the script also works on a state from before 0.207.0 (it then reports only
jobs and steps). The pilot report's numbers come from this file, never from memory or from agents' messages.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def _ro(path: Path) -> sqlite3.Connection | None:
    if not path.is_file():
        return None
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    c.row_factory = sqlite3.Row
    return c


def _has(c: sqlite3.Connection, table: str) -> bool:
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _rows(c, sql, args=()):
    return [dict(r) for r in c.execute(sql, args).fetchall()]


def export(state_dir: Path, team_id: str = "") -> list:
    state_dir = Path(state_dir)
    tc = _ro(state_dir / "team.sqlite3")
    kc = _ro(state_dir / "kanban.sqlite3")
    if tc is None:
        raise SystemExit(f"không có {state_dir / 'team.sqlite3'}")
    out = []
    teams = _rows(tc, "SELECT team_id, name, brain_id FROM teams" + (" WHERE team_id=?" if team_id else ""),
                  (team_id,) if team_id else ())
    for t in teams:
        tid = t["team_id"]
        out.append({"link": "team", "team_id": tid, "name": t["name"]})
        if _has(tc, "team_mandate_versions"):
            for v in _rows(tc, "SELECT version, snapshot_json, by, at FROM team_mandate_versions WHERE team_id=? "
                               "ORDER BY version", (tid,)):
                out.append({"link": "mandate_version", "team_id": tid, "at": v["at"], "version": v["version"],
                            "by": v["by"], "mandate": json.loads(v["snapshot_json"])})
        opp_by_task = {}
        if _has(tc, "mandate_opportunities"):
            for o in _rows(tc, "SELECT * FROM mandate_opportunities WHERE team_id=? ORDER BY created_at", (tid,)):
                if o.get("observation_id") and _has(tc, "mandate_observations"):
                    ob = tc.execute("SELECT id, source, ref, version_key, ok, observed_at FROM mandate_observations "
                                    "WHERE id=?", (o["observation_id"],)).fetchone()
                    if ob:
                        out.append({"link": "observation", "team_id": tid, "at": ob["observed_at"], **dict(ob)})
                out.append({"link": "opportunity", "team_id": tid, "at": o["created_at"], "opp_id": o["opp_id"],
                            "mandate_version": o["mandate_version"], "source": o["source"], "ref": o["ref"],
                            "version_key": o["version_key"], "kind": o["kind"], "reason": o["reason"],
                            "benefit": o["benefit"], "evidence": json.loads(o["evidence_json"] or "[]")})
                out.append({"link": "decision", "team_id": tid, "at": o["updated_at"], "opp_id": o["opp_id"],
                            "decision": o["decision"], "status": o["status"], "by": o["decided_by"],
                            "task_id": o["task_id"]})
                if o.get("task_id"):
                    opp_by_task[o["task_id"]] = o["opp_id"]
        jobs = []
        if kc is not None:
            jobs = _rows(kc, "SELECT id, title, status, block_kind, team_rev, source_ref, created_at, updated_at, result "
                             "FROM tasks WHERE lane='team' AND team_id=? ORDER BY created_at", (tid,))
        for j in jobs:
            if _has(tc, "team_approvals"):
                for a in _rows(tc, "SELECT * FROM team_approvals WHERE task_id=? ORDER BY created_at", (j["id"],)):
                    out.append({"link": "approval", "team_id": tid, "at": a["created_at"], "task_id": j["id"],
                                "approval_id": a["approval_id"], "kind": a["kind"], "title": a["title"],
                                "requested_by": a["requested_by"], "status": a["status"], "decided_by": a["decided_by"],
                                "decided_at": a["decided_at"], "consumed_at": a["consumed_at"],
                                "calls": [f.get("call") or f.get("label")
                                          for f in json.loads(a["fingerprints_json"] or "[]")]})
            out.append({"link": "job", "team_id": tid, "at": j["created_at"], "task_id": j["id"], "title": j["title"],
                        "status": j["status"], "block_kind": j["block_kind"], "revision": j["team_rev"],
                        "source_ref": j["source_ref"], "opp_id": opp_by_task.get(j["id"]),
                        "result_chars": len(j["result"] or "")})
            for s in _rows(tc, "SELECT step_id, seq, kind, agent_key, status, note, job_revision, updated_at FROM "
                               "team_steps WHERE task_id=? ORDER BY seq", (j["id"],)):
                out.append({"link": "step", "team_id": tid, "at": s["updated_at"], "task_id": j["id"], **s})
            if _has(tc, "team_acceptance"):
                acc = tc.execute("SELECT * FROM team_acceptance WHERE task_id=?", (j["id"],)).fetchone()
                if acc:
                    checks = _rows(tc, "SELECT revision, round, idx, kind, verdict, evidence_json, at FROM "
                                       "team_acceptance_checks WHERE task_id=? ORDER BY id", (j["id"],))
                    out.append({"link": "acceptance", "team_id": tid, "at": acc["updated_at"], "task_id": j["id"],
                                "status": acc["status"], "rounds_used": acc["rounds_used"],
                                "confirmed_by": acc["confirmed_by"],
                                "checks": [dict(c, evidence=json.loads(c.pop("evidence_json") or "{}")) for c in checks]})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("state_dir")
    ap.add_argument("--team", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    lines = export(Path(a.state_dir), a.team)
    text = "\n".join(json.dumps(x, ensure_ascii=False, default=str) for x in lines) + "\n"
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"đã ghi {len(lines)} dòng vào {a.out}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
