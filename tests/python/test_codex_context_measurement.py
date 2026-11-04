"""Regressions for separating request context from turn-level usage."""
from _paths import ROOT, SERVER
from pathlib import Path
import tempfile
import unittest
import sessions
import compaction


class ContextMeasurementTests(unittest.TestCase):
    def test_early_request_columns_move_without_changing_conversation_sources(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'sessions.db'
            store = sessions.SessionStore(path)
            sid = store.create_session(engine='codex')
            store.set_codex_thread_id(sid, 'native-preserved')
            store.append_message(sid, 'user', 'Synthetic decision and source reference.')
            store.set_last_input_tokens(sid, 900000)
            store._conn.execute('ALTER TABLE sessions ADD COLUMN last_context_input_tokens INTEGER DEFAULT 0')
            store._conn.execute("ALTER TABLE sessions ADD COLUMN last_context_provider TEXT DEFAULT ''")
            store._conn.execute("UPDATE sessions SET last_context_input_tokens=7000,last_context_provider='codex' WHERE id=?", (sid,))
            store._conn.commit()
            store.close()
            store = sessions.SessionStore(path)
            try:
                row = store.get_session(sid)
                self.assertEqual(row['last_context_input_tokens'], 7000)
                self.assertEqual(row['last_input_tokens'], 900000)
                self.assertEqual(row['codex_thread_id'], 'native-preserved')
                self.assertEqual(store.get_messages(sid)[0]['content'], 'Synthetic decision and source reference.')
                columns = {r[1] for r in store._conn.execute('PRAGMA table_info(sessions)')}
                self.assertNotIn('last_context_input_tokens', columns)
                self.assertNotIn('last_context_provider', columns)
            finally:
                store.close()

    def test_thread_changes_invalidate_context_but_same_thread_keeps_it(self):
        with tempfile.TemporaryDirectory() as td:
            store = sessions.SessionStore(Path(td) / 'sessions.db')
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
                self.assertEqual(store.get_session(sid)['last_input_tokens'], 0)
            finally:
                store.close()

    def test_old_turn_sum_is_not_migrated_to_request_context(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sessions.db"
            store = sessions.SessionStore(path)
            sid = store.create_session(engine="codex")
            store.set_last_input_tokens(sid, 900000)
            # Simulate an existing database from before the new measurement column.
            store._conn.execute("DROP TABLE subscription_request_context")
            store._conn.commit()
            store._conn.close()
            store = sessions.SessionStore(path)
            row = store.get_session(sid)
            self.assertEqual(row["last_input_tokens"], 900000)
            self.assertEqual(row["last_context_input_tokens"], 0)
            self.assertFalse(compaction.nen_mach_thue_bao(row["last_context_input_tokens"]))
            store.set_last_context_input_tokens(sid, 7000)
            row = store.get_session(sid)
            self.assertEqual(row["last_input_tokens"], 900000)
            self.assertEqual(row["last_context_input_tokens"], 7000)
            store.clear_codex_thread_id(sid)
            row = store.get_session(sid)
            self.assertEqual(row["last_context_input_tokens"], 0)
            store._conn.close()

    def test_codex_rotation_reads_request_measurement(self):
        text = (ROOT / "server/main.py").read_text(encoding="utf-8")
        start = text.index("                if stored_codex_thread and compaction.nen_mach_thue_bao(")
        end = text.index("                ccli.session_id = stored_codex_thread or None", start)
        self.assertNotIn("_row0.get(\"last_input_tokens\")", text[start:end])
        self.assertIn("last_context_input_tokens", text[start:end])


if __name__ == "__main__":
    unittest.main()
