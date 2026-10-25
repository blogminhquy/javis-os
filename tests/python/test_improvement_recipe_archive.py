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

_SEED_SELECTION = selections.ExperimentSelectionTests.seed_technical_complete_cells


def semantic_capture(test, principal, surface, targets):
    observed = capture_context([ContextSource('owner', test.brain, 'owner.md')],
                               surface=surface, complete_plan=True)
    item = observed['sources'][0]
    text = test.protected.read_bytes().decode('utf-8')
    return capture_semantics(surface={**surface, 'language': 'en'}, sources=[{
        'kind': 'file', 'ref': item['ref'], 'locator': {'root': item['root'], 'relative': item['relative']},
        'role': 'protected', 'required': True, 'present': True, 'identity': item['identity'],
        'hash': item['hash'], 'projection': text, 'projection_hash': IM._hash(text)}],
        content=text, complete_plan=True)


class RecipeArchiveTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('improvement_recipe_archive'),
                             'Actual encrypted canonical RecipeArchive is absent')
        with patch.object(sources.HostSnapshotTests, 'context_capture', semantic_capture):
            self.f = fixtures.PreparationTests()
            self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.source = self.f.f.f
        self.owner, self.assets, self.store = self.f.owner, self.f.assets, self.f.store
        self.plans, self.host = self.f.plans, self.f.host
        self.host.context_capture = lambda *args: semantic_capture(self.source, *args)
        from improvement_recipe_archive import RecipeArchive
        self.archive = RecipeArchive(self.plans)
        self.candidate = self.stage('one', 'Check every subtotal.')
        self.decision = {'kind': 'procedure', 'cue': 'When checking authorized totals',
            'procedure': 'Count each authorized row once, then check the subtotal.',
            'applicability': ['Tabular totals'], 'exclusions': ['Missing required rows'],
            'expires_at': time.time() + 4000000}

    def stage(self, suffix, instruction, *, evidence_refs=None):
        raw = self.source.skill.read_bytes()
        start = raw.index(b'Retain owner rules.')
        if suffix == 'one':
            self.plans.authoring.declare_region(self.owner, 'association-experiment',
                self.source.target['revision_id'], start, len(raw), expected_target_generation=1,
                event_key='archive-owner-region')
        return self.plans.authoring.stage(self.owner, 'association-experiment', {
            'version': 1, 'target_id': self.source.target['target_id'],
            'base_revision_id': self.source.target['revision_id'], 'before_hash': hashlib.sha256(raw).hexdigest(),
            'operation': 'replace_body_region', 'start': start, 'end': len(raw),
            'replacement': 'Retain owner rules.\n' + instruction + '\n',
            'hypothesis': 'Count authorized rows.', 'failure_signature': 'Omitted row.',
            'expected_behavior': 'Every row counted once.', 'possible_regressions': ['Duplicate row.'],
            'evidence_refs': [] if evidence_refs is None else evidence_refs, 'angle': 'execution'}, event_key='archive-stage-' + suffix)

    def capture(self, *, key='archive-owner-capture', decision=None, **changes):
        return self.archive.capture(self.owner, 'association-experiment',
            changes.pop('candidate_id', self.candidate['candidate_id']), self.decision if decision is None else decision,
            expected_generation=changes.pop('expected_generation', 1), expected_context_generation=1,
            event_key=key, **changes)

    def rows(self, table):
        with closing(self.store._conn()) as connection:
            return [dict(row) for row in connection.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]

    def no_publication(self):
        self.assertEqual(self.rows('improvement_recipes'), [])
        self.assertFalse([row for row in self.rows('improvement_events') if row['operation'] == 'recipe_capture'])

    def manifest(self, saved):
        return json.loads(self.assets.blobs.read(self.owner.brain_id, saved['manifest_hash']))

    def test_actual_encrypted_manifest_uses_original_source_pins_and_unverified_grade(self):
        before = {table: self.rows(table) for table in ('agent_calls', 'improvement_case_exposures', 'improvement_operations')}
        saved = self.capture()
        self.assertEqual(set(saved), {'kind', 'recipe_id', 'manifest_hash', 'experiment_id', 'candidate_id', 'authority_status', 'business_proof'})
        self.assertRegex(saved['recipe_id'], '^ir_[0-9a-f]{24}$')
        manifest = self.manifest(saved)
        self.assertEqual(set(manifest), {'version', 'kind', 'authorship', 'recipe_id', 'brain_id', 'experiment_id',
            'context_id', 'target_id', 'base_revision_id', 'candidate_id', 'cue', 'procedure', 'applicability', 'exclusions',
            'before_hash', 'after_hash', 'patch_hash', 'provenance_hash', 'source_basis', 'source_basis_hash', 'scope_hash',
            'engine_config', 'engine_config_hash', 'owner_rule_hash', 'target_protected_hash', 'source_authority_hash',
            'language', 'trial_refs', 'comparison', 'verdict', 'confidence_basis', 'checked_at', 'expires_at', 'actor', 'created_at'})
        self.assertEqual(set(manifest['source_basis']), {'version', 'candidate', 'context', 'preparation', 'candidate_evidence_refs', 'comparison_ref'})
        self.assertEqual(set(manifest['source_basis']['candidate']), {'id', 'context_id', 'experiment_id', 'target_id',
            'base_revision_id', 'base_hash', 'content_hash', 'patch_hash', 'provenance_hash', 'ordinal', 'source_authority_hash'})
        self.assertEqual(set(manifest['source_basis']['context']), {'context_id', 'binding_hash', 'scope_hash', 'grant_hash',
            'context_generation', 'policy_version', 'engine_config_hash'})
        self.assertEqual(manifest['verdict'], 'untested')
        self.assertEqual(manifest['confidence_basis'], {'attribution': 'not_isolated', 'candidate_outcome': 'unobserved',
            'evidence_class': 'technical', 'business_proof': False, 'transfer': 'unverified'})
        self.assertEqual(manifest['authorship'], 'owner_unverified_procedure')
        self.assertEqual(manifest['source_basis_hash'], IM._hash(manifest['source_basis']))
        self.assertEqual(manifest['trial_refs'], [])
        self.assertIsNone(manifest['source_basis']['preparation'])
        self.assertIsNone(manifest['comparison'])
        self.assertLessEqual(manifest['expires_at'], manifest['checked_at'] + 2592000)
        self.assertEqual(manifest['target_protected_hash'], self.rows('improvement_targets')[0]['protected_hash'])
        self.assertNotEqual(manifest['owner_rule_hash'], manifest['target_protected_hash'])
        ciphertext = self.assets.blobs._path(self.owner.brain_id, saved['manifest_hash']).read_bytes()
        self.assertTrue(ciphertext.startswith(b'enc:'))
        self.assertNotIn(self.decision['procedure'].encode(), ciphertext)
        self.assertEqual({table: self.rows(table) for table in before}, before)
        self.assertEqual(self.rows('improvement_recipe_states')[0]['generation'], 1)

    def test_second_original_candidate_preserves_own_provenance(self):
        candidate = self.stage('two', 'Check each selected total twice.')
        saved = self.capture(candidate_id=candidate['candidate_id'])
        self.assertEqual(self.manifest(saved)['source_basis']['candidate']['ordinal'], 2)

    def test_no_entry_records_only_actual_basis_and_replays_cold(self):
        saved = self.capture(decision={'kind': 'NO_ENTRY'})
        self.assertEqual(set(saved), {'kind', 'experiment_id', 'candidate_id', 'source_basis_hash', 'authority_status', 'business_proof'})
        self.assertEqual(self.rows('improvement_recipes'), [])
        self.host.revoke(self.owner, 'association-experiment', expected_generation=1, event_key='archive-revoke-source')
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Replay cannot decrypt')), \
             patch.object(self.host, '_snapshot_observe', side_effect=AssertionError('Replay cannot refresh')):
            self.assertEqual(self.capture(decision={'kind': 'NO_ENTRY'}), saved)

    def test_changed_payload_conflicts_and_recorded_replay_is_cold_after_off(self):
        saved = self.capture()
        self.source.protected.unlink()
        self.assets.set_policy(self.owner, 'off', expected_version=0, event_key='archive-mode-off')
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Replay cannot decrypt')):
            self.assertEqual(self.capture(), saved)
            with self.assertRaisesRegex(IM.ConflictError, 'event_payload_conflict'):
                self.capture(decision={**self.decision, 'cue': 'Changed cue'})

    def test_closed_raw_text_and_expiry_validation_precedes_writes(self):
        for change in ({'procedure': ' '}, {'cue': '\0bad'}, {'procedure': '\ud800'}, {'expires_at': True},
                       {'expires_at': float('inf')}, {'verdict': 'helped'}, {'source_refs': []},
                       {'procedure': 'Bearer abcdefghijklmnop1234567890'},
                       {'applicability': ['x', 'x']}, {'exclusions': ['']}, {'cue': 'x' * 1001},
                       {'procedure': 'x' * 16385}):
            with self.subTest(change=repr(change)), self.assertRaises(ValueError):
                self.capture(decision={**self.decision, **change})
        self.no_publication()

    def test_source_drift_during_last_blob_write_refuses_all_rows_and_event(self):
        write = self.assets.blobs.write
        def drift(brain, raw):
            digest = write(brain, raw)
            self.source.protected.write_bytes(b'Changed protected owner rule.\n')
            return digest
        with patch.object(self.assets.blobs, 'write', side_effect=drift), self.assertRaises(IM.ConflictError):
            self.capture()
        self.no_publication()

    def test_no_entry_final_observation_cannot_publish_stale_decision(self):
        observe = self.host._snapshot_observe
        def drift(*args):
            observe(*args)
            self.source.protected.write_bytes(b'Changed final source.\n')
        with patch.object(self.host, '_snapshot_observe', side_effect=drift), self.assertRaises(IM.ConflictError):
            self.capture(decision={'kind': 'NO_ENTRY'})
        self.no_publication()

    def test_old_source_expiry_cannot_restart_at_copy_time(self):
        created = self.rows('improvement_trial_contexts')[-1]['created_at']
        with patch('improvement_recipe_archive.time.time', return_value=created + 2592001), self.assertRaises(PermissionError):
            self.capture()
        self.no_publication()

    def test_engine_drift_revocation_foreign_and_unsupported_provider_refuse(self):
        from improvement_trial_file_sources import BrainFileFixtures
        with patch.object(self.host, 'fixture_observer', wraps=self.host.fixture_observer), self.assertRaises(PermissionError):
            self.capture()
        self.assertIs(type(self.host.fixture_observer), BrainFileFixtures)
        self.source.engine['reasoning'] = 'high'
        with self.assertRaises(IM.ConflictError): self.capture()
        self.source.engine['reasoning'] = 'medium'
        with self.assertRaises(PermissionError):
            self.archive.capture(self.source.other, 'association-experiment', self.candidate['candidate_id'], self.decision,
                expected_generation=1, expected_context_generation=1, event_key='foreign-archive-capture')
        self.host.revoke(self.owner, 'association-experiment', expected_generation=1, event_key='archive-source-revoked')
        with self.assertRaises(PermissionError): self.capture()
        self.no_publication()

    def test_generation_and_context_generation_cannot_be_caller_authority(self):
        with self.assertRaises(IM.ConflictError): self.capture(expected_generation=2)
        with self.assertRaises((IM.ConflictError, TypeError)):
            self.archive.capture(self.owner, 'association-experiment', self.candidate['candidate_id'], self.decision,
                expected_generation=1, expected_context_generation=2, event_key='archive-wrong-context')
        self.no_publication()

    def test_concurrent_same_event_has_one_immutable_record(self):
        barrier = threading.Barrier(2)
        def capture(_):
            barrier.wait(timeout=10)
            return self.capture()
        with ThreadPoolExecutor(max_workers=2) as pool:
            values = list(pool.map(capture, range(2)))
        self.assertEqual(values[0], values[1])
        self.assertEqual(len(self.rows('improvement_recipes')), 1)

    def test_unknown_capture_cannot_guess_empty_owner_rules(self):
        # Create another real source context with the original v1 collector.
        self.f.doCleanups()
        self.f = fixtures.PreparationTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.source = self.f.f.f
        self.owner, self.assets, self.store = self.f.owner, self.f.assets, self.f.store
        self.plans, self.host = self.f.plans, self.f.host
        from improvement_recipe_archive import RecipeArchive
        self.archive = RecipeArchive(self.plans)
        self.candidate = self.stage('one', 'Check every subtotal.')
        with self.assertRaisesRegex(PermissionError, 'semantic_capture'):
            self.capture()
        self.no_publication()

    def test_policy_off_during_slow_write_and_bad_readback_cannot_publish(self):
        write = self.assets.blobs.write
        def off(brain, raw):
            digest = write(brain, raw)
            self.assets.set_policy(self.owner, 'off', expected_version=0, event_key='archive-off-during-write')
            return digest
        with patch.object(self.assets.blobs, 'write', side_effect=off), self.assertRaises(PermissionError):
            self.capture()
        self.no_publication()

    def test_late_holdout_alias_cannot_relabel_tuning_source(self):
        write = self.assets.blobs.write
        def alias(brain, raw):
            digest = write(brain, raw)
            with self.store._Tx(self.store) as connection:
                token = connection.execute("SELECT fingerprint FROM improvement_case_families WHERE case_id='case-0' LIMIT 1").fetchone()[0]
                connection.execute('INSERT INTO improvement_case_families VALUES(?,?,?,?,?)',
                    (self.f.association['case_set_id'], 'case-1', brain, token, 'qualification'))
            return digest
        with patch.object(self.assets.blobs, 'write', side_effect=alias), self.assertRaisesRegex(PermissionError, 'holdout_alias'):
            self.capture()
        self.no_publication()

    def test_manifest_readback_and_upstream_marker_are_checked_before_publication(self):
        from improvement_harness2_context import GRADER_VERDICT_MARKERS
        with self.assertRaises(ValueError):
            self.capture(decision={**self.decision, 'procedure': GRADER_VERDICT_MARKERS[0]})
        read, write = self.assets.blobs.read, self.assets.blobs.write
        manifest_digest = None
        def written(brain, raw):
            nonlocal manifest_digest
            manifest_digest = write(brain, raw)
            return manifest_digest
        def changed(brain, digest):
            value = read(brain, digest)
            return value + b' ' if digest == manifest_digest else value
        with patch.object(self.assets.blobs, 'write', side_effect=written), \
             patch.object(self.assets.blobs, 'read', side_effect=changed), self.assertRaises(AssetUnavailable):
            self.capture()
        self.no_publication()


