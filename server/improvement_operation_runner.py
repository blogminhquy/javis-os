"""One actual role attempt, owned through worker, result and plaintext cleanup."""
from __future__ import annotations

import asyncio
import json
import time
from contextlib import aclosing

import improvement_store as IM
from improvement_experiment_protocol import _digest
from improvement_operation_adapter import ClaudeOperationAdapter
from improvement_operation_evidence import OperationEvidence
from improvement_operation_execution import OperationExecution
from improvement_operation_results import OperationResults
from improvement_operation_retry import native_transient
from improvement_operation_schema import TERMINAL
from improvement_operation_workspace import OperationWorkspaceCleanupError
from improvement_telemetry import NativeUsageRecorder
from improvement_trial_runner import _RunFailure, _drain, _settled_call, _synchronous, _runner_body, _NativeRunnerEvidence

HEARTBEAT_SECONDS = 20
LEASE_SECONDS = 60


class OperationRunner:
    def __init__(self, execution, *, adapter_factory=ClaudeOperationAdapter, recorder_factory=NativeUsageRecorder):
        if type(execution) is not OperationExecution or not all(_synchronous(value) for value in (adapter_factory, recorder_factory)):
            raise TypeError("concrete_operation_runner_dependencies_required")
        self.execution = execution
        self.adapter_factory, self.recorder_factory = adapter_factory, recorder_factory
        self.evidence, self.results = OperationEvidence(execution), OperationResults(execution)

    async def _response(self, principal, identifier):
        row = await asyncio.to_thread(self.execution.get, principal, identifier)
        result = None
        if row["status"] in TERMINAL and row["attempt"]:
            try:
                result = await asyncio.to_thread(self.results.read, principal, identifier, row["attempt"])
            except PermissionError:
                pass
        return {**row, "result": result}

    async def run(self, principal, identifier, *, on_claimed=None):
        if on_claimed is not None and not _synchronous(on_claimed):
            raise ValueError("synchronous_operation_claim_observer_required")
        initial = await asyncio.to_thread(self.execution.get, principal, identifier)
        if initial["status"] != "reserved":
            return await self._response(principal, identifier)
        claim = asyncio.create_task(asyncio.to_thread(self.execution.claim, principal, identifier,
            expected_generation=initial["generation"], lease_seconds=LEASE_SECONDS))
        values, cancelled = await _drain(asyncio.gather(claim, return_exceptions=True))
        claimed = values[0]
        if cancelled is not None:
            if isinstance(claimed, dict):
                await _settled_call(self.execution.abort, principal, identifier, expected_generation=claimed["generation"],
                                    lease_token=claimed["lease_token"], reason="cancelled")
            else:
                await _settled_call(self.execution.reject_unclaimed, principal, identifier,
                                    expected_generation=initial["generation"], reason="cancelled")
            raise cancelled
        if isinstance(claimed, BaseException):
            if not isinstance(claimed, (PermissionError, IM.ConflictError)):
                raise claimed
            try:
                await _settled_call(self.execution.reject_unclaimed, principal, identifier,
                                    expected_generation=initial["generation"], reason="authority_changed")
            except IM.ConflictError:
                pass  # A foreign lease does not become this runner's cleanup authority.
            return await self._response(principal, identifier)
        lifetime, receipt = [None], [None]
        try:
            return await self._run_claimed(principal, identifier, claimed, on_claimed, lifetime, receipt)
        finally:
            async def cleanup():
                if lifetime[0] is None:
                    return
                try:
                    await _settled_call(self.execution.workspace.cleanup_owned, identifier, claimed["attempt"], receipt[0], lifetime[0])
                except Exception:
                    raise OperationWorkspaceCleanupError() from None
                finally:
                    await _settled_call(self.execution.workspace.release_execution, lifetime[0])
            values, cancelled = await _drain(asyncio.gather(asyncio.create_task(cleanup()), return_exceptions=True))
            if isinstance(values[0], BaseException):
                raise values[0]
            if cancelled is not None:
                raise cancelled

    async def _run_claimed(self, principal, identifier, claimed, on_claimed, lifetime, receipt):
        execution = self.execution
        current, token, recorder, evaluation = claimed, claimed["lease_token"], None, None
        phase = "runner_failed"
        native_evidence = None
        lock = asyncio.Lock()
        if on_claimed is not None:
            try:
                on_claimed(claimed)
            except BaseException:
                await _settled_call(execution.abort, principal, identifier, expected_generation=current["generation"],
                                    lease_token=token, reason="runner_failed")
                raise

        async def authority():
            try:
                return await asyncio.to_thread(execution.guard, principal, identifier)
            except Exception as error:
                raise _RunFailure("authority_changed") from error

        async def before_start():
            nonlocal current, recorder
            async with lock:
                await authority()
                if recorder is not None:
                    raise _RunFailure("worker_failed")
                current = await _settled_call(execution.start_engine, principal, identifier,
                    expected_generation=current["generation"], lease_token=token)
                metadata = {"experiment_id": current["experiment_id"], "operation_id": identifier,
                    "attempt": current["attempt"], "execution_id": "improvement_operation:" + identifier,
                    "role": current["role"], "purpose": current["purpose"], "learning_origin": "compose"}
                try:
                    recorder = await _settled_call(self.recorder_factory, execution.ledger, current["attempts"][-1]["call_id"], metadata,
                        brain_id=current["brain_id"], provider=pin["provider"], model=pin["model"])
                    if not all(_synchronous(getattr(recorder, name, None)) for name in ("observe", "finish")):
                        raise ValueError("operation_usage_recorder_unavailable")
                except Exception as error:
                    raise _RunFailure("telemetry_failed") from error

        async def observe(packet):
            body = _runner_body(packet)
            if body["type"] == "engine_event":
                if recorder is None:
                    raise _RunFailure("worker_failed")
                await _settled_call(recorder.observe, body["event"], sequence=packet["sequence"])

        async def heartbeat():
            while True:
                await asyncio.sleep(HEARTBEAT_SECONDS)
                async with lock:
                    latest = await asyncio.to_thread(execution.get, principal, identifier)
                    if latest["status"] in TERMINAL:
                        return latest
                    await authority()
                    await _settled_call(execution.heartbeat, principal, identifier,
                        expected_generation=current["generation"], lease_token=token, lease_seconds=LEASE_SECONDS)

        pin = None

        def native_current(connection, joined):
            row, attempt = execution._leased(connection, principal, identifier, current['generation'], token, time.time())
            if row['attempt'] != claimed['attempt'] or row['request_hash'] != IM._hash(claimed['request']):
                raise IM.ConflictError('operation_native_owner_changed')
            prepared = execution._current(connection, principal, row)
            execution.host._snapshot_observe(principal, prepared[1])
            if receipt[0] is not None:
                if not attempt['workspace_json'] or json.loads(attempt['workspace_json']) != receipt[0]:
                    raise IM.ConflictError('operation_native_workspace_changed')
                execution.workspace.validate(receipt[0])
            if execution._current(connection, principal, row) != prepared:
                raise IM.ConflictError('operation_native_authority_changed')
            execution.host._snapshot_observe(principal, prepared[1])
            execution._leased(connection, principal, identifier, current['generation'], token, time.time())
            return 'allow'

        async def process():
            nonlocal current, phase, evaluation, pin, native_evidence
            def acquire():
                lifetime[0] = execution.workspace.acquire_execution(current["brain_id"], identifier, current["attempt"])
                if lifetime[0] is None:
                    raise _RunFailure("capacity_unavailable")
            await _settled_call(acquire)
            prepared = await authority()
            pin = prepared[1]["engine_config"]
            phase = "unsupported_configuration"
            adapter = self.adapter_factory(pin, workspace=execution.workspace, before_engine_start=before_start)
            if type(adapter) is ClaudeOperationAdapter:
                scope = IM._hash({'version': 1, 'kind': 'operation', 'brain_id': current['brain_id'],
                    'subject_id': identifier, 'attempt': claimed['attempt'], 'request_hash': IM._hash(claimed['request']),
                    'engine_config_hash': IM._hash(pin)})
                adapter.bind_native_authority(execution.assets, principal, scope_hash=scope, current=native_current, lock=lock)
                verified = await adapter.verify_async()
            else:
                verified = await _settled_call(adapter.verify)
            if (type(verified) is not dict or verified.get("supported") is not True
                    or verified.get("account_ready") is False or verified.get("domain") == "qualification"):
                raise _RunFailure("unsupported_configuration")
            _digest(verified.get("capability_hash"))
            phase = "runner_failed"
            manifest = await _settled_call(execution.materialize, principal, identifier,
                expected_generation=current["generation"], lease_token=token)
            receipt[0] = await _settled_call(execution.workspace.prepare, identifier, current["attempt"], manifest)
            async with lock:
                current = await _settled_call(execution.prepared, principal, identifier,
                    expected_generation=current["generation"], lease_token=token, receipt=receipt[0])
            native_request = {"version": 1, **{key: current[key] for key in ("operation_id", "attempt", "role", "purpose")},
                "deadline_at": current["deadline_at"], "engine_config_hash": manifest["engine_config_hash"], "capability_hash": verified["capability_hash"]}
            phase, terminal, transient = "worker_failed", None, False
            if manifest['version'] == 2:
                native_evidence = _NativeRunnerEvidence(append=self.evidence.append, get=execution.get,
                    principal=principal, identifier=identifier, attempt=claimed['attempt'], token=token,
                    lock=lock, authority=authority, observe=observe, transient_check=native_transient)
            options = {} if native_evidence is None else {'on_closing_observations': native_evidence.closing}
            async with aclosing(adapter.execute(native_request, receipt[0], **options)) as packets:
                async for packet in packets:
                    if native_evidence is not None:
                        await native_evidence.accept(packet)
                        continue
                    async with lock:
                        try:
                            await _settled_call(self.evidence.append, principal, identifier, packet,
                                expected_generation=current["generation"], lease_token=token)
                        except BaseException:
                            await observe(packet)
                            raise
                        await observe(packet)
                        if packet["type"] == "engine_event" and native_transient(packet["event"]):
                            transient = True
                        if packet["type"] == "engine_event" and packet["event"].get("type") == "terminal":
                            terminal = packet["event"]
            if native_evidence is not None:
                if native_evidence.failed: raise _RunFailure('evidence_failed')
                terminal, transient = native_evidence.terminal, native_evidence.transient
            if transient:
                raise _RunFailure("native_transient_error")
            if recorder is None or terminal is None:
                raise _RunFailure("worker_failed")
            phase = "telemetry_failed"
            await _settled_call(recorder.finish, "completed" if terminal.get("is_error") is False else "failed")
            phase = "evidence_failed"
            await authority()
            evaluation = asyncio.create_task(asyncio.to_thread(self.results.finish, principal, identifier,
                expected_generation=current["generation"], lease_token=token, capability_hash=verified["capability_hash"]))
            current = await asyncio.shield(evaluation)

        worker, pulse = asyncio.create_task(process()), asyncio.create_task(heartbeat())
        error = None
        try:
            async with asyncio.timeout(max(0.0, current["deadline_at"] - time.time())):
                done, _ = await asyncio.wait((worker, pulse), return_when=asyncio.FIRST_COMPLETED)
                if pulse in done and not worker.done():
                    await pulse
                    raise _RunFailure("cancelled")
                await worker
        except BaseException as failure:
            error = failure
        finally:
            worker.cancel()
            pulse.cancel()
            _, cancelled = await _drain(asyncio.gather(worker, pulse, return_exceptions=True))
            if cancelled is not None:
                error = cancelled
        if error is not None:
            reason = ("cancelled" if isinstance(error, asyncio.CancelledError) else "timeout" if isinstance(error, TimeoutError)
                      else error.reason if isinstance(error, _RunFailure) else phase)

            async def close_attempt():
                try:
                    async with lock:
                        latest = await asyncio.to_thread(execution.get, principal, identifier)
                        try:
                            await _settled_call(execution.abort, principal, identifier, expected_generation=latest["generation"],
                                                lease_token=token, reason=reason)
                        except IM.ConflictError:
                            pass
                        if native_evidence is not None:
                            await native_evidence.flush_late_locked()
                        if recorder is not None:
                            try:
                                await _settled_call(recorder.finish, "unknown")
                            except Exception:
                                pass  # Marked SQL call keeps failed/missing usage observable.
                finally:
                    if evaluation is not None:
                        await asyncio.gather(evaluation, return_exceptions=True)
            _, cancelled = await _drain(asyncio.create_task(close_attempt()))
            if cancelled is not None:
                error = cancelled
            if isinstance(error, asyncio.CancelledError):
                raise error
        return await self._response(principal, identifier)
