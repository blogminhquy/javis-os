"""Actual worker routing/order with engineering endpoint/runtime, no native call."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import copy
import io
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

import improvement_native_worker as native
import improvement_worker as trial_worker
import improvement_operation_worker as operation_worker
import improvement_claude as claude
from improvement_native_protocol import encode_startup2
from improvement_store import _json
import test_improvement_native_protocol as wire
import test_improvement_trial_profile4 as profile_fixture
import test_improvement_operation_profile2 as operation_fixture


class EngineeringRuntime:
    async def preflight(self, *, managed_policy):
        EngineeringSession.order.append('guarded_preflight')
        if managed_policy != 'absent': raise AssertionError('unadmitted policy')
        return {'observed': 'engineering-runtime'}
    async def aclose(self):
        EngineeringSession.order.append('runtime_close')
        if EngineeringSession.close_failure: raise OSError('unproven runtime drain')


class EngineeringSession:
    order, instances, close_failure, wrong_ack = [], [], False, False
    # Ordinary startup2 sessions carry no qualification run; only startup3 sets it.
    _qualification = None
    def __init__(self, packet, *, namespace):
        self._packet, self._namespace = copy.deepcopy(packet), namespace
        self.runtime, self._adopted, self.closed, self.events = EngineeringRuntime(), False, False, []
        self.__class__.instances.append(self)
    async def adopt(self):
        self.order.append('adopt'); self._adopted = True
    async def send(self, event):
        self.order.append(event['type']); self.events.append(copy.deepcopy(event))
    async def receive(self):
        self.order.append('accounting_ack')
        receipt = self._packet['request']['receipt']
        keys = ('trial_id', 'attempt', 'input_hash') if self._namespace == 'trial' else (
            'operation_id', 'attempt', 'role', 'purpose', 'input_hash')
        identity = {key: receipt[key] for key in keys}
        if self.wrong_ack: identity['attempt'] = True
        return {'type': 'engine_start_ack', **identity}
    async def aclose(self): self.order.append('session_close'); self.closed = True


class EngineeringAdapter:
    admitted = True
    def __init__(self, pin): pass
    def admit_preflight(self):
        EngineeringSession.order.append('static_admission')
        return {'admitted': self.admitted, 'runtime': {'managed_policy': 'absent'}}
    def verify_observed(self, runtime):
        EngineeringSession.order.append('verified_observation')
        return {'supported': True, 'capability_hash': 'c' * 64, 'runtime': runtime}
    def verify(self): raise AssertionError('legacy unguarded verifier bypassed native route')


class StartupRoutesTests(unittest.TestCase):
    def setUp(self):
        EngineeringSession.order, EngineeringSession.instances = [], []
        EngineeringSession.close_failure, EngineeringSession.wrong_ack, EngineeringAdapter.admitted = False, False, True

    def runner(self):
        self.assertTrue(callable(getattr(native, 'run_startup2', None)), 'actual startup2 worker route missing')
        return native.run_startup2

    def test_fixed_mains_pass_original_bytes_and_namespace_to_new_route(self):
        for module, kind in ((trial_worker, 'trial'), (trial_worker, 'preflight'), (operation_worker, 'operation')):
            raw = encode_startup2(wire.startup(kind))
            run = AsyncMock(return_value=0)
            with self.subTest(kind=kind), patch.object(native, 'run_startup2', run, create=True), \
                    patch.object(module, 'run_request', AsyncMock(side_effect=AssertionError('legacy route used'))), \
                    patch.object(module.sys, 'stdin', SimpleNamespace(buffer=io.BytesIO(raw))), \
                    patch.object(module.sys, 'stdout', SimpleNamespace(buffer=io.BytesIO())):
                self.assertEqual(module.main(), 0)
                run.assert_awaited_once_with(raw, entrypoint='operation' if module is operation_worker else 'trial')

    def test_noncanonical_duplicate_and_cross_namespace_rejected_before_endpoint_adoption(self):
        run = self.runner()
        raw = encode_startup2(wire.startup('preflight'))
        bad = raw.replace(b'"version":2', b'"version":2,"version":2', 1)
        with patch.object(native, 'NativeWorkerSessionV2', EngineeringSession):
            for value, entrypoint in ((bad, 'trial'), (raw, 'operation'),
                    (encode_startup2(wire.startup('operation')), 'trial')):
                with self.subTest(entrypoint=entrypoint), self.assertRaises(ValueError):
                    asyncio.run(run(value, entrypoint=entrypoint))
        self.assertEqual(EngineeringSession.instances, [])

    def test_preflight_adopts_then_admits_then_verifies_and_closes_before_success(self):
        run = self.runner()
        with patch.object(native, 'NativeWorkerSessionV2', EngineeringSession), \
                patch.object(claude, 'ClaudeTrialAdapter', EngineeringAdapter):
            self.assertEqual(asyncio.run(run(encode_startup2(wire.startup('preflight')), entrypoint='trial')), 0)
        self.assertEqual(EngineeringSession.order, ['adopt', 'static_admission', 'guarded_preflight',
            'verified_observation', 'runtime_close', 'preflight_complete', 'session_close'])
        self.assertEqual(EngineeringSession.instances[0].events[0]['runtime'], {'observed': 'engineering-runtime'})

    def test_unqualified_static_admission_prevents_every_cli_and_always_closes(self):
        run = self.runner(); EngineeringAdapter.admitted = False
        with patch.object(native, 'NativeWorkerSessionV2', EngineeringSession), \
                patch.object(claude, 'ClaudeTrialAdapter', EngineeringAdapter):
            with self.assertRaises(ValueError): asyncio.run(run(encode_startup2(wire.startup('preflight')), entrypoint='trial'))
        self.assertNotIn('guarded_preflight', EngineeringSession.order)
        self.assertNotIn('preflight_complete', EngineeringSession.order)
        self.assertTrue(EngineeringSession.instances[0].closed)

    def test_runtime_close_failure_never_emits_preflight_complete(self):
        run = self.runner(); EngineeringSession.close_failure = True
        with patch.object(native, 'NativeWorkerSessionV2', EngineeringSession), \
                patch.object(claude, 'ClaudeTrialAdapter', EngineeringAdapter):
            with self.assertRaises(OSError): asyncio.run(run(encode_startup2(wire.startup('preflight')), entrypoint='trial'))
        self.assertNotIn('preflight_complete', EngineeringSession.order)
        self.assertTrue(EngineeringSession.instances[0].closed)

    def test_trial_and_operation_delegation_keeps_adopted_private_endpoint_owner(self):
        run = self.runner()
        for kind, module in (('trial', trial_worker), ('operation', operation_worker)):
            callback = AsyncMock()
            raw = encode_startup2(wire.startup(kind))
            with self.subTest(kind=kind), patch.object(native, 'NativeWorkerSessionV2', EngineeringSession), \
                    patch.object(module, 'run_request', callback):
                asyncio.run(run(raw, entrypoint=kind))
                owner = EngineeringSession.instances[-1]
                callback.assert_awaited_once_with(owner._packet['request'], owner.receive, owner.send, native_session=owner)
                self.assertTrue(owner.closed)


class NativeTrialQueryTests(unittest.TestCase):
    setUp = StartupRoutesTests.setUp
    kind, module = 'trial', trial_worker

    def payload(self):
        fixture = profile_fixture.TrialProfileFourTests()
        profile, engine, manifest, receipt = fixture.installation()
        self.addCleanup(fixture.doCleanups)
        return {'version': 1, 'config_pin': profile.pin, 'workspace_root': str(Path(receipt['path']).parents[1]),
            'receipt': receipt, 'capability_hash': 'c' * 64}

    def execute(self):
        payload = self.payload()
        packet = wire.startup(self.kind); packet['request'] = payload
        session = EngineeringSession(packet, namespace=self.kind)
        testcase = self
        class Engine:
            def __init__(self, **kwargs):
                self.cwd, self.session_id = kwargs['cwd'], None
                self._on_stderr = lambda _: None
            async def query(self, prompt):
                options = self.trial_profile.options(self)
                tools = ['mcp__fixture__fixture_read'] + (['mcp__skill__skill_asset_read'] if testcase.kind == 'trial' else [])
                testcase.assertEqual(options.allowed_tools, tools)
                testcase.assertTrue(callable(getattr(self.trial_profile, 'create_client', None)))
                await self.trial_profile.before_query()
                EngineeringSession.order.append('user_query')
                yield {'type': 'artifact', 'content': 'Exact output\r\n'}
        async def run():
            await session.adopt()
            await self.module.run_request(payload, AsyncMock(side_effect=AssertionError('foreign ACK')),
                AsyncMock(side_effect=AssertionError('foreign emit')), engine_factory=Engine, native_session=session)
        with patch.object(native, 'NativeWorkerSessionV2', EngineeringSession), \
                patch.object(claude, 'ClaudeTrialAdapter', EngineeringAdapter), \
                patch('improvement_native_profile.NativeProfileBinding', profile_fixture.EngineeringBinding), \
                patch.object(trial_worker, '_sdk_hidden_processes', side_effect=AssertionError('legacy process shim')):
            asyncio.run(run())
        return session

    def test_actual_request_uses_native_binding_private_ack_and_runtime_close_before_completion(self):
        session = self.execute()
        order = EngineeringSession.order
        self.assertLess(order.index('static_admission'), order.index('guarded_preflight'))
        self.assertLess(order.index('verified_observation'), order.index('worker_ready'))
        self.assertLess(order.index('accounting_ack'), order.index('user_query'))
        self.assertLess(order.index('runtime_close'), order.index('worker_complete'))
        self.assertEqual(session.events[-2]['event'], {'type': 'artifact', 'content': 'Exact output\r\n'})

    def test_wrong_typed_private_ack_never_queries_or_completes(self):
        EngineeringSession.wrong_ack = True
        with self.assertRaises(ValueError): self.execute()
        self.assertNotIn('user_query', EngineeringSession.order)
        self.assertNotIn('worker_complete', EngineeringSession.order)

    def test_runtime_drain_failure_after_engine_never_completes(self):
        EngineeringSession.close_failure = True
        with self.assertRaises(OSError): self.execute()
        self.assertIn('user_query', EngineeringSession.order)
        self.assertNotIn('worker_complete', EngineeringSession.order)

    def test_new_input_cannot_enter_legacy_worker_or_unguarded_verifier(self):
        payload = self.payload()
        with self.assertRaisesRegex(ValueError, 'native_worker_required'):
            asyncio.run(self.module.run_request(payload, AsyncMock(), AsyncMock(),
                adapter_factory=EngineeringAdapter, engine_factory=lambda **kwargs: self.fail('legacy engine constructed')))
        self.assertNotIn('guarded_preflight', EngineeringSession.order)


class NativeOperationQueryTests(NativeTrialQueryTests):
    kind, module = 'operation', operation_worker

    def payload(self):
        fixture = operation_fixture.OperationProfileTwoTests(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        profile, _, _, receipt = fixture.installation()
        return {'version': 1, 'config_pin': profile.config, 'workspace_root': str(profile.workspace.root),
            'receipt': receipt, 'capability_hash': 'c' * 64}


if __name__ == '__main__': unittest.main()