class RecipePreparationTests(unittest.IsolatedAsyncioTestCase):
    factory = prepared_inputs.ImproverInputTests.factory
    prepare = prepared_inputs.ImproverInputTests.prepare
    stage = RecipeArchiveTests.stage
    rows = RecipeArchiveTests.rows
    no_publication = RecipeArchiveTests.no_publication
    manifest = RecipeArchiveTests.manifest

    @classmethod
    def setUpClass(cls):
        import _improvement_history
        module = _improvement_history.load('dbdec4eb', 'improvement_improver_inputs', '_archive_original_improver_inputs')
        cls.original_inputs = module.ImproverInputs

    def setUp(self):
        # Borrow methods onto this running async case. A second manually set-up
        # IsolatedAsyncioTestCase has no runner and cannot execute doCleanups.
        self.addCleanup(self.source_cleanup_complete)
        with patch.object(sources.HostSnapshotTests, 'context_capture', semantic_capture):
            prepared_inputs.ImproverInputTests.setUp(self)
        self.source = self.f.f.f
        self.store, self.plans = self.assets.store, self.f.plans
        self.host.context_capture = lambda *args: semantic_capture(self.source, *args)
        from improvement_recipe_archive import RecipeArchive
        self.archive = RecipeArchive(self.plans)
        self.decision = {'kind': 'procedure', 'cue': 'When checking authorized totals', 'procedure': 'Check each subtotal.',
            'applicability': [], 'exclusions': [], 'expires_at': time.time() + 4000000}

    def source_cleanup_complete(self):
        self.assertFalse(self.source.directory._finalizer.alive, 'Borrowed source directory was not explicitly closed')
        self.assertFalse(self.source.root.exists(), 'Borrowed source scratch root remains after cleanup')

    async def prepared(self):
        await self.prepare()
        self.candidate = self.stage('one', 'Check each authorized subtotal.')

    def capture(self, *, decision=None):
        return self.archive.capture(self.owner, 'association-experiment', self.candidate['candidate_id'],
            self.decision if decision is None else decision, expected_generation=3, expected_context_generation=1,
            event_key='archive-sealed-preparation')

    async def test_exact_real_sealed_results_and_decoded_trace_are_normalized_without_private_text(self):
        await self.prepared()
        saved = self.capture()
        manifest = self.manifest(saved)
        self.assertEqual(manifest['source_basis']['preparation'], self.sealed)
        self.assertEqual(len(manifest['trial_refs']), 1)
        actual = manifest['trial_refs'][0]
        sealed = self.sealed['result_refs'][0]
        self.assertEqual({key: actual[key] for key in ('trial_id', 'attempt', 'result_id', 'result_hash', 'request_hash')},
                         {key: sealed[key] for key in ('trial_id', 'attempt', 'result_id', 'result_hash', 'request_hash')})
        normalized = self.rows('improvement_recipe_trial_refs')[0]
        self.assertEqual(normalized['trace_hash'], actual['trace_hash'])
        self.assertEqual(normalized['trace_count'], actual['trace_count'])
        self.assertEqual(normalized['position'], 0)
        self.assertNotIn('synthetic preparation baseline', IM._json(manifest))
        self.assertNotIn('private-owner-answer', IM._json(manifest))
        self.assertEqual(manifest['verdict'], 'untested')

    async def test_preparation_exists_but_unsealed_is_not_absent(self):
        self.candidate = self.stage('one', 'Check every subtotal.')
        with self.assertRaises(IM.ConflictError):
            self.archive.capture(self.owner, 'association-experiment', self.candidate['candidate_id'], self.decision,
                expected_generation=2, expected_context_generation=1, event_key='archive-unsealed-preparation')
        self.no_publication()

    async def test_original_candidate_evidence_deduplicates_only_exact_sealed_pins(self):
        await self.prepared()
        self.candidate = self.stage('two', 'Check the original sealed subtotal.', evidence_refs=[
            {'kind': 'tuning_trial', 'id': self.sealed['result_refs'][0]['trial_id']}])
        manifest = self.manifest(self.capture())
        self.assertEqual(len(manifest['trial_refs']), 1)
        self.assertEqual(manifest['source_basis']['candidate_evidence_refs'], [
            {'kind': 'tuning_trial', 'id': self.sealed['result_refs'][0]['trial_id']}])

    async def test_shared_history_keeps_original_sealed_proposer_bytes_and_recipes_empty(self):
        await self.prepared()
        original = self.original_inputs(self.plans).build(self.owner, 'association-experiment', expected_generation=3)
        current = self.archive.inputs.build(self.owner, 'association-experiment', expected_generation=3)
        self.assertEqual(current, original)
        self.assertEqual(current['data']['recipes'], [])
        self.assertEqual(self.assets.blobs.read(self.owner.brain_id, current['input_blob_hash']),
                         IM._json(original['data']).encode('utf-8'))

    async def test_changed_original_result_pointer_during_blob_write_refuses(self):
        await self.prepared()
        write = self.assets.blobs.write
        changed = False
        def reevaluate(brain, raw):
            nonlocal changed
            digest = write(brain, raw)
            if not changed:
                changed = True
                current = self.trials.get(self.owner, self.admitted.trial_id)
                self.trials.reevaluate(self.owner, self.admitted.trial_id, 1,
                    expected_generation=current['generation'], event_key='archive-reevaluation-during-write', checker_registry={})
            return digest
        with patch.object(self.assets.blobs, 'write', side_effect=reevaluate), self.assertRaises(IM.ConflictError):
            self.capture()
        self.no_publication()

    async def test_late_trace_during_blob_write_and_no_entry_final_guard_refuse(self):
        await self.prepared()
        write = self.assets.blobs.write
        appended = False
        def late(brain, raw):
            nonlocal appended
            digest = write(brain, raw)
            if not appended:
                appended = True
                self.trials.append_observation(self.owner, self.admitted.trial_id,
                    {'version': 1, 'sequence': 999, 'type': 'worker_error', 'reason': 'late_exit', 'error_type': 'RuntimeError'},
                    lease_token=self.original_writer, attempt=1, late=True)
            return digest
        with patch.object(self.assets.blobs, 'write', side_effect=late), self.assertRaises(IM.ConflictError):
            self.capture()
        self.no_publication()


