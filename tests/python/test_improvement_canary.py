"""M3 canary: session arms, owner verdicts, two-failure suspension, promotion gate, grants.

A fake clock drives the 7-day window here. That is a technical check of the rule, never a live
canary: real promotion needs real days and real owner verdicts.
"""
from _paths import ROOT, SERVER  # noqa: F401

import sqlite3
import unittest
import unittest.mock
from contextlib import closing

import improvement_canary as CN
import improvement_store as IM
import test_improvement_activation as base
import turn_context

DAY = 86400


class PureCanaryTests(unittest.TestCase):
    def test_bucket_is_stable_and_allocation_bounds_the_arm(self):
        self.assertEqual(CN.bucket("salt", "s1"), CN.bucket("salt", "s1"))
        self.assertEqual(CN.arm(10, "salt", ""), "control")
        sessions = [f"session-{i}" for i in range(2000)]
        share = sum(CN.arm(10, "salt", s) == "canary" for s in sessions) / len(sessions)
        self.assertGreater(share, 0.06)
        self.assertLess(share, 0.14)
        for bad in (0, 100, 10.0, True):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                CN.allocation(bad)

    def test_observation_needs_seven_days_and_ten_canary_verdicts(self):
        verdicts = [{"session_id": f"s{i}", "message_id": 1, "arm": "canary", "verdict": "pass"} for i in range(10)]
        self.assertFalse(CN.observation([], verdicts, started_at=0, now=6.9 * DAY)["sufficient"])
        self.assertFalse(CN.observation([], verdicts[:9], started_at=0, now=30 * DAY)["sufficient"])
        self.assertTrue(CN.observation([], verdicts, started_at=0, now=7 * DAY)["sufficient"])
        control = [{"session_id": f"c{i}", "message_id": 1, "arm": "control", "verdict": "pass"} for i in range(20)]
        self.assertFalse(CN.observation([], control, started_at=0, now=30 * DAY)["sufficient"])

    def test_pilot_conclusion_is_honest(self):
        final = {"mechanical_verdict": "eligible", "complete": True, "pilot": {"numeric_gate": True},
                 "outcomes": {"qualification": {"win": 6, "loss": 0, "tie": 14, "unknown": 0}}, "statistics": {"p_value": 0.015625}}
        self.assertEqual(CN.pilot_conclusion(final, "final")["conclusion"], "improved_in_scope")
        tuning_win = {**final, "outcomes": {"tuning": {"win": 3, "loss": 0, "tie": 3, "unknown": 0}}}
        self.assertEqual(CN.pilot_conclusion(tuning_win, "tuning")["conclusion"], "insufficient_evidence")
        tie = {"mechanical_verdict": "inconclusive", "complete": True, "outcomes": {"tuning": {"win": 0, "loss": 0, "tie": 6, "unknown": 0}}}
        self.assertEqual(CN.pilot_conclusion(tie, "tuning")["conclusion"], "equivalent")
        self.assertEqual(CN.pilot_conclusion({**tie, "mechanical_verdict": "rejected"}, "tuning")["conclusion"], "worse")
        self.assertEqual(CN.wilson(5, 5)[1], 1.0)
        self.assertIsNone(CN.wilson(0, 0))


class CanaryBase(base.ActivationBase):
    def setUp(self):
        super().setUp()
        self.now = [1_000_000.0]
        self.activations.clock = lambda: self.now[0]
        self.canaries = CN.Canaries(self.activations, clock=lambda: self.now[0])

    def start(self, allocation=50, key="canary-start"):
        return self.activations.apply(self.owner, self.candidate["candidate_id"], "ke-toan", event_key=key,
                                      allocation_pct=allocation)

    def salt(self, activation_id):
        with closing(sqlite3.connect(self.store.path)) as connection:
            return connection.execute("SELECT salt FROM improvement_canaries WHERE activation_id=?", (activation_id,)).fetchone()[0]

    def sessions(self, activation, wanted, count=1):
        salt, found = self.salt(activation["activation_id"]), []
        for i in range(10_000):
            session = f"conv-{i}"
            if CN.arm(activation["canary"]["allocation_pct"], salt, session) == wanted:
                found.append(session)
                if len(found) == count:
                    return found
        raise AssertionError("no session in arm")

    def read(self, session, message=1, agent="ke-toan"):
        token = turn_context.bind(turn_context.make("dashboard", la_chu=True, session_id=session, message_id=message,
                                                    agent={"key": base.AGENTS[agent], "slug": agent}))
        try:
            return base.IA.effective_skill_asset(self.root, self.slug).content
        finally:
            turn_context.reset(token)

    def exposures(self):
        with closing(sqlite3.connect(self.store.path)) as connection:
            return connection.execute("SELECT session_id,message_id,arm FROM improvement_canary_exposures "
                                      "ORDER BY session_id,message_id").fetchall()


