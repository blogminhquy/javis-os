"""Host V2 consumer contract; engineering fixtures never invoke an SDK or account."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import copy
import hashlib
import importlib
import inspect
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import time
import traceback
import threading
import socket
from collections import deque
from types import SimpleNamespace
from unittest.mock import patch


def component(test):
    mod = importlib.import_module('improvement_native_transport')
    test.assertTrue(hasattr(mod, 'GuardianSessionV2'), 'host guardian V2 consumer missing')
    return mod


def fixture_manifest(entrypoint):
    runtime = {'path': r'C:\Python\python.exe', 'sha256': 'a' * 64,
               'volume_serial_64': 1, 'file_id_128': 'b' * 32}
    target = 'improvement_native_lifetime.py' if entrypoint == 'guardian' else 'improvement_worker.py'
    return {'version': 1, 'entrypoint': entrypoint,
        'runtime': {'executable': runtime, 'dll': {**runtime, 'path': r'C:\Python\python312.dll'}},
        'source': {'root': r'C:\source', 'files': {'improvement_native_bootstrap.py': 'c' * 64,
            'improvement_native_image.py': 'd' * 64, target: 'e' * 64}},
        'imports': {'site_packages': r'C:\packages', 'files': {}}}


async def persist(joined):
    return {'decision': 'allow', 'durable_evidence_hash': 'f' * 64}


def arguments():
    return {'image_policy': {'version': 1, 'path': r'C:\native\selected.exe', 'sha256': 'a' * 64},
        'fences': [r'C:\scratch\brain.lock', r'C:\scratch\attempt.lock'], 'launch_nonce': '1' * 64,
        'invocations': [{'purpose': 'query', 'nonce': '2' * 64}],
        'timeout': 5, 'close_timeout': 5, 'lifetime_timeout': 30, 'persist_before_allow': persist}


class HostGuardianContractTests(unittest.TestCase):
    def test_constructor_never_acquires_files_sockets_handles_or_processes(self):
        mod = component(self)
        with patch.object(mod, '_host_windows', side_effect=AssertionError('constructor native API')), \
                patch.object(mod.subprocess, 'Popen', side_effect=AssertionError('constructor Popen')), \
                patch('builtins.open', side_effect=AssertionError('constructor file')), \
                patch('socket.socketpair', side_effect=AssertionError('constructor socket pair')), \
                patch.object(mod.GuardianSessionV2, '_prepare_guards', side_effect=AssertionError('constructor files')), \
                patch.object(mod.GuardianSessionV2, '_pair', side_effect=AssertionError('constructor sockets')):
            owner = self.session()
        self.assertIsNone(owner._api); self.assertEqual(owner._guards, []); self.assertEqual(owner._socket_records, [])
        self.assertIsNone(owner._loop); self.assertIsNone(owner._process)

    def session(self, **changes):
        mod = component(self)
        return mod.GuardianSessionV2(fixture_manifest('guardian'),
            {'version': 1, 'bootstrap': fixture_manifest('trial'), 'scratch': r'C:\scratch'},
            **{**arguments(), **changes})

    def test_closed_construction_does_not_launch_or_claim_a_process_incarnation(self):
        mod = component(self)
        guardian, policy, options = fixture_manifest('guardian'), {
            'version': 1, 'bootstrap': fixture_manifest('trial'), 'scratch': r'C:\scratch'}, arguments()
        owner = mod.GuardianSessionV2(guardian, policy, **options)
        guardian['source']['files'].clear(); policy['bootstrap']['entrypoint'] = 'guardian'
        options['image_policy']['sha256'] = '9' * 64; options['invocations'].clear()
        self.assertFalse(owner.closed)
        self.assertIsNone(owner.worker_identity)
        self.assertIsNone(owner.guardian_identity)
        self.assertTrue(inspect.iscoroutinefunction(owner.start))
        self.assertTrue(inspect.iscoroutinefunction(owner.aclose))

    def test_sync_or_unbounded_authorization_callback_refuses(self):
        for callback in (None, lambda value: {'decision': 'allow'}):
            with self.subTest(callback=callback), self.assertRaises((ValueError, TypeError)):
                self.session(persist_before_allow=callback)
        for value in (True, math.inf, 0, 61):
            with self.subTest(timeout=value), self.assertRaises((ValueError, TypeError)):
                self.session(timeout=value)
        for value in (True, math.inf, 0, 301):
            with self.subTest(lifetime_timeout=value), self.assertRaises((ValueError, TypeError)):
                self.session(lifetime_timeout=value)

    def test_ambiguous_purposes_replayed_nonces_and_metadata_extra_fields_refuse(self):
        changes = [{'image_policy': {**arguments()['image_policy'], 'config_pin': {}}},
            {'launch_nonce': '2' * 64}, {'invocations': [{'purpose': 'ambient', 'nonce': '3' * 64}]},
            {'invocations': [{'purpose': 'query', 'nonce': '2' * 64}, {'purpose': 'query', 'nonce': '3' * 64}]}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError)):
                self.session(**change)

    def test_guardian_manifest_cannot_select_worker_or_cross_runtime(self):
        mod = component(self)
        policy = {'version': 1, 'bootstrap': fixture_manifest('trial'), 'scratch': r'C:\scratch'}
        for guardian in (fixture_manifest('trial'), fixture_manifest('guardian')):
            if guardian['entrypoint'] == 'guardian': guardian['runtime']['dll']['file_id_128'] = '9' * 32
            with self.subTest(guardian=guardian['entrypoint']), self.assertRaises((ValueError, TypeError)):
                mod.GuardianSessionV2(guardian, policy, **arguments())

    def test_existing_v1_entrypoint_remains_available(self):
        mod = component(self)
        self.assertTrue(inspect.isasyncgenfunction(mod.execute_worker))
        self.assertTrue(inspect.isasyncgenfunction(mod.execute_worker_v2))

    def test_control_decode_refuses_duplicate_keys_noncanonical_extra_and_foreign_binding(self):
        mod = component(self)
        value = {'version': 2, 'type': 'stdio_sealed', 'sequence': 2, 'launch_nonce': '1' * 64,
                 'worker_pid': 300, 'worker_birth': 400, 'all_data_pipes_closed': True}
        def raw(item):
            return json.dumps(item, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')
        options = {'launch_nonce': '1' * 64, 'expected_sequence': 2,
                   'invocations': arguments()['invocations'],
                   'worker_identity': {'worker_pid': 300, 'worker_birth': 400}}
        parsed = mod._decode_guardian_control2(raw(value), **options)
        self.assertEqual(parsed, value)
        parsed['worker_pid'] = 1
        self.assertEqual(mod._decode_guardian_control2(raw(value), **options), value)
        invalid = [b' ' + raw(value), raw(value)[:-1] + b',"version":2}',
            raw({**value, 'sequence': True}), raw({**value, 'version': 2.0}),
            raw({**value, 'worker_birth': 401}), raw({**value, 'unexpected': 'private'}),
            raw({**value, 'all_data_pipes_closed': 1}), b'{"x":' + b'[' * 33 + b'0' + b']' * 33 + b'}']
        for packet in invalid:
            with self.subTest(packet=packet[:40]), self.assertRaises((ValueError, OSError)):
                mod._decode_guardian_control2(packet, **options)

    def test_distinct_real_file_owners_all_close_despite_recycled_python_ids(self):
        owner = self.session()
        with tempfile.TemporaryFile() as fixture:
            # Separate opens have independent native owners. Releasing a closed
            # Python wrapper must never authorize skipping another native close.
            for unused in range(128):
                reader = os.fdopen(os.dup(fixture.fileno()), 'rb')
                owner._close_stream(reader)
                self.assertTrue(reader.closed, 'new native file owner was skipped')
                del reader


class HostGuardianFlowTests(unittest.IsolatedAsyncioTestCase):
    def owner(self):
        mod = component(self)
        return mod.GuardianSessionV2(fixture_manifest('guardian'),
            {'version': 1, 'bootstrap': fixture_manifest('trial'), 'scratch': r'C:\scratch'}, **arguments())

    def local_owner(self):
        owner = self.owner()
        owner._loop = asyncio.get_running_loop(); owner._deadline = owner._loop.time() + 30
        owner._packets, owner._pending_publish, owner._final_drained = deque(), {}, None
        owner._available, owner._space = asyncio.Event(), asyncio.Event()
        owner._offer = None
        return owner

    async def test_cancelled_thread_task_never_releases_guards_or_disappears_on_retry(self):
        mod = component(self); owner = self.local_owner()
        started, release, finished = threading.Event(), threading.Event(), threading.Event()
        closed = []; owner._guards.append(SimpleNamespace(close=lambda: closed.append(True)))
        def work():
            started.set(); release.wait(8); finished.set()
        operation = owner._task(asyncio.to_thread(work))
        try:
            while not started.is_set(): await asyncio.sleep(.001)
            operation.cancel()
            with self.assertRaises(asyncio.CancelledError): await operation
            self.assertFalse(finished.is_set())
            for unused in range(2):
                with self.assertRaises(mod.GuardianSessionV2CleanupError): await owner.aclose()
                self.assertFalse(owner.closed); self.assertEqual(closed, [])
                self.assertIn(operation, owner._tasks)
        finally:
            release.set()
            while not finished.is_set(): await asyncio.sleep(.001)
            mod._HOST_V2_RETAINED.discard(owner)

    async def test_cancelled_actual_control_receive_is_sticky_unknown(self):
        mod = component(self); owner = self.local_owner()
        pair = owner._pair('control')
        closed = []; owner._guards.append(SimpleNamespace(close=lambda: closed.append(True)))
        owner._guardian_task = owner._task(owner._guardian_loop())
        try:
            await asyncio.sleep(.01)
            owner._guardian_task.cancel()
            await asyncio.gather(owner._guardian_task, return_exceptions=True)
            for unused in range(2):
                with self.assertRaises(mod.GuardianSessionV2CleanupError): await owner.aclose()
                self.assertFalse(owner.closed); self.assertEqual(closed, [])
                self.assertIn(owner._guardian_task, owner._tasks)
        finally:
            for endpoint in pair:
                if endpoint.fileno() >= 0: endpoint.close()
            mod._HOST_V2_RETAINED.discard(owner)

    async def test_actual_socket_configuration_failure_keeps_both_endpoint_owners(self):
        owner = self.local_owner(); original = socket.socketpair; endpoints = []
        def pair():
            actual = original(); endpoints.extend(actual); return actual
        try:
            with patch.object(socket, 'socketpair', side_effect=pair), patch.object(
                    socket.socket, 'set_inheritable', side_effect=OSError('engineering_configuration_failure')):
                with self.assertRaises(OSError): owner._pair('control')
            await owner.aclose()
            self.assertTrue(owner.closed)
            self.assertEqual(len(endpoints), 2)
            self.assertTrue(all(endpoint.fileno() < 0 for endpoint in endpoints))
        finally:
            for endpoint in endpoints:
                if endpoint.fileno() >= 0: endpoint.close()

    async def test_slow_consumer_and_close_preserve_bounded_defensive_observations(self):
        owner = self.owner()
        owner._packets, owner._pending_publish, owner._final_drained = deque(), {}, None
        owner._available, owner._space = asyncio.Event(), asyncio.Event()
        owner._worker_identity = {'worker_pid': 300, 'worker_birth': 400}
        for index in range(15):
            await owner._publish('worker', index + 1, {'type': 'engine_event', 'event': {'type': 'usage', 'index': index}})
        worker = asyncio.create_task(owner._publish('worker', 16, {'type': 'engine_event', 'event': {'type': 'usage', 'index': 15}}))
        guardian = asyncio.create_task(owner._publish('guardian', 1, {'type': 'image_observed'}))
        await asyncio.sleep(0)
        self.assertFalse(worker.done()); self.assertFalse(guardian.done())
        self.assertEqual(len(owner.closing_observations), 17)
        owner._stop()
        self.assertEqual(await asyncio.gather(worker, guardian), [False, False])
        await owner._publish('guardian', 2, {'type': 'drained'})
        observed = owner.closing_observations
        self.assertEqual(len(observed), 18)
        self.assertEqual([p['sequence'] for p in observed], list(range(1, 19)))
        self.assertEqual(sum(p['body']['type'] == 'engine_event' for p in observed), 16)
        observed[0]['body']['event'].clear()
        self.assertEqual(owner.closing_observations[0]['body']['event']['type'], 'usage')

    async def test_guardian_terminal_without_worker_completion_refuses_after_queued_usage(self):
        mod = component(self); owner = self.owner()
        owner._loop = asyncio.get_running_loop(); owner._deadline = owner._loop.time() + 30
        owner._packets, owner._pending_publish, owner._final_drained = deque(), {}, None
        owner._available, owner._space = asyncio.Event(), asyncio.Event()
        owner._worker_identity = {'worker_pid': 300, 'worker_birth': 400}
        owner.native_drained = True
        owner._guardian_task = asyncio.create_task(asyncio.sleep(0))
        await owner._guardian_task
        await owner._publish('worker', 1, {'type': 'engine_event', 'event': {'type': 'usage', 'tokens': 3}})
        await owner._publish('guardian', 2, {'type': 'drained'})
        self.assertEqual(len(owner.closing_observations), 2)
        self.assertEqual((await owner.receive())['body']['event']['tokens'], 3)
        self.assertEqual((await owner.receive())['body']['type'], 'drained')
        with self.assertRaises(mod.GuardianSessionV2Error):
            await asyncio.wait_for(owner.receive(), .05)
        self.assertFalse(owner._worker_complete)

    async def test_actual_short_file_writes_complete_public_bootstrap_and_zero_none_refuse(self):
        owner = self.owner(); payload = b'bootstrap-framing\x00' + bytes(range(256)) * 4
        class ShortWriter:
            def __init__(self, file, failure=None): self.file, self.failure, self.calls = file, failure, 0
            def write(self, data):
                self.calls += 1
                if self.calls == 2 and self.failure is not False: return self.failure
                return self.file.write(data[:17])
            def flush(self): self.file.flush()
        with tempfile.TemporaryFile() as target:
            writer = ShortWriter(target, False); owner._process = SimpleNamespace(stdin=writer)
            owner._write_public(payload)
            target.seek(0)
            self.assertEqual(target.read(), payload)
            self.assertGreater(writer.calls, 1)
        for failure in (0, None):
            with self.subTest(failure=failure), tempfile.TemporaryFile() as target:
                owner._process = SimpleNamespace(stdin=ShortWriter(target, failure))
                with self.assertRaises(OSError): owner._write_public(payload)

    async def test_iterator_cancel_settles_accounting_then_preserves_received_and_queued_packets(self):
        mod = component(self)
        accounting, release_accounting = asyncio.Event(), asyncio.Event()
        late, release_late = asyncio.Event(), asyncio.Event()
        retained = []
        class Session:
            def __init__(self, *args, **kwargs): self.closed = False
            async def start(self, startup): pass
            async def receive(self): return {'sequence': 1, 'body': {'type': 'engine_start_requested'}}
            async def send_worker(self, body): raise AssertionError('cancelled accounting must not ACK')
            async def aclose(self): self.closed = True
            @property
            def closing_observations(self):
                return ({'sequence': 2, 'body': {'type': 'engine_event', 'event': {'type': 'usage', 'tokens': 3}}},)
        async def before():
            accounting.set(); await release_accounting.wait()
        async def closing(observations):
            retained.extend(observations); late.set(); await release_late.wait()
        with patch.object(mod, 'GuardianSessionV2', Session):
            iterator = mod.execute_worker_v2('trial', {'deadline_at': time.time() + 30, 'capability_hash': 'c' * 64},
                {'trial_id': 'engineering', 'attempt': 1, 'path': r'C:\scratch'}, config_pin={},
                workspace_root=r'C:\scratch', brain_id='engineering', before_engine_start=before,
                guardian_manifest={}, policy={}, image_policy={}, launch_nonce='1' * 64, invocations=[],
                persist_before_allow=persist, on_closing_observations=closing, environment={})
            reading = asyncio.create_task(anext(iterator))
            await accounting.wait(); reading.cancel(); await asyncio.sleep(0)
            self.assertFalse(reading.done())
            release_accounting.set(); await late.wait(); reading.cancel(); await asyncio.sleep(0)
            self.assertFalse(reading.done())
            release_late.set()
            with self.assertRaises(asyncio.CancelledError): await reading
            self.assertEqual([p['sequence'] for p in retained], [1, 2])
            self.assertEqual(retained[1]['body']['event']['tokens'], 3)


_WORKER_STUB = r'''import asyncio,base64,hashlib,json,os,socket,subprocess,sys
from improvement_native_protocol import decode_startup2,worker_binding
from improvement_private_channel import PrivateWorkerChannelV2
from improvement_native_capture import NativeDebugInvocation
from improvement_image_channel import ImageMetadataChannel
p=decode_startup2(sys.stdin.buffer.readline(8*1024*1024+1))
os.environ.clear();os.environ.update(p['environment'])
b=worker_binding(p);sock=socket.fromshare(base64.b64decode(p['private_share'],validate=True));sock.setblocking(False)
private=None
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')
async def send(body):
 await private.send(body)
async def receive():
 return (await private.receive())['body']
class Process:
 def __init__(self,p):self.p=p;self.pid=p.pid
 async def wait(self):return await asyncio.to_thread(self.p.wait)
 async def aclose(self):await self.wait()
async def opener(argv,**kwargs):
 return Process(subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
  creationflags=kwargs['creationflags'],env=dict(os.environ),cwd=os.getcwd()))
async def native(item):
 argv=[SELECTED,'/d','/c','echo INERT_HOST_V2_MARKER']
 proof={}
 def validate(args):
  if args[1]!=subprocess.list2cmdline(argv) or args[5]!=0x08000006:return False
  proof.update(version=1,basis='engineering_actual_create_arguments',argv_hash=hashlib.sha256(canonical(argv)).hexdigest(),
   command_hash=hashlib.sha256(args[1].encode('utf-8')).hexdigest())
  return True
 channel=ImageMetadataChannel(socket.fromshare(base64.b64decode(item['share'],validate=True)),role='worker',nonce=item['nonce'],
  worker_pid=p['worker_pid'],worker_birth=p['worker_birth'],timeout=8,close_timeout=8)
 async def ack(frame):
  await send({'type':'dispatch_observed','purpose':item['purpose'],'nonce':item['nonce'],
   'native_pid':frame['native_pid'],'native_birth':frame['native_birth'],'dispatch':proof,
   'dispatch_hash':hashlib.sha256(canonical(proof)).hexdigest()})
  return await channel.exchange(frame)
 purpose='sdk_query' if item['purpose']=='query' else 'isolated_preflight'
 try:
  async with NativeDebugInvocation(opener,purpose=purpose,nonce=item['nonce'],validate_create=validate,image_ack=ack) as owner:
   proc=await owner.open_process(argv);await proc.wait()
 finally:await channel.aclose()
async def main():
 global private
 private=PrivateWorkerChannelV2(sock,binding=b,role='worker',timeout=8,close_timeout=8)
 await send({'type':'endpoints_adopted'})
 for item in p['images'][:2]:await native(item)
 ident=b['identity']
 await send({'type':'worker_ready',**ident,'capability_hash':p['request']['capability_hash']})
 await native(p['images'][2])
 await native(p['images'][3])
 await send({'type':'engine_start_requested',**ident})
 if (await receive())!={'type':'engine_start_ack',**ident}:raise ValueError('ACK')
 await send({'type':'engine_event',**ident,'event':{'type':'engineering_marker','content':'PRIVATE_ENGINE_MARKER'}})
 await send({'type':'worker_complete',**ident,'fixture_events':[],'tool_denials':[]})
 await private.aclose()
asyncio.run(main())
'''


@unittest.skipUnless(os.name == 'nt', 'Actual independent base-Python guardian and engineering worker')
class HostGuardianWindowsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mod = component(self)
        from improvement_native_bootstrap import _runtime_paths
        from improvement_native_image import ImageReadGuard
        from improvement_sandbox import worker_environment
        import msvcrt
        short = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'Temp'
        self.temp = tempfile.TemporaryDirectory(prefix='jh2-', dir=short)
        self.root = Path(self.temp.name)
        self.source, self.packages = self.root / 's', self.root / 'p'
        self.source.mkdir(); self.packages.mkdir()
        for path in (self.packages / 'win32', self.packages / 'win32/lib', self.packages / 'pywin32_system32'):
            path.mkdir(exist_ok=True)
        self.scratch = self.root / 'scratch'; self.scratch.mkdir()
        self.private_home = self.root / 'PRIVATE_AUTH_HOME'; self.private_home.mkdir()
        self.selected = self.root / 'inert.exe'
        shutil.copyfile(Path(os.environ['SystemRoot']) / 'System32/cmd.exe', self.selected)
        names = ('improvement_native_bootstrap.py', 'improvement_native_lifetime.py', 'improvement_native_image.py',
            'improvement_fixed_worker_launch.py', 'improvement_native_capture.py', 'improvement_native_capture_win32.py',
            'improvement_image_channel.py', 'improvement_blobs.py', 'improvement_native_protocol.py', 'improvement_private_channel.py')
        for name in names: shutil.copyfile(SERVER / name, self.source / name)
        (self.source / 'improvement_worker.py').write_text('SELECTED=' + repr(str(self.selected)) + '\n' + _WORKER_STUB, encoding='utf-8')
        def pin(path):
            digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
            with ImageReadGuard(path, digest) as guard, open(path, 'rb') as reader:
                actual = guard.compare_file_handle(msvcrt.get_osfhandle(reader.fileno()))['actual']
            return {key: actual[key] for key in ('sha256', 'volume_serial_64', 'file_id_128')} | {'path': path}
        self.guardian = {'version': 1, 'entrypoint': 'guardian',
            'runtime': {name: pin(path) for name, path in _runtime_paths().items()},
            'source': {'root': str(self.source), 'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.source.iterdir()}},
            'imports': {'site_packages': str(self.packages), 'files': {}}}
        self.policy = {'version': 1, 'scratch': str(self.scratch),
            'bootstrap': {**self.guardian, 'entrypoint': 'trial'}}
        self.invocations = [{'purpose': purpose, 'nonce': str(index + 2) * 64} for index, purpose in
            enumerate(('adapter_version', 'auth_status', 'sdk_version', 'query'))]
        self.joins, self.packets, self.owners = [], [], []
        self.options = {'image_policy': {'version': 1, 'path': str(self.selected),
                'sha256': hashlib.sha256(self.selected.read_bytes()).hexdigest()},
            'fences': [str(self.root / 'brain.lock'), str(self.root / 'attempt.lock')],
            'launch_nonce': '1' * 64, 'invocations': self.invocations, 'timeout': 12, 'close_timeout': 8,
            'lifetime_timeout': 30,
            'persist_before_allow': self.persist}
        self.identity = {'trial_id': 'engineering', 'attempt': 1, 'input_hash': 'a' * 64}
        self.startup = {'kind': 'trial', 'request': {'version': 1, 'config_pin': {'engineering': True},
            'workspace_root': str(self.root), 'receipt': {**self.identity, 'path': str(self.scratch)}, 'capability_hash': 'c' * 64},
            'environment': worker_environment(self.scratch, auth_home=self.private_home)}
        self.addAsyncCleanup(self.cleanup)

    async def persist(self, joined):
        self.joins.append(copy.deepcopy(joined))
        self.assertEqual(joined['dispatch']['basis'], 'engineering_actual_create_arguments')
        joined['native_pid'] = 1
        joined['dispatch']['basis'] = 'caller_mutation'
        return {'decision': 'allow', 'durable_evidence_hash': 'd' * 64}

    def owner(self, **changes):
        owner = self.mod.GuardianSessionV2(self.guardian, self.policy, **{**self.options, **changes})
        self.owners.append(owner)
        return owner

    async def finalize_unknown_engineering_resources(self, owner, children):
        # Independent fixture finalizer, explicitly NOT product cleanup proof.
        # Every child here comes from this test's actual Popen return, never PID.
        for child in children:
            if child.stdin and not child.stdin.closed: child.stdin.close()
            await asyncio.to_thread(child.wait, timeout=8)
        pending = [task for task in owner._tasks if not task.done()]
        if pending:
            unused, pending = await asyncio.wait(pending, timeout=8)
            self.assertFalse(pending)
        for record in owner._socket_records:
            if record['socket'].fileno() >= 0: record['socket'].close()
        for child in children:
            for stream in (child.stdin, child.stdout, child.stderr):
                if stream and not stream.closed: stream.close()
            if not child._handle.closed: child._handle.Close()
        for guard in reversed(owner._guards): guard.close()
        self.mod._HOST_V2_RETAINED.discard(owner)

    async def test_partial_public_bootstrap_failure_supplies_stdin_eof_but_never_claims_drain(self):
        owner = self.mod.GuardianSessionV2(self.guardian, self.policy, **self.options)
        def partial(raw):
            owner._process.stdin.write(raw[:2]); owner._process.stdin.flush()
            raise OSError('engineering_partial_bootstrap')
        try:
            with patch.object(owner, '_write_public', side_effect=partial):
                with self.assertRaises(self.mod.GuardianSessionV2CleanupError): await owner.start(self.startup)
            self.assertTrue(owner._process.stdin.closed, 'partial framed bootstrap requires owned EOF')
            await asyncio.to_thread(owner._process.wait, timeout=8)
            self.assertFalse(owner.closed); self.assertFalse(owner.native_drained)
            self.assertTrue(owner._guards)
            with self.assertRaises(self.mod.GuardianSessionV2CleanupError): await owner.aclose()
        finally:
            await self.finalize_unknown_engineering_resources(owner, [owner._process] if owner._process else [])

    async def test_actual_popen_success_then_boundary_exception_retains_acquisition_unknown(self):
        owner = self.mod.GuardianSessionV2(self.guardian, self.policy, **self.options)
        original, children = self.mod.subprocess.Popen, []
        def boundary(*args, **kwargs):
            child = original(*args, **kwargs); children.append(child)
            raise OSError('engineering_after_actual_popen_success')
        try:
            with patch.object(self.mod.subprocess, 'Popen', side_effect=boundary):
                with self.assertRaises(self.mod.GuardianSessionV2CleanupError): await owner.start(self.startup)
            self.assertEqual(len(children), 1); self.assertIsNone(owner._process)
            self.assertFalse(owner.closed); self.assertTrue(owner._guards)
            with self.assertRaises(self.mod.GuardianSessionV2CleanupError): await owner.aclose()
        finally:
            await self.finalize_unknown_engineering_resources(owner, children)

    async def cleanup(self):
        for owner in self.owners:
            try: await owner.aclose()
            except BaseException:
                self.cleanup_diagnostic(owner)
                raise
        self.temp.cleanup()

    def cleanup_diagnostic(self, owner):
        # Function/line and booleans only: never dump private startup or stderr.
        error = owner._cleanup_task.exception() if owner._cleanup_task and owner._cleanup_task.done() else None
        print('HOST_V2_CLEANUP', type(error).__name__,
            [(item.name, item.lineno) for item in traceback.extract_tb(error.__traceback__)] if error else [],
            'drained', owner.native_drained, 'stopped', owner._stopped,
            'control_done', owner._guardian_task.done() if owner._guardian_task else None,
            'failure_type', type(owner._failure).__name__)

    async def consume(self, owner):
        while True:
            packet = await owner.receive()
            self.packets.append(packet)
            self.assertEqual(packet['sequence'], len(self.packets))
            self.assertEqual(set(packet), {'version', 'sequence', 'source', 'source_sequence',
                'launch_nonce', 'worker_pid', 'worker_birth', 'body'})
            if packet['body']['type'] == 'engine_start_requested':
                await owner.send_worker({'type': 'engine_start_ack', **self.identity})
            if packet['body']['type'] == 'worker_complete': break
        try: await owner.aclose()
        except BaseException:
            self.cleanup_diagnostic(owner)
            raise

    async def test_true_three_actor_private_startup_join_and_actual_terminal_drain(self):
        owner = self.owner()
        # Constructor snapshots must survive mutation before any process starts.
        self.guardian['source']['files']['improvement_worker.py'] = '0' * 64
        self.options['image_policy']['sha256'] = '0' * 64
        api = self.mod._host_windows()
        original, sources = api.duplicate, []
        def duplicate(*args):
            sources.append(args[0])
            return original(*args)
        with patch.object(api, 'duplicate', side_effect=duplicate):
            await owner.start(self.startup)
        self.assertEqual(len(sources), 4)
        self.assertTrue(all(value == int(owner._process._handle) for value in sources))
        self.assertNotEqual(owner.guardian_identity['guardian_pid'], os.getpid())
        self.assertNotEqual(owner.worker_identity['worker_pid'], owner.guardian_identity['guardian_pid'])
        await self.consume(owner)
        self.assertEqual([item['purpose'] for item in self.joins], [item['purpose'] for item in self.invocations])
        self.assertTrue(owner.closed)
        for path in self.options['fences']:
            directory = Path(path + '.native')
            self.assertFalse(directory.exists() and any(directory.iterdir()))
        self.assertTrue(any(packet['body']['type'] == 'engine_event' for packet in self.packets))

    async def test_pending_durable_append_cannot_authorize_after_close(self):
        held, release = asyncio.Event(), asyncio.Event()
        async def pending(joined):
            self.joins.append(joined); held.set(); await release.wait()
            return {'decision': 'allow', 'durable_evidence_hash': 'd' * 64}
        owner = self.owner(persist_before_allow=pending)
        await owner.start(self.startup)
        await asyncio.wait_for(held.wait(), 8)
        closing = asyncio.create_task(owner.aclose())
        await asyncio.sleep(.01)
        release.set()
        await closing
        self.assertTrue(owner.closed)
        self.assertFalse(any(packet['body']['type'] == 'engine_event' for packet in self.packets))

    async def test_ambiguous_stop_send_needs_actual_drain_and_preserves_real_guardian_exit_code(self):
        held, release = asyncio.Event(), asyncio.Event()
        async def pending(joined):
            held.set(); await release.wait()
            return {'decision': 'allow', 'durable_evidence_hash': 'd' * 64}
        # Explicit engineering guardian exits 17 only after its real native drain.
        target = self.source / 'improvement_native_lifetime.py'
        with target.open('a', encoding='utf-8') as output:
            output.write('\nif __name__ == "__main__": raise SystemExit(17)\n')
        self.guardian['source']['files'][target.name] = hashlib.sha256(target.read_bytes()).hexdigest()
        owner = self.owner(persist_before_allow=pending)
        await owner.start(self.startup); await asyncio.wait_for(held.wait(), 8)
        original = owner._send_command
        async def ambiguous(kind, **extra):
            result = await original(kind, **extra)
            if kind == 'stop':
                release.set()
                raise OSError('engineering_post_send_ambiguity')
            return result
        try:
            with patch.object(owner, '_send_command', side_effect=ambiguous):
                await owner.aclose()
        finally:
            release.set()
            # The independent actual guardian reader is retained across failure.
            await asyncio.wait_for(owner._drained_event.wait(), 8)
        self.assertTrue(owner.closed)
        self.assertEqual(owner._process.returncode, 17)

    async def test_completed_worker_gets_bounded_natural_drain_before_any_stop(self):
        release = self.scratch / 'engineering-release'
        target = self.source / 'improvement_worker.py'
        text = target.read_text(encoding='utf-8')
        text = text.replace(' await private.aclose()\n',
            ' while not os.path.exists(' + repr(str(release)) + '): await asyncio.sleep(.005)\n await private.aclose()\n')
        target.write_text(text, encoding='utf-8')
        self.guardian['source']['files'][target.name] = hashlib.sha256(target.read_bytes()).hexdigest()
        owner = self.owner(); await owner.start(self.startup)
        while True:
            packet = await owner.receive(); self.packets.append(packet)
            if packet['body']['type'] == 'engine_start_requested':
                await owner.send_worker({'type': 'engine_start_ack', **self.identity})
            if packet['body']['type'] == 'worker_complete': break
        self.assertFalse(owner.native_drained)
        self.assertFalse(owner._api.terminal(owner._slots['process'].value))
        stops = []
        original = owner._send_command
        async def track(kind, **extra):
            if kind == 'stop': stops.append(owner.native_drained)
            return await original(kind, **extra)
        with patch.object(owner, '_send_command', side_effect=track):
            closing = asyncio.create_task(owner.aclose())
            try:
                await asyncio.sleep(.025)
                self.assertEqual(stops, [], 'completed live worker was stopped before bounded natural drain')
            finally:
                release.write_bytes(b'engineering-only')
                await closing
        self.assertTrue(owner.native_drained); self.assertTrue(owner.closed)
        self.assertEqual(stops, [])

    async def test_before_engine_accounting_ack_remains_separate_from_image_authorization(self):
        owner = self.owner(); await owner.start(self.startup)
        while True:
            packet = await owner.receive(); self.packets.append(packet)
            if packet['body']['type'] == 'engine_start_requested': break
        self.assertEqual([item['purpose'] for item in self.joins],
                         ['adapter_version', 'auth_status', 'sdk_version', 'query'])
        await owner.aclose()
        self.assertFalse(any(packet['body']['type'] == 'engine_event' for packet in self.packets))


if __name__ == '__main__':
    unittest.main()
