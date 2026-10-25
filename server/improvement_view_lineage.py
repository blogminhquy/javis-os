"""Explicit v4 SQL/blob lineage; current host observation remains a separate gate."""
import improvement_store as IM
from improvement_blobs import AssetUnavailable
from improvement_experiment_lineage import _comparison_proof, _row, _same, current_fences
from improvement_view_history import load_history
from improvement_view_trial_protocol import validate_request_v4


def load_view_lineage(connection, brain, value, *, blobs, current, require_link, trial_id=None):
    if type(current) is not bool or type(require_link) is not bool or (trial_id is not None and not require_link):
        raise ValueError('explicit_view_lineage_mode_required')
    request = validate_request_v4(value)
    try:
        proof = _comparison_proof(connection, brain, request, blobs=blobs, current=current)
        views = load_history(connection, brain, proof, blobs=blobs)
        view = views[request['variant']]
        _same({'view_id': view['view_id'], 'view_hash': view['manifest_hash'],
            'binding_hash': _binding(connection, brain, proof['comparison']['id'])}, request['view'])
        if require_link:
            link = connection.execute('SELECT * FROM improvement_view_trial_links WHERE comparison_id=? AND brain_id=? AND cell_position=?',
                (proof['comparison']['id'], brain, request['lineage']['cell_position'])).fetchone()
            if link is None:
                raise PermissionError('view_trial_link_unavailable')
            _same({'experiment_id': proof['definition']['experiment_id'], 'request_hash': IM._hash(request),
                **proof['cell'], **request['view']}, link)
            trial = _row(connection, 'improvement_trials', brain, link['trial_id'])
            if (trial['request_hash'] != link['request_hash'] or trial['request_json'] != IM._json(request)
                    or trial_id is not None and trial['id'] != trial_id):
                raise IM.ConflictError('view_trial_link_changed')
        qualification = None
        if proof['comparison']['kind'] == 'final':
            from improvement_view_qualification_history import load_qualification
            qualification = load_qualification(connection, brain, request, proof, blobs=blobs)
        elif request.get('qualification_id'):
            raise PermissionError('unexpected_qualification_claim')
        if current:
            current_fences(connection, brain, proof)
        return {**proof, 'view': view, **({'qualification': qualification} if qualification is not None else {})}
    except (IM.ConflictError, PermissionError):
        raise
    except (TypeError, ValueError, KeyError, UnicodeError, RecursionError) as error:
        raise AssetUnavailable('view_lineage_corrupt') from error


def _binding(connection, brain, comparison_id):
    row = connection.execute('SELECT binding_hash FROM improvement_comparison_views WHERE comparison_id=? AND brain_id=?',
        (comparison_id, brain)).fetchone()
    if row is None:
        raise PermissionError('comparison_views_unavailable')
    return row[0]
