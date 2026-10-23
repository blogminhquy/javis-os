"""Owner-authorized append-only confirmations of exact immutable trial products.

Recording evidence never settles a call, changes an execution verdict, or activates a
bundle. The evaluator consumes these typed records separately from untrusted answers.
"""
from __future__ import annotations

import json
import time
from contextlib import closing

import improvement_cases as IC
import improvement_evaluation as IE
import improvement_store as IM
from improvement_trial_products import TrialProducts
from improvement_trials import TERMINAL
from resonance_store import Principal


def _brain(principal):
    if not isinstance(principal, Principal):
        raise PermissionError("owner_required")
    return IM._brain(principal)


def _attempt(value):
    if type(value) is not int or not 1 <= value < 2 ** 63:
        raise ValueError("invalid_trial_attempt")


class OwnerDecisionStore:
    def __init__(self, trials):
        self.trials = trials

    def _readable(self):
        if IM._schema_version(self.trials.store) < 3:
            raise PermissionError("trial_record_unavailable")

    def _context(self, connection, brain, identifier, attempt):
        row = self.trials._row(connection, brain, identifier)
        attempt_row = connection.execute("SELECT * FROM improvement_trial_attempts WHERE trial_id=? AND brain_id=? "
                                         "AND attempt=?", (identifier, brain, attempt)).fetchone()
        if attempt_row is None:
            raise PermissionError("trial_record_unavailable")
        request = json.loads(row["request_json"])
        if IM._hash(request) != row["request_hash"]:
            raise IM.ConflictError("trial_request_drift")
        if request.get('version') == 4:
            from improvement_view_lineage import load_view_lineage
            load_view_lineage(connection, brain, request, blobs=self.trials.blobs,
                current=False, require_link=True, trial_id=identifier)
        if request.get("version") == 3:
            from improvement_preparation_lineage import load_preparation_lineage
            load_preparation_lineage(connection, brain, request, blobs=self.trials.blobs,
                                     current=False, require_link=True, trial_id=identifier)
        if request.get("version") == 2:
            from improvement_experiment_lineage import load_lineage
            load_lineage(connection, brain, request, blobs=self.trials.blobs, current=False, require_link=True, trial_id=identifier)
        pins = request["pins"]
        case_set = self.trials.cases._row(connection, "improvement_case_sets", brain, request["case_set_id"])
        if case_set["manifest_hash"] != pins["case_set_hash"]:
            raise IM.ConflictError("stale_trial_case_set")
        case = self.trials.cases._case(connection, brain, request["case_set_id"], request["case_id"])
        contract_row = connection.execute("SELECT contract_json FROM improvement_contracts WHERE brain_id=? "
                                          "AND manifest_hash=?", (brain, pins["contract_hash"])).fetchone()
        if contract_row is None:
            raise PermissionError("trial_record_unavailable")
        contract = json.loads(contract_row["contract_json"])
        if IM._hash(contract) != pins["contract_hash"] or case["id"] != request["case_id"]:
            raise IM.ConflictError("trial_contract_drift")
        return row, attempt_row, case, contract, pins["contract_hash"]

    def record(self, principal, trial_id, attempt, criterion_id, verdict, *, output_hash,
               contract_hash, expected_generation, event_key) -> dict:
        brain = _brain(principal)
        _attempt(attempt)
        if (not isinstance(criterion_id, str) or not IC._ID.fullmatch(criterion_id)
                or not isinstance(verdict, str) or verdict not in {"pass", "fail", "unknown"}):
            raise ValueError("invalid_owner_decision")
        IC._digest(output_hash)
        IC._digest(contract_hash)
        if type(expected_generation) is not int or expected_generation < 1:
            raise IM.ConflictError("owner_decision_stale")
        self._readable()
        payload = {"trial_id": trial_id, "attempt": attempt, "criterion_id": criterion_id,
                   "verdict": verdict, "output_hash": output_hash, "contract_hash": contract_hash,
                   "expected_generation": expected_generation}
        assets = self.trials.assets
        with self.trials.store._Tx(self.trials.store) as connection:
            replay = assets._replay(connection, brain, event_key, "trial_owner_decision", payload)
            if replay is not None:
                return replay
            row, attempt_row, case, contract, pinned_hash = self._context(connection, brain, trial_id, attempt)
            if (row["generation"] != expected_generation or row["status"] not in TERMINAL
                    or attempt_row["status"] not in TERMINAL):
                raise IM.ConflictError("owner_decision_stale")
            criterion = next((item for item in contract["criteria"] if item["id"] == criterion_id), None)
            if criterion is None or criterion["kind"] != "owner_confirm":
                raise ValueError("owner_confirmation_criterion_required")
            if contract_hash != pinned_hash:
                raise IM.ConflictError("owner_decision_contract_stale")
            artifact = TrialProducts(self.trials)._row(connection, "improvement_trial_artifacts", brain, trial_id, attempt)
            raw = self.trials.blobs.read(brain, artifact["content_hash"])
            if (artifact["content_hash"] != output_hash or len(raw) != artifact["byte_size"]
                    or artifact["path"] != contract["output"]["path"]
                    or criterion["config"].get("path", artifact["path"]) != artifact["path"]):
                raise IM.ConflictError("owner_decision_output_stale")
            now = time.time()
            inserted = connection.execute("INSERT INTO improvement_trial_owner_decisions(trial_id,brain_id,attempt,"
                "criterion_id,output_hash,contract_hash,verdict,actor,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (trial_id, brain, attempt, criterion_id, output_hash, contract_hash, verdict, principal.by, now))
            changed = connection.execute("UPDATE improvement_trials SET generation=generation+1,updated_at=? WHERE id=? "
                                         "AND brain_id=? AND generation=?", (now, trial_id, brain, expected_generation))
            if changed.rowcount != 1:
                raise IM.ConflictError("owner_decision_stale")
            result = {"decision_id": inserted.lastrowid, "trial_id": trial_id, "attempt": attempt,
                      "case_id": case["id"], "criterion_id": criterion_id, "output_hash": output_hash,
                      "contract_hash": contract_hash, "verdict": verdict, "actor": principal.by,
                      "generation": expected_generation + 1}
            assets._event(connection, principal, event_key, "trial_owner_decision", payload, result)
            return result

    def decisions(self, principal, trial_id, attempt) -> tuple[IE.OwnerDecision, ...]:
        brain = _brain(principal)
        _attempt(attempt)
        self._readable()
        with closing(self.trials.store._conn()) as connection:
            _, _, case, _, _ = self._context(connection, brain, trial_id, attempt)
            rows = connection.execute("SELECT criterion_id,output_hash,contract_hash,verdict "
                "FROM improvement_trial_owner_decisions WHERE trial_id=? AND brain_id=? AND attempt=? ORDER BY id",
                (trial_id, brain, attempt)).fetchall()
            return tuple(IE.OwnerDecision(case["id"], row["criterion_id"], row["output_hash"],
                                          row["contract_hash"], row["verdict"]) for row in rows)
