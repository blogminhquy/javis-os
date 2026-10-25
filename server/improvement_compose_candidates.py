"""Typed composed drafts over the existing encrypted candidate authority.

Only the actual compose publisher uses these transaction-owned helpers. Ordinary
staging keeps its two slots. A composed draft has no inherited edit/semantic
authority; its history is authenticated again by the existing proposal reader.
"""
from __future__ import annotations

import hashlib
import json
import secrets

import improvement_cases as IC
import improvement_store as IM
from improvement_blobs import AssetUnavailable
from improvement_compose_protocol import parse_compose_output
from improvement_generation_protocol import input_bytes
from improvement_operation_records import OperationRecords
from improvement_qualification_records import require_product_store
from improvement_skill_patch import validate_body_patch
from improvement_trial_records import _brain


def decisions_document(identifier, authorization, product, parsed):
    return {'version': 1, 'kind': 'compose_decisions', 'composition_id': identifier,
        'input_hash': authorization['input_hash'], 'basis_hash': authorization['basis_hash'],
        'operation_id': product['row']['id'], 'result_id': product['record']['id'],
        'artifact_hash': product['report']['artifact']['hash'], 'output': parsed['output']}


def prepare(authoring, connection, principal, state, observed, raw, parsed, *, composition_id, event_key, stamp):
    IC.CaseStore(authoring.assets)._own_transaction(connection)
    require_product_store(authoring.assets, principal, connection=connection)
    authoring._edit_open(connection, _brain(principal), state['context']['experiment_id'])
    authoring._guard(connection, principal, state, observed)
    patch = parsed['output']['patch']
    if any(patch[key] != value for key, value in {'target_id': state['target']['id'],
            'base_revision_id': state['target']['current_revision_id'], 'before_hash': state['target']['source_hash']}.items()):
        raise IM.ConflictError('composed_candidate_scope_changed')
    checked = validate_body_patch(raw, patch, None)
    input_bytes(patch); input_bytes({'content': checked['content'].decode('utf-8')})
    if checked['content'] != parsed['content'] or checked['content_hash'] != parsed['content_hash']:
        raise AssetUnavailable('composed_candidate_bytes_changed')
    refs = authoring._evidence(connection, _brain(principal), state['context'], patch['evidence_refs'])
    provenance = {'version': 2, 'context_id': state['context']['id'], 'experiment_id': state['context']['experiment_id'],
        'target_id': patch['target_id'], 'base_revision_id': patch['base_revision_id'], 'before_hash': patch['before_hash'],
        'after_hash': checked['content_hash'], 'patch_hash': checked['patch_hash'], 'ordinal': 3,
        'source_authority_hash': observed['source_authority_hash'], 'context_generation': state['grant']['generation'],
        'authority_id': None, 'authority_generation': None, 'owner_request_event': None, 'evidence_refs': refs,
        'semantic_status': 'unreviewed', 'reference_inventory': checked['reference_inventory'],
        'dependency_status': 'unresolved', 'composition_id': composition_id}
    content = authoring.blobs.write(_brain(principal), checked['content'])
    patch_hash = authoring.blobs.write(_brain(principal), input_bytes(patch))
    provenance_hash = authoring.blobs.write(_brain(principal), input_bytes(provenance))
    if content != checked['content_hash'] or patch_hash != checked['patch_hash']:
        raise AssetUnavailable('composed_candidate_publication_changed')
    return {'id': 'isc_' + secrets.token_hex(12), 'brain_id': _brain(principal), 'context_id': state['context']['id'],
        'experiment_id': state['context']['experiment_id'], 'target_id': patch['target_id'],
        'base_revision_id': patch['base_revision_id'], 'base_hash': patch['before_hash'],
        'base_generation': state['target']['generation'], 'ordinal': 3, 'content_hash': content,
        'byte_size': checked['byte_size'], 'patch_hash': patch_hash, 'provenance_hash': provenance_hash,
        'authority_id': None, 'authority_generation': None, 'semantic_status': 'unreviewed',
        'owner_event_key': event_key, 'created_at': stamp}


def insert(authoring, connection, principal, composition_id, draft):
    IC.CaseStore(authoring.assets)._own_transaction(connection)
    brain = _brain(principal)
    require_product_store(authoring.assets, principal, connection=connection)
    published = connection.execute('SELECT * FROM improvement_compositions WHERE id=? AND brain_id=?',
        (composition_id, brain)).fetchone()
    if (published is None or published['outcome'] != 'candidate' or draft['brain_id'] != brain
            or published['candidate_id'] != draft['id'] or any(published[key] != draft[key] for key in
                ('experiment_id', 'content_hash', 'patch_hash', 'provenance_hash'))):
        raise IM.ConflictError('composed_candidate_publication_required')
    ordinals = [row[0] for row in connection.execute('SELECT ordinal FROM improvement_skill_candidates '
        'WHERE experiment_id=? AND brain_id=? ORDER BY ordinal', (draft['experiment_id'], brain))]
    if ordinals != [1, 2] or draft['ordinal'] != 3 or draft['authority_id'] is not None or draft['authority_generation'] is not None:
        raise IM.ConflictError('composed_candidate_slots_changed')
    fields = tuple(draft)
    connection.execute('INSERT INTO improvement_skill_candidates (' + ','.join(fields) + ') VALUES('
        + ','.join('?' for _ in fields) + ')', tuple(draft.values()))
    return authoring.records._public(connection, authoring.records._row(connection, brain, draft['id']))


def _load(authoring, brain, digest):
    raw = authoring.blobs.read(brain, digest)
    value = json.loads(raw)
    if type(value) is not dict or IM._json(value).encode('utf-8') != raw:
        raise AssetUnavailable('composed_provenance_blob_changed')
    return value


