"""Owned private2 endpoint; actual process provenance and phase gates are external.

Only the closed native_protocol bodies can cross this socket. The constructor
takes exclusive ownership after checks; no makefile/other reader, writer or closer
may use it. A cancelled logical I/O task never counts as observed IO completion.
"""
from __future__ import annotations

import asyncio
import json
import math
import socket
import struct
import sys

from improvement_native_protocol import (MAX_PRIVATE_BYTES, encode_private_packet2,
    decode_private_packet2, validate_private_packet2)

_RETAINED = set()


class PrivateChannelError(OSError):
    pass


class PrivateChannelCleanupError(PrivateChannelError):
    def __init__(self, owner):
        super().__init__('private_channel_cleanup_unproven')
        self.owner = owner


def _duration(value, maximum):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= maximum:
        raise ValueError('private_channel_deadline_invalid')


class PrivateWorkerChannelV2:
    """One send plus one receive may run concurrently on the constructing loop.

    Receive defaults to the immutable overall lifetime, allowing a model to be
    quiet. A caller may request a shorter phase deadline. Each actual send uses
    the bounded timeout; no packet resets lifetime. Cleanup owns logical tasks
    through successful socket close and actual uncancelled task completion.
    """
    def __init__(self, owned_socket, *, binding, role, timeout=8, close_timeout=8, lifetime_timeout=300):
        if type(role) is not str or role not in ('host', 'worker'):
            raise ValueError('private_channel_role_invalid')
        _duration(timeout, 60); _duration(close_timeout, 60); _duration(lifetime_timeout, 300)
        if type(binding) is not dict or any(type(key) is not str for key in binding):
            raise ValueError('private_channel_binding_invalid')
        probe = {'version': 2, 'sequence': 1, **{key: binding.get(key) for key in
            ('launch_nonce', 'worker_pid', 'worker_birth')}, 'body': {'type': 'endpoints_adopted'}}
        try:
            validate_private_packet2(probe, binding=binding, direction='worker', expected_sequence=1)
            copied = json.loads(json.dumps(binding, ensure_ascii=False, allow_nan=False))
        except (ValueError, TypeError):
            raise ValueError('private_channel_binding_invalid') from None
        if type(owned_socket) is not socket.socket:
            raise ValueError('private_channel_socket_invalid')
        try:
            if (owned_socket.fileno() < 0 or owned_socket.get_inheritable()
                    or owned_socket.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM):
                raise ValueError('private_channel_socket_invalid')
            owned_socket.getpeername()
            loop = asyncio.get_running_loop()
            owned_socket.setblocking(False)
        except (OSError, RuntimeError):
            raise ValueError('private_channel_socket_invalid') from None
        self._socket, self._loop, self._binding, self._role = owned_socket, loop, copied, role
        self._timeout, self._close_timeout = timeout, close_timeout
        self._deadline = loop.time() + lifetime_timeout
        self._send_sequence = self._receive_sequence = 0
        self._tasks, self._buffers, self._active = [], {}, set()
        self._closing = self._closed = self._poisoned = self._lost = self._socket_closed = False
        self._cleanup_task = None

    @property
    def closed(self): return self._closed
    @property
    def poisoned(self): return self._poisoned
    @property
    def close_authority_lost(self): return self._lost

    def _same_loop(self):
        if asyncio.get_running_loop() is not self._loop:
            raise PrivateChannelError('private_channel_loop_changed')

    def _remaining(self, timeout):
        remaining = self._deadline - self._loop.time()
        if timeout is not None:
            _duration(timeout, 300)
            remaining = min(remaining, timeout)
        if remaining <= 0: raise PrivateChannelError('private_channel_deadline')
        return remaining

    async def _exact(self, size):
        value = bytearray()
        self._retain_buffer(value)
        while len(value) < size:
            if self._closing: raise PrivateChannelError('private_channel_closing')
            part = await self._loop.sock_recv(self._socket, size - len(value))
            if not part: raise PrivateChannelError('private_channel_eof')
            value.extend(part)
        return bytes(value)

    def _retain_buffer(self, value):
        # Each actual logical I/O task owns only its active buffers. Keep them
        # on uncertain cleanup, discard after its completed result is consumed.
        self._buffers.setdefault(asyncio.current_task(), []).append(value)

    async def _receive(self):
        header = await self._exact(4)
        size, = struct.unpack('!I', header)
        if not 0 < size <= MAX_PRIVATE_BYTES: raise PrivateChannelError('private_channel_size')
        frame = header + await self._exact(size)
        packet = decode_private_packet2(frame, binding=self._binding,
            direction='worker' if self._role == 'host' else 'host', expected_sequence=self._receive_sequence + 1)
        self._receive_sequence += 1
        return packet

    async def _send(self, body):
        packet = {'version': 2, 'sequence': self._send_sequence + 1,
            **{key: self._binding[key] for key in ('launch_nonce', 'worker_pid', 'worker_birth')}, 'body': body}
        frame = encode_private_packet2(packet, binding=self._binding, direction=self._role,
            expected_sequence=self._send_sequence + 1)
        self._retain_buffer(frame)
        await self._loop.sock_sendall(self._socket, frame)
        self._send_sequence += 1
        # Return the sent snapshot, never a reference to caller-mutable body.
        return decode_private_packet2(frame, binding=self._binding, direction=self._role,
            expected_sequence=self._send_sequence)

    async def _operate(self, kind, callback, timeout):
        self._same_loop()
        if self._closing or self._closed or self._poisoned:
            raise PrivateChannelError('private_channel_unavailable')
        try:
            if kind in self._active: raise PrivateChannelError('private_channel_concurrent_operation')
            remaining = self._remaining(timeout)
            self._active.add(kind)
            task = asyncio.create_task(callback())
            self._tasks.append(task)
            done, _ = await asyncio.wait((task,), timeout=remaining)
            if task not in done: raise PrivateChannelError('private_channel_deadline')
            result = task.result()
            self._active.remove(kind)
            self._buffers.pop(task, None)
            self._tasks.remove(task)
            return result
        except BaseException as error:
            self._poisoned = True
            await self.aclose()
            if isinstance(error, asyncio.CancelledError): raise
            raise PrivateChannelError('private_channel_failed') from None

    async def send(self, body):
        return await self._operate('send', lambda: self._send(body), self._timeout)

    async def receive(self, *, timeout=None):
        return await self._operate('receive', self._receive, timeout)

    async def _close_impl(self):
        self._closing = self._poisoned = True
        if self._lost: raise PrivateChannelError('private_channel_close_authority_lost')
        if not self._socket_closed:
            if self._socket.fileno() < 0:
                self._lost = True
                raise PrivateChannelError('private_channel_close_authority_lost')
            if any(not task.done() for task in self._tasks):
                try: self._socket.shutdown(socket.SHUT_RDWR)
                except OSError: pass  # Wake-up hint; success is not close proof.
                if sys.platform != 'win32' and isinstance(self._loop, asyncio.SelectorEventLoop):
                    # Selector readiness must settle while this descriptor is
                    # still owned/open. Proactor instead needs closesocket to
                    # initiate completion of outstanding Windows operations.
                    pending = [task for task in self._tasks if not task.done()]
                    if pending:
                        _, pending = await asyncio.wait(pending, timeout=self._close_timeout)
                        if pending: raise PrivateChannelError('private_channel_io_unsettled')
            try:
                self._socket.close()
            except BaseException:
                if self._socket.fileno() < 0: self._lost = True
                raise
            if self._socket.fileno() >= 0: raise PrivateChannelError('private_channel_close_unproven')
            self._socket_closed = True
        pending = [task for task in self._tasks if not task.done()]
        if pending:
            _, pending = await asyncio.wait(pending, timeout=self._close_timeout)
            if pending: raise PrivateChannelError('private_channel_io_unsettled')
        for task in self._tasks:
            if task.cancelled(): raise PrivateChannelError('private_channel_cancelled_io_unproven')
            try: task.result()
            except BaseException: pass  # Observed terminal operation error, not cancellation.
        self._closed = True
        self._buffers.clear()
        self._tasks.clear()
        _RETAINED.discard(self)

    async def aclose(self):
        self._same_loop()
        if self._closed: return
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._close_impl())
        cancelled = False
        while True:
            try:
                await asyncio.shield(self._cleanup_task)
                break
            except asyncio.CancelledError:
                cancelled = True
                if self._cleanup_task.done():
                    try:
                        self._cleanup_task.result()
                    except BaseException:
                        _RETAINED.add(self)
                        raise PrivateChannelCleanupError(self) from None
                    break
            except BaseException:
                _RETAINED.add(self)
                raise PrivateChannelCleanupError(self) from None
        if cancelled: raise asyncio.CancelledError
