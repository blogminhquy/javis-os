"""M7 Team trials and recipe transfer: pinned comparable ground (T01), report scope (T02), transfer untested (L02)."""
from _paths import ROOT, SERVER  # noqa: F401

import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

import improvement_store as IM
import improvement_team as T

TEAM = {"team_id": "team-1", "brain_id": "/brain", "leader_key": "agent-a", "leader_mode": "limited"}
MEMBERS = [{"agent_key": "agent-a", "role": "leader"}, {"agent_key": "agent-b", "role": "member"}]


def info(**over):
    base = {"agent-a": {"slug": "a", "system": "prompt a", "model": "m1", "model_provider": "p", "reasoning": "medium"},
            "agent-b": {"slug": "b", "system": "prompt b", "model": "m2", "model_provider": "p", "reasoning": "high"}}
    for key, values in over.items():
        base[key] = {**base[key], **values}
    return base


def pin(members=MEMBERS, team=TEAM, acceptance="acc", **over):
    data = info(**over)
    return T.pin_manifest(team, members, lambda key: data.get(key), acceptance)


class TeamPinTests(unittest.TestCase):
    def test_procedure_change_may_alter_only_that_member(self):
        base = pin()
        changed = pin(**{"agent-b": {"system": "prompt b\nprocedure"}})
        self.assertTrue(T.compare(base, changed, {"kind": "procedure", "agent_key": "agent-b"})["comparable"])
        self.assertEqual(T.compare(base, changed, {"kind": "procedure", "agent_key": "agent-a"})["reason"],
                         "unexpected_prompt_change")
        self.assertEqual(T.compare(base, changed, {"kind": "skill", "agent_key": "agent-b"})["reason"],
                         "unexpected_prompt_change")
        self.assertTrue(T.compare(base, pin(), {"kind": "skill", "agent_key": "agent-b"})["comparable"])

    def test_roster_role_leader_model_or_contract_change_is_another_experiment(self):
        base, change = pin(), {"kind": "procedure", "agent_key": "agent-b"}
        cases = {
            "topology_changed": [pin(members=[MEMBERS[0], {**MEMBERS[1], "role": "reviewer"}]), pin(members=MEMBERS[:1]),
                                 pin(team={**TEAM, "leader_key": "agent-b"}), pin(acceptance="other")],
            "model_changed": [pin(**{"agent-a": {"model": "m9"}}), pin(**{"agent-b": {"reasoning": "low"}})],
        }
        for reason, pins in cases.items():
            for other in pins:
                with self.subTest(reason=reason):
                    self.assertEqual(T.compare(base, other, change)["reason"], reason)
        self.assertEqual(T.compare(base, base, {"kind": "procedure", "agent_key": "agent-z"})["reason"], "change_not_in_team")

    def test_missing_member_cannot_be_pinned(self):
        with self.assertRaisesRegex(PermissionError, "team_member_unavailable"):
            T.pin_manifest(TEAM, MEMBERS + [{"agent_key": "gone"}], lambda key: info().get(key), "acc")

    def test_report_is_scoped_to_this_team_and_has_no_production_effect(self):
        change = {"kind": "procedure", "agent_key": "agent-b"}
        ok = T.report({"comparable": True}, change, {"candidate": "win"})
        self.assertEqual((ok["verdict"], ok["scope"], ok["transfer"], ok["production_effects"]), ("win", "team", "untested", []))
        self.assertEqual(T.report({"comparable": False, "reason": "model_changed"}, change, {"candidate": "win"})["verdict"],
                         "incomparable")
        for bad in ({}, {"candidate": "great"}, {"candidate": "win", "combined": "win"}):
            with self.assertRaises(ValueError):
                T.report({"comparable": True}, change, bad)


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
        self.team_writes = []
        self.trials = T.TeamTrials(self.assets, read_team=lambda brain, team_id: (self.team, MEMBERS),
                                   member_info=lambda brain, key: self.data.get(key),
                                   acceptance=lambda brain, team_id: "acc")

    def test_pin_record_and_list_never_touch_team_work(self):
        base = self.trials.pin(self.owner, "team-1", event_key="team-pin-base")
        self.assertEqual(self.trials.pin(self.owner, "team-1", event_key="team-pin-base-2")["pin_id"], base["pin_id"])  # same ground
        self.data["agent-b"] = {**self.data["agent-b"], "system": "prompt b\nprocedure"}
        cand = self.trials.pin(self.owner, "team-1", event_key="team-pin-cand")
        self.assertNotEqual(base["pin_id"], cand["pin_id"])
        change = {"kind": "procedure", "agent_key": "agent-b"}
        trial = self.trials.record(self.owner, base["pin_id"], cand["pin_id"], change, {"candidate": "win"},
                                   event_key="team-trial-1")
        self.assertEqual((trial["verdict"], trial["production_effects"], trial["transfer"]), ("win", [], "untested"))
        self.assertEqual(self.trials.record(self.owner, base["pin_id"], cand["pin_id"], change, {"candidate": "win"},
                                            event_key="team-trial-1"), trial)  # replay
        self.assertEqual(self.trials.trials(self.owner, "team-1")[0]["trial_id"], trial["trial_id"])
        self.data["agent-a"] = {**self.data["agent-a"], "model": "m9"}
        other = self.trials.pin(self.owner, "team-1", event_key="team-pin-model")
        incomparable = self.trials.record(self.owner, base["pin_id"], other["pin_id"], change, {"candidate": "win"},
                                          event_key="team-trial-2")
        self.assertEqual((incomparable["verdict"], incomparable["comparison"]["reason"]), ("incomparable", "model_changed"))
        with self.assertRaisesRegex(ValueError, "two_pins"):
            self.trials.record(self.owner, base["pin_id"], base["pin_id"], change, {"candidate": "win"}, event_key="team-trial-3")

    def test_team_of_another_brain_and_history_immutability(self):
        self.team = {**self.team, "brain_id": "/other"}
        with self.assertRaisesRegex(PermissionError, "team_unavailable"):
            self.trials.pin(self.owner, "team-1", event_key="team-pin-foreign")
        self.team = {**self.team, "brain_id": self.owner.brain_id}
        self.trials.pin(self.owner, "team-1", event_key="team-pin-ok")
        with closing(sqlite3.connect(self.store.path)) as connection:
            for statement in ("UPDATE improvement_team_pins SET manifest_json='{}'", "DELETE FROM improvement_team_pins"):
                with self.subTest(statement=statement), self.assertRaises(sqlite3.DatabaseError):
                    connection.execute(statement)

    def test_schema_sixteen_from_fifteen_adds_tables_once(self):
        import improvement_team_schema as S
        with self.store._Tx(self.store) as connection:
            for name in ("improvement_transfers", "improvement_team_trials", "improvement_team_pins"):
                connection.execute(f"DROP TABLE {name}")
            self.assertFalse(any(connection.execute("SELECT 1 FROM sqlite_master WHERE name=?", (n,)).fetchone() for n in S._NAMES))
            connection.execute("UPDATE improvement_schema SET version=15 WHERE id=1")
        IM.ensure(self.store)
        self.assertEqual(IM._schema_version(self.store), 16)
        self.assertEqual(len(list(self.store.path.parent.glob(self.store.path.name + ".pre-improvement-m7-team.bak"))), 1)
        with patch.object(self.store, "_backup_before", side_effect=AssertionError("no second backup")):
            IM.ensure(self.store)


