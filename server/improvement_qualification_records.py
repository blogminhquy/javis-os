"""Authenticated engineering-domain history in the existing encrypted M0 owner.

An expected run anchor comes from a trusted store factory, never model/report
JSON. Missing records in an anchored store fail closed. These records are not
native provenance, launch permission, production readiness or account authority.
"""
from __future__ import annotations

from contextlib import closing
import hashlib
import json
import math
from pathlib import Path

import improvement_store as IM
from improvement_blobs import AssetUnavailable
from improvement_native_protocol import _canonical, _digest, _fields, _parse, _text
from improvement_qualification_environment import _endpoint

_RUN = 'native_qualification_session'
_ATTEMPT = 'native_qualification_attempt'


def _read_blob(assets, brain, envelope, *, expected_hash):
    _digest(envelope['blob_hash'])
    raw = assets.blobs.read(brain, envelope['blob_hash'])
    if hashlib.sha256(raw).hexdigest() != expected_hash:
        raise AssetUnavailable('qualification_record_changed')
    value = _parse(raw)
    if _canonical(value) != raw: raise AssetUnavailable('qualification_record_changed')
    return value


def read_run(assets, principal, *, connection=None):
    """Cold history authentication; absent ordinary history remains ordinary."""
    if type(assets) is not IM.ImprovementStore:
        raise TypeError('concrete_qualification_store_required')
    brain = IM._brain(principal)
    if connection is None:
        with closing(assets.store._conn()) as conn:
            return read_run(assets, principal, connection=conn)
    anchor = assets.qualification_anchor
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='improvement_events'").fetchone():
        if anchor is not None: raise AssetUnavailable('qualification_run_unavailable')
        return None
    roots = list(connection.execute("SELECT * FROM improvement_events WHERE brain_id=? AND "
        "(operation=? OR event_key LIKE 'native-qualification:%')", (brain, _RUN)))
    if anchor is None:
        if roots or connection.execute("SELECT 1 FROM improvement_events WHERE brain_id=? AND "
                "(operation=? OR event_key LIKE 'qualification-attempt:%')", (brain, _ATTEMPT)).fetchone():
            raise PermissionError('qualification_store_anchor_required')
        return None
    _digest(anchor)
    if len(roots) != 1 or roots[0]['event_key'] != 'native-qualification:' + anchor:
        raise AssetUnavailable('qualification_run_unavailable')
    envelope = assets._replay(connection, brain, 'native-qualification:' + anchor, _RUN, {'run_hash': anchor})
    _fields(envelope, {'version', 'run_hash', 'blob_hash'})
    if type(envelope['version']) is not int or envelope['version'] != 1 or envelope['run_hash'] != anchor:
        raise AssetUnavailable('qualification_run_changed')
    scope = _read_blob(assets, brain, envelope, expected_hash=anchor)
    _fields(scope, {'version', 'domain', 'account_ready', 'run_nonce', 'root', 'brain_id', 'pin_hash',
        'release_fingerprint', 'review_hash', 'endpoint', 'maximum_queries', 'created_at', 'deadline_at'})
    if (type(scope['version']) is not int or scope['version'] != 1 or scope['domain'] != 'qualification'
            or scope['account_ready'] is not False or scope['brain_id'] != brain
            or type(scope['maximum_queries']) is not int or not 1 <= scope['maximum_queries'] <= 32):
        raise AssetUnavailable('qualification_run_changed')
    for name in ('run_nonce', 'pin_hash', 'release_fingerprint', 'review_hash'): _digest(scope[name])
    _endpoint(scope['endpoint']); _text(scope['root'], 4000)
    for name in ('created_at', 'deadline_at'):
        if type(scope[name]) not in (int, float) or not math.isfinite(scope[name]):
            raise AssetUnavailable('qualification_run_changed')
    if not 0 < scope['deadline_at'] - scope['created_at'] <= 3600:
        raise AssetUnavailable('qualification_run_changed')
    root = Path(scope['root'])
    if (not root.is_absolute() or '..' in root.parts or str(root) != scope['root']
            or not assets.store.path.is_relative_to(root) or not assets.blobs.root.is_relative_to(root)):
        raise AssetUnavailable('qualification_store_changed')
    return scope


def require_product_store(assets, principal, *, connection=None):
    """Refuse an authenticated engineering store even without a report label."""
    if read_run(assets, principal, connection=connection) is not None:
        raise PermissionError('non_product_execution_domain')


def _key(kind, subject_id, attempt):
    if type(kind) is not str or kind not in ('trial', 'operation'):
        raise ValueError('invalid_qualification_subject')
    _text(subject_id, 160)
    if type(attempt) is not int or not 1 <= attempt < 2 ** 63:
        raise ValueError('invalid_qualification_attempt')
    return 'qualification-attempt:' + IM._hash([kind, subject_id, attempt])


