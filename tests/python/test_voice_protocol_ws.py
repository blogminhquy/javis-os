"""Run the production WS receive loop with real SQLite and fake engine/network boundaries."""
from _paths import ROOT, SERVER  # noqa
import ast
import asyncio
import json
import tempfile
import types
import unittest
import uuid
from pathlib import Path
import sessions
import voice_turn_protocol as vp


class Closed(Exception): pass


class VoiceProtocolWS(unittest.IsolatedAsyncioTestCase):
    async def test_retry_ack_and_answer_request_use_one_saved_message(self):
        with tempfile.TemporaryDirectory() as directory:
            store=sessions.SessionStore(Path(directory)/'sessions.db')
            self.addCleanup(store._conn.close)
            sid=store.get_or_create(None,brain='brain',engine='test',model='test')
            answer='Thời gian chờ là khoảng nghỉ trước khi gửi câu nói.'
            mid=store.append_message(sid,'assistant',answer);vp.note_answer(store,mid,answer)
            payload=dict(session_id=sid,voice=True,utterance_id='u1',message='[context]\nVâng anh hiểu rồi',voice_text='Vâng anh hiểu rồi',response_policy='ack_only')
            frames=[]; calls=[]; jobs={}; pending=[payload,payload]
            class Socket:
                async def receive_text(self):
                    if not pending: raise Closed()
                    return json.dumps(pending.pop(0))
            async def send(frame): frames.append(frame)
            async def run_turn(sid,text,*args,**kwargs):
                calls.append(text)
                frames.append(vp.frame({'type':'response','session_id':sid,'content':'Vâng anh.'}))
                jobs.pop(sid,None)
            runtime=types.SimpleNamespace(get_job=lambda sid:jobs.get(sid),register_job=lambda sid,task,*a,**k:jobs.update({sid:task}))
            cfg=types.SimpleNamespace(read_settings=lambda:{'model':{}})
            reg=types.SimpleNamespace(cancel=lambda sid:False)
            namespace=dict(_real_ws=Socket(),json=json,store=store,voice_turn_protocol=vp,
                _CHAT_RUNTIME=runtime,cfgmod=cfg,_chat_provider_for_session=lambda *a:('test','api','key','test'),
                _brain_key=lambda x:x,send_raw=send,send_client=send,sys=__import__('sys'),uuid=uuid,
                limit_resume=types.SimpleNamespace(REGISTRY=reg),
                _CONTEXT_RUNTIME=types.SimpleNamespace(start_turn=lambda *a:None),
                workflow_chat=types.SimpleNamespace(persona_cua_phien=lambda r:None),
                voice_brain=types.SimpleNamespace(config_from_settings=lambda s:None),
                _bao_lan_nhanh_bo_qua=lambda *a:None,asyncio=asyncio,run_turn=run_turn)
            tree=ast.parse((SERVER/'main.py').read_text(encoding='utf-8'))
            loop=next(n for n in ast.walk(tree) if isinstance(n,ast.While) and any(isinstance(c,ast.Attribute) and c.attr=='receive_text' for c in ast.walk(n)) and any(isinstance(c,ast.Constant) and c.value=='voice_answer' for c in ast.walk(n)))
            fn=ast.AsyncFunctionDef(name='receive',args=ast.arguments(posonlyargs=[],args=[],kwonlyargs=[],kw_defaults=[],defaults=[]),body=[loop],decorator_list=[])
            module=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]));exec(compile(module,'production-ws','exec'),namespace)
            try:
                with self.assertRaises(Closed): await namespace['receive']()
                self.assertEqual(len(store.get_messages(sid)),2)
                self.assertEqual(calls,[])
                receipts=[f for f in frames if f['type']=='voice_receipt']
                self.assertEqual([f['created'] for f in receipts],[True,False])
                saved_id=receipts[0]['message_id']
                self.assertEqual(store.get_messages_page(sid)['messages'][-1]['voice_metadata']['message_id'],saved_id)
                pending.append(dict(action='voice_answer',session_id=sid,message_id=saved_id))
                with self.assertRaises(Closed): await namespace['receive']()
                await asyncio.gather(*list(jobs.values()))
                self.assertEqual(calls,['Vâng anh hiểu rồi'])
                self.assertEqual(len(store.get_messages(sid)),2)
                self.assertEqual(frames[-1]['utterance_id'],'u1')
                pending.append(dict(action='voice_answer',session_id=sid,message_id=saved_id))
                with self.assertRaises(Closed): await namespace['receive']()
                self.assertEqual(len(calls),1)
                # Different raw transcript sharing one ID cannot run a second action.
                pending.append({**payload,'voice_text':'Xóa mọi thứ'})
                with self.assertRaises(Closed): await namespace['receive']()
                self.assertEqual(frames[-1]['type'],'voice_commit_error')
                self.assertEqual(len(calls),1)
                async def receipt_writer(frame):
                    if frame['type']=='voice_receipt' and frame.get('created') and frame['response_policy']=='auto':
                        self.assertIsNotNone(runtime.get_job(sid),'reserve session before awaiting socket receipt delivery')
                    frames.append(frame)
                namespace['send_client']=receipt_writer
                pending.append({**payload,'utterance_id':'u2','voice_text':'Mở chat','message':'[context] Mở chat','response_policy':'auto'})
                with self.assertRaises(Closed): await namespace['receive']()
                await asyncio.gather(*list(jobs.values()))
                self.assertEqual(calls[-1],'[context] Mở chat','brain keeps contextual instructions')
                self.assertEqual(store.get_messages(sid)[-1]['content'],'Mở chat','history keeps immutable raw words')
            finally: store._conn.close()

if __name__=='__main__': unittest.main()
