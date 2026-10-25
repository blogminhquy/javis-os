"""Host-derived frozen comparisons; metadata is never execution or activation authority."""
from __future__ import annotations

import json
import time
from contextlib import closing

import improvement_cases as IC
import improvement_store as IM
from improvement_experiments import ExperimentRecords, _generation, _identifier
from improvement_experiment_protocol import definition
from improvement_skill_candidates import SkillCandidates
from improvement_trial_admission import TrialAdmission
from improvement_trial_associations import _association, _FIELDS
from improvement_trial_host import HostContextStore, _brain
from improvement_trial_sources import authorize_case
from improvement_experiment_schema import TERMINAL_PHASES
from improvement_qualification_records import require_product_store


class ExperimentPlans:
    def __init__(self, host, skill_candidates, *, checker_registry=None):
        if (type(host) is not HostContextStore or type(skill_candidates) is not SkillCandidates
                or skill_candidates.assets is not host.assets):
            raise TypeError("concrete_experiment_plans_required")
        self.host, self.authoring = host, skill_candidates
        self.assets, self.store, self.blobs = host.assets, host.store, host.blobs
        self.records = ExperimentRecords(self.assets)
        self.admission = TrialAdmission(host, checker_registry=checker_registry)
        self.associations = self.admission.associations

    @staticmethod
    def _create_request(value):
        value = IC._frozen(value)
        fields = {"experiment_id", "contract_id", "case_set_id", "base_bundle_id",
                  "expected_context_generation", "repeat_policy", "timeout_seconds"}
        if type(value) is dict and set(value) == fields | {"candidate_policy"}:
            if (type(value['candidate_policy']) is not str
                    or value['candidate_policy'] != 'two_proposals_and_one_compose'):
                raise ValueError('invalid_experiment_candidate_policy')
        else:
            IC._fields(value, fields)
        for key in ("experiment_id", "contract_id", "case_set_id", "base_bundle_id"):
            _identifier(value[key])
        _generation(value["expected_context_generation"])
        if (type(value["repeat_policy"]) is not str or value["repeat_policy"] not in ("feasibility", "pilot")
                or type(value["timeout_seconds"]) is not int or not 1 <= value["timeout_seconds"] <= 300):
            raise ValueError("invalid_experiment_request")
        return value

    def _prepare(self, connection, principal, public, *, source_split=None):
        if source_split not in (None, 'tuning'):
            raise ValueError('invalid_experiment_source_projection')
        brain = _brain(principal)
        row, binding, contract_hash, refs = self.associations._authority(connection, principal,
            public["experiment_id"], public["contract_id"])
        grant = self.host._grant(connection, row)
        if grant["generation"] != public["expected_context_generation"]:
            raise IM.ConflictError("trial_context_grant_stale")
        associated = _association(connection, brain, public["case_set_id"])
        if associated is None:
            raise PermissionError("experiment_case_set_unassociated")
        IC._fields(associated, _FIELDS)
        if any(associated[key] != value for key, value in {
                "context_id": row["id"], "experiment_id": public["experiment_id"],
                "contract_id": public["contract_id"], "contract_hash": contract_hash,
                "grant_hash": row["grant_hash"]}.items()):
            raise PermissionError("experiment_case_set_unassociated")
        case_set = IC.CaseStore._row(connection, "improvement_case_sets", brain, public["case_set_id"])
        manifest = json.loads(case_set["manifest_json"])
        if (case_set["manifest_hash"] != associated["manifest_hash"] or IM._hash(manifest) != case_set["manifest_hash"]
                or type(manifest.get("cases")) is not list or not 1 <= len(manifest["cases"]) <= 1000):
            raise IM.ConflictError("experiment_case_set_changed")
        actual = [json.loads(item[0]) for item in connection.execute(
            "SELECT case_json FROM improvement_cases WHERE brain_id=? AND case_set_id=? ORDER BY id", (brain, public["case_set_id"]))]
        if sorted(actual, key=lambda item: item["id"]) != sorted(manifest["cases"], key=lambda item: item["id"]):
            raise IM.ConflictError("experiment_case_set_changed")
        targets = {target["id"]: target for target in binding["targets"]}
        if len(targets) != 1 or len(binding["targets"]) != 1 or next(iter(targets.values()))["kind"] != "skill":
            raise PermissionError("experiment_target_unavailable")
        target = next(iter(targets.values()))
        current = self.assets._target(connection, brain, target["id"])
        base_hash = self.admission._bundle(connection, brain, public["base_bundle_id"], targets, baseline=True, blobs={})
        contract = json.loads(IC.CaseStore._row(connection, "improvement_contracts", brain, public["contract_id"])["contract_json"])
        metric = contract["primary_metric"]
        if metric["direction"] != "higher" or metric["aggregation"] != "all_pass":
            raise PermissionError("experiment_endpoint_unsupported")
        value = definition({"version": 1, "experiment_id": public["experiment_id"], "context_id": row["id"],
            "target_id": target["id"], "base_revision_id": current["current_revision_id"], "base_hash": target["source_hash"],
            "base_generation": target["generation"], "base_bundle_id": public["base_bundle_id"], "base_bundle_hash": base_hash,
            "contract_id": public["contract_id"], "contract_hash": contract_hash, "case_set_id": public["case_set_id"],
            "case_set_hash": case_set["manifest_hash"], "baseline_context_hash": row["context_hash"], "binding_hash": row["binding_hash"],
            **{key: row[key] for key in ("engine_config_hash", "grant_hash", "scope_hash", "policy_version")},
            "context_generation": grant["generation"], "repeat_policy": {"kind": public["repeat_policy"],
                "repeats": 2 if public["repeat_policy"] == "pilot" else 1}, "timeout_seconds": public["timeout_seconds"],
            "endpoint": {"kind": "binary_all_pass", "criterion_id": metric["criterion_id"], "direction": "higher"},
            "decision_policy": {"id": "paired-skill-v1", "version": 1,
                "multiple_tests": 3 if public.get('candidate_policy') == 'two_proposals_and_one_compose' else 2},
            "evaluator": contract["evaluator"], "evidence_class": "technical"})
        self.records._bound_in(connection, brain, value, public["expected_context_generation"])
        for case in actual:
            if source_split is not None and case['split'] != source_split:
                continue
            authorize_case(connection, brain, {"case_set_id": public["case_set_id"], "case_id": case["id"],
                "pins": {"case_set_hash": case_set["manifest_hash"], "grant_hash": row["grant_hash"]}},
                binding["fixture_inventory"], blobs=self.blobs, baseline_content=binding["capture"]["baseline_context"]["content"])
        return value, binding, self.admission._registry(refs)

    def create(self, principal, request, *, event_key):
        brain = _brain(principal)
        public = self._create_request(request)
        IM.ensure(self.store)
        with closing(self.store._conn()) as connection:
            replay = self.assets._replay(connection, brain, event_key, "experiment_owner_create", public)
            if replay is not None:
                return replay
            prepared = self._prepare(connection, principal, public)
        self.host._snapshot_observe(principal, prepared[1])
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "experiment_owner_create", public)
            if replay is not None:
                return replay
            if self._prepare(connection, principal, public) != prepared:
                raise IM.ConflictError("experiment_authority_changed")
            inner_key = "experiment-definition-" + IM._hash([brain, event_key])
            result = self.records._create_in(connection, principal, prepared[0], public["expected_context_generation"], inner_key)
            self.host._snapshot_observe(principal, prepared[1])
            if self._prepare(connection, principal, public) != prepared:
                raise IM.ConflictError("experiment_authority_changed")
            self.host._snapshot_observe(principal, prepared[1])
            self.assets._event(connection, principal, event_key, "experiment_owner_create", public, result)
            return result

    def _state(self, connection, principal, experiment_id, expected_generation, *, unsealed, source_split=None):
        brain = _brain(principal)
        row = self.records._row(connection, brain, experiment_id)
        self.records._public(row)
        if row["generation"] != expected_generation or row["phase"] in (*TERMINAL_PHASES, "blocked", "stopping"):
            raise IM.ConflictError("experiment_state_stale")
        if unsealed and connection.execute("SELECT 1 FROM improvement_experiment_selections WHERE brain_id=? AND experiment_id=?",
                                           (brain, experiment_id)).fetchone():
            raise IM.ConflictError("experiment_sealed")
        value = definition(json.loads(row["definition_json"]))
        public = {key: value[key] for key in ("experiment_id", "contract_id", "case_set_id", "base_bundle_id", "timeout_seconds")}
        public.update(expected_context_generation=value["context_generation"], repeat_policy=value["repeat_policy"]["kind"])
        if value['decision_policy']['multiple_tests'] == 3:
            public['candidate_policy'] = 'two_proposals_and_one_compose'
        prepared = self._prepare(connection, principal, public, source_split=source_split)
        if prepared[0] != value:
            raise IM.ConflictError("experiment_definition_changed")
        return row, prepared

    def _arm(self, connection, principal, row, prepared, candidate_id, authority_id):
        """Check original immutable proposal AND one explicitly chosen live edit grant."""
        if row["phase"] == "preparing":
            raise IM.ConflictError("preparation_incomplete")
        brain, value = _brain(principal), prepared[0]
        candidate = self.authoring.records._row(connection, brain, candidate_id)
        if candidate['ordinal'] == 3 and value['decision_policy']['multiple_tests'] != 3:
            raise PermissionError('experiment_composed_arm_budget_unreserved')
        if any(candidate[key] != value[key] for key in
               ("experiment_id", "context_id", "target_id", "base_revision_id", "base_hash", "base_generation")):
            raise PermissionError("experiment_arm_scope_changed")
        state = self.authoring._state(connection, principal, row["id"], value["target_id"], value["base_revision_id"], value["base_hash"])
        observed, raw = self.authoring.observe(principal, state["target"])
        self.authoring.read_proposal(connection, principal, candidate, state, observed, raw)
        authority = self.authoring.records._authority(connection, brain, authority_id)
        if candidate['ordinal'] == 3 and authority['kind'] != 'exact_diff':
            raise PermissionError('experiment_composed_exact_diff_required')
        if authority["status"] != "active" or authority["generation"] != 1:
            raise PermissionError("experiment_arm_authority_unavailable")
        expected = {key: value[key] for key in ("context_id", "target_id", "base_revision_id", "base_hash", "base_generation", "context_generation")}
        expected.update(before_hash=value["base_hash"], source_authority_hash=observed["source_authority_hash"])
        if any(authority[key] != item for key, item in expected.items()):
            raise PermissionError("experiment_arm_authority_changed")
        if not ((authority["kind"] == "editable_region" and authority["id"] == candidate["authority_id"])
                or (authority["kind"] == "exact_diff" and authority["candidate_id"] == candidate["id"]
                    and authority["after_hash"] == candidate["content_hash"])):
            raise PermissionError("experiment_arm_authority_changed")
        envelope = {"version": 1, "experiment_id": row["id"], "definition_hash": row["definition_hash"],
            **{key: candidate[key] for key in ("context_id", "target_id", "base_revision_id", "base_hash", "base_generation",
                "ordinal", "content_hash", "byte_size", "patch_hash", "provenance_hash", "semantic_status", "owner_event_key")},
            "candidate_id": candidate["id"], "authority_id": authority["id"], "authority_generation": authority["generation"],
            "authority_hash": IM._hash(dict(authority)), "source_authority_hash": observed["source_authority_hash"]}
        self.authoring._guard(connection, principal, state, observed)
        if dict(self.authoring.records._authority(connection, brain, authority_id)) != dict(authority):
            raise IM.ConflictError("experiment_arm_authority_changed")
        return envelope

    def bind_arm(self, principal, experiment_id, candidate_id, authority_id, *, expected_generation, event_key):
        brain = _brain(principal)
        for identifier in (experiment_id, candidate_id, authority_id):
            _identifier(identifier)
        _generation(expected_generation)
        self.records._available()
        payload = {"experiment_id": experiment_id, "candidate_id": candidate_id, "authority_id": authority_id,
                   "expected_generation": expected_generation}
        with closing(self.store._conn()) as connection:
            replay = self.assets._replay(connection, brain, event_key, "experiment_bind_arm", payload)
            if replay is not None:
                return replay
            row, prepared = self._state(connection, principal, experiment_id, expected_generation, unsealed=True)
            envelope = self._arm(connection, principal, row, prepared, candidate_id, authority_id)
        self.host._snapshot_observe(principal, prepared[1])
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "experiment_bind_arm", payload)
            if replay is not None:
                return replay
            current, current_prepared = self._state(connection, principal, experiment_id, expected_generation, unsealed=True)
            if current_prepared != prepared or self._arm(connection, principal, current, current_prepared, candidate_id, authority_id) != envelope:
                raise IM.ConflictError("experiment_arm_changed")
            existing = connection.execute("SELECT * FROM improvement_experiment_arms WHERE experiment_id=? AND brain_id=? AND ordinal=?",
                                          (experiment_id, brain, envelope["ordinal"])).fetchone()
            if existing is not None:
                raise IM.ConflictError("experiment_arm_already_bound")
            connection.execute("INSERT INTO improvement_experiment_arms VALUES(?,?,?,?,?,?,?,?,?)", (
                experiment_id, brain, envelope["ordinal"], candidate_id, authority_id, envelope["authority_generation"],
                IM._hash(envelope), IM._json(envelope), time.time()))
            self.host._snapshot_observe(principal, prepared[1])
            if self._arm(connection, principal, current, current_prepared, candidate_id, authority_id) != envelope:
                raise IM.ConflictError("experiment_arm_changed")
            self.host._snapshot_observe(principal, prepared[1])
            connection.execute("UPDATE improvement_experiments SET phase='proposing',generation=generation+1,updated_at=? WHERE id=? AND brain_id=?",
                               (time.time(), experiment_id, brain))
            result = {"experiment_id": experiment_id, "candidate_id": candidate_id, "ordinal": envelope["ordinal"],
                "authority_id": authority_id, "envelope_hash": IM._hash(envelope), "generation": expected_generation + 1}
            self.assets._event(connection, principal, event_key, "experiment_bind_arm", payload, result)
            return result

    def _frozen_arm(self, connection, principal, row, prepared, ordinal):
        saved = connection.execute("SELECT * FROM improvement_experiment_arms WHERE experiment_id=? AND brain_id=? AND ordinal=?",
                                  (row["id"], _brain(principal), ordinal)).fetchone()
        if saved is None:
            raise PermissionError("experiment_arm_unavailable")
        envelope = self._arm(connection, principal, row, prepared, saved["candidate_id"], saved["authority_id"])
        if IM._json(envelope) != saved["envelope_json"] or IM._hash(envelope) != saved["envelope_hash"]:
            raise IM.ConflictError("experiment_arm_changed")
        return saved

    def freeze(self, principal, experiment_id, ordinal, kind, *, expected_generation, event_key):
        from improvement_experiment_protocol import comparison_matrix
        brain = _brain(principal)
        _identifier(experiment_id)
        _generation(expected_generation)
        if type(ordinal) is not int or ordinal not in (1, 2, 3) or type(kind) is not str or kind not in ("tuning", "final"):
            raise ValueError("invalid_comparison_request")
        self.records._available()
        payload = {"experiment_id": experiment_id, "ordinal": ordinal, "kind": kind, "expected_generation": expected_generation}
        with self.store._Tx(self.store) as connection:
            replay = self.assets._replay(connection, brain, event_key, "experiment_freeze", payload)
            if replay is not None:
                return replay
            row, prepared = self._state(connection, principal, experiment_id, expected_generation, unsealed=kind == "tuning")
            if row["phase"] == "preparing":
                raise IM.ConflictError("preparation_incomplete")
            if kind == "final":
                selection = connection.execute("SELECT * FROM improvement_experiment_selections WHERE brain_id=? AND experiment_id=?",
                                               (brain, experiment_id)).fetchone()
                if selection is None or selection["choice"] != "candidate" or selection["ordinal"] != ordinal:
                    raise PermissionError("experiment_final_selection_unavailable")
            arm = self._frozen_arm(connection, principal, row, prepared, ordinal)
            if connection.execute("SELECT 1 FROM improvement_comparisons WHERE experiment_id=? AND brain_id=? AND ordinal=? AND kind=?",
                                  (experiment_id, brain, ordinal, kind)).fetchone():
                raise IM.ConflictError("experiment_comparison_already_frozen")
            value = prepared[0]
            manifest = json.loads(IC.CaseStore._row(connection, "improvement_case_sets", brain, value["case_set_id"])["manifest_json"])
            splits = ("tuning",) if kind == "tuning" else ("qualification", "regression")
            cases = [case["id"] for case in manifest["cases"] if case["split"] in splits]
            matrix = comparison_matrix(value, arm["envelope_hash"], ordinal, kind, cases, manifest["seed"])
            raw = IM._json(matrix).encode("utf-8")
            self.host._snapshot_observe(principal, prepared[1])
            blob_hash = self.blobs.write(brain, raw)
            if blob_hash != IM._hash(matrix):
                raise IM.ConflictError("experiment_matrix_changed")
            current, current_prepared = self._state(connection, principal, experiment_id, expected_generation, unsealed=kind == "tuning")
            if current_prepared != prepared or dict(self._frozen_arm(connection, principal, current, current_prepared, ordinal)) != dict(arm):
                raise IM.ConflictError("experiment_authority_changed")
            self.host._snapshot_observe(principal, prepared[1])
            identifier = "icp_" + IM._hash([brain, experiment_id, ordinal, kind, blob_hash])[:32]
            connection.execute("INSERT INTO improvement_comparisons VALUES(?,?,?,?,?,?,?,?,?,?,?)", (
                identifier, brain, experiment_id, ordinal, kind, row["definition_hash"], arm["envelope_hash"],
                IM._hash(matrix), blob_hash, 2 * len(matrix["pairs"]), time.time()))
            connection.execute("UPDATE improvement_experiments SET phase=?,generation=generation+1,updated_at=? WHERE id=? AND brain_id=?",
                               ("probing" if kind == "tuning" else "qualifying", time.time(), experiment_id, brain))
            result = {"comparison_id": identifier, "experiment_id": experiment_id, "ordinal": ordinal, "kind": kind,
                "matrix_hash": blob_hash, "cell_count": 2 * len(matrix["pairs"]), "generation": expected_generation + 1}
            self.assets._event(connection, principal, event_key, "experiment_freeze", payload, result)
            return result

    def select(self, principal, experiment_id, choice, *, ordinal, expected_generation, event_key):
        brain = _brain(principal)
        require_product_store(self.assets, principal)
        _identifier(experiment_id)
        _generation(expected_generation)
        if (type(choice) is not str or choice not in ("keep_base", "candidate")
                or (choice == "keep_base" and ordinal is not None)
                or (choice == "candidate" and (type(ordinal) is not int or ordinal not in (1, 2, 3)))):
            raise ValueError("invalid_experiment_selection")
        self.records._available()
        payload = {"experiment_id": experiment_id, "choice": choice, "ordinal": ordinal, "expected_generation": expected_generation}
        if choice == "candidate":
            return self._select_candidate(principal, payload, event_key)
        with self.store._Tx(self.store) as connection:
            require_product_store(self.assets, principal, connection=connection)
            replay = self.assets._replay(connection, brain, event_key, "experiment_select", payload)
            if replay is not None:
                return replay
            row = self.records._row(connection, brain, experiment_id)
            self.records._public(row)
            if row["generation"] != expected_generation or row["phase"] in (*TERMINAL_PHASES, "stopping"):
                raise IM.ConflictError("experiment_state_stale")
            if connection.execute("SELECT 1 FROM improvement_experiment_selections WHERE brain_id=? AND experiment_id=?",
                                  (brain, experiment_id)).fetchone():
                raise IM.ConflictError("experiment_sealed")
            connection.execute("INSERT INTO improvement_experiment_selections VALUES(?,?,?,?,?,?,?,?)", (
                experiment_id, brain, choice, None, row["definition_hash"], "[]", event_key, time.time()))
            connection.execute("UPDATE improvement_experiments SET phase='stopping',generation=generation+1,stop_kind='completed',"
                "stop_event_key=?,stop_reason='keep_base',resume_from=NULL,blocker_json=NULL,blocker_hash=NULL,updated_at=? WHERE id=? AND brain_id=?",
                (event_key, time.time(), experiment_id, brain))
            result = self.records._public(self.records._row(connection, brain, experiment_id))
            self.assets._event(connection, principal, event_key, "experiment_select", payload, result)
            return result

    @staticmethod
    def _latest_tuning_report(connection, brain, experiment_id, ordinal):
        # Publication events are append-only and monotonic. Wall time can move
        # backwards, and republishing identical evidence reuses its report row.
        row = connection.execute("SELECT r.*,e.id AS publication_id,e.result_json AS publication_json,c.id AS expected_comparison_id "
            "FROM improvement_events e JOIN improvement_comparisons c ON c.id=json_extract(e.result_json,'$.comparison_id') "
            "AND c.brain_id=e.brain_id LEFT JOIN improvement_comparison_reports r "
            "ON r.id=json_extract(e.result_json,'$.report_id') AND r.brain_id=e.brain_id "
            "WHERE e.brain_id=? AND c.experiment_id=? AND c.ordinal=? AND c.kind='tuning' "
            "AND e.operation='comparison_report' ORDER BY e.id DESC LIMIT 1",
            (brain, experiment_id, ordinal)).fetchone()
        if row is None:
            raise PermissionError("experiment_selection_report_unavailable")
        published = json.loads(row["publication_json"])
        if (row["id"] is None or row["experiment_id"] != experiment_id or row["comparison_id"] != row["expected_comparison_id"]
                or published.get("report_hash") != row["report_hash"]):
            raise PermissionError("experiment_selection_report_unavailable")
        return dict(row)

    def _select_candidate(self, principal, payload, event_key):
        """Seal exact current tuning evidence; this grants no final execution."""
        from improvement_comparison_results import ComparisonResults
        brain, experiment_id = _brain(principal), payload["experiment_id"]
        generation, ordinal = payload["expected_generation"], payload["ordinal"]
        reports = ComparisonResults(self)
        with closing(self.store._conn()) as connection:
            require_product_store(self.assets, principal, connection=connection)
            replay = self.assets._replay(connection, brain, event_key, "experiment_select", payload)
            if replay is not None:
                return replay
            self._state(connection, principal, experiment_id, generation, unsealed=True)
            declared = tuple(row[0] for row in connection.execute("SELECT ordinal FROM improvement_experiment_arms "
                "WHERE brain_id=? AND experiment_id=? ORDER BY ordinal", (brain, experiment_id)))
            if ordinal not in declared:
                raise PermissionError("experiment_selection_report_unavailable")
            prepared = []
            for arm_ordinal in declared:
                saved = self._latest_tuning_report(connection, brain, experiment_id, arm_ordinal)
                metadata = reports._metadata(connection, brain, saved["comparison_id"])
                captured = reports._snapshot(connection, brain, metadata)
                prepared.append((arm_ordinal, saved, metadata, captured))
        validated = []
        for arm_ordinal, saved, metadata, captured in prepared:
            report = reports.read(principal, saved["id"])
            refs, summary = reports._evidence(principal, metadata, captured)
            policy = reports._policy(metadata["definition"])
            if (report["policy"] != policy or report["result_refs"] != refs or report["summary"] != summary
                    or not summary["complete"] or (arm_ordinal == ordinal and not summary["selection_supported"])
                    or report["arm_hash"] != metadata["comparison"]["arm_hash"] or IM._hash(report) != saved["report_hash"]):
                raise PermissionError("experiment_selection_report_unavailable")
            validated.append((arm_ordinal, saved, metadata, captured, policy))
        with self.store._Tx(self.store) as connection:
            require_product_store(self.assets, principal, connection=connection)
            replay = self.assets._replay(connection, brain, event_key, "experiment_select", payload)
            if replay is not None:
                return replay
            if tuple(row[0] for row in connection.execute("SELECT ordinal FROM improvement_experiment_arms "
                    "WHERE brain_id=? AND experiment_id=? ORDER BY ordinal", (brain, experiment_id))) != declared:
                raise IM.ConflictError("experiment_selection_evidence_changed")
            for arm_ordinal, saved, metadata, captured, policy in validated:
                if (self._latest_tuning_report(connection, brain, experiment_id, arm_ordinal) != saved
                        or reports._snapshot(connection, brain, metadata) != captured or reports._policy(metadata["definition"]) != policy):
                    raise IM.ConflictError("experiment_selection_evidence_changed")
            # Final full source/arm observation and SQL fences follow all slow
            # report/blob/policy work. No model, new claim or exposure is opened.
            for _, _, metadata, _, _ in validated:
                reports._guard(connection, principal, metadata, generation)
            require_product_store(self.assets, principal, connection=connection)
            evidence = [[saved["id"], saved["report_hash"]] for _, saved, _, _, _ in validated]
            connection.execute("INSERT INTO improvement_experiment_selections VALUES(?,?,?,?,?,?,?,?)", (
                experiment_id, brain, "candidate", ordinal, metadata["comparison"]["definition_hash"],
                IM._json(evidence), event_key, time.time()))
            connection.execute("UPDATE improvement_experiments SET phase='comparing',generation=generation+1,updated_at=? WHERE id=? AND brain_id=?",
                               (time.time(), experiment_id, brain))
            result = self.records._public(self.records._row(connection, brain, experiment_id))
            self.assets._event(connection, principal, event_key, "experiment_select", payload, result)
            return result
