"""Actual frozen-plan admission/current SQL with engineering native verification."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
from contextlib import closing
import unittest
from unittest.mock import patch

from improvement_claude import ClaudeTrialAdapter
import test_improvement_experiment_admission as experiment_fixture
import test_improvement_preparation as preparation_fixture
import test_improvement_view_sources as view_fixture


class PlanAuthorityAssertions:
    def counts(self):
        with closing(self.assets.store._conn()) as connection:
            return tuple(connection.execute('SELECT COUNT(*) FROM ' + name).fetchone()[0]
                         for name in ('improvement_trials', 'agent_calls'))

    def checker(self, revoke):
        before = self.counts()
        def verify(adapter):
            boundary = adapter._native_boundary
            self.assertIsNotNone(boundary, 'actual frozen-plan admission must bind before native verification')
            self.assertIs(boundary.assets, self.assets)
            self.assertIs(boundary.principal, self.owner)
            self.assertEqual(self.counts(), before)
            with self.assets.store._Tx(self.assets.store) as connection:
                self.assertEqual(boundary.current(connection, None), 'allow')
            if revoke:
                self.assets.set_policy(self.owner, 'off', expected_version=0, event_key='native-plan-revoke')
                with self.assets.store._Tx(self.assets.store) as connection:
                    with self.assertRaises(PermissionError):
                        boundary.current(connection, None)
                raise PermissionError('engineering_observed_plan_authority_denial')
            with self.assets.store._Tx(self.assets.store) as connection:
                self.assertEqual(boundary.current(connection, None), 'allow')
            return {'supported': True, 'capability_hash': 'c' * 64}
        return verify

    def check(self, invoke, *, revoke=False):
        before = self.counts()
        with patch.object(ClaudeTrialAdapter, 'verify', self.checker(revoke)):
            if revoke:
                with self.assertRaisesRegex(ValueError, 'trial_native_unavailable'): invoke()
                self.assertEqual(self.counts(), before)
            else:
                result = invoke()
                self.assertEqual(self.counts(), tuple(value + 1 for value in before))
                with patch.object(ClaudeTrialAdapter, 'verify', side_effect=AssertionError('historical plan replay probed')):
                    self.assertEqual(invoke(), result)


class ExperimentPlanAuthorityTests(PlanAuthorityAssertions, unittest.TestCase):
    def setUp(self):
        self.f = experiment_fixture.ExperimentAdmissionTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.owner, self.assets = self.f.owner, self.f.assets

    def test_frozen_experiment_cell_binds_authority_and_replay_is_cold(self):
        self.check(self.f.admit)

    def test_policy_revocation_during_experiment_preflight_cannot_reserve(self):
        self.check(self.f.admit, revoke=True)


class PreparationPlanAuthorityTests(PlanAuthorityAssertions, unittest.TestCase):
    def setUp(self):
        self.f = preparation_fixture.PreparationTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.owner, self.assets = self.f.owner, self.f.assets
        self.f.freeze()
        self.subject = self.f.service()

    def invoke(self):
        return self.subject.admit_next(self.owner, 'association-experiment', expected_generation=2,
                                       event_key='native-preparation-admit')

    def test_frozen_baseline_preparation_binds_authority_and_replay_is_cold(self):
        self.check(self.invoke)

    def test_policy_revocation_during_preparation_preflight_cannot_reserve(self):
        self.check(self.invoke, revoke=True)


class ViewPlanAuthorityTests(PlanAuthorityAssertions, view_fixture.SourceFixture, unittest.IsolatedAsyncioTestCase):
    # SourceFixture creates real sealed preparation, semantic result and exact
    # candidate/view lineage using a synthetic SDK adapter. No actual native IO.
    async def check_view(self, revoke=False):
        from improvement_comparison_schedule import ComparisonSchedule
        from improvement_view_admission import ViewExperimentAdmission
        views = self.views_service()
        self.freeze(views)
        plans = self.f.plans
        subject = ViewExperimentAdmission(plans, views, ComparisonSchedule(plans, plans.admission.trials))
        generation = self.generation()
        def invoke():
            return subject.admit_next(self.owner, self.comparison['experiment_id'], self.comparison['id'],
                expected_generation=generation, event_key='native-view-admission')
        await asyncio.to_thread(self.check, invoke, revoke=revoke)

    async def test_frozen_view_cell_binds_authority_and_replay_is_cold(self):
        await self.check_view()

    async def test_policy_revocation_during_view_preflight_cannot_reserve(self):
        await self.check_view(revoke=True)


if __name__ == '__main__': unittest.main()
