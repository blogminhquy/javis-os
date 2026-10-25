"""SQL/blob-only final ownership history; never current source or native authority."""
import json

import improvement_cases as IC
import improvement_store as IM
from improvement_experiment_protocol import definition
from improvement_view_history import _json_blob

OPERATION = 'view_final_qualification_reserve'


def selection_rows(connection, brain, comparison_id):
    comparison = connection.execute('SELECT * FROM improvement_comparisons WHERE id=? AND brain_id=?',
        (comparison_id, brain)).fetchone()
    if comparison is None:
        raise PermissionError('view_final_comparison_unavailable')
    if comparison['kind'] != 'final':
        raise PermissionError('view_final_comparison_required')
    experiment = connection.execute('SELECT * FROM improvement_experiments WHERE id=? AND brain_id=?',
        (comparison['experiment_id'], brain)).fetchone()
    value = definition(json.loads(experiment['definition_json']))
    selection = connection.execute('SELECT * FROM improvement_experiment_selections WHERE experiment_id=? AND brain_id=?',
        (experiment['id'], brain)).fetchone()
    arm = connection.execute('SELECT * FROM improvement_experiment_arms WHERE experiment_id=? AND brain_id=? AND ordinal=?',
        (experiment['id'], brain, comparison['ordinal'])).fetchone()
    if (selection is None or arm is None or selection['choice'] != 'candidate' or selection['ordinal'] != comparison['ordinal']
            or selection['definition_hash'] != experiment['definition_hash'] or IM._hash(value) != experiment['definition_hash']
            or comparison['definition_hash'] != experiment['definition_hash'] or comparison['arm_hash'] != arm['envelope_hash']):
        raise PermissionError('view_final_selection_unavailable')
    event = connection.execute("SELECT * FROM improvement_events WHERE brain_id=? AND event_key=? AND operation='experiment_select'",
        (brain, selection['event_key'])).fetchone()
    if event is None:
        raise PermissionError('view_final_selection_event_unavailable')
    published = json.loads(event['result_json'])
    generation = published.get('generation')
    if (type(generation) is not int or generation < 2 or published.get('experiment_id') != experiment['id']
            or published.get('definition_hash') != experiment['definition_hash'] or published.get('phase') != 'comparing'
            or event['request_hash'] != IM._hash({'experiment_id': experiment['id'], 'choice': 'candidate',
                'ordinal': selection['ordinal'], 'expected_generation': generation - 1})):
        raise IM.ConflictError('view_final_selection_event_changed')
    declared = [row[0] for row in connection.execute('SELECT ordinal FROM improvement_experiment_arms '
        'WHERE experiment_id=? AND brain_id=? ORDER BY ordinal LIMIT 3', (experiment['id'], brain))]
    refs = json.loads(selection['evidence_json'])
    if (not 1 <= len(declared) <= 2 or type(refs) is not list or len(refs) != len(declared)
            or any(type(ref) is not list or len(ref) != 2 for ref in refs)):
        raise IM.ConflictError('view_final_selection_reports_changed')
    reports = []
    for ordinal, ref in zip(declared, refs):
        IC._text(ref[0], 128)
        IC._digest(ref[1])
        row = connection.execute('SELECT r.*,p.ordinal,p.kind,p.arm_hash,p.definition_hash FROM improvement_comparison_reports r '
            'JOIN improvement_comparisons p ON p.id=r.comparison_id AND p.brain_id=r.brain_id '
            'WHERE r.id=? AND r.brain_id=? AND r.experiment_id=?', (ref[0], brain, experiment['id'])).fetchone()
        if (row is None or row['report_hash'] != ref[1] or row['blob_hash'] != ref[1] or row['ordinal'] != ordinal
                or row['kind'] != 'tuning' or row['definition_hash'] != experiment['definition_hash']):
            raise IM.ConflictError('view_final_selection_reports_changed')
        publication = connection.execute("SELECT * FROM improvement_events WHERE brain_id=? AND operation='comparison_report' "
            "AND json_extract(result_json,'$.report_id')=? AND json_extract(result_json,'$.report_hash')=? "
            "AND json_extract(result_json,'$.comparison_id')=? AND id<? ORDER BY id DESC LIMIT 1",
            (brain, row['id'], row['report_hash'], row['comparison_id'], event['id'])).fetchone()
        if publication is None:
            raise PermissionError('view_final_report_publication_unavailable')
        body = json.loads(publication['result_json'])
        public_generation = body.get('generation')
        if (set(body) != {'report_id', 'report_hash', 'comparison_id', 'generation', 'complete'}
                or type(public_generation) is not int or not 2 <= public_generation < generation
                or body['complete'] is not True or publication['request_hash'] != IM._hash({
                    'comparison_id': row['comparison_id'], 'expected_generation': public_generation - 1})):
            raise IM.ConflictError('view_final_report_publication_changed')
        reports.append(dict(row))
    selection_hash = IM._hash({'version': 1, 'brain_id': brain, 'comparison_id': comparison_id,
        'definition_hash': experiment['definition_hash'], 'candidate_id': arm['candidate_id'],
        'selection_event_key': selection['event_key'], 'selection_request_hash': event['request_hash'],
        'selection_result_hash': IM._hash(published),
        'reports': [[row[key] for key in ('ordinal', 'id', 'report_hash', 'policy_hash')] for row in reports]})
    return {'experiment': dict(experiment), 'definition': value, 'comparison': dict(comparison),
        'arm': dict(arm), 'selection': dict(selection), 'reports': reports, 'selection_hash': selection_hash}


