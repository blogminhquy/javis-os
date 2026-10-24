"""One fresh trial process, with host-owned IPC and lifetime-bounded descendants."""
from __future__ import annotations

import os
import sys
import threading
import time
from contextlib import contextmanager, nullcontext
from pathlib import Path

# Isolated Python removes the script directory; restore only this trusted host source root.
_SERVER_DIR = str(Path(__file__).resolve().parent)
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)
import winproc


def process_flags():
    return winproc.no_window()


@contextmanager
def _sdk_hidden_processes():
    """Single-query worker scope: hide SDK version/query descendants on Windows.

    SDK0.2.116 does not pass creation flags to its transport. This temporary
    boundary belongs only to this isolated worker, never the shared chat server
    or installed SDK. Preserve caller flags and restore the transport on exit.
    """
    from claude_agent_sdk._internal.transport import subprocess_cli
    original = subprocess_cli.anyio.open_process

    async def hidden(*args, **kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | winproc.no_window()
        return await original(*args, **kwargs)

    subprocess_cli.anyio.open_process = hidden
    try:
        yield
    finally:
        subprocess_cli.anyio.open_process = original


class WorkerGroupCleanupError(OSError):
    """The host still owns the job; releasing workspace/brain ownership is unsafe."""


class WorkerGroup:
    """Attach before sending input: a worker cannot start its engine before ownership exists."""

    def __init__(self, pid, *, recovery_fences=(), suspended=False):
        self.pid, self.handle = pid, None
        self._close_lock = threading.Lock()
        self._process_handles = {}
        self._inventory_lock = threading.Lock()
        self._births = 0
        self._inventory_error = False
        self._guardian = None
        if os.name == 'nt' and recovery_fences:
            from improvement_native_lifetime import NativeLifetime
            self._guardian = NativeLifetime(pid, recovery_fences, suspended=suspended)
            return
        if os.name != "nt":
            if pid == os.getpgid(0) or os.getpgid(pid) != pid:
                raise OSError("trial_worker_process_group_unavailable")
            return
        import ctypes
        from ctypes import wintypes

        class BasicLimit(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                        ("flags", wintypes.DWORD), ("minimum_working_set", ctypes.c_size_t),
                        ("maximum_working_set", ctypes.c_size_t), ("active_processes", wintypes.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in
                        ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]

        class ExtendedLimit(ctypes.Structure):
            _fields_ = [("basic", BasicLimit), ("io", IoCounters), ("process_memory", ctypes.c_size_t),
                        ("job_memory", ctypes.c_size_t), ("peak_process_memory", ctypes.c_size_t),
                        ("peak_job_memory", ctypes.c_size_t)]

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.SetInformationJobObject.restype = wintypes.BOOL
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        job = kernel.CreateJobObjectW(None, None)
        if not job:
            raise OSError("trial_worker_job_unavailable")
        process = None
        try:
            limits = ExtendedLimit()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise OSError("trial_worker_job_unavailable")
            self.handle, self._kernel = job, kernel
            self._start_inventory()
            process = kernel.OpenProcess(0x0101, False, pid)  # PROCESS_SET_QUOTA | PROCESS_TERMINATE
            if not process or not kernel.AssignProcessToJobObject(job, process):
                raise OSError("trial_worker_job_unavailable")
        except BaseException:
            kernel.CloseHandle(job)
            self._stop_inventory()
            raise
        finally:
            if process:
                kernel.CloseHandle(process)
        self.handle, self._kernel = job, kernel
        if suspended:
            try:
                self._resume_initial_thread()
            except BaseException:
                self.close()
                raise

    def _resume_initial_thread(self):
        """Assign the suspended launcher before it can create an unowned child."""
        import ctypes
        from ctypes import wintypes
        class ThreadEntry(ctypes.Structure):
            _fields_ = [('size', wintypes.DWORD), ('usage', wintypes.DWORD), ('thread', wintypes.DWORD),
                ('process', wintypes.DWORD), ('priority', wintypes.LONG), ('delta', wintypes.LONG), ('flags', wintypes.DWORD)]
        kernel = self._kernel
        kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        kernel.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(ThreadEntry)]
        kernel.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(ThreadEntry)]
        kernel.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenThread.restype = wintypes.HANDLE
        kernel.ResumeThread.argtypes = [wintypes.HANDLE]
        kernel.ResumeThread.restype = wintypes.DWORD
        snapshot = kernel.CreateToolhelp32Snapshot(4, 0)  # TH32CS_SNAPTHREAD
        if snapshot == ctypes.c_void_p(-1).value:
            raise OSError('native_initial_thread_inventory_unavailable')
        threads = []
        try:
            entry = ThreadEntry()
            entry.size = ctypes.sizeof(entry)
            more = kernel.Thread32First(snapshot, ctypes.byref(entry))
            while more:
                if entry.process == self.pid:
                    threads.append(entry.thread)
                more = kernel.Thread32Next(snapshot, ctypes.byref(entry))
        finally:
            kernel.CloseHandle(snapshot)
        if len(threads) != 1:
            raise OSError('native_initial_thread_unproven')
        thread = kernel.OpenThread(2, False, threads[0])  # THREAD_SUSPEND_RESUME
        if not thread:
            raise OSError('native_initial_thread_unavailable')
        try:
            if kernel.ResumeThread(thread) != 1:
                raise OSError('native_initial_thread_resume_unproven')
        finally:
            kernel.CloseHandle(thread)

    def close(self):
        with self._close_lock:
            if getattr(self, '_guardian', None) is not None:
                self._guardian.close()
                self.pid = None
                return
            if os.name == "nt":
                if self.handle:
                    self._drain_windows_job()
                    if not self._kernel.CloseHandle(self.handle):
                        raise WorkerGroupCleanupError('trial_worker_job_close_unproven')
                    self.handle = None
                    self._stop_inventory()
            elif self.pid is not None:
                winproc.kill_tree(self.pid)
            self.pid = None

    def _start_inventory(self):
        """Capture birth handles from an inactive job; verify completeness at drain.

        Ordinary completion messages may be dropped. Their count must equal the
        kernel's cumulative TotalProcesses before any cleanup proof is issued.
        A missing/unreadable notification leaves ownership and fences intact.
        """
        import ctypes
        from ctypes import wintypes
        kernel = self._kernel
        kernel.CreateIoCompletionPort.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.c_size_t, wintypes.DWORD]
        kernel.CreateIoCompletionPort.restype = wintypes.HANDLE
        kernel.GetQueuedCompletionStatus.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_void_p), wintypes.DWORD]
        kernel.GetQueuedCompletionStatus.restype = wintypes.BOOL
        port = kernel.CreateIoCompletionPort(ctypes.c_void_p(-1), None, 0, 1)
        if not port:
            raise OSError('native_process_inventory_unavailable')
        class Association(ctypes.Structure):
            _fields_ = [('key', ctypes.c_void_p), ('port', wintypes.HANDLE)]
        association = Association(1, port)
        if not kernel.SetInformationJobObject(self.handle, 7, ctypes.byref(association), ctypes.sizeof(association)):
            kernel.CloseHandle(port)
            raise OSError('native_process_inventory_unavailable')
        self._inventory_port = port
        self._inventory_stop = threading.Event()

        def monitor():
            while not self._inventory_stop.is_set():
                message, key, pid = wintypes.DWORD(), ctypes.c_size_t(), ctypes.c_void_p()
                if not kernel.GetQueuedCompletionStatus(port, ctypes.byref(message), ctypes.byref(key), ctypes.byref(pid), 50):
                    if ctypes.get_last_error() != 258:
                        self._inventory_error = True
                    continue
                if message.value != 6:  # JOB_OBJECT_MSG_NEW_PROCESS
                    continue
                with self._inventory_lock:
                    value = pid.value
                    if not value or self._births >= 4096:
                        self._inventory_error = True
                        continue
                    if value not in self._process_handles:
                        handle = kernel.OpenProcess(0x100000, False, value)
                        if handle:
                            self._process_handles[value] = handle
                        elif ctypes.get_last_error() != 87:
                            self._inventory_error = True
                    self._births += 1

        self._inventory_thread = threading.Thread(target=monitor, name='native-process-inventory', daemon=True)
        self._inventory_thread.start()

    def _stop_inventory(self):
        if getattr(self, '_inventory_port', None) is None:
            return
        self._inventory_stop.set()
        self._inventory_thread.join()
        self._kernel.CloseHandle(self._inventory_port)
        self._inventory_port = None

    def inventory(self):
        if self._guardian is not None:
            return self._guardian.inventory()
        import ctypes
        from ctypes import wintypes
        self._kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
        self._kernel.QueryInformationJobObject.restype = wintypes.BOOL
        class Members(ctypes.Structure):
            _fields_ = [('assigned', ctypes.c_uint32), ('count', ctypes.c_uint32), ('pids', ctypes.c_size_t * 4096)]
        value = Members()
        if (not self._kernel.QueryInformationJobObject(self.handle, 3, ctypes.byref(value), ctypes.sizeof(value), None)
                or value.assigned > len(value.pids) or value.count != value.assigned):
            raise WorkerGroupCleanupError('trial_worker_job_inventory_unavailable')
        return list(value.pids[:value.count])

    def _drain_windows_job(self):
        # KILL_ON_JOB_CLOSE requests termination; it is not a process-exit wait.
        # Keep the actual job handle until its documented ActiveProcesses is0:
        # https://learn.microsoft.com/windows/win32/api/winnt/ns-winnt-jobobject_basic_accounting_information
        import ctypes
        from ctypes import wintypes

        class Accounting(ctypes.Structure):
            _fields_ = [('user', ctypes.c_int64), ('kernel', ctypes.c_int64),
                ('period_user', ctypes.c_int64), ('period_kernel', ctypes.c_int64),
                ('faults', ctypes.c_uint32), ('total', ctypes.c_uint32),
                ('active', ctypes.c_uint32), ('terminated', ctypes.c_uint32)]

        kernel = self._kernel
        kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.TerminateJobObject.restype = wintypes.BOOL
        kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
        kernel.QueryInformationJobObject.restype = wintypes.BOOL
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD

        class Members(ctypes.Structure):
            _fields_ = [('assigned', ctypes.c_uint32), ('count', ctypes.c_uint32), ('pids', ctypes.c_size_t * 4096)]

        def capture():
            members = Members()
            if (not kernel.QueryInformationJobObject(self.handle, 3, ctypes.byref(members), ctypes.sizeof(members), None)
                    or members.assigned > len(members.pids) or members.count != members.assigned):
                raise WorkerGroupCleanupError('trial_worker_job_inventory_unavailable')
            with getattr(self, '_inventory_lock', nullcontext()):
                for pid in members.pids[:members.count]:
                    if pid in self._process_handles:
                        continue
                    handle = kernel.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE
                    if not handle:
                        if getattr(ctypes, 'get_last_error', lambda: 0)() == 87:
                            continue  # The process object no longer exists.
                        raise WorkerGroupCleanupError('trial_worker_process_wait_unavailable')
                    self._process_handles[pid] = handle

        # Accounting/PID-list removal can precede the process object's signaled
        # exit state. Capture handles before termination and retain them across
        # retryable observation failures; never infer I/O quiescence from a PID.
        capture()
        if not kernel.TerminateJobObject(self.handle, 1):
            raise WorkerGroupCleanupError('trial_worker_job_termination_unproven')
        deadline = time.monotonic() + 5
        while True:
            capture()
            accounting = Accounting()
            if not kernel.QueryInformationJobObject(self.handle, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None):
                raise WorkerGroupCleanupError('trial_worker_job_drain_unavailable')
            with getattr(self, '_inventory_lock', nullcontext()):
                waits = [kernel.WaitForSingleObject(handle, 0) for handle in self._process_handles.values()]
                complete = (getattr(self, '_inventory_port', None) is None or
                    (not self._inventory_error and self._births == accounting.total))
            if any(value not in (0, 0x102) for value in waits):
                raise WorkerGroupCleanupError('trial_worker_process_exit_unproven')
            if accounting.active == 0 and complete and all(value == 0 for value in waits):
                for pid, handle in tuple(self._process_handles.items()):
                    if not kernel.CloseHandle(handle):
                        raise WorkerGroupCleanupError('trial_worker_process_handle_close_unproven')
                    del self._process_handles[pid]
                return
            if time.monotonic() >= deadline:
                raise WorkerGroupCleanupError('trial_worker_job_still_active')
            time.sleep(.01)


