"""Actual operation2 workspace/profile, engineering binding seam, no native call."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import copy
import hashlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import improvement_operation_protocol as protocol
import improvement_operation_profile as OP
from improvement_native_protocol import _ENV_FIXED, _ENV_PATHS
from improvement_store import _hash, _json
import test_improvement_operation_workspace as W


class EngineeringOperationBinding:
    instances = []
    def __init__(self, runtime, **arguments):
        if runtime == 'reject': raise ValueError('engineering_rejected')
        self.runtime, self.arguments = runtime, copy.deepcopy(arguments)
        self.delivery = None; self.clients = []
        self.__class__.instances.append(self)
    def create_client(self, options): self.clients.append(options); return self
    @property
    def completed_delivery(self): return copy.deepcopy(self.delivery)


class OperationProfileTwoTests(unittest.TestCase):
    def setUp(self):
        self.fixture = W.OperationWorkspaceTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.boundary = []

    def installation(self, version=2):
        workspace = self.fixture.workspace()
        value = W.materialization(); value['version'] = version
        config = {'version': 1, 'provider': 'anthropic-cli', 'engine_id': 'claude-sdk',
            'model': 'selected-operation-model', 'reasoning': 'high', 'cli_path': str(self.fixture.root / 'unused.exe'),
            'cli_hash': 'a' * 64, 'cli_version': 'engineering', 'sdk_version': '0.2.116',
            'profile_version': 'engineering', 'profile_hash': 'b' * 64}
        value['engine_config_hash'] = _hash(config)
        receipt = workspace.prepare('operation-1', 1, value)
        self.addCleanup(workspace.cleanup_proven, 'operation-1', 1, receipt)
        async def acknowledge(): self.boundary.append('ack')
        profile = OP.OperationProfile(config, workspace, receipt, 'c' * 64, before_query=acknowledge)
        engine = SimpleNamespace(session_id=None, cwd=receipt['path'], _on_stderr=lambda text: None)
        return profile, engine, value, receipt

    def bind(self, profile, runtime=None):
        environment = {**dict.fromkeys(_ENV_PATHS, 'engineering-exact-path'), **_ENV_FIXED}
        with patch('improvement_native_profile.NativeProfileBinding', EngineeringOperationBinding):
            profile.bind_native_runtime(object() if runtime is None else runtime, environment=environment)
        return EngineeringOperationBinding.instances[-1], environment

    def test_input2_accepts_only_exact_v1_field_and_data_contract_without_upgrading_v1(self):
        old = W.materialization(); value = {**old, 'version': 2}
        self.assertEqual(protocol.operation_materialization(old), old)
        self.assertEqual(protocol.operation_materialization(value), value)
        self.assertNotEqual(_hash(value), _hash(old))
        for changes in ({'version': True}, {'version': 3}, {'native_ready': True},
                {'data': {'task': 'unhashed replacement'}}, {'learning_origin': 'trial'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                protocol.operation_materialization({**value, **changes})
        self.assertEqual(protocol.operation_request(value['request']), old['request'])

    def test_two_options_and_start_fail_closed_without_native_binding(self):
        profile, engine, _, _ = self.installation()
        self.assertFalse(hasattr(profile, 'create_client'))
        with self.assertRaisesRegex(ValueError, 'native.*unbound'): profile.options(engine)
        with self.assertRaisesRegex(ValueError, 'native.*unbound'): asyncio.run(profile.before_query())
        self.assertEqual(self.boundary, [])

    def test_policy_identity_data_and_canonical_user_input_bind_actual_operation(self):
        profile, engine, value, receipt = self.installation()
        with patch.object(profile._native, 'bind_native_runtime', side_effect=AssertionError('Trial4 binder is not operation authority')):
            binding, environment = self.bind(profile)
        expected = {'version': 2, 'cli_path': profile.pin['cli_path'], 'model': profile.pin['model'],
            'reasoning': profile.pin['reasoning'], 'prompt_hash': hashlib.sha256(profile.system_prompt.encode()).hexdigest(),
            'cwd': receipt['path'], 'tools': ['mcp__fixture__fixture_read'], 'tool_policy': 'fixture_only'}
        self.assertEqual(binding.arguments, {'kind': 'operation', 'identity': {key: receipt[key] for key in
            ('operation_id', 'attempt', 'role', 'purpose', 'input_hash')}, 'data_hash': value['request']['input_hash'],
            'user_prompt': profile.user_prompt(), 'environment': environment, 'query_policy': expected})
        self.assertNotEqual(binding.arguments['data_hash'], receipt['input_hash'])
        options = profile.options(engine)
        self.assertIs(profile.create_client(options), binding)
        self.assertEqual(options.allowed_tools, ['mcp__fixture__fixture_read'])
        self.assertEqual(set(options.mcp_servers), {'fixture'})

    def test_environment_options_and_delivery_snapshots_are_defensive(self):
        profile, engine, _, _ = self.installation(); binding, environment = self.bind(profile)
        environment['HOME'] = 'caller mutation'
        options = profile.options(engine)
        self.assertEqual(options.env, binding.arguments['environment'])
        options.env['HOME'] = 'options mutation'
        self.assertEqual(profile.options(engine).env, binding.arguments['environment'])
        self.assertIsNone(profile.installation_receipt('session-a')['native_input_delivery'])
        binding.delivery = {'version': 1, 'engineering_only': 'completed-original-write'}
        receipt = profile.installation_receipt('session-a'); receipt['native_input_delivery'].clear()
        self.assertEqual(profile.installation_receipt('session-a')['native_input_delivery'], binding.delivery)

    def test_binding_is_once_before_options_start_and_failed_bind_has_no_factory(self):
        profile, engine, _, _ = self.installation()
        with self.assertRaises(ValueError): self.bind(profile, 'reject')
        self.assertFalse(hasattr(profile, 'create_client'))
        self.bind(profile); profile.options(engine)
        with self.assertRaises(ValueError): self.bind(profile)
        asyncio.run(profile.before_query()); self.assertEqual(self.boundary, ['ack'])
        with self.assertRaises(ValueError): asyncio.run(profile.before_query())

    def test_observe_emits_receipt2_with_exact_old_fields_plus_delivery_and_raw_null_usage(self):
        from claude_agent_sdk import AssistantMessage, ResultMessage, SystemMessage, TextBlock
        profile, engine, _, _ = self.installation(); binding, _ = self.bind(profile)
        profile.options(engine)
        events = profile.observe(SystemMessage('init', {'tools': ['mcp__fixture__fixture_read'], 'session_id': 'session-a'}))
        events += profile.observe(AssistantMessage([TextBlock('interim')], model=profile.pin['model'], session_id='session-a'))
        binding.delivery = {'version': 1, 'engineering_only': 'completed-original-write'}
        events += profile.observe(ResultMessage('success', 0, 0, False, 1, 'session-a', result='{"value":1}\r\n'))
        event = next(item for item in events if item['type'] == 'operation_installation_receipt')
        receipt = event['receipt']
        self.assertEqual(set(receipt), OP.RECEIPT_FIELDS | {'native_input_delivery'})
        self.assertEqual(receipt['version'], 2); self.assertEqual(event['hash'], _hash(receipt))
        self.assertEqual(receipt['native_input_delivery'], binding.delivery)
        self.assertIsNone(receipt['actual_reasoning']); self.assertEqual(receipt['coverage']['reasoning'], 'unknown')
        self.assertIsNone(next(item for item in events if item['type'] == 'usage')['usage'])
        self.assertLess(events.index(event), next(i for i, item in enumerate(events) if item['type'] == 'terminal'))
        self.assertFalse(any(item['type'] == 'installation_receipt' for item in events))

    def test_legacy1_keys_prompt_tools_environment_and_absent_factory_remain_exact(self):
        profile, engine, manifest, _ = self.installation(1)
        self.assertFalse(hasattr(profile, 'create_client'))
        with self.assertRaises(ValueError): self.bind(profile)
        options = profile.options(engine)
        self.assertEqual(options.env, {}); self.assertEqual(options.allowed_tools, ['mcp__fixture__fixture_read'])
        self.assertEqual(set(profile.installation_receipt('session-a')), OP.RECEIPT_FIELDS)
        self.assertEqual(profile.installation_receipt('session-a')['version'], 1)
        self.assertEqual(profile.user_prompt(), _json({'request': manifest['request'], 'authorized_input': manifest['data']}))


if __name__ == '__main__': unittest.main()
