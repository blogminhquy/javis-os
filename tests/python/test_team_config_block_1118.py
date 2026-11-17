"""2026-11-18: a configuration error is one block and one notice, never a loop of failed steps.

Marathon case: 16 Work steps were created for members whose provider cannot run a gated step on this machine; every
press of the retry button made a new step that failed the same way (13 failed steps, 11 attempts, 13 identical chat
posts). Now: a pre-engine config failure blocks the job as kind `config` once; a retry re-runs the preflight on the
CURRENT config and, while still blocked, returns the coded error without creating a step or calling the engine; a plan
that assigns work to a member who cannot run it stops the job before any turn.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import tempfile
import unittest
from pathlib import Path

import engine_capability as EC
import sessions
import task_store
import team_runner as TR
import team_store

TMP = Path(tempfile.mkdtemp(prefix="team-config-block-"))
INFO = {k: {"slug": k, "name": k.upper(), "system": "S"} for k in ("a", "b", "c")}


def run(coro):
    return asyncio.run(coro)


class Fixture:
    def __init__(self, name, config_bad=True):
        d = TMP / name
        d.mkdir(parents=True)
        self.state = {"bad": config_bad}
        self.engine_calls = []
        self.ss = sessions.SessionStore(db_path=d / "s.db")
        self.ts = task_store.TaskStore(d / "k.sqlite3")
        self.tm = team_store.TeamStore(d / "t.sqlite3")

        def engine_for(team, key, role):
            async def run_(req):
                if self.state["bad"]:
                    raise TR.EngineUnavailable("capability gate", code="capability_unsupported", stage="capability")
                await req["engine_started"]()
                self.engine_calls.append((key, role))
                return {"text": f"{key} ok", "tokens_in": 1, "tokens_out": 1}
            run_.marks_engine = True
            return "openai-oauth", "m", run_

        def preflight(team, key, role):
            if self.state["bad"] and role in TR.TOOL_ROLES:
                return {"code": "capability_unsupported", "message": "cannot run gated step", "fix_hint": "use Claude"}
            return None

        self.runner = TR.TeamRunner(teams=self.tm, tasks=self.ts, sessions=self.ss, engine_for=engine_for,
                                    agent_info=lambda b, k: INFO.get(k.replace("ag_", "")), preflight=preflight)
        self.tid = team_store.new_team_id()
        sid = self.ss.create_session(brain="B", channel=f"team:{self.tid}", title=name)
        self.tm.create_team("B", name, "", sid, team_id=self.tid)
        self.tm.set_work_mode(self.tid, "gated")
        for k in ("a", "b", "c"):
            self.tm.add_member(self.tid, f"ag_{k}", k)
        self.tm.set_leader(self.tid, "ag_a")
        self.team = self.tm.get(self.tid)

    def blocked_posts(self):
        msgs = self.ss.get_team_messages_page(self.team["session_id"], limit=200)["messages"]
        return [m for m in msgs if (m.get("meta") or {}).get("kind") == "job_blocked"]


class ConfigBlockTests(unittest.TestCase):
    def test_runtime_config_failure_is_one_step_one_notice_and_retry_rechecks(self):
        f = Fixture("runtime")
        sub = f.runner.submit(f.tid, "Do it", mentions=["ag_a", "ag_b", "ag_c"], as_job=True, client_msg_id="j1")
        job = sub["task_id"]
        run(f.runner.dispatch_once(wait=True))
        task = f.ts.get_task(job)
        steps = f.tm.steps(job)
        self.assertEqual((task["status"], task["block_kind"]), ("team_blocked", "config"), task)
        self.assertEqual(len([s for s in steps if s["status"] == "failed"]), 1, [(s["kind"], s["status"]) for s in steps])
        self.assertEqual(len(f.blocked_posts()), 1)
        self.assertEqual(f.engine_calls, [])

        before = len(f.tm.steps(job))
        for _ in range(3):  # pressing retry while the config is still bad never makes a step or calls an engine
            with self.assertRaises(TR.ConfigBlocked) as ctx:
                f.runner.unblock(job, "retry")
            self.assertEqual(ctx.exception.code, "capability_unsupported")
            self.assertTrue(ctx.exception.fix_hint)
        self.assertEqual(len(f.tm.steps(job)), before)
        self.assertEqual(f.ts.get_task(job)["status"], "team_blocked")
        self.assertEqual(len(f.blocked_posts()), 1)

        f.state["bad"] = False  # the owner fixes the member: the next press runs on the CURRENT config
        self.assertTrue(f.runner.unblock(job, "retry"))
        run(f.runner.dispatch_once(wait=True))
        self.assertTrue(f.engine_calls)
        self.assertNotEqual(f.ts.get_task(job)["block_kind"], "config")

    def test_plan_assigning_work_to_a_blocked_member_stops_before_any_turn(self):
        f = Fixture("plan")
        sub = f.runner.submit(f.tid, "Plan it", as_job=True, client_msg_id="j2")
        job = sub["task_id"]
        task = f.ts.get_task(job)
        team = f.tm.get(f.tid)
        ok = f.runner._add_steps(team, task, [{"kind": "work", "agent": "ag_b", "brief": "x", "inputs": []},
                                              {"kind": "work", "agent": "ag_c", "brief": "y", "inputs": []}])
        self.assertFalse(ok)
        self.assertEqual(f.ts.get_task(job)["block_kind"], "config")
        self.assertEqual(f.engine_calls, [])
        self.assertEqual(len([s for s in f.tm.steps(job) if s["status"] == "failed"]), 0)
        self.assertEqual(len(f.blocked_posts()), 1)
        with self.assertRaises(TR.ConfigBlocked):
            f.runner.unblock(job, "resume")

    def test_non_config_errors_keep_the_old_retry_behaviour(self):
        self.assertNotIn("engine", EC.CONFIG_CODES)
        self.assertIn("capability_unsupported", EC.CONFIG_CODES)
        self.assertNotIn("quota_or_rate_limit", EC.CONFIG_CODES)


if __name__ == "__main__":
    unittest.main()
