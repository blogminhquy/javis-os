"""Actual SQLite/encrypted observation2 storage; no native/provider calls."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import hashlib
import json
import time
import unittest
from contextlib import closing
from unittest.mock import patch

import improvement_store as IM
from improvement_blobs import AssetUnavailable
import test_improvement_trials as T
import test_improvement_operation_execution as O
import test_improvement_native_observation as P


class StorageCases:
    def append(self, packet, **changes):
        return self.evidence.append(self.owner, self.identifier, packet,
            **{'lease_token': self.token, 'expected_generation': self.row['generation'], **changes})

    def read(self, sequence):
        return self.evidence.read(self.owner, self.identifier, 1, sequence)

    def worker(self, sequence=2, source_sequence=1, kind='engine_event'):
        body = {'type': kind, **{key: self.receipt[key] for key in self.identity_keys}}
        if kind == 'engine_event': body['event'] = {'type': 'usage', 'usage': None, 'content': 'Đối soát 😀\r\n\x00'}
        if kind == 'worker_ready': body['capability_hash'] = 'd' * 64
        if kind == 'worker_complete':
            body['tool_denials'] = []
            if self.kind == 'trial': body['fixture_events'] = []
        return P.packet(body, sequence=sequence, source='worker', source_sequence=source_sequence)

    def old_packet(self, sequence=1):
        return {'version': 1, 'sequence': sequence, 'type': 'worker_ready', 'capability_hash': 'd' * 64,
                **{key: self.receipt[key] for key in self.identity_keys}}

    def rows(self):
        with closing(self.store._conn()) as connection:
            return connection.execute('SELECT * FROM ' + self.table + ' WHERE ' + self.id_column +
                '=? AND attempt=1 ORDER BY sequence', (self.identifier,)).fetchall()

    def terminal(self):
        self.row = self.execution.start_engine(self.owner, self.identifier,
            expected_generation=self.row['generation'], lease_token=self.token)
        if self.kind == 'trial':
            return self.execution.cancel(self.owner, self.identifier,
                expected_generation=self.row['generation'], event_key='storage-cancel')
        return self.execution.abort(self.owner, self.identifier,
            expected_generation=self.row['generation'], lease_token=self.token, reason='cancelled')

    def test_v2_encrypted_roundtrip_metadata_exact_hash_defensive_and_replay(self):
        first = self.append(P.offer())
        value = self.worker(); saved = self.append(value)
        self.assertEqual(saved['kind'], 'engine_event')
        self.assertEqual(saved['payload_hash'], hashlib.sha256(P.canonical(value)).hexdigest())
        self.assertEqual(self.append(value), saved); self.assertEqual(self.append(P.offer()), first)
        observed = self.read(2); self.assertEqual(observed, value)
        observed['body']['event']['content'] = 'mutated'
        self.assertEqual(self.read(2), value)
        self.assertEqual([row['kind'] for row in self.rows()], ['launch_offer', 'engine_event'])
        hashes = json.loads(self.rows()[1]['blob_hashes_json'])
        self.assertNotEqual(self.blobs._path(self.owner.brain_id, hashes[0]).read_bytes(), P.canonical(value))
        other = copy.deepcopy(value); other['body']['event']['usage'] = {'input_tokens': 9}
        with self.assertRaises(IM.ConflictError): self.append(other)

    def test_v2_completion_permits_actual_drain_then_freezes_active_trace(self):
        self.append(P.offer()); self.append(self.worker(kind='worker_complete'))
        drained = P.packet({'type': 'drained', 'root_terminal': True, 'debug_exit': True,
            'job_active': 0, 'guards_closed': True, 'reason': 'completed'}, sequence=3, source_sequence=2)
        saved = self.append(drained); self.assertEqual(saved['kind'], 'drained')
        self.assertEqual(self.append(drained), saved)
        with self.assertRaises(IM.ConflictError): self.append(self.worker(4, 2))

    def test_no_v1_packet_can_join_v2_attempt(self):
        self.append(P.offer())
        with self.assertRaises((ValueError, IM.ConflictError)): self.append(self.old_packet(2))
        self.assertEqual(len(self.rows()), 1)

    def test_no_v2_replay_or_append_can_join_v1_attempt(self):
        first = self.append(self.old_packet())
        with self.assertRaises((ValueError, IM.ConflictError)): self.append(P.offer())
        value = self.worker()
        with self.assertRaises((ValueError, IM.ConflictError)): self.append(value)
        self.assertEqual(self.append(self.old_packet()), first)

    def test_v2_foreign_incarnation_identity_and_global_source_gap_refuse(self):
        self.append(P.offer())
        invalid = [self.worker(3), self.worker(2, 2), {**self.worker(), 'worker_birth': 401},
            {**self.worker(), 'launch_nonce': '9' * 64}]
        foreign = self.worker(); foreign['body']['input_hash'] = 'f' * 64; invalid.append(foreign)
        for value in invalid:
            with self.subTest(value=value), self.assertRaises((ValueError, IM.ConflictError)): self.append(value)
        self.assertEqual(len(self.rows()), 1)

    def test_late_gapped_usage_requires_original_writer_and_never_reopens_authority(self):
        self.append(P.offer()); stopped = self.terminal()
        value = self.worker(9, 7)
        with self.assertRaises(IM.ConflictError): self.append(value)
        with self.assertRaises(IM.ConflictError): self.append(value, late=True, attempt=1, lease_token='foreign')
        saved = self.append(value, late=True, attempt=1)
        self.assertTrue(saved['late']); self.assertEqual(self.read(9), value)
        self.append(self.worker(5, 3), late=True, attempt=1)
        self.assertEqual(self.append(value, late=True, attempt=1), saved)
        current = self.execution.get(self.owner, self.identifier)
        self.assertEqual((current['status'], current['generation']), (stopped['status'], stopped['generation']))
        self.assertEqual(self.execution.ledger.get(current['attempts'][0]['call_id'])['status'], 'interrupted')

    def test_late_usage_without_first_binding_anchor_fails_explicitly(self):
        self.terminal()
        with self.assertRaisesRegex((ValueError, IM.ConflictError), 'binding_anchor_missing'):
            self.append(self.worker(9, 7), late=True, attempt=1)
        self.assertEqual(self.rows(), [])

    def test_prior_encrypted_anchor_must_verify_for_read_append_and_replay(self):
        self.append(P.offer())
        hashes = json.loads(self.rows()[0]['blob_hashes_json'])
        self.blobs._path(self.owner.brain_id, hashes[0]).unlink()
        for action in (lambda: self.read(1), lambda: self.append(self.worker()), lambda: self.append(P.offer())):
            with self.subTest(action=action), self.assertRaises(AssetUnavailable): action()

    def test_v2_second_lease_check_after_actual_encrypted_write_prevents_commit(self):
        self.append(P.offer())
        with closing(self.store._conn()) as connection:
            until = connection.execute('SELECT lease_until FROM ' + self.attempt_table + ' WHERE ' +
                self.id_column + '=? AND attempt=1', (self.identifier,)).fetchone()[0]
        clock = [until - 1]; original = self.blobs.write
        def delayed(*args, **kwargs):
            result = original(*args, **kwargs); clock[0] = until + 1; return result
        with patch.object(time, 'time', side_effect=lambda: clock[0]), patch.object(self.blobs, 'write', side_effect=delayed):
            with self.assertRaises(IM.ConflictError): self.append(self.worker())
        self.assertEqual(len(self.rows()), 1)


class TrialObservationStorageTests(StorageCases, unittest.TestCase):
    def setUp(self):
        from improvement_trial_evidence import TrialEvidence
        self.fixture = T.TrialStoreTests(); self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.execution = self.fixture.trials
        self.row, self.token = self.fixture.prepared()
        self.owner, self.store, self.blobs = self.fixture.owner, self.fixture.rs, self.fixture.assets.blobs
        self.kind, self.id_column = 'trial', 'trial_id'
        self.table, self.attempt_table = 'improvement_trial_observations', 'improvement_trial_attempts'
        self.identifier = self.row['trial_id']; self.evidence = TrialEvidence(self.execution)
        self.identity_keys = ('trial_id', 'attempt', 'input_hash')
        with closing(self.store._conn()) as connection:
            self.receipt = json.loads(connection.execute('SELECT workspace_json FROM improvement_trial_attempts WHERE trial_id=? AND attempt=1',
                (self.identifier,)).fetchone()[0])


class OperationObservationStorageTests(StorageCases, unittest.TestCase):
    def setUp(self):
        from improvement_operation_evidence import OperationEvidence
        self.fixture = O.OperationExecutionTests(); self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.execution = self.fixture.execution()
        self.row, self.token, self.receipt = self.fixture.prepared(self.execution)
        self.owner, self.store, self.blobs = self.fixture.owner, self.fixture.store, self.fixture.assets.blobs
        self.kind, self.id_column = 'operation', 'operation_id'
        self.table, self.attempt_table = 'improvement_operation_observations', 'improvement_operation_attempts'
        self.identifier = self.row['operation_id']; self.evidence = OperationEvidence(self.execution)
        self.identity_keys = ('operation_id', 'attempt', 'role', 'purpose', 'input_hash')


if __name__ == '__main__': unittest.main()
