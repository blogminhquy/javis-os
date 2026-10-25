"""Bounded read-only CLI observations; synthetic files, no native/model calls."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import hashlib
import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import improvement_trial_selection as selection
import improvement_claude as native
import test_improvement_trial_selection as fixtures


class BinaryObservationTests(unittest.TestCase):
    setUp = fixtures.SelectionTests.setUp
    write = fixtures.SelectionTests.write
    pin = fixtures.SelectionTests.pin

    def bounded(self, function):
        decorator = getattr(selection, '_bounded_binary_reads', None)
        self.assertTrue(callable(decorator), 'Bounded fresh CLI observation is absent')
        return decorator(function)

    def reads(self, spy):
        return [call for call in spy.call_args_list if call.kwargs.get('digest')
                and call.args[0] == self.binary]

    def test_twelve_pins_use_two_full_reads_but_all_settings_sdk_and_profile_checks(self):
        @self.bounded
        def load():
            return [self.pin() for _ in range(12)]

        with patch.object(selection, '_read_stable', wraps=selection._read_stable) as read:
            pins = load()
            self.assertEqual(len(self.reads(read)), 2)
            self.assertEqual(pins, [pins[0]] * 12)
            self.assertEqual(native.profile_hash.call_count, 24)
            self.assertEqual(selection.importlib.metadata.version.call_count, 24)
            load()
            self.assertEqual(len(self.reads(read)), 4, 'No cache across view resolutions')

    def test_metadata_restored_same_size_edit_is_refused_by_final_full_byte_read(self):
        identity, old = selection._identity, self.binary.stat()
        original = identity(old)

        def unchanged_metadata(info):
            return original if info.st_ino == old.st_ino else identity(info)

        @self.bounded
        def load():
            self.pin()
            self.pin()
            raw = self.binary.read_bytes()
            self.binary.write_bytes(b'X' + raw[1:])
            os.utime(self.binary, ns=(old.st_atime_ns, old.st_mtime_ns))
            return 'must not escape'

        with patch.object(selection, '_identity', side_effect=unchanged_metadata), \
                patch.object(selection, '_read_stable', wraps=selection._read_stable) as read, \
                self.assertRaisesRegex(ValueError, 'source_changed'):
            load()
        self.assertEqual(len(self.reads(read)), 2)

    def test_permission_denial_on_a_memo_hit_is_not_hidden_until_scope_exit(self):
        real_open = selection.os.open

        def denied(path, *args, **kwargs):
            if path == self.binary:
                raise PermissionError('Synthetic read revocation')
            return real_open(path, *args, **kwargs)

        @self.bounded
        def load():
            self.pin()
            with patch.object(selection.os, 'open', side_effect=denied):
                self.pin()
            self.fail('A pin must not escape the permission denial')

        with self.assertRaisesRegex(ValueError, 'source_unavailable'):
            load()

    def test_memo_hit_reopens_and_checks_actual_descriptor_without_reading_body(self):
        @self.bounded
        def load():
            self.pin()
            with patch.object(selection.os, 'fstat', wraps=selection.os.fstat) as fstat:
                self.pin()
                self.assertGreaterEqual(fstat.call_count, 6)  # settings twice plus binary

        with patch.object(selection, '_read_stable', wraps=selection._read_stable) as read:
            load()
        self.assertEqual(len(self.reads(read)), 2)

    def test_settings_and_profile_are_not_memoized_with_the_binary_digest(self):
        @self.bounded
        def load():
            first = self.pin()
            self.config['model']['main']['model'] = 'new-owner-selected-model'
            self.write()
            native.profile_hash.return_value = 'c' * 64
            second = self.pin()
            self.assertNotEqual(first['model'], second['model'])
            self.assertEqual(second['profile_hash'], 'c' * 64)
            with patch.object(selection.importlib.metadata, 'version', return_value='unverified-sdk'), \
                    self.assertRaisesRegex(ValueError, 'runtime_unverified'):
                self.pin()

        load()

    def test_other_digest_sources_are_always_fresh_inside_the_scope(self):
        source = self.root / 'source.py'
        source.write_bytes(b'first source')

        @self.bounded
        def load():
            self.pin()
            first = selection._read_stable(source, 1024, digest=True)[0]
            source.write_bytes(b'other source')
            second = selection._read_stable(source, 1024, digest=True)[0]
            self.assertNotEqual(first, second)
            self.assertEqual(second, hashlib.sha256(b'other source').hexdigest())

        load()

    def test_exception_and_cancellation_discard_memo_without_masking_the_error(self):
        for error in (RuntimeError('original failure'), asyncio.CancelledError()):
            @self.bounded
            def fail():
                self.pin()
                raise error

            with patch.object(selection, '_read_stable', wraps=selection._read_stable) as read:
                with self.assertRaises(type(error)) as caught:
                    fail()
                self.assertIs(caught.exception, error)
                self.pin()
                self.assertEqual(len(self.reads(read)), 2)

    def test_thread_scopes_cannot_reuse_another_threads_digest(self):
        gate = threading.Barrier(2)
        real_read, reads, lock = selection._read_stable, {}, threading.Lock()

        def tracked(path, *args, **kwargs):
            if path == self.binary and kwargs.get('digest'):
                with lock:
                    ident = threading.get_ident()
                    reads[ident] = reads.get(ident, 0) + 1
            return real_read(path, *args, **kwargs)

        @self.bounded
        def load(_):
            self.pin()
            gate.wait(timeout=10)
            return [self.pin() for _ in range(11)]

        with patch.object(selection, '_read_stable', side_effect=tracked), ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(load, (1, 2)))
        self.assertEqual(sorted(reads.values()), [2, 2])
        self.assertEqual(results[0], results[1])

    def test_replaced_and_missing_paths_cannot_reuse_a_memo(self):
        @self.bounded
        def replaced():
            self.pin()
            other = self.binary.with_name('replacement.exe')
            other.write_bytes(self.binary.read_bytes())
            other.replace(self.binary)
            self.pin()

        with self.assertRaisesRegex(ValueError, 'source_changed'):
            replaced()

        @self.bounded
        def missing():
            self.pin()
            self.binary.unlink()
            self.pin()

        with self.assertRaisesRegex(ValueError, 'source_unavailable'):
            missing()

    def test_nested_scope_refuses_and_does_not_leak_the_outer_memo(self):
        @self.bounded
        def inner():
            self.pin()

        @self.bounded
        def outer():
            self.pin()
            inner()

        with self.assertRaisesRegex(ValueError, 'observation_nested'):
            outer()
        self.pin()

    def test_async_and_generator_functions_cannot_escape_the_sync_boundary(self):
        async def asynchronous():
            self.pin()

        def generator():
            yield self.pin()

        async def asynchronous_generator():
            yield self.pin()

        for function in (asynchronous, generator, asynchronous_generator):
            with self.assertRaisesRegex(TypeError, 'requires_sync'):
                self.bounded(function)


if __name__ == '__main__':
    unittest.main()
