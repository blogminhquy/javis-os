"""Disposable engineering authority and retained native preflight ownership."""
from __future__ import annotations

from contextlib import closing
import asyncio
from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import secrets
import sys
import tempfile
import time

from cryptography.fernet import Fernet

import improvement_store as IM
from improvement_blobs import AssetUnavailable, RevisionBlobs, check_ancestry
from improvement_claude import _runtime_identity
from improvement_native_formats import NATIVE_PROFILE_VERSION
from improvement_native_protocol import _canonical, _digest, _fields, _parse
from improvement_native_release import _pin, observe_release
from improvement_qualification_environment import _endpoint, dummy_environment
from improvement_sandbox import _private_directory, worker_environment
from resonance_store import GoalStore, Principal

_TOKEN = object()
_RESULT_TOKEN = object()
_BINDING_TOKEN = object()


@dataclass(frozen=True, slots=True, init=False)
class QualificationQueryBinding:
    version: int
    domain: str
    supported: bool
    account_ready: bool
    run_hash: str
    preflight_hash: str
    kind: str
    subject_id: str
    attempt: int
    request_hash: str
    workspace_hash: str
    materialization_hash: str
    engine_config_hash: str
    authority_hash: str

    def __init__(self, token, values):
        if token is not _BINDING_TOKEN: raise TypeError('retained_qualification_attempt_required')
        for name in self.__dataclass_fields__: object.__setattr__(self, name, values[name])


@dataclass(frozen=True, slots=True, init=False)
class QualificationPreflight:
    version: int
    domain: str
    supported: bool
    account_ready: bool
    technical_ready: bool
    run_hash: str
    pin_hash: str
    release_fingerprint: str
    review_hash: str
    launch_nonce: str
    environment_hash: str
    observation_hash: str
    trace_hash: str
    decision_hashes: tuple
    cleanup: str

    def __init__(self, token, values):
        if token is not _RESULT_TOKEN: raise TypeError('completed_qualification_parent_required')
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, values[name])

    @classmethod
    def _from_parent(cls, boundary):
        from improvement_native_parent import NativeParentBoundary
        if (type(boundary) is not NativeParentBoundary or boundary._qualification is None
                or not boundary._qualification_complete or boundary._guardian.closed is not True
                or not boundary._evidence_settled):
            raise TypeError('completed_qualification_parent_required')
        values = boundary._result_fields
        for name in ('run_hash', 'pin_hash', 'release_fingerprint', 'review_hash', 'launch_nonce',
                'environment_hash', 'observation_hash', 'trace_hash'):
            _digest(values[name])
        if type(values['decision_hashes']) is not tuple or len(values['decision_hashes']) != 2:
            raise ValueError('qualification_decisions_required')
        for value in values['decision_hashes']: _digest(value)
        # The off-loop final check can precede revocation while its caller waits
        # to resume. Recheck synchronously in the issuing task, without an await.
        boundary._qualification._assert_native_current()
        return cls(_RESULT_TOKEN, values)


