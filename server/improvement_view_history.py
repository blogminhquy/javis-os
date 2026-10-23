"""Immutable view SQL/blob history only; no host, authoring or native backedges."""
import hashlib
import json

import improvement_store as IM
from improvement_experiment_lineage import _row, _same
from improvement_experiment_protocol import comparison_hash
from improvement_view_protocol import view_manifest


def metadata(connection, brain, comparison_id):
    binding = connection.execute('SELECT * FROM improvement_comparison_views WHERE comparison_id=? AND brain_id=?',
        (comparison_id, brain)).fetchone()
    if binding is None:
        return None
    views = {}
    for variant, column in (('baseline', 'base_view_id'), ('candidate', 'candidate_view_id')):
        row = connection.execute('SELECT * FROM improvement_effective_views WHERE id=? AND brain_id=? AND comparison_id=? AND variant=?',
            (binding[column], brain, comparison_id, variant)).fetchone()
        if row is None or row['semantic_receipt_id'] != binding['semantic_receipt_id']:
            raise IM.ConflictError('comparison_view_metadata_changed')
        views[variant] = {'view_id': row['id'], 'manifest_hash': row['manifest_hash']}
    return {'evidence_class': 'technical', 'comparison_id': comparison_id, 'binding_hash': binding['binding_hash'],
        'semantic_receipt_id': binding['semantic_receipt_id'], 'created_at': binding['created_at'], 'views': views}


def require_publication(connection, brain, value, current_generation):
    matches = []
    for row in connection.execute("SELECT request_hash,result_json FROM improvement_events WHERE brain_id=? "
            "AND operation='comparison_views_freeze' ORDER BY id", (brain,)):
        try:
            result = json.loads(row['result_json'])
        except (ValueError, TypeError) as error:
            raise IM.ConflictError('comparison_view_publication_changed') from error
        if type(result) is dict and result.get('comparison_id') == value['comparison_id']:
            matches.append((row, result))
    if len(matches) != 1:
        raise PermissionError('comparison_view_publication_unavailable')
    row, result = matches[0]
    generation = result.get('generation')
    if (type(generation) is not int or not 2 <= generation <= current_generation
            or result != {**value, 'generation': generation}
            or row['result_json'] != IM._json(result)
            or row['request_hash'] != IM._hash({'comparison_id': value['comparison_id'], 'expected_generation': generation - 1})):
        raise IM.ConflictError('comparison_view_publication_changed')


def _json_blob(blobs, brain, digest):
    raw = blobs.read(brain, digest)
    if type(raw) is not bytes or len(raw) > 1048576 or hashlib.sha256(raw).hexdigest() != digest:
        raise IM.ConflictError('comparison_view_blob_changed')
    value = json.loads(raw)
    if raw != IM._json(value).encode('utf-8'):
        raise IM.ConflictError('comparison_view_blob_changed')
    return value


