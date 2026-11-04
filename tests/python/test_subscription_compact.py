"""Exercise the actual changed function bodies without starting the web server."""
import ast
import asyncio
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'server'))
sys.path.append('/app/server')
import subscription_prompt as prompt
import memory_index


def subscription_function():
    tree = ast.parse((ROOT / 'server/main.py').read_text(encoding='utf-8'))
    node = next(n for n in ast.walk(tree)
                if isinstance(n, ast.AsyncFunctionDef) and n.name == '_subscription_system_prompt')
    return compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), '<subscription>', 'exec')

SUBSCRIPTION = subscription_function()


class SubscriptionTests(unittest.TestCase):
    def invoke(self, *, provider='oauth', mode='compact-v1', action='use', error=False,
               persona=False, stable=False, memory=True, skills=True, long_profile=False,
               source_error=False):
        calls = []
        profile = 'OWNER_PROTECTED_' + ('P' * 24000 if long_profile else '')
        class Adaptive:
            def prepare(self, *args):
                base = args[-1](not memory, not skills)
                calls.append(('base', base))
                if error:
                    raise RuntimeError('simulated compiler failure')
                return NS(action=action, system_prompt=base)
        def source_builder(_, **kw):
            if source_error:
                raise OSError('simulated source failure')
            return 'SOURCE:' + str(kw)
        ns = {
            '_persona': ('agent', 'test') if persona else None,
            '_legacy_system_prompt': lambda **kw: 'LEGACY',
            '_cfg_all': {'context_runtime': {'subscription_prompt_mode': mode}},
            'brain': 'fixture', '_brain_root': lambda _: '/fixture/brain',
            'system_sync': NS(ensure_synced=lambda _: calls.append('sync'),
                              mirror_skills=lambda _: calls.append('mirror')),
            'lang_mod': NS(khoi_ngon_ngu=lambda _: 'LANGUAGE_PROTECTED'),
            '_lang_qd': NS(lang='vi'), '_STABLE_CLOCK_NOTE': 'STABLE_CLOCK',
            'context_compiler': NS(dong_ho=lambda **kw: 'LIVE_CLOCK'),
            'build_adaptive_source_prompt': source_builder,
            'memory_control': NS(profile_block=lambda: profile,
                                 learning_enabled=lambda _: False,
                                 LEARNING_OFF_NOTE='LEARNING_OFF'),
            '_brain_memory_dir': lambda _: '/fixture/brain/memory',
            '_row0': {'project_id': 'project'},
            '_project_block': lambda _: 'PROJECT_PROTECTED',
            '_session_block': lambda _: 'SESSION_PROTECTED',
            '_javis_core_block': lambda _: 'CORE_PROTECTED',
            '_khoi_coding': lambda *_: 'CODING_PROTECTED',
            '_resonance_turn_enabled': lambda _: True,
            '_RESONANCE_GOAL_HINT': 'RESONANCE_PROTECTED',
            'conv_sid': 'session-123', '_TG_BOT': None,
            'build_system_prompt': lambda *a, **kw: 'OLD_SYSTEM',
            'channel_context': NS(build_channel_block=lambda *a, **kw: 'OLD_CHANNEL'),
            '_javis_port': lambda: 7777,
            '_get_adaptive_context': lambda: Adaptive(),
            'asyncio': asyncio, 'runtime_trace': None, 'user_message': 'hello',
            'store': NS(get_messages=lambda _: []),
            '_CONTEXT_RUNTIME': NS(record_runtime_event=lambda *a: calls.append('error')),
        }
        exec(SUBSCRIPTION, ns)
        result = asyncio.run(ns['_subscription_system_prompt']('codex', 'fixture-model', provider, stable))
        return result[0], calls

    def test_opt_in_only_and_cli_untouched(self):
        for kwargs in ({'mode': 'legacy'}, {'provider': 'cli'}, {'mode': None}):
            text, _ = self.invoke(**kwargs)
            self.assertIn('OLD_SYSTEM', text)
            self.assertNotIn(prompt.CONTRACT, text)

    def test_persona_keeps_own_prompt(self):
        text, calls = self.invoke(persona=True)
        self.assertEqual(text, 'LEGACY')
        self.assertEqual(calls, [])

    def test_protected_blocks_are_preserved(self):
        text, calls = self.invoke(long_profile=True)
        for marker in ('OWNER_PROTECTED_' + 'P' * 24000, 'PROJECT_PROTECTED',
                       'SESSION_PROTECTED', 'CORE_PROTECTED', 'CODING_PROTECTED',
                       'LANGUAGE_PROTECTED', 'RESONANCE_PROTECTED', 'LEARNING_OFF'):
            self.assertIn(marker, text)
        self.assertIn('mirror', calls)

    def test_compiler_failure_keeps_compact_and_restores_sources(self):
        text, calls = self.invoke(error=True)
        self.assertIn(prompt.CONTRACT, text)
        self.assertIn("'include_memory': True", text)
        self.assertIn("'include_skills': True", text)
        self.assertIn('error', calls)

    def test_no_assignment_does_not_restore_full_legacy_contract(self):
        text, _ = self.invoke(action='legacy')
        self.assertIn(prompt.CONTRACT, text)
        self.assertNotIn('OLD_SYSTEM', text)

    def test_broken_source_reader_does_not_crash_the_chat(self):
        text, calls = self.invoke(source_error=True)
        self.assertEqual(text, 'LEGACY')
        self.assertIn('error', calls)

    def test_independent_source_fallback(self):
        text, _ = self.invoke(memory=True, skills=False)
        self.assertIn("'include_memory': False", text)
        self.assertIn("'include_skills': True", text)

    def test_stable_prompt_uses_turn_header(self):
        text, _ = self.invoke(stable=True)
        self.assertNotIn('session-123', text)
        self.assertIn('STABLE_CLOCK', text)
        self.assertIn('[Phiên chat: web:<id>]', text)

    def test_active_session_and_clock(self):
        text, _ = self.invoke()
        self.assertIn('web:session-123', text)
        self.assertIn('LIVE_CLOCK', text)


