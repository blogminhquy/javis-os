"""Actual owner HTTP creation preserves the reserved policy; no native work."""
from _paths import ROOT, SERVER  # noqa: F401

import json
import unittest
from contextlib import closing

import httpx
from fastapi import FastAPI

from improvement_experiment_api import register, ExperimentApiDeps
from improvement_experiment_service import ExperimentService
from improvement_trial_service import OwnerTrialService
import test_improvement_comparison_plans as fixtures


class ComposedApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_http_create_reserves_three_and_rejects_an_extra_budget_knob(self):
        fixture = fixtures.ComparisonPlanTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        plans = fixture.plans()
        trials = OwnerTrialService(fixture.host)
        service = ExperimentService(plans, trials)
        self.addAsyncCleanup(trials.close)
        self.addAsyncCleanup(service.close)
        app = FastAPI()
        register(app, ExperimentApiDeps(read_store=lambda: fixture.assets,
            resolve_brain=lambda brain: fixture.owner.brain_id, owner_session=lambda request: None,
            service=lambda: service))
        request = {**fixture.request(candidate_policy='two_proposals_and_one_compose'),
                   'event_key': 'owner-http-reserved-composed-policy'}
        before = (fixture.count('agent_calls'), fixture.count('improvement_trials'))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            denied = await client.post('/improvement-experiments', json={**request, 'multiple_tests': 3})
            self.assertEqual(denied.status_code, 400)
            with closing(fixture.store._conn()) as connection:
                self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name='improvement_experiments'").fetchone(),
                    'Invalid HTTP request must not even migrate the released fixture schema')
            response = await client.post('/improvement-experiments', json=request)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(response.json()['ok'])
        with closing(fixture.store._conn()) as connection:
            definition = json.loads(connection.execute('SELECT definition_json FROM improvement_experiments').fetchone()[0])
        self.assertEqual(definition['decision_policy'], {'id': 'paired-skill-v1', 'version': 1, 'multiple_tests': 3})
        self.assertEqual((fixture.count('agent_calls'), fixture.count('improvement_trials')), before)
        self.assertEqual(fixture.count('improvement_compose_authorizations'), 0)
        self.assertEqual(fixture.count('improvement_operations'), 0)


if __name__ == '__main__':
    unittest.main()
