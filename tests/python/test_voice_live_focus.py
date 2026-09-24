"""No provider network: validate silent history restore and wake text dispatch."""
from _paths import ROOT, SERVER  # noqa: F401
import json
import ast
import asyncio
import tempfile
import types
from pathlib import Path
import unittest
import voice_live as vl
import sessions


class LiveFocusTests(unittest.IsolatedAsyncioTestCase):
    async def test_gpt_wake_text_is_the_tool_request(self):
        provider = vl.GPTLive('unused')
        await provider.send_text('Javis tìm thông tin dự án Alpha')
        events = provider.translate({'type': 'session.delegation.created',
                                     'delegation': {'target': 'client', 'id': 'task'}})
        self.assertEqual(events[-1]['args']['request'], 'Javis tìm thông tin dự án Alpha')

    async def test_focus_close_persists_final_reply_without_provider_turn_done(self):
        with tempfile.TemporaryDirectory() as directory:
            store = sessions.SessionStore(str(Path(directory) / 'sessions.db'))
            sid = store.get_or_create(None, brain='brain', engine='test', model='test')
            store.append_message(sid, 'user', 'Câu hỏi trước')
            order, frames = [], []
            delivered = asyncio.Event()
            class Provider:
                name = 'gpt-live'
                model = 'test'
                wants_reconnect = False
                async def connect(self): order.append('connect')
                async def restore_history(self, history):
                    order.append('history'); self.history = history
                def supports_async_tools(self): return True
                async def close(self): order.append('close')
                async def events(self):
                    yield {'type': 'transcript', 'role': 'assistant', 'text': 'Latest answer', 'final': False}
                    await asyncio.Event().wait()
            class Socket:
                async def accept(self): pass
                async def send_text(self, text):
                    frame = json.loads(text); frames.append(frame)
                    if frame['type'] == 'ready': order.append('ready')
                    if frame['type'] == 'transcript': delivered.set()
                async def receive(self):
                    await delivered.wait()
                    return {'text': '{"type":"stop"}'}
                async def close(self): pass
            provider = Provider()
            namespace = dict(asyncio=asyncio, json=json, WebSocket=Socket, Query=lambda x: x,
                             cfgmod=types.SimpleNamespace(gate_active=lambda: False, read_settings=lambda: {}),
                             voice_live=types.SimpleNamespace(make_provider=lambda *a, **k: provider),
                             get_store=lambda: store, _brain_key=lambda b: b)
            tree = ast.parse((SERVER / 'main.py').read_text(encoding='utf-8'))
            route = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'voice_live_ws')
            route.decorator_list = []
            exec(compile(ast.Module(body=[route], type_ignores=[]), 'live-route', 'exec'), namespace)
            try:
                await namespace['voice_live_ws'](Socket(), sid, 'brain', 'vi-VN')
                self.assertEqual(order[:3], ['connect', 'history', 'ready'])
                self.assertEqual([m['content'] for m in store.get_messages(sid)], ['Câu hỏi trước', 'Latest answer'])
            finally:
                store._conn.close()

    async def test_openai_wake_text_requests_exactly_one_response(self):
        provider = vl.OpenAIRealtime('unused')
        sent = []
        async def send(message):
            sent.append(message)
        provider._send = send
        await provider.send_text('Javis, nói tiếp nhé')
        self.assertEqual([m['type'] for m in sent], ['conversation.item.create', 'response.create'])
        self.assertEqual(sent[0]['item']['content'][0]['text'], 'Javis, nói tiếp nhé')

    async def test_restore_does_not_create_response_or_repeat_the_last_request(self):
        history = [{'role': 'user', 'content': 'tên dự án là Alpha'},
                   {'role': 'assistant', 'content': 'Em nhớ rồi.'}]
        for cls in (vl.GeminiLive, vl.OpenAIRealtime, vl.GPTLive):
            with self.subTest(provider=cls.name):
                provider = cls('unused')
                sent = []
                async def send(message):
                    sent.append(message)
                provider._send = send
                await provider.restore_history(history)
                wire = json.dumps(sent, ensure_ascii=False)
                self.assertIn('Alpha', wire)
                self.assertNotIn('response.create', wire)
                if cls is vl.GeminiLive:
                    self.assertFalse(sent[0]['clientContent']['turnComplete'])
                    self.assertEqual(sent[0]['clientContent']['turns'][1]['role'], 'model')
                elif cls is vl.OpenAIRealtime:
                    self.assertEqual(sent[1]['item']['role'], 'assistant')
                    self.assertEqual(sent[1]['item']['content'][0]['type'], 'output_text')
                else:
                    self.assertEqual(sent[0]['type'], 'session.thinking.append')

    async def test_history_budget_and_roles(self):
        provider = vl.OpenAIRealtime('unused')
        sent = []
        async def send(message):
            sent.append(message)
        provider._send = send
        await provider.restore_history([{'role': 'system', 'content': 'not history'}] +
                                       [{'role': 'user', 'content': 'x' * 3000}] * 30)
        self.assertLessEqual(len(sent), 12)
        self.assertLessEqual(sum(len(m['item']['content'][0]['text']) for m in sent), 8000)
        self.assertTrue(all(m['item']['role'] == 'user' for m in sent))

    async def test_gpt_history_keeps_latest_turn_and_valid_bounded_frames(self):
        provider = vl.GPTLive('unused')
        messages = provider.history_messages([
            {'role': 'user', 'content': 'old ' * 500},
            {'role': 'assistant', 'content': 'LATEST_CONTEXT'}])
        self.assertIn('LATEST_CONTEXT', messages[-1]['content'])
        for message in messages:
            self.assertLessEqual(len(message['content']), vl.GPT_LIVE_APPEND_MAX)
            self.assertIn(json.loads(message['content'].split('\n', 1)[1])['role'], ('user', 'assistant'))


if __name__ == '__main__':
    unittest.main()
