"""Actual SQL/Fernet/source owners; synthetic fixtures prove no native readiness."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import threading
import time
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from unittest.mock import patch

import improvement_store as IM
from improvement_blobs import AssetUnavailable
from improvement_trial_context import ContextSource, capture_context
from improvement_trial_semantics import capture_semantics
import test_improvement_host_snapshots as sources
import test_improvement_preparation as fixtures
import test_improvement_experiment_selection as selections
import test_improvement_improver_inputs as prepared_inputs
from test_improvement_recipe_archive import semantic_capture, traced_selection_cells

import test_improvement_view_sources as view_sources
import test_improvement_view_execution as view_execution


class RecipeViewReferenceTests(view_sources.SourceFixture, unittest.IsolatedAsyncioTestCase):
    owned_service = view_execution.ViewExecutionTests.owned_service
    admit = view_execution.ViewExecutionTests.admit
    view_adapter_factory = view_execution.ViewExecutionTests.view_adapter_factory

    def setUp(self):
        with patch.object(sources.HostSnapshotTests, 'context_capture', semantic_capture):
            view_sources.SourceFixture.setUp(self)

    async def completed_views(self):
        import improvement_claude as native
        from improvement_trial_runner import TrialRunner
        from improvement_comparison_results import ComparisonResults
        from improvement_recipe_archive import RecipeArchive
        service, _ = self.owned_service()
        self.trials, self.executed, self.closed, self.workspaces = service.trials, 0, 0, {}
        actual = []
        for position in (0, 1):
            with patch.object(native.ClaudeTrialAdapter, 'verify', return_value={'supported': True, 'capability_hash': 'd' * 64}):
                admitted = self.admit(service, key='archive-view-storage-cell-' + str(position))
            result = await TrialRunner(self.trials, context_loader=self.host.context_loader,
                live_guard=self.host.live_guard, adapter_factory=self.view_adapter_factory).run(self.owner, admitted.trial_id)
            self.assertEqual(result['status'], 'completed', result)
            actual.append(admitted.trial_id)
        reports = ComparisonResults(self.f.plans)
        reports.create(self.owner, self.comparison['id'], expected_generation=self.generation(), event_key='archive-view-storage-report')
        archive = RecipeArchive(self.f.plans)
        generation = self.generation()
        with closing(self.assets.store._conn()) as connection:
            captured = archive._capture(connection, self.owner, 'association-experiment', self.proposal['id'], generation, 1)
            self.assertTrue(set(actual) <= {ref['trial_id'] for ref in captured['refs']})
            self.assertTrue(all(json.loads(connection.execute('SELECT request_json FROM improvement_trials WHERE id=?',
                (trial,)).fetchone()[0])['version'] == 4 for trial in actual))
        return archive, actual, generation

    def capture_view(self, archive, generation, key, *, principal=None):
        return archive.capture(self.owner if principal is None else principal, 'association-experiment', self.proposal['id'],
            {'kind': 'procedure', 'cue': 'When checking view evidence', 'procedure': 'Check the controlling subtotal.',
             'applicability': [], 'exclusions': [], 'expires_at': time.time() + 4000000},
            expected_generation=generation, expected_context_generation=1, event_key=key)

    def no_view_publication(self):
        with closing(self.assets.store._conn()) as connection:
            for table in ('improvement_recipes', 'improvement_recipe_states', 'improvement_recipe_trial_refs'):
                self.assertEqual(connection.execute('SELECT count(*) FROM ' + table).fetchone()[0], 0, table)
            self.assertEqual(connection.execute("SELECT count(*) FROM improvement_events WHERE operation='recipe_capture'").fetchone()[0], 0)

    def corrupt_stored(self, table, column, value, identifier, key='trial_id'):
        # Negative-only forensic corruption: ordinary writers cannot create
        # this state. Restore every exact SQL guard before the public reader.
        with self.assets.store._Tx(self.assets.store) as connection:
            triggers = list(connection.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name=?", (table,)))
            for trigger in triggers:
                connection.execute('DROP TRIGGER ' + trigger['name'])
            connection.execute('UPDATE '+table+' SET '+column+'=? WHERE '+key+'=?', (value, identifier))
            for trigger in triggers:
                connection.execute(trigger['sql'])

    def assert_sql_refusal(self, row, pin):
        with closing(self.assets.store._conn()) as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                with self.assertRaisesRegex(sqlite3.IntegrityError, 'recipe_trial_scope_mismatch'):
                    connection.execute('INSERT INTO improvement_recipes('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')', list(row.values()))
                    connection.execute('INSERT INTO improvement_recipe_trial_refs VALUES(?,?,?,?,?,?,?,?,?)',
                        (row['id'], self.owner.brain_id, 0, pin['trial_id'], pin['attempt'], pin['result_id'],
                         pin['result_hash'], pin['trace_hash'], pin['trace_count']))
            finally:
                connection.rollback()

    async def test_actual_archive_refuses_stored_view_comparison_binding_source_result_cell_and_request_drift(self):
        archive, actual, generation = await self.completed_views()
        with closing(self.assets.store._conn()) as connection:
            link = dict(connection.execute("SELECT * FROM improvement_view_trial_links WHERE variant='candidate'").fetchone())
            trial = dict(connection.execute('SELECT * FROM improvement_trials WHERE id=?', (link['trial_id'],)).fetchone())
            baseline = connection.execute("SELECT id FROM improvement_effective_views WHERE variant='baseline'").fetchone()[0]
            asset = dict(connection.execute('SELECT * FROM improvement_effective_view_assets WHERE view_id=?', (link['view_id'],)).fetchone())
            result = dict(connection.execute('SELECT * FROM improvement_trial_results WHERE trial_id=?', (link['trial_id'],)).fetchone())
        request = json.loads(trial['request_json'])
        foreign_comparison = copy.deepcopy(request)
        foreign_comparison['lineage']['comparison_id'] = 'foreign-comparison'
        mutations = [
            ('improvement_view_trial_links', 'view_id', baseline, link['view_id'], link['trial_id'], 'trial_id'),
            ('improvement_view_trial_links', 'binding_hash', '0'*64, link['binding_hash'], link['trial_id'], 'trial_id'),
            ('improvement_view_trial_links', 'cell_position', 3999, link['cell_position'], link['trial_id'], 'trial_id'),
            ('improvement_effective_view_assets', 'authority_hash', '0'*64, asset['authority_hash'], link['view_id'], 'view_id'),
            ('improvement_trial_results', 'result_hash', '0'*64, result['result_hash'], result['id'], 'id'),
            ('improvement_trials', 'request_json', IM._json(foreign_comparison), trial['request_json'], trial['id'], 'id'),
            ('improvement_trials', 'request_hash', '0'*64, trial['request_hash'], trial['id'], 'id'),
        ]
        for table, column, damaged, original, identifier, key in mutations:
            with self.subTest(table=table, column=column):
                try:
                    self.corrupt_stored(table, column, damaged, identifier, key)
                    if column == 'request_json':
                        self.corrupt_stored('improvement_trials', 'request_hash', IM._hash(foreign_comparison), trial['id'], 'id')
                    with self.assertRaises((PermissionError, IM.ConflictError, AssetUnavailable, ValueError)):
                        self.capture_view(archive, generation, 'archive-corrupt-view-' + column)
                    self.no_view_publication()
                finally:
                    self.corrupt_stored(table, column, original, identifier, key)
                    if column == 'request_json':
                        self.corrupt_stored('improvement_trials', 'request_hash', trial['request_hash'], trial['id'], 'id')
        from resonance_store import Principal
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Foreign brain cannot decrypt archive evidence')):
            with self.assertRaises(PermissionError):
                self.capture_view(archive, generation, 'archive-foreign-view-brain', principal=Principal('owner', 'foreign-owner', 'foreign-brain'))
        self.no_view_publication()
        # The exact valid graph remains readable after each corruption control.
        saved = self.capture_view(archive, generation, 'archive-restored-view-graph')
        self.assertEqual(saved['kind'], 'recorded')

    async def test_view_archive_current_revocation_and_late_trace_during_last_blob_write_refuse(self):
        from improvement_trial_evidence import _packet
        archive, actual, generation = await self.completed_views()
        trial = actual[-1]
        with closing(self.assets.store._conn()) as connection:
            sequence = connection.execute('SELECT max(sequence)+1 FROM improvement_trial_observations WHERE trial_id=?', (trial,)).fetchone()[0]
        _, raw = _packet({'version': 1, 'sequence': sequence, 'type': 'worker_error',
            'reason': 'late_view_storage_observation', 'error_type': 'SyntheticFixture'})
        digest = self.assets.blobs.write(self.owner.brain_id, raw)
        write, injected = self.assets.blobs.write, False
        def late(brain, raw):
            nonlocal injected
            saved = write(brain, raw)
            if json.loads(raw).get('kind') == 'recipe' and not injected:
                injected = True
                with self.assets.store._Tx(self.assets.store) as connection:
                    connection.execute('INSERT INTO improvement_trial_observations VALUES(?,?,1,?,?,?,?,1,?)',
                        (trial, brain, sequence, 'worker_error', digest, IM._json([digest]), time.time()))
            return saved
        with patch.object(self.assets.blobs, 'write', side_effect=late), self.assertRaises((IM.ConflictError, AssetUnavailable)):
            self.capture_view(archive, generation, 'archive-late-view-trace')
        self.assertTrue(injected)
        self.no_view_publication()
        self.host.revoke(self.owner, 'association-experiment', expected_generation=1, event_key='archive-revoked-current-view-source')
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Revoked current authority cannot decrypt')):
            with self.assertRaises((PermissionError, IM.ConflictError)):
                self.capture_view(archive, generation, 'archive-revoked-current-view')
        self.no_view_publication()

    async def test_last_source_callback_cannot_change_authenticated_view_asset_sql_before_publication(self):
        archive, actual, generation = await self.completed_views()
        with closing(self.assets.store._conn()) as connection:
            asset = dict(connection.execute("SELECT a.* FROM improvement_effective_view_assets a "
                "JOIN improvement_effective_views v ON v.id=a.view_id WHERE v.variant='candidate'").fetchone())
            trigger = connection.execute("SELECT sql FROM sqlite_master WHERE name='improvement_effective_view_assets_update'").fetchone()[0]
        author_guard, observe = archive.authoring._guard, self.host._snapshot_observe
        active, calls, injected = None, 0, False
        def remember(connection, *args):
            nonlocal active
            result = author_guard(connection, *args)
            active = connection
            return result
        def last_callback(*args):
            nonlocal calls, injected
            result = observe(*args)
            if active is not None:
                calls += 1
                if calls == 2:
                    # Negative-only corruption through the final callback's
                    # owned connection; every actual guard is restored before
                    # the archive's SQL-only publication fence runs.
                    active.execute('DROP TRIGGER improvement_effective_view_assets_update')
                    active.execute('UPDATE improvement_effective_view_assets SET authority_hash=? WHERE view_id=?', ('0'*64, asset['view_id']))
                    active.execute(trigger)
                    injected = True
            return result
        with patch.object(archive.authoring, '_guard', side_effect=remember), \
             patch.object(self.host, '_snapshot_observe', side_effect=last_callback), \
             self.assertRaisesRegex(IM.ConflictError, 'recipe_authority_changed'):
            self.capture_view(archive, generation, 'archive-last-callback-view-asset')
        self.assertTrue(injected)
        self.no_view_publication()
        with closing(self.assets.store._conn()) as connection:
            self.assertEqual(connection.execute('SELECT authority_hash FROM improvement_effective_view_assets WHERE view_id=?',
                (asset['view_id'],)).fetchone()[0], asset['authority_hash'])

    async def test_current_ten_archives_all_actual_view_before_after_refs_without_promoting_grade(self):
        archive, actual, generation = await self.completed_views()
        saved = self.capture_view(archive, generation, 'archive-view-current-ten')
        manifest = json.loads(self.assets.blobs.read(self.owner.brain_id, saved['manifest_hash']))
        expected = set(actual) | {ref['trial_id'] for ref in manifest['source_basis']['preparation']['result_refs']}
        self.assertEqual(expected, {ref['trial_id'] for ref in manifest['trial_refs']})
        self.assertEqual(manifest['verdict'], 'confounded')
        self.assertFalse(manifest['confidence_basis']['business_proof'])
        self.assertEqual(manifest['confidence_basis']['transfer'], 'unverified')
        with closing(self.assets.store._conn()) as connection:
            normalized = [dict(row) for row in connection.execute('SELECT * FROM improvement_recipe_trial_refs ORDER BY position')]
            for position, ref in enumerate(manifest['trial_refs']):
                self.assertEqual(normalized[position], {'recipe_id': saved['recipe_id'], 'brain_id': self.owner.brain_id,
                    'position': position, **{key: value for key, value in ref.items() if key != 'request_hash'}})
            self.assertEqual(connection.execute('SELECT count(*) FROM improvement_experiment_trial_links WHERE trial_id IN (?,?)', actual).fetchone()[0], 0)
            recipe = dict(connection.execute('SELECT * FROM improvement_recipes WHERE id=?', (saved['recipe_id'],)).fetchone())
            link = dict(connection.execute("SELECT * FROM improvement_view_trial_links WHERE variant='candidate'").fetchone())
            pin = next(ref for ref in manifest['trial_refs'] if ref['trial_id'] == link['trial_id'])
        # Exercise the new normalized SQL boundary independently of the host
        # reader, against negative-only corruption of an actual owned link.
        for field, value in (('binding_hash', '0'*64), ('view_hash', '0'*64), ('cell_position', 3999), ('request_hash', '0'*64)):
            try:
                self.corrupt_stored('improvement_view_trial_links', field, value, link['trial_id'])
                row = {**recipe, 'id': 'ir_sql_bad_' + field, 'manifest_hash': 'f'*64, 'manifest_blob_hash': 'f'*64}
                with self.subTest(sql_guard=field):
                    self.assert_sql_refusal(row, pin)
            finally:
                self.corrupt_stored('improvement_view_trial_links', field, link[field], link['trial_id'])
        with closing(self.assets.store._conn()) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM improvement_recipes').fetchone()[0], 1)
            trial = dict(connection.execute('SELECT * FROM improvement_trials WHERE id=?', (link['trial_id'],)).fetchone())
        original = json.loads(trial['request_json'])
        # Even a forensic request/link hash pair cannot relabel the actual
        # frozen v4 experiment bundle/contract/case-set pins at this SQL boundary.
        for field in ('base_bundle_hash', 'candidate_bundle_hash', 'contract_hash', 'case_set_hash'):
            changed = copy.deepcopy(original)
            changed['pins'][field] = '0'*64
            digest = IM._hash(changed)
            try:
                self.corrupt_stored('improvement_trials', 'request_json', IM._json(changed), trial['id'], 'id')
                self.corrupt_stored('improvement_trials', 'request_hash', digest, trial['id'], 'id')
                self.corrupt_stored('improvement_view_trial_links', 'request_hash', digest, trial['id'])
                row = {**recipe, 'id': 'ir_sql_bad_' + field, 'manifest_hash': 'f'*64, 'manifest_blob_hash': 'f'*64}
                with self.subTest(sql_request_pin=field):
                    self.assert_sql_refusal(row, pin)
            finally:
                self.corrupt_stored('improvement_trials', 'request_json', trial['request_json'], trial['id'], 'id')
                self.corrupt_stored('improvement_trials', 'request_hash', trial['request_hash'], trial['id'], 'id')
                self.corrupt_stored('improvement_view_trial_links', 'request_hash', link['request_hash'], trial['id'])
        with closing(self.assets.store._conn()) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM improvement_recipes').fetchone()[0], 1)

    async def test_exact_historical_nine_still_refuses_actual_view_refs_atomically(self):
        import improvement_recipe_schema as nine
        archive, actual, generation = await self.completed_views()
        # Historical schema fixture only: owned view/result rows remain exact.
        with self.assets.store._Tx(self.assets.store) as connection:
            connection.execute('DROP TRIGGER improvement_recipe_trial_scope')
            connection.execute(next(sql for sql in nine.statements() if sql.startswith('CREATE TRIGGER improvement_recipe_trial_scope ')))
            connection.execute('UPDATE improvement_schema SET version=9')
            nine.assert_installed(connection)
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'recipe_trial_scope_mismatch'):
            self.capture_view(archive, generation, 'archive-view-historical-nine')
        with closing(self.assets.store._conn()) as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM improvement_recipes').fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT count(*) FROM improvement_events WHERE operation='recipe_capture'").fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
