"""Immutable technical evidence, settlement and cold authentication; no executor."""
from __future__ import annotations

from contextlib import closing
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import time

import improvement_store as IM
from improvement_blobs import AssetUnavailable, MAX_ASSET_BYTES
from improvement_native_protocol import _canonical, _digest, _fields, _parse
from improvement_qualification_records import read_attempt, read_run

_COMPLETION = object()
_STAGE = object()
_CLEANUP = object()
_RESULT = object()
_EVIDENCE = 'native_qualification_query_evidence'
_FINAL = 'native_qualification_query_result'


def _freeze(value):
    if type(value) is dict: return tuple((key, _freeze(item)) for key, item in sorted(value.items()))
    if type(value) is list: return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True, slots=True, init=False)
class QualificationQueryResult:
    version: int
    domain: str
    supported: bool
    account_ready: bool
    business_proof: bool
    run_hash: str
    kind: str
    subject_id: str
    attempt: int
    request_hash: str
    materialization_hash: str
    workspace_hash: str
    engine_config_hash: str
    query_authority_hash: str
    attempt_link_hash: str
    preflight_hash: str
    release_fingerprint: str
    review_hash: str
    launch_nonce: str
    environment_hash: str
    call_id: int
    engine_at: float
    trace_hashes: tuple
    native_decisions: tuple
    installation_hash: str
    input_delivery_hash: str
    checks: tuple
    execution_status: str
    cleanup: str
    cleanup_evidence_hash: str

    def __init__(self, token, values):
        if token is not _RESULT: raise TypeError('authenticated_qualification_result_required')
        _validate_result(values)
        for name in self.__dataclass_fields__: object.__setattr__(self, name, _freeze(values[name]))


def _validate_result(value):
    _fields(value, set(QualificationQueryResult.__dataclass_fields__))
    if (type(value['version']) is not int or value['version'] != 1 or value['domain'] != 'qualification'
            or any(value[name] is not False for name in ('supported', 'account_ready', 'business_proof'))
            or value['kind'] != 'trial' or type(value['attempt']) is not int or value['attempt'] < 1
            or value['cleanup'] != 'proven' or value['execution_status'] not in ('completed', 'failed')
            or type(value['call_id']) is not int or value['call_id'] < 1
            or type(value['engine_at']) not in (int, float) or value['engine_at'] <= 0):
        raise AssetUnavailable('qualification_result_invalid')
    for name in ('run_hash', 'request_hash', 'materialization_hash', 'workspace_hash', 'engine_config_hash',
            'query_authority_hash', 'attempt_link_hash', 'preflight_hash', 'release_fingerprint', 'review_hash',
            'launch_nonce', 'environment_hash', 'installation_hash', 'input_delivery_hash', 'cleanup_evidence_hash'):
        _digest(value[name])
    if type(value['trace_hashes']) is not list or not value['trace_hashes']: raise AssetUnavailable('qualification_trace_missing')
    for item in value['trace_hashes']: _digest(item)
    if type(value['native_decisions']) is not list or len(value['native_decisions']) != 4:
        raise AssetUnavailable('qualification_decisions_missing')
    for decision in value['native_decisions']:
        _fields(decision, {'decision', 'durable_evidence_hash'})
        if decision['decision'] != 'allow': raise AssetUnavailable('qualification_decisions_missing')
        _digest(decision['durable_evidence_hash'])
    if type(value['checks']) is not list or not value['checks']: raise AssetUnavailable('qualification_checks_missing')
    for check in value['checks']:
        _fields(check, {'id', 'verdict', 'reason', 'evidence'})
        if check['verdict'] not in ('pass', 'fail', 'unknown'): raise AssetUnavailable('qualification_checks_invalid')


