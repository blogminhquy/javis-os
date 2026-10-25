"""Concrete linked tuning inputs; never install an A candidate as an M0 revision."""
import json

import improvement_cases as IC
import improvement_store as IM
from improvement_sandbox import _manifest
from improvement_view_trial_protocol import validate_request_v4


def materialize_view(trials, connection, row, baseline_context, principal):
    request = validate_request_v4(json.loads(row['request_json']))
    if IM._hash(baseline_context) != request['baseline_context_hash']:
        raise IM.ConflictError('trial_context_drift')
    from improvement_native_formats import input_version
    version = input_version(request['engine_config'], 'view')
    brain = row['brain_id']
    case = trials._current(connection, brain, request, trial_id=row['id'], principal=principal)
    resolved, _ = trials._views.resolve_request(principal, request, connection=connection,
        require_link=True, trial_id=row['id'])
    asset = resolved.manifest['assets'][0]
    pins = request['pins']
    contract = json.loads(connection.execute('SELECT contract_json FROM improvement_contracts '
        'WHERE brain_id=? AND manifest_hash=?', (brain, pins['contract_hash'])).fetchone()[0])
    public = IC.public_contract(contract)
    result = _manifest({'version': version, 'brain_id': brain,
        'bundle_hash': pins['base_bundle_hash' if request['variant'] == 'baseline' else 'candidate_bundle_hash'],
        'engine_config_hash': pins['engine_config_hash'], 'contract_hash': pins['contract_hash'],
        'grant_hash': pins['grant_hash'], 'baseline_context': baseline_context,
        'public_contract': {'content': public, 'hash': IM._hash(public)},
        'assets': [{'id': asset['id'], 'path': asset['canonical_ref'], 'hash': asset['content_hash'],
            'content': resolved.content.decode('utf-8')}],
        'case': trials.cases._solver(connection, brain, case),
        'learning_origin': 'qualification' if case['split'] == 'qualification' else 'trial',
        'effective_view': request['view']})
    # Refresh actual source/meaning/grants after every decrypted solver input.
    # The outer transaction records exposure only after this proof succeeds.
    trials._current(connection, brain, request, trial_id=row['id'], principal=principal)
    return result
