"""Regression tests for native workflow routing, without starting an app or LLM."""
from _paths import ROOT
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest


def extract(path, names, namespace):
    tree = ast.parse(Path(path).read_text())
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    assert len(nodes) == len(names), names
    module = ast.Module(body=nodes, type_ignores=[])
    code = 'from __future__ import annotations\n' + ast.unparse(module)
    exec(compile(code, str(path), 'exec'), namespace)


class CodexFake:
    pass


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.settings = {'model': {'main': {'provider': 'anthropic-cli', 'model': 'sonnet'}}}
        self.available = True
        self.provider_calls = []
        self.factories = []
        self.team = {'CLAUDE': 'anthropic-cli', 'CODEX': 'openai-oauth'}
        self.team.update({
            'tools_supported': lambda p: p in ('anthropic-cli', 'openai-oauth', 'openrouter'),
            'text_only_supported': lambda p: True,
            'aux_engine': SimpleNamespace(
                CLAUDE='anthropic-cli', CODEX='openai-oauth', GROK_CLI='grok-cli',
                ANTIGRAVITY='antigravity-cli', API_PROVIDERS=('openrouter',),
                availability=lambda spec, cfg: (self.available, 'unavailable'),
                _build_codex=lambda spec, base, mode, tag, profile: self.build(spec),
                _build_api=lambda spec, base, mode, tag: self.build(spec)),
            'TeamEngineUnavailable': RuntimeError,
        })
        extract(ROOT / 'server/team_engine.py', {'choose_spec', 'build_tools'}, self.team)
        self.ns = {
            '_brain_root': lambda b: Path(b),
            '_effective_main': lambda cfg: dict(cfg['model']['main']),
            'cfgmod': SimpleNamespace(read_settings=lambda: self.settings),
            '_agent_model_provider': lambda model, provider='': provider or ('openai-oauth' if (model or '').startswith('gpt') else 'anthropic-cli'),
            'team_engine': SimpleNamespace(**self.team),
            'claude_engine': self.base,
            '_write_codex_profile': lambda: None,
            '_step_grant': lambda extra: ([], []),
            '_aux_model': lambda: 'opus-aux-should-not-leak',
            '_empty_mcp_file': lambda: None,
            'plugins_host': SimpleNamespace(granted_plugin_tools=lambda t: False),
            'aux_engine': SimpleNamespace(bg_max_wall_s=lambda: 300),
        }
        extract(ROOT / 'server/main.py', {'_workflow_agent_helpers', '_workflow_reasoning'}, self.ns)

    def base(self, **kw):
        engine = SimpleNamespace(**kw)
        self.factories.append(engine)
        return engine

    def build(self, spec):
        self.provider_calls.append(dict(spec))
        return SimpleNamespace(model=spec['model'], provider=spec['provider'])

    def make(self, model=None, provider='', tools=None):
        return self.ns['_workflow_agent_helpers']('/isolated', tools)[0]('system', model, provider)

    def test_inherits_sonnet_not_auxiliary(self):
        engine = self.make()
        self.assertEqual(engine.model, 'sonnet')
        self.assertEqual(engine.javis_vault, '/isolated')
        self.assertFalse(self.provider_calls)

    def test_inherits_changed_main_on_next_call(self):
        self.make()
        self.settings['model']['main'] = {'provider': 'openai-oauth', 'model': 'gpt-6.1-sol'}
        engine = self.make()
        self.assertEqual((engine.provider, engine.model), ('openai-oauth', 'gpt-6.1-sol'))

    def test_preserves_video_opus_pin(self):
        self.assertEqual(self.make('claude-opus-5-5', 'anthropic-cli').model, 'claude-opus-5-5')

    def test_preserves_visual_gpt_pin(self):
        self.make('gpt-6.1-sol', 'openai-oauth')
        self.assertEqual(self.provider_calls[-1], {'provider': 'openai-oauth', 'model': 'gpt-6.1-sol'})

    def test_explicit_provider_retained(self):
        self.make('model-on-openrouter', 'openrouter')
        self.assertEqual(self.provider_calls[-1]['provider'], 'openrouter')

    def test_unavailable_provider_does_not_fallback(self):
        self.available = False
        with self.assertRaisesRegex(RuntimeError, 'unavailable'):
            self.make('gpt-6.1-sol', 'openai-oauth')
        self.assertFalse(self.provider_calls)

    def test_unsupported_pin_does_not_fallback(self):
        with self.assertRaises(RuntimeError):
            self.make('unsupported', 'unknown-provider')
        self.assertFalse(self.provider_calls)

    def test_gated_background_retains_claude_tool_isolation(self):
        engine = self.make(tools=['Read'])
        self.assertEqual(engine.allowed_tools, ['Read'])
        self.assertEqual(engine.disallowed_tools, ['Bash', 'WebFetch', 'WebSearch', 'Task'])
        self.assertFalse(self.provider_calls)

    def test_reasoning_uses_existing_provider_adapters(self):
        calls = []
        self.ns.update(CodexCLI=CodexFake,
                       _codex_do_sau=lambda engine, level, prompt: calls.append(('codex', level)) or prompt,
                       _team_reasoning=lambda engine, level, prompt: calls.append(('other', level)) or prompt)
        self.assertEqual(self.ns['_workflow_reasoning'](CodexFake(), 'medium', 'copy'), 'copy')
        self.assertEqual(self.ns['_workflow_reasoning'](SimpleNamespace(), 'low', 'copy'), 'copy')
        self.assertEqual(calls, [('codex', 'medium'), ('other', 'low')])

    def test_graph_forwards_effort_without_retry(self):
        levels = []
        events = []
        class Engine:
            async def query(self, prompt):
                yield {'type': 'final', 'content': 'draft'}
        self.ns.update({
            'AGENT_REASONING_DEFAULT': 'medium',
            '_route_step_model': lambda router, prompt, model, sid: (model, ''),
            '_workflow_reasoning': lambda eng, level, prompt: levels.append(level) or prompt,
            '_loi_het_luot_cua_buoc': lambda *args: '',
        })
        extract(ROOT / 'server/main.py', {'_run_workflow_step'}, self.ns)
        node = SimpleNamespace(agent='writer', id='one', metadata={}, verify_agent='', max_retries=0)
        async def sink(event):
            events.append(event)
        result = asyncio.run(self.ns['_run_workflow_step'](
            node, 'brief', lambda *args: Engine(), lambda *args: ('Writer', 'system', '', ''),
            sink, reasoning_for=lambda slug: 'medium'))
        self.assertEqual(result['output'], 'draft')
        self.assertEqual(levels, ['medium'])
        self.assertFalse(any(e['type'] == 'step_retry' for e in events))

    def test_legacy_and_graph_use_effort_adapter(self):
        tree = ast.parse((ROOT / 'server/main.py').read_text())
        for name in ('_execute_workflow_raw', '_run_workflow_step'):
            node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
            calls = [n for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == '_workflow_reasoning']
            self.assertEqual(len(calls), 2, name)  # writer and optional checker


if __name__ == '__main__':
    unittest.main()