@dataclass(frozen=True, slots=True, init=False)
class _NativeCompletion:
    boundary: object
    ack: bytes
    input_delivery_hash: str

    def __init__(self, token, boundary, ack, delivery):
        if token is not _COMPLETION: raise TypeError('completed_native_owner_required')
        for name, value in (('boundary', boundary), ('ack', _canonical(ack)), ('input_delivery_hash', delivery)):
            object.__setattr__(self, name, value)

    @classmethod
    def _from_boundary(cls, boundary):
        from improvement_native_parent import NativeParentBoundary
        if type(boundary) is not NativeParentBoundary or not hasattr(boundary, '_query_binding'):
            raise TypeError('completed_native_owner_required')
        context = boundary._qualification._query_context(boundary._query_binding)
        owner = boundary._guardian
        if (context['boundary'] is not boundary or not boundary._qualification_complete
                or boundary._owner_state != 'DETACHED' or not boundary._evidence_settled
                or owner.closed is not True or not owner.native_drained or not owner._worker_complete
                or owner._allowed != {'adapter_version', 'auth_status', 'sdk_version', 'query'}
                or not owner._accounting_acknowledged or boundary._ack_witness is None
                or any(type(status) is not int or status != 0 for status in
                    (owner._worker_exit_code, owner._guardian_exit_code))):
            raise PermissionError('qualification_native_completion_unproven')
        receipts = [packet['body']['event'] for packet in boundary._qualification_packets.values()
            if packet['body']['type'] == 'engine_event' and packet['body']['event'].get('type') == 'installation_receipt']
        if len(receipts) != 1 or not receipts[0]['receipt'].get('native_input_delivery'):
            raise PermissionError('qualification_input_delivery_unproven')
        return cls(_COMPLETION, boundary, boundary._ack_witness, IM._hash(receipts[0]['receipt']['native_input_delivery']))


@dataclass(frozen=True, slots=True, init=False)
class _StagedEvidence:
    session: object
    context: object
    raw: bytes
    digest: str
    envelope: bytes

    def __init__(self, token, session, context, value, envelope):
        if token is not _STAGE: raise TypeError('owned_staged_evidence_required')
        for name, item in (('session', session), ('context', context), ('raw', _canonical(value)),
                ('digest', IM._hash(value)), ('envelope', _canonical(envelope))): object.__setattr__(self, name, item)


@dataclass(frozen=True, slots=True, init=False)
class _CleanupReceipt:
    session: object
    context: object
    raw: bytes

    def __init__(self, token, session, context, values):
        if token is not _CLEANUP: raise TypeError('owned_cleanup_required')
        for name, item in (('session', session), ('context', context), ('raw', _canonical(values))):
            object.__setattr__(self, name, item)

    @classmethod
    def _from_runner(cls, runner, context, handles):
        from improvement_trial_runner import TrialRunner
        if (type(runner) is not TrialRunner or runner._qualification is None or context['owner'] is not runner.trials
                or handles is None or any(not handle.closed for handle in handles)
                or context['boundary']._owner_state != 'DETACHED'):
            raise PermissionError('qualification_cleanup_unproven')
        binding = context['binding']
        if not runner.trials.workspace.cleanup_proven(binding.subject_id, binding.attempt, context['receipt']):
            raise PermissionError('qualification_cleanup_unproven')
        return cls(_CLEANUP, runner._qualification, context, dict(version=1, run_hash=binding.run_hash,
            kind=binding.kind, subject_id=binding.subject_id, attempt=binding.attempt,
            workspace_hash=binding.workspace_hash, evidence_hash=(context['stage'].digest if context['stage'] is not None
                else IM._hash({'incomplete': binding.authority_hash})),
            workspace_removed=True, lifetime_released=True, native_drained=True))


def _identity(run_hash, kind, identifier, attempt):
    return dict(run_hash=run_hash, kind=kind, subject_id=identifier, attempt=attempt)


def _key(operation, identity): return operation + ':' + IM._hash(identity)


def _write(assets, principal, value):
    raw = _canonical(value)
    return dict(version=1, content_hash=hashlib.sha256(raw).hexdigest(), blob_hashes=[
        assets.blobs.write(principal.brain_id, raw[index:index + MAX_ASSET_BYTES])
        for index in range(0, len(raw), MAX_ASSET_BYTES)])


