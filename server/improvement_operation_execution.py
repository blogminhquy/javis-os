"""Actual role attempt ownership over the existing host, SQL and call ledger."""
from __future__ import annotations

import hashlib
import json
import math
import secrets
import time
from contextlib import closing

from agent_ledger import CallLedger
import improvement_store as IM
from improvement_comparison_plans import ExperimentPlans
from improvement_experiment_protocol import definition, _id
from improvement_experiments import _generation
from improvement_operation_adapter import ClaudeOperationAdapter
from improvement_operation_protocol import operation_materialization
from improvement_operation_records import OperationRecords
from improvement_operation_schema import TERMINAL, assert_installed
from improvement_operation_workspace import OperationWorkspace
from improvement_trial_records import _brain
from improvement_trial_service import OwnerTrialService

FAILURE_REASONS = {"cancelled", "timeout", "authority_changed", "worker_failed", "runner_failed", "telemetry_failed",
                   "evidence_failed", "capacity_unavailable", "unsupported_configuration", "native_transient_error"}


class OperationExecution:
    def __init__(self, plans, trial_service):
        if (type(plans) is not ExperimentPlans or type(trial_service) is not OwnerTrialService
                or trial_service.host is not plans.host or trial_service.trials.assets is not plans.assets
                or trial_service.trials.store is not plans.store):
            raise TypeError("concrete_operation_execution_dependencies_required")
        self.plans, self.host, self.trial_service = plans, plans.host, trial_service
        self.assets, self.store, self.blobs = plans.assets, plans.store, plans.blobs
        self.records, self.ledger = OperationRecords(self.assets), CallLedger(self.store)
        barrier = trial_service.trials.workspace
        self.workspace = OperationWorkspace(barrier.root.parent / "operations", brain_barrier=barrier)

    def _row(self, connection, principal, identifier):
        brain = _brain(principal)
        _id(identifier)
        row = connection.execute("SELECT * FROM improvement_operations WHERE id=? AND brain_id=?", (identifier, brain)).fetchone()
        if row is None:
            raise PermissionError("operation_unavailable")
        self.records._public(row)
        return row

    def _public(self, connection, row):
        attempts = [dict(item) for item in connection.execute(
            "SELECT attempt,status,call_id,lease_until,engine_at,materialization_hash,workspace_json,failure_reason,created_at "
            "FROM improvement_operation_attempts WHERE operation_id=? AND brain_id=? ORDER BY attempt", (row["id"], row["brain_id"]))]
        experiment = self.plans.records._row(connection, row["brain_id"], row["experiment_id"])
        value = definition(json.loads(experiment["definition_json"]))
        return {**self.records._public(row), "brain_id": row["brain_id"], "request": json.loads(row["request_json"]),
                "attempts": attempts, "deadline_at": attempts[0]["created_at"] + value["timeout_seconds"] if attempts else None}

    @staticmethod
    def deadline(connection, row, timeout_seconds):
        first = connection.execute("SELECT created_at FROM improvement_operation_attempts WHERE operation_id=? AND brain_id=? "
                                   "ORDER BY attempt LIMIT 1", (row["id"], row["brain_id"])).fetchone()
        if first is None:
            raise IM.ConflictError("operation_attempt_unavailable")
        return first["created_at"] + timeout_seconds

    def get(self, principal, identifier):
        self.records.get(principal, identifier)
        with closing(self.store._conn()) as connection:
            return self._public(connection, self._row(connection, principal, identifier))

    def _current(self, connection, principal, row):
        assert_installed(connection)
        if row["kind"] == "compose":
            from improvement_compose_permissions import ComposePermissions
            request = json.loads(row["request_json"])
            return ComposePermissions(self.plans).current(connection, principal,
                request['compose_authorization_id'], operation=row)['prepared']
        experiment = self.plans.records._row(connection, row["brain_id"], row["experiment_id"])
        experiment, prepared = self.plans._state(connection, principal, row["experiment_id"], experiment["generation"], unsealed=True)
        phases = ("proposing", "probing", "comparing") if row["kind"] == "semantic" else ("proposing",)
        if (experiment["phase"] not in phases or experiment["context_id"] != row["context_id"]
                or experiment["definition_hash"] != json.loads(row["request_json"])["definition_hash"]):
            raise IM.ConflictError("operation_authority_changed")
        return prepared

    def guard(self, principal, identifier):
        with closing(self.store._conn()) as connection:
            row = self._row(connection, principal, identifier)
            prepared = self._current(connection, principal, row)
        self.host._snapshot_observe(principal, prepared[1])
        return prepared

    def reserve(self, principal, identifier, *, expected_generation, event_key):
        _generation(expected_generation)
        payload = {"operation_id": identifier, "expected_generation": expected_generation}
        with closing(self.store._conn()) as connection:
            replay = self.assets._replay(connection, _brain(principal), event_key, "operation_native_reserve", payload)
            if replay is not None:
                return replay
            row = self._row(connection, principal, identifier)
            if row["generation"] != expected_generation or row["status"] != "pending" or row["attempt"] != 0:
                raise IM.ConflictError("operation_state_stale")
            prepared = self._current(connection, principal, row)
            original = dict(row)
        self.host._snapshot_observe(principal, prepared[1])
        def native_current(connection, joined):
            for _ in range(2):
                current = self._row(connection, principal, identifier)
                if dict(current) != original or self._current(connection, principal, current) != prepared:
                    raise IM.ConflictError("operation_authority_changed")
                self.host._snapshot_observe(principal, prepared[1])
            return "allow"

        adapter = ClaudeOperationAdapter(prepared[1]["engine_config"])
        adapter.bind_native_authority(self.assets, principal, scope_hash=IM._hash({
            "version": 1, "kind": "operation_reserve", "brain_id": _brain(principal),
            "request_hash": IM._hash(payload), "authority_hash": IM._hash([original, prepared])}), current=native_current)
        capability = adapter.verify()
        if (type(capability) is not dict or capability.get("supported") is not True
                or capability.get("account_ready") is False or capability.get("domain") == "qualification"):
            raise ValueError("operation_native_unavailable")
        from improvement_experiment_protocol import _digest
        _digest(capability.get("capability_hash"))
        self.host._snapshot_observe(principal, prepared[1])
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, _brain(principal), event_key, "operation_native_reserve", payload)
            if replay is not None:
                return replay
            row = self._row(connection, principal, identifier)
            if self._current(connection, principal, row) != prepared:
                raise IM.ConflictError("operation_authority_changed")
            self.records._reserve_attempt_in(connection, principal, identifier, expected_generation=expected_generation,
                event_key="native-operation-reserve-" + IM._hash([row["brain_id"], event_key]))
            self.host._snapshot_observe(principal, prepared[1])
            self._current(connection, principal, self._row(connection, principal, identifier))
            result = self._public(connection, self._row(connection, principal, identifier))
            self.assets._event(connection, principal, event_key, "operation_native_reserve", payload, result)
            return result

    @staticmethod
    def _attempt(connection, row):
        attempt = connection.execute("SELECT * FROM improvement_operation_attempts WHERE operation_id=? AND brain_id=? AND attempt=?",
                                     (row["id"], row["brain_id"], row["attempt"])).fetchone()
        if attempt is None:
            raise IM.ConflictError("operation_attempt_unavailable")
        return attempt

    def _leased(self, connection, principal, identifier, generation, token, now):
        _generation(generation)
        row = self._row(connection, principal, identifier)
        attempt = self._attempt(connection, row)
        if (row["generation"] != generation or row["status"] in TERMINAL or type(token) is not str or not token
                or attempt["lease_token"] != token or attempt["lease_until"] is None or attempt["lease_until"] <= now):
            raise IM.ConflictError("operation_lease_stale")
        return row, attempt

    def claim(self, principal, identifier, *, expected_generation, lease_seconds=60):
        if type(lease_seconds) not in (int, float) or not 1 <= lease_seconds <= 300:
            raise ValueError("invalid_operation_lease")
        self.guard(principal, identifier)
        with self.store._Tx(self.store) as connection:
            row = self._row(connection, principal, identifier)
            prepared = self._current(connection, principal, row)
            attempt = self._attempt(connection, row)
            _generation(expected_generation)
            now = time.time()
            deadline = self.deadline(connection, row, prepared[0]["timeout_seconds"])
            if (row["generation"] != expected_generation or row["status"] != "reserved"
                    or attempt["lease_token"] is not None or deadline <= now):
                raise IM.ConflictError("operation_claim_stale")
            token = secrets.token_urlsafe(32)
            connection.execute("UPDATE improvement_operation_attempts SET lease_token=?,lease_until=?,writer_hash=?,updated_at=? "
                "WHERE operation_id=? AND brain_id=? AND attempt=?", (token, min(now + lease_seconds, deadline),
                hashlib.sha256(token.encode()).hexdigest(), now, identifier, row["brain_id"], row["attempt"]))
            self._advance(connection, row, row["status"], now)
            self.host._snapshot_observe(principal, prepared[1])
            self._current(connection, principal, self._row(connection, principal, identifier))
            return {**self._public(connection, self._row(connection, principal, identifier)), "lease_token": token}

    @staticmethod
    def _advance(connection, row, status, now):
        connection.execute("UPDATE improvement_operations SET status=?,generation=generation+1,updated_at=? WHERE id=? AND brain_id=?",
                           (status, now, row["id"], row["brain_id"]))

    def materialize(self, principal, identifier, *, expected_generation, lease_token):
        with closing(self.store._conn()) as connection:
            row, _ = self._leased(connection, principal, identifier, expected_generation, lease_token, time.time())
            prepared = self._current(connection, principal, row)
            data_hash = row["input_blob_hash"]
            request = json.loads(row["request_json"])
        self.host._snapshot_observe(principal, prepared[1])
        data = json.loads(self.blobs.read(_brain(principal), data_hash))
        from improvement_native_formats import input_version
        version = input_version(prepared[1]['engine_config'], 'operation')
        manifest = operation_materialization({"version": version, "brain_id": _brain(principal), "operation_id": identifier,
            "request": request, "engine_config_hash": prepared[0]["engine_config_hash"], "data": data, "learning_origin": "compose"})
        with self.store._Tx(self.store) as connection:
            row, _ = self._leased(connection, principal, identifier, expected_generation, lease_token, time.time())
            if self._current(connection, principal, row) != prepared:
                raise IM.ConflictError("operation_authority_changed")
            self.host._snapshot_observe(principal, prepared[1])
            self._current(connection, principal, row)
            self._leased(connection, principal, identifier, expected_generation, lease_token, time.time())
        return manifest

    def heartbeat(self, principal, identifier, *, expected_generation, lease_token, lease_seconds=60):
        if type(lease_seconds) not in (int, float) or not 1 <= lease_seconds <= 300:
            raise ValueError("invalid_operation_lease")
        self.guard(principal, identifier)
        with self.store._Tx(self.store) as connection:
            row, attempt = self._leased(connection, principal, identifier, expected_generation, lease_token, time.time())
            prepared = self._current(connection, principal, row)
            self.host._snapshot_observe(principal, prepared[1])
            self._current(connection, principal, row)
            stamp = time.time()
            self._leased(connection, principal, identifier, expected_generation, lease_token, stamp)
            deadline = self.deadline(connection, row, prepared[0]["timeout_seconds"])
            if deadline <= stamp:
                raise IM.ConflictError("operation_lease_stale")
            connection.execute("UPDATE improvement_operation_attempts SET lease_until=?,updated_at=? "
                "WHERE operation_id=? AND brain_id=? AND attempt=?", (min(stamp + lease_seconds, deadline), stamp,
                identifier, row["brain_id"], row["attempt"]))
            return self._public(connection, row)

    def prepared(self, principal, identifier, *, expected_generation, lease_token, receipt):
        manifest = self.materialize(principal, identifier, expected_generation=expected_generation, lease_token=lease_token)
        if self.workspace.validate(receipt) != manifest or receipt["operation_id"] != identifier:
            raise IM.ConflictError("operation_materialization_changed")
        with self.store._Tx(self.store) as connection:
            row, attempt = self._leased(connection, principal, identifier, expected_generation, lease_token, time.time())
            prepared = self._current(connection, principal, row)
            if row["status"] != "reserved" or receipt["attempt"] != row["attempt"]:
                raise IM.ConflictError("operation_state_stale")
            now = time.time()
            connection.execute("UPDATE improvement_operation_attempts SET status='prepared',materialization_hash=?,workspace_json=?,updated_at=? "
                "WHERE operation_id=? AND brain_id=? AND attempt=?", (IM._hash(manifest), IM._json(receipt), now,
                identifier, row["brain_id"], row["attempt"]))
            self._advance(connection, row, "prepared", now)
            self.host._snapshot_observe(principal, prepared[1])
            self._current(connection, principal, self._row(connection, principal, identifier))
            return self._public(connection, self._row(connection, principal, identifier))

    def start_engine(self, principal, identifier, *, expected_generation, lease_token, now=None):
        # Every start still requires current actual host sources and SQL grants.
        if now is not None and (type(now) not in (int, float) or not math.isfinite(now)):
            raise ValueError("invalid_operation_clock")
        self.guard(principal, identifier)
        with self.store._Tx(self.store) as connection:
            stamp = time.time() if now is None else now
            row, attempt = self._leased(connection, principal, identifier, expected_generation, lease_token, stamp)
            prepared = self._current(connection, principal, row)
            if row["status"] != "prepared" or attempt["engine_at"] is not None or attempt["workspace_json"] is None:
                raise IM.ConflictError("operation_state_stale")
            manifest = self.workspace.validate(json.loads(attempt["workspace_json"]))
            if (manifest["operation_id"] != identifier or manifest["brain_id"] != row["brain_id"]
                    or IM._hash(manifest) != attempt["materialization_hash"]
                    or IM._hash(manifest["request"]) != row["request_hash"]
                    or manifest["request"]["input_hash"] != row["input_hash"]
                    or manifest["engine_config_hash"] != prepared[0]["engine_config_hash"]):
                raise IM.ConflictError("operation_materialization_changed")
            self.host._snapshot_observe(principal, prepared[1])
            self._current(connection, principal, row)
            stamp = time.time() if now is None else now
            self._leased(connection, principal, identifier, expected_generation, lease_token, stamp)
            pin = prepared[1]["engine_config"]
            if not self.ledger._mark_engine_in(connection, attempt["call_id"], pin["provider"], pin["model"], stamp):
                raise IM.ConflictError("operation_call_state_stale")
            connection.execute("UPDATE improvement_operation_attempts SET status='running',engine_at=?,updated_at=? "
                "WHERE operation_id=? AND brain_id=? AND attempt=?", (stamp, stamp, identifier, row["brain_id"], row["attempt"]))
            self._advance(connection, row, "running", stamp)
            return self._public(connection, self._row(connection, principal, identifier))

    def abort(self, principal, identifier, *, expected_generation, lease_token, reason):
        if type(reason) is not str or reason not in FAILURE_REASONS:
            raise ValueError("invalid_operation_failure_reason")
        if type(lease_token) is not str or not lease_token:
            raise IM.ConflictError("operation_abort_writer_unbound")
        with self.store._Tx(self.store) as connection:
            row = self._row(connection, principal, identifier)
            attempt = self._attempt(connection, row)
            writer = hashlib.sha256(lease_token.encode()).hexdigest()
            if not attempt["writer_hash"] or not secrets.compare_digest(writer, attempt["writer_hash"]):
                raise IM.ConflictError("operation_abort_writer_unbound")
            if row["status"] in TERMINAL:
                return self._public(connection, row)
            _generation(expected_generation)
            if row["generation"] != expected_generation or attempt["lease_token"] != lease_token:
                raise IM.ConflictError("operation_abort_stale")
            now = time.time()
            self._stop_in(connection, row, attempt, now, reason)
            result = self._public(connection, self._row(connection, principal, identifier))
            self.assets._event(connection, principal, "operation-abort:" + identifier + ":" + str(row["attempt"]),
                "operation_abort", {"operation_id": identifier, "attempt": row["attempt"], "reason": reason}, result)
            return result

    def _stop_in(self, connection, row, attempt, now, reason, status=None):
        identifier = row["id"]
        call = self.bound_call(connection, row, attempt)
        marker = call["engine_at"]
        status = status or ("not_run" if marker is None else "interrupted")
        if marker is None:
            if not self.ledger._refund_in(connection, attempt["call_id"], now):
                raise IM.ConflictError("operation_call_state_stale")
        else:
            self.ledger._settle_in(connection, attempt["call_id"], "interrupted", None, None, None, now)
        connection.execute("UPDATE improvement_operation_attempts SET status=?,engine_at=?,failure_reason=?,lease_token=NULL,lease_until=NULL,updated_at=? "
            "WHERE operation_id=? AND brain_id=? AND attempt=?", (status, marker, reason, now, identifier, row["brain_id"], row["attempt"]))
        self._advance(connection, row, status, now)

    @staticmethod
    def bound_call(connection, row, attempt):
        call = connection.execute("SELECT * FROM agent_calls WHERE id=?", (attempt["call_id"],)).fetchone()
        if (call is None or (attempt["engine_at"] is not None and attempt["engine_at"] != call["engine_at"])
                or call["brain_id"] != row["brain_id"] or call["purpose"] != row["purpose"]
                or call["mirror_ref"] != "improvement_operation:" + row["id"]
                or call["reason_ref"] != "improvement_operation:" + row["id"] + ":attempt:" + str(attempt["attempt"])
                or call["context_ref"] != "improvement:" + row["experiment_id"] or call["attempt"] != attempt["attempt"]):
            raise IM.ConflictError("operation_call_state_stale")
        return call

    def reject_unclaimed(self, principal, identifier, *, expected_generation, reason):
        if type(reason) is not str or reason not in FAILURE_REASONS:
            raise ValueError("invalid_operation_failure_reason")
        _generation(expected_generation)
        with self.store._Tx(self.store) as connection:
            row = self._row(connection, principal, identifier)
            if row["status"] in TERMINAL:
                return self._public(connection, row)
            attempt = self._attempt(connection, row)
            if (row["generation"] != expected_generation or row["status"] != "reserved"
                    or attempt["writer_hash"] is not None or attempt["lease_token"] is not None
                    or attempt["engine_at"] is not None):
                raise IM.ConflictError("operation_claim_stale")
            now = time.time()
            if not self.ledger._refund_in(connection, attempt["call_id"], now):
                raise IM.ConflictError("operation_call_state_stale")
            connection.execute("UPDATE improvement_operation_attempts SET status='not_run',failure_reason=?,updated_at=? "
                "WHERE operation_id=? AND brain_id=? AND attempt=?", (reason, now, identifier, row["brain_id"], row["attempt"]))
            self._advance(connection, row, "not_run", now)
            result = self._public(connection, self._row(connection, principal, identifier))
            self.assets._event(connection, principal, "operation-unclaimed:" + identifier + ":" + str(row["attempt"]),
                "operation_unclaimed", {"operation_id": identifier, "attempt": row["attempt"], "reason": reason}, result)
            return result

    def cancel(self, principal, identifier, *, expected_generation, event_key):
        brain = _brain(principal)
        _generation(expected_generation)
        _id(identifier)
        payload = {"operation_id": identifier, "expected_generation": expected_generation}
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "operation_owner_cancel", payload)
            if replay is not None:
                return replay
            row = self._row(connection, principal, identifier)
            if row["generation"] != expected_generation:
                raise IM.ConflictError("operation_state_stale")
            if row["status"] in ("not_run", "interrupted"):
                # Preserve immutable attempt outcome while fencing a retry that
                # has not yet reserved its next call. The SQL fence requires this
                # actual owner event in the same transaction, not a raw status edit.
                predicted = self._public(connection, {**dict(row), "status": "cancelled", "generation": row["generation"] + 1})
                self.assets._event(connection, principal, event_key, "operation_owner_cancel", payload, predicted)
                self._advance(connection, row, "cancelled", time.time())
                return self._public(connection, self._row(connection, principal, identifier))
            elif row["status"] not in TERMINAL:
                if row["attempt"]:
                    self._stop_in(connection, row, self._attempt(connection, row), time.time(), "cancelled", "cancelled")
                else:
                    self._advance(connection, row, "cancelled", time.time())
            result = self._public(connection, self._row(connection, principal, identifier))
            self.assets._event(connection, principal, event_key, "operation_owner_cancel", payload, result)
            return result

    def retry(self, principal, identifier, *, expected_generation, event_key):
        from improvement_operation_retry import OperationRetry
        return OperationRetry(self).reserve(principal, identifier, expected_generation=expected_generation, event_key=event_key)
