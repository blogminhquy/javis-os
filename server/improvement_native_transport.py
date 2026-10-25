"""Host-only native IPC supervisor shared by genuine Trial and operation adapters."""
from __future__ import annotations

import asyncio
from contextlib import aclosing
import json
import subprocess
import sys
import time
from pathlib import Path

import winproc
from improvement_cases import _fields
from improvement_claude import _settled_owned
from improvement_sandbox import _private_directory, worker_environment, _bytes_hash
from improvement_store import _json


async def execute_worker(kind_namespace, request, receipt, *, config_pin, workspace_root, brain_id, before_engine_start):
    from improvement_worker import WorkerGroup, WorkerGroupCleanupError, process_flags
    if kind_namespace == "trial":
        worker_file, identity_keys = "improvement_worker.py", ("trial_id", "attempt", "input_hash")
    elif kind_namespace == "operation":
        worker_file, identity_keys = "improvement_operation_worker.py", ("operation_id", "attempt", "role", "purpose", "input_hash")
    else:
        raise ValueError("unsupported_native_worker_namespace")
    if not callable(before_engine_start):
        raise ValueError("native_start_boundary_unbound")
    prefix = kind_namespace + "_"
    deadline = request["deadline_at"]
    await asyncio.to_thread(_private_directory, Path(receipt["path"]) / "tmp")
    environment = worker_environment(Path(receipt["path"]))
    identity = {key: receipt[key] for key in identity_keys}
    process = guard = None
    stderr_task = None
    maximum = 8 * 1024 * 1024

    async def send(packet):
        raw = _json(packet).encode("utf-8") + b"\n"

        def write():
            process.stdin.write(raw)
            process.stdin.flush()

        await asyncio.to_thread(write)

    async def drain_stderr():
        # Drain to avoid a pipe deadlock; raw stderr is never a public result or artifact.
        while await asyncio.to_thread(process.stderr.read, 4096):
            pass

    async def close_worker():
        if guard is not None:
            # A failed drain observation retains the actual job handle. Keep
            # this owned finally task alive: letting the error escape would let
            # a Runner clean plaintext/release its brain lock while children may
            # still use those bytes. This retries cleanup only, never inference.
            while True:
                try:
                    await asyncio.to_thread(guard.close)
                    break
                except WorkerGroupCleanupError:
                    await asyncio.sleep(.05)
        elif process is not None and process.poll() is None:
            await asyncio.to_thread(winproc.kill_tree, process.pid)
        if process is not None:
            try:
                await asyncio.to_thread(process.wait, timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait, timeout=5)
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()
        if stderr_task is not None:
            await asyncio.gather(stderr_task, return_exceptions=True)

    try:
        async with asyncio.timeout(max(0.0, deadline - time.time())):
            spawn = asyncio.create_task(asyncio.to_thread(subprocess.Popen,
                [sys.executable, "-I", "-X", "utf8", str(Path(__file__).with_name(worker_file))],
                cwd=receipt["path"], env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, start_new_session=sys.platform != "win32",
                creationflags=process_flags() | (4 if sys.platform == 'win32' else 0)))
            spawned, cancelled = await _settled_owned(asyncio.gather(spawn, return_exceptions=True))
            if isinstance(spawned[0], BaseException):
                raise spawned[0]
            process = spawned[0]
            # The child blocks on its first input until its whole lifetime is owned.
            root = Path(workspace_root)
            barrier = root if kind_namespace == 'trial' else root.parent / 'trials'
            identifier = receipt['trial_id' if kind_namespace == 'trial' else 'operation_id']
            fences = (barrier / '.executions' / (_bytes_hash(brain_id.encode()) + '.lock'),
                root / '.lifetimes' / (_bytes_hash(f'{identifier}:{receipt["attempt"]}'.encode()) + '.lock'))
            ownership, interrupted = await _settled_owned(asyncio.gather(
                asyncio.create_task(asyncio.to_thread(WorkerGroup, process.pid, recovery_fences=fences,
                    suspended=sys.platform == 'win32')), return_exceptions=True))
            if isinstance(ownership[0], BaseException):
                raise ownership[0]
            guard = ownership[0]
            if interrupted is not None:
                raise interrupted
            if cancelled is not None:
                raise cancelled
            stderr_task = asyncio.create_task(drain_stderr())
            await send({"version": 1, "config_pin": config_pin, "workspace_root": str(workspace_root),
                        "receipt": receipt, "capability_hash": request["capability_hash"]})
            sequence, state = 0, "starting"
            while True:
                raw = await asyncio.to_thread(process.stdout.readline, maximum + 1)
                if not raw or len(raw) > maximum or not raw.endswith(b"\n"):
                    raise ValueError(prefix + "worker_protocol_incomplete")
                packet = json.loads(raw)
                sequence += 1
                if (not isinstance(packet, dict) or type(packet.get("sequence")) is not int
                        or packet.get("sequence") != sequence or type(packet.get("version")) is not int
                        or packet.get("version") != 1):
                    raise ValueError("invalid_" + kind_namespace + "_worker_packet")
                kind = packet.get("type")
                if kind == "worker_error":
                    _fields(packet, {"version", "sequence", "type", "reason", "error_type"})
                    yield packet
                    raise RuntimeError(prefix + "worker_failed")
                extras = {"worker_ready": {"capability_hash"}, "engine_start_requested": set(),
                          "engine_event": {"event"}, "worker_complete": {"tool_denials"}}
                if kind_namespace == "trial":
                    extras["fixture_event"] = {"event"}
                    extras["worker_complete"].add("fixture_events")
                if kind not in extras:
                    raise ValueError("invalid_" + kind_namespace + "_worker_packet")
                _fields(packet, {"version", "sequence", "type", *identity, *extras[kind]})
                if _json({key: packet[key] for key in identity}) != _json(identity):
                    raise ValueError(prefix + "worker_identity_drift")
                if kind == "worker_ready":
                    if state != "starting" or packet["capability_hash"] != request["capability_hash"]:
                        raise ValueError(prefix + "capability_drift")
                    state = "ready"
                elif kind == "engine_start_requested":
                    if state != "ready":
                        raise ValueError(prefix + "worker_start_repeated")
                    await before_engine_start()
                    await send({"type": "engine_start_ack", **identity})
                    state = "running"
                elif state != "running":
                    raise ValueError(prefix + "worker_event_before_start")
                yield packet
                if kind == "worker_complete":
                    break
            if await asyncio.to_thread(process.wait, timeout=5) != 0:
                raise RuntimeError(prefix + "worker_failed")
    finally:
        closed, cancelled = await _settled_owned(asyncio.gather(
            asyncio.create_task(close_worker()), return_exceptions=True))
        if isinstance(closed[0], BaseException):
            raise closed[0]
        if cancelled is not None:
            raise cancelled


# V2 is an explicit consumer only. No current caller/qualification is enabled.
_HOST_V2_RETAINED = set()
_HOST_API = None
_V2_PURPOSES = ('adapter_version', 'auth_status', 'sdk_version', 'query')


class GuardianSessionV2Error(OSError):
    def __init__(self, owner=None):
        super().__init__('host_guardian_v2_unproven')
        self.owner = owner


class GuardianSessionV2CleanupError(GuardianSessionV2Error):
    pass


class _HostCloseRejected(OSError):
    """Only an actual native CloseHandle FALSE permits another close attempt."""


def _v2_fields(value, fields):
    if type(value) is not dict or any(type(key) is not str for key in value) or set(value) != set(fields):
        raise ValueError('invalid_host_guardian_v2')


def _v2_uint(value, bits=64):
    return type(value) is int and 0 < value < (1 << bits)


def _v2_digest(value):
    import re
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('invalid_host_guardian_v2')