def _read(assets, principal, envelope):
    _fields(envelope, {'version', 'content_hash', 'blob_hashes'})
    if type(envelope['version']) is not int or envelope['version'] != 1 or type(envelope['blob_hashes']) is not list or not envelope['blob_hashes']:
        raise AssetUnavailable('qualification_evidence_unavailable')
    _digest(envelope['content_hash'])
    for digest in envelope['blob_hashes']: _digest(digest)
    raw = b''.join(assets.blobs.read(principal.brain_id, digest) for digest in envelope['blob_hashes'])
    if hashlib.sha256(raw).hexdigest() != envelope['content_hash'] or _canonical(_parse(raw)) != raw:
        raise AssetUnavailable('qualification_evidence_changed')
    return _parse(raw)


def _stored(assets, principal, connection, operation, identity):
    key = _key(operation, identity)
    rows = list(connection.execute('SELECT event_key FROM improvement_events WHERE brain_id=? AND operation=? AND request_hash=?',
        (principal.brain_id, operation, IM._hash(identity))))
    if len(rows) != 1 or rows[0]['event_key'] != key: raise AssetUnavailable('qualification_evidence_unavailable')
    envelope = assets._replay(connection, principal.brain_id, key, operation, identity)
    return _read(assets, principal, envelope), envelope


