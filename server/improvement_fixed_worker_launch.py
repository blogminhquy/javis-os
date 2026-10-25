"""Fixed guardian worker creation, with job assignment inside CreateProcessW.

No consumer or qualification is installed. The host must authenticate this source
and the complete declared bootstrap manifest; hashes alone do not authorize it.
The guardian must serialize its borrowed job/pipe capabilities throughout launch.
It alone owns job/debug/descendant drain and seals its ORIGINAL pipe copies before
host private input. This owner closes only its own duplicates and declared pins.
No SDK, account, model, arbitrary argv/environment or socket handles enter here.
"""
from __future__ import annotations

from functools import lru_cache
import json
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess

from improvement_native_bootstrap import validate_bootstrap_manifest, _canonical, _load_guard_type, _runtime_paths


_FLAGS = 0x08080406  # NO_WINDOW | EXTENDED_STARTUPINFO | UNICODE_ENV | SUSPENDED | DEBUG_ONLY
_RETAINED = set()


def _invalid():
    raise ValueError('invalid_fixed_worker_launch')


def _fields(value, fields):
    if type(value) is not dict or any(type(key) is not str for key in value) or set(value) != fields:
        _invalid()


def _path(value):
    if type(value) is not str or not value or len(value) > 32766:
        _invalid()
    try:
        value.encode('utf-16-le')
    except UnicodeEncodeError:
        _invalid()
    parsed = PureWindowsPath(value)
    if (not parsed.is_absolute() or re.fullmatch('[A-Za-z]:', parsed.drive) is None
            or str(parsed) != value or re.search(r'[\x00-\x1f<>"|?*:]' , value[2:])
            or any(part in ('.', '..') or part.endswith((' ', '.')) for part in parsed.parts[1:])):
        _invalid()


def _handle(value):
    if type(value) is not int or not 0 < value < 2 ** 64 - 1:
        _invalid()


def _policy(value):
    _fields(value, {'version', 'bootstrap', 'scratch'})
    if type(value['version']) is not int or value['version'] != 1:
        _invalid()
    _path(value['scratch'])
    manifest = validate_bootstrap_manifest(value['bootstrap'])
    if manifest['entrypoint'] not in ('trial', 'operation'):
        _invalid()
    for path in (manifest['source']['root'], manifest['imports']['site_packages'],
                 *(pin['path'] for pin in manifest['runtime'].values())):
        _path(path)
    # Validate original built-in path types before canonical copying can erase subclasses.
    for path in (value['bootstrap']['source']['root'], value['bootstrap']['imports']['site_packages'],
                 *(pin['path'] for pin in value['bootstrap']['runtime'].values())):
        _path(path)
    result = {'version': 1, 'bootstrap': manifest, 'scratch': value['scratch']}
    return json.loads(_canonical(result))


class FixedWorkerLaunchError(OSError):
    """Retryable owned refusal; exception text contains no private dispatch data."""
    def __init__(self, owner):
        super().__init__('fixed_worker_launch_unproven')
        self.owner = owner


class _NativeCloseRejected(OSError):
    """Internal status emitted only after the actual native BOOL is FALSE."""


