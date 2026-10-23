"""One owned trial attempt, with durable start/evidence boundaries and no query retries."""
from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Mapping
from contextlib import aclosing

import improvement_cases as IC
import improvement_store as IM
from improvement_claude import ClaudeTrialAdapter
from improvement_telemetry import NativeUsageRecorder
from improvement_trial_results import _guard
from improvement_trials import TERMINAL
from improvement_sandbox import WorkspaceCleanupError

HEARTBEAT_SECONDS = 20
LEASE_SECONDS = 60


class _RunFailure(Exception):
    def __init__(self, reason):
        self.reason = reason


def _synchronous(callback):
    return (callable(callback) and not inspect.iscoroutinefunction(callback)
            and not inspect.iscoroutinefunction(getattr(callback, "__call__", None)))


async def _drain(future):
    """Retain ownership through any number of caller cancellation requests."""
    cancelled = None
    while True:
        try:
            return await asyncio.shield(future), cancelled
        except asyncio.CancelledError as error:
            if future.cancelled():
                raise
            cancelled = error


async def _settled_call(callback, *args, **kwargs):
    """Cancellation cannot abandon an owned SQLite/telemetry transition thread."""
    task = asyncio.create_task(asyncio.to_thread(callback, *args, **kwargs))
    values, cancelled = await _drain(asyncio.gather(task, return_exceptions=True))
    if cancelled is not None:
        raise cancelled
    if isinstance(values[0], BaseException):
        raise values[0]
    return values[0]


