"""SQL/blob view lineage is history, never native or current source authority."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import importlib
import importlib.util
import json
import unittest
from contextlib import closing
from unittest.mock import patch

import improvement_store as IM
from improvement_blobs import AssetUnavailable
from improvement_experiment_protocol import comparison_hash, matrix_cell
import test_improvement_view_sources as sources
import test_improvement_view_schema as schema_fixtures


class ViewLineageTests(sources.SourceFixture, unittest.IsolatedAsyncioTestCase):
    def request(self, metadata, position=0):
        with closing(self.assets.store._conn()) as connection:
            frozen = json.loads(connection.execute('SELECT definition_json FROM improvement_experiments WHERE id=? AND brain_id=?',
                (self.comparison['experiment_id'], self.owner.brain_id)).fetchone()[0])
        matrix = json.loads(self.assets.blobs.read(self.owner.brain_id, self.comparison['matrix_blob_hash']))
        cell = matrix_cell(matrix, position)
        return {'version': 4, 'pins': {key: frozen[key] for key in ('experiment_id', 'base_bundle_hash', 'contract_hash',
                'case_set_hash', 'engine_config_hash', 'grant_hash', 'scope_hash', 'policy_version')} |
                {'candidate_bundle_hash': self.comparison['arm_hash']},
            'case_set_id': frozen['case_set_id'], **{key: cell[key] for key in ('case_id', 'repeat', 'variant')},
            'engine_config': self.admitted.request['engine_config'], 'baseline_context_hash': frozen['baseline_context_hash'],
            'target_generations': {frozen['target_id']: frozen['base_generation']}, 'deadline_at': 1,
            'lineage': {'version': 1, 'context_id': frozen['context_id'], 'definition_hash': self.comparison['definition_hash'],
                'comparison_id': self.comparison['id'], 'comparison_hash': comparison_hash(self.comparison),
                'matrix_hash': self.comparison['matrix_hash'], 'arm_ordinal': self.comparison['ordinal'],
                'arm_hash': self.comparison['arm_hash'], 'candidate_id': self.proposal['id'],
                'pair_id': cell['pair_id'], 'cell_position': position},
            'view': {'view_id': metadata['views'][cell['variant']]['view_id'],
                'view_hash': metadata['views'][cell['variant']]['manifest_hash'], 'binding_hash': metadata['binding_hash']}}

    def load(self, request, *, current=True, require_link=False, brain=None, trial_id=None):
        self.assertIsNotNone(importlib.util.find_spec('improvement_view_lineage'), 'Actual scoped view lineage reader is absent')
        module = importlib.import_module('improvement_view_lineage')
        with closing(self.assets.store._conn()) as connection:
            return module.load_view_lineage(connection, brain or self.owner.brain_id, request, blobs=self.assets.blobs,
                current=current, require_link=require_link, trial_id=trial_id)

    async def test_real_pair_authenticates_both_manifests_without_content_answers_or_new_trials(self):
        metadata = self.freeze(self.views_service())
        before = self.counts()
        content = {self.proposal['base_hash'], self.proposal['content_hash']}
        with patch.object(self.assets.blobs, 'read', wraps=self.assets.blobs.read) as reads:
            for position in (0, 1):
                request = self.request(metadata, position)
                proof = self.load(request)
                self.assertEqual(proof['view']['view_id'], request['view']['view_id'])
                self.assertEqual(proof['view']['manifest_hash'], request['view']['view_hash'])
                self.assertEqual(proof['view']['manifest']['variant'], request['variant'])
                self.assertEqual(proof['cell']['pair_id'], request['lineage']['pair_id'])
                with self.assertRaisesRegex(PermissionError, 'view_trial_link_unavailable'):
                    self.load(request, require_link=True)
        self.assertFalse(content & {call.args[1] for call in reads.call_args_list})
        self.assertEqual(self.counts(), before)

    async def test_foreign_view_variant_hash_pair_and_legacy_substitutions_reject(self):
        metadata = self.freeze(self.views_service())
        request = self.request(metadata)
        for change in (lambda r: r['view'].update(view_id='foreign-view'),
                lambda r: r['view'].update(view_hash='0' * 64), lambda r: r['view'].update(binding_hash='0' * 64),
                lambda r: r['view'].update(view_id=metadata['views']['candidate' if r['variant'] == 'baseline' else 'baseline']['view_id']),
                lambda r: r['lineage'].update(pair_id='0' * 64), lambda r: r['lineage'].update(candidate_id='foreign-candidate')):
            altered = copy.deepcopy(request)
            change(altered)
            with self.subTest(altered=altered['view']), self.assertRaises((IM.ConflictError, PermissionError)):
                self.load(altered)
        with self.assertRaises(PermissionError):
            self.load(request, brain='foreign-brain')
        legacy = {key: value for key, value in request.items() if key != 'view'} | {'version': 2}
        from improvement_experiment_lineage import load_lineage
        with closing(self.assets.store._conn()) as connection, self.assertRaisesRegex(PermissionError, 'view_trial_version_required'):
            load_lineage(connection, self.owner.brain_id, legacy, blobs=self.assets.blobs, current=False, require_link=False)

    async def test_history_survives_revocation_without_source_or_native_observation(self):
        metadata = self.freeze(self.views_service())
        request = self.request(metadata)
        self.host.revoke(self.owner, self.comparison['experiment_id'], expected_generation=1, event_key='view-lineage-revoke')
        self.assets.set_policy(self.owner, 'off', expected_version=0, event_key='view-lineage-off')
        with patch.object(self.host, '_snapshot_observe', side_effect=AssertionError('History cannot observe sources')):
            self.assertEqual(self.load(request, current=False)['view']['view_id'], request['view']['view_id'])
            with self.assertRaises(PermissionError):
                self.load(request)

    async def test_tampered_manifest_proof_and_receipt_bytes_fail_historical_integrity(self):
        metadata = self.freeze(self.views_service())
        request = self.request(metadata)
        with closing(self.assets.store._conn()) as connection:
            receipt = connection.execute('SELECT * FROM improvement_semantic_receipts WHERE id=? AND brain_id=?',
                (metadata['semantic_receipt_id'], self.owner.brain_id)).fetchone()
        reader = self.assets.blobs.read
        for digest in (metadata['binding_hash'], metadata['views']['baseline']['manifest_hash'],
                metadata['views']['candidate']['manifest_hash'], receipt['binding_blob_hash'], receipt['blob_hash']):
            def corrupt(brain, key):
                raw = reader(brain, key)
                return b'{}' if key == digest else raw
            with self.subTest(digest=digest), patch.object(self.assets.blobs, 'read', side_effect=corrupt), \
                    self.assertRaises((IM.ConflictError, PermissionError, AssetUnavailable)):
                self.load(request, current=False)

    async def test_sql_metadata_without_real_publication_never_becomes_historical_authority(self):
        with self.assets.store._Tx(self.assets.store) as connection:
            for variant in ('baseline', 'candidate'):
                schema_fixtures.ViewScopeTests.insert(connection, 'improvement_effective_views', self.views[variant])
                schema_fixtures.ViewScopeTests.insert(connection, 'improvement_effective_view_assets', self.view_assets[variant])
            schema_fixtures.ViewScopeTests.insert(connection, 'improvement_comparison_views', self.binding)
        metadata = self.views_service().read_existing(self.owner, self.comparison['id'])
        with patch.object(self.assets.blobs, 'read', wraps=self.assets.blobs.read) as reads, \
                self.assertRaisesRegex(PermissionError, 'comparison_view_publication_unavailable'):
            self.load(self.request(metadata), current=False)
        forbidden = {metadata['binding_hash'], *(item['manifest_hash'] for item in metadata['views'].values())}
        self.assertFalse(forbidden & {call.args[1] for call in reads.call_args_list})


class ExplicitModeTests(unittest.TestCase):
    def test_modes_are_typed_and_trial_identity_requires_link_verification(self):
        from improvement_view_lineage import load_view_lineage
        for modes in ({'current': 1, 'require_link': False}, {'current': False, 'require_link': 1},
                {'current': False, 'require_link': False, 'trial_id': 'unverified-trial'}):
            with self.subTest(modes=modes), self.assertRaisesRegex(ValueError, 'explicit_view_lineage_mode_required'):
                load_view_lineage(None, 'shape-only', None, blobs=None, **modes)


class OwnerHistoryTests(sources.SourceFixture, unittest.IsolatedAsyncioTestCase):
    request = ViewLineageTests.request
    load = ViewLineageTests.load

    async def service(self):
        return await sources.SourceFixture.service(self, verdict='owner_required')

    async def test_exact_synthetic_owner_event_survives_history_without_erasing_unknown(self):
        evidence = self.semantic_subject.current_evidence(self.owner, self.proposal['id'])
        key = 'view-history-exact-synthetic-owner'
        self.semantic_subject.arbitrate(self.owner, self.proposal['id'], evidence['receipt_id'], verdict='pass',
            reason='Synthetic isolated history fixture; no human business acceptance.',
            expected_binding_hash=evidence['binding_hash'], expected_generation=self.generation(), event_key=key)
        metadata = self.freeze(self.views_service())
        request = self.request(metadata)
        proof = self.load(request, current=False)
        self.assertEqual(proof['view']['manifest']['semantic']['owner_event_key'], key)
        self.assertEqual(self.semantic_subject.current_evidence(self.owner, self.proposal['id'])['verdict'], 'unknown')


if __name__ == '__main__':
    unittest.main()
