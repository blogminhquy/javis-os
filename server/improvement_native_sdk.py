"""Isolated-worker SDK116 invocation ownership and fixed technical preflight.

Guardian image authorization and host durable authorization remain external.
The private completed-write callback is delivery evidence, not input acceptance,
provider acceptance, loaded-page identity, or comprehension.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from improvement_image_channel import ImageMetadataChannel
from improvement_native_capture import NativeDebugInvocation
from improvement_native_protocol import _ENV_FIXED, _ENV_OPTIONAL, _ENV_PATHS, _fields, _text, _digest, _tree
from improvement_query_dispatch import validate_query_dispatch

_PURPOSES = ('adapter_version', 'auth_status', 'sdk_version', 'query')
_FLAGS = 0x08000006
_RETAINED = set()
_PATCH_OWNER = None
_MAX_OUTPUT = 65536


class NativeSDKError(OSError):
    """Closed public error; never includes SDK/callback/input error text."""


class NativeSDKCleanupError(NativeSDKError):
    def __init__(self, owner):
        super().__init__('native_sdk_cleanup_unproven')
        self.owner = owner


def _canonical(value):
    _tree(value)
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def _hash(value): return hashlib.sha256(_canonical(value)).hexdigest()


def _copy(value): return json.loads(_canonical(value))


def _hash_cli(path):
    # Current-file observation only. The guardian owns actual image comparison.
    with Path(path).open('rb') as source:
        before = os.fstat(source.fileno())
        if not 0 < before.st_size <= 512 * 1024 * 1024: raise NativeSDKError('native_sdk_image_size_invalid')
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
        after = os.fstat(source.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            raise NativeSDKError('native_sdk_image_drift')
        return digest


def _environment(value):
    _tree(value)
    if (type(value) is not dict or not _ENV_PATHS | _ENV_FIXED.keys() <= value.keys()
            or not value.keys() <= _ENV_PATHS | _ENV_FIXED.keys() | _ENV_OPTIONAL):
        raise ValueError('native_sdk_environment_invalid')
    for name, item in value.items():
        _text(item)
        if name in _ENV_FIXED and item != _ENV_FIXED[name]: raise ValueError('native_sdk_environment_invalid')
    return dict(value)


def _pin(value):
    _tree(value)
    _fields(value, {'version', 'provider', 'engine_id', 'model', 'reasoning', 'cli_path', 'cli_hash',
        'cli_version', 'sdk_version', 'profile_version', 'profile_hash'})
    if (type(value['version']) is not int or value['version'] != 1 or value['provider'] != 'anthropic-cli'
            or value['engine_id'] != 'claude-sdk' or value['sdk_version'] != '0.2.116'
            or value['reasoning'] not in ('low', 'medium', 'high', 'xhigh', 'max')):
        raise ValueError('native_sdk_pin_invalid')
    for key, item in value.items():
        if key != 'version': _text(item)
    for name in ('cli_hash', 'profile_hash'): _digest(value[name])
    from improvement_native_bootstrap import _absolute
    _absolute(value['cli_path'])
    if re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', value['cli_version']) is None:
        raise ValueError('native_sdk_pin_invalid')
    return dict(value)


class _AnyioProxy:
    def __init__(self, original, opener): self._original, self.open_process = original, opener
    def __getattr__(self, name): return getattr(self._original, name)


class NativeInvocationSet:
    """Own fresh preflight and at most one fresh SDK transport in one worker.

    Caller transfers all image channels after successful construction. Startup
    and source qualification must already bind them to the held worker. This
    class never creates a client, resumes a session, or sends model input.
    """
    def __init__(self, pin, *, image_channels, emit_dispatch, environment, cwd, source_policy_hash):
        self._initialize(pin, image_channels=image_channels, emit_dispatch=emit_dispatch,
            environment=_environment(environment), cwd=cwd, source_policy_hash=source_policy_hash)

    @classmethod
    def from_qualification_worker(cls, owner):
        from improvement_native_worker import NativeWorkerSessionV2
        from improvement_private_channel import PrivateWorkerChannelV2
        from improvement_qualification_protocol import validate_startup3, worker_binding3
        from improvement_qualification_environment import validate_dummy_environment
        if (cls is not NativeInvocationSet or type(owner) is not NativeWorkerSessionV2
                or not owner._qualification or owner._namespace not in ('preflight', 'trial') or not owner._started
                or owner._closing or owner._closed or owner._failed or owner._adopted
                or owner._runtime is not None or owner._runtime_owns_images
                or owner._adopt_task is not asyncio.current_task() or owner._loop is not asyncio.get_running_loop()
                or not owner._environment_installed):
            raise TypeError('active_qualification_worker_required')
        packet = validate_startup3(owner._packet)
        environment = validate_dummy_environment(packet['environment'])
        private = owner._private
        purposes = _PURPOSES[:2] if packet['kind'] == 'preflight' else _PURPOSES
        if (packet['kind'] != owner._namespace or dict(os.environ) != environment
                or (packet['kind'] == 'trial' and packet['qualification']['version'] != 2)
                or type(private) is not PrivateWorkerChannelV2 or private.closed or private._role != 'worker'
                or private._binding != worker_binding3(packet) or owner._binding != private._binding
                or tuple(owner._channels) != purposes or len(owner._records) != 1 + len(purposes)
                or owner._cwd != (owner._scratch if packet['kind'] == 'preflight' else packet['request']['receipt']['path'])):
            raise ValueError('qualification_worker_adoption_invalid')
        for record, name, channel in zip(owner._records, ('private', *purposes),
                (private, *owner._channels.values())):
            if (record['name'] != name or record['state'] != 'channel_owned'
                    or record['acquisition_unknown'] or record['close_succeeded'] or record['close_authority_lost']
                    or record['channel'] is not channel or record['socket'] is not channel._socket
                    or record['socket'].fileno() < 0):
                raise ValueError('qualification_worker_adoption_invalid')
        for item, channel in zip(packet['images'], owner._channels.values()):
            if (channel._nonce != item['nonce'] or channel._worker_pid != packet['worker_pid']
                    or channel._worker_birth != packet['worker_birth']):
                raise ValueError('qualification_worker_adoption_invalid')
        self = cls.__new__(cls)
        self._initialize(packet['request']['config_pin'], image_channels=owner._channels,
            emit_dispatch=owner._emit_dispatch, environment=environment, cwd=owner._cwd,
            source_policy_hash=packet['request']['config_pin']['profile_hash'])
        self._qualification_owner = owner
        return self

    def _initialize(self, pin, *, image_channels, emit_dispatch, environment, cwd, source_policy_hash):
        from improvement_native_bootstrap import _absolute
        self._pin = _pin(pin)
        self._environment = dict(environment)
        _absolute(cwd); _digest(source_policy_hash)
        if not inspect.iscoroutinefunction(emit_dispatch): raise TypeError('native_sdk_dispatch_callback_invalid')
        if (type(image_channels) is not dict or any(type(key) is not str for key in image_channels)
                or tuple(image_channels) not in (_PURPOSES, _PURPOSES[:2])):
            raise ValueError('native_sdk_channels_invalid')
        nonces, worker = set(), None
        for channel in image_channels.values():
            if type(channel) is not ImageMetadataChannel or channel._role != 'worker' or channel.closed:
                raise ValueError('native_sdk_channels_invalid')
            _digest(channel._nonce)
            binding = channel._worker_pid, channel._worker_birth
            if channel._nonce in nonces or (worker is not None and worker != binding):
                raise ValueError('native_sdk_channels_invalid')
            nonces.add(channel._nonce); worker = binding
        self._channels, self._emit = dict(image_channels), emit_dispatch
        self._cwd, self._source_hash = cwd, source_policy_hash
        self._used, self._entries, self._tasks, self._buffers = set(), [], [], []
        self._runtime = self._transport = self._cleanup_task = None
        self._preflight_started = self._closing = self._closed = self._poisoned = False
        self._patch_original = self._patch_proxy = self._patch_sdk = None
        self._patch_lost = False
        self._saved_open = None

    @property
    def closed(self): return self._closed
    @property
    def captures(self): return tuple(item['capture'] for item in self._entries)

    def _sdk(self):
        from claude_agent_sdk._internal.transport import subprocess_cli
        from claude_agent_sdk import __version__
        if __version__ != self._pin['sdk_version']: raise NativeSDKError('native_sdk_version_drift')
        return subprocess_cli

    def _task(self, coroutine):
        task = asyncio.create_task(coroutine); self._tasks.append(task); return task

    async def _settle(self, task, timeout=8):
        done, _ = await asyncio.wait((task,), timeout=timeout)
        if task not in done or task.cancelled(): raise NativeSDKError('native_sdk_task_unproven')
        return task.result()

    def _capture(self, purpose, argv, environment, *, query_policy=None):
        if self._closing or self._poisoned or purpose in self._used or purpose not in self._channels:
            raise NativeSDKError('native_sdk_invocation_refused')
        self._used.add(purpose)
        argv, environment = list(argv), dict(environment)
        entry = dict(purpose=purpose, entered=False, closed=False, creation=None, dispatch=None, capture=None,
            argv=argv, environment=environment, output_tasks=[])
        def validate(args):
            if (len(args) != 9 or args[0] is not None or type(args[1]) is not str
                    or args[1] != subprocess.list2cmdline(argv) or type(args[5]) is not int
                    or args[5] != _FLAGS or type(args[6]) is not dict or args[6] != environment or args[7] != self._cwd):
                return False
            consistency = validate_query_dispatch(argv, command_line=args[1], executable=args[0],
                cwd=args[7], creationflags=args[5], expected=query_policy) if purpose == 'query' else {
                    'version': 1, 'argv_hash': _hash(argv), 'command_line_hash': hashlib.sha256(args[1].encode()).hexdigest(),
                    'cwd_hash': hashlib.sha256(self._cwd.encode()).hexdigest(), 'creationflags': args[5]}
            entry['dispatch'] = dict(version=1, purpose=purpose, basis='native_argument_consistency',
                argument_consistency=consistency, environment_hash=_hash(environment), source_policy_hash=self._source_hash)
            return True
        async def image_ack(frame):
            if entry['dispatch'] is None: raise NativeSDKError('native_sdk_dispatch_missing')
            entry['creation'] = _copy(frame)
            body = dict(type='dispatch_observed', purpose=purpose, nonce=self._channels[purpose]._nonce,
                native_pid=frame['native_pid'], native_birth=frame['native_birth'],
                dispatch_hash=_hash(entry['dispatch']), dispatch=_copy(entry['dispatch']))
            await self._emit(body)
            return await self._channels[purpose].exchange(frame)
        sdk = self._sdk()
        if self._saved_open is None:
            if _PATCH_OWNER is not None: raise NativeSDKError('native_sdk_patch_busy')
            self._saved_open = sdk.anyio.open_process
        entry['capture'] = NativeDebugInvocation(self._saved_open, purpose=(
            'sdk_query' if purpose == 'query' else 'sdk_version' if purpose == 'sdk_version' else 'isolated_preflight'),
            nonce=self._channels[purpose]._nonce, validate_create=validate, image_ack=image_ack)
        self._entries.append(entry)
        return entry

    async def _read(self, stream, buffer):
        if stream is None: raise NativeSDKError('native_sdk_output_missing')
        sdk = self._sdk()
        while True:
            try: data = await stream.receive(65536)
            except sdk.anyio.EndOfStream: return bytes(buffer)
            if type(data) is not bytes or not data or len(buffer) + len(data) > _MAX_OUTPUT:
                raise NativeSDKError('native_sdk_output_invalid')
            buffer.extend(data)

    async def _close_entry(self, entry):
        if entry['entered'] and not entry['closed']:
            await entry['capture'].aclose()
            entry['closed'] = True
        for task in entry['output_tasks']:
            try: await self._settle(task)
            except Exception:
                # A terminal failed read has settled; a cancelled or pending raw
                # operation has not established completion and remains owned.
                if not task.done() or task.cancelled(): raise

    async def _fixed(self, purpose):
        argv = [self._pin['cli_path'], *{'adapter_version': ['--version'], 'auth_status': ['auth', 'status', '--json'],
            'sdk_version': ['-v']}[purpose]]
        entry = self._capture(purpose, argv, self._environment)
        try:
            await entry['capture'].__aenter__(); entry['entered'] = True
            process = await entry['capture'].open_process(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, cwd=self._cwd, env=dict(self._environment))
            buffers = [bytearray(), bytearray()]; self._buffers.extend(buffers)
            reads = [self._task(self._read(stream, buffer)) for stream, buffer in zip((process.stdout, process.stderr), buffers)]
            entry['output_tasks'].extend(reads)
            wait = self._task(process.wait())
            async def collect(): return await asyncio.gather(*reads, wait)
            results = await self._settle(self._task(collect()), 2 if purpose == 'sdk_version' else 15)
            if results[2] != 0: raise NativeSDKError('native_sdk_preflight_exit')
            return results[0]
        finally:
            await self._close_entry(entry)

    async def preflight(self, *, managed_policy):
        if (self._preflight_started or self._closing or type(managed_policy) is not str
                or managed_policy not in ('absent', 'present', 'unknown')):
            raise NativeSDKError('native_sdk_preflight_refused')
        self._preflight_started = True
        try:
            cli_hash = _hash_cli(self._pin['cli_path'])
            if cli_hash != self._pin['cli_hash']: raise NativeSDKError('native_sdk_image_drift')
            version = self._version(await self._fixed('adapter_version'))
            status = json.loads((await self._fixed('auth_status')).decode('utf-8'))
            if type(status) is not dict: raise NativeSDKError('native_sdk_auth_invalid')
            auth = dict(logged_in=status.get('loggedIn') is True, method=status.get('authMethod'),
                provider=status.get('apiProvider'), plan=status.get('subscriptionType'))
            for key in ('method', 'provider', 'plan'):
                if auth[key] is not None: _text(auth[key], 128)
            self._runtime = dict(platform=sys.platform, cli_hash=cli_hash, sdk_version=self._pin['sdk_version'],
                profile_hash=self._pin['profile_hash'], managed_policy=managed_policy, cli_version=version, auth=auth)
            return _copy(self._runtime)
        except asyncio.CancelledError:
            self._poisoned = True; await self.aclose(); raise
        except BaseException:
            self._poisoned = True; await self.aclose()
            raise NativeSDKError('native_sdk_preflight_failed') from None

    def _version(self, data):
        match = re.match(rb'([0-9]+\.[0-9]+\.[0-9]+)(?:\s|$)', data)
        if match is None or match[1].decode('ascii') != self._pin['cli_version']:
            raise NativeSDKError('native_sdk_cli_version_drift')
        return match[1].decode('ascii')

    def transport(self, options, *, query_policy, on_user_write):
        if self._runtime is None or self._transport is not None or self._closing or self._poisoned or tuple(self._channels) != _PURPOSES:
            raise NativeSDKError('native_sdk_transport_refused')
        if not inspect.iscoroutinefunction(on_user_write): raise TypeError('native_sdk_write_callback_invalid')
        sdk = self._sdk()
        from claude_agent_sdk import ClaudeAgentOptions
        if type(options) is not ClaudeAgentOptions: raise TypeError('native_sdk_options_invalid')
        if any(getattr(options, name, None) for name in ('resume', 'continue_conversation', 'fork_session', 'session_id', 'session_store', 'user')):
            raise NativeSDKError('native_sdk_fresh_session_required')
        if str(options.cli_path) != self._pin['cli_path'] or str(options.cwd) != self._cwd or dict(options.env) != self._environment:
            raise NativeSDKError('native_sdk_options_drift')
        private_policy = _copy(query_policy)
        if any(private_policy.get(name) != value for name, value in (
                ('cli_path', self._pin['cli_path']), ('model', self._pin['model']),
                ('reasoning', self._pin['reasoning']), ('cwd', self._cwd))):
            raise NativeSDKError('native_sdk_query_pin_drift')
        effective = replace(options, permission_prompt_tool_name='stdio')
        owner = self

        class NativeSDKTransport(sdk.SubprocessCLITransport):
            def __init__(self):
                super().__init__(prompt='', options=effective)
                self._native_entry = None
                self._native_lock = asyncio.Lock()
                self._native_close_task = None
                self._native_closed = self._native_version = self._native_user = self._native_failed = False
                self._native_sdk_refs = []
                self._native_io = []
                self._native_readers = []
                self._native_originals = None

            def _io(self, coroutine):
                task = owner._task(coroutine)
                self._native_io.append(task)
                return task

            async def _handle_stderr(self):
                # SDK close cancels its detached wrapper. Keep the actual SDK
                # stream reader alive until close wakes it and proves completion.
                task = self._io(super()._handle_stderr())
                await asyncio.shield(task)

            def read_messages(self):
                return self._native_messages()

            async def _native_messages(self):
                iterator = sdk.SubprocessCLITransport._read_messages_impl(self)
                self._native_readers.append(iterator)
                try:
                    while True:
                        task = self._io(anext(iterator))
                        try: value = await asyncio.shield(task)
                        except StopAsyncIteration: return
                        # The consumer now owns this successful value. Keeping
                        # completed Task results would retain every plaintext
                        # message for the entire invocation and after close.
                        if task.cancelled() or not task.done() or task.exception() is not None:
                            raise NativeSDKError('native_sdk_read_completion_unknown')
                        self._native_io.remove(task)
                        owner._tasks.remove(task)
                        yield value
                except BaseException as error:
                    self._native_failed = True
                    await self.close()
                    if isinstance(error, (asyncio.CancelledError, GeneratorExit)): raise
                    raise NativeSDKError('native_sdk_read_failed') from None

            async def _check_claude_version(self):
                if not self._native_version:
                    owner._version(await owner._fixed('sdk_version'))
                    self._native_version = True

            async def _native_open(self, argv, **kwargs):
                if not self._native_version or self._native_entry is not None: raise NativeSDKError('native_sdk_query_refused')
                expected_env = {**owner._environment, 'CLAUDE_CODE_ENTRYPOINT': 'sdk-py',
                    'CLAUDE_AGENT_SDK_VERSION': owner._pin['sdk_version'], 'PWD': owner._cwd}
                if (type(argv) is not list or type(kwargs.get('env')) is not dict or kwargs['env'] != expected_env
                        or kwargs.get('cwd') != owner._cwd or kwargs.get('user') is not None
                        or set(kwargs) != {'stdin', 'stdout', 'stderr', 'cwd', 'env', 'user'}
                        or kwargs['stdin'] != subprocess.PIPE or kwargs['stdout'] != subprocess.PIPE
                        or kwargs['stderr'] not in (None, subprocess.PIPE)):
                    raise NativeSDKError('native_sdk_spawn_options_refused')
                # Validate builder output before installing the raw Create hook too.
                validate_query_dispatch(argv, command_line=subprocess.list2cmdline(argv), executable=None,
                    cwd=owner._cwd, creationflags=_FLAGS, expected=private_policy)
                self._native_entry = owner._capture('query', argv, expected_env, query_policy=private_policy)
                await self._native_entry['capture'].__aenter__(); self._native_entry['entered'] = True
                return await self._native_entry['capture'].open_process(argv, **kwargs)

            async def connect(self):
                if self._native_closed or self._native_failed or self._process is not None:
                    raise NativeSDKError('native_sdk_connect_refused')
                try:
                    if os.name != 'nt' or not sys.flags.isolated or dict(os.environ) != owner._environment:
                        raise NativeSDKError('native_sdk_isolated_environment_required')
                    await self._check_claude_version()
                    owner._install(sdk, self._native_open)
                    try:
                        await super().connect()
                    except BaseException:
                        # Keep exclusive proxy ownership until the actual
                        # failed capture has drained; never restore a peer's.
                        await self.close()
                        raise
                    finally: owner._restore()
                    if not self._native_version or self._native_entry is None or self._process is not self._native_entry['capture'].process:
                        raise NativeSDKError('native_sdk_connect_unattested')
                    if self._stdin_stream is None or self._stdin_stream.transport_stream is not self._process.stdin:
                        raise NativeSDKError('native_sdk_stdin_unattested')
                    self._native_originals = (self._process, self._process.stdin, self._stdin_stream,
                        self._stdout_stream, self._stderr_stream, self._stderr_task)
                except BaseException as error:
                    self._native_failed = True
                    await self.close()
                    if isinstance(error, asyncio.CancelledError): raise
                    raise NativeSDKError('native_sdk_connect_failed') from None

            async def write(self, data):
                try:
                    async with self._native_lock:
                        if self._native_failed or self._native_closed: raise NativeSDKError('native_sdk_write_refused')
                        is_user = owner._user_frame(data)
                        if is_user and self._native_user: raise NativeSDKError('native_sdk_single_user_required')
                        if self._native_originals is None: raise NativeSDKError('native_sdk_write_unbound')
                        process, raw_stdin, stream, *_ = self._native_originals
                        def original():
                            return (self._process is process and process is self._native_entry['capture'].process
                                and self._stdin_stream is stream and process.stdin is raw_stdin
                                and stream.transport_stream is raw_stdin)
                        if not original(): raise NativeSDKError('native_sdk_write_identity_changed')
                        send = self._io(super().write(data))
                        await asyncio.shield(send)
                        if is_user:
                            if not original():
                                raise NativeSDKError('native_sdk_write_identity_changed')
                            self._native_user = True
                            await on_user_write(data, process=process, stdin=raw_stdin,
                                creation=_copy(self._native_entry['creation']),
                                dispatch_nonce=owner._channels['query']._nonce,
                                dispatch_hash=_hash(self._native_entry['dispatch']))
                except BaseException as error:
                    self._native_failed = True
                    await self.close()
                    if isinstance(error, asyncio.CancelledError): raise
                    raise NativeSDKError('native_sdk_write_failed') from None

            async def _native_close(self):
                async with self._native_lock:
                    if self._native_originals is not None:
                        process, raw_stdin, stream, stdout, stderr, stderr_task = self._native_originals
                        # A rejected substituted SDK field grants no authority
                        # to close the foreign object. Restore only owned refs.
                        self._process, self._stdin_stream = process, stream
                        self._stdout_stream, self._stderr_stream, self._stderr_task = stdout, stderr, stderr_task
                        if process.stdin is not raw_stdin:
                            # Actual anyio Process.stdin is readonly. If its
                            # invariant cannot be restored, retain native owner
                            # for enclosing process drain rather than close an
                            # unrelated stream. Mutable test adapters restore.
                            process.stdin = raw_stdin
                        if stream.transport_stream is not raw_stdin: stream.transport_stream = raw_stdin
                    self._native_sdk_refs.append((self._process, self._stdin_stream, self._stdout_stream,
                        self._stderr_stream, self._stderr_task))
                    if self._native_failed and self._native_entry is not None:
                        # Interrupted sends must be woken by actual native/pipe
                        # drain before SDK close waits for the original write lock.
                        await owner._close_entry(self._native_entry)
                    await super().close()
                    if self._native_entry is not None: await owner._close_entry(self._native_entry)
                    for task in self._native_io:
                        try: await owner._settle(task)
                        except Exception:
                            if not task.done() or task.cancelled(): raise
                    for iterator in self._native_readers:
                        await owner._settle(owner._task(iterator.aclose()))
                    for refs in self._native_sdk_refs:
                        stderr = refs[-1]
                        if stderr is not None and not stderr.done(): raise NativeSDKError('native_sdk_stderr_unsettled')
                    self._native_closed = True

            async def close(self):
                if self._native_closed: return
                if self._native_close_task is None or self._native_close_task.done():
                    self._native_close_task = owner._task(self._native_close())
                await owner._shield(self._native_close_task)

        # Fail malformed actual SDK command at factory time, before any creation.
        transport = NativeSDKTransport()
        argv = transport._build_command()
        validate_query_dispatch(argv, command_line=subprocess.list2cmdline(argv), executable=None,
            cwd=self._cwd, creationflags=_FLAGS, expected=private_policy)
        self._transport = transport
        return transport

    @staticmethod
    def _user_frame(data):
        if type(data) is not str or not data.endswith('\n') or data.count('\n') != 1 or len(data.encode()) > 8 * 1024 * 1024:
            raise NativeSDKError('native_sdk_frame_invalid')
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result: raise NativeSDKError('native_sdk_frame_invalid')
                result[key] = value
            return result
        def reject(_): raise NativeSDKError('native_sdk_frame_invalid')
        value = json.loads(data, object_pairs_hook=pairs, parse_constant=reject)
        _tree(value)
        if type(value) is not dict or type(value.get('type')) is not str: raise NativeSDKError('native_sdk_frame_invalid')
        return value['type'] == 'user'

    def _install(self, sdk, opener):
        global _PATCH_OWNER
        if _PATCH_OWNER is not None or self._patch_proxy is not None: raise NativeSDKError('native_sdk_patch_busy')
        self._patch_sdk, self._patch_original = sdk, sdk.anyio
        self._patch_proxy = _AnyioProxy(sdk.anyio, opener)
        sdk.anyio = self._patch_proxy
        _PATCH_OWNER = self

    def _restore(self):
        global _PATCH_OWNER
        if self._patch_proxy is None: return
        if _PATCH_OWNER is not self or self._patch_sdk.anyio is not self._patch_proxy:
            self._patch_lost = True
            raise NativeSDKError('native_sdk_patch_ownership_lost')
        self._patch_sdk.anyio = self._patch_original
        self._patch_proxy = None
        _PATCH_OWNER = None

    async def _shield(self, task):
        cancelled = False
        while True:
            try:
                done, _ = await asyncio.wait((task,), timeout=20)
                if task not in done or task.cancelled(): raise NativeSDKError('native_sdk_cleanup_task_unproven')
                task.result(); break
            except asyncio.CancelledError: cancelled = True
            except BaseException:
                _RETAINED.add(self)
                raise NativeSDKCleanupError(self) from None
        if cancelled: raise asyncio.CancelledError

    async def _cleanup(self):
        self._closing = True
        if self._transport is not None: await self._transport.close()
        for entry in reversed(self._entries): await self._close_entry(entry)
        for channel in self._channels.values(): await channel.aclose()
        for task in self._tasks:
            if task is self._cleanup_task or task is asyncio.current_task(): continue
            if not task.done(): await self._settle(task)
            if task.cancelled(): raise NativeSDKError('native_sdk_task_completion_unknown')
        if self._patch_lost: raise NativeSDKError('native_sdk_patch_ownership_lost')
        self._restore()
        self._closed = True
        _RETAINED.discard(self)

    async def aclose(self):
        if self._closed: return
        if self._cleanup_task is None or self._cleanup_task.done(): self._cleanup_task = asyncio.create_task(self._cleanup())
        await self._shield(self._cleanup_task)

    async def __aenter__(self): return self
    async def __aexit__(self, *args): await self.aclose()