def load_history(connection, brain, proof, *, blobs):
    frozen, comparison, arm = proof['definition'], proof['comparison'], proof['arm']
    saved = metadata(connection, brain, comparison['id'])
    if saved is None:
        raise PermissionError('comparison_views_unavailable')
    experiment = _row(connection, 'improvement_experiments', brain, frozen['experiment_id'])
    require_publication(connection, brain, saved, experiment['generation'])
    binding = connection.execute('SELECT * FROM improvement_comparison_views WHERE comparison_id=? AND brain_id=?',
        (comparison['id'], brain)).fetchone()
    if binding['binding_blob_hash'] != binding['binding_hash']:
        raise IM.ConflictError('comparison_view_binding_changed')
    receipt = _row(connection, 'improvement_semantic_receipts', brain, saved['semantic_receipt_id'])
    _same({'candidate_id': arm['candidate_id'], 'experiment_id': frozen['experiment_id']}, receipt)
    receipt_binding = _json_blob(blobs, brain, receipt['binding_blob_hash'])
    evidence = _json_blob(blobs, brain, receipt['blob_hash'])
    _same({'version': 1, 'candidate_id': arm['candidate_id'], 'definition_hash': comparison['definition_hash'],
        **{key: frozen[key] for key in ('experiment_id', 'context_id', 'target_id', 'base_revision_id', 'base_hash',
            'base_generation', 'binding_hash', 'baseline_context_hash', 'engine_config_hash', 'grant_hash', 'scope_hash',
            'context_generation', 'policy_version', 'evaluator')},
        **{key: arm[key] for key in ('content_hash', 'patch_hash', 'provenance_hash', 'source_authority_hash')}}, receipt_binding)
    if (receipt['binding_blob_hash'] != receipt['binding_hash'] or evidence['binding'] != receipt_binding
            or IM._hash(evidence['assessment']) != receipt['assessment_hash']
            or IM._hash(evidence['dependencies']) != receipt_binding['dependency_hash']
            or any(evidence[key] != receipt[key] for key in ('candidate_id', 'operation_id', 'result_id'))):
        raise IM.ConflictError('semantic_receipt_changed')
    manifests = {}
    for variant in ('baseline', 'candidate'):
        row = _row(connection, 'improvement_effective_views', brain, saved['views'][variant]['view_id'])
        if row['manifest_blob_hash'] != row['manifest_hash']:
            raise IM.ConflictError('comparison_view_manifest_changed')
        manifest = view_manifest(_json_blob(blobs, brain, row['manifest_blob_hash']))
        _same({'brain_id': brain, 'comparison_id': comparison['id'], 'comparison_hash': comparison_hash(comparison),
            'definition_hash': comparison['definition_hash'], 'arm_ordinal': comparison['ordinal'],
            'arm_hash': comparison['arm_hash'], 'candidate_id': arm['candidate_id'], 'variant': variant,
            **{key: frozen[key] for key in ('experiment_id', 'context_id', 'context_generation', 'engine_config_hash',
                'baseline_context_hash', 'contract_hash', 'case_set_hash', 'grant_hash', 'scope_hash', 'policy_version')}}, manifest)
        _same({key: frozen[key] for key in ('target_id', 'base_revision_id', 'base_hash', 'base_generation')}, manifest['target'])
        _same({key: manifest[key] for key in ('brain_id', 'experiment_id', 'context_id', 'comparison_id', 'variant',
            'candidate_id', 'source_authority_hash')} | {key: manifest['target'][key] for key in ('target_id', 'base_revision_id',
            'base_hash', 'base_generation')} | {'semantic_receipt_id': receipt['id']}, row)
        if (manifest['semantic'] != {'receipt_id': receipt['id'], 'binding_hash': receipt['binding_hash'],
                'assessment_hash': receipt['assessment_hash'], 'dependency_hash': receipt_binding['dependency_hash'],
                'owner_event_key': manifest['semantic']['owner_event_key']}
                or manifest['source_authority_hash'] != receipt_binding['source_authority_hash']
                or manifest['source_authority_hash'] != arm['source_authority_hash']):
            raise IM.ConflictError('comparison_view_semantic_changed')
        asset = manifest['assets'][0]
        if asset['content_hash'] != (frozen['base_hash'] if variant == 'baseline' else arm['content_hash']):
            raise IM.ConflictError('comparison_view_content_changed')
        rows = list(connection.execute('SELECT * FROM improvement_effective_view_assets WHERE view_id=? AND brain_id=? ORDER BY position',
            (row['id'], brain)))
        if len(rows) != 1:
            raise IM.ConflictError('comparison_view_assets_changed')
        _same({'position': 0, 'asset_id': asset['id'], **{key: asset[key] for key in ('canonical_ref', 'before_hash',
            'content_hash', 'identity', 'authority_hash', 'origin')}}, rows[0])
        manifests[variant] = manifest
    baseline, candidate = manifests['baseline'], manifests['candidate']
    if baseline['target'] != candidate['target'] or baseline['semantic'] != candidate['semantic']:
        raise IM.ConflictError('comparison_view_pair_changed')
    expected = {'version': 1, 'evidence_class': 'technical', 'brain_id': brain, 'comparison_id': comparison['id'],
        'comparison_hash': baseline['comparison_hash'], 'definition_hash': comparison['definition_hash'],
        'source_authority_hash': baseline['source_authority_hash'], 'semantic': baseline['semantic'], 'views': saved['views']}
    if _json_blob(blobs, brain, binding['binding_blob_hash']) != expected:
        raise IM.ConflictError('comparison_view_binding_changed')
    owner_key = baseline['semantic']['owner_event_key']
    if owner_key is not None:
        owner = connection.execute("SELECT result_json FROM improvement_events WHERE brain_id=? AND event_key=? "
            "AND operation='semantic_owner_arbitration'", (brain, owner_key)).fetchone()
        if owner is None:
            raise PermissionError('view_semantic_owner_event_unavailable')
        _same({'candidate_id': arm['candidate_id'], 'receipt_id': receipt['id'], 'binding_hash': receipt['binding_hash'],
            'verdict': 'pass'}, json.loads(owner[0]))
    return {variant: {**saved['views'][variant], 'manifest': manifest} for variant, manifest in manifests.items()}
