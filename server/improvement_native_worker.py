"""Isolated worker endpoint/runtime ownership for closed startup2/startup3.

The original guardian/host process handles authenticate the worker externally.
This owner verifies its own actual incarnation, not peer provenance or source
qualification. Configuration follows environment adoption; no client is created here.
"""
from __future__ import annotations

import asyncio
import base64
import os
from pathlib import Path, PureWindowsPath
import socket
import sys

from improvement_native_protocol import validate_startup2, worker_binding

_RETAINED = set()


class NativeWorkerError(OSError):
    def __init__(self, reason, owner):
        super().__init__(reason)
        self.owner = owner


class NativeWorkerCleanupError(NativeWorkerError):
    def __init__(self, owner): super().__init__('native_worker_cleanup_unproven', owner)


def _absolute(value):
    if (type(value) is not str or not value or '\x00' in value or len(value) > 32766
            or not PureWindowsPath(value).is_absolute()
            or any(part in ('.', '..') or part.endswith((' ', '.')) for part in value.replace('\\', '/').split('/')[1:])):
        raise ValueError('native_worker_path_invalid')
    return Path(value)


class NativeWorkerSessionV2:
    """Adopt exactly one private host endpoint and ordered image endpoints.

    Startup environment lasts for the isolated process; it is never restored to
    ambient host values. Private parent ACL/source/manifest authentication and
    complete workspace/current-authority verification remain host consumers'
    obligations. Unknown fromshare acquisition requires enclosing process drain.
    """
    def __init__(self, packet, *, namespace):
        copied = validate_startup2(packet)
        if type(namespace) is not str or namespace not in ('trial', 'operation', 'preflight') or namespace != copied['kind']:
            raise ValueError('native_worker_namespace_invalid')
        self._initialize(copied, namespace=namespace, binding=worker_binding(copied), qualification=False)

    @classmethod
    def from_startup3(cls, packet, *, namespace):
        from improvement_qualification_protocol import validate_startup3, worker_binding3
        copied = validate_startup3(packet)
        if (cls is not NativeWorkerSessionV2 or namespace not in ('preflight', 'trial') or copied['kind'] != namespace
                or (namespace == 'trial' and copied['qualification']['version'] != 2)):
            raise ValueError('qualification_preflight_required')
        self = cls.__new__(cls)
        self._initialize(copied, namespace=namespace, binding=worker_binding3(copied), qualification=True)
        return self

    def _initialize(self, packet, *, namespace, binding, qualification):
        self._packet, self._namespace, self._binding = packet, namespace, binding
        self._qualification = qualification
        self._private = self._runtime = self._loop = self._adopt_task = self._cleanup_task = None
        self._records, self._channels = [], {}
        self._runtime_owns_images = False
        self._started = self._adopted = self._closing = self._closed = self._failed = False
        self._environment_started = self._environment_installed = False
        self._scratch = self._cwd = None

    @property
    def closed(self): return self._closed

    @property
    def runtime(self):
        if not self._adopted or self._closing or self._closed or self._failed:
            raise NativeWorkerError('native_worker_runtime_unavailable', self)
        return self._runtime

    def _same_loop(self):
        if self._loop is not None and asyncio.get_running_loop() is not self._loop:
            raise NativeWorkerError('native_worker_loop_changed', self)

    def _verify_identity_and_paths(self):
        if os.name != 'nt' or not sys.flags.isolated or not sys.flags.no_site:
            raise NativeWorkerError('native_worker_isolation_required', self)
        from improvement_native_capture_win32 import backend
        api = backend()
        current = api.current_process()
        if (api.process_id(current) != os.getpid() or os.getpid() != self._packet['worker_pid']
                or api.birth(current) != self._packet['worker_birth']):
            raise NativeWorkerError('native_worker_incarnation_mismatch', self)
        if Path.cwd().resolve() != Path(__file__).resolve().parent:
            raise NativeWorkerError('native_worker_launch_directory_mismatch', self)
        names = ('HOME', 'USERPROFILE', 'TEMP', 'TMP', 'APPDATA', 'LOCALAPPDATA')
        initial = [os.environ.get(name) for name in names]
        scratch = _absolute(initial[0])
        if any(type(value) is not str or _absolute(value) != scratch for value in initial):
            raise NativeWorkerError('native_worker_initial_scratch_mismatch', self)
        if not scratch.is_dir(): raise NativeWorkerError('native_worker_scratch_unavailable', self)
        # Observe ordinary directory ancestry only; do not claim ACL authority.
        for path in (scratch, *scratch.parents):
            status = path.lstat()
            if path.is_symlink() or getattr(status, 'st_file_attributes', 0) & 0x400:
                raise NativeWorkerError('native_worker_scratch_linked', self)
        env = self._packet['environment']
        if self._qualification:
            from improvement_blobs import check_ancestry
            home = _absolute(env['HOME']); check_ancestry(home)
            if not home.is_dir() or tuple(home.iterdir()):
                raise NativeWorkerError('qualification_home_not_empty', self)
        if self._namespace == 'preflight':
            expected = {'TEMP': 'tmp', 'TMP': 'tmp', 'JAVIS_STATE_DIR': 'host-state', 'BRAINS_DIR': 'empty-brains',
                'OBSIDIAN_VAULT_PATH': 'empty-vault', 'BRAIN_PATH': 'empty-brain', 'SOURCES_PATH': 'empty-sources'}
            if any(_absolute(env[key]) != scratch / leaf for key, leaf in expected.items()):
                raise NativeWorkerError('native_worker_preflight_scratch_mismatch', self)
            cwd = scratch
        else:
            cwd = _absolute(self._packet['request']['receipt']['path'])
        self._scratch, self._cwd = str(scratch), str(cwd)

    def _fromshare(self, name, blob):
        record = dict(name=name, state='acquiring', socket=None, channel=None,
            acquisition_unknown=True, close_succeeded=False, close_authority_lost=False)
        self._records.append(record)
        # No await or thread handoff. An exception before the return is stored
        # leaves acquisition UNKNOWN, even if CPython might have closed a socket.
        record['socket'] = socket.fromshare(base64.b64decode(blob, validate=True))
        record['acquisition_unknown'] = False
        record['state'] = 'raw_owned'
        return record

    async def _adopt_owned(self):
        if self._closing: raise NativeWorkerError('native_worker_closing', self)
        self._verify_identity_and_paths()
        self._environment_started = True
        os.environ.clear()
        os.environ.update(self._packet['environment'])
        self._environment_installed = True
        # These modules are pure on import. No SDK/application configuration is
        # imported before installing the authenticated startup environment.
        from improvement_private_channel import PrivateWorkerChannelV2
        from improvement_image_channel import ImageMetadataChannel
        from improvement_native_sdk import NativeInvocationSet
        record = self._fromshare('private', self._packet['private_share'])
        private = PrivateWorkerChannelV2(record['socket'], binding=self._binding, role='worker')
        record['channel'], record['state'] = private, 'channel_owned'
        self._private = private
        for item in self._packet['images']:
            record = self._fromshare(item['purpose'], item['share'])
            channel = ImageMetadataChannel(record['socket'], role='worker', nonce=item['nonce'],
                worker_pid=self._packet['worker_pid'], worker_birth=self._packet['worker_birth'])
            record['channel'], record['state'] = channel, 'channel_owned'
            self._channels[item['purpose']] = channel
        if self._qualification:
            self._runtime = NativeInvocationSet.from_qualification_worker(self)
        else:
            self._runtime = NativeInvocationSet(self._packet['request']['config_pin'], image_channels=self._channels,
                emit_dispatch=self._emit_dispatch, environment=self._packet['environment'], cwd=self._cwd,
                source_policy_hash=self._packet['request']['config_pin']['profile_hash'])
        self._runtime_owns_images = True
        await self._private.send({'type': 'endpoints_adopted'})
        if self._closing: raise NativeWorkerError('native_worker_closing', self)
        self._adopted = True
        return self

    async def adopt(self):
        if self._started or self._closing or self._closed:
            raise NativeWorkerError('native_worker_adoption_refused', self)
        self._started = True
        self._loop = asyncio.get_running_loop()
        self._adopt_task = asyncio.create_task(self._adopt_owned())
        try:
            done, _ = await asyncio.wait((self._adopt_task,), timeout=15)
            if self._adopt_task not in done or self._adopt_task.cancelled():
                raise NativeWorkerError('native_worker_adoption_unproven', self)
            return self._adopt_task.result()
        except BaseException as error:
            self._failed = True
            await self.aclose()
            if isinstance(error, asyncio.CancelledError): raise
            raise NativeWorkerError('native_worker_adoption_failed', self) from None

    async def _operate(self, direction, body=None):
        self._same_loop()
        if not self._adopted or self._closing or self._closed or self._failed:
            raise NativeWorkerError('native_worker_channel_unavailable', self)
        try:
            result = await (self._private.send(body) if direction == 'send' else self._private.receive())
            return result['body']
        except BaseException as error:
            self._failed = True
            await self.aclose()
            if isinstance(error, asyncio.CancelledError): raise
            raise NativeWorkerError('native_worker_channel_failed', self) from None

    async def send(self, body): return await self._operate('send', body)
    async def receive(self): return await self._operate('receive')

    async def _emit_dispatch(self, body):
        self._same_loop()
        if not self._adopted or self._closing or self._closed or self._failed:
            raise NativeWorkerError('native_worker_dispatch_unavailable', self)
        try:
            return (await self._private.send(body))['body']
        except BaseException as error:
            # This callback runs inside the runtime's active CREATE gate.
            # Worker close would wait runtime close and this SAME callback.
            # Let capture/runtime unwind first; outer worker finally owns close.
            self._failed = True
            if isinstance(error, asyncio.CancelledError): raise
            raise NativeWorkerError('native_worker_dispatch_failed', self) from None

    def _close_raw(self, record):
        if record['state'] == 'channel_owned' or record['close_succeeded']: return
        sock = record['socket']
        if sock is None: return
        if record['close_authority_lost'] or sock.fileno() < 0:
            record['close_authority_lost'] = True
            raise NativeWorkerCleanupError(self)
        try: sock.close()
        except BaseException:
            if sock.fileno() < 0: record['close_authority_lost'] = True
            raise
        if sock.fileno() >= 0: raise NativeWorkerCleanupError(self)
        record['close_succeeded'], record['state'] = True, 'closed'

    async def _cleanup(self):
        self._closing = True
        errors = []
        # Close metadata I/O to wake an owned adopt/send/receive. It does not
        # provide the guardian's independent native/job drain observation.
        if self._private is not None:
            try: await self._private.aclose()
            except BaseException as error: errors.append(error)
        if self._adopt_task is not None:
            done, _ = await asyncio.wait((self._adopt_task,), timeout=8)
            if self._adopt_task not in done or self._adopt_task.cancelled(): errors.append('adopt_completion_unknown')
            elif self._adopt_task.done():
                try: self._adopt_task.result()
                except BaseException: pass
        if self._runtime is not None:
            try: await self._runtime.aclose()
            except BaseException as error: errors.append(error)
        if not self._runtime_owns_images:
            for channel in self._channels.values():
                try: await channel.aclose()
                except BaseException as error: errors.append(error)
        for record in self._records:
            try: self._close_raw(record)
            except BaseException as error: errors.append(error)
            if record['acquisition_unknown']: errors.append('socket_acquisition_unknown')
            if record['state'] == 'channel_owned' and not record['channel'].closed:
                errors.append('channel_completion_unknown')
        if errors: raise NativeWorkerCleanupError(self)
        self._closed = True
        _RETAINED.discard(self)

    async def aclose(self):
        self._same_loop()
        if self._closed: return
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup())
        interrupted = False
        while True:
            try:
                await asyncio.shield(self._cleanup_task)
                break
            except asyncio.CancelledError:
                interrupted = True
                if self._cleanup_task.cancelled():
                    _RETAINED.add(self)
                    raise NativeWorkerCleanupError(self) from None
            except BaseException:
                _RETAINED.add(self)
                raise NativeWorkerCleanupError(self) from None
        if interrupted: raise asyncio.CancelledError

    async def __aenter__(self): return await self.adopt()
    async def __aexit__(self, *args): await self.aclose()