def _control_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def _v2_copy(value):
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _validate_comparison(value):
    import re
    _v2_fields(value, {'matches', 'selected', 'actual', 'proof_basis', 'metadata_mutation_exclusion',
        'debug_event_origin', 'loaded_image_identity', 'comprehension'})
    if type(value['matches']) is not bool:
        raise ValueError('invalid_host_guardian_v2')
    for name in ('selected', 'actual'):
        item = value[name]
        _v2_fields(item, {'volume_serial_64', 'file_id_128', 'sha256', 'size'})
        _v2_digest(item['sha256'])
        if (not _v2_uint(item['volume_serial_64']) or type(item['file_id_128']) is not str
                or re.fullmatch('[0-9a-f]{32}', item['file_id_128']) is None
                or type(item['size']) is not int or not 0 < item['size'] <= 512 * 1024 * 1024):
            raise ValueError('invalid_host_guardian_v2')
    if (value['matches'] != (value['selected'] == value['actual'])
            or type(value['proof_basis']) is not str
            or value['proof_basis'] != 'observed_borrowed_file_identity_and_reopened_sha256'
            or any(type(value[key]) is not str or value[key] != 'unknown' for key in (
                'metadata_mutation_exclusion', 'debug_event_origin', 'loaded_image_identity', 'comprehension'))):
        raise ValueError('invalid_host_guardian_v2')


def _decode_guardian_control2(raw, *, launch_nonce, expected_sequence, invocations, worker_identity):
    """Decode the actual received canonical JSON bytes, never a projection."""
    import base64
    if type(raw) is not bytes or not 0 < len(raw) <= 65536:
        raise ValueError('invalid_host_guardian_v2')
    quoted = escaped = False
    depth = 0
    for byte in raw:
        if byte > 127: raise ValueError('invalid_host_guardian_v2')
        if quoted:
            if escaped: escaped = False
            elif byte == 92: escaped = True
            elif byte == 34: quoted = False
        elif byte == 34: quoted = True
        elif byte in (123, 91):
            depth += 1
            if depth > 12: raise ValueError('invalid_host_guardian_v2')
        elif byte in (125, 93):
            depth -= 1
            if depth < 0: raise ValueError('invalid_host_guardian_v2')
    if quoted or depth: raise ValueError('invalid_host_guardian_v2')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('invalid_host_guardian_v2')
            result[key] = value
        return result
    def integer(value):
        if len(value) > 20: raise ValueError('invalid_host_guardian_v2')
        return int(value)
    def reject(value): raise ValueError('invalid_host_guardian_v2')
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_int=integer, parse_float=reject, parse_constant=reject)
        if _control_json(value) != raw: raise ValueError('canonical')
    except (ValueError, TypeError, RecursionError):
        raise ValueError('invalid_host_guardian_v2') from None
    if type(value) is not dict or type(value.get('type')) is not str:
        raise ValueError('invalid_host_guardian_v2')
    kind = value['type']
    base = {'version', 'type', 'sequence', 'launch_nonce', 'worker_pid', 'worker_birth'}
    extras = {
        'launch_offer': {'worker_tid', 'worker_thread_birth', 'process', 'stdio', 'images', 'root_image', 'bootstrap_count'},
        'stdio_sealed': {'all_data_pipes_closed'},
        'image_observed': {'purpose', 'nonce', 'native_pid', 'native_birth', 'native_tid', 'native_thread_birth',
            'comparison', 'source_worker_incarnation_verified', 'exact_outer_job', 'association_basis', 'observation_hash'},
        'drained': {'root_terminal', 'debug_exit', 'job_active', 'guards_closed', 'reason'}}
    if kind not in extras: raise ValueError('invalid_host_guardian_v2')
    _v2_fields(value, base | extras[kind])
    if (type(value['version']) is not int or value['version'] != 2
            or not _v2_uint(value['sequence'], 63) or value['sequence'] != expected_sequence
            or type(value['launch_nonce']) is not str or value['launch_nonce'] != launch_nonce
            or not _v2_uint(value['worker_pid'], 32) or not _v2_uint(value['worker_birth'])):
        raise ValueError('invalid_host_guardian_v2')
    if worker_identity is not None and any(type(value[key]) is not type(item) or value[key] != item
                                         for key, item in worker_identity.items()):
        raise ValueError('invalid_host_guardian_v2')
    if kind == 'launch_offer':
        if (not _v2_uint(value['worker_tid'], 32) or not _v2_uint(value['worker_thread_birth'])
                or type(value['bootstrap_count']) is not int or value['bootstrap_count'] != 1):
            raise ValueError('invalid_host_guardian_v2')
        _validate_comparison(value['root_image'])
        _v2_fields(value['process'], {'handle', 'access'})
        _v2_fields(value['stdio'], {'stdin', 'stdout', 'stderr'})
        for descriptor, access in [(value['process'], 0x101000), *[
                (value['stdio'][name], 0x40000000 if name == 'stdin' else 0x80000000)
                for name in ('stdin', 'stdout', 'stderr')]]:
            _v2_fields(descriptor, {'handle', 'access'})
            if (not _v2_uint(descriptor['handle']) or descriptor['handle'] == (1 << 64) - 1
                    or type(descriptor['access']) is not int or descriptor['access'] != access):
                raise ValueError('invalid_host_guardian_v2')
        handles = [value['process']['handle'], *[item['handle'] for item in value['stdio'].values()]]
        if len(set(handles)) != 4 or type(value['images']) is not list or len(value['images']) != len(invocations):
            raise ValueError('invalid_host_guardian_v2')
        for item, expected in zip(value['images'], invocations):
            _v2_fields(item, {'purpose', 'nonce', 'share'})
            if (type(item['purpose']) is not str or type(item['nonce']) is not str
                    or any(item[key] != expected[key] for key in ('purpose', 'nonce'))
                    or type(item['share']) is not str or not 0 < len(item['share']) <= 8192):
                raise ValueError('invalid_host_guardian_v2')
            blob = base64.b64decode(item['share'], validate=True)
            if not 0 < len(blob) <= 4096 or base64.b64encode(blob).decode('ascii') != item['share']:
                raise ValueError('invalid_host_guardian_v2')
    elif kind == 'stdio_sealed':
        if value['all_data_pipes_closed'] is not True: raise ValueError('invalid_host_guardian_v2')
    elif kind == 'image_observed':
        _validate_comparison(value['comparison']); _v2_digest(value['observation_hash'])
        if (type(value['purpose']) is not str or type(value['nonce']) is not str
                or not any(item['purpose'] == value['purpose'] and item['nonce'] == value['nonce'] for item in invocations)
                or any(not _v2_uint(value[key], 32) for key in ('native_pid', 'native_tid'))
                or any(not _v2_uint(value[key]) for key in ('native_birth', 'native_thread_birth'))
                or value['source_worker_incarnation_verified'] is not True or value['exact_outer_job'] is not True
                or type(value['association_basis']) is not str
                or value['association_basis'] != 'qualified_worker_create_capture_and_guardian_object_checks'):
            raise ValueError('invalid_host_guardian_v2')
        import hashlib
        observation = {key: item for key, item in value.items() if key not in ('version', 'type', 'sequence', 'observation_hash')}
        if hashlib.sha256(_control_json(observation)).hexdigest() != value['observation_hash']:
            raise ValueError('invalid_host_guardian_v2')
    else:
        if (any(value[key] is not True for key in ('root_terminal', 'debug_exit', 'guards_closed'))
                or type(value['job_active']) is not int or value['job_active'] != 0
                or type(value['reason']) is not str
                or value['reason'] not in ('completed', 'host_stop', 'image_denied', 'cancelled', 'refused')):
            raise ValueError('invalid_host_guardian_v2')
    return value