def _authenticate(assets, principal, connection, stage, *, terminal):
    """No workspace/runtime/source observations: immutable joins remain cold."""
    from improvement_qualification_protocol import validate_query_binding
    from improvement_trial_evidence import decode_trace
    from improvement_native_trace_checks import validated_history, reread_native_decisions
    from improvement_native_decisions import NativeImageDecisionStore, attempt_scope
    _fields(stage, {'version', 'identity', 'binding', 'preflight', 'link', 'request', 'manifest', 'workspace',
        'contract', 'ack', 'trace_hashes', 'native_decisions', 'installation_hash', 'input_delivery_hash',
        'checks', 'execution_status', 'launch_nonce', 'environment_hash', 'usage_completion'})
    if type(stage['version']) is not int or stage['version'] != 1: raise AssetUnavailable('qualification_stage_version')
    binding, identity = stage['binding'], stage['identity']
    scope = read_run(assets, principal, connection=connection)
    if scope is None or IM._hash(scope) != identity['run_hash']: raise AssetUnavailable('qualification_run_changed')
    _authenticate_preflight(assets, principal, connection, stage['preflight'], scope)
    link = read_attempt(assets, principal, kind=identity['kind'], subject_id=identity['subject_id'], attempt=identity['attempt'],
        capability_hash=binding['authority_hash'], connection=connection)
    if link != stage['link']: raise AssetUnavailable('qualification_link_changed')
    validate_query_binding(binding, link=link, preflight_hash=IM._hash(stage['preflight']))
    workspace, request, manifest = stage['workspace'], stage['request'], stage['manifest']
    if (IM._hash(request) != binding['request_hash'] or IM._hash(workspace) != binding['workspace_hash']
            or IM._hash(manifest) != binding['materialization_hash'] or workspace['input_hash'] != IM._hash(manifest)
            or IM._hash(request['engine_config']) != binding['engine_config_hash']
            or IM._hash(stage['contract']) != request['pins']['contract_hash']):
        raise AssetUnavailable('qualification_stage_changed')
    row = connection.execute('SELECT * FROM improvement_trial_attempts WHERE trial_id=? AND brain_id=? AND attempt=?',
        (identity['subject_id'], principal.brain_id, identity['attempt'])).fetchone()
    call = connection.execute('SELECT * FROM agent_calls WHERE id=?', (link['call_id'],)).fetchone()
    ack = stage['ack']
    _fields(ack, {'call_id', 'engine_at', 'engine_start_request_sequence', 'ack_identity_hash', 'ack_send_complete'})
    if (row is None or call is None or row['call_id'] != call['id'] or ack['call_id'] != call['id']
            or call['engine_at'] is None or ack['engine_at'] != call['engine_at'] or row['engine_at'] != call['engine_at']
            or ack['ack_send_complete'] is not True or json.loads(row['workspace_json']) != workspace
            or row['materialization_hash'] != binding['materialization_hash'] or row['result_json'] is not None):
        raise AssetUnavailable('qualification_accounting_changed')
    _digest(ack['ack_identity_hash'])
    if terminal and (row['status'] != stage['execution_status'] or call['status'] !=
            ('ok' if stage['execution_status'] == 'completed' else 'error') or row['lease_token'] is not None or row['lease_until'] is not None):
        raise AssetUnavailable('qualification_settlement_changed')
    usage = stage['usage_completion']
    execution = usage.get('execution', {}) if type(usage) is dict else {}
    expected_usage = dict(experiment_id=request['pins']['experiment_id'], trial_id=identity['subject_id'],
        attempt=identity['attempt'], execution_id='improvement_trial:' + identity['subject_id'], role='solver', purpose='improve_probe')
    if (usage.get('event_kind') != 'execution' or usage.get('source_id') != 'improvement-native-v1'
            or usage.get('status') != stage['execution_status'] or usage.get('provider') != request['engine_config']['provider']
            or usage.get('model') != request['engine_config']['model']
            or any(execution.get(name) != item for name, item in expected_usage.items())):
        raise AssetUnavailable('qualification_usage_completion_changed')
    records = list(connection.execute('SELECT * FROM improvement_trial_observations WHERE trial_id=? AND brain_id=? AND attempt=? ORDER BY sequence',
        (identity['subject_id'], principal.brain_id, identity['attempt'])))
    packets = validated_history(records, lambda row: decode_trace(assets.blobs, principal.brain_id, row), kind='trial', receipt=workspace)
    if [row['payload_hash'] for row in records] != stage['trace_hashes']:
        raise AssetUnavailable('qualification_trace_changed')
    decision_scope = attempt_scope(kind='trial', brain_id=principal.brain_id, receipt=workspace,
        config_pin=request['engine_config'], capability_hash=binding['authority_hash'])
    decisions = NativeImageDecisionStore(assets)
    actual = reread_native_decisions(packets, kind='trial', receipt=workspace,
        read_decision=lambda joined: decisions.read(principal, joined, scope_hash=decision_scope, connection=connection))
    if actual != stage['native_decisions'] or len(actual) != 4 or any(item['decision'] != 'allow' for item in actual):
        raise AssetUnavailable('qualification_decisions_changed')
    starts = [packet for packet in packets if packet['body']['type'] == 'engine_start_requested']
    installations = [packet['body']['event'] for packet in packets if packet['body']['type'] == 'engine_event'
        and packet['body']['event'].get('type') == 'installation_receipt']
    if (len(starts) != 1 or starts[0]['sequence'] != ack['engine_start_request_sequence']
            or len(installations) != 1 or IM._hash(installations[0]['receipt']) != installations[0]['hash']
            or installations[0]['hash'] != stage['installation_hash']
            or IM._hash(installations[0]['receipt'].get('native_input_delivery')) != stage['input_delivery_hash']
            or any(packet['launch_nonce'] != stage['launch_nonce'] for packet in packets)):
        raise AssetUnavailable('qualification_delivery_changed')
    expected_ack = {'type': 'engine_start_ack', 'trial_id': identity['subject_id'], 'attempt': identity['attempt'],
        'input_hash': workspace['input_hash']}
    from improvement_native_transport import _control_json
    if hashlib.sha256(_control_json(expected_ack)).hexdigest() != ack['ack_identity_hash']:
        raise AssetUnavailable('qualification_ack_changed')
    return packets