async def prepare_native_runtime(session, payload, *, kind):
    """Admit before any CLI, then verify actual guarded child observations."""
    from improvement_native_protocol import _canonical
    if (type(session) is not NativeWorkerSessionV2 or session._namespace != kind
            or session._packet['kind'] != kind
            or _canonical(payload) != _canonical(session._packet['request'])):
        raise ValueError('native_worker_request_unbound')
    runtime = session.runtime  # Also requires completed adoption on the same owner.
    if session._qualification:
        from improvement_claude import _runtime_identity
        from improvement_qualification_protocol import validate_technical_observation
        if (not session._environment_installed or runtime._preflight_started or runtime._entries
                or runtime._transport is not None or runtime._used):
            raise PermissionError('qualification_runtime_already_started')
        # Application imports (notably config's UTF-8 initialization) may add
        # process defaults. This isolated owner reinstalls its exact adopted
        # environment before observations/client construction; no ambient value
        # or caller override can enter the technical child environment.
        os.environ.clear()
        os.environ.update(session._packet['environment'])
        pin = payload['config_pin']
        if kind not in ('preflight', 'trial'): raise PermissionError('qualification_query_forbidden')
        if kind == 'trial' and session._packet['qualification']['version'] != 2:
            raise PermissionError('qualification_query_binding_required')
        static = _runtime_identity(pin)
        if (static.get('platform') != sys.platform or static.get('managed_policy') != 'absent'
                or any(static.get(name) != pin[name] for name in ('cli_hash', 'sdk_version', 'profile_hash'))):
            raise PermissionError('qualification_runtime_drift')
        observed = validate_technical_observation(await runtime.preflight(managed_policy='absent'), pin=pin)
        return {'supported': False, 'account_ready': False, 'domain': 'qualification', 'technical_ready': True}, observed
    from improvement_claude import ClaudeTrialAdapter
    adapter = ClaudeTrialAdapter(payload['config_pin'])
    admission = adapter.admit_preflight()
    if admission.get('admitted') is not True: raise ValueError('native_preflight_not_admitted')
    observed = await runtime.preflight(managed_policy=admission['runtime']['managed_policy'])
    verified = adapter.verify_observed(observed)
    if (verified.get('supported') is not True or (kind != 'preflight'
            and verified.get('capability_hash') != payload['capability_hash'])):
        raise ValueError('native_worker_capability_drift')
    return verified, observed


