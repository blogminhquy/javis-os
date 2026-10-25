"""Actual compose Records/Execution ownership; no native/query readiness claim.

Permission fixture is real private two-arm SQL/Fernet/host history with explicitly
synthetic_storage_fixture cells. Declared verifier True/False controls below test
only actual reservation/lease/refund; the format2 selector seam tests storage and
PREPARED ownership, never source qualification, a native ACK or a model call.
Positive operations and immutable creation events are written by OperationRecords.
"""
from _paths import ROOT, SERVER  # noqa: F401

import inspect
import json
import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

import improvement_store as IM
import improvement_native_protocol as native_wire
from improvement_compose_inputs import ComposeInputs
from improvement_compose_permissions import ComposePermissions
from improvement_native_formats import input_version
from improvement_operation_adapter import ClaudeOperationAdapter
from improvement_operation_execution import OperationExecution
from improvement_operation_profile import operation_user_prompt
from improvement_operation_records import OperationRecords
from improvement_trial_service import OwnerTrialService
import test_improvement_compose_permissions as permissions
import test_improvement_operation_workspace as workspace


DENIED = (*permissions.DENIED, sqlite3.IntegrityError)


class ComposeAdmissionTests(unittest.TestCase):
    def setUp(self):
        parameter = inspect.signature(ComposePermissions.current).parameters.get('operation')
        self.assertIsNotNone(parameter, 'Compose current cannot authenticate its actual owned operation mutation')
        self.assertIsNone(parameter.default, 'Operation normalization must be an explicit optional argument')
        self.f = permissions.ComposePermissionTests()
        self.f.setUp()
        self.addCleanup(lambda: self.assertTrue(self.f.doCleanups(), 'Permission fixture cleanup failed'))
        self.owner, self.assets, self.store = self.f.owner, self.f.assets, self.f.store
        self.saved = self.f.authorize()
        self.records = OperationRecords(self.assets)
        self.enterContext(patch('subprocess.run', side_effect=lambda *a, **kw: workspace._acl_only(workspace._REAL_RUN, *a, **kw)))
        self.enterContext(patch('subprocess.Popen', side_effect=lambda *a, **kw: workspace._acl_only(workspace._REAL_POPEN, *a, **kw)))
        self.execution = OperationExecution(self.f.f.plans, OwnerTrialService(self.f.f.plan_fixture.host))
        self.before_counts = self.f.counts_without_exposures()

    def request(self, **changes):
        return {'version': 2, 'experiment_id': self.saved['experiment_id'], 'context_id': self.saved['context_id'],
            'definition_hash': self.f.f.lineage.created['definition_hash'], 'kind': 'compose',
            'role': 'composer', 'purpose': 'improve_compose', 'candidate_id': None, 'parent_id': None,
            'input_hash': self.saved['input_hash'], 'compose_authorization_id': self.saved['authorization_id'], **changes}

    def create(self, *, request=None, key='actual-owner-compose-operation', owner=None):
        principal = self.owner if owner is None else owner
        value = self.request() if request is None else request
        with self.store._Tx(self.store) as connection:
            # The concrete host checks full source permission, then actual Records
            # writes metadata/event in this same transaction, not a caller op row.
            self.f.service.current(connection, principal, value['compose_authorization_id'])
            return self.records._create_in(connection, principal, value, value['input_hash'],
                expected_generation=self.saved['experiment_generation'], event_key=key)

    def raw_operation(self, connection, identifier):
        return self.execution._row(connection, self.owner, identifier)

    def reserve_and_claim(self, operation):
        with patch.object(ClaudeOperationAdapter, 'verify', return_value={'supported': True, 'capability_hash': 'c' * 64}):
            reserved = self.execution.reserve(self.owner, operation['operation_id'], expected_generation=operation['generation'],
                event_key='declared-synthetic-compose-reserve')
        claim = self.execution.claim(self.owner, operation['operation_id'], expected_generation=reserved['generation'], lease_seconds=300)
        return reserved, claim

    def assert_no_new_call(self):
        self.assertEqual(self.f.counts_without_exposures(), self.before_counts)
        with closing(self.store._conn()) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM agent_calls WHERE purpose='improve_compose'").fetchone()[0], 0)

    def test_actual_pending_records_event_and_only_owned_experiment_mutation_are_accepted(self):
        with closing(self.store._conn()) as connection:
            before = dict(connection.execute('SELECT * FROM improvement_experiments').fetchone())
        operation = self.create()
        self.assertEqual((operation['kind'], operation['role'], operation['purpose'], operation['status'], operation['attempt']),
                         ('compose', 'composer', 'improve_compose', 'pending', 0))
        with closing(self.store._conn()) as connection:
            raw = self.raw_operation(connection, operation['operation_id'])
            after = dict(connection.execute('SELECT * FROM improvement_experiments').fetchone())
            self.assertEqual(after, {**before, 'generation': before['generation'] + 1, 'updated_at': raw['created_at']})
            events = [dict(row) for row in connection.execute("SELECT * FROM improvement_events WHERE operation='operation_create'")]
            self.assertEqual(len(events), 1)
            expected_payload = {'request': self.request(), 'input_blob_hash': self.saved['input_hash'],
                                'expected_generation': self.saved['experiment_generation']}
            self.assertEqual(events[0]['request_hash'], IM._hash(expected_payload))
            self.assertEqual(json.loads(events[0]['result_json']), operation)
            before_events = self.f.rows('improvement_events')
            with patch.object(ComposeInputs, 'build', side_effect=AssertionError('Own operation guard cannot rebuild input')):
                current = self.f.service.current(connection, self.owner, self.saved['authorization_id'], operation=raw)
                self.assertEqual(current['data']['kind'], 'body_compose_projection')
                self.assertEqual(IM._hash(current['data']), self.saved['input_hash'])
                self.execution.guard(self.owner, operation['operation_id'])
            self.assertEqual(self.f.rows('improvement_events'), before_events)
        with self.assertRaises(DENIED), self.store._Tx(self.store) as connection:
            self.records._create_in(connection, self.owner, self.request(), self.saved['input_hash'],
                expected_generation=before['generation'] + 1, event_key='ordinary-second-compose-refused')
        self.assertEqual(len(self.f.rows('improvement_operations')), 1)
        self.assert_no_new_call()

    def test_foreign_revoked_or_input_mismatched_creation_has_no_partial_operation_or_call(self):
        for value, principal in ((self.request(compose_authorization_id='icpa_foreign'), self.owner),
                                  (self.request(input_hash='f' * 64), self.owner),
                                  (self.request(), self.f.f.host_files.other)):
            with self.subTest(request=value, principal=principal), self.assertRaises(DENIED):
                self.create(request=value, owner=principal)
        self.f.service.revoke(self.owner, self.saved['authorization_id'], expected_generation=1,
                              event_key='revoke-before-compose-creation')
        with self.assertRaises(DENIED): self.create()
        self.assertEqual(self.f.rows('improvement_operations'), [])
        self.assertFalse(any(row['operation'] == 'operation_create' for row in self.f.rows('improvement_events')))
        self.assert_no_new_call()

    def test_extra_generation_and_duplicate_creation_history_cannot_be_normalized(self):
        operation = self.create()
        class RollbackControl(Exception): pass
        with self.assertRaises(RollbackControl), self.store._Tx(self.store) as connection:
            connection.execute('UPDATE improvement_experiments SET generation=generation+1')
            raw = self.raw_operation(connection, operation['operation_id'])
            with self.assertRaises(DENIED):
                self.f.service.current(connection, self.owner, self.saved['authorization_id'], operation=raw)
            with self.assertRaises(DENIED): self.execution._current(connection, self.owner, raw)
            raise RollbackControl()
        # Intentionally duplicate immutable history is a refusal-only negative.
        # The real positive operation and its first event came from Records.
        with self.assertRaises(RollbackControl), self.store._Tx(self.store) as connection:
            payload = {'request': self.request(), 'input_blob_hash': self.saved['input_hash'],
                       'expected_generation': self.saved['experiment_generation']}
            self.assets._event(connection, self.owner, 'duplicate-operation-create-invalid-history', 'operation_create', payload, operation)
            raw = self.raw_operation(connection, operation['operation_id'])
            with self.assertRaises(DENIED):
                self.f.service.current(connection, self.owner, self.saved['authorization_id'], operation=raw)
            with self.assertRaises(DENIED): self.execution._current(connection, self.owner, raw)
            raise RollbackControl()
        self.execution.guard(self.owner, operation['operation_id'])
        self.assert_no_new_call()

    def test_revoke_pending_denies_reserve_before_verifier_but_cold_metadata_and_cancel_remain(self):
        operation = self.create()
        revoked = self.f.service.revoke(self.owner, self.saved['authorization_id'], expected_generation=1,
                                        event_key='revoke-pending-compose')
        with patch.object(ClaudeOperationAdapter, 'verify', side_effect=AssertionError('Revoked consent reached native verifier')) as verifier:
            with self.assertRaises(DENIED):
                self.execution.reserve(self.owner, operation['operation_id'], expected_generation=operation['generation'],
                                       event_key='refuse-revoked-compose-reserve')
        verifier.assert_not_called()
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Cold metadata/cancel cannot decrypt')):
            self.assertEqual(self.f.service.get(self.owner, self.saved['authorization_id']), revoked)
            self.assertEqual(self.records.get(self.owner, operation['operation_id'])['status'], 'pending')
            stopped = self.execution.cancel(self.owner, operation['operation_id'], expected_generation=operation['generation'],
                                            event_key='cancel-revoked-pending-compose')
        self.assertEqual(stopped['status'], 'cancelled')
        self.assert_no_new_call()

    def test_unsupported_reserve_has_no_call_then_real_lease_default_format_refuses_and_abort_refunds(self):
        operation = self.create()
        with patch.object(ClaudeOperationAdapter, 'verify', return_value={'supported': False}):
            with self.assertRaisesRegex(ValueError, 'operation_native_unavailable'):
                self.execution.reserve(self.owner, operation['operation_id'], expected_generation=operation['generation'],
                                       event_key='unsupported-compose-no-call')
        self.assert_no_new_call()
        reserved, claim = self.reserve_and_claim(operation)
        call_id = reserved['attempts'][-1]['call_id']
        self.assertEqual((self.execution.ledger.get(call_id)['purpose'], claim['status']), ('improve_compose', 'reserved'))
        self.assertEqual(input_version(self.f.f.host_files.engine, 'operation'), 1, 'actual legacy-profile selector stays unchanged')
        with self.assertRaisesRegex(ValueError, 'compose_native_input2_required'):
            self.execution.materialize(self.owner, operation['operation_id'], expected_generation=claim['generation'],
                                       lease_token=claim['lease_token'])
        stopped = self.execution.abort(self.owner, operation['operation_id'], expected_generation=claim['generation'],
                                       lease_token=claim['lease_token'], reason='unsupported_configuration')
        self.assertEqual(stopped['status'], 'not_run')
        call = self.execution.ledger.get(call_id)
        self.assertEqual(call['status'], 'refunded')
        self.assertIsNone(call['engine_at'])
        self.assertIsNone(stopped['attempts'][-1]['workspace_json'])

    def test_declared_native2_storage_prepared_grammar_and_upstream_prompt_revoke_blocks_engine_marker(self):
        operation = self.create()
        reserved, claim = self.reserve_and_claim(operation)
        identifier, token = operation['operation_id'], claim['lease_token']
        # Fixture DI controls the format only, not registration/model/native ACK.
        with patch('improvement_native_formats.input_version', return_value=2):
            manifest = self.execution.materialize(self.owner, identifier, expected_generation=claim['generation'], lease_token=token)
            receipt = self.execution.workspace.prepare(identifier, 1, manifest)
            self.addCleanup(lambda: self.assertTrue(self.execution.workspace.cleanup_proven(identifier, 1, receipt)))
            prepared = self.execution.prepared(self.owner, identifier, expected_generation=claim['generation'],
                                                lease_token=token, receipt=receipt)
        self.assertEqual((manifest['version'], prepared['status']), (2, 'prepared'))
        self.assertEqual(self.execution.workspace.validate(receipt), manifest)
        prompt = json.loads(operation_user_prompt(manifest))
        self.assertEqual(prompt['compose_task']['evidence_projection'], manifest['data'])
        self.assertIn('checkpoint 1 of 1', prompt['compose_task']['upstream_method'])
        self.assertEqual(native_wire._identity('operation', receipt),
                         {key: receipt[key] for key in ('operation_id', 'attempt', 'role', 'purpose', 'input_hash')})
        with self.assertRaises(ValueError): native_wire._identity('operation', {**receipt, 'purpose': 'improve_propose'})
        self.f.service.revoke(self.owner, self.saved['authorization_id'], expected_generation=1, event_key='revoke-prepared-compose')
        with self.assertRaises(DENIED):
            self.execution.start_engine(self.owner, identifier, expected_generation=prepared['generation'], lease_token=token)
        stopped = self.execution.abort(self.owner, identifier, expected_generation=prepared['generation'],
                                       lease_token=token, reason='authority_changed')
        call = self.execution.ledger.get(stopped['attempts'][-1]['call_id'])
        self.assertEqual((stopped['status'], call['status']), ('not_run', 'refunded'))
        self.assertIsNone(call['engine_at'])


if __name__ == '__main__': unittest.main()
