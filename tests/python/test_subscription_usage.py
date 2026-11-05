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

    def test_codex_rotation_reads_request_measurement_with_turn_total_fallback(self):
        text = (ROOT / 'server/main.py').read_text(encoding='utf-8')
        start = text.index('                _codex_do = _row0.get("last_context_provider") == "codex"')
        end = text.index('                ccli.session_id = stored_codex_thread or None', start)
        block = text[start:end]
        self.assertIn('last_context_input_tokens', block)
        self.assertIn('last_input_tokens', block)          # fallback when nothing was measured
        self.assertIn('compaction.nen_mach_thue_bao(\n                        _codex_ctx,', block)

    def test_rotation_stays_on_by_default(self):
        # #999 tried to gate every rotation behind an opt-in plus a compact_summary that
        # subscription engines never get. Rotation is an owner decision and stays on.
        text = (ROOT / 'server/main.py').read_text(encoding='utf-8')
        self.assertNotIn('subscription_thread_rotation_mode', text)
        tree = ast.parse(text)
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and n.func.attr == 'nen_mach_thue_bao']
        self.assertGreaterEqual(len(calls), 3)

    def test_thread_changes_invalidate_measurement(self):
        from sessions import SessionStore
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp) / 'sessions.db')
            try:
                sid = store.create_session(engine='codex')
                store.set_codex_thread_id(sid, 'native-1')
                store.set_last_context_input_tokens(sid, 7000)
                store.set_codex_thread_id(sid, 'native-1')
                self.assertEqual(store.get_session(sid)['last_context_input_tokens'], 7000)
                store.set_codex_thread_id(sid, 'native-2')
                self.assertEqual(store.get_session(sid)['last_context_input_tokens'], 0)
                store.set_last_context_input_tokens(sid, 8000)
                store.clear_native_threads(sid, keep='cli')
                self.assertEqual(store.get_session(sid)['last_context_input_tokens'], 0)
                self.assertIsNone(store.get_session(sid)['codex_thread_id'])
                store.set_codex_thread_id(sid, 'native-3')
                store.set_last_context_input_tokens(sid, 9000)
                store.clear_codex_thread_id(sid)
                self.assertEqual(store.get_session(sid)['last_context_input_tokens'], 0)
                store.set_last_context_input_tokens(sid, 9000)
                store.clear_last_context_input_tokens(sid)
                self.assertEqual(store.get_session(sid)['last_context_provider'], '')
            finally:
                store.close()

    def test_measurement_row_goes_with_its_session(self):
        from sessions import SessionStore
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp) / 'sessions.db')
            try:
                sid = store.create_session(engine='codex')
                store.set_last_context_input_tokens(sid, 7000)
                store.delete(sid)
                left = store._conn.execute(
                    'SELECT COUNT(*) FROM subscription_request_context WHERE session_id=?', (sid,)).fetchone()[0]
                self.assertEqual(left, 0)
            finally:
                store.close()


if __name__ == '__main__':
    unittest.main()
