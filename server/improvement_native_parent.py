"""Actual parent preflight/query ownership under existing M0 authority.

The release registry authenticates declared source/runtime/import content. Native
image/lifetime owners establish their documented observations; neither hashes nor
these records claim loaded-page identity, provider acceptance or comprehension.
"""
from __future__ import annotations

import asyncio
from contextlib import aclosing, closing
import hashlib
import inspect
from pathlib import Path
import secrets
import subprocess
import tempfile
import time

import improvement_store as IM
from improvement_blobs import MAX_ASSET_BYTES
from improvement_native_decisions import NativeImageDecisionStore, attempt_scope
from improvement_native_protocol import _canonical, _digest, _fields, _parse
from improvement_native_release import qualified_launch
from improvement_native_transport import GuardianSessionV2, execute_worker_v2
from improvement_sandbox import worker_environment

_RETAINED_SCRATCH = set()
_PURPOSES = ('adapter_version', 'auth_status', 'sdk_version', 'query')


def _sha(value): return hashlib.sha256(value.encode('utf-8')).hexdigest()


async def _settled(coroutine):
    from improvement_claude import _settled_owned
    results, interrupted = await _settled_owned(asyncio.gather(asyncio.create_task(coroutine), return_exceptions=True))
    if isinstance(results[0], BaseException): raise results[0]
    if interrupted is not None: raise interrupted
    return results[0]


def _dispatch(joined, pin, environment, cwd, query_policy):
    """Recheck captured summary against this exact host-selected launch scope."""
    dispatch, purpose = joined['dispatch'], joined['purpose']
    _fields(dispatch, {'version', 'purpose', 'basis', 'argument_consistency', 'environment_hash', 'source_policy_hash'})
    expected_environment = (dict(environment) if purpose != 'query' else {**environment,
        'CLAUDE_CODE_ENTRYPOINT': 'sdk-py', 'CLAUDE_AGENT_SDK_VERSION': pin['sdk_version'], 'PWD': cwd})
    if (dispatch['version'] != 1 or dispatch['basis'] != 'native_argument_consistency'
            or dispatch['source_policy_hash'] != pin['profile_hash']
            or dispatch['environment_hash'] != IM._hash(expected_environment)
            or joined['image']['comparison']['selected']['sha256'] != pin['cli_hash']):
        raise ValueError('native_parent_dispatch_drift')
    actual = dispatch['argument_consistency']
    if purpose != 'query':
        argv = [pin['cli_path'], *{'adapter_version': ['--version'], 'auth_status': ['auth', 'status', '--json'],
            'sdk_version': ['-v']}[purpose]]
        expected = {'version': 1, 'argv_hash': IM._hash(argv),
            'command_line_hash': _sha(subprocess.list2cmdline(argv)), 'cwd_hash': _sha(cwd), 'creationflags': 0x08000006}
        if _canonical(actual) != _canonical(expected): raise ValueError('native_parent_dispatch_drift')
        return
    if query_policy is None: raise ValueError('native_parent_query_forbidden')
    _fields(actual, {'version', 'verdict', 'basis', 'model', 'reasoning', 'prompt_hash', 'tools', 'argv_hash',
        'command_line_hash', 'cli_path_hash', 'cwd_hash', 'settings_hash', 'mcp_config_hash', 'expected_hash',
        'creationflags', 'coverage', 'tool_policy'})
    servers = ('fixture', 'skill') if query_policy['tool_policy'] == 'pinned_skill' else ('fixture',)
    expected = {'version': 2, 'verdict': 'pass', 'basis': 'query_argument_consistency',
        **{key: query_policy[key] for key in ('model', 'reasoning', 'prompt_hash', 'tools', 'tool_policy')},
        'cli_path_hash': _sha(pin['cli_path']), 'cwd_hash': _sha(cwd), 'expected_hash': IM._hash(query_policy),
        'settings_hash': IM._hash({'fastMode': False, 'disableAllHooks': True}),
        'mcp_config_hash': IM._hash({'mcpServers': {name: {'type': 'sdk', 'name': name} for name in servers}}),
        'creationflags': 0x08000006, 'coverage': dict.fromkeys(
            ('os_boundary', 'image', 'provider_acceptance', 'internal_reasoning'), 'unknown')}
    if any(_canonical(actual[key]) != _canonical(value) for key, value in expected.items()):
        raise ValueError('native_parent_dispatch_drift')
    for key in ('argv_hash', 'command_line_hash'): _digest(actual[key])


