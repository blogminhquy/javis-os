"""Owned selected-final claims in the existing CaseStore registry, never flags."""
import json
import secrets
import time

import improvement_store as IM
from improvement_cases import CaseStore
from improvement_comparison_plans import ExperimentPlans
from improvement_comparison_results import ComparisonResults
from improvement_experiments import _generation, _identifier
from improvement_trial_records import _brain
from improvement_views import EffectiveViews
from improvement_view_schema import assert_installed
from improvement_view_qualification_history import (OPERATION, selection_rows, pins_for, families,
    qualification_metadata, load_qualification)


class ViewQualification:
    def __init__(self, plans, views):
        if (type(plans) is not ExperimentPlans or type(views) is not EffectiveViews or views.plans is not plans
                or views.assets is not plans.assets or views.store is not plans.store):
            raise TypeError('concrete_same_store_qualification_required')
        self.plans, self.views = plans, views
        self.assets, self.store, self.blobs = plans.assets, plans.store, plans.blobs
        self.cases = plans.admission.trials.cases

    @staticmethod
    def _regression_aliases(connection, brain, case_set_id):
        if connection.execute("SELECT 1 FROM improvement_case_families r JOIN improvement_case_families q "
                "ON q.brain_id=r.brain_id AND q.fingerprint=r.fingerprint WHERE r.brain_id=? AND r.case_set_id=? "
                "AND r.split='regression' AND q.split='qualification' LIMIT 1", (brain, case_set_id)).fetchone():
            raise PermissionError('view_final_regression_qualification_alias')

    def _current_reports(self, connection, principal, frame):
        reader = ComparisonResults(self.plans)
        for saved in frame['reports']:
            latest = self.plans._latest_tuning_report(connection, _brain(principal), frame['experiment']['id'], saved['ordinal'])
            if latest['id'] != saved['id'] or latest['report_hash'] != saved['report_hash']:
                raise IM.ConflictError('view_final_selection_reports_changed')
            metadata = reader._metadata(connection, _brain(principal), saved['comparison_id'])
            captured = reader._snapshot(connection, _brain(principal), metadata)
            report = reader.read(principal, saved['id'])
            refs, summary = reader._evidence(principal, metadata, captured)
            policy = reader._policy(metadata['definition'])
            if (report['policy'] != policy or saved['policy_hash'] != IM._hash(policy)
                    or report['result_refs'] != refs or report['summary'] != summary or summary['complete'] is not True
                    or saved['ordinal'] == frame['selection']['ordinal'] and summary['selection_supported'] is not True):
                raise PermissionError('view_final_selection_evidence_unavailable')

    def preview(self, connection, principal, comparison_id, *, expected_generation):
        brain = _brain(principal)
        _identifier(comparison_id)
        _generation(expected_generation)
        assert_installed(connection)
        frame = selection_rows(connection, brain, comparison_id)
        if frame['experiment']['generation'] != expected_generation:
            raise IM.ConflictError('experiment_state_stale')
        # Validate grant/source/meaning before decrypting any selected report.
        self.views.load_current(principal, comparison_id, 'baseline')
        self._regression_aliases(connection, brain, frame['definition']['case_set_id'])
        self._current_reports(connection, principal, frame)
        if selection_rows(connection, brain, comparison_id) != frame:
            raise IM.ConflictError('view_final_selection_changed')
        # The final current capture follows all selected result/artifact reads.
        self.views.load_current(principal, comparison_id, 'baseline')
        return frame

    def _reserve_in(self, connection, principal, comparison_id, *, expected_generation):
        self.cases._own_transaction(connection)
        brain = _brain(principal)
        frame = self.preview(connection, principal, comparison_id, expected_generation=expected_generation)
        value, pins = frame['definition'], pins_for(frame)
        binding = self.views._metadata(connection, brain, comparison_id)
        tokens = families(connection, brain, value['case_set_id'])
        existing = connection.execute('SELECT * FROM improvement_view_qualification_links WHERE comparison_id=? AND brain_id=?',
            (comparison_id, brain)).fetchone()
        if existing is not None:
            claim = self.cases._row(connection, 'improvement_qualification', brain, existing['reservation_id'])
            owned = sorted(row[0] for row in connection.execute('SELECT fingerprint FROM improvement_qualification_claims '
                'WHERE reservation_id=? AND brain_id=?', (claim['id'], brain)))
            if (existing['selection_hash'] != frame['selection_hash'] or existing['binding_hash'] != binding['binding_hash']
                    or existing['family_hash'] != IM._hash(tokens) or owned != tokens
                    or claim['pins_json'] != IM._json(pins) or claim['pins_hash'] != IM._hash(pins)
                    or claim['status'] not in ('reserved', 'consumed')):
                raise IM.ConflictError('view_qualification_changed')
            payload = {'comparison_id': comparison_id, 'binding_hash': binding['binding_hash'], 'selection_hash': frame['selection_hash']}
            expected = {key: existing[key] for key in ('comparison_id', 'reservation_id', 'binding_hash', 'selection_hash', 'pins_hash', 'family_hash')}
            if self.assets._replay(connection, brain, existing['reservation_event_key'], OPERATION, payload) != expected:
                raise PermissionError('view_qualification_event_unavailable')
            return claim['id']
        if connection.execute('SELECT 1 FROM improvement_qualification WHERE brain_id=? AND case_set_id=?',
                (brain, value['case_set_id'])).fetchone():
            raise IM.ConflictError('qualification_already_reserved')
        self.cases._enabled(connection, brain)
        for token in tokens:
            if (connection.execute('SELECT 1 FROM improvement_qualification_claims WHERE brain_id=? AND fingerprint=?', (brain, token)).fetchone()
                    or connection.execute('SELECT 1 FROM improvement_case_exposures WHERE brain_id=? AND fingerprint=?', (brain, token)).fetchone()):
                raise IM.ConflictError('qualification_family_unavailable')
        for row in connection.execute('SELECT DISTINCT s.status,s.manifest_json FROM improvement_case_sources c '
                'JOIN improvement_snapshots s ON s.id=c.snapshot_id AND s.brain_id=c.brain_id '
                'WHERE c.case_set_id=? AND c.brain_id=?', (value['case_set_id'], brain)):
            if row['status'] != 'sufficient' or json.loads(row['manifest_json'])['grant_hash'] != pins['grant_hash']:
                raise IM.ConflictError('stale_source_grant')
        identifier, now = 'iq_' + secrets.token_hex(12), time.time()
        connection.execute('INSERT INTO improvement_qualification VALUES(?,?,?,?,?,?,?,?)',
            (identifier, brain, value['case_set_id'], IM._hash(pins), IM._json(pins), 'reserved', now, None))
        for token in tokens:
            connection.execute('INSERT INTO improvement_qualification_claims VALUES(?,?,?)', (brain, token, identifier))
        event_key = 'view-final-qualification-' + IM._hash([brain, comparison_id])
        link = {'comparison_id': comparison_id, 'brain_id': brain, 'experiment_id': value['experiment_id'],
            'reservation_id': identifier, 'case_set_id': value['case_set_id'], 'candidate_id': frame['arm']['candidate_id'],
            'selection_event_key': frame['selection']['event_key'], 'reservation_event_key': event_key,
            'selection_hash': frame['selection_hash'], 'binding_hash': binding['binding_hash'],
            'pins_hash': IM._hash(pins), 'family_hash': IM._hash(tokens), 'created_at': now}
        connection.execute('INSERT INTO improvement_view_qualification_links (' + ','.join(link) + ') VALUES ('
            + ','.join('?' for _ in link) + ')', tuple(link.values()))
        payload = {'comparison_id': comparison_id, 'binding_hash': link['binding_hash'], 'selection_hash': link['selection_hash']}
        result = {key: link[key] for key in ('comparison_id', 'reservation_id', 'binding_hash', 'selection_hash', 'pins_hash', 'family_hash')}
        self.assets._event(connection, principal, event_key, OPERATION, payload, result)
        return identifier

    def validate_current(self, connection, principal, request, proof):
        frame = self.preview(connection, principal, proof['comparison']['id'],
            expected_generation=self.plans.records._row(connection, _brain(principal), request['pins']['experiment_id'])['generation'])
        loaded = load_qualification(connection, _brain(principal), request, proof, blobs=self.blobs)
        if loaded['selection'] != frame:
            raise IM.ConflictError('view_final_selection_changed')
        return loaded

    def consume_in(self, connection, principal, request):
        self.cases._own_transaction(connection)
        link, claim = qualification_metadata(connection, _brain(principal), request)
        case = CaseStore._case(None, connection, _brain(principal), request['case_set_id'], request['case_id'])
        if case['split'] != 'qualification' or request.get('qualification_id') != claim['id']:
            raise PermissionError('view_qualification_consumption_unavailable')
        if claim['status'] == 'reserved':
            connection.execute("UPDATE improvement_qualification SET status='consumed',consumed_at=? "
                "WHERE id=? AND brain_id=? AND status='reserved'", (time.time(), claim['id'], _brain(principal)))
        return link['reservation_id']
