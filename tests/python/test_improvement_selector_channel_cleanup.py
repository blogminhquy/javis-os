"""Real selector socket completion; stdlib only, no application state or children."""
import asyncio
from pathlib import Path
import socket
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'server'))

from improvement_image_channel import ImageMetadataChannel
from improvement_private_channel import PrivateWorkerChannelV2


@unittest.skipIf(sys.platform == 'win32', 'POSIX readiness semantics; Windows native qualification uses Proactor')
class SelectorChannelCleanupTests(unittest.IsolatedAsyncioTestCase):
    def _setupAsyncioRunner(self):
        # Exercise the actual public selector API without synthetic futures.
        self._asyncioRunner = asyncio.Runner(debug=True, loop_factory=asyncio.SelectorEventLoop)

    async def test_shutdown_settles_actual_pending_receive_before_descriptor_close(self):
        binding = {'kind': 'trial', 'launch_nonce': 'a' * 64, 'worker_pid': 123, 'worker_birth': 456,
            'identity': {'trial_id': 'trial-a', 'attempt': 1, 'input_hash': 'b' * 64},
            'invocations': [{'purpose': purpose, 'nonce': str(index + 1) * 64} for index, purpose in
                enumerate(('adapter_version', 'auth_status', 'sdk_version', 'query'))]}
        for kind in ('image', 'private'):
            with self.subTest(kind=kind):
                left, right = socket.socketpair()
                left.setblocking(False); right.setblocking(False)
                try:
                    if kind == 'image':
                        owner = ImageMetadataChannel(left, role='guardian', nonce='a' * 64,
                            worker_pid=123, worker_birth=456, timeout=1, close_timeout=.2)
                        operation = asyncio.create_task(owner.receive_create())
                        tasks = lambda: tuple(owner._io_tasks)
                    else:
                        owner = PrivateWorkerChannelV2(left, role='host', binding=binding,
                            timeout=1, close_timeout=.2, lifetime_timeout=2)
                        operation = asyncio.create_task(owner.receive())
                        tasks = lambda: tuple(owner._tasks)
                    while not tasks(): await asyncio.sleep(0)
                    observed = tasks()
                    await asyncio.sleep(.01)  # Actual sock_recv is registered, no peer data/EOF.
                    operation.cancel()
                    with self.assertRaises(asyncio.CancelledError): await operation
                    self.assertTrue(owner.closed)
                    self.assertEqual(left.fileno(), -1)
                    self.assertTrue(observed)
                    self.assertTrue(all(task.done() and not task.cancelled() for task in observed))
                finally:
                    try: right.shutdown(socket.SHUT_RDWR)
                    except OSError: pass
                    right.close()
                    # Even a failing assertion must not close a descriptor still
                    # registered by the actual reader under test.
                    remaining = {task for task in (operation, *tasks()) if not task.done()}
                    if remaining:
                        _, remaining = await asyncio.wait(remaining, timeout=1)
                    # Failure-only fixture drain; never part of the successful
                    # uncancelled-completion assertions above.
                    for raw in remaining: raw.cancel()
                    await asyncio.gather(operation, *tasks(), return_exceptions=True)
                    left.close()


if __name__ == '__main__': unittest.main()
