"""Concrete private session/M0 owners; static observer seams, no native child."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import importlib
import importlib.util
import json
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import improvement_native_qualifications as registry
import test_improvement_native_sdk as native


class QualificationSessionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('improvement_qualification_session'), 'concrete host QualificationSession missing')
        self.m = importlib.import_module('improvement_qualification_session')
        self.pin = native.pin()
        self.pin['profile_version'] = 'claude-owned-images-v3'
        self.runtime = {'platform': sys.platform, 'cli_hash': self.pin['cli_hash'], 'sdk_version': self.pin['sdk_version'],
            'profile_hash': self.pin['profile_hash'], 'managed_policy': 'absent'}
        self.prefix = (sys.platform, self.pin['cli_version'], self.pin['cli_hash'], self.pin['sdk_version'], self.pin['profile_version'], self.pin['profile_hash'])
        self.fingerprint, self.review_hash = 'a' * 64, 'b' * 64
        self.endpoint = 'http://127.0.0.1:15432'

    def open(self, **changes):
        options = dict(pin=self.pin, endpoint=self.endpoint, expected_fingerprint=self.fingerprint,
            lifetime_seconds=300, maximum_queries=4)
        with patch.object(registry, 'REVIEWED_QUALIFICATION_CANDIDATES', {(*self.prefix, self.fingerprint): self.review_hash}, create=True), \
                patch.object(self.m, '_runtime_identity', return_value=copy.deepcopy(self.runtime)), \
                patch.object(self.m, 'observe_release', return_value={'version': 1, 'fingerprint': self.fingerprint,
                    'manifests': {'engineering': 'not launch authority'}}):
            session = self.m.QualificationSession.open(**{**options, **changes})
        self.addCleanup(session.cleanup)
        return session

    def test_no_reviewed_candidate_refuses_before_inventory_or_scratch_allocation(self):
        with patch.object(registry, 'REVIEWED_QUALIFICATION_CANDIDATES', {}, create=True), \
                patch.object(self.m, 'observe_release', side_effect=AssertionError('unreviewed inventory')), \
                patch.object(self.m.tempfile, 'TemporaryDirectory', side_effect=AssertionError('unreviewed scratch')):
            with self.assertRaisesRegex(PermissionError, 'qualification_candidate_unreviewed'):
                self.m.QualificationSession.open(pin=self.pin, endpoint=self.endpoint, expected_fingerprint=self.fingerprint,
                    lifetime_seconds=300, maximum_queries=4)

    def test_runtime_or_source_drift_refuses_before_scratch_allocation(self):
        candidates = {(*self.prefix, self.fingerprint): self.review_hash}
        for field, value in (('cli_hash', 'f' * 64), ('sdk_version', 'foreign'), ('profile_hash', 'f' * 64), ('managed_policy', 'present')):
            with self.subTest(field=field), patch.object(registry, 'REVIEWED_QUALIFICATION_CANDIDATES', candidates, create=True), \
                    patch.object(self.m, '_runtime_identity', return_value={**self.runtime, field: value}), \
                    patch.object(self.m.tempfile, 'TemporaryDirectory', side_effect=AssertionError('drift scratch')):
                with self.assertRaises(PermissionError):
                    self.m.QualificationSession.open(pin=self.pin, endpoint=self.endpoint, expected_fingerprint=self.fingerprint,
                        lifetime_seconds=300, maximum_queries=4)
        with patch.object(registry, 'REVIEWED_QUALIFICATION_CANDIDATES', candidates, create=True), \
                patch.object(self.m, '_runtime_identity', return_value=self.runtime), \
                patch.object(self.m, 'observe_release', return_value={'fingerprint': 'f' * 64}), \
                patch.object(self.m.tempfile, 'TemporaryDirectory', side_effect=AssertionError('drift scratch')):
            with self.assertRaises(PermissionError):
                self.m.QualificationSession.open(pin=self.pin, endpoint=self.endpoint, expected_fingerprint=self.fingerprint,
                    lifetime_seconds=300, maximum_queries=4)

    def test_actual_fresh_private_root_records_encrypted_m0_scope_before_any_call(self):
        session = self.open(); scope = session.scope()
        self.assertEqual(scope['domain'], 'qualification'); self.assertIs(scope['account_ready'], False)
        self.assertEqual(scope['pin_hash'], self.m.IM._hash(self.pin))
        self.assertEqual(scope['release_fingerprint'], self.fingerprint)
        self.assertEqual(scope['review_hash'], self.review_hash)
        self.assertEqual(scope['maximum_queries'], 4)
        self.assertEqual(session.read_scope(), scope)
        scope['domain'] = 'caller-mutation'
        self.assertEqual(session.read_scope()['domain'], 'qualification')
        with closing(session.assets.store._conn()) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM agent_calls').fetchone()[0], 0)
            row = connection.execute("SELECT * FROM improvement_events WHERE operation='native_qualification_session'").fetchone()
            self.assertIsNotNone(row)
            envelope = json.loads(row['result_json'])
        raw = session.assets.blobs._path(session.principal.brain_id, envelope['blob_hash']).read_text()
        self.assertTrue(raw.startswith('enc:')); self.assertNotIn('127.0.0.1', raw)
        self.assertTrue(session.assets.store.path.is_relative_to(session.root))
        self.assertTrue(session.assets.blobs.root.is_relative_to(session.root))

    def test_each_actual_environment_uses_fresh_empty_home_and_no_ambient_auth(self):
        session = self.open(); cwd = session.root / 'trials' / 'attempt'; cwd.mkdir(parents=True)
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'host-key-never-copy', 'CLAUDE_CONFIG_DIR': 'host-config-never-copy'}):
            first = session.environment(cwd); second = session.environment(cwd)
        self.assertNotEqual(first['HOME'], second['HOME'])
        self.assertEqual(list(Path(first['HOME']).iterdir()), [])
        self.assertEqual(list(Path(second['HOME']).iterdir()), [])
        self.assertTrue(Path(first['HOME']).is_relative_to(session.root))
        self.assertEqual(first['USERPROFILE'], first['HOME'])
        self.assertEqual(first['ANTHROPIC_API_KEY'], 'javis-native-qualification-dummy')
        self.assertEqual(first['ANTHROPIC_BASE_URL'], self.endpoint)
        self.assertNotIn('CLAUDE_CONFIG_DIR', first)
        self.assertNotIn('host-key-never-copy', str(first))

    def test_private_environment_supplies_closed_wire_paths_when_posix_base_omits_appdata(self):
        session = self.open(); cwd = session.root / 'portable-trial'; cwd.mkdir()
        original = self.m.worker_environment
        def posix_base(*args, **kwargs):
            return {name: value for name, value in original(*args, **kwargs).items()
                if name not in ('APPDATA', 'LOCALAPPDATA')}
        with patch.object(self.m, 'worker_environment', side_effect=posix_base):
            environment = session.environment(cwd)
        home = Path(environment['HOME'])
        self.assertEqual(environment['APPDATA'], str(home / 'AppData' / 'Roaming'))
        self.assertEqual(environment['LOCALAPPDATA'], str(home / 'AppData' / 'Local'))
        self.assertEqual(list(home.iterdir()), [], 'preparation leaves the actual private HOME empty')

    def test_foreign_workspace_and_closed_session_never_get_an_environment(self):
        session = self.open()
        outside = Path(tempfile.mkdtemp()); self.addCleanup(lambda: outside.rmdir())
        with self.assertRaises(PermissionError): session.environment(outside)
        cwd = session.root / 'trials'; cwd.mkdir()
        session.close()
        with self.assertRaises(PermissionError): session.environment(cwd)
        self.assertEqual(session.read_scope()['domain'], 'qualification', 'forensic read remains available after close')
        self.assertTrue(session.root.exists())

    def test_parent_traversal_cannot_make_a_foreign_workspace_appear_within_root(self):
        session = self.open()
        outside = Path(tempfile.mkdtemp(prefix='qual-outside-', dir=session.root.parent))
        self.addCleanup(lambda: outside.rmdir())
        alias = session.root / '..' / outside.name
        with self.assertRaises(PermissionError): session.environment(alias)

    def test_expired_environment_and_unsettled_owner_keep_forensic_state_without_cleanup(self):
        session = self.open(); cwd = session.root / 'trials'; cwd.mkdir()
        with patch.object(self.m.time, 'time', return_value=session.scope()['deadline_at']):
            with self.assertRaisesRegex(PermissionError, 'expired'): session.environment(cwd)
        owner = object(); session._owners.add(owner)
        with self.assertRaisesRegex(RuntimeError, 'owners_unsettled'): session.cleanup()
        self.assertTrue(session.root.exists())
        self.assertEqual(session.read_scope()['domain'], 'qualification')
        session._owners.remove(owner)

    def test_actual_scope_blob_corruption_cannot_be_read_as_a_valid_run(self):
        session = self.open()
        with closing(session.assets.store._conn()) as connection:
            row = connection.execute("SELECT result_json FROM improvement_events WHERE operation='native_qualification_session'").fetchone()
        digest = json.loads(row[0])['blob_hash']
        session.assets.blobs._path(session.principal.brain_id, digest).unlink()
        with self.assertRaises(Exception) as caught: session.read_scope()
        self.assertIn(type(caught.exception).__name__, ('AssetUnavailable', 'PermissionError'))

    def test_session_root_cannot_be_reassigned_to_a_foreign_directory(self):
        session = self.open()
        with self.assertRaises(AttributeError): session.root = Path(tempfile.gettempdir())

    def test_canonical_profile_seeds_owner_and_recursively_pins_helper_bytes_offline(self):
        import improvement_claude as profile
        import improvement_native_release as release
        import test_improvement_native_release as inventory
        owner, helper = 'improvement_qualification_session.py', 'improvement_qualification_environment.py'
        self.assertIn(owner, profile.PROFILE_SOURCES, 'qualifier owner omitted from selected profile/release closure')
        fixture = inventory.NativeReleaseTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        for name in set(profile.PROFILE_SOURCES) | set(release._SEEDS): fixture.write_source(name, 'VALUE=1\n')
        owner_text = 'import improvement_qualification_environment\nimport claude_agent_sdk\nVALUE=1\n'
        fixture.write_source(owner, owner_text); fixture.write_source(helper, 'VALUE=2\n')
        configuration = inventory.pin()
        def current_hash():
            return release._fingerprint({name: self.m.hashlib.sha256((fixture.source / name).read_bytes()).hexdigest()
                for name in profile.PROFILE_SOURCES})
        configuration['profile_hash'] = current_hash()
        # Actual source/RECORD closure; inert runtime/manifest seams make this
        # portable, and are explicitly not launch/native qualification proof.
        with patch.object(release, '_runtime_pins', return_value={'executable': {'sha256': '1' * 64}, 'dll': {'sha256': '2' * 64}}), \
                patch('improvement_native_bootstrap.validate_bootstrap_manifest', side_effect=lambda value: copy.deepcopy(value)):
            original = release.observe_release(configuration, source_root=fixture.source, site_packages=fixture.packages)
            self.assertIn(owner, original['content']['source']); self.assertIn(helper, original['content']['source'])
            fixture.write_source(owner, owner_text + 'CHANGED=1\n')
            with self.assertRaisesRegex(ValueError, 'profile_changed'):
                release.observe_release(configuration, source_root=fixture.source, site_packages=fixture.packages)
            fixture.write_source(owner, owner_text)
            fixture.write_source(helper, 'VALUE=3\n')
            changed = release.observe_release(configuration, source_root=fixture.source, site_packages=fixture.packages)
            self.assertNotEqual(changed['fingerprint'], original['fingerprint'])
            self.assertNotEqual(changed['content']['source'][helper], original['content']['source'][helper])

    def test_closed_bounds_and_dummy_endpoint_refuse_without_opening_authority(self):
        for changes in ({'lifetime_seconds': True}, {'lifetime_seconds': 0}, {'lifetime_seconds': 3601},
                {'maximum_queries': True}, {'maximum_queries': 0}, {'maximum_queries': 33}, {'endpoint': 'http://localhost:15432'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError): self.open(**changes)


if __name__ == '__main__': unittest.main()
