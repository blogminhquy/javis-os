"""Actual experiment compose facade; synthetic native packets never prove readiness."""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import copy
import json
import threading
import unittest
from contextlib import closing, aclosing
from unittest.mock import patch
import improvement_store as IM
from improvement_compose_permissions import ComposePermissions
from improvement_experiment_requests import validate
from improvement_experiment_service import ExperimentService
from improvement_trial_requests import TrialRequestError
from improvement_trial_service import OwnerTrialService
import test_improvement_compositions as publication


class ComposeControlsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.h = publication.CompositionTests()
        # Register every nested fixture cleanup on this initialized async owner.
        self.h.addCleanup = self.addCleanup
        self.h.setUp()
        self.owner, self.assets, self.saved = self.h.owner, self.h.assets, self.h.saved
        trials = OwnerTrialService(self.h.execution.plans.host)
        self.addAsyncCleanup(trials.close)
        self.service = ExperimentService(self.h.execution.plans, trials)
        self.addAsyncCleanup(self.service.close)
        self.experiment = self.saved['experiment_id']
        self.generation = self.saved['experiment_generation']

    def payload(self, **changes):
        return {'expected_generation': self.generation, 'event_key': 'owner-compose-facade', **changes}

    async def control(self, operation, **changes):
        return await self.service.workflow(self.owner, self.experiment, operation, self.payload(**changes))

    def synthetic_native(self, *, qualified=True):
        # Reuse labelled native controls only, then attach its runner to the ONE
        # actual experiment tasks/execution. No product/reader/current bypass.
        synthetic = self.h.service(qualified_storage=qualified)
        self.h.execution = self.service.execution
        from improvement_operation_runner import OperationRunner
        self.service.operation_tasks.runner = OperationRunner(self.service.execution, adapter_factory=self.h.adapter)

    async def test_closed_shapes_and_ownership_share_actual_tasks(self):
        for operation in ('compose-preview', 'compose-authorize', 'compose', 'compose-revoke'):
            value = self.payload()
            if operation in ('compose', 'compose-revoke'):
                value['authorization_id'] = self.saved['authorization_id']
            try:
                accepted = validate(value, operation)
            except TrialRequestError:
                accepted = None
            self.assertIsNotNone(accepted, 'Closed compose control is absent: ' + operation)
            for extra in ('input_hash', 'definition_hash', 'native_ready', 'operation', 'multiple_tests'):
                with self.assertRaises(TrialRequestError):
                    validate({**value, extra: True}, operation)
            for bad in (True, 0, '1'):
                with self.assertRaises(TrialRequestError):
                    validate({**value, 'expected_generation': bad}, operation)
        self.assertIs(self.service.composer.execution, self.service.execution)
        self.assertIs(self.service.composer.tasks, self.service.operation_tasks)

    async def test_preview_refs_current_source_and_no_consent_or_native(self):
        before = len(self.h.rows('improvement_compose_authorizations'))
        with patch('improvement_operation_adapter.ClaudeOperationAdapter.verify', side_effect=AssertionError('Preview cannot probe')):
            result = await self.control('compose-preview')
            self.assertEqual(result['experiment_id'], self.experiment)
            self.assertEqual(len(result['candidate_refs']), 2)
            self.assertTrue(result['tuning_refs'])
            self.assertEqual(result['native_capability'], 'unknown')
            self.assertFalse(result['business_proof'])
            self.assertNotIn('data', result)
            self.assertNotIn('baseline', result)
            self.assertNotIn('observations', result)
            self.assertEqual(await self.control('compose-preview'), result)
            protected = self.h.f.f.f.host_files.protected
            original = protected.read_bytes()
            try:
                protected.write_bytes(original + b'\nCurrent owner source drift.\n')
                with self.assertRaises((PermissionError, IM.ConflictError)):
                    await self.control('compose-preview')
            finally:
                protected.write_bytes(original)
        self.assertEqual(len(self.h.rows('improvement_compose_authorizations')), before)
        self.assertEqual(self.h.rows('improvement_operations'), [])

    async def test_consent_authorize_revoke_distinct_generations_and_cold_live_denial(self):
        consent = await self.control('compose-authorize')
        self.assertEqual(consent['experiment_generation'], self.generation)
        self.assertEqual(consent['generation'], 1)
        cold = ComposePermissions.from_existing(self.assets)
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Cold cannot decrypt')):
            self.assertEqual(cold.get(self.owner, consent['authorization_id']), consent)
            with self.assertRaises(PermissionError):
                cold.preview(self.owner, self.experiment, expected_generation=self.generation, event_key='cold-cannot-preview')
            with self.assertRaises(PermissionError):
                cold.authorize(self.owner, self.experiment, expected_generation=self.generation, event_key='cold-cannot-authorize')
            with closing(self.h.store._conn()) as connection, self.assertRaises(PermissionError):
                cold.current(connection, self.owner, consent['authorization_id'])
            self.assets.set_policy(self.owner, 'off', expected_version=0, event_key='facade-off-before-revoke')
            revoked = await self.control('compose-revoke', authorization_id=consent['authorization_id'],
                expected_generation=1, event_key='owner-revoke-compose-facade')
            self.assertEqual((revoked['generation'], revoked['status']), (2, 'revoked'))
            self.assertEqual(await self.control('compose-revoke', authorization_id=consent['authorization_id'],
                expected_generation=1, event_key='owner-revoke-compose-facade'), revoked)
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Consent retry cannot decrypt')):
            replay = await self.control('compose-authorize')
        self.assertEqual((replay['generation'], replay['status']), (2, 'revoked'))
        self.assertEqual(cold.get(self.owner, consent['authorization_id'])['status'], 'revoked')

    async def test_foreign_authorization_path_or_brain_fails_before_native(self):
        with patch('improvement_operation_adapter.ClaudeOperationAdapter.verify', side_effect=AssertionError('Foreign scope cannot probe')):
            with self.assertRaises(PermissionError):
                await self.service.workflow(self.owner, 'foreign-experiment', 'compose',
                    self.payload(authorization_id=self.saved['authorization_id']))
            with self.assertRaises(PermissionError):
                await self.service.workflow(self.h.f.f.f.host_files.other, self.experiment, 'compose',
                    self.payload(authorization_id=self.saved['authorization_id']))
            with self.assertRaises(PermissionError):
                await self.service.workflow(self.owner, 'foreign-experiment', 'compose-revoke',
                    self.payload(authorization_id=self.saved['authorization_id'], expected_generation=1))
        self.assertEqual(self.h.rows('improvement_operations'), [])
        self.h.f.assert_no_new_call()

    async def test_actual_publication_same_event_join_one_compose_and_stopped_cold_replay(self):
        self.synthetic_native()
        self.h.raw = json.dumps(self.h.output(), ensure_ascii=False)
        arguments = {'authorization_id': self.saved['authorization_id']}
        first, second = await asyncio.gather(self.control('compose', **arguments), self.control('compose', **arguments))
        self.assertEqual(first, second)
        self.assertEqual(first['status'], 'candidate_staged')
        self.assertEqual(self.h.queries, 1)
        with self.assertRaises((PermissionError, ValueError, IM.ConflictError)):
            await self.control('compose', **arguments, event_key='different-owner-compose-event')
        current = self.service.records.get(self.owner, self.experiment)
        stopped = await self.service.cancel(self.owner, self.experiment, expected_generation=current['generation'], event_key='stop-facade-after-compose')
        self.assertEqual(stopped['current']['phase'], 'cancelled')
        self.assets.set_policy(self.owner, 'off', expected_version=0, event_key='cold-facade-off-after-compose')
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Stopped history cannot decrypt')), \
                patch.object(self.service.plans.host, '_snapshot_observe', side_effect=AssertionError('Stopped history cannot observe')):
            self.assertEqual(await self.control('compose', **arguments), first)
        self.assertEqual(self.h.queries, 1)

    async def test_default_unknown_publication_is_closed_through_facade(self):
        self.synthetic_native(qualified=False)
        try:
            result = await self.control('compose', authorization_id=self.saved['authorization_id'])
        except (PermissionError, ValueError, IM.ConflictError):
            result = None
        if result is not None:
            self.assertEqual(result['status'], 'native_incomplete')
        self.h.assert_no_composition()
        self.assertEqual(self.h.queries, 1)

    async def test_false_native_capability_creates_zero_operations_or_calls(self):
        with patch('improvement_native_formats.input_version', return_value=2), \
                patch('improvement_operation_adapter.ClaudeOperationAdapter.verify', return_value={'supported': False}):
            with self.assertRaisesRegex(ValueError, 'operation_native_unavailable'):
                await self.control('compose', authorization_id=self.saved['authorization_id'])
        self.assertEqual(self.h.rows('improvement_operations'), [])
        self.h.f.assert_no_new_call()

    async def test_interrupted_start_replays_after_stop_without_redispatch(self):
        self.synthetic_native()
        payload = {'authorization_id': self.saved['authorization_id'], 'expected_generation': self.generation}
        begun = await asyncio.to_thread(self.service.composer._begin, self.owner, payload, 'owner-compose-facade')
        self.assertIn('operation_id', begun)
        current = self.service.records.get(self.owner, self.experiment)
        result = await self.service.cancel(self.owner, self.experiment, expected_generation=current['generation'],
            event_key='cancel-interrupted-start')
        self.assertEqual(result['current']['phase'], 'cancelled')
        with patch.object(self.assets.blobs, 'read', side_effect=AssertionError('Interrupted replay cannot decrypt')), \
                patch('improvement_operation_adapter.ClaudeOperationAdapter.verify', side_effect=AssertionError('Replay cannot verify')):
            replay = await self.control('compose', authorization_id=self.saved['authorization_id'])
        self.assertEqual(replay['status'], 'operation_recorded')
        self.assertEqual(replay['operation_id'], begun['operation_id'])
        self.assertEqual(replay['operation_status'], 'cancelled')
        self.assertEqual(self.h.queries, 0)

    async def test_stop_drains_blocked_preview_and_refuses_its_late_metadata(self):
        entered, release = threading.Event(), threading.Event()
        original = self.service.composer.permissions.inputs.build
        def slow(*args, **kwargs):
            result = original(*args, **kwargs)
            entered.set()
            if not release.wait(15):
                raise AssertionError('Test did not release preview')
            return result
        with patch.object(self.service.composer.permissions.inputs, 'build', side_effect=slow):
            pending = asyncio.create_task(self.control('compose-preview'))
            self.assertTrue(await asyncio.to_thread(entered.wait, 10))
            current = self.service.records.get(self.owner, self.experiment)
            stopping = asyncio.create_task(self.service.cancel(self.owner, self.experiment,
                expected_generation=current['generation'], event_key='stop-blocked-preview'))
            for _ in range(100):
                if self.service.records.get(self.owner, self.experiment)['phase'] == 'stopping':
                    break
                await asyncio.sleep(0.01)
            self.assertFalse(stopping.done())
            release.set()
            outcome, = await asyncio.gather(pending, return_exceptions=True)
            self.assertIsInstance(outcome, (PermissionError, IM.ConflictError))
            self.assertEqual((await stopping)['current']['phase'], 'cancelled')
        self.assertEqual(self.h.rows('improvement_operations'), [])

    async def test_stop_drains_direct_composer_authorization_scope_before_operation_exists(self):
        self.synthetic_native()
        entered, release = threading.Event(), threading.Event()
        original = self.service.composer.permissions.current
        def slow(*args, **kwargs):
            result = original(*args, **kwargs)
            entered.set()
            if not release.wait(15):
                raise AssertionError('Test did not release composer admission')
            return result
        finish_entered = threading.Event()
        finish_stop = self.service._finish_stop
        def finishing(*args, **kwargs):
            finish_entered.set()
            return finish_stop(*args, **kwargs)
        with patch.object(self.service.composer.permissions, 'current', side_effect=slow), \
                patch.object(self.service, '_finish_stop', side_effect=finishing):
            pending = asyncio.create_task(self.service.composer.compose(self.owner, self.saved['authorization_id'],
                expected_generation=self.generation, event_key='direct-composer-owned-scope'))
            self.assertTrue(await asyncio.to_thread(entered.wait, 10))
            current = self.service.records.get(self.owner, self.experiment)
            stopping = asyncio.create_task(self.service.cancel(self.owner, self.experiment,
                expected_generation=current['generation'], event_key='stop-direct-composer-scope'))
            drained_before_release = await asyncio.to_thread(finish_entered.wait, 2)
            release.set()
            outcome, = await asyncio.gather(pending, return_exceptions=True)
            self.assertIsInstance(outcome, (PermissionError, IM.ConflictError))
            self.assertEqual((await stopping)['current']['phase'], 'cancelled')
            self.assertFalse(drained_before_release, 'Stop must map authorization scope and retain admission ownership')
        self.assertEqual(self.h.rows('improvement_operations'), [])
        self.h.f.assert_no_new_call()

    async def test_close_during_slow_authorize_cannot_create_a_late_grant(self):
        entered, release = threading.Event(), threading.Event()
        original = self.service.composer.permissions.inputs.build
        before = len(self.h.rows('improvement_compose_authorizations'))
        def slow(*args, **kwargs):
            result = original(*args, **kwargs)
            entered.set()
            if not release.wait(15):
                raise AssertionError('Test did not release consent build')
            return result
        with patch.object(self.service.composer.permissions.inputs, 'build', side_effect=slow):
            pending = asyncio.create_task(self.control('compose-authorize'))
            self.assertTrue(await asyncio.to_thread(entered.wait, 10))
            closing = asyncio.create_task(self.service.close())
            await asyncio.sleep(0.05)
            self.assertFalse(closing.done())
            release.set()
            outcome, = await asyncio.gather(pending, return_exceptions=True)
            await closing
            self.assertIsInstance(outcome, RuntimeError)
        self.assertEqual(len(self.h.rows('improvement_compose_authorizations')), before,
            'Closing a live owner cannot commit consent from its drained worker')

    async def test_close_during_final_consent_source_fence_rolls_back_inserted_grant(self):
        inserted, entered, release = threading.Event(), threading.Event(), threading.Event()
        before = len(self.h.rows('improvement_compose_authorizations'))
        permissions = self.service.composer.permissions
        original_event, original_fence = self.assets._event, permissions._fence
        def event(connection, principal, key, operation, payload, result):
            original_event(connection, principal, key, operation, payload, result)
            if operation == 'compose_authorize':
                inserted.set()
        def fence(*args, **kwargs):
            result = original_fence(*args, **kwargs)
            if inserted.is_set():
                entered.set()
                if not release.wait(15):
                    raise AssertionError('Test did not release final consent fence')
            return result
        with patch.object(self.assets, '_event', side_effect=event), patch.object(permissions, '_fence', side_effect=fence):
            pending = asyncio.create_task(self.control('compose-authorize'))
            self.assertTrue(await asyncio.to_thread(entered.wait, 10))
            closing = asyncio.create_task(self.service.close())
            await asyncio.sleep(0.05)
            self.assertFalse(closing.done())
            release.set()
            outcome, = await asyncio.gather(pending, return_exceptions=True)
            await closing
            self.assertIsInstance(outcome, RuntimeError)
        self.assertEqual(len(self.h.rows('improvement_compose_authorizations')), before,
            'Final source/current revalidation must recheck concrete owner lifetime before committing consent')

    async def test_stop_cancels_actual_slow_native_task_and_drains_adapter(self):
        self.synthetic_native()
        entered = asyncio.Event()
        original = self.service.operation_tasks.runner.adapter_factory
        def blocking(pin, *, workspace, before_engine_start):
            inner = original(pin, workspace=workspace, before_engine_start=before_engine_start)
            class Adapter:
                def verify(self):
                    return inner.verify()
                async def execute(self, request, receipt, *, on_closing_observations=None):
                    async with aclosing(inner.execute(request, receipt, on_closing_observations=on_closing_observations)) as packets:
                        async for packet in packets:
                            yield packet
                            if packet['body']['type'] == 'worker_ready':
                                entered.set()
                                await asyncio.Future()
            return Adapter()
        self.service.operation_tasks.runner.adapter_factory = blocking
        pending = asyncio.create_task(self.control('compose', authorization_id=self.saved['authorization_id']))
        await asyncio.wait_for(entered.wait(), 20)
        current = self.service.records.get(self.owner, self.experiment)
        stopped = await self.service.cancel(self.owner, self.experiment, expected_generation=current['generation'],
            event_key='stop-slow-native-composer')
        await asyncio.gather(pending, return_exceptions=True)
        self.assertEqual(stopped['current']['phase'], 'cancelled')
        self.assertEqual(self.h.adapter_closes, 1)
        self.assertEqual(self.service.operation_tasks._tasks, {})
        self.assertEqual(self.h.rows('improvement_operations')[0]['status'], 'cancelled')
        self.h.assert_no_composition()

    async def test_stop_waits_for_late_publication_thread_and_prevents_composition(self):
        self.synthetic_native()
        entered, release, finishing = threading.Event(), threading.Event(), threading.Event()
        original, finish_stop = self.service.composer._publish, self.service._finish_stop
        def slow(*args, **kwargs):
            entered.set()
            if not release.wait(20):
                raise AssertionError('Test did not release publication')
            return original(*args, **kwargs)
        def finish(*args, **kwargs):
            finishing.set()
            return finish_stop(*args, **kwargs)
        with patch.object(self.service.composer, '_publish', side_effect=slow), \
                patch.object(self.service, '_finish_stop', side_effect=finish):
            pending = asyncio.create_task(self.control('compose', authorization_id=self.saved['authorization_id']))
            self.assertTrue(await asyncio.to_thread(entered.wait, 30))
            current = self.service.records.get(self.owner, self.experiment)
            stopping = asyncio.create_task(self.service.cancel(self.owner, self.experiment,
                expected_generation=current['generation'], event_key='stop-late-compose-publication'))
            finished_early = await asyncio.to_thread(finishing.wait, 1)
            release.set()
            outcome, = await asyncio.gather(pending, return_exceptions=True)
            self.assertIsInstance(outcome, (PermissionError, IM.ConflictError))
            self.assertEqual((await stopping)['current']['phase'], 'cancelled')
            self.assertFalse(finished_early)
        self.h.assert_no_composition()
        self.assertEqual(self.h.queries, 1)

    async def test_close_drains_preview_thread_and_refuses_late_result(self):
        entered, release = threading.Event(), threading.Event()
        original = self.service.composer.permissions.inputs.build
        def slow(*args, **kwargs):
            entered.set()
            if not release.wait(15):
                raise AssertionError('Test did not release preview thread')
            return original(*args, **kwargs)
        with patch.object(self.service.composer.permissions.inputs, 'build', side_effect=slow):
            pending = asyncio.create_task(self.control('compose-preview'))
            self.assertTrue(await asyncio.to_thread(entered.wait, 10))
            closing = asyncio.create_task(self.service.close())
            await asyncio.sleep(0.05)
            self.assertFalse(closing.done(), 'Owner must drain the blocked preview')
            release.set()
            result = await asyncio.gather(pending, return_exceptions=True)
            await closing
            self.assertIsInstance(result[0], RuntimeError, 'Closed owner cannot return late preview')
        self.assertTrue(self.service.composer._closed)


if __name__ == '__main__':
    unittest.main()