def actual_binding(assets, principal, *, kind, subject_id, attempt, capability_hash, run_hash, connection):
    """Authenticate immutable joins against actual SQL, without live FS access."""
    _key(kind, subject_id, attempt); _digest(capability_hash); _digest(run_hash)
    brain = IM._brain(principal)
    # Table names come exclusively from the closed built-in kind inventory.
    prefix, identity = ('improvement_trials', 'trial_id') if kind == 'trial' else ('improvement_operations', 'operation_id')
    table = 'improvement_trial_attempts' if kind == 'trial' else 'improvement_operation_attempts'
    row = connection.execute(f'SELECT * FROM {prefix} WHERE id=? AND brain_id=?', (subject_id, brain)).fetchone()
    attempt_row = connection.execute(f'SELECT * FROM {table} WHERE {identity}=? AND brain_id=? AND attempt=?',
        (subject_id, brain, attempt)).fetchone()
    if row is None or attempt_row is None or not attempt_row['workspace_json']:
        raise AssetUnavailable('qualification_attempt_unavailable')
    request = json.loads(row['request_json'])
    if IM._hash(request) != row['request_hash']: raise AssetUnavailable('qualification_request_changed')
    if kind == 'trial':
        pin, experiment, purpose = request['engine_config'], request['pins']['experiment_id'], 'improve_probe'
    else:
        from improvement_trial_records import HostContextRecords
        context = connection.execute('SELECT * FROM improvement_trial_contexts WHERE id=? AND brain_id=?',
            (row['context_id'], brain)).fetchone()
        if context is None: raise AssetUnavailable('qualification_context_unavailable')
        pin = HostContextRecords(assets)._decode(context)['engine_config']
        experiment, purpose = row['experiment_id'], row['purpose']
    scope = read_run(assets, principal, connection=connection)
    if scope is None or IM._hash(scope) != run_hash or IM._hash(pin) != scope['pin_hash']:
        raise AssetUnavailable('qualification_configuration_changed')
    workspace = json.loads(attempt_row['workspace_json'])
    if (workspace.get(identity) != subject_id or type(workspace.get('attempt')) is not int
            or workspace['attempt'] != attempt):
        raise AssetUnavailable('qualification_workspace_changed')
    _digest(attempt_row['materialization_hash'])
    if attempt_row['materialization_hash'] != workspace.get('input_hash'):
        raise AssetUnavailable('qualification_materialization_changed')
    path = Path(workspace['path'])
    if '..' in path.parts or not path.is_absolute() or not path.is_relative_to(Path(scope['root'])):
        raise AssetUnavailable('qualification_workspace_foreign')
    call = connection.execute('SELECT * FROM agent_calls WHERE id=?', (attempt_row['call_id'],)).fetchone()
    expected = {'brain_id': brain, 'purpose': purpose, 'context_ref': 'improvement:' + experiment,
        'mirror_ref': 'improvement_' + kind + ':' + subject_id,
        'reason_ref': 'improvement_' + kind + ':' + subject_id + ':attempt:' + str(attempt), 'attempt': attempt}
    if (call is None or any(call[name] != value for name, value in expected.items())
            or call['engine_at'] != attempt_row['engine_at']):
        raise IM.ConflictError('qualification_call_binding_changed')
    return {'version': 1, 'domain': 'qualification', 'run_hash': run_hash, 'brain_id': brain,
        'kind': kind, 'subject_id': subject_id, 'attempt': attempt, 'request_hash': row['request_hash'],
        'workspace_hash': IM._hash(workspace), 'materialization_hash': attempt_row['materialization_hash'],
        'engine_config_hash': IM._hash(pin), 'capability_hash': capability_hash, 'call_id': call['id'], 'call_binding': expected}


def read_attempt(assets, principal, *, kind, subject_id, attempt, capability_hash, connection=None):
    """Cold authenticated link; missing engineering links cannot become product."""
    key = _key(kind, subject_id, attempt); _digest(capability_hash)
    if connection is None:
        with closing(assets.store._conn()) as conn:
            return read_attempt(assets, principal, kind=kind, subject_id=subject_id, attempt=attempt,
                capability_hash=capability_hash, connection=conn)
    scope = read_run(assets, principal, connection=connection)
    if scope is None: return None
    run_hash = IM._hash(scope)
    envelope = assets._replay(connection, IM._brain(principal), key, _ATTEMPT, {'run_hash': run_hash})
    if envelope is None: raise AssetUnavailable('qualification_attempt_link_unavailable')
    _fields(envelope, {'version', 'run_hash', 'link_hash', 'blob_hash'})
    if type(envelope['version']) is not int or envelope['version'] != 1 or envelope['run_hash'] != run_hash:
        raise AssetUnavailable('qualification_attempt_link_changed')
    _digest(envelope['link_hash'])
    recorded = _read_blob(assets, IM._brain(principal), envelope, expected_hash=envelope['link_hash'])
    actual = actual_binding(assets, principal, kind=kind, subject_id=subject_id, attempt=attempt,
        capability_hash=capability_hash, run_hash=run_hash, connection=connection)
    if recorded != actual: raise AssetUnavailable('qualification_attempt_link_changed')
    return recorded
