"""Lazy x64 Windows debug APIs for the isolated capture component only."""
from functools import lru_cache
import os
import platform


@lru_cache(maxsize=1)
def backend():
    if os.name != 'nt' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise OSError('native_capture_platform_unsupported')
    import ctypes as C
    from ctypes import wintypes as W
    if C.sizeof(C.c_void_p) != 8 or C.sizeof(W.DWORD) != 4:
        raise OSError('native_capture_abi_unsupported')
    H, PTR = W.HANDLE, C.c_void_p
    class Create(C.Structure):
        _fields_ = [('file', H), ('process', H), ('thread', H), ('base', PTR), ('offset', W.DWORD),
            ('size', W.DWORD), ('tls', PTR), ('start', PTR), ('name', PTR), ('unicode', W.WORD)]
    class Dll(C.Structure):
        _fields_ = [('file', H), ('base', PTR), ('offset', W.DWORD), ('size', W.DWORD), ('name', PTR), ('unicode', W.WORD)]
    class Record(C.Structure):
        _fields_ = [('code', W.DWORD), ('flags', W.DWORD), ('record', PTR), ('address', PTR),
            ('count', W.DWORD), ('information', C.c_size_t * 15)]
    class ExceptionInfo(C.Structure):
        _fields_ = [('record', Record), ('firstchance', W.DWORD)]
    class Data(C.Union):
        _fields_ = [('create', Create), ('dll', Dll), ('exception', ExceptionInfo),
            ('exitcode', W.DWORD), ('raw', C.c_byte * 160)]
    class Event(C.Structure):
        _fields_ = [('code', W.DWORD), ('pid', W.DWORD), ('tid', W.DWORD), ('data', Data)]
    if C.sizeof(Event) != 176 or Event.data.offset != 16:
        raise OSError('native_capture_debug_layout_unsupported')
    kernel = C.WinDLL('kernel32', use_last_error=True)
    def declare(name, args, result):
        function = getattr(kernel, name)
        function.argtypes, function.restype = args, result
    declare('GetCurrentProcess', [], H)
    declare('GetCurrentThreadId', [], W.DWORD)
    declare('DuplicateHandle', [H, H, H, C.POINTER(H), W.DWORD, W.BOOL, W.DWORD], W.BOOL)
    declare('CloseHandle', [H], W.BOOL)
    declare('WaitForDebugEvent', [C.POINTER(Event), W.DWORD], W.BOOL)
    declare('ContinueDebugEvent', [W.DWORD, W.DWORD, W.DWORD], W.BOOL)
    declare('GetProcessId', [H], W.DWORD)
    declare('GetProcessIdOfThread', [H], W.DWORD)
    declare('GetThreadId', [H], W.DWORD)
    for name in ('GetProcessTimes', 'GetThreadTimes'):
        declare(name, [H, *([C.POINTER(W.FILETIME)] * 4)], W.BOOL)
    declare('ResumeThread', [H], W.DWORD)
    declare('SuspendThread', [H], W.DWORD)
    declare('TerminateProcess', [H, W.UINT], W.BOOL)
    declare('WaitForSingleObject', [H, W.DWORD], W.DWORD)
    declare('GetExitCodeProcess', [H, C.POINTER(W.DWORD)], W.BOOL)
    declare('DebugSetProcessKillOnExit', [W.BOOL], W.BOOL)
    def check(value):
        if not value: raise C.WinError(C.get_last_error())
        return value
    class Backend:
        def current_thread(self): return kernel.GetCurrentThreadId()
        def current_process(self): return kernel.GetCurrentProcess()
        def duplicate(self, handle):
            result = H()
            check(kernel.DuplicateHandle(kernel.GetCurrentProcess(), handle, kernel.GetCurrentProcess(),
                C.byref(result), 0, False, 2))
            return result.value
        def close(self, handle): check(kernel.CloseHandle(handle))
        def birth(self, handle, thread=False):
            values = [W.FILETIME() for _ in range(4)]
            function = kernel.GetThreadTimes if thread else kernel.GetProcessTimes
            check(function(handle, *[C.byref(v) for v in values]))
            return (values[0].dwHighDateTime << 32) | values[0].dwLowDateTime
        def process_id(self, handle): return kernel.GetProcessId(handle)
        def thread_owner(self, handle): return kernel.GetProcessIdOfThread(handle)
        def thread_id(self, handle): return kernel.GetThreadId(handle)
        def wait(self, handle):
            result = kernel.WaitForSingleObject(handle, 0)
            if result not in (0, 258): raise C.WinError(C.get_last_error())
            return result == 0
        def exit_code(self, handle):
            value = W.DWORD(); check(kernel.GetExitCodeProcess(handle, C.byref(value)))
            return value.value
        def terminate(self, handle): check(kernel.TerminateProcess(handle, 74))
        def enable_kill(self): check(kernel.DebugSetProcessKillOnExit(True))
        def resume(self, handle): return kernel.ResumeThread(handle)
        def suspend(self, handle): return kernel.SuspendThread(handle)
        def next_event(self):
            event = Event()
            if kernel.WaitForDebugEvent(C.byref(event), 0): return event
            if C.get_last_error() != 121: raise C.WinError(C.get_last_error())
            return None
        def continue_event(self, event, status=0x00010002):
            check(kernel.ContinueDebugEvent(event.pid, event.tid, status))
    return Backend()
