"""A bot at auto may request a price only from its owner's fixed contact."""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ['JAVIS_STATE_DIR'] = tempfile.mkdtemp(prefix='price-request-')

import bot_price_request as price
import turn_context
import chatbot_store
import mcp_hub


class PriceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        state = patch.object(price, 'STATE_DIR', Path(temp.name))
        state.start()
        self.addCleanup(state.stop)
        connection = patch.object(price.mcp_store, 'get_connection',
                                  return_value={'enabled': True, 'perm': 'full'})
        connection.start()
        self.addCleanup(connection.stop)
        self.bot = {'id': 'bot', 'enabled': True, 'muc_quyen': 'auto', 'accounts': ['account'],
                    'price_contact': {'account_id': 'account', 'thread_id': '123', 'label': 'Contact'}}
        self.turn = {'bot_id': 'bot', 'bot_mode': 'auto', 'kenh': 'zalo_personal',
                     'price_request_live': True,
                     'account_id': 'account', 'chat_id': 'customer', 'chat_type': 'private',
                     'message_id': '456', 'customer_question': 'Phí giải thể bao nhiêu?', 'la_chu': False}
        self.raw = {'conn': {'id': 'account', 'perm': 'full'}, 'tool': 'zalo_send_message'}
        self.send = AsyncMock(return_value=json.dumps({'success': True, 'messageId': '789'}))
        self.tokens = []
        import conversations
        history = patch.object(conversations, 'tin_gan_day', return_value=[])
        self.history = history.start()
        self.addCleanup(history.stop)
        self.request = {'service_request': self.turn['customer_question'], 'source_message_ids': ['456']}

    def tearDown(self):
        for token in reversed(self.tokens):
            turn_context.reset(token)

    def test_scoped_pricing_tools_stay_visible_in_lazy_mode(self):
        specs, routes = price.build_tools('auto', {'send': self.raw}, lambda *a, **kw: self.send)
        visible, dispatch = mcp_hub._apply_lazy(specs, routes, force=True)
        names = {spec['fn'] for spec in specs}
        self.assertTrue(names.issubset({spec['fn'] for spec in visible}))
        self.assertTrue(names.issubset(dispatch))
        self.send.assert_not_called()

    async def call(self, turn=None, args=None):
        self.tokens.append(turn_context.bind(self.turn if turn is None else turn))
        spec, entry = price.build('auto', {'send': self.raw}, lambda *a, **kw: self.send)
        with patch.object(chatbot_store, 'get_bot', return_value=self.bot):
            actual = self.turn if turn is None else turn
            request = {'service_request': actual['customer_question'],
                       'source_message_ids': [str(actual['message_id'])]}
            return await entry['call'](request if args is None else args)

    async def test_quoted_url_keeps_reply_target_instead_of_sending_link_card(self):
        from channels import zalo_personal as channel
        import zalo_personal_channel
        with patch.object(channel, '_send_link', new_callable=AsyncMock) as link, \
             patch.object(zalo_personal_channel, '_goi', new_callable=AsyncMock,
                          return_value={'success': True, 'messageId': 'receipt'}) as send:
            ok, error = await channel._gui_mot({'id': 'account'}, 'customer',
                                              'Xem https://example.com/ho-so', 'private', reply_to='123')
        self.assertTrue(ok, error)
        link.assert_not_awaited()
        self.assertEqual(send.call_args.args[1], 'zalo_send_message')
        self.assertEqual(send.call_args.args[2]['replyToMsgId'], '123')

    async def test_fixed_contact_and_original_question(self):
        result = await self.call()
        self.assertTrue(json.loads(result)['ok'])
        args = self.send.call_args.args[0]
        self.assertEqual(args['threadId'], '123')
        self.assertEqual(args['threadType'], 0)
        self.assertIn(self.turn['customer_question'], args['text'])
        self.assertNotIn('Hội thoại khách:', args['text'])
        self.assertNotIn('Tin nhắn:', args['text'])
        self.assertEqual(self.bot['muc_quyen'], 'auto')

    async def handoff(self, args=None, turn=None, guard=None):
        import bot_case_handoff
        self.tokens.append(turn_context.bind(turn or dict(self.turn, customer_question='Làm cho a nhé')))
        if not self.history.return_value:
            self.history.return_value = [
                {'id': 1, 'external_message_id': '450', 'sender_type': 'customer', 'message_type': 'text',
                 'text': 'Công ty 0000000001 cần cập nhật chủ sở hữu hưởng lợi và ngành nghề.'},
                {'id': 2, 'external_message_id': '451', 'sender_type': 'human', 'message_type': 'text',
                 'text': 'Phí 1.080.000 đồng đã gồm VAT 8%.'},
                {'id': 3, 'external_message_id': '456', 'sender_type': 'customer', 'message_type': 'text',
                 'text': 'Làm cho a nhé'}]
        request = {'company_name': 'CÔNG TY TNHH KIỂM THỬ A', 'tax_id': '0000000001',
                   'work_items': ['Cập nhật thông tin chủ sở hữu hưởng lợi', 'Cập nhật ngành nghề'],
                   'fee_vnd': 1080000, 'fee_note': 'đã gồm VAT 8%',
                   'confirmation_source': 'current', 'source_message_ids': ['450', '451', 'current']}
        _, entry = bot_case_handoff.build('auto', {'send': dict(self.raw, spec={}),
                                                  'files': dict(self.raw, tool='zalo_send_file', spec={})},
                                          guard or (lambda *a, **kw: self.send))
        with patch.object(chatbot_store, 'get_bot', return_value=self.bot):
            return await entry['call'](request if args is None else args)

    async def test_confirmed_case_handoff_format_and_receipt(self):
        result = json.loads(await self.handoff())
        self.assertTrue(result['ok'])
        payload = self.send.await_args_list[0].args[-1]
        self.assertEqual(payload['threadId'], '123')
        self.assertEqual(payload['threadType'], 0)
        self.assertEqual(payload['text'], 'CÔNG TY TNHH KIỂM THỬ A (0000000001)\n'
                         '- Cập nhật thông tin chủ sở hữu hưởng lợi\n- Cập nhật ngành nghề\n'
                         'Phí: 1.080.000 đồng (đã gồm VAT 8%)')
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(price.STATE_DIR / 'bot_price_requests.sqlite3')) as db:
            row = db.execute('SELECT tax_id,receipt,confirmation,sources FROM case_handoffs').fetchone()
        self.assertEqual(row[:3], ('0000000001', '789', '456'))
        self.assertIn('Phí 1.080.000', row[3])

    async def test_handoff_duplicate_confirmation_on_later_turn_sends_once(self):
        first = await self.handoff()
        later = dict(self.turn, message_id='457', customer_question='Ok làm cho anh')
        self.history.return_value.append({'id': 4, 'external_message_id': '457', 'sender_type': 'customer',
                                          'message_type': 'text', 'text': 'Ok làm cho anh'})
        second = await self.handoff(turn=later)
        self.assertEqual(first, second)
        self.assertEqual(self.send.await_count, 2)  # staff handoff + customer acknowledgement, once each

    async def test_handoff_read_context_does_not_send(self):
        result = json.loads(await self.handoff(args={}))
        self.assertEqual(result['status'], 'context_ready')
        self.assertFalse(result['sent'])
        self.send.assert_not_awaited()

    def new_company_request(self, name='Công ty TNHH Kiểm Thử B'):
        self.history.return_value = [
            {'id': 1, 'external_message_id': '450', 'sender_type': 'customer', 'message_type': 'text',
             'text': 'Thành lập ' + name + ', trụ sở 123 Đường Mẫu, vốn 2 tỷ.'},
            {'id': 2, 'external_message_id': '451', 'sender_type': 'human', 'message_type': 'text',
             'text': 'Gói FULL 3.660.120 đồng gồm VAT 8%.'},
            {'id': 3, 'external_message_id': '456', 'sender_type': 'customer', 'message_type': 'text',
             'text': 'Làm cho anh nhé'}]
        return {'case_type': 'new_company', 'company_name': name,
                'work_items': ['Thành lập công ty; trụ sở 123 Đường Mẫu; vốn điều lệ 2 tỷ đồng'],
                'fee_vnd': 3660120, 'fee_note': 'gói FULL, đã gồm VAT 8%',
                'missing_information': ['Số CCCD kế toán Nguyễn Văn Mẫu'],
                'confirmation_source': 'current', 'source_message_ids': ['450', '451', 'current']}

    async def test_new_incorporation_without_tax_id_hands_over_missing_information(self):
        result = json.loads(await self.handoff(args=self.new_company_request()))
        self.assertTrue(result['ok'])
        self.assertEqual(result['tax_id'], '')
        text = self.send.await_args_list[0].args[-1]['text']
        self.assertIn('Công ty TNHH Kiểm Thử B (thành lập mới, chưa có MST)', text)
        self.assertIn('Cần bổ sung: Số CCCD kế toán Nguyễn Văn Mẫu', text)
        self.assertIn('Phí: 3.660.120 đồng', text)

    async def test_new_company_retries_deduplicate_and_other_company_stays_separate(self):
        first = self.new_company_request()
        await self.handoff(args=first)
        await self.handoff(args=dict(first, tax_id=''))
        self.assertEqual(self.send.await_count, 2)
        second = self.new_company_request('CÔNG TY TNHH HỒ SƠ KHÁC')
        await self.handoff(args=second)
        self.assertEqual(self.send.await_count, 4)

    async def test_existing_company_still_requires_tax_id(self):
        args = self.new_company_request()
        args.pop('case_type')
        self.assertTrue((await self.handoff(args=args)).startswith('ERROR:'))
        self.send.assert_not_awaited()

    async def test_new_company_name_must_be_verified_and_tax_id_cannot_be_invented(self):
        args = self.new_company_request()
        for changes in ({'company_name': 'Công ty không thuộc hồ sơ này'}, {'tax_id': '0000000002'},
                        {'missing_information': 'CCCD'}, {'case_type': 'unknown'}):
            self.assertTrue((await self.handoff(args=dict(args, **changes))).startswith('ERROR:'))
        self.send.assert_not_awaited()

    async def test_handoff_rejects_wrong_company_and_noncustomer_confirmation(self):
        await self.handoff(args={})
        base = {'company_name': 'Company', 'tax_id': '0000000001', 'work_items': ['Cập nhật'],
                'fee_vnd': 1080000, 'confirmation_source': 'current',
                'source_message_ids': ['450', '451', 'current']}
        for change in ({'tax_id': '0000000002'}, {'confirmation_source': '451'},
                       {'source_message_ids': ['wrong-chat']}, {'threadId': 'attacker'},
                       {'fee_vnd': True}, {'work_items': []}):
            result = await self.handoff(args=dict(base, **change))
            self.assertTrue(result.startswith('ERROR:'), (change, result))
        self.send.assert_not_awaited()

    async def test_handoff_timeout_is_uncertain_and_not_resent(self):
        self.send.side_effect = TimeoutError('timeout')
        first = await self.handoff()
        self.assertIn('uncertain', first)
        self.assertEqual(await self.handoff(), first)
        self.assertEqual(self.send.await_count, 1)

    async def test_handoff_real_guard_checks_connection_and_audits(self):
        connector = {'tool_meta': {'danger': ['zalo_send_message']}}
        with patch.object(mcp_hub.mcp_catalog, 'get', return_value=connector), \
             patch.object(mcp_hub, '_rate_ok', return_value=True), \
             patch.object(mcp_hub, '_audit_append') as audit, \
             patch.object(mcp_hub.mcp_client, 'call_route', self.send):
            result = await self.handoff(guard=mcp_hub._guard)
        self.assertTrue(json.loads(result)['ok'])
        self.assertEqual(audit.call_args.args[0]['mode'], 'auto')
        self.assertTrue(audit.call_args.args[0]['ok'])

    async def test_handoff_disabled_connection_never_sends(self):
        with patch.object(price.mcp_store, 'get_connection', return_value={'enabled': False, 'perm': 'full'}):
            result = await self.handoff(guard=mcp_hub._guard)
        self.assertTrue(result.startswith('ERROR:'))
        self.send.assert_not_awaited()

    def case_with_image(self):
        args = self.new_company_request()
        image = {'id': 3, 'external_message_id': '455', 'sender_type': 'customer', 'message_type': 'image',
                 'text': 'CCCD', 'metadata_json': json.dumps({'image_url': 'https://example.com/customer.jpg'})}
        self.history.return_value.insert(2, image)
        args['image_message_ids'] = ['455']
        return args

    async def fake_image_download(self, url, directory, stem):
        path = directory / (stem + '.jpg')
        path.write_bytes(b'customer-photo-bytes')
        return path, ''

    async def test_handoff_requires_case_photos_instead_of_silently_sending_text_only(self):
        args = self.case_with_image()
        args.pop('image_message_ids')
        result = json.loads(await self.handoff(args=args))
        self.assertEqual(result['status'], 'images_required')
        self.assertEqual(result['image_message_ids'], ['455'])
        self.send.assert_not_awaited()

    async def test_case_images_send_to_fixed_contact_with_receipts_and_no_duplicates(self):
        import image_vision
        import zalo_cli
        args = self.case_with_image()
        uploads = []
        async def delivered(*call_args):
            payload = call_args[-1]
            if payload.get('paths'):
                paths = [Path(p) for p in payload['paths']]
                self.assertEqual(paths[0].read_bytes(), b'customer-photo-bytes')
                self.assertEqual(payload['threadId'], '123')
                uploads.extend(paths)
                return json.dumps({'success': True, 'messageIds': ['photo-receipt']})
            return json.dumps({'success': True, 'messageId': 'text-receipt'})
        self.send.side_effect = delivered
        connector = {'tool_meta': {'danger': ['zalo_send_message', 'zalo_send_file']}}
        with patch.object(image_vision, 'fetch_image', side_effect=self.fake_image_download) as download, \
             patch.object(zalo_cli, 'home_of', return_value=str(price.STATE_DIR / 'session')), \
             patch.object(mcp_hub.mcp_catalog, 'get', return_value=connector), \
             patch.object(mcp_hub, '_rate_ok', return_value=True), \
             patch.object(mcp_hub, '_audit_append'), \
             patch.object(mcp_hub.mcp_client, 'call_route', self.send):
            first = json.loads(await self.handoff(args=args, guard=mcp_hub._guard))
            second = json.loads(await self.handoff(args=args, guard=mcp_hub._guard))
        self.assertTrue(first['ok'])
        self.assertTrue(second['ok'])
        self.assertEqual(first['attachments']['images'][0]['message_ids'], ['photo-receipt'])
        self.assertEqual(self.send.await_count, 3)
        self.assertEqual(download.await_count, 1)
        self.assertTrue(all(not p.exists() for p in uploads))

    async def test_unrelated_old_staff_and_other_chat_images_never_send(self):
        args = self.case_with_image()
        old = dict(self.history.return_value[2], external_message_id='old-photo')
        staff = dict(old, external_message_id='staff-photo', sender_type='human')
        self.history.return_value.insert(0, old)
        self.history.return_value.insert(3, staff)
        for mid in ['old-photo', 'staff-photo', 'other-chat-photo']:
            result = await self.handoff(args=dict(args, image_message_ids=[mid]))
            self.assertTrue(result.startswith('ERROR:'))
        self.send.assert_not_awaited()

    async def test_photo_timeout_reports_partial_delivery_and_never_resends(self):
        import image_vision
        import zalo_cli
        args = self.case_with_image()
        async def delivered(payload):
            if payload.get('paths'):
                raise TimeoutError('timeout')
            return json.dumps({'success': True, 'messageId': 'text-receipt'})
        self.send.side_effect = delivered
        with patch.object(image_vision, 'fetch_image', side_effect=self.fake_image_download), \
             patch.object(zalo_cli, 'home_of', return_value=str(price.STATE_DIR / 'session')):
            first = json.loads(await self.handoff(args=args))
            second = json.loads(await self.handoff(args=args))
        self.assertFalse(first['ok'])
        self.assertTrue(first['text_sent'])
        self.assertFalse(second['ok'])
        self.assertEqual(self.send.await_count, 2)

    async def test_download_failure_can_retry_without_repeating_case_text(self):
        import image_vision
        import zalo_cli
        args = self.case_with_image()
        calls = []
        async def download(url, directory, stem):
            calls.append(url)
            if len(calls) == 1:
                return None, 'temporary download failure'
            return await self.fake_image_download(url, directory, stem)
        async def delivered(payload):
            return json.dumps({'success': True, 'messageIds': ['photo']} if payload.get('paths')
                              else {'success': True, 'messageId': 'text'})
        self.send.side_effect = delivered
        with patch.object(image_vision, 'fetch_image', side_effect=download), \
             patch.object(zalo_cli, 'home_of', return_value=str(price.STATE_DIR / 'session')):
            first = json.loads(await self.handoff(args=args))
            second = json.loads(await self.handoff(args=args))
        self.assertFalse(first['ok'])
        self.assertTrue(first['text_sent'])
        self.assertTrue(second['ok'])
        self.assertEqual(self.send.await_count, 3)

    async def test_general_file_send_stays_blocked_at_auto_even_with_callback(self):
        connector = {'tool_meta': {'danger': ['zalo_send_file']}}
        with patch.object(mcp_hub.mcp_catalog, 'get', return_value=connector):
            result = await mcp_hub._guard(dict(self.raw, tool='zalo_send_file'),
                                         'other-tool', 'auto', authorize=lambda args: True)({})
        self.assertTrue(result.startswith('ERROR:'))

    async def test_existing_text_handoff_can_be_supplemented_with_photos(self):
        import image_vision
        import zalo_cli
        args = self.case_with_image()
        photo = self.history.return_value.pop(2)
        first_args = dict(args, image_message_ids=[])
        first = json.loads(await self.handoff(args=first_args))
        self.history.return_value.insert(2, photo)
        self.send.return_value = json.dumps({'success': True, 'messageIds': ['photo-receipt']})
        with patch.object(image_vision, 'fetch_image', side_effect=self.fake_image_download), \
             patch.object(zalo_cli, 'home_of', return_value=str(price.STATE_DIR / 'session')):
            second = json.loads(await self.handoff(args=args))
        self.assertTrue(second['ok'])
        self.assertEqual(second['message_id'], first['message_id'])
        self.assertEqual(self.send.await_count, 3)

    async def test_customer_acknowledgement_follows_staff_receipt_and_names_missing_documents(self):
        result = json.loads(await self.handoff(args=self.new_company_request()))
        self.assertTrue(result['customer_notified'])
        payloads = [call.args[-1] for call in self.send.await_args_list]
        self.assertEqual([payload['threadId'] for payload in payloads], ['123', 'customer'])
        self.assertIn('đã chuyển thông tin hồ sơ', payloads[-1]['text'])
        self.assertIn('CCCD kế toán Nguyễn Văn Mẫu', payloads[-1]['text'])

    async def test_ack_timeout_keeps_staff_delivery_and_does_not_resend(self):
        async def delivered(payload):
            if payload['threadId'] == 'customer':
                raise TimeoutError('ack timeout')
            return json.dumps({'success': True, 'messageId': 'staff-receipt'})
        self.send.side_effect = delivered
        first = json.loads(await self.handoff())
        second = json.loads(await self.handoff())
        self.assertFalse(first['ok'])
        self.assertTrue(first['handoff_delivered'])
        self.assertFalse(first['customer_notified'])
        self.assertEqual(first['message_id'], 'staff-receipt')
        self.assertFalse(second['customer_notified'])
        self.assertEqual(self.send.await_count, 2)

    async def test_connection_revoked_after_download_does_not_upload_or_acknowledge(self):
        import image_vision
        import zalo_cli
        args = self.case_with_image()
        connection = {'enabled': True, 'perm': 'full'}
        async def download(url, directory, stem):
            result = await self.fake_image_download(url, directory, stem)
            connection['enabled'] = False
            return result
        connector = {'tool_meta': {'danger': ['zalo_send_message', 'zalo_send_file']}}
        with patch.object(image_vision, 'fetch_image', side_effect=download), \
             patch.object(zalo_cli, 'home_of', return_value=str(price.STATE_DIR / 'session')), \
             patch.object(price.mcp_store, 'get_connection', return_value=connection), \
             patch.object(mcp_hub.mcp_catalog, 'get', return_value=connector), \
             patch.object(mcp_hub, '_rate_ok', return_value=True), \
             patch.object(mcp_hub, '_audit_append'), \
             patch.object(mcp_hub.mcp_client, 'call_route', self.send):
            result = json.loads(await self.handoff(args=args, guard=mcp_hub._guard))
        self.assertFalse(result['ok'])
        self.assertTrue(result['text_sent'])
        self.assertEqual(self.send.await_count, 1)

    async def test_multiple_images_keep_successful_receipts_when_later_image_fails(self):
        import image_vision
        import zalo_cli
        args = self.case_with_image()
        self.history.return_value.insert(3, dict(self.history.return_value[2],
                                                external_message_id='455-back'))
        args['image_message_ids'] = ['455', '455-back']
        file_sends = []
        async def delivered(payload):
            if not payload.get('paths'):
                return json.dumps({'success': True, 'messageId': 'text'})
            file_sends.append(payload)
            if len(file_sends) == 2:
                raise TimeoutError('second image timeout')
            return json.dumps({'success': True, 'messageIds': ['front-receipt']})
        self.send.side_effect = delivered
        with patch.object(image_vision, 'fetch_image', side_effect=self.fake_image_download), \
             patch.object(zalo_cli, 'home_of', return_value=str(price.STATE_DIR / 'session')):
            first = json.loads(await self.handoff(args=args))
            second = json.loads(await self.handoff(args=args))
        self.assertFalse(first['ok'])
        self.assertEqual(first['attachments']['images'][0]['message_ids'], ['front-receipt'])
        self.assertFalse(second['ok'])
        self.assertEqual(len(file_sends), 2)

    async def test_reminder_reads_context_before_sending_resolved_service(self):
        self.history.return_value = [
            {'external_message_id': '450', 'sender_type': 'customer', 'message_type': 'text',
             'text': 'Phí giải thể bao nhiêu?'},
            {'external_message_id': '454', 'sender_type': 'customer', 'message_type': 'text',
             'text': 'Phí làm giấy an ninh trật tự thì sao e?'},
            {'external_message_id': '456', 'sender_type': 'customer', 'message_type': 'text',
             'text': 'Báo phí nha e'},
            {'external_message_id': '999', 'sender_type': 'customer', 'message_type': 'text',
             'text': 'Tin đến sau lượt hiện tại'},
        ]
        turn = dict(self.turn, customer_question='Báo phí nha e')
        context = json.loads(await self.call(turn, args={}))
        self.assertTrue(context['ok'])
        self.assertFalse(context['sent'])
        self.assertEqual([row['message_id'] for row in context['messages']], ['450', '454', '456'])
        self.history.assert_called_with('zalo_personal', 'account', 'customer', 80)
        self.send.assert_not_awaited()
        result = await self.call(turn, args={
            'service_request': 'Khách cần báo phí dịch vụ làm giấy an ninh trật tự.',
            'source_message_ids': ['454', '456']})
        self.assertTrue(json.loads(result)['ok'])
        text = self.send.call_args.args[0]['text']
        self.assertIn('dịch vụ làm giấy an ninh trật tự', text)
        self.assertNotIn('giải thể', text)
        self.assertNotIn('Báo phí nha e', text)

    async def test_missing_context_never_guesses_an_older_service(self):
        self.history.return_value = [
            {'external_message_id': '450', 'sender_type': 'customer', 'message_type': 'text',
             'text': 'Phí giải thể bao nhiêu?'}]
        result = json.loads(await self.call(dict(self.turn, customer_question='Báo phí nha e'), args={}))
        self.assertEqual(len(result['messages']), 1)
        self.assertEqual(result['messages'][0]['text'], 'Báo phí nha e')
        self.send.assert_not_awaited()

    async def test_unverified_or_assistant_sources_never_send(self):
        self.history.return_value = [
            {'external_message_id': '455', 'sender_type': 'ai', 'message_type': 'text', 'text': 'Advice'},
            {'external_message_id': '456', 'sender_type': 'customer', 'message_type': 'text',
             'text': self.turn['customer_question']}]
        for source in ['455', 'other-chat-message', True, 456.0]:
            result = await self.call(args={'service_request': 'Xin báo phí giải thể.',
                                           'source_message_ids': [source]})
            self.assertTrue(result.startswith('ERROR:'))
        self.send.assert_not_awaited()

    async def test_current_external_and_stored_sources_resolve_to_same_turn(self):
        self.history.return_value = [
            {'id': 16552, 'external_message_id': '9000000000001', 'sender_type': 'customer',
             'message_type': 'text', 'text': 'Giấy vệ sinh thực phẩm thì bao nhiêu e'}]
        turn = dict(self.turn, message_id='9000000000001',
                    customer_question='Giấy vệ sinh thực phẩm thì bao nhiêu e')
        for source in ['current', '9000000000001', 9000000000001, '16552', 16552]:
            result = await self.call(turn, args={
                'service_request': 'Khách xin báo phí làm giấy vệ sinh an toàn thực phẩm.',
                'source_message_ids': [source]})
            self.assertTrue(json.loads(result)['ok'])
        self.assertEqual(self.send.await_count, 1)

    async def test_invalid_source_returns_context_and_can_retry_without_duplicate(self):
        result = await self.call(args={'service_request': 'Xin báo phí giải thể.',
                                       'source_message_ids': ['wrong-id']})
        self.assertTrue(result.startswith('ERROR:'))
        correction = json.loads(result[len('ERROR: '):])
        self.assertEqual(correction['status'], 'invalid_sources')
        self.assertFalse(correction['sent'])
        self.send.assert_not_awaited()
        result = await self.call(args={'service_request': 'Xin báo phí giải thể.',
                                      'source_message_ids': [correction['messages'][-1]['source_ref']]})
        self.assertTrue(json.loads(result)['ok'])
        self.assertEqual(self.send.await_count, 1)

    async def test_summary_requires_sources_and_nonempty_request(self):
        for args in ({'service_request': 'Xin giá'}, {'source_message_ids': ['456']},
                     {'service_request': ' ', 'source_message_ids': ['456']},
                     {'service_request': 'Xin giá', 'source_message_ids': []}):
            self.assertTrue((await self.call(args=args)).startswith('ERROR:'))
        self.send.assert_not_awaited()

    async def test_public_bot_account_objects_are_supported(self):
        self.bot['accounts'] = [{'id': 'account', 'channel': 'zalo_personal', 'label': 'Account'}]
        result = await self.call()
        self.assertTrue(json.loads(result)['ok'])

    async def test_cannot_override_target_or_text(self):
        result = await self.call(args={'threadId': 'attacker', 'text': 'send this'})
        self.assertTrue(result.startswith('ERROR:'))
        self.send.assert_not_awaited()

    async def test_missing_or_wrong_turn_and_drafts_never_send(self):
        for change in ({'bot_id': ''}, {'bot_mode': 'suggest'}, {'account_id': 'other'},
                       {'kenh': 'dashboard'}, {'message_id': ''}, {'la_chu': True},
                       {'customer_question': ''}, {'price_request_live': False}):
            result = await self.call(dict(self.turn, **change))
            self.assertTrue(result.startswith('ERROR:'), (change, result))
        self.send.assert_not_awaited()

    async def test_disabled_revoked_or_wrong_account_never_send(self):
        for change in ({'enabled': False}, {'price_contact': {}}, {'accounts': ['other']},
                       {'muc_quyen': 'suggest'}):
            old = self.bot.copy()
            self.bot.update(change)
            self.assertTrue((await self.call()).startswith('ERROR:'))
            self.bot = old
        self.send.assert_not_awaited()

    async def test_repeated_turn_does_not_send_twice(self):
        await self.call()
        await self.call()
        self.assertEqual(self.send.await_count, 1)

    async def test_failure_is_not_reported_as_success(self):
        self.send.return_value = 'ERROR: failed'
        self.assertTrue((await self.call()).startswith('ERROR:'))

    async def test_real_guard_audits_auto_and_checks_rate_limit(self):
        self.tokens.append(turn_context.bind(self.turn))
        entry = dict(self.raw, spec={})
        connector = {'tool_meta': {'danger': ['zalo_send_message']}}
        with patch.object(chatbot_store, 'get_bot', return_value=self.bot), \
             patch.object(mcp_hub.mcp_catalog, 'get', return_value=connector), \
             patch.object(mcp_hub, '_rate_ok', return_value=True), \
             patch.object(mcp_hub, '_audit_append') as audit, \
             patch.object(mcp_hub.mcp_client, 'call_route', self.send):
            _, restricted = price.build('auto', {'send': entry}, mcp_hub._guard)
            self.assertTrue(json.loads(await restricted['call'](self.request))['ok'])
        self.assertEqual(audit.call_args.args[0]['mode'], 'auto')
        self.assertTrue(audit.call_args.args[0]['ok'])
        args = self.send.call_args.args[2]
        self.assertEqual(args['threadId'], '123')

    async def test_rate_limit_and_connection_permission_are_not_bypassed(self):
        self.tokens.append(turn_context.bind(self.turn))
        connector = {'tool_meta': {'danger': ['zalo_send_message']}}
        with patch.object(chatbot_store, 'get_bot', return_value=self.bot), \
             patch.object(mcp_hub.mcp_catalog, 'get', return_value=connector), \
             patch.object(mcp_hub, '_rate_ok', return_value=False), \
             patch.object(mcp_hub.mcp_client, 'call_route', self.send):
            _, restricted = price.build('auto', {'send': self.raw}, mcp_hub._guard)
            self.assertTrue((await restricted['call'](self.request)).startswith('ERROR:'))
            denied = await mcp_hub._guard(dict(self.raw, conn={'id': 'account', 'perm': 'safe'}),
                                        'send', 'auto', authorize=lambda a: True)({})
            self.assertTrue(denied.startswith('ERROR:'))
        self.send.assert_not_awaited()

    async def test_timeout_is_uncertain_and_not_retried(self):
        self.send.side_effect = TimeoutError('timeout')
        first = await self.call()
        second = await self.call()
        self.assertIn('uncertain', first)
        self.assertEqual(second, first)
        self.assertEqual(self.send.await_count, 1)

    async def test_connection_disabled_after_discovery_never_sends(self):
        self.tokens.append(turn_context.bind(self.turn))
        connector = {'tool_meta': {'danger': ['zalo_send_message']}}
        with patch.object(chatbot_store, 'get_bot', return_value=self.bot), \
             patch.object(mcp_hub.mcp_catalog, 'get', return_value=connector), \
             patch.object(price.mcp_store, 'get_connection', return_value={'enabled': False, 'perm': 'full'}), \
             patch.object(mcp_hub.mcp_client, 'call_route', self.send):
            _, restricted = price.build('auto', {'send': self.raw}, mcp_hub._guard)
            self.assertTrue((await restricted['call'](self.request)).startswith('ERROR:'))
        self.send.assert_not_awaited()

    def test_config_saved_by_owner_keeps_auto(self):
        path = price.STATE_DIR / 'chatbots.json'
        path.write_text(json.dumps({'version': 1, 'bots': [self.bot]}), encoding='utf-8')
        with patch.object(chatbot_store, 'STORE_PATH', path):
            ok, err = chatbot_store.update_bot('bot', {'price_contact': json.dumps(self.bot['price_contact'])})
            self.assertTrue(ok, err)
            saved = chatbot_store.get_bot('bot')
            self.assertEqual(saved['price_contact'], self.bot['price_contact'])
            self.assertEqual(saved['muc_quyen'], 'auto')
            self.assertFalse(chatbot_store.update_bot('bot', {'price_contact': '[]'})[0])

    def test_cli_turn_key_preserves_host_binding(self):
        token = turn_context.bind(self.turn)
        try:
            key = turn_context.issue_key()
            self.assertEqual(turn_context.resolve_key(key), self.turn)
        finally:
            turn_context.reset(token)
        self.assertIsNone(turn_context.resolve_key(key))

    def test_owner_config_validation(self):
        self.assertEqual(price.clean_contact('{}'), {})
        for bad in ('[]', '{"thread_id":"123"}', {'account_id': '../x', 'thread_id': '123'}):
            with self.assertRaises(ValueError):
                price.clean_contact(bad)

    async def test_generic_send_stays_blocked(self):
        connector = {'tool_meta': {'danger': ['zalo_send_message']}}
        with patch.object(mcp_hub.mcp_catalog, 'get', return_value=connector):
            result = await mcp_hub._guard(self.raw, 'send', 'auto')({'threadId': '123', 'text': 'x'})
        self.assertTrue(result.startswith('ERROR:'))

    async def contact_tools(self, turn=None):
        self.tokens.append(turn_context.bind(turn or dict(self.turn, chat_id='123', sender_id='123',
                                                          message_id='contact-1')))
        _, routes = price.build_tools('auto', {'send': self.raw}, lambda *a, **kw: self.send)
        return routes

    async def test_contact_can_ask_original_customer_then_deliver_quote(self):
        sent = json.loads(await self.call())
        routes = await self.contact_tools()
        with patch.object(chatbot_store, 'get_bot', return_value=self.bot):
            pending = json.loads(await routes['javis_service_price_requests']['call']({}))['requests']
            self.assertEqual(pending[0]['id'], sent['request_id'])
            result = await routes['javis_service_price_reply']['call'](
                {'request_id': sent['request_id'], 'kind': 'ask_customer', 'text': 'Địa chỉ công ty ở đâu ạ?'})
            self.assertTrue(json.loads(result)['ok'])
            self.assertEqual(self.send.call_args.args[0]['threadId'], 'customer')
            self.assertEqual(self.send.await_count, 2)
        routes = await self.contact_tools(dict(self.turn, chat_id='123', sender_id='123', message_id='contact-2'))
        with patch.object(chatbot_store, 'get_bot', return_value=self.bot):
            result = await routes['javis_service_price_reply']['call'](
                {'request_id': sent['request_id'], 'kind': 'quote', 'text': 'Phí được xác nhận: 2 triệu.'})
            self.assertTrue(json.loads(result)['ok'])
            self.assertEqual(json.loads(await routes['javis_service_price_requests']['call']({}))['requests'], [])

    async def test_contact_message_only_sends_once_even_if_request_or_text_changes(self):
        request = json.loads(await self.call())['request_id']
        routes = await self.contact_tools()
        with patch.object(chatbot_store, 'get_bot', return_value=self.bot):
            for text in ('Địa chỉ ở đâu?', 'Công ty có doanh thu không?'):
                await routes['javis_service_price_reply']['call'](
                    {'request_id': request, 'kind': 'ask_customer', 'text': text})
        self.assertEqual(self.send.await_count, 2)  # original enquiry + one follow-up

    async def test_customer_other_sender_or_draft_cannot_use_contact_tools(self):
        request = json.loads(await self.call())['request_id']
        for changes in ({'chat_id': 'customer', 'sender_id': 'customer'},
                        {'sender_id': 'attacker'}, {'price_request_live': False}):
            routes = await self.contact_tools(dict(dict(self.turn, chat_id='123', sender_id='123'), **changes))
            with patch.object(chatbot_store, 'get_bot', return_value=self.bot):
                self.assertTrue((await routes['javis_service_price_requests']['call']({})).startswith('ERROR:'))
                result = await routes['javis_service_price_reply']['call'](
                    {'request_id': request, 'kind': 'quote', 'text': 'test'})
                self.assertTrue(result.startswith('ERROR:'))
        self.assertEqual(self.send.await_count, 1)

    async def test_contact_send_checks_real_guard_revocation_and_receipt(self):
        request = json.loads(await self.call())['request_id']
        self.tokens.append(turn_context.bind(dict(self.turn, chat_id='123', sender_id='123', message_id='reply')))
        connector = {'tool_meta': {'danger': ['zalo_send_message']}}
        self.send.return_value = 'ERROR: no receipt'
        with patch.object(chatbot_store, 'get_bot', return_value=self.bot), \
             patch.object(mcp_hub.mcp_catalog, 'get', return_value=connector), \
             patch.object(mcp_hub, '_rate_ok', return_value=True), \
             patch.object(mcp_hub, '_audit_append'), \
             patch.object(mcp_hub.mcp_client, 'call_route', self.send):
            _, routes = price.build_tools('auto', {'send': dict(self.raw, spec={})}, mcp_hub._guard)
            with patch.object(price.mcp_store, 'get_connection', return_value={'enabled': False, 'perm': 'full'}):
                result = await routes['javis_service_price_reply']['call'](
                    {'request_id': request, 'kind': 'quote', 'text': 'test'})
                self.assertTrue(result.startswith('ERROR:'))
            self.assertEqual(self.send.await_count, 1)
            self.assertEqual(len(json.loads(await routes['javis_service_price_requests']['call']({}))['requests']), 1)

    async def test_current_question_only_forwarded_once_per_actual_message(self):
        await self.call()
        result = await self.call(dict(self.turn, message_id='457',
                                     customer_question='Phí làm giấy an ninh trật tự thì sao e?'))
        self.assertTrue(json.loads(result)['ok'])
        text = self.send.call_args.args[0]['text']
        self.assertTrue(text.endswith('Phí làm giấy an ninh trật tự thì sao e?'))
        self.assertNotIn('Phí giải thể', text)
        self.assertNotIn('Earlier customer facts', text)
        await self.call(dict(self.turn, message_id='457',
                             customer_question='Phí làm giấy an ninh trật tự thì sao e?'))
        self.assertEqual(self.send.await_count, 2)

    async def test_other_bot_account_contact_or_unknown_request_cannot_receive_quote(self):
        request = json.loads(await self.call())['request_id']
        routes = await self.contact_tools()
        for change in ({'id': 'other'}, {'price_contact': {'account_id': 'account', 'thread_id': '999'}},
                       {'accounts': ['other']}):
            bot = dict(self.bot, **change)
            with patch.object(chatbot_store, 'get_bot', return_value=bot):
                result = await routes['javis_service_price_reply']['call'](
                    {'request_id': request, 'kind': 'quote', 'text': 'test'})
                self.assertTrue(result.startswith('ERROR:'))
        self.assertEqual(self.send.await_count, 1)


if __name__ == '__main__':
    unittest.main()
