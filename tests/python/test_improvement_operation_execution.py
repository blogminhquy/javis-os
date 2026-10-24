"""Real SQL role lease/marker/settlement; synthetic metadata, no model calls."""
from _paths import ROOT, SERVER  # noqa: F401

import importlib.util
import json
import time
import unittest
from contextlib import closing
from unittest.mock import patch

import improvement_store as IM
from improvement_operation_records import OperationRecords
from improvement_trial_service import OwnerTrialService
import test_improvement_preparation as F
import test_improvement_operation_workspace as W
import usage_store as US
import usage_index as UI


class OperationExecutionTests(unittest.TestCase):
    def setUp(self):
        self.f = F.PreparationTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.enterContext(patch("subprocess.run", side_effect=lambda *args, **kwargs: W._acl_only(W._REAL_RUN, *args, **kwargs)))
        self.enterContext(patch("subprocess.Popen", side_effect=lambda *args, **kwargs: W._acl_only(W._REAL_POPEN, *args, **kwargs)))
        self.owner, self.assets, self.store = self.f.owner, self.f.assets, self.f.store
        root = self.store.path.parent
        for obj, name, value in ((US, "_PATH", root / "operation-usage.json"), (US, "_EVENTS_PATH", root / "operation-events.jsonl"),
                (US, "_TELEMETRY_ERRORS", {}), (UI, "_EVENTS_PATH", root / "operation-events.jsonl"),
                (UI, "DB_PATH", root / "operation-usage-index.db"), (UI, "_claude_dir", lambda: str(root / "empty-native")),
                (UI, "_codex_dir", lambda: str(root / "empty-codex"))):
            self.enterContext(patch.object(obj, name, value))
        self.trial_service = OwnerTrialService(self.f.host)
        with self.store._Tx(self.store) as connection:
            connection.execute("UPDATE improvement_experiments SET phase='proposing',generation=generation+1")
            definition = json.loads(connection.execute("SELECT definition_json FROM improvement_experiments").fetchone()[0])
        self.data = {"task": "Return a synthetic bounded role artifact", "evidence": []}
        blob = self.assets.blobs.write(self.owner.brain_id, IM._json(self.data).encode())
        request = {"version": 1, "experiment_id": definition["experiment_id"], "context_id": definition["context_id"],
                   "definition_hash": IM._hash(definition), "kind": "propose", "role": "improver", "purpose": "improve_propose",
                   "candidate_id": None, "parent_id": None, "input_hash": blob}
        with self.store._Tx(self.store) as connection:
            self.operation = OperationRecords(self.assets)._create_in(connection, self.owner, request, blob,
                expected_generation=2, event_key="execution-test-operation")

    def execution(self):
        self.assertIsNotNone(importlib.util.find_spec("improvement_operation_execution"), "Actual role leases are absent")
        from improvement_operation_execution import OperationExecution
        return OperationExecution(self.f.plans, self.trial_service)

    def reserve(self, service):
        with patch("improvement_operation_adapter.ClaudeOperationAdapter.verify",
                   return_value={"supported": True, "capability_hash": "c" * 64}):
            return service.reserve(self.owner, self.operation["operation_id"], expected_generation=1,
                                   event_key="execution-reserve")

    def prepared(self, service):
        row = self.reserve(service)
        claim = service.claim(self.owner, row["operation_id"], expected_generation=row["generation"])
        manifest = service.materialize(self.owner, row["operation_id"], expected_generation=claim["generation"],
                                       lease_token=claim["lease_token"])
        receipt = service.workspace.prepare(row["operation_id"], 1, manifest)
        prepared = service.prepared(self.owner, row["operation_id"], expected_generation=claim["generation"],
                                   lease_token=claim["lease_token"], receipt=receipt)
        return prepared, claim["lease_token"], receipt

    def test_real_lease_materialization_and_engine_marker_share_the_actual_call(self):
        service = self.execution()
        self.assertIs(service.workspace.brain_barrier, self.trial_service.trials.workspace)
        row, token, receipt = self.prepared(service)
        actual = service.workspace.validate(receipt)
        self.assertEqual(actual["data"], self.data)
        self.assertEqual(actual["learning_origin"], "compose")
        started = service.start_engine(self.owner, row["operation_id"], expected_generation=row["generation"], lease_token=token)
        attempt = started["attempts"][-1]
        call = service.ledger.get(attempt["call_id"])
        self.assertEqual((call["status"], call["purpose"]), ("running", "improve_propose"))
        self.assertEqual(call["engine_at"], attempt["engine_at"])
        self.assertIsNotNone(call["engine_at"])
        self.assertFalse(service.ledger.refund(call["id"]))

    def test_unmarked_abort_refunds_but_marked_abort_counts_after_off(self):
        service = self.execution()
        row, token, receipt = self.prepared(service)
        self.assets.set_policy(self.owner, "off", expected_version=0, event_key="execution-off")
        with self.assertRaises(PermissionError):
            service.start_engine(self.owner, row["operation_id"], expected_generation=row["generation"], lease_token=token)
        stopped = service.abort(self.owner, row["operation_id"], expected_generation=row["generation"],
                                lease_token=token, reason="authority_changed")
        self.assertEqual(stopped["status"], "not_run")
        self.assertEqual(service.ledger.get(stopped["attempts"][-1]["call_id"])["status"], "refunded")
        self.assertTrue(service.workspace.cleanup_proven(row["operation_id"], 1, receipt))

    def test_stale_writer_and_expired_lease_cannot_start_or_replace_inputs(self):
        service = self.execution()
        row, token, receipt = self.prepared(service)
        for generation, writer, now in ((row["generation"] - 1, token, None),
                                         (row["generation"], "foreign-writer", None),
                                         (row["generation"], token, time.time() + 600)):
            with self.subTest(generation=generation, writer=writer, now=now), self.assertRaises(IM.ConflictError):
                service.start_engine(self.owner, row["operation_id"], expected_generation=generation,
                                     lease_token=writer, now=now)
        self.assertIsNone(service.ledger.get(row["attempts"][-1]["call_id"])["engine_at"])

    def test_marked_abort_retains_counted_start_and_rejects_foreign_writer(self):
        service = self.execution()
        row, token, receipt = self.prepared(service)
        row = service.start_engine(self.owner, row["operation_id"], expected_generation=row["generation"], lease_token=token)
        self.assets.set_policy(self.owner, "off", expected_version=0, event_key="off-after-operation-marker")
        with self.assertRaises(IM.ConflictError):
            service.abort(self.owner, row["operation_id"], expected_generation=row["generation"],
                          lease_token="foreign-writer", reason="cancelled")
        stopped = service.abort(self.owner, row["operation_id"], expected_generation=row["generation"],
                                lease_token=token, reason="cancelled")
        self.assertEqual(stopped["status"], "interrupted")
        call = service.ledger.get(stopped["attempts"][-1]["call_id"])
        self.assertEqual((call["status"], call["counted"]), ("interrupted", 1))
        self.assertIsNotNone(call["engine_at"])

    def test_foreign_workspace_sql_reference_cannot_mark_current_role_call(self):
        service = self.execution()
        row, token, receipt = self.prepared(service)
        manifest = service.workspace.validate(receipt)
        manifest["operation_id"] = "foreign-operation"
        foreign = service.workspace.prepare("foreign-operation", 1, manifest)
        with self.store._Tx(self.store) as connection:
            connection.execute("UPDATE improvement_operation_attempts SET workspace_json=?,materialization_hash=? "
                               "WHERE operation_id=?", (IM._json(foreign), IM._hash(manifest), row["operation_id"]))
        with self.assertRaisesRegex(IM.ConflictError, "operation_materialization_changed"):
            service.start_engine(self.owner, row["operation_id"], expected_generation=row["generation"], lease_token=token)
        self.assertIsNone(service.ledger.get(row["attempts"][-1]["call_id"])["engine_at"])

    def test_no_native_capability_means_no_reserved_call_and_replay_after_off_is_cold(self):
        service = self.execution()
        with patch("improvement_operation_adapter.ClaudeOperationAdapter.verify", return_value={"supported": False}):
            with self.assertRaisesRegex(ValueError, "operation_native_unavailable"):
                service.reserve(self.owner, self.operation["operation_id"], expected_generation=1, event_key="unsupported-operation")
        self.assertEqual(service.get(self.owner, self.operation["operation_id"])["attempts"], [])
        reserved = self.reserve(service)
        self.assets.set_policy(self.owner, "off", expected_version=0, event_key="off-after-reservation")
        with patch.object(self.f.host, "_snapshot_observe", side_effect=AssertionError("Replay re-observed sources")), \
             patch.object(self.assets.blobs, "read", side_effect=AssertionError("Replay decrypted input")), \
             patch("improvement_operation_adapter.ClaudeOperationAdapter.verify", side_effect=AssertionError("Replay probed native")):
            self.assertEqual(service.reserve(self.owner, self.operation["operation_id"], expected_generation=1,
                                             event_key="execution-reserve"), reserved)

    def test_actual_call_marker_cannot_be_refunded_when_attempt_marker_is_missing(self):
        service = self.execution()
        row, token, receipt = self.prepared(service)
        call_id = row["attempts"][-1]["call_id"]
        # Historical/corrupt partial metadata is not proof the model was unused.
        self.assertTrue(service.ledger.mark_engine(call_id, "anthropic-cli", "synthetic-selected-model"))
        actual_marker = service.ledger.get(call_id)["engine_at"]
        stopped = service.abort(self.owner, row["operation_id"], expected_generation=row["generation"],
                                lease_token=token, reason="worker_failed")
        self.assertEqual(stopped["status"], "interrupted")
        self.assertEqual(stopped["attempts"][-1]["engine_at"], actual_marker)
        self.assertEqual(service.ledger.get(call_id)["status"], "interrupted")

    def test_heartbeat_uses_actual_writer_and_current_authority_without_new_generation(self):
        service = self.execution()
        row, token, receipt = self.prepared(service)
        method = getattr(service, "heartbeat", None)
        self.assertTrue(callable(method), "Actual operation heartbeat is absent")
        current = method(self.owner, row["operation_id"], expected_generation=row["generation"], lease_token=token)
        self.assertEqual(current["generation"], row["generation"])
        self.assertLessEqual(current["attempts"][-1]["lease_until"], current["deadline_at"])
        with self.assertRaises(IM.ConflictError):
            method(self.owner, row["operation_id"], expected_generation=row["generation"], lease_token="foreign")
        self.assets.set_policy(self.owner, "off", expected_version=0, event_key="off-before-heartbeat")
        with self.assertRaises(PermissionError):
            method(self.owner, row["operation_id"], expected_generation=row["generation"], lease_token=token)

    def test_unclaimed_refund_cannot_close_an_acquired_foreign_lease(self):
        service = self.execution()
        row = self.reserve(service)
        method = getattr(service, "reject_unclaimed", None)
        self.assertTrue(callable(method), "Actual unclaimed reservation cleanup is absent")
        claimed = service.claim(self.owner, row["operation_id"], expected_generation=row["generation"])
        with self.assertRaises(IM.ConflictError):
            method(self.owner, row["operation_id"], expected_generation=claimed["generation"], reason="cancelled")
        self.assertEqual(service.ledger.get(claimed["attempts"][-1]["call_id"])["status"], "reserved")

    def test_preclaim_cancel_refunds_after_off_without_native_or_source_probe(self):
        service = self.execution()
        row = self.reserve(service)
        method = getattr(service, "reject_unclaimed", None)
        self.assertTrue(callable(method), "Actual preclaim cancellation cleanup is absent")
        self.assets.set_policy(self.owner, "off", expected_version=0, event_key="off-before-unclaimed-refund")
        with patch.object(self.f.host, "_snapshot_observe", side_effect=AssertionError("Cleanup re-observed source")):
            stopped = method(self.owner, row["operation_id"], expected_generation=row["generation"], reason="cancelled")
        self.assertEqual(stopped["status"], "not_run")
        self.assertEqual(service.ledger.get(stopped["attempts"][-1]["call_id"])["status"], "refunded")

    def test_nonfinite_or_boolean_start_clock_cannot_mark_a_call(self):
        service = self.execution()
        row, token, receipt = self.prepared(service)
        for now in (float("nan"), float("inf"), True):
            with self.subTest(now=now), self.assertRaises(ValueError):
                service.start_engine(self.owner, row["operation_id"], expected_generation=row["generation"], lease_token=token, now=now)
        self.assertIsNone(service.ledger.get(row["attempts"][-1]["call_id"])["engine_at"])

    def test_same_schema_number_with_stale_role_guards_cannot_be_native_authority(self):
        service = self.execution()
        with self.store._Tx(self.store) as connection:
            connection.execute("DROP TRIGGER improvement_operation_attempt_scope")
        with patch("improvement_operation_adapter.ClaudeOperationAdapter.verify", side_effect=AssertionError("Stale schema probed native")), \
                self.assertRaisesRegex(IM.ConflictError, "operation_schema_changed"):
            service.reserve(self.owner, self.operation["operation_id"], expected_generation=1, event_key="forbidden-stale-schema-start")
        self.assertEqual(service.get(self.owner, self.operation["operation_id"])["attempts"], [])
        self.assets.set_policy(self.owner, "off", expected_version=0, event_key="off-despite-stale-draft-schema")
        self.assertEqual(service.cancel(self.owner, self.operation["operation_id"], expected_generation=1,
                                        event_key="cancel-despite-stale-draft-schema")["status"], "cancelled")

    def test_unknown_future_schema_never_becomes_native_authority_even_if_old_guards_exist(self):
        service = self.execution()
        with self.store._Tx(self.store) as connection:
            connection.execute("UPDATE improvement_schema SET version=? WHERE id=1", (IM.SCHEMA_VERSION + 1,))
        with patch("improvement_operation_adapter.ClaudeOperationAdapter.verify", side_effect=AssertionError("Unknown schema probed native")), \
                self.assertRaisesRegex(IM.SchemaError, "unsupported_improvement_schema"):
            service.reserve(self.owner, self.operation["operation_id"], expected_generation=1, event_key="forbidden-future-schema-query")


if __name__ == "__main__":
    unittest.main()