class CanaryTests(CanaryBase):
    def test_session_arm_is_pinned_and_both_arms_are_recorded_once(self):
        activation = self.start()
        self.assertEqual(activation["canary"]["state"], "canary")
        canary, control = self.sessions(activation, "canary")[0], self.sessions(activation, "control")[0]
        for _ in range(3):
            self.assertEqual(self.read(canary), self.overlay())
            self.assertEqual(self.read(control), self.canonical)
        self.assertEqual(sorted(self.exposures()), sorted([(canary, 1, "canary"), (control, 1, "control")]))
        self.read(canary, message=2)
        self.assertEqual(len(self.exposures()), 3)
        # Other assistants never enter this canary.
        self.assertEqual(self.read(canary, agent="ban-hang"), self.canonical)
        self.assertEqual(len(self.exposures()), 3)

    def verdict(self, activation, session, verdict, message=1, key=None):
        return self.canaries.verdict(self.owner, activation["activation_id"], session, message, verdict,
                                     event_key=key or f"verdict-{session}-{message}-{verdict}")

    def test_verdict_requires_an_exposure_and_is_recorded_once(self):
        activation = self.start()
        session = self.sessions(activation, "canary")[0]
        with self.assertRaises(PermissionError):
            self.verdict(activation, session, "pass")
        self.read(session)
        first = self.verdict(activation, session, "pass")
        self.assertEqual(first["arm"], "canary")
        self.assertEqual(self.verdict(activation, session, "pass"), first)
        with self.assertRaisesRegex(IM.ConflictError, "recorded"):
            self.verdict(activation, session, "fail", key="second-verdict")

    def test_two_failing_canary_sessions_suspend_and_control_failures_do_not(self):
        activation = self.start()
        canary = self.sessions(activation, "canary", 2)
        control = self.sessions(activation, "control", 3)
        for session in control:
            self.read(session)
            self.assertFalse(self.verdict(activation, session, "fail")["suspended"])
        self.read(canary[0])
        self.assertFalse(self.verdict(activation, canary[0], "fail")["suspended"])
        self.read(canary[1])
        self.assertTrue(self.verdict(activation, canary[1], "fail")["suspended"])
        row = self.activations.list(self.owner)[0]
        self.assertEqual((row["state"], row["reason"]), ("suspended", "canary_regression"))
        self.assertEqual(row["canary"]["state"], "ended")
        self.assertEqual(self.read(canary[0], message=9), self.canonical)

    def test_promotion_needs_the_full_window_then_serves_everyone(self):
        activation = self.start()
        canary = self.sessions(activation, "canary", 10)
        control = self.sessions(activation, "control")[0]
        for session in canary:
            self.read(session)
            self.verdict(activation, session, "pass")
        generation = self.canaries.summary(self.owner, activation["activation_id"])["generation"]
        with self.assertRaisesRegex(PermissionError, "insufficient"):
            self.canaries.promote(self.owner, activation["activation_id"], expected_generation=generation,
                                  event_key="promote-early")
        self.now[0] += 7 * DAY
        with self.assertRaisesRegex(IM.ConflictError, "stale"):
            self.canaries.promote(self.owner, activation["activation_id"], expected_generation=generation + 5,
                                  event_key="promote-stale")
        promoted = self.canaries.promote(self.owner, activation["activation_id"], expected_generation=generation,
                                         event_key="promote-after-window")
        self.assertEqual(promoted["state"], "promoted")
        self.assertEqual(self.read(control, message=5), self.overlay())

    def test_promotion_refuses_after_the_owner_edited_the_skill(self):
        activation = self.start()
        for session in self.sessions(activation, "canary", 10):
            self.read(session)
            self.verdict(activation, session, "pass")
        self.now[0] += 8 * DAY
        self.skill.write_bytes(self.canonical + b"\nOwner edit during canary.\n")
        with self.assertRaises(IM.ConflictError):
            self.canaries.promote(self.owner, activation["activation_id"], expected_generation=1, event_key="promote-drift")

    def test_unjudgeable_turns_fail_closed_to_control(self):
        activation = self.start()
        canary = self.sessions(activation, "canary")[0]
        self.assertEqual(self.read(canary, message=0), self.canonical)  # steer follow-ups carry no message id
        self.assertEqual(self.read("", message=3), self.canonical)
        token = turn_context.bind(turn_context.make("dashboard", la_chu=True, session_id=canary, message_id=4,
                                                    agent={"key": base.AGENTS["ke-toan"], "slug": "ke-toan"}))
        try:
            with base.IA.cli_transport():
                self.assertEqual(base.IA.effective_skill_asset(self.root, self.slug).content, self.canonical)
        finally:
            turn_context.reset(token)
        self.assertEqual(self.exposures(), [])

    def test_exposure_rides_the_callers_open_transaction(self):
        import time as clock
        activation = self.start()
        canary = self.sessions(activation, "canary")[0]
        token = turn_context.bind(turn_context.make("dashboard", la_chu=True, session_id=canary, message_id=7,
                                                    agent={"key": base.AGENTS["ke-toan"], "slug": "ke-toan"}))
        try:
            started = clock.monotonic()
            with self.store._Tx(self.store) as connection:
                asset = base.IA.effective_skill_asset(self.root, self.slug, connection=connection)
            self.assertLess(clock.monotonic() - started, 2.0)
        finally:
            turn_context.reset(token)
        self.assertEqual(asset.content, self.overlay())
        self.assertEqual(self.exposures(), [(canary, 7, "canary")])

    def test_lost_exposure_never_serves_the_candidate(self):
        activation = self.start()
        canary = self.sessions(activation, "canary")[0]
        blocker = sqlite3.connect(self.store.path, timeout=5)
        try:
            blocker.execute("BEGIN IMMEDIATE")
            self.assertEqual(self.read(canary, message=8), self.canonical)
        finally:
            blocker.rollback(); blocker.close()
        self.assertEqual(self.exposures(), [])

    def test_verdicts_only_while_the_canary_runs(self):
        activation = self.start()
        session = self.sessions(activation, "canary")[0]
        self.read(session)
        self.activations.revert(self.owner, activation["activation_id"], expected_generation=1, event_key="revert-before-verdict")
        with self.assertRaisesRegex(IM.ConflictError, "not_running"):
            self.verdict(activation, session, "pass")

    def test_promotion_rechecks_the_skill_inside_the_transaction(self):
        activation = self.start()
        for session in self.sessions(activation, "canary", 10):
            self.read(session)
            self.verdict(activation, session, "pass")
        self.now[0] += 8 * DAY
        real, calls = base.SR.read_skill_asset, []

        def drifting(*args, **kwargs):
            asset = real(*args, **kwargs)
            calls.append(1)
            if len(calls) == 1:
                self.skill.write_bytes(self.canonical + b"\nEdited between the read and the transaction.\n")
            return asset
        with unittest.mock.patch.object(base.SR, "read_skill_asset", side_effect=drifting), \
                self.assertRaisesRegex(IM.ConflictError, "basis_changed"):
            self.canaries.promote(self.owner, activation["activation_id"], expected_generation=1, event_key="promote-race")

    def test_grant_opens_nothing_when_the_assistant_identity_changed(self):
        self.canaries.grant(self.owner, self.candidate["target_id"], "ke-toan", 10, event_key="grant-identity")
        with closing(self.store._conn()) as connection:
            candidate = connection.execute("SELECT * FROM improvement_skill_candidates WHERE id=?",
                                           (self.candidate["candidate_id"],)).fetchone()
        self.activations.agent_key = lambda brain, slug: "agent-recreated-2" if slug == "ke-toan" else ""
        opened = self.canaries.open_granted(self.owner, candidate)
        self.assertEqual(opened[0]["skipped"], "auto_scope_identity_changed")
        self.assertEqual(self.activations.list(self.owner), [])

    def test_revert_ends_the_canary(self):
        activation = self.start()
        self.activations.revert(self.owner, activation["activation_id"], expected_generation=1, event_key="revert-canary")
        self.assertEqual(self.canaries.summary(self.owner, activation["activation_id"])["state"], "ended")

    def test_grants_open_canaries_only_for_qualified_candidates(self):
        grant = self.canaries.grant(self.owner, self.candidate["target_id"], "ke-toan", 10, event_key="grant-auto")
        with self.assertRaisesRegex(IM.ConflictError, "exists"):
            self.canaries.grant(self.owner, self.candidate["target_id"], "ke-toan", 20, event_key="grant-again")
        with closing(self.store._conn()) as connection:
            candidate = connection.execute("SELECT * FROM improvement_skill_candidates WHERE id=?",
                                           (self.candidate["candidate_id"],)).fetchone()
        self.assertEqual(self.canaries.auto_apply_for_report(self.owner, "icr_" + "0" * 32), [])
        opened = self.canaries.open_granted(self.owner, candidate)
        self.assertEqual(opened[0]["canary"]["allocation_pct"], 10)
        self.assertEqual(self.canaries.open_granted(self.owner, candidate)[0]["state"], "active")  # same key replays
        self.canaries.revoke_grant(self.owner, grant["grant_id"], expected_generation=1, event_key="revoke-auto")
        self.assertEqual(self.canaries.open_granted(self.owner, candidate), [])
        # The canary the grant opened stays (spec 18.2).
        self.assertEqual(self.activations.list(self.owner)[0]["state"], "active")

    def test_schema_twelve_from_eleven_adds_tables_once(self):
        import improvement_canary_schema as S
        IM.ensure(self.store)
        with self.store._Tx(self.store) as connection:
            for name in ("improvement_imports", "improvement_refinements", "improvement_transfers", "improvement_team_trials", "improvement_team_pins", "improvement_bundle_members", "improvement_bundle_activations", "improvement_agent_overlays", "improvement_agent_procedures", "improvement_routing_overlays", "improvement_routing_candidates"):
                connection.execute(f"DROP TABLE IF EXISTS {name}")
            for name in reversed(S._NAMES):
                kind = "TABLE" if name in ("improvement_canaries", "improvement_canary_exposures", "improvement_canary_verdicts",
                    "improvement_auto_scopes") else "INDEX" if name.endswith("_live") else "TRIGGER"
                connection.execute(f"DROP {kind} IF EXISTS {name}")
            connection.execute("UPDATE improvement_schema SET version=11 WHERE id=1")
        IM.ensure(self.store)
        self.assertEqual(IM._schema_version(self.store), IM.SCHEMA_VERSION)
        backups = list(self.store.path.parent.glob(self.store.path.name + ".pre-improvement-m3-canaries.bak"))
        self.assertEqual(len(backups), 1)
        with closing(sqlite3.connect(backups[0])) as connection:
            self.assertEqual(connection.execute("SELECT version FROM improvement_schema").fetchone()[0], 11)
        with unittest.mock.patch.object(self.store, "_backup_before", side_effect=AssertionError("no second backup")):
            IM.ensure(self.store)


