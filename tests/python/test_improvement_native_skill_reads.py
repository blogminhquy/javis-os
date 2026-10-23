"""Versioned native skill-tool installation; real SDK handlers, synthetic messages."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from improvement_claude import TrialProfile
from improvement_sandbox import FixtureBroker, TrialWorkspace, _effective_hash, _manifest, trial_system_prompt
from improvement_skill_asset_broker import SkillAssetBroker
from improvement_store import _hash, _json
from test_improvement_skill_asset_broker import manifest as make_manifest, request as asset_request

FIXTURE = 'mcp__fixture__fixture_read'
SKILL = 'mcp__skill__skill_asset_read'


class VersionedSkillInputTests(unittest.TestCase):
    def test_nested_native_qualification_injections_keep_contiguous_sse_indexes(self):
        import test_improvement_runtime_qualification as qualification
        append = getattr(qualification, 'append_tool_calls', None)
        self.assertIsNotNone(append, 'Nested qualification replies need one composable SSE index allocator')
        body = b'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"tool_use"}}\n\n'
        body = append(body, [('asset-read', SKILL, {'asset_id': 'asset-a'})])
        body = append(body, [('outside-a', 'Bash', {}), ('outside-b', 'Read', {})])
        values = [json.loads(line[6:]) for line in body.decode().splitlines() if line.startswith('data: ')]
        for kind in ('content_block_start', 'content_block_delta', 'content_block_stop'):
            self.assertEqual([value['index'] for value in values if value['type'] == kind], [0, 1, 2])
        self.assertEqual([value['content_block']['id'] for value in values if value['type'] == 'content_block_start'],
                         ['asset-read', 'outside-a', 'outside-b'])

    def test_new_input_pins_view_and_asset_but_prompt_contains_only_read_descriptor(self):
        manifest = make_manifest() | {'version': 3}
        self.assertEqual(_manifest(manifest), manifest)
        prompt = trial_system_prompt(manifest)
        self.assertIn(manifest['baseline_context']['content'], prompt)
        self.assertIn(_json(manifest['public_contract']['content']), prompt)
        self.assertIn(SKILL, prompt)
        self.assertIn(_json(asset_request(manifest)), prompt)
        self.assertNotIn(manifest['assets'][0]['content'], prompt)
        self.assertEqual(_effective_hash(manifest), _effective_hash(manifest | {'version': 2}))
        changed = copy.deepcopy(manifest)
        changed['effective_view']['view_hash'] = 'e' * 64
        self.assertNotEqual(_effective_hash(manifest), _effective_hash(changed))

    def test_old_prompts_and_input_hashes_remain_byte_exact(self):
        current = make_manifest()
        old = {key: value for key, value in current.items() if key != 'effective_view'} | {'version': 1}
        expected = (old['baseline_context']['content'] + '\n\n<effective_assets>\n'
                    + _json(old['assets']) + '\n</effective_assets>\n\n<public_acceptance>\n'
                    + _json(old['public_contract']['content']) + '\n</public_acceptance>')
        for item in (old, current):
            self.assertEqual(_manifest(item), item)
            self.assertEqual(trial_system_prompt(item).encode(), expected.encode())
        self.assertNotEqual(_hash(current), _hash(current | {'version': 3}))

    def test_v3_broker_returns_only_pinned_bytes_and_strict_single_skill_schema(self):
        manifest = make_manifest() | {'version': 3}
        broker = SkillAssetBroker(manifest, trial_id='trial-v3', attempt=1, input_hash=_hash(manifest))
        result = broker.read(asset_request(manifest))
        self.assertEqual(result['content'], manifest['assets'][0]['content'])
        self.assertEqual(result['input_hash'], _hash(manifest))
        for assets in ([], [manifest['assets'][0]] * 2,
                       [manifest['assets'][0] | {'path': 'agents/foreign.md'}]):
            with self.subTest(assets=assets), self.assertRaises(ValueError):
                _manifest(manifest | {'assets': assets})


class NativeSkillProfileTests(unittest.TestCase):
    def installation(self, version=3):
        scratch = tempfile.TemporaryDirectory(prefix='native-skill-profile-')
        self.addCleanup(scratch.cleanup)
        root = Path(scratch.name)
        manifest = make_manifest() | {'version': version}
        if version == 1:
            manifest.pop('effective_view')
        pin = {'provider': 'anthropic-cli', 'model': 'claude-opus-5-5', 'reasoning': 'medium',
               'cli_path': str(root / 'never-executed.exe'), 'sdk_version': '0.2.116'}
        manifest['engine_config_hash'] = _hash(pin)
        workspace = TrialWorkspace(root / 'workspaces').prepare('trial-v3', 1, manifest)
        self.addCleanup(TrialWorkspace(root / 'workspaces').cleanup, 'trial-v3', 1)
        profile = TrialProfile(pin, FixtureBroker(manifest['case']['fixtures'], manifest['grant_hash']),
                               trial_system_prompt(manifest))
        profile.bind_installation(manifest, workspace, 'c' * 64)
        engine = SimpleNamespace(session_id=None, cwd=workspace['path'], _on_stderr=lambda _: None)
        return profile, engine, manifest, workspace

    def handlers(self, profile, engine):
        # Capture the actual SDK @tool handler before create_sdk_mcp_server wraps it.
        from unittest.mock import patch
        import claude_agent_sdk
        actual = claude_agent_sdk.create_sdk_mcp_server
        handlers = {}

        def capture(name, *, tools):
            handlers.update({tool.name: tool.handler for tool in tools})
            return actual(name, tools=tools)

        with patch.object(claude_agent_sdk, 'create_sdk_mcp_server', side_effect=capture):
            options = profile.options(engine)
        return options, handlers

    def test_only_bound_v3_has_two_closed_tools_and_legacy_keeps_fixture_inventory(self):
        for version in (1, 2, 3):
            profile, engine, manifest, _ = self.installation(version)
            options, handlers = self.handlers(profile, engine)
            expected = [FIXTURE, SKILL] if version == 3 else [FIXTURE]
            self.assertEqual(options.allowed_tools, expected)
            self.assertEqual(set(options.mcp_servers), {'fixture', 'skill'} if version == 3 else {'fixture'})
            self.assertEqual(set(handlers), {'fixture_read', 'skill_asset_read'} if version == 3 else {'fixture_read'})
            self.assertEqual(options.tools, [])
            self.assertEqual(options.setting_sources, [])
            self.assertTrue(options.strict_mcp_config)
            if version == 3:
                result = asyncio.run(handlers['skill_asset_read'](asset_request(manifest)))
                self.assertIs(result['is_error'], False)
                self.assertEqual(json.loads(result['content'][0]['text'])['content'], manifest['assets'][0]['content'])
                denied = asyncio.run(handlers['skill_asset_read'](asset_request(manifest) | {'asset_id': 'foreign'}))
                self.assertIs(denied['is_error'], True)
                self.assertNotIn(manifest['assets'][0]['content'], str(denied))

    def completed(self, *, native_error=False, alter=None):
        from claude_agent_sdk import AssistantMessage, ResultMessage, SystemMessage, ToolResultBlock, ToolUseBlock, UserMessage
        profile, engine, manifest, workspace = self.installation()
        _, handlers = self.handlers(profile, engine)
        events = profile.observe(SystemMessage('init', {'tools': [FIXTURE, SKILL], 'session_id': 'session-a'}))
        args = asset_request(manifest)
        events += profile.observe(AssistantMessage([ToolUseBlock('read-a', SKILL, args)],
                                  model=profile.pin['model'], session_id='session-a'))
        response = asyncio.run(handlers['skill_asset_read'](args))
        content = copy.deepcopy(response['content'])
        if alter:
            alter(content)
        events += profile.observe(UserMessage([ToolResultBlock('read-a', content, native_error)]))
        events += profile.observe(ResultMessage('success', 0, 0, False, 1, 'session-a', result='synthetic output'))
        receipt = next(event['receipt'] for event in events if event['type'] == 'installation_receipt')
        return profile, manifest, workspace, events, receipt

    def test_actual_handler_and_typed_native_messages_yield_independent_read_summary(self):
        from improvement_skill_asset_proof import correlate_asset_reads
        _, manifest, workspace, events, receipt = self.completed()
        self.assertEqual(receipt['version'], 3)
        self.assertEqual(receipt['effective_view'], manifest['effective_view'])
        self.assertEqual(receipt['asset_revisions'][0]['observed_use'], 'observed')
        proof = correlate_asset_reads(manifest, workspace, events)
        self.assertEqual(proof['verdict'], 'pass')
        self.assertEqual(receipt['asset_read_proofs'], proof['proofs'])
        self.assertEqual(receipt['coverage']['reasoning'], 'unknown')
        self.assertIsNone(receipt['actual_reasoning'])
        native = next(event for event in events if event['type'] == 'tool_result')
        self.assertIs(native['native_is_error'], False)

    def test_absent_read_error_or_changed_native_response_cannot_claim_observed_use(self):
        from claude_agent_sdk import ResultMessage, SystemMessage
        profile, engine, _, _ = self.installation()
        profile.options(engine)
        profile.observe(SystemMessage('init', {'tools': [FIXTURE, SKILL], 'session_id': 'session-a'}))
        events = profile.observe(ResultMessage('success', 0, 0, False, 1, 'session-a', result='I used the skill'))
        receipt = next(event['receipt'] for event in events if event['type'] == 'installation_receipt')
        self.assertEqual(receipt['asset_read_proofs'], [])
        self.assertEqual(receipt['asset_revisions'][0]['observed_use'], 'unknown')
        for kwargs in ({'native_error': True}, {'native_error': None},
                       {'alter': lambda content: content[0].update(text='forged response')}):
            with self.subTest(kwargs=kwargs):
                *_, receipt = self.completed(**kwargs)
                self.assertEqual(receipt['asset_read_proofs'], [])
                self.assertEqual(receipt['asset_revisions'][0]['observed_use'], 'unknown')


class NativeSkillCheckerTests(unittest.TestCase):
    def records(self):
        from claude_agent_sdk import AssistantMessage, ResultMessage, SystemMessage, ToolResultBlock, ToolUseBlock, UserMessage
        from test_improvement_trial_checks import TrialChecksTests
        record = TrialChecksTests()
        record.setUp()
        view = {'view_id': 'view-a', 'view_hash': 'a' * 64, 'binding_hash': 'b' * 64}
        record.manifest.update(version=3, effective_view=view)
        record.request.update(version=4, view=view, lineage={
            'version': 1, 'context_id': 'context-a', 'definition_hash': 'd' * 64,
            'comparison_id': 'comparison-a', 'comparison_hash': 'e' * 64, 'matrix_hash': 'f' * 64,
            'arm_ordinal': 1, 'arm_hash': record.request['pins']['candidate_bundle_hash'],
            'candidate_id': 'candidate-a', 'pair_id': '1' * 64, 'cell_position': 0})
        scratch = tempfile.TemporaryDirectory(prefix='native-skill-checker-')
        self.addCleanup(scratch.cleanup)
        workspaces = TrialWorkspace(Path(scratch.name) / 'workspaces')
        record.workspace = workspaces.prepare('trial-1', 1, record.manifest)
        self.addCleanup(workspaces.cleanup, 'trial-1', 1)
        pin = {key: record.request['engine_config'][key] for key in ('provider', 'model', 'reasoning', 'cli_path', 'sdk_version')}
        broker = FixtureBroker(record.manifest['case']['fixtures'], record.manifest['grant_hash'])
        profile = TrialProfile(pin, broker, trial_system_prompt(record.manifest))
        profile.bind_installation(record.manifest, record.workspace, record.capability)
        _, handlers = NativeSkillProfileTests.handlers(self, profile,
            SimpleNamespace(session_id=None, cwd=record.workspace['path'], _on_stderr=lambda _: None))
        args = asset_request(record.manifest)
        events = profile.observe(SystemMessage('init', {'tools': [FIXTURE, SKILL], 'session_id': 'session-1'}))
        events += profile.observe(AssistantMessage([ToolUseBlock('asset-a', SKILL, args)], model=pin['model'], session_id='session-1'))
        response = asyncio.run(handlers['skill_asset_read'](args))
        events += profile.observe(UserMessage([ToolResultBlock('asset-a', response['content'], False)]))
        broker.read('fixture.read', {'snapshot_id': 'snapshot-1'}, 'v1', record.manifest['grant_hash'])
        events += profile.observe(ResultMessage('success', 0, 0, False, 1, 'session-1', result='{"value":42}\r\n'))
        record.events = events
        record.receipt = next(event['receipt'] for event in events if event['type'] == 'installation_receipt')
        record.rebuild_packets(fixture=broker.events)
        return record

    def test_full_checker_recomputes_read_and_preserves_all18_and_reasoning_unknown(self):
        record = self.records()
        rows = record.check()
        self.assertEqual(len(rows), 18)
        self.assertEqual(rows['asset_observed_use']['verdict'], 'pass', rows)
        for key in ('installation', 'tool_inventory', 'side_effects', 'event_coverage', 'asset_installation'):
            self.assertEqual(rows[key]['verdict'], 'pass', rows[key])
        self.assertEqual(rows['actual_reasoning']['verdict'], 'unknown')
        self.assertTrue(all(row['evidence']['business_proof'] is False for row in rows.values()))

    def test_forged_or_changed_summary_cannot_replace_raw_native_read(self):
        record = self.records()
        record.events = [event for event in record.events if event['type'] != 'skill_asset_broker_observation']
        record.rebuild_packets()
        self.assertNotEqual(record.check()['asset_observed_use']['verdict'], 'pass')
        record = self.records()
        record.receipt['asset_read_proofs'][0]['tool_use_id'] = 'fabricated-call'
        record.rebuild_packets()
        self.assertEqual(record.check()['asset_observed_use']['verdict'], 'fail')

    def test_claimed_observed_use_without_proof_and_extra_receipt_fields_fail_closed(self):
        record = self.records()
        record.receipt['asset_read_proofs'] = []
        record.rebuild_packets()
        self.assertEqual(record.check()['asset_observed_use']['verdict'], 'fail')
        record = self.records()
        record.receipt['understood'] = True
        record.rebuild_packets()
        self.assertEqual(record.check()['installation']['verdict'], 'fail')

    def test_missing_native_optional_error_stays_unknown_without_global_default(self):
        record = self.records()
        for event in record.events:
            if event['type'] == 'tool_result':
                event['is_error'] = event['native_is_error'] = None
        record.receipt['asset_read_proofs'] = []
        record.receipt['asset_revisions'][0]['observed_use'] = 'unknown'
        record.rebuild_packets()
        rows = record.check()
        self.assertEqual(rows['asset_observed_use']['verdict'], 'unknown')
        self.assertEqual(rows['side_effects']['verdict'], 'unknown')


if __name__ == '__main__':
    unittest.main()