class QualificationSession:
    def __init__(self, token):
        if token is not _TOKEN:
            raise TypeError('host_qualification_factory_required')

    @classmethod
    def open(cls, *, pin, endpoint, expected_fingerprint, lifetime_seconds, maximum_queries):
        pin = _pin(pin)
        endpoint = _endpoint(endpoint); _digest(expected_fingerprint)
        if (pin['profile_version'] != NATIVE_PROFILE_VERSION
                or type(lifetime_seconds) is not int or not 1 <= lifetime_seconds <= 3600
                or type(maximum_queries) is not int or not 1 <= maximum_queries <= 32):
            raise ValueError('qualification_scope_invalid')
        from improvement_native_qualifications import REVIEWED_QUALIFICATION_CANDIDATES
        key = (sys.platform, pin['cli_version'], pin['cli_hash'], pin['sdk_version'],
            pin['profile_version'], pin['profile_hash'], expected_fingerprint)
        review = REVIEWED_QUALIFICATION_CANDIDATES.get(key)
        if review is None:
            raise PermissionError('qualification_candidate_unreviewed')
        _digest(review)
        runtime = _runtime_identity(pin)
        if (type(runtime) is not dict or runtime.get('platform') != sys.platform
                or runtime.get('managed_policy') != 'absent'
                or any(runtime.get(name) != pin[name] for name in ('cli_hash', 'sdk_version', 'profile_hash'))):
            raise PermissionError('qualification_runtime_drift')
        release = observe_release(pin)
        if release['fingerprint'] != expected_fingerprint:
            raise PermissionError('qualification_source_drift')
        self = cls(_TOKEN)
        self._temporary = tempfile.TemporaryDirectory(prefix='jnqual-')
        self._root = Path(self._temporary.name).absolute()
        self._closed = self._cleaned = False
        self._owners = set()
        self._native_boundaries = {}
        self._native_started = False
        self._native_parent = None
        self._completed_preflight = self._preflight_task = None
        self._host_operations, self._queries, self._pending_proofs = {}, {}, {}
        self._attempt_resources = {}
        try:
            _private_directory(self.root)
            brain = self.root / 'brain'; brain.mkdir(mode=0o700)
            self.principal = Principal('owner', 'owner', str(brain))
            key_bytes = Fernet.generate_key()
            # New disposable engineering encryption material, never copied host auth.
            key_path = self.root / 'fixture-encryption.key'
            with key_path.open('xb') as handle: handle.write(key_bytes)
            key_path.chmod(0o600)
            codec = Fernet(key_bytes)
            blobs = RevisionBlobs(self.root / 'assets',
                encrypt=lambda text: 'enc:' + codec.encrypt(text.encode()).decode(),
                decrypt=lambda text: codec.decrypt(text.removeprefix('enc:').encode()).decode())
            created = time.time()
            self._scope = {'version': 1, 'domain': 'qualification', 'account_ready': False,
                'run_nonce': secrets.token_hex(32), 'root': str(self.root), 'brain_id': self.principal.brain_id,
                'pin_hash': IM._hash(pin), 'release_fingerprint': expected_fingerprint, 'review_hash': review,
                'endpoint': endpoint, 'maximum_queries': maximum_queries,
                'created_at': created, 'deadline_at': created + lifetime_seconds}
            self.run_hash = IM._hash(self._scope)
            self.assets = IM.ImprovementStore(GoalStore(self.root / 'state' / 'resonance.sqlite3'), blobs,
                qualification_anchor=self.run_hash)
            IM.ensure(self.assets.store)
            from agent_ledger import CallLedger
            self.ledger = CallLedger(self.assets.store)
            self._event_key = 'native-qualification:' + self.run_hash
            self._pin = _parse(_canonical(pin))
            self._release = release
            self._native_authority = (self.assets, self.principal, self.root, self.run_hash,
                _canonical(self._pin), _canonical(release), _canonical(runtime), self.assets.store, self.assets.blobs)
            raw = _canonical(self._scope)
            blob = self.assets.blobs.write(self.principal.brain_id, raw)
            with self.assets.store._Tx(self.assets.store) as connection:
                IM.ImprovementStore._event(connection, self.principal, self._event_key,
                    'native_qualification_session', {'run_hash': self.run_hash},
                    {'version': 1, 'run_hash': self.run_hash, 'blob_hash': blob})
            return self
        except BaseException:
            self._temporary.cleanup()
            raise

    @property
    def root(self):
        return self._root

    def scope(self):
        return _parse(_canonical(self._scope))

    def read_scope(self):
        if self._cleaned: raise PermissionError('qualification_session_unavailable')
        with closing(self.assets.store._conn()) as connection:
            record = IM.ImprovementStore._replay(connection, self.principal.brain_id, self._event_key,
                'native_qualification_session', {'run_hash': self.run_hash})
        if record is None: raise PermissionError('qualification_session_unavailable')
        _fields(record, {'version', 'run_hash', 'blob_hash'})
        if type(record['version']) is not int or record['version'] != 1 or record['run_hash'] != self.run_hash:
            raise AssetUnavailable('qualification_session_changed')
        _digest(record['blob_hash'])
        raw = self.assets.blobs.read(self.principal.brain_id, record['blob_hash'])
        if (hashlib.sha256(raw).hexdigest() != self.run_hash or raw != _canonical(self._scope)):
            raise AssetUnavailable('qualification_session_changed')
        return _parse(raw)

    @staticmethod
    def open_forensic(root, *, expected_run_hash):
        """Explicit anchored read-only reopen; never migrations, launch or auth."""
        from improvement_qualification_records import read_run
        _digest(expected_run_hash)
        supplied = Path(root)
        if not supplied.is_absolute() or '..' in supplied.parts:
            raise PermissionError('qualification_archive_root_invalid')
        root = supplied.absolute(); check_ancestry(root)
        key_path = root / 'fixture-encryption.key'; check_ancestry(key_path)
        with key_path.open('rb') as handle: key_bytes = handle.read(65)
        if len(key_bytes) != 44: raise AssetUnavailable('qualification_archive_key_invalid')
        codec = Fernet(key_bytes)
        blobs = RevisionBlobs(root / 'assets',
            encrypt=lambda text: 'enc:' + codec.encrypt(text.encode()).decode(),
            decrypt=lambda text: codec.decrypt(text.removeprefix('enc:').encode()).decode())
        path = root / 'state' / 'resonance.sqlite3'; check_ancestry(path)
        assets = IM.read_existing(path, blobs, qualification_anchor=expected_run_hash)
        if assets is None: raise AssetUnavailable('qualification_archive_unavailable')
        principal = Principal('owner', 'owner', str(root / 'brain'))
        if read_run(assets, principal) is None: raise AssetUnavailable('qualification_archive_unavailable')
        return assets, principal

    def bind_attempt(self, owner, principal, identifier, *, expected_generation, lease_token, capability_hash):
        """Count and bind a prepared real attempt before its first query launch.

        Exact replay is historical identity only; it still requires an active
        pre-engine lease and does not permit relaunch or refresh a closed run.
        """
        from improvement_trials import TrialStore
        from improvement_operation_execution import OperationExecution
        from improvement_qualification_records import _key, _ATTEMPT, actual_binding, read_attempt, read_run
        _digest(capability_hash)
        if (type(owner) not in (TrialStore, OperationExecution) or owner.assets is not self.assets
                or principal != self.principal):
            raise PermissionError('qualification_attempt_owner_foreign')
        kind = 'trial' if type(owner) is TrialStore else 'operation'
        with self.assets.store._Tx(self.assets.store) as connection:
            if self._closed or self._cleaned: raise PermissionError('qualification_session_closed')
            scope = read_run(self.assets, principal, connection=connection)
            if scope != self._scope: raise AssetUnavailable('qualification_session_changed')
            if time.time() >= scope['deadline_at']: raise PermissionError('qualification_session_expired')
            row, attempt = owner._leased(connection, principal, identifier, expected_generation, lease_token, time.time())
            call = connection.execute('SELECT * FROM agent_calls WHERE id=?', (attempt['call_id'],)).fetchone()
            if (row['status'] != 'prepared' or attempt['status'] != 'prepared' or attempt['engine_at'] is not None
                    or call is None or call['status'] != 'reserved' or call['engine_at'] is not None):
                raise IM.ConflictError('qualification_attempt_already_started')
            workspace = _parse(attempt['workspace_json'].encode())
            manifest = owner.workspace.validate(workspace)
            if (IM._hash(manifest) != attempt['materialization_hash']
                    or attempt['materialization_hash'] != workspace['input_hash']
                    or manifest['brain_id'] != principal.brain_id
                    or manifest['engine_config_hash'] != IM._hash(self._pin)):
                raise IM.ConflictError('qualification_materialization_changed')
            if kind == 'trial':
                expected = owner._materialization(connection, row, manifest['baseline_context'], principal=principal)
                if expected != manifest: raise IM.ConflictError('qualification_materialization_changed')
            else:
                prepared = owner._current(connection, principal, row)
                owner.host._snapshot_observe(principal, prepared[1])
                from improvement_operation_protocol import operation_materialization
                from improvement_native_formats import input_version
                expected = operation_materialization({'version': input_version(self._pin, 'operation'),
                    'brain_id': principal.brain_id, 'operation_id': identifier,
                    'request': _parse(row['request_json'].encode()), 'engine_config_hash': IM._hash(self._pin),
                    'data': _parse(self.assets.blobs.read(principal.brain_id, row['input_blob_hash'])),
                    'learning_origin': 'compose'})
                if expected != manifest: raise IM.ConflictError('qualification_materialization_changed')
            link = actual_binding(self.assets, principal, kind=kind, subject_id=identifier, attempt=attempt['attempt'],
                capability_hash=capability_hash, run_hash=self.run_hash, connection=connection)
            key = _key(kind, identifier, attempt['attempt'])
            previous = self.assets._replay(connection, principal.brain_id, key, _ATTEMPT, {'run_hash': self.run_hash})
            if previous is not None:
                if previous.get('link_hash') != IM._hash(link): raise IM.ConflictError('qualification_attempt_changed')
                link = read_attempt(self.assets, principal, kind=kind, subject_id=identifier, attempt=attempt['attempt'],
                    capability_hash=capability_hash, connection=connection)
            else:
                count = connection.execute('SELECT COUNT(*) FROM improvement_events WHERE brain_id=? AND operation=?',
                    (principal.brain_id, _ATTEMPT)).fetchone()[0]
                if count >= scope['maximum_queries']: raise PermissionError('qualification_query_budget_exhausted')
                raw = _canonical(link)
                blob = self.assets.blobs.write(principal.brain_id, raw)
                self.assets._event(connection, principal, key, _ATTEMPT, {'run_hash': self.run_hash},
                    {'version': 1, 'run_hash': self.run_hash, 'link_hash': IM._hash(link), 'blob_hash': blob})
            # Blob encryption and callbacks may be slow. No expired lease/run
            # can publish a newly counted attempt merely from its early check.
            if self._closed or time.time() >= scope['deadline_at']:
                raise PermissionError('qualification_session_expired')
            owner._leased(connection, principal, identifier, expected_generation, lease_token, time.time())
            return link

    def environment(self, cwd):
        if self._closed or self._cleaned:
            raise PermissionError('qualification_session_closed')
        scope = self.read_scope()
        if time.time() >= scope['deadline_at']:
            raise PermissionError('qualification_session_expired')
        supplied = Path(cwd)
        if '..' in supplied.parts:
            raise PermissionError('qualification_workspace_foreign')
        cwd = supplied.absolute()
        check_ancestry(cwd)
        if not cwd.is_relative_to(self.root) or not cwd.is_dir():
            raise PermissionError('qualification_workspace_foreign')
        homes = self.root / 'homes'; homes.mkdir(exist_ok=True, mode=0o700)
        check_ancestry(homes)
        home = homes / secrets.token_hex(16)
        home.mkdir(mode=0o700)
        check_ancestry(home)
        if tuple(home.iterdir()): raise PermissionError('qualification_home_not_empty')
        base = worker_environment(cwd, auth_home=home)
        # Explicit engineering wire shape is stable during portable preparation;
        # these are paths under a fresh empty HOME, never ambient platform config.
        base.update(APPDATA=str(home / 'AppData' / 'Roaming'), LOCALAPPDATA=str(home / 'AppData' / 'Local'))
        return dummy_environment(base, endpoint=scope['endpoint'])

    def _assert_native_current(self, *, connection=None):
        import improvement_native_qualifications as qualifications
        from improvement_qualification_records import read_run
        if type(self) is not QualificationSession: raise TypeError('concrete_qualification_session_required')
        if self._closed or self._cleaned: raise PermissionError('qualification_session_closed')
        assets, principal, root, run_hash, pin, release, runtime, store, blobs = self._native_authority
        if (self.assets is not assets or self.principal is not principal or self.root != root
                or self.assets.store is not store or self.assets.blobs is not blobs
                or self.run_hash != run_hash or self.assets.qualification_anchor != run_hash
                or self.assets.store.path != root / 'state' / 'resonance.sqlite3'
                or self.assets.blobs.root != root / 'assets' or self.principal.brain_id != str(root / 'brain')
                or _canonical(self._pin) != pin or _canonical(self._release) != release
                or IM._hash(self._scope) != run_hash or self._scope['pin_hash'] != IM._hash(self._pin)):
            raise AssetUnavailable('qualification_session_changed')
        for path in (root, store.path, blobs.root, root / 'brain'): check_ancestry(path)
        if read_run(self.assets, self.principal, connection=connection) != self._scope:
            raise AssetUnavailable('qualification_session_changed')
        if time.time() >= self._scope['deadline_at']: raise PermissionError('qualification_session_expired')
        key = (sys.platform, *(self._pin[name] for name in ('cli_version', 'cli_hash', 'sdk_version',
            'profile_version', 'profile_hash')), self._scope['release_fingerprint'])
        if qualifications.REVIEWED_QUALIFICATION_CANDIDATES.get(key) != self._scope['review_hash']:
            raise PermissionError('qualification_candidate_unreviewed')
        if _canonical(_runtime_identity(self._pin)) != runtime:
            raise PermissionError('qualification_runtime_drift')
        # Runtime/source metadata and encrypted reads can be slow. Recheck the
        # revocable authority after them, including under the control send lock.
        if self._closed or self._cleaned: raise PermissionError('qualification_session_closed')
        if time.time() >= self._scope['deadline_at']: raise PermissionError('qualification_session_expired')
        if qualifications.REVIEWED_QUALIFICATION_CANDIDATES.get(key) != self._scope['review_hash']:
            raise PermissionError('qualification_candidate_unreviewed')

    def _preflight_launch(self, scratch):
        from improvement_fixed_worker_launch import _policy
        self._assert_native_current()
        scratch = Path(scratch); check_ancestry(scratch)
        if not scratch.is_absolute() or not scratch.is_relative_to(self.root) or not scratch.is_dir():
            raise PermissionError('qualification_workspace_foreign')
        observed = observe_release(self._pin)
        if _canonical(observed) != self._native_authority[5]:
            raise PermissionError('qualification_source_drift')
        self._assert_native_current()
        return {'guardian_manifest': observed['manifests']['guardian'],
            'policy': _policy({'version': 1, 'bootstrap': observed['manifests']['trial'], 'scratch': str(scratch)}),
            'image_policy': {'version': 1, 'path': self._pin['cli_path'], 'sha256': self._pin['cli_hash']},
            'release_fingerprint': observed['fingerprint'], 'qualification_hash': self._scope['review_hash']}

    def _query_launch(self, kind, scratch):
        if kind != 'trial': raise PermissionError('qualification_query_kind_unavailable')
        return self._preflight_launch(scratch)

    def _assert_trial_owner(self, admission, principal):
        from improvement_trial_admission import TrialAdmission
        if (type(admission) is not TrialAdmission or principal is not self.principal
                or admission.assets is not self.assets or admission.store is not self.assets.store
                or admission.host.assets is not self.assets
                or not admission.trials.workspace.root.absolute().is_relative_to(self.root)):
            raise PermissionError('qualification_attempt_owner_foreign')
        self._assert_native_current()

    def _require_preflight(self):
        self._assert_native_current()
        proof = self._completed_preflight
        if (type(proof) is not QualificationPreflight or self._native_parent is None
                or not self._native_parent._qualification_complete
                or proof.run_hash != self.run_hash or proof.pin_hash != IM._hash(self._pin)):
            raise PermissionError('qualification_preflight_required')
        return proof

    def _query_binding(self, owner, principal, identifier, *, expected_generation, lease_token):
        from improvement_trials import TrialStore
        self._require_preflight()
        if type(owner) is not TrialStore or owner.assets is not self.assets or principal is not self.principal:
            raise PermissionError('qualification_attempt_owner_foreign')
        with self.assets.store._Tx(self.assets.store) as connection:
            row, attempt = owner._leased(connection, principal, identifier, expected_generation, lease_token, time.time())
            receipt = _parse(attempt['workspace_json'].encode())
            manifest = owner.workspace.validate(receipt)
            request = _parse(row['request_json'].encode())
            if (manifest['version'] != 5 or request['engine_config'] != self._pin
                    or not Path(receipt['path']).is_relative_to(self.root)):
                raise PermissionError('qualification_baseline5_required')
            values = dict(version=1, domain='qualification', supported=False, account_ready=False,
                run_hash=self.run_hash, preflight_hash=IM._hash(asdict(self._require_preflight())), kind='trial',
                subject_id=identifier, attempt=attempt['attempt'], request_hash=row['request_hash'],
                workspace_hash=IM._hash(receipt), materialization_hash=IM._hash(manifest), engine_config_hash=IM._hash(self._pin))
        binding = QualificationQueryBinding(_BINDING_TOKEN, {**values, 'authority_hash': IM._hash(values)})
        # Existing bind_attempt is the sole atomic query budget debit.
        link = self.bind_attempt(owner, principal, identifier, expected_generation=expected_generation,
            lease_token=lease_token, capability_hash=binding.authority_hash)
        key = (identifier, binding.attempt)
        if key in self._queries: raise PermissionError('qualification_query_already_bound')
        self._queries[key] = dict(binding=binding, owner=owner, principal=principal, identifier=identifier,
            expected_generation=expected_generation, lease_token=lease_token, request=request,
            receipt=receipt, manifest=manifest, link=link, boundary=None, completion=None, stage=None, cleanup=None)
        self._query_current(binding)
        return binding

    def _query_context(self, binding):
        if type(binding) is not QualificationQueryBinding: raise PermissionError('qualification_binding_foreign')
        context = self._queries.get((binding.subject_id, binding.attempt))
        if context is None or context['binding'] is not binding: raise PermissionError('qualification_binding_foreign')
        return context

    def _query_current(self, binding, *, connection=None, workspace=True, leased=True):
        from improvement_qualification_records import read_attempt
        self._require_preflight()
        context = self._query_context(binding)
        if connection is None:
            with closing(self.assets.store._conn()) as conn:
                return self._query_current(binding, connection=conn, workspace=workspace, leased=leased)
        self._assert_native_current(connection=connection)
        owner, principal, identifier = (context[key] for key in ('owner', 'principal', 'identifier'))
        row = owner._row(connection, principal.brain_id, identifier)
        if leased:
            _, attempt = owner._leased(connection, principal, identifier, row['generation'], context['lease_token'], time.time())
        request = _parse(row['request_json'].encode())
        if request != context['request'] or row['attempt'] != binding.attempt:
            raise PermissionError('qualification_attempt_changed')
        owner._current(connection, principal.brain_id, request, trial_id=identifier, principal=principal)
        owner._native_host.live_guard(principal, request)
        if workspace and owner.workspace.validate(context['receipt']) != context['manifest']:
            raise PermissionError('qualification_materialization_changed')
        link = read_attempt(self.assets, principal, kind='trial', subject_id=identifier, attempt=binding.attempt,
            capability_hash=binding.authority_hash, connection=connection)
        if link != context['link']: raise PermissionError('qualification_attempt_changed')
        self._assert_native_current(connection=connection)
        return context

    async def run_trial(self, admission, public_start_request):
        from improvement_trial_runner import TrialRunner, _drain, _settled_call
        self._assert_trial_owner(admission, self.principal)
        task = asyncio.current_task()
        if task in self._host_operations: raise PermissionError('qualification_facade_already_owned')
        self._host_operations[task] = None  # Before the first await/reservation.
        try:
            if self._completed_preflight is None:
                if self._preflight_task is None:
                    self._preflight_task = asyncio.create_task(self.verify_native())
                values, cancelled = await _drain(asyncio.gather(self._preflight_task, return_exceptions=True))
                if cancelled is not None: raise cancelled
                if isinstance(values[0], BaseException): raise values[0]
            self._require_preflight()
            operation = asyncio.create_task(asyncio.to_thread(admission.admit_qualification, self, self.principal, public_start_request))
            values, cancelled = await _drain(asyncio.gather(operation, return_exceptions=True))
            if cancelled is not None:
                if not isinstance(values[0], BaseException):
                    admitted = values[0]
                    latest = await _settled_call(admission.trials.get, self.principal, admitted.trial_id)
                    if latest['status'] == 'reserved':
                        await _settled_call(admission.trials.reject_unclaimed, self.principal, admitted.trial_id,
                            expected_generation=latest['generation'], reason='cancelled')
                raise cancelled
            if isinstance(values[0], BaseException): raise values[0]
            admitted = values[0]
            self._host_operations[task] = (admitted.trial_id, 1)
            result = await TrialRunner.for_qualification(self, admission).run_qualification(self.principal, admitted.trial_id)
            self._assert_native_current()  # Final returning-task fence, no await gap.
            return result
        finally:
            self._host_operations.pop(task, None)

    async def aclose_queries(self):
        from improvement_trial_runner import _drain
        self.close()
        tasks = tuple(task for task in self._host_operations if task is not asyncio.current_task())
        if tasks: await _drain(asyncio.gather(*tasks, return_exceptions=True))
        if self._preflight_task is not None:
            await _drain(asyncio.gather(self._preflight_task, return_exceptions=True))
        await self.aclose_native()
        # Retained actual runner/lifetime owners can outlive a failed facade.
        # Retry only their known cleanup, never admission, settlement or query.
        for key, resource in tuple(self._attempt_resources.items()):
            await resource['runner']._cleanup_qualification_attempt(key)
        from improvement_trial_runner import _settled_call
        from improvement_qualification_results import QualificationQueryResults
        for context in tuple(self._pending_proofs.values()):
            await _settled_call(QualificationQueryResults(self)._save_cleanup_diagnostic, context)

    def _attach_native(self, guardian, boundary):
        from improvement_native_transport import GuardianSessionV2
        from improvement_native_parent import NativeParentBoundary
        self._assert_native_current()
        if (type(guardian) is not GuardianSessionV2 or type(boundary) is not NativeParentBoundary
                or boundary._qualification is not self or boundary._guardian is not guardian
                or guardian._used or guardian.closed or guardian in self._owners
                or boundary._owner_state != 'PREPARED'):
            raise PermissionError('qualification_native_owner_foreign')
        self._owners.add(guardian); self._native_boundaries[guardian] = boundary
        guardian._qualification_boundary = boundary
        boundary._owner_state = 'ATTACHED'

    def _detach_native(self, guardian, boundary):
        if (self._native_boundaries.get(guardian) is not boundary or guardian not in self._owners
                or guardian.closed is not True or not boundary._evidence_settled):
            raise RuntimeError('qualification_native_owners_unsettled')
        del self._native_boundaries[guardian]; self._owners.remove(guardian)
        boundary._owner_state = 'DETACHED'

    async def verify_native(self):
        if self._native_started: raise PermissionError('qualification_preflight_already_used')
        self._native_started = True  # Reserve before the first await.
        self._assert_native_current()
        from improvement_native_parent import NativeParentBoundary
        task = asyncio.current_task()
        own = task not in self._host_operations
        if own: self._host_operations[task] = ('preflight', 0)
        try:
            result = await NativeParentBoundary.for_qualification(self).verify_qualification()
            self._assert_native_current()
            self._completed_preflight = result
            return result
        finally:
            if own: self._host_operations.pop(task, None)

    async def aclose_native(self):
        self.close()
        error = None
        for guardian, boundary in tuple(self._native_boundaries.items()):
            try: await boundary._close_qualification()
            except BaseException as caught: error = caught
        if error is not None: raise error

    def close(self):
        self._closed = True
        self._temporary._finalizer.detach()
        for task, operation in tuple(self._host_operations.items()):
            if operation == ('preflight', 0): continue
            loop = task.get_loop()
            if not loop.is_closed() and not task.done(): loop.call_soon_threadsafe(task.cancel)
        for owner in tuple(self._owners):
            loop = getattr(owner, '_loop', None)
            if loop is not None and hasattr(owner, '_space') and not loop.is_closed():
                try:
                    if asyncio.get_running_loop() is loop: owner._stop()
                    else: loop.call_soon_threadsafe(owner._stop)
                except RuntimeError: loop.call_soon_threadsafe(owner._stop)

    def cleanup(self):
        self.close()
        if self._owners or self._host_operations or self._pending_proofs or self._attempt_resources or any(
                context['completion'] is not None and context['cleanup'] is None for context in self._queries.values()):
            raise RuntimeError('qualification_native_owners_unsettled')
        if not self._cleaned:
            self._temporary.cleanup()
            self._cleaned = True
