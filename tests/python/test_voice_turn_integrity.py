"""Execute the production nested voice handler with real transcript guards and SQLite storage."""
from _paths import ROOT, SERVER  # noqa: F401
import ast
import asyncio
import sys
import tempfile
import types
import unittest
from pathlib import Path
import voice_brain
import nghe_sua
import sessions


class VoiceTurnIntegrity(unittest.IsolatedAsyncioTestCase):
    async def run_turn(self, original, output, append_new=None):
        with tempfile.TemporaryDirectory() as directory:
            store = sessions.SessionStore(str(Path(directory) / 'sessions.db'))
            sid = store.get_or_create(None, brain='brain', engine='test', model='test')
            store.append_message(sid, 'user', original)
            frames, fallbacks, ui = [], [], []

            async def stream(*args):
                if append_new:
                    store.append_message(sid, 'user', append_new)
                for delta in output:
                    yield delta

            async def get_brain(*args):
                return types.SimpleNamespace(stream=stream, provider='test', model='test')

            async def send(frame):
                frames.append(frame)

            async def fallback(sid, message, *args):
                fallbacks.append(message)

            async def ui_request(*args, **kwargs):
                ui.append(args)
                return {'ok': True}

            async def persist(*args):
                pass

            proxy = types.SimpleNamespace(**vars(voice_brain))
            proxy.get_brain = get_brain
            namespace = dict(voice_brain=proxy, nghe_sua=nghe_sua, asyncio=asyncio, sys=sys,
                             store=store, send_raw=send, run_turn=fallback, _persist_turn=persist,
                             _CHAT_RUNTIME=types.SimpleNamespace(finish_job=lambda *a: None),
                             ui_targets=types.SimpleNamespace(normalize_target=lambda a, t: t),
                             ui_bridge=types.SimpleNamespace(request=ui_request))
            tree = ast.parse((SERVER / 'main.py').read_text(encoding='utf-8'))
            handler = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == 'run_voice_turn')
            exec(compile(ast.Module(body=[handler], type_ignores=[]), 'voice-handler', 'exec'), namespace)
            try:
                await namespace['run_voice_turn'](sid, original, 'brain', 'tag', None, {'loc_tap_am': True})
                return [m['content'] for m in store.get_messages(sid)], frames, fallbacks, ui
            finally:
                store._conn.close()

    async def test_destructive_first_line_cannot_overwrite_or_execute_ui(self):
        original = 'Javis, đừng mở trang Models, đưa anh về trò chuyện nhé.'
        messages, frames, fallbacks, ui = await self.run_turn(original, ['JAVIS_NGHE: Javis\n', 'Đã mở.\nJAVIS_UI: open_page models'])
        self.assertEqual(messages, [original])
        self.assertEqual(fallbacks, [original])
        self.assertFalse(ui)
        self.assertFalse([f for f in frames if f['type'] == 'stream'])

    async def test_late_rewrite_is_validated_before_speech(self):
        original = 'Đưa anh về màn hình trò chuyện nhé.'
        messages, frames, fallbacks, ui = await self.run_turn(original, ['Em đây anh.\n', 'JAVIS_NGHE: Javis'])
        self.assertEqual(messages, [original])
        self.assertEqual(fallbacks, [original])
        self.assertFalse([f for f in frames if f['type'] == 'stream'])

    async def test_missing_transcript_marker_falls_back_without_ui_action(self):
        original = 'Đừng mở trang Models.'
        messages, frames, fallbacks, ui = await self.run_turn(original, ['JAVIS_UI: open_page models'])
        self.assertEqual(messages, [original])
        self.assertEqual(fallbacks, [original])
        self.assertFalse(ui)

    async def test_noise_decision_cannot_delete_another_turn(self):
        messages, frames, _, _ = await self.run_turn('tiếng TV', ['JAVIS_BO_QUA: tạp âm'], append_new='câu mới')
        self.assertEqual(messages, ['tiếng TV', 'câu mới'])
        self.assertFalse([f for f in frames if f.get('bo_qua')])

    async def test_model_noise_guess_cannot_delete_an_accepted_utterance(self):
        messages, frames, fallbacks, _ = await self.run_turn('không', ['JAVIS_BO_QUA: tạp âm'])
        self.assertEqual(messages, ['không'])
        self.assertEqual(fallbacks, ['không'])
        self.assertFalse([f for f in frames if f.get('bo_qua')])

    async def test_spelling_correction_cannot_replace_newer_message(self):
        messages, frames, _, ui = await self.run_turn('David ơi', ['JAVIS_NGHE: Javis ơi\nEm đây anh.'], append_new='câu mới')
        self.assertEqual(messages, ['David ơi', 'câu mới'])
        self.assertFalse([f for f in frames if f['type'] == 'user_text'])
        self.assertFalse(ui)

    async def test_even_plausible_name_repair_cannot_change_committed_text(self):
        prefix = '[NGỮ CẢNH GIAO DIỆN: trang=chat]\n\n'
        messages, frames, fallbacks, _ = await self.run_turn(prefix + 'David ơi', ['JAVIS_NGHE: Javis ơi\n', 'Em đây anh.'])
        self.assertEqual(messages, [prefix + 'David ơi'])
        self.assertFalse([f for f in frames if f['type'] == 'user_text'])
        self.assertEqual(fallbacks, [prefix + 'David ơi'])

    async def test_exact_transcript_can_answer_without_fallback(self):
        original = 'Em phải trả lời vâng'
        messages, frames, fallbacks, _ = await self.run_turn(original, ['JAVIS_NGHE: ' + original + '\nVâng anh.'])
        self.assertEqual(messages, [original])
        self.assertFalse(fallbacks)
        self.assertTrue([f for f in frames if f['type'] == 'stream'])


if __name__ == '__main__':
    unittest.main()
