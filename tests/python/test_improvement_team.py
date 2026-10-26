"""M7 Team trials and recipe transfer: pinned comparable ground (T01), report scope (T02), untested transfer."""
from _paths import ROOT, SERVER  # noqa: F401

import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

import improvement_store as IM
import improvement_team as T

TEAM = {"team_id": "team-1", "brain_id": "/brain", "leader_key": "agent-a", "leader_mode": "limited", "work_mode": "gated"}
MEMBERS = [{"agent_key": "agent-a", "role": "leader"}, {"agent_key": "agent-b", "role": "member"}]


def info(**over):
    base = {"agent-a": {"slug": "a", "agent_hash": "ha", "owner_rules_hash": "ra", "procedure": "", "skills": {"report": "s1"},
                        "provider": "p", "model": "m1", "reasoning": "medium"},
            "agent-b": {"slug": "b", "agent_hash": "hb", "owner_rules_hash": "rb", "procedure": "",
                        "skills": {"report": "s1", "email": "e1"}, "provider": "p", "model": "m2", "reasoning": "high"}}
    for key, values in over.items():
        base[key] = {**base[key], **values}
    return base


def pin(members=MEMBERS, team=TEAM, contract="acc", **over):
    data = info(**over)
    return T.pin_manifest(team, members, lambda key: data.get(key), contract)


PROC_B = {"kind": "procedure", "ref": "agent-b"}


class TeamPinTests(unittest.TestCase):
    def test_procedure_change_may_alter_only_that_member(self):
        base, changed = pin(), pin(**{"agent-b": {"procedure": "iao_1"}})
        self.assertTrue(T.compare(base, changed, PROC_B)["comparable"])
        self.assertEqual(T.compare(base, changed, {"kind": "procedure", "ref": "agent-a"})["reason"], "unexpected_change")
        self.assertEqual(T.compare(base, changed, {"kind": "skill", "ref": "report"})["reason"], "unexpected_change")
        self.assertEqual(T.compare(base, pin(), PROC_B)["reason"], "change_not_observed")

    def test_skill_change_is_comparable_and_distinct_from_procedure(self):
        base = pin()
        changed = pin(**{"agent-a": {"skills": {"report": "s2"}}, "agent-b": {"skills": {"report": "s2", "email": "e1"}}})
        self.assertTrue(T.compare(base, changed, {"kind": "skill", "ref": "report"})["comparable"])
        self.assertEqual(T.compare(base, changed, {"kind": "skill", "ref": "email"})["reason"], "unexpected_change")
        self.assertNotEqual(IM._hash(base), IM._hash(changed))  # two real pins, not one reused id
        granted = pin(**{"agent-a": {"skills": {"report": "s1", "email": "e1"}}})
        self.assertEqual(T.compare(base, granted, {"kind": "skill", "ref": "email"})["reason"], "skill_grant_changed")

    def test_roster_role_leader_mode_model_contract_or_agent_file_is_another_experiment(self):
        base = pin()
        cases = {
            "topology_changed": [pin(members=[MEMBERS[0], {**MEMBERS[1], "role": "reviewer"}]), pin(members=MEMBERS[:1]),
                                 pin(team={**TEAM, "leader_key": "agent-b"}), pin(team={**TEAM, "work_mode": "full"}),
                                 pin(contract="other")],
            "model_changed": [pin(**{"agent-a": {"model": "m9"}}), pin(**{"agent-b": {"provider": "q"}})],
            "agent_changed": [pin(**{"agent-b": {"agent_hash": "hb2", "procedure": "iao_1"}}),
                              pin(**{"agent-b": {"owner_rules_hash": "rb2", "procedure": "iao_1"}})],
        }
        for reason, pins in cases.items():
            for other in pins:
                with self.subTest(reason=reason):
                    self.assertEqual(T.compare(base, other, PROC_B)["reason"], reason)

    def test_missing_member_cannot_be_pinned(self):
        with self.assertRaisesRegex(PermissionError, "team_member_unavailable"):
            T.pin_manifest(TEAM, MEMBERS + [{"agent_key": "gone"}], lambda key: info().get(key), "acc")

    def test_report_is_scoped_and_has_no_production_effect(self):
        ok = T.report({"comparable": True}, PROC_B, {"candidate": "win"})
        self.assertEqual((ok["verdict"], ok["scope"], ok["transfer"], ok["production_effects"], ok["learning_frozen"]),
                         ("win", "team", "untested", [], False))
        self.assertEqual(T.report({"comparable": False, "reason": "model_changed"}, PROC_B, {"candidate": "win"})["verdict"],
                         "incomparable")
        for bad in ({}, {"candidate": "great"}, {"candidate": "win", "combined": "win"}):
            with self.assertRaises(ValueError):
                T.report({"comparable": True}, PROC_B, bad)
        for bad in ({"kind": "procedure", "agent_key": "b"}, {"kind": "rename", "ref": "b"}):
            with self.assertRaises(ValueError):
                T.validate_change(bad)


