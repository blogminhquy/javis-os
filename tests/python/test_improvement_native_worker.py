"""Startup2 worker adoption; no account, CLI, SDK client, or model invocation."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import base64
import copy
import importlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


def component(test):
    test.assertIsNotNone(importlib.util.find_spec('improvement_native_worker'), 'native worker session missing')
    return importlib.import_module('improvement_native_worker')


def packet(kind='preflight', *, scratch=r'C:\private\scratch'):
    from improvement_native_protocol import _ENV_PATHS, _ENV_FIXED
    environment = {**{key: scratch for key in _ENV_PATHS}, **_ENV_FIXED}
    environment.update(TEMP=scratch + r'\tmp', TMP=scratch + r'\tmp',
        JAVIS_STATE_DIR=scratch + r'\host-state', BRAINS_DIR=scratch + r'\empty-brains',
        OBSIDIAN_VAULT_PATH=scratch + r'\empty-vault', BRAIN_PATH=scratch + r'\empty-brain',
        SOURCES_PATH=scratch + r'\empty-sources')
    config = dict(version=1, provider='anthropic-cli', engine_id='claude-sdk', model='selected', reasoning='high',
        cli_path=r'C:\private\inert.exe', cli_hash='a' * 64, cli_version='2.1.99', sdk_version='0.2.116',
        profile_version='unqualified-test', profile_hash='b' * 64)
    request = dict(version=1, config_pin=config)
    if kind != 'preflight':
        receipt = dict(path=scratch, attempt=1, input_hash='c' * 64)
        if kind == 'trial': receipt['trial_id'] = 'owned'
        else: receipt.update(operation_id='owned', role='improver', purpose='improve_propose')
        request.update(workspace_root=scratch, receipt=receipt, capability_hash='d' * 64)
    purposes = ('adapter_version', 'auth_status') + (() if kind == 'preflight' else ('sdk_version', 'query'))
    share = base64.b64encode(b'constructor-only').decode('ascii')
    return dict(version=2, type='startup2', kind=kind, launch_nonce='1' * 64, worker_pid=101,
        worker_birth=102, private_share=share, images=[dict(purpose=purpose, nonce=str(index + 2) * 64,
        share=share) for index, purpose in enumerate(purposes)], request=request, environment=environment)


class NativeWorkerContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_startup3_is_explicit_preflight_only_and_default_route_never_adopts_it(self):
        from test_improvement_qualification_protocol import startup
        from improvement_qualification_protocol import encode_startup3
        m = component(self)
        value = startup('preflight')
        # A missing platform symbol is only a no-acquisition sentinel here;
        # creating it does not simulate native endpoint adoption.
        with patch.object(m.socket, 'fromshare', side_effect=AssertionError('no acquisition'), create=True):
            with self.assertRaises(ValueError): m.NativeWorkerSessionV2(value, namespace='preflight')
            with self.assertRaises(ValueError): await m.run_startup2(encode_startup3(value), entrypoint='trial')
            with self.assertRaises(ValueError): await m.run_startup3(encode_startup3(value), entrypoint='operation')
            for kind in ('trial', 'operation'):
                with self.assertRaises(ValueError): m.NativeWorkerSessionV2.from_startup3(startup(kind), namespace=kind)
                with self.assertRaises(ValueError): await m.run_startup3(encode_startup3(startup(kind)), entrypoint='trial')
            owner = m.NativeWorkerSessionV2.from_startup3(value, namespace='preflight')
            self.assertEqual(owner._packet['qualification'], value['qualification'])
            value['qualification']['run_hash'] = '0' * 64
            self.assertNotEqual(owner._packet['qualification'], value['qualification'])
            await owner.aclose()

    async def test_closed_constructor_snapshots_without_socket_environment_or_sdk_side_effect(self):
        m = component(self)
        value, original_env = packet(), dict(os.environ)
        owner = m.NativeWorkerSessionV2(value, namespace='preflight')
        value['environment']['HOME'] = 'MUTATED'
        self.assertNotEqual(owner._packet['environment']['HOME'], 'MUTATED')
        self.assertEqual(dict(os.environ), original_env)
        self.assertFalse(owner.closed)
        with self.assertRaises(m.NativeWorkerError): _ = owner.runtime
        await owner.aclose()
        self.assertTrue(owner.closed)

    async def test_namespace_and_closed_startup_refuse_before_adoption(self):
        m = component(self)
        for namespace in ('', 'trial', True, None):
            with self.subTest(namespace=namespace), self.assertRaises((ValueError, TypeError)):
                m.NativeWorkerSessionV2(packet(), namespace=namespace)
        for change in ({'version': True}, {'unexpected': 'PRIVATE'}, {'worker_birth': False}):
            with self.subTest(keys=list(change)), self.assertRaises((ValueError, TypeError)):
                m.NativeWorkerSessionV2({**packet(), **change}, namespace='preflight')

    async def test_all_supported_namespace_constructors_have_no_execution_authority(self):
        m = component(self)
        for kind in ('preflight', 'trial', 'operation'):
            owner = m.NativeWorkerSessionV2(packet(kind), namespace=kind)
            with self.subTest(kind=kind), self.assertRaises(m.NativeWorkerError):
                await owner.send({'type': 'endpoints_adopted'})
            await owner.aclose()
            self.assertTrue(owner.closed)


_CHILD = r'''
import asyncio,json,os,socket,sys
sys.path.insert(0,sys.argv[1])
from improvement_native_worker import NativeWorkerSessionV2
mode=sys.argv[2]
startup=json.loads(sys.stdin.buffer.readline())
initial=dict(os.environ)
owner=(NativeWorkerSessionV2.from_startup3(startup,namespace=startup['kind']) if startup['version']==3
 else NativeWorkerSessionV2(startup,namespace=startup['kind']))
imports=[]
import builtins
original_import=builtins.__import__
def observe(name,*args,**kwargs):
 if name in ('improvement_private_channel','improvement_image_channel','improvement_native_sdk'):
  imports.append(dict(os.environ)==startup['environment'])
 module=original_import(name,*args,**kwargs)
 if name=='improvement_native_sdk' and mode.startswith('qualification_factory_'):
  original_factory=module.NativeInvocationSet.from_qualification_worker
  def factory(cls,current):
   if mode=='qualification_factory_environment':os.environ['ANTHROPIC_BASE_URL']='http://127.0.0.1:15433'
   elif mode=='qualification_factory_record':current._records[0]['acquisition_unknown']=True
   elif mode=='qualification_factory_run':current._packet['qualification']['run_hash']='0'*64
   try:return original_factory(current)
   finally:
    # Restore the deliberate record fault so this fixture can prove actual known close.
    if mode=='qualification_factory_record':current._records[0]['acquisition_unknown']=False
  module.NativeInvocationSet.from_qualification_worker=classmethod(factory)
 return module
builtins.__import__=observe
if mode=='cancel':
 original_fromshare=socket.fromshare
 counter=[0]
 def backpressured(info):
  result=original_fromshare(info);counter[0]+=1
  if counter[0]==1:
   result.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,1024)
   result.setblocking(False)
   for _ in range(4096):
    try:result.send(b'x'*4096)
    except BlockingIOError:break
   else:raise RuntimeError('fixture_backpressure_unavailable')
  return result
 socket.fromshare=backpressured
async def main():
 result={'adopted':False,'error_type':None,'closed':False,'env_unchanged':False}
 try:
  if mode=='cancel':
   task=asyncio.create_task(owner.adopt())
   for _ in range(2000):
    if owner._private is not None and any(not item.done() for item in owner._private._tasks):break
    if task.done():raise RuntimeError('fixture_gate_missing')
    await asyncio.sleep(.001)
   else:raise RuntimeError('fixture_gate_timeout')
   for _ in range(4):task.cancel();await asyncio.sleep(0)
   await task
  else:await owner.adopt()
  result.update(adopted=True,env_exact=dict(os.environ)==startup['environment'],
   runtime_cwd=owner.runtime._cwd,sdk_imported='claude_agent_sdk' in sys.modules,
   initial_scratch_preserved=owner._scratch==initial['HOME'],
   login_home_preserved=os.environ['HOME']==startup['environment']['HOME'],
   imports_after_env=all(imports),runtime_commands=len(owner.runtime.captures))
  if mode=='dispatch_failure':
   original_runtime=owner.runtime
   class ActiveRuntime:
    def __init__(self):self.active=None;self.reentrant=False
    async def dispatch(self):
     self.active=asyncio.current_task()
     try:await original_runtime._emit({'type':'dispatch_observed','purpose':'adapter_version',
      'nonce':startup['images'][0]['nonce'],'native_pid':1,'native_birth':1,
      'dispatch_hash':'0'*64,'dispatch':{}})
     finally:self.active=None
    async def aclose(self):
     if self.active is not None and not self.active.done():
      self.reentrant=True
      done,_=await asyncio.wait((self.active,),timeout=.05)
      if self.active not in done:raise RuntimeError('fixture_active_callback_cycle')
     await original_runtime.aclose()
   layer=ActiveRuntime();owner._runtime=layer
   # Actual metadata socket is closed. No fake native identity is attested:
   # this adapter models only the capture->dispatch->runtime-close dependency.
   await owner._private.aclose()
   try:await layer.dispatch()
   finally:result['runtime_cleanup_reentrant']=layer.reentrant
  elif mode=='eof':await owner.receive()
  elif startup['kind']!='preflight':
   identity=owner._binding['identity']
   await owner.send({'type':'worker_ready',**identity,'capability_hash':startup['request']['capability_hash']})
   result['ack']=await owner.receive()
 except BaseException as error:result['error_type']=type(error).__name__
 finally:
  try:await owner.aclose()
  except BaseException as error:result['cleanup_error_type']=type(error).__name__
  result.update(closed=owner.closed,env_unchanged=dict(os.environ)==initial,
   environment_started=owner._environment_started,records=len(owner._records),
   acquisition_unknown=any(item['acquisition_unknown'] for item in owner._records),
   channels_closed=all(item['channel'] is None or item['channel'].closed for item in owner._records),
   retained=owner in __import__('improvement_native_worker')._RETAINED)
 print(json.dumps(result,separators=(',',':')),flush=True)
asyncio.run(main())
'''


@unittest.skipUnless(os.name == 'nt' and sys.flags.isolated, 'real fromshare fixtures require isolated Windows driver')
class NativeWorkerWindowsTests(unittest.IsolatedAsyncioTestCase):
    async def run_child(self, kind='preflight', *, change=None, mode='normal', flags=('-I', '-S', '-B'), wrong_cwd=False,
                        qualification=False):
        component(self)
        from improvement_native_capture_win32 import backend
        from improvement_native_protocol import worker_binding
        from improvement_private_channel import PrivateWorkerChannelV2, PrivateChannelError
        api = backend()
        with tempfile.TemporaryDirectory(prefix='native-worker-') as directory:
            root = Path(directory); scratch = root / 'scratch'; scratch.mkdir()
            workspace = root / 'workspace'; workspace.mkdir()
            value = packet(kind, scratch=str(scratch))
            login = root / 'external-empty-login'; login.mkdir()
            value['environment'].update(HOME=str(login), USERPROFILE=str(login),
                APPDATA=str(login / 'AppData/Roaming'), LOCALAPPDATA=str(login / 'AppData/Local'))
            if qualification:
                from improvement_qualification_environment import dummy_environment
                from improvement_native_protocol import _canonical
                import hashlib
                digest=lambda item:hashlib.sha256(_canonical(item)).hexdigest()
                value.update(version=3,type='startup3')
                value['request']['config_pin']['profile_version']='claude-owned-images-v3'
                value['environment']=dummy_environment(value['environment'],endpoint='http://127.0.0.1:15432')
                scope=dict(version=1,domain='qualification',account_ready=False,run_nonce='9'*64,
                    root=str(root),brain_id=str(root/'brain'),pin_hash=digest(value['request']['config_pin']),
                    release_fingerprint='8'*64,review_hash='7'*64,endpoint='http://127.0.0.1:15432',
                    maximum_queries=4,created_at=1000.0,deadline_at=1300.0)
                value['qualification']=dict(version=1,run_hash=digest(scope),scope=scope,
                    environment_hash=digest(value['environment']),attempt_link=None)
            if kind != 'preflight': value['request']['receipt']['path'] = str(workspace)
            initial = {key: str(scratch) for key in ('HOME', 'USERPROFILE', 'TEMP', 'TMP', 'APPDATA', 'LOCALAPPDATA')}
            initial.update(SYSTEMROOT=os.environ.get('SYSTEMROOT', r'C:\Windows'), WINDIR=r'C:\Windows',
                PATH=str(Path(sys._base_executable).parent))
            child = subprocess.Popen([sys._base_executable, *flags, '-c', _CHILD, str(SERVER), mode],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=str(scratch if wrong_cwd else SERVER), env=initial, creationflags=0x08000000)
            child_handle = int(child._handle)
            child_birth = api.birth(child_handle)
            self.assertEqual(api.process_id(child_handle), child.pid)
            self.assertFalse(api.wait(child_handle))
            value['worker_pid'], value['worker_birth'] = child.pid, child_birth
            pairs = [socket.socketpair() for _ in range(len(value['images']) + 1)]
            host = None
            try:
                shares = []
                for _, endpoint in pairs:
                    self.assertEqual(api.process_id(child_handle), child.pid)
                    self.assertEqual(api.birth(child_handle), child_birth)
                    self.assertFalse(api.wait(child_handle))
                    shares.append(base64.b64encode(endpoint.share(child.pid)).decode('ascii'))
                value['private_share'] = shares[0]
                for item, share in zip(value['images'], shares[1:]): item['share'] = share
                original_value=copy.deepcopy(value)
                if change is not None: change(value)
                # Host binding uses the actual retained target incarnation, even
                # when testing an invalid worker receipt PID/birth.
                host_value = {**original_value, 'worker_pid': child.pid, 'worker_birth': child_birth}
                if qualification:
                    from improvement_qualification_protocol import worker_binding3
                    binding=worker_binding3(host_value)
                else: binding=worker_binding(host_value)
                host = PrivateWorkerChannelV2(pairs[0][0], binding=binding, role='host')
                for _, endpoint in pairs: endpoint.close()
                child.stdin.write(json.dumps(value).encode() + b'\n'); child.stdin.flush()
                child.stdin.close(); child.stdin = None
                good = (change is None and flags == ('-I', '-S', '-B') and not wrong_cwd
                    and mode != 'cancel' and not mode.startswith('qualification_factory_'))
                if good:
                    observed = await host.receive(timeout=8)
                    self.assertEqual(observed['body'], {'type': 'endpoints_adopted'})
                    if mode == 'eof': await host.aclose()
                    elif kind != 'preflight':
                        observed = await host.receive(timeout=8)
                        self.assertEqual(observed['body']['type'], 'worker_ready')
                        await host.send({'type': 'engine_start_ack', **worker_binding(value)['identity']})
                stdout, stderr = await asyncio.to_thread(child.communicate, timeout=12)
                self.assertEqual(child.returncode, 0, stderr.decode(errors='replace')[-1000:])
                self.assertTrue(api.wait(child_handle))
                result = json.loads(stdout)
                result['expected_runtime_cwd'] = str(scratch if kind == 'preflight' else workspace)
                return result
            finally:
                if child.poll() is None:
                    child.terminate()
                    await asyncio.to_thread(child.wait, timeout=8)
                if host is not None: await host.aclose()
                for index, (first, second) in enumerate(pairs):
                    if index != 0 or host is None: first.close()
                    second.close()
                for stream in (child.stdin, child.stdout, child.stderr):
                    if stream is not None: stream.close()

    async def test_real_preflight_adoption_installs_env_before_runtime_without_cli_or_sdk(self):
        result = await self.run_child()
        self.assertTrue(result['adopted'])
        self.assertTrue(result['closed'])
        self.assertTrue(result['env_exact'])
        self.assertTrue(result['imports_after_env'])
        self.assertTrue(result['login_home_preserved'])
        self.assertTrue(result['initial_scratch_preserved'])
        self.assertEqual(result['runtime_cwd'], result['expected_runtime_cwd'])
        self.assertEqual(result['runtime_commands'], 0)
        self.assertFalse(result['sdk_imported'])
        self.assertTrue(result['channels_closed'])

    async def test_startup3_actual_adoption_constructs_sdk_only_after_exact_dummy_environment(self):
        result=await self.run_child(qualification=True)
        self.assertTrue(result['adopted']); self.assertTrue(result['closed']); self.assertTrue(result['env_exact'])
        self.assertTrue(result['imports_after_env']); self.assertEqual(result['records'],3)
        self.assertFalse(result['sdk_imported']); self.assertEqual(result['runtime_commands'],0)
        self.assertTrue(result['channels_closed'])

    async def test_startup3_actual_factory_refuses_changed_environment_run_and_private_record(self):
        for mode in ('environment','run','record'):
            with self.subTest(mode=mode):
                result=await self.run_child(qualification=True,mode='qualification_factory_'+mode)
                self.assertFalse(result['adopted']); self.assertTrue(result['closed'])
                self.assertEqual(result['records'],3); self.assertTrue(result['channels_closed'])

    async def test_startup3_actual_fromshare_failure_retains_unknown_for_enclosing_process_drain(self):
        def change(value):value['images'][0]['share']=base64.b64encode(b'invalid-native-share').decode('ascii')
        result=await self.run_child(qualification=True,change=change)
        self.assertFalse(result['adopted']); self.assertFalse(result['closed']); self.assertTrue(result['retained'])
        self.assertTrue(result['acquisition_unknown']); self.assertTrue(result['channels_closed'])

    async def test_real_trial_and_operation_body_channels_use_closed_protocol(self):
        for kind in ('trial', 'operation'):
            with self.subTest(kind=kind):
                result = await self.run_child(kind)
                self.assertTrue(result['adopted'])
                self.assertTrue(result['closed'])
                self.assertEqual(result['runtime_cwd'], result['expected_runtime_cwd'])
                self.assertEqual(result['ack']['type'], 'engine_start_ack')
                self.assertFalse(result['sdk_imported'])

    async def test_actual_self_incarnation_refuses_wrong_pid_and_birth_before_env_or_fromshare(self):
        for name in ('worker_pid', 'worker_birth'):
            def change(value): value[name] += 1
            with self.subTest(name=name):
                result = await self.run_child(change=change)
                self.assertFalse(result['adopted'])
                self.assertFalse(result['environment_started'])
                self.assertTrue(result['env_unchanged'])
                self.assertEqual(result['records'], 0)
                self.assertTrue(result['closed'])

    async def test_actual_missing_isolation_and_wrong_cwd_refuse_before_env_or_sockets(self):
        for args in ({'flags': ('-S', '-B')}, {'flags': ('-I', '-B')}, {'wrong_cwd': True}):
            with self.subTest(args=args):
                result = await self.run_child(**args)
                self.assertFalse(result['environment_started'])
                self.assertEqual(result['records'], 0)
                self.assertTrue(result['closed'])

    async def test_preflight_scratch_mismatch_refuses_before_environment(self):
        def change(value): value['environment']['TEMP'] += '-foreign'
        result = await self.run_child(change=change)
        self.assertFalse(result['environment_started'])
        self.assertEqual(result['records'], 0)
        self.assertTrue(result['closed'])

    async def test_real_fromshare_failure_after_private_adoption_retains_unknown_until_process_exit(self):
        def change(value): value['images'][0]['share'] = base64.b64encode(b'invalid-native-share').decode('ascii')
        result = await self.run_child(change=change)
        self.assertFalse(result['adopted'])
        self.assertTrue(result['environment_started'])
        self.assertTrue(result['acquisition_unknown'])
        self.assertTrue(result['retained'])
        self.assertFalse(result['closed'])
        self.assertTrue(result['channels_closed'])

    async def test_runtime_constructor_failure_closes_all_known_adopted_channels(self):
        def change(value): value['request']['config_pin']['sdk_version'] = 'unsupported'
        result = await self.run_child(change=change)
        self.assertFalse(result['adopted'])
        self.assertTrue(result['closed'])
        self.assertFalse(result['acquisition_unknown'])
        self.assertTrue(result['channels_closed'])

    async def test_private_host_eof_drains_session_without_runtime_command(self):
        result = await self.run_child(mode='eof')
        self.assertTrue(result['adopted'])
        self.assertTrue(result['closed'])
        self.assertEqual(result['error_type'], 'NativeWorkerError')
        self.assertEqual(result['runtime_commands'], 0)

    async def test_repeated_adopt_cancellation_closes_pending_real_socket_send(self):
        result = await self.run_child(mode='cancel')
        self.assertFalse(result['adopted'])
        self.assertTrue(result['closed'])
        self.assertEqual(result['error_type'], 'CancelledError')
        self.assertTrue(result['channels_closed'])

    async def test_active_runtime_dispatch_failure_unwinds_before_worker_cleanup(self):
        result = await self.run_child(mode='dispatch_failure')
        self.assertTrue(result['adopted'])
        self.assertTrue(result['closed'])
        self.assertFalse(result['runtime_cleanup_reentrant'], 'capture callback must unwind before worker cleanup')
        self.assertEqual(result['error_type'], 'NativeWorkerError')


if __name__ == '__main__': unittest.main()
