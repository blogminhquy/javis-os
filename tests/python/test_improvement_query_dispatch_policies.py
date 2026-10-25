"""Pure inventory policy vectors; no SDK, clients, files or native processes."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import hashlib
import json
import subprocess
import unittest

from improvement_query_dispatch import validate_query_dispatch


CLI = r'C:\Trusted Tools\claude.exe'
CWD = r'D:\Trial Workspace\owned'
PROMPT = 'Owner rule\nCafé "quoted" \\tail'
FIXTURE = 'mcp__fixture__fixture_read'
SKILL = 'mcp__skill__skill_asset_read'


def sha(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def vector(policy='fixture_only', version=2):
    tools = [FIXTURE] if policy == 'fixture_only' else [FIXTURE, SKILL]
    servers = {'fixture': {'type': 'sdk', 'name': 'fixture'}}
    if len(tools) == 2:
        servers['skill'] = {'type': 'sdk', 'name': 'skill'}
    pin = {'version': version, 'cli_path': CLI, 'model': 'selected-model', 'reasoning': 'medium',
           'prompt_hash': sha(PROMPT), 'cwd': CWD, 'tools': tools}
    if version == 2:
        pin['tool_policy'] = policy
    args = [CLI, '--output-format', 'stream-json', '--verbose', '--system-prompt', PROMPT,
            '--tools', '', '--allowedTools', ','.join(tools), '--model', 'selected-model',
            '--permission-prompt-tool', 'stdio', '--permission-mode', 'default', '--settings',
            '{"fastMode":false,"disableAllHooks":true}', '--mcp-config', canonical({'mcpServers': servers}),
            '--strict-mcp-config', '--setting-sources=', '--no-session-persistence', '--disable-slash-commands',
            '--no-chrome', '--restricted', '--safe-mode', '--effort', 'medium', '--input-format', 'stream-json']
    return pin, args


def validate(pin, args):
    return validate_query_dispatch(args, command_line=subprocess.list2cmdline(args), executable=None,
        cwd=CWD, creationflags=0x08000006, expected=pin)


class QueryDispatchPolicyTests(unittest.TestCase):
    def test_fixture_only_policy_accepts_exact_single_server_without_granting_skill(self):
        pin, args = vector()
        result = validate(pin, args)
        self.assertEqual((result['version'], result['tool_policy'], result['tools']), (2, 'fixture_only', [FIXTURE]))
        self.assertEqual(result['expected_hash'], sha(canonical(pin)))
        self.assertEqual(result['mcp_config_hash'], sha(canonical({'mcpServers': {'fixture': {'type': 'sdk', 'name': 'fixture'}}})))
        self.assertTrue(all(value == 'unknown' for value in result['coverage'].values()))

    def test_pinned_skill_policy_accepts_only_exact_two_read_tools(self):
        pin, args = vector('pinned_skill')
        result = validate(pin, args)
        self.assertEqual((result['version'], result['tool_policy'], result['tools']), (2, 'pinned_skill', [FIXTURE, SKILL]))
        self.assertEqual(result['expected_hash'], sha(canonical(pin)))

    def test_legacy_version_one_result_bytes_and_two_tool_policy_are_unchanged(self):
        pin, args = vector('pinned_skill', 1)
        result = validate(pin, args)
        expected = {'version': 1, 'verdict': 'pass', 'basis': 'query_argument_consistency',
            'model': 'selected-model', 'reasoning': 'medium', 'prompt_hash': sha(PROMPT), 'tools': [FIXTURE, SKILL],
            'argv_hash': sha(canonical(args)), 'command_line_hash': sha(subprocess.list2cmdline(args)),
            'cli_path_hash': sha(CLI), 'cwd_hash': sha(CWD),
            'settings_hash': sha(canonical({'fastMode': False, 'disableAllHooks': True})),
            'mcp_config_hash': sha(args[args.index('--mcp-config') + 1]),
            'expected_hash': sha(canonical(pin)), 'creationflags': 0x08000006,
            'coverage': {'os_boundary': 'unknown', 'image': 'unknown', 'provider_acceptance': 'unknown', 'internal_reasoning': 'unknown'}}
        self.assertEqual(canonical(result).encode(), canonical(expected).encode())
        fixture_pin, fixture_args = vector('fixture_only', 1)
        with self.assertRaisesRegex(ValueError, '^invalid_query_dispatch$'):
            validate(fixture_pin, fixture_args)
        pin['tool_policy'] = 'pinned_skill'
        with self.assertRaises(ValueError):
            validate(pin, args)

    def test_policy_and_inventory_cannot_be_swapped_or_extended(self):
        for policy in ('fixture_only', 'pinned_skill'):
            pin, args = vector(policy)
            for changed in ([SKILL], [], [FIXTURE, 'Bash'], list(reversed([FIXTURE, SKILL])), [FIXTURE, FIXTURE]):
                bad = copy.deepcopy(pin)
                bad['tools'] = changed
                with self.subTest(policy=policy, tools=changed), self.assertRaises(ValueError):
                    validate(bad, args)
            other = copy.deepcopy(pin)
            other['tool_policy'] = 'pinned_skill' if policy == 'fixture_only' else 'fixture_only'
            with self.assertRaises(ValueError):
                validate(other, args)

    def test_unknown_policy_version_and_schema_confusion_refuse_generically(self):
        pin, args = vector()
        mutations = [{'tool_policy': value} for value in ('', 'all', 'improver', True, None, [], {})]
        mutations += [{'version': value} for value in (True, False, 0, 3, '2', 2.0)]
        mutations += [{'role': 'improver'}, {'purpose': 'query'}]
        for change in mutations:
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, '^invalid_query_dispatch$'):
                validate(pin | change, args)
        del pin['tool_policy']
        with self.assertRaises(ValueError):
            validate(pin, args)

    def test_fixture_only_mcp_rejects_added_skill_external_or_duplicate_descriptor(self):
        pin, args = vector()
        invalid = [canonical({'mcpServers': {'fixture': {'type': 'sdk', 'name': 'fixture'}, 'skill': {'type': 'sdk', 'name': 'skill'}}}),
            canonical({'mcpServers': {'fixture': {'type': 'stdio', 'command': 'foreign'}}}),
            '{"mcpServers":{"fixture":{"type":"sdk","name":"fixture"},"fixture":{"type":"sdk","name":"fixture"}}}',
            canonical({'mcpServers': {}})]
        for config in invalid:
            changed = list(args)
            changed[changed.index('--mcp-config') + 1] = config
            with self.subTest(config=config), self.assertRaisesRegex(ValueError, '^invalid_query_dispatch$'):
                validate(pin, changed)

    def test_new_policy_keeps_model_prompt_settings_and_flag_grammar_closed(self):
        pin, args = vector()
        for flag, value in (('--model', 'foreign'), ('--effort', 'low'), ('--system-prompt', 'changed'),
                ('--allowedTools', FIXTURE + ',' + SKILL), ('--settings', '{"fastMode":0,"disableAllHooks":true}')):
            changed = list(args)
            changed[changed.index(flag) + 1] = value
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                validate(pin, changed)
        for flag in ('--resume', '--thinking', '--plugin-dir'):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                validate(pin, args + [flag, 'foreign'])

    def test_results_are_defensive_and_contain_no_prompt_paths_or_raw_config(self):
        pin, args = vector()
        before = canonical(pin), canonical(args)
        result = validate(pin, args)
        result['tools'].append(SKILL)
        result['coverage']['os_boundary'] = 'pass'
        again = validate(pin, args)
        self.assertEqual(again['tools'], [FIXTURE])
        self.assertEqual(again['coverage']['os_boundary'], 'unknown')
        self.assertEqual(before, (canonical(pin), canonical(args)))
        for forbidden in (PROMPT, CLI, CWD, '--settings', 'mcpServers'):
            self.assertNotIn(forbidden, canonical(again))


if __name__ == '__main__':
    unittest.main()
