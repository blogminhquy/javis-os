"""Independent runtime-to-transport acceptance checks; no external network or DMs."""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
from contextlib import ExitStack
from pathlib import Path
import hashlib
import hmac
import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

_state = tempfile.TemporaryDirectory(prefix="zernio-integration-")
os.environ["JAVIS_STATE_DIR"] = _state.name
os.environ["JAVIS_ALLOWED_HOSTS"] = "testserver"
import chatbot_runtime as runtime
import conversations
import zernio_bot as z
from test_zernio_channel import ZernioTests


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    # Share only setup and input builders, not inherited test assertions.
    asyncSetUp = ZernioTests.asyncSetUp
    asyncTearDown = ZernioTests.asyncTearDown
    make_bot = ZernioTests.make_bot
    event = ZernioTests.event
    receive = ZernioTests.receive
    flush = ZernioTests.flush

    async def test_real_runtime_two_brains_status_sync_and_send_receipt(self):
        configs = {key: {"id": key, "name": key, "channel": "zernio", "brain": key + "-brain",
                         "enabled": True, "muc_quyen": "suggest", "nguon_tra_loi": "agent"}
                   for key in ("integration-a", "integration-b")}
        records = {}
        for index, key in enumerate(configs):
            records[key] = ({"id": f"acc_integration_{index}", "channel": "zernio"}, json.dumps({
                "account_id": f"provider-integration-{index}", "username": key,
                "secret": "sign-" + key, "api_key": "private"}))
        seen = []
        async def engine(text, meta, progress, *, channel, bot):
            seen.append((bot['id'], bot['brain'], meta['account_id'], text))
            return {"text": "reply for " + bot['brain']}
        with ExitStack() as stack:
            stack.enter_context(patch.object(runtime.chatbot_store, "get_bot", side_effect=lambda key: dict(configs[key]) if key in configs else None))
            stack.enter_context(patch.object(runtime.chatbot_store, "tokens", side_effect=lambda key: [records[key]]))
            stack.enter_context(patch.object(runtime.chatbot_store, "enabled_bots", return_value=list(configs.values())))
            stack.enter_context(patch.dict(runtime._deps, {"answer": engine}))
            # Keep real answer factory and inbox. Substitute only unrelated model
            # grounding/media/hooks so the channel integration remains offline.
            for name, value in {"_make_command_fn": None, "_make_precheck_fn": None, "_make_event_fn": None,
                                "_inbox_dir": self.directory.name, "_admin_token": "", "_rp_named_meta": {},
                                "_nho_neu_khong_goi": None, "_nen_tra_loi": True, "channel_ceiling": ""}.items():
                if name == '_rp_named_meta':
                    stack.enter_context(patch.object(runtime, name, side_effect=lambda cfg,text,meta:meta))
                else:
                    stack.enter_context(patch.object(runtime, name, return_value=value))
            stack.enter_context(patch.object(runtime, "_tra_tai_lieu", new=AsyncMock(return_value={"co":False,"nguon":[]})))
            stack.enter_context(patch.object(runtime, "plugin_context", new=AsyncMock(return_value="")))
            stack.enter_context(patch.object(runtime, "anh_cho_bot", new=AsyncMock(side_effect=lambda text,images,cfg:(text,[]))))
            stack.enter_context(patch.object(runtime, "gan_anh_cho", return_value=[]))
            stack.enter_context(patch.object(runtime.chatbot_tu_dong, "can_danh_gia", return_value=False))
            bots = []
            try:
                for index, key in enumerate(configs):
                    ok,error = runtime.start_bot(key)
                    self.assertTrue(ok,error)
                    bot = z._REGISTRY[f'provider-integration-{index}']
                    bot.send_text = AsyncMock(return_value=(False,'timeout'))
                    bots.append(bot)
                    self.assertEqual(runtime.status(key)['state'], 'running')
                    await self.receive(self.event('integration-e'+str(index),'integration-m'+str(index),bot=bot,text='only '+key),bot.secret)
                self.assertEqual(runtime.sync_all()['running'], 2)
                self.assertIs(z._REGISTRY['provider-integration-0'],bots[0])
                self.clock += 5
                for bot in bots:
                    await self.flush(bot)
                    rows = conversations.tin_gan_day('zernio',bot.account_id,'same-conversation',20)
                    self.assertFalse([r for r in rows if r['sender_type']=='ai'], rows)
                self.assertEqual(seen,[(key,key+'-brain',records[key][0]['id'],'only '+key) for key in configs])
                for bot in bots:
                    bot.send_text.return_value = (True,'')
                    await self.flush(bot)
                    rows = conversations.tin_gan_day('zernio',bot.account_id,'same-conversation',20)
                    replies = [r for r in rows if r['sender_type']=='ai']
                    self.assertEqual(len(replies),1,rows)
                    self.assertEqual(replies[0]['text'],'reply for '+configs[bot.bot_id]['brain'])
                self.assertEqual(len(seen),2)  # retry reuses journaled model output
                unknown = self.event('unassigned','unassigned',bot=bots[0])
                unknown['account']['id'] = 'not-assigned'
                self.assertEqual((await self.receive(unknown,bots[0].secret))[0],404)
                self.assertEqual(len(seen),2)
            finally:
                for key in configs:
                    runtime.stop_bot(key)

    async def test_real_takeover_release_and_takeover_inside_model(self):
        self.mode_patch.stop()  # Exercise the actual SQLite takeover store.
        await self.receive()
        cid = conversations.conversation_id_of('zernio','acc_a','same-conversation')
        self.assertTrue(conversations.dat_che_do(cid,'human')[0])
        self.clock += 5
        await self.flush()
        self.bot.answer_fn.assert_not_awaited()
        self.assertTrue(conversations.tin_theo_id('zernio','acc_a','same-conversation','m1'))
        self.assertTrue(conversations.dat_che_do(cid,'ai')[0])
        await self.receive(self.event('released','released'))
        self.clock += 5
        await self.flush()
        self.bot.send_text.assert_awaited_once()
        async def take_over(*args):
            conversations.dat_che_do(cid,'human')
            return 'must not be sent'
        self.bot.answer_fn.side_effect = take_over
        await self.receive(self.event('during','during'))
        self.clock += 5
        await self.flush()
        self.assertEqual(self.bot.send_text.await_count,1)
        conversations.dat_che_do(cid,'ai')
        self.bot.answer_fn.side_effect = None
        await self.receive(self.event('released-again','released-again'))
        self.clock += 5
        await self.flush()
        self.assertEqual(self.bot.send_text.await_count,2)

    async def test_real_timer_waits_five_seconds_from_last_arrival(self):
        import time
        self.time_patch.stop()
        self.clock = time.time()
        await self.receive()
        await asyncio.sleep(1.0)
        self.clock = time.time()
        await self.receive(self.event('timer-2','timer-2',text='last message'))
        await asyncio.sleep(4.2)
        self.bot.send_text.assert_not_awaited()
        await asyncio.sleep(1.1)
        self.bot.send_text.assert_awaited_once()
        self.assertEqual(self.bot.answer_fn.call_args.args[0],'hello\nlast message')

    async def test_node_bridge_delivers_actual_ack_through_python_auth_middleware(self):
        import http.server
        import threading
        from fastapi.testclient import TestClient
        import main
        client = TestClient(main.app)
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                response = client.post(self.path,content=self.rfile.read(int(self.headers['Content-Length'])),
                                       headers={'Authorization':self.headers.get('Authorization',''),
                                                'Content-Type':'application/json'})
                self.send_response(response.status_code)
                self.end_headers()
                self.wfile.write(response.content)
        server = http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread = threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        script = """
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {Bridge,JsonState} from './bridges/zernio/src/bridge.js';
import {createRuntimeClient} from './bridges/zernio/src/server.js';
const [event,file,url,now] = JSON.parse(process.argv[1]);
const bridge = new Bridge({secret:'secret-a',accountId:'provider-a',username:'alice',state:new JsonState(file),
 runtime:createRuntimeClient({baseUrl:url,token:'scoped'}),now:()=>now});
const raw=Buffer.from(JSON.stringify(event));
const result=bridge.receive(raw,{'x-zernio-signature':crypto.createHmac('sha256','secret-a').update(raw).digest('hex')});
assert.equal(result.status,202);
clearTimeout(bridge.timers.get('same-conversation'));
await bridge.flush('same-conversation');
assert.equal(new JsonState(file).load().conversations['same-conversation'].processing,undefined);
console.log('Node bridge accepted durable Python runtime ACK, sent no DM');
"""
        body = self.event()
        body['message'].update(platform='instagram',sentAt=body['timestamp'])
        try:
            with patch.object(main.cfgmod,'gate_active',return_value=True), patch.object(main.cfgmod,'valid_session',return_value=False), \
                 patch.dict(os.environ,{'ZERNIO_ADAPTER_TOKEN':'scoped','ZERNIO_ADAPTER_ACCOUNT_ID':'provider-a'}):
                process = await asyncio.create_subprocess_exec('node','--input-type=module','-e',script,
                    json.dumps([body,str(Path(self.directory.name)/'node-state.json'),f'http://127.0.0.1:{server.server_port}',self.clock*1000]),
                    cwd=ROOT,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
                stdout,stderr = await asyncio.wait_for(process.communicate(),20)
                self.assertEqual(process.returncode,0,stderr.decode())
                self.assertIn(b'durable Python runtime ACK',stdout)
                self.assertTrue(conversations.tin_theo_id('zernio','acc_a','same-conversation','m1'))
                self.bot.send_text.assert_not_awaited()
                self.clock += 5
                await self.flush()
                self.bot.send_text.assert_awaited_once()
        finally:
            await asyncio.to_thread(server.shutdown)
            server.server_close()
            thread.join(timeout=2)

    async def test_http_auth_hmac_adapter_and_secret_redaction(self):
        from fastapi.testclient import TestClient
        import main
        client = TestClient(main.app)
        raw = json.dumps(self.event()).encode()
        signature = hmac.new(self.bot.secret.encode(),raw,hashlib.sha256).hexdigest()
        with patch.object(main.cfgmod,'gate_active',return_value=True), patch.object(main.cfgmod,'valid_session',return_value=False):
            for sig, expected in [(signature,202),('0'*64,401)]:
                response = client.post('/webhooks/zernio',content=raw,headers={'X-Zernio-Signature':sig})
                self.assertEqual(response.status_code,expected,response.text)
                self.assertNotIn(self.bot.secret,response.text)
                self.assertNotIn('private-key',response.text)
            payload = {'conversationId':'adapter-http','account':{'id':'provider-a'},'messages':[self.event()['message']]}
            for token in ['', 'wrong']:
                with patch.dict(os.environ,{'ZERNIO_ADAPTER_TOKEN':token,'ZERNIO_ADAPTER_ACCOUNT_ID':'provider-a'}):
                    response = client.post('/zernio/inbound',json=payload,headers={'Authorization':'Bearer scoped'})
                    self.assertEqual(response.status_code,401,response.text)
            with patch.dict(os.environ,{'ZERNIO_ADAPTER_TOKEN':'scoped','ZERNIO_ADAPTER_ACCOUNT_ID':'provider-a'}):
                response = client.post('/zernio/inbound',json=payload,headers={'Authorization':'Bearer scoped'})
                self.assertEqual(response.status_code,202,response.text)
                self.assertFalse(response.json()['replySent'])
                payload['account']['id']='provider-b'
                self.assertEqual(client.post('/zernio/inbound',json=payload,headers={'Authorization':'Bearer scoped'}).status_code,403)


if __name__ == '__main__':
    unittest.main(defaultTest='IntegrationTests')