def _host_windows():
    """Fixed host duplication/I/O only; deliberately has no OpenProcess API."""
    global _HOST_API
    if _HOST_API is not None: return _HOST_API
    import os
    if os.name != 'nt': raise OSError('host_guardian_windows_required')
    import ctypes as C
    from ctypes import wintypes as W
    if C.sizeof(C.c_void_p) != 8: raise OSError('host_guardian_abi_unsupported')
    kernel = C.WinDLL('kernel32', use_last_error=True)
    H, P = W.HANDLE, C.c_void_p
    def declare(name, args, result):
        value = getattr(kernel, name); value.argtypes, value.restype = args, result
    declare('GetCurrentProcess', [], H)
    declare('GetProcessId', [H], W.DWORD)
    declare('GetProcessTimes', [H, *([C.POINTER(W.FILETIME)] * 4)], W.BOOL)
    declare('GetExitCodeProcess', [H, C.POINTER(W.DWORD)], W.BOOL)
    declare('WaitForSingleObject', [H, W.DWORD], W.DWORD)
    declare('DuplicateHandle', [H, H, H, C.POINTER(H), W.DWORD, W.BOOL, W.DWORD], W.BOOL)
    declare('GetFileType', [H], W.DWORD)
    declare('CloseHandle', [H], W.BOOL)
    declare('ReadFile', [H, P, W.DWORD, C.POINTER(W.DWORD), P], W.BOOL)
    declare('WriteFile', [H, P, W.DWORD, C.POINTER(W.DWORD), P], W.BOOL)
    declare('GetWindowsDirectoryW', [W.LPWSTR, W.UINT], W.UINT)
    def check(value):
        if not value: raise C.WinError(C.get_last_error())
        return value
    class Api:
        def slot(self): return H()
        def duplicate(self, source, handle, access, slot):
            check(kernel.DuplicateHandle(source, handle, kernel.GetCurrentProcess(), C.byref(slot), access, False, 0))
        def close(self, handle):
            if not kernel.CloseHandle(handle): raise _HostCloseRejected('host_native_close_rejected')
        def pid(self, handle): return check(kernel.GetProcessId(handle))
        def birth(self, handle):
            values = [W.FILETIME() for _ in range(4)]
            check(kernel.GetProcessTimes(handle, *[C.byref(value) for value in values]))
            return values[0].dwHighDateTime << 32 | values[0].dwLowDateTime
        def terminal(self, handle):
            status = kernel.WaitForSingleObject(handle, 0)
            if status not in (0, 258): raise OSError('host_native_wait_unproven')
            return status == 0
        def exit_code(self, handle):
            if not self.terminal(handle): raise OSError('host_native_exit_unproven')
            value = W.DWORD()
            check(kernel.GetExitCodeProcess(handle, C.byref(value)))
            return value.value
        def pipe(self, handle):
            if kernel.GetFileType(handle) != 3: raise OSError('host_native_pipe_required')
        def read(self, handle, size=4096):
            buffer, count = C.create_string_buffer(size), W.DWORD()
            if not kernel.ReadFile(handle, buffer, size, C.byref(count), None):
                if C.get_last_error() in (109, 233): return b''
                raise C.WinError(C.get_last_error())
            return bytes(buffer.raw[:count.value])
        def write(self, handle, raw):
            offset = 0
            while offset < len(raw):
                part, count = raw[offset:offset + 65536], W.DWORD()
                buffer = C.create_string_buffer(part)
                check(kernel.WriteFile(handle, buffer, len(part), C.byref(count), None))
                if not count.value: raise OSError('host_native_write_unproven')
                offset += count.value
        def environment(self, scratch):
            buffer = C.create_unicode_buffer(32768)
            count = kernel.GetWindowsDirectoryW(buffer, len(buffer))
            if not 0 < count < len(buffer): raise OSError('host_windows_directory_unproven')
            windows = buffer.value
            return {'SYSTEMROOT': windows, 'WINDIR': windows, 'PATH': str(Path(windows) / 'System32') + ';' + windows,
                'HOME': scratch, 'USERPROFILE': scratch, 'APPDATA': scratch, 'LOCALAPPDATA': scratch,
                'TEMP': scratch, 'TMP': scratch}
    _HOST_API = Api()
    return _HOST_API


