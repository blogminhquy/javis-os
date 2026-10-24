"""Schema6 preserves actual released history; metadata cannot impersonate calls."""
from _paths import ROOT, SERVER  # noqa: F401

import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
import threading
import time
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from unittest.mock import patch

import improvement_store as IM
import test_improvement_experiments as fixtures

RELEASED_B = "47f50f707268681dd4cbe8c7e443945155376237"
if importlib.util.find_spec("improvement_operation_schema"):
    import improvement_operation_schema as SCHEMA
else:
    SCHEMA = None


class OperationFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = subprocess.run(["git", "show", RELEASED_B + ":server/improvement_store.py"],
                                cwd=ROOT, capture_output=True, check=True).stdout
        module = types.ModuleType("_released_improvement_schema5")
        sys.modules[module.__name__] = module
        exec(compile(source, "released-schema5/improvement_store.py", "exec"), module.__dict__)
        cls.old_reader = module

    def setUp(self):
        self.h = fixtures.ExperimentTests()
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.assets, self.store, self.owner = self.h.assets, self.h.store, self.h.owner
        with patch.object(IM, "ensure", side_effect=self.old_reader.ensure):
            self.experiment = self.h.create()
        self.before = self.h.history()


class OperationMigrationTests(OperationFixture):
    def test_earlier_known_schema_versions_upgrade_without_losing_policy_or_backup(self):
        for version in (1, 2, 3):
            with self.subTest(version=version):
                database = type(self.store)(self.store.path.parent / ("older-" + str(version) + ".sqlite3"))
                blocks = [(IM._SCHEMA, ("improvement_revisions", "improvement_bundles",
                                        "improvement_bundle_assets", "improvement_events"))]
                if version >= 2:
                    blocks.append((fixtures.CASES.SCHEMA, fixtures.CASES.IMMUTABLE))
                if version >= 3:
                    blocks.append((fixtures.TRIALS.SCHEMA, fixtures.TRIALS.IMMUTABLE))
                with database._Tx(database) as connection:
                    for statements, immutable in blocks:
                        for statement in statements:
                            connection.execute(statement)
                        IM._immutable_triggers(connection, immutable)
                    connection.execute("INSERT INTO improvement_schema VALUES(1,?)", (version,))
                    connection.execute("INSERT INTO improvement_policies VALUES('legacy-brain','off',7)")
                IM.ensure(database)
                self.assertEqual(IM._schema_version(database), IM.SCHEMA_VERSION)
                with closing(database._conn()) as connection:
                    self.assertEqual(tuple(connection.execute("SELECT * FROM improvement_policies").fetchone()),
                                     ("legacy-brain", "off", 7))
                    self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
                backup = database.path.with_name(database.path.name + ".pre-improvement-m2-generated.bak")
                with closing(sqlite3.connect(backup)) as connection:
                    self.assertEqual(connection.execute("SELECT version FROM improvement_schema").fetchone()[0], version)

    def test_schema5_upgrades_preserving_actual_candidate_trial_call_and_event_bytes(self):
        IM.ensure(self.store)
        self.assertEqual(IM._schema_version(self.store), IM.SCHEMA_VERSION, "Current compose migration is absent")
        after = self.h.history()
        self.assertEqual({name: after[name] for name in self.before}, self.before)
        self.assertTrue({"improvement_preparations", "improvement_preparation_trial_links",
                         "improvement_operations", "improvement_operation_attempts",
                         "improvement_operation_observations", "improvement_operation_results",
                         "improvement_proposal_publications", "improvement_generated_candidates",
                         "improvement_semantic_receipts"}.issubset(after))
        backup = self.store.path.with_name(self.store.path.name + ".pre-improvement-m2-generated.bak")
        self.assertTrue(backup.is_file())
        with closing(sqlite3.connect(backup)) as connection:
            self.assertEqual(connection.execute("SELECT version FROM improvement_schema").fetchone()[0], 5)
            self.assertEqual(connection.execute("SELECT id FROM improvement_skill_candidates").fetchone()[0],
                             self.h.candidate["candidate_id"])
            self.assertEqual(connection.execute("SELECT count(*) FROM agent_calls").fetchone()[0],
                             len(self.before["agent_calls"]))
        digest = hashlib.sha256(backup.read_bytes()).hexdigest()
        IM.ensure(self.store)
        self.assertEqual(hashlib.sha256(backup.read_bytes()).hexdigest(), digest)

    def test_actual_released_b_reader_rejects_new_schema_before_backup_or_write(self):
        IM.ensure(self.store)
        self.assertEqual(IM._schema_version(self.store), IM.SCHEMA_VERSION, "Current compose migration is absent")
        before = self.h.history()
        with patch.object(self.store, "_backup_before", side_effect=AssertionError("Old binary cannot write")):
            with self.assertRaises(self.old_reader.SchemaError):
                self.old_reader.read_existing(self.store.path, self.assets.blobs)
            with self.assertRaises(self.old_reader.SchemaError):
                self.old_reader.ensure(self.store)
        self.assertEqual(self.h.history(), before)

    def test_concurrent_first_writers_make_one_complete_schema5_backup(self):
        gate, backups = threading.Barrier(2), []
        original = self.store._backup_before

        def backup(*args):
            backups.append(args)
            return original(*args)

        def migrate(_):
            gate.wait(timeout=10)
            IM.ensure(self.store)

        with patch.object(self.store, "_backup_before", side_effect=backup), ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(migrate, (1, 2)))
        self.assertEqual(backups, [("improvement_compositions", ".pre-improvement-m2-compose.bak"),
                                  ("improvement_preparations", ".pre-improvement-m2-generated.bak"),
                                  ("improvement_effective_views", ".pre-improvement-m2-views.bak")])
        self.assertEqual(IM._schema_version(self.store), IM.SCHEMA_VERSION)
        self.assertEqual({name: self.h.history()[name] for name in self.before}, self.before)

    def test_failure_rolls_back_every_new_table_trigger_and_version(self):
        self.assertIsNotNone(SCHEMA, "Generated-role schema is absent")
        with patch.object(SCHEMA, "SCHEMA", (*SCHEMA.SCHEMA, "INVALID GENERATED MIGRATION")):
            with self.assertRaises(sqlite3.OperationalError):
                IM.ensure(self.store)
        self.assertEqual(IM._schema_version(self.store), 5)
        self.assertEqual(self.h.history(), self.before)
        with closing(self.store._conn()) as connection:
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name='improvement_operation_scope'").fetchone())
        IM.ensure(self.store)
        self.assertEqual(IM._schema_version(self.store), IM.SCHEMA_VERSION)

    def test_unknown_future_version_rejects_without_backup_or_mutation(self):
        with self.store._Tx(self.store) as connection:
            connection.execute("UPDATE improvement_schema SET version=?", (IM.SCHEMA_VERSION + 1,))
        with patch.object(self.store, "_backup_before", side_effect=AssertionError("Unknown schema cannot back up")):
            with self.assertRaises(IM.SchemaError):
                IM.ensure(self.store)
            with self.assertRaises(IM.SchemaError):
                IM.read_existing(self.store.path, self.assets.blobs)
        self.assertEqual(self.h.history(), self.before)


