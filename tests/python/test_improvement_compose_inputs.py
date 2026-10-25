"""Host composition inputs over real SQL/Fernet and labelled storage controls.

The existing selection fixture supplies synthetic availability during upstream
historical admission and synthetic_storage_fixture completed result cells. These
are explicit storage/lineage controls, never real native/account/business proof.
Both A patches are actually staged; domain_process is set before arm2 staging.
No fabricated compose operation, third candidate or inherited pass is supplied.
"""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import hashlib
import importlib
import importlib.util
import json
import unittest
from contextlib import closing
from dataclasses import replace
from unittest.mock import patch

import improvement_cases as IC
import improvement_comparison_results as C
import improvement_experiment_protocol as P
import improvement_store as IM
from improvement_blobs import AssetUnavailable
from improvement_compose_protocol import render_compose_input
import test_improvement_experiment_selection as fixtures


DENIED = (PermissionError, IM.ConflictError, AssetUnavailable, ValueError)


class ComposeInputTests(unittest.TestCase):
    def setUp(self):
        # Missing implementation must fail before expensive/private fixture work.
        self.assertIsNotNone(importlib.util.find_spec('improvement_compose_inputs'),
                             'Actual authenticated ComposeInputs host consumer is absent')
        self.inputs_module = importlib.import_module('improvement_compose_inputs')
        self.fixture = fixtures.ExperimentSelectionTests()
        self.fixture.setUp()
        self.addCleanup(lambda: self.assertTrue(self.fixture.doCleanups(), 'Actual fixture cleanup failed'))
        self.lineage, self.owner = self.fixture.h, self.fixture.owner
        self.assets, self.store = self.fixture.assets, self.fixture.store
        self.plan_fixture = self.lineage.h
        self.plans = self.plan_fixture.plans()
        self.host_files = self.plan_fixture.f
        self.first = self.plan_fixture.h.candidate
        self.original_patches = [json.loads(self.assets.blobs.read(self.owner.brain_id, self.first['patch_hash']))]
        second_patch = copy.deepcopy(self.original_patches[0])
        second_patch.update(replacement='Retain owner rules.\nCheck the controlling source total twice.\n',
                            angle='domain_process')
        self.second = self.plan_fixture.authoring.stage(self.owner, 'association-experiment', second_patch,
                                                       event_key='compose-input-domain-candidate')
        self.original_patches.append(second_patch)
        bound = self.plans.bind_arm(self.owner, 'association-experiment', self.second['candidate_id'],
            self.second['edit_authority']['authority_id'], expected_generation=self.fixture.saved['generation'],
            event_key='compose-input-domain-arm')
        frozen = self.plans.freeze(self.owner, 'association-experiment', 2, 'tuning',
            expected_generation=bound['generation'], event_key='compose-input-domain-tuning')
        with closing(self.store._conn()) as connection:
            self.other_comparison = dict(connection.execute('SELECT * FROM improvement_comparisons WHERE id=?',
                (frozen['comparison_id'],)).fetchone())
        matrix = json.loads(self.assets.blobs.read(self.owner.brain_id, self.other_comparison['matrix_blob_hash']))
        request = copy.deepcopy(self.lineage.request)
        request['pins']['candidate_bundle_hash'] = bound['envelope_hash']
        request['lineage'].update(comparison_id=self.other_comparison['id'],
            comparison_hash=P.comparison_hash(self.other_comparison), matrix_hash=self.other_comparison['matrix_hash'],
            arm_ordinal=2, arm_hash=bound['envelope_hash'], candidate_id=bound['candidate_id'])
        with patch.object(self.lineage, 'comparison', self.other_comparison), \
                patch.object(self.lineage, 'matrix', matrix), patch.object(self.lineage, 'request', request), \
                patch.object(self.lineage, 'frozen', frozen):
            self.fixture.seed_technical_complete_cells(wins=True)
        self.other_saved = self.fixture.reports.create(self.owner, self.other_comparison['id'],
            expected_generation=frozen['generation'], event_key='compose-input-complete-domain-report')
        for saved in (self.fixture.saved, self.other_saved):
            report = self.fixture.reports.read(self.owner, saved['report_id'])
            self.assertTrue(report['summary']['selection_supported'])
            self.assertEqual(report['summary']['business_eligibility'], 'unverified')
        self.service = self.inputs_module.ComposeInputs(self.plans)
        self.generation = self.other_saved['generation']
        self.before = self.counts()

    def counts(self):
        with closing(self.store._conn()) as connection:
            return {table: connection.execute('SELECT count(*) FROM ' + table).fetchone()[0] for table in (
                'improvement_trials', 'agent_calls', 'improvement_skill_candidates', 'improvement_comparisons',
                'improvement_comparison_reports', 'improvement_qualification_claims', 'improvement_case_exposures')}

    def build(self, owner=None, generation=None):
        return self.service.build(self.owner if owner is None else owner, 'association-experiment',
            expected_generation=self.generation if generation is None else generation)

    def input_events(self):
        with closing(self.store._conn()) as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM improvement_events WHERE operation='compose_input'")]

    def exposure_rows(self):
        with closing(self.store._conn()) as connection:
            return [dict(row) for row in connection.execute('SELECT * FROM improvement_case_exposures WHERE brain_id=? '
                'ORDER BY fingerprint,case_set_id', (self.owner.brain_id,))]

    def assert_no_publication(self):
        self.assertEqual(self.input_events(), [])
        self.assertEqual(self.counts(), self.before)
        self.assertEqual(self.plans.records.get(self.owner, 'association-experiment')['generation'], self.generation)

    def test_exact_current_projection_encrypted_basis_idempotence_and_actual_upstream_consumer(self):
        # The historical A patch refs are empty; do not rewrite those immutable
        # manifests to pretend they cited trials which happened after authoring.
        self.assertEqual([item['evidence_refs'] for item in self.original_patches], [[], []])
        answers = {IM._hash(case['answer']) for case in self.plan_fixture.h.h.f.cases}
        original_read = self.assets.blobs.read
        old_exposures = self.exposure_rows()
        with closing(self.store._conn()) as connection:
            tuning_keys = {(row[0], row[1], row[2]) for row in connection.execute('SELECT DISTINCT brain_id,fingerprint,case_set_id '
                "FROM improvement_case_families WHERE brain_id=? AND case_set_id=? AND split='tuning'",
                (self.owner.brain_id, self.lineage.value['case_set_id']))}
        with patch.object(self.assets.blobs, 'read', wraps=original_read) as reads, \
                patch.object(IC.CaseStore, 'evaluator_case', side_effect=AssertionError('No private evaluator read')):
            saved = self.build()
        self.assertEqual(set(saved), {'data', 'input_hash', 'input_blob_hash', 'basis_hash', 'basis_blob_hash'})
        data = saved['data']
        self.assertEqual(data['kind'], 'body_compose_projection')
        self.assertEqual(data['experiment_id'], 'association-experiment')
        self.assertEqual(data['context_id'], self.lineage.value['context_id'])
        self.assertEqual(data['definition_hash'], IM._hash(self.lineage.value))
        self.assertEqual(data['baseline']['content'].encode(), self.host_files.skill.read_bytes())
        self.assertEqual(data['public_contract'], IC.public_contract(self.plan_fixture.h.h.f.contract))
        self.assertEqual([candidate['patch'] for candidate in data['candidates']], self.original_patches)
        self.assertEqual([candidate['candidate_id'] for candidate in data['candidates']],
                         [self.first['candidate_id'], self.second['candidate_id']])
        with closing(self.store._conn()) as connection:
            linked = {row[0] for row in connection.execute('SELECT trial_id FROM improvement_experiment_trial_links')}
        observations = [item for group in data['tuning'] for item in group['observations']]
        self.assertEqual({item['ref']['id'] for item in observations}, linked)
        self.assertEqual({item['ref']['kind'] for item in observations}, {'tuning_trial'})
        self.assertEqual({group['variant'] for group in data['tuning']},
                         {'base', self.first['candidate_id'], self.second['candidate_id']})
        rendered = json.loads(render_compose_input(data))
        self.assertEqual(rendered['evidence_projection'], data)
        self.assertIn('checkpoint 1 of 1', rendered['upstream_method'])
        self.assertEqual(saved['input_hash'], IM._hash(data))
        self.assertEqual(saved['input_blob_hash'], saved['input_hash'])
        self.assertEqual(json.loads(original_read(self.owner.brain_id, saved['input_blob_hash'])), data)
        basis = json.loads(original_read(self.owner.brain_id, saved['basis_blob_hash']))
        self.assertEqual(IM._hash(basis), saved['basis_hash'])
        self.assertEqual(saved['basis_blob_hash'], saved['basis_hash'])
        self.assertFalse(answers & {call.args[1] for call in reads.call_args_list})
        for raw in (json.dumps(data), json.dumps(basis), json.dumps(self.input_events())):
            self.assertNotIn('private-owner-answer-', raw)
        self.assertIn('technical-baseline', json.dumps(data))
        self.assertIn('technical-candidate', json.dumps(data))
        self.assertEqual(len(self.input_events()), 1)
        metadata = json.loads(self.input_events()[0]['result_json'])
        self.assertEqual(metadata, {key: saved[key] for key in ('input_hash', 'input_blob_hash', 'basis_hash', 'basis_blob_hash')})
        for key in ('input_blob_hash', 'basis_blob_hash'):
            self.assertTrue(self.assets.blobs._path(self.owner.brain_id, saved[key]).read_bytes().startswith(b'enc:'))
        exposures = self.exposure_rows()
        def keyed(rows): return {(row['brain_id'], row['fingerprint'], row['case_set_id']): row for row in rows}
        old_by_key, actual_by_key = keyed(old_exposures), keyed(exposures)
        self.assertEqual(set(actual_by_key), set(old_by_key) | tuning_keys, 'exact tuning exposures, no extra holdout families')
        self.assertEqual({key: actual_by_key[key] for key in old_by_key}, old_by_key, 'preserve old exposure timestamps/history')
        self.assertEqual(self.build(), saved)
        self.assertEqual(self.exposure_rows(), exposures, 'replay cannot duplicate or refresh exposure')
        self.assertEqual(len(self.input_events()), 1)
        self.assertEqual(self.counts(), {**self.before, 'improvement_case_exposures': len(exposures)})
        self.assertEqual(self.plans.records.get(self.owner, 'association-experiment')['generation'], self.generation)

    def test_latest_incomplete_tuning_report_cannot_be_replaced_with_older_supported_report(self):
        with self.store._Tx(self.store) as connection:
            connection.execute("UPDATE improvement_trial_attempts SET result_json=NULL WHERE trial_id='it_technical_comparison_0'")
        newer = self.fixture.reports.create(self.owner, self.lineage.comparison['id'],
            expected_generation=self.generation, event_key='compose-input-newest-incomplete')
        with self.assertRaises(DENIED): self.build(generation=newer['generation'])
        self.assertEqual(self.input_events(), [])
        self.assertEqual(self.counts()['improvement_comparison_reports'], self.before['improvement_comparison_reports'] + 1)

    def test_only_current_owner_brain_and_exact_policy_can_build(self):
        for principal in (self.host_files.other, replace(self.owner, kind='agent', id='model')):
            with self.subTest(principal=principal), self.assertRaises(DENIED): self.build(owner=principal)
        policy = self.assets.get_policy(self.owner)
        self.assets.set_policy(self.owner, 'off', expected_version=policy['version'], event_key='compose-input-policy-off')
        with self.assertRaises(DENIED): self.build()
        self.assert_no_publication()

    def test_late_actual_attempt_pointer_drift_during_input_blob_write_refuses_publication(self):
        original_write = self.assets.blobs.write
        changed = []
        def write(brain, raw):
            digest = original_write(brain, raw)
            value = json.loads(raw)
            if value.get('kind') == 'body_compose_projection' and not changed:
                with self.store._Tx(self.store) as connection:
                    connection.execute("UPDATE improvement_trial_attempts SET result_json=NULL WHERE trial_id='it_technical_comparison_0'")
                changed.append(True)
            return digest
        with patch.object(self.assets.blobs, 'write', side_effect=write), self.assertRaises(DENIED): self.build()
        self.assertEqual(changed, [True])
        self.assert_no_publication()

    def test_late_canonical_source_drift_during_input_blob_write_refuses_publication(self):
        original_write = self.assets.blobs.write
        changed = []
        def write(brain, raw):
            digest = original_write(brain, raw)
            value = json.loads(raw)
            if value.get('kind') == 'body_compose_projection' and not changed:
                self.host_files.protected.write_bytes(b'Owner instructions changed after input projection.\n')
                changed.append(True)
            return digest
        with patch.object(self.assets.blobs, 'write', side_effect=write), self.assertRaises(DENIED): self.build()
        self.assertEqual(changed, [True])
        self.assert_no_publication()

    def test_replay_after_real_context_revocation_refuses_and_preserves_encrypted_history(self):
        saved = self.build()
        events = self.input_events()
        counts, exposures = self.counts(), self.exposure_rows()
        self.plan_fixture.host.revoke(self.owner, 'association-experiment', expected_generation=1,
                                     event_key='compose-input-revoke-context')
        with self.assertRaises(DENIED): self.build()
        self.assertEqual(self.input_events(), events)
        self.assertEqual(json.loads(self.assets.blobs.read(self.owner.brain_id, saved['input_blob_hash'])), saved['data'])
        self.assertEqual(self.counts(), counts)
        self.assertEqual(self.exposure_rows(), exposures)

    def test_unanchored_engineering_domain_marker_cannot_publish_or_replay_input(self):
        # Intentionally invalid unanchored negative marker, not an invented valid
        # qualification session or native result; categorical refusal is required.
        with self.store._Tx(self.store) as connection:
            self.assets._event(connection, self.owner, 'native-qualification:' + 'a' * 64,
                'native_qualification_session', {'run_hash': 'a' * 64}, {'unanchored_control_fixture': True})
        with self.assertRaisesRegex(PermissionError, 'qualification_store_anchor_required'): self.build()
        self.assert_no_publication()


if __name__ == '__main__': unittest.main()