class NativeParentBoundary:
    def __init__(self, pin, assets, principal, *, scope_hash, current, lock=None):
        if type(assets) is not IM.ImprovementStore:
            raise TypeError('concrete_native_parent_store_required')
        IM._brain(principal); _digest(scope_hash)
        if (not callable(current) or inspect.iscoroutinefunction(current)
                or inspect.iscoroutinefunction(getattr(current, '__call__', None))
                or (lock is not None and type(lock) is not asyncio.Lock)):
            raise ValueError('native_parent_authority_required')
        self.pin = _parse(_canonical(pin))
        self.assets, self.principal, self.scope_hash = assets, principal, scope_hash
        self.current, self.lock = current, lock
        self.decisions = NativeImageDecisionStore(assets)
        self._verification_started = self._query_started = False
        self._qualification = None

    @classmethod
    def for_qualification(cls, session):
        from improvement_qualification_session import QualificationSession
        if cls is not NativeParentBoundary or type(session) is not QualificationSession:
            raise TypeError('concrete_qualification_session_required')
        session._assert_native_current()
        if session._native_parent is not None: raise PermissionError('qualification_preflight_already_used')
        self = cls.__new__(cls)
        self._qualification = session
        self.pin = _parse(_canonical(session._pin))
        self.assets, self.principal = session.assets, session.principal
        self.scope_hash = IM._hash({'version': 1, 'domain': 'qualification',
            'run_hash': session.run_hash, 'phase': 'preflight'})
        self.current, self.lock = None, None
        self.decisions = NativeImageDecisionStore(self.assets)
        self._verification_started = self._query_started = False
        self._guardian = self._scratch = self._qualification_seed = None
        self._qualification_packets, self._qualification_joined = {}, {}
        self._qualification_complete = self._evidence_settled = False
        self._owner_state = 'PREPARED'
        self._close_lock = asyncio.Lock()
        session._native_started, session._native_parent = True, self
        return self

    async def _serialized(self, callback):
        if self.lock is None: return await _settled(asyncio.to_thread(callback))
        async with self.lock:
            return await _settled(asyncio.to_thread(callback))

    @classmethod
    def for_qualification_query(cls, session, binding):
        from improvement_qualification_session import QualificationSession
        if cls is not NativeParentBoundary or type(session) is not QualificationSession:
            raise TypeError('concrete_qualification_session_required')
        context = session._query_current(binding)
        if context['boundary'] is not None: raise PermissionError('qualification_query_already_used')
        self = cls.__new__(cls)
        self._qualification, self._query_binding = session, binding
        self.pin = _parse(_canonical(session._pin))
        self.assets, self.principal = session.assets, session.principal
        self.scope_hash = attempt_scope(kind='trial', brain_id=session.principal.brain_id,
            receipt=context['receipt'], config_pin=self.pin, capability_hash=binding.authority_hash)
        self.current, self.lock = None, None
        self.decisions = NativeImageDecisionStore(self.assets)
        self._verification_started = self._query_started = False
        self._guardian = self._scratch = self._qualification_seed = None
        self._qualification_packets, self._qualification_joined = {}, {}
        self._qualification_complete = self._evidence_settled = False
        self._owner_state = 'PREPARED'
        self._close_lock = asyncio.Lock()
        self._ack_witness = None
        context['boundary'] = self
        return self

    def _assert_query_current(self, *, connection=None):
        if hasattr(self, '_query_binding'):
            return self._qualification._query_current(self._query_binding, connection=connection)
        self._qualification._assert_native_current(connection=connection)

    def _ack_accounting(self):
        from improvement_telemetry import NativeUsageRecorder
        context = self._assert_query_current()
        recorder = context.get('recorder')
        with closing(self.assets.store._conn()) as connection:
            attempt = connection.execute('SELECT * FROM improvement_trial_attempts WHERE trial_id=? AND attempt=?',
                (self._query_binding.subject_id, self._query_binding.attempt)).fetchone()
            call = connection.execute('SELECT * FROM agent_calls WHERE id=?', (context['link']['call_id'],)).fetchone()
            if (type(recorder) is not NativeUsageRecorder or attempt['status'] != 'running' or call['status'] != 'running'
                    or call['engine_at'] is None or call['engine_at'] != attempt['engine_at']):
                raise PermissionError('qualification_accounting_uncommitted')
            self._assert_query_current(connection=connection)
            return {'call_id': call['id'], 'engine_at': call['engine_at']}

    async def _current(self):
        def check():
            with self.assets.store._Tx(self.assets.store) as connection:
                if self._qualification is not None:
                    self._assert_query_current(connection=connection)
                    return
                if self.current(connection, None) != 'allow':
                    raise PermissionError('native_parent_authority_changed')
        await self._serialized(check)

    def _persist(self, *, environment, cwd, scope_hash, query_policy=None):
        environment, pin = dict(environment), self.pin
        async def persist(joined):
            def current(connection, value):
                _dispatch(value, pin, environment, cwd, query_policy)
                if self._qualification is not None:
                    purposes = _PURPOSES if hasattr(self, '_query_binding') else _PURPOSES[:2]
                    if value['purpose'] not in purposes: raise PermissionError('qualification_query_forbidden')
                    self._assert_query_current(connection=connection)
                    return 'allow'
                return self.current(connection, value)
            if self._qualification is not None:
                self._qualification_joined[joined['purpose']] = _parse(_canonical(joined))
            return await self._serialized(lambda: self.decisions.persist(self.principal, joined,
                scope_hash=scope_hash, current=current))
        return persist

    def _save_preflight(self, nonce, packets):
        raw = _canonical(packets)
        digest = hashlib.sha256(raw).hexdigest()
        payload = {'scope_hash': self.scope_hash, 'launch_nonce': nonce, 'trace_hash': digest,
                   'engine_config_hash': IM._hash(self.pin)}
        identity = [self.scope_hash, nonce]
        if self._qualification is not None: identity.append(digest)
        key = 'native-preflight:' + IM._hash(identity)
        with self.assets.store._Tx(self.assets.store) as connection:
            previous = self.assets._replay(connection, IM._brain(self.principal), key, 'native_preflight_evidence', payload)
            if previous is not None: return previous
            hashes = [self.assets.blobs.write(IM._brain(self.principal), raw[offset:offset + MAX_ASSET_BYTES])
                for offset in range(0, len(raw), MAX_ASSET_BYTES)]
            record = {'version': 1, **payload, 'blob_hashes': hashes}
            self.assets._event(connection, self.principal, key, 'native_preflight_evidence', payload, record)
            return record

    def _check_qualification_start(self, guardian):
        from improvement_qualification_session import QualificationSession
        from improvement_blobs import check_ancestry
        from improvement_qualification_environment import validate_dummy_environment
        session = self._qualification
        if (type(session) is not QualificationSession or self._guardian is not guardian
                or session._native_boundaries.get(guardian) is not self or guardian not in session._owners
                or self._owner_state != 'ATTACHED' or self._qualification_seed is None):
            raise PermissionError('qualification_native_owner_foreign')
        session._assert_native_current()
        if hasattr(self, '_query_binding'):
            context = self._assert_query_current()
            seed = self._qualification_seed
            environment = validate_dummy_environment(seed['environment'])
            scratch, home = Path(self._scratch.name), Path(environment['HOME'])
            for path in (scratch, home): check_ancestry(path)
            if (seed['kind'] != 'trial' or seed['request'] != self._query_start_request
                    or seed['qualification'] != self._query_start_qualification
                    or not scratch.is_dir() or not scratch.is_relative_to(session.root)
                    or not home.is_dir() or home.parent != session.root / 'homes' or tuple(home.iterdir())
                    or guardian._policy['scratch'] != str(scratch)
                    or seed['request']['receipt'] != context['receipt']):
                raise PermissionError('qualification_query_start_changed')
            return _parse(_canonical(seed))
        seed = self._qualification_seed
        environment = validate_dummy_environment(seed['environment'])
        scratch, home = Path(self._scratch.name), Path(environment['HOME'])
        for path in (scratch, home): check_ancestry(path)
        if (not scratch.is_dir() or not scratch.is_relative_to(session.root)
                or not home.is_dir() or home.parent != session.root / 'homes' or tuple(home.iterdir())
                or environment['USERPROFILE'] != str(home)
                or environment['APPDATA'] != str(home / 'AppData' / 'Roaming')
                or environment['LOCALAPPDATA'] != str(home / 'AppData' / 'Local')
                or seed['qualification']['scope'] != session.scope()
                or seed['qualification']['run_hash'] != session.run_hash
                or seed['qualification']['environment_hash'] != IM._hash(environment)
                or seed['qualification']['attempt_link'] is not None
                or seed['request'] != {'version': 1, 'config_pin': self.pin}
                or guardian._policy['scratch'] != str(scratch)):
            raise PermissionError('qualification_home_inconsistent')
        expected = {'TEMP': 'tmp', 'TMP': 'tmp', 'JAVIS_STATE_DIR': 'host-state', 'BRAINS_DIR': 'empty-brains',
            'OBSIDIAN_VAULT_PATH': 'empty-vault', 'BRAIN_PATH': 'empty-brain', 'SOURCES_PATH': 'empty-sources'}
        if any(Path(environment[name]) != scratch / leaf for name, leaf in expected.items()):
            raise PermissionError('qualification_workspace_foreign')
        return _parse(_canonical(seed))

    def _retain_qualification_packets(self, packets):
        for packet in packets:
            packet = _parse(_canonical(packet)); sequence = packet['sequence']
            previous = self._qualification_packets.get(sequence)
            if previous is not None and previous != packet: raise ValueError('qualification_trace_changed')
            self._qualification_packets[sequence] = packet

    async def _close_qualification(self):
        async with self._close_lock:
            owner = self._guardian
            if owner is None or self._owner_state == 'DETACHED': return
            self._owner_state = 'CLOSING'
            error = None
            try: await _settled(owner.aclose())
            except BaseException as caught: error = caught
            self._evidence_settled = False
            try:
                self._retain_qualification_packets(owner.closing_observations)
                packets = [self._qualification_packets[key] for key in sorted(self._qualification_packets)]
                self._trace_record = await _settled(asyncio.to_thread(self._save_preflight, owner._nonce, packets))
                self._evidence_settled = True
            except BaseException as caught:
                if error is None: error = caught
            if owner.closed is True and self._evidence_settled:
                self._owner_state = 'DRAINED'
                try:
                    self._scratch.cleanup()
                    self._qualification._detach_native(owner, self)
                except BaseException as caught:
                    self._evidence_settled = False
                    if error is None: error = caught
            if self._owner_state != 'DETACHED': self._owner_state = 'RETAINED_UNKNOWN'
            if error is not None: raise error

    async def verify_qualification(self):
        from improvement_qualification_protocol import validate_technical_observation
        from improvement_qualification_session import QualificationPreflight
        session = self._qualification
        if session is None or self._verification_started:
            raise PermissionError('qualification_preflight_already_used')
        self._verification_started = True
        session._assert_native_current()
        self._scratch = tempfile.TemporaryDirectory(prefix='preflight-', dir=session.root)
        self._scratch._finalizer.detach()  # The retained Session map is the lifetime owner.
        nonce, runtime, error = secrets.token_hex(32), None, None
        try:
            launch = await _settled(asyncio.to_thread(session._preflight_launch, self._scratch.name))
            environment = session.environment(self._scratch.name)
            self._qualification_seed = {'kind': 'preflight', 'request': {'version': 1, 'config_pin': self.pin},
                'environment': environment, 'qualification': {'version': 1, 'run_hash': session.run_hash,
                    'scope': session.scope(), 'environment_hash': IM._hash(environment), 'attempt_link': None}}
            remaining = session._scope['deadline_at'] - time.time()
            if remaining <= 0: raise PermissionError('qualification_session_expired')
            self._guardian = GuardianSessionV2(launch['guardian_manifest'], launch['policy'], image_policy=launch['image_policy'],
                fences=[str(Path(self._scratch.name) / 'admission.lock'), str(Path(self._scratch.name) / 'preflight.lock')],
                launch_nonce=nonce, invocations=[{'purpose': purpose, 'nonce': secrets.token_hex(32)} for purpose in _PURPOSES[:2]],
                persist_before_allow=self._persist(environment=environment, cwd=self._scratch.name, scope_hash=self.scope_hash),
                timeout=30, close_timeout=8, lifetime_timeout=min(60, remaining))
            session._attach_native(self._guardian, self)
            await self._guardian.start_qualification(self)
            self._owner_state = 'ACTIVE'
            while True:
                packet = await self._guardian.receive()
                self._retain_qualification_packets((packet,))
                if packet['body']['type'] == 'worker_error': raise RuntimeError('qualification_preflight_worker_failed')
                if packet['body']['type'] == 'preflight_complete':
                    runtime = packet['body']['runtime']; break
        except BaseException as caught:
            error = caught
        finally:
            if self._guardian is not None and session._native_boundaries.get(self._guardian) is self:
                try: await self._close_qualification()
                except BaseException as caught:
                    if error is None: error = caught
            else:
                self._scratch.cleanup()
        if error is not None: raise error
        owner = self._guardian
        if (runtime is None or owner.closed is not True or not owner.native_drained or not owner._worker_complete
                or any(type(status) is not int or status != 0 for status in
                    (getattr(owner, '_worker_exit_code', None), getattr(owner, '_guardian_exit_code', None)))
                or owner._allowed != set(_PURPOSES[:2]) or self._owner_state != 'DETACHED'):
            raise RuntimeError('qualification_preflight_cleanup_unproven')
        observed = validate_technical_observation(runtime, pin=self.pin)
        decisions = []
        for purpose in _PURPOSES[:2]:
            joined = self._qualification_joined.get(purpose)
            if joined is None: raise PermissionError('qualification_decisions_required')
            decision = self.decisions.read(self.principal, joined, scope_hash=self.scope_hash)
            if decision['decision'] != 'allow': raise PermissionError('qualification_decisions_required')
            decisions.append(decision['durable_evidence_hash'])
        await self._current()
        self._result_fields = {'version': 1, 'domain': 'qualification', 'supported': False, 'account_ready': False,
            'technical_ready': True, 'run_hash': session.run_hash, 'pin_hash': IM._hash(self.pin),
            'release_fingerprint': session._scope['release_fingerprint'], 'review_hash': session._scope['review_hash'],
            'launch_nonce': nonce, 'environment_hash': IM._hash(environment), 'observation_hash': IM._hash(observed),
            'trace_hash': self._trace_record['trace_hash'], 'decision_hashes': tuple(decisions), 'cleanup': 'proven'}
        self._qualification_complete = True
        return QualificationPreflight._from_parent(self)

    @staticmethod
    def _scratch_close(scratch, error):
        owner = getattr(error, 'owner', None)
        if owner is not None and not owner.closed:
            _RETAINED_SCRATCH.add(scratch)
        else:
            scratch.cleanup()

    async def verify(self, adapter):
        if self._qualification is not None: raise PermissionError('qualification_product_forbidden')
        if self._verification_started: raise ValueError('native_parent_preflight_already_used')
        self._verification_started = True
        admission = await _settled(asyncio.to_thread(adapter.admit_preflight))
        if type(admission) is not dict or admission.get('admitted') is not True:
            return {'supported': False, 'reason': admission.get('reason') if type(admission) is dict else 'native_preflight_refused',
                'requested': {key: self.pin[key] for key in ('provider', 'engine_id', 'model', 'reasoning')}}
        scratch = tempfile.TemporaryDirectory(prefix='jnp-')
        owner, error, packets, runtime = None, None, [], None
        nonce = secrets.token_hex(32)
        try:
            launch = await _settled(asyncio.to_thread(qualified_launch, self.pin, kind='preflight', scratch=scratch.name))
            await self._current()
            environment = worker_environment(Path(scratch.name))
            owner = GuardianSessionV2(launch['guardian_manifest'], launch['policy'], image_policy=launch['image_policy'],
                fences=[str(Path(scratch.name) / 'admission.lock'), str(Path(scratch.name) / 'preflight.lock')],
                launch_nonce=nonce, invocations=[{'purpose': purpose, 'nonce': secrets.token_hex(32)} for purpose in _PURPOSES[:2]],
                persist_before_allow=self._persist(environment=environment, cwd=scratch.name, scope_hash=self.scope_hash),
                timeout=30, close_timeout=8, lifetime_timeout=60)
            await owner.start({'kind': 'preflight', 'request': {'version': 1, 'config_pin': self.pin}, 'environment': environment})
            while True:
                packet = await owner.receive()
                packets.append(packet)
                if packet['body']['type'] == 'worker_error': raise RuntimeError('native_preflight_worker_failed')
                if packet['body']['type'] == 'preflight_complete':
                    runtime = packet['body']['runtime']
                    break
        except BaseException as caught:
            error = caught
        finally:
            if owner is not None:
                try:
                    await _settled(owner.aclose())
                except BaseException as caught:
                    error = caught
                packets.extend(owner.closing_observations)
                try:
                    await _settled(asyncio.to_thread(self._save_preflight, nonce, packets))
                except BaseException as caught:
                    if error is None: error = caught
            self._scratch_close(scratch, error)
        if error is not None: raise error
        if runtime is None or any(type(status) is not int or status != 0 for status in
                (owner._worker_exit_code, owner._guardian_exit_code)):
            raise RuntimeError('native_preflight_exit_failed')
        return await _settled(asyncio.to_thread(adapter.verify_observed, runtime))

    async def execute(self, kind, request, receipt, *, adapter, workspace_root, brain_id,
            before_engine_start, system_prompt, tool_policy, on_closing_observations):
        if self._qualification is not None: raise PermissionError('qualification_product_forbidden')
        if (type(kind) is not str or type(tool_policy) is not str or not (
                (kind == 'trial' and tool_policy in ('pinned_skill', 'baseline_inline'))
                or (kind == 'operation' and tool_policy == 'fixture_only'))):
            raise ValueError('native_parent_query_policy_invalid')
        if self._query_started: raise ValueError('native_parent_query_already_used')
        self._query_started = True
        if not inspect.iscoroutinefunction(on_closing_observations):
            raise ValueError('native_parent_closing_evidence_required')
        admission = await _settled(asyncio.to_thread(adapter.admit_preflight))
        if type(admission) is not dict or admission.get('admitted') is not True:
            raise ValueError('native_parent_query_unqualified')
        scope = attempt_scope(kind=kind, brain_id=brain_id, receipt=receipt, config_pin=self.pin,
                              capability_hash=request['capability_hash'])
        scratch, error = tempfile.TemporaryDirectory(prefix='jnq-'), None
        try:
            launch = await _settled(asyncio.to_thread(qualified_launch, self.pin, kind=kind, scratch=scratch.name))
            await self._current()
            environment = worker_environment(Path(receipt['path']))
            tools = ['mcp__fixture__fixture_read'] + (['mcp__skill__skill_asset_read'] if tool_policy == 'pinned_skill' else [])
            policy = {'version': 2, **{key: self.pin[key] for key in ('cli_path', 'model', 'reasoning')},
                'prompt_hash': _sha(system_prompt), 'cwd': receipt['path'], 'tools': tools, 'tool_policy': tool_policy}
            async with aclosing(execute_worker_v2(kind, request, receipt, config_pin=self.pin,
                    workspace_root=workspace_root, brain_id=brain_id, before_engine_start=before_engine_start,
                    **{key: launch[key] for key in ('guardian_manifest', 'policy', 'image_policy')},
                    launch_nonce=secrets.token_hex(32), invocations=[{'purpose': purpose, 'nonce': secrets.token_hex(32)} for purpose in _PURPOSES],
                    persist_before_allow=self._persist(environment=environment, cwd=receipt['path'], scope_hash=scope, query_policy=policy),
                    on_closing_observations=on_closing_observations, environment=environment)) as packets:
                async for packet in packets: yield packet
        except BaseException as caught:
            error = caught
            raise
        finally:
            self._scratch_close(scratch, error)

    async def execute_qualification(self, binding, *, owner, principal, identifier, expected_generation,
            lease_token, before_engine_start, on_closing_observations):
        from dataclasses import asdict
        from improvement_native_transport import execute_worker_qualification
        from improvement_sandbox import trial_system_prompt
        context = self._assert_query_current()
        if (binding is not self._query_binding or owner is not context['owner'] or principal is not context['principal']
                or identifier != context['identifier'] or expected_generation != context['expected_generation']
                or lease_token != context['lease_token'] or self._query_started):
            raise PermissionError('qualification_query_owner_changed')
        self._query_started = True
        session = self._qualification
        self._scratch = tempfile.TemporaryDirectory(prefix='query-', dir=session.root)
        self._scratch._finalizer.detach()
        try:
            launch = await _settled(asyncio.to_thread(session._query_launch, 'trial', self._scratch.name))
            self._assert_query_current()
            environment = session.environment(context['receipt']['path'])
            receipt = context['receipt']
            self._query_start_request = dict(version=1, config_pin=self.pin,
                workspace_root=str(owner.workspace.root), receipt=receipt, capability_hash=binding.authority_hash)
            self._query_start_qualification = dict(version=2, run_hash=session.run_hash, scope=session.scope(),
                environment_hash=IM._hash(environment), attempt_link=context['link'],
                preflight_hash=binding.preflight_hash, query_binding=asdict(binding))
            self._qualification_seed = dict(kind='trial', request=self._query_start_request,
                environment=environment, qualification=self._query_start_qualification)
            query_policy = dict(version=2, **{key: self.pin[key] for key in ('cli_path', 'model', 'reasoning')},
                prompt_hash=_sha(trial_system_prompt(context['manifest'])), cwd=receipt['path'],
                tools=['mcp__fixture__fixture_read'], tool_policy='baseline_inline')
            self._query_execution = dict(launch=launch, environment=environment,
                deadline_at=min(context['request']['deadline_at'], session._scope['deadline_at']),
                persist=self._persist(environment=environment, cwd=receipt['path'], scope_hash=self.scope_hash,
                    query_policy=query_policy))
            async with aclosing(execute_worker_qualification(self, before_engine_start=before_engine_start,
                    on_closing_observations=on_closing_observations)) as packets:
                async for packet in packets:
                    self._retain_qualification_packets((packet,))
                    yield packet
            from improvement_qualification_results import _NativeCompletion
            await self._close_qualification()
            self._qualification_complete = True
            context['completion'] = _NativeCompletion._from_boundary(self)
        finally:
            if self._guardian is not None and session._native_boundaries.get(self._guardian) is self:
                await self._close_qualification()
            elif self._scratch is not None:
                self._scratch.cleanup()