class OperationMetadataTests(OperationFixture):
    def module(self, name):
        spec = importlib.util.find_spec(name)
        self.assertIsNotNone(spec, "Real role/preparation metadata is absent: " + name)
        return __import__(name)

    def prepare(self, *, generation=1, key="owner-freeze-preparation", case_ids=None):
        protocol = self.module("improvement_preparation_protocol")
        records = self.module("improvement_preparation_records").PreparationRecords(self.assets)
        value = self.h.definition()
        schedule = protocol.preparation_schedule(value, case_ids if case_ids is not None else ["case-0"], 47)
        blob = self.assets.blobs.write(self.owner.brain_id, IM._json(schedule).encode())
        IM.ensure(self.store)
        with self.store._Tx(self.store) as connection:
            return records._freeze_in(connection, self.owner, schedule, blob,
                                      expected_generation=generation, event_key=key)

    def request(self, *, kind="propose", parent_id=None, candidate_id=None):
        return {"version": 1, "experiment_id": "association-experiment", "context_id": self.h.definition()["context_id"],
                "definition_hash": IM._hash(self.h.definition()), "kind": kind,
                "role": "semantic_reviewer" if kind == "semantic" else "improver",
                "purpose": "improve_evaluate" if kind == "semantic" else "improve_propose",
                "parent_id": parent_id, "candidate_id": candidate_id, "input_hash": hashlib.sha256(b"input").hexdigest()}

    def operation(self, request=None, *, key="owner-operation-create", generation=2):
        records = self.module("improvement_operation_records").OperationRecords(self.assets)
        blob = self.assets.blobs.write(self.owner.brain_id, b"input")
        with self.store._Tx(self.store) as connection:
            return records._create_in(connection, self.owner, request or self.request(), blob,
                                      expected_generation=generation, event_key=key)

    def proposing(self):
        IM.ensure(self.store)
        # Synthetic host metadata state, not evidence of native preparation.
        with self.store._Tx(self.store) as connection:
            connection.execute("UPDATE improvement_experiments SET phase='proposing',generation=generation+1")

    def test_cold_legacy_reads_never_migrate_decrypt_or_make_native_calls(self):
        operations = self.module("improvement_operation_records").OperationRecords(self.assets)
        preparations = self.module("improvement_preparation_records").PreparationRecords(self.assets)
        with patch.object(self.assets.blobs, "read", side_effect=AssertionError("Cold metadata cannot decrypt")), \
             patch.object(self.store, "_backup_before", side_effect=AssertionError("Cold metadata cannot migrate")):
            self.assertEqual(operations.list(self.owner, "association-experiment"), [])
            self.assertEqual(preparations.list(self.owner, "association-experiment"), [])
            with self.assertRaises(PermissionError):
                operations.get(self.owner, "io_missing")
            with self.assertRaises(PermissionError):
                preparations.get(self.owner, "ip_missing")
        self.assertEqual(IM._schema_version(self.store), 5)
        self.assertEqual(self.h.history(), self.before)

    def test_complete_baseline_schedule_has_no_arm_and_cas_retains_live_capacity(self):
        result = self.prepare()
        self.assertEqual(result["cell_count"], 1)
        current = self.h.records().get(self.owner, "association-experiment")
        self.assertEqual((current["phase"], current["generation"]), ("preparing", 2))
        self.assertEqual(len(self.h.history()["agent_calls"]), len(self.before["agent_calls"]))
        self.assertEqual(len(self.h.history()["improvement_experiment_arms"]), 0)
        self.assertEqual(self.prepare(), result)
        with self.assertRaises(IM.ConflictError):
            self.prepare(key="stale-freeze-preparation")
        with closing(self.store._conn()) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM improvement_experiments WHERE phase='preparing'").fetchone()[0], 1)
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE improvement_preparations SET schedule_hash=?", ("f" * 64,))
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM improvement_preparations")

    def test_qualification_cell_cannot_be_frozen_as_preparation(self):
        for identifier in ("case-1", "case-2"):
            with self.subTest(identifier=identifier), self.assertRaises((IM.ConflictError, PermissionError, ValueError)):
                self.prepare(case_ids=[identifier])
        self.assertEqual(self.h.records().get(self.owner, "association-experiment")["phase"], "proposed")

    def test_schedule_enumerates_all_repeats_and_rejects_duplicate_or_empty_membership(self):
        protocol = self.module("improvement_preparation_protocol")
        value = self.h.definition()
        value["repeat_policy"] = {"kind": "pilot", "repeats": 2}
        schedule = protocol.preparation_schedule(value, ["case-1"], 47)
        self.assertEqual(schedule["cells"], [{"case_id": "case-1", "repeat": 1}, {"case_id": "case-1", "repeat": 2}])
        self.assertEqual(set(schedule), {"version", "experiment_id", "definition_hash", "context_id", "case_set_id",
                                       "case_set_hash", "repeat_policy", "schedule_seed", "cells"})
        for identifiers in ([], ["case-1", "case-1"], [True]):
            with self.subTest(identifiers=identifiers), self.assertRaises(ValueError):
                protocol.preparation_schedule(value, identifiers, 47)

    def test_preparation_preserves_existing_signed_case_seed_contract(self):
        protocol = self.module("improvement_preparation_protocol")
        schedule = protocol.preparation_schedule(self.h.definition(), ["case-1"], -47)
        self.assertEqual(schedule["cells"], [{"case_id": "case-1", "repeat": 1}])

    def test_genuine_role_request_has_no_trial_identity_and_metadata_cannot_reserve_calls(self):
        self.proposing()
        saved = self.operation()
        self.assertEqual((saved["kind"], saved["role"], saved["purpose"], saved["status"], saved["attempt"]),
                         ("propose", "improver", "improve_propose", "pending", 0))
        self.assertEqual(self.operation(), saved)
        self.assertEqual(len(self.h.history()["agent_calls"]), len(self.before["agent_calls"]))
        self.assertEqual(len(self.h.history()["improvement_operation_attempts"]), 0)
        records = self.module("improvement_operation_records").OperationRecords(self.assets)
        with patch.object(self.assets.blobs, "read", side_effect=AssertionError("Cold role history cannot decrypt")):
            self.assertEqual(records.get(self.owner, saved["operation_id"]), saved)
            self.assertEqual(records.list(self.owner, "association-experiment"), [saved])
        with self.assertRaises(PermissionError):
            records.get(self.h.f.other, saved["operation_id"])
        with self.assertRaises(IM.ConflictError):
            self.operation(key="duplicate-propose-operation", generation=3)

    def test_mixed_or_forged_role_and_operation_request_fields_reject(self):
        protocol = self.module("improvement_operation_protocol")
        request = self.request()
        self.assertEqual(protocol.operation_request(request), request)
        for changes in ({"trial_id": "fake"}, {"purpose": "improve_probe"}, {"role": "semantic_reviewer"},
                        {"version": True}, {"candidate_id": self.h.candidate["candidate_id"]},
                        {"parent_id": "invented-parent"}, {"native_ready": True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                protocol.operation_request({**request, **changes})

    def test_repair_is_single_and_binds_actual_original_operation_in_same_experiment(self):
        self.proposing()
        original = self.operation()
        request = self.request(kind="repair", parent_id=original["operation_id"])
        saved = self.operation(request, key="owner-single-structural-repair", generation=3)
        self.assertEqual(saved["parent_id"], original["operation_id"])
        with self.assertRaises(IM.ConflictError):
            self.operation(request, key="second-structural-repair", generation=4)
        with closing(self.store._conn()) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE improvement_operations SET purpose='improve_probe',generation=generation+1")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM improvement_operations")

    def test_semantic_candidate_scope_and_stale_generation_reject_without_any_call(self):
        self.proposing()
        with self.assertRaises(IM.ConflictError):
            self.operation(generation=1)
        with self.assertRaises(PermissionError):
            self.operation(self.request(kind="semantic", candidate_id="foreign-candidate"))
        saved = self.operation(self.request(kind="semantic", candidate_id=self.h.candidate["candidate_id"]))
        self.assertEqual(saved["role"], "semantic_reviewer")
        self.assertEqual(len(self.h.history()["agent_calls"]), len(self.before["agent_calls"]))
        self.assertEqual(self.h.history()["improvement_skill_candidates"], self.before["improvement_skill_candidates"])

    def test_pending_metadata_cannot_be_marked_native_completed_or_publish_evidence(self):
        self.proposing()
        saved = self.operation()
        with self.store._Tx(self.store) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE improvement_operations SET status='completed',generation=generation+1 WHERE id=?",
                                   (saved["operation_id"],))
        self.assertEqual(self.h.history()["improvement_operation_results"], [])
        self.assertEqual(self.h.history()["improvement_proposal_publications"], [])
        self.assertEqual(self.h.history()["improvement_semantic_receipts"], [])

    def test_solver_call_cannot_be_substituted_for_real_role_attempt(self):
        self.proposing()
        saved = self.operation()
        with self.store._Tx(self.store) as connection:
            call = connection.execute("SELECT id FROM agent_calls WHERE purpose='improve_probe'").fetchone()[0]
            with self.assertRaisesRegex(sqlite3.IntegrityError, "operation_call_scope_mismatch"):
                connection.execute("INSERT INTO improvement_operation_attempts "
                    "(operation_id,brain_id,attempt,status,call_id,created_at,updated_at) VALUES(?,?,1,'reserved',?,?,?)",
                    (saved["operation_id"], self.owner.brain_id, call, time.time(), time.time()))
        self.assertEqual(self.h.history()["agent_calls"], self.before["agent_calls"])

    def test_legacy_trial_cannot_be_laundered_into_typed_preparation_link(self):
        saved = self.prepare()
        with self.store._Tx(self.store) as connection:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "preparation_trial_scope_mismatch"):
                connection.execute("INSERT INTO improvement_preparation_trial_links VALUES(?,?,?,0,?,?,?,1,?)", (
                    saved["preparation_id"], self.owner.brain_id, "association-experiment", self.h.admitted.trial_id,
                    IM._hash(self.h.admitted.request), "case-0", time.time()))
        self.assertEqual(self.h.history()["improvement_preparation_trial_links"], [])

    def test_concurrent_operation_metadata_has_one_cas_winner_without_call(self):
        self.proposing()
        gate = threading.Barrier(2)

        def create(index):
            gate.wait(timeout=10)
            try:
                return self.operation(key="concurrent-operation-" + str(index))
            except IM.ConflictError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(create, (1, 2)))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(len(self.h.history()["improvement_operations"]), 1)
        self.assertEqual(self.h.history()["agent_calls"], self.before["agent_calls"])

    def test_off_preserves_historical_replay_but_denies_new_roles(self):
        self.proposing()
        saved = self.operation()
        self.assets.set_policy(self.owner, "off", expected_version=0, event_key="off-after-role-metadata")
        self.assertEqual(self.operation(), saved)
        with self.assertRaises(PermissionError):
            self.operation(self.request(kind="semantic", candidate_id=self.h.candidate["candidate_id"]),
                           key="semantic-after-off", generation=3)
        self.assertEqual(len(self.h.history()["improvement_operations"]), 1)

    def test_preparation_and_operation_metadata_rollback_with_their_owner_event(self):
        self.module("improvement_preparation_protocol")
        IM.ensure(self.store)
        before = self.h.history()
        with patch.object(self.assets, "_event", side_effect=RuntimeError("Synthetic event write failure")):
            with self.assertRaises(RuntimeError):
                self.prepare()
        self.assertEqual(self.h.history(), before)
        self.proposing()
        before = self.h.history()
        with patch.object(self.assets, "_event", side_effect=RuntimeError("Synthetic event write failure")):
            with self.assertRaises(RuntimeError):
                self.operation()
        self.assertEqual(self.h.history(), before)


if __name__ == "__main__":
    unittest.main()
