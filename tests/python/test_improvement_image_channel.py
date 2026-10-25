"""Metadata-only private socketpairs; no SDK, subprocess, or account access."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import importlib
import importlib.util
import json
import socket
import struct
import unittest
from unittest.mock import patch


NONCE = 'a' * 64


def create_frame():
    return {'version': 1, 'type': 'native_create_held', 'nonce': NONCE, 'worker_pid': 123,
        'worker_birth': 456, 'creator_thread': 7, 'native_pid': 8, 'native_birth': 901,
        'native_tid': 10, 'native_thread_birth': 11, 'hfile': 12, 'hprocess': 13, 'hthread': 14,
        'bootstrap_count': 1, 'kill_on_exit': True}


def wire(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')
    return struct.pack('!I', len(raw)) + raw


class ImageMetadataChannelTests(unittest.IsolatedAsyncioTestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('improvement_image_channel'), 'metadata image channel missing')
        return importlib.import_module('improvement_image_channel')

    def pair(self):
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)
        left.setblocking(False); right.setblocking(False)
        return left, right

    def channel(self, sock, role='guardian', **changes):
        args = dict(role=role, nonce=NONCE, worker_pid=123, worker_birth=456, timeout=1, close_timeout=1)
        args.update(changes)
        return self.module().ImageMetadataChannel(sock, **args)

    async def test_allow_and_deny_roundtrips_are_bound_and_defensive(self):
        for decision in ('allow', 'deny'):
            left, right = self.pair()
            async with self.channel(left, 'worker') as worker, self.channel(right) as guardian:
                task = asyncio.create_task(worker.exchange(create_frame()))
                received = await guardian.receive_create()
                self.assertEqual(received, create_frame())
                received['native_birth'] = 999
                await guardian.send_ack(decision)
                ack = await task
                self.assertEqual(ack, {'version': 1, 'type': 'native_image_ack', 'nonce': NONCE,
                    'worker_birth': 456, 'native_birth': 901, 'decision': decision})
                self.assertEqual(worker.state, 'done')
                self.assertEqual(guardian.state, 'done')
            self.assertTrue(worker.closed and guardian.closed)
            self.assertEqual(left.fileno(), -1)
            self.assertEqual(right.fileno(), -1)

    async def test_constructor_strict_types_and_connected_noninheritable_stream(self):
        cls = self.module().ImageMetadataChannel
        class Text(str): pass
        left, right = self.pair()
        good = dict(role='worker', nonce=NONCE, worker_pid=123, worker_birth=456)
        bad = [dict(role=Text('worker')), dict(role='other'), dict(nonce='A' * 64), dict(nonce=Text(NONCE)),
            dict(worker_pid=True), dict(worker_birth=0), dict(worker_pid=1 << 32),
            dict(timeout=True), dict(timeout=float('inf')), dict(close_timeout=0)]
        for change in bad:
            with self.subTest(change=change), self.assertRaises((TypeError, ValueError)):
                cls(left, **{**good, **change})
        self.assertGreaterEqual(left.fileno(), 0)
        left.set_inheritable(True)
        try:
            with self.assertRaises((ValueError, OSError)): cls(left, **good)
        finally: left.set_inheritable(False)
        for family, kind in ((socket.AF_INET, socket.SOCK_STREAM), (socket.AF_INET, socket.SOCK_DGRAM)):
            sock = socket.socket(family, kind)
            try:
                with self.assertRaises((ValueError, OSError)): cls(sock, **good)
            finally: sock.close()

    async def test_fragmented_header_and_body_are_reassembled_once(self):
        left, right = self.pair()
        async with self.channel(left) as guardian:
            task = asyncio.create_task(guardian.receive_create())
            raw = wire(create_frame())
            for index in range(0, len(raw), 3):
                await asyncio.get_running_loop().sock_sendall(right, raw[index:index + 3])
                await asyncio.sleep(0)
            self.assertEqual(await task, create_frame())
            await guardian.send_ack('deny')

    async def test_bad_length_duplicate_depth_canonical_and_schema_poison(self):
        frame = create_frame()
        canonical = wire(frame)[4:]
        payloads = [struct.pack('!I', 0), struct.pack('!I', 8193),
            struct.pack('!I', 0xffffffff),
            b'{"version":1,"version":1}', b'{"x":{"nested":1}}', b'{"x":[1]}',
            json.dumps(frame).encode(), canonical.replace(b'"version":1', b'"version":true'),
            canonical.replace(NONCE.encode(), ('b' * 64).encode()),
            wire({**frame, 'worker_birth': 999})[4:], wire({**frame, 'hfile': 0})[4:],
            wire({**frame, 'argv': 'PRIVATE_PAYLOAD'})[4:], b'\xff', b'{"x":NaN}']
        for index, body in enumerate(payloads):
            left, right = self.pair()
            channel = self.channel(left)
            raw = body if index < 3 else struct.pack('!I', len(body)) + body
            with self.subTest(index=index):
                await asyncio.get_running_loop().sock_sendall(right, raw)
                with self.assertRaises(OSError) as caught: await channel.receive_create()
                self.assertNotIn('PRIVATE_PAYLOAD', str(caught.exception))
                self.assertTrue(channel.poisoned and channel.closed)
                with self.assertRaises(OSError): await channel.receive_create()

    async def test_eof_at_header_and_body_is_terminal_without_resync(self):
        for fragment in (b'', b'\x00\x00', struct.pack('!I', 100) + b'{'):
            left, right = self.pair()
            channel = self.channel(left)
            await asyncio.get_running_loop().sock_sendall(right, fragment)
            right.close()
            with self.assertRaises(OSError): await channel.receive_create()
            self.assertTrue(channel.closed and channel.poisoned)

    async def test_outbound_bad_metadata_and_wrong_ack_binding_cannot_allow(self):
        class Text(str): pass
        for change in ({'nonce': Text(NONCE)}, {'worker_pid': True}, {'hthread': 1 << 64}, {'prompt': 'PRIVATE'}):
            left, right = self.pair()
            channel = self.channel(left, 'worker')
            with self.subTest(change=change), self.assertRaises(OSError):
                await channel.exchange({**create_frame(), **change})
            self.assertTrue(channel.closed and channel.poisoned)
        left, right = self.pair()
        channel = self.channel(left, 'worker')
        task = asyncio.create_task(channel.exchange(create_frame()))
        await asyncio.get_running_loop().sock_recv(right, 8192)
        ack = {'version': 1, 'type': 'native_image_ack', 'nonce': NONCE,
            'worker_birth': 456, 'native_birth': 902, 'decision': 'allow'}
        await asyncio.get_running_loop().sock_sendall(right, wire(ack))
        with self.assertRaises(OSError): await task
        self.assertTrue(channel.closed and channel.poisoned)

    async def test_replay_and_wrong_order_are_refused(self):
        left, right = self.pair()
        channel = self.channel(left)
        with self.assertRaises(OSError): await channel.send_ack('allow')
        self.assertTrue(channel.closed)
        left, right = self.pair()
        async with self.channel(left, 'worker') as worker, self.channel(right) as guardian:
            task = asyncio.create_task(worker.exchange(create_frame()))
            await guardian.receive_create()
            await guardian.send_ack('allow')
            await task
            with self.assertRaises(OSError): await worker.exchange(create_frame())
            with self.assertRaises(OSError): await guardian.send_ack('allow')

    async def test_partial_receive_repeated_cancellation_settles_uncancelled_io(self):
        left, right = self.pair()
        channel = self.channel(left)
        task = asyncio.create_task(channel.receive_create())
        await asyncio.get_running_loop().sock_sendall(right, wire(create_frame())[:9])
        await asyncio.sleep(.01)
        task.cancel()
        for _ in range(8):
            await asyncio.sleep(0)
            task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertTrue(channel.closed and channel.poisoned)
        self.assertTrue(all(item.done() and not item.cancelled() for item in channel._io_tasks))

    async def test_actual_partial_send_then_cancel_poison_closes_without_io_task_cancel(self):
        left, right = self.pair()
        channel = self.channel(left, 'worker')
        loop = asyncio.get_running_loop()
        original_send = loop.sock_sendall
        prefix_sent = asyncio.Event()
        async def partial(sock, raw):
            if sock is left:
                await original_send(sock, raw[:6])
                prefix_sent.set()
                await loop.sock_recv(sock, 1)  # Real blocked I/O, awakened by shutdown.
                raise OSError('injected partial send')
            return await original_send(sock, raw)
        with patch.object(loop, 'sock_sendall', side_effect=partial):
            task = asyncio.create_task(channel.exchange(create_frame()))
            await asyncio.wait_for(prefix_sent.wait(), 1)
            self.assertEqual(await loop.sock_recv(right, 100), wire(create_frame())[:6])
            task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
        self.assertTrue(channel.closed and channel.poisoned)
        self.assertTrue(all(item.done() and not item.cancelled() for item in channel._io_tasks))

    async def test_deadline_poison_settles_real_blocked_receive(self):
        left, right = self.pair()
        channel = self.channel(left, timeout=.03)
        with self.assertRaises(OSError): await channel.receive_create()
        self.assertTrue(channel.closed and channel.poisoned)
        self.assertTrue(all(item.done() and not item.cancelled() for item in channel._io_tasks))

    async def test_shutdown_failure_retains_pending_io_without_cancelling_then_retries(self):
        left, right = self.pair()
        channel = self.channel(left)
        task = asyncio.create_task(channel.receive_create())
        await asyncio.sleep(.01)
        original = socket.socket.shutdown
        def failed(sock, how):
            if sock is left: raise OSError('injected before shutdown')
            return original(sock, how)
        with patch.object(socket.socket, 'shutdown', failed):
            with self.assertRaises(OSError) as caught: await channel.aclose()
        self.assertIs(caught.exception.owner, channel)
        self.assertTrue(any(not item.done() for item in channel._io_tasks))
        self.assertTrue(all(not item.cancelled() for item in channel._io_tasks))
        await channel.aclose()
        with self.assertRaises(OSError): await task
        self.assertTrue(channel.closed)

    async def test_live_preclose_failure_retains_real_socket_for_retry(self):
        left, right = self.pair()
        channel = self.channel(left)
        original = socket.socket.close
        def before(sock):
            if sock is left: raise OSError('injected before real close')
            return original(sock)
        with patch.object(socket.socket, 'close', before):
            with self.assertRaises(OSError) as caught: await channel.aclose()
        self.assertIs(caught.exception.owner, channel)
        self.assertGreaterEqual(left.fileno(), 0)
        self.assertFalse(channel.close_authority_lost)
        left.getpeername()  # Actual still-owned socket, not a fake numeric authority.
        await channel.aclose()
        self.assertTrue(channel.closed)

    async def test_consumed_close_fault_is_permanently_unproven_not_false_retry_success(self):
        left, right = self.pair()
        channel = self.channel(left)
        original = socket.socket.close
        def after(sock):
            original(sock)
            if sock is left: raise OSError('injected after real close consumed authority')
        with patch.object(socket.socket, 'close', after):
            with self.assertRaises(OSError) as caught: await channel.aclose()
        self.assertIs(caught.exception.owner, channel)
        self.assertEqual(left.fileno(), -1)
        self.assertTrue(channel.close_authority_lost)
        self.assertFalse(channel.closed)
        with self.assertRaises(OSError) as caught: await channel.aclose()
        self.assertIs(caught.exception.owner, channel)
        self.assertFalse(channel.closed)

    async def test_cancelled_raw_receive_never_becomes_completed_io_cleanup(self):
        left, right = self.pair()
        channel = self.channel(left)
        caller = asyncio.create_task(channel.receive_create())
        while not channel._io_tasks: await asyncio.sleep(0)
        raw = channel._io_tasks[0]
        await asyncio.sleep(.01)  # Actual public-loop socket read is pending.
        raw.cancel()
        with self.assertRaises(self.module().ImageChannelCleanupError) as caught:
            await caller
        self.assertIs(caught.exception.owner, channel)
        self.assertTrue(raw.cancelled())
        self.assertEqual(left.fileno(), -1)  # Actual close still happens.
        self.assertFalse(channel.closed)
        self.assertTrue(channel.io_completion_unknown)
        self.assertTrue(channel._buffers)
        with self.assertRaises(self.module().ImageChannelCleanupError): await channel.aclose()
        self.assertFalse(channel.closed)


if __name__ == '__main__': unittest.main()