class MemoryTests(unittest.TestCase):
    def test_frequent_name_short_query_and_continuation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            facts = root / 'brain/memory/facts'
            facts.mkdir(parents=True)
            for n in range(12):
                (facts / f'villago-{n}.md').write_text(
                    f'---\ntype: business\n---\nVillago resort booking decision {n}.\n', encoding='utf-8')
            (facts / 'codex.md').write_text('Codex token input optimization.', encoding='utf-8')
            index = memory_index.MemoryIndex(root / 'state')
            try:
                found = index.retrieve(root / 'brain', 'Villago', strict_relevance=True)
                self.assertTrue(found.records)
                self.assertTrue(all('villago' in x['normalized'] for x in found.records))
                found = index.retrieve(root / 'brain', 'continue', active_state=['Villago booking'], strict_relevance=True)
                self.assertTrue(found.records)
                found = index.retrieve(root / 'brain', 'Codex token input optimization',
                                       active_state=['Villago booking'], strict_relevance=True)
                self.assertTrue(found.records)
                self.assertTrue(all('codex' in x['normalized'] for x in found.records))
                found = index.retrieve(root / 'brain',
                    'Chào bạn, trả lời đúng một câu ngắn. Không cần gọi công cụ.',
                    active_state=['Villago booking'], strict_relevance=True)
                self.assertEqual(found.records, ())
                found = index.retrieve(root / 'brain', 'Trả lời ngắn gọn, Villago', strict_relevance=True)
                self.assertTrue(found.records)
            finally:
                index._conn().close()

    def test_low_score_and_unrelated_graph_results_rejected(self):
        self.assertFalse(memory_index._eligible_memory(
            {'normalized': 'token input', 'retrieval_score': .23}, ['token'], .38))
        self.assertFalse(memory_index._eligible_memory(
            {'normalized': 'villago an ngu', 'retrieval_score': .8}, ['token'], .38))
        self.assertTrue(memory_index._eligible_memory(
            {'normalized': 'codex token input', 'retrieval_score': .7}, ['token'], .38))

    def test_core_identity_survives_without_overlap(self):
        self.assertTrue(memory_index._eligible_memory(
            {'always_on': True, 'normalized': 'owner identity', 'retrieval_score': .1}, [], .9))

    def test_single_generic_match_cannot_fill_multi_topic_slots(self):
        self.assertFalse(memory_index._eligible_memory(
            {'normalized': 'skill unrelated', 'retrieval_score': .8},
            ['codex', 'token', 'skill'], .38))

    def test_real_index_returns_empty_and_retains_fallback_for_explicit_recall(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            facts = root / 'brain/memory/facts'
            facts.mkdir(parents=True)
            (facts / 'villago.md').write_text('---\ntype: business\n---\nVillago resort Da Lat bookings.\n')
            (facts / 'codex.md').write_text('---\ntype: decision\n---\nCodex token input prompt optimization.\n')
            index = memory_index.MemoryIndex(root / 'state')
            found = index.retrieve(root / 'brain', 'unrelatedquux missingtopic', strict_relevance=True)
            self.assertEqual(found.records, ())
            self.assertFalse(found.fallback_required)
            found = index.retrieve(root / 'brain', 'remember unrelatedquux missingtopic', strict_relevance=True)
            self.assertTrue(found.fallback_required)
            found = index.retrieve(root / 'brain', 'Tôi đã chốt unrelatedquux missingtopic?', strict_relevance=True)
            self.assertTrue(found.fallback_required)
            found = index.retrieve(root / 'brain', 'Codex token input prompt', strict_relevance=True)
            self.assertTrue(found.records)
            self.assertTrue(all('codex' in x['normalized'] for x in found.records))
            found = index.retrieve(root / 'brain',
                'hãy đo và rà lại tất cả rồi đề xuất giải pháp tổng thể giúp tôi',
                strict_relevance=True)
            self.assertEqual(found.records, ())
            index._conn().close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
