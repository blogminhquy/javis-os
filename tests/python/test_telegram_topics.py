"""Offline regression coverage for topic replies, topic isolation and durable jobs."""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, AsyncMock
from types import SimpleNamespace

os.environ['JAVIS_STATE_DIR'] = tempfile.mkdtemp(prefix='topics-state-')
os.environ['BRAINS_DIR'] = tempfile.mkdtemp(prefix='topics-brains-')

import telegram_topics as topics
import telegram_bot
import turn_context


class Response:
    content = b'yes'
    status_code = 200
    def __init__(self, ok=True):
        self.ok = ok
    def json(self):
        return {'ok': self.ok, 'result': {'message_id': 7}, 'description': 'topic unavailable'}


class Client:
    def __init__(self):
        self.calls = []
        self.reject_photo = False
        self.reject_all = False
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        pass
    async def post(self, url, **kwargs):
        self.calls.append((url.rsplit('/', 1)[-1], kwargs))
        return Response(not self.reject_all and not (self.reject_photo and url.endswith('sendPhoto')))


def load_plugin(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'system/plugins' / name / 'plugin.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AddressTests(unittest.TestCase):
    def test_legacy_and_other_channels(self):
        self.assertEqual(topics.payload('-100'), {'chat_id': '-100'})
        self.assertEqual(topics.conversation({'platform': 'zalo', 'chat_id': '42', 'message_thread_id': 5}), '42')
        self.assertEqual(topics.turn_destination({'kenh': 'dashboard'}, 'web:x'), 'web:x')

    def test_roundtrip_and_fail_closed(self):
        self.assertEqual(topics.payload(topics.target('-100', 12)), {'chat_id': '-100', 'message_thread_id': 12})
        for value in ['-100:topic:0', '-100:topic:no', 'web:x:topic:1']:
            with self.assertRaises(ValueError):
                topics.payload(value)
        for value in [True, -1, 1.5, '1.0']:
            with self.assertRaises(ValueError):
                topics.target('-100', value)

    def test_host_origin_keeps_topic_without_overriding_other_recipient(self):
        turn = {'kenh': 'telegram', 'chat_id': '-100', 'message_thread_id': 12}
        for requested in ['', '-100', '-100:topic:12']:
            self.assertEqual(topics.turn_destination(turn, requested), '-100:topic:12')
        self.assertEqual(topics.turn_destination(turn, '77'), '77')
        token = turn_context.bind(turn_context.from_meta('telegram', {'chat_id': '-100', 'message_thread_id': 12}, True))
        try:
            self.assertEqual(turn_context.resolve_key(turn_context.issue_key())['message_thread_id'], 12)
        finally:
            turn_context.reset(token)


class TransportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = Client()
        self.bot = telegram_bot.TelegramBot('fake', '-100', None)

    async def test_text_chunks_status_typing_and_edit(self):
        dest = '-100:topic:12'
        await self.bot._send(self.client, dest, 'x' * 4000)
        await self.bot._typing(self.client, dest)
        await self.bot._send_status(self.client, dest, 'working')
        await self.bot._edit_status(self.client, dest, 7, 'done')
        for method, kwargs in self.client.calls:
            payload = kwargs['json']
            self.assertEqual(payload['chat_id'], '-100')
            if method == 'editMessageText':
                self.assertNotIn('message_thread_id', payload)
            else:
                self.assertEqual(payload['message_thread_id'], 12)

    async def test_file_photo_audio_and_document_fallback(self):
        for suffix in ['.png', '.mp3', '.pdf']:
            with tempfile.NamedTemporaryFile(suffix=suffix) as f:
                f.write(b'file content'); f.flush()
                self.client.reject_photo = suffix == '.png'
                with patch.object(telegram_bot.httpx, 'AsyncClient', return_value=self.client):
                    ok, err = await self.bot.send_file(f.name, chat='-100:topic:12')
                self.assertTrue(ok, err)
        methods = [m for m, _ in self.client.calls]
        self.assertIn('sendPhoto', methods)
        self.assertIn('sendAudio', methods)
        self.assertIn('sendDocument', methods)
        for _, kw in self.client.calls:
            self.assertEqual(kw['data']['chat_id'], '-100')
            self.assertEqual(kw['data']['message_thread_id'], 12)

    async def test_replied_photo_keeps_topic_for_download_brain(self):
        message = {'chat': {'id': 77, 'type': 'private'}, 'message_thread_id': 12,
                   'reply_to_message': {'photo': [{'file_id': 'image'}], 'message_id': 1}}
        image_message = self.bot._anh_cua_tin_duoc_tra_loi(message)
        self.assertEqual(image_message['message_thread_id'], 12)
        self.assertEqual(topics.conversation({**image_message, 'chat_id': '77', 'platform': 'telegram'}), '77:topic:12')

    async def test_rejected_topic_never_falls_back_to_general(self):
        self.client.reject_all = True
        with patch.object(telegram_bot.httpx, 'AsyncClient', return_value=self.client):
            ok, _ = await self.bot.send_text('-100:topic:12', 'hello')
        self.assertFalse(ok)
        self.assertTrue(self.client.calls)
        self.assertTrue(all(kw['json']['message_thread_id'] == 12 for _, kw in self.client.calls))

    async def test_dispatch_queue_stop_and_callback_isolate_topics(self):
        calls = []
        async def command(cmd, arg, chat, meta):
            calls.append(chat)
            return {'reply': 'done'}
        self.bot.command_fn = command
        for topic in [12, 99]:
            meta = self.bot._build_meta({'chat': {'id': -100, 'type': 'supergroup'}, 'message_thread_id': topic})
            self.assertEqual(meta['chat_id'], '-100')
            await self.bot._dispatch(self.client, '-100', '/status', meta)
        self.assertEqual(calls, ['-100:topic:12', '-100:topic:99'])
        self.bot._xep_hang('-100:topic:12', 'first')
        self.bot._xep_hang('-100:topic:99', 'second')
        await self.bot._dispatch(self.client, '-100', '/stop', {'message_thread_id': 12})
        self.assertNotIn('-100:topic:12', self.bot._cho)
        self.assertIn('-100:topic:99', self.bot._cho)
        async def callback(data, chat):
            calls.append(chat)
            return {'text': 'selected'}
        self.bot.callback_fn = callback
        await self.bot._handle_callback(self.client, {'id': 'q', 'data': 'bs:0', 'message': {
            'chat': {'id': -100}, 'message_id': 7, 'message_thread_id': 99}})
        self.assertEqual(calls[-1], '-100:topic:99')


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        import main
        cls.main = main

    async def test_notification_sender_and_parent_allowlist(self):
        main = self.main
        settings = {'telegram': {'enabled': True, 'token': 'fake', 'chat_id': '-100'}}
        client = Client()
        with patch.object(main.cfgmod, 'read_settings', return_value=settings), patch('httpx.AsyncClient', return_value=client):
            ok, err = await main._gui_qua_kenh('-100:topic:12', 'report')
            self.assertTrue(ok, err)
            ok, _ = await main._gui_qua_kenh('-999:topic:12', 'private')
            self.assertFalse(ok)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0][1]['json']['message_thread_id'], 12)

    async def test_topic_rules_persist_clear_and_reject_non_topic(self):
        main = self.main
        original = main.cfgmod.read_settings()
        original['telegram'].update(enabled=True, token='', chat_id='-100', topic_routes={})
        main.cfgmod.write_settings(original)
        result = await main._tg_owner_command('topic', 'reminder', '-100:topic:12')
        self.assertIn('reminder', result['reply'])
        settings = main.cfgmod.read_settings()['telegram']
        self.assertEqual(settings['topic_routes']['reminder'], '-100:topic:12')
        self.assertEqual(topics.notification_destination(settings, 'reminder', '77'), '-100:topic:12')
        self.assertEqual(topics.notification_destination(settings, 'reminder', '77', explicit=True), '77')
        before = main.cfgmod.read_settings()
        await main._tg_owner_command('topic', 'incident', '-999:topic:99')
        self.assertEqual(main.cfgmod.read_settings(), before)
        await main._tg_owner_command('topic', 'incident', '-100')
        self.assertNotIn('incident', main.cfgmod.read_settings()['telegram']['topic_routes'])
        await main._tg_owner_command('topic', 'off reminder', '-100:topic:12')
        self.assertNotIn('reminder', main.cfgmod.read_settings()['telegram']['topic_routes'])

    async def test_notification_group_routes_and_explicit_topic_priority(self):
        main = self.main
        settings = {'telegram': {'enabled': True, 'token': 'fake', 'chat_id': '77,-100',
                                'owner_chat_id': '77', 'topic_routes': {'incident': '-100:topic:99'}}}
        decide = {'group': 'incident', 'verdict': 'loud'}
        send = AsyncMock(return_value=(True, ''))
        with patch.object(main.cfgmod, 'read_settings', return_value=settings), \
             patch.object(main, '_notify_decide', return_value=decide), \
             patch.object(main, '_bo_vao_hom_thu', new=AsyncMock(return_value={'id': 'inbox'})), \
             patch.object(main, '_gui_qua_kenh', new=send):
            await main._notify_owner('', 'system alert', kind='system')
            self.assertEqual(send.call_args.args[0], '-100:topic:99')
            await main._notify_owner('-100:topic:12', 'job result', kind='system')
            self.assertEqual(send.call_args.args[0], '-100:topic:12')
            settings['telegram']['topic_routes']['incident'] = '-100:topic:bad'
            send.reset_mock()
            await main._notify_owner('', 'system alert', kind='system')
            send.assert_not_called()

    async def test_file_endpoint_retains_thread_and_rejects_unknown_chat(self):
        main = self.main
        send = AsyncMock(return_value=(True, ''))
        bot = SimpleNamespace(_task=SimpleNamespace(done=lambda: False), chat_ids=['-100'], send_file=send)
        with patch.object(main, '_TG_BOT', bot):
            result = await main.telegram_send_file({'path': 'sample.png', 'chat_id': '-100', 'message_thread_id': 12})
            self.assertTrue(result['ok'])
            self.assertEqual(send.call_args.kwargs['chat'], '-100:topic:12')
            send.reset_mock()
            result = await main.telegram_send_file({'path': 'sample.png', 'chat_id': '-999:topic:12'})
            self.assertFalse(result['ok'])
            send.assert_not_called()

    async def test_real_turn_shell_separates_topic_sessions_and_host_context(self):
        main = self.main
        captures = []
        async def engine(*args, **kwargs):
            captures.append((kwargs['chat_id'], kwargs['sess'], kwargs['conv_sid'], turn_context.current()))
            return {'text': 'done', 'files': []}
        with patch.object(main, '_tg_answer_engine', new=engine), \
             patch.object(main, '_persist_turn', new=AsyncMock()), \
             patch.object(main, '_chat_provider_kenh', return_value=('anthropic-cli', 'cli', '', 'opus')):
            for topic in [12, 99, 12]:
                await main._tg_answer('hello', {'platform': 'telegram', 'chat_id': '-100', 'message_thread_id': topic})
        self.assertIs(captures[0][1], captures[2][1])
        self.assertIsNot(captures[0][1], captures[1][1])
        self.assertNotEqual(captures[0][2], captures[1][2])
        self.assertEqual(captures[0][3]['chat_id'], '-100')
        self.assertEqual(captures[0][3]['message_thread_id'], 12)

    async def test_schedule_tool_records_origin_topic(self):
        plugin = load_plugin('javis-schedule')
        captured = []
        async def post(payload, **kwargs):
            captured.append(payload)
            return 'created'
        token = turn_context.bind(turn_context.from_meta('telegram', {'chat_id': '-100', 'message_thread_id': 12}, True))
        try:
            with patch.object(plugin, '_post_reminder', side_effect=post):
                await plugin._do_create(str(ROOT / '.test-state'), {
                    'name': 'sleep', 'prompt': 'Sleep', 'schedule': '23:00', 'notify_only': True, 'chat_id': '-100'})
        finally:
            turn_context.reset(token)
        self.assertEqual(captured[0]['chat_id'], '-100:topic:12')
        self.assertEqual(json.loads(json.dumps(captured[0]))['chat_id'], '-100:topic:12')

    async def test_sessions_and_unscoped_history_are_separate(self):
        main = self.main
        one = topics.target('-100', 12)
        two = topics.target('-100', 99)
        self.assertIsNot(main._tg_session(one), main._tg_session(two))
        main._tg_session(one)['or'] = [{'content': 'private topic'}]
        self.assertIsNone(main._tg_session(two).get('or'))
        import chatbot_runtime
        meta = {'platform': 'telegram', 'chat_id': '-100', 'message_thread_id': 12, 'chat_type': 'group'}
        with patch.object(chatbot_runtime.conversations, 'tin_gan_day', side_effect=AssertionError('unscoped read')):
            self.assertEqual(chatbot_runtime.ngu_canh_nhom(meta, 'telegram', 'account'), '')
            self.assertEqual(chatbot_runtime.private_history({}, meta, 30), [])


if __name__ == '__main__':
    unittest.main()
