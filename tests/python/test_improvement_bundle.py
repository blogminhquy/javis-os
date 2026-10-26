"""M6 agent-skill bundle: manifest validation (A04) and attribution labels (Q06, Q07)."""
from _paths import ROOT, SERVER  # noqa: F401

import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

import improvement_bundle as B
import improvement_store as IM
import test_improvement_activation as activation_base
import test_improvement_agent_procedures as procedure_base

PROC = "iap_" + "a" * 32


def manifest(**over):
    value = {"agent": "ke-toan", "members": [{"key": "skill", "kind": "skill", "candidate_id": "candidate-one"},
                                             {"key": "procedure", "kind": "procedure", "procedure_id": PROC, "surfaces": ["dm"]}],
             "depends_on": {"procedure": ["skill"]}}
    value.update(over)
    return value


class ManifestTests(unittest.TestCase):
    def test_dependencies_come_first(self):
        clean = B.validate(manifest())
        self.assertEqual(clean["order"], ["skill", "procedure"])
        self.assertEqual(B.validate(manifest(depends_on={}))["order"], ["procedure", "skill"])

    def test_refusals_before_anything_is_written(self):
        skill = {"key": "skill", "kind": "skill", "candidate_id": "candidate-one"}
        proc = {"key": "procedure", "kind": "procedure", "procedure_id": PROC, "surfaces": ["dm"]}
        cases = {
            "bundle_dependency_cycle": manifest(depends_on={"procedure": ["skill"], "skill": ["procedure"]}),
            "bundle_dependency_unknown": manifest(depends_on={"procedure": ["helper"]}),
            "bundle_needs_two_members": manifest(members=[skill]),
            "bundle_member_kind_repeated": manifest(members=[skill, {**skill, "key": "skill2"}]),
            "bundle_surface_not_covered": manifest(members=[skill, {**proc, "surfaces": ["dm", "team"]}]),
            "invalid_bundle_member": manifest(members=[skill, {**proc, "procedure_id": "../x"}]),
            "invalid_bundle_manifest": {**manifest(), "extra": 1},
            "invalid_agent_surfaces": manifest(members=[skill, {**proc, "surfaces": []}]),
        }
        for reason, value in cases.items():
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                B.validate(value)
        with self.assertRaisesRegex(ValueError, "invalid_bundle_member"):
            B.validate(manifest(members=[{**skill, "path": "skills/x"}, proc]))  # no extra fields such as a helper path


class AttributionTests(unittest.TestCase):
    def test_baseline_vs_combined_only_is_confounded(self):
        self.assertEqual(B.attribution({"combined": "win"}),
                         {"bundle": "win", "agent": "confounded", "skill": "confounded", "interaction": "not_measured"})

    def test_combined_never_inherits_single_arm_passes(self):
        self.assertEqual(B.attribution({"agent_only": "win", "skill_only": "win", "combined": "loss"})["interaction"], "conflict")
        self.assertEqual(B.attribution({"agent_only": "tie", "skill_only": "tie", "combined": "win"})["interaction"], "synergy")
        self.assertEqual(B.attribution({"agent_only": "win", "skill_only": "tie", "combined": "win"})["interaction"], "consistent")
        self.assertEqual(B.attribution({"agent_only": "unknown", "skill_only": "win", "combined": "win"})["interaction"], "unknown")
        for bad in ({}, {"combined": "great"}, {"combined": "win", "helper_only": "win"}):
            with self.assertRaises(ValueError):
                B.attribution(bad)


