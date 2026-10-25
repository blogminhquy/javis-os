"""Actual published schema6 upgrade/rollback; no engine or runtime authority."""
from _paths import ROOT, SERVER  # noqa: F401

import hashlib
import json
import importlib
import importlib.util
import shutil
import sqlite3
import subprocess
import sys
import threading
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from unittest.mock import patch

import test_improvement_store as fixtures
import improvement_store as IM
import test_improvement_semantic_review as semantic
from improvement_view_protocol import view_manifest, view_hash
from improvement_experiment_protocol import comparison_hash

RELEASED_C = '2727edcc5cdfab6f2dcf2e2871164f22f2771f92'
VIEWS_BACKUP = '.pre-improvement-m2-views.bak'
_READER = None


def released_reader():
    global _READER
    if _READER is None:
        raw = subprocess.run(['git', 'show', RELEASED_C + ':server/improvement_store.py'],
            cwd=ROOT, capture_output=True, check=True).stdout
        reader = types.ModuleType('_published_improvement_schema6')
        sys.modules[reader.__name__] = reader
        exec(compile(raw, 'published-schema6/improvement_store.py', 'exec'), reader.__dict__)
        assert reader.SCHEMA_VERSION == 6
        _READER = reader
    return _READER


def history(database):
    with closing(database._conn()) as connection:
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master "
            "WHERE type='table' AND name LIKE 'improvement_%' ORDER BY name")]
        return {table: [tuple(row) for row in connection.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]
                for table in tables}


class ViewMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_reader = released_reader()

    def setUp(self):
        self.f = fixtures.ImprovementStoreTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.database, self.assets, self.owner = self.f.rs, self.f.store, self.f.owner
        with patch.object(IM, 'ensure', side_effect=self.old_reader.ensure):
            self.baseline = self.f.capture()
        self.assertEqual(IM._schema_version(self.database), 6)
        self.before = history(self.database)

    def assert_retained(self):
        after = history(self.database)
        self.assertEqual({name: after[name] for name in self.before if name != 'improvement_schema'},
                         {name: rows for name, rows in self.before.items() if name != 'improvement_schema'})

    def test_schema6_upgrade_preserves_encrypted_history_and_actual_reader_rollback(self):
        IM.ensure(self.database)
        self.assertEqual(IM._schema_version(self.database), IM.SCHEMA_VERSION, 'Current migration is absent')
        self.assert_retained()
        with closing(self.database._conn()) as connection:
            names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({'improvement_effective_views', 'improvement_effective_view_assets',
                         'improvement_comparison_views'} <= names)
        self.assertEqual(self.assets.read_revision(self.owner, self.baseline['revision_id']), self.f.source()[1])
        backup = self.database.path.with_name(self.database.path.name + VIEWS_BACKUP)
        self.assertTrue(backup.is_file())
        backup_hash = hashlib.sha256(backup.read_bytes()).hexdigest()
        restored = self.f.root / 'restored-schema6.sqlite3'
        shutil.copyfile(backup, restored)
        old = self.old_reader.read_existing(restored, self.f.blobs)
        self.assertEqual(self.old_reader._schema_version(old.store), 6)
        self.assertEqual(history(old.store), self.before)
        self.assertEqual(old.read_revision(self.owner, self.baseline['revision_id']), self.f.source()[1])
        IM.ensure(self.database)
        self.assertEqual(hashlib.sha256(backup.read_bytes()).hexdigest(), backup_hash)

    def test_current_c_binary_refuses_schema7_before_any_backup_write_or_decryption(self):
        IM.ensure(self.database)
        self.assertEqual(IM._schema_version(self.database), IM.SCHEMA_VERSION)
        before = history(self.database)
        with patch.object(self.database, '_backup_before', side_effect=AssertionError('Old code cannot write')), \
                patch.object(self.f.blobs, 'read', side_effect=AssertionError('Old code cannot decrypt')):
            with self.assertRaises(self.old_reader.SchemaError):
                self.old_reader.ensure(self.database)
            with self.assertRaises(self.old_reader.SchemaError):
                self.old_reader.read_existing(self.database.path, self.f.blobs)
        self.assertEqual(history(self.database), before)

    def test_concurrent_first_writers_take_exactly_one_schema6_views_backup(self):
        gate, calls = threading.Barrier(2), []
        original = self.database._backup_before

        def backup(*args):
            calls.append(args)
            return original(*args)

        def migrate(_):
            gate.wait(timeout=10)
            IM.ensure(self.database)

        with patch.object(self.database, '_backup_before', side_effect=backup), ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(migrate, (1, 2)))
        self.assertEqual(calls, [('improvement_compositions', '.pre-improvement-m2-compose.bak'),
                                 ('improvement_effective_views', VIEWS_BACKUP)])
        self.assertEqual(IM._schema_version(self.database), IM.SCHEMA_VERSION)
        self.assert_retained()
        backup = self.database.path.with_name(self.database.path.name + VIEWS_BACKUP)
        with closing(sqlite3.connect(backup)) as connection:
            self.assertEqual(connection.execute('SELECT version FROM improvement_schema').fetchone()[0], 6)

    def test_failed_views_ddl_rolls_back_all_new_objects_and_schema_version(self):
        self.assertIsNotNone(importlib.util.find_spec('improvement_view_schema'), 'Actual view schema is absent')
        schema = importlib.import_module('improvement_view_schema')
        with patch.object(schema, 'SCHEMA', (*schema.SCHEMA, 'INVALID VIEW MIGRATION')):
            with self.assertRaises(sqlite3.OperationalError):
                IM.ensure(self.database)
        self.assertEqual(IM._schema_version(self.database), 6)
        self.assertEqual(history(self.database), self.before)
        with closing(self.database._conn()) as connection:
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name='improvement_effective_views'").fetchone())
        IM.ensure(self.database)
        self.assertEqual(IM._schema_version(self.database), IM.SCHEMA_VERSION)

    def test_unknown_versions_reject_before_backup_or_mutation(self):
        # Unknown means newer than this build (9 and 10 are known intermediate versions now).
        for version in (IM.SCHEMA_VERSION + 1, 999):
            with self.subTest(version=version):
                with self.database._Tx(self.database) as connection:
                    connection.execute('UPDATE improvement_schema SET version=?', (version,))
                before = history(self.database)
                with patch.object(self.database, '_backup_before', side_effect=AssertionError('Unknown cannot write')):
                    with self.assertRaises(IM.SchemaError):
                        IM.ensure(self.database)
                    with self.assertRaises(IM.SchemaError):
                        IM.read_existing(self.database.path, self.f.blobs)
                self.assertEqual(history(self.database), before)

    def test_fresh_schema7_retains_pre_m0_backup_without_fabricating_schema6(self):
        fresh = type(self.database)(self.f.root / 'fresh.sqlite3')
        IM.ensure(fresh)
        self.assertEqual(IM._schema_version(fresh), IM.SCHEMA_VERSION)
        self.assertTrue(fresh.path.with_name(fresh.path.name + '.pre-improvement-m0.bak').is_file())
        self.assertFalse(fresh.path.with_name(fresh.path.name + VIEWS_BACKUP).exists())

    def test_current_metadata_reader_remains_read_only_probe_free_and_decrypt_free(self):
        IM.ensure(self.database)
        self.assertEqual(IM._schema_version(self.database), IM.SCHEMA_VERSION)
        before = history(self.database)
        with patch.object(self.database, '_backup_before', side_effect=AssertionError('Cold metadata cannot write')), \
                patch.object(self.f.blobs, 'read', side_effect=AssertionError('Cold metadata cannot decrypt')):
            reader = IM.read_existing(self.database.path, self.f.blobs)
            self.assertEqual(reader.get_policy(self.owner), {'mode': 'suggest', 'version': 0})
            with closing(reader.store._conn()) as connection:
                self.assertEqual(connection.execute('SELECT count(*) FROM improvement_effective_views').fetchone()[0], 0)
                with self.assertRaises(sqlite3.OperationalError):
                    connection.execute('CREATE TABLE unauthorized_write(value TEXT)')
        self.assertEqual(history(self.database), before)