def pins_for(frame):
    value = frame['definition']
    return {key: value[key] for key in ('experiment_id', 'base_bundle_hash', 'contract_hash', 'case_set_hash',
        'engine_config_hash', 'grant_hash', 'scope_hash', 'policy_version')} | {'candidate_bundle_hash': frame['arm']['envelope_hash']}


def families(connection, brain, case_set_id):
    values = sorted({row[0] for row in connection.execute("SELECT fingerprint FROM improvement_case_families "
        "WHERE brain_id=? AND case_set_id=? AND split='qualification'", (brain, case_set_id))})
    if not values:
        raise ValueError('qualification_cases_required')
    return values


def qualification_metadata(connection, brain, request):
    if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='improvement_view_qualification_links'").fetchone() is None:
        raise PermissionError('view_qualification_unavailable')
    link = connection.execute('SELECT * FROM improvement_view_qualification_links WHERE comparison_id=? AND brain_id=?',
        (request['lineage']['comparison_id'], brain)).fetchone()
    if link is None:
        raise PermissionError('view_qualification_unavailable')
    claim = IC.CaseStore._row(connection, 'improvement_qualification', brain, link['reservation_id'])
    actual_pins = json.loads(claim['pins_json'])
    IC.CaseStore._pin_shape(actual_pins)
    case = IC.CaseStore._case(None, connection, brain, request['case_set_id'], request['case_id'])
    if (link['experiment_id'] != request['pins']['experiment_id'] or link['case_set_id'] != request['case_set_id']
            or link['candidate_id'] != request['lineage']['candidate_id'] or link['binding_hash'] != request['view']['binding_hash']
            or claim['case_set_id'] != link['case_set_id'] or actual_pins != request['pins']
            or claim['pins_hash'] != IM._hash(actual_pins) or link['pins_hash'] != claim['pins_hash']
            or claim['status'] not in ('reserved', 'consumed')
            or (claim['status'] == 'reserved') != (claim['consumed_at'] is None)
            or (case['split'] == 'qualification' and request.get('qualification_id') != claim['id'])
            or (case['split'] == 'regression' and 'qualification_id' in request) or case['split'] not in ('qualification', 'regression')):
        raise IM.ConflictError('view_qualification_request_changed')
    return dict(link), dict(claim)


def load_qualification(connection, brain, request, proof, *, blobs):
    link, claim = qualification_metadata(connection, brain, request)
    frame = selection_rows(connection, brain, proof['comparison']['id'])
    tokens = families(connection, brain, link['case_set_id'])
    claimed = sorted(row[0] for row in connection.execute('SELECT fingerprint FROM improvement_qualification_claims '
        'WHERE reservation_id=? AND brain_id=?', (claim['id'], brain)))
    if (link['selection_hash'] != frame['selection_hash'] or link['selection_event_key'] != frame['selection']['event_key']
            or request['pins'] != pins_for(frame) or claimed != tokens or link['family_hash'] != IM._hash(tokens)):
        raise IM.ConflictError('view_qualification_history_changed')
    for row in frame['reports']:
        report = _json_blob(blobs, brain, row['blob_hash'])
        if (report.get('comparison_id') != row['comparison_id'] or report.get('arm_hash') != row['arm_hash']
                or IM._hash(report['policy']) != row['policy_hash'] or report['summary'].get('complete') is not True
                or row['ordinal'] == frame['selection']['ordinal'] and report['summary'].get('selection_supported') is not True):
            raise IM.ConflictError('view_qualification_report_changed')
    payload = {'comparison_id': link['comparison_id'], 'binding_hash': link['binding_hash'], 'selection_hash': link['selection_hash']}
    expected = {key: link[key] for key in ('comparison_id', 'reservation_id', 'binding_hash', 'selection_hash', 'pins_hash', 'family_hash')}
    if IM.ImprovementStore._replay(connection, brain, link['reservation_event_key'], OPERATION, payload) != expected:
        raise PermissionError('view_qualification_event_unavailable')
    return {'link': link, 'claim': claim, 'selection': frame}
