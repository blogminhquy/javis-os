"""Owned next admission over the real brain barrier, Trials and CallLedger."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import threading
import unittest
from contextlib import closing
from unittest.mock import patch, AsyncMock

import improvement_store as IM
from improvement_claude import ClaudeTrialAdapter
from improvement_experiment_service import ExperimentService
from improvement_trial_service import OwnerTrialService
import test_improvement_view_sources as sources


class ViewNextTests(sources.SourceFixture, unittest.IsolatedAsyncioTestCase):
    def owned_service(self):
        metadata = self.freeze(self.views_service())
        owner_service = OwnerTrialService(self.host)
        self.addAsyncCleanup(owner_service.close)
        service = ExperimentService(self.f.plans, owner_service)
        self.addAsyncCleanup(service.close)
        return service, metadata

    def admit(self, service, key='view-next-owner-admission', generation=None):
        return service.view_admission.admit_next(self.owner, self.comparison['experiment_id'], self.comparison['id'],
            expected_generation=self.generation() if generation is None else generation, event_key=key)

    async def test_next_derives_actual_v4_cell_and_reserves_once_in_existing_ledger(self):
        service, metadata = self.owned_service()
        before = self.counts()[-1]
        with patch.object(ClaudeTrialAdapter, 'verify', return_value={'supported': True, 'capability_hash': 'c' * 64}):
            admitted = self.admit(service)
        self.assertEqual(admitted.request['version'], 4)
        self.assertEqual(admitted.request['lineage']['cell_position'], 0)
        self.assertEqual(admitted.request['view']['binding_hash'], metadata['binding_hash'])
        self.assertEqual(self.counts()[-1], before + 1)
        with closing(self.assets.store._conn()) as connection:
            call = connection.execute('SELECT c.* FROM agent_calls c JOIN improvement_trial_attempts a ON a.call_id=c.id '
                'WHERE a.trial_id=? AND a.brain_id=?', (admitted.trial_id, self.owner.brain_id)).fetchone()
        self.assertEqual(call['purpose'], 'improve_probe')
        self.assertIsNone(call['engine_at'])

    async def test_pending_next_denies_before_plaintext_or_native_preflight(self):
        service, _ = self.owned_service()
        with patch.object(ClaudeTrialAdapter, 'verify', return_value={'supported': True, 'capability_hash': 'c' * 64}):
            self.admit(service)
        counts = self.counts()
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Pending cell cannot decrypt')), \
                patch.object(ClaudeTrialAdapter, 'verify', side_effect=AssertionError('Pending cell cannot probe')), \
                self.assertRaisesRegex(IM.ConflictError, 'pending|busy'):
            self.admit(service, key='view-next-deny-second-pending')
        self.assertEqual(self.counts(), counts)

    async def test_foreign_brain_barrier_denies_before_plaintext_but_exact_replay_is_cold(self):
        service, _ = self.owned_service()
        generation = self.generation()
        handle = service.trials.workspace.acquire_brain_execution(self.owner.brain_id)
        self.assertIsNotNone(handle)
        try:
            with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Busy admission cannot decrypt')), \
                    self.assertRaisesRegex(IM.ConflictError, 'busy'):
                self.admit(service, key='view-next-before-foreign-release')
        finally:
            handle.close()
        with patch.object(ClaudeTrialAdapter, 'verify', return_value={'supported': True, 'capability_hash': 'c' * 64}):
            admitted = self.admit(service, generation=generation)
        self.host.revoke(self.owner, self.comparison['experiment_id'], expected_generation=1, event_key='view-next-replay-revoke')
        self.assets.set_policy(self.owner, 'off', expected_version=0, event_key='view-next-replay-off')
        handle = service.trials.workspace.acquire_brain_execution(self.owner.brain_id)
        self.assertIsNotNone(handle)
        try:
            with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Replay cannot decrypt')), \
                    patch.object(ClaudeTrialAdapter, 'verify', side_effect=AssertionError('Replay cannot probe')):
                self.assertEqual(self.admit(service, generation=generation), admitted)
        finally:
            handle.close()

    async def test_two_concurrent_owner_keys_cannot_reserve_two_immutable_cells(self):
        service, _ = self.owned_service()
        counts = self.counts()
        entered, release = threading.Event(), threading.Event()

        def slow_verify(_adapter):
            entered.set()
            if not release.wait(10):
                raise AssertionError('Native preflight was not released')
            return {'supported': True, 'capability_hash': 'c' * 64}

        with patch.object(ClaudeTrialAdapter, 'verify', slow_verify):
            first = asyncio.create_task(asyncio.to_thread(self.admit, service))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 10))
                with self.assertRaisesRegex(IM.ConflictError, 'busy|pending'):
                    await asyncio.to_thread(self.admit, service, key='view-next-concurrent-other-key')
            finally:
                release.set()
            admitted = await asyncio.wait_for(first, 15)
        self.assertEqual(admitted.request['lineage']['cell_position'], 0)
        self.assertEqual(self.counts()[-1], counts[-1] + 1)

    async def test_revocation_during_native_preflight_cannot_commit_any_new_call(self):
        service, _ = self.owned_service()
        counts = self.counts()

        def revoke(_adapter):
            self.host.revoke(self.owner, self.comparison['experiment_id'], expected_generation=1, event_key='view-next-during-preflight-revoke')
            return {'supported': True, 'capability_hash': 'c' * 64}

        with patch.object(ClaudeTrialAdapter, 'verify', revoke), self.assertRaises((PermissionError, IM.ConflictError)):
            self.admit(service)
        self.assertEqual(self.counts(), counts)

    async def test_owner_service_hands_exact_real_v4_reservation_to_existing_task_dispatcher(self):
        service, metadata = self.owned_service()
        # Native execution remains Task4's responsibility. This synthetic handoff
        # spies on the real durable admission without fabricating a Trial or Call.
        dispatch = AsyncMock(return_value=None)
        with patch.object(ClaudeTrialAdapter, 'verify', return_value={'supported': True, 'capability_hash': 'c' * 64}), \
                patch.object(service.tasks, 'start', dispatch):
            result = await service.next(self.owner, self.comparison['experiment_id'], self.comparison['id'],
                expected_generation=self.generation(), event_key='view-next-service-real-handoff')
        dispatch.assert_awaited_once()
        request = dispatch.call_args.args[1]
        self.assertEqual(request['version'], 4)
        self.assertEqual(request['view']['binding_hash'], metadata['binding_hash'])
        self.assertEqual(result['effective_view'], request['view'])
        self.assertEqual(service.trials.get(self.owner, result['trial_id'])['request'], request)

    async def test_cancelled_http_preflight_remains_owned_until_stop_settles(self):
        service, _ = self.owned_service()
        counts = self.counts()
        entered, release = threading.Event(), threading.Event()

        def slow_verify(_adapter):
            entered.set()
            if not release.wait(10):
                raise AssertionError('Owned preflight was not released')
            return {'supported': True, 'capability_hash': 'c' * 64}

        with patch.object(ClaudeTrialAdapter, 'verify', slow_verify):
            request = asyncio.create_task(service.next(self.owner, self.comparison['experiment_id'], self.comparison['id'],
                expected_generation=self.generation(), event_key='view-next-http-cancel-during-preflight'))
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 10))
                request.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await request
                stopped = asyncio.create_task(service.cancel(self.owner, self.comparison['experiment_id'],
                    expected_generation=self.generation(), event_key='view-next-stop-cancelled-http'))
                for _ in range(200):
                    if self.f.plans.records.get(self.owner, self.comparison['experiment_id'])['phase'] == 'stopping':
                        break
                    await asyncio.sleep(.005)
                self.assertEqual(self.f.plans.records.get(self.owner, self.comparison['experiment_id'])['phase'], 'stopping')
                self.assertFalse(stopped.done())
            finally:
                release.set()
            result = await asyncio.wait_for(stopped, 15)
        self.assertEqual(result['current']['phase'], 'cancelled')
        self.assertEqual(self.counts(), counts)


if __name__ == '__main__':
    unittest.main()