def read_provenance(authoring, connection, principal, candidate, provenance, patch, after):
    """Cold immutable lineage, in addition to the caller's current source guard."""
    from improvement_compose_permissions import ComposePermissions, _permission_metadata
    from improvement_operation_results import OperationResults
    from improvement_operation_execution import OperationExecution
    from improvement_trial_records import HostContextRecords
    from improvement_role_workflow import _product_checks
    brain = _brain(principal)
    require_product_store(authoring.assets, principal, connection=connection)
    row = connection.execute('SELECT * FROM improvement_compositions WHERE id=? AND brain_id=?',
        (provenance['composition_id'], brain)).fetchone()
    if (row is None or row['outcome'] != 'candidate' or row['candidate_id'] != candidate['id']
            or any(row[key] != candidate[key] for key in ('experiment_id', 'content_hash', 'patch_hash', 'provenance_hash'))
            or candidate['authority_id'] is not None or candidate['authority_generation'] is not None):
        raise AssetUnavailable('composed_provenance_link_changed')
    authorization = ComposePermissions._row(connection, brain, row['authorization_id'])
    metadata = _permission_metadata(authoring.assets, connection, authorization)
    if (authorization['context_id'] != candidate['context_id'] or any(authorization[key] != row[key]
            for key in ('experiment_id', 'input_hash', 'basis_hash'))):
        raise AssetUnavailable('composed_provenance_permission_changed')
    operation = connection.execute('SELECT * FROM improvement_operations WHERE id=? AND brain_id=?',
        (row['operation_id'], brain)).fetchone()
    result = connection.execute('SELECT * FROM improvement_operation_results WHERE id=? AND brain_id=?',
        (row['result_id'], brain)).fetchone()
    if operation is None or result is None:
        raise AssetUnavailable('composed_provenance_result_unavailable')
    OperationRecords._public(operation)
    request = json.loads(operation['request_json'])
    if (operation['kind'] != 'compose' or operation['status'] != 'completed'
            or operation['experiment_id'] != row['experiment_id'] or operation['context_id'] != candidate['context_id']
            or operation['input_hash'] != row['input_hash'] or request['compose_authorization_id'] != authorization['id']
            or request['definition_hash'] != authorization['definition_hash'] or result['operation_id'] != operation['id']
            or result['attempt'] != operation['attempt'] or result['blob_hash'] != row['output_hash']):
        raise AssetUnavailable('composed_provenance_result_changed')
    # Reuse the actual reader, including native observations and encrypted
    # durable decisions; a saved passing report alone is not intact history.
    report = OperationResults.read_stored(authoring.assets, principal, operation['id'], operation['attempt'])
    if (report.get('version') != 2 or IM._hash(report) != result['result_hash']
            or report.get('operation_id') != operation['id'] or report.get('attempt') != operation['attempt']
            or report.get('request_hash') != operation['request_hash']):
        raise AssetUnavailable('composed_provenance_report_changed')
    _product_checks(report)
    context = connection.execute('SELECT * FROM improvement_trial_contexts WHERE id=? AND brain_id=?',
        (operation['context_id'], brain)).fetchone()
    configuration = HostContextRecords(authoring.assets)._decode(context)['engine_config']
    artifact = report['artifact']
    raw_output = authoring.blobs.read(brain, artifact['blob_hash'])
    if hashlib.sha256(raw_output).hexdigest() != artifact['hash'] or len(raw_output) != artifact['byte_size']:
        raise AssetUnavailable('composed_provenance_artifact_changed')
    data = _load(authoring, brain, row['input_hash'])
    basis = _load(authoring, brain, row['basis_hash'])
    if (data.get('context_id') != candidate['context_id'] or data.get('definition_hash') != authorization['definition_hash']
            or basis.get('experiment_id') != row['experiment_id'] or basis.get('definition_hash') != authorization['definition_hash']):
        raise AssetUnavailable('composed_provenance_input_changed')
    parsed = parse_compose_output(raw_output.decode('utf-8'), data)
    document = decisions_document(row['id'], metadata,
        {'row': dict(operation), 'record': dict(result), 'report': report}, parsed)
    if (row['decisions_hash'] != row['decisions_blob_hash']
            or _load(authoring, brain, row['decisions_blob_hash']) != document or parsed['keep_base']
            or parsed['content'] != after or parsed['output']['patch'] != patch):
        raise AssetUnavailable('composed_provenance_decisions_changed')
    payload = {'authorization_id': row['authorization_id'], 'expected_generation': metadata['experiment_generation']}
    event = authoring.assets._replay(connection, brain, candidate['owner_event_key'], 'compose_generate', payload)
    if (type(event) is not dict or event.get('composition_id') != row['id'] or event.get('operation_id') != operation['id']
            or event.get('result_id') != result['id'] or event.get('status') != 'candidate_staged'
            or [item.get('candidate_id') for item in event.get('candidates', [])] != [candidate['id']]):
        raise AssetUnavailable('composed_provenance_publication_changed')
    # Reuse the actual role-call binder after every encrypted observation.
    # Late observed token/cost updates are not new execution authority and do
    # not need equality of the whole usage row.
    attempt = OperationExecution._attempt(connection, operation)
    call = OperationExecution.bound_call(connection, operation, attempt)
    if (attempt['status'] != 'completed' or attempt['engine_at'] is None or call['status'] != 'ok'
            or call['engine'] != configuration['provider'] or call['model'] != configuration['model']
            or attempt['materialization_hash'] != report['materialization_hash'] or attempt['result_json'] != IM._json(report)):
        raise AssetUnavailable('composed_provenance_call_changed')
    require_product_store(authoring.assets, principal, connection=connection)
