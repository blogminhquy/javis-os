"""Actual SDK client/transport with fake capture/IO; no native/account query."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import hashlib
import importlib
import json
import os
import sys
import unittest
from unittest.mock import patch

import test_improvement_native_sdk as fixture

try:
    profile_module = importlib.import_module('improvement_native_profile')
except ModuleNotFoundError as error:
    if error.name != 'improvement_native_profile': raise
    profile_module = None


@unittest.skipUnless(os.name == 'nt' and sys.flags.isolated, 'owned SDK transport requires isolated Windows driver')
class NativeProfileTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixture.NativeSDKTests.asyncSetUp
    asyncTearDown = fixture.NativeSDKTests.asyncTearDown
    preflight = fixture.NativeSDKTests.preflight
    options = fixture.NativeSDKTests.options
    policy = fixture.NativeSDKTests.policy
    connect = fixture.NativeSDKTests.connect

    def binding(self, **changes):
        self.assertIsNotNone(profile_module, 'native profile binding missing')
        values = dict(kind='operation', identity={'operation_id': 'op-native', 'attempt': 1,
            'role': 'improver', 'purpose': 'improve_propose', 'input_hash': 'b' * 64},
            data_hash='c' * 64, user_prompt='Exact wrapper \u0111\u1ed1i so\u00e1t\r\n',
            environment=dict(self.env), query_policy=self.policy())
        values.update(changes)
        return profile_module.NativeProfileBinding(self.owner, **values)

    def frame(self, prompt='Exact wrapper \u0111\u1ed1i so\u00e1t\r\n'):
        return json.dumps({'type': 'user', 'message': {'role': 'user', 'content': prompt},
            'parent_tool_use_id': None, 'session_id': 'default'}) + '\n'

    async def ready(self):
        await self.preflight()
        binding = self.binding()
        client = binding.create_client(self.options())
        await self.connect(client._custom_transport)
        return binding, client._custom_transport

    async def test_actual_sdk_client_uses_owned_transport_without_mutating_original_options(self):
        from claude_agent_sdk import ClaudeSDKClient
        await self.preflight()
        binding = self.binding()
        options = self.options(); options.env = {'AMBIENT_VALUE': 'must-not-reach-child'}
        client = binding.create_client(options)
        self.assertIs(type(client), ClaudeSDKClient)
        self.assertIs(client.options, options)
        self.assertEqual(options.env, {'AMBIENT_VALUE': 'must-not-reach-child'})
        self.assertEqual(client._custom_transport._options.env, self.env)
        self.assertIsNone(options.permission_prompt_tool_name)
        self.assertEqual(client._custom_transport._options.permission_prompt_tool_name, 'stdio')
        self.assertIsNone(binding.completed_delivery)
        await self.connect(client._custom_transport)
        self.assertEqual(fixture.Capture.instances[-1].kwargs['env']['HOME'], self.env['HOME'])

    async def test_completed_exact_original_write_records_raw_hash_and_no_live_handles(self):
        binding, transport = await self.ready()
        await transport.write('{"type":"control_request"}\n')
        self.assertIsNone(binding.completed_delivery)
        await transport.write(self.frame())
        proof = binding.completed_delivery
        self.assertEqual(proof['identity']['operation_id'], 'op-native')
        self.assertEqual(proof['native_pid'], transport._process.pid)
        self.assertEqual(proof['native_birth'], 202)
        self.assertEqual(proof['wire_session_id'], 'default')
        self.assertEqual(proof['user_frame_hash'], hashlib.sha256(self.frame().encode()).hexdigest())
        self.assertEqual(proof['dispatch_nonce'], self.channels['query']._nonce)
        self.assertEqual(proof['coverage']['provider_acceptance'], 'unknown')
        self.assertFalse({'hfile', 'hprocess', 'hthread'} & proof.keys())
        proof['identity']['attempt'] = 99
        self.assertEqual(binding.completed_delivery['identity']['attempt'], 1)
        self.assertNotIn('Exact wrapper', json.dumps(binding.completed_delivery))

    async def test_changed_full_user_wrapper_refuses_delivery_proof_after_real_transport_write(self):
        binding, transport = await self.ready()
        with self.assertRaises(OSError): await transport.write(self.frame('Altered wrapper'))
        self.assertIsNone(binding.completed_delivery)
        self.assertTrue(fixture.Capture.instances[-1].closed)

    async def test_failed_original_send_has_no_completed_delivery(self):
        binding, transport = await self.ready()
        transport._process.stdin.error = OSError('synthetic send failure')
        with self.assertRaises(OSError): await transport.write(self.frame())
        self.assertIsNone(binding.completed_delivery)

    async def test_single_factory_and_duplicate_user_never_replace_first_write_proof(self):
        binding, transport = await self.ready()
        with self.assertRaises((ValueError, OSError)): binding.create_client(self.options())
        await transport.write(self.frame())
        first = binding.completed_delivery
        with self.assertRaises(OSError): await transport.write(self.frame())
        self.assertEqual(binding.completed_delivery, first)

    async def test_constructor_binds_exact_runtime_environment_and_query_pins(self):
        for values in ({'kind': 'preflight'}, {'environment': {**self.env, 'EXTRA': 'value'}},
                {'query_policy': {**self.policy(), 'model': 'foreign'}},
                {'query_policy': {**self.policy(), 'reasoning': 'low'}},
                {'query_policy': {**self.policy(), 'tool_policy': 'pinned_skill'}},
                {'identity': {'operation_id': 'other', 'attempt': True, 'input_hash': 'b' * 64}},
                {'data_hash': 'invalid'}):
            with self.subTest(fields=list(values)), self.assertRaises((ValueError, TypeError)):
                self.binding(**values)

    async def test_static_delivery_validation_rejects_drift_without_claiming_execution_authority(self):
        binding, transport = await self.ready()
        await transport.write(self.frame())
        proof = binding.completed_delivery
        keywords = dict(kind='operation', identity=proof['identity'], data_hash='c' * 64,
            user_prompt='Exact wrapper \u0111\u1ed1i so\u00e1t\r\n')
        self.assertEqual(profile_module.validate_input_delivery(proof, **keywords), proof)
        changes = [('native_pid', True), ('wire_session_id', 'foreign'), ('user_frame_hash', 'd' * 64),
            ('user_prompt_hash', 'd' * 64), ('data_hash', 'd' * 64), ('unexpected', 'raw-handle'),
            ('identity', {**proof['identity'], 'attempt': True})]
        for key, value in changes:
            altered = copy.deepcopy(proof); altered[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                profile_module.validate_input_delivery(altered, **keywords)

    async def test_factory_failure_is_one_shot_and_does_not_launch_without_preflight(self):
        binding = self.binding()
        with self.assertRaises(OSError): binding.create_client(self.options())
        await self.preflight()
        with self.assertRaises((ValueError, OSError)): binding.create_client(self.options())
        self.assertEqual(len(fixture.Capture.instances), 2)


if __name__ == '__main__': unittest.main()
