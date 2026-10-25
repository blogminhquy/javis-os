"""Host-owned evaluation results and call settlement share one durable transaction."""
from __future__ import annotations

import json
import secrets
import tempfile
import time
from contextlib import closing
from pathlib import Path

import improvement_cases as IC
import improvement_evaluation as EVAL
import improvement_store as IM
import improvement_usage as IU
from improvement_blobs import MAX_ASSET_BYTES, AssetUnavailable
from improvement_trial_checks import execution_invariants
from improvement_trial_evidence import TrialEvidence
from improvement_trial_products import TrialProducts
from improvement_qualification_records import require_product_store


def _guard(callback, request):
    if not callable(callback):
        raise ValueError("trial_live_guard_required")
    observed = IC._frozen(callback())
    expected = {key: request[key] for key in ("baseline_context_hash", "target_generations")}
    expected.update({key: request["pins"][key] for key in ("scope_hash", "grant_hash", "engine_config_hash")})
    if observed != expected:
        raise IM.ConflictError("trial_live_authority_changed")
    return observed


def _verdict(values):
    values = list(values)
    return "fail" if "fail" in values else "unknown" if not values or "unknown" in values else "pass"


class TrialResults:
    def __init__(self, trials):
        self.trials = trials

    def read(self, principal, identifier, attempt, *, result_id=None):
        brain = IM._brain(principal)
        if type(attempt) is not int or not 1 <= attempt < 2 ** 63:
            raise ValueError("invalid_trial_attempt")
        if IM._schema_version(self.trials.store) < 3:
            raise PermissionError("trial_result_unavailable")
        with closing(self.trials.store._conn()) as connection:
            require_product_store(self.trials.assets, principal, connection=connection)
            trial = self.trials._row(connection, brain, identifier)
            request = json.loads(trial["request_json"])
            if request.get('version') == 4:
                from improvement_view_lineage import load_view_lineage
                if IM._hash(request) != trial['request_hash']:
                    raise AssetUnavailable('view_trial_request_changed')
                load_view_lineage(connection, brain, request, blobs=self.trials.blobs, current=False, require_link=True, trial_id=identifier)
            if request.get("version") == 3:
                from improvement_preparation_lineage import load_preparation_lineage
                if IM._hash(request) != trial["request_hash"]:
                    raise AssetUnavailable("preparation_trial_request_changed")
                load_preparation_lineage(connection, brain, request, blobs=self.trials.blobs,
                                         current=False, require_link=True, trial_id=identifier)
            if request.get("version") == 2:
                from improvement_experiment_lineage import load_lineage
                if IM._hash(request) != trial["request_hash"]:
                    raise AssetUnavailable("experiment_trial_request_changed")
                load_lineage(connection, brain, request, blobs=self.trials.blobs, current=False, require_link=True, trial_id=identifier)
            row = connection.execute("SELECT result_json FROM improvement_trial_attempts WHERE trial_id=? AND attempt=?",
                                     (identifier, attempt)).fetchone()
            if not row or not row[0]:
                raise PermissionError("trial_result_unavailable")
            pointer = json.loads(row[0])
            result = connection.execute("SELECT * FROM improvement_trial_results WHERE id=? AND trial_id=? AND brain_id=? AND attempt=?",
                                        (result_id or pointer["result_id"], identifier, brain, attempt)).fetchone()
            if result is None:
                raise PermissionError("trial_result_unavailable")
            if result_id is None and (result["result_hash"] != pointer["result_hash"] or result["blob_hash"] != pointer["blob_hash"]):
                raise AssetUnavailable("trial_result_reference_changed")
            raw = self.trials.blobs.read(brain, result["blob_hash"])
            report = json.loads(raw)
            if IM._hash(report) != result["result_hash"]:
                raise AssetUnavailable("trial_result_hash_mismatch")
            if request.get('version') == 4 and (report.get('version') != 4 or report.get('trial_id') != identifier
                    or report.get('attempt') != attempt or report.get('request_hash') != trial['request_hash']
                    or report.get('experiment_lineage') != request['lineage'] or report.get('effective_view') != request['view']):
                raise AssetUnavailable('view_trial_result_changed')
            if request.get("version") == 2 and (report.get("version") != 2 or report.get("trial_id") != identifier
                    or report.get("attempt") != attempt or report.get("request_hash") != trial["request_hash"]
                    or report.get("experiment_lineage") != request["lineage"]):
                raise AssetUnavailable("experiment_trial_result_changed")
            if request.get("version") == 3 and (report.get("version") != 3 or report.get("trial_id") != identifier
                    or report.get("attempt") != attempt or report.get("request_hash") != trial["request_hash"]
                    or report.get("preparation_lineage") != request["preparation"]):
                raise AssetUnavailable("preparation_trial_result_changed")
            records = list(connection.execute('SELECT * FROM improvement_trial_observations WHERE trial_id=? AND attempt=? ORDER BY sequence',
                (identifier, attempt))) if 'native_decisions' in report else []
            if 'native_decisions' in report:
                from improvement_native_trace_checks import validated_history, reread_native_decisions
                from improvement_native_decisions import NativeImageDecisionStore, attempt_scope
                stored_attempt = connection.execute('SELECT workspace_json FROM improvement_trial_attempts WHERE trial_id=? AND attempt=?',
                    (identifier, attempt)).fetchone()
                workspace = json.loads(stored_attempt['workspace_json'])
                reader = TrialEvidence(self.trials)
                packets = validated_history(records, lambda item: reader._decode(brain, item), kind='trial', receipt=workspace)
                trace = {'count': len(records), 'last_sequence': records[-1]['sequence'],
                    'hash': IM._hash([[item['sequence'], item['payload_hash']] for item in records])}
                if trace != report['trace']: raise AssetUnavailable('trial_result_trace_changed')
                scope = attempt_scope(kind='trial', brain_id=brain, receipt=workspace,
                    config_pin=request['engine_config'], capability_hash=report['capability_hash'])
                decisions = NativeImageDecisionStore(self.trials.assets)
                actual = reread_native_decisions(packets, kind='trial', receipt=workspace,
                    read_decision=lambda joined: decisions.read(principal, joined, scope_hash=scope, connection=connection))
                if actual != report['native_decisions']: raise AssetUnavailable('native_result_decisions_changed')
            return report

    def reevaluate(self, principal, identifier, attempt, *, expected_generation, event_key, checker_registry):
        """Append a historical product evaluation; never reopen or query an execution."""
        from improvement_trial_decisions import OwnerDecisionStore
        from improvement_trials import TERMINAL
        brain = IM._brain(principal)
        if type(expected_generation) is not int or expected_generation < 1 or type(attempt) is not int or attempt < 1:
            raise IM.ConflictError("trial_reevaluation_stale")
        payload = {"trial_id": identifier, "attempt": attempt, "expected_generation": expected_generation}
        owners = OwnerDecisionStore(self.trials)
        with self.trials.store._Tx(self.trials.store) as connection:
            require_product_store(self.trials.assets, principal, connection=connection)
            replay = self.trials.assets._replay(connection, brain, event_key, "trial_reevaluate", payload)
            if replay is not None:
                return replay
            row, attempt_row, case, contract, contract_hash = owners._context(connection, brain, identifier, attempt)
            if (row["generation"] != expected_generation or row["status"] not in TERMINAL
                    or attempt_row["status"] not in TERMINAL or not attempt_row["result_json"]):
                raise IM.ConflictError("trial_reevaluation_stale")
            pointer = json.loads(attempt_row["result_json"])
            previous = self.read(principal, identifier, attempt)
            artifact = TrialProducts(self.trials)._row(connection, "improvement_trial_artifacts", brain, identifier, attempt)
            content = self.trials.blobs.read(brain, artifact["content_hash"])
            if (artifact["path"] != contract["output"]["path"] or len(content) != artifact["byte_size"]
                    or artifact["content_hash"] != previous["artifact_hash"] or contract_hash != previous["contract_hash"]):
                raise IM.ConflictError("trial_product_changed")
            private = {"id": case["id"], "answer": json.loads(self.trials.blobs.read(brain, case["answer_hash"])),
                       "evaluator_refs": case["evaluator_refs"]}
            decisions = owners.decisions(principal, identifier, attempt)
            decision_ids = [item[0] for item in connection.execute("SELECT id FROM improvement_trial_owner_decisions "
                "WHERE trial_id=? AND attempt=? ORDER BY id", (identifier, attempt))]
        # Recheck the immutable native artifact, even if its disposable workspace has
        # since been cleaned. An owner edit in another file cannot replace these bytes.
        with tempfile.TemporaryDirectory(prefix="trial-recheck-") as directory:
            path = Path(directory) / IC.output_path(artifact["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            evaluation = EVAL.evaluate_trial(contract, directory, private, checker_registry, owner_decisions=decisions)
        report = {**previous, "evaluation": evaluation, "previous_result_id": pointer["result_id"],
                  "evaluation_origin": "owner_recheck", "owner_decision_ids": decision_ids}
        report["verdict"] = _verdict([evaluation["verdict"], *(item["verdict"] for item in previous["mandatory"])])
        raw = IM._json(report).encode("utf-8")
        if len(raw) > MAX_ASSET_BYTES:
            raise ValueError("trial_result_too_large")
        with self.trials.store._Tx(self.trials.store) as connection:
            require_product_store(self.trials.assets, principal, connection=connection)
            replay = self.trials.assets._replay(connection, brain, event_key, "trial_reevaluate", payload)
            if replay is not None:
                return replay
            row, current_attempt, _, _, _ = owners._context(connection, brain, identifier, attempt)
            if (row["generation"] != expected_generation or row["status"] not in TERMINAL
                    or current_attempt["result_json"] != attempt_row["result_json"]):
                raise IM.ConflictError("trial_reevaluation_stale")
            if evaluation["output_hash"] is not None and evaluation["output_hash"] != previous["artifact_hash"]:
                raise IM.ConflictError("trial_evaluation_output_mismatch")
            blob = self.trials.blobs.write(brain, raw)
            result_id, now = "ir_" + secrets.token_hex(12), time.time()
            digest = IM._hash(report)
            connection.execute("INSERT INTO improvement_trial_results VALUES(?,?,?,?,?,?,?)",
                               (result_id, identifier, brain, attempt, digest, blob, now))
            new_pointer = {"result_id": result_id, "result_hash": digest, "blob_hash": blob}
            connection.execute("UPDATE improvement_trial_attempts SET result_json=?,updated_at=? WHERE trial_id=? AND attempt=?",
                               (IM._json(new_pointer), now, identifier, attempt))
            connection.execute("UPDATE improvement_trials SET generation=generation+1,updated_at=? WHERE id=?", (now, identifier))
            result = self.trials._public(connection, self.trials._row(connection, brain, identifier))
            self.trials.assets._event(connection, principal, event_key, "trial_reevaluate", payload, result)
            return result

    def _artifact_hash(self, connection, row, workspace, contract):
        stored = connection.execute("SELECT * FROM improvement_trial_artifacts WHERE trial_id=? AND attempt=?",
                                    (row["id"], row["attempt"])).fetchone()
        if not stored:
            return None
        if stored["path"] != contract["output"]["path"]:
            raise IM.ConflictError("trial_output_changed")
        raw = self.trials.blobs.read(row["brain_id"], stored["content_hash"])
        try:
            actual = EVAL._artifact(workspace["output_root"], stored["path"])
        except EVAL._Unavailable as error:
            raise IM.ConflictError("trial_output_changed") from error
        if len(raw) != stored["byte_size"] or actual.content != raw:
            raise IM.ConflictError("trial_output_changed")
        return stored["content_hash"]

    def finish(self, principal, identifier, *, expected_generation, lease_token,
               capability_hash, live_guard, checker_registry):
        """Internal runner boundary: no report, verdict or actor is accepted from JSON.

        The live guard and checker registry are trusted host dependencies. The worker
        never receives this lease or these callables. Checker execution happens
        outside the SQLite write transaction; authority and exact output are checked
        again before publishing a result and settling its existing call.
        """
        brain = IM._brain(principal)
        IC._digest(capability_hash)
        require_product_store(self.trials.assets, principal)
        request = self.trials.get(principal, identifier)["request"]
        guard = _guard(live_guard, request)
        with self.trials.store._Tx(self.trials.store) as connection:
            require_product_store(self.trials.assets, principal, connection=connection)
            row, attempt = self.trials._leased(connection, principal, identifier, expected_generation, lease_token, time.time())
            if row["status"] != "evaluating" or attempt["engine_at"] is None:
                raise IM.ConflictError("trial_evaluation_stale")
            case = self.trials._current(connection, brain, request, trial_id=row["id"], principal=principal)
            workspace = json.loads(attempt["workspace_json"])
            manifest = self.trials.workspace.validate(workspace)
            if IM._hash(manifest) != attempt["materialization_hash"]:
                raise IM.ConflictError("trial_materialization_drift")
            contract = json.loads(connection.execute("SELECT contract_json FROM improvement_contracts WHERE brain_id=? AND manifest_hash=?",
                                                     (brain, request["pins"]["contract_hash"])).fetchone()[0])
            if IM._hash(contract) != request["pins"]["contract_hash"]:
                raise IM.ConflictError("trial_contract_drift")
            TrialProducts(self.trials)._products(connection, row, principal=principal, capability_hash=capability_hash)
            records = list(connection.execute("SELECT * FROM improvement_trial_observations WHERE trial_id=? AND attempt=? ORDER BY sequence",
                                              (identifier, row["attempt"])))
            reader = TrialEvidence(self.trials)
            packets = [reader._decode(brain, record) for record in records]
            native = None
            decision_reader = None
            if manifest['version'] in (4, 5):
                from improvement_native_trace_checks import validated_history, validate_native_trace, require_durable_allow
                from improvement_native_decisions import NativeImageDecisionStore, attempt_scope
                from improvement_sandbox import trial_system_prompt
                decoded = {record['sequence']: packet for record, packet in zip(records, packets)}
                validated_history(records, lambda record: decoded[record['sequence']], kind='trial', receipt=workspace)
                scope = attempt_scope(kind='trial', brain_id=brain, receipt=workspace,
                    config_pin=request['engine_config'], capability_hash=capability_hash)
                image_decisions = NativeImageDecisionStore(self.trials.assets)
                decision_reader = lambda joined: image_decisions.read(principal, joined, scope_hash=scope)
                prompt = IM._json({'task': manifest['case']['task'], 'fixtures': [
                    {key: item[key] for key in ('snapshot_id', 'source')} for item in manifest['case']['fixtures']]})
                native = validate_native_trace(packets, kind='trial', receipt=workspace, pin=request['engine_config'],
                    capability_hash=capability_hash, system_prompt=trial_system_prompt(manifest), user_prompt=prompt,
                    data_hash=workspace['input_hash'], read_decision=lambda joined: image_decisions.read(principal, joined, scope_hash=scope, connection=connection),
                    tool_policy='baseline_inline' if manifest['version'] == 5 else 'pinned_skill')
                require_durable_allow(native)
            artifact_hash = self._artifact_hash(connection, row, workspace, contract)
            private = {"id": case["id"], "answer": json.loads(self.trials.blobs.read(brain, case["answer_hash"])),
                       "evaluator_refs": case["evaluator_refs"]}
            number = row["attempt"]
        # Host checkers may perform expensive isolated work. Never hold a write lock
        # across them, and never reinterpret a failed evaluator as permission to query.
        mandatory = execution_invariants(request, manifest, workspace, packets, capability_hash, contract=contract, read_decision=decision_reader)
        from improvement_trial_decisions import OwnerDecisionStore
        decisions = OwnerDecisionStore(self.trials).decisions(principal, identifier, number)
        evaluation = EVAL.evaluate_trial(contract, workspace["output_root"], private, checker_registry, owner_decisions=decisions)
        usage = IU.trial_usage(request["pins"]["experiment_id"], identifier)
        _guard(live_guard, request)
        bodies = packets if native is None else native['worker_bodies']
        terminal = next(packet["event"] for packet in bodies
                        if packet["type"] == "engine_event" and packet["event"].get("type") == "terminal")
        status = "failed" if terminal["is_error"] else "completed"
        report = {"version": 1, "trial_id": identifier, "attempt": number, "execution_status": status,
                  "artifact_hash": artifact_hash, "contract_hash": request["pins"]["contract_hash"],
                  "evaluation": evaluation, "mandatory": mandatory, "usage": usage,
                  "verdict": _verdict([evaluation["verdict"], *(item["verdict"] for item in mandatory)]),
                  "capability_hash": capability_hash, "live_guard": guard,
                  "trace": {"count": len(records), "last_sequence": records[-1]["sequence"],
                            "hash": IM._hash([[record["sequence"], record["payload_hash"]] for record in records])}}
        if native is not None: report['native_decisions'] = native['decisions']
        if request.get('version') == 4:
            report.update(version=4, request_hash=IM._hash(request), experiment_lineage=request['lineage'], effective_view=request['view'])
        elif request.get("version") == 2:
            report.update(version=2, request_hash=IM._hash(request), experiment_lineage=request["lineage"])
        elif request.get("version") == 3:
            report.update(version=3, request_hash=IM._hash(request), preparation_lineage=request["preparation"])
        raw = IM._json(report).encode("utf-8")
        if len(raw) > MAX_ASSET_BYTES:
            raise ValueError("trial_result_too_large")
        digest = IM._hash(report)
        with self.trials.store._Tx(self.trials.store) as connection:
            require_product_store(self.trials.assets, principal, connection=connection)
            row, attempt = self.trials._leased(connection, principal, identifier, expected_generation, lease_token, time.time())
            if row["status"] != "evaluating" or row["attempt"] != number:
                raise IM.ConflictError("trial_evaluation_stale")
            self.trials._current(connection, brain, request, trial_id=row["id"], principal=principal)
            self.trials.workspace.validate(workspace)
            if native is not None:
                current_records = list(connection.execute('SELECT * FROM improvement_trial_observations WHERE trial_id=? AND attempt=? ORDER BY sequence',
                    (identifier, number)))
                if [dict(record) for record in current_records] != [dict(record) for record in records]:
                    raise IM.ConflictError('trial_result_trace_changed')
                current_packets = validated_history(current_records, lambda record: reader._decode(brain, record), kind='trial', receipt=workspace)
                if current_packets != packets: raise IM.ConflictError('trial_result_trace_changed')
                actual = [image_decisions.read(principal, joined, scope_hash=scope, connection=connection) for joined in native['joins']]
                if actual != native['decisions']: raise IM.ConflictError('native_result_decisions_changed')
                require_durable_allow({'decisions': actual})
            if self._artifact_hash(connection, row, workspace, contract) != artifact_hash:
                raise IM.ConflictError("trial_output_changed")
            if evaluation["output_hash"] is not None and evaluation["output_hash"] != artifact_hash:
                raise IM.ConflictError("trial_evaluation_output_mismatch")
            blob = self.trials.blobs.write(brain, raw)
            _guard(live_guard, request)
            result_id = "ir_" + secrets.token_hex(12)
            now = time.time()
            self.trials._leased(connection, principal, identifier, expected_generation, lease_token, now)
            connection.execute("INSERT INTO improvement_trial_results VALUES(?,?,?,?,?,?,?)",
                               (result_id, identifier, brain, number, digest, blob, now))
            pointer = {"result_id": result_id, "result_hash": digest, "blob_hash": blob}
            if not self.trials.ledger._settle_in(connection, attempt["call_id"], "error" if status == "failed" else "ok",
                                                  None, None, None, now):
                raise IM.ConflictError("trial_call_state_stale")
            connection.execute("UPDATE improvement_trial_attempts SET status=?,result_json=?,lease_token=NULL,lease_until=NULL,updated_at=? "
                               "WHERE trial_id=? AND attempt=?", (status, IM._json(pointer), now, identifier, number))
            connection.execute("UPDATE improvement_trials SET status=?,generation=generation+1,updated_at=? WHERE id=?", (status, now, identifier))
            result = self.trials._public(connection, self.trials._row(connection, brain, identifier))
        self.trials.cleanup_terminal(principal, identifier)
        return result
