"""Claude rotation must use a root request, not the sum of a tool loop."""
from _paths import SERVER
import unittest
import tempfile
from pathlib import Path
from claude_agent_sdk import AssistantMessage
import claude_cli
import claude_sdk_engine
import compaction


class ClaudeRequestContextTests(unittest.TestCase):
    def setUp(self):
        claude_cli._cai_dem_cache()

    def event(self, usage, parent=None):
        msg = AssistantMessage(content=[], model='test', usage=usage, parent_tool_use_id=parent)
        events, _ = claude_sdk_engine.map_message(msg)
        return [e for e in events if e.get('type') == 'request_context']

    def test_uses_all_input_components_of_root_request(self):
        self.assertEqual(self.event({'input_tokens': 20, 'cache_read_input_tokens': 80,
                                     'cache_creation_input_tokens': 30}),
                         [{'type': 'request_context', 'input_tokens': 130}])

    def test_subagent_and_invalid_usage_are_not_context(self):
        self.assertEqual(self.event({'input_tokens': 999}, parent='tool-id'), [])
        for usage in (None, {'input_tokens': -1}, {'input_tokens': True}):
            self.assertEqual(self.event(usage), [{'type': 'request_context', 'input_tokens': 0}])

    def test_last_request_not_loop_total_controls_rotation(self):
        requests = [self.event({'input_tokens': 160000})[0]['input_tokens'] for _ in range(8)]
        self.assertGreater(sum(requests), compaction.SUBSCRIPTION_THREAD_MAX_TOKENS)
        self.assertFalse(compaction.nen_mach_thue_bao(requests[-1]))

    def test_rotation_and_prewarm_use_same_context_with_fallback(self):
        row = {'last_input_tokens': 1200000, 'last_context_provider': 'claude-code',
               'last_context_input_tokens': 160000}
        tokens = compaction.subscription_context_tokens(row, 'claude-code')
        self.assertEqual(tokens, 160000)
        self.assertFalse(compaction.nen_mach_thue_bao(tokens, msg_count=11, rotated_at=0))
        self.assertFalse(compaction.next_turn_rotates(tokens, 10, 0))
        row['last_context_provider'] = 'codex'
        self.assertEqual(compaction.subscription_context_tokens(row, 'claude-code'), 1200000)
        self.assertTrue(compaction.next_turn_rotates(1200000, 10, 0))

    def test_invalid_legacy_token_count_does_not_crash_rotation(self):
        tokens = compaction.subscription_context_tokens({'last_input_tokens': 'invalid'}, 'claude-code')
        self.assertFalse(compaction.nen_mach_thue_bao(tokens))

    def test_context_follows_claude_thread(self):
        from sessions import SessionStore
        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp) / 'sessions.db')
            try:
                sid = store.create_session()
                store.set_cli_session_id(sid, 'thread-one')
                store.set_last_context_input_tokens(sid, 160000, 'claude-code')
                store.set_cli_session_id(sid, 'thread-one')
                self.assertEqual(store.get_session(sid)['last_context_input_tokens'], 160000)
                store.set_cli_session_id(sid, 'thread-two')
                self.assertEqual(store.get_session(sid)['last_context_input_tokens'], 0)
                store.set_last_context_input_tokens(sid, 160000, 'claude-code')
                store.clear_cli_session_id(sid)
                self.assertEqual(store.get_session(sid)['last_context_input_tokens'], 0)
                store.set_cli_session_id(sid, 'thread-three')
                store.set_last_context_input_tokens(sid, 160000, 'claude-code')
                store.clear_native_threads(sid, keep='codex')
                self.assertEqual(store.get_session(sid)['last_context_input_tokens'], 0)
            finally:
                store.close()


if __name__ == '__main__':
    unittest.main()
