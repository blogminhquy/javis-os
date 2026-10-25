"""Actual SQLite and encrypted blobs for host image decisions; no native launch."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import hashlib
import importlib
import json
import unittest
from contextlib import closing
from unittest.mock import patch

import test_improvement_store as fixture
import test_improvement_native_observation as grammar
import improvement_store as IM
from improvement_blobs import AssetUnavailable

try:
    decisions = importlib.import_module('improvement_native_decisions')
except ModuleNotFoundError as error:
    if error.name != 'improvement_native_decisions': raise
    decisions = None


def joined():
    image = grammar.image()
    body = image['body']
    image = {key: value for key, value in image.items() if key not in ('source', 'source_sequence', 'body')}
    image.update(body)
    dispatch = {'version': 1, 'purpose': 'query', 'basis': 'native_argument_consistency',
        'argument_consistency': {'synthetic_private_marker': 'PRIVATE_DISPATCH_\u0111\u1ed1i_so\u00e1t\r\n'},
        'environment_hash': 'e' * 64, 'source_policy_hash': 'a' * 64}
    return {'version': 2, 'launch_nonce': image['launch_nonce'], 'worker_pid': image['worker_pid'],
        'worker_birth': image['worker_birth'], **{key: body[key] for key in
            ('purpose', 'nonce', 'native_pid', 'native_birth', 'observation_hash')},
        'dispatch_hash': hashlib.sha256(grammar.canonical(dispatch)).hexdigest(),
        'dispatch': dispatch, 'image': image}


class DecisionStoreTests(unittest.TestCase):
    def setUp(self):
        fixture.ImprovementStoreTests.setUp(self)
        IM.ensure(self.rs)
        self.assertIsNotNone(decisions, 'durable native decision store missing')
        self.decisions = decisions.NativeImageDecisionStore(self.store)
        self.scope = '9' * 64
        self.calls = []

    def current(self, connection, observation):
        self.calls.append(connection)
        if self.store._policy(connection, 'brain-a')['version'] != 0:
            raise IM.ConflictError('current_authority_changed')
        self.assertEqual(observation['dispatch']['source_policy_hash'], 'a' * 64)
        return 'allow'

    def persist(self, value=None, **kwargs):
        return self.decisions.persist(self.owner, joined() if value is None else value,
            scope_hash=self.scope, current=kwargs.pop('current', self.current), **kwargs)

    def rows(self):
        with closing(self.rs._conn()) as connection:
            return [dict(row) for row in connection.execute('SELECT * FROM improvement_events')]

    def record(self): return json.loads(self.rows()[0]['result_json'])

    def test_actual_encrypted_record_and_public_hash_only_audit(self):
        value = joined()
        result = self.persist(value)
        self.assertEqual(set(result), {'decision', 'durable_evidence_hash'})
        self.assertEqual(result['decision'], 'allow')
        record = self.record()
        self.assertEqual(result['durable_evidence_hash'], IM._hash(record))
        raw = b''.join(self.blobs.read('brain-a', digest) for digest in record['blob_hashes'])
        self.assertEqual(json.loads(raw), value)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), record['joined_hash'])
        self.assertNotIn('PRIVATE_DISPATCH', self.rows()[0]['result_json'])
        files = list((self.root / 'assets').rglob('*.enc'))
        self.assertTrue(files)
        self.assertTrue(all(path.read_text('ascii').startswith('enc:') for path in files))
        self.assertEqual(len(self.calls), 2)

    def test_exact_replay_rechecks_current_authority_and_does_not_duplicate_event(self):
        first = self.persist()
        self.assertEqual(self.persist(), first)
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(len(self.calls), 4)
        self.store.set_policy(self.owner, 'off', expected_version=0, event_key='policy-change-1')
        with self.assertRaisesRegex(IM.ConflictError, 'current_authority_changed'): self.persist()
        self.assertEqual(len(self.rows()), 2)

    def test_replay_refuses_changed_dispatch_and_missing_encrypted_evidence(self):
        self.persist()
        altered = joined()
        altered['dispatch']['argument_consistency']['synthetic_private_marker'] = 'changed'
        altered['dispatch_hash'] = hashlib.sha256(grammar.canonical(altered['dispatch'])).hexdigest()
        with self.assertRaises(IM.ConflictError): self.persist(altered)
        self.blobs._path('brain-a', self.record()['blob_hashes'][0]).unlink()
        with self.assertRaises(AssetUnavailable): self.persist()
        self.assertEqual(len(self.rows()), 1)

    def test_authority_is_checked_again_after_actual_blob_write(self):
        original_write = self.blobs.write
        def changed_during_write(brain, raw):
            digest = original_write(brain, raw)
            self.calls[-1].execute("INSERT INTO improvement_policies VALUES('brain-a','off',1)")
            return digest
        with patch.object(self.blobs, 'write', side_effect=changed_during_write):
            with self.assertRaisesRegex(IM.ConflictError, 'current_authority_changed'): self.persist()
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.rows(), [])

    def test_mismatch_is_durably_denied_even_if_current_callback_allows(self):
        value = joined()
        image = value['image']
        image['comparison']['actual']['sha256'] = 'd' * 64
        image['comparison']['matches'] = False
        material = {key: image[key] for key in ('launch_nonce', 'worker_pid', 'worker_birth')}
        material.update({key: item for key, item in image.items() if key not in
            ('version', 'type', 'sequence', 'launch_nonce', 'worker_pid', 'worker_birth', 'observation_hash')})
        value['observation_hash'] = image['observation_hash'] = hashlib.sha256(grammar.canonical(material, ascii=True)).hexdigest()
        self.assertEqual(self.persist(value)['decision'], 'deny')
        self.assertEqual(self.record()['decision'], 'deny')

    def test_closed_binding_hash_and_scope_refusals_precede_any_event(self):
        mutations = [lambda value: value.update(native_pid=True),
            lambda value: value.update(worker_birth=401),
            lambda value: value.update(dispatch_hash='0' * 64),
            lambda value: value['image'].update(observation_hash='0' * 64),
            lambda value: value.update(unexpected='raw-capability')]
        for mutate in mutations:
            value = joined(); mutate(value)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError): self.persist(value)
        with self.assertRaises(ValueError):
            self.decisions.persist(self.owner, joined(), scope_hash='invalid', current=self.current)
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.calls, [])

    def test_callback_cannot_mutate_retained_raw_observation_and_replay_allow_cannot_change(self):
        value = joined()
        expected = copy.deepcopy(value)
        def mutable_current(connection, observation):
            result = self.current(connection, observation)
            observation['dispatch']['argument_consistency'].clear()
            return result
        self.persist(value, current=mutable_current)
        self.assertEqual(value, expected)
        record = self.record()
        self.assertEqual(json.loads(self.blobs.read('brain-a', record['blob_hashes'][0])), expected)
        with self.assertRaises(IM.ConflictError): self.persist(current=lambda connection, observation: 'deny')
        self.assertEqual(len(self.rows()), 1)

    def test_owner_and_synchronous_closed_callback_required(self):
        async def asynchronous(connection, observation): return 'allow'
        for callback in (None, asynchronous, lambda connection, observation: True):
            with self.subTest(callback=callback), self.assertRaises(ValueError): self.persist(current=callback)
        agent = fixture.RS.Principal('agent', 'agent', 'brain-a')
        with self.assertRaises(PermissionError):
            self.decisions.persist(agent, joined(), scope_hash=self.scope, current=self.current)
        self.assertEqual(self.rows(), [])


if __name__ == '__main__': unittest.main()
