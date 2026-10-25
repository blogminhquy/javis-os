"""Historical decision reads use actual SQLite/encrypted bytes, not live grants."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import unittest
from contextlib import closing
from unittest.mock import patch

import test_improvement_native_decision_store as fixture
import improvement_store as IM
from improvement_blobs import AssetUnavailable


class DecisionReadTests(unittest.TestCase):
    setUp = fixture.DecisionStoreTests.setUp
    current = fixture.DecisionStoreTests.current
    persist = fixture.DecisionStoreTests.persist
    rows = fixture.DecisionStoreTests.rows
    record = fixture.DecisionStoreTests.record

    def test_actual_historical_read_is_cold_after_policy_change_and_writes_nothing(self):
        saved = self.persist()
        self.store.set_policy(self.owner, 'off', expected_version=0, event_key='policy-change-1')
        before = self.rows()
        with patch.object(self.blobs, 'write', side_effect=AssertionError('read wrote blob')):
            with closing(self.rs._conn()) as connection:
                result = self.decisions.read(self.owner, fixture.joined(), scope_hash=self.scope, connection=connection)
            self.assertEqual(result, saved)
            result['decision'] = 'deny'
            self.assertEqual(self.decisions.read(self.owner, fixture.joined(), scope_hash=self.scope), saved)
        self.assertEqual(self.rows(), before)
        self.assertEqual(len(self.calls), 2, 'historical read must not call live authority')

    def test_missing_foreign_scope_changed_join_and_deleted_ciphertext_refuse(self):
        with self.assertRaises(PermissionError):
            self.decisions.read(self.owner, fixture.joined(), scope_hash=self.scope)
        self.persist()
        with self.assertRaises(PermissionError):
            self.decisions.read(self.owner, fixture.joined(), scope_hash='8' * 64)
        altered = fixture.joined()
        altered['native_pid'] = altered['image']['native_pid'] = 999
        with self.assertRaises((ValueError, IM.ConflictError, AssetUnavailable)):
            self.decisions.read(self.owner, altered, scope_hash=self.scope)
        self.blobs._path('brain-a', self.record()['blob_hashes'][0]).unlink()
        with self.assertRaises(AssetUnavailable):
            self.decisions.read(self.owner, fixture.joined(), scope_hash=self.scope)

    def test_denied_decision_stays_denied_and_reader_requires_owner(self):
        result = self.persist(current=lambda connection, value: 'deny')
        self.assertEqual(self.decisions.read(self.owner, fixture.joined(), scope_hash=self.scope), result)
        agent = fixture.fixture.RS.Principal('agent', 'agent', 'brain-a')
        with self.assertRaises(PermissionError):
            self.decisions.read(agent, fixture.joined(), scope_hash=self.scope)

    def test_attempt_scope_binds_complete_workspace_config_identity_and_capability(self):
        scope = fixture.decisions.attempt_scope
        args = dict(kind='trial', brain_id='brain-a', receipt={'trial_id': 'real-trial', 'attempt': 1,
            'input_hash': 'a' * 64, 'path': 'synthetic-path'}, config_pin={'profile_hash': 'b' * 64},
            capability_hash='c' * 64)
        first = scope(**args)
        self.assertEqual(first, scope(**copy.deepcopy(args)))
        for key, replacement in [('brain_id', 'brain-b'), ('capability_hash', 'd' * 64),
                ('config_pin', {'profile_hash': 'e' * 64}),
                ('receipt', {**args['receipt'], 'path': 'other-workspace'}),
                ('receipt', {**args['receipt'], 'attempt': 2})]:
            self.assertNotEqual(first, scope(**{**args, key: replacement}))
        for identity in [True, 0]:
            with self.assertRaises(ValueError):
                scope(**{**args, 'receipt': {**args['receipt'], 'attempt': identity}})
        with self.assertRaises(ValueError): scope(**{**args, 'kind': 'preflight'})


if __name__ == '__main__': unittest.main()
