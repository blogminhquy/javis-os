"""View-format ownership guards with genuine existing Trial/CallLedger history."""
from _paths import ROOT, SERVER  # noqa: F401

import json
import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

import improvement_store as IM
from improvement_claude import ClaudeTrialAdapter
from improvement_experiment_admission import ExperimentAdmission
from improvement_experiment_protocol import matrix_cell
import test_improvement_view_sources as sources
import test_improvement_view_schema as schema_fixtures


class ViewAdmissionSchemaTests(sources.SourceFixture, unittest.IsolatedAsyncioTestCase):
    def baseline_cell(self):
        matrix = json.loads(self.assets.blobs.read(self.owner.brain_id, self.comparison['matrix_blob_hash']))
        return next((position, matrix_cell(matrix, position)) for position in range(self.comparison['cell_count'])
            if matrix_cell(matrix, position)['variant'] == 'baseline')

    async def test_preparation_trial_cannot_be_linked_as_a_v4_view_trial(self):
        subject = self.views_service()
        metadata = self.freeze(subject)
        position, cell = self.baseline_cell()
        with closing(self.assets.store._conn()) as connection:
            self.assertIsNotNone(connection.execute("SELECT name FROM sqlite_master WHERE name='improvement_view_trial_links'").fetchone(),
                'Actual immutable view Trial link table is absent')
            trial = dict(connection.execute('SELECT * FROM improvement_trials WHERE id=?', (self.admitted.trial_id,)).fetchone())
        self.assertEqual(json.loads(trial['request_json'])['version'], 3)
        row = {'comparison_id': self.comparison['id'], 'brain_id': self.owner.brain_id, 'experiment_id': self.comparison['experiment_id'],
            'cell_position': position, 'trial_id': trial['id'], 'request_hash': trial['request_hash'], **cell,
            'view_id': metadata['views']['baseline']['view_id'], 'view_hash': metadata['views']['baseline']['manifest_hash'],
            'binding_hash': metadata['binding_hash'], 'created_at': 1.0}
        with self.assertRaises(sqlite3.IntegrityError), self.assets.store._Tx(self.assets.store) as connection:
            schema_fixtures.ViewScopeTests.insert(connection, 'improvement_view_trial_links', row)

    async def test_bound_view_comparison_rejects_legacy_admission_before_plaintext_or_native(self):
        subject = self.views_service()
        self.freeze(subject)
        position, _ = self.baseline_cell()
        counts = self.counts()
        with (patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Legacy fallback cannot decrypt')),
              patch.object(ClaudeTrialAdapter, 'verify', side_effect=AssertionError('Legacy fallback cannot probe native')),
              self.assertRaisesRegex(PermissionError, 'view_trial_version_required')):
            ExperimentAdmission(self.f.plans).admit(self.owner, self.comparison['experiment_id'], self.comparison['id'],
                position, expected_generation=self.generation(), event_key='deny-legacy-after-bound-views')
        self.assertEqual(self.counts(), counts)

    async def test_actual_legacy_link_prevents_even_direct_sql_view_binding_atomically(self):
        position, _ = self.baseline_cell()
        with patch.object(ClaudeTrialAdapter, 'verify', return_value={'supported': True, 'capability_hash': 'c' * 64}):
            admitted = ExperimentAdmission(self.f.plans).admit(self.owner, self.comparison['experiment_id'], self.comparison['id'],
                position, expected_generation=self.generation(), event_key='real-legacy-before-view-binding')
        with closing(self.assets.store._conn()) as connection:
            self.assertIsNotNone(connection.execute('SELECT 1 FROM improvement_experiment_trial_links WHERE trial_id=?',
                (admitted.trial_id,)).fetchone())
        counts = self.counts()
        with self.assertRaises(sqlite3.IntegrityError), self.assets.store._Tx(self.assets.store) as connection:
            for variant in ('baseline', 'candidate'):
                schema_fixtures.ViewScopeTests.insert(connection, 'improvement_effective_views', self.views[variant])
                schema_fixtures.ViewScopeTests.insert(connection, 'improvement_effective_view_assets', self.view_assets[variant])
            schema_fixtures.ViewScopeTests.insert(connection, 'improvement_comparison_views', self.binding)
        self.assertEqual(self.counts(), counts)


class LegacyFormatShapeTests(unittest.TestCase):
    def test_malformed_legacy_lineage_rejects_as_shape_before_sql_or_plaintext(self):
        from improvement_experiment_lineage import require_experiment_version
        with closing(sqlite3.connect(':memory:')) as connection:
            for lineage in (None, {}, False):
                value = {'version': 2, 'pins': {}, 'lineage': lineage}
                with self.subTest(lineage=lineage), self.assertRaises(ValueError):
                    require_experiment_version(connection, 'shape-only-brain', value)


if __name__ == '__main__':
    unittest.main()
