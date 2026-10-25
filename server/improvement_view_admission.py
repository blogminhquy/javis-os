"""Owned technical-view admission, using the existing brain barrier and ledger."""
import json
import time
from contextlib import closing

import improvement_store as IM
from improvement_claude import ClaudeTrialAdapter
from improvement_comparison_plans import ExperimentPlans
from improvement_comparison_schedule import ComparisonSchedule
from improvement_experiment_protocol import definition, comparison_matrix, comparison_hash, matrix_cell, _digest
from improvement_experiments import _identifier, _generation
from improvement_trial_admission import AdmittedTrial
from improvement_trial_records import _brain
from improvement_trials import _request
from improvement_view_trial_protocol import validate_request_v4
from improvement_views import EffectiveViews

_OPERATION = 'experiment_admit_view_slot'


class ViewExperimentAdmission:
    def __init__(self, plans, views, schedule):
        if (type(plans) is not ExperimentPlans or type(views) is not EffectiveViews or views.plans is not plans
                or type(schedule) is not ComparisonSchedule or schedule.plans is not plans):
            raise TypeError('concrete_same_store_view_admission_required')
        self.plans, self.views, self.schedule = plans, views, schedule
        self.host, self.assets, self.store = plans.host, plans.assets, plans.store
        self.trials = plans.admission.trials
        from improvement_view_qualification import ViewQualification
        self.qualification = ViewQualification(plans, views)
        self.host.bind_views(views)
        self.trials.bind_views(views)

    def _replay(self, connection, principal, payload, event_key):
        brain = _brain(principal)
        saved = self.assets._replay(connection, brain, event_key, _OPERATION, payload)
        if saved is None:
            return None
        row = self.trials._row(connection, brain, saved['trial_id'])
        request = _request(json.loads(row['request_json']))
        reserve_key = 'experiment-view-reserve-' + IM._hash([brain, event_key])
        if (request['version'] != 4 or request['pins']['experiment_id'] != payload['experiment_id']
                or request['lineage']['comparison_id'] != payload['comparison_id']
                or saved != {'trial_id': row['id'], 'request_hash': IM._hash(request), 'reserve_event_key': reserve_key}
                or row['request_hash'] != saved['request_hash']):
            raise IM.ConflictError('view_admission_replay_changed')
        link = connection.execute('SELECT * FROM improvement_view_trial_links WHERE comparison_id=? AND brain_id=? AND cell_position=?',
            (payload['comparison_id'], brain, request['lineage']['cell_position'])).fetchone()
        if (link is None or link['trial_id'] != row['id'] or link['request_hash'] != saved['request_hash']
                or any(link[key] != value for key, value in request['view'].items())
                or self.assets._replay(connection, brain, reserve_key, 'trial_reserve', request) is None):
            raise IM.ConflictError('view_admission_replay_changed')
        return AdmittedTrial(row['id'], request, reserve_key)

    def _prepare(self, connection, principal, payload, position):
        brain = _brain(principal)
        comparison = connection.execute('SELECT * FROM improvement_comparisons WHERE id=? AND brain_id=? AND experiment_id=?',
            (payload['comparison_id'], brain, payload['experiment_id'])).fetchone()
        if comparison is None:
            raise PermissionError('experiment_comparison_unavailable')
        if comparison['kind'] == 'final':
            self.qualification.preview(connection, principal, comparison['id'], expected_generation=payload['expected_generation'])
        row, prepared = self.plans._state(connection, principal, payload['experiment_id'], payload['expected_generation'],
            unsealed=comparison['kind'] == 'tuning', source_split='tuning')
        value = definition(json.loads(row['definition_json']))
        arm = self.plans._frozen_arm(connection, principal, row, prepared, comparison['ordinal'])
        if comparison['definition_hash'] != row['definition_hash'] or comparison['arm_hash'] != arm['envelope_hash']:
            raise IM.ConflictError('view_admission_comparison_changed')
        cases = connection.execute('SELECT manifest_json FROM improvement_case_sets WHERE id=? AND brain_id=?',
            (value['case_set_id'], brain)).fetchone()
        if cases is None:
            raise PermissionError('experiment_case_set_unavailable')
        manifest = json.loads(cases[0])
        splits = ('tuning',) if comparison['kind'] == 'tuning' else ('qualification', 'regression')
        matrix = comparison_matrix(value, arm['envelope_hash'], comparison['ordinal'], comparison['kind'],
            [case['id'] for case in manifest['cases'] if case['split'] in splits], manifest['seed'])
        if comparison['matrix_hash'] != IM._hash(matrix) or comparison['cell_count'] != 2 * len(matrix['pairs']):
            raise IM.ConflictError('experiment_matrix_changed')
        cell = matrix_cell(matrix, position)
        metadata = self.views._metadata(connection, brain, comparison['id'])
        if metadata is None:
            raise PermissionError('comparison_views_unavailable')
        descriptor = metadata['views'][cell['variant']]
        request = validate_request_v4({'version': 4,
            'pins': {key: value[key] for key in ('experiment_id', 'base_bundle_hash', 'contract_hash', 'case_set_hash',
                'engine_config_hash', 'grant_hash', 'scope_hash', 'policy_version')} | {'candidate_bundle_hash': arm['envelope_hash']},
            'case_set_id': value['case_set_id'], **{key: cell[key] for key in ('case_id', 'repeat', 'variant')},
            'engine_config': prepared[1]['engine_config'], 'baseline_context_hash': value['baseline_context_hash'],
            'target_generations': {value['target_id']: value['base_generation']}, 'deadline_at': 1,
            'lineage': {'version': 1, 'context_id': value['context_id'], 'definition_hash': row['definition_hash'],
                'comparison_id': comparison['id'], 'comparison_hash': comparison_hash(comparison), 'matrix_hash': comparison['matrix_hash'],
                'arm_ordinal': arm['ordinal'], 'arm_hash': arm['envelope_hash'], 'candidate_id': arm['candidate_id'],
                'pair_id': cell['pair_id'], 'cell_position': position},
            'view': {'view_id': descriptor['view_id'], 'view_hash': descriptor['manifest_hash'], 'binding_hash': metadata['binding_hash']}})
        if comparison['kind'] == 'tuning':
            self.host._bound(connection, principal, request, allow_unlinked=True)
        return request, prepared

    def admit_next(self, principal, experiment_id, comparison_id, *, expected_generation, event_key):
        brain = _brain(principal)
        _identifier(experiment_id)
        _identifier(comparison_id)
        _generation(expected_generation)
        payload = {'experiment_id': experiment_id, 'comparison_id': comparison_id, 'expected_generation': expected_generation}
        self.plans.records._available()
        with closing(self.store._conn()) as connection:
            replay = self._replay(connection, principal, payload, event_key)
            if replay is not None:
                return replay
            self.schedule.next_slot(principal, experiment_id, comparison_id, expected_generation, event_key)
            self.schedule.require_idle(connection, brain, experiment_id)
        handle = self.trials.workspace.acquire_brain_execution(brain)
        if handle is None:
            raise IM.ConflictError('view_execution_busy')
        try:
            return self._admit_owned(principal, payload, event_key)
        finally:
            handle.close()

    def _admit_owned(self, principal, payload, event_key):
        brain = _brain(principal)
        position = self.schedule.next_slot(principal, payload['experiment_id'], payload['comparison_id'], payload['expected_generation'], event_key)
        with closing(self.store._conn()) as connection:
            self.schedule.require_idle(connection, brain, payload['experiment_id'])
            prepared = self._prepare(connection, principal, payload, position)
        self.host._snapshot_observe(principal, prepared[1][1])
        def native_current(connection, joined):
            for _ in range(2):
                self.schedule.require_idle(connection, brain, payload['experiment_id'])
                if (self.schedule.next_slot(principal, payload['experiment_id'], payload['comparison_id'],
                        payload['expected_generation'], event_key) != position
                        or self._prepare(connection, principal, payload, position) != prepared):
                    raise IM.ConflictError('view_admission_authority_changed')
                self.host._snapshot_observe(principal, prepared[1][1])
            return 'allow'

        try:
            adapter = ClaudeTrialAdapter(prepared[0]['engine_config'])
            adapter.bind_native_authority(self.assets, principal, scope_hash=IM._hash({
                'version': 1, 'kind': 'view_cell_admission', 'brain_id': brain,
                'event_key_hash': IM._hash(event_key), 'request_hash': IM._hash(payload),
                'authority_hash': IM._hash(prepared[0])}), current=native_current)
            available = adapter.verify()
            if type(available) is not dict or available.get('supported') is not True:
                raise ValueError('trial_native_unavailable')
            _digest(available.get('capability_hash'))
        except (ValueError, OSError, RuntimeError):
            raise ValueError('trial_native_unavailable') from None
        reserve_key = 'experiment-view-reserve-' + IM._hash([brain, event_key])
        with self.store._Tx(self.store) as connection:
            replay = self._replay(connection, principal, payload, event_key)
            if replay is not None:
                return replay
            self.schedule.require_idle(connection, brain, payload['experiment_id'])
            if (self.schedule.next_slot(principal, payload['experiment_id'], payload['comparison_id'], payload['expected_generation'], event_key) != position
                    or self._prepare(connection, principal, payload, position) != prepared):
                raise IM.ConflictError('view_admission_authority_changed')
            request = {**prepared[0], 'deadline_at': time.time() + prepared[1][0]['timeout_seconds']}
            kind = connection.execute('SELECT kind FROM improvement_comparisons WHERE id=? AND brain_id=?',
                (payload['comparison_id'], brain)).fetchone()[0]
            if kind == 'final':
                claim = self.qualification._reserve_in(connection, principal, payload['comparison_id'],
                    expected_generation=payload['expected_generation'])
                case = self.trials.cases._case(connection, brain, request['case_set_id'], request['case_id'])
                if case['split'] == 'qualification':
                    request = validate_request_v4(request | {'qualification_id': claim})
                self.host._bound(connection, principal, request, allow_unlinked=True)
            trial = self.trials._reserve_in(connection, principal, request, event_key=reserve_key)
            self.host._bound(connection, principal, request)
            # Final real source/grant capture follows every slow linked blob read.
            self.views.resolve_request(principal, request, connection=connection, require_link=True, trial_id=trial['trial_id'])
            self.assets._event(connection, principal, event_key, _OPERATION, payload,
                {'trial_id': trial['trial_id'], 'request_hash': IM._hash(request), 'reserve_event_key': reserve_key})
            return AdmittedTrial(trial['trial_id'], request, reserve_key)
