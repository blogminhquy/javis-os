"""Actual private compose consent/current history; no operation or model query.

The two-arm fixture uses real SQL/Fernet/source/candidate/report code with its
explicit synthetic_storage_fixture result cells and upstream synthetic admission
availability. Those controls do not prove native/account/business readiness.
Only an actual host owner call may create these new permission records.
"""
from _paths import ROOT, SERVER  # noqa: F401

import importlib
import importlib.util
import json
import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

from cryptography.fernet import InvalidToken
import improvement_store as IM
from improvement_blobs import AssetUnavailable, MAX_ASSET_BYTES
from improvement_compose_inputs import ComposeInputs
import test_improvement_compose_inputs as fixtures


META = {'authorization_id', 'experiment_id', 'context_id', 'input_hash', 'basis_hash',
        'guard_blob_hash', 'experiment_generation', 'generation', 'status'}
DENIED = (PermissionError, IM.ConflictError, AssetUnavailable, ValueError)


class ComposePermissionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('improvement_compose_permissions'),
                             'Actual host-owned ComposePermissions service is absent')
        module = importlib.import_module('improvement_compose_permissions')
        self.f = fixtures.ComposeInputTests()
        self.f.setUp()
        self.addCleanup(lambda: self.assertTrue(self.f.doCleanups(), 'Actual two-arm fixture cleanup failed'))
        self.service = module.ComposePermissions(self.f.plans)
        self.assets, self.store, self.owner = self.f.assets, self.f.store, self.f.owner

    def authorize(self, *, key='owner-compose-consent', generation=None):
        return self.service.authorize(self.owner, 'association-experiment',
            expected_generation=self.f.generation if generation is None else generation, event_key=key)

    def rows(self, table):
        with closing(self.store._conn()) as connection:
            return [dict(row) for row in connection.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]

    def authorization_events(self):
        return [row for row in self.rows('improvement_events') if row['operation'] == 'compose_authorize']

    def counts_without_exposures(self):
        return {key: value for key, value in self.f.counts().items() if key != 'improvement_case_exposures'}

    def current(self, saved, *, owner=None):
        with closing(self.store._conn()) as connection:
            return self.service.current(connection, self.owner if owner is None else owner, saved['authorization_id'])

    @staticmethod
    def contains(value, expected):
        if value == expected:
            return True
        if type(value) is dict:
            return any(ComposePermissionTests.contains(child, expected) for child in value.values())
        if type(value) is list:
            return any(ComposePermissionTests.contains(child, expected) for child in value)
        return False

    def test_explicit_owner_permission_persists_exact_immutable_links_and_small_encrypted_guard_without_dispatch(self):
        before = self.counts_without_exposures()
        with closing(self.store._conn()) as connection:
            experiment = dict(connection.execute('SELECT * FROM improvement_experiments').fetchone())
        saved = self.authorize()
        self.assertEqual(set(saved), META)
        self.assertEqual((saved['experiment_id'], saved['context_id'], saved['experiment_generation']),
            ('association-experiment', self.f.lineage.value['context_id'], self.f.generation))
        self.assertEqual((saved['generation'], saved['status']), (1, 'active'))
        auths, grants = self.rows('improvement_compose_authorizations'), self.rows('improvement_compose_grants')
        self.assertEqual(len(auths), 1)
        self.assertEqual(len(grants), 1)
        self.assertEqual(auths[0]['id'], saved['authorization_id'])
        self.assertEqual(auths[0]['actor'], self.owner.by)
        for key in ('experiment_id', 'context_id', 'input_hash', 'basis_hash'):
            self.assertEqual(auths[0][key], saved[key])
        self.assertEqual((grants[0]['authorization_id'], grants[0]['status'], grants[0]['generation']),
                         (saved['authorization_id'], 'active', 1))
        events = self.authorization_events()
        self.assertEqual(len(events), 1)
        metadata = json.loads(events[0]['result_json'])
        for key in ('authorization_id', 'input_hash', 'basis_hash', 'guard_blob_hash', 'experiment_generation'):
            self.assertEqual(metadata[key], saved[key])
        current = self.current(saved)
        self.assertTrue({'data', 'basis', 'prepared'} <= set(current))
        self.assertEqual(IM._hash(current['data']), saved['input_hash'])
        self.assertEqual(IM._hash(current['basis']), saved['basis_hash'])
        self.assertEqual(current['data']['kind'], 'body_compose_projection')
        self.assertEqual(json.loads(self.assets.blobs.read(self.owner.brain_id, saved['input_hash'])), current['data'])
        self.assertEqual(json.loads(self.assets.blobs.read(self.owner.brain_id, saved['basis_hash'])), current['basis'])
        raw_guard = self.assets.blobs.read(self.owner.brain_id, saved['guard_blob_hash'])
        guard = json.loads(raw_guard)
        self.assertLessEqual(len(raw_guard), MAX_ASSET_BYTES)
        self.assertTrue(self.contains(guard, experiment), 'guard must bind the exact original experiment row')
        self.assertNotIn('technical-baseline', raw_guard.decode(), 'guard stores links, not bulk trial artifact text')
        self.assertNotIn('private-owner-answer-', raw_guard.decode())
        for key in ('input_hash', 'basis_hash', 'guard_blob_hash'):
            self.assertTrue(self.assets.blobs._path(self.owner.brain_id, saved[key]).read_bytes().startswith(b'enc:'))
        with self.assertRaises(sqlite3.IntegrityError), self.store._Tx(self.store) as connection:
            connection.execute('DELETE FROM improvement_compose_authorizations')
        self.assertEqual(self.counts_without_exposures(), before)
        self.assertEqual(self.rows('improvement_operations'), [])
        self.assertEqual(self.rows('improvement_compositions'), [])
        self.assertEqual(self.f.plans.records.get(self.owner, 'association-experiment')['generation'], self.f.generation)

    def test_cold_listing_get_revocation_and_authorize_replay_after_off_never_decrypt_refresh_or_revive(self):
        saved = self.authorize()
        identifier = saved['authorization_id']
        with self.assertRaises(DENIED):
            self.service.revoke(self.f.host_files.other, identifier, expected_generation=1, event_key='foreign-revoke-compose')
        with self.assertRaises(IM.ConflictError):
            self.service.revoke(self.owner, identifier, expected_generation=99, event_key='stale-revoke-compose')
        self.assets.set_policy(self.owner, 'off', expected_version=self.assets.get_policy(self.owner)['version'],
                               event_key='compose-permission-off')
        self.f.host_files.protected.write_bytes(b'Owner rules changed after consent.\n')
        before = self.counts_without_exposures()
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Cold permission metadata must not decrypt')), \
                patch.object(self.f.plan_fixture.host, '_snapshot_observe', side_effect=AssertionError('Cold metadata must not observe')), \
                patch.object(ComposeInputs, 'build', side_effect=AssertionError('Cold metadata must not rebuild input')):
            self.assertEqual(self.service.get(self.owner, identifier), saved)
            listed = self.service.list(self.owner, 'association-experiment')
            items = listed['items'] if type(listed) is dict else listed
            self.assertEqual(items, [saved])
            revoked = self.service.revoke(self.owner, identifier, expected_generation=1, event_key='owner-revoke-compose')
            self.assertEqual(set(revoked), META)
            self.assertEqual((revoked['generation'], revoked['status']), (2, 'revoked'))
            self.assertEqual(self.authorize(), revoked, 'historical authorize replay returns current grant state')
            self.assertEqual(self.service.get(self.owner, identifier), revoked)
            self.assertEqual(self.service.revoke(self.owner, identifier, expected_generation=1,
                event_key='owner-revoke-compose'), revoked)
            with self.assertRaises(IM.ConflictError):
                self.service.revoke(self.owner, identifier, expected_generation=1, event_key='new-stale-revoke-compose')
        self.assertEqual(len(self.authorization_events()), 1)
        self.assertEqual(len(self.rows('improvement_compose_grants')), 1)
        self.assertEqual(self.counts_without_exposures(), before)
        with self.assertRaises(DENIED): self.current(saved)

    def test_current_checks_actual_brain_and_fresh_protected_source_and_exact_experiment_state(self):
        saved = self.authorize()
        current = self.current(saved)
        self.assertEqual(IM._hash(current['data']), saved['input_hash'])
        with self.assertRaises(DENIED): self.current(saved, owner=self.f.host_files.other)
        class RollbackControl(Exception): pass
        with self.assertRaises(RollbackControl), self.store._Tx(self.store) as connection:
            connection.execute('UPDATE improvement_experiments SET generation=generation+1')
            with self.assertRaises(DENIED):
                self.service.current(connection, self.owner, saved['authorization_id'])
            raise RollbackControl()
        before = self.rows('improvement_events')
        self.f.host_files.protected.write_bytes(b'Protected owner rules drift while compose consent remains active.\n')
        with self.assertRaises(DENIED): self.current(saved)
        self.assertEqual(self.rows('improvement_events'), before)
        self.assertEqual(self.service.get(self.owner, saved['authorization_id'])['status'], 'active',
                         'source refusal does not rewrite cold permission history')

    def test_late_policy_or_domain_change_in_authorization_event_rolls_back_consent_but_not_prior_input(self):
        original_event = self.assets._event
        for mode in ('policy', 'domain'):
            with self.subTest(mode=mode):
                changed = []
                def event(connection, principal, key, operation, payload, result):
                    if operation == 'compose_authorize':
                        if mode == 'policy':
                            connection.execute("INSERT INTO improvement_policies(brain_id,mode,version) VALUES(?,'off',1) "
                                "ON CONFLICT(brain_id) DO UPDATE SET mode='off',version=version+1", (self.owner.brain_id,))
                        else:
                            original_event(connection, principal, 'native-qualification:' + 'e' * 64,
                                'native_qualification_session', {'run_hash': 'e' * 64}, {'unanchored_refusal_control': True})
                        changed.append(True)
                    return original_event(connection, principal, key, operation, payload, result)
                with patch.object(self.assets, '_event', side_effect=event), self.assertRaises(DENIED):
                    self.authorize(key='late-compose-consent-' + mode)
                self.assertEqual(changed, [True])
                self.assertEqual(self.rows('improvement_compose_authorizations'), [])
                self.assertEqual(self.rows('improvement_compose_grants'), [])
                self.assertEqual(self.authorization_events(), [])
                # The legitimate earlier input transaction may remain published
                # and exposed; the failed consent is a distinct atomic boundary.
                self.assertEqual(len(self.f.input_events()), 1)
                self.assertEqual(self.counts_without_exposures(),
                    {key: value for key, value in self.f.before.items() if key != 'improvement_case_exposures'})

    def test_current_uses_real_query_only_connection_without_public_build_or_any_writer(self):
        saved = self.authorize()
        events, exposures, counts = self.rows('improvement_events'), self.f.exposure_rows(), self.f.counts()
        with closing(self.store._conn()) as connection:
            connection.execute('PRAGMA query_only=ON')
            with patch.object(ComposeInputs, 'build', side_effect=AssertionError('Current may not rebuild/publicly publish')), \
                    patch.object(self.store, '_Tx', side_effect=AssertionError('Current may not open a writer')), \
                    patch.object(self.assets, '_event', side_effect=AssertionError('Current may not append an event')):
                current = self.service.current(connection, self.owner, saved['authorization_id'])
        self.assertEqual(IM._hash(current['data']), saved['input_hash'])
        self.assertEqual(IM._hash(current['basis']), saved['basis_hash'])
        self.assertTrue('prepared' in current)
        for forbidden in ('supported', 'account_ready', 'native_ready', 'activation_eligible'):
            self.assertNotIn(forbidden, current)
        self.assertEqual(self.rows('improvement_events'), events)
        self.assertEqual(self.f.exposure_rows(), exposures)
        self.assertEqual(self.f.counts(), counts)
        with closing(sqlite3.connect(':memory:')) as foreign:
            with self.assertRaises((*DENIED, TypeError)):
                self.service.current(foreign, self.owner, saved['authorization_id'])

    def test_encrypted_guard_corruption_refuses_current_without_damaging_cold_permission_metadata(self):
        saved = self.authorize()
        path = self.assets.blobs._path(self.owner.brain_id, saved['guard_blob_hash'])
        self.assertTrue(path.is_relative_to(self.assets.blobs.root))
        ciphertext = path.read_bytes()
        before = self.rows('improvement_events')
        try:
            path.write_bytes(b'enc:deliberately-invalid-control')
            with self.assertRaises((AssetUnavailable, ValueError, InvalidToken)): self.current(saved)
            self.assertEqual(self.service.get(self.owner, saved['authorization_id']), saved)
            self.assertEqual(self.rows('improvement_events'), before)
        finally:
            path.write_bytes(ciphertext)


if __name__ == '__main__': unittest.main()
