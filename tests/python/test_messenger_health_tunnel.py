"""Quick-tunnel callback and reachability regressions. No real HTTP or account writes."""
from _paths import ROOT
import asyncio
import importlib.util
import json
import sys
import types
import unittest
from unittest.mock import patch

import httpx

spec = importlib.util.spec_from_file_location('messenger_health_tunnel', ROOT/'system/plugins/messenger-health/plugin.py')
health = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health)

OLD = 'https://old.trycloudflare.com/ext/inbox-receiver/messenger/webhook'
NEW = 'https://new.trycloudflare.com/ext/inbox-receiver/messenger/webhook'


class TunnelHealthTests(unittest.TestCase):
    def setUp(self):
        self.state = {'enabled': True, 'mode': 'quick', 'state': 'running', 'url': 'https://new.trycloudflare.com'}
        self.remote = types.SimpleNamespace(MANAGER=types.SimpleNamespace(status=lambda: self.state))
        self.modules = patch.dict(sys.modules, {'remote_tunnel': self.remote})
        self.modules.start()
        self.addCleanup(self.modules.stop)

    def test_live_tunnel_retains_receive_only_extension(self):
        self.assertEqual(health._expected_webhook_url(OLD), NEW)
        self.assertEqual(health._expected_webhook_url(OLD+'?v=2'), NEW+'?v=2')

    def test_custom_domain_is_never_replaced(self):
        url = 'https://owned.example/messenger/webhook'
        self.assertEqual(health._expected_webhook_url(url), url)

    def test_inactive_or_nonquick_tunnel_is_not_used(self):
        for field, value in [('enabled',False), ('mode','token'), ('state','starting')]:
            with self.subTest(field=field):
                before=self.state[field]
                self.state[field]=value
                self.assertEqual(health._expected_webhook_url(OLD), OLD)
                self.state[field]=before

    def test_untrusted_live_urls_are_not_used(self):
        for url in ['http://new.trycloudflare.com', 'https://trycloudflare.com.evil.example',
                    'https://u:p@new.trycloudflare.com', 'https://new.trycloudflare.com:1234',
                    'https://new.trycloudflare.com/other', 'https://new.trycloudflare.com/?secret=1']:
            with self.subTest(url=url):
                self.state['url']=url
                self.assertEqual(health._expected_webhook_url(OLD),OLD)

    def test_reachability_accepts_unsigned_verification_rejection(self):
        for status in (200,400,403,405):
            client = self.client(status)
            self.assertTrue(asyncio.run(health._webhook_reachable(client,NEW))['ok'])
            self.assertEqual(client.calls, [(NEW,{'timeout':8,'follow_redirects':False})])

    def test_reachability_rejects_redirect_missing_and_upstream_error(self):
        for status in (302,404,502,503,530):
            self.assertFalse(asyncio.run(health._webhook_reachable(self.client(status),NEW))['ok'])

    def test_dns_error_has_no_secret_or_raw_request(self):
        client=self.client(200,error=True)
        result=asyncio.run(health._webhook_reachable(client,NEW))
        self.assertFalse(result['ok'])
        self.assertNotIn('PRIVATE_SENTINEL',json.dumps(result))

    def client(self,status,error=False):
        class Client:
            def __init__(self): self.calls=[]
            async def __aenter__(self): return self
            async def __aexit__(self,*args): pass
            async def get(self,url,**kwargs):
                self.calls.append((url,kwargs))
                if error: raise httpx.ConnectError('PRIVATE_SENTINEL')
                return types.SimpleNamespace(status_code=status)
        return Client()

    def run_case(self,repair=False,status=403,save_ok=True):
        accounts=[{'id':x,'channel':'messenger','label':x,'meta':{'app_id':'app','webhook_url':OLD}} for x in ('a','b')]
        writes=[]; repairs=[]; checks=[]
        def save(aid,patch):
            writes.append((aid,patch))
            return save_ok,''
        async def run_checks(client,page,token,secret,app,url,running):
            checks.append(url)
            ok=bool(repairs) or url==OLD
            return {'ok':ok,'page_name':page,'items':[{'label':'Webhook','ok':ok,'detail':OLD,'fix':'repair'}]}
        async def repair_fn(client,page,token,app,secret,url,verify):
            repairs.append(url)
            return {'errors':[]}
        fakes={
            'channel_accounts':types.SimpleNamespace(list_accounts=lambda **k:accounts,get_token=lambda x:x,update_account=save),
            'chatbot_store':types.SimpleNamespace(bots_using_account=lambda x:[]),
            'config':types.SimpleNamespace(read_settings=lambda:{'messenger':{'verify_token':'PRIVATE_SENTINEL'}}),
            'messenger_bot':types.SimpleNamespace(split_credentials=lambda x:{'page_id':x,'access_token':'PRIVATE_SENTINEL','app_secret':'PRIVATE_SENTINEL'},registered=lambda:{}),
            'messenger_setup':types.SimpleNamespace(run_checks=run_checks,repair=repair_fn),
        }
        client=self.client(status)
        with patch.dict(sys.modules,fakes),patch.object(httpx,'AsyncClient',lambda **k:client):
            result=json.loads(asyncio.run(health._run({},repair)))
        self.assertNotIn('PRIVATE_SENTINEL',json.dumps(result))
        self.assertEqual(checks,[NEW,NEW])
        self.assertEqual(len(client.calls),1,'Shared app callback should be probed once per check')
        return result,writes,repairs

    def test_readonly_check_detects_stale_callback_without_mutation(self):
        result,writes,repairs=self.run_case()
        self.assertTrue(all(p['ok'] is False for p in result['pages']))
        self.assertEqual(writes,[])
        self.assertEqual(repairs,[])

    def test_explicit_repair_preserves_extension_and_updates_only_callback(self):
        result,writes,repairs=self.run_case(repair=True)
        self.assertTrue(all(p['ok'] is True for p in result['pages']))
        self.assertEqual(repairs,[NEW,NEW])
        self.assertEqual(writes,[(x,{'meta':{'webhook_url':NEW}}) for x in ('a','b')])

    def test_unreachable_callback_does_not_persist_a_success(self):
        result,writes,_=self.run_case(repair=True,status=530)
        self.assertTrue(all(p['ok'] is False for p in result['pages']))
        self.assertEqual(writes,[])

    def test_save_failure_is_reported(self):
        result,_,_=self.run_case(repair=True,save_ok=False)
        self.assertTrue(all(p['ok'] is False and p['repair_errors'] for p in result['pages']))


if __name__=='__main__':
    unittest.main(verbosity=2)
