"""One owned trial attempt, with durable start/evidence boundaries and no query retries."""
from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections.abc import Mapping
from contextlib import aclosing, closing

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


def _runner_body(packet):
    """Project for interpretation only; evidence always receives the envelope."""
    if type(packet) is dict and type(packet.get('version')) is int and packet['version'] == 2:
        return packet['body']
    return packet


class _NativeRunnerEvidence:
    """One original writer's pending evidence, never an execution capability."""
    def __init__(self, *, append, get, principal, identifier, attempt, token, lock, authority, observe,
                 transient_check=None):
        self.append, self.get, self.principal, self.identifier = append, get, principal, identifier
        self.attempt, self.token, self.lock = attempt, token, lock
        self.authority, self.observe, self.transient_check = authority, observe, transient_check
        self.pending, self.observed = {}, set()
        self.failed, self.terminal, self.transient = False, None, False

    def _retain(self, packet):
        snapshot = IC._frozen(packet)
        if (type(snapshot) is not dict or type(snapshot.get('version')) is not int or snapshot['version'] != 2
                or type(snapshot.get('body')) is not dict or type(snapshot.get('sequence')) is not int):
            raise _RunFailure('evidence_failed')
        key = IM._hash(snapshot)
        entry = self.pending.setdefault(key, {'packet': snapshot, 'stored': False})
        return key, entry

    async def _observe_owned(self, key, packet):
        if key in self.observed:
            return
        values, cancelled = await _drain(asyncio.gather(
            # Recorder implementations may consume/mutate their input. They
            # cannot change the original failed envelope awaiting late storage.
            asyncio.create_task(self.observe(IC._frozen(packet))), return_exceptions=True))
        if not isinstance(values[0], BaseException):
            # Retain only a digest after successful consumption, never a parsed
            # successful task/result or its raw plaintext across the stream.
            self.observed.add(key)
            body = _runner_body(packet)
            if body.get('type') == 'engine_event':
                event = body['event']
                if event.get('type') == 'terminal': self.terminal = IC._frozen(event)
                if self.transient_check is not None and self.transient_check(event): self.transient = True
        if cancelled is not None: raise cancelled
        if isinstance(values[0], BaseException): raise values[0]

    async def _accept_locked(self, key, entry, *, active=True):
        packet, error = entry['packet'], None
        try:
            if not active: raise _RunFailure('evidence_failed')
            latest = await _settled_call(self.get, self.principal, self.identifier)
            if latest['attempt'] != self.attempt or latest['status'] not in ('prepared', 'running'):
                raise _RunFailure('evidence_failed')
            await _settled_call(self.append, self.principal, self.identifier, packet,
                expected_generation=latest['generation'], lease_token=self.token, attempt=self.attempt)
            entry['stored'] = True
        except BaseException as failure:
            self.failed, error = True, failure
        try:
            await self._observe_owned(key, packet)
        except BaseException as failure:
            self.failed = True
            if error is None or isinstance(failure, asyncio.CancelledError): error = failure
        if entry['stored'] and key in self.observed: self.pending.pop(key, None)
        if error is not None:
            if isinstance(error, asyncio.CancelledError): raise error
            if isinstance(error, _RunFailure): raise error
            raise _RunFailure('evidence_failed') from error

    async def accept(self, packet):
        key, entry = self._retain(packet)
        async with self.lock:
            await self._accept_locked(key, entry)

    async def _closing_owned(self, packets):
        error, active = None, True
        async with self.lock:
            try:
                await self.authority()
            except BaseException as failure:
                self.failed, error, active = True, failure, False
            for packet in packets:
                try:
                    key, entry = self._retain(packet)
                    await self._accept_locked(key, entry, active=active)
                except BaseException as failure:
                    self.failed = True
                    if error is None or isinstance(failure, asyncio.CancelledError): error = failure
        if error is not None: raise error

    async def closing(self, packets):
        # The adapter can be closing because its caller is being cancelled.
        # Own the whole batch, not merely its first SQLite or telemetry thread.
        values, cancelled = await _drain(asyncio.gather(
            asyncio.create_task(self._closing_owned(tuple(packets))), return_exceptions=True))
        if cancelled is not None:
            self.failed = True
            raise cancelled
        if isinstance(values[0], BaseException): raise values[0]

    async def flush_late_locked(self):
        """Called after abort with the generation lock already held."""
        for key, entry in sorted(tuple(self.pending.items()), key=lambda item: item[1]['packet']['sequence']):
            try:
                if not entry['stored']:
                    await _settled_call(self.append, self.principal, self.identifier, entry['packet'],
                        lease_token=self.token, attempt=self.attempt, late=True)
                    entry['stored'] = True
            except Exception:
                self.failed = True  # Missing anchor/foreign writer never mints an allow.
            try:
                await self._observe_owned(key, entry['packet'])
            except Exception:
                self.failed = True
            if entry['stored'] and key in self.observed: self.pending.pop(key, None)


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
        self._qualification = None

    @classmethod
    def for_qualification(cls, session, admission):
        from improvement_qualification_session import QualificationSession
        if cls is not TrialRunner or type(session) is not QualificationSession:
            raise TypeError('concrete_qualification_session_required')
        session._assert_trial_owner(admission, session.principal)
        session._require_preflight()
        self = cls(admission.trials, context_loader=admission.host.context_loader, live_guard=admission.host.live_guard)
        self._qualification = session
        return self

    async def run_qualification(self, principal, trial_id):
        if self._qualification is None or principal is not self._qualification.principal:
            raise PermissionError('qualification_runner_required')
        self._qualification._require_preflight()
        task = asyncio.current_task()
        own = task not in self._qualification._host_operations
        if own: self._qualification._host_operations[task] = (trial_id, 0)
        try:
            result = await self._run(principal, trial_id)
            self._qualification._assert_native_current()
            return result
        finally:
            if own: self._qualification._host_operations.pop(task, None)

    async def _cleanup_qualification_attempt(self, key):
        session = self._qualification
        resource = session._attempt_resources.get(key)
        if resource is None: return
        if resource['runner'] is not self or resource['owner'] is not self.trials:
            raise PermissionError('qualification_resource_owner_foreign')
        task = asyncio.current_task()
        if resource['finalizer'] is not task:
            previous = resource['finalizer']
            # Session registration lasts through preparation/process drainage;
            # a caller may reuse the same host task after an operation ends.
            if ((previous is not None and not previous.done()) or any(
                    operation is not task and not operation.done() and scope in (key, (key[0], 0))
                    for operation, scope in session._host_operations.items())):
                raise PermissionError('qualification_attempt_active')
            # A relinquished resource gets one actual cleanup task. Reserve it
            # synchronously; rivals cannot start a second finalizer at an await.
            finalizer = asyncio.create_task(self._cleanup_qualification_attempt(key))
            resource['finalizer'] = finalizer
            values, cancelled = await _drain(asyncio.gather(finalizer, return_exceptions=True))
            if isinstance(values[0], BaseException): raise values[0]
            if cancelled is not None: raise cancelled
            return
        context = session._queries.get(key)
        boundary = None if context is None else context['boundary']
        # Preserve the original workspace and kernel-held lifetime whenever
        # native close or evidence settlement is still unresolved.
        if boundary is not None and boundary._owner_state != 'DETACHED':
            raise RuntimeError('qualification_native_owners_unsettled')
        handles = resource['lifetime'][0]
        if handles is None:
            await _settled_call(self.trials.cleanup_terminal, session.principal, key[0])
            session._attempt_resources.pop(key, None)
            return
        try:
            await _settled_call(self.trials.workspace.cleanup, *key)
        except Exception:
            raise WorkspaceCleanupError() from None
        finally:
            await _settled_call(self.trials.workspace.release_execution, handles)
        if boundary is not None:
            from improvement_qualification_results import _CleanupReceipt
            context['cleanup'] = await _settled_call(_CleanupReceipt._from_runner, self, context, handles)
        elif not await _settled_call(self.trials.workspace.cleanup_proven, *key,
                None if context is None else context['receipt']):
            raise RuntimeError('qualification_workspace_unsettled')
        if any(not handle.closed for handle in handles):
            raise RuntimeError('qualification_lifetime_unsettled')
        session._attempt_resources.pop(key, None)

    async def _response(self, principal, identifier):
        current = await asyncio.to_thread(self.trials.get, principal, identifier)
        if self._qualification is not None:
            from improvement_qualification_results import QualificationQueryResults
            resource = self._qualification._attempt_resources.get((identifier, current['attempt']))
            if resource is not None:
                await resource['runner']._cleanup_qualification_attempt((identifier, current['attempt']))
            context = self._qualification._pending_proofs.get((identifier, current['attempt']))
            if context is not None:
                context['publisher'] = asyncio.current_task()
                return await _settled_call(QualificationQueryResults(self._qualification).publish, self.trials,
                    principal, identifier, attempt=current['attempt'], evidence_hash=context['stage'].digest,
                    cleanup_receipt=context['cleanup'])
            return await _settled_call(QualificationQueryResults.read_stored, self.trials.assets, principal,
                kind='trial', subject_id=identifier, attempt=current['attempt'], expected_run_hash=self._qualification.run_hash)
        result = None
        if current["status"] in TERMINAL:
            try:
                result = await asyncio.to_thread(self.trials.read_result, principal, identifier, current["attempt"])
            except PermissionError:
                pass  # Interrupted/not-run attempts need not have an evaluation result.
        return {**current, "result": result}

    async def run(self, principal, trial_id, *, on_claimed=None):
        if self._qualification is not None: raise PermissionError('qualification_product_forbidden')
        return await self._run(principal, trial_id, on_claimed=on_claimed)

    async def _run(self, principal, trial_id, *, on_claimed=None):
        IM._brain(principal)
        if on_claimed is not None and not _synchronous(on_claimed):
            raise ValueError("synchronous_trial_claim_observer_required")
        initial = await asyncio.to_thread(self.trials.get, principal, trial_id)
        if initial["status"] != "reserved":
            if initial["status"] in TERMINAL and self._qualification is None:
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
        resource_key = (trial_id, claimed['attempt'])
        if self._qualification is not None:
            self._qualification._host_operations[asyncio.current_task()] = resource_key
            if resource_key in self._qualification._attempt_resources:
                raise PermissionError('qualification_lifetime_already_owned')
            self._qualification._attempt_resources[resource_key] = dict(owner=self.trials, runner=self, lifetime=lifetime,
                host_task=asyncio.current_task(), finalizer=None)
        result = None
        try:
            result = await self._run_claimed(principal, trial_id, claimed, on_claimed, lifetime)
        finally:
            async def cleanup():
                if self._qualification is not None:
                    await self._cleanup_qualification_attempt(resource_key)
                    return
                if lifetime[0] is None:
                    await _settled_call(self.trials.cleanup_terminal, principal, trial_id)
                    return
                try:
                    await _settled_call(self.trials.workspace.cleanup, trial_id, claimed["attempt"])
                except Exception:
                    raise WorkspaceCleanupError() from None
                finally:
                    await _settled_call(self.trials.workspace.release_execution, lifetime[0])
            resource = None
            if self._qualification is not None:
                resource = self._qualification._attempt_resources[resource_key]
                if resource['host_task'] is not asyncio.current_task():
                    raise RuntimeError('qualification_resource_owner_foreign')
            finalizer = asyncio.create_task(cleanup())
            if resource is not None:
                resource['finalizer'] = finalizer
            values, cancelled = await _drain(asyncio.gather(finalizer, return_exceptions=True))
            if isinstance(values[0], BaseException):
                raise values[0]
            if cancelled is not None:
                raise cancelled
        if self._qualification is not None:
            from improvement_qualification_results import QualificationQueryResults, _CleanupReceipt
            context = self._qualification._queries.get((trial_id, claimed['attempt']))
            if context is None or context['stage'] is None:
                raise PermissionError('qualification_execution_incomplete')
            cleanup = context['cleanup']
            context['publisher'] = asyncio.current_task()
            return await _settled_call(QualificationQueryResults(self._qualification).publish,
                self.trials, principal, trial_id, attempt=claimed['attempt'], evidence_hash=result,
                cleanup_receipt=cleanup)
        return result

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
        native_evidence, workspace_receipt = None, None

        def live_guard():
            if self._qualification is not None: self._qualification._require_preflight()
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
                    if self._qualification is not None:
                        self._qualification._query_context(query_binding)['recorder'] = recorder
                except Exception as error:
                    raise _RunFailure("telemetry_failed") from error
                # The adapter releases its worker ACK only after this callback returns.

        async def observe(packet):
            body = _runner_body(packet)
            if body.get("type") == "engine_event":
                if recorder is None:
                    raise _RunFailure("worker_failed")
                try:
                    await _settled_call(recorder.observe, body["event"], sequence=packet["sequence"])
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
        query_binding = None

        def native_current(connection, joined):
            row, attempt = self.trials._leased(connection, principal, trial_id, current['generation'], token, time.time())
            if row['attempt'] != claimed['attempt'] or row['request_hash'] != IM._hash(request):
                raise IM.ConflictError('trial_native_owner_changed')
            self.trials._current(connection, current['brain_id'], request, trial_id=trial_id, principal=principal)
            _guard(live_guard, request)
            if workspace_receipt is not None:
                if not attempt['workspace_json'] or json.loads(attempt['workspace_json']) != workspace_receipt:
                    raise IM.ConflictError('trial_native_workspace_changed')
                self.trials.workspace.validate(workspace_receipt)
            self.trials._current(connection, current['brain_id'], request, trial_id=trial_id, principal=principal)
            _guard(live_guard, request)
            self.trials._leased(connection, principal, trial_id, current['generation'], token, time.time())
            return 'allow'

        async def closing_authority():
            def check():
                with closing(self.trials.store._conn()) as connection:
                    native_current(connection, None)
            await _settled_call(check)

        async def process():
            nonlocal current, manifest, phase, evaluation, native_evidence, workspace_receipt, query_binding
            def acquire():
                lifetime[0] = self.trials.workspace.acquire_execution(current["brain_id"], trial_id, current["attempt"])
                if lifetime[0] is None:
                    raise _RunFailure("capacity_unavailable")
            await _settled_call(acquire)
            await authority()
            phase = "unsupported_configuration"
            adapter = None
            if self._qualification is not None:
                self._qualification._require_preflight()
                if request['engine_config'] != self._qualification._pin: raise _RunFailure('unsupported_configuration')
                verified = None
            else:
                adapter = self.adapter_factory(request["engine_config"], workspace_root=self.trials.workspace.root,
                                               before_engine_start=before_start)
            if self._qualification is not None:
                pass
            elif type(adapter) is ClaudeTrialAdapter:
                scope = IM._hash({'version': 1, 'kind': 'trial', 'brain_id': current['brain_id'],
                    'subject_id': trial_id, 'attempt': claimed['attempt'], 'request_hash': IM._hash(request),
                    'engine_config_hash': request['pins']['engine_config_hash']})
                adapter.bind_native_authority(self.trials.assets, principal, scope_hash=scope, current=native_current, lock=lock)
                verified = await adapter.verify_async()
            else:
                verified = await _settled_call(adapter.verify)
            if self._qualification is None and (not isinstance(verified, dict) or verified.get("supported") is not True
                    or verified.get("account_ready") is False or verified.get("domain") == "qualification"):
                raise _RunFailure("unsupported_configuration")
            if self._qualification is None: IC._digest(verified.get("capability_hash"))
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
                workspace_receipt = IC._frozen(workspace)
                if self._qualification is not None:
                    query_binding = await _settled_call(self._qualification._query_binding, self.trials, principal, trial_id,
                        expected_generation=current['generation'], lease_token=token)
                    from improvement_native_parent import NativeParentBoundary
                    adapter = NativeParentBoundary.for_qualification_query(self._qualification, query_binding)
            native_request = {"version": 1, "trial_id": trial_id, "attempt": current["attempt"],
                "deadline_at": request["deadline_at"], "engine_config_hash": request["pins"]["engine_config_hash"],
                "capability_hash": query_binding.authority_hash if query_binding is not None else verified["capability_hash"]}
            phase = "worker_failed"
            terminal = None
            if manifest['version'] in (4, 5):
                native_evidence = _NativeRunnerEvidence(append=self.trials.append_observation, get=self.trials.get,
                    principal=principal, identifier=trial_id, attempt=claimed['attempt'], token=token,
                    lock=lock, authority=closing_authority, observe=observe)
            options = {} if native_evidence is None else {'on_closing_observations': native_evidence.closing}
            stream = (adapter.execute(native_request, workspace, **options) if self._qualification is None else
                adapter.execute_qualification(query_binding, owner=self.trials, principal=principal, identifier=trial_id,
                    expected_generation=current['generation'], lease_token=token, before_engine_start=before_start,
                    on_closing_observations=native_evidence.closing))
            async with aclosing(stream) as packets:
                async for packet in packets:
                    if native_evidence is not None:
                        await native_evidence.accept(packet)
                        continue
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
            if native_evidence is not None:
                if native_evidence.failed: raise _RunFailure('evidence_failed')
                terminal = native_evidence.terminal
            if recorder is None or terminal is None:
                raise _RunFailure("worker_failed")
            phase = "telemetry_failed"
            await _settled_call(recorder.finish, "failed" if terminal["is_error"] else "completed")
            if self._qualification is not None:
                from improvement_qualification_results import QualificationQueryResults
                async with lock:
                    await authority()
                    context = self._qualification._query_context(query_binding)
                    evaluation = asyncio.create_task(asyncio.to_thread(QualificationQueryResults(self._qualification).stage,
                        self.trials, principal, trial_id, expected_generation=current['generation'], lease_token=token,
                        binding=query_binding, native_completion=context['completion']))
                    await asyncio.shield(evaluation)
                    current = await _settled_call(self.trials.get, principal, trial_id)
                return
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
                        if native_evidence is not None:
                            await native_evidence.flush_late_locked()
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
        if self._qualification is not None:
            if error is not None: raise _RunFailure(reason) from error
            return evaluation.result()
        return await self._response(principal, trial_id)
