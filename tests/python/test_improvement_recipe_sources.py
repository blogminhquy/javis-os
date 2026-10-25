"""Concrete retained source authority; synthetic fixtures never query a provider."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import importlib.util
import json
import os
import sys
import unittest
from contextlib import closing, contextmanager
from unittest.mock import patch

from improvement_blobs import AssetUnavailable
from improvement_trial_records import HostContextRecords
from resonance_store import Principal

import improvement_store as IM
from improvement_assets import capture_source
import test_improvement_trial_service as fixtures


@contextmanager
def after_return(callback, action, *, occurrence=1):
    """Mutate real scratch authority after slow I/O without replacing its owner."""
    previous = sys.getprofile()
    calls = 0
    def profile(frame, event, result):
        nonlocal calls
        if event == 'return' and frame.f_code is callback.__code__:
            calls += 1
            if calls == occurrence:
                action()
        if previous is not None:
            previous(frame, event, result)
    sys.setprofile(profile)
    try:
        yield
    finally:
        sys.setprofile(previous)


class RecipeSourceTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.DashboardServiceTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.owner = self.f.f.owner
        self.host = self.f.factory(source_selections=self.f.selections)
        self.meta = self.f.create(self.host)
        with closing(self.f.assets.store._conn()) as connection:
            row = self.host._row(connection, IM._brain(self.owner), self.meta['experiment_id'])
            self.binding = self.host._decode(row)

    def revise(self):
        path = self.f.f.brain / 'skills/custom/SKILL.md'
        path.write_bytes(path.read_bytes().replace(b'PRIVATE MUTABLE TARGET BODY', b'REVISED MUTABLE TARGET BODY'))
        source, raw = capture_source(self.f.f.brain, 'skill', 'custom', pack_state_dir=self.f.f.state / 'packs-state')
        result = self.f.assets.capture(self.owner, source, raw, expected_generation=self.f.target['generation'],
                                       event_key='recipe-source-revision')
        # The ordinary warmed mirror must acknowledge the real changed skill inventory.
        sync = self.f.host.system_sync
        sync._MIRROR_SIG[str(self.f.f.brain)] = sync._mirror_signature(self.f.f.brain / 'skills')
        return result

    def capture(self, observer=None, **kwargs):
        return (observer or self.observer()).capture(self.owner, self.meta['context_id'],
            expected_generation=kwargs.get('expected_generation', self.meta['generation']))

    def sql_write(self, statement, arguments=()):
        with closing(self.f.assets.store._conn()) as connection:
            connection.execute(statement, arguments)
            connection.commit()

    def revoke(self):
        self.host.revoke(self.owner, self.meta['experiment_id'], expected_generation=self.meta['generation'],
                         event_key='recipe-source-revoke')

    def observer(self):
        self.assertIsNotNone(importlib.util.find_spec('improvement_recipe_sources'),
                             'Concrete RecipeSources observer is missing after legitimate revision')
        from improvement_recipe_sources import RecipeSources
        return RecipeSources(self.host)

    def test_legitimate_current_revision_is_observed_while_execution_stays_exact(self):
        revised = self.revise()
        self.assertEqual(revised['target_id'], self.f.target['target_id'])
        self.assertGreater(revised['generation'], self.f.target['generation'])
        with self.assertRaises(IM.ConflictError):
            self.host._snapshot_observe(self.owner, self.binding)
        observer = self.observer()
        snapshot = observer.capture(self.owner, self.meta['context_id'], expected_generation=self.meta['generation'])
        self.assertEqual(snapshot['binding'], self.binding)
        self.assertEqual(snapshot['current_targets'][0]['source_hash'], revised['source_hash'])
        self.assertNotEqual(snapshot['current_capture'], self.binding['capture'])
        self.assertEqual(snapshot['fixture_inventory'], self.binding['fixture_inventory'])
        observer.check(self.owner, snapshot)


    def test_snapshot_is_exact_private_and_read_only(self):
        observer = self.observer()
        with closing(self.f.assets.store._conn()) as connection:
            before = list(connection.iterdump())
        paths = sorted(str(path) for path in self.f.f.root.rglob('*'))
        snapshot = self.capture(observer)
        self.assertEqual(set(snapshot), {'version', 'context_id', 'context_generation', 'binding_hash',
            'source_scope_hash', 'engine_config_hash', 'language', 'owner_rule_hash', 'binding', 'current_capture',
            'current_targets', 'target_authorities', 'fixture_inventory', 'sql', 'authority_hash'})
        self.assertEqual(set(snapshot['sql']), {'context', 'grant', 'policy', 'targets'})
        self.assertEqual(snapshot['authority_hash'], IM._hash({key: value for key, value in snapshot.items()
                                                            if key != 'authority_hash'}))
        observer.check(self.owner, snapshot)
        self.assertEqual(paths, sorted(str(path) for path in self.f.f.root.rglob('*')))
        with closing(self.f.assets.store._conn()) as connection:
            self.assertEqual(before, list(connection.iterdump()))
            self.assertEqual(connection.execute('SELECT count(*) FROM agent_calls').fetchone()[0], 0)
        changed = copy.deepcopy(snapshot)
        changed['language'] = 'en'
        with self.assertRaises(IM.ConflictError):
            observer.check(self.owner, changed)
        changed['authority_hash'] = IM._hash({key: value for key, value in changed.items() if key != 'authority_hash'})
        with self.assertRaises(IM.ConflictError):
            observer.check(self.owner, changed)

    def test_unrelated_current_discovery_is_fresh_and_old_execution_stays_exact(self):
        observer = self.observer()
        first = self.capture(observer)
        self.f.f.write(self.f.f.brain, 'agents/new-helper.md',
                       '---\nname: New helper\nrole: Fresh discovery metadata\n---\nPRIVATE AGENT BODY\n')
        current = self.capture(observer)
        self.assertNotEqual(current['current_capture'], first['current_capture'])
        self.assertEqual(current['binding'], self.binding)
        self.assertEqual(current['owner_rule_hash'], first['owner_rule_hash'])
        self.assertIn('New helper', str(current['current_capture']))
        self.assertNotIn('PRIVATE AGENT BODY', current['current_capture']['baseline_context']['content'])
        observer.check(self.owner, current)
        with self.assertRaises(IM.ConflictError):
            observer.check(self.owner, first)
        with self.assertRaises(ValueError):
            self.host._snapshot_observe(self.owner, self.binding)

    def test_current_suggest_policy_can_advance_without_authorizing_old_execution(self):
        self.f.assets.set_policy(self.owner, 'off', expected_version=0, event_key='source-off')
        self.f.assets.set_policy(self.owner, 'suggest', expected_version=1, event_key='source-suggest')
        snapshot = self.capture()
        self.assertEqual(snapshot['sql']['policy']['version'], 2)
        self.assertEqual(snapshot['binding']['grant']['policy_version'], 0)
        with closing(self.f.assets.store._conn()) as connection, self.assertRaises(IM.ConflictError):
            self.host._snapshot_binding(connection, self.owner, self.meta['experiment_id'], self.f.ref)

    def test_foreign_owner_brain_and_stale_generation_refuse_before_binding_reads(self):
        observer = self.observer()
        with after_return(self.host.blobs.read, lambda: self.fail('binding must remain unread')):
            for owner in (Principal('agent', 'agent-1', str(self.f.f.brain)),
                          Principal('owner', 'owner-2', str(self.f.f.root / 'foreign'))):
                with self.subTest(owner=owner), self.assertRaises(PermissionError):
                    observer.capture(owner, self.meta['context_id'], expected_generation=self.meta['generation'])
            with self.assertRaises(IM.ConflictError):
                self.capture(observer, expected_generation=self.meta['generation'] + 1)

    def test_source_grant_revocation_and_policy_off_refuse_before_binding_reads(self):
        from improvement_recipe_sources import RecipeSourceUnavailable
        observer = self.observer()
        self.f.assets.set_policy(self.owner, 'off', expected_version=0, event_key='source-off')
        with after_return(self.host.blobs.read, lambda: self.fail('binding must remain unread')):
            with self.assertRaises(RecipeSourceUnavailable):
                self.capture(observer)
        self.f.assets.set_policy(self.owner, 'suggest', expected_version=1, event_key='source-suggest')
        self.revoke()
        with after_return(self.host.blobs.read, lambda: self.fail('binding must remain unread')):
            with self.assertRaises(IM.ConflictError):
                self.capture(observer)
            with self.assertRaises(RecipeSourceUnavailable):
                self.capture(observer, expected_generation=self.meta['generation'] + 1)

    def test_future_schema_refuses_before_binding_reads(self):
        observer = self.observer()
        self.sql_write('UPDATE improvement_schema SET version=? WHERE id=1', (IM.SCHEMA_VERSION + 1,))
        with after_return(self.host.blobs.read, lambda: self.fail('binding must remain unread')):
            with self.assertRaises(IM.SchemaError):
                self.capture(observer)

    def test_malformed_current_schema_refuses_before_binding_reads(self):
        observer = self.observer()
        self.sql_write('DROP TRIGGER improvement_recipe_states_delete')
        with after_return(self.host.blobs.read, lambda: self.fail('binding must remain unread')):
            with self.assertRaises(IM.ConflictError):
                self.capture(observer)

    def test_sql_target_retirement_refuses_before_binding_reads(self):
        from improvement_recipe_sources import RecipeSourceUnavailable
        observer = self.observer()
        self.f.assets.retire(self.owner, self.f.target['target_id'], expected_generation=self.f.target['generation'],
                             event_key='recipe-source-retire')
        with after_return(self.host.blobs.read, lambda: self.fail('binding must remain unread')):
            with self.assertRaises(RecipeSourceUnavailable):
                self.capture(observer)

    def test_late_protected_edit_after_binding_read_is_unavailable(self):
        from improvement_recipe_sources import RecipeSourceUnavailable
        observer = self.observer()
        with after_return(HostContextRecords._decode,
                          lambda: self.f.f.write(self.f.f.state, 'user_profile.md', 'Changed actual owner rule.')):
            with self.assertRaises(RecipeSourceUnavailable):
                self.capture(observer)

    def test_late_fixture_edit_after_current_capture_is_unavailable(self):
        from improvement_recipe_sources import RecipeSourceUnavailable
        observer = self.observer()
        with after_return(self.host.context_capture._collector.recipe_capture,
                          lambda: self.f.input.write_bytes(b'{"input":"changed fixture"}')):
            with self.assertRaises(RecipeSourceUnavailable):
                self.capture(observer)

    def test_late_protected_edit_after_fixture_read_is_unavailable(self):
        from improvement_recipe_sources import RecipeSourceUnavailable
        observer = self.observer()
        with after_return(type(self.host.fixture_observer).__call__,
                          lambda: self.f.f.write(self.f.f.state, 'user_profile.md', 'Late actual owner rule.')):
            with self.assertRaises(RecipeSourceUnavailable):
                self.capture(observer)

    def test_late_selected_engine_edit_after_fixture_read_is_unavailable(self):
        from improvement_recipe_sources import RecipeSourceUnavailable
        observer = self.observer()
        def mutate():
            self.f.f.settings['model']['main']['model'] = 'opus'
            self.f.f.save_settings()
        with after_return(type(self.host.fixture_observer).__call__, mutate):
            with self.assertRaises(RecipeSourceUnavailable):
                self.capture(observer)

    def test_final_sql_source_grant_fence_follows_last_target_callback(self):
        observer = self.observer()
        # Target observer runs once before binding I/O, then once per fresh pass.
        with after_return(self.host.target_observer, self.revoke, occurrence=3):
            with self.assertRaises(IM.ConflictError):
                self.capture(observer)

    def test_final_sql_target_fence_follows_last_target_callback(self):
        from improvement_recipe_sources import RecipeSourceUnavailable
        observer = self.observer()
        def retire():
            self.f.assets.retire(self.owner, self.f.target['target_id'], expected_generation=self.f.target['generation'],
                                 event_key='late-source-retire')
        with after_return(self.host.target_observer, retire, occurrence=3):
            with self.assertRaises(RecipeSourceUnavailable):
                self.capture(observer)

    def test_final_schema_fence_follows_last_target_callback(self):
        observer = self.observer()
        with after_return(self.host.target_observer,
                          lambda: self.sql_write('UPDATE improvement_schema SET version=? WHERE id=1',
                                                 (IM.SCHEMA_VERSION + 1,)), occurrence=3):
            with self.assertRaises(IM.SchemaError):
                self.capture(observer)

    def test_actual_target_body_change_without_current_revision_is_unavailable(self):
        from improvement_recipe_sources import RecipeSourceUnavailable
        observer = self.observer()
        path = self.f.f.brain / 'skills/custom/SKILL.md'
        path.write_bytes(path.read_bytes() + b'\nUncaptured source change.\n')
        with self.assertRaises(RecipeSourceUnavailable):
            self.capture(observer)

    def test_actual_fixture_file_mode_change_revokes_original_inventory(self):
        from improvement_recipe_sources import RecipeSourceUnavailable
        observer = self.observer()
        mode = self.f.input.stat().st_mode
        self.addCleanup(self.f.input.chmod, mode)
        self.f.input.chmod(mode & ~0o222)
        with self.assertRaises(RecipeSourceUnavailable):
            self.capture(observer)

    @unittest.skipIf(os.name == 'nt', 'Windows directory chmod does not exercise directory permissions')
    def test_actual_root_mode_change_revokes_original_authority(self):
        from improvement_recipe_sources import RecipeSourceUnavailable
        observer = self.observer()
        path = self.f.f.brain
        mode = path.stat().st_mode
        self.addCleanup(path.chmod, mode)
        path.chmod(mode ^ 0o020)
        with self.assertRaises(RecipeSourceUnavailable):
            self.capture(observer)

    def test_protected_file_replacement_with_same_text_revokes_authority(self):
        from improvement_recipe_sources import RecipeSourceUnavailable
        observer = self.observer()
        path = self.f.f.state / 'user_profile.md'
        replacement = path.with_name('replacement.md')
        replacement.write_bytes(path.read_bytes())
        replacement.replace(path)
        with self.assertRaises(RecipeSourceUnavailable):
            self.capture(observer)

    def test_retained_dependencies_drift_remains_integrity_error(self):
        from improvement_recipe_sources import RecipeSourceUnavailable
        observer = self.observer()
        retained = self.host.context_capture
        for obj, name, value in ((self.host, 'selected_engine', lambda: self.binding['engine_config']),
                (self.host, 'target_observer', lambda *args: self.binding['targets']),
                (retained, '_check', lambda: None), (retained, '_collector', object()),
                (retained._collector, '_scan', lambda *args: None),
                (self.host, 'fixture_observer', lambda *args, **kwargs: self.binding['fixture_inventory'])):
            with self.subTest(name=name), patch.object(obj, name, value):
                with self.assertRaises(IM.ConflictError) as caught:
                    self.capture(observer)
                self.assertNotIsInstance(caught.exception, RecipeSourceUnavailable)
        with patch.object(self.f.host.sessions, '_store', None):
            with self.assertRaisesRegex(ValueError, 'trial_service_source_lifetime_changed'):
                self.capture(observer)

    def test_retained_replacement_during_binding_read_remains_integrity_error(self):
        observer = self.observer()
        with after_return(HostContextRecords._decode, lambda: setattr(self.host.context_capture, '_check', lambda: None)):
            with self.assertRaises(IM.ConflictError):
                self.capture(observer)

    def test_corrupt_historical_ciphertext_is_integrity_error(self):
        from improvement_recipe_sources import RecipeSourceUnavailable
        from cryptography.fernet import InvalidToken
        observer = self.observer()
        with closing(self.f.assets.store._conn()) as connection:
            context = self.host._row(connection, IM._brain(self.owner), self.meta['experiment_id'])
            digest = json.loads(context['blob_hashes_json'])[0]
        path = self.host.blobs._path(IM._brain(self.owner), digest)
        path.write_bytes(b'enc:invalid-ciphertext')
        with self.assertRaises((AssetUnavailable, InvalidToken)) as caught:
            self.capture(observer)
        self.assertNotIsInstance(caught.exception, RecipeSourceUnavailable)

    def test_actual_source_module_replacement_is_integrity_error(self):
        observer = self.observer()
        with patch.dict(sys.modules, {'improvement_trial_dashboard': object()}):
            with self.assertRaises(IM.ConflictError):
                self.capture(observer)

    def test_sql_only_state_uses_current_revision_and_never_reads_sources(self):
        self.revise()
        observer = self.observer()
        with after_return(self.host.blobs.read, lambda: self.fail('SQL state cannot decrypt')):
            with closing(self.f.assets.store._conn()) as connection:
                state = observer._state(connection, self.owner, self.meta['context_id'], self.meta['generation'])
        self.assertEqual(state['targets'][0]['generation'], 2)
        self.assertEqual(state['context']['target_generations_json'],
                         IM._json({self.f.target['target_id']: 1}))

    def test_unsupported_host_is_refused_without_any_source_io(self):
        from improvement_recipe_sources import RecipeSources
        from improvement_trial_host import HostContextStore
        with self.assertRaises(TypeError):
            RecipeSources(object())
        fake = HostContextStore(self.f.assets, context_capture=lambda *args: self.binding['capture'],
            selected_engine=lambda: self.binding['engine_config'], target_observer=lambda *args: self.binding['targets'],
            fixture_observer=self.host.fixture_observer)
        with self.assertRaises(TypeError):
            RecipeSources(fake)

    def test_borrowed_collector_cannot_legitimize_caller_engine_or_target_provider(self):
        from improvement_recipe_sources import RecipeSources
        from improvement_trial_host import HostContextStore
        fake = HostContextStore(self.f.assets, context_capture=self.host.context_capture,
            selected_engine=lambda: self.binding['engine_config'], target_observer=self.host.target_observer,
            fixture_observer=self.host.fixture_observer)
        with self.assertRaises(TypeError):
            RecipeSources(fake)
        fake = HostContextStore(self.f.assets, context_capture=self.host.context_capture,
            selected_engine=self.host.selected_engine, target_observer=lambda *args: self.binding['targets'],
            fixture_observer=self.host.fixture_observer)
        with self.assertRaises(TypeError):
            RecipeSources(fake)

    def test_actual_current_target_permissions_are_pinned_in_private_snapshot(self):
        from improvement_trial_file_sources import _authority
        observer = self.observer()
        path = self.f.f.brain / 'skills/custom/SKILL.md'
        before = self.capture(observer)
        mode = path.stat().st_mode
        self.addCleanup(path.chmod, mode)
        path.chmod(mode & ~0o222)
        after = self.capture(observer)
        self.assertTrue('target_authorities' in before, 'Current target native authority must be retained')
        self.assertNotEqual(before['target_authorities'], after['target_authorities'])
        self.assertEqual(after['target_authorities'], [{'target_id': self.f.target['target_id'],
            'authority': _authority(self.f.f.brain, 'skills/custom/SKILL.md')}])
        with self.assertRaises(IM.ConflictError):
            observer.check(self.owner, before)

    def test_actual_target_mode_change_during_target_callback_is_unavailable(self):
        from improvement_recipe_sources import RecipeSourceUnavailable
        observer = self.observer()
        path = self.f.f.brain / 'skills/custom/SKILL.md'
        mode = path.stat().st_mode
        self.addCleanup(path.chmod, mode)
        with after_return(self.host.target_observer, lambda: path.chmod(mode & ~0o222)):
            with self.assertRaises(RecipeSourceUnavailable):
                self.capture(observer)

    def test_dashboard_recipe_capture_rejects_forged_volatile_locator(self):
        from improvement_trial_semantics import capture_semantics
        frozen = copy.deepcopy(self.binding['capture'])
        record = next(item for item in frozen['sources'] if item['ref'] == 'dashboard:volatile')
        record['locator'] = {'policy': 'caller-current-clock'}
        frozen = capture_semantics(surface=frozen['surface'], sources=frozen['sources'],
            content=frozen['baseline_context']['content'], complete_plan=True)
        with self.assertRaises(ValueError):
            self.host.context_capture.recipe_capture(self.owner, frozen['surface'], self.binding['targets'],
                                                      frozen_capture=frozen)

    def test_actual_target_permissions_changed_after_binding_read_are_unavailable(self):
        from improvement_recipe_sources import RecipeSourceUnavailable
        observer = self.observer()
        path = self.f.f.brain / 'skills/custom/SKILL.md'
        mode = path.stat().st_mode
        self.addCleanup(path.chmod, mode)
        with after_return(HostContextRecords._decode, lambda: path.chmod(mode & ~0o222)):
            with self.assertRaises(RecipeSourceUnavailable):
                self.capture(observer)

    def test_actual_target_permission_change_after_last_engine_read_is_unavailable(self):
        from improvement_recipe_sources import RecipeSourceUnavailable
        observer = self.observer()
        path = self.f.f.brain / 'skills/custom/SKILL.md'
        mode = path.stat().st_mode
        self.addCleanup(path.chmod, mode)
        with after_return(self.host.selected_engine, lambda: path.chmod(mode & ~0o222), occurrence=3):
            with self.assertRaises(RecipeSourceUnavailable):
                self.capture(observer)

    def test_actual_target_parent_replacement_during_callback_is_unavailable(self):
        from improvement_recipe_sources import RecipeSourceUnavailable
        observer = self.observer()
        parent = self.f.f.brain / 'skills/custom'
        tombstone = parent.with_name('old-custom')
        self.assertTrue(parent.resolve().is_relative_to(self.f.f.root.resolve()))
        def replace_parent():
            parent.rename(tombstone)
            parent.mkdir()
            (tombstone / 'SKILL.md').rename(parent / 'SKILL.md')
            tombstone.rmdir()
        with after_return(self.host.target_observer, replace_parent):
            with self.assertRaises(RecipeSourceUnavailable):
                self.capture(observer)

    def test_injected_target_acl_projection_drift_is_unavailable(self):
        import improvement_trial_file_sources as files
        from improvement_recipe_sources import RecipeSourceUnavailable
        observer = self.observer()
        original = files._acl_hash
        path = self.f.f.brain / 'skills/custom/SKILL.md'
        changed = []
        def acl(observed):
            return 'e' * 64 if changed and observed == path else original(observed)
        # Fault injection checks the exact native ACL projection fence, not a native ACL edit.
        with patch.object(files, '_acl_hash', acl), after_return(self.host.selected_engine,
                                                               lambda: changed.append(True), occurrence=3):
            with self.assertRaises(RecipeSourceUnavailable):
                self.capture(observer)

    def test_same_brain_different_actor_is_rejected_by_authenticated_binding(self):
        from improvement_recipe_sources import RecipeSourceUnavailable
        observer = self.observer()
        decoded = []
        other = Principal('owner', 'other-owner', str(self.f.f.brain))
        with after_return(HostContextRecords._decode, lambda: decoded.append(True)):
            with self.assertRaises(AssetUnavailable) as caught:
                observer.capture(other, self.meta['context_id'], expected_generation=self.meta['generation'])
        self.assertEqual(decoded, [True])
        self.assertNotIsInstance(caught.exception, RecipeSourceUnavailable)

    def test_retained_goal_store_connection_callback_drift_is_integrity_error(self):
        observer = self.observer()
        original = self.f.assets.store._conn
        with patch.object(self.f.assets.store, '_conn', lambda: original()):
            with self.assertRaises(IM.ConflictError):
                self.capture(observer)

    def test_owner_rule_hash_validates_complete_v2_and_preserves_archive_order(self):
        from improvement_recipe_sources import owner_rule_hash
        capture = self.binding['capture']
        expected = IM._hash([{key: source[key] for key in
            ('kind', 'ref', 'locator', 'required', 'present', 'hash', 'projection_hash')}
            for source in capture['sources'] if source['role'] == 'protected'])
        self.assertEqual(owner_rule_hash(capture), expected)
        unknown = copy.deepcopy(capture)
        unknown['baseline_context']['coverage'] = 'unknown'
        with self.assertRaises(PermissionError):
            owner_rule_hash(unknown)
        malformed = copy.deepcopy(capture)
        malformed['version'] = 1
        with self.assertRaises(ValueError):
            owner_rule_hash(malformed)


if __name__ == '__main__':
    unittest.main()