class GuardianSessionV2:
    """Host owner of one fixed guardian and its independently created worker.

    Inputs are externally authenticated declared manifests, not self-authorizing
    hashes. start({kind,request,environment}) sends private data only through the
    adopted worker stdin after stdio_sealed. receive() returns fresh incoming
    packet2 snapshots; send_worker() supports only the accounting ACK. The async
    durable callback receives a defensive joined dispatch/image observation and
    returns exactly {decision,durable_evidence_hash}; its transaction must check
    current lease/generation. It is never called a database proof by this owner.
    Cleanup failure retains error.owner. A caller must retain its outer lease and
    plaintext until aclose proves native drain, both actual process exits and IO
    settlement. No PID reopen, kill_tree, provider call or runtime registration.
    """
    def __init__(self, guardian_manifest, policy, *, image_policy, fences, launch_nonce, invocations,
                 persist_before_allow, timeout=15, close_timeout=8, lifetime_timeout=300):
        import inspect
        import math
        from improvement_native_bootstrap import validate_bootstrap_manifest
        from improvement_fixed_worker_launch import _policy, _path
        guardian = validate_bootstrap_manifest(guardian_manifest)
        policy = _policy(policy)
        if guardian['entrypoint'] != 'guardian' or guardian['runtime'] != policy['bootstrap']['runtime']:
            raise ValueError('invalid_host_guardian_v2')
        _v2_fields(image_policy, {'version', 'path', 'sha256'})
        if type(image_policy['version']) is not int or image_policy['version'] != 1:
            raise ValueError('invalid_host_guardian_v2')
        _path(image_policy['path']); _v2_digest(image_policy['sha256']); _v2_digest(launch_nonce)
        if type(fences) is not list or len(fences) != 2:
            raise ValueError('invalid_host_guardian_v2')
        for path in fences:
            _path(path)
            if not path.endswith('.lock'): raise ValueError('invalid_host_guardian_v2')
        if len({path.casefold() for path in fences}) != 2:
            raise ValueError('invalid_host_guardian_v2')
        if type(invocations) is not list or not 1 <= len(invocations) <= 4:
            raise ValueError('invalid_host_guardian_v2')
        positions, nonces = [], {launch_nonce}
        for item in invocations:
            _v2_fields(item, {'purpose', 'nonce'}); _v2_digest(item['nonce'])
            if type(item['purpose']) is not str or item['purpose'] not in _V2_PURPOSES or item['nonce'] in nonces:
                raise ValueError('invalid_host_guardian_v2')
            positions.append(_V2_PURPOSES.index(item['purpose'])); nonces.add(item['nonce'])
        if positions != sorted(set(positions)) or not inspect.iscoroutinefunction(persist_before_allow):
            raise ValueError('invalid_host_guardian_v2')
        for value, maximum in ((timeout, 60), (close_timeout, 60), (lifetime_timeout, 300)):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= maximum:
                raise ValueError('invalid_host_guardian_v2')
        self._guardian_manifest, self._policy = guardian, policy
        self._image_policy, self._fences, self._invocations = dict(image_policy), list(fences), _v2_copy(invocations)
        self._nonce, self._timeout, self._close_timeout, self._lifetime = launch_nonce, timeout, close_timeout, lifetime_timeout
        self._persist = persist_before_allow
        self._process = self._guardian_handle = self._guardian_birth = None
        self._worker_identity = self._guardian_identity = None
        self._api = self._loop = self._binding = self._private = None
        self._control_pair = self._private_pair = None
        self._socket_records, self._slots, self._handle_states, self._stream_states = [], {}, {}, {}
        self._guards, self._readers, self._raw_offers = [], [], []
        self._tasks, self._joins, self._dispatches, self._images, self._allowed = set(), {}, {}, {}, set()
        self._spawn_task = self._start_task = self._guardian_task = self._worker_task = self._cleanup_task = None
        self._public_write_task = None
        self._io_completion_unknown = self._spawn_unknown = False
        self._startup_seed = self._startup_raw = self._failure = None
        self._qualification_boundary = None
        self._out_sequence = self._in_sequence = self._packet_sequence = 0
        self._used = self._stopped = self._admission_attempted = self._adopted = self._sealed = False
        self._pair_unknown = self._share_unknown = self._guardian_detached = False
        self._worker_ready = self._engine_requested = self._accounting_acknowledged = self._worker_complete = False
        self.closed = self.native_drained = False

    @property
    def guardian_identity(self):
        return None if self._guardian_identity is None else dict(self._guardian_identity)

    @property
    def worker_identity(self):
        return None if self._worker_identity is None else dict(self._worker_identity)

    def _error(self, cleanup=False):
        _HOST_V2_RETAINED.add(self)
        return (GuardianSessionV2CleanupError if cleanup else GuardianSessionV2Error)(self)

    def _task(self, coroutine):
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        def observed(done):
            if done.cancelled():
                self._io_completion_unknown = True
                _HOST_V2_RETAINED.add(self)
        task.add_done_callback(observed)
        return task

    def _remaining(self):
        value = self._deadline - self._loop.time()
        if value <= 0: raise self._error()
        return min(value, 300)

    def _same_loop(self):
        if self._loop is not asyncio.get_running_loop(): raise self._error()

    async def _wait(self, task, timeout=None):
        done, pending = await asyncio.wait((task,), timeout=self._remaining() if timeout is None else timeout)
        if pending: raise self._error()
        if task.cancelled():
            self._io_completion_unknown = True
            raise self._error()
        result = task.result()
        self._tasks.discard(task)
        return result

    def _check_guardian(self, *, terminal=False):
        if self._process is None or self._guardian_handle is None: raise self._error()
        if self._api.pid(self._guardian_handle) != self._process.pid: raise self._error()
        birth = self._api.birth(self._guardian_handle)
        if self._guardian_birth is None:
            self._guardian_birth = birth
            self._guardian_identity = {'guardian_pid': self._process.pid, 'guardian_birth': birth}
        if birth != self._guardian_birth or (not terminal and self._api.terminal(self._guardian_handle)):
            raise self._error()

    def _check_worker(self, *, terminal=False):
        slot = self._slots.get('process')
        if slot is None or not slot.value or self._worker_identity is None: raise self._error()
        if (self._api.pid(slot.value) != self._worker_identity['worker_pid']
                or self._api.birth(slot.value) != self._worker_identity['worker_birth']
                or (not terminal and self._api.terminal(slot.value))):
            raise self._error()

    def _guard(self, path, digest):
        from improvement_native_image import ImageReadGuard
        try: guard = ImageReadGuard(path, digest)
        except BaseException as error:
            if getattr(error, 'guard', None) is not None: self._guards.append(error.guard)
            raise
        self._guards.append(guard)
        return guard

    def _prepare_guards(self):
        import os
        import msvcrt
        from improvement_native_bootstrap import _runtime_paths
        actual = _runtime_paths()
        runtime = self._guardian_manifest['runtime']
        if any(os.path.normcase(actual[name]) != os.path.normcase(pin['path']) for name, pin in runtime.items()):
            raise self._error()
        seen = set()
        for manifest in (self._guardian_manifest, self._policy['bootstrap']):
            for pin in manifest['runtime'].values():
                guard = self._guard(pin['path'], pin['sha256'])
                reader = open(pin['path'], 'rb'); self._readers.append(reader)
                compared = guard.compare_file_handle(msvcrt.get_osfhandle(reader.fileno()))
                if (compared['matches'] is not True or any(compared['actual'][key] != pin[key]
                        for key in ('sha256', 'volume_serial_64', 'file_id_128'))):
                    raise self._error()
                self._close_stream(reader); self._readers.pop()
            for base, files in ((manifest['source']['root'], manifest['source']['files']),
                                (manifest['imports']['site_packages'], manifest['imports']['files'])):
                for name, digest in files.items():
                    path = str(Path(base).joinpath(*name.split('/')))
                    if (path, digest) not in seen:
                        self._guard(path, digest); seen.add((path, digest))
        self._guard(self._image_policy['path'], self._image_policy['sha256'])

    def _pair(self, kind):
        import socket
        self._pair_unknown = True
        pair = socket.socketpair()
        setattr(self, '_' + kind + '_pair', pair)
        for endpoint in pair:
            self._socket_records.append({'socket': endpoint, 'state': 'live'})
        self._pair_unknown = False
        for endpoint in pair:
            endpoint.set_inheritable(False); endpoint.setblocking(False)
        return pair

    def _record(self, sock):
        return next(record for record in self._socket_records if record['socket'] is sock)

    def _close_socket(self, sock):
        record = self._record(sock)
        if record['state'] in ('closed', 'channel_owned'): return
        if record['state'] != 'live' or sock.fileno() < 0: raise self._error(True)
        record['state'] = 'closing'
        try: sock.close()
        except BaseException: raise self._error(True) from None
        if sock.fileno() >= 0: raise self._error(True)
        record['state'] = 'closed'

    def _close_handle(self, key, handle):
        state = self._handle_states.get(key)
        if state == 'closed': return
        if state == 'closing': raise self._error(True)
        self._handle_states[key] = 'closing'
        try: self._api.close(handle)
        except _HostCloseRejected:
            self._handle_states[key] = 'live'
            raise
        self._handle_states[key] = 'closed'

    def _close_stream(self, stream):
        state = self._stream_states.get(stream)
        if state == 'closed': return
        if state == 'closing' or stream.closed: raise self._error(True)
        self._stream_states[stream] = 'closing'
        stream.close()
        if not stream.closed: raise self._error(True)
        self._stream_states[stream] = 'closed'

    def _envelope(self, source, source_sequence, body):
        self._packet_sequence += 1
        return {'version': 2, 'sequence': self._packet_sequence, 'source': source,
            'source_sequence': source_sequence, 'launch_nonce': self._nonce, **self._worker_identity, 'body': _v2_copy(body)}

    async def _publish(self, source, source_sequence, body):
        packet = self._envelope(source, source_sequence, body)
        if self._stopped and body['type'] == 'drained':
            self._final_drained = packet
            self._available.set()
            return False
        if source in self._pending_publish: raise self._error()
        self._pending_publish[source] = packet
        while len(self._packets) >= 15 and not self._stopped:
            self._space.clear()
            await self._space.wait()
        if self._stopped: return False
        self._packets.append(packet)
        self._pending_publish.pop(source)
        self._available.set()
        return True

    async def _control_exact(self, size):
        raw = bytearray()
        while len(raw) < size:
            part = await self._loop.sock_recv(self._control_pair[0], size - len(raw))
            if not part: raise self._error()
            raw.extend(part)
        return bytes(raw)

    async def _send_command(self, kind, **extra):
        import struct
        async with self._control_lock:
            if self._stopped and kind != 'stop': raise self._error()
            if kind == 'image_authorize' and self._qualification_boundary is not None:
                # This runs after the durable append, under the same send lock.
                # Revocation before send initiation must never emit an allow.
                self._qualification_boundary._assert_query_current()
            self._out_sequence += 1
            value = {'version': 2, 'type': kind, 'sequence': self._out_sequence,
                     'launch_nonce': self._nonce, **self._worker_identity, **extra}
            raw = _control_json(value)
            if not 0 < len(raw) <= 65536: raise self._error()
            task = self._task(self._loop.sock_sendall(self._control_pair[0], struct.pack('!I', len(raw)) + raw))
            await self._wait(task, self._timeout)

    @property
    def closing_observations(self):
        """Defensive, at most eighteen received packets not transferred by receive.

        The consumer must durably account for these even when its iterator is
        cancelled. UNKNOWN cleanup never erases an already observed usage event.
        """
        values = list(getattr(self, '_packets', ()))
        values.extend(getattr(self, '_pending_publish', {}).values())
        final = getattr(self, '_final_drained', None)
        if final is not None: values.append(final)
        return tuple(_v2_copy(item) for item in sorted(values, key=lambda item: item['sequence']))

    def _stop(self, error=None):
        self._stopped = True
        if error is not None and self._failure is None: self._failure = error
        self._space.set(); self._available.set()

    async def start(self, startup):
        import base64
        from improvement_native_protocol import validate_startup2
        if self._used or self._qualification_boundary is not None: raise self._error()
        _v2_fields(startup, {'kind', 'request', 'environment'})
        # Validate private grammar before acquiring any native capability. These
        # placeholders are never sent or persisted as an observed incarnation.
        probe = validate_startup2({'version': 2, 'type': 'startup2', **_v2_copy(startup),
            'launch_nonce': self._nonce, 'worker_pid': 1, 'worker_birth': 1,
            'private_share': base64.b64encode(b'validation-only').decode('ascii'),
            'images': [{**item, 'share': base64.b64encode(b'validation-only').decode('ascii')}
                       for item in self._invocations]})
        expected = 'operation' if probe['kind'] == 'operation' else 'trial'
        if self._policy['bootstrap']['entrypoint'] != expected: raise ValueError('invalid_host_guardian_v2')
        await self._start_validated({key: probe[key] for key in ('kind', 'request', 'environment')})

    async def start_qualification(self, boundary):
        import base64
        from improvement_native_parent import NativeParentBoundary
        from improvement_qualification_protocol import validate_startup3
        if (self._used or self.closed or type(boundary) is not NativeParentBoundary
                or boundary._qualification is None or self._qualification_boundary is not boundary):
            raise PermissionError('qualification_native_owner_foreign')
        seed = boundary._check_qualification_start(self)
        probe = validate_startup3({'version': 3, 'type': 'startup3', **seed,
            'launch_nonce': self._nonce, 'worker_pid': 1, 'worker_birth': 1,
            'private_share': base64.b64encode(b'validation-only').decode('ascii'),
            'images': [{**item, 'share': base64.b64encode(b'validation-only').decode('ascii')}
                for item in self._invocations]})
        if (probe['kind'] not in ('preflight', 'trial') or self._policy['bootstrap']['entrypoint'] != 'trial'
                or (probe['kind'] == 'trial' and probe['qualification']['version'] != 2)):
            raise ValueError('qualification_preflight_required')
        boundary._owner_state = 'STARTING'
        await self._start_validated({key: probe[key] for key in ('kind', 'request', 'environment', 'qualification')})

    async def _start_validated(self, seed):
        from collections import deque
        self._used, self._startup_seed = True, seed
        self._loop = asyncio.get_running_loop(); self._deadline = self._loop.time() + self._lifetime
        self._packets, self._pending_publish, self._final_drained = deque(), {}, None
        self._available, self._space = asyncio.Event(), asyncio.Event()
        self._offer_event, self._seal_event = asyncio.Event(), asyncio.Event()
        self._endpoint_event, self._drained_event = asyncio.Event(), asyncio.Event()
        self._control_lock = asyncio.Lock(); self._published_dispatches, self._published_images = set(), set()
        self._stop_sent = False; self._offer = None; self._pipe_tasks = []; self._ack_task = None
        self._api = _host_windows()
        self._start_task = self._task(self._start_owned())
        try:
            await self._wait(self._start_task, self._timeout)
        except BaseException:
            self._stop()
            await self.aclose()
            raise

    async def _event_wait(self, event):
        while not event.is_set():
            if self._failure is not None: raise self._error()
            if self._stopped: raise self._error()
            await asyncio.sleep(.005)

    async def _start_owned(self):
        import base64
        from improvement_native_bootstrap import encode_bootstrap_frame
        from improvement_native_protocol import encode_startup2, worker_binding
        from improvement_private_channel import PrivateWorkerChannelV2
        guard_task = self._task(asyncio.to_thread(self._prepare_guards))
        await self._wait(guard_task, self._timeout)
        if self._stopped: return
        def spawn():
            manifest = self._guardian_manifest
            # Popen is an opaque acquisition boundary: even an exception may
            # follow native success before its return reaches this assignment.
            self._spawn_unknown = True
            self._process = subprocess.Popen([manifest['runtime']['executable']['path'], '-I', '-S', '-B',
                str(Path(manifest['source']['root']) / 'improvement_native_bootstrap.py')],
                cwd=self._policy['scratch'], env=self._api.environment(self._policy['scratch']),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=0x08000000, close_fds=True, bufsize=0)
            self._guardian_handle = int(self._process._handle)
            self._spawn_unknown = False
        self._spawn_task = self._task(asyncio.to_thread(spawn))
        await self._wait(self._spawn_task, self._timeout)
        self._check_guardian()
        for stream in (self._process.stdout, self._process.stderr):
            self._pipe_tasks.append(self._task(self._drain_stream(stream)))
        if self._stopped: return
        self._pair('control')
        self._share_unknown = True
        share = self._control_pair[1].share(self._process.pid)
        self._control_share = share
        self._share_unknown = False
        self._check_guardian()
        metadata = {'version': 2, 'type': 'guardian_startup2',
            'control_share': base64.b64encode(share).decode('ascii'), 'policy': self._policy,
            'image_policy': self._image_policy, 'fences': self._fences, 'launch_nonce': self._nonce,
            'invocations': self._invocations, 'timeout': self._timeout, 'close_timeout': self._close_timeout,
            'lifetime_timeout': self._remaining()}
        public = encode_bootstrap_frame(self._guardian_manifest) + _control_json(metadata) + b'\n'
        self._admission_attempted = True
        self._public_write_task = self._task(asyncio.to_thread(self._write_public, public))
        await self._wait(self._public_write_task, self._timeout)
        self._close_stream(self._process.stdin)
        self._guardian_task = self._task(self._guardian_loop())
        await self._event_wait(self._offer_event)
        if self._stopped: return
        self._close_socket(self._control_pair[1])
        self._pair('private'); self._check_worker()
        self._share_unknown = True
        private_share = self._private_pair[1].share(self._worker_identity['worker_pid'])
        self._private_share = private_share
        self._share_unknown = False
        self._check_worker()
        startup = {'version': 2, 'type': 'startup2', **self._startup_seed,
            'launch_nonce': self._nonce, **self._worker_identity,
            'private_share': base64.b64encode(private_share).decode('ascii'), 'images': self._offer['images']}
        if self._qualification_boundary is not None:
            from improvement_qualification_protocol import encode_startup3, worker_binding3
            startup.update(version=3, type='startup3')
            self._startup_raw = encode_startup3(startup); self._binding = worker_binding3(startup)
        else:
            self._startup_raw = encode_startup2(startup); self._binding = worker_binding(startup)
        self._adopted = True
        await self._send_command('adopted')
        await self._event_wait(self._seal_event)
        if self._stopped: return
        self._private = PrivateWorkerChannelV2(self._private_pair[0], binding=self._binding, role='host',
            timeout=self._timeout, close_timeout=self._close_timeout, lifetime_timeout=self._remaining())
        self._record(self._private_pair[0])['state'] = 'channel_owned'
        self._worker_task = self._task(self._worker_loop())
        for name in ('stdout', 'stderr'):
            self._pipe_tasks.append(self._task(self._drain_handle(self._slots[name].value)))
        raw = encode_bootstrap_frame(self._policy['bootstrap']) + self._startup_raw
        await self._wait(self._task(asyncio.to_thread(self._api.write, self._slots['stdin'].value, raw)), self._timeout)
        await self._event_wait(self._endpoint_event)
        self._close_socket(self._private_pair[1])
        # Private configuration and socket-share bytes are no longer needed.
        self._startup_raw = self._private_share = self._control_share = None

    def _write_public(self, raw):
        offset = 0
        while offset < len(raw):
            count = self._process.stdin.write(raw[offset:])
            if type(count) is not int or not 0 < count <= len(raw) - offset:
                raise OSError('host_guardian_startup_write_incomplete')
            offset += count
        self._process.stdin.flush()

    async def _drain_stream(self, stream):
        while True:
            task = self._task(asyncio.to_thread(stream.read, 4096))
            if not await self._wait(task, self._lifetime): return

    async def _drain_handle(self, handle):
        while True:
            task = self._task(asyncio.to_thread(self._api.read, handle))
            if not await self._wait(task, self._lifetime): return

    def _adopt_offer(self, value, raw):
        import hashlib
        if self._offer is not None: raise self._error()
        self._check_guardian()
        descriptors = {'process': value['process'], **value['stdio']}
        for key, descriptor in descriptors.items():
            slot = self._api.slot(); self._slots[key] = slot
            self._handle_states[key] = 'acquiring'
            try: self._api.duplicate(self._guardian_handle, descriptor['handle'], descriptor['access'], slot)
            finally:
                if slot.value: self._handle_states[key] = 'live'
            if not slot.value: raise self._error()
            if key != 'process': self._api.pipe(slot.value)
        actual = {'worker_pid': self._api.pid(self._slots['process'].value),
                  'worker_birth': self._api.birth(self._slots['process'].value)}
        self._worker_identity = actual
        if any(actual[key] != value[key] for key in actual): raise self._error()
        self._check_worker(); self._check_guardian()
        pin, comparison = self._policy['bootstrap']['runtime']['executable'], value['root_image']
        if comparison['matches'] is not True or any(comparison['actual'][key] != pin[key]
                for key in ('sha256', 'volume_serial_64', 'file_id_128')): raise self._error()
        self._raw_offers.append(raw); self._offer = value
        return {'type': 'launch_offer', 'worker_tid': value['worker_tid'],
            'worker_thread_birth': value['worker_thread_birth'], 'root_image': comparison,
            'bootstrap_count': value['bootstrap_count'], 'images': _v2_copy(self._invocations),
            'offer_hash': hashlib.sha256(raw).hexdigest()}

    async def _guardian_loop(self):
        import struct
        try:
            while True:
                size, = struct.unpack('!I', await self._control_exact(4))
                if not 0 < size <= 65536: raise self._error()
                raw = await self._control_exact(size)
                value = _decode_guardian_control2(raw, launch_nonce=self._nonce,
                    expected_sequence=self._in_sequence + 1, invocations=self._invocations,
                    worker_identity=self._worker_identity)
                self._in_sequence += 1
                kind = value['type']
                body = {key: item for key, item in value.items() if key not in
                    ('version', 'sequence', 'launch_nonce', 'worker_pid', 'worker_birth')}
                if kind == 'launch_offer':
                    body = self._adopt_offer(value, raw)
                    await self._publish('guardian', value['sequence'], body)
                    self._offer_event.set()
                elif kind == 'stdio_sealed':
                    if not self._adopted or self._sealed: raise self._error()
                    self._sealed = True
                    await self._publish('guardian', value['sequence'], body)
                    self._seal_event.set()
                elif kind == 'image_observed':
                    purpose = value['purpose']
                    if not self._sealed or purpose in self._images: raise self._error()
                    if value['comparison']['selected']['sha256'] != self._image_policy['sha256']: raise self._error()
                    self._images[purpose] = value
                    if await self._publish('guardian', value['sequence'], body):
                        self._published_images.add(purpose); self._maybe_join(purpose)
                elif kind == 'drained':
                    if self._offer is None or self.native_drained: raise self._error()
                    self.native_drained = True; self._drained_event.set()
                    await self._publish('guardian', value['sequence'], body)
                    return
        except asyncio.CancelledError as error:
            self._io_completion_unknown = True
            self._stop(error)
            raise
        except BaseException as error:
            self._stop(error)

    async def _worker_loop(self):
        packet, published = None, False
        try:
            while not self._stopped:
                packet, published = None, False
                packet = await self._private.receive(timeout=None if self._accounting_acknowledged else self._timeout)
                body, kind = packet['body'], packet['body']['type']
                if not self._endpoint_event.is_set():
                    if kind != 'endpoints_adopted': raise self._error()
                    self._check_worker(); self._endpoint_event.set()
                elif kind == 'endpoints_adopted': raise self._error()
                elif kind == 'dispatch_observed':
                    purpose = body['purpose']
                    expected = next((item['purpose'] for item in self._invocations
                                     if item['purpose'] not in self._dispatches), None)
                    if purpose != expected: raise self._error()
                    self._dispatches[purpose] = body
                elif kind == 'worker_ready':
                    await self._await_allowed(('adapter_version', 'auth_status'))
                    if (self._worker_ready or not {'adapter_version', 'auth_status'} <= self._allowed
                            or body['capability_hash'] != self._startup_seed['request']['capability_hash']): raise self._error()
                    self._worker_ready = True
                elif kind == 'engine_start_requested':
                    await self._await_allowed(_V2_PURPOSES)
                    if not self._worker_ready or self._engine_requested or set(_V2_PURPOSES) != self._allowed: raise self._error()
                    self._engine_requested = True
                elif kind == 'preflight_complete':
                    await self._await_allowed(('adapter_version', 'auth_status'))
                    if self._startup_seed['kind'] != 'preflight' or self._allowed != {'adapter_version', 'auth_status'}:
                        raise self._error()
                    self._worker_complete = True
                elif kind == 'worker_error':
                    pass
                else:
                    if self._ack_task is not None:
                        await self._wait(self._ack_task, self._timeout)
                    if not self._accounting_acknowledged or 'query' not in self._allowed: raise self._error()
                    if kind == 'worker_complete': self._worker_complete = True
                published = await self._publish('worker', packet['sequence'], body)
                if kind == 'dispatch_observed' and published:
                    self._published_dispatches.add(body['purpose']); self._maybe_join(body['purpose'])
                if kind in ('worker_complete', 'preflight_complete', 'worker_error'): return
        except asyncio.CancelledError as error:
            self._io_completion_unknown = True
            self._stop(error)
            raise
        except BaseException as error:
            self._stop(error)

        finally:
            # A decoded event is evidence even when phase validation rejects it.
            # Keep it out of live delivery and reuse the one worker pending slot.
            if packet is not None and not published and 'worker' not in self._pending_publish:
                self._pending_publish['worker'] = self._envelope('worker', packet['sequence'], packet['body'])

    def _maybe_join(self, purpose):
        if (self._stopped or purpose in self._joins or purpose not in self._published_images
                or purpose not in self._published_dispatches): return
        self._joins[purpose] = self._task(self._authorize(purpose))

    async def _await_allowed(self, purposes):
        for purpose in purposes:
            task = self._joins.get(purpose)
            if task is None: raise self._error()
            await self._wait(task, self._timeout)
            if purpose not in self._allowed: raise self._error()

    async def _authorize(self, purpose):
        try:
            dispatch, image = self._dispatches[purpose], self._images[purpose]
            if any(dispatch[key] != image[key] for key in ('nonce', 'native_pid', 'native_birth')): raise self._error()
            self._check_worker()
            joined = {'version': 2, 'launch_nonce': self._nonce, **self._worker_identity,
                'purpose': purpose, **{key: dispatch[key] for key in ('nonce', 'native_pid', 'native_birth', 'dispatch_hash')},
                'observation_hash': image['observation_hash'], 'dispatch': dispatch['dispatch'], 'image': image}
            task = self._task(self._persist(_v2_copy(joined)))
            decision = _v2_copy(await self._wait(task, self._timeout))
            _v2_fields(decision, {'decision', 'durable_evidence_hash'}); _v2_digest(decision['durable_evidence_hash'])
            if type(decision['decision']) is not str or decision['decision'] not in ('allow', 'deny'): raise self._error()
            if self._stopped: return
            self._remaining(); self._check_worker()
            if image['comparison']['matches'] is not True and decision['decision'] != 'deny': raise self._error()
            await self._send_command('image_authorize', purpose=purpose,
                **{key: dispatch[key] for key in ('nonce', 'native_pid', 'native_birth', 'dispatch_hash')},
                observation_hash=image['observation_hash'], **decision)
            if decision['decision'] == 'allow': self._allowed.add(purpose)
            else: self._stop()
        except asyncio.CancelledError as error:
            self._io_completion_unknown = True
            self._stop(error)
            raise
        except BaseException as error:
            self._stop(error)

    async def send_worker(self, body):
        self._same_loop()
        if (self._stopped or self._private is None or not self._engine_requested
                or self._accounting_acknowledged or self._ack_task is not None or self._allowed != set(_V2_PURPOSES)):
            raise self._error()
        async def send():
            boundary = self._qualification_boundary
            accounting = None
            if boundary is not None and hasattr(boundary, '_query_binding'):
                # Last synchronous returning-task fence immediately before the
                # original private send. Callback completion cannot mint ACK.
                accounting = boundary._ack_accounting()
            packet = await self._private.send(_v2_copy(body))
            if self._stopped: raise self._error()
            self._accounting_acknowledged = True
            if accounting is not None:
                boundary._ack_witness = {**accounting, 'engine_start_request_sequence': boundary._engine_request_sequence,
                    'ack_identity_hash': _bytes_hash(_control_json(body)), 'ack_send_complete': True}
            return packet
        self._ack_task = self._task(send())
        packet = await self._wait(self._ack_task, self._timeout)
        return _v2_copy(packet)

    async def receive(self):
        self._same_loop()
        while not self._packets:
            if self._failure is not None: raise self._error()
            if self.closed: raise StopAsyncIteration
            if self._stopped: raise self._error()
            if self.native_drained and self._guardian_task is not None and self._guardian_task.done():
                if self._worker_complete: raise StopAsyncIteration
                self._stop(self._error())
                raise self._error()
            self._available.clear()
            try:
                # This cancels only a logical Event wait, never a source reader
                # or native write. Actual I/O remains in the retained owners.
                async with asyncio.timeout(self._remaining()):
                    await self._available.wait()
            except TimeoutError as error:
                self._stop(error)
                raise self._error() from None
        packet = self._packets.popleft(); self._space.set()
        return _v2_copy(packet)

    async def _settle_tasks(self, tasks, deadline):
        tasks = set(tasks)
        if not tasks: return
        done, pending = await asyncio.wait(tasks, timeout=max(0, deadline - self._loop.time()))
        if any(task.cancelled() for task in done): self._io_completion_unknown = True
        # A cancelled wrapper says nothing about a thread/overlapped operation's
        # actual completion. Retain the entire group on every later retry.
        if pending or self._io_completion_unknown or self._spawn_unknown: raise self._error(True)
        # Errors are observations, not permission to discard an unsettled task.
        for task in done:
            try: task.result()
            except BaseException: pass
            self._tasks.discard(task)

    async def _wait_terminal(self, handle, deadline):
        while not self._api.terminal(handle):
            if self._loop.time() >= deadline: raise self._error(True)
            await asyncio.sleep(.005)

    async def _cleanup(self):
        deadline = self._loop.time() + self._close_timeout
        self._stop()
        # A native acquisition may complete after its public await was cancelled.
        # Its pre-owned slots/process field remain the only adoption authority.
        if self._start_task is not None:
            await self._settle_tasks((self._start_task,), deadline)
        if self._spawn_task is not None:
            await self._settle_tasks((self._spawn_task,), deadline)
        if self._pair_unknown or self._share_unknown or self._spawn_unknown or self._io_completion_unknown:
            raise self._error(True)
        if self._process is not None and self._handle_states.get('guardian_process') != 'closed':
            if self._guardian_handle is None: raise self._error(True)
            self._check_guardian(terminal=True)
            if self._admission_attempted:
                if self._worker_complete and not self.native_drained:
                    # A validated completion allows a bounded chance for the
                    # guardian's existing root pump to finish naturally. This
                    # wait is availability only: no record/exit is inferred.
                    grace = min(deadline, self._deadline,
                        self._loop.time() + min(1.0, self._close_timeout / 4))
                    while (not self.native_drained and self._guardian_task is not None
                            and not self._guardian_task.done() and self._loop.time() < grace):
                        await asyncio.sleep(.005)
                if self._offer is None or (self._guardian_task is not None and self._guardian_task.done() and not self.native_drained):
                    # EOF asks the exact guardian to drain; without its required
                    # native record the outer owner/fences still remain UNKNOWN.
                    if self._public_write_task is not None:
                        await self._settle_tasks((self._public_write_task,), deadline)
                    if self._process.stdin is not None: self._close_stream(self._process.stdin)
                    if self._control_pair is not None: self._close_socket(self._control_pair[0])
                    await self._wait_terminal(self._guardian_handle, deadline)
                    self._check_guardian(terminal=True)
                    raise self._error(True)
                if self._offer is not None and not self.native_drained and not self._stop_sent:
                    self._stop_sent = True
                    try: await self._send_command('stop')
                    except BaseException as error:
                        # A write error neither proves delivery nor invalidates
                        # an independently received exact native drain. Never
                        # replay it; require that record and actual exits below.
                        self._stop_write_error = error
                if not self.native_drained:
                    while not self._drained_event.is_set():
                        if (self._guardian_task is None or self._guardian_task.done()
                                or self._loop.time() >= deadline): raise self._error(True)
                        await asyncio.sleep(.005)
                if self._worker_identity is None or not self.native_drained: raise self._error(True)
                await self._wait_terminal(self._slots['process'].value, deadline)
                self._check_worker(terminal=True)
                self._worker_exit_code = self._api.exit_code(self._slots['process'].value)
            else:
                # No metadata entered the guardian: its fixed entrypoint cannot
                # launch a worker. Closing this one public pipe supplies EOF.
                if self._process.stdin is not None:
                    self._close_stream(self._process.stdin)
            await self._wait_terminal(self._guardian_handle, deadline)
            self._check_guardian(terminal=True)
            self._guardian_exit_code = self._api.exit_code(self._guardian_handle)
        if self._private is not None:
            await self._private.aclose()
        # Socket close is real ownership settlement, not cancellation of a read.
        for record in self._socket_records:
            if record['state'] != 'channel_owned': self._close_socket(record['socket'])
        await self._settle_tasks(tuple(self._tasks), deadline)
        if self._process is not None:
            # Only now detach Python's pre-close flag from this SAME retained
            # native capability; never OpenProcess a PID from a receipt.
            if not self._guardian_detached:
                self._guardian_detached = True
                detached = self._process._handle.Detach()
                if detached != self._guardian_handle: raise self._error(True)
            self._process.returncode = self._guardian_exit_code
            self._close_handle('guardian_process', self._guardian_handle)
            for stream in (self._process.stdin, self._process.stdout, self._process.stderr):
                if stream is not None: self._close_stream(stream)
        for key, slot in self._slots.items():
            if slot.value: self._close_handle(key, slot.value)
            elif self._handle_states.get(key) == 'acquiring': raise self._error(True)
        for reader in self._readers:
            self._close_stream(reader)
        for guard in reversed(self._guards): guard.close()
        self._guards.clear(); self._raw_offers.clear()
        self._startup_seed = self._startup_raw = self._private_share = self._control_share = None
        self.closed = True
        _HOST_V2_RETAINED.discard(self)
        self._available.set()

    async def aclose(self):
        """Retry known failures only; ambiguous native closes retain this owner."""
        if self.closed: return
        if self._loop is None:
            self.closed = True
            return
        self._same_loop(); self._stop()
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup())
        interrupted = False
        while True:
            try:
                await asyncio.shield(self._cleanup_task)
                break
            except asyncio.CancelledError:
                interrupted = True
                if self._cleanup_task.cancelled():
                    self._io_completion_unknown = True
                    raise self._error(True) from None
            except BaseException:
                raise self._error(True) from None
        if interrupted: raise asyncio.CancelledError


