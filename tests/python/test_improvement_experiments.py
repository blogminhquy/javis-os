"""Current schema preserves released A authoring and actual M1 trial/ledger history."""
from _paths import ROOT, SERVER  # noqa: F401

import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
import threading
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from unittest.mock import patch

import improvement_store as IM
import improvement_case_schema as CASES
import improvement_trial_schema as TRIALS
import improvement_candidate_schema as CANDIDATES
from improvement_candidate_records import CandidateRecords
from improvement_skill_candidates import SkillCandidates
import test_improvement_trial_admission as fixtures

RELEASED_A = "cbef2f464932e533825512e8e11c2299e6b3bf4f"
if importlib.util.find_spec("improvement_experiments"):
    from improvement_experiments import ExperimentRecords
    import improvement_experiment_schema as EXPERIMENTS
else:
    ExperimentRecords = EXPERIMENTS = None


def schema4_ensure(store):
    """Install the four actual released blocks, never downgrade a newer database."""
    with store._Tx(store) as connection:
        if connection.execute("SELECT 1 FROM sqlite_master WHERE name='improvement_schema'").fetchone():
            return
        blocks = ((IM._SCHEMA, ("improvement_revisions", "improvement_bundles", "improvement_bundle_assets", "improvement_events")),
                  (CASES.SCHEMA, CASES.IMMUTABLE), (TRIALS.SCHEMA, TRIALS.IMMUTABLE),
                  (CANDIDATES.SCHEMA, CANDIDATES.IMMUTABLE))
        for statements, immutable in blocks:
            for statement in statements:
                connection.execute(statement)
            IM._immutable_triggers(connection, immutable)
        connection.execute("INSERT INTO improvement_schema VALUES(1,4)")


class ExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The same pinned historical-source fetch pattern is used by existing rollback tests.
        result = subprocess.run(["git", "show", RELEASED_A + ":server/improvement_store.py"],
                                cwd=ROOT, capture_output=True, check=True)
        module = types.ModuleType("_released_improvement_schema4")
        sys.modules[module.__name__] = module
        exec(compile(result.stdout, "released-schema4/improvement_store.py", "exec"), module.__dict__)
        cls.old_reader = module

    def setUp(self):
        with patch.object(IM, "ensure", side_effect=schema4_ensure):
            self.h = fixtures.AdmissionTests()
            self.h.setUp()
            self.addCleanup(self.h.doCleanups)
            self.f = self.h.f.f
            self.assets, self.store, self.owner = self.f.assets, self.f.database, self.f.owner
            # Synthetic availability only; actual reservation, request, call and holdout claim.
            self.admitted = self.h.admit()
            raw = self.f.skill.read_bytes()
            start = raw.index(b"Retain owner rules.")
            authoring = SkillCandidates(self.assets, pack_state_dir=self.f.root / "packs")
            authoring.declare_region(self.owner, "association-experiment", self.f.target["revision_id"], start, len(raw),
                                    expected_target_generation=1, event_key="legacy-a-edit-region")
            self.candidate = authoring.stage(self.owner, "association-experiment", {
                "version": 1, "target_id": self.f.target["target_id"], "base_revision_id": self.f.target["revision_id"],
                "before_hash": hashlib.sha256(raw).hexdigest(), "operation": "replace_body_region", "start": start,
                "end": len(raw), "replacement": "Retain owner rules.\nCheck every subtotal.\n",
                "hypothesis": "Count all authorized rows.", "failure_signature": "Omitted row.",
                "expected_behavior": "Each row counted once.", "possible_regressions": ["Duplicate row."],
                "evidence_refs": [], "angle": "execution"}, event_key="legacy-a-stage")
        self.before = self.history()

    def history(self):
        with closing(self.store._conn()) as connection:
            tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' "
                "AND (name LIKE 'improvement_%' OR name='agent_calls') ORDER BY name") if row[0] != "improvement_schema"]
            return {table: [tuple(row) for row in connection.execute('SELECT * FROM "' + table + '" ORDER BY rowid')]
                    for table in tables}

    def records(self):
        self.assertIsNotNone(ExperimentRecords, "Durable owner experiment records are absent")
        return ExperimentRecords(self.assets)

    def definition(self):
        request, pins = self.admitted.request, self.admitted.request["pins"]
        with closing(self.store._conn()) as connection:
            context = connection.execute("SELECT * FROM improvement_trial_contexts WHERE id=?",
                                         (self.h.f.binding["context_id"],)).fetchone()
        return {"version": 1, "experiment_id": "association-experiment", "context_id": context["id"],
            "target_id": self.f.target["target_id"], "base_revision_id": self.f.target["revision_id"],
            "base_hash": self.candidate["base_hash"], "base_generation": 1,
            "base_bundle_id": self.h.public["base_bundle_id"], "base_bundle_hash": pins["base_bundle_hash"],
            "contract_id": self.h.public["contract_id"], "contract_hash": pins["contract_hash"],
            "case_set_id": request["case_set_id"], "case_set_hash": pins["case_set_hash"],
            "baseline_context_hash": request["baseline_context_hash"], "binding_hash": context["binding_hash"],
            **{key: pins[key] for key in ("engine_config_hash", "grant_hash", "scope_hash", "policy_version")},
            "context_generation": 1, "repeat_policy": {"kind": "feasibility", "repeats": 1}, "timeout_seconds": 120,
            "endpoint": {"kind": "binary_all_pass", "criterion_id": "content", "direction": "higher"},
            "decision_policy": {"id": "paired-skill-v1", "version": 1, "multiple_tests": 1},
            "evaluator": self.h.f.contract["evaluator"], "evidence_class": "technical"}

    def create(self, key="owner-experiment-create", **changes):
        records = self.records()
        self.assertTrue(callable(getattr(records, "create", None)), "Durable experiment creation is absent")
        return records.create(self.owner, {**self.definition(), **changes}, expected_context_generation=1, event_key=key)

    def test_schema4_cold_experiment_metadata_never_migrates_or_decrypts(self):
        records = self.records()
        with patch.object(self.assets.blobs, "read", side_effect=AssertionError("Cold reads cannot decrypt")):
            self.assertEqual(records.list(self.owner), {"items": [], "next_cursor": None})
            with self.assertRaises(PermissionError):
                records.get(self.owner, "association-experiment")
        self.assertEqual(IM._schema_version(self.store), 4)
        self.assertEqual(self.history(), self.before)

    def test_current_upgrade_preserves_actual_a_and_m1_history(self):
        IM.ensure(self.store)
        self.assertEqual(IM._schema_version(self.store), IM.SCHEMA_VERSION, "Current migration must retain experiment history")
        self.assertEqual({name: self.history()[name] for name in self.before}, self.before)
        self.assertEqual(CandidateRecords(self.assets).get(self.owner, self.candidate["candidate_id"]), self.candidate)
        self.assertEqual(self.h.admission.trials.get(self.owner, self.admitted.trial_id)["request"], self.admitted.request)
        backup = self.store.path.with_name(self.store.path.name + ".pre-improvement-m2-experiments.bak")
        self.assertTrue(backup.is_file())
        with closing(sqlite3.connect(backup)) as connection:
            self.assertEqual(connection.execute("SELECT version FROM improvement_schema").fetchone()[0], 4)
            self.assertEqual(connection.execute("SELECT id FROM improvement_skill_candidates").fetchone()[0], self.candidate["candidate_id"])
        digest = hashlib.sha256(backup.read_bytes()).hexdigest()
        IM.ensure(self.store)
        self.assertEqual(hashlib.sha256(backup.read_bytes()).hexdigest(), digest)

    def test_concurrent_upgrade_serializes_one_complete_backup(self):
        gate, backups = threading.Barrier(2), []
        original = self.store._backup_before

        def backup(*args):
            backups.append(args)
            return original(*args)

        def migrate(_):
            gate.wait()
            IM.ensure(self.store)

        with patch.object(self.store, "_backup_before", side_effect=backup), ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(migrate, (1, 2)))
        self.assertEqual(backups, [("improvement_compositions", ".pre-improvement-m2-compose.bak"),
                                  ("improvement_experiments", ".pre-improvement-m2-experiments.bak"),
                                  ("improvement_preparations", ".pre-improvement-m2-generated.bak"),
                                  ("improvement_effective_views", ".pre-improvement-m2-views.bak")])
        self.assertEqual(IM._schema_version(self.store), IM.SCHEMA_VERSION)
        self.assertEqual({name: self.history()[name] for name in self.before}, self.before)

    def test_failed_migration_rolls_back_all_new_tables_and_triggers(self):
        self.assertIsNotNone(EXPERIMENTS, "Experiment migration is absent")
        with patch.object(EXPERIMENTS, "SCHEMA", (*EXPERIMENTS.SCHEMA, "INVALID EXPERIMENT MIGRATION")):
            with self.assertRaises(sqlite3.OperationalError):
                IM.ensure(self.store)
        self.assertEqual(IM._schema_version(self.store), 4)
        self.assertEqual(self.history(), self.before)
        IM.ensure(self.store)
        self.assertEqual(IM._schema_version(self.store), IM.SCHEMA_VERSION)

    def test_actual_released_a_reader_rejects_current_schema_before_any_write(self):
        IM.ensure(self.store)
        self.assertEqual(IM._schema_version(self.store), IM.SCHEMA_VERSION)
        before = self.history()
        with patch.object(self.store, "_backup_before", side_effect=AssertionError("Old reader cannot back up or migrate")):
            with self.assertRaises(self.old_reader.SchemaError):
                self.old_reader.read_existing(self.store.path, self.assets.blobs)
            with self.assertRaises(self.old_reader.SchemaError):
                self.old_reader.ensure(self.store)
        self.assertEqual(self.history(), before)
        self.assertEqual(IM._schema_version(self.store), IM.SCHEMA_VERSION)

    def test_unknown_future_schema_rejects_without_backup_or_mutation(self):
        with self.store._Tx(self.store) as connection:
            connection.execute("UPDATE improvement_schema SET version=999")
        with patch.object(self.store, "_backup_before", side_effect=AssertionError("Unknown schema must remain untouched")):
            with self.assertRaises(IM.SchemaError):
                IM.ensure(self.store)
        self.assertEqual(self.history(), self.before)

    def test_creation_is_atomic_exact_replay_and_metadata_is_cold(self):
        result = self.create()
        self.assertEqual((result["phase"], result["generation"], result["authority_status"]), ("proposed", 1, "not_checked"))
        self.assertEqual(self.create(), result)
        self.assertNotIn(str(self.f.brain), json.dumps(result))
        before = self.history()
        with patch.object(self.assets.blobs, "read", side_effect=AssertionError("Metadata cannot decrypt")):
            self.assertEqual(self.records().get(self.owner, result["experiment_id"]), result)
            self.assertEqual(self.records().list(self.owner)["items"], [result])
        self.assertEqual(self.history(), before)
        with self.assertRaises(IM.ConflictError):
            self.create(timeout_seconds=119)

    def test_unrelated_case_set_and_foreign_owner_cannot_create(self):
        records = self.records()
        self.assertTrue(callable(getattr(records, "create", None)), "Durable experiment creation is absent")
        definition = self.definition()
        for changes in ({"case_set_id": "another-case-set"}, {"context_id": self.f.binding["context_id"]},
                        {"grant_hash": "f" * 64}, {"contract_hash": "f" * 64}):
            with self.subTest(changes=changes), self.assertRaises((PermissionError, IM.ConflictError)):
                records.create(self.owner, {**definition, **changes}, expected_context_generation=1,
                               event_key="invalid-experiment-create")
        with self.assertRaises(PermissionError):
            records.create(self.f.other, definition, expected_context_generation=1, event_key="foreign-experiment-create")
        self.assertEqual(records.list(self.owner)["items"], [])

    def test_block_resume_and_stop_retain_generation_and_historical_replay(self):
        row, records = self.create(), self.records()
        blocker = {"code": "runtime_unavailable", "fingerprint": "a" * 64}
        blocked = records.block(self.owner, row["experiment_id"], blocker,
                                expected_generation=1, event_key="block-experiment-runtime")
        self.assertEqual((blocked["phase"], blocked["generation"], blocked["resume_from"]), ("blocked", 2, "proposed"))
        with self.assertRaises(IM.ConflictError):
            records.resume(self.owner, row["experiment_id"], observed_fingerprint="a" * 64,
                           expected_generation=2, event_key="resume-unchanged-runtime")
        resumed = records.resume(self.owner, row["experiment_id"], observed_fingerprint="b" * 64,
                                 expected_generation=2, event_key="resume-new-runtime")
        self.assertEqual((resumed["phase"], resumed["generation"]), ("proposed", 3))
        ticket = records.begin_stop(self.owner, row["experiment_id"], kind="cancelled", reason="owner_requested",
                                    expected_generation=3, event_key="stop-owner-experiment")
        self.assertEqual((ticket["phase"], ticket["generation"], ticket["stop_kind"]), ("stopping", 4, "cancelled"))
        self.assertEqual(self.create(), row)  # Historical create never resets current state.
        self.assertEqual(records.get(self.owner, row["experiment_id"])["phase"], "stopping")
        with self.assertRaises(IM.ConflictError):
            records.resume(self.owner, row["experiment_id"], observed_fingerprint="c" * 64,
                           expected_generation=4, event_key="cannot-resume-stopping")

    def test_revoked_context_prevents_resume_but_owner_can_fence_stop(self):
        row, records = self.create(), self.records()
        records.block(self.owner, row["experiment_id"], {"code": "candidate_unavailable", "fingerprint": "a" * 64},
                      expected_generation=1, event_key="block-before-revoke")
        self.f.host.revoke(self.owner, row["experiment_id"], expected_generation=1, event_key="revoke-experiment-source")
        with self.assertRaises(PermissionError):
            records.resume(self.owner, row["experiment_id"], observed_fingerprint="b" * 64,
                           expected_generation=2, event_key="no-resume-revoked-source")
        ticket = records.begin_stop(self.owner, row["experiment_id"], kind="stale", reason="source_changed",
                                    expected_generation=2, event_key="stop-revoked-experiment")
        self.assertEqual(ticket["phase"], "stopping")

    def test_definition_history_and_direct_terminal_transition_are_sql_guarded(self):
        row = self.create()
        for assignment in ("definition_hash='changed',generation=generation+1", "phase='completed',generation=generation+1",
                           "generation=generation+2"):
            with self.subTest(assignment=assignment), self.store._Tx(self.store) as connection:
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute("UPDATE improvement_experiments SET " + assignment)
        with self.store._Tx(self.store) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM improvement_experiments")
        self.assertEqual(self.records().get(self.owner, row["experiment_id"]), row)

    def test_old_schema_mutations_are_unavailable_without_migrating(self):
        records = self.records()
        with self.assertRaises(PermissionError):
            records.block(self.owner, "association-experiment", {"code": "runtime_unavailable", "fingerprint": "a" * 64},
                          expected_generation=1, event_key="old-schema-block")
        with self.assertRaises(PermissionError):
            records.begin_stop(self.owner, "association-experiment", kind="cancelled", reason="owner_requested",
                               expected_generation=1, event_key="old-schema-stop")
        self.assertEqual(IM._schema_version(self.store), 4)
        self.assertEqual(self.history(), self.before)

    def test_concurrent_cas_has_one_winner_and_no_failed_event(self):
        row = self.create()
        gate = threading.Barrier(2)

        def block(index):
            gate.wait()
            try:
                return self.records().block(self.owner, row["experiment_id"],
                    {"code": "runtime_unavailable", "fingerprint": str(index) * 64},
                    expected_generation=1, event_key="concurrent-block-" + str(index))
            except IM.ConflictError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(block, (1, 2)))
        self.assertEqual(sum(value is not None for value in results), 1)
        with closing(self.store._conn()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM improvement_events WHERE operation='experiment_block'").fetchone()[0], 1)
        self.assertEqual(self.records().get(self.owner, row["experiment_id"])["generation"], 2)

    def test_policy_off_prevents_new_work_but_not_stop_or_historical_replay(self):
        row, records = self.create(), self.records()
        self.assets.set_policy(self.owner, "off", expected_version=0, event_key="off-after-experiment")
        self.assertEqual(self.create(), row)
        with self.assertRaises(PermissionError):
            self.create("new-create-after-off")
        stopped = records.begin_stop(self.owner, row["experiment_id"], kind="cancelled", reason="policy_changed",
                                     expected_generation=1, event_key="stop-after-policy-off")
        self.assertEqual(stopped["phase"], "stopping")

    def test_malformed_definition_rejects_before_schema_migration(self):
        definition = self.definition()
        for changes in ({"context_generation": True}, {"base_hash": "bad"}, {"evidence_class": "accepted_business"},
                        {"caller_authority": "trusted"}, {"repeat_policy": {"kind": "pilot", "repeats": 1}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.records().create(self.owner, {**definition, **changes}, expected_context_generation=1,
                                      event_key="malformed-definition")
        self.assertEqual(IM._schema_version(self.store), 4)
        self.assertEqual(self.history(), self.before)

    def test_sql_null_cannot_omit_stop_intent(self):
        row = self.create()
        with self.store._Tx(self.store) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE improvement_experiments SET phase='stopping',generation=generation+1,"
                    "stop_kind=NULL,stop_event_key='missing-stop-intent',stop_reason='owner_requested'")

    def test_sql_null_cannot_omit_selected_candidate(self):
        row = self.create()
        with self.store._Tx(self.store) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO improvement_experiment_selections VALUES(?,?,'candidate',NULL,?,?,?,0)", (
                    row["experiment_id"], self.owner.brain_id, row["definition_hash"], "[]", "owner-experiment-create"))

    def test_existing_unassociated_case_set_is_not_definition_authority(self):
        unassociated = self.f.cases.put_case_set(self.owner,
            [{**case, "evaluator_refs": []} for case in self.h.f.cases], 49, event_key="unassociated-experiment-cases")
        with self.assertRaises(PermissionError):
            self.create(case_set_id=unassociated["case_set_id"], case_set_hash=unassociated["manifest_hash"])
        self.assertEqual(self.records().list(self.owner)["items"], [])

    def test_blocked_and_stopping_keep_the_sql_brain_capacity(self):
        row, records = self.create(), self.records()
        # Exercise the SQL capacity fence independently of Plans' live source preflight.
        with closing(self.store._conn()) as connection:
            other_context = connection.execute("SELECT * FROM improvement_trial_contexts WHERE id=?",
                                               (self.f.binding["context_id"],)).fetchone()
        other = {**self.definition(), "experiment_id": other_context["experiment_id"], "context_id": other_context["id"],
                 "baseline_context_hash": other_context["context_hash"],
                 **{key: other_context[key] for key in ("binding_hash", "engine_config_hash", "grant_hash", "scope_hash", "policy_version")}}

        def competing_insert():
            with self.store._Tx(self.store) as connection:
                with self.assertRaisesRegex(sqlite3.IntegrityError, "UNIQUE constraint failed: improvement_experiments.brain_id"):
                    connection.execute("INSERT INTO improvement_experiments(id,brain_id,context_id,target_id,definition_hash,definition_json,"
                        "phase,generation,created_at,updated_at) VALUES(?,?,?,?,?,?,'proposed',1,0,0)", (
                        other["experiment_id"], self.owner.brain_id, other["context_id"], other["target_id"], IM._hash(other), IM._json(other)))

        records.block(self.owner, row["experiment_id"], {"code": "runtime_unavailable", "fingerprint": "a" * 64},
                      expected_generation=1, event_key="block-retains-brain-slot")
        competing_insert()
        records.begin_stop(self.owner, row["experiment_id"], kind="cancelled", reason="owner_requested",
                           expected_generation=2, event_key="stopping-retains-brain-slot")
        competing_insert()


if __name__ == "__main__":
    unittest.main()
