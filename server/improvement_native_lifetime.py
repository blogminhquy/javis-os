"""Windows native cleanup ownership survives the single querying host's death.

Only this supervisor owns the native job. EOF from its host requests termination;
durable fences disappear only after actual process-exit waits. A supervisor crash
leaves fences in place: recovery must remain blocked rather than guess quiescence.
No model input, account configuration or auth is sent to this supervisor.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path


def fence_directory(lock_path):
    return Path(str(lock_path) + '.native')


def fence_busy(lock_path):
    from improvement_blobs import check_ancestry
    directory = fence_directory(lock_path)
    check_ancestry(directory)
    return directory.exists() and any(directory.iterdir())


class NativeLifetime:
    def __init__(self, pid, fences, *, suspended=False):
        from improvement_sandbox import worker_environment
        import winproc
        self._lock = threading.Lock()
        self._closed = False
        paths = [str(Path(value).absolute()) for value in fences]
        if len(paths) != 2 or len(set(paths)) != 2:
            raise ValueError('native_lifetime_fences_invalid')
        self.process = subprocess.Popen([sys.executable, '-I', '-X', 'utf8', str(Path(__file__).resolve())],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            cwd=Path(__file__).resolve().parent, env=worker_environment(Path(paths[0]).parent), creationflags=winproc.no_window())
        try:
            self.process.stdin.write((json.dumps({'pid': pid, 'locks': paths, 'suspended': suspended}) + '\n').encode())
            self.process.stdin.flush()
            ready = json.loads(self.process.stdout.readline(1024))
            if (type(ready) is not dict or set(ready) != {'type', 'pid'} or ready['type'] != 'ready'
                    or type(ready['pid']) is not int or ready['pid'] <= 0):
                raise ValueError('native_lifetime_ready_invalid')
            self.guardian_pid = ready['pid']
        except BaseException:
            self.process.stdin.close()
            self.process.wait()
            self.process.stdout.close()
            raise OSError('native_lifetime_start_unproven') from None

    def inventory(self):
        with self._lock:
            self.process.stdin.write(b'inventory\n')
            self.process.stdin.flush()
            value = json.loads(self.process.stdout.readline(128 * 1024))
            if type(value) is not list or any(type(pid) is not int or pid <= 0 for pid in value):
                raise OSError('native_lifetime_inventory_unproven')
            return value

    def close(self):
        from improvement_worker import WorkerGroupCleanupError
        with self._lock:
            if self._closed:
                return
            if not self.process.stdin.closed:
                self.process.stdin.close()
            result = self.process.stdout.readline(1024)
            code = self.process.wait()
            if result != b'closed\n' or code != 0:
                raise WorkerGroupCleanupError('native_lifetime_cleanup_unproven')
            self.process.stdout.close()
            self._closed = True


def supervise(packet=None):
    from improvement_worker import WorkerGroup, WorkerGroupCleanupError
    from improvement_blobs import check_ancestry
    from improvement_sandbox import _private_directory
    if packet is None:
        packet = json.loads(sys.stdin.buffer.readline(32768))
    if (type(packet) is not dict or set(packet) != {'pid', 'locks', 'suspended'} or type(packet['suspended']) is not bool
            or type(packet['pid']) is not int or packet['pid'] <= 0
            or type(packet['locks']) is not list or len(packet['locks']) != 2):
        raise ValueError('native_lifetime_request_invalid')
    paths = [Path(value) for value in packet['locks']]
    if (any(not path.is_absolute() or path.suffix != '.lock' for path in paths)
            or len(set(paths)) != 2):
        raise ValueError('native_lifetime_fences_invalid')
    token = uuid.uuid4().hex + '.fence'
    markers = []
    group = WorkerGroup(packet['pid'])
    try:
        for path in paths:
            directory = fence_directory(path)
            check_ancestry(directory)
            _private_directory(directory)
            marker = directory / token
            with marker.open('xb') as output:
                output.write(b'native-cleanup-unproven\n')
                output.flush()
                os.fsync(output.fileno())
            markers.append(marker)
        if packet['suspended']:
            group._resume_initial_thread()
        emit(json.dumps({'type': 'ready', 'pid': os.getpid()}))  # Only now may the host release the worker input gate.
        for line in sys.stdin.buffer:
            if line != b'inventory\n':
                raise ValueError('native_lifetime_control_invalid')
            emit(json.dumps(group.inventory()))
    finally:
        while True:
            try:
                group.close()
                break
            except WorkerGroupCleanupError:
                time.sleep(.05)
        for marker in markers:
            marker.unlink()  # Any failure leaves recovery fail-closed.
    emit('closed')


def emit(value):
    sys.stdout.buffer.write(value.encode('ascii') + b'\n')
    sys.stdout.buffer.flush()


# Guardian v2 is deliberately unreachable from the legacy entrypoint below.
# A qualified host must authenticate this source and the complete fixed policy.
# The earlier 83-source qualification is historical after this source changes.
_V2_RETAINED = set()
_V2_PURPOSES = ('adapter_version', 'auth_status', 'sdk_version', 'query')


class GuardianV2Error(OSError):
    """Closed public refusal; no peer packet, private input or native error text."""


class GuardianV2CleanupError(GuardianV2Error):
    def __init__(self, owner):
        super().__init__('guardian_v2_cleanup_unproven')
        self.owner = owner


class _GuardianCloseRejected(OSError):
    """The actual CloseHandle call returned FALSE; capability remains owned."""


def _v2_fields(value, fields):
    if type(value) is not dict or any(type(key) is not str for key in value) or set(value) != set(fields):
        raise ValueError('guardian_v2_schema_invalid')


def _v2_digest(value):
    import re
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}', value) is None:
        raise ValueError('guardian_v2_digest_invalid')


def _v2_uint(value, bits=64):
    return type(value) is int and 0 < value < (1 << bits)


def _v2_json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


class _GuardianControl:
    """One owned metadata socket, with retained uncancelled public asyncio I/O."""
    def __init__(self, sock, timeout):
        import asyncio
        import socket
        if type(sock) is not socket.socket:
            raise ValueError('guardian_v2_control_invalid')
        if (sock.fileno() < 0 or sock.get_inheritable()
                or sock.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM):
            raise ValueError('guardian_v2_control_invalid')
        sock.getpeername()
        self.loop = asyncio.get_running_loop()
        sock.setblocking(False)
        self.socket, self.timeout = sock, timeout
        self.tasks, self.buffers = [], []
        self.socket_closed = self.closed = self.lost = self.poisoned = False
        self.io_completion_unknown = False

    async def _operate(self, awaitable, timeout=None):
        import asyncio
        task = asyncio.create_task(awaitable)
        self.tasks.append(task)
        done, pending = await asyncio.wait((task,), timeout=self.timeout if timeout is None else timeout)
        if pending:
            self.poisoned = True
            raise GuardianV2Error('guardian_v2_control_deadline')
        try: return task.result()
        except BaseException:
            self.poisoned = True
            raise GuardianV2Error('guardian_v2_control_failed') from None

    async def receive(self, timeout=None):
        import struct
        async def exact(size):
            value = bytearray()
            self.buffers.append(value)
            while len(value) < size:
                part = await self.loop.sock_recv(self.socket, size - len(value))
                if not part: raise GuardianV2Error('guardian_v2_control_eof')
                value.extend(part)
            return bytes(value)
        async def read():
            size, = struct.unpack('!I', await exact(4))
            if not 0 < size <= 65536: raise GuardianV2Error('guardian_v2_control_size')
            raw = await exact(size)
            # Input commands are flat scalar-only objects. Bound nesting before
            # JSON parsing; outputs may contain only our fixed nested metadata.
            from improvement_image_channel import _flat_ascii
            _flat_ascii(raw)
            def pairs(items):
                result = {}
                for key, value in items:
                    if key in result: raise ValueError('duplicate')
                    result[key] = value
                return result
            def integer(raw):
                if len(raw) > 20: raise ValueError('integer')
                return int(raw)
            def reject(raw): raise ValueError('number')
            value = json.loads(raw, object_pairs_hook=pairs, parse_int=integer,
                parse_float=reject, parse_constant=reject)
            if _v2_json(value) != raw: raise ValueError('canonical')
            return value
        if self.closed or self.poisoned: raise GuardianV2Error('guardian_v2_control_poisoned')
        return await self._operate(read(), timeout)

    async def send(self, value):
        import struct
        raw = _v2_json(value)
        if self.closed or self.poisoned or not 0 < len(raw) <= 65536:
            raise GuardianV2Error('guardian_v2_control_unavailable')
        packet = struct.pack('!I', len(raw)) + raw
        self.buffers.append(packet)
        await self._operate(self.loop.sock_sendall(self.socket, packet))

    async def close(self, timeout):
        import asyncio
        import socket
        if self.closed: return
        if any(task.cancelled() for task in self.tasks): self.io_completion_unknown = True
        if self.lost: raise GuardianV2Error('guardian_v2_control_close_authority_lost')
        if not self.socket_closed:
            if self.socket.fileno() < 0:
                self.lost = True
                raise GuardianV2Error('guardian_v2_control_close_authority_lost')
            if any(not task.done() for task in self.tasks):
                try: self.socket.shutdown(socket.SHUT_RDWR)
                except OSError: pass  # Wake-up hint only; actual close is still required.
            try: self.socket.close()
            except BaseException:
                if self.socket.fileno() < 0: self.lost = True
                raise
            if self.socket.fileno() >= 0: raise GuardianV2Error('guardian_v2_control_close_unproven')
            self.socket_closed = True
        pending = [task for task in self.tasks if not task.done()]
        if pending:
            done, pending = await asyncio.wait(pending, timeout=timeout)
            if pending: raise GuardianV2Error('guardian_v2_control_io_unsettled')
        for task in self.tasks:
            if task.cancelled():
                self.io_completion_unknown = True
                continue
            try: task.result()
            except BaseException: pass
        # A cancelled public sock_recv/sendall Task cannot attest actual IOCP
        # completion. Socket close requests cancellation but supplies no such
        # proof either. Permanently retain tasks/buffers for enclosing process
        # drain; native quiescence remains a separate independently checked fact.
        if self.io_completion_unknown:
            raise GuardianV2Error('guardian_v2_control_io_completion_unknown')
        self.closed = True
        self.buffers.clear()


def _guardian_windows():
    """Lazy fixed-ABI APIs; no native loading occurs on module import."""
    from improvement_native_capture_win32 import backend
    debug = backend()  # Explicit Windows AMD64/layout gate, also used by capture.
    import ctypes as C
    from ctypes import wintypes as W
    H, P = W.HANDLE, C.c_void_p
    kernel = C.WinDLL('kernel32', use_last_error=True)
    def declare(name, args, result):
        function = getattr(kernel, name)
        function.argtypes, function.restype = args, result
    declare('CreateJobObjectW', [P, W.LPCWSTR], H)
    declare('SetInformationJobObject', [H, C.c_int, P, W.DWORD], W.BOOL)
    declare('QueryInformationJobObject', [H, C.c_int, P, W.DWORD, P], W.BOOL)
    declare('TerminateJobObject', [H, W.UINT], W.BOOL)
    declare('IsProcessInJob', [H, H, C.POINTER(W.BOOL)], W.BOOL)
    declare('CreatePipe', [C.POINTER(H), C.POINTER(H), P, W.DWORD], W.BOOL)
    declare('GetCurrentProcess', [], H)
    declare('DuplicateHandle', [H, H, H, C.POINTER(H), W.DWORD, W.BOOL, W.DWORD], W.BOOL)
    declare('CloseHandle', [H], W.BOOL)
    declare('OpenProcess', [W.DWORD, W.BOOL, W.DWORD], H)
    declare('CreateIoCompletionPort', [H, H, C.c_size_t, W.DWORD], H)
    declare('GetQueuedCompletionStatus', [H, C.POINTER(W.DWORD), C.POINTER(C.c_size_t), C.POINTER(P), W.DWORD], W.BOOL)
    class Basic(C.Structure):
        _fields_ = [('process', C.c_longlong), ('job', C.c_longlong), ('flags', W.DWORD),
            ('min', C.c_size_t), ('max', C.c_size_t), ('active', W.DWORD),
            ('affinity', C.c_size_t), ('priority', W.DWORD), ('scheduling', W.DWORD)]
    class IO(C.Structure):
        _fields_ = [(name, C.c_ulonglong) for name in ('a', 'b', 'c', 'd', 'e', 'f')]
    class Limits(C.Structure):
        _fields_ = [('basic', Basic), ('io', IO), ('process_mem', C.c_size_t),
            ('job_mem', C.c_size_t), ('peak_process', C.c_size_t), ('peak_job', C.c_size_t)]
    class Accounting(C.Structure):
        _fields_ = [('user', C.c_longlong), ('kernel', C.c_longlong), ('period_user', C.c_longlong),
            ('period_kernel', C.c_longlong), ('faults', W.DWORD), ('total', W.DWORD),
            ('active', W.DWORD), ('terminated', W.DWORD)]
    class Members(C.Structure):
        _fields_ = [('assigned', W.DWORD), ('count', W.DWORD), ('pids', C.c_size_t * 4096)]
    class Association(C.Structure):
        _fields_ = [('key', P), ('port', H)]
    def check(value):
        if not value: raise C.WinError(C.get_last_error())
        return value
    class Api:
        def close(self, value):
            if not kernel.CloseHandle(value): raise _GuardianCloseRejected('guardian_v2_close_rejected')
        def pipe(self, slots): check(kernel.CreatePipe(C.byref(slots[0]), C.byref(slots[1]), None, 0))
        def slots(self): return [H(), H()]
        def job(self): return check(kernel.CreateJobObjectW(None, None))
        def limits(self, job):
            limits = Limits(); limits.basic.flags = 0x2000
            check(kernel.SetInformationJobObject(job, 9, C.byref(limits), C.sizeof(limits)))
        def port(self): return check(kernel.CreateIoCompletionPort(H(-1), None, 0, 1))
        def associate(self, job, port):
            value = Association(1, port)
            check(kernel.SetInformationJobObject(job, 7, C.byref(value), C.sizeof(value)))
        def message(self, port):
            message, key, pid = W.DWORD(), C.c_size_t(), P()
            if not kernel.GetQueuedCompletionStatus(port, C.byref(message), C.byref(key), C.byref(pid), 25):
                if C.get_last_error() != 258: raise C.WinError(C.get_last_error())
                return None
            return message.value, key.value, pid.value
        def open_observer(self, pid):
            handle = kernel.OpenProcess(0x101000, False, pid)
            if not handle and C.get_last_error() != 87: raise C.WinError(C.get_last_error())
            return handle
        def members(self, job):
            value = Members()
            check(kernel.QueryInformationJobObject(job, 3, C.byref(value), C.sizeof(value), None))
            if value.assigned > 4096 or value.count != value.assigned:
                raise GuardianV2Error('guardian_v2_inventory_incomplete')
            return list(value.pids[:value.count])
        def accounting(self, job):
            value = Accounting()
            check(kernel.QueryInformationJobObject(job, 1, C.byref(value), C.sizeof(value), None))
            return value.total, value.active
        def terminate_job(self, job): check(kernel.TerminateJobObject(job, 74))
        def in_job(self, process, job):
            value = W.BOOL(); check(kernel.IsProcessInJob(process, job, C.byref(value))); return bool(value.value)
        def duplicate(self, source, handle, slots, access=None):
            check(kernel.DuplicateHandle(source, handle, kernel.GetCurrentProcess(), C.byref(slots[0]),
                0 if access is None else access, False, 2 if access is None else 0))
    return Api(), debug


class GuardianV2:
    """Guardian-first one-worker owner, with fixed metadata-only control2.

    run() accepts an exclusively owned connected noninheritable control socket.
    The qualified host duplicates offers FROM its retained original guardian
    process, then acknowledges adopted (shares retained, not worker fromshare).
    No private startup/input may be sent until stdio_sealed. Image authorization
    is trusted host durable evidence, not an independent database attestation.
    Worker CREATE association still depends on qualified trusted capture code.
    Native drained excludes control socket closure; closed includes both.
    Supplied lock parents must already be host-authenticated private directories;
    this owner checks ancestry and inherits their ACL, never establishes it.
    """
    def __init__(self, policy, *, image_policy, fences, launch_nonce, invocations, timeout=15, close_timeout=8,
            lifetime_timeout=300):
        import math
        from improvement_fixed_worker_launch import _policy, _path
        self._policy = _policy(policy)
        _v2_fields(image_policy, {'version', 'path', 'sha256'})
        if type(image_policy['version']) is not int or image_policy['version'] != 1:
            raise ValueError('guardian_v2_image_policy_invalid')
        _path(image_policy['path']); _v2_digest(image_policy['sha256']); _v2_digest(launch_nonce)
        if type(fences) is not list or len(fences) != 2:
            raise ValueError('guardian_v2_fences_invalid')
        for path in fences:
            _path(path)
            if not path.endswith('.lock'): raise ValueError('guardian_v2_fences_invalid')
        if len({value.casefold() for value in fences}) != 2: raise ValueError('guardian_v2_fences_invalid')
        if type(invocations) is not list or not 1 <= len(invocations) <= 4:
            raise ValueError('guardian_v2_invocations_invalid')
        ordered, nonces = [], {launch_nonce}
        for invocation in invocations:
            _v2_fields(invocation, {'purpose', 'nonce'})
            purpose, nonce = invocation['purpose'], invocation['nonce']
            if type(purpose) is not str or purpose not in _V2_PURPOSES:
                raise ValueError('guardian_v2_purpose_invalid')
            _v2_digest(nonce)
            if nonce in nonces: raise ValueError('guardian_v2_nonce_reused')
            ordered.append(_V2_PURPOSES.index(purpose)); nonces.add(nonce)
        if ordered != sorted(set(ordered)): raise ValueError('guardian_v2_purpose_order_invalid')
        for value in (timeout, close_timeout):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 60:
                raise ValueError('guardian_v2_deadline_invalid')
        if (type(lifetime_timeout) not in (int, float) or not math.isfinite(lifetime_timeout)
                or not 0 < lifetime_timeout <= 300):
            raise ValueError('guardian_v2_lifetime_invalid')
        self._image_policy, self._fences = dict(image_policy), list(fences)
        self._invocations = [dict(item) for item in invocations]
        self._nonce, self._timeout, self._close_timeout = launch_nonce, timeout, close_timeout
        self._lifetime_timeout, self._lifetime_deadline = lifetime_timeout, None
        self.state, self.closed, self.native_drained = 'fresh', False, False
        self._api = self._debug = self._loop = self._creator = self._control = None
        self._factory = self._caps = self._job = self._port = None
        self._guards, self._markers, self._pipe_slots, self._files = [], [], {}, []
        self._marker_files = []
        self._records, self._tasks, self._handle_states = [], [], {}
        self._channels, self._images, self._shares = {}, {}, []
        self._observer_lock = threading.Lock()
        self._observers, self._births, self._inventory_error = [], 0, False
        self._inventory_stop, self._inventory_thread = threading.Event(), None
        self._pending = self._root_task = self._command_task = self._cleanup_task = self._run_task = None
        self._root_image, self._bootstrap, self._root_error = None, None, None
        self._seen_exit = self._root_terminal = self._used = self._stdio_sealed = False
        self._stop = self._held = self._release = None
        self._out_sequence = self._in_sequence = 0
        self._adopted = False
        self._launch_offer_sent = False
        self._job_termination_requested = self._root_termination_requested = False
        self._reason = 'completed'
        self._failure = self._cleanup_error = self._root_failure = None

    def _same_creator(self):
        import asyncio
        if self._loop is not asyncio.get_running_loop() or self._debug.current_thread() != self._creator:
            raise GuardianV2Error('guardian_v2_creator_changed')

    def _task(self, coroutine):
        import asyncio
        task = asyncio.create_task(coroutine)
        self._tasks.append(task)
        return task

    def _guard(self, path, digest):
        from improvement_native_image import ImageReadGuard
        try: guard = ImageReadGuard(path, digest)
        except BaseException as error:
            if getattr(error, 'guard', None) is not None: self._guards.append(error.guard)
            raise
        self._guards.append(guard)
        return guard

    def _close_handle(self, key, handle):
        state = self._handle_states.get(key)
        if state == 'closed': return
        if state == 'closing': raise GuardianV2Error('guardian_v2_close_result_unknown')
        self._handle_states[key] = 'closing'
        try: self._api.close(handle)
        except _GuardianCloseRejected:
            self._handle_states[key] = 'live'
            raise
        self._handle_states[key] = 'closed'

    def _close_socket(self, record):
        if record['state'] == 'closed': return
        if record['state'] == 'lost': raise GuardianV2Error('guardian_v2_share_close_authority_lost')
        sock = record['socket']
        if sock.fileno() < 0:
            record['state'] = 'lost'
            raise GuardianV2Error('guardian_v2_share_close_authority_lost')
        try: sock.close()
        except BaseException:
            if sock.fileno() < 0: record['state'] = 'lost'
            raise
        if sock.fileno() >= 0: raise GuardianV2Error('guardian_v2_share_close_unproven')
        record['state'] = 'closed'

    def _prepare_fences(self):
        from improvement_blobs import check_ancestry
        for path in self._fences:
            directory = fence_directory(path)
            # Lock parents are authenticated private host directories. Inherit
            # their ACL; never import business config or spawn ACL utilities in
            # the guardian. This is not a new hostile-filesystem isolation proof.
            check_ancestry(directory)
            if not directory.parent.is_dir(): raise GuardianV2Error('guardian_v2_fence_parent_unavailable')
            directory.mkdir(exist_ok=True, mode=0o700)
            check_ancestry(directory)
            marker = directory / (self._nonce + '.v2.fence')
            output = marker.open('xb')
            self._markers.append(marker)
            record = {'file': output, 'state': 'live'}
            self._marker_files.append(record)
            output.write(b'guardian-v2-cleanup-unproven\n'); output.flush(); os.fsync(output.fileno())
            self._close_marker_file(record)

    def _close_marker_file(self, record):
        if record['state'] == 'closed': return
        if record['state'] in ('closing', 'lost'):
            raise GuardianV2Error('guardian_v2_marker_close_unproven')
        record['state'] = 'closing'
        try: record['file'].close()
        except OSError:
            record['state'] = 'lost' if record['file'].closed else 'live'
            raise
        if not record['file'].closed: raise GuardianV2Error('guardian_v2_marker_close_unproven')
        record['state'] = 'closed'

    def _start_inventory(self):
        self._port = self._api.port()
        self._api.associate(self._job, self._port)
        def monitor():
            try:
                while not self._inventory_stop.is_set():
                    message = self._api.message(self._port)
                    if message is None: continue
                    kind, key, pid = message
                    if kind != 6: continue  # JOB_OBJECT_MSG_NEW_PROCESS, as legacy WorkerGroup.
                    with self._observer_lock:
                        self._births += 1
                        if key != 1 or not _v2_uint(pid, 32) or self._births > 4096:
                            self._inventory_error = True
                            continue
                        # PID comes ONLY from this job's kernel notification. This
                        # observer is never worker launch/duplication authority.
                        handle = self._api.open_observer(pid)
                        if not handle: continue  # ERROR_INVALID_PARAMETER: object already gone.
                        record = {'handle': handle, 'pid': pid, 'birth': None}
                        self._observers.append(record)  # Own before any fallible query.
                        record['birth'] = self._debug.birth(handle)
                        if self._debug.process_id(handle) != pid or not self._api.in_job(handle, self._job):
                            self._inventory_error = True
            except BaseException:
                self._inventory_error = True
        self._inventory_thread = threading.Thread(target=monitor, name='guardian-v2-inventory', daemon=True)
        self._inventory_thread.start()

    def _live_worker(self):
        caps = self._caps
        if (not caps or not caps['process_handle'] or not caps['thread_handle']
                or not _v2_uint(caps['pid'], 32) or not _v2_uint(caps['birth'])
                or self._debug.process_id(caps['process_handle']) != caps['pid']
                or self._debug.birth(caps['process_handle']) != caps['birth']
                or self._debug.wait(caps['process_handle'])
                or not self._api.in_job(caps['process_handle'], self._job)):
            raise GuardianV2Error('guardian_v2_source_worker_unproven')

    def _continue(self):
        event = self._pending
        if event is None: raise GuardianV2Error('guardian_v2_pending_missing')
        status = 0x00010002
        if event.code == 1 and event.data.exception.record.code not in (0x80000003, 0x80000004):
            status = 0x80010001
        self._debug.continue_event(event, status)
        self._pending = None
        if event.code == 5: self._seen_exit = True

    def _next(self):
        event = self._debug.next_event()
        if event is None: return None
        self._pending = event
        if event.code == 3:
            if event.data.create.file: self._files.append(event.data.create.file)
        elif event.code == 6 and event.data.dll.file: self._files.append(event.data.dll.file)
        if event.pid != self._caps['pid']:
            raise GuardianV2Error('guardian_v2_root_event_mismatch')
        return event

    async def _root_drain(self):
        import asyncio
        self._same_creator()
        if not self._caps: return
        if self._seen_exit and self._root_terminal: return
        if not self._caps['process_handle'] or not self._caps['thread_handle'] or not self._caps['pid']:
            raise GuardianV2Error('guardian_v2_raw_root_unknown')
        if self._bootstrap is None:
            self._bootstrap = self._debug.resume(self._caps['thread_handle'])
            if self._bootstrap != 1: raise GuardianV2Error('guardian_v2_bootstrap_unproven')
        if (not self._seen_exit and not self._job_termination_requested and not self._root_termination_requested
                and not self._debug.wait(self._caps['process_handle'])):
            self._debug.terminate(self._caps['process_handle'])
            self._root_termination_requested = True
        if self._pending: self._continue()
        deadline = self._loop.time() + self._close_timeout
        while not self._seen_exit or not self._debug.wait(self._caps['process_handle']):
            event = self._next() if not self._seen_exit else None
            if event is not None: self._continue()
            elif self._loop.time() >= deadline: raise GuardianV2Error('guardian_v2_root_exit_unproven')
            else: await asyncio.sleep(.003)
        self._root_terminal = True

    async def _root_pump(self):
        import asyncio
        try:
            self._same_creator()
            self._bootstrap = self._debug.resume(self._caps['thread_handle'])
            if self._bootstrap != 1: raise GuardianV2Error('guardian_v2_bootstrap_unproven')
            while not self._seen_exit:
                if self._stop.is_set():
                    await self._root_drain()
                    return
                event = self._next()
                if event is None:
                    await asyncio.sleep(.003)
                    continue
                if event.code == 3:
                    if self._root_image is not None: raise GuardianV2Error('guardian_v2_duplicate_root_create')
                    value, caps = event.data.create, self._caps
                    if (not value.file or self._debug.process_id(value.process) != caps['pid']
                            or self._debug.birth(value.process) != caps['birth']
                            or self._debug.thread_id(value.thread) != caps['tid']
                            or self._debug.thread_owner(value.thread) != caps['pid']
                            or self._debug.birth(value.thread, True) != caps['thread_birth']):
                        raise GuardianV2Error('guardian_v2_root_create_unproven')
                    compared = self._root_guard.compare_file_handle(int(value.file))
                    pin = self._policy['bootstrap']['runtime']['executable']
                    if compared['matches'] is not True or any(compared['actual'][key] != pin[key]
                            for key in ('sha256', 'volume_serial_64', 'file_id_128')):
                        raise GuardianV2Error('guardian_v2_root_image_denied')
                    self._root_image = compared
                    self._held.set()
                    while not self._release.is_set() and not self._stop.is_set(): await asyncio.sleep(.003)
                    if self._stop.is_set():
                        await self._root_drain()
                        return
                    if not self._stdio_sealed: raise GuardianV2Error('guardian_v2_stdio_not_sealed')
                    if self._debug.suspend(value.thread) != 0: raise GuardianV2Error('guardian_v2_root_rearm_unproven')
                    self._continue()
                    if self._debug.resume(value.thread) != 1: raise GuardianV2Error('guardian_v2_root_resume_unproven')
                else: self._continue()
            deadline = self._loop.time() + self._close_timeout
            while not self._debug.wait(self._caps['process_handle']):
                if self._loop.time() >= deadline: raise GuardianV2Error('guardian_v2_root_terminal_unproven')
                await asyncio.sleep(.003)
            self._root_terminal = True
        except BaseException as error:
            self._root_failure = error
            self._root_error = 'guardian_v2_root_pump_failed'
            self._reason = 'refused'
            self._stop.set()
            try: await self._root_drain()
            except BaseException: pass
        finally: self._held.set()

    async def _event(self, kind, **extra):
        self._out_sequence += 1
        value = {'version': 2, 'type': kind, 'sequence': self._out_sequence, 'launch_nonce': self._nonce,
            'worker_pid': self._caps['pid'], 'worker_birth': self._caps['birth'], **extra}
        await self._control.send(value)

    def _share_images(self):
        import base64
        import socket
        from improvement_image_channel import ImageMetadataChannel
        for invocation in self._invocations:
            self._live_worker()
            left, right = socket.socketpair()
            left_record = {'socket': left, 'state': 'live'}
            right_record = {'socket': right, 'state': 'live'}
            self._shares.extend((left_record, right_record))
            channel = ImageMetadataChannel(left, role='guardian', nonce=invocation['nonce'],
                worker_pid=self._caps['pid'], worker_birth=self._caps['birth'],
                timeout=self._timeout, close_timeout=self._close_timeout)
            left_record['state'] = 'channel_owned'
            self._channels[invocation['purpose']] = channel
            # Target is the original retained worker incarnation, never a receipt PID.
            right_record['target'] = (self._caps['pid'], self._caps['birth'])
            blob = right.share(self._caps['pid'])
            right_record['blob'] = blob
            self._live_worker()
            self._close_socket(right_record)
            self._images[invocation['purpose']] = {'purpose': invocation['purpose'], 'nonce': invocation['nonce'],
                'share': base64.b64encode(blob).decode('ascii'), 'state': 'fresh', 'task': None,
                'socket': left, 'deadline': None}

    async def _prepare(self):
        import asyncio
        from improvement_fixed_worker_launch import FixedWorkerLaunch
        self._api, self._debug = _guardian_windows()
        self._creator = self._debug.current_thread()
        # A fresh debugger thread has documented kill-on-exit TRUE by default.
        # DebugSetProcessKillOnExit itself requires an existing connection; check
        # it immediately after fixed creation, before any explicit Resume.
        self._prepare_fences()
        self._job = self._api.job()
        self._api.limits(self._job)
        self._start_inventory()  # Port associated before the first assignment/birth.
        self._image_guard = self._guard(self._image_policy['path'], self._image_policy['sha256'])
        root = self._policy['bootstrap']['runtime']['executable']
        self._root_guard = self._guard(root['path'], root['sha256'])
        for name in ('stdin', 'stdout', 'stderr'):
            slots = self._api.slots(); self._pipe_slots[name] = slots
            self._api.pipe(slots)  # Output slots retained before native invocation.
        stdio = {name: slots[0 if name == 'stdin' else 1].value for name, slots in self._pipe_slots.items()}
        self._factory = FixedWorkerLaunch(self._policy, job_handle=self._job, stdio=stdio)
        try: self._caps = self._factory.launch()
        finally:
            if self._caps is None: self._caps = self._factory.capabilities
        self._debug.enable_kill()
        self._root_task = self._task(self._root_pump())
        held = self._task(self._held.wait())
        done, pending = await asyncio.wait((held,), timeout=min(self._timeout,
            max(0, self._lifetime_deadline - self._loop.time())))
        if pending or self._root_image is None or self._root_error:
            raise GuardianV2Error('guardian_v2_root_gate_unproven')
        self._share_images()
        self.state = 'offered'
        await self._event('launch_offer', worker_tid=self._caps['tid'], worker_thread_birth=self._caps['thread_birth'],
            process={'handle': self._caps['process_handle'], 'access': 0x101000},
            stdio={name: {'handle': slots[1 if name == 'stdin' else 0].value,
                'access': 0x40000000 if name == 'stdin' else 0x80000000} for name, slots in self._pipe_slots.items()},
            images=[{key: image[key] for key in ('purpose', 'nonce', 'share')} for image in self._images.values()],
            root_image=self._root_image, bootstrap_count=self._bootstrap)
        self._launch_offer_sent = True

    def _validate_command(self, value):
        base = {'version', 'type', 'sequence', 'launch_nonce', 'worker_pid', 'worker_birth'}
        if type(value) is not dict or type(value.get('type')) is not str: raise ValueError('command')
        kind = value['type']
        extra = {'purpose', 'nonce', 'native_pid', 'native_birth', 'observation_hash', 'dispatch_hash',
            'durable_evidence_hash', 'decision'} if kind == 'image_authorize' else set()
        if kind not in ('adopted', 'image_authorize', 'stop'): raise ValueError('command')
        _v2_fields(value, base | extra)
        if (type(value['version']) is not int or value['version'] != 2
                or not _v2_uint(value['sequence'], 63) or value['sequence'] != self._in_sequence + 1
                or type(value['launch_nonce']) is not str or value['launch_nonce'] != self._nonce
                or not _v2_uint(value['worker_pid'], 32) or value['worker_pid'] != self._caps['pid']
                or not _v2_uint(value['worker_birth']) or value['worker_birth'] != self._caps['birth']):
            raise ValueError('binding')
        if kind == 'image_authorize':
            if type(value['purpose']) is not str or value['purpose'] not in self._images: raise ValueError('purpose')
            for key in ('nonce', 'observation_hash', 'dispatch_hash', 'durable_evidence_hash'): _v2_digest(value[key])
            if (not _v2_uint(value['native_pid'], 32) or not _v2_uint(value['native_birth'])
                    or type(value['decision']) is not str or value['decision'] not in ('allow', 'deny')):
                raise ValueError('authorization')
        self._in_sequence = value['sequence']
        return kind

    def _seal_stdio(self):
        if not self._factory.temporary_duplicates_closed: raise GuardianV2Error('guardian_v2_transient_stdio_live')
        self._close_pipes()
        self._stdio_sealed = True

    def _close_pipes(self):
        for name, slots in self._pipe_slots.items():
            for index, slot in enumerate(slots):
                if slot.value:
                    self._close_handle(('pipe', name, index), slot.value)
                    slot.value = None

    async def _image_received(self, purpose, frame):
        import hashlib
        self._live_worker()
        record = {'purpose': purpose, 'frame': frame, 'slots': {}, 'comparison': None}
        self._records.append(record)
        for name, source, access in (('file', 'hfile', None), ('process', 'hprocess', 0x101000),
                                     ('thread', 'hthread', 0x0800)):
            slots = self._api.slots(); record['slots'][name] = slots
            self._api.duplicate(self._caps['process_handle'], frame[source], slots, access)
        process, thread, file = (record['slots'][key][0].value for key in ('process', 'thread', 'file'))
        if (self._debug.process_id(process) != frame['native_pid'] or self._debug.birth(process) != frame['native_birth']
                or self._debug.wait(process) or not self._api.in_job(process, self._job)
                or self._debug.thread_owner(thread) != frame['native_pid'] or self._debug.thread_id(thread) != frame['native_tid']
                or self._debug.birth(thread, True) != frame['native_thread_birth']):
            raise GuardianV2Error('guardian_v2_native_object_unproven')
        comparison = self._image_guard.compare_file_handle(file)
        record['comparison'] = comparison
        observation = {'purpose': purpose, 'nonce': frame['nonce'], 'native_pid': frame['native_pid'],
            'native_birth': frame['native_birth'], 'native_tid': frame['native_tid'],
            'native_thread_birth': frame['native_thread_birth'], 'comparison': comparison,
            'source_worker_incarnation_verified': True, 'exact_outer_job': True,
            'association_basis': 'qualified_worker_create_capture_and_guardian_object_checks'}
        observation_hash = hashlib.sha256(_v2_json({'launch_nonce': self._nonce,
            'worker_pid': self._caps['pid'], 'worker_birth': self._caps['birth'], **observation})).hexdigest()
        image = self._images[purpose]
        image.update(state='held', record=record, observation_hash=observation_hash)
        await self._event('image_observed', **observation, observation_hash=observation_hash)

    async def _authorize(self, value):
        image = self._images[value['purpose']]
        if image['state'] != 'held': raise GuardianV2Error('guardian_v2_authorization_replayed')
        record, frame = image['record'], image['record']['frame']
        if (value['nonce'] != image['nonce'] or value['observation_hash'] != image['observation_hash']
                or value['native_pid'] != frame['native_pid'] or value['native_birth'] != frame['native_birth']):
            raise GuardianV2Error('guardian_v2_authorization_mismatch')
        self._live_worker()
        process = record['slots']['process'][0].value
        if self._debug.wait(process) or not self._api.in_job(process, self._job):
            raise GuardianV2Error('guardian_v2_authorization_native_terminal')
        self._image_guard.snapshot()
        decision = 'allow' if value['decision'] == 'allow' and record['comparison']['matches'] is True else 'deny'
        # Consume before awaiting send: a partial send can never authorize reuse.
        image['state'] = 'spent'
        image['authorization'] = dict(value)
        await self._channels[value['purpose']].send_ack(decision)
        if decision == 'deny':
            self._reason = 'image_denied'; self._stop.set()

    async def _session(self):
        import asyncio
        import select
        adoption_deadline = min(self._lifetime_deadline, self._loop.time() + self._timeout)
        self._command_task = self._task(self._control.receive(max(0, adoption_deadline - self._loop.time())))
        while not self._stop.is_set():
            if self._root_task.done():
                self._root_task.result()
                self._stop.set()
                break
            now = self._loop.time()
            if now >= self._lifetime_deadline or (not self._adopted and now >= adoption_deadline):
                raise GuardianV2Error('guardian_v2_session_deadline')
            if any(image['state'] in ('fresh', 'held') and image['deadline'] is not None
                    and now >= image['deadline'] for image in self._images.values()):
                raise GuardianV2Error('guardian_v2_image_deadline')
            if self._command_task.done():
                value = self._command_task.result()
                kind = self._validate_command(value)
                if kind == 'stop': self._reason = 'host_stop'; self._stop.set(); break
                if kind == 'adopted':
                    if self._adopted or self.state != 'offered': raise GuardianV2Error('guardian_v2_adoption_replayed')
                    self._live_worker()
                    self._adopted = True; self._seal_stdio()
                    await self._event('stdio_sealed', all_data_pipes_closed=True)
                    self.state = 'running'; self._release.set()
                elif kind == 'image_authorize':
                    if not self._adopted: raise GuardianV2Error('guardian_v2_authorization_before_adoption')
                    await self._authorize(value)
                if self._stop.is_set(): break
                self._command_task = self._task(self._control.receive(max(0,
                    (self._lifetime_deadline if self._adopted else adoption_deadline) - self._loop.time())))
            for purpose, image in self._images.items():
                if (self._adopted and image['state'] == 'fresh' and image['task'] is None
                        and select.select([image['socket']], [], [], 0)[0]):
                    # Readiness observes no bytes and owns no I/O. The channel
                    # stays sole reader/closer; its short absolute timer begins
                    # at actual CREATE bytes/EOF, not at unrelated earlier work.
                    image['deadline'] = min(self._lifetime_deadline, self._loop.time() + self._timeout)
                    image['task'] = self._task(self._channels[purpose].receive_create())
                task = image['task']
                if task is not None and image['state'] == 'fresh' and task.done():
                    frame = task.result()
                    await self._image_received(purpose, frame)
            await asyncio.sleep(.003)

    async def _native_cleanup(self):
        import asyncio
        if self.native_drained: return
        self._stop.set()
        if self._factory and not self._caps: self._caps = self._factory.capabilities
        if self._caps and self._bootstrap is None:
            # A post-Create factory refusal can precede pump startup. Establish
            # the debug event gate before terminating the job: resuming an
            # already terminated initial thread cannot establish suspend count.
            self._same_creator()
            if not self._caps['process_handle'] or not self._caps['thread_handle'] or not self._caps['pid']:
                raise GuardianV2Error('guardian_v2_raw_root_unknown')
            self._debug.enable_kill()
            self._bootstrap = self._debug.resume(self._caps['thread_handle'])
            if self._bootstrap != 1: raise GuardianV2Error('guardian_v2_bootstrap_unproven')
        if self._job and not self._job_termination_requested:
            self._api.terminate_job(self._job)
            self._job_termination_requested = True
        if self._root_task and not self._root_task.done():
            done, pending = await asyncio.wait((self._root_task,), timeout=self._close_timeout)
            if pending: raise GuardianV2Error('guardian_v2_root_pump_unsettled')
            self._root_task.result()
        if self._caps: await self._root_drain()
        if self._factory and self._factory.created and not self._caps:
            raise GuardianV2Error('guardian_v2_raw_creation_unknown')
        # Preserve event-origin rule: this guardian never continues a worker's
        # native debug event. Worker death/outer job termination settle that tree.
        deadline = self._loop.time() + self._close_timeout
        if self._job:
            while True:
                total, active = self._api.accounting(self._job)
                with self._observer_lock:
                    complete = not self._inventory_error and self._births == total
                    waits = [self._debug.wait(item['handle']) for item in self._observers if item['handle']]
                native_waits = [self._debug.wait(record['slots']['process'][0].value) for record in self._records
                    if record['slots'].get('process') and record['slots']['process'][0].value]
                if active == 0 and complete and all(waits) and all(native_waits): break
                if self._loop.time() >= deadline: raise GuardianV2Error('guardian_v2_job_drain_unproven')
                await asyncio.sleep(.005)
        for channel in self._channels.values(): await channel.aclose()
        for record in self._shares:
            if record['state'] != 'channel_owned': self._close_socket(record)
        for image in self._images.values():
            task = image['task']
            if task is not None and not task.done():
                done, pending = await asyncio.wait((task,), timeout=self._close_timeout)
                if pending: raise GuardianV2Error('guardian_v2_image_task_unsettled')
            if task is not None:
                try: task.result()
                except BaseException: pass
        for record in self._records:
            for name, slots in record['slots'].items():
                if slots[0].value:
                    self._close_handle(('native', id(record), name), slots[0].value); slots[0].value = None
        while self._files:
            self._close_handle(('event_file', id(self._files), len(self._files)), self._files[-1]); self._files.pop()
        # All public async image operations must settle before source guards close.
        self._close_pipes()
        if self._factory: self._factory.close()
        if self._inventory_thread:
            self._inventory_stop.set()
            self._inventory_thread.join(.2)
            if self._inventory_thread.is_alive(): raise GuardianV2Error('guardian_v2_inventory_thread_unsettled')
        for index, item in enumerate(self._observers):
            if item['handle']:
                self._close_handle(('observer', index), item['handle']); item['handle'] = None
        if self._port:
            self._close_handle(('port',), self._port); self._port = None
        if self._job:
            self._close_handle(('job',), self._job); self._job = None
        while self._guards:
            self._guards[-1].close(); self._guards.pop()
        for record in self._marker_files: self._close_marker_file(record)
        while self._markers:
            self._markers[-1].unlink(missing_ok=True); self._markers.pop()
        self.native_drained = True

    async def _cleanup(self):
        await self._native_cleanup()
        # Also cover a fromshare socket retained by the entrypoint before a
        # failed control constructor transferred ownership.
        for record in self._shares:
            if record['state'] != 'channel_owned': self._close_socket(record)
        # Drained describes native ownership only. Send it while control remains
        # owned, then close socket and await real uncancelled I/O completion.
        if (self._control and not self._control.poisoned and self._launch_offer_sent
                and not getattr(self, '_drained_sent', False)):
            try:
                await self._event('drained', root_terminal=self._root_terminal, debug_exit=self._seen_exit,
                    job_active=0, guards_closed=True, reason=self._reason)
                self._drained_sent = True
            except BaseException: pass
        if self._control: await self._control.close(self._close_timeout)
        # Observe all logical tasks, not just underlying socket I/O owners.
        import asyncio
        pending = [task for task in self._tasks if not task.done()]
        if pending:
            done, pending = await asyncio.wait(pending, timeout=self._close_timeout)
            if pending: raise GuardianV2Error('guardian_v2_tasks_unsettled')
        for task in self._tasks:
            try: task.result()
            except BaseException: pass
        self.closed, self.state = True, 'closed'
        _V2_RETAINED.discard(self)

    async def aclose(self):
        import asyncio
        if self.closed: return
        if self._loop is None:
            self.closed, self.state, self.native_drained = True, 'closed', True
            return
        if self._debug: self._same_creator()
        elif asyncio.get_running_loop() is not self._loop: raise GuardianV2Error('guardian_v2_loop_changed')
        if self._cleanup_task is None or self._cleanup_task.done(): self._cleanup_task = asyncio.create_task(self._cleanup())
        cancelled = False
        while True:
            try:
                await asyncio.shield(self._cleanup_task)
                break
            except asyncio.CancelledError:
                cancelled = True
                if self._cleanup_task.done():
                    try: self._cleanup_task.result()
                    except BaseException:
                        _V2_RETAINED.add(self)
                        raise GuardianV2CleanupError(self) from None
                    break
            except BaseException as error:
                self._cleanup_error = error
                _V2_RETAINED.add(self)
                raise GuardianV2CleanupError(self) from None
        if cancelled: raise asyncio.CancelledError

    async def run(self, owned_control_socket):
        import asyncio
        if self._used or self.closed: raise GuardianV2Error('guardian_v2_once_only')
        self._used = True
        self._loop, self._run_task = asyncio.get_running_loop(), asyncio.current_task()
        self._lifetime_deadline = self._loop.time() + self._lifetime_timeout
        self._stop, self._held, self._release = asyncio.Event(), asyncio.Event(), asyncio.Event()
        cancelled = False
        try:
            self._control = _GuardianControl(owned_control_socket, self._timeout)
            await self._prepare()
            await self._session()
        except asyncio.CancelledError:
            cancelled = True; self._reason = 'cancelled'
        except BaseException as error:
            self._failure = error  # Retain privately; never reflect peer/native text.
            self._reason = 'refused'
        finally:
            await self.aclose()
        if cancelled: raise asyncio.CancelledError


def validate_guardian_startup2(packet):
    """Closed host metadata only; socket sharing authenticates no host by itself."""
    import base64
    fields = {'version', 'type', 'control_share', 'policy', 'image_policy', 'fences',
        'launch_nonce', 'invocations', 'timeout', 'close_timeout', 'lifetime_timeout'}
    _v2_fields(packet, fields)
    if (type(packet['version']) is not int or packet['version'] != 2
            or type(packet['type']) is not str or packet['type'] != 'guardian_startup2'
            or type(packet['control_share']) is not str or not 0 < len(packet['control_share']) <= 8192):
        raise ValueError('guardian_v2_startup_invalid')
    try:
        blob = base64.b64decode(packet['control_share'], validate=True)
        if not 0 < len(blob) <= 4096 or base64.b64encode(blob).decode('ascii') != packet['control_share']:
            raise ValueError('share')
    except (ValueError, UnicodeError): raise ValueError('guardian_v2_startup_invalid') from None
    GuardianV2(packet['policy'], **{key: packet[key] for key in fields - {'version', 'type', 'control_share', 'policy'}})
    return json.loads(_v2_json(packet))


def read_guardian_startup2(stream):
    """One canonical ASCII NDJSON packet <=2MiB, nesting <=12, duplicates refused."""
    raw = stream.readline(2 * 1024 * 1024 + 1)
    if type(raw) is not bytes or not raw.endswith(b'\n') or len(raw) > 2 * 1024 * 1024:
        raise ValueError('guardian_v2_startup_invalid')
    raw = raw[:-1]
    quoted = escaped = False
    depth = 0
    for byte in raw:
        if byte > 127: raise ValueError('guardian_v2_startup_invalid')
        if quoted:
            if escaped: escaped = False
            elif byte == 92: escaped = True
            elif byte == 34: quoted = False
        elif byte == 34: quoted = True
        elif byte in (123, 91):
            depth += 1
            if depth > 12: raise ValueError('guardian_v2_startup_invalid')
        elif byte in (125, 93):
            depth -= 1
            if depth < 0: raise ValueError('guardian_v2_startup_invalid')
    if quoted or depth: raise ValueError('guardian_v2_startup_invalid')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('guardian_v2_startup_invalid')
            result[key] = value
        return result
    def integer(raw):
        if len(raw) > 20: raise ValueError('guardian_v2_startup_invalid')
        return int(raw)
    def reject(raw): raise ValueError('guardian_v2_startup_invalid')
    try:
        packet = json.loads(raw, object_pairs_hook=pairs, parse_int=integer, parse_constant=reject)
        if _v2_json(packet) != raw: raise ValueError('canonical')
        return validate_guardian_startup2(packet)
    except (ValueError, TypeError, RecursionError):
        raise ValueError('guardian_v2_startup_invalid') from None


async def serve_guardian_startup2(packet):
    """Adopt only a host-shared control socket; no private worker input here.

    Cleanup failure retains owner while this guardian lives; if its outer entry
    process exits, durable fences remain blocked for independent recovery.
    """
    import base64
    import socket
    packet = validate_guardian_startup2(packet)
    owner = GuardianV2(packet['policy'], **{key: packet[key] for key in
        ('image_policy', 'fences', 'launch_nonce', 'invocations', 'timeout', 'close_timeout', 'lifetime_timeout')})
    sock = socket.fromshare(base64.b64decode(packet['control_share'], validate=True))
    owner._startup_socket = sock  # Retain immediately, including failed adoption.
    try: await owner.run(sock)
    finally:
        if owner._control is None:
            record = {'socket': sock, 'state': 'live'}
            owner._shares.append(record)
            try: owner._close_socket(record)
            except BaseException:
                owner.closed, owner.state = False, 'closing'
                owner._cleanup_task = None
                _V2_RETAINED.add(owner)
                raise GuardianV2CleanupError(owner) from None


def guardian_main():
    """One startup line; preserve legacy validation when the packet is not v2."""
    import asyncio
    import io
    raw = sys.stdin.buffer.readline(2 * 1024 * 1024 + 1)
    try: packet = read_guardian_startup2(io.BytesIO(raw))
    except ValueError:
        if len(raw) > 32768: raise ValueError('native_lifetime_request_invalid') from None
        packet = json.loads(raw)  # Preserve original legacy duplicate/JSON behavior.
        if type(packet) is dict and type(packet.get('version')) is int and packet['version'] == 2:
            raise ValueError('guardian_v2_startup_invalid') from None
        if type(packet) is not dict or set(packet) != {'pid', 'locks', 'suspended'}:
            raise ValueError('native_lifetime_request_invalid') from None
        supervise(packet)
    else:
        asyncio.run(serve_guardian_startup2(packet))


if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    guardian_main()
