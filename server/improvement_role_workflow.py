"""Shared owned role workflow and actual native product gates; no role dispatch API."""
from __future__ import annotations
import asyncio
from contextlib import closing
import improvement_store as IM
from improvement_operation_execution import OperationExecution
from improvement_operation_results import OperationResults
from improvement_operation_tasks import OperationTasks
from improvement_trial_records import _brain
from improvement_result_domain import NATIVE_GATES, require_product_report
from improvement_qualification_records import require_product_store

_REQUIRED = {'materialization', 'worker_protocol', 'installation', 'tool_inventory', 'side_effects',
             'completion', 'actual_model', 'native_session'}
_UNOBSERVED = {'actual_reasoning', 'actual_input_use'}


def _product_checks(report):
    """Exact report inventory; the concrete result reader authenticates history."""
    require_product_report(report)
    if type(report.get('version')) is not int or report['version'] not in (1, 2):
        raise PermissionError('proposal_native_evidence_unavailable')
    required = _REQUIRED | (NATIVE_GATES if report['version'] == 2 else set())
    rows = report.get('checks')
    if type(rows) is not list or any(type(row) is not dict or type(row.get('id')) is not str for row in rows):
        raise PermissionError('proposal_native_evidence_unavailable')
    checks = {item['id']: item.get('verdict') for item in rows}
    if (len(checks) != len(rows) or set(checks) != required | _UNOBSERVED
            or any(checks[key] != 'pass' for key in required)
            or any(checks[key] not in ('pass', 'unknown') for key in _UNOBSERVED)):
        raise PermissionError('proposal_native_evidence_unavailable')


class RoleWorkflow:
    _product_kinds = frozenset()

    def __init__(self, execution, tasks):
        if (type(execution) is not OperationExecution or type(tasks) is not OperationTasks
                or tasks.execution is not execution):
            raise TypeError('concrete_role_workflow_dependencies_required')
        self.execution, self.tasks, self.plans = execution, tasks, execution.plans
        self.assets, self.store, self.blobs = execution.assets, execution.store, execution.blobs
        self.products = OperationResults(execution)
        self._operations, self._closed, self._closing, self._loop = {}, False, None, None

    def _bind(self):
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise RuntimeError('role_workflow_loop_changed')

    def _open(self):
        if self._closed:
            raise RuntimeError('role_workflow_closed')

    def _product(self, connection, principal, identifier):
        require_product_store(self.assets, principal, connection=connection)
        row = self.execution._row(connection, principal, identifier)
        if row['kind'] not in self._product_kinds or row['status'] != 'completed':
            raise IM.ConflictError('proposal_operation_incomplete')
        if connection.execute("SELECT 1 FROM improvement_events WHERE brain_id=? AND operation='operation_owner_cancel' "
            "AND json_extract(result_json,'$.operation_id')=?", (row['brain_id'], identifier)).fetchone():
            raise IM.ConflictError('proposal_operation_cancelled')
        attempt = self.execution._attempt(connection, row)
        call = self.execution.bound_call(connection, row, attempt)
        context = self.plans.host._row(connection, row['brain_id'], row['experiment_id'])
        pin = self.plans.host._decode(context)['engine_config']
        if (attempt['status'] != 'completed' or attempt['engine_at'] is None or call['engine_at'] != attempt['engine_at']
                or call['status'] != 'ok' or call['engine'] != pin['provider'] or call['model'] != pin['model']):
            raise IM.ConflictError('proposal_call_incomplete')
        records = [dict(item) for item in connection.execute('SELECT * FROM improvement_operation_results '
            'WHERE operation_id=? AND brain_id=? AND attempt=?', (identifier, row['brain_id'], row['attempt']))]
        if len(records) != 1:
            raise IM.ConflictError('proposal_result_unavailable')
        report = self.products.read(principal, identifier, row['attempt'])
        if (IM._hash(report) != records[0]['result_hash'] or attempt['result_json'] != IM._json(report)
                or report['materialization_hash'] != attempt['materialization_hash'] or report['engine_config_hash'] != IM._hash(pin)):
            raise IM.ConflictError('proposal_result_changed')
        _product_checks(report)
        trace = [dict(item) for item in connection.execute('SELECT * FROM improvement_operation_observations '
            'WHERE operation_id=? AND brain_id=? AND attempt=? ORDER BY sequence', (identifier, row['brain_id'], row['attempt']))]
        if any(item['late'] for item in trace) or [item['payload_hash'] for item in trace] != report['trace_hashes']:
            raise IM.ConflictError('proposal_native_trace_changed')
        raw = self.products.artifact(principal, identifier, row['attempt']).decode('utf-8')
        require_product_store(self.assets, principal, connection=connection)
        return {'row': dict(row), 'attempt': dict(attempt), 'call': call, 'record': records[0], 'report': report, 'trace': trace, 'raw': raw}

    def _product_fence(self, connection, principal, product):
        require_product_store(self.assets, principal, connection=connection)
        row = self.execution._row(connection, principal, product['row']['id'])
        attempt = self.execution._attempt(connection, row)
        if (dict(row) != product['row'] or dict(attempt) != product['attempt']
                or self.execution.bound_call(connection, row, attempt) != product['call']):
            raise IM.ConflictError('proposal_operation_changed')
        if connection.execute("SELECT 1 FROM improvement_events WHERE brain_id=? AND operation='operation_owner_cancel' "
                "AND json_extract(result_json,'$.operation_id')=?", (row['brain_id'], row['id'])).fetchone():
            raise IM.ConflictError('proposal_operation_cancelled')
        trace = [dict(item) for item in connection.execute('SELECT * FROM improvement_operation_observations '
            'WHERE operation_id=? AND brain_id=? AND attempt=? ORDER BY sequence', (row['id'], row['brain_id'], row['attempt']))]
        if trace != product['trace']:
            raise IM.ConflictError('proposal_native_trace_changed')
        require_product_store(self.assets, principal, connection=connection)

    def _read_product(self, principal, identifier):
        with closing(self.store._conn()) as connection:
            return self._product(connection, principal, identifier)

    async def _run_owned(self, principal, scope_id, event_key, payload, factory):
        require_product_store(self.assets, principal)
        self._bind()
        self._open()
        key, digest = (_brain(principal), event_key), IM._hash(payload)
        previous = self._operations.get(key)
        if previous is not None:
            if previous[0] != digest:
                raise IM.ConflictError('role_workflow_event_conflict')
            result = await self.tasks._join(previous[1])
            require_product_store(self.assets, principal)
            return result
        task = asyncio.create_task(factory())
        self._operations[key] = digest, task, scope_id, principal

        def finished(done):
            if self._operations.get(key, (None, None))[1] is done:
                self._operations.pop(key)
            self.tasks._consume(done)

        task.add_done_callback(finished)
        result = await self.tasks._join(task)
        require_product_store(self.assets, principal)
        return result

    async def close(self):
        self._bind()
        if self._closing is None:
            self._closed = True
            self._closing = asyncio.create_task(self._close())
        return await self.tasks._join(self._closing)

    async def _close(self):
        failure = None
        try:
            await self.tasks.close()
        except BaseException as error:
            failure = error
        await asyncio.gather(*(entry[1] for entry in list(self._operations.values())), return_exceptions=True)
        if failure is not None:
            raise failure
        return True