def _authenticate_preflight(assets, principal, connection, proof, scope):
    from improvement_qualification_session import QualificationPreflight
    from improvement_native_decisions import NativeImageDecisionStore
    _fields(proof, set(QualificationPreflight.__dataclass_fields__))
    if (proof['version'] != 1 or type(proof['version']) is not int or proof['domain'] != 'qualification'
            or proof['supported'] is not False or proof['account_ready'] is not False or proof['technical_ready'] is not True
            or proof['cleanup'] != 'proven' or proof['run_hash'] != IM._hash(scope)
            or proof['pin_hash'] != scope['pin_hash'] or proof['release_fingerprint'] != scope['release_fingerprint']
            or proof['review_hash'] != scope['review_hash']): raise AssetUnavailable('qualification_preflight_changed')
    scope_hash = IM._hash(dict(version=1, domain='qualification', run_hash=proof['run_hash'], phase='preflight'))
    payload = dict(scope_hash=scope_hash, launch_nonce=proof['launch_nonce'], trace_hash=proof['trace_hash'], engine_config_hash=scope['pin_hash'])
    key = 'native-preflight:' + IM._hash([scope_hash, proof['launch_nonce'], proof['trace_hash']])
    record = assets._replay(connection, principal.brain_id, key, 'native_preflight_evidence', payload)
    if record is None: raise AssetUnavailable('qualification_preflight_unavailable')
    _fields(record, {'version', *payload, 'blob_hashes'})
    if record['version'] != 1 or any(record[name] != item for name, item in payload.items()):
        raise AssetUnavailable('qualification_preflight_changed')
    raw = b''.join(assets.blobs.read(principal.brain_id, digest) for digest in record['blob_hashes'])
    if hashlib.sha256(raw).hexdigest() != proof['trace_hash']: raise AssetUnavailable('qualification_preflight_changed')
    packets = _parse(raw)
    completions = [packet['body']['runtime'] for packet in packets if packet['body']['type'] == 'preflight_complete']
    if len(completions) != 1 or IM._hash(completions[0]) != proof['observation_hash']:
        raise AssetUnavailable('qualification_preflight_changed')
    actual = []
    for purpose in ('adapter_version', 'auth_status'):
        dispatches = [packet for packet in packets if packet['body']['type'] == 'dispatch_observed' and packet['body']['purpose'] == purpose]
        images = [packet for packet in packets if packet['body']['type'] == 'image_observed' and packet['body']['purpose'] == purpose]
        if len(dispatches) != 1 or len(images) != 1: raise AssetUnavailable('qualification_preflight_changed')
        packet, dispatch, image_packet = dispatches[0], dispatches[0]['body'], images[0]
        wire = dict(version=2, sequence=image_packet['source_sequence'],
            **{key: packet[key] for key in ('launch_nonce', 'worker_pid', 'worker_birth')}, **image_packet['body'])
        joined = dict(version=2, **{key: packet[key] for key in ('launch_nonce', 'worker_pid', 'worker_birth')},
            purpose=purpose, **{key: dispatch[key] for key in ('nonce', 'native_pid', 'native_birth', 'dispatch_hash')},
            observation_hash=wire['observation_hash'], dispatch=dispatch['dispatch'], image=wire)
        decision = NativeImageDecisionStore(assets).read(principal, joined, scope_hash=scope_hash, connection=connection)
        if decision['decision'] != 'allow' or dispatch['dispatch']['environment_hash'] != proof['environment_hash']:
            raise AssetUnavailable('qualification_preflight_changed')
        actual.append(decision['durable_evidence_hash'])
    if actual != proof['decision_hashes']: raise AssetUnavailable('qualification_preflight_changed')