@lru_cache(maxsize=1)
def _backend():
    if os.name != 'nt':
        raise OSError('fixed_worker_windows_required')
    import ctypes as C
    from ctypes import wintypes as W
    if C.sizeof(C.c_void_p) != 8 or C.sizeof(W.DWORD) != 4:
        raise OSError('fixed_worker_abi_unsupported')
    H, P = W.HANDLE, C.c_void_p
    class Startup(C.Structure):
        _fields_ = [('cb', W.DWORD), ('reserved', W.LPWSTR), ('desktop', W.LPWSTR), ('title', W.LPWSTR),
            ('x', W.DWORD), ('y', W.DWORD), ('width', W.DWORD), ('height', W.DWORD),
            ('chars_x', W.DWORD), ('chars_y', W.DWORD), ('fill', W.DWORD), ('flags', W.DWORD),
            ('show', W.WORD), ('reserved_size', W.WORD), ('reserved_data', P),
            ('stdin', H), ('stdout', H), ('stderr', H)]
    class StartupEx(C.Structure):
        _fields_ = [('startup', Startup), ('attributes', P)]
    class ProcessInfo(C.Structure):
        _fields_ = [('process', H), ('thread', H), ('pid', W.DWORD), ('tid', W.DWORD)]
    class BasicLimits(C.Structure):
        _fields_ = [('process_time', C.c_longlong), ('job_time', C.c_longlong), ('flags', W.DWORD),
            ('min', C.c_size_t), ('max', C.c_size_t), ('active', W.DWORD), ('affinity', C.c_size_t),
            ('priority', W.DWORD), ('scheduling', W.DWORD)]
    class IO(C.Structure):
        _fields_ = [(name, C.c_ulonglong) for name in ('a', 'b', 'c', 'd', 'e', 'f')]
    class ExtendedLimits(C.Structure):
        _fields_ = [('basic', BasicLimits), ('io', IO), ('process_mem', C.c_size_t),
            ('job_mem', C.c_size_t), ('peak_process', C.c_size_t), ('peak_job', C.c_size_t)]
    class Accounting(C.Structure):
        _fields_ = [('user', C.c_longlong), ('kernel', C.c_longlong), ('period_user', C.c_longlong),
            ('period_kernel', C.c_longlong), ('faults', W.DWORD), ('total', W.DWORD),
            ('active', W.DWORD), ('terminated', W.DWORD)]
    class ObjectInfo(C.Structure):
        _fields_ = [('attributes', W.ULONG), ('access', W.ULONG), ('handles', W.ULONG),
            ('pointers', W.ULONG), ('reserved', W.ULONG * 10)]
    if C.sizeof(Startup) != 104 or C.sizeof(StartupEx) != 112 or C.sizeof(ProcessInfo) != 24:
        raise OSError('fixed_worker_layout_unsupported')
    kernel = C.WinDLL('kernel32', use_last_error=True)
    native = C.WinDLL('ntdll')
    def declare(name, args, result):
        function = getattr(kernel, name)
        function.argtypes, function.restype = args, result
    declare('GetCurrentProcess', [], H)
    declare('GetHandleInformation', [H, C.POINTER(W.DWORD)], W.BOOL)
    declare('GetFileType', [H], W.DWORD)
    declare('DuplicateHandle', [H, H, H, C.POINTER(H), W.DWORD, W.BOOL, W.DWORD], W.BOOL)
    declare('CloseHandle', [H], W.BOOL)
    declare('QueryInformationJobObject', [H, C.c_int, P, W.DWORD, C.POINTER(W.DWORD)], W.BOOL)
    declare('IsProcessInJob', [H, H, C.POINTER(W.BOOL)], W.BOOL)
    declare('InitializeProcThreadAttributeList', [P, W.DWORD, W.DWORD, C.POINTER(C.c_size_t)], W.BOOL)
    declare('UpdateProcThreadAttribute', [P, W.DWORD, C.c_size_t, P, C.c_size_t, P, P], W.BOOL)
    declare('DeleteProcThreadAttributeList', [P], None)
    declare('CreateProcessW', [W.LPCWSTR, W.LPWSTR, P, P, W.BOOL, W.DWORD, P, W.LPCWSTR,
                              C.POINTER(StartupEx), C.POINTER(ProcessInfo)], W.BOOL)
    declare('WaitForSingleObject', [H, W.DWORD], W.DWORD)
    declare('GetWindowsDirectoryW', [W.LPWSTR, W.UINT], W.UINT)
    for name in ('GetProcessTimes', 'GetThreadTimes'):
        declare(name, [H, *([C.POINTER(W.FILETIME)] * 4)], W.BOOL)
    native.NtQueryObject.argtypes = [H, C.c_int, P, W.ULONG, C.POINTER(W.ULONG)]
    native.NtQueryObject.restype = W.LONG
    def check(value):
        if not value: raise C.WinError(C.get_last_error())
        return value
    class Attributes:
        def __init__(self):
            self.state = 'empty'
            self.buffer = self.jobs = self.handles = None
        @property
        def live(self):
            return self.state in ('initializing', 'live', 'deleting')
        def prepare(self, job, handles):
            self.jobs, self.handles = (H * 1)(job), (H * 3)(*handles)
            size = C.c_size_t()
            kernel.InitializeProcThreadAttributeList(None, 2, 0, C.byref(size))
            if not 0 < size.value < 65536: raise OSError('fixed_worker_attributes_invalid')
            self.buffer = C.create_string_buffer(size.value)
            self.state = 'initializing'
            initialized = kernel.InitializeProcThreadAttributeList(self.buffer, 2, 0, C.byref(size))
            if not initialized:
                self.state = 'empty'
                check(initialized)
            self.state = 'live'
            check(kernel.UpdateProcThreadAttribute(self.buffer, 0, 0x0002000D,
                self.jobs, C.sizeof(self.jobs), None, None))
            check(kernel.UpdateProcThreadAttribute(self.buffer, 0, 0x00020002,
                self.handles, C.sizeof(self.handles), None, None))
        def close(self):
            if self.state in ('initializing', 'deleting'):
                raise OSError('fixed_worker_attribute_state_unknown')
            if self.state == 'live':
                self.state = 'deleting'
                kernel.DeleteProcThreadAttributeList(self.buffer)
                self.state = 'closed'
    class Backend:
        def close(self, handle):
            if not kernel.CloseHandle(handle):
                raise _NativeCloseRejected('fixed_worker_native_close_rejected')
        def handle_flags(self, handle):
            flags = W.DWORD(); check(kernel.GetHandleInformation(handle, C.byref(flags))); return flags.value
        def job(self, handle):
            if self.handle_flags(handle) != 0: raise OSError('fixed_worker_job_flags_invalid')
            limits, accounting = ExtendedLimits(), Accounting()
            check(kernel.QueryInformationJobObject(handle, 9, C.byref(limits), C.sizeof(limits), None))
            check(kernel.QueryInformationJobObject(handle, 1, C.byref(accounting), C.sizeof(accounting), None))
            if limits.basic.flags != 0x2000 or accounting.active or accounting.total:
                raise OSError('fixed_worker_job_not_empty_or_kill_only')
        def pipe(self, handle, *, read):
            self.handle_flags(handle)
            if kernel.GetFileType(handle) != 3: raise OSError('fixed_worker_pipe_required')
            info, count = ObjectInfo(), W.ULONG()
            status = native.NtQueryObject(handle, 0, C.byref(info), C.sizeof(info), C.byref(count))
            if status or count.value != C.sizeof(info) or not info.access & (1 if read else 2):
                raise OSError('fixed_worker_pipe_access_invalid')
        def handle_slot(self): return H()
        def duplicate(self, handle, result):
            current = kernel.GetCurrentProcess()
            check(kernel.DuplicateHandle(current, handle, current, C.byref(result), 0, True, 2))
        def attribute_storage(self): return Attributes()
        def attributes(self, job, handles, storage): storage.prepare(job, handles)
        def environment(self, scratch):
            buffer = C.create_unicode_buffer(32768)
            count = kernel.GetWindowsDirectoryW(buffer, len(buffer))
            if not 0 < count < len(buffer): raise OSError('fixed_worker_windows_directory_invalid')
            windows = buffer.value
            env = {'SYSTEMROOT': windows, 'WINDIR': windows,
                'PATH': str(Path(windows) / 'System32') + ';' + windows,
                'HOME': scratch, 'USERPROFILE': scratch, 'APPDATA': scratch, 'LOCALAPPDATA': scratch,
                'TEMP': scratch, 'TMP': scratch}
            return C.create_unicode_buffer('\0'.join(key + '=' + env[key] for key in sorted(env)) + '\0\0')
        def create(self, executable, command, cwd, environment, attributes, handles, result):
            startup = StartupEx()
            startup.startup.cb, startup.startup.flags = C.sizeof(startup), 0x100
            startup.startup.stdin, startup.startup.stdout, startup.startup.stderr = handles
            startup.attributes = C.cast(attributes.buffer, P)
            line = C.create_unicode_buffer(command)
            check(kernel.CreateProcessW(executable, line, None, None, True, _FLAGS, environment,
                                        cwd, C.byref(startup), C.byref(result)))
        def process_info(self): return ProcessInfo()
        def in_job(self, process, job):
            value = W.BOOL(); check(kernel.IsProcessInJob(process, job, C.byref(value))); return bool(value.value)
        def birth(self, handle, thread=False):
            values = [W.FILETIME() for _ in range(4)]
            function = kernel.GetThreadTimes if thread else kernel.GetProcessTimes
            check(function(handle, *[C.byref(value) for value in values]))
            return values[0].dwHighDateTime << 32 | values[0].dwLowDateTime
        def terminal(self, process):
            status = kernel.WaitForSingleObject(process, 0)
            if status not in (0, 258): raise OSError('fixed_worker_exit_unproven')
            return status == 0
    return Backend()


