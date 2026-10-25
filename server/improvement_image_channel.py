"""One metadata-only image exchange over an exclusively owned connected socket.

No cross-process socket sharing or peer-process authority is established here.
The guardian binding must come from its retained original live worker handle.
No other reader/writer/makefile wrapper may use the transferred socket.
"""
from __future__ import annotations

import asyncio
import json
import math
import re
import socket
import struct
import sys

_MAX_FRAME = 8192
_RETAINED = set()
_CREATE = frozenset(('version', 'type', 'nonce', 'worker_pid', 'worker_birth', 'creator_thread',
    'native_pid', 'native_birth', 'native_tid', 'native_thread_birth', 'hfile', 'hprocess', 'hthread',
    'bootstrap_count', 'kill_on_exit'))
_ACK = frozenset(('version', 'type', 'nonce', 'worker_birth', 'native_birth', 'decision'))


class ImageChannelError(OSError):
    """Closed public protocol error, never raw packet or underlying error text."""


class ImageChannelCleanupError(ImageChannelError):
    def __init__(self, owner):
        super().__init__('image_channel_cleanup_unproven')
        self.owner = owner


def _uint(value, bits):
    return type(value) is int and 0 < value < (1 << bits)


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result: raise ImageChannelError('image_channel_duplicate_key')
        result[key] = value
    return result


def _integer(raw):
    if len(raw) > 20: raise ImageChannelError('image_channel_integer_invalid')
    return int(raw)


def _no_number(raw):
    raise ImageChannelError('image_channel_number_invalid')


def _flat_ascii(raw):
    # A closed schema has one object and scalar values. Bound nesting before
    # calling json.loads, rather than relying on its recursion limit.
    if not raw or raw[0] != 123 or raw[-1] != 125 or any(byte > 127 for byte in raw):
        raise ImageChannelError('image_channel_json_invalid')
    quoted = escaped = False
    depth = 0
    for byte in raw:
        if quoted:
            if escaped: escaped = False
            elif byte == 92: escaped = True
            elif byte == 34: quoted = False
        elif byte == 34: quoted = True
        elif byte == 123:
            depth += 1
            if depth != 1: raise ImageChannelError('image_channel_depth_invalid')
        elif byte == 125:
            depth -= 1
            if depth != 0: raise ImageChannelError('image_channel_depth_invalid')
        elif byte in (91, 93): raise ImageChannelError('image_channel_depth_invalid')
    if quoted or depth != 0: raise ImageChannelError('image_channel_json_invalid')