class QualificationQueryResults:
    def __init__(self, session):
        from improvement_qualification_session import QualificationSession
        if type(session) is not QualificationSession: raise TypeError('concrete_qualification_session_required')
        self.session = session

    def stage(self, owner, principal, identifier, *, expected_generation, lease_token, binding, native_completion):
        from improvement_native_trace_checks import validated_history, validate_native_trace, require_durable_allow
        from improvement_native_decisions import NativeImageDecisionStore, attempt_scope
        from improvement_trial_evidence import decode_trace
        from improvement_trial_checks import execution_invariants
        from improvement_sandbox import trial_system_prompt
        session = self.session
        context = session._query_current(binding)
        if (context['owner'] is not owner or principal is not session.principal or identifier != binding.subject_id
                or lease_token != context['lease_token'] or type(native_completion) is not _NativeCompletion
                or context['completion'] is not native_completion or native_completion.boundary is not context['boundary']):
            raise PermissionError('qualification_completion_foreign')
        boundary = context['boundary']
        with closing(session.assets.store._conn()) as connection:
            row, attempt = owner._leased(connection, principal, identifier, expected_generation, lease_token, time.time())
            records = list(connection.execute('SELECT * FROM improvement_trial_observations WHERE trial_id=? AND attempt=? ORDER BY sequence',
                (identifier, binding.attempt)))
            packets = validated_history(records, lambda row: decode_trace(owner.blobs, principal.brain_id, row), kind='trial', receipt=context['receipt'])
            if packets != [boundary._qualification_packets[key] for key in sorted(boundary._qualification_packets)]:
                raise PermissionError('qualification_completion_trace_changed')
            contract = json.loads(connection.execute('SELECT contract_json FROM improvement_contracts WHERE brain_id=? AND manifest_hash=?',
                (principal.brain_id, context['request']['pins']['contract_hash'])).fetchone()[0])
            scope = attempt_scope(kind='trial', brain_id=principal.brain_id, receipt=context['receipt'],
                config_pin=session._pin, capability_hash=binding.authority_hash)
            decisions = NativeImageDecisionStore(session.assets)
            read_decision = lambda joined: decisions.read(principal, joined, scope_hash=scope, connection=connection)
            manifest = context['manifest']
            prompt = IM._json({'task': manifest['case']['task'], 'fixtures': [
                {key: item[key] for key in ('snapshot_id', 'source')} for item in manifest['case']['fixtures']]})
            native = validate_native_trace(packets, kind='trial', receipt=context['receipt'], pin=session._pin,
                capability_hash=binding.authority_hash, system_prompt=trial_system_prompt(manifest), user_prompt=prompt,
                data_hash=binding.materialization_hash, read_decision=read_decision, tool_policy='baseline_inline')
            require_durable_allow(native)
            checks = execution_invariants(context['request'], manifest, context['receipt'], packets, binding.authority_hash,
                contract=contract, read_decision=read_decision)
        installations = [body['event'] for body in native['worker_bodies'] if body['type'] == 'engine_event'
            and body['event'].get('type') == 'installation_receipt']
        terminals = [body['event'] for body in native['worker_bodies'] if body['type'] == 'engine_event'
            and body['event'].get('type') == 'terminal']
        if len(installations) != 1 or len(terminals) != 1 or type(terminals[0]['is_error']) is not bool:
            raise PermissionError('qualification_execution_incomplete')
        if any(check['verdict'] != 'pass' for check in checks if check['id'] in
                ('native_input_delivery', 'materialization', 'workspace_binding', 'worker_protocol')):
            raise PermissionError('qualification_execution_incomplete')
        identity = _identity(session.run_hash, 'trial', identifier, binding.attempt)
        import usage_index
        usage_events, _ = usage_index.improvement_events(context['request']['pins']['experiment_id'], identifier)
        usage_completions = [event for event in usage_events if event.get('event_kind') == 'execution'
            and event.get('source_id') == 'improvement-native-v1' and event.get('execution', {}).get('attempt') == binding.attempt]
        if len(usage_completions) != 1: raise PermissionError('qualification_usage_completion_required')
        value = dict(version=1, identity=identity, binding=asdict(binding), preflight=json.loads(IM._json(asdict(session._require_preflight()))),
            link=context['link'], request=context['request'], manifest=manifest, workspace=context['receipt'], contract=contract,
            ack=_parse(native_completion.ack), trace_hashes=[row['payload_hash'] for row in records],
            native_decisions=native['decisions'], installation_hash=installations[0]['hash'],
            input_delivery_hash=native_completion.input_delivery_hash, checks=checks,
            execution_status='failed' if terminals[0]['is_error'] else 'completed', launch_nonce=boundary._guardian._nonce,
            environment_hash=IM._hash(boundary._qualification_seed['environment']), usage_completion=usage_completions[0])
        envelope = _write(session.assets, principal, value)
        evidence = _StagedEvidence(_STAGE, session, context, value, envelope)
        context['stage'] = evidence
        owner.finish_qualification(session, principal, identifier, expected_generation=expected_generation,
            lease_token=lease_token, evidence=evidence)
        # Only a returned transaction has committed a stage. Retain its proof
        # before cancellation can bypass the following cleanup/publication.
        session._pending_proofs[(identifier, binding.attempt)] = context
        return evidence.digest

    def publish(self, owner, principal, identifier, *, attempt, evidence_hash, cleanup_receipt):
        session = self.session
        context = session._queries.get((identifier, attempt))
        if (context is None or context['owner'] is not owner or principal is not session.principal
                or type(cleanup_receipt) is not _CleanupReceipt or cleanup_receipt is not context['cleanup']
                or cleanup_receipt.context is not context or cleanup_receipt.session is not session
                or type(context['stage']) is not _StagedEvidence or context['stage'].digest != evidence_hash
                or session._pending_proofs.get((identifier, attempt)) is not context):
            raise PermissionError('qualification_cleanup_foreign')
        binding = context['binding']
        identity = _identity(session.run_hash, 'trial', identifier, attempt)
        stage = _parse(context['stage'].raw)
        cleanup = _parse(cleanup_receipt.raw)
        cleanup_envelope = _write(session.assets, principal, cleanup)
        result = dict(version=1, domain='qualification', supported=False, account_ready=False, business_proof=False,
            **identity, **{name: stage['binding'][name] for name in ('request_hash', 'materialization_hash', 'workspace_hash', 'engine_config_hash', 'preflight_hash')},
            query_authority_hash=binding.authority_hash, attempt_link_hash=IM._hash(stage['link']),
            release_fingerprint=session._scope['release_fingerprint'], review_hash=session._scope['review_hash'],
            launch_nonce=stage['launch_nonce'], environment_hash=stage['environment_hash'],
            call_id=stage['ack']['call_id'], engine_at=stage['ack']['engine_at'],
            **{name: stage[name] for name in ('trace_hashes', 'native_decisions', 'installation_hash', 'input_delivery_hash', 'checks', 'execution_status')},
            cleanup='proven', cleanup_evidence_hash=IM._hash(cleanup))
        value = dict(version=1, result=result, evidence_hash=evidence_hash, cleanup=cleanup_envelope)
        envelope = _write(session.assets, principal, value)
        with session.assets.store._Tx(session.assets.store) as connection:
            session._query_current(binding, connection=connection, workspace=False, leased=False)
            stored, _ = _stored(session.assets, principal, connection, _EVIDENCE, identity)
            if stored != stage: raise AssetUnavailable('qualification_stage_changed')
            _authenticate(session.assets, principal, connection, stage, terminal=True)
            if (context['boundary']._owner_state != 'DETACHED' or any(
                    key == (identifier, attempt) and task is not context.get('publisher')
                    for task, key in session._host_operations.items())
                    or Path(context['receipt']['path']).exists()):
                raise PermissionError('qualification_attempt_owners_unsettled')
            session.assets._event(connection, principal, _key(_FINAL, identity), _FINAL, identity, envelope)
            session._query_current(binding, connection=connection, workspace=False, leased=False)
            _authenticate(session.assets, principal, connection, stage, terminal=True)
            session._assert_native_current(connection=connection)
        session._pending_proofs.pop((identifier, attempt), None)
        session._assert_native_current()
        return QualificationQueryResult(_RESULT, result)

    def _save_cleanup_diagnostic(self, context):
        """Close/expiry may save owned cleanup facts, never a successful result."""
        session = self.session
        binding = context['binding']
        if (session._queries.get((binding.subject_id, binding.attempt)) is not context
                or type(context['stage']) is not _StagedEvidence or type(context['cleanup']) is not _CleanupReceipt
                or context['cleanup'].context is not context or context['cleanup'].session is not session
                or context['boundary']._owner_state != 'DETACHED' or Path(context['receipt']['path']).exists()):
            raise PermissionError('qualification_cleanup_unproven')
        identity = _identity(session.run_hash, binding.kind, binding.subject_id, binding.attempt)
        cleanup = _parse(context['cleanup'].raw)
        envelope = _write(session.assets, session.principal, cleanup)
        with session.assets.store._Tx(session.assets.store) as connection:
            stage, _ = _stored(session.assets, session.principal, connection, _EVIDENCE, identity)
            if IM._hash(stage) != context['stage'].digest: raise AssetUnavailable('qualification_stage_changed')
            _authenticate(session.assets, session.principal, connection, stage, terminal=True)
            operation = 'native_qualification_query_cleanup_diagnostic'
            session.assets._event(connection, session.principal, _key(operation, identity), operation, identity, envelope)
        session._pending_proofs.pop((binding.subject_id, binding.attempt), None)

    @staticmethod
    def read_stored(assets, principal, *, kind, subject_id, attempt, expected_run_hash):
        _digest(expected_run_hash)
        if assets.qualification_anchor != expected_run_hash or kind != 'trial':
            raise PermissionError('qualification_run_anchor_required')
        identity = _identity(expected_run_hash, kind, subject_id, attempt)
        with closing(assets.store._conn()) as connection:
            scope = read_run(assets, principal, connection=connection)
            if scope is None or IM._hash(scope) != expected_run_hash: raise AssetUnavailable('qualification_run_changed')
            stage, stage_envelope = _stored(assets, principal, connection, _EVIDENCE, identity)
            final, _ = _stored(assets, principal, connection, _FINAL, identity)
            _fields(final, {'version', 'result', 'evidence_hash', 'cleanup'})
            if type(final['version']) is not int or final['version'] != 1 or final['evidence_hash'] != stage_envelope['content_hash']:
                raise AssetUnavailable('qualification_final_changed')
            _authenticate(assets, principal, connection, stage, terminal=True)
            cleanup = _read(assets, principal, final['cleanup'])
            _fields(cleanup, {*identity, 'version', 'workspace_hash', 'evidence_hash', 'workspace_removed', 'lifetime_released', 'native_drained'})
            result = final['result']; _validate_result(result)
            if (any(cleanup[name] != item or result[name] != item for name, item in identity.items())
                    or type(cleanup['version']) is not int or cleanup['version'] != 1
                    or any(cleanup[name] is not True for name in ('workspace_removed', 'lifetime_released', 'native_drained'))
                    or cleanup['evidence_hash'] != final['evidence_hash'] or cleanup['workspace_hash'] != stage['binding']['workspace_hash']
                    or result['cleanup_evidence_hash'] != IM._hash(cleanup)
                    or result['query_authority_hash'] != stage['binding']['authority_hash']
                    or result['attempt_link_hash'] != IM._hash(stage['link'])
                    or result['call_id'] != stage['ack']['call_id'] or result['engine_at'] != stage['ack']['engine_at']
                    or result['release_fingerprint'] != scope['release_fingerprint'] or result['review_hash'] != scope['review_hash']
                    or any(result[name] != stage['binding'][name] for name in ('request_hash', 'materialization_hash', 'workspace_hash', 'engine_config_hash', 'preflight_hash'))
                    or any(result[name] != stage[name] for name in ('trace_hashes', 'native_decisions', 'installation_hash', 'input_delivery_hash', 'checks', 'execution_status', 'launch_nonce', 'environment_hash'))):
                raise AssetUnavailable('qualification_final_changed')
            return QualificationQueryResult(_RESULT, result)
