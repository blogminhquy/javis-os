"""Authenticated, account-scoped recovery against a real temporary journal/inbox."""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import concurrent.futures
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

_temp = tempfile.TemporaryDirectory(prefix='zernio-status-')
os.environ['JAVIS_STATE_DIR'] = _temp.name
os.environ['JAVIS_ALLOWED_HOSTS'] = 'testserver'
import main
import zernio_bot as z
import conversations
from fastapi.testclient import TestClient


class DeliveryStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=_temp.name)
        self.addCleanup(self.tmp.cleanup)
        self.store = z.DurableState(Path(self.tmp.name) / 'state.json')
        self.account = {'id': 'acc_status', 'channel': 'zernio', 'brain': 'Brain A'}
        self.bot = {'id': 'bot_status', 'account_ids': ['acc_status']}
        self.key = z._batch_key('provider_status', 'chat_status')
        self.issue = {'id': 'issue_status', 'revision': 2, 'reason': 'unsupported_media',
                      'attempts': 0, 'next_retry_at': None, 'created_at': 1234}
        self.batch = {'processing': [{'text': 'PRIVATE CUSTOMER'}], 'reply': 'PRIVATE REPLY', 'send_key': 'PRIVATE KEY'}
        conversations.ghi_su_kien({'channel': 'zernio', 'account_id': 'acc_status', 'bot_id': 'bot_status',
            'external_chat_id': 'chat_status', 'external_message_id': 'incoming', 'sender_type': 'customer', 'text': 'test'})
        self.cid = conversations.conversation_id_of('zernio', 'acc_status', 'chat_status')
        conversations.dat_che_do(self.cid, 'human')
        self.store.save({'events': {}, 'messages': {}, 'conversations': {self.key: {
            'account_id': 'provider_status', 'javis_account_id': 'acc_status', 'bot_id': 'bot_status',
            'conversation_id': 'chat_status', 'messages': [{'text': 'already inboxed'}],
            'delivery_issue': copy.deepcopy(self.issue), 'delivery_batch': copy.deepcopy(self.batch)}}})
        patches = [patch.object(z, '_state_store', self.store),
            patch.object(main.cfgmod, 'gate_active', return_value=True),
            patch.object(main.cfgmod, 'valid_session', side_effect=lambda token: token == 'test-session'),
            patch.object(main.cfgmod, 'touch_session'), patch.object(main.cfgmod, 'renew_session', return_value=False),
            patch('channel_accounts.list_accounts', side_effect=lambda channel='', brain='': [self.account] if brain in ('', 'Brain A') else []),
            patch('chatbot_store.bots_using_account', side_effect=lambda aid: [self.bot] if aid == 'acc_status' else []),
            patch('httpx.AsyncClient', side_effect=AssertionError('unexpected external HTTP'))]
        for p in patches:
            p.start(); self.addCleanup(p.stop)
        self.client = TestClient(main.app)
        self.client.cookies.set('javis_session', 'test-session')
        self.url = '/channels/accounts/acc_status/zernio/delivery-issues'

    def resolve(self, url=None, revision=2):
        return self.client.post((url or self.url) + '/issue_status/resolve?brain=Brain%20A',
            json={'revision': revision, 'resolution': 'handled_by_staff'})

    def test_requires_login_for_both_routes(self):
        self.client.cookies.clear()
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(self.resolve().status_code, 401)

    def test_scope_and_allowlisted_metadata(self):
        r = self.client.get(self.url + '?brain=Brain%20A')
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), {'ok': True, 'issues': [dict(self.issue, conversation_id=self.cid)]})
        self.assertNotIn('PRIVATE', r.text)
        for url in (self.url.replace('acc_status', 'other'), self.url + '?brain=Brain%20B'):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 404)
            self.assertNotIn('issue_status', r.text)
        self.assertEqual(self.resolve(self.url.replace('acc_status', 'other')).status_code, 404)
        self.assertEqual(self.client.post(self.url+'/issue_status/resolve?brain=Brain%20B', json={'revision':2,'resolution':'handled_by_staff'}).status_code, 404)

    def test_resolve_once_keeps_history_human_and_never_resends_after_restart(self):
        r = self.resolve()
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.resolve().status_code, 409)
        state = z.DurableState(self.store.file_path).load()['conversations'][self.key]
        self.assertNotIn('delivery_issue', state)
        self.assertNotIn('delivery_batch', state)
        self.assertEqual(state['delivery_history'][0]['batch'], self.batch)
        self.assertEqual(state['delivery_history'][0]['issue']['revision'], 3)
        self.assertEqual(state['delivery_history'][0]['resolution'], 'handled_by_staff')
        self.assertEqual(conversations.che_do('zernio','acc_status','chat_status'), 'human')
        bot = z.ZernioBot({'account_id':'provider_status','username':'test','secret':'test','api_key':'test'}, '', AsyncMock())
        bot.account_id, bot.bot_id = 'acc_status', 'bot_status'
        bot.send_delivery = AsyncMock()
        with patch.dict(z._REGISTRY, {'provider_status':bot}, clear=True):
            asyncio.run(z._flush(self.key))
        self.assertEqual(bot.answer_fn.call_count, 0)
        self.assertEqual(bot.send_delivery.call_count, 0)
        self.assertEqual(self.client.get(self.url).json()['issues'], [])

    def test_stale_revision_reassignment_busy_and_retry_conflict(self):
        before = self.store.load()
        self.assertEqual(self.resolve(revision=1).status_code, 409)
        self.bot['id'] = 'replacement'
        self.assertEqual(self.resolve().status_code, 409)
        self.bot['id'] = 'bot_status'
        guard = self.store.conversation_lock(self.key)
        try:
            self.assertEqual(self.resolve().status_code, 409)
        finally:
            guard.close()
        self.assertEqual(self.store.load(), before)
        with self.store.transaction() as state:
            c = state['conversations'][self.key]
            c.update(c.pop('delivery_batch'))
            c['delivery_issue']['next_retry_at'] = 9999999999
        self.assertEqual(self.resolve().status_code, 409)

    def test_concurrent_resolve_has_exactly_one_winner(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(lambda _: self.resolve().status_code, range(2)))
        self.assertEqual(sorted(statuses), [200, 409])
        self.assertEqual(len(self.store.load()['conversations'][self.key]['delivery_history']), 1)

    def test_invalid_resolution_and_revision_do_not_mutate(self):
        before = self.store.load()
        for body in ({'revision': True, 'resolution':'handled_by_staff'}, {'revision':2,'resolution':'retry'}, {'revision':'2','resolution':'handled_by_staff'}):
            self.assertEqual(self.client.post(self.url+'/issue_status/resolve',json=body).status_code, 422)
        self.assertEqual(self.store.load(), before)

if __name__ == '__main__':
    unittest.main()