async def execute_worker_v2(kind_namespace, request, receipt, *, config_pin, workspace_root, brain_id,
        before_engine_start, guardian_manifest, policy, image_policy, launch_nonce, invocations,
        persist_before_allow, on_closing_observations, environment=None, timeout=15, close_timeout=8):
    """Explicit V2 adapter; no caller enables it until complete qualification.

    on_closing_observations(tuple) is mandatory and owns durable late evidence/
    usage handling under the caller's actual writer/lease state. It runs through
    cancellation, including failed cleanup; UNKNOWN never erases received usage.
    before_engine_start remains the separate accounting transaction/ACK gate.
    A completion packet also requires successful retained process exit statuses.
    """
    import inspect
    if kind_namespace not in ('trial', 'operation'):
        raise ValueError('unsupported_native_worker_namespace')
    if (not inspect.iscoroutinefunction(before_engine_start)
            or not inspect.iscoroutinefunction(on_closing_observations)):
        raise ValueError('native_v2_callbacks_unbound')
    remaining = request['deadline_at'] - time.time()
    if not 0 < remaining <= 300: raise ValueError('native_v2_deadline_invalid')
    root = Path(workspace_root)
    barrier = root if kind_namespace == 'trial' else root.parent / 'trials'
    identifier = receipt['trial_id' if kind_namespace == 'trial' else 'operation_id']
    fences = [str(barrier / '.executions' / (_bytes_hash(brain_id.encode()) + '.lock')),
        str(root / '.lifetimes' / (_bytes_hash(f'{identifier}:{receipt["attempt"]}'.encode()) + '.lock'))]
    owner = GuardianSessionV2(guardian_manifest, policy, image_policy=image_policy, fences=fences,
        launch_nonce=launch_nonce, invocations=invocations, persist_before_allow=persist_before_allow,
        timeout=timeout, close_timeout=close_timeout, lifetime_timeout=remaining)
    startup = {'kind': kind_namespace, 'request': {'version': 1, 'config_pin': config_pin,
        'workspace_root': str(workspace_root), 'receipt': receipt, 'capability_hash': request['capability_hash']},
        'environment': worker_environment(Path(receipt['path'])) if environment is None else environment}
    packets = _execute_worker_loop(owner, startup, kind_namespace=kind_namespace,
        before_engine_start=before_engine_start, on_closing_observations=on_closing_observations)
    async with aclosing(packets):
        async for packet in packets:
            try:
                yield packet
            except asyncio.CancelledError as error:
                await _throw_cancellation(packets, error)


