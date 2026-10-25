"""Real Windows executable-file guards; own files, no CLI/model/account execution."""
from _paths import ROOT, SERVER  # noqa: F401

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.name == 'nt', 'Windows native file sharing')
class NativeImageGuardTests(unittest.TestCase):
    def setUp(self):
        import improvement_native_image as image
        self.image = image
        self.temp = tempfile.TemporaryDirectory(prefix='image-guard-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / 'parent' / 'selected.exe'
        self.path.parent.mkdir()
        self.path.write_bytes(b'OWNED_INERT_BYTES')
        self.digest = hashlib.sha256(self.path.read_bytes()).hexdigest()

    def guard(self, digest=None):
        return self.image.ImageReadGuard(self.path, digest or self.digest)

    def junction(self, path, target):
        self.assertTrue(path.is_relative_to(self.root) and target.is_relative_to(self.root))
        process = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(path), str(target)],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertTrue(path.is_junction())

    def test_exact_bytes_are_held_until_close_then_writer_can_succeed(self):
        with self.guard() as guard:
            self.assertEqual(guard.snapshot()['sha256'], self.digest)
            self.assertEqual(guard.snapshot()['filesystem'], 'NTFS')
            with self.assertRaises(PermissionError):
                self.path.write_bytes(b'CHANGED')
        self.path.write_bytes(b'CHANGED')
        guard.close()
        with self.assertRaisesRegex(ValueError, 'closed'):
            guard.snapshot()

    def test_replacement_and_ancestor_rename_are_denied_then_released(self):
        replacement = self.root / 'replacement.exe'
        replacement.write_bytes(b'REPLACEMENT')
        renamed = self.root / 'renamed'
        with self.guard():
            with self.assertRaises(PermissionError):
                os.replace(replacement, self.path)
            with self.assertRaises(PermissionError):
                self.path.parent.rename(renamed)
        self.path.parent.rename(renamed)
        os.replace(replacement, renamed / self.path.name)

    def test_hash_mismatch_closes_every_guard_before_returning_error(self):
        with self.assertRaisesRegex(ValueError, 'hash'):
            self.guard('0' * 64)
        self.path.parent.rename(self.root / 'released')
        self.root.rename(self.root.with_name(self.root.name + '-released'))
        self.root.with_name(self.root.name + '-released').rename(self.root)

    def test_preexisting_file_writer_refuses_guard_without_leaking_ancestors(self):
        with self.path.open('r+b'):
            with self.assertRaises(OSError):
                self.guard()
        self.path.parent.rename(self.root / 'released')

    def test_existing_junction_ancestor_is_refused_even_for_exact_bytes(self):
        real = self.root / 'real'
        self.path.parent.rename(real)
        self.junction(self.path.parent, real)
        try:
            with self.assertRaisesRegex(ValueError, 'reparse'):
                self.guard()
        finally:
            os.rmdir(self.path.parent)
            real.rename(self.path.parent)

    def test_ancestor_guards_block_a_swap_during_later_component_acquisition(self):
        original = self.image._open
        parent, held = self.path.parent, self.root / 'held'
        state = {'attempted': False, 'blocked': False}

        def changed(path):
            if Path(path) == parent and not state['attempted']:
                state['attempted'] = True
                try:
                    parent.rename(held)
                except PermissionError:
                    state['blocked'] = True
                else:
                    held.rename(parent)
            return original(path)

        with patch.object(self.image, '_open', side_effect=changed), self.guard():
            self.assertEqual(state, {'attempted': True, 'blocked': True})
        parent.rename(held)  # Same attack becomes possible after ownership ends.
        held.rename(parent)

    def test_swap_before_first_handle_is_detected_on_actual_reparse_handle(self):
        original = self.image._open
        parent, held = self.path.parent, self.root / 'held'
        state = {'swapped': False}

        def changed(path):
            if not state['swapped']:
                parent.rename(held)
                self.junction(parent, held)
                state['swapped'] = True
            return original(path)

        try:
            with patch.object(self.image, '_open', side_effect=changed), \
                    self.assertRaisesRegex(ValueError, 'reparse'):
                self.guard()
        finally:
            if state['swapped']:
                os.rmdir(parent)
                held.rename(parent)

    def test_hash_reads_the_retained_handle_instead_of_reopening_a_path(self):
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('Path hash is not retained-handle proof')):
            with self.guard() as guard:
                self.assertEqual(guard.snapshot()['sha256'], self.digest)

    def test_failed_close_retains_ownership_for_a_successful_retry(self):
        guard = self.guard()
        with patch.object(self.image, '_close', side_effect=OSError('controlled_close_failure')):
            with self.assertRaisesRegex(OSError, 'controlled_close_failure'):
                guard.close()
        self.assertFalse(guard._closed)
        self.assertTrue(guard._handles)
        with self.assertRaises(PermissionError):
            self.path.write_bytes(b'CHANGED')
        guard.close()
        self.path.write_bytes(b'CHANGED')

    def test_partial_close_cannot_return_a_guarded_snapshot(self):
        guard, original = self.guard(), self.image._close
        calls = []

        def partial(handle):
            calls.append(handle)
            if len(calls) == 2:
                raise OSError('controlled_partial_close')
            return original(handle)

        try:
            with patch.object(self.image, '_close', side_effect=partial):
                with self.assertRaisesRegex(OSError, 'controlled_partial_close'):
                    guard.close()
            self.path.write_bytes(b'NO_LONGER_GUARDED')
            with self.assertRaisesRegex(ValueError, 'closed|closing'):
                guard.snapshot()
        finally:
            guard.close()

    def test_closed_guard_cannot_be_reentered_as_an_owned_context(self):
        guard = self.guard()
        guard.close()
        with self.assertRaisesRegex(ValueError, 'closed'):
            with guard:
                self.fail('A closed guard cannot claim an active ownership scope')

    def test_entry_failure_releases_handles_without_requiring_an_exit_call(self):
        import stat
        guard = self.guard()
        try:
            self.path.chmod(stat.S_IREAD)
            with self.assertRaisesRegex(ValueError, 'identity'):
                with guard:
                    self.fail('Drift must refuse entry')
            self.path.chmod(stat.S_IREAD | stat.S_IWRITE)
            self.path.write_bytes(b'RELEASED')
        finally:
            self.path.chmod(stat.S_IREAD | stat.S_IWRITE)
            guard.close()

    def test_entry_cleanup_failure_retains_guard_on_exception_for_retry(self):
        import stat
        guard = self.guard()
        try:
            self.path.chmod(stat.S_IREAD)
            with patch.object(self.image, '_close', side_effect=OSError('entry_cleanup_failed')):
                with self.assertRaisesRegex(OSError, 'entry_cleanup_failed') as caught:
                    with guard:
                        self.fail('Drift must refuse entry')
            self.assertIs(caught.exception.guard, guard)
        finally:
            self.path.chmod(stat.S_IREAD | stat.S_IWRITE)
            guard.close()

    def test_exit_cleanup_failure_retains_guard_on_exception_for_retry(self):
        guard = self.guard()
        try:
            with patch.object(self.image, '_close', side_effect=OSError('exit_cleanup_failed')):
                with self.assertRaisesRegex(OSError, 'exit_cleanup_failed') as caught:
                    with guard:
                        pass
            self.assertIs(caught.exception.guard, guard)
        finally:
            guard.close()

    def test_snapshot_detects_metadata_drift_but_does_not_claim_mutation_exclusion(self):
        import stat
        with self.guard() as guard:
            try:
                self.path.chmod(stat.S_IREAD)
                with self.assertRaisesRegex(ValueError, 'identity'):
                    guard.snapshot()
            finally:
                self.path.chmod(stat.S_IREAD | stat.S_IWRITE)
            self.assertEqual(guard.snapshot()['metadata_mutation_exclusion'], 'unknown')
            self.assertEqual(guard.snapshot()['loaded_image_identity'], 'unknown')

    def test_other_child_file_writes_still_work_during_guard(self):
        unrelated = self.path.parent / 'other.bin'
        with self.guard():
            unrelated.write_bytes(b'UNRELATED')
            unrelated.unlink()
            self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), self.digest)

    def test_leaf_junction_or_directory_cannot_masquerade_as_executable(self):
        self.path.unlink()
        self.path.mkdir()
        with self.assertRaisesRegex(ValueError, 'kind'):
            self.guard()


