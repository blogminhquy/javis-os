"""Late domain-marker refusal using actual ordinary incomplete-report fixtures.

The injected immutable marker is an intentionally unanchored CONTROL-FLOW
negative, not a valid qualification run or product/native/quality evidence.
Actual authenticated engineering-store cases live in product_boundaries tests.
"""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
from contextlib import closing
import json
import unittest
from unittest.mock import patch

import improvement_store as IM
from improvement_operation_execution import OperationExecution
from improvement_operation_runner import OperationRunner
from improvement_operation_tasks import OperationTasks
from improvement_role_workflow import RoleWorkflow
from improvement_trial_service import OwnerTrialService
import test_improvement_comparison_reports as reports_fixture


class QualificationProductRaceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = reports_fixture.ComparisonReportTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.assets, self.store, self.owner = self.fixture.assets, self.fixture.store, self.fixture.owner

    def mark_domain(self):
        # No valid run, auth or result is invented. An unanchored marker must
        # categorically refuse ordinary use instead of silently downgrading.
        with self.store._Tx(self.store) as connection:
            self.mark_in(connection)

    def mark_in(self, connection):
        self.assets._event(connection, self.owner, 'native-qualification:' + 'a' * 64,
            'native_qualification_session', {'run_hash': 'a' * 64},
            {'unanchored_control_fixture': True})

    def count(self, table):
        with closing(self.store._conn()) as connection:
            return connection.execute('SELECT count(*) FROM ' + table).fetchone()[0]

    def test_domain_change_during_report_blob_write_prevents_final_publication(self):
        original = self.assets.blobs.write
        changed = []
        def write(brain, raw):
            digest = original(brain, raw)
            value = json.loads(raw)
            if isinstance(value, dict) and 'result_refs' in value and 'summary' in value:
                self.mark_domain(); changed.append(True)
            return digest
        with patch.object(self.assets.blobs, 'write', side_effect=write):
            with self.assertRaisesRegex(PermissionError, 'qualification_store_anchor_required'):
                self.fixture.create()
        self.assertEqual(changed, [True])
        self.assertEqual(self.count('improvement_comparison_reports'), 0)

    def test_domain_change_after_cold_report_evidence_prevents_return(self):
        saved = self.fixture.create()
        reports = self.fixture.reports()
        original = reports._evidence
        def evidence(*args, **kwargs):
            result = original(*args, **kwargs)
            self.mark_domain()
            return result
        with patch.object(reports, '_evidence', side_effect=evidence):
            with self.assertRaisesRegex(PermissionError, 'qualification_store_anchor_required'):
                reports.read(self.owner, saved['report_id'])
        self.assertEqual(self.count('improvement_comparison_reports'), 1, 'original encrypted history remains')

    def test_domain_change_before_selection_transaction_prevents_keep_base_publication(self):
        plans = self.fixture.h.h.plans()
        original_tx = self.store._Tx
        changed = []
        def transaction(store):
            with original_tx(store) as connection:
                self.mark_in(connection)
            changed.append(True)
            return original_tx(store)
        with patch.object(self.store, '_Tx', side_effect=transaction):
            with self.assertRaisesRegex(PermissionError, 'qualification_store_anchor_required'):
                plans.select(self.owner, 'association-experiment', 'keep_base', ordinal=None,
                    expected_generation=self.fixture.h.frozen['generation'], event_key='late-domain-selection')
        self.assertEqual(changed, [True])
        self.assertEqual(self.count('improvement_experiment_selections'), 0)

    def test_domain_change_while_owned_role_settles_prevents_result_return(self):
        async def exercise():
            plans = self.fixture.h.h.plans()
            execution = OperationExecution(plans, OwnerTrialService(plans.host))
            workflow = RoleWorkflow(execution, OperationTasks(execution, OperationRunner(execution)))
            async def controlled_result():
                self.mark_domain()
                return {'control_fixture': 'not a product or model result'}
            try:
                with self.assertRaisesRegex(PermissionError, 'qualification_store_anchor_required'):
                    await workflow._run_owned(self.owner, 'association-experiment', 'late-domain-role-result',
                        {'control_fixture': True}, controlled_result)
            finally: await workflow.close()
        asyncio.run(exercise())


if __name__ == '__main__': unittest.main()
