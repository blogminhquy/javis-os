"""Authenticate existing sealed preparation history without reconstructing model input."""
from __future__ import annotations

import json

import improvement_store as IM
from improvement_trial_records import _brain


def sealed_history(inputs, connection, principal, experiment_id, generation):
    from improvement_improver_inputs import ImproverInputs
    from improvement_experiment_protocol import definition
    if type(inputs) is not ImproverInputs:
        raise TypeError('concrete_improver_inputs_required')
    brain = _brain(principal)
    row = inputs.plans.records._row(connection, brain, experiment_id)
    inputs.plans.records._public(row)
    if type(generation) is not int or row['generation'] != generation:
        raise IM.ConflictError('experiment_state_stale')
    value = definition(json.loads(row['definition_json']))
    inputs.plans.records._bound_in(connection, brain, value, value['context_generation'])
    preparation = connection.execute('SELECT * FROM improvement_preparations WHERE experiment_id=? AND brain_id=?',
                                     (experiment_id, brain)).fetchone()
    if preparation is None:
        raise IM.ConflictError('improver_preparation_incomplete')
    snapshot = inputs.preparation._completion_snapshot(connection, brain, preparation)
    complete = [json.loads(item[0]) for item in connection.execute("SELECT result_json FROM improvement_events "
        "WHERE brain_id=? AND operation='preparation_complete' ORDER BY id", (brain,))]
    complete = [item for item in complete if item.get('experiment_id') == experiment_id]
    if not complete or any(item != complete[0] for item in complete):
        raise IM.ConflictError('improver_preparation_unsealed')
    complete = complete[0]
    refs = [{'trial_id': link['trial_id'], 'attempt': link['current_attempt'], 'request_hash': link['request_hash'],
             **json.loads(link['result_json'])} for link in snapshot[0]]
    if (set(complete) != {'experiment_id', 'preparation_id', 'schedule_hash', 'phase', 'generation', 'result_refs'}
            or complete['preparation_id'] != preparation['id'] or complete['schedule_hash'] != preparation['schedule_hash']
            or complete['phase'] != 'proposing' or type(complete['generation']) is not int
            or not 1 <= complete['generation'] <= generation or complete['result_refs'] != refs):
        raise IM.ConflictError('improver_sealed_results_changed')
    evidence = []
    for ref in refs:
        identity = (ref['trial_id'], brain, ref['attempt'])
        trace = [dict(item) for item in connection.execute('SELECT * FROM improvement_trial_observations '
            'WHERE trial_id=? AND brain_id=? AND attempt=? ORDER BY sequence', identity)]
        products = {}
        for name in ('artifacts', 'receipts'):
            item = connection.execute('SELECT * FROM improvement_trial_' + name + ' WHERE trial_id=? AND brain_id=? AND attempt=?', identity).fetchone()
            products[name] = dict(item) if item is not None else None
        evidence.append({'trace': trace, **products})
    return {'preparation': dict(preparation), 'completion': complete,
            'links': snapshot[0], 'attempts': snapshot[1], 'evidence': evidence}