class ImageMetadataChannel:
    """Worker exchange(CREATE), or guardian receive_create()/send_ack(decision).

    One invocation only. Any error poisons the channel; it cannot resynchronize.
    Pending I/O tasks are not cancelled: shutdown/close interrupts their I/O,
    and cleanup retains them until actual completion. Lost close authority
    is permanently unproven and requires enclosing process drain.
    """
    def __init__(self, owned_socket, *, role, nonce, worker_pid, worker_birth, timeout=8, close_timeout=8):
        if type(role) is not str or role not in ('worker', 'guardian'):
            raise ValueError('image_channel_role_invalid')
        if type(nonce) is not str or re.fullmatch('[0-9a-f]{64}', nonce) is None:
            raise ValueError('image_channel_nonce_invalid')
        if not _uint(worker_pid, 32) or not _uint(worker_birth, 64):
            raise ValueError('image_channel_worker_binding_invalid')
        for value in (timeout, close_timeout):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 60:
                raise ValueError('image_channel_deadline_invalid')
        if type(owned_socket) is not socket.socket:
            raise TypeError('image_channel_socket_invalid')
        try:
            if (owned_socket.fileno() < 0 or owned_socket.get_inheritable()
                    or owned_socket.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM):
                raise ValueError('image_channel_socket_invalid')
            owned_socket.getpeername()
            loop = asyncio.get_running_loop()
            owned_socket.setblocking(False)
        except (OSError, RuntimeError):
            raise ValueError('image_channel_socket_invalid') from None
        # Ownership transfers only after the strict constructor checks succeed.
        self._socket, self._loop = owned_socket, loop
        self._role, self._nonce = role, nonce
        self._worker_pid, self._worker_birth = worker_pid, worker_birth
        self._timeout, self._close_timeout = timeout, close_timeout
        self._deadline = None
        self._state, self._creation = 'fresh', None
        self._closing = self._closed = self._poisoned = self._close_authority_lost = False
        self._socket_close_succeeded = False
        self._io_completion_unknown = False
        self._io_tasks, self._buffers = [], []
        self._cleanup_task = None

    @property
    def state(self): return self._state
    @property
    def closed(self): return self._closed
    @property
    def poisoned(self): return self._poisoned
    @property
    def close_authority_lost(self): return self._close_authority_lost

    @property
    def io_completion_unknown(self): return self._io_completion_unknown

    def _same_loop(self):
        if asyncio.get_running_loop() is not self._loop:
            raise ImageChannelError('image_channel_loop_changed')

    def _begin(self, role, phase, next_phase):
        self._same_loop()
        if self._closed or self._closing or self._poisoned or self._role != role or self._state != phase:
            raise ImageChannelError('image_channel_order_invalid')
        if self._deadline is None: self._deadline = self._loop.time() + self._timeout
        if self._loop.time() >= self._deadline: raise ImageChannelError('image_channel_deadline_exceeded')
        self._state = next_phase

    def _check_io(self):
        if self._closing or self._poisoned: raise ImageChannelError('image_channel_poisoned')

    def _validate(self, value, kind, native_birth=None):
        keys = _CREATE if kind == 'create' else _ACK
        if type(value) is not dict or any(type(key) is not str for key in value) or value.keys() != keys:
            raise ImageChannelError('image_channel_schema_invalid')
        if (type(value['version']) is not int or value['version'] != 1 or type(value['type']) is not str
                or value['type'] != ('native_create_held' if kind == 'create' else 'native_image_ack')
                or type(value['nonce']) is not str or value['nonce'] != self._nonce
                or not _uint(value['worker_birth'], 64) or value['worker_birth'] != self._worker_birth):
            raise ImageChannelError('image_channel_binding_invalid')
        if kind == 'create':
            for name in ('worker_pid', 'creator_thread', 'native_pid', 'native_tid'):
                if not _uint(value[name], 32): raise ImageChannelError('image_channel_identity_invalid')
            for name in ('native_birth', 'native_thread_birth', 'hfile', 'hprocess', 'hthread'):
                if not _uint(value[name], 64): raise ImageChannelError('image_channel_identity_invalid')
            if (value['worker_pid'] != self._worker_pid or type(value['bootstrap_count']) is not int
                    or value['bootstrap_count'] != 1 or value['kill_on_exit'] is not True
                    or any(value[name] == (1 << 64) - 1 for name in ('hfile', 'hprocess', 'hthread'))):
                raise ImageChannelError('image_channel_identity_invalid')
        elif (not _uint(value['native_birth'], 64) or value['native_birth'] != native_birth
                or type(value['decision']) is not str or value['decision'] not in ('allow', 'deny')):
            raise ImageChannelError('image_channel_ack_invalid')
        return dict(value)

    def _encode(self, value, kind, native_birth=None):
        value = self._validate(value, kind, native_birth)
        raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')
        if not 0 < len(raw) <= _MAX_FRAME: raise ImageChannelError('image_channel_size_invalid')
        return raw

    async def _read_exact(self, size):
        raw = bytearray()
        self._buffers.append(raw)
        while len(raw) < size:
            self._check_io()
            part = await self._loop.sock_recv(self._socket, size - len(raw))
            if not part or len(part) > size - len(raw): raise ImageChannelError('image_channel_eof')
            raw.extend(part)
        return bytes(raw)

    async def _receive(self, kind, native_birth=None):
        header = await self._read_exact(4)
        size = struct.unpack('!I', header)[0]
        if not 0 < size <= _MAX_FRAME: raise ImageChannelError('image_channel_size_invalid')
        raw = await self._read_exact(size)
        _flat_ascii(raw)
        value = json.loads(raw.decode('ascii'), object_pairs_hook=_pairs, parse_int=_integer,
            parse_float=_no_number, parse_constant=_no_number)
        canonical = self._encode(value, kind, native_birth)
        if raw != canonical: raise ImageChannelError('image_channel_noncanonical')
        return dict(value)

    async def _send(self, value, kind, native_birth=None):
        raw = self._encode(value, kind, native_birth)
        packet = struct.pack('!I', len(raw)) + raw
        self._buffers.append(packet)
        self._check_io()
        await self._loop.sock_sendall(self._socket, packet)

    async def _worker_exchange(self, frame):
        frame = self._validate(frame, 'create')
        await self._send(frame, 'create')
        return await self._receive('ack', frame['native_birth'])

    async def _operate(self, role, phase, next_phase, operation, result_phase):
        self._same_loop()
        try:
            self._begin(role, phase, next_phase)
            task = asyncio.create_task(operation())
            self._io_tasks.append(task)
            # asyncio.wait, unlike wait_for or awaiting task directly, does not
            # propagate caller cancellation to the retained socket I/O task.
            done, _ = await asyncio.wait((task,), timeout=max(0, self._deadline - self._loop.time()))
            if task not in done: raise ImageChannelError('image_channel_deadline_exceeded')
            result = task.result()
            self._check_io()
            self._state = result_phase
            return result
        except asyncio.CancelledError:
            self._poisoned = True
            await self.aclose()
            raise
        except BaseException:
            self._poisoned = True
            await self.aclose()
            raise ImageChannelError('image_channel_exchange_failed') from None

    async def exchange(self, create_frame):
        return await self._operate('worker', 'fresh', 'exchanging',
            lambda: self._worker_exchange(create_frame), 'done')

    async def receive_create(self):
        result = await self._operate('guardian', 'fresh', 'receiving', lambda: self._receive('create'), 'held')
        self._creation = dict(result)
        return dict(result)

    async def send_ack(self, decision):
        async def send():
            if type(decision) is not str or decision not in ('allow', 'deny'):
                raise ImageChannelError('image_channel_decision_invalid')
            frame = {'version': 1, 'type': 'native_image_ack', 'nonce': self._nonce,
                'worker_birth': self._worker_birth, 'native_birth': self._creation['native_birth'], 'decision': decision}
            await self._send(frame, 'ack', self._creation['native_birth'])
        await self._operate('guardian', 'held', 'sending_ack', send, 'done')

    async def _cleanup(self):
        self._closing = True
        if self._close_authority_lost: raise ImageChannelError('image_channel_close_authority_lost')
        pending = [task for task in self._io_tasks if not task.done()]
        if pending and not self._socket_close_succeeded:
            self._poisoned = True
            self._socket.shutdown(socket.SHUT_RDWR)
            if sys.platform != 'win32' and isinstance(self._loop, asyncio.SelectorEventLoop):
                # Keep the descriptor registered until shutdown wakes the actual
                # reader/writer. Closing it first removes the kernel readiness
                # event while the selector's public sock_* future is still live.
                _, remaining = await asyncio.wait(pending, timeout=self._close_timeout)
                if remaining: raise ImageChannelError('image_channel_io_completion_unproven')
        if not self._socket_close_succeeded:
            if self._socket.fileno() < 0:
                self._close_authority_lost = True
                raise ImageChannelError('image_channel_close_authority_lost')
            try:
                self._socket.close()
            except BaseException:
                if self._socket.fileno() < 0: self._close_authority_lost = True
                raise
            if self._socket.fileno() >= 0: raise ImageChannelError('image_channel_close_unproven')
            self._socket_close_succeeded = True
        # Windows shutdown alone need not finish an outstanding WSARecv. A
        # successful closesocket initiates completion; it is not completion.
        # Keep the uncancelled tasks/buffers until the public loop API settles.
        if pending:
            done, remaining = await asyncio.wait(pending, timeout=self._close_timeout)
            if remaining: raise ImageChannelError('image_channel_io_completion_unproven')
        if any(task.cancelled() for task in self._io_tasks):
            self._io_completion_unknown = True
        if self._io_completion_unknown:
            raise ImageChannelError('image_channel_io_completion_unproven')
        for task in self._io_tasks:
            try: task.result()
            except BaseException: pass  # Observe, but do not expose peer/buffer error text.
        self._closed = True
        self._buffers.clear()
        _RETAINED.discard(self)

    async def aclose(self):
        self._same_loop()
        if self._closed: return
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup())
        cancelled = False
        while True:
            try:
                await asyncio.shield(self._cleanup_task)
                break
            except asyncio.CancelledError:
                if self._cleanup_task.done():
                    try: self._cleanup_task.result()
                    except BaseException:
                        self._poisoned = True; _RETAINED.add(self)
                        raise ImageChannelCleanupError(self) from None
                    cancelled = True
                    break
                cancelled = True
            except BaseException:
                self._poisoned = True; _RETAINED.add(self)
                raise ImageChannelCleanupError(self) from None
        if cancelled: raise asyncio.CancelledError

    async def __aenter__(self):
        self._same_loop()
        if self._closed or self._closing: raise ImageChannelError('image_channel_closed')
        return self

    async def __aexit__(self, *_): await self.aclose()
