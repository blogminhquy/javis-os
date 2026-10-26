"""Personal Zalo file intake: actual MCP shape, permissions and bounded network IO.

Files land in the bot brain's inbox/khach like every other bot channel, ride along with the
private-chat batch (zc.gop_tin, 0.128.0), and a downloaded file is removed when its turn is dropped.
"""
from _paths import ROOT, SERVER
import asyncio
import os
import tempfile
os.environ['JAVIS_STATE_DIR'] = tempfile.mkdtemp(prefix='zalo-file-state-')
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
import httpx
import zalo_attachments as za
import zalo_personal_channel as zc
from channels.zalo_personal import Transport

# Shape emitted by installed javis-zalo 1.2.0 normalizeMessage(), not history.
# Personal identifiers and the signed URL are anonymized for the public test.
LIVE = {'id': 'f1', 'threadId': '1234567890', 'threadType': 'dm',
        'senderId': '1234567890', 'senderName': 'Example Sender',
        'type': 'share.file', 'text': 'Sales report.xlsx', 'timestamp': 1791830597925,
        'attachment': {'type': 'share.file', 'url': 'https://files.zdn.vn/report?token=example',
                       'description': 'Sales report.xlsx'}, 'replyTo': None}

class ChunkStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b'x' * (za.MAX_BYTES // 2 + 1)
        yield b'x' * (za.MAX_BYTES // 2 + 1)

class IntakeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.inbox = self.root / 'brain' / 'inbox' / 'khach'

    async def download(self, handler, info=None):
        real_client = httpx.AsyncClient
        factory = lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)
        with patch.object(za, 'public_target', AsyncMock(return_value=('files.zdn.vn', '93.184.216.34'))), \
             patch.object(za.httpx, 'AsyncClient', factory):
            return await za.fetch_file(info or za.normalize(LIVE), self.inbox)

    def test_actual_live_shape(self):
        ev = zc.chuan_hoa_tin({'id':'a'}, LIVE, {})
        self.assertEqual(ev['message_type'], 'file')
        self.assertEqual(ev['metadata']['attachment'], {'url': LIVE['attachment']['url'], 'name':'Sales report.xlsx','size':None})

    def test_history_missing_url_and_size(self):
        info = za.normalize({k:v for k,v in LIVE.items() if k != 'attachment'})
        self.assertEqual(info['url'], '')
        self.assertIsNone(info['size'])

    def test_size_variants_and_invalid(self):
        for value, expected in [('123',123),('bad',None),(-1,0)]:
            self.assertEqual(za.normalize({'attachment':{'size':value}})['size'], expected)
        self.assertEqual(za.normalize({'content':{'href':'https://files.zdn.vn/a','title':'a.csv','fsize':22}})['size'],22)

    async def test_download_success_pinned_tls(self):
        def handler(req):
            self.assertEqual(req.url.host, '93.184.216.34')
            self.assertEqual(req.headers['host'], 'files.zdn.vn')
            self.assertEqual(req.extensions['sni_hostname'], 'files.zdn.vn')
            return httpx.Response(200, content=b'file bytes')
        saved, err = await self.download(handler)
        self.assertEqual(err, '')
        self.assertEqual(saved.read_bytes(), b'file bytes')
        self.assertEqual(saved.parent, self.inbox)
        self.assertTrue(saved.name.startswith('zalo_') and saved.name.endswith('Sales report.xlsx'))

    async def test_duplicate_filename(self):
        h=lambda req: httpx.Response(200,content=b'ok')
        got=[(await self.download(h))[0] for _ in range(4)]
        self.assertEqual(len(set(got)),4)

    async def test_traversal_name(self):
        p,_=await self.download(lambda req:httpx.Response(200,content=b'ok'), {'url':'https://files.zdn.vn/a','name':'../../evil\\x.csv','size':0})
        self.assertNotIn('..', p.name)
        self.assertNotIn('\\',p.name)
        self.assertEqual(p.parent,self.inbox)

    async def test_http_expired_and_error(self):
        for status in (403,404,410,500):
            p,e=await self.download(lambda req:httpx.Response(status))
            self.assertIsNone(p)
            self.assertIn(str(status),e)
        self.assertEqual(list(self.root.rglob('*.part')),[])

    async def test_network_error(self):
        def h(req): raise httpx.ConnectError('secret signed URL')
        p,e=await self.download(h)
        self.assertIsNone(p); self.assertIn('ConnectError',e); self.assertNotIn('secret',e)

    async def test_missing_url(self):
        p,e=await za.fetch_file({'name':'a.xlsx'},self.inbox)
        self.assertIsNone(p); self.assertIn('MCP',e)

    async def test_oversize_metadata_header_stream(self):
        called=[]
        p,e=await self.download(lambda req:called.append(req),{'url':'https://files.zdn.vn/a','size':za.MAX_BYTES+1})
        self.assertIsNone(p); self.assertFalse(called)
        for h in (lambda req:httpx.Response(200,headers={'content-length':str(za.MAX_BYTES+1)}),
                  lambda req:httpx.Response(200,stream=ChunkStream())):
            p,e=await self.download(h)
            self.assertIsNone(p); self.assertIn('20MB',e)
        self.assertEqual(list(self.root.rglob('*.part')),[])

    async def test_empty_and_redirect_limit(self):
        for h in (lambda req:httpx.Response(200,content=b''),
                  lambda req:httpx.Response(302,headers={'location':'/again'})):
            p,e=await self.download(h); self.assertIsNone(p); self.assertTrue(e)

    async def test_dns_ssrf(self):
        for ip in ('127.0.0.1','10.1.1.1','169.254.169.254','::1','192.168.1.2'):
            with patch.object(asyncio.get_running_loop(),'getaddrinfo',AsyncMock(return_value=[(2,1,6,'',(ip,443))])):
                with self.assertRaises(ValueError): await za.public_target('https://files.zdn.vn/a')
        for url in ('http://files.zdn.vn/a','https://127.0.0.1/a','https://localhost/a','https://u:p@files.zdn.vn/a','https://files.zdn.vn:444/a'):
            with self.assertRaises(ValueError): await za.public_target(url)

    async def test_redirect_checked_before_request(self):
        requests=[]
        real = za.public_target
        async def target(url):
            if url == LIVE['attachment']['url']: return 'files.zdn.vn','93.184.216.34'
            return await real(url)
        def h(req):
            requests.append(req); return httpx.Response(302,headers={'location':'https://127.0.0.1/private'})
        real_client=httpx.AsyncClient
        with patch.object(za,'public_target',target),patch.object(za.httpx,'AsyncClient',lambda **kw:real_client(transport=httpx.MockTransport(h),**kw)):
            p,e=await za.fetch_file(za.normalize(LIVE),self.inbox)
        self.assertIsNone(p); self.assertEqual(len(requests),1)

    async def test_timeout_and_partial_cleanup(self):
        async def h(req): await asyncio.sleep(.1); return httpx.Response(200,content=b'ok')
        with patch.object(za,'TIMEOUT',.01):
            p,e=await self.download(h)
        self.assertIsNone(p); self.assertIn('TimeoutError',e)
        self.assertEqual(list(self.root.rglob('*.part')),[])

    async def test_symlink_directory(self):
        other = self.root/'other'; other.mkdir()
        self.inbox.parent.mkdir(parents=True)
        try:
            self.inbox.symlink_to(other,target_is_directory=True)
        except OSError:
            self.skipTest('this machine cannot create symlinks')
        p,e=await self.download(lambda req:httpx.Response(200,content=b'ok'))
        self.assertIsNone(p); self.assertEqual(list(other.iterdir()),[])

    def test_content_formats_and_invalid(self):
        for ext in za.TEXT_EXTENSIONS:
            p=self.root/('a'+ext); p.write_text('doanh thu 123')
            self.assertIn('doanh thu 123',za.turn_text(p))
        # 0.336.0: PDF, Word and Excel are read to text (zalo_attachments.turn_text + doc_text); a broken one says so.
        p=self.root/'a.xlsx'; p.write_bytes(b'PK')
        t=za.turn_text(p)
        self.assertIn('không đọc được',t); self.assertIn('Không suy đoán',t)
        p=self.root/'a.pptx'; p.write_bytes(b'PK')
        self.assertIn('chưa đọc nội dung',za.turn_text(p))
        p=self.root/'a.txt';p.write_bytes(b'\xff')
        self.assertIn('Không đọc được',za.turn_text(p))

    def file_event(self):
        return zc.chuan_hoa_tin({'id':'a'},dict(LIVE,timestamp=__import__('time').time()*1000),{})

    async def transport(self, changes=None, pre=None, permission='auto', group=False, takeover='bot', reply_when='always',
                        saved=None, ev=None, answer=None, swap_bot=False):
        ev=ev or self.file_event()
        if group: ev.update(chat_type='group', external_chat_id='g')
        ev.update(changes or {})
        answer=answer or AsyncMock(return_value={'im_lang':True})
        precheck=AsyncMock(return_value=pre)
        bot=Transport('a',[],answer,precheck_fn=precheck,
                      download_dir=lambda chat:str(self.inbox),
                      cfg_fn=lambda:{'muc_quyen':permission,'reply_when':reply_when})
        async def fetch_impl(*a):
            if swap_bot: zc._BOTS['a']=object()     # bot turned off while the file was downloading
            return (saved,'' if saved else 'link hết hạn')
        fetch=AsyncMock(side_effect=fetch_impl)
        with patch.dict(zc._BOTS,{'a':bot}), patch.object(zc,'ket_noi_theo_id',return_value={'id':'a'}), \
             patch.object(zc,'chu_vua_nhan_tay',return_value=False),patch.object(zc,'nhan_dien_goi',return_value=(False,False)), \
             patch('conversations.che_do',return_value=takeover),patch.object(za,'fetch_file',fetch):
            await bot.xu_ly(ev)
        return fetch, answer

    async def test_sender_denied_no_download(self):
        fetch,answer=await self.transport(pre={})
        fetch.assert_not_awaited();answer.assert_not_awaited()

    async def test_account_human_missing_sender_denied(self):
        for changes in ({'account_id':'wrong'},{'sender_type':'human'},{'sender_id':''},{'sender_id':'stranger'}):
            fetch,answer=await self.transport(changes)
            fetch.assert_not_awaited();answer.assert_not_awaited()

    async def test_permission_preserved(self):
        for permission in ('suggest','read_docs'):
            fetch,answer=await self.transport(permission=permission)
            fetch.assert_not_awaited();answer.assert_not_awaited()

    async def test_download_error_reaches_answer(self):
        fetch,answer=await self.transport()
        fetch.assert_awaited_once();answer.assert_awaited_once()
        self.assertIn('Không tải được file',answer.call_args.args[0])
        self.assertEqual(fetch.call_args.args[1],self.inbox)

    async def test_group_precheck_denied(self):
        fetch,answer=await self.transport(pre={},group=True)
        fetch.assert_not_awaited();answer.assert_not_awaited()

    async def test_successful_file_reaches_session(self):
        p=self.root/'report.csv';p.write_text('sku,total\nA,123')
        fetch,answer=await self.transport(saved=p)
        fetch.assert_awaited_once()
        self.assertIn(str(p),answer.call_args.args[0])
        self.assertIn('A,123',answer.call_args.args[0])
        self.assertEqual(answer.call_args.args[1]['account_id'],'a')

    async def test_takeover_no_download(self):
        fetch,answer=await self.transport(takeover='human')
        fetch.assert_not_awaited();answer.assert_not_awaited()

    async def test_untagged_group_no_download(self):
        fetch,answer=await self.transport(group=True,reply_when='auto')
        fetch.assert_not_awaited();answer.assert_not_awaited()

    async def test_group_allowed_download(self):
        fetch,answer=await self.transport(group=True)
        fetch.assert_awaited_once();answer.assert_awaited_once()

    async def test_real_audience_and_group_precheck(self):
        import chatbot_runtime, chatbot_store
        for cfg,meta in [({'audience':'chon','people':['owner']},{'chat_type':'private','chat_id':'stranger'}),
                         ({'groups':['allowed'],'reply_when':'always'},{'chat_type':'group','chat_id':'blocked','user_id':'u'})]:
            cfg.update(id='test',muc_quyen='auto')
            with patch.object(chatbot_store,'get_bot',return_value=cfg),patch.object(chatbot_runtime,'_ghi_nhom_cho'):
                self.assertIsNotNone(chatbot_runtime._make_precheck_fn('test')('file',meta))

    async def test_text_image_not_downloaded(self):
        for kind in ('text','image'):
            fetch,answer=await self.transport({'message_type':kind,'text':'xin chào'})
            fetch.assert_not_awaited();answer.assert_awaited_once()

    # ---- private-chat batch (zc.gop_tin) carries the files ----
    def batch(self, *kinds):
        evs=[]
        for i,k in enumerate(kinds):
            if k=='file':
                e=self.file_event()
            else:
                e=dict(self.file_event(),message_type='text',text=k,metadata={})
            e['external_message_id']=f'm{i}'
            evs.append(e)
        return zc.gop_tin(evs)

    def test_batch_keeps_files(self):
        ev=self.batch('xem giúp em','file')
        self.assertEqual(ev['message_type'],'text')
        self.assertEqual(ev['text'],'xem giúp em')
        self.assertEqual([a['name'] for a in ev['metadata']['attachments']],['Sales report.xlsx'])
        self.assertNotIn('attachment',ev['metadata'])
        only=self.batch('file','file')
        self.assertEqual(only['message_type'],'file')
        self.assertEqual(len(only['metadata']['attachments']),2)
        many=zc.gop_tin([self.file_event() for _ in range(zc.MAX_FILE_GOP+3)])
        self.assertEqual(len(many['metadata']['attachments']),zc.MAX_FILE_GOP)
        self.assertNotIn('attachments',self.batch('chào','hỏi')['metadata'])

    async def test_batched_text_and_file_reach_answer(self):
        p=self.root/'report.csv';p.write_text('sku,total\nA,123')
        fetch,answer=await self.transport(ev=self.batch('xem giúp em file này','file'),saved=p)
        fetch.assert_awaited_once();answer.assert_awaited_once()
        self.assertIn('xem giúp em file này',answer.call_args.args[0])
        self.assertIn('A,123',answer.call_args.args[0])

    async def test_batched_file_only_reaches_answer(self):
        p=self.root/'report.csv';p.write_text('x')
        fetch,answer=await self.transport(ev=self.batch('file'),saved=p)
        self.assertEqual(fetch.await_count,1);answer.assert_awaited_once()
        self.assertIn('(người dùng gửi file)',answer.call_args.args[0])

    async def test_read_only_bot_still_answers_text(self):
        fetch,answer=await self.transport(ev=self.batch('lớp 9 còn chỗ không ạ','file'),permission='suggest')
        fetch.assert_not_awaited();answer.assert_awaited_once()
        self.assertIn('lớp 9 còn chỗ không ạ',answer.call_args.args[0])
        self.assertIn('không có quyền lưu file',answer.call_args.args[0])

    async def test_batched_stranger_file_dropped_text_kept(self):
        fetch,answer=await self.transport(ev=self.batch('chào','file'),changes={'sender_id':'stranger'})
        answer.assert_awaited_once()     # the text still gets its answer
        fetch.assert_not_awaited()

    async def test_dropped_turn_removes_downloaded_file(self):
        p=self.root/'zalo_x_report.csv';p.write_text('x')
        fetch,answer=await self.transport(saved=p,swap_bot=True)
        fetch.assert_awaited_once();answer.assert_not_awaited()
        self.assertFalse(p.exists())
        p.write_text('x')
        boom=AsyncMock(side_effect=RuntimeError('engine down'))
        await self.transport(saved=p,answer=boom)     # xu_ly logs a failed turn instead of raising
        boom.assert_awaited_once()
        self.assertFalse(p.exists())

if __name__ == '__main__': unittest.main()
