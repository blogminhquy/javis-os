"""Completion requires actual terminal exit success; no account or SDK client."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import hashlib
import os
from pathlib import Path
import time
import unittest
from unittest.mock import patch

import test_improvement_native_transport_v2 as fixture


async def noop(*args): pass


class NativeExitStatusContractTests(unittest.IsolatedAsyncioTestCase):
    def iterator(self, worker=0, guardian=0, *, closing=None):
        self.mod = fixture.component(self)
        instances = self.instances = []
        class Session:
            def __init__(self, *args, **kwargs):
                self.closed = False
                if worker != 'missing': self._worker_exit_code = worker
                if guardian != 'missing': self._guardian_exit_code = guardian
                instances.append(self)
            async def start(self, startup): pass
            async def receive(self): return {'sequence': 1, 'body': {'type': 'worker_complete'}}
            async def aclose(self): self.closed = True
            @property
            def closing_observations(self):
                return ({'sequence': 2, 'body': {'type': 'engine_event', 'event': {
                    'type': 'usage', 'usage': {'input_tokens': 7, 'output_tokens': None}}}},)
        self.factory_patch = patch.object(self.mod, 'GuardianSessionV2', Session)
        self.factory_patch.start(); self.addCleanup(self.factory_patch.stop)
        return self.mod.execute_worker_v2('trial', {'deadline_at': time.time() + 30, 'capability_hash': 'c' * 64},
            {'trial_id': 'engineering', 'attempt': 1, 'path': r'C:\scratch'}, config_pin={},
            workspace_root=r'C:\scratch', brain_id='engineering', before_engine_start=noop,
            guardian_manifest={}, policy={}, image_policy={}, launch_nonce='1' * 64, invocations=[],
            persist_before_allow=fixture.persist, on_closing_observations=closing or noop, environment={})

    async def test_engineering_missing_bool_or_nonzero_terminal_status_refuses_after_evidence(self):
        for worker, guardian in ((7, 0), (0, 7), ('missing', 0), (0, 'missing'), (False, 0), (0, False)):
            retained = []
            async def closing(observations):
                self.assertTrue(self.instances[0].closed)
                retained.extend(observations)
            with self.subTest(worker=worker, guardian=guardian):
                iterator = self.iterator(worker, guardian, closing=closing)
                with self.assertRaisesRegex(RuntimeError, 'trial_worker_exit_failed'):
                    async for unused in iterator: pass
                self.assertEqual(retained[0]['body']['event']['usage'], {'input_tokens': 7, 'output_tokens': None})
                self.factory_patch.stop()

    async def test_engineering_exact_zero_statuses_allow_completion(self):
        iterator = self.iterator()
        packets = [packet async for packet in iterator]
        self.assertEqual(packets[0]['body']['type'], 'worker_complete')
        self.assertTrue(self.instances[0].closed)

    async def test_close_at_yielded_completion_still_refuses_nonzero_status(self):
        retained = []
        async def closing(observations): retained.extend(observations)
        iterator = self.iterator(7, closing=closing)
        self.assertEqual((await anext(iterator))['body']['type'], 'worker_complete')
        with self.assertRaisesRegex(RuntimeError, 'trial_worker_exit_failed'): await iterator.aclose()
        self.assertTrue(self.instances[0].closed)
        self.assertEqual(len(retained), 1)

    async def test_cancellation_at_completion_preserves_cancellation_priority(self):
        iterator = self.iterator(7)
        await anext(iterator)
        with self.assertRaises(asyncio.CancelledError): await iterator.athrow(asyncio.CancelledError())
        self.assertTrue(self.instances[0].closed)


@unittest.skipUnless(os.name == 'nt', 'Actual retained worker/guardian Windows exit statuses')
class NativeExitStatusWindowsTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.HostGuardianWindowsTests.asyncSetUp
    cleanup = fixture.HostGuardianWindowsTests.cleanup
    cleanup_diagnostic = fixture.HostGuardianWindowsTests.cleanup_diagnostic
    persist = fixture.HostGuardianWindowsTests.persist

    async def test_actual_complete_then_exit7_is_execution_failure_after_drain_and_closing_evidence(self):
        target = self.source / 'improvement_worker.py'
        script = fixture._WORKER_STUB.replace(
            "{'type':'engineering_marker','content':'PRIVATE_ENGINE_MARKER'}",
            "{'type':'usage','usage':{'input_tokens':7,'output_tokens':None}}")
        self.assertNotEqual(script, fixture._WORKER_STUB)
        target.write_text('SELECTED=' + repr(str(self.selected)) + '\n' + script + '\nraise SystemExit(7)\n', encoding='utf-8')
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        self.guardian['source']['files'][target.name] = digest
        self.policy['bootstrap']['source']['files'][target.name] = digest
        for name in ('.executions', '.lifetimes'): (self.root / name).mkdir()
        actual_class = self.mod.GuardianSessionV2
        def factory(*args, **kwargs):
            owner = actual_class(*args, **kwargs); self.owners.append(owner); return owner
        retained, phases = [], []
        async def closing(observations):
            phases.append('closing')
            self.assertTrue(self.owners[0].closed)
            self.assertTrue(self.owners[0].native_drained)
            retained.extend(observations)
        receipt = {**self.identity, 'path': str(self.scratch)}
        iterator = self.mod.execute_worker_v2('trial', {'deadline_at': time.time() + 30, 'capability_hash': 'c' * 64},
            receipt, config_pin=self.startup['request']['config_pin'], workspace_root=str(self.root),
            brain_id='engineering', before_engine_start=noop, guardian_manifest=self.guardian, policy=self.policy,
            image_policy=self.options['image_policy'], launch_nonce=self.options['launch_nonce'],
            invocations=self.invocations, persist_before_allow=self.persist, on_closing_observations=closing,
            environment=self.startup['environment'], timeout=12, close_timeout=8)
        caught = None
        with patch.object(self.mod, 'GuardianSessionV2', side_effect=factory):
            try:
                async for packet in iterator: self.packets.append(packet)
            except RuntimeError as error: caught = error; phases.append('error')
        self.assertEqual(len(self.owners), 1)
        owner = self.owners[0]
        self.assertTrue(owner.closed); self.assertTrue(owner.native_drained)
        self.assertEqual((owner._worker_exit_code, owner._guardian_exit_code), (7, 0))
        self.assertTrue(any(packet['body']['type'] == 'worker_complete' for packet in self.packets))
        usages = [packet['body']['event']['usage'] for packet in (*self.packets, *retained)
                  if packet['body']['type'] == 'engine_event' and packet['body']['event']['type'] == 'usage']
        self.assertEqual(usages, [{'input_tokens': 7, 'output_tokens': None}])
        self.assertTrue(all(not Path(path + '.native').exists() or not any(Path(path + '.native').iterdir())
                            for path in owner._fences))
        print('ACTUAL_EXIT_STATUS', owner._worker_exit_code, owner._guardian_exit_code,
              'closed', owner.closed, 'drained', owner.native_drained, 'usage', usages, 'phases', phases)
        self.assertIsNotNone(caught, 'worker_complete followed by actual exit7 was incorrectly successful')
        self.assertNotIsInstance(caught, self.mod.GuardianSessionV2CleanupError)
        self.assertEqual(str(caught), 'trial_worker_exit_failed')
        self.assertEqual(phases, ['closing', 'error'])


if __name__ == '__main__': unittest.main()
