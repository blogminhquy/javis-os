"""Receive-only standby subscription regressions. All HTTP and account writes are mocked."""
from _paths import ROOT
import asyncio
import importlib.util
import json
import sys
import types
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('health_standby', ROOT/'system/plugins/messenger-health/plugin.py')
health = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health)
URL = 'https://owned.example/ext/inbox-receiver/messenger/webhook'
SECRET = 'PRIVATE_SENTINEL'


class StandbyTests(unittest.TestCase):
    def setUp(self):
        self.wh = {'ok': True, 'active': True, 'fields': ['messages', 'messaging_postbacks', 'feed', 'message_reads']}
        self.ps = {'ok': True, 'found': True, 'fields': ['messages', 'messaging_postbacks', 'feed']}
        self.calls = []
        self.fail_at = 0
        self.raise_at = 0
        self.writes = []
        self.legacy_calls = []
        self.opt_in = True
        async def wh(*args): return self.wh
        async def ps(*args): return self.ps
        async def baseline(*args): return {'ok': True, 'items': []}
        async def legacy(*args):
            self.legacy_calls.append(args)
            return {'errors': []}
        account = {'id': 'a', 'label': 'Page', 'meta': {'app_id': 'app', 'webhook_url': URL, 'webhook_standby': True}}
        self.account = account
        self.modules = patch.dict(sys.modules, {
            'messenger_setup': types.SimpleNamespace(app_webhook=wh, page_subscription=ps, run_checks=baseline, repair=legacy),
            'messenger_bot': types.SimpleNamespace(GRAPH='https://graph.facebook.com/v27.0', registered=lambda: {},
                split_credentials=lambda x: {'page_id': 'page', 'access_token': SECRET, 'app_secret': SECRET}),
            'channel_accounts': types.SimpleNamespace(list_accounts=lambda **kw: [account], get_token=lambda x: SECRET,
                update_account=lambda *a: self.writes.append(a)),
            'chatbot_store': types.SimpleNamespace(bots_using_account=lambda x: []),
            'config': types.SimpleNamespace(read_settings=lambda: {'messenger': {'verify_token': SECRET}}),
        })
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.client = types.SimpleNamespace(post=self.post, get=self.get)

    async def get(self, url, **kwargs):
        return types.SimpleNamespace(status_code=403)

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        n = len(self.calls)
        if n == self.raise_at:
            raise RuntimeError(SECRET)
        good = n != self.fail_at
        if good:
            data = kwargs['data']
            if url.endswith('/subscriptions'):
                self.wh['fields'] = data['fields'].split(',')
            elif url.endswith('/subscribed_apps'):
                self.ps['fields'] = data['subscribed_fields'].split(',')
            else:
                self.fail('Unexpected outbound endpoint')
        return types.SimpleNamespace(is_success=good, status_code=200 if good else 400,
            json=lambda: {'success': True} if good else {'error': {'message': SECRET}})

    def repair(self, url=URL):
        result = asyncio.run(health._repair_standby(self.client, 'page', SECRET, 'app', SECRET, url, SECRET))
        self.assertNotIn(SECRET, json.dumps(result))
        return result

    def check(self):
        return asyncio.run(health._standby_check(self.client, 'page', SECRET, 'app', SECRET))

    def test_both_app_and_page_must_subscribe(self):
        self.assertFalse(self.check()['ok'])
        self.wh['fields'].append('standby')
        self.assertFalse(self.check()['ok'])
        self.ps['fields'].append('standby')
        self.assertTrue(self.check()['ok'])
        self.wh['active'] = False
        self.assertFalse(self.check()['ok'])
        self.assertEqual(self.calls, [])

    def test_preserves_fields_and_uses_only_subscription_endpoints(self):
        self.assertEqual(self.repair()['errors'], [])
        self.assertTrue(self.check()['ok'])
        self.assertIn('message_reads', self.wh['fields'])
        self.assertIn('feed', self.ps['fields'])
        self.assertEqual(len(self.calls), 2)
        first = self.calls[0][1]
        self.assertEqual(first['data']['callback_url'], URL)
        self.assertEqual(first['data']['verify_token'], SECRET)
        self.assertNotIn('access_token', first['data'])
        self.assertNotIn('params', first)

    def test_read_error_does_not_replace_unknown_existing_fields(self):
        self.wh = {'ok': False, 'error': SECRET}
        self.assertTrue(self.repair()['errors'])
        self.assertEqual(self.calls, [])
        result = self.check()
        self.assertFalse(result['ok'])
        self.assertNotIn(SECRET, json.dumps(result))

    def test_app_failure_does_not_modify_page(self):
        self.fail_at = 1
        self.assertTrue(self.repair()['errors'])
        self.assertEqual(len(self.calls), 1)
        self.assertNotIn('standby', self.ps['fields'])

    def test_page_failure_is_reported_and_never_mistaken_for_success(self):
        self.fail_at = 2
        self.assertTrue(self.repair()['errors'])
        self.assertFalse(self.check()['ok'])

    def test_network_exception_does_not_expose_credentials(self):
        self.raise_at = 1
        self.assertTrue(self.repair()['errors'])
        self.assertEqual(len(self.calls), 1)

    def test_non_https_is_rejected_before_mutation(self):
        self.assertTrue(self.repair('http://owned.example/webhook')['errors'])
        self.assertEqual(self.calls, [])

    def run_health(self, repair):
        import httpx
        outer = self
        class Client:
            async def __aenter__(self): return outer.client
            async def __aexit__(self, *args): pass
        with patch.object(httpx, 'AsyncClient', lambda **kw: Client()):
            result = json.loads(asyncio.run(health._run({}, repair)))
        self.assertEqual(self.writes, [])
        self.assertNotIn(SECRET, json.dumps(result))
        return result['pages'][0]

    def test_live_check_marks_opted_in_missing_standby_failed_without_posting(self):
        result = self.run_health(False)
        self.assertFalse(result['ok'])
        self.assertEqual(self.calls, [])

    def test_explicit_repair_uses_preserving_path_and_checks_result(self):
        result = self.run_health(True)
        self.assertTrue(result['ok'])
        self.assertEqual(result['repair_errors'], [])
        self.assertEqual(self.legacy_calls, [])
        self.assertEqual(len(self.calls), 2)

    def test_other_accounts_keep_existing_repair_behavior(self):
        self.account['meta'].pop('webhook_standby')
        self.assertTrue(self.run_health(True)['ok'])
        self.assertEqual(len(self.legacy_calls), 1)
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