class BundleServiceTests(procedure_base.AgentProcedureBase):
    def setUp(self):
        super().setUp()
        self.bundles = B.Bundles(self.assets, activations=self.activations, procedures=self.service)
        self.procedure = self.stage()

    def manifest(self):
        return {"members": [{"key": "skill", "kind": "skill", "candidate_id": self.candidate["candidate_id"]},
                            {"key": "procedure", "kind": "procedure", "procedure_id": self.procedure["procedure_id"],
                             "surfaces": ["dm"]}], "depends_on": {"procedure": ["skill"]}}

    def apply(self, key="bundle-apply", confirmed=True):
        return self.bundles.apply(self.owner, "ke-toan", self.manifest(), owner_confirmed=confirmed, event_key=key)

    def skill_seen(self):
        return activation_base.ActivationBase.seen(self, "ke-toan")

    def procedure_seen(self, skill_served=True, session_created_at=None):
        import improvement_agent as AG
        agent_text, memory_text = self.files["ke-toan"]
        return AG.effective_procedure(self.root, self.keys["ke-toan"], "dm", agent_text=agent_text, memory_text=memory_text,
                                      skill_served=skill_served, session_created_at=session_created_at)

    def both_canonical(self):
        self.assertEqual(self.skill_seen(), self.canonical)
        self.assertEqual(self.procedure_seen(), "")

    def test_apply_serves_both_members_and_revert_removes_both(self):
        with self.assertRaisesRegex(PermissionError, "confirmation"):
            self.apply(confirmed=False)
        bundle = self.apply()
        self.assertEqual((bundle["state"], bundle["evidence_level"]), ("active", "manual_trial"))
        self.assertEqual(sorted(m["kind"] for m in bundle["members"]), ["procedure", "skill"])
        self.assertEqual(self.apply(), bundle)  # event-key replay
        self.assertEqual(self.skill_seen(), self.overlay())
        self.assertIn(procedure_base.PROCEDURE, self.procedure_seen())
        self.assertEqual(self.skill.read_bytes(), self.canonical)
        with self.assertRaisesRegex(IM.ConflictError, "stale"):
            self.bundles.revert(self.owner, bundle["bundle_id"], expected_generation=1, event_key="bundle-revert-stale")
        reverted = self.bundles.revert(self.owner, bundle["bundle_id"], expected_generation=bundle["generation"],
                                       event_key="bundle-revert")
        self.assertEqual(reverted["state"], "reverted")
        self.both_canonical()
        self.assertEqual(self.service.overlays(self.owner)[0]["state"], "reverted")

    def test_one_member_leaving_takes_the_whole_bundle_down(self):
        bundle = self.apply()
        overlay = next(m["pointer_id"] for m in bundle["members"] if m["kind"] == "procedure")
        self.service.revert(self.owner, overlay, expected_generation=1, event_key="member-revert")
        self.assertEqual(self.skill_seen(), self.canonical)  # read time, before any reconcile
        self.assertEqual(self.bundles.reconcile(self.owner), [{"bundle_id": bundle["bundle_id"], "reason": "member_unavailable"}])
        skill = next(m["pointer_id"] for m in bundle["members"] if m["kind"] == "skill")
        with closing(sqlite3.connect(self.store.path)) as connection:
            self.assertEqual(connection.execute("SELECT state FROM improvement_activations WHERE id=?", (skill,)).fetchone()[0],
                             "reverted")

    def test_skill_drift_hides_the_procedure_and_is_recorded(self):
        bundle = self.apply()
        self.skill.write_bytes(self.canonical + b"\nOwner edit.\n")
        self.assertEqual(self.procedure_seen(), "")
        self.assertEqual(self.bundles.reconcile(self.owner), [{"bundle_id": bundle["bundle_id"], "reason": "member_unavailable"}])
        self.skill.write_bytes(self.canonical)  # restoring the bytes never revives the bundle unasked
        self.both_canonical()

    def test_procedure_only_where_the_skill_half_is_read(self):
        self.apply()
        # Telegram, CLI, or a subscription engine reading native skills: the procedure would come without its skill.
        self.assertEqual(self.procedure_seen(skill_served=False), "")
        # The skill half serves every new turn, so the bundled procedure is not pinned to old sessions either.
        self.assertIn(procedure_base.PROCEDURE, self.procedure_seen(session_created_at=1.0))

    def test_revoked_edit_authority_hides_the_procedure(self):
        bundle = self.apply()
        with closing(sqlite3.connect(self.store.path)) as connection:
            authority = connection.execute("SELECT id FROM improvement_candidate_authorities WHERE candidate_id=?",
                                           (self.candidate["candidate_id"],)).fetchone()[0]
        from improvement_candidate_records import CandidateRecords
        with closing(sqlite3.connect(self.store.path)) as connection:
            generation = connection.execute("SELECT generation FROM improvement_candidate_authority_grants "
                                            "WHERE authority_id=?", (authority,)).fetchone()[0]
        CandidateRecords(self.assets).revoke_authority(self.owner, authority, expected_generation=generation,
                                                       event_key="revoke-authority")
        self.assertEqual(self.skill_seen(), self.canonical)
        self.assertEqual(self.procedure_seen(), "")
        self.assertEqual(self.bundles.reconcile(self.owner)[0]["bundle_id"], bundle["bundle_id"])

    def test_a_finished_bundle_never_strands_member_pointers(self):
        bundle = self.apply()
        members = {m["kind"]: m["pointer_id"] for m in bundle["members"]}
        with patch.object(B.Bundles, "_revert_all", return_value=False):  # members not moved back (crash, error)
            self.bundles.revert(self.owner, bundle["bundle_id"], expected_generation=bundle["generation"], event_key="bundle-revert-strand")
        self.assertEqual(self.bundles.member_of(self.owner, "skill", members["skill"]), "")  # per-kind revert open again
        self.both_canonical()  # never served without its bundle
        self.bundles.reconcile(self.owner)  # the sweep moves the leftovers back
        self.assertEqual(self.activations.list(self.owner)[0]["state"], "reverted")
        self.assertEqual(self.service.overlays(self.owner)[0]["state"], "reverted")

    def test_reconcile_and_a_live_apply_never_both_act(self):
        original, steps = B.Bundles._apply_member, []

        def slow(self_, principal, bundle_id, agent_slug, clean, member_key):
            original(self_, principal, bundle_id, agent_slug, clean, member_key)
            if member_key == "skill":
                self_.clock = lambda: 10 ** 10  # the apply takes "forever": a reconcile takes over meanwhile
                steps.append(self.bundles.reconcile(self.owner))
        self.bundles.clock = __import__("time").time
        with patch.object(B.Bundles, "_apply_member", slow), self.assertRaisesRegex(IM.ConflictError, "interrupted"):
            self.apply()
        self.assertEqual(steps[0][0]["reason"], "interrupted")
        self.assertEqual(self.bundles.list(self.owner)[0]["state"], "failed")
        self.both_canonical()
        self.assertTrue(all(row["state"] != "active" for row in self.activations.list(self.owner)))
        self.assertTrue(all(row["state"] != "active" for row in self.service.overlays(self.owner)))

    def test_member_failure_rolls_back_and_nothing_half_new_is_served(self):
        other = self.stage(procedure_base.PROCEDURE + " Them buoc.", key="stage-standalone")
        self.service.apply(self.owner, other["procedure_id"], ["team"], owner_confirmed=True, event_key="standalone")
        with self.assertRaisesRegex(IM.ConflictError, "agent_overlay_busy"):
            self.apply()
        row = self.bundles.list(self.owner)[0]
        self.assertEqual((row["state"], row["reason"]), ("failed", "member_apply_failed"))
        self.assertEqual(self.skill_seen(), self.canonical)
        self.assertEqual(self.activations.list(self.owner)[0]["state"], "reverted")

    def test_interrupted_apply_stays_canonical_then_recovers(self):
        original = B.Bundles._apply_member

        def crash(self_, principal, bundle_id, agent_slug, clean, member_key):
            original(self_, principal, bundle_id, agent_slug, clean, member_key)
            if member_key == "skill":
                raise SystemExit("process died")
        with patch.object(B.Bundles, "_apply_member", crash), self.assertRaises(SystemExit):
            self.apply()
        self.assertEqual(self.bundles.list(self.owner)[0]["state"], "applying")
        self.assertEqual(self.activations.list(self.owner)[0]["state"], "active")
        self.assertEqual(self.skill_seen(), self.canonical)  # the gate hides the half-applied bundle
        self.assertEqual(self.bundles.reconcile(self.owner), [])  # too recent: maybe still running
        self.bundles.clock = lambda: 10 ** 10
        self.assertEqual(self.bundles.reconcile(self.owner)[0]["reason"], "interrupted")
        self.assertEqual(self.bundles.list(self.owner)[0]["state"], "failed")
        self.assertEqual(self.activations.list(self.owner)[0]["state"], "reverted")

    def test_one_bundle_in_flight_per_assistant(self):
        self.apply()
        with self.assertRaisesRegex(IM.ConflictError, "bundle_busy"):
            self.bundles.apply(self.owner, "ke-toan", self.manifest(), owner_confirmed=True, event_key="bundle-apply-2")

    def test_a_procedure_of_another_assistant_is_refused(self):
        foreign = self.stage(agent="ban-hang", key="stage-foreign")
        value = self.manifest()
        value["members"][1]["procedure_id"] = foreign["procedure_id"]
        with self.assertRaisesRegex(PermissionError, "bundle_member_unavailable"):
            self.bundles.apply(self.owner, "ke-toan", value, owner_confirmed=True, event_key="bundle-foreign")

    def test_schema_fifteen_from_fourteen_adds_tables_once(self):
        import improvement_bundle_schema as S
        IM.ensure(self.store)
        with self.store._Tx(self.store) as connection:
            for name in ("improvement_imports", "improvement_refinements", "improvement_transfers", "improvement_team_trials", "improvement_team_pins",
                         "improvement_bundle_members", "improvement_bundle_activations"):
                connection.execute(f"DROP TABLE {name}")
            self.assertFalse(any(connection.execute("SELECT 1 FROM sqlite_master WHERE name=?", (n,)).fetchone() for n in S._NAMES))
            connection.execute("UPDATE improvement_schema SET version=14 WHERE id=1")
        IM.ensure(self.store)
        self.assertEqual(IM._schema_version(self.store), IM.SCHEMA_VERSION)
        backups = list(self.store.path.parent.glob(self.store.path.name + ".pre-improvement-m6-bundles.bak"))
        self.assertEqual(len(backups), 1)
        with patch.object(self.store, "_backup_before", side_effect=AssertionError("no second backup")):
            IM.ensure(self.store)

    def test_http_routes_and_member_revert_refusal(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import improvement_activation_api as API
        app = FastAPI()
        API.register(app, API.ActivationApiDeps(activations=lambda: self.activations,
            resolve_brain=lambda value: self.owner.brain_id, agents=lambda: self.service, bundles=lambda: self.bundles))
        client = TestClient(app)
        applied = client.post("/improvement-agent-bundles", json={"agent": "ke-toan", "manifest": self.manifest(),
                                                            "owner_confirmed": True, "event_key": "http-bundle-apply"})
        self.assertEqual(applied.status_code, 200, applied.text)
        bundle = applied.json()["bundle"]
        members = {m["kind"]: m["pointer_id"] for m in bundle["members"]}
        refused = client.post(f"/improvement-activations/{members['skill']}/revert",
                              json={"expected_generation": 1, "event_key": "http-member-revert"})
        self.assertEqual((refused.status_code, refused.json()["reason"]), (409, "bundle_member_revert_with_bundle"))
        refused = client.post(f"/improvement-agent-overlays/{members['procedure']}/revert",
                              json={"expected_generation": 1, "event_key": "http-member-revert-2"})
        self.assertEqual(refused.status_code, 409)
        listed = client.get("/improvement-agent-bundles?agent=ke-toan").json()
        self.assertEqual(listed["bundles"][0]["bundle_id"], bundle["bundle_id"])
        reverted = client.post(f"/improvement-agent-bundles/{bundle['bundle_id']}/revert",
                               json={"expected_generation": bundle["generation"], "event_key": "http-bundle-revert"}).json()
        self.assertEqual(reverted["bundle"]["state"], "reverted")
        bad = client.post("/improvement-agent-bundles", json={"agent": "ke-toan", "manifest": {"members": []},
                                                        "owner_confirmed": True, "event_key": "http-bundle-bad"})
        self.assertEqual(bad.status_code, 422)


if __name__ == "__main__":
    unittest.main()