async def run_request(payload, read_control, emit, *, adapter_factory=None, engine_factory=None, native_session=None):
    """Validate host materialization before creating an engine; model text is always data."""
    from improvement_cases import _digest, _fields, _frozen
    from improvement_store import _hash, _json
    from improvement_sandbox import FixtureBroker, TrialWorkspace, trial_system_prompt
    from improvement_claude import ClaudeTrialAdapter, TrialProfile
    payload = _frozen(payload)
    _fields(payload, {"version", "config_pin", "workspace_root", "receipt", "capability_hash"})
    if type(payload["version"]) is not int or payload["version"] != 1:
        raise ValueError("unsupported_trial_worker_protocol")
    _digest(payload["capability_hash"])
    receipt = payload["receipt"]
    manifest = TrialWorkspace(Path(payload["workspace_root"])).validate(receipt)
    pin = payload["config_pin"]
    if manifest["engine_config_hash"] != _hash(pin):
        raise ValueError("trial_configuration_drift")
    if native_session is None:
        if manifest['version'] in (4, 5): raise ValueError('trial_native_worker_required')
        verified = (adapter_factory or ClaudeTrialAdapter)(pin).verify()
    else:
        if manifest['version'] not in (4, 5): raise ValueError('trial_native_input4_or5_required')
        from improvement_native_worker import prepare_native_runtime
        verified, _ = await prepare_native_runtime(native_session, payload, kind='trial')
        read_control, emit = native_session.receive, native_session.send
    technical = native_session is not None and native_session._qualification
    if technical:
        if (manifest['version'] != 5 or verified.get('domain') != 'qualification'
                or verified.get('technical_ready') is not True or verified.get('supported') is not False
                or native_session._packet['qualification']['version'] != 2
                or native_session._packet['qualification']['query_binding']['authority_hash'] != payload['capability_hash']):
            raise ValueError('trial_qualification_binding_drift')
    elif not verified.get("supported") or verified.get("capability_hash") != payload["capability_hash"]:
        raise ValueError("trial_capability_drift")
    identity = {"trial_id": receipt["trial_id"], "attempt": receipt["attempt"], "input_hash": receipt["input_hash"]}
    await emit({"type": "worker_ready", **identity, "capability_hash": payload["capability_hash"]})

    async def before_query():
        await emit({"type": "engine_start_requested", **identity})
        acknowledgement = await read_control()
        expected = {"type": "engine_start_ack", **identity}
        if (_json(acknowledgement) != _json(expected) if native_session is not None else acknowledgement != expected):
            raise ValueError("trial_engine_start_not_acknowledged")

    broker = FixtureBroker(manifest["case"]["fixtures"], manifest["grant_hash"])
    instructions = trial_system_prompt(manifest)
    profile_pin = {key: pin[key] for key in ("provider", "model", "reasoning", "cli_path", "sdk_version")}
    profile = TrialProfile(profile_pin, broker, instructions, before_query=before_query)
    profile.bind_installation(manifest, receipt, payload["capability_hash"])
    if engine_factory is None:
        from claude_cli import claude_engine
        engine_factory = claude_engine
    engine = engine_factory(system_prompt=instructions, cwd=receipt["path"],
                            tag=f"improvement:{receipt['trial_id']}:{receipt['attempt']}",
                            allowed_tools=[], model=pin["model"])
    engine.trial_profile = profile
    prompt = _json({"task": manifest["case"]["task"], "fixtures": [
        {"snapshot_id": item["snapshot_id"], "source": item["source"]} for item in manifest["case"]["fixtures"]]})
    if native_session is not None:
        if technical: profile.bind_qualification_runtime(native_session, user_prompt=prompt)
        else: profile.bind_native_runtime(native_session.runtime, environment=native_session._packet['environment'], user_prompt=prompt)
    fixture_sequence = 0
    with (_sdk_hidden_processes() if native_session is None else nullcontext()):
        async for event in engine.query(prompt):
            await emit({"type": "engine_event", **identity, "event": event})
            for observation in broker.events[fixture_sequence:]:
                await emit({"type": "fixture_event", **identity, "event": observation})
            fixture_sequence = len(broker.events)
    if native_session is not None:
        # Common engine disconnect suppresses errors; this owned close cannot.
        await native_session.runtime.aclose()
    await emit({"type": "worker_complete", **identity, "fixture_events": broker.events, "tool_denials": profile.denials})


