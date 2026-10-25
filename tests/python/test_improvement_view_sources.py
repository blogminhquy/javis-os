"""Actual source/semantic authority and atomic isolated-view publication."""
from _paths import ROOT, SERVER  # noqa: F401

import importlib
import importlib.util
import copy
import asyncio
import json
import sqlite3
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from unittest.mock import patch

import improvement_store as IM
from improvement_experiment_protocol import comparison_hash
import test_improvement_view_schema as fixtures


class SourceFixture:
    setUp = fixtures.ViewScopeTests.setUp
    factory = fixtures.ViewScopeTests.factory
    prepare = fixtures.ViewScopeTests.prepare
    adapter = fixtures.ViewScopeTests.adapter
    body_patch = fixtures.ViewScopeTests.body_patch
    service = fixtures.ViewScopeTests.service
    review = fixtures.ViewScopeTests.review
    asyncSetUp = fixtures.ViewScopeTests.asyncSetUp

    def views_service(self):
        self.assertIsNotNone(importlib.util.find_spec('improvement_views'), 'Concrete current-source view publisher is absent')
        module = importlib.import_module('improvement_views')
        return module.EffectiveViews(self.f.plans, self.semantic_subject)

    def generation(self):
        with closing(self.assets.store._conn()) as connection:
            return connection.execute('SELECT generation FROM improvement_experiments WHERE id=? AND brain_id=?',
                (self.comparison['experiment_id'], self.owner.brain_id)).fetchone()[0]

    def freeze(self, subject, *, generation=None, key='owner-freeze-actual-views'):
        return subject.freeze_comparison(self.owner, self.comparison['id'],
            expected_generation=self.generation() if generation is None else generation, event_key=key)

    def counts(self):
        with closing(self.assets.store._conn()) as connection:
            return tuple(connection.execute('SELECT count(*) FROM ' + table).fetchone()[0] for table in
                ('improvement_effective_views', 'improvement_effective_view_assets', 'improvement_comparison_views', 'agent_calls'))


