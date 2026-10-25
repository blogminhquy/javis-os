"""One isolated worker invocation; trusted CREATE capture, no guardian association.

No runtime consumer is installed here. The outer guardian must already own the
worker/job and keep its image guard through actual job drain. ACK transport must
be cooperative async I/O; blocking stdin/to_thread readers are not supported.
"""
from __future__ import annotations

import asyncio
import inspect
import math
import os
import re
import sys
import time

_ACTIVE = None
_RETAINED = set()
_FLAGS = 0x08000006
_CREATE_KEYS = frozenset(('version', 'type', 'nonce', 'worker_pid', 'worker_birth', 'creator_thread',
    'native_pid', 'native_birth', 'native_tid', 'native_thread_birth', 'hfile', 'hprocess', 'hthread',
    'bootstrap_count', 'kill_on_exit'))
_ACK_KEYS = frozenset(('version', 'type', 'nonce', 'worker_birth', 'native_birth', 'decision'))


class NativeCaptureError(OSError):
    """Closed public error; private argv/env/callback error text is not included."""


class NativeCaptureCleanupError(NativeCaptureError):
    def __init__(self, owner):
        super().__init__('native_capture_cleanup_unproven')
        self.owner = owner


class NativeDebugInvocation:
    """Async owner of exactly one saved SDK anyio.open_process invocation.

    The returned Process is unchanged. Keep this context alive across SDK close:
    its pump must remain on the actual creator thread through continued EXIT.
    validate_create receives worker-private actual CreateProcess arguments; ACK
    receives only borrowed numeric capabilities and closed nonce/birth metadata.
    """
    def __init__(self, open_process, *, purpose, nonce, validate_create, image_ack,
            spawn_timeout=5, ack_timeout=8, drain_timeout=8):
        if not inspect.iscoroutinefunction(open_process) or not callable(validate_create) or inspect.iscoroutinefunction(validate_create):
            raise TypeError('native_capture_callable_invalid')
        if not inspect.iscoroutinefunction(image_ack):
            raise TypeError('native_capture_ack_callback_invalid')
        if type(purpose) is not str or purpose not in ('sdk_version', 'sdk_query', 'isolated_preflight'):
            raise ValueError('native_capture_purpose_invalid')
        if type(nonce) is not str or re.fullmatch('[0-9a-f]{64}', nonce) is None:
            raise ValueError('native_capture_nonce_invalid')
        for value in (spawn_timeout, ack_timeout, drain_timeout):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 60:
                raise ValueError('native_capture_deadline_invalid')
        self._opener, self.validate_create, self._image_ack = open_process, validate_create, image_ack
        self.purpose, self.nonce = purpose, nonce
        self._spawn_timeout, self._ack_timeout, self._drain_timeout = spawn_timeout, ack_timeout, drain_timeout
        self.process = None
        self.created = self.terminal = False
        self._entered = self._used = self._closed = self._restored = False
        self._api = self._winapi = self._original = self._creator = self._loop = None
        self._spawn_task = self._pump_task = self._ack_task = self._cleanup_task = None
        self._tasks = []
        self._handles = {'process': None, 'thread': None}
        self._files = []
        self._raw = None
        self._raw_returned = False
        self._pending = None
        self._event_handles = []
        self._seen_exit = self._termination_requested = self._allowed = False
        self._bootstrap = self._rearm = self._final_resume = None
        self._pump_error = None
        self._pid = self._tid = None

    @property
    def resume_counts(self): return self._bootstrap, self._rearm, self._final_resume

    @property
    def owned_handle_count(self):
        return sum(bool(value) for value in self._handles.values()) + len(self._files) + (
            len(self._raw) if self._raw and not self._raw_returned else 0)

    async def __aenter__(self):
        global _ACTIVE
        if self._entered or _ACTIVE is not None:
            raise NativeCaptureError('native_capture_scope_invalid')
        if os.name != 'nt' or not sys.flags.isolated:
            raise NativeCaptureError('native_capture_isolated_windows_required')
        from improvement_native_capture_win32 import backend
        import _winapi
        self._api, self._winapi = backend(), _winapi
        self._creator, self._loop = self._api.current_thread(), asyncio.get_running_loop()
        self._captured, self._stop, self._gate = asyncio.Event(), asyncio.Event(), asyncio.Event()
        self._original = _winapi.CreateProcess
        self._entered = True
        _ACTIVE = self
        return self

    def _same_thread(self):
        if not self._entered or self._api.current_thread() != self._creator or asyncio.get_running_loop() is not self._loop:
            raise NativeCaptureError('native_capture_creator_thread_changed')

    def _task(self, coroutine):
        task = asyncio.create_task(coroutine)
        self._tasks.append(task)
        return task

    async def _settle(self, task, timeout):
        done, _ = await asyncio.wait((task,), timeout=timeout)
        if task not in done: raise NativeCaptureError('native_capture_deadline_exceeded')
        return task.result()

    def _capture(self, *args, **kwargs):
        # Do not retain private dispatch material in metadata or public errors.
        if self._api.current_thread() != self._creator or self.created or self._stop.is_set():
            raise NativeCaptureError('native_capture_creation_refused')
        if kwargs or len(args) != 9 or type(args[5]) is not int or args[5] & _FLAGS != _FLAGS or args[5] & 0x01000000:
            raise NativeCaptureError('native_capture_creation_refused')
        try:
            valid = self.validate_create(args)
        except BaseException:
            raise NativeCaptureError('native_capture_dispatch_refused') from None
        if valid is not True:
            raise NativeCaptureError('native_capture_dispatch_refused')
        hp, ht, self._pid, self._tid = self._original(*args)
        self.created, self._raw = True, (hp, ht)
        self._captured.set()
        self._handles['process'] = self._api.duplicate(hp)
        self._handles['thread'] = self._api.duplicate(ht)
        self._raw_returned = True
        return hp, ht, self._pid, self._tid

    def _process_handle(self): return self._handles['process'] or self._raw[0]
    def _thread_handle(self): return self._handles['thread'] or self._raw[1]

    def _restore_patch(self):
        if self._restored: return
        if self._winapi.CreateProcess != self._capture:
            raise NativeCaptureError('native_capture_patch_changed')
        self._winapi.CreateProcess = self._original
        self._restored = True

    async def open_process(self, *args, **kwargs):
        self._same_thread()
        if not self._entered or self._used or self._closed:
            raise NativeCaptureError('native_capture_single_invocation_required')
        self._used = True
        flags = kwargs.get('creationflags', 0)
        if type(flags) is not int or flags & 0x01000000:
            raise NativeCaptureError('native_capture_creation_flags_invalid')
        kwargs = {**kwargs, 'creationflags': flags | _FLAGS}
        self._winapi.CreateProcess = self._capture
        self._pump_task = self._task(self._pump())
        self._spawn_task = self._task(self._opener(*args, **kwargs))
        try:
            self.process = await self._settle(self._spawn_task, self._spawn_timeout)
            self._restore_patch()
            if not self.created or self.process.pid != self._pid:
                raise NativeCaptureError('native_capture_spawn_identity_invalid')
            gate = self._task(self._gate.wait())
            await self._settle(gate, self._spawn_timeout + self._ack_timeout)
            if not self._allowed:
                raise NativeCaptureError(self._pump_error or 'native_capture_image_denied')
            return self.process
        except asyncio.CancelledError:
            await self.aclose()
            raise
        except BaseException:
            await self.aclose()
            raise NativeCaptureError(self._pump_error or 'native_capture_open_failed') from None

    def _continue(self, status=0x00010002):
        self._same_thread()
        event = self._pending
        if event is None: raise NativeCaptureError('native_capture_pending_event_missing')
        self._api.continue_event(event, status)
        self._pending = None
        if event.code == 5: self._seen_exit = True

    def _next_event(self):
        self._same_thread()
        event = self._api.next_event()
        if event is None: return None
        self._pending = event
        if event.pid != self._pid: raise NativeCaptureError('native_capture_event_identity_invalid')
        if event.code == 3:
            self._event_handles.extend((event.data.create.process, event.data.create.thread))
            if event.data.create.file: self._files.append(event.data.create.file)
        elif event.code == 6 and event.data.dll.file:
            self._files.append(event.data.dll.file)
        return event

    def _bootstrap_once(self):
        self._same_thread()
        if self._bootstrap is None:
            self._api.enable_kill()
            self._bootstrap = self._api.resume(self._thread_handle())
            if self._bootstrap != 1: raise NativeCaptureError('native_capture_bootstrap_invalid')

    def _terminate(self):
        if self.created and not self._seen_exit and not self._termination_requested:
            self._api.terminate(self._process_handle())
            self._termination_requested = True

    async def _terminal_wait(self):
        deadline = time.monotonic() + self._drain_timeout
        while not self._api.wait(self._process_handle()):
            if time.monotonic() >= deadline: raise NativeCaptureError('native_capture_terminal_unproven')
            await asyncio.sleep(.005)
        self.terminal = True

    async def _drain_native(self):
        if not self.created or self.terminal: return
        self._bootstrap_once()
        self._terminate()
        if self._pending: self._continue()
        deadline = time.monotonic() + self._drain_timeout
        while not self._seen_exit:
            event = self._next_event()
            if event is not None: self._continue()
            else:
                if time.monotonic() >= deadline: raise NativeCaptureError('native_capture_debug_exit_unproven')
                await asyncio.sleep(.005)
        await self._terminal_wait()

    def _frame(self, event):
        value = event.data.create
        process, thread = self._process_handle(), self._thread_handle()
        native_birth, thread_birth = self._api.birth(process), self._api.birth(thread, True)
        if not value.file or not value.process or not value.thread:
            raise NativeCaptureError('native_capture_create_handles_missing')
        if (self._api.process_id(value.process) != self._pid or self._api.birth(value.process) != native_birth
                or self._api.thread_owner(value.thread) != self._pid or self._api.thread_id(value.thread) != self._tid
                or self._api.birth(value.thread, True) != thread_birth):
            raise NativeCaptureError('native_capture_create_handles_mismatch')
        frame = {'version': 1, 'type': 'native_create_held', 'nonce': self.nonce,
            'worker_pid': os.getpid(), 'worker_birth': self._api.birth(self._api.current_process()),
            'creator_thread': self._creator, 'native_pid': self._pid, 'native_birth': native_birth,
            'native_tid': self._tid, 'native_thread_birth': thread_birth, 'hfile': int(value.file),
            'hprocess': int(value.process), 'hthread': int(value.thread), 'bootstrap_count': self._bootstrap,
            'kill_on_exit': True}
        if frame.keys() != _CREATE_KEYS: raise NativeCaptureError('native_capture_frame_invalid')
        return frame

    async def _creation_ack(self, event):
        frame = self._frame(event)
        self._ack_task = self._task(self._image_ack(dict(frame)))
        stopped = self._task(self._stop.wait())
        try:
            done, _ = await asyncio.wait((self._ack_task, stopped), timeout=self._ack_timeout,
                return_when=asyncio.FIRST_COMPLETED)
            if self._stop.is_set() or self._ack_task not in done:
                self._ack_task.cancel()
                raise NativeCaptureError('native_capture_ack_interrupted')
            try: ack = self._ack_task.result()
            except BaseException:
                raise NativeCaptureError('native_capture_ack_failed') from None
            if type(ack) is not dict or any(type(key) is not str for key in ack) or ack.keys() != _ACK_KEYS:
                raise NativeCaptureError('native_capture_ack_invalid')
            if (any(type(ack[key]) is not str for key in ('type', 'nonce', 'decision'))
                    or any(type(ack[key]) is not int for key in ('version', 'worker_birth', 'native_birth'))):
                raise NativeCaptureError('native_capture_ack_invalid')
            if (ack['version'] != 1 or ack['type'] != 'native_image_ack' or ack['nonce'] != self.nonce
                    or ack['worker_birth'] != frame['worker_birth'] or ack['native_birth'] != frame['native_birth']
                    or ack['decision'] not in ('allow', 'deny')):
                raise NativeCaptureError('native_capture_ack_invalid')
            if ack['decision'] != 'allow': raise NativeCaptureError('native_capture_image_denied')
            self._rearm = self._api.suspend(event.data.create.thread)
            if self._rearm != 0: raise NativeCaptureError('native_capture_rearm_invalid')
            self._continue()
            # No await between the checked ACK and final explicit resume.
            if self._stop.is_set(): raise NativeCaptureError('native_capture_ack_interrupted')
            self._final_resume = self._api.resume(event.data.create.thread)
            if self._final_resume != 1: raise NativeCaptureError('native_capture_final_resume_invalid')
            self._allowed = True
            self._gate.set()
        finally:
            stopped.cancel()
            try: await stopped
            except asyncio.CancelledError: pass

    async def _pump(self):
        try:
            await self._captured.wait()
            self._bootstrap_once()
            while not self._seen_exit:
                if self._stop.is_set():
                    await self._drain_native()
                    break
                event = self._next_event()
                if event is None:
                    await asyncio.sleep(.005)
                elif event.code == 3:
                    await self._creation_ack(event)
                elif event.code == 1:
                    code = event.data.exception.record.code
                    self._continue(0x00010002 if code in (0x80000003, 0x80000004) else 0x80010001)
                else: self._continue()
            if self.created and not self.terminal: await self._terminal_wait()
        except BaseException as error:
            self._pump_error = str(error) if type(error) is NativeCaptureError else 'native_capture_pump_failed'
            self._stop.set()
            try: await self._drain_native()
            except BaseException: pass  # State remains owned; cleanup must retry or refuse.
        finally:
            self._gate.set()

    async def _cleanup(self):
        global _ACTIVE
        self._same_thread()
        self._stop.set()
        if self._ack_task and not self._ack_task.done(): self._ack_task.cancel()
        if self._pump_task:
            if not self.created and self._spawn_task and self._spawn_task.done(): self._pump_task.cancel()
            try: await self._settle(self._pump_task, self._drain_timeout)
            except asyncio.CancelledError: pass
        await self._drain_native()
        if self._spawn_task:
            try: self.process = await self._settle(self._spawn_task, self._drain_timeout)
            except (Exception, asyncio.CancelledError):
                if not self._spawn_task.done(): raise
            if not self._restored: self._restore_patch()
        if self.created and (not self._seen_exit or not self.terminal):
            raise NativeCaptureError('native_capture_terminal_unproven')
        if self.process is not None:
            await self._settle(self._task(self.process.wait()), self._drain_timeout)
            await self._settle(self._task(self.process.aclose()), self._drain_timeout)
        if self._ack_task:
            try: await self._settle(self._ack_task, self._drain_timeout)
            except (Exception, asyncio.CancelledError):
                if not self._ack_task.done(): raise
        # Settle all task ownership before releasing source/event capabilities.
        for task in self._tasks:
            if not task.done():
                task.cancel()
                try: await self._settle(task, self._drain_timeout)
                except (Exception, asyncio.CancelledError):
                    if not task.done(): raise
        while self._files:
            self._api.close(self._files[-1]); self._files.pop()
        for key in self._handles:
            if self._handles[key]:
                self._api.close(self._handles[key]); self._handles[key] = None
        if self._raw and not self._raw_returned:
            while self._raw:
                self._api.close(self._raw[-1]); self._raw = self._raw[:-1]
        self._closed = True
        if _ACTIVE is self: _ACTIVE = None
        _RETAINED.discard(self)

    async def aclose(self):
        self._same_thread()
        if self._closed: return
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup())
        cancelled = False
        while True:
            try:
                await asyncio.shield(self._cleanup_task)
                break
            except asyncio.CancelledError:
                if self._cleanup_task.done():
                    try: self._cleanup_task.result()
                    except BaseException:
                        _RETAINED.add(self)
                        raise NativeCaptureCleanupError(self) from None
                    cancelled = True
                    break
                cancelled = True
            except BaseException:
                _RETAINED.add(self)
                raise NativeCaptureCleanupError(self) from None
        if cancelled: raise asyncio.CancelledError

    async def __aexit__(self, exc_type, exc, traceback):
        await self.aclose()
        if exc_type is None and self._pump_error:
            raise NativeCaptureError(self._pump_error)
        return False
