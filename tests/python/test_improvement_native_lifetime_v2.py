"""Guardian v2 engineering fixtures; no SDK, model, account or runtime registration."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import base64
import hashlib
import importlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import socket
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch


NONCE = 'a' * 64
INVOCATION = 'b' * 64


def policy():
    pin = {'path': r'C:\Python\python.exe', 'sha256': 'a' * 64, 'volume_serial_64': 1, 'file_id_128': 'b' * 32}
    return {'version': 1, 'scratch': r'C:\scratch', 'bootstrap': {
        'version': 1, 'entrypoint': 'trial', 'runtime': {'executable': pin, 'dll': {**pin, 'path': r'C:\Python\python312.dll'}},
        'source': {'root': r'C:\source', 'files': {'improvement_native_bootstrap.py': 'c' * 64,
            'improvement_native_image.py': 'd' * 64, 'improvement_worker.py': 'e' * 64}},
        'imports': {'site_packages': r'C:\packages', 'files': {}}}}


def arguments():
    return dict(image_policy={'version': 1, 'path': r'C:\selected.exe', 'sha256': 'd' * 64},
        fences=[r'C:\scratch\brain.lock', r'C:\scratch\attempt.lock'], launch_nonce=NONCE,
        invocations=[{'purpose': 'query', 'nonce': INVOCATION}], timeout=3, close_timeout=3)


def component(test):
    mod = importlib.import_module('improvement_native_lifetime')
    test.assertTrue(hasattr(mod, 'GuardianV2'), 'guardian-first canonical v2 owner missing')
    return mod


def wire(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')
    return struct.pack('!I', len(raw)) + raw


async def receive(sock):
    async def exact(size):
        raw = bytearray()
        while len(raw) < size:
            part = await asyncio.get_running_loop().sock_recv(sock, size - len(raw))
            if not part: raise EOFError('fixture peer closed')
            raw.extend(part)
        return bytes(raw)
    size, = struct.unpack('!I', await exact(4))
    if not 0 < size <= 65536: raise AssertionError('fixture bounded frame')
    return json.loads(await exact(size))


class GuardianV2ContractTests(unittest.TestCase):
    def test_closed_inputs_reject_private_dispatch_and_nonbuiltin_authority(self):
        cls = component(self).GuardianV2
        for extra in ({'argv': ['private']}, {'env': {}}, {'config': {}}, {'model': 'private'}):
            with self.subTest(extra=extra), self.assertRaises((ValueError, TypeError)):
                cls({**policy(), **extra}, **arguments())
        class Text(str): pass
        changes = [dict(launch_nonce=True), dict(launch_nonce=Text(NONCE)), dict(timeout=math.inf),
            dict(close_timeout=True), dict(invocations=[]), dict(invocations=[{'purpose': 'other', 'nonce': INVOCATION}]),
            dict(invocations=[{'purpose': 'query', 'nonce': INVOCATION}] * 2),
            dict(image_policy={**arguments()['image_policy'], 'auth_home': r'C:\private'}),
            dict(fences=[r'C:\scratch\brain.lock'] * 2)]
        for change in changes:
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError)):
                cls(policy(), **{**arguments(), **change})

    def test_constructor_does_not_create_process_or_take_private_input(self):
        mod = component(self)
        with patch('subprocess.Popen', side_effect=AssertionError('constructor must not spawn')):
            value = policy()
            owner = mod.GuardianV2(value, **arguments())
            value['bootstrap']['entrypoint'] = 'operation'
            self.assertFalse(owner.closed)
            self.assertEqual(owner.state, 'fresh')

    def test_closed_startup2_reader_rejects_duplicate_private_depth_and_types(self):
        mod = component(self)
        self.assertTrue(hasattr(mod, 'read_guardian_startup2'), 'closed guardian startup2 reader missing')
        packet = {'version': 2, 'type': 'guardian_startup2', 'control_share': base64.b64encode(b'fixture').decode(),
            'policy': policy(), **arguments(), 'lifetime_timeout': 300}
        raw = wire(packet)[4:] + b'\n'
        actual = mod.read_guardian_startup2(io.BytesIO(raw))
        self.assertEqual(actual, packet)
        actual['policy']['bootstrap']['entrypoint'] = 'operation'
        self.assertEqual(packet['policy']['bootstrap']['entrypoint'], 'trial')
        bad = [raw[:-1], b'{"version":2,"version":2}\n', b'{"x":' + b'[' * 30 + b'0' + b']' * 30 + b'}\n',
            wire({**packet, 'argv': ['private']})[4:] + b'\n', wire({**packet, 'version': True})[4:] + b'\n',
            wire({**packet, 'control_share': 'invalid!'})[4:] + b'\n']
        for value in bad:
            with self.subTest(size=len(value)), self.assertRaises((ValueError, OSError, TypeError)):
                mod.read_guardian_startup2(io.BytesIO(value))

    def test_legacy_main_consumes_one_packet_and_routes_without_v2_authority(self):
        from types import SimpleNamespace
        mod = component(self)
        self.assertTrue(hasattr(mod, 'guardian_main'), 'versioned guardian startup routing missing')
        packet = {'pid': 123, 'locks': [r'C:\a.lock', r'C:\b.lock'], 'suspended': False}
        stream = io.BytesIO(json.dumps(packet).encode() + b'\nUNREAD\n')
        seen = []
        with patch.object(sys, 'stdin', SimpleNamespace(buffer=stream)), patch.object(mod, 'supervise', side_effect=seen.append):
            mod.guardian_main()
        self.assertEqual(seen, [packet])
        self.assertEqual(stream.read(), b'UNREAD\n')

    def test_lifetime_budget_accepts_public_234s_and_rejects_unbounded_extensions(self):
        cls = component(self).GuardianV2
        owner = cls(policy(), **arguments(), lifetime_timeout=234)
        self.assertEqual(owner.state, 'fresh')
        for value in (True, 0, -1, math.inf, 300.01):
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                cls(policy(), **arguments(), lifetime_timeout=value)


class GuardianV2ControlIOTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_raw_control_io_is_permanently_unproven(self):
        mod = component(self)
        left, right = socket.socketpair()
        self.addCleanup(left.close); self.addCleanup(right.close)
        control = mod._GuardianControl(left, 1)
        receiver = asyncio.create_task(control.receive())
        while not control.tasks or not control.buffers: await asyncio.sleep(0)
        raw_io = control.tasks[0]
        raw_io.cancel()
        with self.assertRaises(mod.GuardianV2Error): await receiver
        with self.assertRaises(mod.GuardianV2Error): await control.close(1)
        self.assertFalse(control.closed)
        self.assertTrue(control.socket_closed)
        self.assertTrue(control.buffers)
        self.assertIn(raw_io, control.tasks)
        self.assertTrue(raw_io.cancelled())
        with self.assertRaises(mod.GuardianV2Error): await control.close(1)
        self.assertFalse(control.closed)


_STUB = r'''import os,sys,json,asyncio,socket,subprocess
sys.path.insert(0,os.path.dirname(__file__))
from improvement_native_capture import NativeDebugInvocation
from improvement_image_channel import ImageMetadataChannel
p=json.loads(sys.stdin.buffer.readline(16384))
os.write(1,b'WORKER_STARTED\n')
if p['mode']=='root': sys.exit(0)
class Process:
 def __init__(self,p): self.p=p;self.pid=p.pid;self.stdin=p.stdin;self.stdout=p.stdout;self.stderr=p.stderr
 async def wait(self): return await self.p.wait()
 async def aclose(self):
  if self.stdin:self.stdin.close()
  await self.p.wait()
async def opener(command,**kw): return Process(await asyncio.create_subprocess_exec(*command,**kw))
async def main():
 import base64
 sock=socket.fromshare(base64.b64decode(p['share']))
 channel=ImageMetadataChannel(sock,role='worker',nonce=p['nonce'],worker_pid=os.getpid(),worker_birth=p['birth'])
 command=[p['exe'],'/d','/c','echo OWNED_NATIVE_MARKER']
 def validate(args): return args[1]==subprocess.list2cmdline(command)
 async with channel:
  async with NativeDebugInvocation(opener,purpose='sdk_query',nonce=p['nonce'],validate_create=validate,image_ack=channel.exchange) as owner:
   proc=await owner.open_process(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd=os.path.dirname(__file__),env={'SystemRoot':r'C:\Windows'})
   raw=await proc.stdout.read()
   await proc.wait()
   os.write(1,raw)
asyncio.run(main())
'''


@unittest.skipUnless(os.name == 'nt' and sys.flags.isolated, 'actual x64 guardian requires isolated fixture driver')
class GuardianV2WindowsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mod = component(self)
        from improvement_native_capture_win32 import backend
        from improvement_native_bootstrap import _runtime_paths
        from improvement_native_image import ImageReadGuard
        import msvcrt
        self.api, self.msvcrt = backend(), msvcrt
        self.temp = tempfile.TemporaryDirectory(prefix='guardian-v2-')
        self.root = Path(self.temp.name)
        self.source, self.packages = self.root / 'source', self.root / 'packages'
        self.source.mkdir(); self.packages.mkdir(); (self.root / 'scratch').mkdir()
        for name in ('improvement_native_image.py', 'improvement_native_capture.py',
                     'improvement_native_capture_win32.py', 'improvement_image_channel.py'):
            shutil.copyfile(SERVER / name, self.source / name)
        (self.source / 'improvement_native_bootstrap.py').write_text(_STUB, encoding='utf-8')
        (self.source / 'improvement_worker.py').write_text('# inert fixed target\n', encoding='utf-8')
        self.selected, self.foreign = self.root / 'selected.exe', self.root / 'foreign.exe'
        for path in (self.selected, self.foreign):
            shutil.copyfile(Path(os.environ['SystemRoot']) / 'System32/cmd.exe', path)
        def pin(path):
            digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
            with ImageReadGuard(path, digest) as guard, open(path, 'rb') as reader:
                actual = guard.compare_file_handle(msvcrt.get_osfhandle(reader.fileno()))['actual']
            return {key: actual[key] for key in ('sha256', 'volume_serial_64', 'file_id_128')} | {'path': path}
        self.policy = {'version': 1, 'scratch': str(self.root / 'scratch'), 'bootstrap': {
            'version': 1, 'entrypoint': 'trial', 'runtime': {name: pin(path) for name, path in _runtime_paths().items()},
            'source': {'root': str(self.source), 'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.source.iterdir()}},
            'imports': {'site_packages': str(self.packages), 'files': {}}}}
        self.options = {**arguments(), 'image_policy': {'version': 1, 'path': str(self.selected),
            'sha256': hashlib.sha256(self.selected.read_bytes()).hexdigest()},
            'fences': [str(self.root / 'brain.lock'), str(self.root / 'attempt.lock')], 'timeout': 8, 'close_timeout': 8}
        if self._testMethodName == 'test_delayed_unused_channel_preserves_short_actual_create_gate':
            self.options.update(timeout=8, lifetime_timeout=5)
        if self._testMethodName == 'test_held_create_authorization_keeps_short_deadline':
            self.options.update(timeout=0.05, lifetime_timeout=5)
        self.left, self.right = socket.socketpair()
        self.left.setblocking(False); self.right.setblocking(False)
        self.owner = self.mod.GuardianV2(self.policy, **self.options)
        self.start_gate = asyncio.Event()
        owner, control = self.owner, self.left
        async def launch():
            await self.start_gate.wait()
            return await owner.run(control)
        self.task = asyncio.create_task(launch())
        self.frames, self.fds, self.out_sequence = [], [], 0
        self.addAsyncCleanup(self.finish)

    async def finish(self):
        self.right.close()
        if not self.task.done(): self.task.cancel()
        try: await self.task
        except BaseException: pass
        try: await self.owner.aclose()
        except BaseException:
            import traceback
            print('FIXTURE_OWNED_STATE', self.owner._caps, 'pending',
                None if self.owner._pending is None else self.owner._pending.code,
                'exit', self.owner._seen_exit, 'terminal', self.owner._root_terminal,
                'births', self.owner._births, 'inventory_error', self.owner._inventory_error,
                'root_failure', repr(self.owner._root_failure), flush=True)
            traceback.print_exception(self.owner._cleanup_error)
            raise
        self.left.close()
        for fd in self.fds: os.close(fd)
        self.temp.cleanup()

    async def event(self):
        self.start_gate.set()
        try: value = await asyncio.wait_for(receive(self.right), 12)
        except EOFError:
            import traceback
            self.fail('fixture guardian closed before event: ' + ''.join(traceback.format_exception(self.owner._failure)))
        self.assertEqual(value['sequence'], len(self.frames) + 1)
        self.assertEqual(value['launch_nonce'], NONCE)
        self.frames.append(value)
        return value

    async def command(self, kind, **extra):
        self.out_sequence += 1
        value = {'version': 2, 'type': kind, 'sequence': self.out_sequence, 'launch_nonce': NONCE,
            'worker_pid': self.offer['worker_pid'], 'worker_birth': self.offer['worker_birth'], **extra}
        await asyncio.get_running_loop().sock_sendall(self.right, wire(value))

    async def start(self, mode='root', exe=None):
        self.offer = await self.event()
        self.assertEqual(self.offer['type'], 'launch_offer')
        self.assertTrue(self.offer['root_image']['matches'])
        self.assertEqual(self.offer['bootstrap_count'], 1)
        self.assertFalse(self.owner.closed)
        self.assertFalse((self.source / 'marker').exists())
        self.stdin = self.api.duplicate(self.offer['stdio']['stdin']['handle'])
        self.stdout = self.api.duplicate(self.offer['stdio']['stdout']['handle'])
        self.stderr = self.api.duplicate(self.offer['stdio']['stderr']['handle'])
        for name, flag in (('stdin', os.O_WRONLY), ('stdout', os.O_RDONLY), ('stderr', os.O_RDONLY)):
            fd = self.msvcrt.open_osfhandle(getattr(self, name), flag | os.O_BINARY)
            self.fds.append(fd); setattr(self, name + '_fd', fd)
        # Host adopted means retained source duplicates/shares; worker has not adopted yet.
        await self.command('adopted')
        sealed = await self.event()
        self.assertEqual(sealed['type'], 'stdio_sealed')
        self.assertTrue(sealed['all_data_pipes_closed'])
        image = self.offer['images'][0]
        if mode is not None:
            packet = {'mode': mode, 'exe': str(exe or self.selected), 'share': image['share'],
                'nonce': image['nonce'], 'birth': self.offer['worker_birth']}
            os.write(self.stdin_fd, (json.dumps(packet) + '\n').encode('ascii'))
        return sealed

    async def drain(self):
        while True:
            event = await self.event()
            if event['type'] == 'drained':
                self.assertEqual((event['root_terminal'], event['debug_exit'], event['job_active']), (True, True, 0))
                break
        await self.task
        self.assertTrue(self.owner.closed)
        for path in self.options['fences']:
            directory = Path(path + '.native')
            self.assertFalse(directory.exists() and any(directory.iterdir()))
        return os.read(self.stdout_fd, 16384)

    async def test_root_gate_seals_stdio_and_root_exit_drains_fences(self):
        await self.start()
        self.assertEqual(await self.drain(), b'WORKER_STARTED\n')

    async def test_selected_image_requires_matching_durable_authorization(self):
        await self.start('image')
        observed = await self.event()
        self.assertEqual(observed['type'], 'image_observed')
        self.assertTrue(observed['comparison']['matches'])
        self.assertNotIn('argv', json.dumps(observed))
        await self.command('image_authorize', purpose='query', nonce=INVOCATION,
            native_pid=observed['native_pid'], native_birth=observed['native_birth'],
            observation_hash=observed['observation_hash'], dispatch_hash='c' * 64,
            durable_evidence_hash='d' * 64, decision='allow')
        raw = await self.drain()
        self.assertIn(b'OWNED_NATIVE_MARKER', raw)

    async def test_identical_foreign_file_cannot_allow(self):
        await self.start('image', self.foreign)
        observed = await self.event()
        self.assertFalse(observed['comparison']['matches'])
        self.assertEqual(observed['comparison']['selected']['sha256'], observed['comparison']['actual']['sha256'])
        await self.command('image_authorize', purpose='query', nonce=INVOCATION,
            native_pid=observed['native_pid'], native_birth=observed['native_birth'],
            observation_hash=observed['observation_hash'], dispatch_hash='c' * 64,
            durable_evidence_hash='d' * 64, decision='allow')
        self.assertNotIn(b'OWNED_NATIVE_MARKER', await self.drain())

    async def test_explicit_deny_cannot_resume_native_even_if_image_matches(self):
        await self.start('image')
        observed = await self.event()
        await self.command('image_authorize', purpose='query', nonce=INVOCATION,
            native_pid=observed['native_pid'], native_birth=observed['native_birth'],
            observation_hash=observed['observation_hash'], dispatch_hash='c' * 64,
            durable_evidence_hash='d' * 64, decision='deny')
        self.assertNotIn(b'OWNED_NATIVE_MARKER', await self.drain())

    async def test_wrong_observation_authorization_cannot_resume_native(self):
        await self.start('image')
        observed = await self.event()
        await self.command('image_authorize', purpose='query', nonce=INVOCATION,
            native_pid=observed['native_pid'], native_birth=observed['native_birth'],
            observation_hash='f' * 64, dispatch_hash='c' * 64,
            durable_evidence_hash='d' * 64, decision='allow')
        self.assertNotIn(b'OWNED_NATIVE_MARKER', await self.drain())

    async def test_worker_death_held_create_uses_job_drain_not_foreign_continue(self):
        await self.start('image')
        self.assertEqual((await self.event())['type'], 'image_observed')
        self.api.terminate(self.owner._caps['process_handle'])
        self.assertNotIn(b'OWNED_NATIVE_MARKER', await self.drain())

    async def test_eof_held_create_drains_without_allow(self):
        await self.start('image')
        self.assertEqual((await self.event())['type'], 'image_observed')
        self.right.shutdown(socket.SHUT_RDWR); self.right.close()
        await self.task
        self.assertTrue(self.owner.closed)
        self.assertTrue(self.owner.native_drained)
        self.assertNotIn(b'OWNED_NATIVE_MARKER', os.read(self.stdout_fd, 16384))

    async def test_repeated_cancel_before_adopted_drains_root_and_unadopted_shares(self):
        self.offer = await self.event()
        self.task.cancel(); await asyncio.sleep(0); self.task.cancel()
        with self.assertRaises(asyncio.CancelledError): await self.task
        self.assertTrue(self.owner.closed)
        self.assertTrue(self.owner.native_drained)

    async def test_wrong_binding_and_replay_refuse_without_root_private_input(self):
        self.offer = await self.event()
        await self.command('adopted', worker_birth=self.offer['worker_birth'] + 1)
        await self.task
        self.assertTrue(self.owner.closed)
        self.assertTrue(self.owner.native_drained)

    async def test_partial_share_failure_drains_exact_unadopted_target(self):
        original = socket.socket.share
        def failed_share(sock, pid):
            original(sock, pid)
            raise OSError('fixture failure after actual target share creation')
        with patch.object(socket.socket, 'share', failed_share):
            self.start_gate.set()
            await self.task
        self.assertTrue(self.owner.native_drained)
        self.assertTrue(self.owner.closed)
        self.assertTrue(self.owner._root_terminal and self.owner._seen_exit)

    async def test_known_rejected_close_retains_guard_fences_and_can_retry(self):
        await self.start()
        with patch.object(self.owner._api, 'close', side_effect=self.mod._GuardianCloseRejected('fixture rejected native close')):
            with self.assertRaises(self.mod.GuardianV2CleanupError) as error: await self.task
        self.assertIs(error.exception.owner, self.owner)
        self.assertFalse(self.owner.closed or self.owner.native_drained)
        self.assertIn(self.owner, self.mod._V2_RETAINED)
        self.assertTrue(self.owner._root_terminal and self.owner._seen_exit)
        self.assertTrue(self.owner._guards)
        self.assertTrue(all(any(Path(path + '.native').iterdir()) for path in self.options['fences']))
        await self.owner.aclose()
        self.assertTrue(self.owner.closed and self.owner.native_drained)

    async def test_missing_nondirectory_or_linked_fence_parent_refuses_before_worker(self):
        self.right.close()
        self.task.cancel()
        try: await self.task
        except asyncio.CancelledError: pass
        await self.owner.aclose()
        import subprocess
        link = self.root / 'linked'
        result = subprocess.run([str(self.selected), '/d', '/c', 'mklink', '/J', str(link), str(self.root / 'scratch')],
            capture_output=True, timeout=5, creationflags=0x08000000, env={'SystemRoot': os.environ['SystemRoot']})
        self.assertEqual(result.returncode, 0, result.stderr)
        for bad in (self.root / 'missing' / 'brain.lock', self.selected / 'brain.lock', link / 'brain.lock'):
            self.left, peer = socket.socketpair(); self.left.setblocking(False)
            self.addCleanup(peer.close)
            self.owner = self.mod.GuardianV2(self.policy, **{**self.options,
                'fences': [str(bad), self.options['fences'][1]]})
            await self.owner.run(self.left)
            self.assertIsNone(self.owner._caps)
            self.assertTrue(self.owner.closed)

    async def test_replayed_adopted_drains_before_any_private_startup(self):
        await self.start(mode=None)
        await self.command('adopted')
        self.assertEqual(await self.drain(), b'')

    async def test_oversized_control_frame_refuses_without_resynchronization(self):
        self.offer = await self.event()
        await asyncio.get_running_loop().sock_sendall(self.right, struct.pack('!I', 65537))
        await self.task
        self.assertTrue(self.owner.closed and self.owner.native_drained)

    async def test_precreate_refusal_releases_only_empty_owned_job(self):
        import improvement_fixed_worker_launch as factory
        with patch.object(factory._backend(), 'create', side_effect=OSError('fixture before CreateProcess')):
            self.start_gate.set()
            await self.task
        self.assertIsNone(self.owner._caps)
        self.assertTrue(self.owner.closed and self.owner.native_drained)

    async def test_postcreate_refusal_retains_raw_root_until_actual_debug_exit(self):
        import improvement_fixed_worker_launch as factory
        api = factory._backend()
        original = api.create
        def fail_after(*args):
            original(*args)
            raise OSError('fixture after actual CreateProcess output slots filled')
        with patch.object(api, 'create', fail_after):
            self.start_gate.set()
            try: await self.task
            except self.mod.GuardianV2CleanupError:
                import traceback
                traceback.print_exception(self.owner._cleanup_error)
                raise
        self.assertTrue(self.owner._factory.created)
        self.assertIsNone(self.owner._caps['birth'])  # Proves the postcheck never ran.
        self.assertTrue(self.owner._root_terminal and self.owner._seen_exit)
        self.assertTrue(self.owner.closed and self.owner.native_drained)

    async def test_pump_exception_is_refusal_after_actual_exit_drain(self):
        await self.start(mode=None)
        original, calls = self.owner._debug.next_event, []
        def one_failure():
            if not calls:
                calls.append(True)
                raise OSError('fixture debug read failed')
            return original()
        with patch.object(self.owner._debug, 'next_event', one_failure):
            self.assertEqual(await self.drain(), b'')
        self.assertEqual(self.frames[-1]['reason'], 'refused')

    async def test_delayed_unused_channel_preserves_short_actual_create_gate(self):
        await self.start(mode=None)
        fixed_deadline = self.owner._lifetime_deadline
        await asyncio.sleep(0.10)  # Deliberately unused after adoption; no CREATE bytes yet.
        pending_image = self.owner._images['query']
        self.assertIsNone(pending_image['task'])
        self.assertIsNone(pending_image['deadline'])
        self.assertIsNone(self.owner._channels['query']._deadline)
        image = self.offer['images'][0]
        packet = {'mode': 'image', 'exe': str(self.selected), 'share': image['share'],
            'nonce': image['nonce'], 'birth': self.offer['worker_birth']}
        os.write(self.stdin_fd, (json.dumps(packet) + '\n').encode('ascii'))
        observed = await self.event()
        self.assertEqual(observed['type'], 'image_observed')
        await self.command('image_authorize', purpose='query', nonce=INVOCATION,
            native_pid=observed['native_pid'], native_birth=observed['native_birth'],
            observation_hash=observed['observation_hash'], dispatch_hash='c' * 64,
            durable_evidence_hash='d' * 64, decision='allow')
        self.assertIn(b'OWNED_NATIVE_MARKER', await self.drain())
        self.assertEqual(self.owner._lifetime_deadline, fixed_deadline)

    async def test_held_create_authorization_keeps_short_deadline(self):
        await self.start('image')
        self.assertEqual((await self.event())['type'], 'image_observed')
        await asyncio.sleep(0.10)
        self.assertNotIn(b'OWNED_NATIVE_MARKER', await self.drain())
        self.assertEqual(self.frames[-1]['reason'], 'refused')


if __name__ == '__main__': unittest.main()
