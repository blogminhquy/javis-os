"""Closed v4 Trial shape and identity; no source, grant, SQL or native authority."""
from improvement_cases import _fields
from improvement_store import _hash, _json
from improvement_experiment_protocol import _freeze, _id, _digest, validate_request_v2


def validate_request_v4(value):
    request = _freeze(value)
    required = {'version', 'pins', 'case_set_id', 'case_id', 'variant', 'repeat', 'engine_config',
                'baseline_context_hash', 'target_generations', 'deadline_at', 'lineage', 'view'}
    if (type(request) is not dict or set(request) not in (required, required | {'qualification_id'})
            or type(request.get('version')) is not int or request['version'] != 4):
        raise ValueError('invalid_view_trial_request')
    descriptor = request['view']
    _fields(descriptor, {'view_id', 'view_hash', 'binding_hash'})
    _id(descriptor['view_id'])
    _digest(descriptor['view_hash'])
    _digest(descriptor['binding_hash'])
    # Reuse pure common shape checks only. This copy never reaches a request
    # hash, logical slot, database, host authorization or runtime consumer.
    common = {key: child for key, child in request.items() if key != 'view'}
    common['version'] = 2
    normalized = validate_request_v2(common)
    normalized.update(version=4, view=descriptor)
    if len(_json(normalized).encode('utf-8')) > 65536:
        raise ValueError('view_trial_request_too_large')
    return normalized


def logical_key_v4(value):
    request = validate_request_v4(value)
    lineage, view = request['lineage'], request['view']
    return _hash(['improvement-trial-v4', request['pins']['experiment_id'], lineage['comparison_id'],
        lineage['comparison_hash'], lineage['arm_hash'], lineage['pair_id'], lineage['cell_position'],
        request['case_set_id'], request['case_id'], request['repeat'], request['variant'],
        view['view_id'], view['view_hash'], view['binding_hash']])