class TransferTargetTests(unittest.TestCase):
    def test_targets_are_closed(self):
        self.assertEqual(T.target({"kind": "team", "ref": "team-1"}), {"kind": "team", "ref": "team-1"})
        for bad in ({"kind": "brain", "ref": "x"}, {"kind": "agent"}, {"kind": "agent", "ref": "../x\n"}, "agent"):
            with self.assertRaises(ValueError):
                T.target(bad)


class StoreBase(unittest.TestCase):
    def setUp(self):
        import test_improvement_recipe_archive as fixtures
        self.f = fixtures.RecipeArchiveTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.owner, self.assets, self.store = self.f.owner, self.f.assets, self.f.store
        IM.ensure(self.store)


class TeamTrialStoreTests(StoreBase):
    def setUp(self):
        super().setUp()
        self.team = {**TEAM, "brain_id": self.owner.brain_id}
        self.data = info()

        def contract(brain, team_id, task_id):
            if task_id != "task-1":
                raise PermissionError("team_task_unavailable")
            return "criteria-1"
        self.trials = T.TeamTrials(self.assets, read_team=lambda brain, team_id: (self.team, MEMBERS),
                                   member_info=lambda brain, key: self.data.get(key), contract=contract)

    def test_pin_record_and_list_never_touch_team_work(self):
        base = self.trials.pin(self.owner, "team-1", task_id="task-1", event_key="team-pin-base")
        self.assertEqual(base["manifest"]["contract"], "criteria-1")
        self.assertEqual(self.trials.pin(self.owner, "team-1", task_id="task-1", event_key="team-pin-base-2")["pin_id"],
                         base["pin_id"])  # same ground, same pin
        self.data["agent-b"] = {**self.data["agent-b"], "procedure": "iao_" + "1" * 32}
        # A retry of the first key after the ground moved returns the first pin, not a conflict.
        self.assertEqual(self.trials.pin(self.owner, "team-1", task_id="task-1", event_key="team-pin-base"), base)
        cand = self.trials.pin(self.owner, "team-1", task_id="task-1", event_key="team-pin-cand")
        trial = self.trials.record(self.owner, base["pin_id"], cand["pin_id"], PROC_B, {"candidate": "win"},
                                   event_key="team-trial-1")
        self.assertEqual((trial["verdict"], trial["production_effects"], trial["transfer"]), ("win", [], "untested"))
        self.assertEqual(self.trials.record(self.owner, base["pin_id"], cand["pin_id"], PROC_B, {"candidate": "win"},
                                            event_key="team-trial-1"), trial)  # replay
        self.assertEqual(self.trials.trials(self.owner, "team-1")[0]["trial_id"], trial["trial_id"])
        self.data["agent-a"] = {**self.data["agent-a"], "model": "m9"}
        other = self.trials.pin(self.owner, "team-1", task_id="task-1", event_key="team-pin-model")
        incomparable = self.trials.record(self.owner, base["pin_id"], other["pin_id"], PROC_B, {"candidate": "win"},
                                          event_key="team-trial-2")
        self.assertEqual((incomparable["verdict"], incomparable["comparison"]["reason"]), ("incomparable", "model_changed"))
        for bad, reason in (((base["pin_id"], base["pin_id"]), "two_pins"), (({"x": 1}, cand["pin_id"]), "invalid_team_pin")):
            with self.assertRaisesRegex(ValueError, reason):
                self.trials.record(self.owner, *bad, PROC_B, {"candidate": "win"}, event_key="team-trial-bad")

    def test_skill_change_records_two_real_pins(self):
        base = self.trials.pin(self.owner, "team-1", event_key="team-pin-skill-base")
        self.data["agent-a"] = {**self.data["agent-a"], "skills": {"report": "s2"}}
        self.data["agent-b"] = {**self.data["agent-b"], "skills": {"report": "s2", "email": "e1"}}
        cand = self.trials.pin(self.owner, "team-1", event_key="team-pin-skill-cand")
        trial = self.trials.record(self.owner, base["pin_id"], cand["pin_id"], {"kind": "skill", "ref": "report"},
                                   {"candidate": "tie"}, event_key="team-trial-skill")
        self.assertEqual(trial["verdict"], "tie")

    def test_foreign_team_job_or_pins_are_refused(self):
        with self.assertRaisesRegex(PermissionError, "team_task_unavailable"):
            self.trials.pin(self.owner, "team-1", task_id="task-of-other-team", event_key="team-pin-foreign-task")
        self.team = {**self.team, "brain_id": "/other"}
        with self.assertRaisesRegex(PermissionError, "team_unavailable"):
            self.trials.pin(self.owner, "team-1", event_key="team-pin-foreign")
        self.team = {**self.team, "brain_id": self.owner.brain_id}
        one = self.trials.pin(self.owner, "team-1", event_key="team-pin-one")
        self.team = {**self.team, "team_id": "team-2"}
        two = self.trials.pin(self.owner, "team-2", event_key="team-pin-two")
        with self.assertRaisesRegex(ValueError, "different_teams"):
            self.trials.record(self.owner, one["pin_id"], two["pin_id"], PROC_B, {"candidate": "win"}, event_key="team-trial-x")
        with closing(sqlite3.connect(self.store.path)) as connection:
            for statement in ("UPDATE improvement_team_pins SET manifest_json='{}'", "DELETE FROM improvement_team_pins"):
                with self.subTest(statement=statement), self.assertRaises(sqlite3.DatabaseError):
                    connection.execute(statement)

    def test_schema_sixteen_from_fifteen_adds_tables_once(self):
        import improvement_team_schema as S
        with self.store._Tx(self.store) as connection:
            for name in ("improvement_imports", "improvement_refinements",
                         "improvement_transfers", "improvement_team_trials", "improvement_team_pins"):
                connection.execute(f"DROP TABLE {name}")
            self.assertFalse(any(connection.execute("SELECT 1 FROM sqlite_master WHERE name=?", (n,)).fetchone() for n in S._NAMES))
            connection.execute("UPDATE improvement_schema SET version=15 WHERE id=1")
        IM.ensure(self.store)
        self.assertEqual(IM._schema_version(self.store), IM.SCHEMA_VERSION)
        self.assertEqual(len(list(self.store.path.parent.glob(self.store.path.name + ".pre-improvement-m7-team.bak"))), 1)
        with patch.object(self.store, "_backup_before", side_effect=AssertionError("no second backup")):
            IM.ensure(self.store)

    def test_http_routes(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import improvement_activation_api as API
        transfers = T.RecipeTransfers(self.assets)
        app = FastAPI()
        API.register(app, API.ActivationApiDeps(activations=lambda: None, resolve_brain=lambda value: self.owner.brain_id,
                                                team_trials=lambda: self.trials, recipe_transfers=lambda: transfers))
        client = TestClient(app)
        base = client.post("/improvement-team-pins", json={"team_id": "team-1", "task_id": "task-1", "event_key": "http-pin-base"})
        self.assertEqual(base.status_code, 200, base.text)
        self.data["agent-b"] = {**self.data["agent-b"], "procedure": "iao_" + "2" * 32}
        cand = client.post("/improvement-team-pins", json={"team_id": "team-1", "task_id": "task-1",
                                                           "event_key": "http-pin-cand"}).json()
        trial = client.post("/improvement-team-trials", json={
            "baseline_pin_id": base.json()["pin"]["pin_id"], "candidate_pin_id": cand["pin"]["pin_id"],
            "change": PROC_B, "arms": {"candidate": "tie"}, "event_key": "http-trial"})
        self.assertEqual(trial.json()["trial"]["verdict"], "tie")
        self.assertEqual(len(client.get("/improvement-team-trials?team_id=team-1").json()["trials"]), 1)
        bad = client.post("/improvement-team-trials", json={"baseline_pin_id": {"x": 1}, "candidate_pin_id": "y",
            "change": PROC_B, "arms": {"candidate": "win"}, "event_key": "http-trial-bad"})
        self.assertEqual(bad.status_code, 422)
        self.assertEqual(client.get("/improvement-recipe-transfers?kind=team&ref=team-1").json()["transfers"], [])


class RecipeTransferStoreTests(StoreBase):
    def setUp(self):
        super().setUp()
        self.recipe = self.f.capture()["recipe_id"]
        self.transfers = T.RecipeTransfers(self.assets)

    def verdict(self):
        with closing(sqlite3.connect(self.store.path)) as connection:
            return connection.execute("SELECT verdict FROM improvement_recipes WHERE id=?", (self.recipe,)).fetchone()[0]

    def test_transfer_is_untested_and_scoped_to_its_target(self):
        to = {"kind": "team", "ref": "team-1"}
        before = self.verdict()
        made = self.transfers.propose(self.owner, self.recipe, to, event_key="transfer-team-1")
        self.assertEqual(made["evidence"], "untested")
        self.assertEqual(self.transfers.propose(self.owner, self.recipe, to, event_key="transfer-team-1-again")["transfer_id"],
                         made["transfer_id"])
        self.assertEqual([x["transfer_id"] for x in self.transfers.for_target(self.owner, to)], [made["transfer_id"]])
        self.assertEqual(self.transfers.for_target(self.owner, {"kind": "team", "ref": "team-2"}), [])
        self.assertEqual(self.transfers.for_target(self.owner, {"kind": "agent", "ref": "team-1"}), [])
        self.assertEqual(self.verdict(), before)  # the source recipe and its evidence are untouched

    def test_revoked_or_expired_source_disappears_and_cannot_move(self):
        to = {"kind": "agent", "ref": "agent-b"}
        self.transfers.propose(self.owner, self.recipe, to, event_key="transfer-agent-b")
        self.transfers.clock = lambda: 10 ** 12  # past every expiry
        self.assertEqual(self.transfers.for_target(self.owner, to), [])
        with self.assertRaisesRegex(PermissionError, "recipe_unavailable"):
            self.transfers.propose(self.owner, self.recipe, {"kind": "engine", "ref": "openai"}, event_key="transfer-late")
        with self.assertRaisesRegex(PermissionError, "recipe_unavailable"):
            self.transfers.propose(self.owner, "missing-recipe", to, event_key="transfer-missing")


if __name__ == "__main__":
    unittest.main()
