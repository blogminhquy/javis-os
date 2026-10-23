"""Fixed factory engineering fixtures only; no SDK, CLI or account execution."""
from _paths import ROOT, SERVER  # noqa: F401

import ctypes
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


def component(test):
    test.assertIsNotNone(importlib.util.find_spec('improvement_fixed_worker_launch'), 'fixed worker factory missing')
    return importlib.import_module('improvement_fixed_worker_launch')


def policy():
    pin = {'path': r'C:\Python\python.exe', 'sha256': 'a' * 64, 'volume_serial_64': 1, 'file_id_128': 'b' * 32}
    return {'version': 1, 'scratch': r'C:\scratch', 'bootstrap': {
        'version': 1, 'entrypoint': 'trial', 'runtime': {'executable': pin, 'dll': {**pin, 'path': r'C:\Python\python313.dll'}},
        'source': {'root': r'C:\source', 'files': {'improvement_native_bootstrap.py': 'c' * 64,
            'improvement_native_image.py': 'd' * 64, 'improvement_worker.py': 'e' * 64}},
        'imports': {'site_packages': r'C:\packages', 'files': {}}}}


class FixedWorkerContractTests(unittest.TestCase):
    def test_closed_policy_and_borrowed_capabilities_are_defensively_copied(self):
        mod = component(self)
        value, stdio = policy(), {'stdin': 11, 'stdout': 12, 'stderr': 13}
        owner = mod.FixedWorkerLaunch(value, job_handle=10, stdio=stdio)
        value['bootstrap']['entrypoint'] = 'operation'
        stdio['stdin'] = 99
        self.assertFalse(owner.created)
        self.assertIsNone(owner.capabilities)
        self.assertFalse(owner.temporary_duplicates_closed)
        owner.close()
        with self.assertRaises((ValueError, OSError)):
            owner.launch()

    def test_version_types_extra_authority_and_arbitrary_dispatch_refuse(self):
        mod = component(self)
        changes = [{'version': True}, {'version': 2}, {'argv': ['other.py']}, {'env': {'TOKEN': 'private'}},
                   {'model': 'private'}, {'cwd': r'C:\elsewhere'}, {'parent_process': 20}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError)):
                mod.FixedWorkerLaunch({**policy(), **change}, job_handle=10, stdio={'stdin': 11, 'stdout': 12, 'stderr': 13})
        for entry in ('guardian', 'other', True):
            value = policy()
            value['bootstrap']['entrypoint'] = entry
            with self.subTest(entry=entry), self.assertRaises((ValueError, TypeError)):
                mod.FixedWorkerLaunch(value, job_handle=10, stdio={'stdin': 11, 'stdout': 12, 'stderr': 13})

    def test_pin_paths_hashes_and_builtin_only_contract_refuse(self):
        mod = component(self)
        class Text(str): pass
        for path in ('relative', r'\\server\share\file', r'C:\source\..\evil', 'C:\\bad\x00x', 'C:\\bad\ud800', r'C:\source:stream'):
            value = policy()
            value['bootstrap']['source']['root'] = path
            with self.subTest(path=repr(path)), self.assertRaises((ValueError, TypeError)):
                mod.FixedWorkerLaunch(value, job_handle=10, stdio={'stdin': 11, 'stdout': 12, 'stderr': 13})
        for mutation in ('hash', 'identity', 'subclass'):
            value = policy()
            if mutation == 'hash': value['bootstrap']['source']['files']['improvement_worker.py'] = 'X' * 64
            elif mutation == 'identity': value['bootstrap']['runtime']['dll']['volume_serial_64'] = True
            else: value['scratch'] = Text(value['scratch'])
            with self.subTest(mutation=mutation), self.assertRaises((ValueError, TypeError)):
                mod.FixedWorkerLaunch(value, job_handle=10, stdio={'stdin': 11, 'stdout': 12, 'stderr': 13})

    def test_metadata_job_stdio_aliases_nonhandles_and_extra_roles_refuse(self):
        mod = component(self)
        for stdio in ({'stdin': 11, 'stdout': 12}, {'stdin': 11, 'stdout': 12, 'stderr': 13, 'control': 14},
                      {'stdin': True, 'stdout': 12, 'stderr': 13}, {'stdin': 11, 'stdout': 11, 'stderr': 13},
                      {'stdin': 10, 'stdout': 12, 'stderr': 13}, {'stdin': -1, 'stdout': 12, 'stderr': 13}):
            with self.subTest(stdio=stdio), self.assertRaises((ValueError, TypeError)):
                mod.FixedWorkerLaunch(policy(), job_handle=10, stdio=stdio)
        for metadata in ({'read': 14}, {'socket': 15}, [], True):
            with self.subTest(metadata=metadata), self.assertRaises((ValueError, TypeError)):
                mod.FixedWorkerLaunch(policy(), job_handle=10, stdio={'stdin': 11, 'stdout': 12, 'stderr': 13}, metadata=metadata)

    @unittest.skipIf(os.name == 'nt', 'Linux import/refusal contract')
    def test_linux_import_is_safe_and_launch_refuses_explicitly(self):
        mod = component(self)
        owner = mod.FixedWorkerLaunch(policy(), job_handle=10, stdio={'stdin': 11, 'stdout': 12, 'stderr': 13})
        with self.assertRaises(OSError): owner.launch()
        owner.close()