async def execute_worker_qualification(boundary, *, before_engine_start, on_closing_observations):
    from improvement_native_parent import NativeParentBoundary
    import secrets
    import inspect
    if type(boundary) is not NativeParentBoundary or not hasattr(boundary, '_query_binding'):
        raise TypeError('retained_qualification_query_required')
    context = boundary._assert_query_current()
    inputs = boundary._query_execution
    remaining = inputs['deadline_at'] - time.time()
    if not 0 < remaining <= 300: raise ValueError('native_v2_deadline_invalid')
    if (not inspect.iscoroutinefunction(before_engine_start) or not inspect.iscoroutinefunction(on_closing_observations)):
        raise ValueError('native_v2_callbacks_unbound')
    root = context['owner'].workspace.root
    identifier, attempt = boundary._query_binding.subject_id, boundary._query_binding.attempt
    fences = [str(root / '.executions' / (_bytes_hash(boundary.principal.brain_id.encode()) + '.lock')),
        str(root / '.lifetimes' / (_bytes_hash(f'{identifier}:{attempt}'.encode()) + '.lock'))]
    launch = inputs['launch']
    owner = GuardianSessionV2(launch['guardian_manifest'], launch['policy'], image_policy=launch['image_policy'],
        fences=fences, launch_nonce=secrets.token_hex(32),
        invocations=[{'purpose': purpose, 'nonce': secrets.token_hex(32)} for purpose in _V2_PURPOSES],
        persist_before_allow=inputs['persist'], timeout=15, close_timeout=8, lifetime_timeout=remaining)
    boundary._guardian = owner
    boundary._qualification._attach_native(owner, boundary)
    packets = _execute_worker_loop(owner, None, kind_namespace='trial', before_engine_start=before_engine_start,
        on_closing_observations=on_closing_observations, boundary=boundary)
    async with aclosing(packets):
        async for packet in packets:
            try:
                yield packet
            except asyncio.CancelledError as error:
                await _throw_cancellation(packets, error)


