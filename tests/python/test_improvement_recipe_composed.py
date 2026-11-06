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

import test_improvement_composed_arms as composed


class RecipeComposedTests(unittest.IsolatedAsyncioTestCase):
    new_fixture = composed.ComposedArmTests.new_fixture
    close_services = composed.ComposedArmTests.close_services
    output = composed.ComposedArmTests.output
    adapter = composed.ComposedArmTests.adapter
    service = composed.ComposedArmTests.service
    compose = composed.ComposedArmTests.compose
    rows = composed.ComposedArmTests.rows
    published = composed.ComposedArmTests.published
    generation = composed.ComposedArmTests.generation
    setUp = composed.ComposedArmTests.setUp
    exact_diff = composed.ComposedArmTests.exact_diff
    bind = composed.ComposedArmTests.bind
    frozen = composed.ComposedArmTests.frozen
    semantic = composed.ComposedArmTests.semantic
    semantic_adapter = composed.ComposedArmTests.semantic_adapter

    async def test_typed_three_actual_independent_semantic_view_pair_archives_own_v4_refs(self):
        import improvement_claude as native
        from improvement_native_formats import input_version as actual_input_version
        from improvement_comparison_results import ComparisonResults
        from improvement_comparison_schedule import ComparisonSchedule
        from improvement_recipe_archive import RecipeArchive
        from improvement_trial_runner import TrialRunner
        from improvement_view_admission import ViewExperimentAdmission
        from improvement_view_lineage import load_view_lineage
        from improvement_views import EffectiveViews
        # Existing parent-cell controls and synthetic operation packets remain
        # labelled. New v4 cells use real Trial/Call/Runner/Results/trace owners.
        with patch.object(sources.HostSnapshotTests, 'context_capture', semantic_capture), \
             patch.object(selections.ExperimentSelectionTests, 'seed_technical_complete_cells', traced_selection_cells):
            await self.published()
        bound = self.bind(self.exact_diff())
        frozen = self.frozen(bound)
        semantic = self.semantic()
        reviewed = await semantic.review(self.owner, self.candidate['id'], expected_generation=self.generation(),
            event_key='recipe-typed-three-independent-semantic')
        evidence = semantic.current_evidence(self.owner, self.candidate['id'])
        self.assertEqual(evidence['verdict'], 'unknown')
        views = EffectiveViews(self.plans, semantic)
        metadata = views.freeze_comparison(self.owner, frozen['comparison_id'], expected_generation=self.generation(),
            event_key='recipe-typed-three-independent-views')
        self.trials, self.executed, self.closed, self.workspaces = self.plans.admission.trials, 0, 0, {}
        admission = ViewExperimentAdmission(self.plans, views, ComparisonSchedule(self.plans, self.trials))
        actual = []
        # Operation2 is the existing labelled semantic storage control. Trials
        # retain this synthetic profile's actual legacy view input3; their
        # effective-view request/result lineage is v4, as in ViewExecutionTests.
        with patch('improvement_native_formats.input_version', side_effect=lambda pin, surface:
                   2 if surface == 'operation' else actual_input_version(pin, surface)):
            for position in (0, 1):
                with patch.object(native.ClaudeTrialAdapter, 'verify', return_value={'supported': True, 'capability_hash': 'd' * 64}):
                    admitted = admission.admit_next(self.owner, self.saved['experiment_id'], frozen['comparison_id'],
                        expected_generation=self.generation(), event_key='recipe-typed-three-owned-v4-' + str(position))
                runner = TrialRunner(self.trials, context_loader=self.execution.host.context_loader,
                    live_guard=self.execution.host.live_guard,
                    adapter_factory=lambda *args, **kwargs: view_execution.ViewExecutionTests.view_adapter_factory(self, *args, **kwargs))
                result = await runner.run(self.owner, admitted.trial_id)
                self.assertEqual(result['status'], 'completed', result)
                self.assertEqual(result['result']['version'], 4)
                self.assertNotEqual(result['result']['verdict'], 'pass')
                actual.append(admitted.trial_id)
                with closing(self.store._conn()) as connection:
                    proof = load_view_lineage(connection, self.owner.brain_id, admitted.request, blobs=self.assets.blobs,
                        current=False, require_link=True, trial_id=admitted.trial_id)
                    self.assertEqual(proof['arm']['ordinal'], 3)
                    self.assertEqual(proof['view']['manifest_hash'], admitted.request['view']['view_hash'])
                self.assertEqual(admitted.request['view']['binding_hash'], metadata['binding_hash'])
        comparison = ComparisonResults(self.plans).create(self.owner, frozen['comparison_id'],
            expected_generation=self.generation(), event_key='recipe-typed-three-own-report')
        decision = {'kind': 'procedure', 'cue': 'When checking composed view totals',
            'procedure': 'Check the controlling subtotal.', 'applicability': [], 'exclusions': [], 'expires_at': time.time() + 4000000}
        saved = RecipeArchive(self.plans).capture(self.owner, self.saved['experiment_id'], self.candidate['id'], decision,
            expected_generation=self.generation(), expected_context_generation=1, event_key='recipe-typed-three-view-capture')
        manifest = json.loads(self.assets.blobs.read(self.owner.brain_id, saved['manifest_hash']))
        self.assertEqual(manifest['source_basis']['candidate']['ordinal'], 3)
        self.assertEqual(manifest['comparison']['report_id'], comparison['report_id'])
        self.assertEqual(manifest['verdict'], 'confounded')
        self.assertEqual(manifest['confidence_basis']['transfer'], 'unverified')
        self.assertFalse(manifest['confidence_basis']['business_proof'])
        with closing(self.store._conn()) as connection:
            refs = [dict(row) for row in connection.execute('SELECT * FROM improvement_recipe_trial_refs ORDER BY position')]
            self.assertEqual(len(refs), len(manifest['trial_refs']))
            for position, pin in enumerate(manifest['trial_refs']):
                self.assertEqual(refs[position], {'recipe_id': saved['recipe_id'], 'brain_id': self.owner.brain_id,
                    'position': position, **{key: value for key, value in pin.items() if key != 'request_hash'}})
            self.assertTrue(set(actual) <= {ref['trial_id'] for ref in manifest['trial_refs']})
            self.assertEqual(connection.execute('SELECT count(*) FROM improvement_view_trial_links WHERE comparison_id=?',
                (frozen['comparison_id'],)).fetchone()[0], 2)
            self.assertEqual(connection.execute('SELECT semantic_receipt_id FROM improvement_comparison_views WHERE comparison_id=?',
                (frozen['comparison_id'],)).fetchone()[0], reviewed['receipt_id'])

    async def test_conflicting_required_parent_result_pins_refuse_all_recipe_publication(self):
        # Removing the conflicting-pin check would select one of these two
        # required historical results and incorrectly publish a recipe.
        from improvement_recipe_archive import RecipeArchive
        from improvement_comparison_results import ComparisonResults
        from improvement_trial_results import TrialResults
        with patch.object(sources.HostSnapshotTests, 'context_capture', semantic_capture), \
             patch.object(selections.ExperimentSelectionTests, 'seed_technical_complete_cells', traced_selection_cells):
            await self.published()
        archive = RecipeArchive(self.plans)
        reports = ComparisonResults(self.plans)
        publication = self.rows('improvement_compositions')[-1]
        basis = json.loads(self.assets.blobs.read(self.owner.brain_id, publication['basis_hash']))
        original_ref = basis['report_refs'][0]
        original = reports.read(self.owner, original_ref['id'])
        with closing(self.store._conn()) as connection:
            result = dict(connection.execute('SELECT * FROM improvement_trial_results WHERE id=?',
                (original['result_refs'][0][1],)).fetchone())
        trials = self.plans.admission.trials
        current = trials.get(self.owner, result['trial_id'])
        TrialResults(trials).reevaluate(self.owner, result['trial_id'], result['attempt'],
            expected_generation=current['generation'], event_key='duplicate-pin-owner-recheck', checker_registry={})
        newer = reports.create(self.owner, original['comparison_id'], expected_generation=self.generation(),
            event_key='duplicate-pin-new-parent-report')
        revised = reports.read(self.owner, newer['report_id'])
        old_pin, new_pin = original['result_refs'][0], revised['result_refs'][0]
        self.assertEqual(old_pin[0], new_pin[0])
        self.assertNotEqual(old_pin[1:], new_pin[1:])
        with closing(self.store._conn()) as connection:
            required = [dict(connection.execute('SELECT * FROM improvement_trial_results WHERE id=?',
                (pin[1],)).fetchone()) for pin in (old_pin, new_pin)]
            event = dict(connection.execute("SELECT * FROM improvement_events WHERE operation='comparison_report' "
                "AND event_key='duplicate-pin-new-parent-report'").fetchone())
            consent = dict(connection.execute("SELECT * FROM improvement_events WHERE operation='compose_authorize' "
                "AND json_extract(result_json,'$.authorization_id')=?", (publication['authorization_id'],)).fetchone())
        self.assertEqual([(row['trial_id'], row['attempt']) for row in required],
                         [(result['trial_id'], result['attempt'])] * 2)
        self.assertNotEqual(required[0]['result_hash'], required[1]['result_hash'])
        for row in required:
            report = TrialResults(trials).read(self.owner, row['trial_id'], row['attempt'], result_id=row['id'])
            self.assertEqual(IM._hash(report), row['result_hash'])

        # An ordinary composer cannot request conflicting parent histories.
        # This forensic storage fixture retains both actual immutable reports
        # and their publication events, but corrupts the basis to require both.
        # Rebind its hash links so real proposal authentication succeeds first;
        # no reader, evidence normalizer, source guard or result is replaced.
        basis['report_refs'] = [original_ref, {'id': newer['report_id'], 'report_hash': newer['report_hash'],
                                             'publication_id': event['id']}]
        basis_hash = self.assets.blobs.write(self.owner.brain_id, IM._json(basis).encode('utf-8'))
        decisions = json.loads(self.assets.blobs.read(self.owner.brain_id, publication['decisions_blob_hash']))
        decisions['basis_hash'] = basis_hash
        decisions_hash = self.assets.blobs.write(self.owner.brain_id, IM._json(decisions).encode('utf-8'))
        metadata = json.loads(consent['result_json'])
        metadata['basis_hash'] = basis_hash
        tables = ('improvement_compositions', 'improvement_compose_authorizations', 'improvement_events')
        with self.store._Tx(self.store) as connection:
            triggers = list(connection.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' "
                "AND tbl_name IN (?,?,?)", tables))
            for trigger in triggers:
                connection.execute('DROP TRIGGER ' + trigger['name'])
            connection.execute('UPDATE improvement_compositions SET basis_hash=?,decisions_hash=?,decisions_blob_hash=? WHERE id=?',
                (basis_hash, decisions_hash, decisions_hash, publication['id']))
            connection.execute('UPDATE improvement_compose_authorizations SET basis_hash=? WHERE id=?',
                (basis_hash, publication['authorization_id']))
            connection.execute('UPDATE improvement_events SET result_json=? WHERE id=?', (IM._json(metadata), consent['id']))
            for trigger in triggers:
                connection.execute(trigger['sql'])
        with closing(self.store._conn()) as connection:
            state = self.plans.authoring._state(connection, self.owner, self.candidate['experiment_id'],
                self.candidate['target_id'], self.candidate['base_revision_id'], self.candidate['base_hash'])
            observed, raw = self.plans.authoring.observe(self.owner, state['target'])
            proposal = self.plans.authoring.read_proposal(connection, self.owner, self.candidate, state, observed, raw)
            self.assertEqual(proposal['provenance']['composition_id'], publication['id'])
        decision = {'kind': 'procedure', 'cue': 'When checking composed totals', 'procedure': 'Check the controlling subtotal.',
            'applicability': [], 'exclusions': [], 'expires_at': time.time() + 4000000}
        with self.assertRaisesRegex(IM.ConflictError, '^recipe_conflicting_trial_pins$'):
            archive.capture(self.owner, 'association-experiment', self.candidate['id'], decision,
                expected_generation=self.generation(), expected_context_generation=1, event_key='archive-conflicting-parent-pins')
        for table in ('improvement_recipes', 'improvement_recipe_states', 'improvement_recipe_trial_refs'):
            self.assertEqual(self.rows(table), [], table)
        self.assertFalse([row for row in self.rows('improvement_events') if row['operation'] == 'recipe_capture'])

    async def test_typed_three_keeps_actual_composed_provenance_and_own_tuning_refs(self):
        # The existing publisher uses labelled synthetic adapters/availability;
        # all consent, encrypted inputs, operation/result and candidate owners run.
        with patch.object(sources.HostSnapshotTests, 'context_capture', semantic_capture), \
             patch.object(selections.ExperimentSelectionTests, 'seed_technical_complete_cells', traced_selection_cells):
            await self.published()
        from improvement_recipe_archive import RecipeArchive
        decision = {'kind': 'procedure', 'cue': 'When checking composed totals', 'procedure': 'Check each controlling subtotal.',
            'applicability': [], 'exclusions': [], 'expires_at': time.time() + 4000000}
        saved = RecipeArchive(self.plans).capture(self.owner, 'association-experiment', self.candidate['id'], decision,
            expected_generation=self.generation(), expected_context_generation=1, event_key='archive-actual-typed-three')
        manifest = json.loads(self.assets.blobs.read(self.owner.brain_id, saved['manifest_hash']))
        self.assertEqual(manifest['source_basis']['candidate']['ordinal'], 3)
        self.assertEqual(manifest['provenance_hash'], self.candidate['provenance_hash'])
        self.assertEqual(manifest['verdict'], 'untested')
        self.assertIsNone(manifest['comparison'])
        self.assertTrue(manifest['source_basis']['candidate_evidence_refs'])

    async def test_changed_composed_basis_report_publication_and_late_parent_trace_refuse(self):
        from improvement_recipe_archive import RecipeArchive
        from improvement_trial_evidence import _packet
        with patch.object(sources.HostSnapshotTests, 'context_capture', semantic_capture), \
             patch.object(selections.ExperimentSelectionTests, 'seed_technical_complete_cells', traced_selection_cells):
            await self.published()
        archive = RecipeArchive(self.plans)
        decision = {'kind': 'procedure', 'cue': 'When checking composed totals', 'procedure': 'Check the controlling subtotal.',
            'applicability': [], 'exclusions': [], 'expires_at': time.time() + 4000000}
        def capture():
            return archive.capture(self.owner, 'association-experiment', self.candidate['id'], decision,
                expected_generation=self.generation(), expected_context_generation=1, event_key='archive-damaged-composition')
        publication = self.rows('improvement_compositions')[-1]
        basis = json.loads(self.assets.blobs.read(self.owner.brain_id, publication['basis_hash']))
        parent = basis['report_refs'][0]
        for digest in (publication['basis_hash'], parent['report_hash']):
            path = self.assets.blobs._path(self.owner.brain_id, digest)
            ciphertext = path.read_bytes()
            try:
                path.write_bytes(b'enc:damaged-synthetic-storage')
                with self.assertRaises((AssetUnavailable, ValueError)):
                    capture()
            finally:
                path.write_bytes(ciphertext)
        # Deliberate forensic-corruption fixture only: restore the original SQL
        # trigger before reading, and restore the event afterwards. No production
        # history rewrite is introduced or used to make a positive test pass.
        store = self.assets.store
        with closing(store._conn()) as connection:
            event = dict(connection.execute('SELECT * FROM improvement_events WHERE id=?', (parent['publication_id'],)).fetchone())
            trigger = connection.execute("SELECT sql FROM sqlite_master WHERE name='improvement_events_update'").fetchone()[0]
        damaged = json.loads(event['result_json'])
        damaged['report_hash'] = '0' * 64
        def event_json(raw):
            with store._Tx(store) as connection:
                connection.execute('DROP TRIGGER improvement_events_update')
                connection.execute('UPDATE improvement_events SET result_json=? WHERE id=?', (raw, event['id']))
                connection.execute(trigger)
        try:
            event_json(IM._json(damaged))
            with self.assertRaises((AssetUnavailable, PermissionError, IM.ConflictError)):
                capture()
        finally:
            event_json(event['result_json'])
        report = self.plans.authoring.blobs.read(self.owner.brain_id, parent['report_hash'])
        refs = json.loads(report)['result_refs']
        with closing(store._conn()) as connection:
            child = dict(connection.execute('SELECT * FROM improvement_trial_results WHERE id=?', (refs[-1][1],)).fetchone())
        packet, raw = _packet({'version': 1, 'sequence': 2, 'type': 'worker_error',
            'reason': 'late_parent_storage_observation', 'error_type': 'SyntheticFixture'})
        digest = self.assets.blobs.write(self.owner.brain_id, raw)
        write, injected = self.assets.blobs.write, False
        def late(brain, raw):
            nonlocal injected
            result = write(brain, raw)
            if not injected:
                injected = True
                with store._Tx(store) as connection:
                    connection.execute('INSERT INTO improvement_trial_observations VALUES(?,?,1,2,?,?,?,1,?)',
                        (child['trial_id'], brain, 'worker_error', digest, IM._json([digest]), time.time()))
            return result
        with patch.object(self.assets.blobs, 'write', side_effect=late), self.assertRaises(IM.ConflictError):
            capture()
        self.assertEqual(self.rows('improvement_recipes'), [])
        self.assertFalse([row for row in self.rows('improvement_events') if row['operation'] == 'recipe_capture'])
