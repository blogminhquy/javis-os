"""One concrete SQL/cleanup schedule, without native or grant readiness claims."""
import json
from contextlib import closing

import improvement_store as IM
from improvement_comparison_plans import ExperimentPlans
from improvement_comparison_links import comparison_table, experiment_trial_scope
from improvement_operation_schema import TERMINAL as ROLE_TERMINAL
from improvement_trial_records import _brain
from improvement_trials import TrialStore, TERMINAL


class ComparisonSchedule:
    def __init__(self, plans, trials):
        if (type(plans) is not ExperimentPlans or type(trials) is not TrialStore
                or trials.assets is not plans.assets or trials.store is not plans.store
                or trials.workspace.root != plans.admission.trials.workspace.root):
            raise TypeError('concrete_same_store_schedule_required')
        self.plans, self.trials = plans, trials
        self.store, self.records = plans.store, plans.records

    def require_idle(self, connection, brain, experiment_id):
        scope, parameters = experiment_trial_scope(connection, brain, experiment_id)
        terminal = tuple(sorted(TERMINAL))
        if connection.execute('SELECT 1 FROM improvement_trials t JOIN (' + scope + ') l '
                'ON l.trial_id=t.id AND l.brain_id=t.brain_id WHERE t.status NOT IN (' +
                ','.join('?' for _ in terminal) + ') LIMIT 1', (*parameters, *terminal)).fetchone():
            raise IM.ConflictError('experiment_work_pending')
        if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='improvement_operations'").fetchone():
            terminal = tuple(sorted(ROLE_TERMINAL))
            if connection.execute('SELECT 1 FROM improvement_operations WHERE brain_id=? AND experiment_id=? '
                    'AND status NOT IN (' + ','.join('?' for _ in terminal) + ') LIMIT 1',
                    (brain, experiment_id, *terminal)).fetchone():
                raise IM.ConflictError('experiment_work_pending')

    def next_slot(self, principal, experiment_id, comparison_id, expected_generation, event_key):
        brain = _brain(principal)
        with closing(self.store._conn()) as connection:
            # An admission replay already chose its immutable slot. Recover it
            # before current-state checks, then Admission verifies the exact event.
            event = connection.execute("SELECT operation,result_json FROM improvement_events WHERE brain_id=? AND event_key=?",
                                       (brain, event_key)).fetchone()
            if event is not None:
                if event["operation"] not in ("experiment_admit_slot", "experiment_admit_view_slot"):
                    raise IM.ConflictError("event_payload_conflict")
                saved = json.loads(event["result_json"])
                trial = self.trials._row(connection, brain, saved["trial_id"])
                return json.loads(trial["request_json"])["lineage"]["cell_position"]
            row = self.records._row(connection, brain, experiment_id)
            self.records._public(row)
            if row["generation"] != expected_generation or row["phase"] not in ("probing", "comparing", "qualifying"):
                raise IM.ConflictError("experiment_state_stale")
            comparison = connection.execute("SELECT * FROM improvement_comparisons WHERE brain_id=? AND experiment_id=? AND id=?",
                                            (brain, experiment_id, comparison_id)).fetchone()
            if comparison is None:
                raise PermissionError("experiment_comparison_unavailable")
            table = comparison_table(connection, brain, comparison_id)
            links = list(connection.execute("SELECT l.cell_position,l.trial_id,t.status,t.attempt,a.status AS attempt_status,"
                "a.result_json,a.workspace_json FROM " + table + " l "
                "JOIN improvement_trials t ON t.id=l.trial_id AND t.brain_id=l.brain_id "
                "LEFT JOIN improvement_trial_attempts a ON a.trial_id=t.id AND a.brain_id=t.brain_id AND a.attempt=t.attempt "
                "WHERE l.brain_id=? AND l.comparison_id=? ORDER BY l.cell_position LIMIT 4001", (brain, comparison_id)))
            if ([row["cell_position"] for row in links] != list(range(len(links)))
                    or any(row["status"] not in TERMINAL or row['attempt_status'] not in TERMINAL or row['result_json'] is None for row in links)):
                raise IM.ConflictError("experiment_cell_pending_or_gapped")
            if len(links) >= comparison["cell_count"]:
                raise IM.ConflictError("experiment_comparison_exhausted")
            for link in links:
                try:
                    pointer = json.loads(link['result_json'])
                    if type(pointer) is not dict or set(pointer) != {'result_id', 'result_hash', 'blob_hash'}:
                        raise ValueError('invalid_result_pointer')
                    result = connection.execute('SELECT result_hash,blob_hash FROM improvement_trial_results '
                        'WHERE id=? AND brain_id=? AND trial_id=? AND attempt=?',
                        (pointer['result_id'], brain, link['trial_id'], link['attempt'])).fetchone()
                    if result is None or any(result[key] != pointer[key] for key in ('result_hash', 'blob_hash')):
                        raise ValueError('missing_published_result')
                    receipt = json.loads(link['workspace_json']) if link['workspace_json'] is not None else None
                    if not self.trials.workspace.cleanup_proven(link['trial_id'], link['attempt'], receipt):
                        raise ValueError('cleanup_unproven')
                except (ValueError, TypeError, KeyError) as error:
                    raise IM.ConflictError('experiment_cell_pending_or_incomplete') from error
            return len(links)

