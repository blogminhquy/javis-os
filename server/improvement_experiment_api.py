"""Owner-session transport; cold GET never constructs execution dependencies."""
from __future__ import annotations

import inspect
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse, Response

import improvement_store as IM
import localefmt
from evidence_store import redact
from improvement_experiments import ExperimentRecords, _identifier
from improvement_experiment_requests import validate, WORKFLOW_CONTROLS
from improvement_trial_requests import read_json, TrialRequestError
from improvement_trial_runner import _settled_call
from resonance_store import Principal


@dataclass
class ExperimentApiDeps:
    read_store: object
    resolve_brain: object
    owner_session: object
    service: object
    write_store: object = None
    # Called with (principal, report_id) after a report is published, e.g. to open granted canaries
    # for a qualified final. Failures are logged and never undo the published report.
    after_report: object = None

    def __post_init__(self):
        if self.write_store is not None and (not callable(self.write_store)
                or inspect.iscoroutinefunction(self.write_store)
                or inspect.iscoroutinefunction(getattr(self.write_store, '__call__', None))):
            raise TypeError('synchronous_experiment_writer_required')
        for name in ("read_store", "resolve_brain", "owner_session", "service"):
            callback = getattr(self, name)
            if not callable(callback):
                raise TypeError("experiment_api_dependencies_required")
            if name != "owner_session" and (inspect.iscoroutinefunction(callback)
                    or inspect.iscoroutinefunction(getattr(callback, "__call__", None))):
                raise TypeError("synchronous_experiment_factory_required")


def _error(error):
    if isinstance(error, TrialRequestError):
        status, reason = error.status_code, ("experiment_request_too_large" if error.status_code == 413 else "invalid_experiment_request")
    elif isinstance(error, IM.ConflictError):
        status, reason = 409, "experiment_conflict"
    elif isinstance(error, PermissionError):
        status, reason = 403, "experiment_scope_unavailable"
    elif isinstance(error, ValueError) and str(error).startswith(("invalid_", "unknown_brain")):
        status, reason = 422, "invalid_experiment_request"
    else:
        status, reason = 503, "experiment_unavailable"
    return JSONResponse({"ok": False, "reason": reason, "error": localefmt.chu(
        "Không thể thực hiện yêu cầu cải tiến trong phạm vi hiện tại.",
        "The improvement request is unavailable in the current scope.")}, status_code=status)


