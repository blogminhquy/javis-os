"""Owned experiment operations over the existing trial dispatcher and ledger."""
from __future__ import annotations

import asyncio
import json
import time
from contextlib import closing

import improvement_store as IM
from improvement_comparison_plans import ExperimentPlans
from improvement_experiments import _generation, _identifier
from improvement_experiment_schema import TERMINAL_PHASES
from improvement_trial_records import _brain
from improvement_trial_runner import _drain, _settled_call
from improvement_trial_service import OwnerTrialService
from improvement_trials import TERMINAL
from improvement_execution_limits import (MAX_COMPARISON_TRIALS, MAX_PREPARATION_TRIALS,
    MAX_TRIAL_ATTEMPTS, MAX_ROLE_OPERATIONS, MAX_ROLE_ATTEMPTS)
from improvement_operation_schema import TERMINAL as ROLE_TERMINAL
from improvement_comparison_links import comparison_tables, has_view_binding, experiment_trial_scope


def _call_settled(status, engine_at):
    return status in ('ok', 'error', 'interrupted') if engine_at is not None else status == 'refunded'


class ExperimentService:
    def __init__(self, plans, trial_service):
        if (type(plans) is not ExperimentPlans or type(trial_service) is not OwnerTrialService
                or plans.host is not trial_service.host or plans.assets is not trial_service.assets
                or plans.admission.trials.store is not trial_service.trials.store
                or plans.admission.trials.workspace.root != trial_service.trials.workspace.root):
            raise TypeError("concrete_experiment_service_required")
        self.plans, self.records, self.assets = plans, plans.records, plans.assets
        self.store, self.trial_service = plans.store, trial_service
        self.trials, self.tasks = trial_service.trials, trial_service.tasks
        from improvement_experiment_admission import ExperimentAdmission
        self.admission = ExperimentAdmission(plans)
        from improvement_preparation import PreparationService
        from improvement_operation_execution import OperationExecution
        from improvement_operation_runner import OperationRunner
        from improvement_operation_tasks import OperationTasks
        from improvement_proposals import ProposalService
        from improvement_semantic_review import SemanticReview
        from improvement_compositions import ComposerService
        self.preparation = PreparationService(plans)
        self.execution = OperationExecution(plans, trial_service)
        self.operation_tasks = OperationTasks(self.execution, OperationRunner(self.execution))
        self.proposals = ProposalService(self.execution, self.operation_tasks)
        self.semantic = SemanticReview(self.execution, self.operation_tasks)
        self.composer = ComposerService(self.execution, self.operation_tasks)
        from improvement_comparison_schedule import ComparisonSchedule
        from improvement_view_admission import ViewExperimentAdmission
        from improvement_views import EffectiveViews, _retired
        self.schedule = ComparisonSchedule(plans, self.trials)
        self.views = plans.host._views
        if self.views is None or _retired(self.views):
            self.views = EffectiveViews(plans, self.semantic)
        elif self.views.semantic._closed:
            # Its original owner still holds retirement authority. Exposing a
            # new facade with a closed semantic workflow cannot restore it.
            raise IM.ConflictError('comparison_view_lifetime_unavailable')
        self.view_admission = ViewExperimentAdmission(plans, self.views, self.schedule)
        self.trials.bind_views(self.views)
        self._operations = {}
        self._loop = None
        self._closed = False
        self._closing = None

    def _bind(self):
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise RuntimeError("experiment_service_loop_changed")

    @staticmethod
    def _consume(task):
        if not task.cancelled():
            task.exception()

    async def _join(self, task):
        values, cancelled = await _drain(asyncio.gather(task, return_exceptions=True))
        if cancelled is not None:
            raise cancelled
        if isinstance(values[0], BaseException):
            raise values[0]
        return values[0]

    async def _operation(self, principal, experiment_id, event_key, kind, payload, callback):
        self._bind()
        brain = _brain(principal)
        _identifier(experiment_id)
        # Match the shared event-key contract before allocating an owned task.
        if type(event_key) is not str or not 8 <= len(event_key) <= 160:
            raise ValueError("invalid_event_key")
        if self._closed:
            raise RuntimeError("experiment_service_closed")
        key = brain, experiment_id, event_key
        digest = IM._hash([kind, payload])
        existing = self._operations.get(key)
        if existing is not None:
            if existing[0] != digest:
                raise IM.ConflictError("experiment_operation_identity_conflict")
            return await self._join(existing[2])
        task = asyncio.create_task(callback())
        self._operations[key] = digest, kind, task

        def finished(completed):
            if self._operations.get(key, (None, None, None))[2] is completed:
                self._operations.pop(key)
            self._consume(completed)

        task.add_done_callback(finished)
        return await self._join(task)

    def _snapshot(self, connection, brain, experiment_id):
        links = []
        # Preserve each format's immutable fields. Both comparison formats share
        # one bound of16,000 cells; preparation retains its separate2,000 bound.
        schema = connection.execute("SELECT version FROM improvement_schema WHERE id=1").fetchone()[0]
        comparison_formats = comparison_tables(connection)
        scopes = [(table, MAX_COMPARISON_TRIALS) for table in comparison_formats]
        comparison_count = 0
        if schema >= 6:
            scopes.append(('improvement_preparation_trial_links', MAX_PREPARATION_TRIALS))
        for table, bound in scopes:
            selected = [dict(row) for row in connection.execute(
                "SELECT l.*,t.status AS trial_status,t.generation AS trial_generation,t.attempt AS current_attempt,"
                "t.request_hash AS actual_request_hash FROM " + table + " l "
                "JOIN improvement_trials t ON t.id=l.trial_id AND t.brain_id=l.brain_id "
                "WHERE l.brain_id=? AND l.experiment_id=? ORDER BY l.trial_id LIMIT ?",
                (brain, experiment_id, bound + 1))]
            if len(selected) > bound:
                raise IM.ConflictError('experiment_trial_history_changed')
            if table in comparison_formats:
                comparison_count += len(selected)
                if comparison_count > MAX_COMPARISON_TRIALS:
                    raise IM.ConflictError('experiment_trial_history_changed')
            links.extend(selected)
        if len({link['trial_id'] for link in links}) != len(links):
            raise IM.ConflictError('experiment_trial_history_changed')
        # UNION avoids SQLite's host parameter limit at the valid 18000-cell
        # bound and scopes before reading attempts or interpreting reservations.
        selected_sql, parameters = experiment_trial_scope(connection, brain, experiment_id)
        attempts = [dict(row) for row in connection.execute(
            "SELECT a.*,c.status AS call_status,c.engine_at AS call_engine_at,c.brain_id AS call_brain_id,"
            "c.purpose AS call_purpose,c.reason_ref AS call_reason_ref,c.mirror_ref AS call_mirror_ref,"
            "c.attempt AS call_attempt,c.context_ref AS call_context_ref "
            "FROM improvement_trial_attempts a JOIN (" + selected_sql + ") l "
            "ON l.trial_id=a.trial_id AND l.brain_id=a.brain_id LEFT JOIN agent_calls c ON c.id=a.call_id "
            "ORDER BY a.trial_id,a.attempt LIMIT ?", (*parameters, MAX_TRIAL_ATTEMPTS + 1))]
        recorded_attempts = {(a["trial_id"], a["attempt"]) for a in attempts}
        if (len(attempts) > MAX_TRIAL_ATTEMPTS
                or any(link["request_hash"] != link["actual_request_hash"] for link in links)
                or recorded_attempts != {(link['trial_id'], number) for link in links for number in range(1, link['current_attempt'] + 1)}
                or any(a['call_brain_id'] != brain or a['engine_at'] != a['call_engine_at']
                    or a['call_purpose'] != 'improve_probe' or a['call_attempt'] != a['attempt']
                    or a['call_context_ref'] != 'improvement:' + experiment_id
                    or a['call_mirror_ref'] != 'improvement_trial:' + a['trial_id']
                    or a['call_reason_ref'] != 'improvement_trial:' + a['trial_id'] + ':attempt:' + str(a['attempt']) for a in attempts)):
            raise IM.ConflictError("experiment_trial_history_changed")
        roles, role_attempts = [], []
        if schema >= 6:
            roles = [dict(row) for row in connection.execute('SELECT * FROM improvement_operations '
                'WHERE brain_id=? AND experiment_id=? ORDER BY id LIMIT ?', (brain, experiment_id, MAX_ROLE_OPERATIONS + 1))]
            role_attempts = [dict(row) for row in connection.execute('SELECT a.* FROM improvement_operation_attempts a '
                'JOIN improvement_operations o ON o.id=a.operation_id AND o.brain_id=a.brain_id '
                'WHERE o.brain_id=? AND o.experiment_id=? ORDER BY a.operation_id,a.attempt LIMIT ?',
                (brain, experiment_id, MAX_ROLE_ATTEMPTS + 1))]
            if len(roles) > MAX_ROLE_OPERATIONS or len(role_attempts) > MAX_ROLE_ATTEMPTS:
                raise IM.ConflictError('experiment_role_history_changed')
            for row in roles:
                self.execution.records._public(row)
                actual = [a for a in role_attempts if a['operation_id'] == row['id']]
                if [a['attempt'] for a in actual] != list(range(1, row['attempt'] + 1)):
                    raise IM.ConflictError('experiment_role_history_changed')
                for attempt in actual:
                    attempt['bound_call'] = dict(self.execution.bound_call(connection, row, attempt))
                    if attempt['engine_at'] != attempt['bound_call']['engine_at']:
                        raise IM.ConflictError('experiment_role_history_changed')
        return links, attempts, roles, role_attempts

    def _finish_stop(self, principal, experiment_id):
        """Filesystem work outside the writer; final CAS under the real brain lock."""
        brain = _brain(principal)
        workspace = self.trials.workspace
        handle = workspace.acquire_brain_execution(brain)
        if handle is None:
            return self.records.get(principal, experiment_id)
        try:
            with closing(self.store._conn()) as connection:
                row = self.records._row(connection, brain, experiment_id)
                current = self.records._public(row)
                if row["phase"] != "stopping":
                    return current
                identity = [row[key] for key in ("generation", "stop_kind", "stop_event_key", "stop_reason", "definition_hash")]
                snapshot = self._snapshot(connection, brain, experiment_id)
            if (any(row["trial_status"] not in TERMINAL for row in snapshot[0])
                    or any(row["status"] not in TERMINAL for row in snapshot[1])
                    or any(row['status'] not in ROLE_TERMINAL for row in snapshot[2])
                    or any(row['status'] not in ROLE_TERMINAL for row in snapshot[3])
                    or any(not _call_settled(a['call_status'], a['call_engine_at']) for a in snapshot[1])
                    or any(not _call_settled(a['bound_call']['status'], a['bound_call']['engine_at']) for a in snapshot[3])):
                return current
            for attempt in snapshot[1]:
                receipt = json.loads(attempt["workspace_json"]) if attempt["workspace_json"] is not None else None
                if not workspace.cleanup_proven(attempt["trial_id"], attempt["attempt"], receipt):
                    return current
            for attempt in snapshot[3]:
                receipt = json.loads(attempt['workspace_json']) if attempt['workspace_json'] is not None else None
                if not self.execution.workspace.cleanup_proven(attempt['operation_id'], attempt['attempt'], receipt):
                    return current
            event_key = "experiment-finish-" + IM._hash([brain, experiment_id, identity[2]])
            payload = {"experiment_id": experiment_id, "stop_identity": identity}
            with self.store._Tx(self.store) as connection:
                row = self.records._row(connection, brain, experiment_id)
                if row["phase"] in TERMINAL_PHASES:
                    return self.records._public(row)
                if (row["phase"] != "stopping"
                        or [row[key] for key in ("generation", "stop_kind", "stop_event_key", "stop_reason", "definition_hash")] != identity
                        or self._snapshot(connection, brain, experiment_id) != snapshot):
                    raise IM.ConflictError("experiment_stop_state_changed")
                connection.execute("UPDATE improvement_experiments SET phase=stop_kind,generation=generation+1,updated_at=? "
                    "WHERE id=? AND brain_id=?", (time.time(), experiment_id, brain))
                result = self.records._public(self.records._row(connection, brain, experiment_id))
                self.assets._event(connection, principal, event_key, "experiment_finish_stop", payload, result)
                return result
        finally:
            handle.close()

    async def _settle_stop(self, principal, experiment_id):
        brain = _brain(principal)
        # The durable stopping fence precedes this join. No admitted native
        # handoff can escape the following refreshed immutable link snapshot.
        pending = tuple(entry[2] for key, entry in self._operations.items()
                        if key[:2] == (brain, experiment_id) and entry[1] in ('next', 'preparation_next'))
        if pending:
            await _drain(asyncio.gather(*pending, return_exceptions=True))

        def snapshot():
            with closing(self.store._conn()) as connection:
                row = self.records._row(connection, brain, experiment_id)
                current = self.records._public(row)
                if row["phase"] != "stopping":
                    return current, None, []
                return current, row["stop_event_key"], self._snapshot(connection, brain, experiment_id)

        current, stop_key, work = await _settled_call(snapshot)
        if stop_key is None:
            return current
        identifiers = [link["trial_id"] for link in work[0]]
        for identifier in identifiers:
            # A bounded number of actual reserve/prepare/run/evaluate advances.
            for _ in range(5):
                current = await asyncio.to_thread(self.trials.get, principal, identifier)
                if current["status"] in TERMINAL:
                    break
                try:
                    await self.trial_service.cancel(principal, identifier,
                        expected_generation=current["generation"],
                        event_key="experiment-cancel-" + IM._hash([brain, experiment_id, stop_key, identifier, current["generation"]]))
                    break
                except IM.ConflictError:
                    continue
        await self.tasks.drain_owned(principal, identifiers)
        # The stopping writer fences any late create/reserve/repair. Cancel the
        # actual native task BEFORE joining its whole model/publication workflow.
        # A completed DB row still needs an owner-cancel fence and a task drain.
        for role in work[2]:
            for _ in range(8):
                row = await asyncio.to_thread(self.execution.get, principal, role['id'])
                try:
                    await self.operation_tasks.cancel(principal, role['id'], expected_generation=row['generation'],
                        event_key='experiment-role-cancel-' + IM._hash([brain, experiment_id, stop_key, role['id'], row['generation']]))
                    break
                except IM.ConflictError:
                    continue
        for workflow in (self.proposals, self.semantic, self.composer):
            pending = []
            for key, entry in tuple(workflow._operations.items()):
                if key[0] != brain:
                    continue
                scope = entry[2]
                if workflow is self.composer:
                    permission = await _settled_call(workflow.permissions.get, entry[3], scope)
                    scope = permission['experiment_id']
                if scope == experiment_id:
                    pending.append(entry[1])
            if pending:
                await _drain(asyncio.gather(*pending, return_exceptions=True))
        pending = tuple(entry[2] for key, entry in self._operations.items()
            if key[:2] == (brain, experiment_id) and (entry[1].startswith('workflow:')
                or entry[1] in ('create', 'bind', 'freeze', 'report', 'resume', 'select_candidate', 'view-freeze', 'view-evidence')))
        if pending:
            await _drain(asyncio.gather(*pending, return_exceptions=True))
        return await _settled_call(self._finish_stop, principal, experiment_id)

    def _candidate_scope(self, principal, experiment_id, candidate_id):
        with closing(self.store._conn()) as connection:
            candidate = self.plans.authoring.records._row(connection, _brain(principal), candidate_id)
            if candidate['experiment_id'] != experiment_id:
                raise PermissionError('experiment_candidate_unavailable')

    def _stopped_workflow_history(self, principal, experiment_id, operation, data):
        """Replay recorded intent after stop without source reads or redispatch.

        The durable phase also protects a newly constructed service after restart;
        an in-memory stopping flag would incorrectly deny historical retries and
        disappear on restart. No new intent can pass this branch.
        """
        brain, key = _brain(principal), data['event_key']
        admitted = None
        with closing(self.store._conn()) as connection:
            experiment = self.records._row(connection, brain, experiment_id)
            self.records._public(experiment)
            if experiment['phase'] not in (*TERMINAL_PHASES, 'stopping'):
                return False, None
            if 'candidate_id' in data:
                candidate = self.plans.authoring.records._row(connection, brain, data['candidate_id'])
                if candidate['experiment_id'] != experiment_id:
                    raise PermissionError('experiment_candidate_unavailable')
            if operation in ('compose', 'compose-authorize'):
                historical, result = self.composer.permissions.replay_control(principal, experiment_id, operation, data)
                if historical:
                    return True, result
                raise IM.ConflictError('experiment_stopping')
            if operation in ('semantic-evidence', 'compose-preview'):
                raise IM.ConflictError('experiment_stopping')
            payload = {'experiment_id': experiment_id, 'expected_generation': data['expected_generation']}
            if operation == 'preparation-next':
                admitted = self.preparation._replay(connection, principal, payload, key)
                result = None
            else:
                event = {'preparation-freeze': 'preparation_owner_freeze', 'preparation-complete': 'preparation_complete',
                         'propose': 'proposal_generate', 'semantic-review': 'semantic_review',
                         'semantic-arbitrate': 'semantic_owner_arbitration'}[operation]
                if operation.startswith('semantic-'):
                    payload = {'candidate_id': data['candidate_id'], 'expected_generation': data['expected_generation']}
                if operation == 'semantic-arbitrate':
                    payload.update(receipt_id=data['receipt_id'], verdict=data['verdict'], reason=data['reason'],
                                   binding_hash=data['expected_binding_hash'])
                result = self.assets._replay(connection, brain, key, event, payload)
                if result is None and operation in ('propose', 'semantic-review'):
                    workflow = self.proposals if operation == 'propose' else self.semantic
                    start = self.assets._replay(connection, brain, workflow._start_key(brain, key), event + '_start', payload)
                    if start is not None:
                        row = self.execution._row(connection, principal, start['operation_id'])
                        result = {**start, 'status': 'operation_recorded', 'operation_status': row['status']}
            if result is not None:
                return True, result
            if admitted is None:
                raise IM.ConflictError('experiment_stopping')
        from improvement_trial_views import read_trial
        return True, read_trial(self.assets, principal, admitted.trial_id)

    async def workflow(self, principal, experiment_id, operation, value):
        """Closed owner C controls, owned before any synchronous source/SQL work."""
        from improvement_experiment_requests import validate, WORKFLOW_CONTROLS
        if operation not in WORKFLOW_CONTROLS:
            raise ValueError('invalid_experiment_control')
        data = validate(value, operation)
        _identifier(experiment_id)
        arguments = {key: item for key, item in data.items() if key != 'event_key'}

        async def execute():
            if operation.startswith('compose'):
                await _settled_call(self.composer.permissions.scope, principal, experiment_id, arguments.get('authorization_id'))
                if operation == 'compose-revoke':
                    return await _settled_call(self.composer.permissions.revoke, principal, event_key=data['event_key'], **arguments)
            historical, result = await _settled_call(self._stopped_workflow_history, principal, experiment_id, operation, data)
            if historical:
                return result
            if 'candidate_id' in arguments:
                await _settled_call(self._candidate_scope, principal, experiment_id, arguments['candidate_id'])
            if operation == 'compose':
                return await self.composer.compose(principal, event_key=data['event_key'], **arguments)
            if operation in ('compose-preview', 'compose-authorize'):
                method = self.composer.permissions.preview if operation == 'compose-preview' else self.composer.permissions.authorize
                self.composer._open()
                result = await _settled_call(method, principal, experiment_id, event_key=data['event_key'], **arguments)
                self.composer._open()
                return result
            if operation == 'propose':
                return await self.proposals.generate(principal, experiment_id, event_key=data['event_key'], **arguments)
            if operation == 'semantic-review':
                return await self.semantic.review(principal, event_key=data['event_key'], **arguments)
            if operation == 'semantic-arbitrate':
                return await _settled_call(self.semantic.arbitrate, principal, event_key=data['event_key'], **arguments)
            if operation == 'semantic-evidence':
                evidence = await _settled_call(self.semantic.current_evidence, principal, **arguments)
                # Private source bytes and runtime paths belong to neither cold
                # metadata nor this explicit, currently source-guarded projection.
                return {key: evidence[key] for key in ('receipt_id', 'candidate_id', 'experiment_id',
                    'operation_id', 'result_id', 'binding_hash', 'assessment', 'native_verdict', 'verdict', 'owner_assessment', 'business_proof')}
            if operation != 'preparation-next':
                method = self.preparation.freeze if operation == 'preparation-freeze' else self.preparation.complete
                return await _settled_call(method, principal, experiment_id, event_key=data['event_key'], **arguments)
            admitted, handed_off = None, False
            try:
                admitted = await _settled_call(self.preparation.admit_next, principal, experiment_id,
                    event_key=data['event_key'], **arguments)
                current = await asyncio.to_thread(self.trials.get, principal, admitted.trial_id)
                state = await asyncio.to_thread(self.records.get, principal, experiment_id)
                if current['status'] == 'reserved':
                    if self._closed or state['phase'] in (*TERMINAL_PHASES, 'stopping', 'blocked'):
                        await self.trial_service._abandon_unclaimed(principal, admitted)
                    else:
                        await self.tasks.start(principal, admitted.request, event_key=admitted.reserve_event_key)
                        handed_off = True
                from improvement_trial_views import read_trial
                return await _settled_call(read_trial, self.assets, principal, admitted.trial_id)
            except (Exception, asyncio.CancelledError):
                if admitted is not None and not handed_off:
                    await self.trial_service._abandon_unclaimed(principal, admitted)
                raise

        kind = 'preparation_next' if operation == 'preparation-next' else 'workflow:' + operation
        return await self._operation(principal, experiment_id, data['event_key'], kind, data, execute)

    async def cancel(self, principal, experiment_id, *, expected_generation, event_key):
        _generation(expected_generation)

        async def stop():
            acknowledgment = await _settled_call(self.records.begin_stop, principal, experiment_id,
                kind="cancelled", reason="owner_requested", expected_generation=expected_generation, event_key=event_key)
            current = await self._settle_stop(principal, experiment_id)
            return {"acknowledgment": acknowledgment, "current": current}

        return await self._operation(principal, experiment_id, event_key, "cancel",
            {"expected_generation": expected_generation}, stop)

    def _next_slot(self, principal, experiment_id, comparison_id, expected_generation, event_key):
        return self.schedule.next_slot(principal, experiment_id, comparison_id, expected_generation, event_key)

    def _admit_next(self, principal, experiment_id, comparison_id, expected_generation, event_key):
        brain = _brain(principal)
        with closing(self.store._conn()) as connection:
            view = has_view_binding(connection, brain, comparison_id)
        if view:
            return self.view_admission.admit_next(principal, experiment_id, comparison_id,
                expected_generation=expected_generation, event_key=event_key)
        position = self._next_slot(principal, experiment_id, comparison_id, expected_generation, event_key)
        with closing(self.store._conn()) as connection:
            replay = connection.execute('SELECT 1 FROM improvement_events WHERE brain_id=? AND event_key=?', (brain, event_key)).fetchone()
            if replay is None:
                self.schedule.require_idle(connection, brain, experiment_id)
        if replay is not None:
            return self.admission.admit(principal, experiment_id, comparison_id, position,
                expected_generation=expected_generation, event_key=event_key)
        handle = self.trials.workspace.acquire_brain_execution(brain)
        if handle is None:
            raise IM.ConflictError('experiment_execution_busy')
        try:
            position = self._next_slot(principal, experiment_id, comparison_id, expected_generation, event_key)
            with closing(self.store._conn()) as connection:
                self.schedule.require_idle(connection, brain, experiment_id)
            return self.admission.admit(principal, experiment_id, comparison_id, position,
                expected_generation=expected_generation, event_key=event_key)
        finally:
            handle.close()

    async def next(self, principal, experiment_id, comparison_id, *, expected_generation, event_key):
        _identifier(comparison_id)
        _generation(expected_generation)

        async def start():
            admitted, handed_off = None, False
            try:
                admitted = await _settled_call(self._admit_next, principal, experiment_id, comparison_id, expected_generation, event_key)
                current = await asyncio.to_thread(self.trials.get, principal, admitted.trial_id)
                state = await asyncio.to_thread(self.records.get, principal, experiment_id)
                if current["status"] == "reserved":
                    if self._closed or state["phase"] in (*TERMINAL_PHASES, "stopping", "blocked"):
                        await self.trial_service._abandon_unclaimed(principal, admitted)
                    else:
                        await self.tasks.start(principal, admitted.request, event_key=admitted.reserve_event_key)
                        handed_off = True
                from improvement_trial_views import read_trial
                return await _settled_call(read_trial, self.assets, principal, admitted.trial_id)
            except (Exception, asyncio.CancelledError):
                if admitted is not None and not handed_off:
                    await self.trial_service._abandon_unclaimed(principal, admitted)
                raise

        return await self._operation(principal, experiment_id, event_key, "next",
            {"comparison_id": comparison_id, "expected_generation": expected_generation}, start)

    def _view_scope(self, connection, principal, experiment_id, comparison_id):
        brain = _brain(principal)
        row = self.records._row(connection, brain, experiment_id)
        self.records._public(row)
        comparison = connection.execute('SELECT * FROM improvement_comparisons WHERE id=? AND brain_id=? AND experiment_id=?',
            (comparison_id, brain, experiment_id)).fetchone()
        if comparison is None:
            raise PermissionError('experiment_comparison_unavailable')
        arm = connection.execute('SELECT * FROM improvement_experiment_arms WHERE experiment_id=? AND brain_id=? AND ordinal=?',
            (experiment_id, brain, comparison['ordinal'])).fetchone()
        if arm is None or IM._hash(json.loads(arm['envelope_json'])) != comparison['arm_hash']:
            raise IM.ConflictError('experiment_arm_changed')
        return row, {'definition': json.loads(row['definition_json']), 'comparison': dict(comparison), 'arm': json.loads(arm['envelope_json'])}

    def _view_evidence(self, principal, experiment_id, comparison_id, expected_generation):
        from improvement_experiment_lineage import current_fences
        from improvement_experiment_qualification import require_tuning_families
        brain = _brain(principal)
        with closing(self.store._conn()) as connection:
            row, proof = self._view_scope(connection, principal, experiment_id, comparison_id)
            if row['generation'] != expected_generation:
                raise IM.ConflictError('experiment_state_stale')
            metadata = self.views._metadata(connection, brain, comparison_id)
            if metadata is None:
                raise PermissionError('comparison_views_unavailable')
        resolved = self.views.load_current(principal, comparison_id, 'baseline')
        with closing(self.store._conn()) as connection:
            if proof['comparison']['kind'] == 'final':
                self.view_admission.qualification.preview(connection, principal, comparison_id, expected_generation=expected_generation)
            current, final_proof = self._view_scope(connection, principal, experiment_id, comparison_id)
            if (current['generation'] != expected_generation or final_proof != proof
                    or self.views._metadata(connection, brain, comparison_id) != metadata):
                raise IM.ConflictError('comparison_view_authority_changed')
            require_tuning_families(connection, brain, proof['definition']['case_set_id'])
            current_fences(connection, brain, proof)
        return {'view_binding': metadata, 'evidence_scope': 'current_view_sources_and_semantics',
            'current_generation': expected_generation, 'checked_at': time.time(),
            'observational_unknowns': list(resolved.observational_unknowns)}

    async def control(self, principal, experiment_id, operation, value):
        from improvement_experiment_requests import validate
        data = validate(value, operation)
        if operation not in ("create", "bind", "freeze", "report", "select", 'view-freeze', 'view-evidence'):
            raise ValueError("invalid_experiment_control")
        if operation == "create" and data["experiment_id"] != experiment_id:
            raise ValueError("invalid_experiment_identity")
        event_key = data["event_key"]
        arguments = {key: item for key, item in data.items() if key != "event_key"}

        def write():
            if operation == "create":
                return self.plans.create(principal, arguments, event_key=event_key)
            if operation == "bind":
                return self.plans.bind_arm(principal, experiment_id, event_key=event_key, **arguments)
            if operation == "freeze":
                return self.plans.freeze(principal, experiment_id, event_key=event_key, **arguments)
            if operation == "select":
                return self.plans.select(principal, experiment_id, event_key=event_key, **arguments)
            if operation in ('view-freeze', 'view-evidence'):
                with closing(self.store._conn()) as connection:
                    self._view_scope(connection, principal, experiment_id, data['comparison_id'])
                if operation == 'view-freeze':
                    return self.views.freeze_comparison(principal, event_key=event_key, **arguments)
                return self._view_evidence(principal, experiment_id, **arguments)
            with closing(self.store._conn()) as connection:
                self.records._row(connection, _brain(principal), experiment_id)
                if connection.execute("SELECT 1 FROM improvement_comparisons WHERE id=? AND brain_id=? AND experiment_id=?",
                    (data["comparison_id"], _brain(principal), experiment_id)).fetchone() is None:
                    raise PermissionError("experiment_comparison_unavailable")
            from improvement_comparison_results import ComparisonResults
            return ComparisonResults(self.plans).create(principal, event_key=event_key, **arguments)

        async def execute():
            acknowledgment = await _settled_call(write)
            if operation == "select" and data["choice"] == "keep_base":
                return {"acknowledgment": acknowledgment, "current": await self._settle_stop(principal, experiment_id)}
            return acknowledgment

        kind = 'select_candidate' if operation == 'select' and data['choice'] == 'candidate' else operation
        return await self._operation(principal, experiment_id, event_key, kind, data, execute)

    def _resume(self, principal, experiment_id, expected_generation, event_key):
        """Explicit preflight for observable source/runtime blockers, never regrant."""
        from improvement_claude import ClaudeTrialAdapter
        from improvement_experiment_protocol import definition
        brain = _brain(principal)
        # The owner event pins owner intent, not a browser-supplied fingerprint.
        payload = {"experiment_id": experiment_id, "expected_generation": expected_generation}
        with closing(self.store._conn()) as connection:
            replay = self.assets._replay(connection, brain, event_key, "experiment_owner_resume", payload)
            if replay is not None:
                return replay
            row = self.records._row(connection, brain, experiment_id)
            self.records._public(row)
            if row["generation"] != expected_generation or row["phase"] != "blocked":
                raise IM.ConflictError("experiment_state_stale")
            blocker = json.loads(row["blocker_json"])
            if blocker["code"] not in ("source_unavailable", "runtime_unavailable"):
                raise PermissionError("experiment_blocker_resume_unavailable")
            frozen = definition(json.loads(row["definition_json"]))
            public = {key: frozen[key] for key in ("experiment_id", "contract_id", "case_set_id", "base_bundle_id", "timeout_seconds")}
            public.update(expected_context_generation=frozen["context_generation"], repeat_policy=frozen["repeat_policy"]["kind"])
            prepared = self.plans._prepare(connection, principal, public)
            for arm in connection.execute("SELECT ordinal FROM improvement_experiment_arms WHERE brain_id=? AND experiment_id=?",
                                          (brain, experiment_id)):
                self.plans._frozen_arm(connection, principal, row, prepared, arm["ordinal"])
            original = dict(row)
        self.plans.host._snapshot_observe(principal, prepared[1])
        def native_current(connection, joined):
            for _ in range(2):
                current = self.records._row(connection, brain, experiment_id)
                self.records._public(current)
                if dict(current) != original or self.plans._prepare(connection, principal, public) != prepared:
                    raise IM.ConflictError("experiment_resume_authority_changed")
                for arm in connection.execute("SELECT ordinal FROM improvement_experiment_arms WHERE brain_id=? AND experiment_id=?",
                                              (brain, experiment_id)):
                    self.plans._frozen_arm(connection, principal, current, prepared, arm["ordinal"])
                self.plans.host._snapshot_observe(principal, prepared[1])
            return "allow"

        adapter = ClaudeTrialAdapter(prepared[1]["engine_config"])
        adapter.bind_native_authority(self.assets, principal, scope_hash=IM._hash({
            "version": 1, "kind": "experiment_owner_resume", "brain_id": brain,
            "event_key_hash": IM._hash(event_key), "request_hash": IM._hash(payload),
            "authority_hash": IM._hash(original)}), current=native_current)
        available = adapter.verify()
        if type(available) is not dict or available.get("supported") is not True:
            raise PermissionError("experiment_runtime_unavailable")
        from improvement_cases import _digest
        _digest(available.get("capability_hash"))
        fingerprint = IM._hash({"code": blocker["code"], "status": "available", "capability_hash": available["capability_hash"],
            "binding_hash": frozen["binding_hash"], "engine_config_hash": frozen["engine_config_hash"]})
        self.plans.host._snapshot_observe(principal, prepared[1])
        internal_key = "experiment-resume-" + IM._hash([brain, event_key])
        # Resume owns no worker/capacity transfer. Actual dispatch repeats the
        # full source/arm/native guard after this metadata transition.
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "experiment_owner_resume", payload)
            if replay is not None:
                return replay
            result = self.records._resume_in(connection, principal, experiment_id, observed_fingerprint=fingerprint,
                expected_generation=expected_generation, event_key=internal_key)
            self.assets._event(connection, principal, event_key, "experiment_owner_resume", payload, result)
        return result

    async def resume(self, principal, experiment_id, *, expected_generation, event_key):
        _generation(expected_generation)
        return await self._operation(principal, experiment_id, event_key, "resume",
            {"expected_generation": expected_generation},
            lambda: _settled_call(self._resume, principal, experiment_id, expected_generation, event_key))

    def _recover_ack(self, principal, experiment_id, event_key):
        brain = _brain(principal)
        payload = {"experiment_id": experiment_id}
        with self.store._Tx(self.store) as connection:
            saved = self.assets._replay(connection, brain, event_key, "experiment_recover", payload)
            if saved is not None:
                return saved
            result = self.records._public(self.records._row(connection, brain, experiment_id))
            self.assets._event(connection, principal, event_key, "experiment_recover", payload, result)
            return result

    async def recover(self, principal, experiment_id, *, event_key):
        async def recover():
            acknowledgment = await _settled_call(self._recover_ack, principal, experiment_id, event_key)
            await _settled_call(self._recover_linked, principal, experiment_id)
            current = await self._settle_stop(principal, experiment_id)
            return {"acknowledgment": acknowledgment, "current": current}

        return await self._operation(principal, experiment_id, event_key, "recover", {}, recover)

    def _recover_linked(self, principal, experiment_id):
        """Settle and clean only actual links; broad owner recovery stays separate."""
        brain = _brain(principal)
        with self.store._Tx(self.store) as connection:
            self.records._public(self.records._row(connection, brain, experiment_id))
            snapshot = self._snapshot(connection, brain, experiment_id)
            identifiers = [row['trial_id'] for row in snapshot[0]]
            result = self.trials._recover_in(connection, principal, trial_ids=identifiers)
        for identifier in identifiers:
            self.trials.cleanup_terminal(principal, identifier)
        from improvement_operation_recovery import OperationRecovery
        recovery = OperationRecovery(self.execution)
        for row in snapshot[2]:
            recovery.recover(principal, row['id'])
        return result

    async def close(self):
        self._bind()
        self._closed = True
        if self._closing is None:
            pending = tuple(entry[2] for entry in self._operations.values())

            async def close_operations():
                # Native cancellation must precede whole-workflow joins.
                # Role close owns slow admission/result/publication threads too.
                values = await asyncio.gather(self.proposals.close(), self.semantic.close(), self.composer.close(), return_exceptions=True)
                if pending:
                    await _drain(asyncio.gather(*pending, return_exceptions=True))
                for value in values:
                    if isinstance(value, BaseException):
                        raise value

            self._closing = asyncio.create_task(close_operations())
            self._closing.add_done_callback(self._consume)
        return await self._join(self._closing)