class TeamHttpTests(TeamTrialStoreTests):
    def test_http_routes(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import improvement_activation_api as API
        transfers = T.RecipeTransfers(self.assets)
        app = FastAPI()
        API.register(app, API.ActivationApiDeps(activations=lambda: None, resolve_brain=lambda value: self.owner.brain_id,
                                                team_trials=lambda: self.trials, recipe_transfers=lambda: transfers))
        client = TestClient(app)
        base = client.post("/improvement-team-pins", json={"team_id": "team-1", "event_key": "http-pin-base"})
        self.assertEqual(base.status_code, 200, base.text)
        self.data["agent-b"] = {**self.data["agent-b"], "system": "changed"}
        cand = client.post("/improvement-team-pins", json={"team_id": "team-1", "event_key": "http-pin-cand"}).json()
        trial = client.post("/improvement-team-trials", json={
            "baseline_pin_id": base.json()["pin"]["pin_id"], "candidate_pin_id": cand["pin"]["pin_id"],
            "change": {"kind": "procedure", "agent_key": "agent-b"}, "arms": {"candidate": "tie"}, "event_key": "http-trial"})
        self.assertEqual(trial.json()["trial"]["verdict"], "tie")
        self.assertEqual(len(client.get("/improvement-team-trials?team_id=team-1").json()["trials"]), 1)
        bad = client.post("/improvement-team-trials", json={"baseline_pin_id": "x", "candidate_pin_id": "y",
            "change": {"kind": "rename", "agent_key": "a"}, "arms": {"candidate": "win"}, "event_key": "http-trial-bad"})
        self.assertEqual(bad.status_code, 422)
        listed = client.get("/improvement-recipe-transfers?kind=team&ref=team-1").json()
        self.assertEqual(listed["transfers"], [])


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
        self.assertEqual(self.verdict(), before)  # the source recipe and its evidence are untouched (L02)

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
