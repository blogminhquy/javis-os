"""One host-selected comparison slot; native preflight precedes atomic admission.

Cell position is an internal scheduler choice, never an owner HTTP selector. This
unit proves baseline mechanics; the owner service must choose the next frozen
cell without skipping unavailable candidates. No changed-arm execution opens here.
"""
from __future__ import annotations

import json
import time
from contextlib import closing

import improvement_store as IM
from improvement_comparison_plans import ExperimentPlans
from improvement_experiments import _generation, _identifier
from improvement_experiment_lineage import load_lineage
from improvement_experiment_protocol import definition, comparison_matrix, comparison_hash, matrix_cell, validate_request_v2
from improvement_trial_admission import AdmittedTrial
from improvement_trial_host import _brain
from improvement_trials import _request
from improvement_claude import ClaudeTrialAdapter


class ExperimentAdmission:
    def __init__(self, plans):
        if type(plans) is not ExperimentPlans:
            raise TypeError("concrete_experiment_admission_required")
        self.plans, self.host, self.assets, self.store = plans, plans.host, plans.assets, plans.store
        self.trials = plans.admission.trials

    def _replay(self, connection, principal, payload, event_key):
        brain = _brain(principal)
        saved = self.assets._replay(connection, brain, event_key, "experiment_admit_slot", payload)
        if saved is None:
            return None
        row = self.trials._row(connection, brain, saved["trial_id"])
        request = _request(json.loads(row["request_json"]))
        reserve_key = "experiment-reserve-" + IM._hash([brain, event_key])
        if (saved != {"trial_id": row["id"], "request_hash": IM._hash(request), "reserve_event_key": reserve_key}
                or row["request_hash"] != saved["request_hash"] or request["pins"]["experiment_id"] != payload["experiment_id"]
                or request["lineage"]["comparison_id"] != payload["comparison_id"]
                or request["lineage"]["cell_position"] != payload["cell_position"]):
            raise IM.ConflictError("experiment_admission_replay_changed")
        link = connection.execute("SELECT * FROM improvement_experiment_trial_links WHERE comparison_id=? AND brain_id=? AND cell_position=?",
                                  (payload["comparison_id"], brain, payload["cell_position"])).fetchone()
        if (link is None or link["trial_id"] != row["id"] or link["request_hash"] != saved["request_hash"]
                or self.assets._replay(connection, brain, reserve_key, "trial_reserve", request) is None):
            raise IM.ConflictError("experiment_admission_replay_changed")
        return AdmittedTrial(row["id"], request, reserve_key)

    def _prepare(self, connection, principal, payload):
        brain = _brain(principal)
        row = self.plans.records._row(connection, brain, payload["experiment_id"])
        self.plans.records._public(row)
        if row["generation"] != payload["expected_generation"] or row["phase"] not in ("probing", "comparing"):
            raise IM.ConflictError("experiment_state_stale")
        comparison = connection.execute("SELECT * FROM improvement_comparisons WHERE id=? AND brain_id=? AND experiment_id=?",
                                       (payload["comparison_id"], brain, row["id"])).fetchone()
        if comparison is None:
            raise PermissionError("experiment_comparison_unavailable")
        from improvement_comparison_links import require_legacy_comparison
        require_legacy_comparison(connection, brain, comparison["id"])
        if comparison["kind"] != "tuning":
            raise PermissionError("experiment_final_execution_unavailable")
        # Derive only closed schedule metadata before any plaintext/probe. A
        # blocked candidate never decrypts context, proposal, fixture or answers.
        value = definition(json.loads(row["definition_json"]))
        from improvement_experiment_qualification import require_tuning_families
        require_tuning_families(connection, brain, value['case_set_id'])
        arm = connection.execute("SELECT * FROM improvement_experiment_arms WHERE experiment_id=? AND brain_id=? AND ordinal=?",
                                 (row["id"], brain, comparison["ordinal"])).fetchone()
        if arm is None or arm["envelope_hash"] != comparison["arm_hash"] or comparison["definition_hash"] != row["definition_hash"]:
            raise PermissionError("experiment_arm_unavailable")
        cases = connection.execute("SELECT manifest_json FROM improvement_case_sets WHERE id=? AND brain_id=?",
                                   (value["case_set_id"], brain)).fetchone()
        if cases is None:
            raise PermissionError("experiment_case_set_unavailable")
        manifest = json.loads(cases[0])
        matrix = comparison_matrix(value, arm["envelope_hash"], comparison["ordinal"], "tuning",
            [case["id"] for case in manifest["cases"] if case["split"] == "tuning"], manifest["seed"])
        if IM._hash(matrix) != comparison["matrix_hash"] or comparison["cell_count"] != 2 * len(matrix["pairs"]):
            raise IM.ConflictError("experiment_matrix_changed")
        cell = matrix_cell(matrix, payload["cell_position"])
        if cell["variant"] != "baseline":
            raise PermissionError("experiment_candidate_execution_unavailable")
        row, prepared = self.plans._state(connection, principal, payload["experiment_id"], payload["expected_generation"], unsealed=True)
        arm = self.plans._frozen_arm(connection, principal, row, prepared, comparison["ordinal"])
        if connection.execute("SELECT 1 FROM improvement_experiment_trial_links WHERE comparison_id=? AND brain_id=? AND cell_position=?",
                              (comparison["id"], brain, payload["cell_position"])).fetchone():
            raise IM.ConflictError("experiment_cell_already_admitted")
        value, binding = prepared[:2]
        request = validate_request_v2({"version": 2,
            "pins": {key: value[key] for key in ("experiment_id", "base_bundle_hash", "contract_hash", "case_set_hash",
                "engine_config_hash", "grant_hash", "scope_hash", "policy_version")} | {"candidate_bundle_hash": arm["envelope_hash"]},
            "case_set_id": value["case_set_id"], "case_id": cell["case_id"], "repeat": cell["repeat"], "variant": cell["variant"],
            "engine_config": binding["engine_config"], "baseline_context_hash": value["baseline_context_hash"],
            "target_generations": {value["target_id"]: value["base_generation"]}, "deadline_at": 1,
            "lineage": {"version": 1, "context_id": value["context_id"], "definition_hash": row["definition_hash"],
                "comparison_id": comparison["id"], "comparison_hash": comparison_hash(comparison), "matrix_hash": comparison["matrix_hash"],
                "arm_ordinal": arm["ordinal"], "arm_hash": arm["envelope_hash"], "candidate_id": arm["candidate_id"],
                "pair_id": cell["pair_id"], "cell_position": payload["cell_position"]}})
        self.host._bound(connection, principal, request, allow_unlinked=True)
        return request, prepared

    def admit(self, principal, experiment_id, comparison_id, cell_position, *, expected_generation, event_key):
        brain = _brain(principal)
        _identifier(experiment_id)
        _identifier(comparison_id)
        _generation(expected_generation)
        if type(cell_position) is not int or not 0 <= cell_position < 4000:
            raise ValueError("invalid_experiment_cell")
        self.plans.records._available()
        payload = {"experiment_id": experiment_id, "comparison_id": comparison_id, "cell_position": cell_position,
                   "expected_generation": expected_generation}
        with closing(self.store._conn()) as connection:
            replay = self._replay(connection, principal, payload, event_key)
            if replay is not None:
                return replay
            prepared = self._prepare(connection, principal, payload)
        self.host._snapshot_observe(principal, prepared[1][1])
        def native_current(connection, joined):
            for _ in range(2):
                if self._prepare(connection, principal, payload) != prepared:
                    raise IM.ConflictError("experiment_admission_authority_changed")
                self.host._snapshot_observe(principal, prepared[1][1])
            return "allow"

        try:
            adapter = ClaudeTrialAdapter(prepared[0]["engine_config"])
            adapter.bind_native_authority(self.assets, principal, scope_hash=IM._hash({
                "version": 1, "kind": "experiment_cell_admission", "brain_id": brain,
                "event_key_hash": IM._hash(event_key), "request_hash": IM._hash(payload),
                "authority_hash": IM._hash(prepared[0])}), current=native_current)
            available = adapter.verify()
            if type(available) is not dict or available.get("supported") is not True:
                raise ValueError("trial_native_unavailable")
            from improvement_experiment_protocol import _digest
            _digest(available.get("capability_hash"))
        except (ValueError, OSError, RuntimeError):
            raise ValueError("trial_native_unavailable") from None
        self.host._snapshot_observe(principal, prepared[1][1])
        reserve_key = "experiment-reserve-" + IM._hash([brain, event_key])
        with self.store._Tx(self.store) as connection:
            replay = self._replay(connection, principal, payload, event_key)
            if replay is not None:
                return replay
            if self._prepare(connection, principal, payload) != prepared:
                raise IM.ConflictError("experiment_admission_authority_changed")
            request = {**prepared[0], "deadline_at": time.time() + prepared[1][0]["timeout_seconds"]}
            trial = self.trials._reserve_in(connection, principal, request, event_key=reserve_key)
            # Linked guard includes the exact full request, never a v1 projection.
            load_lineage(connection, brain, request, blobs=self.plans.blobs, current=True,
                         require_link=True, trial_id=trial["trial_id"])
            self.host._bound(connection, principal, request)
            current, current_prepared = self.plans._state(connection, principal, experiment_id, expected_generation, unsealed=True)
            if current_prepared != prepared[1]:
                raise IM.ConflictError("experiment_admission_authority_changed")
            if dict(self.plans._frozen_arm(connection, principal, current, current_prepared, request["lineage"]["arm_ordinal"]))["envelope_hash"] != request["lineage"]["arm_hash"]:
                raise IM.ConflictError("experiment_admission_authority_changed")
            self.host._snapshot_observe(principal, prepared[1][1])
            self.assets._event(connection, principal, event_key, "experiment_admit_slot", payload,
                {"trial_id": trial["trial_id"], "request_hash": IM._hash(request), "reserve_event_key": reserve_key})
            return AdmittedTrial(trial["trial_id"], request, reserve_key)
