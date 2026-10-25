"""Owned baseline5 profile and original SDK write; no CLI/provider/account call."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import copy
from dataclasses import replace
import hashlib
import json
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from improvement_store import _hash
import test_improvement_manifest5 as baseline_fixture
import test_improvement_native_skill_reads as legacy
import test_improvement_trial_profile4 as view
import test_improvement_native_profile as native


class TrialProfileFiveTests(unittest.TestCase):
    def installation(self):
        value = baseline_fixture.baseline()
        text = 'Retain exact authorized owner rules. Café 日本語.\n'
        value['assets'][0].update(content=text, hash=hashlib.sha256(text.encode()).hexdigest())
        with patch.object(legacy, 'make_manifest', return_value=value):
            return legacy.NativeSkillProfileTests.installation(self, 5)

    bind = view.TrialProfileFourTests.bind
    handlers = view.TrialProfileFourTests.handlers

    def test_five_cannot_select_ambient_sdk_options_or_start_before_owned_binding(self):
        profile, engine, _, _ = self.installation()
        with self.assertRaisesRegex(ValueError, 'native.*unbound'): profile.options(engine)
        with self.assertRaisesRegex(ValueError, 'native.*unbound'): asyncio.run(profile.before_query())
        self.assertFalse(hasattr(profile, 'create_client'))

    def test_five_owned_factory_keeps_fixture_only_inventory_and_exact_frozen_environment(self):
        profile, engine, manifest, workspace = self.installation()
        binding, environment = self.bind(profile)
        policy = binding.arguments['query_policy']
        self.assertEqual(policy['tool_policy'], 'baseline_inline')
        self.assertEqual(policy['tools'], [view.F.FIXTURE])
        self.assertEqual(binding.arguments['identity'], {key: workspace[key] for key in ('trial_id', 'attempt', 'input_hash')})
        self.assertEqual(binding.arguments['data_hash'], workspace['input_hash'])
        options = profile.options(engine)
        self.assertEqual(options.allowed_tools, [view.F.FIXTURE])
        self.assertEqual(set(options.mcp_servers), {'fixture'})
        self.assertEqual(options.env, environment)
        environment['HOME'] = 'caller mutation'
        self.assertNotEqual(options.env['HOME'], environment['HOME'])
        self.assertIs(profile.create_client(options), binding)
        with self.assertRaises(ValueError): self.bind(profile)
        self.assertNotIn('effective_view', manifest)

    def test_five_receipt_binds_missing_delivery_as_none_without_inventing_asset_read_or_reasoning(self):
        from claude_agent_sdk import SystemMessage
        profile, engine, manifest, _ = self.installation()
        self.bind(profile)
        profile.options(engine)
        profile.observe(SystemMessage('init', {'tools': [view.F.FIXTURE], 'session_id': 'engineering-baseline-session'}))
        receipt = profile.installation_receipt('engineering-baseline-session')
        self.assertEqual(receipt['version'], 5)
        self.assertEqual(set(receipt), view.BASE | {'native_input_delivery'})
        self.assertIsNone(receipt['native_input_delivery'])
        self.assertIsNone(receipt['actual_reasoning'])
        self.assertEqual(receipt['coverage']['reasoning'], 'unknown')
        self.assertEqual(receipt['asset_revisions'][0]['observed_use'], 'unknown')
        self.assertEqual(receipt['bundle_hash'], manifest['bundle_hash'])
        self.assertNotIn('effective_view', receipt)
        self.assertNotIn('read_outcome_proofs', receipt)

    @unittest.skipUnless(os.name == 'nt', 'query dispatch pins a Windows absolute CLI path and creation flags')
    def test_actual_sdk_command_accepts_only_declared_baseline_policy_and_fixture_tool(self):
        from claude_agent_sdk._internal.transport.subprocess_cli import SubprocessCLITransport
        from improvement_query_dispatch import validate_query_dispatch
        profile, engine, _, _ = self.installation()
        binding, _ = self.bind(profile)
        options = replace(profile.options(engine), permission_prompt_tool_name='stdio')
        argv = SubprocessCLITransport(prompt='', options=options)._build_command()
        policy = binding.arguments['query_policy']
        result = validate_query_dispatch(argv, command_line=subprocess.list2cmdline(argv), executable=None,
            cwd=engine.cwd, creationflags=0x08000006, expected=policy)
        self.assertEqual(result['tool_policy'], 'baseline_inline')
        self.assertEqual(result['tools'], [view.F.FIXTURE])
        changed = list(argv)
        changed[changed.index('--allowedTools') + 1] += ',mcp__skill__skill_asset_read'
        with self.assertRaises(ValueError):
            validate_query_dispatch(changed, command_line=subprocess.list2cmdline(changed), executable=None,
                cwd=engine.cwd, creationflags=0x08000006, expected=policy)


@unittest.skipUnless(os.name == 'nt' and sys.flags.isolated, 'actual SDK transport requires isolated Windows driver')
class NativeBaselineBindingTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = native.NativeProfileTests.asyncSetUp
    asyncTearDown = native.NativeProfileTests.asyncTearDown
    preflight = native.NativeProfileTests.preflight
    options = native.NativeProfileTests.options
    policy = native.NativeProfileTests.policy
    connect = native.NativeProfileTests.connect
    frame = native.NativeProfileTests.frame

    def baseline_binding(self):
        from improvement_native_profile import NativeProfileBinding
        return NativeProfileBinding(self.owner, kind='trial', identity={'trial_id': 'baseline-owned', 'attempt': 1,
            'input_hash': 'b' * 64}, data_hash='b' * 64, user_prompt='Exact wrapper \u0111\u1ed1i so\u00e1t\r\n',
            environment=copy.deepcopy(self.env), query_policy={**self.policy(), 'tool_policy': 'baseline_inline'})

    async def test_actual_owned_sdk_original_write_binds_baseline_trial_identity_and_unknown_provider(self):
        await self.preflight()
        binding = self.baseline_binding()
        client = binding.create_client(self.options())
        await self.connect(client._custom_transport)
        self.assertIsNone(binding.completed_delivery)
        await client._custom_transport.write(self.frame())
        proof = binding.completed_delivery
        self.assertEqual(proof['kind'], 'trial')
        self.assertEqual(proof['identity'], {'trial_id': 'baseline-owned', 'attempt': 1, 'input_hash': 'b' * 64})
        self.assertEqual(proof['data_hash'], 'b' * 64)
        self.assertEqual(proof['user_frame_hash'], hashlib.sha256(self.frame().encode()).hexdigest())
        self.assertEqual(proof['coverage']['provider_acceptance'], 'unknown')
        self.assertEqual(proof['coverage']['native_read_ack'], 'unknown')
        self.assertEqual(proof['coverage']['comprehension'], 'unknown')

    async def test_operation_cannot_select_the_baseline_trial_policy(self):
        from improvement_native_profile import NativeProfileBinding
        await self.preflight()
        with self.assertRaisesRegex(ValueError, 'native_profile_query_policy_drift'):
            NativeProfileBinding(self.owner, kind='operation', identity={'operation_id': 'op-native', 'attempt': 1,
                'role': 'improver', 'purpose': 'improve_propose', 'input_hash': 'b' * 64},
                data_hash='b' * 64, user_prompt='Exact wrapper', environment=copy.deepcopy(self.env),
                query_policy={**self.policy(), 'tool_policy': 'baseline_inline'})


if __name__ == '__main__': unittest.main()
