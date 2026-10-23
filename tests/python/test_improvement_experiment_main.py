"""Actual application auth, lazy dispatcher reuse and shutdown ordering."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import test_improvement_trial_service as fixtures


class MainExperimentTests(unittest.TestCase):
    def setUp(self):
        self.main = fixtures.fixtures.H
        self.assertTrue(hasattr(self.main, "_improvement_experiment_service"), "Experiment main wiring is absent")
        self.f = fixtures.DashboardServiceTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.stack = self.f.stack
        for name, value in (("_IMPROVEMENT_TRIAL_SERVICE", None), ("_IMPROVEMENT_EXPERIMENT_SERVICE", None),
                            ("_IMPROVEMENT_TRIAL_SHUTTING_DOWN", False)):
            self.stack.enter_context(patch.object(self.main, name, value))
        self.stack.enter_context(patch.object(self.main, "_resonance_store", return_value=self.f.assets.store))
        self.client = TestClient(self.main.app)

    def test_all_experiment_routes_deny_token_before_factories_and_preserve_csrf(self):
        routes = [(route.path, sorted(route.methods)[0]) for route in self.main.app.routes
                  if getattr(route, "path", "").startswith(("/improvement-experiments", "/improvement-comparison-reports", '/improvement-operations'))
                  or getattr(route, 'path', '').endswith('/semantic-history')]
        self.assertEqual(len(routes), 26)
        self.assertTrue({('/improvement-experiments/{experiment_id}/view-freeze', 'POST'),
            ('/improvement-experiments/{experiment_id}/view-evidence', 'POST'),
            ('/improvement-experiments/{experiment_id}/views/{comparison_id}', 'GET')} <= set(routes))
        with patch.object(self.main.cfgmod, "gate_active", return_value=True), \
             patch.object(self.main.cfgmod, "valid_session", return_value=False), \
             patch.object(self.main, "_token_ok", return_value=True), \
             patch.object(self.main, "_resonance_store", side_effect=AssertionError("Denied before store")):
            for path, method in routes:
                path = path.replace("{experiment_id}", "invalid").replace("{report_id}", "invalid").replace('{candidate_id}', 'invalid').replace('{operation_id}', 'invalid')
                response = self.client.request(method, path, headers={"Authorization": "Bearer synthetic-token"}, content=b"invalid")
                self.assertEqual(response.status_code, 403, (path, response.text))
        with patch.object(self.main.cfgmod, "gate_active", return_value=True), \
             patch.object(self.main.cfgmod, "valid_session", side_effect=lambda cookie: cookie == "owner-cookie"), \
             patch.object(self.main, "_token_ok", return_value=False):
            self.assertEqual(self.client.get("/improvement-experiments").status_code, 401)
            for path, method in routes:
                if method != 'POST':
                    continue
                path = path.replace('{experiment_id}', 'invalid').replace('{candidate_id}', 'invalid').replace('{operation_id}', 'invalid')
                response = self.client.post(path, cookies={"javis_session": "owner-cookie"},
                    headers={"Origin": "https://foreign.example"}, json={"event_key": "csrf-denied-event"})
                self.assertEqual(response.status_code, 403, path)
                self.assertEqual(response.json()["blocked"], "web_security", path)
        self.assertIsNone(self.main._IMPROVEMENT_EXPERIMENT_SERVICE)

    def test_cold_metadata_does_not_construct_experiment_or_trial_service(self):
        with patch.object(self.main.cfgmod, "gate_active", return_value=False), \
             patch.object(self.main, "_resonance_store", side_effect=AssertionError("Cold GET cannot initialize store")):
            for path in ("/improvement-experiments", "/improvement-experiments/missing", "/improvement-comparison-reports/missing",
                    '/improvement-experiments/missing/preparation', '/improvement-experiments/missing/operations',
                    '/improvement-operations/missing', '/improvement-candidates/missing/semantic-history',
                    '/improvement-experiments/missing/views/missing'):
                response = self.client.get(path, params={"brain": str(self.f.f.brain)})
                self.assertIn(response.status_code, (200, 403, 503), response.text)
                self.assertNotIn("cli_path", response.text)
        self.assertIsNone(self.main._IMPROVEMENT_EXPERIMENT_SERVICE)
        self.assertIsNone(self.main._IMPROVEMENT_TRIAL_SERVICE)

    def test_shutdown_drains_experiment_before_shared_trial_service_and_fences_factories(self):
        service = self.main._improvement_experiment_service()
        self.assertIs(service.trial_service, self.main._improvement_trial_service())
        self.assertIs(service.tasks, self.main._improvement_trial_service().tasks)
        self.assertIs(service.execution.trial_service, service.trial_service)
        self.assertIs(service.execution.workspace.brain_barrier, service.trials.workspace)
        self.assertIs(service.proposals.tasks, service.operation_tasks)
        self.assertIs(service.semantic.tasks, service.operation_tasks)
        observed = []
        experiment_close, trial_close = service.close, service.trial_service.close

        async def experiments():
            observed.append("experiments")
            return await experiment_close()

        async def trials():
            observed.append("trials")
            return await trial_close()

        with patch.object(service, "close", side_effect=experiments), \
             patch.object(service.trial_service, "close", side_effect=trials):
            asyncio.run(self.main._shutdown_improvement_trials())
        self.assertEqual(observed, ["experiments", "trials"])
        self.assertTrue(service._closed)
        self.assertTrue(service.proposals._closed)
        self.assertTrue(service.semantic._closed)
        self.assertTrue(service.operation_tasks._closed)
        with self.assertRaises(RuntimeError):
            self.main._improvement_experiment_service()


if __name__ == "__main__":
    unittest.main()
