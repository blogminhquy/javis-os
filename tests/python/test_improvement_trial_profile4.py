"""Actual TrialProfile4/options/handlers with engineering binding, no native call."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import copy
import hashlib
import json
import unittest
from unittest.mock import patch

from improvement_claude import TrialProfile
from improvement_native_protocol import _ENV_FIXED, _ENV_PATHS
from improvement_read_outcome_proof import correlate_read_outcomes
from improvement_store import _hash, _json
import test_improvement_native_skill_reads as L
import test_improvement_read_outcome_broker as F

BASE = {'version', 'trial_id', 'attempt', 'session_id', 'input_hash', 'effective_hash', 'bundle_hash',
    'contract_hash', 'public_contract_hash', 'engine_config_hash', 'grant_hash', 'capability_hash',
    'baseline_context_hash', 'expected_system_prompt_hash', 'system_prompt_hash', 'tool_inventory_hash',
    'observed_tool_inventory_hash', 'fixture_inventory_hash', 'asset_revisions', 'requested', 'actual_models',
    'actual_reasoning', 'coverage'}
HOST = 'trial_read_broker_observation'


class EngineeringBinding:
    """Only the profile-to-binding seam; root tests the real native owner."""
    instances = []
    def __init__(self, runtime, **kwargs):
        if runtime == 'reject': raise ValueError('engineering_binding_rejected')
        self.runtime, self.arguments = runtime, copy.deepcopy(kwargs)
        self.delivery = None; self.clients = []
        self.__class__.instances.append(self)
    def create_client(self, options):
        self.clients.append(options); return self
    @property
    def completed_delivery(self): return copy.deepcopy(self.delivery)


class TrialProfileFourTests(unittest.TestCase):
    def installation(self, version=4):
        with patch.object(L, 'make_manifest', side_effect=lambda: F.manifest(2)):
            return L.NativeSkillProfileTests.installation(self, version)

    def bind(self, profile, **changes):
        environment = {**dict.fromkeys(_ENV_PATHS, 'engineering-private-path'), **_ENV_FIXED}
        kwargs = {'environment': environment, 'user_prompt': 'Exact user task\r\n日本語'}
        with patch('improvement_native_profile.NativeProfileBinding', EngineeringBinding):
            profile.bind_native_runtime(object(), **{**kwargs, **changes})
        return EngineeringBinding.instances[-1], environment

    def handlers(self, profile, engine):
        return L.NativeSkillProfileTests.handlers(self, profile, engine)

    def test_four_installation_refuses_legacy_options_and_start_without_binding(self):
        profile, engine, _, _ = self.installation()
        with self.assertRaisesRegex(ValueError, 'native.*unbound'): profile.options(engine)
        with self.assertRaisesRegex(ValueError, 'native.*unbound'): asyncio.run(profile.before_query())
        self.assertFalse(hasattr(profile, 'create_client'))

    def test_binding_policy_environment_identity_and_factory_are_exact_and_defensive(self):
        profile, engine, manifest, workspace = self.installation()
        binding, environment = self.bind(profile)
        expected = {'version': 2, 'cli_path': profile.pin['cli_path'], 'model': profile.pin['model'],
            'reasoning': profile.pin['reasoning'], 'prompt_hash': hashlib.sha256(profile.system_prompt.encode()).hexdigest(),
            'cwd': workspace['path'], 'tools': [F.FIXTURE, F.SKILL], 'tool_policy': 'pinned_skill'}
        self.assertEqual(binding.arguments, {'kind': 'trial', 'identity': {key: workspace[key] for key in
            ('trial_id', 'attempt', 'input_hash')}, 'data_hash': workspace['input_hash'],
            'user_prompt': 'Exact user task\r\n日本語', 'environment': environment, 'query_policy': expected})
        environment['HOME'] = 'caller mutation'
        options, _ = self.handlers(profile, engine)
        self.assertEqual(options.env, binding.arguments['environment'])
        self.assertEqual(options.allowed_tools, [F.FIXTURE, F.SKILL])
        self.assertEqual(set(options.mcp_servers), {'fixture', 'skill'})
        self.assertIs(profile.create_client(options), binding)
        options.env['HOME'] = 'return mutation'
        self.assertEqual(profile.options(engine).env, binding.arguments['environment'])

    def test_binding_lifecycle_is_four_installed_once_and_before_options_or_start(self):
        profile, _, _, _ = self.installation()
        with patch('improvement_native_profile.NativeProfileBinding', EngineeringBinding):
            with self.assertRaises(ValueError): profile.bind_native_runtime('reject', environment={}, user_prompt='x')
        self.assertFalse(hasattr(profile, 'create_client'))
        self.bind(profile)
        with self.assertRaises(ValueError): self.bind(profile)
        for version in (1, 2, 3):
            legacy, _, _, _ = self.installation(version)
            with self.subTest(version=version), self.assertRaises(ValueError): self.bind(legacy)
            self.assertFalse(hasattr(legacy, 'create_client'))

    def test_four_handlers_emit_exact_envelopes_and_actual_fixture_source_events(self):
        profile, engine, manifest, _ = self.installation(); self.bind(profile)
        _, handlers = self.handlers(profile, engine)
        for name, args, content in (('skill_asset_read', F.skill_args(manifest), F.SKILL_CONTENT),
                ('fixture_read', F.fixture_args(), F.FIXTURE_CONTENT)):
            response = asyncio.run(handlers[name](args))
            value = json.loads(response['content'][0]['text'])
            self.assertEqual(response['content'][0]['text'], _json(value))
            self.assertEqual(set(value), F.ENVELOPE_FIELDS)
            self.assertEqual(value['result']['content'], content)
            self.assertIs(response['is_error'], False)
        self.assertEqual(profile.broker.events[-1]['status'], 'fixture_hit')
        denied = asyncio.run(handlers['fixture_read']({'path': 'foreign'}))
        self.assertIs(denied['is_error'], True)
        self.assertEqual(json.loads(denied['content'][0]['text'])['result'], F.MISS)
        self.assertEqual(profile.broker.events[-1]['status'], 'fixture_miss')

    def complete(self, *, flag=None, early=False, tool=F.SKILL):
        from claude_agent_sdk import AssistantMessage, ResultMessage, SystemMessage, ToolUseBlock, ToolResultBlock, UserMessage
        profile, engine, manifest, workspace = self.installation(); binding, _ = self.bind(profile)
        _, handlers = self.handlers(profile, engine)
        args = F.skill_args(manifest) if tool == F.SKILL else F.fixture_args()
        name = 'skill_asset_read' if tool == F.SKILL else 'fixture_read'
        events = []
        if early:
            response = asyncio.run(handlers[name](args))
            pending = profile.installation_receipt('session-a')
            self.assertEqual(pending['read_outcome_proofs'], [])
            self.assertEqual(pending['asset_revisions'][0]['observed_use'], 'unknown')
        events += profile.observe(SystemMessage('init', {'tools': [F.FIXTURE, F.SKILL], 'session_id': 'session-a'}))
        if early:
            self.assertEqual([event['type'] for event in events], ['native_system', HOST])
        events += profile.observe(AssistantMessage([ToolUseBlock('read-a', tool, args)],
            model=profile.pin['model'], session_id='session-a'))
        if not early: response = asyncio.run(handlers[name](args))
        delivered = profile.observe(UserMessage([ToolResultBlock('read-a', copy.deepcopy(response['content']), flag)]))
        if not early: self.assertEqual([event['type'] for event in delivered], [HOST, 'tool_result'])
        events += delivered
        binding.delivery = {'version': 1, 'engineering_only': 'completed-write-snapshot'}
        events += profile.observe(ResultMessage('success', 0, 0, False, 1, 'session-a', result='Exact final\r\n'))
        receipt = next(event['receipt'] for event in events if event['type'] == 'installation_receipt')
        return profile, manifest, workspace, events, receipt, binding

    def test_before_init_handler_is_bound_only_after_actual_init_then_exact_raw_none_delivery(self):
        _, manifest, workspace, events, receipt, _ = self.complete(early=True)
        proof = correlate_read_outcomes(manifest, workspace, events)
        self.assertEqual(proof['verdict'], 'pass')
        self.assertEqual(receipt['read_outcome_proofs'], proof['proofs'])
        self.assertIs(next(event for event in events if event['type'] == 'tool_result')['native_is_error'], None)

    def test_receipt4_exact_keys_read_proofs_input_snapshot_and_reasoning_remain_separate(self):
        profile, _, _, events, receipt, binding = self.complete()
        self.assertEqual(set(receipt), BASE | {'effective_view', 'read_outcome_proofs', 'native_input_delivery'})
        self.assertEqual(receipt['version'], 4); self.assertNotIn('asset_read_proofs', receipt)
        self.assertEqual(receipt['asset_revisions'][0]['observed_use'], 'observed')
        self.assertIsNone(receipt['actual_reasoning']); self.assertEqual(receipt['coverage']['reasoning'], 'unknown')
        self.assertEqual(receipt['native_input_delivery'], binding.delivery)
        receipt['native_input_delivery'].clear(); receipt['read_outcome_proofs'].clear()
        again = profile.installation_receipt('session-a')
        self.assertEqual(again['native_input_delivery'], binding.delivery)
        self.assertEqual(len(again['read_outcome_proofs']), 1)
        self.assertIsNone(next(event for event in events if event['type'] == 'usage')['usage'])

    def test_actual_native_error_is_preserved_and_fixture_read_never_marks_skill_observed(self):
        for flag in (False, True):
            _, _, _, events, receipt, _ = self.complete(flag=flag)
            result = next(event for event in events if event['type'] == 'tool_result')
            self.assertIs(result['is_error'], flag); self.assertIs(result['native_is_error'], flag)
            self.assertEqual(receipt['asset_revisions'][0]['observed_use'], 'unknown' if flag else 'observed')
        _, _, _, _, receipt, _ = self.complete(tool=F.FIXTURE)
        self.assertEqual(receipt['asset_revisions'][0]['observed_use'], 'unknown')

    def test_old_receipt_sets_tools_environment_and_missing_factory_stay_exact(self):
        for version in (1, 2, 3):
            profile, engine, _, _ = self.installation(version)
            options, _ = self.handlers(profile, engine)
            self.assertFalse(hasattr(profile, 'create_client')); self.assertEqual(options.env, {})
            expected = BASE | ({'effective_view'} if version > 1 else set()) | ({'asset_read_proofs'} if version == 3 else set())
            self.assertEqual(set(profile.installation_receipt('session-a')), expected)
            self.assertEqual(options.allowed_tools, [F.FIXTURE, F.SKILL] if version == 3 else [F.FIXTURE])


if __name__ == '__main__': unittest.main()
