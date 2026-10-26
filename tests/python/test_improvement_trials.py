"""Durable trial and existing call reservation use real isolated SQLite, without models."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import importlib.util
import json
import sqlite3
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from unittest.mock import patch

import test_improvement_cases as fixtures
import improvement_store as IM
from agent_ledger import CallLedger

if importlib.util.find_spec("improvement_trials"):
    import improvement_trials as IT
else:
    IT = None


class TrialStoreTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(IT, "Durable trials are not implemented")
        fixture = fixtures.ImprovementCaseTests()
        fixture.setUp()
        self.root, self.rs = fixture.root, fixture.rs
        self.assets, self.cases = fixture.assets, fixture.cases
        self.owner, self.other = fixture.owner, fixture.other
        case_set, _ = fixture.case_set()
        pins = fixture.pins(case_set)
        engine = {"version": 1, "provider": "anthropic-cli", "engine_id": "claude-sdk",
            "model": "claude-opus-5-5", "reasoning": "medium", "cli_path": "synthetic-unused-cli",
            "cli_hash": "a" * 64, "cli_version": "2.1.304", "sdk_version": "0.2.116",
            "profile_version": "fixture", "profile_hash": "b" * 64}
        pins["engine_config_hash"] = IM._hash(engine)
        targets = {target["id"]: target["generation"] for target in self.assets.targets(self.owner)}
        self.context = {"content": "Complete synthetic owner instructions",
                        "hash": fixtures.digest("Complete synthetic owner instructions"), "coverage": "complete"}
        self.request = {"version": 1, "pins": pins, "case_set_id": case_set["case_set_id"], "case_id": "case-1",
            "variant": "baseline", "repeat": 1, "engine_config": engine,
            "baseline_context_hash": IM._hash(self.context),
            "target_generations": targets, "deadline_at": time.time() + 300}
        self.trials = IT.TrialStore(self.assets)
        self.ledger = CallLedger(self.rs)

    def reserve(self, key="trial-reserve-0001", **changes):
        return self.trials.reserve(self.owner, {**copy.deepcopy(self.request), **changes}, event_key=key)

    def prepared(self):
        trial = self.reserve()
        claimed = self.trials.claim(self.owner, trial["trial_id"], expected_generation=1)
        manifest = self.trials.materialize(self.owner, trial["trial_id"], expected_generation=claimed["generation"],
            lease_token=claimed["lease_token"], baseline_context=self.context)
        receipt = self.trials.workspace.prepare(trial["trial_id"], 1, manifest)
        prepared = self.trials.prepared(self.owner, trial["trial_id"], expected_generation=claimed["generation"],
            lease_token=claimed["lease_token"], receipt=receipt)
        return prepared, claimed["lease_token"]

    def test_reservation_and_call_are_one_transaction_and_replay_does_not_duplicate(self):
        trial = self.reserve()
        self.assertEqual(trial, self.reserve())
        current = self.trials.get(self.owner, trial["trial_id"])
        self.assertEqual((current["status"], current["generation"], current["attempt"]), ("reserved", 1, 1))
        call = self.ledger.get(current["attempts"][0]["call_id"])
        self.assertEqual(call["purpose"], "improve_probe")
        self.assertEqual(call["context_ref"], "improvement:experiment-1")
        self.assertEqual(call["mirror_ref"], "improvement_trial:" + trial["trial_id"])
        with self.rs._conn() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM goals").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agent_calls").fetchone()[0], 1)
        self.assertFalse((self.root / "team.sqlite3").exists())
        self.assertNotIn("private-answer", json.dumps(current))

    def test_simultaneous_logical_reservations_share_one_trial_and_call(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self.reserve, ("parallel-trial-0001", "parallel-trial-0002")))
        self.assertEqual(results[0]["trial_id"], results[1]["trial_id"])
        with self.rs._conn() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agent_calls").fetchone()[0], 1)

    def test_distinct_trials_compete_for_one_brain_model_slot_atomically(self):
        first, first_token = self.prepared()
        second = self.reserve("second-model-slot", repeat=2)
        claimed = self.trials.claim(self.owner, second["trial_id"], expected_generation=1)
        manifest = self.trials.materialize(self.owner, second["trial_id"],
            expected_generation=claimed["generation"], lease_token=claimed["lease_token"], baseline_context=self.context)
        receipt = self.trials.workspace.prepare(second["trial_id"], 1, manifest)
        second = self.trials.prepared(self.owner, second["trial_id"], expected_generation=claimed["generation"],
                                     lease_token=claimed["lease_token"], receipt=receipt)
        contenders = [(first, first_token), (second, claimed["lease_token"])]

        def start(contender):
            row, token = contender
            # Independent stores/connections share only the durable database gate.
            store = IT.TrialStore(self.assets)
            try:
                return store.start_engine(self.owner, row["trial_id"], expected_generation=row["generation"],
                                          lease_token=token)
            except IM.ConflictError as error:
                return str(error)

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(start, contenders))
        winners = [result for result in results if isinstance(result, dict)]
        self.assertEqual(len(winners), 1, "One brain started multiple model trials")
        self.assertEqual([result for result in results if isinstance(result, str)], ["trial_brain_capacity_unavailable"])
        winner = winners[0]
        loser_index = next(index for index, result in enumerate(results) if isinstance(result, str))
        loser, token = contenders[loser_index]
        self.assertEqual(self.trials.get(self.owner, loser["trial_id"])["status"], "prepared")
        self.assertIsNone(self.ledger.get(loser["attempts"][0]["call_id"])["engine_at"])
        self.trials.cancel(self.owner, winner["trial_id"], expected_generation=winner["generation"],
                           event_key="release-model-slot")
        running = start((loser, token))
        self.assertIsInstance(running, dict)
        self.assertEqual(running["status"], "running")

    def test_model_slot_does_not_block_a_different_authorized_brain(self):
        first, token = self.prepared()
        self.trials.start_engine(self.owner, first["trial_id"], expected_generation=first["generation"],
                                 lease_token=token)
        fixture = fixtures.ImprovementCaseTests()
        fixture.owner, fixture.assets, fixture.cases = self.other, self.assets, self.cases
        case_set, _ = fixture.case_set()
        pins = fixture.pins(case_set, engine_config_hash=self.request["pins"]["engine_config_hash"])
        request = {**copy.deepcopy(self.request), "pins": pins, "case_set_id": case_set["case_set_id"],
                   "target_generations": {target["id"]: target["generation"]
                                          for target in self.assets.targets(self.other)}}
        trial = self.trials.reserve(self.other, request, event_key="other-brain-model-slot")
        claimed = self.trials.claim(self.other, trial["trial_id"], expected_generation=1)
        manifest = self.trials.materialize(self.other, trial["trial_id"], expected_generation=claimed["generation"],
                                          lease_token=claimed["lease_token"], baseline_context=self.context)
        receipt = self.trials.workspace.prepare(trial["trial_id"], 1, manifest)
        prepared = self.trials.prepared(self.other, trial["trial_id"], expected_generation=claimed["generation"],
                                        lease_token=claimed["lease_token"], receipt=receipt)
        running = self.trials.start_engine(self.other, trial["trial_id"], expected_generation=prepared["generation"],
                                           lease_token=claimed["lease_token"])
        self.assertEqual(running["status"], "running")
        self.assertEqual(self.trials.get(self.owner, first["trial_id"])["status"], "running")

    def test_stale_policy_target_and_foreign_scope_cannot_reserve_or_read(self):
        for changes in ({"pins": {**self.request["pins"], "policy_version": 999}},
                        {"target_generations": {key: 999 for key in self.request["target_generations"]}},
                        {"pins": {**self.request["pins"], "engine_config_hash": "c" * 64}}):
            with self.subTest(changes=changes), self.assertRaises((ValueError, IM.ConflictError)):
                self.reserve(**changes)
        trial = self.reserve()
        with self.assertRaises(PermissionError):
            self.trials.get(self.other, trial["trial_id"])

    def test_unsupported_provider_or_invalid_execution_identity_is_rejected_before_reservation(self):
        engine = {**self.request["engine_config"], "provider": "openai"}
        for index, changes in enumerate(({"engine_config": engine, "pins": {**self.request["pins"], "engine_config_hash": IM._hash(engine)}},
                                        {"pins": {**self.request["pins"], "experiment_id": "unscoped/experiment"}})):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.reserve("invalid-request-" + str(index), **changes)

    def test_boolean_generation_cannot_claim_and_exhausted_call_capacity_leaves_no_trial(self):
        trial = self.reserve()
        with self.assertRaises(IM.ConflictError):
            self.trials.claim(self.owner, trial["trial_id"], expected_generation=True)
        from unittest.mock import patch
        with patch.object(fixtures.RS, "_under_ceiling", return_value=False), self.assertRaises(IM.ConflictError):
            self.reserve("capacity-empty-trial", repeat=2)
        with self.rs._conn() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM improvement_trials").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agent_calls").fetchone()[0], 1)

    def test_cancel_before_engine_refunds_and_invalidates_a_claimed_lease(self):
        trial = self.reserve()
        claimed = self.trials.claim(self.owner, trial["trial_id"], expected_generation=1)
        self.assertNotIn("lease_token", self.trials.get(self.owner, trial["trial_id"]))
        cancelled = self.trials.cancel(self.owner, trial["trial_id"], expected_generation=claimed["generation"],
                                       event_key="trial-cancel-0001")
        self.assertEqual(cancelled["status"], "cancelled")
        current = self.trials.get(self.owner, trial["trial_id"])
        self.assertEqual(self.ledger.get(current["attempts"][0]["call_id"])["status"], "refunded")
        with self.assertRaises(IM.ConflictError):
            self.trials.start_engine(self.owner, trial["trial_id"], expected_generation=claimed["generation"],
                                     lease_token=claimed["lease_token"])

    def test_recovery_before_engine_refunds_without_creating_another_attempt(self):
        trial = self.reserve()
        self.trials.claim(self.owner, trial["trial_id"], expected_generation=1, now=100, lease_seconds=10)
        result = self.trials.recover(self.owner, now=111)
        self.assertEqual(result["not_run"], 1)
        current = self.trials.get(self.owner, trial["trial_id"])
        self.assertEqual((current["status"], len(current["attempts"])), ("not_run", 1))
        self.assertEqual(self.ledger.get(current["attempts"][0]["call_id"])["status"], "refunded")
        self.assertEqual(self.trials.recover(self.owner, now=112)["not_run"], 0)

    def test_engine_marker_and_trial_transition_rollback_together_then_cancel_is_counted(self):
        trial, token = self.prepared()
        with self.rs._conn() as connection:
            connection.execute("CREATE TRIGGER fail_trial_start BEFORE UPDATE ON improvement_trial_attempts "
                "WHEN NEW.status='running' BEGIN SELECT RAISE(ABORT,'injected_atomic_failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.trials.start_engine(self.owner, trial["trial_id"], expected_generation=trial["generation"], lease_token=token)
        call = trial["attempts"][0]["call_id"]
        self.assertIsNone(self.ledger.get(call)["engine_at"])
        self.assertEqual(self.trials.get(self.owner, trial["trial_id"])["status"], "prepared")
        with self.rs._conn() as connection:
            connection.execute("DROP TRIGGER fail_trial_start")
        running = self.trials.start_engine(self.owner, trial["trial_id"], expected_generation=trial["generation"], lease_token=token)
        self.trials.cancel(self.owner, trial["trial_id"], expected_generation=running["generation"], event_key="cancel-after-engine")
        self.assertEqual(self.ledger.get(call)["status"], "interrupted")
        self.assertIsNotNone(self.ledger.get(call)["engine_at"])
        self.assertFalse(self.ledger.refund(call))

    def test_post_engine_recovery_is_unknown_and_keeps_the_same_attempt(self):
        trial, token = self.prepared()
        self.trials.start_engine(self.owner, trial["trial_id"], expected_generation=trial["generation"], lease_token=token)
        recovered = self.trials.recover(self.owner, now=time.time() + 61)
        self.assertEqual(recovered["unknown"], 1)
        current = self.trials.get(self.owner, trial["trial_id"])
        self.assertEqual((current["status"], len(current["attempts"])), ("unknown", 1))
        self.assertEqual(self.ledger.get(current["attempts"][0]["call_id"])["status"], "interrupted")

    def test_policy_revocation_after_prepare_blocks_query_marker_but_allows_cancellation(self):
        trial, token = self.prepared()
        self.assets.set_policy(self.owner, "off", expected_version=0, event_key="off-after-prepare")
        with self.assertRaises(PermissionError):
            self.trials.start_engine(self.owner, trial["trial_id"], expected_generation=trial["generation"], lease_token=token)
        self.trials.cancel(self.owner, trial["trial_id"], expected_generation=trial["generation"], event_key="cancel-revoked-trial")
        self.assertEqual(self.ledger.get(trial["attempts"][0]["call_id"])["status"], "refunded")

    def test_qualification_is_consumed_before_fixture_visibility_and_context_pin_is_complete(self):
        claim = self.cases.reserve_qualification(self.owner, self.request["case_set_id"], self.request["pins"],
                                                 event_key="qualification-for-trial")
        trial = self.reserve(case_id="case-2", qualification_id=claim["reservation_id"])
        claimed = self.trials.claim(self.owner, trial["trial_id"], expected_generation=1)
        with self.assertRaises(IM.ConflictError):
            self.trials.materialize(self.owner, trial["trial_id"], expected_generation=claimed["generation"],
                lease_token=claimed["lease_token"], baseline_context={**self.context, "coverage": "unknown"})
        with self.rs._conn() as connection:
            self.assertEqual(connection.execute("SELECT status FROM improvement_qualification").fetchone()[0], "reserved")
        manifest = self.trials.materialize(self.owner, trial["trial_id"], expected_generation=claimed["generation"],
            lease_token=claimed["lease_token"], baseline_context=self.context)
        with self.rs._conn() as connection:
            self.assertEqual(connection.execute("SELECT status FROM improvement_qualification").fetchone()[0], "consumed")
        self.assertEqual(manifest["learning_origin"], "qualification")
        self.assertNotIn("private-answer", json.dumps(manifest))
        self.assertNotIn("host-checker-v1", json.dumps(manifest))

    def test_forged_effective_hash_cannot_be_attested_by_changing_the_workspace_journal(self):
        trial = self.reserve()
        claimed = self.trials.claim(self.owner, trial["trial_id"], expected_generation=1)
        manifest = self.trials.materialize(self.owner, trial["trial_id"], expected_generation=claimed["generation"],
            lease_token=claimed["lease_token"], baseline_context=self.context)
        receipt = self.trials.workspace.prepare(trial["trial_id"], 1, manifest)
        receipt["effective_hash"] = "f" * 64
        _, journal = self.trials.workspace._paths(trial["trial_id"], 1)
        record = json.loads(journal.read_text())
        record["receipt"] = receipt
        journal.write_text(IM._json(record))
        with self.assertRaises((ValueError, IM.ConflictError)):
            self.trials.prepared(self.owner, trial["trial_id"], expected_generation=claimed["generation"],
                lease_token=claimed["lease_token"], receipt=receipt)
        self.assertIsNone(self.ledger.get(trial["attempts"][0]["call_id"])["engine_at"])

    def test_schema_two_metadata_reads_do_not_migrate_and_failed_upgrade_rolls_back(self):
        from unittest.mock import patch
        import improvement_trial_schema as schema
        self.assets.set_policy(self.owner, "off", expected_version=0, event_key="off-before-upgrade")
        with self.rs._conn() as connection:
            contract = connection.execute("SELECT id FROM improvement_contracts").fetchone()[0]
            # Construct a real schema2 fixture, without leaving later experiment tables behind.
            connection.execute("DROP TRIGGER improvement_preparation_arm_fence")
            connection.execute("DROP TRIGGER improvement_legacy_trial_view_fence")
            # Later add-only families first (canaries 12, activations 11, recipes 9, compose 8), so the fixture is a real schema2 store.
            for table in ("improvement_imports", "improvement_refinements", "improvement_transfers", "improvement_team_trials", "improvement_team_pins", "improvement_bundle_members", "improvement_bundle_activations", "improvement_agent_overlays", "improvement_agent_procedures", "improvement_routing_overlays", "improvement_routing_candidates", "improvement_canary_verdicts", "improvement_canary_exposures", "improvement_canaries",
                          "improvement_auto_scopes", "improvement_activations", "improvement_recipe_trial_refs", "improvement_recipe_states",
                          "improvement_recipes", "improvement_compositions", "improvement_compose_grants",
                          "improvement_compose_authorizations"):
                connection.execute("DROP TABLE " + table)
            for table in ("improvement_view_qualification_links", "improvement_view_trial_links", "improvement_comparison_views", "improvement_effective_view_assets", "improvement_effective_views",
                          "improvement_semantic_receipts", "improvement_generated_candidates", "improvement_proposal_publications",
                          "improvement_operation_results", "improvement_operation_observations", "improvement_operation_attempts",
                          "improvement_operations", "improvement_preparation_trial_links", "improvement_preparations",
                          "improvement_experiment_trial_links", "improvement_comparison_reports", "improvement_experiment_selections",
                          "improvement_comparisons", "improvement_experiment_arms", "improvement_experiments",
                          "improvement_skill_candidates", "improvement_candidate_authority_grants", "improvement_candidate_authorities",
                          "improvement_trial_context_grants", "improvement_trial_contexts", "improvement_trial_results", "improvement_trial_owner_decisions", "improvement_trial_artifacts", "improvement_trial_receipts", "improvement_trial_observations",
                          "improvement_trial_attempts", "improvement_trials"):
                connection.execute("DROP TABLE " + table)
            connection.execute("UPDATE improvement_schema SET version=2")
        self.assertEqual(self.cases.get_contract(self.owner, contract)["contract"]["version"], 1)
        with self.assertRaises(PermissionError):
            self.trials.get(self.owner, "missing-trial")
        self.assertEqual(IM._schema_version(self.rs), 2)
        with patch.object(schema, "SCHEMA", (*schema.SCHEMA, "INVALID TRIAL DDL")), self.assertRaises(sqlite3.OperationalError):
            IM.ensure(self.rs)
        self.assertEqual(IM._schema_version(self.rs), 2)
        with self.rs._conn() as connection:
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name='improvement_trials'").fetchone())
        IM.ensure(self.rs)
        self.assertEqual(IM._schema_version(self.rs), IM.SCHEMA_VERSION)
        self.assertEqual(self.assets.get_policy(self.owner), {"mode": "off", "version": 1})

    def test_preparation_requires_committed_exposure_before_the_input_can_be_used(self):
        trial = self.reserve()
        claimed = self.trials.claim(self.owner, trial["trial_id"], expected_generation=1)
        # Simulate a host bypassing the exposure transaction but obtaining the same bytes.
        with self.rs._conn() as connection:
            row = self.trials._row(connection, self.owner.brain_id, trial["trial_id"])
            manifest = self.trials._materialization(connection, row, self.context)
        receipt = self.trials.workspace.prepare(trial["trial_id"], 1, manifest)
        with self.assertRaises(IM.ConflictError):
            self.trials.prepared(self.owner, trial["trial_id"], expected_generation=claimed["generation"],
                lease_token=claimed["lease_token"], receipt=receipt)

    def test_waiting_for_database_cannot_authorize_a_query_after_the_lease_expires(self):
        trial, token = self.prepared()
        with self.rs._conn() as connection:
            expires = connection.execute("SELECT lease_until FROM improvement_trial_attempts").fetchone()[0]
        clock = [expires - 1]
        transaction = self.rs._Tx

        @contextmanager
        def delayed(store):
            with transaction(store) as connection:
                clock[0] = expires + 1
                yield connection

        with patch.object(self.rs, "_Tx", delayed), patch("time.time", side_effect=lambda: clock[0]):
            with self.assertRaises(IM.ConflictError):
                self.trials.start_engine(self.owner, trial["trial_id"], expected_generation=trial["generation"], lease_token=token)
        self.assertIsNone(self.ledger.get(trial["attempts"][0]["call_id"])["engine_at"])

    def test_heartbeat_extends_only_an_owned_live_lease_without_changing_generation(self):
        trial, token = self.prepared()
        with self.rs._conn() as connection:
            expires = connection.execute("SELECT lease_until FROM improvement_trial_attempts").fetchone()[0]
        beat = self.trials.heartbeat(self.owner, trial["trial_id"], expected_generation=trial["generation"],
            lease_token=token, now=expires - 1, lease_seconds=10)
        self.assertEqual(beat["generation"], trial["generation"])
        self.assertGreater(beat["lease_until"], expires)
        self.assertEqual(self.trials.recover(self.owner, now=expires + 1)["not_run"], 0)
        with self.assertRaises(IM.ConflictError):
            self.trials.heartbeat(self.owner, trial["trial_id"], expected_generation=trial["generation"],
                lease_token=token, now=expires + 10)

    def packet(self, trial, sequence=1, kind="worker_ready", **changes):
        with self.rs._conn() as connection:
            receipt = json.loads(connection.execute("SELECT workspace_json FROM improvement_trial_attempts "
                "WHERE trial_id=? AND attempt=1", (trial["trial_id"],)).fetchone()[0])
        payload = {"version": 1, "sequence": sequence, "type": kind, "trial_id": trial["trial_id"], "attempt": 1,
                   "input_hash": receipt["input_hash"]}
        if kind == "worker_ready":
            payload["capability_hash"] = "d" * 64
        elif kind in ("engine_event", "fixture_event"):
            payload["event"] = {"type": "usage", "usage": None}
        elif kind == "worker_complete":
            payload.update(fixture_events=[], tool_denials=[])
        return {**payload, **changes}

    def test_trace_is_immutable_idempotent_encrypted_and_scoped(self):
        trial, token = self.prepared()
        packet = self.packet(trial)
        arguments = {"expected_generation": trial["generation"], "lease_token": token}
        first = self.trials.append_observation(self.owner, trial["trial_id"], packet, **arguments)
        self.assertEqual(first, self.trials.append_observation(self.owner, trial["trial_id"], packet, **arguments))
        self.assertEqual(self.trials.read_observation(self.owner, trial["trial_id"], 1, 1), packet)
        with self.assertRaises(IM.ConflictError):
            self.trials.append_observation(self.owner, trial["trial_id"], {**packet, "capability_hash": "e" * 64}, **arguments)
        with self.assertRaises(PermissionError):
            self.trials.read_observation(self.other, trial["trial_id"], 1, 1)
        with self.rs._conn() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM improvement_trial_observations")

    def test_large_raw_packet_chunks_preserve_exact_bytes_and_missing_chunk_is_unknown(self):
        trial, token = self.prepared()
        packet = self.packet(trial, kind="engine_event", event={"type": "artifact", "content": "x" * (1024 * 1024) + "\r\n"})
        self.trials.append_observation(self.owner, trial["trial_id"], packet,
            expected_generation=trial["generation"], lease_token=token)
        self.assertEqual(self.trials.read_observation(self.owner, trial["trial_id"], 1, 1), packet)
        with self.rs._conn() as connection:
            hashes = json.loads(connection.execute("SELECT blob_hashes_json FROM improvement_trial_observations").fetchone()[0])
            self.assertGreater(len(hashes), 1)
        self.assets.blobs._path(self.owner.brain_id, hashes[-1]).unlink()
        with self.assertRaises(IM.AssetUnavailable):
            self.trials.read_observation(self.owner, trial["trial_id"], 1, 1)

    def test_late_trace_after_cancel_preserves_evidence_without_reopening_or_refunding(self):
        trial, token = self.prepared()
        self.trials.append_observation(self.owner, trial["trial_id"], self.packet(trial),
            expected_generation=trial["generation"], lease_token=token)
        running = self.trials.start_engine(self.owner, trial["trial_id"], expected_generation=trial["generation"], lease_token=token)
        cancelled = self.trials.cancel(self.owner, trial["trial_id"], expected_generation=running["generation"], event_key="cancel-trace-trial")
        packet = self.packet(trial, 2, "engine_event")
        with self.assertRaises(IM.ConflictError):
            self.trials.append_observation(self.owner, trial["trial_id"], packet,
                expected_generation=running["generation"], lease_token=token)
        result = self.trials.append_observation(self.owner, trial["trial_id"], packet, attempt=1, lease_token=token, late=True)
        self.assertTrue(result["late"])
        current = self.trials.get(self.owner, trial["trial_id"])
        self.assertEqual((current["status"], current["generation"]), ("cancelled", cancelled["generation"]))
        self.assertEqual(self.ledger.get(current["attempts"][0]["call_id"])["status"], "interrupted")

    def test_concurrent_trace_replay_and_identity_rejection_do_not_create_extra_rows(self):
        trial, token = self.prepared()
        packet = self.packet(trial)
        options = {"expected_generation": trial["generation"], "lease_token": token}
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.trials.append_observation(self.owner, trial["trial_id"], packet, **options), (1, 2)))
        self.assertEqual(results[0], results[1])
        for value, changes in ((self.packet(trial, 2, input_hash="f" * 64), {}),
                               (self.packet(trial, 2), {"lease_token": "forged"}),
                               (self.packet(trial, 3), {})):
            with self.subTest(changes=changes), self.assertRaises(IM.ConflictError):
                self.trials.append_observation(self.owner, trial["trial_id"], value, **{**options, **changes})
        with self.rs._conn() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM improvement_trial_observations").fetchone()[0], 1)

    def test_policy_revocation_rejects_heartbeat_without_erasing_existing_trace(self):
        trial, token = self.prepared()
        self.trials.append_observation(self.owner, trial["trial_id"], self.packet(trial),
            expected_generation=trial["generation"], lease_token=token)
        self.assets.set_policy(self.owner, "off", expected_version=0, event_key="revoke-heartbeat-policy")
        with self.assertRaises(PermissionError):
            self.trials.heartbeat(self.owner, trial["trial_id"], expected_generation=trial["generation"], lease_token=token)
        self.assertEqual(self.trials.read_observation(self.owner, trial["trial_id"], 1, 1)["type"], "worker_ready")

    def product_trace(self, *, content='{"value":"synthetic"}\r\n', extra_artifact=None, complete=True):
        trial, token = self.prepared()
        self.trials.append_observation(self.owner, trial["trial_id"], self.packet(trial),
            expected_generation=trial["generation"], lease_token=token)
        trial = self.trials.start_engine(self.owner, trial["trial_id"], expected_generation=trial["generation"], lease_token=token)
        receipt = {"version": 1, "trial_id": trial["trial_id"], "attempt": 1,
                   "input_hash": self.packet(trial)["input_hash"]}
        events = [{"type": "artifact", "content": content, "hash": fixtures.digest(content)},
                  {"type": "installation_receipt", "receipt": receipt, "hash": IM._hash(receipt)},
                  {"type": "terminal", "subtype": "success", "is_error": False, "artifact_status": "observed"}]
        if extra_artifact is not None:
            events.insert(1, {"type": "artifact", "content": extra_artifact, "hash": fixtures.digest(extra_artifact)})
        packets = [self.packet(trial, 2, "engine_start_requested")]
        packets.extend(self.packet(trial, index, "engine_event", event=event) for index, event in enumerate(events, 3))
        if complete:
            packets.append(self.packet(trial, len(packets) + 2, "worker_complete"))
        for packet in packets:
            self.trials.append_observation(self.owner, trial["trial_id"], packet,
                expected_generation=trial["generation"], lease_token=token)
        return trial, token, content.encode("utf-8"), receipt

    def test_completed_trace_stages_exact_artifact_and_receipt_without_settling_the_call(self):
        trial, token, raw, receipt = self.product_trace()
        evaluating = self.trials.stage_evaluation(self.owner, trial["trial_id"], expected_generation=trial["generation"], lease_token=token)
        self.assertEqual(evaluating["status"], "evaluating")
        artifact = self.trials.read_artifact(self.owner, trial["trial_id"], 1)
        self.assertEqual(artifact, raw)
        self.assertEqual(self.trials.read_receipt(self.owner, trial["trial_id"], 1), receipt)
        output = self.trials.workspace.root / trial["trial_id"] / "attempt-1" / "outputs" / "answer.json"
        self.assertEqual(output.read_bytes(), raw)
        self.assertEqual(self.ledger.get(trial["attempts"][0]["call_id"])["status"], "running")
        with self.rs._conn() as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM improvement_trial_artifacts")
        with self.assertRaises(PermissionError):
            self.trials.read_artifact(self.other, trial["trial_id"], 1)

    def test_ambiguous_or_incomplete_native_output_cannot_be_staged_as_a_completed_product(self):
        trial, token, _, _ = self.product_trace(extra_artifact="different final output")
        with self.assertRaises(IM.ConflictError):
            self.trials.stage_evaluation(self.owner, trial["trial_id"], expected_generation=trial["generation"], lease_token=token)
        with self.rs._conn() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM improvement_trial_artifacts").fetchone()[0], 0)

    def test_missing_worker_completion_keeps_the_product_unstaged(self):
        trial, token, _, _ = self.product_trace(complete=False)
        with self.assertRaises(IM.ConflictError):
            self.trials.stage_evaluation(self.owner, trial["trial_id"], expected_generation=trial["generation"], lease_token=token)

    def test_changed_output_is_not_overwritten_during_idempotent_evaluation_resume(self):
        trial, token, _, _ = self.product_trace()
        evaluating = self.trials.stage_evaluation(self.owner, trial["trial_id"], expected_generation=trial["generation"], lease_token=token)
        output = self.trials.workspace.root / trial["trial_id"] / "attempt-1" / "outputs" / "answer.json"
        output.write_bytes(b"Owner edit in scratch output")
        with self.assertRaises(IM.ConflictError):
            self.trials.stage_evaluation(self.owner, trial["trial_id"], expected_generation=evaluating["generation"], lease_token=token)
        self.assertEqual(output.read_bytes(), b"Owner edit in scratch output")

    def test_concurrent_owner_output_publication_wins_without_being_replaced(self):
        import improvement_trial_products as products
        trial, token, _, _ = self.product_trace()
        output = self.trials.workspace.root / trial["trial_id"] / "attempt-1" / "outputs" / "answer.json"

        def competing_writer(source, destination):
            output.write_bytes(b"Concurrent owner output")
            raise FileExistsError("owner won publication")

        with patch.object(products.os, "link", side_effect=competing_writer), self.assertRaises(IM.ConflictError):
            self.trials.stage_evaluation(self.owner, trial["trial_id"], expected_generation=trial["generation"], lease_token=token)
        self.assertEqual(output.read_bytes(), b"Concurrent owner output")
        with self.rs._conn() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM improvement_trial_artifacts").fetchone()[0], 0)

    def test_host_abort_before_marker_refunds_with_durable_bounded_reason(self):
        trial, token = self.prepared()
        result = self.trials.abort(self.owner, trial["trial_id"], expected_generation=trial["generation"],
                                  lease_token=token, reason="unsupported_configuration")
        self.assertEqual(result["status"], "not_run")
        self.assertEqual(result["attempts"][0]["failure_reason"], "unsupported_configuration")
        self.assertEqual(self.ledger.get(trial["attempts"][0]["call_id"])["status"], "refunded")

    def test_expired_host_writer_can_close_a_started_call_but_cannot_refund(self):
        trial, token = self.prepared()
        running = self.trials.start_engine(self.owner, trial["trial_id"], expected_generation=trial["generation"], lease_token=token)
        with self.rs._conn() as connection:
            connection.execute("UPDATE improvement_trial_attempts SET lease_until=1 WHERE trial_id=?", (trial["trial_id"],))
        with self.assertRaises(IM.ConflictError):
            self.trials.abort(self.owner, trial["trial_id"], expected_generation=running["generation"],
                              lease_token="forged", reason="worker_failed")
        result = self.trials.abort(self.owner, trial["trial_id"], expected_generation=running["generation"],
                                  lease_token=token, reason="worker_failed")
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(self.ledger.get(trial["attempts"][0]["call_id"])["status"], "interrupted")
        self.assertFalse(self.ledger.refund(trial["attempts"][0]["call_id"]))

    def test_host_abort_does_not_rewrite_external_cancellation_or_accept_arbitrary_reason(self):
        trial, token = self.prepared()
        with self.assertRaises(ValueError):
            self.trials.abort(self.owner, trial["trial_id"], expected_generation=trial["generation"],
                              lease_token=token, reason="arbitrary raw secret or exception text")
        cancelled = self.trials.cancel(self.owner, trial["trial_id"], expected_generation=trial["generation"], event_key="external-cancel-abort")
        result = self.trials.abort(self.owner, trial["trial_id"], expected_generation=trial["generation"],
                                  lease_token=token, reason="cancelled")
        self.assertEqual(result, cancelled)

    def test_rejected_unclaimed_reservation_refunds_after_policy_revocation(self):
        trial = self.reserve()
        self.assets.set_policy(self.owner, "off", expected_version=0, event_key="revoke-before-host-claim")
        result = self.trials.reject_unclaimed(self.owner, trial["trial_id"], expected_generation=1, reason="authority_changed")
        self.assertEqual(result["status"], "not_run")
        self.assertEqual(result["attempts"][0]["failure_reason"], "authority_changed")
        self.assertEqual(self.ledger.get(trial["attempts"][0]["call_id"])["status"], "refunded")
        self.assertEqual(self.trials.reject_unclaimed(self.owner, trial["trial_id"], expected_generation=1,
                                                      reason="authority_changed"), result)

    def test_unclaimed_rejection_cannot_close_another_hosts_claim(self):
        trial = self.reserve()
        self.trials.claim(self.owner, trial["trial_id"], expected_generation=1)
        current = self.trials.get(self.owner, trial["trial_id"])
        for generation in (1, current["generation"]):
            with self.subTest(generation=generation), self.assertRaises(IM.ConflictError):
                self.trials.reject_unclaimed(self.owner, trial["trial_id"], expected_generation=generation, reason="authority_changed")
        self.assertEqual(self.trials.get(self.owner, trial["trial_id"]), current)
        self.assertEqual(self.ledger.get(trial["attempts"][0]["call_id"])["status"], "reserved")

    def test_unclaimed_rejection_rolls_back_refund_if_reason_event_fails(self):
        trial = self.reserve()
        with self.rs._conn() as connection:
            connection.execute("CREATE TRIGGER reject_failure BEFORE INSERT ON improvement_events "
                "WHEN NEW.operation='trial_reject' BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.trials.reject_unclaimed(self.owner, trial["trial_id"], expected_generation=1, reason="authority_changed")
        self.assertEqual(self.trials.get(self.owner, trial["trial_id"])["status"], "reserved")
        self.assertEqual(self.ledger.get(trial["attempts"][0]["call_id"])["status"], "reserved")


if __name__ == "__main__":
    unittest.main()