def main():
    # Read one host request before importing any engine module or starting a descendant.
    import asyncio
    import contextlib
    import json
    import sys
    maximum = 8 * 1024 * 1024
    output = sys.stdout.buffer
    sequence = 0
    native_route = False

    def read_raw():
        raw = sys.stdin.buffer.readline(maximum + 1)
        if not raw or len(raw) > maximum or not raw.endswith(b"\n"):
            raise ValueError("invalid_trial_worker_packet")
        return raw

    def read_packet():
        raw = read_raw()
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("invalid_trial_worker_packet")
        return value

    async def emit(event):
        nonlocal sequence
        sequence += 1
        raw = json.dumps({"version": 1, "sequence": sequence, **event}, ensure_ascii=False,
                         allow_nan=False, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(raw) > maximum:
            raise ValueError("trial_worker_event_too_large")
        output.write(raw)
        output.flush()

    async def read_control():
        return await asyncio.to_thread(read_packet)

    try:
        raw = read_raw()
        payload = json.loads(raw)
        if not isinstance(payload, dict): raise ValueError('invalid_trial_worker_packet')
        if payload.get('version') == 3 or payload.get('type') == 'startup3':
            native_route = True
            from improvement_native_worker import run_startup3
            with contextlib.redirect_stdout(sys.stderr):
                return asyncio.run(run_startup3(raw, entrypoint='trial'))
        if payload.get('version') == 2 or payload.get('type') == 'startup2':
            native_route = True
            from improvement_native_worker import run_startup2
            with contextlib.redirect_stdout(sys.stderr):
                return asyncio.run(run_startup2(raw, entrypoint='trial'))
        # Logs from regular engine code must never become protocol messages.
        with contextlib.redirect_stdout(sys.stderr):
            asyncio.run(run_request(payload, read_control, emit))
    except Exception as error:
        if native_route: return 1  # Private owner reports/cleans; never emit V1 on a V2 route.
        asyncio.run(emit({"type": "worker_error", "reason": "trial_worker_failed", "error_type": type(error).__name__}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
