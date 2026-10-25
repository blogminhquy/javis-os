"""Actual M0 owners with engineering guardian/release seams; no native child."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import copy
import hashlib
import importlib
import importlib.util
import json
import subprocess
import sys
import time
import unittest
from contextlib import closing
from unittest.mock import patch

import test_improvement_native_decision_store as fixture
import test_improvement_native_sdk as sdk_fixture
import improvement_store as IM
from improvement_native_protocol import _canonical


class NativeParentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        fixture.fixture.ImprovementStoreTests.setUp(self)
        IM.ensure(self.rs)
        self.assertIsNotNone(importlib.util.find_spec('improvement_native_parent'), 'actual parent native boundary missing')
        self.m = importlib.import_module('improvement_native_parent')
        self.pin = sdk_fixture.pin()
        self.calls, self.owners = [], []
        self.scope = '9' * 64
        self.admitted, self.worker_exit, self.guardian_exit = True, 0, 0
        self.mutator = None
        self.block_receive = False
        self.receiving, self.closing, self.release_close = asyncio.Event(), asyncio.Event(), asyncio.Event()
        self.release_close.set()
        test = self

        class Adapter:
            def admit_preflight(self):
                test.calls.append('admission')
                return {'admitted': test.admitted, 'reason': 'unqualified' if not test.admitted else None}

            def verify_observed(self, value):
                test.calls.append('verified')
                test.assertTrue(test.owners[-1].closed)
                test.assertEqual(value, {'engineering': 'actual observation seam'})
                return {'supported': True, 'capability_hash': 'c' * 64}

        self.adapter = Adapter()

        class Guardian:
            def __init__(self, guardian_manifest, policy, **options):
                self.policy, self.options = policy, options
                self.closed = False
                self._worker_exit_code, self._guardian_exit_code = test.worker_exit, test.guardian_exit
                test.owners.append(self)

            async def start(self, startup):
                test.calls.append('start')
                self.startup = copy.deepcopy(startup)
                test.assertEqual(startup['kind'], 'preflight')
                test.assertEqual(startup['request'], {'version': 1, 'config_pin': test.pin})
                for invocation in self.options['invocations']:
                    value = fixture.joined()
                    value['launch_nonce'] = value['image']['launch_nonce'] = self.options['launch_nonce']
                    purpose, nonce = invocation['purpose'], invocation['nonce']
                    value['purpose'] = value['image']['purpose'] = purpose
                    value['nonce'] = value['image']['nonce'] = nonce
                    value['image']['comparison']['actual']['sha256'] = test.pin['cli_hash']
                    value['image']['comparison']['selected']['sha256'] = test.pin['cli_hash']
                    image = value['image']
                    material = {key: item for key, item in image.items() if key not in
                        ('version', 'type', 'sequence', 'observation_hash')}
                    value['observation_hash'] = image['observation_hash'] = hashlib.sha256(
                        json.dumps(material, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
                    argv = [test.pin['cli_path'], *(['--version'] if purpose == 'adapter_version' else ['auth', 'status', '--json'])]
                    command = subprocess.list2cmdline(argv)
                    value['dispatch'] = {'version': 1, 'purpose': purpose, 'basis': 'native_argument_consistency',
                        'environment_hash': IM._hash(startup['environment']), 'source_policy_hash': test.pin['profile_hash'],
                        'argument_consistency': {'version': 1, 'argv_hash': IM._hash(argv),
                            'command_line_hash': hashlib.sha256(command.encode()).hexdigest(),
                            'cwd_hash': hashlib.sha256(self.policy['scratch'].encode()).hexdigest(), 'creationflags': 0x08000006}}
                    value['dispatch_hash'] = IM._hash(value['dispatch'])
                    if test.mutator is not None: test.mutator(value)
                    response = await self.options['persist_before_allow'](value)
                    test.assertEqual(response['decision'], 'allow')

            async def receive(self):
                test.receiving.set()
                if test.block_receive: await asyncio.Event().wait()
                return {'version': 2, 'sequence': 1, 'body': {'type': 'preflight_complete',
                    'runtime': {'engineering': 'actual observation seam'}}}

            @property
            def closing_observations(self):
                return ({'version': 2, 'sequence': 2, 'body': {'type': 'drained', 'engineering': True}},)

            async def aclose(self):
                test.closing.set()
                await test.release_close.wait()
                test.calls.append('closed')
                self.closed = True

        self.guardian = Guardian

    def current(self, connection, joined):
        self.calls.append('current')
        if self.store._policy(connection, 'brain-a') != {'mode': 'suggest', 'version': 0}:
            raise IM.ConflictError('current_policy_changed')
        return 'allow'

    def boundary(self):
        return self.m.NativeParentBoundary(self.pin, self.store, self.owner,
            scope_hash=self.scope, current=self.current)

    def launch(self, pin, *, kind, scratch):
        self.calls.append('release')
        self.assertEqual(pin, self.pin)
        return {'guardian_manifest': {'engineering': True}, 'policy': {'scratch': str(scratch)},
            'image_policy': {'version': 1, 'path': self.pin['cli_path'], 'sha256': self.pin['cli_hash']},
            'release_fingerprint': 'd' * 64, 'qualification_hash': 'e' * 64}

    async def verify(self):
        with patch.object(self.m, 'qualified_launch', side_effect=self.launch), \
             patch.object(self.m, 'GuardianSessionV2', self.guardian):
            return await self.boundary().verify(self.adapter)

    def records(self):
        with closing(self.rs._conn()) as connection:
            return [dict(row) for row in connection.execute('SELECT * FROM improvement_events')]

    async def test_static_admission_refuses_before_release_observation_or_guardian(self):
        self.admitted = False
        result = await self.verify()
        self.assertFalse(result['supported'])
        self.assertEqual(self.calls, ['admission'])
        self.assertEqual(self.owners, [])
        self.assertEqual(self.records(), [])

    async def test_guarded_preflight_persists_two_actual_encrypted_decisions_and_closes_before_verify(self):
        result = await self.verify()
        self.assertTrue(result['supported'])
        self.assertEqual(self.calls[:4], ['admission', 'release', 'current', 'start'])
        self.assertEqual(self.calls[-2:], ['closed', 'verified'])
        self.assertEqual(len([row for row in self.records() if row['operation'] == 'native_image_decision']), 2)
        self.assertEqual(len([row for row in self.records() if row['operation'] == 'native_preflight_evidence']), 1)
        self.assertTrue(self.owners[0].closed)

    async def test_preflight_complete_followed_by_exit7_refuses_after_durable_closing_evidence(self):
        self.worker_exit = 7
        with self.assertRaisesRegex(RuntimeError, 'native_preflight_exit_failed'):
            await self.verify()
        self.assertTrue(self.owners[0].closed)
        self.assertNotIn('verified', self.calls)
        record = next(row for row in self.records() if row['operation'] == 'native_preflight_evidence')
        saved = json.loads(record['result_json'])
        raw = b''.join(self.blobs.read('brain-a', digest) for digest in saved['blob_hashes'])
        trace = json.loads(raw)
        self.assertEqual([packet['body']['type'] for packet in trace], ['preflight_complete', 'drained'])

    async def test_captured_environment_drift_never_gets_durable_allow(self):
        def drift(value):
            value['dispatch']['environment_hash'] = '0' * 64
            value['dispatch_hash'] = IM._hash(value['dispatch'])
        self.mutator = drift
        with self.assertRaisesRegex(ValueError, 'native_parent_dispatch_drift'):
            await self.verify()
        self.assertTrue(self.owners[0].closed)
        self.assertNotIn('verified', self.calls)
        self.assertEqual([row['operation'] for row in self.records()], ['native_preflight_evidence'])

    async def test_actual_policy_revocation_refuses_before_guardian_start(self):
        self.store.set_policy(self.owner, 'off', expected_version=0, event_key='policy-revoked-before-native')
        with self.assertRaisesRegex(IM.ConflictError, 'current_policy_changed'): await self.verify()
        self.assertEqual(self.owners, [])
        self.assertNotIn('start', self.calls)

    async def test_repeated_cancellation_retains_close_and_encrypted_closing_evidence(self):
        self.block_receive = True
        self.release_close.clear()
        task = asyncio.create_task(self.verify())
        try:
            await asyncio.wait_for(self.receiving.wait(), 3)
            task.cancel()
            await asyncio.wait_for(self.closing.wait(), 3)
            task.cancel()
            await asyncio.sleep(0)
            self.assertFalse(task.done())
        finally:
            self.release_close.set()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertTrue(self.owners[0].closed)
        self.assertNotIn('verified', self.calls)
        self.assertEqual(len([row for row in self.records() if row['operation'] == 'native_preflight_evidence']), 1)

    async def test_query_parent_persists_all_four_images_in_full_attempt_scope_and_keeps_closing_callback(self):
        import test_improvement_native_trace_checks as captures
        from improvement_native_decisions import attempt_scope, NativeImageDecisionStore
        from improvement_sandbox import worker_environment
        joins, callbacks = [], []
        workspace = {'trial_id': 'genuine-trial', 'attempt': 1, 'input_hash': 'c' * 64, 'path': str(self.root)}
        request = {'deadline_at': time.time() + 60, 'capability_hash': 'd' * 64}
        boundary = self.boundary()

        async def before(): pass
        async def closed(packets): callbacks.extend(packets)

        async def execution(kind, actual_request, receipt, **options):
            self.assertEqual(actual_request, request)
            self.assertEqual(options['environment'], worker_environment(self.root))
            self.assertIs(options['before_engine_start'], before)
            self.assertEqual([item['purpose'] for item in options['invocations']], list(captures.PURPOSES))
            packets = captures.trace(kind, receipt, self.pin, system_prompt='system')
            nonces = {item['purpose']: item['nonce'] for item in options['invocations']}
            for packet in packets:
                packet['launch_nonce'] = options['launch_nonce']
                body = packet['body']
                if body['type'] == 'launch_offer': body['images'] = copy.deepcopy(options['invocations'])
                if body['type'] in ('dispatch_observed', 'image_observed'):
                    body['nonce'] = nonces[body['purpose']]
                if body['type'] == 'dispatch_observed':
                    actual_environment = (options['environment'] if body['purpose'] != 'query' else
                        {**options['environment'], 'CLAUDE_CODE_ENTRYPOINT': 'sdk-py',
                         'CLAUDE_AGENT_SDK_VERSION': self.pin['sdk_version'], 'PWD': receipt['path']})
                    body['dispatch']['environment_hash'] = IM._hash(actual_environment)
                    body['dispatch_hash'] = IM._hash(body['dispatch'])
                if body['type'] == 'image_observed':
                    material = {key: packet[key] for key in ('launch_nonce', 'worker_pid', 'worker_birth')}
                    material.update({key: value for key, value in body.items() if key not in ('type', 'observation_hash')})
                    body['observation_hash'] = hashlib.sha256(json.dumps(material, sort_keys=True,
                        separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
            result = captures.trace_checks.validate_native_trace(packets, kind=kind, receipt=receipt, pin=self.pin,
                capability_hash='d' * 64, system_prompt='system', user_prompt='user', data_hash=receipt['input_hash'])
            for joined in result['joins']:
                joins.append(joined)
                self.assertEqual((await options['persist_before_allow'](joined))['decision'], 'allow')
            try:
                yield packets[-2]
            finally:
                await options['on_closing_observations']((packets[-1],))

        with patch.object(self.m, 'qualified_launch', side_effect=self.launch), \
             patch.object(self.m, 'execute_worker_v2', side_effect=execution):
            values = [value async for value in boundary.execute('trial', request, workspace, adapter=self.adapter,
                workspace_root=self.root, brain_id='brain-a', before_engine_start=before,
                system_prompt='system', tool_policy='pinned_skill', on_closing_observations=closed)]
        self.assertEqual(values[0]['body']['type'], 'worker_complete')
        self.assertEqual(callbacks[0]['body']['type'], 'drained')
        scope = attempt_scope(kind='trial', brain_id='brain-a', receipt=workspace, config_pin=self.pin,
                              capability_hash=request['capability_hash'])
        self.assertNotEqual(scope, self.scope)
        reader = NativeImageDecisionStore(self.store)
        self.assertEqual(len(joins), 4)
        for joined in joins:
            self.assertEqual(reader.read(self.owner, joined, scope_hash=scope)['decision'], 'allow')
            with self.assertRaises(PermissionError): reader.read(self.owner, joined, scope_hash=self.scope)


class NativeAdapterBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        fixture.fixture.ImprovementStoreTests.setUp(self)
        IM.ensure(self.rs)
        self.pin = sdk_fixture.pin()

    async def test_new_registered_boundary_profile_cannot_choose_unbound_legacy_verifier(self):
        from improvement_claude import ClaudeTrialAdapter
        import improvement_native_qualifications as registrations
        prefix = (sys.platform, self.pin['cli_version'], self.pin['cli_hash'], self.pin['sdk_version'],
                  self.pin['profile_version'], self.pin['profile_hash'])
        with patch.object(registrations, 'REVIEWED_RELEASES', {(*prefix, 'a' * 64): 'b' * 64}):
            adapter = ClaudeTrialAdapter(self.pin)
            with patch.object(adapter, '_verify_with_observer', side_effect=AssertionError('legacy observer selected')):
                result = adapter.verify()
        self.assertFalse(result['supported'])
        self.assertEqual(result['reason'], 'native_host_authority_unbound')

    async def test_actual_both_adapters_bind_same_loop_guarded_preflight_without_legacy_probe(self):
        from improvement_claude import ClaudeTrialAdapter
        from improvement_operation_adapter import ClaudeOperationAdapter
        instances, observed = [], []
        loop = asyncio.get_running_loop()

        class Boundary:
            def __init__(self, pin, assets, principal, **kwargs):
                instances.append((pin, assets, principal, kwargs))
            async def verify(self, adapter):
                observed.append((asyncio.get_running_loop(), adapter.pin))
                return {'supported': True, 'capability_hash': 'c' * 64}

        import improvement_native_parent as parent
        current = lambda connection, value: 'allow'
        lock = asyncio.Lock()
        for adapter in (ClaudeTrialAdapter(self.pin), ClaudeOperationAdapter(self.pin)):
            with patch.object(parent, 'NativeParentBoundary', Boundary), \
                 patch('improvement_claude._runtime_observation', side_effect=AssertionError('unguarded probe')):
                adapter.bind_native_authority(self.store, self.owner, scope_hash='9' * 64, current=current, lock=lock)
                result = await adapter.verify_async()
                self.assertTrue(result['supported'])
                with self.assertRaisesRegex(RuntimeError, 'native_sync_preflight_in_async_context'):
                    adapter.verify()
        self.assertEqual(observed, [(loop, self.pin), (loop, self.pin)])
        self.assertEqual(len(instances), 2)
        self.assertTrue(all(value[1] is self.store and value[2] is self.owner and value[3]['lock'] is lock
                            for value in instances))

    async def test_actual_prepared_new_inputs_reach_parent_and_bound_old_inputs_refuse_legacy_launch(self):
        from improvement_claude import ClaudeTrialAdapter
        from improvement_operation_adapter import ClaudeOperationAdapter
        from improvement_sandbox import trial_system_prompt
        from improvement_operation_profile import operation_system_prompt
        import test_improvement_operation_workspace as workspace_fixture
        import test_improvement_read_outcome_broker as manifest_fixture
        setup = workspace_fixture.OperationWorkspaceTests(); setup.setUp()
        self.addCleanup(setup.doCleanups)
        observed = []
        marker = {'version': 2, 'body': {'type': 'engineering_passthrough'}}

        class Boundary:
            async def execute(self, kind, request, receipt, **kwargs):
                observed.append((kind, request, receipt, kwargs))
                yield marker

        async def before(): raise AssertionError('adapter moved accounting outside host')
        async def closing(packets): pass
        for kind in ('trial', 'operation'):
            for modern in (True, False):
                if kind == 'trial':
                    manifest = manifest_fixture.manifest(4 if modern else 1)
                    if not modern: manifest.pop('effective_view')
                    manifest['engine_config_hash'] = IM._hash(self.pin)
                    workspace = setup.barrier
                    identifier = 'new-trial' if modern else 'old-trial'
                    receipt = workspace.prepare(identifier, 1, manifest)
                    self.addCleanup(workspace.cleanup, identifier, 1)
                    adapter = ClaudeTrialAdapter(self.pin, workspace_root=workspace.root, before_engine_start=before)
                    adapter._native_boundary = Boundary()
                    expected_prompt, expected_policy = trial_system_prompt(manifest), 'pinned_skill'
                else:
                    manifest = workspace_fixture.materialization()
                    manifest.update(version=2 if modern else 1, engine_config_hash=IM._hash(self.pin))
                    workspace = setup.workspace()
                    identifier = 'operation-1'
                    receipt = workspace.prepare(identifier, 1 if modern else 2, manifest)
                    self.addCleanup(workspace.cleanup_proven, identifier, receipt['attempt'], receipt)
                    adapter = ClaudeOperationAdapter(self.pin, workspace=workspace, before_engine_start=before)
                    adapter._native._native_boundary = Boundary()
                    expected_prompt, expected_policy = operation_system_prompt(manifest), 'fixture_only'
                request = {'version': 1, **{key: receipt[key] for key in
                    (('trial_id', 'attempt') if kind == 'trial' else ('operation_id', 'attempt', 'role', 'purpose'))},
                    'deadline_at': time.time() + 60, 'engine_config_hash': IM._hash(self.pin), 'capability_hash': 'c' * 64}
                with patch('improvement_native_transport.execute_worker', side_effect=AssertionError('legacy launch')):
                    if not modern:
                        with self.assertRaisesRegex(ValueError, kind + '_native_parent_legacy_input'):
                            [value async for value in adapter.execute(request, receipt, on_closing_observations=closing)]
                        continue
                    result = [value async for value in adapter.execute(request, receipt, on_closing_observations=closing)]
                self.assertEqual(result, [marker])
                self.assertIs(result[0], marker)
                actual = observed[-1]
                self.assertEqual(actual[:3], (kind, request, receipt))
                self.assertEqual(actual[3]['system_prompt'], expected_prompt)
                self.assertEqual(actual[3]['tool_policy'], expected_policy)
                self.assertIs(actual[3]['on_closing_observations'], closing)
                self.assertIs(actual[3]['before_engine_start'], before)
        self.assertEqual(len(observed), 2)


if __name__ == '__main__': unittest.main()
