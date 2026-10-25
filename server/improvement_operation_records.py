"""Cold real role history and transaction-owned metadata; no native dispatch."""
from __future__ import annotations

import json
import secrets
import time
from contextlib import closing

import improvement_cases as IC
import improvement_store as IM
from improvement_experiments import ExperimentRecords, _identifier, _generation
from improvement_experiment_protocol import definition
from improvement_operation_protocol import operation_request
from improvement_trial_records import _brain


class OperationRecords:
    def __init__(self, assets):
        if type(assets) is not IM.ImprovementStore:
            raise TypeError("concrete_operation_store_required")
        self.assets, self.store, self.blobs = assets, assets.store, assets.blobs
        self.experiments = ExperimentRecords(assets)

    @staticmethod
    def _public(row):
        request = operation_request(json.loads(row["request_json"]))
        if (IM._hash(request) != row["request_hash"] or request["input_hash"] != row["input_blob_hash"]
                or any(request[key] != row[key] for key in
                       ("experiment_id", "context_id", "kind", "role", "purpose", "candidate_id", "parent_id", "input_hash"))):
            raise IM.ConflictError("operation_request_changed")
        return {"operation_id": row["id"], **{key: row[key] for key in (
            "experiment_id", "context_id", "kind", "role", "purpose", "candidate_id", "parent_id", "request_hash",
            "input_hash", "status", "generation", "attempt", "created_at")}}

    def get(self, principal, identifier):
        brain = _brain(principal)
        _identifier(identifier)
        if IM._schema_version(self.store) < 6:
            raise PermissionError("operation_unavailable")
        with closing(self.store._conn()) as connection:
            row = connection.execute("SELECT * FROM improvement_operations WHERE id=? AND brain_id=?", (identifier, brain)).fetchone()
            if row is None:
                raise PermissionError("operation_unavailable")
            return self._public(row)

    def list(self, principal, experiment_id):
        brain = _brain(principal)
        _identifier(experiment_id)
        if IM._schema_version(self.store) < 6:
            return []
        with closing(self.store._conn()) as connection:
            self.experiments._row(connection, brain, experiment_id)
            return [self._public(row) for row in connection.execute(
                "SELECT * FROM improvement_operations WHERE experiment_id=? AND brain_id=? ORDER BY id", (experiment_id, brain))]

    def _create_in(self, connection, principal, request, input_blob_hash, *, expected_generation, event_key):
        """Record exact host input; this method cannot reserve an agent call."""
        IC.CaseStore(self.assets)._own_transaction(connection)
        brain = _brain(principal)
        request = operation_request(request)
        _generation(expected_generation)
        IC._digest(input_blob_hash)
        if input_blob_hash != request["input_hash"]:
            raise IM.ConflictError("operation_input_changed")
        payload = {"request": request, "input_blob_hash": input_blob_hash, "expected_generation": expected_generation}
        replay = self.assets._replay(connection, brain, event_key, "operation_create", payload)
        if replay is not None:
            return replay
        row = self.experiments._row(connection, brain, request["experiment_id"])
        self.experiments._public(row)
        phases = (("proposing", "probing", "comparing") if request["kind"] == "semantic"
                  else ("probing", "comparing") if request["kind"] == "compose" else ("proposing",))
        if (row["generation"] != expected_generation or row["phase"] not in phases
                or row["context_id"] != request["context_id"] or row["definition_hash"] != request["definition_hash"]):
            raise IM.ConflictError("experiment_state_stale")
        if connection.execute("SELECT 1 FROM improvement_experiment_selections WHERE experiment_id=? AND brain_id=?",
                              (row["id"], brain)).fetchone():
            raise IM.ConflictError("experiment_sealed")
        value = definition(json.loads(row["definition_json"]))
        self.experiments._bound_in(connection, brain, value, value["context_generation"])
        if request["kind"] == "compose":
            from improvement_compose_permissions import operation_permission
            operation_permission(connection, self.assets, principal, request)
        elif request["kind"] == "semantic":
            candidate = connection.execute("SELECT 1 FROM improvement_skill_candidates WHERE id=? AND brain_id=? "
                "AND experiment_id=? AND context_id=?", (request["candidate_id"], brain, row["id"], row["context_id"])).fetchone()
            if candidate is None:
                raise PermissionError("operation_candidate_unavailable")
        elif request["kind"] == "repair":
            parent = connection.execute("SELECT 1 FROM improvement_operations WHERE id=? AND brain_id=? "
                "AND experiment_id=? AND kind='propose'", (request["parent_id"], brain, row["id"])).fetchone()
            if parent is None:
                raise PermissionError("operation_parent_unavailable")
        duplicate = connection.execute("SELECT 1 FROM improvement_operations WHERE experiment_id=? AND brain_id=? "
            "AND kind=? AND candidate_id IS ?", (row["id"], brain, request["kind"], request["candidate_id"])).fetchone()
        if duplicate:
            raise IM.ConflictError("operation_already_created")
        identifier, stamp = "io_" + secrets.token_hex(12), time.time()
        connection.execute("INSERT INTO improvement_operations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',1,0,?,?)", (
            identifier, brain, row["id"], row["context_id"], request["kind"], request["role"], request["purpose"],
            request["candidate_id"], request["parent_id"], IM._hash(request), IM._json(request), request["input_hash"],
            input_blob_hash, stamp, stamp))
        connection.execute("UPDATE improvement_experiments SET generation=generation+1,updated_at=? WHERE id=? AND brain_id=?",
                           (stamp, row["id"], brain))
        saved = connection.execute("SELECT * FROM improvement_operations WHERE id=? AND brain_id=?", (identifier, brain)).fetchone()
        result = self._public(saved)
        self.assets._event(connection, principal, event_key, "operation_create", payload, result)
        if request["kind"] == "compose":
            operation_permission(connection, self.assets, principal, request, operation=saved)
        return result

    def _reserve_attempt_in(self, connection, principal, identifier, *, expected_generation, event_key):
        """Reserve the genuine role call/attempt atomically; never start an engine."""
        from agent_ledger import CallLedger
        IC.CaseStore(self.assets)._own_transaction(connection)
        brain = _brain(principal)
        _identifier(identifier)
        _generation(expected_generation)
        payload = {"operation_id": identifier, "expected_generation": expected_generation}
        replay = self.assets._replay(connection, brain, event_key, "operation_reserve", payload)
        if replay is not None:
            return replay
        row = connection.execute("SELECT * FROM improvement_operations WHERE id=? AND brain_id=?", (identifier, brain)).fetchone()
        if row is None:
            raise PermissionError("operation_unavailable")
        self._public(row)
        if row["generation"] != expected_generation or row["status"] != "pending" or row["attempt"] != 0:
            raise IM.ConflictError("operation_state_stale")
        experiment = self.experiments._row(connection, brain, row["experiment_id"])
        self.experiments._public(experiment)
        phases = (("proposing", "probing", "comparing") if row["kind"] == "semantic"
                  else ("probing", "comparing") if row["kind"] == "compose" else ("proposing",))
        value = definition(json.loads(experiment["definition_json"]))
        request = operation_request(json.loads(row["request_json"]))
        if (experiment["phase"] not in phases or experiment["context_id"] != row["context_id"]
                or experiment["definition_hash"] != request["definition_hash"]):
            raise IM.ConflictError("experiment_state_stale")
        if connection.execute("SELECT 1 FROM improvement_experiment_selections WHERE experiment_id=? AND brain_id=?",
                              (experiment["id"], brain)).fetchone():
            raise IM.ConflictError("experiment_sealed")
        self.experiments._bound_in(connection, brain, value, value["context_generation"])
        if row["kind"] == "compose":
            from improvement_compose_permissions import operation_permission
            operation_permission(connection, self.assets, principal, request, operation=row)
        execution_id = "improvement_operation:" + identifier
        stamp = time.time()
        call = CallLedger(self.store).reserve(purpose=row["purpose"], reason_ref=execution_id + ":attempt:1",
            brain_id=brain, context_ref="improvement:" + row["experiment_id"], mirror_ref=execution_id,
            obligation=True, attempt=1, now=stamp, c=connection)
        if call is None:
            raise IM.ConflictError("operation_call_capacity_unavailable")
        connection.execute("INSERT INTO improvement_operation_attempts "
            "(operation_id,brain_id,attempt,status,call_id,created_at,updated_at) VALUES(?,?,1,'reserved',?,?,?)",
            (identifier, brain, call, stamp, stamp))
        connection.execute("UPDATE improvement_operations SET status='reserved',generation=generation+1,attempt=1,updated_at=? "
                           "WHERE id=? AND brain_id=?", (stamp, identifier, brain))
        current = connection.execute("SELECT * FROM improvement_operations WHERE id=? AND brain_id=?", (identifier, brain)).fetchone()
        result = self._public(current)
        self.assets._event(connection, principal, event_key, "operation_reserve", payload, result)
        return result
