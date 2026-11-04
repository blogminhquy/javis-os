"""Request usage must not confuse duplicated events or turn totals with context."""
from _paths import ROOT, SERVER
import ast
import unittest
from subscription_usage import CodexUsage


def sample(last, total, cache=0):
    return {"last": {"inputTokens": last, "cachedInputTokens": cache, "outputTokens": 10},
            "total": {"inputTokens": total, "cachedInputTokens": cache, "outputTokens": total // last * 10}}


class UsageTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