@unittest.skipUnless(os.name == 'nt', 'Actual Windows CreateProcessW/JOB_LIST engineering fixture')
class FixedWorkerWindowsTests(unittest.TestCase):
    def setUp(self):
        self.mod = component(self)
        from improvement_native_capture_win32 import backend
        self.debug = backend()
        self.api = self.mod._backend()
        from improvement_native_bootstrap import _runtime_paths
        import improvement_native_image as image
        import msvcrt
        self.image, self.msvcrt = image, msvcrt
        short = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'Temp'
        self.temp = tempfile.TemporaryDirectory(prefix='jf-', dir=short)
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        source, packages = self.root / 's', self.root / 'p'
        source.mkdir(); packages.mkdir()
        (self.root / 'scratch').mkdir()
        self.marker = source / 'marker.json'
        # A fixed-name engineering stub, not the genuine qualified bootstrap or SDK worker.
        stub = '''import ctypes,json,os,sys
k=ctypes.WinDLL('kernel32',use_last_error=True)
k.QueryInformationJobObject.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p,ctypes.c_ulong,ctypes.c_void_p]
k.QueryInformationJobObject.restype=ctypes.c_int
k.GetNamedPipeInfo.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p]
k.GetNamedPipeInfo.restype=ctypes.c_int
accounting=ctypes.create_string_buffer(48)
probe=[bool(k.QueryInformationJobObject(EXPECT_ABSENT[0],1,accounting,len(accounting),None)),
 bool(k.GetNamedPipeInfo(EXPECT_ABSENT[1],None,None,None,None))]
value={'isolated':sys.flags.isolated,'no_site':sys.flags.no_site,'no_bytecode':sys.dont_write_bytecode,
 'site_loaded':'site' in sys.modules,'cwd':os.getcwd(),'home':os.environ.get('HOME'),
 'private':os.environ.get('FIXED_FACTORY_SECRET'),'absent':probe}
with open(os.path.join(os.path.dirname(__file__),'marker.json'),'w',encoding='utf-8') as f:json.dump(value,f)
os.write(1,b'FIXED_WORKER_MARKER\\n')
'''
        self.job = self.make_job()
        self.control_r, self.control_w = os.pipe()
        self.addCleanup(os.close, self.control_r); self.addCleanup(os.close, self.control_w)
        # The noninherited job and host-control endpoints must stay absent in the child.
        stub = 'EXPECT_ABSENT=' + repr([self.job, msvcrt.get_osfhandle(self.control_w)]) + '\n' + stub
        (source / 'improvement_native_bootstrap.py').write_text(stub, encoding='utf-8')
        (source / 'improvement_native_image.py').write_bytes((SERVER / 'improvement_native_image.py').read_bytes())
        (source / 'improvement_worker.py').write_text('# fixed selected entry\n', encoding='utf-8')
        def pin(path):
            digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
            with image.ImageReadGuard(path, digest) as guard, open(path, 'rb') as reader:
                actual = guard.compare_file_handle(msvcrt.get_osfhandle(reader.fileno()))['actual']
            return {key: actual[key] for key in ('sha256', 'volume_serial_64', 'file_id_128')} | {'path': path}
        paths = _runtime_paths()
        self.policy = {'version': 1, 'scratch': str(self.root / 'scratch'), 'bootstrap': {
            'version': 1, 'entrypoint': 'trial', 'runtime': {name: pin(path) for name, path in paths.items()},
            'source': {'root': str(source), 'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}},
            'imports': {'site_packages': str(packages), 'files': {}}}}
        self.input_r, self.input_w = os.pipe()
        self.output_r, self.output_w = os.pipe()
        self.error_r, self.error_w = os.pipe()
        for fd in (self.input_r, self.input_w, self.output_r, self.output_w, self.error_r, self.error_w):
            self.addCleanup(os.close, fd)
        self.stdio = {name: msvcrt.get_osfhandle(fd) for name, fd in
                      (('stdin', self.input_r), ('stdout', self.output_w), ('stderr', self.error_w))}
        self.owners = []
        self.debug_states = {}
        self.addCleanup(self.cleanup_owners)

    def make_job(self, *, kill=True, inherit=False):
        # Test-owned raw job setup independent of the production factory's checks.
        from ctypes import wintypes as W
        class Basic(ctypes.Structure):
            _fields_ = [('process', ctypes.c_longlong), ('job', ctypes.c_longlong), ('flags', W.DWORD),
                ('min', ctypes.c_size_t), ('max', ctypes.c_size_t), ('active', W.DWORD),
                ('affinity', ctypes.c_size_t), ('priority', W.DWORD), ('scheduling', W.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in ('a','b','c','d','e','f')]
        class Limits(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', IO), ('process_mem', ctypes.c_size_t),
                ('job_mem', ctypes.c_size_t), ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, W.LPCWSTR]; kernel.CreateJobObjectW.restype = W.HANDLE
        kernel.SetInformationJobObject.argtypes = [W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD]
        kernel.SetInformationJobObject.restype = W.BOOL
        kernel.SetHandleInformation.argtypes = [W.HANDLE, W.DWORD, W.DWORD]; kernel.SetHandleInformation.restype = W.BOOL
        handle = kernel.CreateJobObjectW(None, None)
        self.assertTrue(handle)
        self.addCleanup(self.debug.close, handle)
        limits = Limits(); limits.basic.flags = 0x2000 if kill else 0
        self.assertTrue(kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
        self.assertTrue(kernel.SetHandleInformation(handle, 1, int(inherit)))
        return handle

    def owner(self, **kwargs):
        owner = self.mod.FixedWorkerLaunch(self.policy, job_handle=kwargs.pop('job_handle', self.job),
                                         stdio=kwargs.pop('stdio', self.stdio), **kwargs)
        self.owners.append(owner)
        return owner

    def protect_close(self, handle, protected):
        from ctypes import wintypes as W
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.SetHandleInformation.argtypes = [W.HANDLE, W.DWORD, W.DWORD]
        kernel.SetHandleInformation.restype = W.BOOL
        self.assertTrue(kernel.SetHandleInformation(handle, 2, 2 if protected else 0))

    def native_close_failure_once(self, original, failed):
        def close(handle):
            if not failed:
                failed.append(handle)
                self.protect_close(handle, True)
                try:
                    return original(handle)  # Real CloseHandle returns FALSE.
                finally:
                    self.protect_close(handle, False)
            return original(handle)
        return close

    def drain(self, owner, *, allow=False):
        caps = owner.capabilities
        if caps is None: return
        state = self.debug_states.setdefault(owner, {'resumed': False, 'terminated': False, 'exit': False})
        if not state['resumed']:
            self.debug.enable_kill()
            self.assertEqual(self.debug.resume(caps['thread_handle']), 1)
            state['resumed'] = True
        if not allow and not state['terminated'] and not state['exit']:
            self.debug.terminate(caps['process_handle'])
            state['terminated'] = True
        deadline = time.monotonic() + 8
        while not state['exit']:
            event = self.debug.next_event()
            if event is None:
                if time.monotonic() > deadline: self.fail('test root debug drain deadline')
                time.sleep(.002); continue
            self.assertEqual(event.pid, caps['pid'])
            if event.code == 3 and event.data.create.file: self.debug.close(event.data.create.file)
            if event.code == 6 and event.data.dll.file: self.debug.close(event.data.dll.file)
            self.debug.continue_event(event, 0x00010002 if event.code != 1 or
                event.data.exception.record.code in (0x80000003, 0x80000004) else 0x80010001)
            state['exit'] = event.code == 5
        while not self.debug.wait(caps['process_handle']):
            if time.monotonic() > deadline: self.fail('test process object exit deadline')
            time.sleep(.002)

    def cleanup_owners(self):
        for owner in self.owners:
            if owner.created and owner.capabilities is not None and not self.debug.wait(owner.capabilities['process_handle']):
                self.drain(owner)
            owner.close()

    def test_actual_job_membership_precedes_any_resume_and_fixed_stub_runs(self):
        owner = self.owner()
        with patch.dict(os.environ, {'FIXED_FACTORY_SECRET': 'never-copy'}): owner.launch()
        caps = owner.capabilities
        self.assertEqual(set(caps), {'process_handle', 'thread_handle', 'pid', 'tid', 'birth', 'thread_birth'})
        self.assertTrue(self.api.in_job(caps['process_handle'], self.job))
        self.assertFalse(self.marker.exists())
        self.assertTrue(owner.temporary_duplicates_closed)
        changed = owner.capabilities; changed['pid'] = 1
        self.assertEqual(owner.capabilities['pid'], caps['pid'])
        with self.assertRaises(OSError): owner.close()
        self.drain(owner, allow=True)
        self.assertEqual(os.read(self.output_r, 4096), b'FIXED_WORKER_MARKER\n')
        value = json.loads(self.marker.read_text(encoding='utf-8'))
        self.assertEqual(value, {'isolated': 1, 'no_site': 1, 'no_bytecode': True, 'site_loaded': False,
            'cwd': self.policy['bootstrap']['source']['root'], 'home': self.policy['scratch'],
            'private': None, 'absent': [False, False]})
        owner.close()
        self.assertIsNone(owner.capabilities)
        self.assertTrue(self.api.handle_flags(self.job) == 0)
        for handle in self.stdio.values(): self.api.handle_flags(handle)

    def test_non_kill_or_inheritable_or_nonempty_job_refuses_without_creation(self):
        for handle in (self.make_job(kill=False), self.make_job(inherit=True)):
            owner = self.owner(job_handle=handle)
            with self.assertRaises(OSError) as caught: owner.launch()
            self.assertIs(caught.exception.owner, owner)
            self.assertFalse(owner.created); owner.close()
        first = self.owner(); first.launch()
        second = self.owner()
        with self.assertRaises(OSError): second.launch()
        self.assertFalse(second.created)
        self.drain(first); first.close(); second.close()

    def test_disk_stdio_and_wrong_direction_pipe_refuse(self):
        with open(self.marker, 'wb') as handle:
            bad = {**self.stdio, 'stdin': self.msvcrt.get_osfhandle(handle.fileno())}
            owner = self.owner(stdio=bad)
            with self.assertRaises(OSError): owner.launch()
            self.assertFalse(owner.created); owner.close()
        owner = self.owner(stdio={**self.stdio, 'stdin': self.msvcrt.get_osfhandle(self.input_w)})
        with self.assertRaises(OSError): owner.launch()
        self.assertFalse(owner.created); owner.close()

    def test_declared_bytes_and_runtime_identity_drift_refuse_before_create(self):
        original_id = self.policy['bootstrap']['runtime']['dll']['file_id_128']
        self.policy['bootstrap']['runtime']['dll']['file_id_128'] = '0' * 32
        owner = self.owner()
        with self.assertRaises(OSError): owner.launch()
        self.assertFalse(owner.created); owner.close()
        self.policy['bootstrap']['runtime']['dll']['file_id_128'] = original_id
        target = Path(self.policy['bootstrap']['source']['root']) / 'improvement_worker.py'
        target.write_text('drift\n', encoding='utf-8')
        owner = self.owner()
        with self.assertRaises(OSError): owner.launch()
        self.assertFalse(owner.created); owner.close()

    def test_native_attribute_failure_refuses_without_fallback_and_keeps_owner(self):
        owner = self.owner()
        with patch.object(self.api, 'attributes', side_effect=OSError('PRIVATE_ATTRIBUTE_FAILURE')):
            with self.assertRaises(OSError) as caught: owner.launch()
        self.assertIs(caught.exception.owner, owner)
        self.assertNotIn('PRIVATE_ATTRIBUTE_FAILURE', str(caught.exception))
        self.assertFalse(owner.created)
        owner.close()
        for handle in self.stdio.values(): self.api.handle_flags(handle)

    def test_post_create_close_failure_retains_raw_root_and_retries_after_terminal(self):
        owner = self.owner()
        original = self.api.close
        failed = []
        fail_once = self.native_close_failure_once(original, failed)
        with patch.object(self.api, 'close', side_effect=fail_once):
            with self.assertRaises(OSError) as caught: owner.launch()
        self.assertIs(caught.exception.owner, owner)
        self.assertTrue(owner.created)
        self.assertFalse(owner.temporary_duplicates_closed)
        self.assertTrue(self.api.in_job(owner.capabilities['process_handle'], self.job))
        self.assertFalse(self.marker.exists())
        with self.assertRaises(OSError): owner.close()
        self.drain(owner)
        owner.close()
        self.assertIsNone(owner.capabilities)

    def test_failed_post_create_observation_keeps_root_and_guarded_bytes_until_terminal(self):
        owner = self.owner()
        with patch.object(self.api, 'in_job', return_value=False):
            with self.assertRaises(OSError) as caught: owner.launch()
        self.assertIs(caught.exception.owner, owner)
        self.assertTrue(owner.created)
        target = Path(self.policy['bootstrap']['source']['root']) / 'improvement_worker.py'
        with self.assertRaises(PermissionError): target.write_text('refused', encoding='utf-8')
        self.assertTrue(self.api.in_job(owner.capabilities['process_handle'], self.job))
        self.drain(owner)
        owner.close()
        target.write_text('released', encoding='utf-8')

    def test_terminal_raw_handle_close_failure_can_retry_without_dropping_handle(self):
        owner = self.owner(); owner.launch(); self.drain(owner)
        original, failed = self.api.close, []
        fail_once = self.native_close_failure_once(original, failed)
        with patch.object(self.api, 'close', side_effect=fail_once):
            with self.assertRaises(OSError) as caught: owner.close()
        self.assertIs(caught.exception.owner, owner)
        self.assertEqual(owner.capabilities['thread_handle'], failed[0])
        owner.close()
        self.assertIsNone(owner.capabilities)

    def test_interrupted_native_success_adopts_populated_process_information(self):
        owner = self.owner()
        original = self.api.create
        def interrupted(*args):
            original(*args)
            raise KeyboardInterrupt('controlled native-return interruption')
        with patch.object(self.api, 'create', side_effect=interrupted):
            with self.assertRaises(OSError) as caught: owner.launch()
        self.assertIs(caught.exception.owner, owner)
        self.assertTrue(owner.created)
        self.assertTrue(self.api.in_job(owner.capabilities['process_handle'], self.job))
        self.drain(owner)
        owner.close()

    def test_interrupted_duplicate_success_keeps_real_pipe_capability_for_close(self):
        owner = self.owner()
        original, acquired = self.api.duplicate, []
        def interrupted(*args):
            result = original(*args)
            acquired.append(result if len(args) == 1 else args[1].value)
            raise KeyboardInterrupt('controlled duplicate-return interruption')
        with patch.object(self.api, 'duplicate', side_effect=interrupted):
            with self.assertRaises(OSError) as caught: owner.launch()
        self.assertIs(caught.exception.owner, owner)
        self.assertFalse(owner.created)
        self.assertEqual(len(acquired), 1)
        self.assertEqual(self.api.handle_flags(acquired[0]) & 1, 1)
        owner.close()
        try:
            self.api.handle_flags(acquired[0])
        except OSError:
            pass
        else:
            # Keep the deliberate RED reproduction itself free of a leaked pipe.
            self.api.close(acquired[0])
            self.fail('interrupted successful DuplicateHandle was not owned for close')

    def test_interrupted_attribute_success_keeps_initialized_storage_for_delete(self):
        owner = self.owner()
        original, acquired = self.api.attributes, []
        def interrupted(*args):
            result = original(*args)
            acquired.append(result if len(args) == 2 else args[2])
            raise KeyboardInterrupt('controlled attribute-return interruption')
        with patch.object(self.api, 'attributes', side_effect=interrupted):
            with self.assertRaises(OSError) as caught: owner.launch()
        self.assertIs(caught.exception.owner, owner)
        self.assertFalse(owner.created)
        self.assertTrue(acquired[0].live)
        owner.close()
        if acquired[0].live:
            acquired[0].close()
            self.fail('interrupted initialized attributes were not owned for delete')

    def test_oserror_after_real_close_keeps_unknown_state_and_never_retries_handle(self):
        owner = self.owner(); owner.launch(); self.drain(owner)
        caps, original, attempts = owner.capabilities, self.api.close, []
        def success_then_error(handle):
            attempts.append(handle)
            original(handle)
            raise OSError('controlled exception after successful native close')
        try:
            with patch.object(self.api, 'close', side_effect=success_then_error):
                with self.assertRaises(OSError) as caught: owner.close()
                self.assertIs(caught.exception.owner, owner)
                with self.assertRaises(OSError): owner.close()
            self.api.handle_flags(caps['process_handle'])
            self.assertEqual(attempts.count(caps['thread_handle']), 1, 'unknown close result must not be retried')
        finally:
            # The controlled fixture knows the first real close succeeded and
            # all source pins closed before it. Production cannot infer this.
            original(caps['process_handle'])
            self.owners.remove(owner)


if __name__ == '__main__':
    unittest.main()