def traced_selection_cells(fixture, **kwargs):
    """Extend labelled synthetic storage reports with actual encrypted packets."""
    from improvement_trial_evidence import _packet
    _SEED_SELECTION(fixture, **kwargs)
    with closing(fixture.store._conn()) as connection:
        seeded = [dict(row) for row in connection.execute('SELECT r.* FROM improvement_trial_results r '
            'JOIN improvement_experiment_trial_links l ON l.trial_id=r.trial_id AND l.brain_id=r.brain_id '
            'WHERE l.comparison_id=? AND r.brain_id=?', (fixture.h.comparison['id'], fixture.owner.brain_id))]
    pending = []
    for result in seeded:
        value = json.loads(fixture.assets.blobs.read(fixture.owner.brain_id, result['blob_hash']))
        packet, encoded = _packet({'version': 1, 'sequence': 1, 'type': 'worker_error',
            'reason': 'synthetic_storage_observation', 'error_type': 'SyntheticFixture'})
        digest = fixture.assets.blobs.write(fixture.owner.brain_id, encoded)
        value['trace'] = {'count': 1, 'last_sequence': 1, 'hash': IM._hash([[1, digest]])}
        blob = fixture.assets.blobs.write(fixture.owner.brain_id, IM._json(value).encode())
        pending.append((result, digest, blob))
    with fixture.store._Tx(fixture.store) as connection:
        for result, digest, blob in pending:
            trial, result_id = result['trial_id'], result['id'] + '_traced'
            stamp = time.time()
            connection.execute('INSERT INTO improvement_trial_observations VALUES(?,?,1,1,?,?,?,0,?)',
                (trial, fixture.owner.brain_id, 'worker_error', digest, IM._json([digest]), stamp))
            connection.execute('INSERT INTO improvement_trial_results VALUES(?,?,?,?,?,?,?)',
                (result_id, trial, fixture.owner.brain_id, 1, blob, blob, stamp))
            connection.execute('UPDATE improvement_trial_attempts SET result_json=? WHERE trial_id=? AND brain_id=? AND attempt=1',
                (IM._json({'result_id': result_id, 'result_hash': blob, 'blob_hash': blob}), trial, fixture.owner.brain_id))