class EffectiveViewSourceTests(SourceFixture, unittest.IsolatedAsyncioTestCase):
    async def test_host_freezes_real_pair_and_resolves_exact_authorized_bytes(self):
        subject = self.views_service()
        before, counts, generation = self.f.f.f.skill.read_bytes(), self.counts(), self.generation()
        result = self.freeze(subject)
        self.assertEqual(self.counts(), (2, 2, 1, counts[-1]))
        self.assertEqual(result['generation'], generation + 1)
        self.assertEqual(self.generation(), generation + 1)
        baseline = subject.load_current(self.owner, self.comparison['id'], 'baseline')
        candidate = subject.load_current(self.owner, self.comparison['id'], 'candidate')
        self.assertEqual(baseline.content, before)
        self.assertEqual(candidate.content, self.assets.blobs.read(self.owner.brain_id, self.proposal['content_hash']))
        self.assertNotEqual(baseline.content, candidate.content)
        self.assertEqual(baseline.manifest['target'], candidate.manifest['target'])
        self.assertEqual(baseline.manifest['comparison_hash'], comparison_hash(self.comparison))
        self.assertEqual(baseline.manifest['semantic'], candidate.manifest['semantic'])
        self.assertEqual(self.f.f.f.skill.read_bytes(), before)
        self.assertEqual(self.semantic_subject.current_evidence(self.owner, self.proposal['id'])['verdict'], 'unknown')
        self.assertEqual(self.f.plans.authoring.records.get(self.owner, self.proposal['id'])['semantic_status'], 'unreviewed')

    async def test_source_change_during_encrypted_write_cannot_publish_any_pair_or_event(self):
        subject, counts, generation = self.views_service(), self.counts(), self.generation()
        write, changed = self.assets.blobs.write, False

        def drift(brain, raw):
            nonlocal changed
            result = write(brain, raw)
            value = json.loads(raw)
            if value.get('evidence_class') == 'technical' and value.get('variant') == 'baseline' and not changed:
                changed = True
                self.f.f.f.skill.write_bytes(self.f.f.f.skill.read_bytes() + b'\nUnreviewed source change.\n')
            return result

        with patch.object(self.assets.blobs, 'write', side_effect=drift), self.assertRaises((IM.ConflictError, PermissionError)):
            self.freeze(subject, generation=generation)
        self.assertTrue(changed)
        self.assertEqual(self.counts(), counts)
        self.assertEqual(self.generation(), generation)
        self.assertIsNone(subject.read_existing(self.owner, self.comparison['id']))

    async def test_second_insert_failure_rolls_back_views_assets_binding_event_and_generation(self):
        subject, counts, generation = self.views_service(), self.counts(), self.generation()
        insert = subject._insert_view

        def fail_second(connection, row, asset):
            if row['variant'] == 'candidate':
                raise sqlite3.OperationalError('actual second view publication failed')
            return insert(connection, row, asset)

        with patch.object(subject, '_insert_view', side_effect=fail_second), self.assertRaises(sqlite3.OperationalError):
            self.freeze(subject, generation=generation)
        self.assertEqual(self.counts(), counts)
        self.assertEqual(self.generation(), generation)
        with closing(self.assets.store._conn()) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM improvement_events WHERE operation='comparison_views_freeze'").fetchone()[0], 0)
        self.freeze(subject, generation=generation)
        self.assertEqual(self.counts()[:3], (2, 2, 1))

    async def test_exact_event_replay_and_cold_metadata_survive_off_and_revocation_without_decryption(self):
        subject, generation = self.views_service(), self.generation()
        result = self.freeze(subject, generation=generation)
        metadata = subject.read_existing(self.owner, self.comparison['id'])
        self.assets.set_policy(self.owner, 'off', expected_version=0, event_key='views-policy-off-after-publication')
        self.host.revoke(self.owner, 'association-experiment', expected_generation=1, event_key='views-revoke-after-publication')
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Cold replay cannot decrypt')), \
                patch.object(self.host, '_snapshot_observe', side_effect=AssertionError('Cold replay cannot observe')):
            self.assertEqual(self.freeze(subject, generation=generation), result)
            self.assertEqual(subject.read_existing(self.owner, self.comparison['id']), metadata)
            with self.assertRaises(IM.ConflictError):
                self.freeze(subject, generation=generation + 1)
            with self.assertRaises((IM.ConflictError, PermissionError)):
                subject.load_current(self.owner, self.comparison['id'], 'candidate')

    async def test_changed_encrypted_manifest_is_never_resolved_under_its_old_hash(self):
        subject = self.views_service()
        self.freeze(subject)
        metadata = subject.read_existing(self.owner, self.comparison['id'])
        digest = metadata['views']['candidate']['manifest_hash']
        read = self.assets.blobs.read

        def corrupt(brain, reference):
            raw = read(brain, reference)
            if reference == digest:
                value = json.loads(raw)
                value['assets'][0]['content_hash'] = '0' * 64
                return IM._json(value).encode()
            return raw

        with patch.object(self.assets.blobs, 'read', side_effect=corrupt), self.assertRaises((IM.ConflictError, ValueError)):
            subject.load_current(self.owner, self.comparison['id'], 'candidate')

    async def test_same_bytes_replaced_source_cannot_reuse_frozen_incarnation(self):
        subject = self.views_service()
        self.freeze(subject)
        path = self.f.f.f.skill
        replacement = path.with_name('replacement.md')
        replacement.write_bytes(path.read_bytes())
        replacement.replace(path)
        with self.assertRaises((IM.ConflictError, PermissionError)):
            subject.load_current(self.owner, self.comparison['id'], 'candidate')

    async def test_concurrent_same_event_replays_when_other_writer_publishes_during_source_capture(self):
        subject, generation, counts = self.views_service(), self.generation(), self.counts()
        module = importlib.import_module('improvement_views')
        capture, local = module.capture_sources, threading.local()
        second_entered, first_done = threading.Event(), threading.Event()

        def delayed(*args, **kwargs):
            if not getattr(local, 'entered', False):
                local.entered = True
                if local.role == 'first':
                    if not second_entered.wait(10):
                        raise TimeoutError('Second caller never reached actual source capture')
                else:
                    second_entered.set()
                    if not first_done.wait(10):
                        raise TimeoutError('First actual publication never settled')
            return capture(*args, **kwargs)

        def run(role):
            local.role = role
            try:
                return self.freeze(subject, generation=generation)
            finally:
                if role == 'first':
                    first_done.set()

        def both():
            with ThreadPoolExecutor(max_workers=2) as pool:
                return list(pool.map(run, ('first', 'second')))

        with patch.object(module, 'capture_sources', side_effect=delayed):
            results = await asyncio.to_thread(both)
        self.assertEqual(results[0], results[1])
        self.assertEqual(self.counts(), (2, 2, 1, counts[-1]))
        self.assertEqual(self.generation(), generation + 1)

    async def test_source_view_freeze_and_load_never_decrypt_holdout_inputs_or_any_expected_answers(self):
        subject = self.views_service()
        with closing(self.assets.store._conn()) as connection:
            forbidden = {row[0] for row in connection.execute('SELECT DISTINCT s.source_hash FROM improvement_snapshots s '
                'JOIN improvement_case_sources r ON r.snapshot_id=s.id AND r.brain_id=s.brain_id '
                'JOIN improvement_cases c ON c.id=r.case_id AND c.case_set_id=r.case_set_id AND c.brain_id=r.brain_id '
                "WHERE c.split IN ('qualification','regression')")}
            forbidden.update(json.loads(row[0])['answer_hash'] for row in connection.execute('SELECT case_json FROM improvement_cases'))
        self.assertTrue(forbidden)
        read = self.assets.blobs.read

        def guarded(brain, digest):
            self.assertNotIn(digest, forbidden, 'Source views must not decrypt sealed input or expected answers')
            return read(brain, digest)

        with patch.object(self.assets.blobs, 'read', side_effect=guarded):
            self.freeze(subject)
            subject.load_current(self.owner, self.comparison['id'], 'candidate')

    async def test_source_change_after_both_view_inserts_rolls_back_the_whole_publication(self):
        subject, counts, generation = self.views_service(), self.counts(), self.generation()
        insert = subject._insert_view

        def mutate_after_insert(connection, row, asset):
            insert(connection, row, asset)
            if row['variant'] == 'candidate':
                self.f.f.f.protected.write_bytes(b'Owner source changed after both actual view inserts.\n')

        with patch.object(subject, '_insert_view', side_effect=mutate_after_insert), self.assertRaises((IM.ConflictError, PermissionError)):
            self.freeze(subject, generation=generation)
        self.assertEqual(self.counts(), counts)
        self.assertEqual(self.generation(), generation)
        self.assertIsNone(subject.read_existing(self.owner, self.comparison['id']))

    async def test_scoped_encrypted_sql_metadata_without_actual_publication_event_is_not_resolvable(self):
        subject = self.views_service()
        capture = importlib.import_module('improvement_view_sources').capture_sources
        snapshot = capture(self.f.plans, self.semantic_subject, self.owner, self.comparison['id'], self.generation())
        views = {variant: {'view_id': row['id'], 'manifest_hash': row['manifest_hash']} for variant, row in self.views.items()}
        proof = subject._proof(snapshot, {'views': views})
        digest = self.assets.blobs.write(self.owner.brain_id, IM._json(proof).encode())
        binding = {**self.binding, 'binding_hash': digest, 'binding_blob_hash': digest}
        with self.assets.store._Tx(self.assets.store) as connection:
            for variant in ('baseline', 'candidate'):
                fixtures.ViewScopeTests.insert(connection, 'improvement_effective_views', self.views[variant])
                fixtures.ViewScopeTests.insert(connection, 'improvement_effective_view_assets', self.view_assets[variant])
            fixtures.ViewScopeTests.insert(connection, 'improvement_comparison_views', binding)
        # Deliberately incomplete negative history, not a fake Trial or ready bit:
        # every SQL/blob/source field is valid but no atomic publisher/event ran.
        with self.assertRaisesRegex(PermissionError, 'publication_unavailable'):
            subject.load_current(self.owner, self.comparison['id'], 'candidate')

    async def test_older_matrix_only_comparison_pin_stays_cold_and_cannot_be_promoted(self):
        subject, generation = self.views_service(), self.generation()
        module = importlib.import_module('improvement_view_sources')
        with patch.object(module, 'comparison_hash', side_effect=lambda row: row['matrix_hash']):
            result = self.freeze(subject, generation=generation)
        metadata = subject.read_existing(self.owner, self.comparison['id'])
        self.assertEqual(self.freeze(subject, generation=generation), result)
        with self.assertRaises(IM.ConflictError):
            subject.load_current(self.owner, self.comparison['id'], 'candidate')
        self.assertEqual(subject.read_existing(self.owner, self.comparison['id']), metadata)


class ProbeObservationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('improvement_view_sources'))
        self.gate = importlib.import_module('improvement_view_sources')._probe_observations
        self.evidence = {'assessment': {'verdict': 'pass', 'findings': []}, 'owner_assessment': None,
            'dependencies': {'verdict': 'pass'}, 'native_verdict': 'unknown', 'verdict': 'unknown',
            'native_checks': [{'id': key, 'verdict': 'pass', 'reason': 'record_pins_match'} for key in
                ('materialization', 'worker_protocol', 'installation', 'tool_inventory', 'side_effects',
                 'completion', 'actual_model', 'actual_reasoning', 'native_session', 'actual_input_use')]}
        for row in self.evidence['native_checks']:
            if row['id'] in ('actual_reasoning', 'actual_input_use'):
                row.update(verdict='unknown', reason={'actual_reasoning': 'native_reasoning_unobserved',
                    'actual_input_use': 'semantic_input_use_unobserved'}[row['id']])

    def test_two_observation_unknowns_remain_unknown_without_mutating_c_evidence(self):
        before = copy.deepcopy(self.evidence)
        self.assertEqual(self.gate(self.evidence), ('actual_input_use', 'actual_reasoning'))
        self.assertEqual(self.evidence, before)

    def test_missing_duplicate_unrecognized_or_malformed_records_cannot_authorize_probe(self):
        original = self.evidence['native_checks']
        for checks in (original[:-1], original + [original[0]],
                [*original[:-1], original[0]], [{'id': 'arbitrary_ready', 'verdict': 'pass'}],
                [*original[:-1], {'id': 'actual_input_use', 'reason': 'semantic_input_use_unobserved'}],
                [*original[:-1], None]):
            with self.subTest(checks=checks), self.assertRaises(PermissionError):
                self.gate({**self.evidence, 'native_checks': checks})

    def test_owner_pass_cannot_waive_any_native_failure_or_other_native_unknown(self):
        self.evidence['owner_assessment'] = {'verdict': 'pass'}
        for index, original in enumerate(self.evidence['native_checks']):
            for verdict in ('fail', 'unknown'):
                if verdict == 'unknown' and original['id'] in ('actual_reasoning', 'actual_input_use'):
                    continue
                changed = copy.deepcopy(self.evidence)
                changed['native_checks'][index]['verdict'] = verdict
                with self.subTest(identifier=original['id'], verdict=verdict), self.assertRaises(PermissionError):
                    self.gate(changed)

    def test_negative_native_aggregate_and_observation_reason_mismatch_are_not_waived(self):
        with self.assertRaises(PermissionError):
            self.gate({**self.evidence, 'native_verdict': 'fail'})
        changed = copy.deepcopy(self.evidence)
        changed['native_checks'][-1]['reason'] = 'unexplained_unknown'
        with self.assertRaises(PermissionError):
            self.gate(changed)

    def test_unknown_meaning_requires_owner_and_negative_or_dependency_unknown_still_blocks(self):
        for verdict in ('unknown', 'owner_required'):
            changed = copy.deepcopy(self.evidence)
            changed['assessment']['verdict'] = verdict
            with self.assertRaises(PermissionError):
                self.gate(changed)
            changed['owner_assessment'] = {'verdict': 'pass'}
            self.assertEqual(self.gate(changed), ('actual_input_use', 'actual_reasoning'))
        for assessment, dependencies in (({'verdict': 'fail', 'findings': []}, 'pass'),
                ({'verdict': 'unknown', 'findings': [{'verdict': 'fail'}]}, 'pass'),
                ({'verdict': 'pass', 'findings': []}, 'unknown')):
            changed = {**self.evidence, 'assessment': assessment, 'dependencies': {'verdict': dependencies},
                'owner_assessment': {'verdict': 'pass'}}
            with self.assertRaises(PermissionError):
                self.gate(changed)


if __name__ == '__main__':
    unittest.main()