class TrialRunner:
    def __init__(self, trials, *, context_loader, live_guard, adapter_factory=ClaudeTrialAdapter,
                 recorder_factory=NativeUsageRecorder, checker_registry=None):
        if not all(_synchronous(value) for value in (context_loader, live_guard, adapter_factory, recorder_factory)):
            raise ValueError("trial_host_dependencies_required")
        if checker_registry is not None and not isinstance(checker_registry, Mapping):
            raise ValueError("invalid_checker_registry")
        self.trials = trials
        self.context_loader, self.live_guard = context_loader, live_guard
        self.adapter_factory, self.recorder_factory = adapter_factory, recorder_factory
        self.checker_registry = dict(checker_registry or {})

    async def _response(self, principal, identifier):
        current = await asyncio.to_thread(self.trials.get, principal, identifier)
        result = None
        if current["status"] in TERMINAL:
            try:
                result = await asyncio.to_thread(self.trials.read_result, principal, identifier, current["attempt"])
            except PermissionError:
                pass  # Interrupted/not-run attempts need not have an evaluation result.
        return {**current, "result": result}

    async def run(self, principal, trial_id, *, on_claimed=None):
        IM._brain(principal)
        if on_claimed is not None and not _synchronous(on_claimed):
            raise ValueError("synchronous_trial_claim_observer_required")
        initial = await asyncio.to_thread(self.trials.get, principal, trial_id)
        if initial["status"] != "reserved":
            if initial["status"] in TERMINAL:
                await _settled_call(self.trials.cleanup_terminal, principal, trial_id)
            return await self._response(principal, trial_id)

        async def reject_unclaimed(reason):
            try:
                await _settled_call(self.trials.reject_unclaimed, principal, trial_id,
                    expected_generation=initial["generation"], reason=reason)
            except IM.ConflictError:
                pass  # A concurrent claimant owns its lease; never close it here.

        try:
            claim = asyncio.create_task(asyncio.to_thread(self.trials.claim, principal, trial_id,
                expected_generation=initial["generation"], lease_seconds=LEASE_SECONDS))
            values, cancelled = await _drain(asyncio.gather(claim, return_exceptions=True))
            if cancelled is not None:
                # No query exists yet, but a committed claim still needs its refund.
                if isinstance(values[0], dict):
                    claimed = values[0]
                    await _settled_call(self.trials.abort, principal, trial_id,
                        expected_generation=claimed["generation"], lease_token=claimed["lease_token"], reason="cancelled")
                else:
                    await reject_unclaimed("cancelled")
                raise cancelled
            if isinstance(values[0], BaseException):
                raise values[0]
            claimed = values[0]
        except (PermissionError, IM.ConflictError):
            await reject_unclaimed("timeout" if initial["request"]["deadline_at"] <= time.time() else "authority_changed")
            return await self._response(principal, trial_id)
        lifetime = [None]
        try:
            return await self._run_claimed(principal, trial_id, claimed, on_claimed, lifetime)
        finally:
            async def cleanup():
                if lifetime[0] is None:
                    await _settled_call(self.trials.cleanup_terminal, principal, trial_id)
                    return
                try:
                    await _settled_call(self.trials.workspace.cleanup, trial_id, claimed["attempt"])
                except Exception:
                    raise WorkspaceCleanupError() from None
                finally:
                    await _settled_call(self.trials.workspace.release_execution, lifetime[0])
            values, cancelled = await _drain(asyncio.gather(asyncio.create_task(cleanup()), return_exceptions=True))
            if isinstance(values[0], BaseException):
                raise values[0]
            if cancelled is not None:
                raise cancelled

    async def _run_claimed(self, principal, trial_id, claimed, on_claimed, lifetime):
        if on_claimed is not None:
            try:
                on_claimed(IC._frozen(claimed))
            except BaseException:
                await _settled_call(self.trials.abort, principal, trial_id,
                    expected_generation=claimed["generation"], lease_token=claimed["lease_token"], reason="runner_failed")
                raise
        request = IC._frozen(claimed["request"])
        token = claimed["lease_token"]
        lock = asyncio.Lock()
        current, recorder = claimed, None
        phase = "runner_failed"
        evaluation = None

        def live_guard():
            return self.live_guard(principal, IC._frozen(request))

        async def authority():
            try:
                await asyncio.to_thread(_guard, live_guard, request)
            except Exception as error:
                raise _RunFailure("authority_changed") from error

        async def before_start():
            nonlocal current, recorder
            async with lock:
                await authority()
                if recorder is not None:
                    raise _RunFailure("worker_failed")
                current = await _settled_call(self.trials.start_engine, principal, trial_id,
                    expected_generation=current["generation"], lease_token=token)
                execution = {"experiment_id": request["pins"]["experiment_id"], "trial_id": trial_id,
                    "case_id": request["case_id"], "variant": request["variant"], "repeat": request["repeat"],
                    "attempt": current["attempt"], "execution_id": f"improvement_trial:{trial_id}",
                    "role": "solver", "purpose": "improve_probe", "learning_origin": manifest["learning_origin"]}
                try:
                    candidate = await _settled_call(self.recorder_factory, self.trials.ledger,
                        current["attempts"][-1]["call_id"], execution, brain_id=current["brain_id"],
                        provider=request["engine_config"]["provider"], model=request["engine_config"]["model"])
                    if any(not callable(getattr(candidate, name, None))
                           or inspect.iscoroutinefunction(getattr(candidate, name)) for name in ("observe", "finish")):
                        if inspect.iscoroutine(candidate):
                            candidate.close()
                        raise ValueError("trial_usage_recorder_unavailable")
                    recorder = candidate
                except Exception as error:
                    raise _RunFailure("telemetry_failed") from error
                # The adapter releases its worker ACK only after this callback returns.

        async def observe(packet):
            if packet.get("type") == "engine_event":
                if recorder is None:
                    raise _RunFailure("worker_failed")
                try:
                    await _settled_call(recorder.observe, packet["event"], sequence=packet["sequence"])
                except Exception as error:
                    raise _RunFailure("telemetry_failed") from error

        async def heartbeat():
            while True:
                await asyncio.sleep(HEARTBEAT_SECONDS)
                async with lock:
                    latest = await asyncio.to_thread(self.trials.get, principal, trial_id)
                    if latest["status"] in TERMINAL:
                        return latest
                    await authority()
                    try:
                        await _settled_call(self.trials.heartbeat, principal, trial_id,
                            expected_generation=current["generation"], lease_token=token, lease_seconds=LEASE_SECONDS)
                    except Exception as error:
                        raise _RunFailure("authority_changed") from error

        manifest = None

        async def process():
            nonlocal current, manifest, phase, evaluation
            def acquire():
                lifetime[0] = self.trials.workspace.acquire_execution(current["brain_id"], trial_id, current["attempt"])
                if lifetime[0] is None:
                    raise _RunFailure("capacity_unavailable")
            await _settled_call(acquire)
            await authority()
            phase = "unsupported_configuration"
            adapter = self.adapter_factory(request["engine_config"], workspace_root=self.trials.workspace.root,
                                           before_engine_start=before_start)
            verified = await asyncio.to_thread(adapter.verify)
            if not isinstance(verified, dict) or verified.get("supported") is not True:
                raise _RunFailure("unsupported_configuration")
            IC._digest(verified.get("capability_hash"))
            phase = "runner_failed"
            context = await asyncio.to_thread(self.context_loader, principal, IC._frozen(request))
            async with lock:
                await authority()
                manifest = await _settled_call(self.trials.materialize, principal, trial_id,
                    expected_generation=current["generation"], lease_token=token, baseline_context=context)
                await authority()
            # Filesystem preparation does not advance the SQL generation. Let
            # the validating heartbeat renew while its owned thread is running;
            # the execution lifetime and settled-call drain still prevent escape.
            workspace = await _settled_call(self.trials.workspace.prepare, trial_id, current["attempt"], manifest)
            async with lock:
                await authority()
                current = await _settled_call(self.trials.prepared, principal, trial_id,
                    expected_generation=current["generation"], lease_token=token, receipt=workspace)
            native_request = {"version": 1, "trial_id": trial_id, "attempt": current["attempt"],
                "deadline_at": request["deadline_at"], "engine_config_hash": request["pins"]["engine_config_hash"],
                "capability_hash": verified["capability_hash"]}
            phase = "worker_failed"
            terminal = None
            async with aclosing(adapter.execute(native_request, workspace)) as packets:
                async for packet in packets:
                    async with lock:
                        try:
                            await _settled_call(self.trials.append_observation, principal, trial_id, packet,
                                expected_generation=current["generation"], lease_token=token)
                        except asyncio.CancelledError:
                            # The append thread has settled; retain actual usage before closing.
                            await observe(packet)
                            raise
                        except Exception as error:
                            # An actual usage observation must survive loss of the raw evidence store.
                            await observe(packet)
                            raise _RunFailure("evidence_failed") from error
                        await observe(packet)
                        if packet.get("type") == "engine_event" and packet["event"].get("type") == "terminal":
                            terminal = packet["event"]
            # aclosing has finished process-group cleanup before any product/evaluator call.
            if recorder is None or terminal is None:
                raise _RunFailure("worker_failed")
            phase = "telemetry_failed"
            await _settled_call(recorder.finish, "failed" if terminal["is_error"] else "completed")
            phase = "evaluation_failed"
            async with lock:
                await authority()
                current = await _settled_call(self.trials.stage_evaluation, principal, trial_id,
                    expected_generation=current["generation"], lease_token=token)
            await authority()
            evaluation = asyncio.create_task(asyncio.to_thread(self.trials.finish, principal, trial_id,
                expected_generation=current["generation"], lease_token=token,
                capability_hash=verified["capability_hash"], live_guard=live_guard,
                checker_registry=self.checker_registry))
            finished = await asyncio.shield(evaluation)
            async with lock:
                current = finished

        worker = asyncio.create_task(process())
        pulse = asyncio.create_task(heartbeat())
        error = None
        try:
            async with asyncio.timeout(max(0.0, request["deadline_at"] - time.time())):
                done, _ = await asyncio.wait((worker, pulse), return_when=asyncio.FIRST_COMPLETED)
                if pulse in done:
                    observed = await pulse
                    if observed["status"] not in {"completed", "failed"}:
                        raise _RunFailure("cancelled")
                await worker
        except BaseException as failure:
            error = failure
        finally:
            if not worker.cancelling():
                worker.cancel()
            if not pulse.cancelling():
                pulse.cancel()
            _, cancelled = await _drain(asyncio.gather(worker, pulse, return_exceptions=True))
            if cancelled is not None:
                error = cancelled
        if error is not None:
            reason = ("cancelled" if isinstance(error, asyncio.CancelledError) else
                      "timeout" if isinstance(error, TimeoutError) else
                      error.reason if isinstance(error, _RunFailure) else phase)
            async def close_attempt():
                try:
                    async with lock:
                        latest = await asyncio.to_thread(self.trials.get, principal, trial_id)
                        try:
                            await _settled_call(self.trials.abort, principal, trial_id,
                                expected_generation=latest["generation"], lease_token=token, reason=reason)
                        except IM.ConflictError:
                            pass  # Never close a lease now owned by another host attempt.
                        latest = await asyncio.to_thread(self.trials.get, principal, trial_id)
                        if recorder is not None:
                            status = latest["status"] if latest["status"] in {"completed", "failed", "cancelled"} else "unknown"
                            try:
                                await _settled_call(recorder.finish, status)
                            except Exception:
                                pass  # The durable marked call keeps missing usage observable.
                finally:
                    # Own the checker through *all* closing failures, including
                    # lock acquisition, row reads, abort and telemetry settlement.
                    # Workspace and brain locks cannot be released before it ends.
                    if evaluation is not None:
                        await asyncio.gather(evaluation, return_exceptions=True)

            _, cancelled = await _drain(asyncio.create_task(close_attempt()))
            if cancelled is not None:
                error = cancelled
            if isinstance(error, asyncio.CancelledError):
                raise error
        return await self._response(principal, trial_id)