class ViewScopeTests(unittest.IsolatedAsyncioTestCase):
    # Reuse actual preparation/admission/settled role publication, with an injected
    # synthetic SDK adapter. This is SQL evidence, never native qualification.
    setUp = semantic.SemanticReviewTests.setUp
    factory = semantic.SemanticReviewTests.factory
    prepare = semantic.SemanticReviewTests.prepare
    adapter = semantic.SemanticReviewTests.adapter
    body_patch = semantic.SemanticReviewTests.body_patch
    service = semantic.SemanticReviewTests.service
    review = semantic.SemanticReviewTests.review

    async def asyncSetUp(self):
        subject = await self.service()
        self.semantic_subject = subject
        result = await self.review(subject)
        plans, brain = self.f.plans, self.owner.brain_id
        authority = plans.authoring.authorize_diff(self.owner, self.candidate['candidate_id'], expected_generation=1,
            before_hash=self.candidate['base_hash'], after_hash=self.candidate['content_hash'], event_key='views-authorize-exact-diff')
        with closing(self.assets.store._conn()) as connection:
            generation = connection.execute('SELECT generation FROM improvement_experiments WHERE id=? AND brain_id=?',
                ('association-experiment', brain)).fetchone()[0]
        bound = plans.bind_arm(self.owner, 'association-experiment', self.candidate['candidate_id'],
            authority['authority_id'], expected_generation=generation, event_key='views-bind-actual-arm')
        frozen = plans.freeze(self.owner, 'association-experiment', bound['ordinal'], 'tuning',
            expected_generation=bound['generation'], event_key='views-freeze-actual-comparison')
        with closing(self.assets.store._conn()) as connection:
            self.comparison = dict(connection.execute('SELECT * FROM improvement_comparisons WHERE id=?',
                (frozen['comparison_id'],)).fetchone())
            self.proposal = dict(connection.execute('SELECT * FROM improvement_skill_candidates WHERE id=?',
                (self.candidate['candidate_id'],)).fetchone())
            self.target = dict(connection.execute('SELECT * FROM improvement_targets WHERE id=?',
                (self.proposal['target_id'],)).fetchone())
            receipt = dict(connection.execute('SELECT * FROM improvement_semantic_receipts WHERE id=?',
                (result['receipt_id'],)).fetchone())
            definition = json.loads(connection.execute('SELECT definition_json FROM improvement_experiments').fetchone()[0])
            self.arm = dict(connection.execute('SELECT * FROM improvement_experiment_arms').fetchone())
        pins = json.loads(self.assets.blobs.read(brain, receipt['binding_blob_hash']))
        self.manifests, self.views, self.view_assets = {}, {}, {}
        for variant in ('baseline', 'candidate'):
            candidate, target = self.proposal, self.target
            content_hash = candidate['base_hash'] if variant == 'baseline' else candidate['content_hash']
            manifest = view_manifest({'version': 1, 'evidence_class': 'technical', 'brain_id': brain,
                'experiment_id': candidate['experiment_id'], 'context_id': candidate['context_id'],
                'context_generation': definition['context_generation'], 'comparison_id': self.comparison['id'],
                'comparison_hash': comparison_hash(self.comparison), 'definition_hash': self.comparison['definition_hash'],
                'arm_ordinal': self.comparison['ordinal'], 'arm_hash': self.comparison['arm_hash'],
                'candidate_id': candidate['id'], 'variant': variant,
                'target': {**{key: candidate[key] for key in ('target_id', 'base_revision_id', 'base_hash', 'base_generation')},
                    **{key: target[key] for key in ('canonical_ref', 'identity', 'protected_hash', 'ownership')}},
                **{key: definition[key] for key in ('engine_config_hash', 'baseline_context_hash', 'contract_hash',
                    'case_set_hash', 'grant_hash', 'scope_hash', 'policy_version')},
                'source_authority_hash': pins['source_authority_hash'],
                'semantic': {'receipt_id': receipt['id'], 'binding_hash': receipt['binding_hash'],
                    'assessment_hash': receipt['assessment_hash'], 'dependency_hash': pins['dependency_hash'], 'owner_event_key': None},
                'assets': [{'id': candidate['base_revision_id'] if variant == 'baseline' else candidate['id'],
                    'canonical_ref': target['canonical_ref'], 'before_hash': candidate['base_hash'],
                    'content_hash': content_hash, 'identity': target['identity'],
                    'authority_hash': pins['source_authority_hash'], 'origin': variant}]})
            digest = self.assets.blobs.write(brain, IM._json(manifest).encode())
            self.assertEqual(digest, view_hash(manifest))
            identifier = 'view_' + variant
            self.manifests[variant] = manifest
            self.views[variant] = {'id': identifier, 'brain_id': brain, 'experiment_id': candidate['experiment_id'],
                'target_id': candidate['target_id'], 'context_id': candidate['context_id'],
                'comparison_id': self.comparison['id'], 'variant': variant, 'candidate_id': candidate['id'],
                **{key: candidate[key] for key in ('base_revision_id', 'base_hash', 'base_generation')},
                'source_authority_hash': pins['source_authority_hash'], 'semantic_receipt_id': receipt['id'],
                'manifest_hash': digest, 'manifest_blob_hash': digest, 'created_at': 1.0}
            asset = manifest['assets'][0]
            self.view_assets[variant] = {'view_id': identifier, 'brain_id': brain, 'position': 0,
                'asset_id': asset['id'], **{key: asset[key] for key in ('canonical_ref', 'before_hash', 'content_hash',
                    'identity', 'authority_hash', 'origin')}}
        proof = {'comparison_id': self.comparison['id'], 'base_view_id': 'view_baseline',
            'candidate_view_id': 'view_candidate', 'semantic_receipt_id': receipt['id'],
            'manifest_hashes': [self.views[v]['manifest_hash'] for v in ('baseline', 'candidate')]}
        digest = self.assets.blobs.write(brain, IM._json(proof).encode())
        self.binding = {key: value for key, value in proof.items() if key != 'manifest_hashes'}
        self.binding.update(brain_id=brain, binding_hash=digest, binding_blob_hash=digest, created_at=1.0)
        self.assertIsNotNone(importlib.util.find_spec('improvement_view_schema'), 'Actual immutable view SQL is absent')

    @staticmethod
    def insert(connection, table, row):
        connection.execute('INSERT INTO ' + table + '(' + ','.join(row) + ') VALUES(' +
            ','.join('?' for _ in row) + ')', tuple(row.values()))

    def save(self, *, assets=True, binding=True):
        with self.assets.store._Tx(self.assets.store) as connection:
            for variant in ('baseline', 'candidate'):
                self.insert(connection, 'improvement_effective_views', self.views[variant])
                if assets:
                    self.insert(connection, 'improvement_effective_view_assets', self.view_assets[variant])
            if binding:
                self.insert(connection, 'improvement_comparison_views', self.binding)

    def rejected(self, table, row):
        with self.assertRaises(sqlite3.IntegrityError), self.assets.store._Tx(self.assets.store) as connection:
            self.insert(connection, table, row)

    async def test_actual_encrypted_pair_has_exact_cold_metadata_and_no_canonical_write(self):
        before = self.f.f.f.skill.read_bytes()
        self.save()
        reader = IM.read_existing(self.assets.store.path, self.assets.blobs)
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Cold metadata cannot decrypt')), \
                patch.object(self.assets.store, '_backup_before', side_effect=AssertionError('Cold metadata cannot migrate')), \
                closing(reader.store._conn()) as connection:
            rows = [dict(row) for row in connection.execute('SELECT * FROM improvement_effective_views ORDER BY variant')]
            self.assertEqual(rows, [self.views[v] for v in ('baseline', 'candidate')])
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(connection.execute('SELECT current_revision_id FROM improvement_targets WHERE id=?',
                (self.target['id'],)).fetchone()[0], self.proposal['base_revision_id'])
        for variant, manifest in self.manifests.items():
            self.assertEqual(json.loads(self.assets.blobs.read(self.owner.brain_id,
                self.views[variant]['manifest_blob_hash'])), manifest)
        self.assertEqual(self.f.f.f.skill.read_bytes(), before)

    async def test_foreign_view_scope_and_source_fields_reject(self):
        for key, bad in (('brain_id', 'foreign-brain'), ('experiment_id', 'foreign-experiment'),
                ('target_id', 'foreign-target'), ('context_id', 'foreign-context'),
                ('comparison_id', 'foreign-comparison'), ('candidate_id', 'foreign-candidate'),
                ('semantic_receipt_id', 'foreign-receipt'), ('base_revision_id', 'foreign-base'),
                ('base_hash', '0' * 64), ('base_generation', 99), ('source_authority_hash', '0' * 64),
                ('variant', 'live'), ('manifest_hash', '0' * 64)):
            with self.subTest(key=key):
                self.rejected('improvement_effective_views', {**self.views['baseline'], key: bad})

    async def test_asset_body_source_origin_and_single_position_are_exact(self):
        self.save(assets=False, binding=False)
        for variant in ('baseline', 'candidate'):
            for key, bad in (('asset_id', 'foreign-asset'), ('brain_id', 'foreign-brain'), ('position', 1),
                    ('canonical_ref', 'skills/other/SKILL.md'), ('before_hash', '0' * 64),
                    ('content_hash', '0' * 64), ('identity', '0' * 64), ('authority_hash', '0' * 64),
                    ('origin', 'candidate' if variant == 'baseline' else 'baseline')):
                with self.subTest(variant=variant, key=key):
                    self.rejected('improvement_effective_view_assets', {**self.view_assets[variant], key: bad})

    async def test_binding_requires_two_complete_correct_variants_and_exact_receipt(self):
        self.save(assets=False, binding=False)
        self.rejected('improvement_comparison_views', self.binding)
        with self.assets.store._Tx(self.assets.store) as connection:
            for row in self.view_assets.values():
                self.insert(connection, 'improvement_effective_view_assets', row)
        for changes in ({'brain_id': 'foreign-brain'}, {'base_view_id': 'view_candidate'},
                {'candidate_view_id': 'view_baseline'}, {'semantic_receipt_id': 'foreign-receipt'},
                {'binding_hash': '0' * 64}, {'comparison_id': 'foreign-comparison'}):
            self.rejected('improvement_comparison_views', {**self.binding, **changes})
        with self.assets.store._Tx(self.assets.store) as connection:
            self.insert(connection, 'improvement_comparison_views', self.binding)

    async def test_history_is_immutable_and_variants_and_binding_are_unique(self):
        self.save()
        for table in ('improvement_effective_views', 'improvement_effective_view_assets', 'improvement_comparison_views'):
            for statement in ('UPDATE ' + table + ' SET brain_id=brain_id', 'DELETE FROM ' + table):
                with self.subTest(statement=statement), self.assertRaisesRegex(sqlite3.IntegrityError, 'immutable'), \
                        self.assets.store._Tx(self.assets.store) as connection:
                    connection.execute(statement)
        self.rejected('improvement_effective_views', {**self.views['baseline'], 'id': 'duplicate_view'})
        self.rejected('improvement_effective_view_assets', self.view_assets['baseline'])
        self.rejected('improvement_comparison_views', self.binding)

    async def test_individually_valid_other_candidate_receipt_and_comparison_cannot_be_spliced(self):
        self.save()
        plans = self.f.plans
        candidate = plans.authoring.stage(self.owner, 'association-experiment', self.body_patch('Retain owner rules.\nVerify totals twice.\n'),
            event_key='views-second-actual-candidate')
        with closing(self.assets.store._conn()) as connection:
            generation = connection.execute('SELECT generation FROM improvement_experiments').fetchone()[0]
        reviewed = await self.semantic_subject.review(self.owner, candidate['candidate_id'],
            expected_generation=generation, event_key='views-second-actual-review')
        authority = plans.authoring.authorize_diff(self.owner, candidate['candidate_id'], expected_generation=1,
            before_hash=candidate['base_hash'], after_hash=candidate['content_hash'], event_key='views-second-exact-diff')
        with closing(self.assets.store._conn()) as connection:
            generation = connection.execute('SELECT generation FROM improvement_experiments').fetchone()[0]
        bound = plans.bind_arm(self.owner, 'association-experiment', candidate['candidate_id'], authority['authority_id'],
            expected_generation=generation, event_key='views-second-bind-arm')
        frozen = plans.freeze(self.owner, 'association-experiment', bound['ordinal'], 'tuning',
            expected_generation=bound['generation'], event_key='views-second-freeze-comparison')
        for changes in ({'candidate_id': candidate['candidate_id']}, {'semantic_receipt_id': reviewed['receipt_id']},
                {'comparison_id': frozen['comparison_id']},
                {'comparison_id': frozen['comparison_id'], 'candidate_id': candidate['candidate_id']}):
            self.rejected('improvement_effective_views', {**self.views['candidate'], 'id': 'spliced_view', **changes})
        other_view = {**self.views['candidate'], 'id': 'other_candidate_view', 'comparison_id': frozen['comparison_id'],
            'candidate_id': candidate['candidate_id'], 'semantic_receipt_id': reviewed['receipt_id']}
        # Valid SQL metadata is still not a validated encrypted manifest or host
        # execution authority; Task2 must authenticate its actual plaintext.
        with self.assets.store._Tx(self.assets.store) as connection:
            self.insert(connection, 'improvement_effective_views', other_view)
            self.insert(connection, 'improvement_effective_view_assets', {**self.view_assets['candidate'],
                'view_id': other_view['id'], 'asset_id': candidate['candidate_id'], 'content_hash': candidate['content_hash']})
        self.rejected('improvement_comparison_views', {**self.binding, 'candidate_view_id': other_view['id']})

    async def test_missing_or_changed_view_guard_refuses_new_authority_without_repair(self):
        schema = importlib.import_module('improvement_view_schema')
        with self.assets.store._Tx(self.assets.store) as connection:
            schema.assert_installed(connection)
            connection.execute('DROP TRIGGER improvement_effective_view_scope')
        before = history(self.assets.store)
        with closing(self.assets.store._conn()) as connection, self.assertRaisesRegex(IM.ConflictError, 'view_schema_changed'):
            schema.assert_installed(connection)
        # The current-version audit refuses the drifted family instead of silently repairing it.
        with self.assertRaises(IM.ConflictError):
            IM.ensure(self.assets.store)
        self.assertEqual(history(self.assets.store), before)
        with closing(self.assets.store._conn()) as connection:
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name='improvement_effective_view_scope'").fetchone())