@unittest.skipUnless(os.name == 'nt', 'Windows borrowed file objects')
class NativeBorrowedFileComparisonTests(unittest.TestCase):
    setUp = NativeImageGuardTests.setUp
    guard = NativeImageGuardTests.guard

    def compare(self, guard, handle):
        self.assertTrue(callable(getattr(guard, 'compare_file_handle', None)), 'public borrowed-handle comparison missing')
        return guard.compare_file_handle(handle)

    def borrowed(self, path=None):
        import msvcrt
        stream = open(path or self.path, 'rb', buffering=0)
        self.addCleanup(stream.close)
        return stream, msvcrt.get_osfhandle(stream.fileno())

    def test_matching_real_handle_has_closed_defensive_metadata_and_preserves_cursor(self):
        stream, handle = self.borrowed()
        stream.seek(7)
        with self.guard() as guard:
            with patch.object(Path, 'read_bytes', side_effect=AssertionError('comparison must not reopen bytes')):
                value = self.compare(guard, handle)
            self.assertEqual(set(value), {'matches', 'selected', 'actual', 'proof_basis',
                'metadata_mutation_exclusion', 'debug_event_origin', 'loaded_image_identity', 'comprehension'})
            self.assertIs(value['matches'], True)
            for item in (value['selected'], value['actual']):
                self.assertEqual(set(item), {'volume_serial_64', 'file_id_128', 'sha256', 'size'})
                self.assertIs(type(item['volume_serial_64']), int)
                self.assertRegex(item['file_id_128'], '^[0-9a-f]{32}$')
                self.assertEqual(item['sha256'], self.digest)
                self.assertEqual(item['size'], 17)
            self.assertEqual(value['proof_basis'], 'observed_borrowed_file_identity_and_reopened_sha256')
            for key in ('metadata_mutation_exclusion', 'debug_event_origin', 'loaded_image_identity', 'comprehension'):
                self.assertEqual(value[key], 'unknown')
            value['selected']['sha256'] = 'changed'
            value['actual']['file_id_128'] = 'changed'
            self.assertTrue(self.compare(guard, handle)['matches'])
        self.assertEqual(stream.tell(), 7)
        self.assertEqual(stream.read(), b'NERT_BYTES')

    def test_identical_bytes_in_foreign_file_do_not_match(self):
        foreign = self.root / 'foreign.exe'
        foreign.write_bytes(b'OWNED_INERT_BYTES')
        _, handle = self.borrowed(foreign)
        with self.guard() as guard:
            value = self.compare(guard, handle)
        self.assertFalse(value['matches'])
        self.assertEqual(value['actual']['sha256'], self.digest)
        self.assertNotEqual(value['actual']['file_id_128'], value['selected']['file_id_128'])

    def test_different_bytes_do_not_match(self):
        foreign = self.root / 'foreign.exe'
        foreign.write_bytes(b'DIFFERENT')
        _, handle = self.borrowed(foreign)
        with self.guard() as guard:
            value = self.compare(guard, handle)
        self.assertFalse(value['matches'])
        self.assertEqual(value['actual']['sha256'], hashlib.sha256(b'DIFFERENT').hexdigest())
        self.assertEqual(value['actual']['size'], 9)

    def test_closed_and_partially_closed_guards_refuse_comparison(self):
        _, handle = self.borrowed()
        guard = self.guard()
        guard.close()
        with self.assertRaisesRegex(ValueError, 'closed'):
            self.compare(guard, handle)
        guard = self.guard()
        try:
            with patch.object(self.image, '_close', side_effect=OSError('close failed')):
                with self.assertRaises(OSError): guard.close()
            with self.assertRaisesRegex(ValueError, 'closed'):
                self.compare(guard, handle)
        finally: guard.close()

    def test_invalid_numeric_and_closed_handles_refuse_before_read(self):
        import ctypes
        stream, closed = self.borrowed()
        stream.close()
        with self.guard() as guard, patch.object(self.image._kernel(), 'ReadFile', side_effect=AssertionError('unsafe read')):
            for handle in (True, False, 0, -1, None, '123', 1 << 100, ctypes.c_void_p(-1).value, closed):
                with self.subTest(handle=handle), self.assertRaises((ValueError, OSError)):
                    self.compare(guard, handle)

    def test_pipe_and_character_handles_refuse_before_read(self):
        import msvcrt
        read_fd, write_fd = os.pipe()
        self.addCleanup(os.close, write_fd)
        self.addCleanup(os.close, read_fd)
        nul = open('NUL', 'rb', buffering=0)
        self.addCleanup(nul.close)
        with self.guard() as guard, patch.object(self.image._kernel(), 'ReadFile', side_effect=AssertionError('unsafe read')):
            for handle in (msvcrt.get_osfhandle(read_fd), msvcrt.get_osfhandle(nul.fileno())):
                with self.subTest(handle=handle), self.assertRaisesRegex(ValueError, 'kind'):
                    self.compare(guard, handle)

    def test_directory_and_reparse_metadata_refuse_before_read(self):
        handle = self.image._open(self.path.parent)
        self.addCleanup(self.image._close, handle)
        with self.guard() as guard, patch.object(self.image._kernel(), 'ReadFile', side_effect=AssertionError('unsafe read')):
            with self.assertRaisesRegex(ValueError, 'kind'):
                self.compare(guard, handle)
        _, handle = self.borrowed()
        original = self.image._info
        def reparse(h):
            value = original(h)
            if h == handle: value.attributes |= 0x400
            return value
        with self.guard() as guard, patch.object(self.image, '_info', side_effect=reparse), \
                patch.object(self.image._kernel(), 'ReadFile', side_effect=AssertionError('unsafe read')):
            with self.assertRaisesRegex(ValueError, 'reparse|kind'):
                self.compare(guard, handle)

    def test_metadata_only_disk_handle_refuses_before_read(self):
        kernel = self.image._kernel()
        with self.guard() as guard:
            handle = kernel.CreateFileW(str(self.path), 0x80, 1, None, 3, 0x02200000, None)
            self.addCleanup(self.image._close, handle)
            with patch.object(kernel, 'ReadFile', side_effect=AssertionError('unsafe read')), \
                    patch.object(kernel, 'ReOpenFile', side_effect=AssertionError('must refuse before reopening')):
                with self.assertRaisesRegex((ValueError, OSError), 'read'):
                    self.compare(guard, handle)

    def test_async_borrowed_handle_is_never_used_for_read(self):
        kernel = self.image._kernel()
        with self.guard() as guard:
            handle = kernel.CreateFileW(str(self.path), 0x80000000, 1, None, 3, 0x42200000, None)
            self.addCleanup(self.image._close, handle)
            original = kernel.ReadFile
            def safe(h, *args):
                if h == handle: raise AssertionError('async borrowed read is unsafe')
                return original(h, *args)
            with patch.object(kernel, 'ReadFile', side_effect=safe):
                self.assertTrue(self.compare(guard, handle)['matches'])

    def test_empty_and_oversize_disk_files_refuse_before_read(self):
        for size in (0, 512 * 1024 * 1024 + 1):
            path = self.root / ('size-%d.bin' % size)
            with path.open('wb') as stream: stream.truncate(size)
            _, handle = self.borrowed(path)
            with self.guard() as guard, patch.object(self.image._kernel(), 'ReadFile', side_effect=AssertionError('unsafe read')):
                with self.subTest(size=size), self.assertRaisesRegex(ValueError, 'size'):
                    self.compare(guard, handle)

    def test_read_failure_restores_cursor_and_keeps_caller_handle(self):
        import ctypes
        stream, handle = self.borrowed()
        stream.seek(4)
        def failed(*args):
            ctypes.set_last_error(5)
            return 0
        with self.guard() as guard, patch.object(self.image._kernel(), 'ReadFile', side_effect=failed):
            with self.assertRaises(OSError): self.compare(guard, handle)
        self.assertEqual(stream.tell(), 4)
        self.assertEqual(stream.read(), b'D_INERT_BYTES')

    def test_private_reader_seek_failure_cannot_return_attestation_or_move_borrowed_cursor(self):
        import ctypes
        stream, handle = self.borrowed()
        stream.seek(7)
        with self.guard() as guard:
            kernel = self.image._kernel()
            original = kernel.SetFilePointerEx
            def unseekable(h, *args):
                self.assertNotEqual(h, handle, 'borrowed cursor must never be queried or changed')
                ctypes.set_last_error(1)
                return 0
            with patch.object(kernel, 'SetFilePointerEx', side_effect=unseekable), \
                    patch.object(kernel, 'ReadFile', side_effect=AssertionError('unsafe read')):
                with self.assertRaises(OSError): self.compare(guard, handle)
        self.assertFalse(stream.closed)
        self.assertEqual(stream.tell(), 7)

    def test_actual_metadata_drift_during_read_refuses_and_restores_cursor(self):
        import stat
        foreign = self.root / 'foreign.exe'
        foreign.write_bytes(b'OWNED_INERT_BYTES')
        stream, handle = self.borrowed(foreign)
        stream.seek(3)
        kernel = self.image._kernel()
        original = kernel.ReadFile
        def drift(h, *args):
            value = original(h, *args)
            foreign.chmod(stat.S_IREAD)
            return value
        try:
            with self.guard() as guard, patch.object(kernel, 'ReadFile', side_effect=drift):
                with self.assertRaisesRegex(ValueError, 'changed'): self.compare(guard, handle)
            self.assertEqual(stream.tell(), 3)
        finally: foreign.chmod(stat.S_IREAD | stat.S_IWRITE)

    def test_guard_metadata_drift_before_or_during_comparison_refuses(self):
        import stat
        foreign = self.root / 'foreign.exe'
        foreign.write_bytes(b'OWNED_INERT_BYTES')
        _, handle = self.borrowed(foreign)
        kernel = self.image._kernel()
        original = kernel.ReadFile
        def drift(h, *args):
            value = original(h, *args)
            self.path.chmod(stat.S_IREAD)
            return value
        with self.guard() as guard:
            try:
                self.path.chmod(stat.S_IREAD)
                with self.assertRaisesRegex(ValueError, 'changed'): self.compare(guard, handle)
                self.path.chmod(stat.S_IREAD | stat.S_IWRITE)
                with patch.object(kernel, 'ReadFile', side_effect=drift):
                    with self.assertRaisesRegex(ValueError, 'changed'): self.compare(guard, handle)
            finally: self.path.chmod(stat.S_IREAD | stat.S_IWRITE)

    def test_private_reader_failed_close_retains_retryable_guard_ownership(self):
        stream, handle = self.borrowed()
        guard = self.guard()
        failed = []
        def close_failed(h):
            failed.append(h)
            raise OSError('private_reader_close_failed')
        try:
            with patch.object(self.image, '_close', side_effect=close_failed):
                with self.assertRaisesRegex(OSError, 'private_reader_close_failed') as caught:
                    self.compare(guard, handle)
            self.assertIs(caught.exception.guard, guard)
            self.assertEqual(len(failed), 1)
            self.assertNotEqual(failed[0], handle)
            with self.assertRaisesRegex(ValueError, 'closed|closing'):
                self.compare(guard, handle)
            guard.close()
            self.assertEqual(stream.read(), b'OWNED_INERT_BYTES')
        finally: guard.close()

    def test_granted_access_query_failure_refuses_without_reopening(self):
        _, handle = self.borrowed()
        with self.guard() as guard, \
                patch.object(self.image._objects(), 'NtQueryObject', return_value=0x103), \
                patch.object(self.image._kernel(), 'ReOpenFile', side_effect=AssertionError('unsafe reopen')):
            with self.assertRaises(OSError): self.compare(guard, handle)

    def test_reopen_failure_preserves_caller_and_guard(self):
        import ctypes
        stream, handle = self.borrowed()
        def failed(*args):
            ctypes.set_last_error(5)
            return ctypes.c_void_p(-1).value
        with self.guard() as guard:
            with patch.object(self.image._kernel(), 'ReOpenFile', side_effect=failed):
                with self.assertRaises(OSError): self.compare(guard, handle)
            self.assertTrue(self.compare(guard, handle)['matches'])
        self.assertEqual(stream.read(), b'OWNED_INERT_BYTES')

    def test_file_id_and_post_read_metadata_failures_cannot_attest(self):
        stream, handle = self.borrowed()
        stream.seek(5)
        kernel = self.image._kernel()
        with self.guard() as guard:
            with patch.object(kernel, 'GetFileInformationByHandleEx', return_value=0):
                with self.assertRaises(OSError): self.compare(guard, handle)
            original_read, original_info = kernel.ReadFile, self.image._info
            state = {'read': False}
            def read(*args):
                state['read'] = True
                return original_read(*args)
            def info(h):
                if h == handle and state['read']: raise OSError('post_read_metadata_failed')
                return original_info(h)
            with patch.object(kernel, 'ReadFile', side_effect=read), patch.object(self.image, '_info', side_effect=info):
                with self.assertRaisesRegex(OSError, 'post_read_metadata_failed'): self.compare(guard, handle)
        self.assertEqual(stream.tell(), 5)


if __name__ == '__main__':
    unittest.main()
