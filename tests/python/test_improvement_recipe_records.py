"""Cold record owner controls use real encrypted archive records and SQL CAS."""
from _paths import ROOT, SERVER  # noqa: F401
import importlib.util
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import improvement_store as IM
from resonance_store import GoalStore
import test_improvement_recipe_archive as fixtures


class RecipeRecordTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('improvement_recipe_records'), 'Actual cold RecipeRecords is absent')
        self.f = fixtures.RecipeArchiveTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.owner, self.assets = self.f.owner, self.f.assets
        from improvement_recipe_records import RecipeRecords
        self.records = RecipeRecords(self.assets)
        self.saved = self.f.capture()

    def test_read_existing_metadata_off_without_migrate_host_body_or_native(self):
        self.assets.set_policy(self.owner, 'off', expected_version=0, event_key='cold-record-off')
        from improvement_recipe_records import RecipeRecords
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('No body decryption')), \
             patch.object(IM, 'ensure', side_effect=AssertionError('No migration')), \
             patch.object(GoalStore, '__init__', side_effect=AssertionError('No writable initialization')):
            reader = RecipeRecords(IM.read_existing(self.f.store.path, self.assets.blobs))
            item = reader.get(self.owner, self.saved['recipe_id'])
            self.assertEqual(item['record_status'], 'active')
            self.assertEqual(item['authority_status'], 'not_checked')
            self.assertIsNone(item['unavailability_reason'])
            self.assertNotIn('procedure', item)
            self.assertEqual(reader.list(self.owner), {'items': [item], 'next_cursor': None})

    def test_exact_nine_cold_metadata_and_owner_revocation_remain_supported_after_off(self):
        import improvement_recipe_schema as nine
        from improvement_recipe_records import RecipeRecords
        self.assets.set_policy(self.owner, 'off', expected_version=0, event_key='historical-nine-off')
        # Restore the exact historical trigger only; archive/event/ciphertext
        # bytes stay unchanged and no view refs are reclassified.
        with self.f.store._Tx(self.f.store) as connection:
            connection.execute('DROP TRIGGER improvement_recipe_trial_scope')
            connection.execute(next(sql for sql in nine.statements() if sql.startswith('CREATE TRIGGER improvement_recipe_trial_scope ')))
            connection.execute('UPDATE improvement_schema SET version=9')
            nine.assert_installed(connection)
        before = self.f.rows('improvement_recipes')
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Historical cold path cannot decrypt')), \
             patch.object(IM, 'ensure', side_effect=AssertionError('Historical cold path cannot migrate')), \
             patch.object(self.f.host, '_snapshot_observe', side_effect=AssertionError('Historical cold path cannot refresh')):
            reader = RecipeRecords(IM.read_existing(self.f.store.path, self.assets.blobs))
            item = reader.get(self.owner, self.saved['recipe_id'])
            self.assertEqual(reader.list(self.owner), {'items': [item], 'next_cursor': None})
            self.assertEqual(item['authority_status'], 'not_checked')
            result = self.records.revoke(self.owner, self.saved['recipe_id'], expected_generation=1,
                event_key='historical-nine-owner-revoke')
            self.assertEqual(result['status'], 'revoked')
        self.assertEqual(IM._schema_version(self.f.store), 9)
        self.assertEqual(self.f.rows('improvement_recipes'), before)

    def test_revoke_cas_replay_and_foreign_identity_are_cold(self):
        options = {'expected_generation': 1, 'event_key': 'cold-owner-revoke'}
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Cold control cannot decrypt')):
            result = self.records.revoke(self.owner, self.saved['recipe_id'], **options)
            self.assertEqual(result['status'], 'revoked')
            self.assertEqual(self.records.revoke(self.owner, self.saved['recipe_id'], **options), result)
            item = self.records.get(self.owner, self.saved['recipe_id'])
            self.assertEqual(item['unavailability_reason'], 'revoked')
            self.assertEqual(self.f.capture(), self.saved)
            self.assertEqual(self.records.get(self.owner, self.saved['recipe_id'])['record_status'], 'revoked')
            with self.assertRaises(IM.ConflictError):
                self.records.revoke(self.owner, self.saved['recipe_id'], expected_generation=1, event_key='cold-new-stale-revoke')
            with self.assertRaises(PermissionError): self.records.get(self.f.source.other, self.saved['recipe_id'])
            self.assertEqual(self.records.list(self.f.source.other), {'items': [], 'next_cursor': None})

    def test_source_revocation_and_elapsed_expiry_are_unavailable_without_sweep(self):
        expires = self.records.get(self.owner, self.saved['recipe_id'])['expires_at']
        with patch('improvement_recipe_records.time.time', return_value=expires + 1):
            self.assertEqual(self.records.get(self.owner, self.saved['recipe_id'])['unavailability_reason'], 'expired')
        self.f.host.revoke(self.owner, 'association-experiment', expected_generation=1, event_key='cold-revoke-source')
        self.assertEqual(self.records.get(self.owner, self.saved['recipe_id'])['source_grant_status'], 'revoked')
        self.assertEqual(self.records.get(self.owner, self.saved['recipe_id'])['unavailability_reason'], 'source_revoked')

    def test_cursor_supersession_and_historical_event_replay(self):
        second = self.f.capture(key='archive-second-record', decision={**self.f.decision, 'cue': 'Second cue'})
        items = sorted([self.saved['recipe_id'], second['recipe_id']])
        first_page = self.records.list(self.owner, limit=1)
        self.assertEqual(first_page['items'][0]['recipe_id'], items[0])
        self.assertEqual(first_page['next_cursor'], items[0])
        last = self.records.list(self.owner, cursor=items[0], limit=1)
        self.assertEqual(last['items'][0]['recipe_id'], items[1])
        self.assertIsNone(last['next_cursor'])
        options = {'expected_generation': 1, 'event_key': 'cold-owner-supersede'}
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Cold transition cannot decrypt')):
            result = self.records.supersede(self.owner, self.saved['recipe_id'], second['recipe_id'], **options)
            self.records.revoke(self.owner, second['recipe_id'], expected_generation=1, event_key='cold-revoke-successor')
            self.assertEqual(self.records.supersede(self.owner, self.saved['recipe_id'], second['recipe_id'], **options), result)
        self.assertEqual(self.records.get(self.owner, self.saved['recipe_id'])['record_status'], 'superseded')

    def test_expired_successor_cannot_replace_active_record(self):
        second = self.f.capture(key='short-record', decision={**self.f.decision, 'cue': 'Short cue', 'expires_at': time.time() + 100})
        with patch('improvement_recipe_records.time.time', return_value=time.time() + 200), self.assertRaises(PermissionError):
            self.records.supersede(self.owner, self.saved['recipe_id'], second['recipe_id'], expected_generation=1,
                                   event_key='expired-successor-refusal')

    def test_concurrent_generation_cas_has_one_new_action(self):
        barrier = threading.Barrier(2)
        def revoke(number):
            barrier.wait(timeout=10)
            try:
                return self.records.revoke(self.owner, self.saved['recipe_id'], expected_generation=1,
                                           event_key='cold-concurrent-revoke-' + str(number))
            except IM.ConflictError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(revoke, range(2)))
        self.assertEqual(sum(item is not None for item in results), 1)
        self.assertEqual(self.records.get(self.owner, self.saved['recipe_id'])['generation'], 2)

    def test_metadata_remains_historical_after_new_canonical_target_revision(self):
        from improvement_assets import capture_source
        old = self.records.get(self.owner, self.saved['recipe_id'])
        self.f.source.skill.write_bytes(self.f.source.skill.read_bytes() + b'New canonical body revision.\n')
        source, raw = capture_source(self.f.source.brain, 'skill', 'report', pack_state_dir=self.f.source.root / 'packs')
        self.assets.capture(self.owner, source, raw, expected_generation=1, event_key='canonical-revision-after-archive')
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Historical metadata cannot decrypt')):
            self.assertEqual(self.records.get(self.owner, self.saved['recipe_id']), old)

    def test_missing_state_is_source_unavailable_and_list_shape_is_closed(self):
        row = self.f.rows('improvement_recipes')[0]
        row.update(id='ir_missing_state', manifest_hash='f' * 64, manifest_blob_hash='f' * 64)
        with self.f.store._Tx(self.f.store) as connection:
            connection.execute('INSERT INTO improvement_recipes(' + ','.join(row) + ') VALUES(' + ','.join('?' for _ in row) + ')', list(row.values()))
        item = self.records.get(self.owner, row['id'])
        self.assertEqual(item['source_grant_status'], 'unavailable')
        self.assertEqual(item['unavailability_reason'], 'source_revoked')
        self.assertEqual(set(item), {'recipe_id', 'manifest_hash', 'experiment_id', 'context_id', 'target_id', 'base_revision_id',
            'candidate_id', 'comparison_report_id', 'scope_hash', 'engine_config_hash', 'owner_rule_hash', 'target_protected_hash',
            'language', 'verdict', 'checked_at', 'expires_at', 'created_at', 'record_status', 'generation', 'reason', 'successor_id',
            'source_grant_status', 'unavailability_reason', 'authority_status', 'business_proof'})
        with self.assertRaises(IM.ConflictError):
            self.records.revoke(self.owner, row['id'], expected_generation=1, event_key='cold-deny-missing-state')
        for invalid in (0, 101, True):
            with self.assertRaises(ValueError): self.records.list(self.owner, limit=invalid)

    def test_missing_source_grant_never_reports_active_even_without_sweep(self):
        with self.f.store._Tx(self.f.store) as connection:
            connection.execute('DELETE FROM improvement_trial_context_grants WHERE brain_id=?', (self.owner.brain_id,))
        item = self.records.get(self.owner, self.saved['recipe_id'])
        self.assertEqual(item['record_status'], 'unavailable')
        self.assertEqual(item['source_grant_status'], 'unavailable')
        self.assertEqual(item['unavailability_reason'], 'source_revoked')

    def test_missing_source_grant_does_not_block_actual_owner_state_revocation(self):
        with self.f.store._Tx(self.f.store) as connection:
            connection.execute('DELETE FROM improvement_trial_context_grants WHERE brain_id=?', (self.owner.brain_id,))
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Revocation cannot decrypt source/body')):
            options = {'expected_generation': 1, 'event_key': 'cold-revoke-missing-source-grant'}
            result = self.records.revoke(self.owner, self.saved['recipe_id'], **options)
            self.assertEqual(result['status'], 'revoked')
            self.assertEqual(result['generation'], 2)
            self.assertEqual(self.records.revoke(self.owner, self.saved['recipe_id'], **options), result)
        state = self.f.rows('improvement_recipe_states')[0]
        self.assertEqual((state['status'], state['generation']), ('revoked', 2))


class HistoricalRecipeRecordsTests(unittest.TestCase):
    def test_actual_official_eight_reader_is_empty_and_named_record_unavailable_without_migration(self):
        import test_improvement_recipe_schema as historical
        from improvement_blobs import RevisionBlobs
        from improvement_recipe_records import RecipeRecords
        from resonance_store import Principal
        historical.RecipeSchemaTests.setUpClass()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = GoalStore(root / 'resonance.sqlite3')
            historical.RecipeSchemaTests.old.ensure(database)
            self.assertEqual(IM._schema_version(database), 8)
            owner = Principal('owner', 'owner', str(root / 'brain'))
            blobs = RevisionBlobs(root / 'assets')
            with patch.object(IM, 'ensure', side_effect=AssertionError('Cold records cannot migrate')), \
                 patch.object(blobs, 'read', side_effect=AssertionError('Cold records cannot decrypt')):
                reader = RecipeRecords(IM.read_existing(database.path, blobs))
                self.assertEqual(reader.list(owner), {'items': [], 'next_cursor': None})
                with self.assertRaises(PermissionError): reader.get(owner, 'ir_old_missing')
            self.assertEqual(IM._schema_version(database), 8)


if __name__ == '__main__': unittest.main()