class SettledHistoryMigrationTests(unittest.IsolatedAsyncioTestCase):
    factory = semantic.SemanticReviewTests.factory
    prepare = semantic.SemanticReviewTests.prepare
    adapter = semantic.SemanticReviewTests.adapter
    body_patch = semantic.SemanticReviewTests.body_patch
    service = semantic.SemanticReviewTests.service
    review = semantic.SemanticReviewTests.review

    def setUp(self):
        with patch.object(IM, 'ensure', side_effect=released_reader().ensure):
            semantic.SemanticReviewTests.setUp(self)

    async def test_real_schema6_role_results_receipts_calls_and_encrypted_bytes_survive_upgrade_and_restore(self):
        with patch.object(IM, 'ensure', side_effect=released_reader().ensure):
            subject = await self.service()
            result = await self.review(subject)
        database = self.assets.store
        self.assertEqual(IM._schema_version(database), 6)
        before = history(database)
        with closing(database._conn()) as connection:
            calls = [tuple(row) for row in connection.execute('SELECT * FROM agent_calls ORDER BY id')]
            receipt = dict(connection.execute('SELECT * FROM improvement_semantic_receipts WHERE id=?',
                (result['receipt_id'],)).fetchone())
        plaintext = self.assets.blobs.read(self.owner.brain_id, receipt['blob_hash'])
        self.assertTrue(before['improvement_operation_results'])
        self.assertTrue(before['improvement_semantic_receipts'])
        self.assertTrue(calls)
        IM.ensure(database)
        self.assertEqual(IM._schema_version(database), IM.SCHEMA_VERSION)
        after = history(database)
        self.assertEqual({name: after[name] for name in before if name != 'improvement_schema'},
            {name: rows for name, rows in before.items() if name != 'improvement_schema'})
        backup = database.path.with_name(database.path.name + VIEWS_BACKUP)
        restored = self.f.f.f.root / 'restored-settled-schema6.sqlite3'
        shutil.copyfile(backup, restored)
        old = released_reader().read_existing(restored, self.assets.blobs)
        self.assertEqual(released_reader()._schema_version(old.store), 6)
        self.assertEqual(history(old.store), before)
        with closing(database._conn()) as current, closing(old.store._conn()) as previous:
            self.assertEqual([tuple(row) for row in current.execute('SELECT * FROM agent_calls ORDER BY id')], calls)
            self.assertEqual([tuple(row) for row in previous.execute('SELECT * FROM agent_calls ORDER BY id')], calls)
        self.assertEqual(self.assets.blobs.read(self.owner.brain_id, receipt['blob_hash']), plaintext)


if __name__ == '__main__':
    unittest.main()
