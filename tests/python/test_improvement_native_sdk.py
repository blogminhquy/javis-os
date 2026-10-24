"""Native SDK component; fake adapters and local SDK builder, no account/client."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import copy
import hashlib
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
    test.assertIsNotNone(importlib.util.find_spec('improvement_native_sdk'), 'native SDK owner missing')
    return importlib.import_module('improvement_native_sdk')


def pin():
    return dict(version=1, provider='anthropic-cli', engine_id='claude-sdk', model='selected-model',
        reasoning='high', cli_path=r'C:\owned\selected.exe', cli_hash='1' * 64, cli_version='2.1.99',
        sdk_version='0.2.116', profile_version='native-test', profile_hash='2' * 64)


class Channel:
    def __init__(self, purpose, order):
        self._nonce = hashlib.sha256(purpose.encode()).hexdigest()
        self._role = 'worker'
        self._worker_pid, self._worker_birth = 101, 102
        self.order, self.closed, self.decision = order, False, 'allow'

    async def exchange(self, frame):
        self.order.append(('image', frame['nonce']))
        return dict(version=1, type='native_image_ack', nonce=self._nonce, worker_birth=102,
            native_birth=202, decision=self.decision)

    async def aclose(self): self.closed = True


class Receive:
    def __init__(self, values=()): self.values = list(values)
    async def receive(self, maximum=65536):
        import anyio
        if not self.values: raise anyio.EndOfStream
        return self.values.pop(0)
    async def aclose(self): pass


class Send:
    def __init__(self): self.sent, self.error = [], None
    async def send(self, data):
        if self.error: raise self.error
        self.sent.append(data)
    async def aclose(self): pass


class Process:
    def __init__(self, output=b'2.1.99 (local)\n', code=0):
        self.pid, self.returncode = 201, code
        self.stdout, self.stderr, self.stdin = Receive([output]), Receive(), Send()
        self.closed = False
        self.closed_event = asyncio.Event()
    async def wait(self):
        if self.returncode is None: self.returncode = 0
        return self.returncode
    async def aclose(self): self.closed = True; self.closed_event.set()
    def terminate(self): self.returncode = 1
    def kill(self): self.returncode = 1


class Capture:
    instances, outputs, fail_close = [], [], False
    def __init__(self, opener, **kwargs):
        self.options, self.process = kwargs, None
        self.closed, self.terminal = False, False
        self.__class__.instances.append(self)
    async def __aenter__(self): return self
    async def open_process(self, argv, **kwargs):
        self.argv, self.kwargs = copy.deepcopy(argv), copy.deepcopy(kwargs)
        raw = (None, subprocess.list2cmdline(argv), None, None, True, 0x08000006,
            kwargs.get('env'), kwargs.get('cwd'), None)
        if self.options['validate_create'](raw) is not True: raise OSError('capture refused')
        self.process = self.__class__.outputs.pop(0) if self.__class__.outputs else Process(
            code=None if self.options['purpose'] == 'sdk_query' else 0)
        frame = dict(version=1, type='native_image_create', nonce=self.options['nonce'], worker_pid=101,
            worker_birth=102, creator_thread=103, native_pid=201, native_birth=202, native_tid=203,
            native_thread_birth=204, hfile=205, hprocess=206, hthread=207, bootstrap_count=1, kill_on_exit=True)
        ack = await self.options['image_ack'](frame)
        if ack['decision'] != 'allow': raise OSError('capture denied')
        return self.process
    async def aclose(self):
        if self.__class__.fail_close: raise OSError('PRIVATE_CLOSE')
        if self.process: await self.process.aclose()
        self.closed = self.terminal = True
    async def __aexit__(self, *args): await self.aclose()


@unittest.skipUnless(os.name == 'nt' and sys.flags.isolated,
                     'owned SDK transport requires isolated Windows driver')
class NativeSDKTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.m = component(self)
        self.channel_patch = patch.object(self.m, 'ImageMetadataChannel', Channel)
        self.channel_patch.start()
        self.addCleanup(self.channel_patch.stop)
        self.order = []
        self.channels = {name: Channel(name, self.order) for name in ('adapter_version', 'auth_status', 'sdk_version', 'query')}
        async def emit(frame): self.order.append(('dispatch', copy.deepcopy(frame)))
        self.emit = emit
        from improvement_native_protocol import _ENV_PATHS, _ENV_FIXED
        self.env = {**{name: r'C:\empty' for name in _ENV_PATHS}, **_ENV_FIXED}
        self.cwd = r'C:\work'
        self.owner = self.m.NativeInvocationSet(pin(), image_channels=self.channels, emit_dispatch=emit,
            environment=self.env, cwd=self.cwd, source_policy_hash='3' * 64)
        Capture.instances, Capture.outputs, Capture.fail_close = [], [], False
        self.capture_patch = patch.object(self.m, 'NativeDebugInvocation', Capture)
        self.capture_patch.start()
        self.addCleanup(self.capture_patch.stop)
        self.hash_patch = patch.object(self.m, '_hash_cli', return_value=pin()['cli_hash'])
        self.hash_patch.start()
        self.addCleanup(self.hash_patch.stop)

    async def asyncTearDown(self):
        Capture.fail_close = False
        if not self.owner.closed: await self.owner.aclose()

    async def test_dummy_environment_cannot_enter_default_constructor_or_unadopted_factory(self):
        from improvement_qualification_environment import dummy_environment
        from improvement_native_worker import NativeWorkerSessionV2
        from test_improvement_qualification_protocol import startup
        environment = dummy_environment(self.env, endpoint='http://127.0.0.1:15432')
        with self.assertRaises(ValueError):
            self.m.NativeInvocationSet(pin(), image_channels=self.channels, emit_dispatch=self.emit,
                environment=environment, cwd=self.cwd, source_policy_hash='3' * 64)
        owner = NativeWorkerSessionV2.from_startup3(startup('preflight'), namespace='preflight')
        try:
            with self.assertRaisesRegex(TypeError, 'active_qualification_worker_required'):
                self.m.NativeInvocationSet.from_qualification_worker(owner)
            with self.assertRaises(TypeError): self.m.NativeInvocationSet.from_qualification_worker(object())
            self.assertEqual(Capture.instances, [])
        finally: await owner.aclose()

    async def preflight(self):
        Capture.outputs = [Process(), Process(json.dumps(dict(loggedIn=True, authMethod='claude.ai',
            apiProvider='firstParty', subscriptionType='max')).encode())]
        return await self.owner.preflight(managed_policy='absent')

    def options(self):
        from claude_agent_sdk import ClaudeAgentOptions
        return ClaudeAgentOptions(cli_path=pin()['cli_path'], cwd=self.cwd, system_prompt='PRIVATE_SYSTEM',
            model='selected-model', effort='high', tools=[], allowed_tools=['mcp__fixture__fixture_read'],
            mcp_servers={'fixture': {'type': 'sdk', 'name': 'fixture', 'instance': object()}},
            strict_mcp_config=True, setting_sources=[], permission_mode='default',
            settings='{"fastMode":false,"disableAllHooks":true}',
            extra_args=dict.fromkeys(('no-session-persistence', 'disable-slash-commands', 'no-chrome', 'restricted', 'safe-mode')),
            env=dict(self.env))

    def policy(self):
        return dict(version=2, cli_path=pin()['cli_path'], model='selected-model', reasoning='high',
            prompt_hash=hashlib.sha256(b'PRIVATE_SYSTEM').hexdigest(), cwd=self.cwd,
            tools=['mcp__fixture__fixture_read'], tool_policy='fixture_only')

    def transport(self, callback=None):
        async def noop(*args, **kwargs): pass
        return self.owner.transport(self.options(), query_policy=self.policy(), on_user_write=callback or noop)

    async def connect(self, transport):
        with patch.dict(os.environ, self.env, clear=True): await transport.connect()

    async def test_stable_preflight_and_dispatch_before_image(self):
        runtime = await self.preflight()
        self.assertEqual(set(runtime), {'platform', 'cli_hash', 'sdk_version', 'profile_hash', 'managed_policy', 'cli_version', 'auth'})
        self.assertEqual(runtime['cli_version'], '2.1.99')
        self.assertTrue(runtime['auth']['logged_in'])
        self.assertEqual([kind for kind, _ in self.order], ['dispatch', 'image', 'dispatch', 'image'])
        self.assertNotIn('native_pid', runtime)
        self.assertNotIn('nonce', runtime)
        with self.assertRaises(OSError): await self.preflight()

    async def test_strict_constructor_rejects_pin_environment_channels_and_callback_types(self):
        good = dict(image_channels=self.channels, emit_dispatch=self.emit, environment=self.env,
            cwd=self.cwd, source_policy_hash='3' * 64)
        cases = [dict(environment={'HOME': 'PRIVATE_ENV'}), dict(source_policy_hash=True),
            dict(image_channels={'adapter_version': self.channels['adapter_version']}),
            dict(emit_dispatch=lambda frame: None), dict(cwd='relative')]
        for change in cases:
            with self.subTest(fields=list(change)), self.assertRaises((ValueError, TypeError, OSError)):
                self.m.NativeInvocationSet(pin(), **{**good, **change})
        wrong = pin(); wrong['version'] = True
        with self.assertRaises((ValueError, TypeError, OSError)): self.m.NativeInvocationSet(wrong, **good)

    async def test_constructor_snapshots_private_pin_and_environment(self):
        self.env['HOME'] = r'C:\MUTATED'
        await self.preflight()
        self.assertEqual(Capture.instances[0].kwargs['env']['HOME'], r'C:\empty')

    async def test_preflight_failure_and_private_callback_errors_are_sanitized(self):
        Capture.outputs = [Process(b'PRIVATE_BAD_VERSION')]
        with self.assertRaises(OSError) as caught: await self.owner.preflight(managed_policy='absent')
        self.assertNotIn('PRIVATE', str(caught.exception))
        self.assertTrue(Capture.instances[0].closed)

    async def test_actual_sdk_builder_stdio_and_saved_global_opener_unchanged(self):
        await self.preflight()
        from claude_agent_sdk._internal.transport import subprocess_cli as sdk
        options = self.options()
        saved_anyio, saved_open = sdk.anyio, sdk.anyio.open_process
        async def callback(*args, **kwargs): pass
        transport = self.owner.transport(options, query_policy=self.policy(), on_user_write=callback)
        self.assertIsNone(options.permission_prompt_tool_name)
        self.assertEqual(transport._options.permission_prompt_tool_name, 'stdio')
        await self.connect(transport)
        self.assertIs(sdk.anyio, saved_anyio)
        self.assertIs(sdk.anyio.open_process, saved_open)
        self.assertEqual([entry.options['purpose'] for entry in Capture.instances],
            ['isolated_preflight', 'isolated_preflight', 'sdk_version', 'sdk_query'])
        query = Capture.instances[-1]
        self.assertIs(transport._process, query.process)
        self.assertFalse(query.closed)
        await transport.close()
        self.assertTrue(query.closed)

    async def test_skip_environment_cannot_bypass_sdk_version(self):
        await self.preflight()
        transport = self.transport()
        with patch.dict(os.environ, {**self.env, 'CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK': '1'}, clear=True):
            with self.assertRaises(OSError): await transport.connect()
        self.assertFalse(any(x.options['purpose'] == 'sdk_query' for x in Capture.instances))

    async def test_query_environment_drift_refused_before_actual_creation(self):
        await self.preflight()
        transport = self.transport()
        with patch.dict(os.environ, {**self.env, 'PRIVATE_AMBIENT': 'SECRET'}, clear=True):
            with self.assertRaises(OSError) as caught: await transport.connect()
        self.assertNotIn('SECRET', str(caught.exception))
        self.assertFalse(any(x.options['purpose'] == 'sdk_query' for x in Capture.instances))

    async def test_fresh_single_transport_and_query_policy_required(self):
        with self.assertRaises(OSError): self.transport()
        await self.preflight()
        options = self.options(); options.resume = 'PRIVATE_SESSION'
        with self.assertRaises((OSError, ValueError)): self.owner.transport(options, query_policy=self.policy(), on_user_write=self.emit)
        transport = self.transport()
        with self.assertRaises(OSError): self.transport()
        await transport.close()

    async def test_completed_original_user_write_callback_identity_and_control_exclusion(self):
        await self.preflight()
        calls = []
        async def callback(data, **identity): calls.append((data, identity))
        transport = self.transport(callback)
        await self.connect(transport)
        original = transport._process
        await transport.write('{"type":"control_request"}\n')
        self.assertEqual(calls, [])
        raw = json.dumps(dict(type='user', message=dict(role='user', content='PRIVATE_USER'),
            parent_tool_use_id=None, session_id='default')) + '\n'
        await transport.write(raw)
        self.assertEqual(calls[0][0], raw)
        self.assertIs(calls[0][1]['process'], original)
        self.assertIs(calls[0][1]['stdin'], original.stdin)
        self.assertEqual(calls[0][1]['creation']['native_pid'], original.pid)
        self.assertEqual(calls[0][1]['dispatch_nonce'], self.channels['query']._nonce)
        self.assertIn(b'PRIVATE_USER', b''.join(original.stdin.sent))
        with self.assertRaises(OSError): await transport.write(raw)

    async def test_failed_and_cancelled_send_never_emits_completed_proof(self):
        await self.preflight()
        calls = []
        async def callback(*args, **kwargs): calls.append(args)
        transport = self.transport(callback); await self.connect(transport)
        original = transport._process
        original.stdin.error = OSError('PRIVATE_SEND')
        with self.assertRaises(OSError) as caught: await transport.write('{"type":"user"}\n')
        self.assertEqual(calls, [])
        self.assertNotIn('PRIVATE', str(caught.exception))
        self.assertTrue(Capture.instances[-1].closed)

    async def test_user_callback_failure_drains_and_refuses_completion(self):
        await self.preflight()
        async def callback(*args, **kwargs): raise ValueError('PRIVATE_USER_CALLBACK')
        transport = self.transport(callback); await self.connect(transport)
        with self.assertRaises(OSError) as caught: await transport.write('{"type":"user"}\n')
        self.assertNotIn('PRIVATE', str(caught.exception))
        self.assertTrue(Capture.instances[-1].closed)

    async def test_user_callback_cancellation_drains_before_caller_returns(self):
        await self.preflight()
        entered = asyncio.Event()
        async def callback(*args, **kwargs): entered.set(); await asyncio.Event().wait()
        transport = self.transport(callback); await self.connect(transport)
        task = asyncio.create_task(transport.write('{"type":"user"}\n'))
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertTrue(Capture.instances[-1].closed)

    async def test_cancelled_original_send_has_no_callback_and_drains(self):
        await self.preflight()
        calls, entered = [], asyncio.Event()
        async def callback(*args, **kwargs): calls.append(args)
        transport = self.transport(callback); await self.connect(transport)
        process = transport._process
        send_tasks = []
        async def blocked(data):
            send_tasks.append(asyncio.current_task()); entered.set()
            await process.closed_event.wait()
            raise OSError('inert_closed_pipe')
        transport._process.stdin.send = blocked
        task = asyncio.create_task(transport.write('{"type":"user"}\n'))
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertEqual(calls, [])
        self.assertTrue(Capture.instances[-1].closed)
        self.assertTrue(send_tasks[0].done())
        self.assertFalse(send_tasks[0].cancelled(), 'caller cancellation must not cancel original send I/O')

    async def test_sdk_read_consumer_cancel_does_not_cancel_actual_read_before_drain(self):
        await self.preflight()
        transport = self.transport(); await self.connect(transport)
        process, entered, reads = transport._process, asyncio.Event(), []
        async def receive(maximum=65536):
            import anyio
            reads.append(asyncio.current_task()); entered.set()
            await process.closed_event.wait()
            raise anyio.EndOfStream
        process.stdout.receive = receive
        iterator = transport.read_messages()
        consumer = asyncio.create_task(anext(iterator))
        await asyncio.wait_for(entered.wait(), 2)
        consumer.cancel()
        with self.assertRaises(asyncio.CancelledError): await consumer
        self.assertTrue(Capture.instances[-1].closed, 'cancelled reader must drain before returning')
        await transport.close()
        self.assertTrue(reads[0].done())
        self.assertFalse(reads[0].cancelled(), 'SDK consumer cancellation must not cancel original read I/O')

    async def test_sdk_stderr_wrapper_cancel_preserves_actual_reader_until_close(self):
        await self.preflight()
        process, entered, reads = Process(code=None), asyncio.Event(), []
        async def receive(maximum=65536):
            import anyio
            reads.append(asyncio.current_task()); entered.set()
            await process.closed_event.wait()
            raise anyio.EndOfStream
        process.stderr.receive = receive
        Capture.outputs = [Process(), process]
        options = self.options(); options.stderr = lambda line: None
        transport = self.owner.transport(options, query_policy=self.policy(), on_user_write=self.emit)
        await self.connect(transport)
        await asyncio.wait_for(entered.wait(), 2)
        await transport.close()
        self.assertTrue(reads[0].done())
        self.assertFalse(reads[0].cancelled())

    async def test_consumed_successful_stream_messages_do_not_accumulate_task_results(self):
        await self.preflight()
        process = Process(code=None)
        process.stdout = Receive([json.dumps(dict(type='assistant', index=index,
            payload=str(index) + 'x' * 32768)).encode() + b'\n' for index in range(40)])
        Capture.outputs = [Process(), process]
        transport = self.transport(); await self.connect(transport)
        count = 0
        async for item in transport.read_messages():
            self.assertEqual(item['index'], count)
            count += 1
        self.assertEqual(count, 40)
        for owned in (transport._native_io, self.owner._tasks):
            retained = [task for task in owned if task.done() and not task.cancelled()
                and task.exception() is None and type(task.result()) is dict]
            self.assertEqual(retained, [], 'consumed native plaintext must not remain in completed Task results')
        await transport.close()

    async def test_completed_send_mutating_original_process_stdin_refuses_callback(self):
        await self.preflight()
        calls = []
        async def callback(*args, **kwargs): calls.append(kwargs)
        transport = self.transport(callback); await self.connect(transport)
        process, original = transport._process, transport._process.stdin
        async def replace_stdin(data):
            original.sent.append(data)
            process.stdin = Send()
        original.send = replace_stdin
        with self.assertRaises(OSError): await transport.write('{"type":"user"}\n')
        self.assertEqual(calls, [])
        self.assertTrue(Capture.instances[-1].closed)

    async def test_prewrite_process_and_wrapper_replacement_refuses_foreign_send(self):
        await self.preflight()
        from anyio.streams.text import TextSendStream
        calls = []
        async def callback(*args, **kwargs): calls.append(kwargs)
        transport = self.transport(callback); await self.connect(transport)
        foreign = Process(code=None)
        transport._process, transport._stdin_stream = foreign, TextSendStream(foreign.stdin)
        with self.assertRaises(OSError): await transport.write('{"type":"user"}\n')
        self.assertEqual(foreign.stdin.sent, [], 'foreign stream must be refused before any send')
        self.assertEqual(calls, [])
        self.assertTrue(Capture.instances[-1].closed)

    async def test_query_policy_cannot_replace_selected_model(self):
        await self.preflight()
        options, policy = self.options(), self.policy()
        options.model = policy['model'] = 'DIFFERENT_MODEL'
        with self.assertRaises((OSError, ValueError)):
            self.owner.transport(options, query_policy=policy, on_user_write=self.emit)

    async def test_dispatch_eof_refuses_allow_and_drains(self):
        async def eof(body): raise EOFError('PRIVATE_DISPATCH')
        self.owner._emit = eof
        with self.assertRaises(OSError) as caught: await self.preflight()
        self.assertNotIn('PRIVATE', str(caught.exception))
        self.assertFalse(any(kind == 'image' for kind, _ in self.order))
        self.assertTrue(Capture.instances[0].closed)

    async def test_failed_capture_close_retains_owner_then_retry(self):
        await self.preflight()
        transport = self.transport(); await self.connect(transport)
        Capture.fail_close = True
        with self.assertRaises(self.m.NativeSDKCleanupError) as caught: await self.owner.aclose()
        self.assertIs(caught.exception.owner, self.owner)
        self.assertFalse(self.owner.closed)
        self.assertIn(Capture.instances[-1], self.owner.captures)
        Capture.fail_close = False
        await self.owner.aclose()
        self.assertTrue(self.owner.closed)


@unittest.skipUnless(os.name == 'nt' and sys.flags.isolated, 'actual Windows capture requires isolated driver')
class NativeSDKInertWindowsTests(unittest.IsolatedAsyncioTestCase):
    async def test_system_python_version_actual_saved_sdk_opener_and_image_channel_terminal(self):
        m = component(self)
        from improvement_image_channel import ImageMetadataChannel
        from improvement_native_capture_win32 import backend
        from improvement_native_protocol import _ENV_PATHS, _ENV_FIXED
        from claude_agent_sdk._internal.transport import subprocess_cli as sdk
        api = backend()
        birth = api.birth(api.current_process())
        with tempfile.TemporaryDirectory(prefix='native-sdk-inert-') as scratch:
            env = {**{key: scratch for key in _ENV_PATHS}, **_ENV_FIXED,
                'SYSTEMROOT': os.environ.get('SYSTEMROOT', r'C:\Windows'), 'WINDIR': r'C:\Windows'}
            selected = str(Path(sys._base_executable).resolve())
            runtime_pin = {**pin(), 'cli_path': selected, 'cli_hash': m._hash_cli(selected),
                'cli_version': '.'.join(map(str, sys.version_info[:3]))}
            worker, guardian = {}, {}
            for purpose in ('adapter_version', 'auth_status'):
                first, second = socket.socketpair()
                nonce = hashlib.sha256(purpose.encode()).hexdigest()
                worker[purpose] = ImageMetadataChannel(first, role='worker', nonce=nonce,
                    worker_pid=os.getpid(), worker_birth=birth)
                guardian[purpose] = ImageMetadataChannel(second, role='guardian', nonce=nonce,
                    worker_pid=os.getpid(), worker_birth=birth)
            observations = []
            async def emit(body): observations.append(body)
            owner = m.NativeInvocationSet(runtime_pin, image_channels=worker, emit_dispatch=emit,
                environment=env, cwd=scratch, source_policy_hash='4' * 64)
            saved_module, saved_open = sdk.anyio, sdk.anyio.open_process
            async def image_allow():
                frame = await guardian['adapter_version'].receive_create()
                self.assertEqual(observations[0]['native_pid'], frame['native_pid'])
                self.assertEqual(observations[0]['native_birth'], frame['native_birth'])
                await guardian['adapter_version'].send_ack('allow')
            image_task = asyncio.create_task(image_allow())
            try:
                output = await owner._fixed('adapter_version')
                self.assertIn(b'Python ', output)
                await image_task
                self.assertEqual(owner.captures[0].resume_counts, (1, 0, 1))
                self.assertTrue(owner.captures[0].terminal)
                self.assertEqual(owner.captures[0].owned_handle_count, 0)
            finally:
                await owner.aclose()
                for channel in guardian.values(): await channel.aclose()
                if not image_task.done():
                    await asyncio.wait_for(image_task, 8)
            self.assertTrue(owner.closed)
            self.assertIs(sdk.anyio, saved_module)
            self.assertIs(sdk.anyio.open_process, saved_open)


if __name__ == '__main__': unittest.main()
