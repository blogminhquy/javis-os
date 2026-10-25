"""Actual baseline worker/parent routes, engineering seams; no native child."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import copy
import hashlib
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import improvement_claude as claude
import improvement_worker as worker
from improvement_store import _hash
from improvement_sandbox import TrialWorkspace, trial_system_prompt, worker_environment
import test_improvement_startup2_routes as routes
import test_improvement_trial_profile5 as profile_fixture
import test_improvement_trial_profile4 as view_fixture
import test_improvement_native_parent as parent_fixture
import test_improvement_native_trace_checks as captures


class BaselineWorkerTests(unittest.TestCase):
    setUp = routes.StartupRoutesTests.setUp

    def payload(self):
        fixture = profile_fixture.TrialProfileFiveTests()
        profile, _, _, receipt = fixture.installation()
        self.addCleanup(fixture.doCleanups)
        return {'version': 1, 'config_pin': profile.pin,
            'workspace_root': str(Path(receipt['path']).parents[1]), 'receipt': receipt,
            'capability_hash': 'c' * 64}

    def execute(self):
        payload = self.payload()
        packet = routes.wire.startup('trial'); packet['request'] = payload
        session = routes.EngineeringSession(packet, namespace='trial')
        test = self

        class Engine:
            def __init__(self, **kwargs):
                self.cwd, self.session_id = kwargs['cwd'], None
                self._on_stderr = lambda _: None
            async def query(self, prompt):
                options = self.trial_profile.options(self)
                test.assertEqual(options.allowed_tools, ['mcp__fixture__fixture_read'])
                test.assertEqual(set(options.mcp_servers), {'fixture'})
                test.assertEqual(self.trial_profile._native_binding.arguments['query_policy']['tool_policy'], 'baseline_inline')
                await self.trial_profile.before_query()
                routes.EngineeringSession.order.append('user_query')
                yield {'type': 'artifact', 'content': 'Baseline output\r\n'}

        async def run():
            await session.adopt()
            await worker.run_request(payload, AsyncMock(side_effect=AssertionError('foreign ACK')),
                AsyncMock(side_effect=AssertionError('foreign emit')), engine_factory=Engine, native_session=session)
        with patch.object(routes.native, 'NativeWorkerSessionV2', routes.EngineeringSession), \
                patch.object(claude, 'ClaudeTrialAdapter', routes.EngineeringAdapter), \
                patch('improvement_native_profile.NativeProfileBinding', view_fixture.EngineeringBinding), \
                patch.object(worker, '_sdk_hidden_processes', side_effect=AssertionError('legacy process shim')):
            asyncio.run(run())
        return session

    def test_actual_baseline_worker_binds_private_ack_fixture_only_and_closes_before_complete(self):
        session = self.execute(); order = routes.EngineeringSession.order
        for first, second in (('static_admission', 'guarded_preflight'), ('verified_observation', 'worker_ready'),
                ('accounting_ack', 'user_query'), ('runtime_close', 'worker_complete')):
            self.assertLess(order.index(first), order.index(second))
        self.assertEqual(session.events[-2]['event'], {'type': 'artifact', 'content': 'Baseline output\r\n'})

    def test_wrong_typed_ack_prevents_baseline_query_and_completion(self):
        routes.EngineeringSession.wrong_ack = True
        with self.assertRaisesRegex(ValueError, 'trial_engine_start_not_acknowledged'): self.execute()
        self.assertNotIn('user_query', routes.EngineeringSession.order)
        self.assertNotIn('worker_complete', routes.EngineeringSession.order)

    def test_unproven_baseline_runtime_drain_prevents_completion(self):
        routes.EngineeringSession.close_failure = True
        with self.assertRaises(OSError): self.execute()
        self.assertIn('user_query', routes.EngineeringSession.order)
        self.assertNotIn('worker_complete', routes.EngineeringSession.order)

    def test_baseline5_refuses_legacy_entry_before_unguarded_verifier(self):
        with self.assertRaisesRegex(ValueError, 'native_worker_required'):
            asyncio.run(worker.run_request(self.payload(), AsyncMock(), AsyncMock(),
                adapter_factory=routes.EngineeringAdapter,
                engine_factory=lambda **kw: self.fail('legacy engine constructed')))
        self.assertEqual(routes.EngineeringSession.order, [])


class BaselineAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_baseline_workspace_routes_exact_prompt_and_policy_without_legacy_launch(self):
        fixture = profile_fixture.TrialProfileFiveTests()
        profile, _, manifest, receipt = fixture.installation()
        self.addCleanup(fixture.doCleanups)
        pin = parent_fixture.sdk_fixture.pin()
        workspace = TrialWorkspace(Path(receipt['path']).parents[1])
        manifest['engine_config_hash'] = _hash(pin)
        receipt = workspace.prepare('baseline-route', 1, manifest)
        self.addCleanup(workspace.cleanup, 'baseline-route', 1)
        calls, marker = [], {'version': 2, 'body': {'type': 'engineering_passthrough'}}
        class Boundary:
            async def execute(self, *args, **kwargs):
                calls.append((args, kwargs)); yield marker
        async def before(): raise AssertionError('accounting moved outside host')
        async def closing(packets): pass
        adapter = claude.ClaudeTrialAdapter(pin,
            workspace_root=Path(receipt['path']).parents[1], before_engine_start=before)
        adapter._native_boundary = Boundary()
        request = {'version': 1, 'trial_id': receipt['trial_id'], 'attempt': receipt['attempt'],
            'deadline_at': time.time() + 60, 'engine_config_hash': _hash(pin), 'capability_hash': 'c' * 64}
        with patch('improvement_native_transport.execute_worker', side_effect=AssertionError('legacy launch')):
            actual = [p async for p in adapter.execute(request, receipt, on_closing_observations=closing)]
        self.assertEqual(actual, [marker]); self.assertIs(actual[0], marker)
        self.assertEqual(calls[0][0], ('trial', request, receipt))
        self.assertEqual(calls[0][1]['system_prompt'], trial_system_prompt(manifest))
        self.assertEqual(calls[0][1]['tool_policy'], 'baseline_inline')
        self.assertIs(calls[0][1]['before_engine_start'], before)
        self.assertIs(calls[0][1]['on_closing_observations'], closing)


class BaselineParentTests(unittest.IsolatedAsyncioTestCase):
    setUp = parent_fixture.NativeParentTests.setUp
    current = parent_fixture.NativeParentTests.current
    boundary = parent_fixture.NativeParentTests.boundary
    launch = parent_fixture.NativeParentTests.launch
    records = parent_fixture.NativeParentTests.records

    async def test_actual_parent_keeps_four_durable_allows_and_original_closing_callback(self):
        from improvement_native_decisions import attempt_scope, NativeImageDecisionStore
        workspace = {'trial_id': 'baseline-genuine', 'attempt': 1, 'input_hash': 'c' * 64, 'path': str(self.root)}
        request = {'deadline_at': time.time() + 60, 'capability_hash': 'd' * 64}
        joins, callbacks = [], []
        async def before(): pass
        async def closing(packets): callbacks.extend(packets)
        async def execution(kind, actual_request, receipt, **options):
            self.assertEqual(kind, 'trial'); self.assertEqual(actual_request, request)
            self.assertIs(options['before_engine_start'], before)
            self.assertEqual(options['environment'], worker_environment(self.root))
            packets = captures.trace(kind, receipt, self.pin, system_prompt='baseline system')
            # Existing trace parser is not changed in this route unit. Obtain
            # engineering joins, then bind baseline policy before actual parent
            # persistence/current checks. Result consumption is a later unit.
            result = captures.trace_checks.validate_native_trace(packets, kind=kind, receipt=receipt, pin=self.pin,
                capability_hash='d' * 64, system_prompt='baseline system', user_prompt='user', data_hash=receipt['input_hash'])
            nonces = {v['purpose']: v['nonce'] for v in options['invocations']}
            for joined in result['joins']:
                joined['launch_nonce'] = joined['image']['launch_nonce'] = options['launch_nonce']
                joined['nonce'] = joined['image']['nonce'] = nonces[joined['purpose']]
                dispatch = joined['dispatch']
                env = options['environment']
                if joined['purpose'] == 'query':
                    env = {**env, 'CLAUDE_CODE_ENTRYPOINT': 'sdk-py', 'CLAUDE_AGENT_SDK_VERSION': self.pin['sdk_version'], 'PWD': receipt['path']}
                    policy = {**captures.query_policy(kind, self.pin, receipt, 'baseline system'),
                        'tools': captures.TOOLS[:1], 'tool_policy': 'baseline_inline'}
                    dispatch['argument_consistency'].update(tools=policy['tools'], tool_policy='baseline_inline',
                        expected_hash=_hash(policy), mcp_config_hash=_hash({'mcpServers': {'fixture': {'type': 'sdk', 'name': 'fixture'}}}))
                dispatch['environment_hash'] = _hash(env)
                joined['dispatch_hash'] = _hash(dispatch)
                image = joined['image']
                material = {k: v for k, v in image.items() if k not in ('version', 'type', 'sequence', 'observation_hash')}
                joined['observation_hash'] = image['observation_hash'] = hashlib.sha256(captures.G.canonical(material, ascii=True)).hexdigest()
                self.assertEqual((await options['persist_before_allow'](joined))['decision'], 'allow')
                joins.append(copy.deepcopy(joined))
            try: yield packets[-2]
            finally: await options['on_closing_observations']((packets[-1],))
        with patch.object(self.m, 'qualified_launch', side_effect=self.launch), \
                patch.object(self.m, 'execute_worker_v2', side_effect=execution):
            values = [p async for p in self.boundary().execute('trial', request, workspace, adapter=self.adapter,
                workspace_root=self.root, brain_id='brain-a', before_engine_start=before,
                system_prompt='baseline system', tool_policy='baseline_inline', on_closing_observations=closing)]
        self.assertEqual(values[0]['body']['type'], 'worker_complete')
        self.assertEqual(callbacks[0]['body']['type'], 'drained')
        scope = attempt_scope(kind='trial', brain_id='brain-a', receipt=workspace, config_pin=self.pin,
            capability_hash=request['capability_hash'])
        self.assertEqual(len(joins), 4)
        self.assertEqual(len([r for r in self.records() if r['operation'] == 'native_image_decision']), 4)
        for joined in joins:
            self.assertEqual(NativeImageDecisionStore(self.store).read(self.owner, joined, scope_hash=scope)['decision'], 'allow')
            with self.assertRaises(PermissionError): NativeImageDecisionStore(self.store).read(self.owner, joined, scope_hash=self.scope)

    async def test_operation_and_unknown_policy_refuse_before_admission_or_release(self):
        async def closing(packets): pass
        for kind, policy in (('operation', 'baseline_inline'), ('trial', 'fixture_only'), ('trial', 'arbitrary')):
            with self.subTest(kind=kind, policy=policy), self.assertRaisesRegex(ValueError, 'native_parent_query_policy_invalid'):
                [p async for p in self.boundary().execute(kind, {}, {}, adapter=self.adapter, workspace_root=self.root,
                    brain_id='brain-a', before_engine_start=AsyncMock(), system_prompt='system',
                    tool_policy=policy, on_closing_observations=closing)]
        self.assertEqual(self.calls, []); self.assertEqual(self.records(), [])


if __name__ == '__main__': unittest.main()