class FixedWorkerLaunch:
    """Own one fixed suspended root; never resume, terminate or pump it here.

    policy is exactly {version:1, bootstrap:<validated declared manifest>, scratch}.
    job_handle and stdio={stdin,stdout,stderr} are live borrowed capabilities.
    metadata is None or {}; Windows sockets require later socket sharing instead.
    launch() returns a fresh capabilities dict, also exposed by capabilities:
    process_handle/thread_handle/pid/tid/birth/thread_birth. Handles are borrowed
    from this owner and must not be closed by a consumer. No Popen transfer occurs.
    temporary_duplicates_closed covers OUR copies only. The guardian must seal
    every original data-pipe copy before private host input and hold source guards
    through its full job drain. close() checks root exit, not debug/job quiescence.
    Every failed operation exposes error.owner; retry cleanup only after the
    guardian proves its root/debug/descendant terminal state. No finalizer hides
    a leaked or unknown capability. Partially closed capabilities may be None.
    An interrupted Initialize/Delete or native close with an ambiguous result
    remains unproven: retaining its owner does not authorize a blind retry.
    """
    def __init__(self, policy, *, job_handle, stdio, metadata=None):
        self._policy = _policy(policy)
        _handle(job_handle)
        _fields(stdio, {'stdin', 'stdout', 'stderr'})
        for value in stdio.values(): _handle(value)
        if len({job_handle, *stdio.values()}) != 4:
            _invalid()
        if metadata is not None and (type(metadata) is not dict or metadata):
            _invalid()
        self._job, self._stdio = job_handle, dict(stdio)
        self._api = self._attributes = self._process = None
        self._guards, self._readers, self._duplicates = [], [], []
        self._handle_states = {}
        self._birth = self._thread_birth = None
        self._used = self._closed = self._closing = self._terminal_known = False
        self._unknown_creation = False
        self.created = self.temporary_duplicates_closed = False

    def _failure(self):
        _RETAINED.add(self)
        return FixedWorkerLaunchError(self)

    @property
    def capabilities(self):
        if not self.created or self._closed:
            return None
        return {'process_handle': None if self._handle_states.get(('root', 'process')) == 'closed' else self._process.process,
                'thread_handle': None if self._handle_states.get(('root', 'thread')) == 'closed' else self._process.thread,
                'pid': self._process.pid, 'tid': self._process.tid,
                'birth': self._birth, 'thread_birth': self._thread_birth}

    def _guard(self, kind, path, digest):
        try:
            guard = kind(path, digest)
        except BaseException as error:
            partial = getattr(error, 'guard', None)
            if partial is not None: self._guards.append(partial)
            raise
        self._guards.append(guard)
        return guard

    def _pins(self):
        import msvcrt
        manifest = self._policy['bootstrap']
        actual_runtime = _runtime_paths()
        if any(os.path.normcase(actual_runtime[name]) != os.path.normcase(pin['path'])
               for name, pin in manifest['runtime'].items()):
            raise OSError('fixed_worker_direct_base_runtime_required')
        root, packages = Path(manifest['source']['root']), Path(manifest['imports']['site_packages'])
        kind = _load_guard_type(root, manifest['source']['files'])
        for pin in manifest['runtime'].values():
            guard = self._guard(kind, pin['path'], pin['sha256'])
            reader = open(pin['path'], 'rb'); self._readers.append(reader)
            compared = guard.compare_file_handle(msvcrt.get_osfhandle(reader.fileno()))
            if (compared['matches'] is not True or any(compared['actual'][key] != pin[key]
                    for key in ('sha256', 'volume_serial_64', 'file_id_128'))):
                raise OSError('fixed_worker_runtime_identity_invalid')
            reader.close(); self._readers.pop()
        for name, digest in manifest['source']['files'].items():
            self._guard(kind, root.joinpath(*name.split('/')), digest)
        for name, digest in manifest['imports']['files'].items():
            self._guard(kind, packages.joinpath(*name.split('/')), digest)
        if not Path(self._policy['scratch']).is_dir():
            raise OSError('fixed_worker_scratch_unavailable')

    def _close_capability(self, key, handle):
        state = self._handle_states.get(key, 'live')
        if state == 'closed':
            return
        if state == 'closing':
            raise OSError('fixed_worker_close_result_unknown')
        if handle:
            self._handle_states[key] = 'closing'
            try:
                self._api.close(handle)
            except _NativeCloseRejected:
                # A documented CloseHandle failure keeps the capability owned.
                # Every other exception, including OSError after native success,
                # keeps 'closing': its result is unknown and cannot be retried.
                self._handle_states[key] = 'live'
                raise
        self._handle_states[key] = 'closed'

    def launch(self):
        if self._used or self._closed or self._closing:
            raise self._failure()
        self._used = True
        try:
            self._api = _backend()
            self._api.job(self._job)
            for name in ('stdin', 'stdout', 'stderr'):
                self._api.pipe(self._stdio[name], read=name == 'stdin')
            self._pins()
            for name in ('stdin', 'stdout', 'stderr'):
                slot = self._api.handle_slot()
                self._duplicates.append(slot)
                self._api.duplicate(self._stdio[name], slot)
            handles = [slot.value for slot in self._duplicates]
            self._attributes = self._api.attribute_storage()
            self._api.attributes(self._job, handles, self._attributes)
            manifest = self._policy['bootstrap']
            root, executable = manifest['source']['root'], manifest['runtime']['executable']['path']
            command = subprocess.list2cmdline([executable, '-I', '-S', '-B', str(Path(root) / 'improvement_native_bootstrap.py')])
            if len(command.encode('utf-16-le')) // 2 > 32766:
                raise OSError('fixed_worker_command_too_long')
            environment = self._api.environment(self._policy['scratch'])
            self._process = self._api.process_info()
            self._api.create(executable, command, root, environment, self._attributes, handles, self._process)
            # This is the first operation after successful native creation. Keep
            # raw PROCESS_INFORMATION, without a fallible duplicate or postcheck.
            self.created = True
            if not all((self._process.process, self._process.thread, self._process.pid, self._process.tid)):
                self._unknown_creation = True
                raise OSError('fixed_worker_creation_capability_unknown')
            if not self._api.in_job(self._process.process, self._job):
                raise OSError('fixed_worker_assignment_unproven')
            self._birth = self._api.birth(self._process.process)
            self._thread_birth = self._api.birth(self._process.thread, True)
            for guard in self._guards: guard.snapshot()
            self._attributes.close(); self._attributes = None
            while self._duplicates:
                slot = self._duplicates[-1]
                self._close_capability(('duplicate', id(slot)), slot.value)
                self._duplicates.pop()
            self.temporary_duplicates_closed = True
            return self.capabilities
        except BaseException:
            # A signal or wrapper failure can interrupt Python after the native
            # call filled this already-owned output structure. Never mistake
            # that case for pre-create refusal and release its source pins.
            if self._process is not None and (self._process.process or self._process.thread):
                self.created = True
                if not all((self._process.process, self._process.thread, self._process.pid, self._process.tid)):
                    self._unknown_creation = True
            raise self._failure() from None

    def close(self):
        if self._closed:
            return
        try:
            if self._unknown_creation:
                raise OSError('fixed_worker_creation_capability_unknown')
            if self.created and not self._terminal_known:
                if not self._process or not self._process.process or not self._api.terminal(self._process.process):
                    raise OSError('fixed_worker_root_terminal_required')
                self._terminal_known = True
            self._closing = True
            if self._attributes is not None:
                self._attributes.close(); self._attributes = None
            while self._duplicates:
                slot = self._duplicates[-1]
                self._close_capability(('duplicate', id(slot)), slot.value)
                self._duplicates.pop()
            while self._readers:
                self._readers[-1].close(); self._readers.pop()
            while self._guards:
                self._guards[-1].close(); self._guards.pop()
            if self.created:
                for name in ('thread', 'process'):
                    handle = getattr(self._process, name)
                    if handle:
                        self._close_capability(('root', name), handle)
                        setattr(self._process, name, None)
            self._closed = True
            _RETAINED.discard(self)
        except BaseException:
            raise self._failure() from None
