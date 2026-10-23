"""Isolated capture component; private cmd echo only, no SDK client or account."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import importlib
import importlib.util
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


def capture_class(test):
    test.assertIsNotNone(importlib.util.find_spec('improvement_native_capture'), 'canonical native capture missing')
    return importlib.import_module('improvement_native_capture').NativeDebugInvocation


async def unused_ack(frame):
    raise AssertionError('no process expected')


class NativeCaptureContractTests(unittest.TestCase):
    def test_invalid_contract_refuses_before_any_opener_call(self):
        cls = capture_class(self)
        async def forbidden(*args, **kwargs): raise AssertionError('no process expected')
        good = dict(purpose='sdk_version', nonce='a' * 64, validate_create=lambda args: True, image_ack=unused_ack)
        self.assertIsInstance(cls(forbidden, **good), cls)
        bad = [dict(purpose=''), dict(purpose='ambient'), dict(nonce='A' * 64), dict(nonce='a' * 63),
            dict(validate_create=None), dict(image_ack=lambda value: value), dict(spawn_timeout=True),
            dict(ack_timeout=math.inf), dict(drain_timeout=0), dict(spawn_timeout=-1)]
        for change in bad:
            with self.subTest(change=change), self.assertRaises((TypeError, ValueError)):
                cls(forbidden, **{**good, **change})


@unittest.skipUnless(os.name == 'nt' and sys.flags.isolated, 'actual Win32 capture requires isolated test driver')
class NativeCaptureWindowsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.cls = capture_class(self)
        from claude_agent_sdk._internal.transport import subprocess_cli
        self.sdk = subprocess_cli
        self.saved = subprocess_cli.anyio.open_process
        self.temp = tempfile.TemporaryDirectory(prefix='canonical-capture-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'home').mkdir()
        self.exe = self.root / 'owned cmd.exe'
        shutil.copyfile(Path(os.environ['SystemRoot']) / 'System32/cmd.exe', self.exe)
        self.command = [str(self.exe), '/d', '/c', 'echo OWNED_CAPTURE_MARKER']
        self.env = {'SystemRoot': 'C:\\Windows', 'WINDIR': 'C:\\Windows', 'PATH': 'C:\\Windows\\System32',
            'HOME': str(self.root / 'home'), 'USERPROFILE': str(self.root / 'home'),
            'TEMP': str(self.root), 'TMP': str(self.root)}
        self.frames = []

    def validate(self, args):
        self.assertEqual(len(args), 9)
        self.assertIn(args[0], (None, str(self.exe)))
        self.assertEqual(args[1], subprocess.list2cmdline(self.command))
        self.assertEqual(args[5], 0x08000006)
        self.assertEqual(args[6], self.env)
        self.assertEqual(args[7], str(self.root))
        return True

    def ack(self, frame, decision='allow'):
        self.frames.append(frame)
        self.assertEqual(set(frame), {'version', 'type', 'nonce', 'worker_pid', 'worker_birth', 'creator_thread',
            'native_pid', 'native_birth', 'native_tid', 'native_thread_birth', 'hfile', 'hprocess', 'hthread',
            'bootstrap_count', 'kill_on_exit'})
        return {'version': 1, 'type': 'native_image_ack', 'nonce': frame['nonce'],
            'worker_birth': frame['worker_birth'], 'native_birth': frame['native_birth'], 'decision': decision}

    def owner(self, image_ack=None, **kwargs):
        async def allow(frame): return self.ack(frame)
        return self.cls(self.saved, purpose='isolated_preflight', nonce='b' * 64,
            validate_create=self.validate, image_ack=image_ack or allow, **kwargs)

    async def launch(self, owner):
        return await owner.open_process(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=self.env, cwd=str(self.root))

    async def output(self, process):
        raw = bytearray()
        while True:
            try: raw.extend(await asyncio.wait_for(process.stdout.receive(65536), 3))
            except self.sdk.anyio.EndOfStream: return bytes(raw)

    async def test_selected_allow_returns_original_anyio_process_and_pumps_through_wait_and_aclose(self):
        async with self.owner() as owner:
            process = await self.launch(owner)
            self.assertIs(process, owner.process)
            self.assertIn(b'OWNED_CAPTURE_MARKER', await self.output(process))
            self.assertEqual(await asyncio.wait_for(process.wait(), 3), 0)
            await process.aclose()
        self.assertTrue(owner.terminal)
        self.assertEqual(owner.resume_counts, (1, 0, 1))
        self.assertEqual(owner.owned_handle_count, 0)

    async def test_deny_never_performs_allow_resume_and_drains(self):
        async def deny(frame): return self.ack(frame, 'deny')
        owner = self.owner(deny)
        with self.assertRaisesRegex(OSError, 'denied'):
            async with owner: await self.launch(owner)
        self.assertTrue(owner.terminal)
        self.assertEqual(owner.resume_counts, (1, None, None))
        self.assertEqual(owner.owned_handle_count, 0)

    async def test_malformed_ack_and_callback_exception_drain_without_private_error_text(self):
        async def malformed(frame): return {'private': 'SECRET_INPUT'}
        async def raises(frame): raise ValueError('SECRET_INPUT')
        async def eof(frame): raise EOFError('SECRET_INPUT')
        for callback in (malformed, raises, eof):
            owner = self.owner(callback)
            with self.subTest(callback=callback.__name__), self.assertRaises(OSError) as caught:
                async with owner: await self.launch(owner)
            self.assertNotIn('SECRET_INPUT', str(caught.exception))
            self.assertTrue(owner.terminal)
            self.assertEqual(owner.resume_counts[2], None)
            self.assertEqual(owner.owned_handle_count, 0)

    async def test_callback_native_error_cannot_leak_private_text(self):
        from improvement_native_capture import NativeCaptureError
        async def private_error(frame): raise NativeCaptureError('SECRET_NATIVE_PAYLOAD')
        owner = self.owner(private_error)
        with self.assertRaises(OSError) as caught:
            async with owner: await self.launch(owner)
        self.assertTrue(owner.terminal)
        self.assertEqual(owner.owned_handle_count, 0)
        self.assertNotIn('SECRET_NATIVE_PAYLOAD', str(caught.exception))

    async def test_ack_rejects_non_builtin_keys_and_values_before_allow(self):
        class Text(str): pass
        class Equal:
            def __eq__(self, other): return True
        changes = [('type', Text('native_image_ack')), ('nonce', Text('b' * 64)),
            ('decision', Text('allow')), ('nonce', Equal()), ('decision', Equal()), ('version', True), ('keys', None)]
        for key, value in changes:
            async def malformed(frame):
                ack = self.ack(frame)
                if key == 'keys': return {Text(name): item for name, item in ack.items()}
                ack[key] = value
                return ack
            owner = self.owner(malformed)
            with self.subTest(field=key, value_type=type(value).__name__):
                with self.assertRaises(OSError):
                    async with owner: await self.launch(owner)
                self.assertTrue(owner.terminal)
                self.assertIsNone(owner.resume_counts[2])
                self.assertEqual(owner.owned_handle_count, 0)

    async def test_ordinary_and_repeated_cancellation_drain_before_caller_returns(self):
        for repeated in (False, True):
            held = asyncio.Event()
            async def waiting(frame):
                self.ack(frame); held.set()
                await asyncio.Event().wait()
            owner = self.owner(waiting)
            async def run():
                async with owner: await self.launch(owner)
            task = asyncio.create_task(run())
            await asyncio.wait_for(held.wait(), 5)
            task.cancel()
            if repeated:
                for _ in range(8):
                    await asyncio.sleep(.001)
                    task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
            self.assertTrue(owner.terminal)
            self.assertEqual(owner.owned_handle_count, 0)

    async def test_before_create_validator_failure_does_not_create_or_leak_private_text(self):
        def refused(args): raise ValueError('SECRET_ENV')
        owner = self.owner()
        owner.validate_create = refused
        with self.assertRaises(OSError) as caught:
            async with owner: await self.launch(owner)
        self.assertNotIn('SECRET_ENV', str(caught.exception))
        self.assertEqual(owner.owned_handle_count, 0)
        self.assertFalse(owner.created)

    async def test_post_create_duplicate_failure_drains_raw_unreturned_handles(self):
        owner = self.owner()
        async with owner:
            original = owner._api.duplicate
            failed = False
            def duplicate(handle):
                nonlocal failed
                if not failed:
                    failed = True
                    raise OSError('injected duplicate failure')
                return original(handle)
            with patch.object(owner._api, 'duplicate', side_effect=duplicate):
                with self.assertRaises(OSError): await self.launch(owner)
        self.assertTrue(owner.created)
        self.assertTrue(owner.terminal)
        self.assertEqual(owner.owned_handle_count, 0)

    async def test_debug_read_failure_and_close_failure_retain_owner_until_retry(self):
        owner = self.owner()
        await owner.__aenter__()
        original = owner._api.next_event
        try:
            with patch.object(owner._api, 'next_event', side_effect=OSError('injected event failure')):
                with self.assertRaises(OSError) as caught: await self.launch(owner)
            self.assertIs(caught.exception.owner, owner)
            self.assertGreater(owner.owned_handle_count, 0)
            await owner.aclose()
            self.assertTrue(owner.terminal)
            self.assertEqual(owner.owned_handle_count, 0)
        finally: await owner.aclose()
        owner = self.owner()
        await owner.__aenter__()
        try:
            process = await self.launch(owner)
            await self.output(process)
            await process.wait()
            with patch.object(owner._api, 'close', side_effect=OSError('injected close failure')):
                with self.assertRaises(OSError) as caught: await owner.aclose()
            self.assertIs(caught.exception.owner, owner)
            self.assertGreater(owner.owned_handle_count, 0)
            await owner.aclose()
            self.assertEqual(owner.owned_handle_count, 0)
        finally: await owner.aclose()

    async def test_uncooperative_ack_is_retained_then_can_be_settled_and_retried(self):
        held, release = asyncio.Event(), asyncio.Event()
        async def stubborn(frame):
            self.ack(frame); held.set()
            while not release.is_set():
                try: await release.wait()
                except asyncio.CancelledError: pass
            return self.ack(frame, 'deny')
        owner = self.owner(stubborn, drain_timeout=.3)
        await owner.__aenter__()
        task = asyncio.create_task(self.launch(owner))
        try:
            await asyncio.wait_for(held.wait(), 5)
            task.cancel()
            with self.assertRaises(OSError) as caught: await task
            self.assertIs(caught.exception.owner, owner)
            self.assertTrue(owner.terminal)
            self.assertFalse(owner._ack_task.done())
            release.set()
            await owner.aclose()
            self.assertEqual(owner.owned_handle_count, 0)
        finally:
            release.set()
            await owner.aclose()


if __name__ == '__main__': unittest.main()