class RecipeComparisonTests(unittest.TestCase):
    rows = RecipeArchiveTests.rows
    no_publication = RecipeArchiveTests.no_publication
    manifest = RecipeArchiveTests.manifest

    def setUp(self):
        import test_improvement_experiment_selection as selections
        class TracedSelection(selections.ExperimentSelectionTests):
            seed_technical_complete_cells = traced_selection_cells
        with patch.object(sources.HostSnapshotTests, 'context_capture', semantic_capture):
            self.fixture = TracedSelection()
            self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.owner, self.assets, self.store = self.fixture.owner, self.fixture.assets, self.fixture.store
        self.plans = self.fixture.h.h.plans()
        self.host = self.plans.host
        self.source = self.fixture.h.h.f
        self.host.context_capture = lambda *args: semantic_capture(self.source, *args)
        from improvement_recipe_archive import RecipeArchive
        self.archive = RecipeArchive(self.plans)
        self.candidate = self.fixture.h.h.h.candidate
        self.decision = {'kind': 'procedure', 'cue': 'When checking totals', 'procedure': 'Check all authorized subtotals.',
            'applicability': [], 'exclusions': [], 'expires_at': time.time() + 4000000}
        self.generation = self.fixture.saved['generation']

    def capture(self):
        return self.archive.capture(self.owner, 'association-experiment', self.candidate['candidate_id'], self.decision,
            expected_generation=self.generation, expected_context_generation=1, event_key='archive-observed-procedure')

    def test_selection_win_never_certifies_transferable_procedure_as_helped(self):
        selected = self.fixture.select()
        self.generation = selected['generation']
        saved = self.capture()
        manifest = self.manifest(saved)
        self.assertEqual(manifest['verdict'], 'confounded')
        self.assertTrue(manifest['comparison']['summary']['selection_supported'])
        self.assertEqual(manifest['confidence_basis']['candidate_outcome'], 'eligible')
        self.assertFalse(manifest['confidence_basis']['business_proof'])
        self.assertEqual(len(manifest['trial_refs']), 2)
        self.assertEqual(len(self.rows('improvement_recipe_trial_refs')), 2)

    def test_latest_incomplete_publication_cannot_fall_back_to_old_favorable_report(self):
        newer = self.fixture.incomplete_then_restore()
        self.generation = newer['generation']
        with self.assertRaises((PermissionError, IM.ConflictError, AssetUnavailable)):
            self.capture()
        self.no_publication()


    def test_new_report_during_slow_manifest_write_is_fenced(self):
        write = self.assets.blobs.write
        changed = False
        def republish(brain, raw):
            nonlocal changed
            digest = write(brain, raw)
            if not changed:
                changed = True
                self.fixture.reports.create(self.owner, self.fixture.h.comparison['id'],
                    expected_generation=self.generation, event_key='archive-later-report')
            return digest
        with patch.object(self.assets.blobs, 'write', side_effect=republish), self.assertRaises(IM.ConflictError):
            self.capture()
        self.no_publication()


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
