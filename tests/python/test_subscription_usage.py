"""Request usage must not confuse duplicated events or turn totals with context."""
from _paths import ROOT, SERVER
import ast
import unittest
import tempfile
from pathlib import Path
from subscription_usage import CodexUsage


def sample(last, total, cache=0):
    return {"last": {"inputTokens": last, "cachedInputTokens": cache, "outputTokens": 10},
            "total": {"inputTokens": total, "cachedInputTokens": cache, "outputTokens": total // last * 10}}


class UsageTests(unittest.TestCase):
    def test_legacy_totals_are_not_migrated_into_context(self):
        from sessions import SessionStore
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'sessions.db'
            store = SessionStore(path)
            sid = store.create_session()
            store.set_last_input_tokens(sid, 400000)
            store.close()
            store = SessionStore(path)
            try:
                row = store.get_session(sid)
                self.assertEqual(row['last_input_tokens'], 400000)
                self.assertEqual(row['last_context_input_tokens'], 0)
                self.assertEqual(row['last_context_provider'], '')
                store.set_last_context_input_tokens(sid, 5000)
                row = store.get_session(sid)
                self.assertEqual(row['last_context_input_tokens'], 5000)
                self.assertEqual(row['last_context_provider'], 'codex')
            finally:
                store.close()

    def test_duplicate_and_limit_notifications_are_not_requests(self):
        usage = CodexUsage({"input": 0, "cache": 0, "output": 0})
        usage.observe(sample(5000, 5000, 4000))
        usage.observe(sample(5000, 5000, 4000))
        self.assertEqual(usage.summary()["usage_event_count"], 2)
        self.assertEqual(usage.summary()["request_count"], 1)
        self.assertEqual(usage.summary()["uncached"], 1000)

    def test_many_requests_do_not_enlarge_last_request(self):
        usage = CodexUsage({"input": 0, "cache": 0, "output": 0})
        for n in range(1, 21):
            usage.observe(sample(5000, n * 5000))
        self.assertEqual(usage.input, 100000)
        self.assertEqual(usage.last_input, 5000)
        self.assertEqual(usage.summary()["request_count"], 20)

    def test_unanchored_resumed_thread_does_not_claim_complete_count(self):
        usage = CodexUsage()
        usage.observe(sample(5000, 100000))
        self.assertIsNone(usage.summary()["request_count"])
        self.assertFalse(usage.summary()["complete"])
        self.assertEqual(usage.last_input, 5000)

    def test_batched_delta_does_not_invent_request_count(self):
        usage = CodexUsage({"input": 0, "cache": 0, "output": 0})
        usage.observe(sample(5000, 15000))
        self.assertEqual(usage.input, 15000)
        self.assertIsNone(usage.summary()["request_count"])

    def test_rotation_calls_use_context_column(self):
        tree = ast.parse((ROOT / 'server/main.py').read_text(encoding='utf-8'))
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and n.func.attr == 'nen_mach_thue_bao']
        self.assertGreaterEqual(len(calls), 3)
        for call in calls:
            self.assertIn('last_context_input_tokens', ast.unparse(call.args[0]))

    def test_rotation_requires_opt_in_and_durable_summary(self):
        tree = ast.parse((ROOT / 'server/main.py').read_text(encoding='utf-8'))
        assignment = next(n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == '_allow_subscription_rotation' for t in n.targets))
        expression = compile(ast.Expression(assignment.value), '<rotation-policy>', 'eval')
        self.assertFalse(eval(expression, {'_cfg_all': {}, '_row0': {'compact_summary': 'decisions and sources'}}))
        settings = {'context_runtime': {'subscription_thread_rotation_mode': 'measured-v1'}}
        self.assertFalse(eval(expression, {'_cfg_all': settings, '_row0': {}}))
        self.assertTrue(eval(expression, {'_cfg_all': settings, '_row0': {'compact_summary': 'decisions and sources'}}))


if __name__ == '__main__':
    unittest.main()
