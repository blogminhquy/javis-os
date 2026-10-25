"""Durable raw role products and checks, separate from proposal/semantic acceptance."""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from contextlib import closing

import improvement_store as IM
import improvement_usage as IU
from improvement_blobs import AssetUnavailable
from improvement_operation_checks import execution_checks
from improvement_operation_execution import OperationExecution
from improvement_trial_evidence import decode_trace
from improvement_trial_records import _brain
from improvement_qualification_records import require_product_store


class OperationResults:
    def __init__(self, execution):
        if type(execution) is not OperationExecution:
            raise TypeError("concrete_operation_results_required")
        self.execution = execution

    def read(self, principal, identifier, attempt):
        return self.read_stored(self.execution.assets, principal, identifier, attempt)

    @staticmethod
    def read_stored(assets, principal, identifier, attempt):
        """The same concrete cold reader for role owners and derived proposals.

        No source refresh or new execution is authorized by historical reading.
        Native observations and durable decisions remain mandatory dependencies.
        """
        from improvement_operation_records import OperationRecords
        if type(assets) is not IM.ImprovementStore:
            raise TypeError('concrete_operation_result_store_required')
        if type(attempt) is not int or attempt not in (1, 2):
            raise ValueError("invalid_operation_result_attempt")
        require_product_store(assets, principal)
        OperationRecords(assets).get(principal, identifier)
        brain = _brain(principal)
        with closing(assets.store._conn()) as connection:
            operation = connection.execute('SELECT * FROM improvement_operations WHERE id=? AND brain_id=?',
                (identifier, brain)).fetchone()
            if operation is None:
                raise PermissionError('operation_unavailable')
            OperationRecords._public(operation)
            rows = list(connection.execute("SELECT * FROM improvement_operation_results WHERE operation_id=? AND brain_id=? AND attempt=?",
                                           (identifier, brain, attempt)))
            if not rows:
                raise PermissionError("operation_result_unavailable")
            if len(rows) != 1:
                raise AssetUnavailable("operation_result_ambiguous")
        record = rows[0]
        raw = assets.blobs.read(brain, record["blob_hash"])
        value = json.loads(raw)
        if (IM._hash(value) != record["result_hash"] or value.get("operation_id") != identifier
                or type(value.get("attempt")) is not int or value["attempt"] != attempt
                or value.get("request_hash") != operation["request_hash"]):
            raise AssetUnavailable("operation_result_binding_mismatch")
        if value.get('version') == 2:
            from improvement_native_trace_checks import validated_history, reread_native_decisions
            from improvement_native_decisions import NativeImageDecisionStore, attempt_scope
            from improvement_trial_records import HostContextRecords
            with closing(assets.store._conn()) as connection:
                stored_attempt = connection.execute('SELECT workspace_json FROM improvement_operation_attempts WHERE operation_id=? AND brain_id=? AND attempt=?',
                    (identifier, brain, attempt)).fetchone()
                workspace = json.loads(stored_attempt['workspace_json'])
                context = connection.execute('SELECT * FROM improvement_trial_contexts WHERE id=? AND brain_id=?',
                    (operation['context_id'], brain)).fetchone()
                configuration = HostContextRecords(assets)._decode(context)['engine_config']
                if IM._hash(configuration) != value['engine_config_hash']: raise AssetUnavailable('operation_result_binding_mismatch')
                rows = list(connection.execute('SELECT * FROM improvement_operation_observations WHERE operation_id=? AND brain_id=? AND attempt=? ORDER BY sequence',
                    (identifier, brain, attempt)))
                packets = validated_history(rows, lambda item: decode_trace(assets.blobs, brain, item), kind='operation', receipt=workspace)
                if [item['payload_hash'] for item in rows] != value['trace_hashes']: raise AssetUnavailable('operation_result_trace_changed')
                scope = attempt_scope(kind='operation', brain_id=brain, receipt=workspace, config_pin=configuration, capability_hash=value['capability_hash'])
                decisions = NativeImageDecisionStore(assets)
                actual = reread_native_decisions(packets, kind='operation', receipt=workspace,
                    read_decision=lambda joined: decisions.read(principal, joined, scope_hash=scope, connection=connection))
                if actual != value.get('native_decisions'): raise AssetUnavailable('native_result_decisions_changed')
        return value

    def artifact(self, principal, identifier, attempt):
        report = self.read(principal, identifier, attempt)
        reference = report["artifact"]
        if reference is None:
            raise PermissionError("operation_artifact_unavailable")
        raw = self.execution.blobs.read(_brain(principal), reference["blob_hash"])
        if hashlib.sha256(raw).hexdigest() != reference["hash"] or len(raw) != reference["byte_size"]:
            raise AssetUnavailable("operation_artifact_changed")
        return raw

    @staticmethod
    def _trace(connection, row):
        return [dict(item) for item in connection.execute("SELECT * FROM improvement_operation_observations WHERE operation_id=? AND brain_id=? "
            "AND attempt=? ORDER BY sequence", (row["id"], row["brain_id"], row["attempt"]))]

    def finish(self, principal, identifier, *, expected_generation, lease_token, capability_hash):
        from improvement_experiment_protocol import _digest
        _digest(capability_hash)
        brain = _brain(principal)
        with closing(self.execution.store._conn()) as connection:
            require_product_store(self.execution.assets, principal, connection=connection)
            row, attempt = self.execution._leased(connection, principal, identifier, expected_generation, lease_token, time.time())
            prepared = self.execution._current(connection, principal, row)
            if row["status"] != "running" or attempt["engine_at"] is None or attempt["workspace_json"] is None:
                raise IM.ConflictError("operation_result_state_stale")
            trace = self._trace(connection, row)
            if (not trace or trace[-1]["kind"] not in ("worker_complete", "drained")
                    or any(item["late"] or item["sequence"] != number for number, item in enumerate(trace, 1))):
                raise IM.ConflictError("operation_trace_incomplete")
            workspace = json.loads(attempt["workspace_json"])
            materialization_hash = attempt["materialization_hash"]
            request_hash, number = row["request_hash"], row["attempt"]
        self.execution.host._snapshot_observe(principal, prepared[1])
        manifest = self.execution.workspace.validate(workspace)
        if (IM._hash(manifest) != materialization_hash or manifest["operation_id"] != identifier
                or manifest["brain_id"] != brain or IM._hash(manifest["request"]) != request_hash):
            raise IM.ConflictError("operation_materialization_changed")
        native = None
        decision_reader = None
        if manifest['version'] == 2:
            from improvement_native_trace_checks import validated_history, validate_native_trace, require_durable_allow
            from improvement_native_decisions import NativeImageDecisionStore, attempt_scope
            from improvement_operation_profile import operation_system_prompt, operation_user_prompt
            packets = validated_history(trace, lambda item: decode_trace(self.execution.blobs, brain, item), kind='operation', receipt=workspace)
            scope = attempt_scope(kind='operation', brain_id=brain, receipt=workspace,
                config_pin=prepared[1]['engine_config'], capability_hash=capability_hash)
            decisions = NativeImageDecisionStore(self.execution.assets)
            decision_reader = lambda joined: decisions.read(principal, joined, scope_hash=scope)
            native = validate_native_trace(packets, kind='operation', receipt=workspace, pin=prepared[1]['engine_config'],
                capability_hash=capability_hash, system_prompt=operation_system_prompt(manifest), user_prompt=operation_user_prompt(manifest),
                data_hash=manifest['request']['input_hash'], read_decision=decision_reader)
            require_durable_allow(native)
            bodies = native['worker_bodies']
        else:
            if trace[-1]['kind'] != 'worker_complete': raise IM.ConflictError('operation_trace_incomplete')
            packets = [decode_trace(self.execution.blobs, brain, item) for item in trace]
            bodies = packets
        checks = execution_checks(prepared[1]["engine_config"], manifest, workspace, packets, capability_hash, read_decision=decision_reader)
        events = [packet["event"] for packet in bodies if packet["type"] == "engine_event"]
        artifacts = [event for event in events if event.get("type") == "artifact"]
        receipts = [event for event in events if event.get("type") == "operation_installation_receipt"]
        artifact = installation = None
        if len(artifacts) == 1 and type(artifacts[0].get("content")) is str:
            raw = artifacts[0]["content"].encode()
            if hashlib.sha256(raw).hexdigest() == artifacts[0].get("hash"):
                blob = self.execution.blobs.write(brain, raw)
                artifact = {"hash": blob, "blob_hash": blob, "byte_size": len(raw)}
        if len(receipts) == 1 and type(receipts[0].get("receipt")) is dict and IM._hash(receipts[0]["receipt"]) == receipts[0].get("hash"):
            blob = self.execution.blobs.write(brain, IM._json(receipts[0]["receipt"]).encode())
            installation = {"hash": blob, "blob_hash": blob}
        report = {"version": 2 if native is not None else 1, "operation_id": identifier, "attempt": number, "request_hash": request_hash,
                  "input_hash": workspace["input_hash"], "materialization_hash": materialization_hash,
                  "engine_config_hash": manifest["engine_config_hash"], "capability_hash": capability_hash,
                  "artifact": artifact, "installation": installation, "checks": checks,
                  "verdict": "fail" if any(item["verdict"] == "fail" for item in checks) else (
                      "unknown" if any(item["verdict"] == "unknown" for item in checks) else "pass"),
                  "usage": IU.operation_usage(manifest["request"]["experiment_id"], identifier),
                  "trace_hashes": [item["payload_hash"] for item in trace], "business_proof": False}
        if native is not None: report['native_decisions'] = native['decisions']
        blob = self.execution.blobs.write(brain, IM._json(report).encode())
        completion = next((item["verdict"] for item in checks if item["id"] == "completion"), "unknown")
        call_status = "ok" if completion == "pass" else "error" if completion == "fail" else "interrupted"
        status = "completed" if call_status == "ok" and report["verdict"] != "fail" else "failed"
        self.execution.host._snapshot_observe(principal, prepared[1])
        with self.execution.store._Tx(self.execution.store) as connection:
            require_product_store(self.execution.assets, principal, connection=connection)
            row, attempt = self.execution._leased(connection, principal, identifier, expected_generation, lease_token, time.time())
            if (row["status"] != "running" or self._trace(connection, row) != trace
                    or attempt["materialization_hash"] != materialization_hash or attempt["workspace_json"] != IM._json(workspace)
                    or self.execution._current(connection, principal, row) != prepared):
                raise IM.ConflictError("operation_result_state_stale")
            self.execution.host._snapshot_observe(principal, prepared[1])
            self.execution._current(connection, principal, row)
            if native is not None:
                # Reauthenticate all encrypted bytes and durable decisions under
                # the actual final transaction, not an earlier checker's view.
                current_packets = validated_history(self._trace(connection, row),
                    lambda item: decode_trace(self.execution.blobs, brain, item), kind='operation', receipt=workspace)
                if current_packets != packets: raise IM.ConflictError('operation_result_state_stale')
                actual = [decisions.read(principal, joined, scope_hash=scope, connection=connection) for joined in native['joins']]
                if actual != native['decisions']: raise IM.ConflictError('native_result_decisions_changed')
                require_durable_allow({'decisions': actual})
            stamp = time.time()
            self.execution._leased(connection, principal, identifier, expected_generation, lease_token, stamp)
            call = self.execution.bound_call(connection, row, attempt)
            pin = prepared[1]["engine_config"]
            if (call["engine_at"] != attempt["engine_at"] or call["status"] not in ("running", call_status)
                    or call["engine"] != pin["provider"] or call["model"] != pin["model"]):
                raise IM.ConflictError("operation_call_state_stale")
            if call["status"] == "running":
                self.execution.ledger._settle_in(connection, attempt["call_id"], call_status, None, None, None, stamp)
            connection.execute("INSERT INTO improvement_operation_results VALUES(?,?,?,?,?,?,?)", (
                "ior_" + secrets.token_hex(12), identifier, brain, number, IM._hash(report), blob, stamp))
            connection.execute("UPDATE improvement_operation_attempts SET status=?,result_json=?,lease_token=NULL,lease_until=NULL,updated_at=? "
                "WHERE operation_id=? AND brain_id=? AND attempt=?", (status, IM._json(report), stamp, identifier, brain, number))
            self.execution._advance(connection, row, status, stamp)
            result = {**self.execution._public(connection, self.execution._row(connection, principal, identifier)), "result": report}
            self.execution.assets._event(connection, principal, "operation-result:" + identifier + ":" + str(number),
                "operation_result", {"operation_id": identifier, "attempt": number, "result_hash": IM._hash(report)},
                {"operation_id": identifier, "attempt": number, "result_hash": IM._hash(report), "status": status})
            return result
