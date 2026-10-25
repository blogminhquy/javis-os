"""Real lease/runner scheduling with an inert adapter; no native/model calls."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import threading
import time
import unittest
from unittest.mock import patch

import improvement_trial_runner as runner_module
import test_improvement_trial_runner as fixtures


class PreparationHeartbeatTests(unittest.IsolatedAsyncioTestCase):
    setUp = fixtures.TrialRunnerTests.setUp
    guard = fixtures.TrialRunnerTests.guard
    factory = fixtures.TrialRunnerTests.factory
    recorder = fixtures.TrialRunnerTests.recorder
    runner = fixtures.TrialRunnerTests.runner
    run_trial = fixtures.TrialRunnerTests.run_trial
    call = fixtures.TrialRunnerTests.call

    async def test_validating_heartbeat_renews_during_slow_workspace_preparation(self):
        prepare, heartbeat = self.f.trials.workspace.prepare, self.f.trials.heartbeat
        active, renewed = threading.Event(), []

        def slow(*args, **kwargs):
            active.set()
            try:
                time.sleep(2.4)  # longer than the original short test lease
                return prepare(*args, **kwargs)
            finally:
                active.clear()

        def pulse(*args, **kwargs):
            result = heartbeat(*args, **kwargs)
            if active.is_set():
                renewed.append(result)
            return result

        deadline = self.trial['request']['deadline_at']
        with patch.object(runner_module, 'LEASE_SECONDS', 2), \
                patch.object(runner_module, 'HEARTBEAT_SECONDS', .05), \
                patch.object(self.f.trials.workspace, 'prepare', side_effect=slow), \
                patch.object(self.f.trials, 'heartbeat', side_effect=pulse):
            result = await self.run_trial()
        self.assertEqual(result['status'], 'completed', result['attempts'])
        self.assertTrue(renewed, 'Filesystem preparation must not monopolize the heartbeat mutex')
        self.assertEqual(result['request']['deadline_at'], deadline)
        self.assertEqual(self.call()['status'], 'ok')

    async def test_revocation_during_slow_preparation_refunds_without_engine_ack(self):
        prepare = self.f.trials.workspace.prepare

        def revoked(*args, **kwargs):
            self.revoked = True
            time.sleep(2.4)
            return prepare(*args, **kwargs)

        with patch.object(runner_module, 'LEASE_SECONDS', 2), \
                patch.object(runner_module, 'HEARTBEAT_SECONDS', .05), \
                patch.object(self.f.trials.workspace, 'prepare', side_effect=revoked):
            result = await self.run_trial()
        self.assertEqual(result['status'], 'not_run')
        self.assertNotIn('ack', self.log)
        self.assertIsNone(self.call()['engine_at'])
        self.assertEqual(self.call()['status'], 'refunded')
        path, _ = self.f.trials.workspace._paths(self.trial['trial_id'], 1)
        self.assertFalse(path.exists())

    async def test_repeated_cancellation_holds_lifetime_until_preparation_thread_settles(self):
        prepare = self.f.trials.workspace.prepare
        entered, release = threading.Event(), threading.Event()

        def blocked(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise TimeoutError('Test preparation gate was never released')
            return prepare(*args, **kwargs)

        with patch.object(self.f.trials.workspace, 'prepare', side_effect=blocked):
            task = asyncio.create_task(self.run_trial())
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 5))
                task.cancel()
                await asyncio.sleep(.02)
                task.cancel()
                await asyncio.sleep(.02)
                self.assertFalse(task.done())
                held = self.f.trials.workspace.acquire_brain_execution(self.f.owner.brain_id)
                if held is not None:
                    held.close()
                self.assertIsNone(held, 'Cancellation cannot release ownership before filesystem work ends')
            finally:
                release.set()
                outcome = await asyncio.gather(task, return_exceptions=True)
        self.assertIsInstance(outcome[0], asyncio.CancelledError)
        self.assertIsNone(self.call()['engine_at'])
        self.assertEqual(self.call()['status'], 'refunded')
        path, _ = self.f.trials.workspace._paths(self.trial['trial_id'], 1)
        self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main()
