"""Explicit owner baseline preparation through the actual existing solver store."""
from __future__ import annotations

import json
import time
from contextlib import closing

import improvement_store as IM
from improvement_claude import ClaudeTrialAdapter
from improvement_comparison_plans import ExperimentPlans
from improvement_experiments import _identifier, _generation
from improvement_experiment_protocol import _digest
from improvement_preparation_lineage import load_preparation_lineage, current_preparation_fences
from improvement_preparation_protocol import PINS, preparation_schedule, validate_preparation_request_v3
from improvement_preparation_records import PreparationRecords
from improvement_trial_admission import AdmittedTrial
from improvement_trial_records import _brain
from improvement_trials import _request, TERMINAL
from improvement_execution_limits import MAX_PREPARATION_TRIALS, MAX_ATTEMPTS_PER_TRIAL


class PreparationService:
    def __init__(self, plans):
        if type(plans) is not ExperimentPlans:
            raise TypeError("concrete_preparation_plans_required")
        self.plans, self.host = plans, plans.host
        self.assets, self.store, self.blobs = plans.assets, plans.store, plans.blobs
        self.records = PreparationRecords(self.assets)
        self.trials = plans.admission.trials

    def freeze(self, principal, experiment_id, *, expected_generation, event_key):
        brain = _brain(principal)
        _identifier(experiment_id)
        _generation(expected_generation)
        self.plans.records._available()
        payload = {"experiment_id": experiment_id, "expected_generation": expected_generation}
        with closing(self.store._conn()) as connection:
            replay = self.assets._replay(connection, brain, event_key, "preparation_owner_freeze", payload)
            if replay is not None:
                return replay
            row, prepared = self.plans._state(connection, principal, experiment_id, expected_generation, unsealed=True)
            if row["phase"] != "proposed":
                raise IM.ConflictError("experiment_state_stale")
            manifest = json.loads(connection.execute("SELECT manifest_json FROM improvement_case_sets WHERE id=? AND brain_id=?",
                (prepared[0]["case_set_id"], brain)).fetchone()[0])
            schedule = preparation_schedule(prepared[0], [case["id"] for case in manifest["cases"] if case["split"] == "tuning"], manifest["seed"])
        self.host._snapshot_observe(principal, prepared[1])
        blob = self.blobs.write(brain, IM._json(schedule).encode("utf-8"))
        self.host._snapshot_observe(principal, prepared[1])
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "preparation_owner_freeze", payload)
            if replay is not None:
                return replay
            current, latest = self.plans._state(connection, principal, experiment_id, expected_generation, unsealed=True)
            if current["phase"] != "proposed" or latest != prepared:
                raise IM.ConflictError("preparation_authority_changed")
            result = self.records._freeze_in(connection, principal, schedule, blob, expected_generation=expected_generation,
                event_key="preparation-definition-" + IM._hash([brain, event_key]))
            self.host._snapshot_observe(principal, prepared[1])
            self.plans.records._bound_in(connection, brain, prepared[0], prepared[0]["context_generation"])
            self.assets._event(connection, principal, event_key, "preparation_owner_freeze", payload, result)
            return result

    def _replay(self, connection, principal, payload, event_key):
        brain = _brain(principal)
        saved = self.assets._replay(connection, brain, event_key, "preparation_admit_next", payload)
        if saved is None:
            return None
        row = self.trials._row(connection, brain, saved["trial_id"])
        request = _request(json.loads(row["request_json"]))
        reserve_key = "preparation-reserve-" + IM._hash([brain, event_key])
        if (saved != {"trial_id": row["id"], "request_hash": IM._hash(request), "reserve_event_key": reserve_key}
                or row["request_hash"] != saved["request_hash"] or request["version"] != 3
                or request["pins"]["experiment_id"] != payload["experiment_id"]):
            raise IM.ConflictError("preparation_admission_replay_changed")
        link = connection.execute("SELECT * FROM improvement_preparation_trial_links WHERE trial_id=? AND brain_id=?",
                                  (row["id"], brain)).fetchone()
        if (link is None or link["preparation_id"] != request["preparation"]["preparation_id"]
                or link["cell_position"] != request["preparation"]["cell_position"] or link["request_hash"] != saved["request_hash"]
                or self.assets._replay(connection, brain, reserve_key, "trial_reserve", request) is None):
            raise IM.ConflictError("preparation_admission_replay_changed")
        return AdmittedTrial(row["id"], request, reserve_key)

    def _next(self, connection, principal, payload):
        brain = _brain(principal)
        row, prepared = self.plans._state(connection, principal, payload["experiment_id"], payload["expected_generation"], unsealed=True)
        if row["phase"] != "preparing":
            raise IM.ConflictError("experiment_state_stale")
        preparation = connection.execute("SELECT * FROM improvement_preparations WHERE experiment_id=? AND brain_id=?",
                                          (row["id"], brain)).fetchone()
        if preparation is None:
            raise PermissionError("preparation_unavailable")
        value, binding = prepared[:2]
        manifest = json.loads(connection.execute("SELECT manifest_json FROM improvement_case_sets WHERE id=? AND brain_id=?",
            (value["case_set_id"], brain)).fetchone()[0])
        schedule = preparation_schedule(value, [case["id"] for case in manifest["cases"] if case["split"] == "tuning"], manifest["seed"])
        links = list(connection.execute("SELECT l.cell_position,t.status,a.result_json FROM improvement_preparation_trial_links l "
            "JOIN improvement_trials t ON t.id=l.trial_id AND t.brain_id=l.brain_id "
            "LEFT JOIN improvement_trial_attempts a ON a.trial_id=t.id AND a.brain_id=t.brain_id AND a.attempt=t.attempt "
            "WHERE l.preparation_id=? AND l.brain_id=? ORDER BY l.cell_position LIMIT ?",
            (preparation["id"], brain, MAX_PREPARATION_TRIALS + 1)))
        positions = [item['cell_position'] for item in links]
        if positions != list(range(len(positions))):
            raise IM.ConflictError("preparation_schedule_gap")
        if len(positions) >= len(schedule["cells"]):
            raise IM.ConflictError("preparation_all_cells_admitted")
        if any(item['status'] not in TERMINAL or item['result_json'] is None for item in links):
            raise IM.ConflictError('preparation_cell_pending_or_incomplete')
        cell = schedule["cells"][len(positions)]
        request = validate_preparation_request_v3({"version": 3, "pins": {key: value[key] for key in PINS},
            "case_set_id": value["case_set_id"], **cell, "variant": "baseline", "engine_config": binding["engine_config"],
            "baseline_context_hash": value["baseline_context_hash"], "target_generations": {value["target_id"]: value["base_generation"]},
            "deadline_at": 1, "preparation": {"version": 1, "context_id": value["context_id"], "definition_hash": row["definition_hash"],
                "preparation_id": preparation["id"], "schedule_hash": preparation["schedule_hash"], "cell_position": len(positions)}})
        self.host._bound(connection, principal, request, allow_unlinked=True)
        return request, prepared

    def admit_next(self, principal, experiment_id, *, expected_generation, event_key):
        brain = _brain(principal)
        _identifier(experiment_id)
        _generation(expected_generation)
        self.plans.records._available()
        payload = {"experiment_id": experiment_id, "expected_generation": expected_generation}
        with closing(self.store._conn()) as connection:
            replay = self._replay(connection, principal, payload, event_key)
            if replay is not None:
                return replay
            prepared = self._next(connection, principal, payload)
        # SQL completion precedes the runner's final workspace/lifetime drain.
        # Serialize both rapid admissions and that cleanup handoff before any
        # new immutable link/call is reserved. Replay above remains historical.
        handle = self.trials.workspace.acquire_brain_execution(brain)
        if handle is None:
            raise IM.ConflictError('preparation_execution_busy')
        try:
            return self._admit_owned(principal, payload, event_key, prepared)
        finally:
            handle.close()

    def _admit_owned(self, principal, payload, event_key, prepared):
        brain = _brain(principal)
        self.host._snapshot_observe(principal, prepared[1][1])
        def native_current(connection, joined):
            for _ in range(2):
                if self._next(connection, principal, payload) != prepared:
                    raise IM.ConflictError("preparation_admission_authority_changed")
                self.host._snapshot_observe(principal, prepared[1][1])
            return "allow"

        try:
            adapter = ClaudeTrialAdapter(prepared[0]["engine_config"])
            adapter.bind_native_authority(self.assets, principal, scope_hash=IM._hash({
                "version": 1, "kind": "preparation_cell_admission", "brain_id": brain,
                "event_key_hash": IM._hash(event_key), "request_hash": IM._hash(payload),
                "authority_hash": IM._hash(prepared[0])}), current=native_current)
            available = adapter.verify()
            if type(available) is not dict or available.get("supported") is not True:
                raise ValueError("trial_native_unavailable")
            _digest(available.get("capability_hash"))
        except (ValueError, OSError, RuntimeError):
            raise ValueError("trial_native_unavailable") from None
        self.host._snapshot_observe(principal, prepared[1][1])
        reserve_key = "preparation-reserve-" + IM._hash([brain, event_key])
        with self.store._Tx(self.store) as connection:
            replay = self._replay(connection, principal, payload, event_key)
            if replay is not None:
                return replay
            if self._next(connection, principal, payload) != prepared:
                raise IM.ConflictError("preparation_admission_authority_changed")
            request = {**prepared[0], "deadline_at": time.time() + prepared[1][0]["timeout_seconds"]}
            trial = self.trials._reserve_in(connection, principal, request, event_key=reserve_key)
            self.host._bound(connection, principal, request)
            self.host._snapshot_observe(principal, prepared[1][1])
            proof = load_preparation_lineage(connection, brain, request, blobs=self.blobs, current=True,
                                               require_link=True, trial_id=trial["trial_id"])
            self.host._snapshot_observe(principal, prepared[1][1])
            current_preparation_fences(connection, brain, proof)
            self.assets._event(connection, principal, event_key, "preparation_admit_next", payload,
                {"trial_id": trial["trial_id"], "request_hash": IM._hash(request), "reserve_event_key": reserve_key})
            return AdmittedTrial(trial["trial_id"], request, reserve_key)

    def _completion_snapshot(self, connection, brain, preparation):
        links = [dict(row) for row in connection.execute(
            "SELECT l.*,t.request_json,t.request_hash AS actual_request_hash,t.status AS trial_status,"
            "t.generation AS trial_generation,t.attempt AS current_attempt,a.status AS attempt_status,a.result_json "
            "FROM improvement_preparation_trial_links l JOIN improvement_trials t ON t.id=l.trial_id AND t.brain_id=l.brain_id "
            "JOIN improvement_trial_attempts a ON a.trial_id=t.id AND a.brain_id=t.brain_id AND a.attempt=t.attempt "
            "WHERE l.preparation_id=? AND l.brain_id=? ORDER BY l.cell_position LIMIT ?",
            (preparation["id"], brain, MAX_PREPARATION_TRIALS + 1))]
        attempts = [dict(row) for row in connection.execute(
            "SELECT a.trial_id,a.attempt,a.status,a.call_id,a.engine_at,a.materialization_hash,a.workspace_json "
            "FROM improvement_trial_attempts a JOIN improvement_preparation_trial_links l "
            "ON l.trial_id=a.trial_id AND l.brain_id=a.brain_id WHERE l.preparation_id=? AND l.brain_id=? "
            "ORDER BY a.trial_id,a.attempt LIMIT ?", (preparation["id"], brain, MAX_PREPARATION_TRIALS * MAX_ATTEMPTS_PER_TRIAL + 1))]
        if (len(links) != preparation["cell_count"] or len(links) > MAX_PREPARATION_TRIALS
                or len(attempts) > MAX_PREPARATION_TRIALS * MAX_ATTEMPTS_PER_TRIAL
                or [row["cell_position"] for row in links] != list(range(preparation["cell_count"]))
                or any(row["trial_status"] not in TERMINAL or row["attempt_status"] not in TERMINAL
                       or row["result_json"] is None or row["request_hash"] != row["actual_request_hash"] for row in links)
                or any(row["status"] not in TERMINAL for row in attempts)):
            raise IM.ConflictError("preparation_results_incomplete")
        return links, attempts

    def complete(self, principal, experiment_id, *, expected_generation, event_key):
        """Seal actual result refs only after the real solver lifetime and cleanup."""
        brain = _brain(principal)
        _identifier(experiment_id)
        _generation(expected_generation)
        payload = {"experiment_id": experiment_id, "expected_generation": expected_generation}
        with closing(self.store._conn()) as connection:
            replay = self.assets._replay(connection, brain, event_key, "preparation_complete", payload)
            if replay is not None:
                return replay
            row = self.plans.records._row(connection, brain, experiment_id)
            self.plans.records._public(row)
            if row["phase"] != "preparing" or row["generation"] != expected_generation:
                raise IM.ConflictError("experiment_state_stale")
            preparation = connection.execute("SELECT * FROM improvement_preparations WHERE experiment_id=? AND brain_id=?",
                                              (experiment_id, brain)).fetchone()
            if preparation is None:
                raise PermissionError("preparation_unavailable")
            # Incomplete metadata must reject before creating any private lock directories.
            self._completion_snapshot(connection, brain, preparation)
        workspace = self.trials.workspace
        handle = workspace.acquire_brain_execution(brain)
        if handle is None:
            raise IM.ConflictError("preparation_execution_busy")
        try:
            with closing(self.store._conn()) as connection:
                row, prepared = self.plans._state(connection, principal, experiment_id, expected_generation, unsealed=True)
                if row["phase"] != "preparing":
                    raise IM.ConflictError("experiment_state_stale")
                preparation = connection.execute("SELECT * FROM improvement_preparations WHERE experiment_id=? AND brain_id=?",
                    (experiment_id, brain)).fetchone()
                if preparation is None:
                    raise PermissionError("preparation_unavailable")
                snapshot = self._completion_snapshot(connection, brain, preparation)
                refs, proofs = [], []
                for link in snapshot[0]:
                    request = _request(json.loads(link["request_json"]))
                    proof = load_preparation_lineage(connection, brain, request, blobs=self.blobs, current=True,
                                                     require_link=True, trial_id=link["trial_id"])
                    pointer = json.loads(link["result_json"])
                    if type(pointer) is not dict or set(pointer) != {"result_id", "result_hash", "blob_hash"}:
                        raise IM.ConflictError("preparation_result_changed")
                    report = self.trials.read_result(principal, link["trial_id"], link["current_attempt"], result_id=pointer["result_id"])
                    from improvement_result_domain import require_product_report
                    require_product_report(report)
                    if IM._hash(report) != pointer["result_hash"]:
                        raise IM.ConflictError("preparation_result_changed")
                    refs.append({"trial_id": link["trial_id"], "attempt": link["current_attempt"],
                                 "request_hash": link["request_hash"], **pointer})
                    proofs.append(proof)
            for attempt in snapshot[1]:
                receipt = json.loads(attempt["workspace_json"]) if attempt["workspace_json"] is not None else None
                if not workspace.cleanup_proven(attempt["trial_id"], attempt["attempt"], receipt):
                    raise IM.ConflictError("preparation_execution_busy")
            self.host._snapshot_observe(principal, prepared[1])
            with self.store._Tx(self.store) as connection:
                replay = self.assets._replay(connection, brain, event_key, "preparation_complete", payload)
                if replay is not None:
                    return replay
                current, latest = self.plans._state(connection, principal, experiment_id, expected_generation, unsealed=True)
                if (current["phase"] != "preparing" or latest != prepared
                        or self._completion_snapshot(connection, brain, preparation) != snapshot):
                    raise IM.ConflictError("preparation_completion_changed")
                self.host._snapshot_observe(principal, prepared[1])
                for proof in proofs:
                    current_preparation_fences(connection, brain, proof)
                connection.execute("UPDATE improvement_experiments SET phase='proposing',generation=generation+1,updated_at=? "
                                   "WHERE id=? AND brain_id=?", (time.time(), experiment_id, brain))
                result = {"experiment_id": experiment_id, "preparation_id": preparation["id"], "schedule_hash": preparation["schedule_hash"],
                          "phase": "proposing", "generation": expected_generation + 1, "result_refs": refs}
                self.assets._event(connection, principal, event_key, "preparation_complete", payload, result)
                return result
        finally:
            handle.close()