class CanaryApiTests(CanaryBase):
    """Owner routes over the same service; writes need the browser session."""

    def client(self, denied=False):
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        from fastapi.testclient import TestClient
        import improvement_activation_api as API
        app = FastAPI()
        API.register(app, API.ActivationApiDeps(activations=lambda: self.activations,
            resolve_brain=lambda value: self.owner.brain_id, canaries=lambda: self.canaries,
            owner_session=(lambda request: JSONResponse({"ok": False}, status_code=403)) if denied else (lambda request: None)))
        return TestClient(app)

    def test_http_canary_apply_summary_verdict_and_grants(self):
        client = self.client()
        applied = client.post("/improvement-activations", json={"candidate_id": self.candidate["candidate_id"],
            "agent_slug": "ke-toan", "allocation_pct": 50, "event_key": "http-canary-apply"}).json()["activation"]
        self.assertEqual(applied["canary"]["allocation_pct"], 50)
        session = self.sessions(applied, "canary")[0]
        self.read(session)
        summary = client.get(f"/improvement-canaries/{applied['activation_id']}").json()["canary"]
        self.assertEqual(summary["exposures"][0]["session_id"], session)
        self.assertFalse(summary["observation"]["sufficient"])
        verdict = client.post(f"/improvement-canaries/{applied['activation_id']}/verdicts", json={
            "session_id": session, "message_id": 1, "verdict": "pass", "event_key": "http-canary-verdict"})
        self.assertEqual(verdict.json()["verdict"]["arm"], "canary")
        early = client.post(f"/improvement-canaries/{applied['activation_id']}/promote",
                            json={"expected_generation": 1, "event_key": "http-canary-promote"})
        self.assertEqual(early.status_code, 403)
        bad = client.post("/improvement-activations", json={"candidate_id": self.candidate["candidate_id"],
            "agent_slug": "ban-hang", "allocation_pct": 100, "event_key": "http-canary-bad"})
        self.assertEqual(bad.status_code, 422)
        grant = client.post("/improvement-auto-scopes", json={"target_id": self.candidate["target_id"],
            "agent_slug": "ban-hang", "allocation_pct": 10, "event_key": "http-grant"}).json()["grant"]
        self.assertEqual(client.get("/improvement-auto-scopes").json()["grants"][0]["grant_id"], grant["grant_id"])
        revoked = client.post(f"/improvement-auto-scopes/{grant['grant_id']}/revoke",
                              json={"expected_generation": 1, "event_key": "http-grant-revoke"})
        self.assertEqual(revoked.json()["grant"]["status"], "revoked")

    def test_http_canary_writes_need_browser_session(self):
        applied = self.start()
        client = self.client(denied=True)
        self.assertEqual(client.post(f"/improvement-canaries/{applied['activation_id']}/promote",
                                     json={"expected_generation": 1, "event_key": "denied-promote"}).status_code, 403)
        self.assertEqual(client.post("/improvement-auto-scopes", json={"target_id": self.candidate["target_id"],
            "agent_slug": "ke-toan", "allocation_pct": 10, "event_key": "denied-grant"}).status_code, 403)
        self.assertEqual(self.canaries.grants(self.owner), [])


class AfterReportHookTests(unittest.TestCase):
    def test_report_publication_calls_hook_and_survives_its_failure(self):
        import asyncio
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import improvement_experiment_api as API
        from improvement_experiment_service import ExperimentService
        service = object.__new__(ExperimentService)
        service.control = unittest.mock.AsyncMock(return_value={"report_id": "icr_" + "1" * 32, "complete": True})
        seen = []

        def hook(principal, report_id):
            seen.append((principal.brain_id, report_id))
            raise RuntimeError("canary store down")
        app = FastAPI()
        API.register(app, API.ExperimentApiDeps(read_store=lambda: None, resolve_brain=lambda value: "brain-root",
            owner_session=lambda request: None, service=lambda: service, after_report=hook))
        response = TestClient(app).post("/improvement-experiments/exp-1/report",
            json={"comparison_id": "cmp-1", "expected_generation": 1, "event_key": "report-hook-key"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["result"]["report_id"], "icr_" + "1" * 32)
        self.assertEqual(seen, [("brain-root", "icr_" + "1" * 32)])


if __name__ == "__main__":
    unittest.main()
