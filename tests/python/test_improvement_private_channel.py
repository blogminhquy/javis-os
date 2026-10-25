"""Private socketpairs only; no app configuration, filesystem, DB or child process."""
import asyncio
import importlib.util
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch

SERVER = Path(__file__).resolve().parents[2] / 'server'
sys.path.insert(0, str(SERVER))
if (SERVER / 'improvement_private_channel.py').exists():
    import improvement_private_channel as channel
else:
    channel = None


class PrivateChannelTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertIsNotNone(channel, 'private worker channel absent')
        self.left, self.right = socket.socketpair()
        self.left.setblocking(False); self.right.setblocking(False)
        self.binding = {'kind': 'trial', 'launch_nonce': 'a' * 64, 'worker_pid': 123, 'worker_birth': 456,
            'identity': {'trial_id': 'trial-a', 'attempt': 1, 'input_hash': 'b' * 64},
            'invocations': [{'purpose': purpose, 'nonce': str(index + 1) * 64} for index, purpose in
                enumerate(('adapter_version', 'auth_status', 'sdk_version', 'query'))]}
        self.owners = []

    def owner(self, sock, role):
        result = channel.PrivateWorkerChannelV2(sock, binding=self.binding, role=role,
            timeout=.2, close_timeout=.3, lifetime_timeout=2)
        self.owners.append(result)
        return result

    async def asyncTearDown(self):
        for owner in self.owners:
            if not owner.close_authority_lost:
                await owner.aclose()
        self.left.close(); self.right.close()

    async def test_both_directions_sequence_and_raw_event_values(self):
        host, worker = self.owner(self.left, 'host'), self.owner(self.right, 'worker')
        sent = await worker.send({'type': 'endpoints_adopted'})
        self.assertEqual(await host.receive(), sent)
        self.assertEqual(sent['sequence'], 1)
        event = {'type': 'engine_event', **self.binding['identity'], 'event': {'type': 'tool_result',
                 'is_error': None, 'content': 'Tiếng Việt\r\n'}}
        await worker.send(event)
        packet = await host.receive()
        self.assertEqual((packet['sequence'], packet['body']), (2, event))
        ack = {'type': 'engine_start_ack', **self.binding['identity']}
        await host.send(ack)
        self.assertEqual((await worker.receive())['body'], ack)

    async def test_eof_settles_uncancelled_reader_before_closed(self):
        host = self.owner(self.left, 'host')
        reader = asyncio.create_task(host.receive())
        while not host._tasks: await asyncio.sleep(0)
        observed = tuple(host._tasks)
        self.right.close()
        with self.assertRaises(channel.PrivateChannelError): await reader
        self.assertTrue(host.closed)
        self.assertTrue(observed)
        self.assertTrue(all(task.done() and not task.cancelled() for task in observed))

    async def test_partial_frame_deadline_poison_never_resynchronizes(self):
        host = self.owner(self.left, 'host')
        await asyncio.get_running_loop().sock_sendall(self.right, b'\x00\x00\x00\x64{')
        with self.assertRaises(channel.PrivateChannelError): await host.receive(timeout=.03)
        self.assertTrue(host.closed and host.poisoned)
        with self.assertRaises(channel.PrivateChannelError): await host.receive()

    async def test_repeated_cancellation_waits_for_owned_close_and_real_io_completion(self):
        host = self.owner(self.left, 'host')
        entered, release = asyncio.Event(), asyncio.Event()
        original = host._close_impl
        async def blocked():
            entered.set()
            await release.wait()
            await original()
        host._close_impl = blocked
        task = asyncio.create_task(host.receive())
        try:
            while not host._tasks: await asyncio.sleep(0)
            observed = tuple(host._tasks)
            task.cancel()
            await entered.wait()
            task.cancel()
            await asyncio.sleep(.01)
            self.assertFalse(task.done())
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertTrue(host.closed)
        self.assertTrue(observed)
        self.assertTrue(all(item.done() and not item.cancelled() for item in observed))

    async def test_preclose_failure_retains_live_socket_for_retry(self):
        host = self.owner(self.left, 'host')
        original = socket.socket.close
        def failed(sock):
            if sock is self.left: raise OSError('controlled preclose fault')
            return original(sock)
        with patch.object(socket.socket, 'close', failed):
            with self.assertRaises(channel.PrivateChannelCleanupError) as caught: await host.aclose()
        self.assertIs(caught.exception.owner, host)
        self.assertFalse(host.closed or host.close_authority_lost)
        self.assertGreaterEqual(self.left.fileno(), 0)
        await host.aclose()
        self.assertTrue(host.closed)

    async def test_postclose_error_retains_unknown_and_never_blindly_retries(self):
        host = self.owner(self.left, 'host')
        original, calls = socket.socket.close, []
        def failed(sock):
            if sock is self.left:
                calls.append(True); original(sock); raise OSError('controlled postclose fault')
            return original(sock)
        with patch.object(socket.socket, 'close', failed):
            for _ in range(2):
                with self.assertRaises(channel.PrivateChannelCleanupError): await host.aclose()
        self.assertEqual(len(calls), 1)
        self.assertFalse(host.closed)
        self.assertTrue(host.close_authority_lost)
        self.assertEqual(self.left.fileno(), -1)

    async def test_cancellation_after_successful_close_preserves_actual_cleanup_fact(self):
        host = self.owner(self.left, 'host')
        original = asyncio.shield
        async def cancelled_after_completion(task):
            await original(task)
            raise asyncio.CancelledError
        with patch.object(asyncio, 'shield', side_effect=cancelled_after_completion):
            with self.assertRaises(asyncio.CancelledError): await host.aclose()
        self.assertTrue(host.closed)
        self.assertNotIn(host, channel._RETAINED)

    async def test_receive_silence_uses_lifetime_not_short_send_timeout(self):
        host = channel.PrivateWorkerChannelV2(self.left, binding=self.binding, role='host',
            timeout=.02, close_timeout=.3, lifetime_timeout=1)
        self.owners.append(host)
        from improvement_native_protocol import encode_private_packet2
        packet = {'version': 2, 'sequence': 1, **{key: self.binding[key] for key in
            ('launch_nonce', 'worker_pid', 'worker_birth')}, 'body': {'type': 'endpoints_adopted'}}
        async def later():
            await asyncio.sleep(.06)
            await asyncio.get_running_loop().sock_sendall(self.right,
                encode_private_packet2(packet, binding=self.binding, direction='worker', expected_sequence=1))
        sender = asyncio.create_task(later())
        try: self.assertEqual(await host.receive(), packet)
        finally: await sender

    async def test_consumed_stream_does_not_retain_completed_plaintext_frames(self):
        host, worker = self.owner(self.left, 'host'), self.owner(self.right, 'worker')
        body = {'type': 'engine_event', **self.binding['identity'], 'event': {'type': 'observation', 'content': 'x' * 16384}}
        for _ in range(32):
            await worker.send(body)
            await host.receive()
        for owner in (host, worker):
            self.assertEqual(len(owner._tasks), 0, 'consumed completed results retained across stream')
            self.assertEqual(len(owner._buffers), 0, 'settled plaintext frame buffers retained across stream')


if __name__ == '__main__':
    unittest.main()