async def run_startup2(raw, *, entrypoint):
    """Fixed entrypoint consumer; initial raw bytes retain strict wire grammar."""
    from improvement_native_protocol import decode_startup2
    packet = decode_startup2(raw)
    kind = packet['kind']
    if (entrypoint not in ('trial', 'operation') or kind not in
            (('trial', 'preflight') if entrypoint == 'trial' else ('operation',))):
        raise ValueError('native_worker_entrypoint_mismatch')
    owner = NativeWorkerSessionV2(packet, namespace=kind)
    return await _run_owned(owner, packet)


async def run_startup3(raw, *, entrypoint):
    from improvement_qualification_protocol import decode_startup3
    packet = decode_startup3(raw)
    if entrypoint != 'trial' or packet['kind'] not in ('preflight', 'trial'):
        raise ValueError('qualification_preflight_required')
    owner = NativeWorkerSessionV2.from_startup3(packet, namespace=packet['kind'])
    return await _run_owned(owner, packet)


async def _run_owned(owner, packet):
    kind = packet['kind']
    try:
        await owner.adopt()  # Installs exact environment before application imports.
        if kind == 'preflight':
            _, observed = await prepare_native_runtime(owner, packet['request'], kind=kind)
            await owner.runtime.aclose()
            await owner.send({'type': 'preflight_complete', 'runtime': observed})
        else:
            if kind == 'trial':
                from improvement_worker import run_request
            else:
                from improvement_operation_worker import run_request
            await run_request(packet['request'], owner.receive, owner.send, native_session=owner)
    except Exception as error:
        if owner._adopted and not owner.closed:
            try:
                await owner.send({'type': 'worker_error', 'reason': kind + '_worker_failed',
                    'error_type': type(error).__name__})
            except Exception:
                pass  # Never invent delivery; outer owner still must close.
        raise
    finally:
        await owner.aclose()
    return 0