async def _throw_cancellation(packets, error):
    """Deliver a caller's cancellation into the inner loop (aclose alone would look like a normal
    close and let a nonzero exit status outrank the cancellation), then keep raising it."""
    try:
        await packets.athrow(error)
    except StopAsyncIteration:
        pass
    raise error


async def _execute_worker_loop(owner, startup, *, kind_namespace, before_engine_start,
        on_closing_observations, boundary=None):
    pending_packet = None
    completion_seen = cancelled = False
    try:
        if boundary is None: await owner.start(startup)
        else:
            await owner.start_qualification(boundary)
            boundary._owner_state = 'ACTIVE'
        while True:
            packet = await owner.receive()
            pending_packet = packet
            kind = packet['body']['type']
            if kind == 'engine_start_requested':
                if boundary is not None: boundary._engine_request_sequence = packet['sequence']
                task = asyncio.create_task(before_engine_start())
                results, interrupted = await _settled_owned(asyncio.gather(task, return_exceptions=True))
                if isinstance(results[0], BaseException): raise results[0]
                if interrupted is not None: raise interrupted
                await owner.send_worker({'type': 'engine_start_ack', **owner._binding['identity']})
            pending_packet = None
            if kind == 'worker_complete': completion_seen = True
            yield packet
            if kind == 'worker_error': raise RuntimeError(kind_namespace + '_worker_failed')
            if kind == 'worker_complete': break
    except asyncio.CancelledError:
        cancelled = True
        raise
    finally:
        closed, interrupted = await _settled_owned(asyncio.gather(
            asyncio.create_task(owner.aclose()), return_exceptions=True))
        observations = owner.closing_observations
        if pending_packet is not None:
            observations = tuple(sorted((*observations, _v2_copy(pending_packet)), key=lambda item: item['sequence']))
        observed, observed_interrupted = await _settled_owned(asyncio.gather(
            asyncio.create_task(on_closing_observations(observations)), return_exceptions=True))
        if isinstance(closed[0], BaseException): raise closed[0]
        if isinstance(observed[0], BaseException): raise observed[0]
        if interrupted is not None: raise interrupted
        if observed_interrupted is not None: raise observed_interrupted
        if completion_seen and not cancelled:
            statuses = (getattr(owner, '_worker_exit_code', None), getattr(owner, '_guardian_exit_code', None))
            if any(type(status) is not int or status != 0 for status in statuses):
                raise RuntimeError(kind_namespace + '_worker_exit_failed')
