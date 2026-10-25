"""Engineering M0 must not become ordinary comparison/selection/role product.

Borrow actual private Session/host/plans/prepared operation setup, with its
declared candidate/static-observer, historical input1 and internal records-
reservation seams. No successful native verifier/product/quality is fabricated.
Seeded immutable replay events and pending join tasks are CONTROL-FLOW fixtures,
not eligible reports or evidence that a model was executed.
"""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
from contextlib import closing
import json
import unittest
from unittest.mock import patch

from improvement_blobs import AssetUnavailable
from improvement_comparison_results import ComparisonResults
from improvement_operation_runner import OperationRunner
from improvement_operation_tasks import OperationTasks
from improvement_role_workflow import RoleWorkflow
import improvement_store as IM
import test_improvement_qualification_operation_binding as fixture


class QualificationProductBoundaryTests(unittest.TestCase):
    setUp = fixture.QualificationOperationBindingTests.setUp

    def experiment(self):
        return self.plans.records.get(self.owner, 'association-experiment')

    def count(self, table):
        with closing(self.store._conn()) as connection:
            return connection.execute('SELECT count(*) FROM ' + table).fetchone()[0]

    def frozen_comparison(self):
        """Actual manual A/arm/matrix authoring only; no claimed successful C."""
        target = self.association.f.target
        raw = self.association.f.skill.read_bytes()
        start = raw.index(b'Retain owner rules.')
        authority = self.plans.authoring.declare_region(self.owner, 'association-experiment',
            target['revision_id'], start, len(raw), expected_target_generation=1,
            event_key='product-domain-declare-region')
        candidate = self.plans.authoring.stage(self.owner, 'association-experiment', {
            'version': 1, 'target_id': target['target_id'], 'base_revision_id': target['revision_id'],
            'before_hash': target['source_hash'], 'operation': 'replace_body_region', 'start': start,
            'end': len(raw), 'replacement': 'Retain owner rules.\nCheck every authorized row.\n',
            'hypothesis': 'A row check could prevent omissions.', 'failure_signature': 'Synthetic unproven omission.',
            'expected_behavior': 'Each authorized row checked once.', 'possible_regressions': ['Duplicate checks.'],
            'evidence_refs': [], 'angle': 'execution'}, event_key='product-domain-stage-unreviewed-candidate')
        bound = self.plans.bind_arm(self.owner, 'association-experiment', candidate['candidate_id'],
            authority['authority_id'], expected_generation=self.experiment()['generation'],
            event_key='product-domain-bind-unreviewed-arm')
        frozen = self.plans.freeze(self.owner, 'association-experiment', bound['ordinal'], 'tuning',
            expected_generation=bound['generation'], event_key='product-domain-freeze-empty-matrix')
        self.assertEqual(self.count('improvement_trials'), 0)
        self.assertEqual(self.count('agent_calls'), 1, 'only the declared upstream prepared operation call exists')
        return frozen

    def test_cold_comparison_read_refuses_anchored_unanchored_and_missing_root_before_report_lookup(self):
        reader = ComparisonResults.from_existing(self.assets)
        before = self.count('improvement_events')
        with self.assertRaisesRegex(PermissionError, 'non_product_execution_domain'):
            reader.read(self.owner, 'icr_no_report_exists')
        ordinary = IM.ImprovementStore(self.store, self.assets.blobs)
        with self.assertRaisesRegex(PermissionError, 'qualification_store_anchor_required'):
            ComparisonResults.from_existing(ordinary).read(self.owner, 'icr_no_report_exists')
        self.assertEqual(self.count('improvement_events'), before)
        with self.store._Tx(self.store) as connection:
            connection.execute('DROP TRIGGER improvement_events_delete')
            connection.execute("DELETE FROM improvement_events WHERE operation='native_qualification_session'")
        with self.assertRaises(AssetUnavailable): reader.read(self.owner, 'icr_no_report_exists')
        self.assertEqual(self.count('improvement_comparison_reports'), 0)

    def test_comparison_creation_cannot_publish_ordinary_inconclusive_no_cell_report(self):
        frozen = self.frozen_comparison(); before = self.experiment()
        with self.assertRaisesRegex(PermissionError, 'non_product_execution_domain'):
            ComparisonResults(self.plans).create(self.owner, frozen['comparison_id'],
                expected_generation=frozen['generation'], event_key='product-domain-no-cell-report')
        self.assertEqual(self.experiment(), before)
        self.assertEqual(self.count('improvement_comparison_reports'), 0)
        with closing(self.store._conn()) as connection:
            self.assertIsNone(connection.execute("SELECT 1 FROM improvement_events WHERE event_key='product-domain-no-cell-report'").fetchone())

    def test_comparison_replay_event_is_not_a_domain_exemption(self):
        identifier, key = 'icp_control_fixture_no_native_results', 'product-domain-comparison-replay'
        generation = self.experiment()['generation']
        payload = {'comparison_id': identifier, 'expected_generation': generation}
        # Actual immutable M0 event simulates an early historical return only.
        # Its result deliberately contains NO verdict/result/eligibility claims.
        with self.store._Tx(self.store) as connection:
            self.assets._event(connection, self.owner, key, 'comparison_report', payload,
                {'engineering_control_fixture': 'must never be returned as ordinary product'})
        before = self.count('improvement_events')
        with self.assertRaisesRegex(PermissionError, 'non_product_execution_domain'):
            ComparisonResults(self.plans).create(self.owner, identifier,
                expected_generation=generation, event_key=key)
        self.assertEqual(self.count('improvement_events'), before)
        self.assertEqual(self.count('improvement_comparison_reports'), 0)

    def test_selection_keep_base_and_both_replay_choices_refuse_without_phase_change(self):
        before = self.experiment(); generation = before['generation']
        with self.subTest(path='new_keep_base'), self.assertRaisesRegex(PermissionError, 'non_product_execution_domain'):
            self.plans.select(self.owner, 'association-experiment', 'keep_base', ordinal=None,
                expected_generation=generation, event_key='product-domain-new-keep-base')
        for choice, ordinal in (('keep_base', None), ('candidate', 1)):
            key = 'product-domain-replay-' + choice
            payload = {'experiment_id': 'association-experiment', 'choice': choice,
                'ordinal': ordinal, 'expected_generation': generation}
            with self.store._Tx(self.store) as connection:
                self.assets._event(connection, self.owner, key, 'experiment_select', payload,
                    {'engineering_control_fixture': 'no candidate or baseline selection is claimed'})
            with self.subTest(path='replay_' + choice), self.assertRaisesRegex(PermissionError, 'non_product_execution_domain'):
                self.plans.select(self.owner, 'association-experiment', choice, ordinal=ordinal,
                    expected_generation=generation, event_key=key)
        self.assertEqual(self.experiment(), before)
        self.assertEqual(self.count('improvement_experiment_selections'), 0)

    def test_actual_owned_role_admission_and_existing_join_never_cross_domain_boundary(self):
        async def exercise():
            workflow = RoleWorkflow(self.execution, OperationTasks(self.execution, OperationRunner(self.execution)))
            payload = {'engineering_control_fixture': 'no model or product'}
            calls = []
            async def factory(): calls.append(True); return None
            joined = None
            try:
                with self.subTest(path='new_factory'), self.assertRaisesRegex(PermissionError, 'non_product_execution_domain'):
                    await workflow._run_owned(self.owner, 'association-experiment', 'product-domain-role-new', payload, factory)
                joined = asyncio.create_task(asyncio.sleep(0, result=None))
                await joined
                key = self.owner.brain_id, 'product-domain-role-existing'
                workflow._operations[key] = IM._hash(payload), joined, 'association-experiment', self.owner
                with self.subTest(path='existing_join'), self.assertRaisesRegex(PermissionError, 'non_product_execution_domain'):
                    await workflow._run_owned(self.owner, 'association-experiment', key[1], payload, factory)
                self.assertEqual(calls, [], 'ordinary admission factory must never run for this actual engineering store')
            finally:
                workflow._operations.clear()
                if joined is not None: await asyncio.gather(joined, return_exceptions=True)
                await workflow.close()
        asyncio.run(exercise())
        self.assertEqual(self.execution.ledger.get(self.row['attempts'][-1]['call_id'])['engine_at'], None)

    def test_role_product_and_final_fence_refuse_before_any_product_row_or_artifact_read(self):
        workflow = RoleWorkflow(self.execution, OperationTasks(self.execution, OperationRunner(self.execution)))
        # Use an exact actual PREPARED row/attempt/call snapshot, not a successful
        # native result. It is merely input to the final-fence entrypoint.
        with closing(self.store._conn()) as connection:
            row = self.execution._row(connection, self.owner, self.identifier)
            attempt = self.execution._attempt(connection, row)
            product = {'row': dict(row), 'attempt': dict(attempt),
                'call': self.execution.bound_call(connection, row, attempt), 'trace': []}
        with patch.object(self.execution, '_row', side_effect=AssertionError('ordinary product row read before domain fence')):
            with closing(self.store._conn()) as connection:
                for path, action in {
                    'product': lambda: workflow._product(connection, self.owner, self.identifier),
                    'final_fence': lambda: workflow._product_fence(connection, self.owner, product)}.items():
                    with self.subTest(path=path), self.assertRaisesRegex(PermissionError, 'non_product_execution_domain'):
                        action()
        self.assertEqual(self.count('improvement_operation_results'), 0)


if __name__ == '__main__': unittest.main()
