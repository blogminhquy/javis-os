"""One host-observed infrastructure retry with the original input and deadline."""
from __future__ import annotations

import json
import time
from contextlib import closing

import improvement_store as IM
from improvement_experiments import _generation
from improvement_experiment_protocol import _digest
from improvement_operation_adapter import ClaudeOperationAdapter
from improvement_operation_execution import OperationExecution
from improvement_operation_protocol import operation_packet
from improvement_trial_evidence import decode_trace
from improvement_trial_records import _brain
from improvement_observation_history import is_observation2, validate_history

_STATUS = {429, 500, 502, 503, 504}
_NETWORK = {"ConnectionError", "ConnectionResetError", "APITimeoutError", "ConnectError", "ReadTimeout", "ConnectTimeout"}


def native_transient(event):
    if type(event) is not dict:
        return False
    if event.get("type") == "error":
        code = event.get("status_code")
        name = event.get("error_type")
        return (type(code) is int and code in _STATUS) or (type(name) is str and name in _NETWORK)
    if event.get("type") == "terminal" and event.get("is_error") is True:
        code = event.get("api_error_status")
        return type(code) is int and code in _STATUS
    return False


class OperationRetry:
    def __init__(self, execution):
        if type(execution) is not OperationExecution:
            raise TypeError("concrete_operation_retry_required")
        self.execution = execution

    def _eligible(self, connection, principal, identifier, generation):
        row = self.execution._row(connection, principal, identifier)
        attempt = self.execution._attempt(connection, row)
        if row["generation"] != generation or row["attempt"] != 1 or row["status"] not in ("not_run", "interrupted"):
            raise IM.ConflictError("operation_retry_unavailable")
        call = self.execution.bound_call(connection, row, attempt)
        trace = [dict(item) for item in connection.execute("SELECT * FROM improvement_operation_observations WHERE operation_id=? "
            "AND brain_id=? AND attempt=1 ORDER BY sequence", (identifier, row["brain_id"]))]
        reason = attempt["failure_reason"]
        if reason == "capacity_unavailable":
            valid = (row["status"] == "not_run" and call["engine_at"] is None and call["status"] == "refunded"
                     and attempt["engine_at"] is None and not any(item["kind"] == "engine_event" for item in trace))
        elif reason == "native_transient_error":
            valid = (row["status"] == "interrupted" and call["engine_at"] is not None and call["status"] == "interrupted"
                     and attempt["engine_at"] == call["engine_at"])
        else:
            valid = False
        if not valid or self.execution._public(connection, row)["deadline_at"] <= time.time():
            raise IM.ConflictError("operation_retry_unavailable")
        return dict(row), dict(attempt), trace

    def _native_proof(self, row, attempt, trace):
        if attempt["failure_reason"] == "capacity_unavailable":
            return []
        receipt = json.loads(attempt["workspace_json"]) if attempt["workspace_json"] else None
        decode = lambda item: decode_trace(self.execution.blobs, row["brain_id"], item)
        native_checked = False
        proof = []
        for item in trace:
            if item["late"] or item["kind"] != "engine_event":
                continue
            decoded = decode(item)
            if is_observation2(decoded):
                if not native_checked:
                    validate_history(trace, decode, kind='operation', receipt=receipt)
                    native_checked = True
                packet = decoded['body']
            else:
                packet, _ = operation_packet(decoded)
            if (receipt is None or any(packet[key] != receipt[key] for key in
                    ("operation_id", "attempt", "role", "purpose", "input_hash"))):
                raise IM.ConflictError("operation_retry_proof_changed")
            if native_transient(packet["event"]):
                proof.append(item["payload_hash"])
        if not proof:
            raise IM.ConflictError("operation_retry_unavailable")
        return proof

    def reserve(self, principal, identifier, *, expected_generation, event_key):
        e, brain = self.execution, _brain(principal)
        _generation(expected_generation)
        e.records.get(principal, identifier)
        payload = {"operation_id": identifier, "expected_generation": expected_generation}
        with closing(e.store._conn()) as connection:
            replay = e.assets._replay(connection, brain, event_key, "operation_infra_retry", payload)
            if replay is not None:
                return replay
            snapshot = self._eligible(connection, principal, identifier, expected_generation)
        handles = e.workspace.acquire_execution(brain, identifier, 1)
        if handles is None:
            raise IM.ConflictError("operation_retry_busy")
        try:
            row, attempt, trace = snapshot
            proof = self._native_proof(row, attempt, trace)
            prepared = e.guard(principal, identifier)
            receipt = json.loads(attempt["workspace_json"]) if attempt["workspace_json"] else None
            e.workspace.cleanup_owned(identifier, 1, receipt, handles)
            def native_current(connection, joined):
                for _ in range(2):
                    eligible = self._eligible(connection, principal, identifier, expected_generation)
                    if eligible != snapshot or self._native_proof(*eligible) != proof:
                        raise IM.ConflictError("operation_retry_proof_changed")
                    current = e._row(connection, principal, identifier)
                    if e._current(connection, principal, current) != prepared:
                        raise IM.ConflictError("operation_authority_changed")
                    e.host._snapshot_observe(principal, prepared[1])
                # Encrypted proof and source reads above can cross the original
                # deadline. Finish with the cheap SQL/time fence before allow.
                if self._eligible(connection, principal, identifier, expected_generation) != snapshot:
                    raise IM.ConflictError("operation_retry_proof_changed")
                return "allow"

            adapter = ClaudeOperationAdapter(prepared[1]["engine_config"])
            adapter.bind_native_authority(e.assets, principal, scope_hash=IM._hash({
                "version": 1, "kind": "operation_infra_retry", "brain_id": brain,
                "event_key_hash": IM._hash(event_key), "request_hash": IM._hash(payload),
                "authority_hash": IM._hash(snapshot)}), current=native_current)
            available = adapter.verify()
            if type(available) is not dict or available.get("supported") is not True:
                raise ValueError("operation_native_unavailable")
            _digest(available.get("capability_hash"))
            e.host._snapshot_observe(principal, prepared[1])
            with e.store._Tx(e.store) as connection:
                replay = e.assets._replay(connection, brain, event_key, "operation_infra_retry", payload)
                if replay is not None:
                    return replay
                if self._eligible(connection, principal, identifier, expected_generation) != snapshot:
                    raise IM.ConflictError("operation_retry_proof_changed")
                current = e._row(connection, principal, identifier)
                if e._current(connection, principal, current) != prepared:
                    raise IM.ConflictError("operation_authority_changed")
                stamp = time.time()
                execution_id = "improvement_operation:" + identifier
                call = e.ledger.reserve(purpose=current["purpose"], reason_ref=execution_id + ":attempt:2",
                    brain_id=brain, context_ref="improvement:" + current["experiment_id"], mirror_ref=execution_id,
                    obligation=True, attempt=2, now=stamp, c=connection)
                if call is None:
                    raise IM.ConflictError("operation_call_capacity_unavailable")
                connection.execute("INSERT INTO improvement_operation_attempts "
                    "(operation_id,brain_id,attempt,status,call_id,created_at,updated_at) VALUES(?,?,2,'reserved',?,?,?)",
                    (identifier, brain, call, stamp, stamp))
                connection.execute("UPDATE improvement_operations SET status='reserved',attempt=2,generation=generation+1,updated_at=? "
                                   "WHERE id=? AND brain_id=?", (stamp, identifier, brain))
                e.host._snapshot_observe(principal, prepared[1])
                current = e._row(connection, principal, identifier)
                e._current(connection, principal, current)
                if e._public(connection, current)["deadline_at"] <= time.time():
                    raise IM.ConflictError("operation_retry_deadline_expired")
                result = e._public(connection, current)
                e.assets._event(connection, principal, "operation-retry-proof:" + identifier,
                    "operation_retry_basis", {"operation_id": identifier, "previous_call_id": attempt["call_id"],
                        "next_call_id": call, "reason": attempt["failure_reason"], "evidence_hashes": proof,
                        "deadline_at": result["deadline_at"]}, {"operation_id": identifier, "attempt": 2})
                e.assets._event(connection, principal, event_key, "operation_infra_retry", payload, result)
                return result
        finally:
            e.workspace.release_execution(handles)