def register(app, deps):
    if type(deps) is not ExperimentApiDeps:
        raise TypeError("experiment_api_dependencies_required")

    # Retain only services actually dispatched by this adapter, never construct
    # one to inspect an orphaned saved start. Workflow ownership stays in service.
    active_compose_owners = {}

    async def assets():
        value = await _settled_call(deps.read_store)
        if value is None:
            raise PermissionError("experiment_unavailable")
        if type(value) is not IM.ImprovementStore:
            raise TypeError("concrete_experiment_store_required")
        return value

    async def dispatch(request, brain, action, *, key, identifiers=(), operation=None):
        try:
            denied = deps.owner_session(request)
            if inspect.isawaitable(denied):
                denied = await denied
            if denied is not None:
                if not isinstance(denied, Response):
                    raise TypeError("experiment_owner_session_response_required")
                return denied
            root = await _settled_call(deps.resolve_brain, brain)
            if type(root) is not str or not root:
                raise TypeError("concrete_experiment_brain_required")
            principal = Principal("owner", "owner", root)
            for identifier in identifiers:
                _identifier(identifier)
            data = validate(await read_json(request), operation) if operation else None
            value = await action(principal, data)
            if redact(value) != value:
                raise ValueError("experiment_view_unavailable")
            return JSONResponse({"ok": True, key: value})
        except Exception as error:
            return await _settled_call(_error, error)

    @app.get("/improvement-experiments")
    async def experiment_list(request: Request, brain: str = "brain", cursor: str | None = None, limit: str = "50"):
        async def action(principal, data):
            if not limit.isascii() or not limit.isdecimal() or len(limit) > 3:
                raise TrialRequestError()
            return await _settled_call(ExperimentRecords(await assets()).list, principal, cursor=cursor, limit=int(limit))
        return await dispatch(request, brain, action, key="experiments")

    @app.get("/improvement-experiments/{experiment_id}")
    async def experiment_get(request: Request, experiment_id: str, brain: str = "brain"):
        async def action(principal, data):
            return await _settled_call(ExperimentRecords(await assets()).get, principal, experiment_id)
        return await dispatch(request, brain, action, key="experiment", identifiers=(experiment_id,))

    @app.get("/improvement-comparison-reports/{report_id}")
    async def comparison_report_get(request: Request, report_id: str, brain: str = "brain"):
        async def action(principal, data):
            from improvement_comparison_results import ComparisonResults
            return await _settled_call(ComparisonResults.from_existing(await assets()).read, principal, report_id)
        return await dispatch(request, brain, action, key="report", identifiers=(report_id,))

    @app.get('/improvement-experiments/{experiment_id}/preparation')
    async def preparation_history(request: Request, experiment_id: str, brain: str = 'brain'):
        async def action(principal, data):
            from improvement_preparation_records import PreparationRecords
            return await _settled_call(PreparationRecords(await assets()).list, principal, experiment_id)
        return await dispatch(request, brain, action, key='preparations', identifiers=(experiment_id,))

    @app.get('/improvement-experiments/{experiment_id}/operations')
    async def operation_history(request: Request, experiment_id: str, brain: str = 'brain'):
        async def action(principal, data):
            from improvement_operation_records import OperationRecords
            return await _settled_call(OperationRecords(await assets()).list, principal, experiment_id)
        return await dispatch(request, brain, action, key='operations', identifiers=(experiment_id,))

    @app.get('/improvement-operations/{operation_id}')
    async def operation_metadata(request: Request, operation_id: str, brain: str = 'brain'):
        async def action(principal, data):
            from improvement_operation_records import OperationRecords
            return await _settled_call(OperationRecords(await assets()).get, principal, operation_id)
        return await dispatch(request, brain, action, key='operation', identifiers=(operation_id,))

    @app.get('/improvement-candidates/{candidate_id}/semantic-history')
    async def semantic_history(request: Request, candidate_id: str, brain: str = 'brain'):
        async def action(principal, data):
            from improvement_semantic_records import SemanticReceipts
            return await _settled_call(SemanticReceipts(await assets()).history, principal, candidate_id)
        return await dispatch(request, brain, action, key='receipts', identifiers=(candidate_id,))

    @app.get('/improvement-experiments/{experiment_id}/views/{comparison_id}')
    async def view_history(request: Request, experiment_id: str, comparison_id: str, brain: str = 'brain'):
        async def action(principal, data):
            from contextlib import closing
            from improvement_view_history import metadata
            store = await assets()
            if IM._schema_version(store.store) < 7:
                return None
            def read():
                with closing(store.store._conn()) as connection:
                    if connection.execute('SELECT 1 FROM improvement_comparisons WHERE id=? AND brain_id=? AND experiment_id=?',
                            (comparison_id, principal.brain_id, experiment_id)).fetchone() is None:
                        raise PermissionError('experiment_comparison_unavailable')
                    return metadata(connection, principal.brain_id, comparison_id)
            return await _settled_call(read)
        return await dispatch(request, brain, action, key='view_binding', identifiers=(experiment_id, comparison_id))

    def register_compose_history(suffix, key, method):
        async def endpoint(request: Request, experiment_id: str, brain: str = 'brain'):
            async def action(principal, data):
                from improvement_compose_permissions import ComposePermissions
                metadata = ComposePermissions.from_existing(await assets())
                return await _settled_call(getattr(metadata, method), principal, experiment_id)
            return await dispatch(request, brain, action, key=key, identifiers=(experiment_id,))
        endpoint.__name__ = 'experiment_' + suffix.replace('-', '_')
        app.add_api_route('/improvement-experiments/{experiment_id}/' + suffix, endpoint, methods=['GET'])

    register_compose_history('compose-consents', 'consents', 'list')
    register_compose_history('compositions', 'compositions', 'compositions')
    register_compose_history('compose-outcomes', 'outcomes', 'outcomes')
    register_compose_history('policy', 'policy', 'policy')

    async def control(request, brain, operation, experiment_id=None):
        async def action(principal, data):
            if operation == 'compose-revoke':
                from improvement_compose_permissions import ComposePermissions
                existing = await assets()
                metadata = ComposePermissions.from_existing(existing)
                await _settled_call(metadata.scope, principal, experiment_id, data['authorization_id'])
                if deps.write_store is not None:
                    writable = await _settled_call(deps.write_store)
                    if (type(writable) is not IM.ImprovementStore
                            or writable.store.path.resolve() != existing.store.path.resolve()
                            or writable.blobs.root.resolve() != existing.blobs.root.resolve()):
                        raise PermissionError('experiment_compose_store_unavailable')
                    metadata = ComposePermissions.from_existing(writable)
                    await _settled_call(metadata.scope, principal, experiment_id, data['authorization_id'])
                return await _settled_call(metadata.revoke, principal, **data)
            service, compose_key = None, None
            if operation in ('compose', 'compose-authorize', 'compose-preview'):
                from improvement_compose_permissions import ComposePermissions
                metadata = ComposePermissions.from_existing(await assets())
                historical, result = await _settled_call(metadata.replay_control, principal, experiment_id, operation, data)
                compose_key = principal.brain_id, experiment_id, data['event_key']
                service = active_compose_owners.get(compose_key)
                if historical and service is None:
                    return result
            from improvement_experiment_service import ExperimentService
            if service is None:
                service = await _settled_call(deps.service)
            if type(service) is not ExperimentService:
                raise TypeError("concrete_experiment_service_required")
            identifier = data["experiment_id"] if operation == "create" else experiment_id
            if operation in WORKFLOW_CONTROLS:
                if compose_key is None:
                    return await service.workflow(principal, identifier, operation, data)
                active = active_compose_owners.get(compose_key)
                if active is not None:
                    return await active.workflow(principal, identifier, operation, data)
                active_compose_owners[compose_key] = service
                try:
                    return await service.workflow(principal, identifier, operation, data)
                finally:
                    active_compose_owners.pop(compose_key, None)
            if operation in ("cancel", "recover", "resume"):
                return await getattr(service, operation)(principal, identifier, **data)
            if operation == "next":
                return await service.next(principal, identifier, **data)
            result = await service.control(principal, identifier, operation, data)
            if operation == "report" and deps.after_report is not None and isinstance(result, dict) and result.get("report_id"):
                try:
                    await _settled_call(deps.after_report, principal, result["report_id"])
                except Exception as error:  # noqa: BLE001 - the report itself is already durable
                    import sys
                    print(f"[improvement canary] after report: {type(error).__name__}: {error}", file=sys.stderr)
            return result
        return await dispatch(request, brain, action, key="result", operation=operation,
                              identifiers=() if experiment_id is None else (experiment_id,))

    @app.post("/improvement-experiments")
    async def experiment_create(request: Request, brain: str = "brain"):
        return await control(request, brain, "create")

    # Each action is a registered closed route, never arbitrary attribute access
    # from an HTTP operation string. Defaults are closure-only, not query inputs.
    def register_control(operation):
        async def endpoint(request: Request, experiment_id: str, brain: str = "brain"):
            return await control(request, brain, operation, experiment_id)
        endpoint.__name__ = "experiment_" + operation
        app.add_api_route("/improvement-experiments/{experiment_id}/" + operation, endpoint, methods=["POST"])

    for operation in ("bind", "freeze", "next", "report", "select", "cancel", "resume", "recover",
            'view-freeze', 'view-evidence', *sorted(WORKFLOW_CONTROLS)):
        register_control(operation)
