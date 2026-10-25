"""Complete paired-case arithmetic over host-verified immutable trial results.

This pure layer has no execution, dataset-acceptance or activation authority.
Repeats are within-case checks, never extra independent statistical samples.
"""
from __future__ import annotations

from math import comb

from improvement_store import _hash
from improvement_experiment_protocol import definition, comparison_matrix, matrix_cell
from improvement_qualification_records import require_product_store

_VERDICTS = {"pass", "fail", "unknown"}
_SPLITS = ("tuning", "qualification", "regression")


def _contract(value, contract):
    if type(contract) is not dict or _hash(contract) != value["contract_hash"]:
        raise ValueError("comparison_contract_changed")
    metric, criteria = contract.get("primary_metric"), contract.get("criteria")
    expected_metric = {"criterion_id": value["endpoint"]["criterion_id"], "direction": "higher", "aggregation": "all_pass"}
    if metric != expected_metric or type(criteria) is not list or not 1 <= len(criteria) <= 12:
        raise ValueError("comparison_endpoint_changed")
    identifiers, required = set(), set()
    for criterion in criteria:
        if (type(criterion) is not dict or type(criterion.get("id")) is not str or not criterion["id"]
                or len(criterion["id"]) > 128 or criterion["id"] in identifiers
                or criterion.get("category") not in ("mandatory", "business") or type(criterion.get("critical")) is not bool):
            raise ValueError("invalid_comparison_criteria")
        identifiers.add(criterion["id"])
        if criterion["category"] == "mandatory" or criterion["critical"]:
            required.add(criterion["id"])
    if metric["criterion_id"] not in identifiers:
        raise ValueError("comparison_endpoint_changed")
    return identifiers, required


def _cases(value, matrix, manifest):
    if (type(manifest) is not dict or _hash(manifest) != value["case_set_hash"]
            or type(manifest.get("cases")) is not list or not 1 <= len(manifest["cases"]) <= 1000):
        raise ValueError("comparison_case_set_changed")
    cases, families = {}, set()
    for case in manifest["cases"]:
        if (type(case) is not dict or type(case.get("id")) is not str or not case["id"] or case["id"] in cases
                or type(case.get("family_key")) is not str or not case["family_key"] or case["family_key"] in families
                or case.get("split") not in _SPLITS or type(case.get("fingerprints")) is not list
                or not case["fingerprints"] or any(type(token) is not str or not token for token in case["fingerprints"])
                or len(set(case["fingerprints"])) != len(case["fingerprints"])):
            raise ValueError("invalid_comparison_case")
        cases[case["id"]] = case
        families.add(case["family_key"])
    if type(matrix) is not dict or matrix.get("kind") not in ("tuning", "final"):
        raise ValueError("invalid_comparison_matrix")
    splits = ("tuning",) if matrix["kind"] == "tuning" else ("qualification", "regression")
    try:
        expected = comparison_matrix(value, matrix["arm_hash"], matrix["ordinal"], matrix["kind"],
            [case["id"] for case in cases.values() if case["split"] in splits], manifest["seed"])
    except (KeyError, TypeError) as error:
        raise ValueError("invalid_comparison_matrix") from error
    if matrix != expected:
        raise ValueError("comparison_matrix_changed")
    return {key: case for key, case in cases.items() if case["split"] in splits}


def _collapse(rows, identifiers):
    observed_failures = {identifier for identifier in identifiers if any(
        row is not None and row["integrity"] == "pass" and row["criteria"][identifier] == "fail" for row in rows)}
    # Product answers from an invalid execution never make a paired win/loss.
    if any(row is None or row["integrity"] != "pass" for row in rows):
        return {identifier: "unknown" for identifier in identifiers}, set(), False, observed_failures
    verdicts, unstable = {}, set()
    for identifier in identifiers:
        values = {row["criteria"][identifier] for row in rows}
        if "unknown" in values:
            verdicts[identifier] = "unknown"
        elif len(values) != 1:
            verdicts[identifier] = "unknown"
            unstable.add(identifier)
        else:
            verdicts[identifier] = next(iter(values))
    return verdicts, unstable, True, observed_failures


def _statistics(outcomes, multiple_tests):
    wins, losses = outcomes["win"], outcomes["loss"]
    n = wins + losses
    numerator = sum(comb(n, index) for index in range(wins, n + 1))
    denominator = 2 ** n
    return {"wins": wins, "losses": losses, "ties": outcomes["tie"], "unknown": outcomes["unknown"],
        "discordant": n, "tail_numerator": str(numerator), "tail_denominator": str(denominator),
        "p_value": numerator / denominator, "threshold_denominator": 20 * multiple_tests,
        "significant": n >= 5 and 20 * multiple_tests * numerator <= denominator}


def aggregate(value, matrix, contract, manifest, evidence):
    """Compare every expected cell; input rows are host projections, not HTTP data.

    Each position is either an explicit missing marker (None) or the exact
    integrity/criterion verdict projection of its pinned immutable result.
    Product criteria and native execution integrity are deliberately separate.
    """
    value = definition(value)
    identifiers, required = _contract(value, contract)
    cases = _cases(value, matrix, manifest)
    count = 2 * len(matrix["pairs"])
    if type(evidence) is not list or len(evidence) != count:
        raise ValueError("comparison_cell_coverage_changed")
    cells = {}
    integrity = {"pass": 0, "fail": 0, "unknown": 0, "missing": 0}
    for position, row in enumerate(evidence):
        cell = matrix_cell(matrix, position)
        if row is None:
            integrity["missing"] += 1
        else:
            if (type(row) is not dict or set(row) != {"position", "integrity", "criteria"}
                    or type(row["position"]) is not int or row["position"] != position
                    or type(row["integrity"]) is not str or row["integrity"] not in _VERDICTS
                    or type(row["criteria"]) is not dict or set(row["criteria"]) != identifiers
                    or any(type(verdict) is not str or verdict not in _VERDICTS for verdict in row["criteria"].values())):
                raise ValueError("invalid_comparison_cell_evidence")
            integrity[row["integrity"]] += 1
        cells[(cell["case_id"], cell["variant"], cell["repeat"])] = row
    repeats = value["repeat_policy"]["repeats"]
    complete = integrity["pass"] == count
    outcomes = {split: {"win": 0, "loss": 0, "tie": 0, "unknown": 0} for split in _SPLITS}
    required_losses, unstable_cases = 0, 0
    primary = value["endpoint"]["criterion_id"]
    for case_id, case in cases.items():
        variants, unstable, valid, failures = {}, {}, {}, {}
        for variant in ("baseline", "candidate"):
            variants[variant], unstable[variant], valid[variant], failures[variant] = _collapse(
                [cells[(case_id, variant, repeat)] for repeat in range(1, repeats + 1)], identifiers)
        case_complete = all(valid.values()) and all(verdict != "unknown" for rows in variants.values() for verdict in rows.values())
        complete = complete and case_complete
        unstable_cases += bool(unstable["baseline"] or unstable["candidate"])
        for criterion in required:
            if variants["baseline"][criterion] == "pass" and criterion in failures["candidate"]:
                required_losses += 1
        baseline, candidate = variants["baseline"][primary], variants["candidate"][primary]
        outcome = ("unknown" if "unknown" in (baseline, candidate) else "tie" if baseline == candidate
                   else "win" if candidate == "pass" else "loss")
        outcomes[case["split"]][outcome] += 1
    stats = _statistics(outcomes["qualification"], value["decision_policy"]["multiple_tests"])
    qualification = [case for case in cases.values() if case["split"] == "qualification"]
    # Uniqueness detects declared overlap, not scientific independence.
    declared_separate = True
    tokens = {token for case in manifest["cases"] if case["split"] != "qualification" for token in case["fingerprints"]}
    for case in qualification:
        current = set(case["fingerprints"])
        declared_separate = declared_separate and not bool(tokens & current)
        tokens.update(current)
    qualification_families = len({case["family_key"] for case in qualification})
    regression_count = sum(case["split"] == "regression" for case in cases.values())
    numeric_gate = bool(matrix["kind"] == "final" and value["repeat_policy"]["kind"] == "pilot"
        and complete and not required_losses and not outcomes["regression"]["loss"]
        and declared_separate and qualification_families >= 20 and regression_count >= 12
        and stats["significant"])
    tuning = outcomes["tuning"]
    selection_supported = bool(matrix["kind"] == "tuning" and complete and not required_losses and tuning["win"] > tuning["loss"])
    verdict = "rejected" if required_losses or outcomes["regression"]["loss"] else "eligible" if numeric_gate or selection_supported else "inconclusive"
    return {"version": 1, "complete": bool(complete), "expected_cells": count, "integrity": integrity,
        "stability": {"unstable_cases": unstable_cases}, "outcomes": outcomes, "required_loss_count": required_losses,
        "statistics": stats, "pilot": {"numeric_gate": numeric_gate, "qualification_family_count": qualification_families,
            "regression_count": regression_count, "declared_separation": declared_separate},
        "selection_supported": selection_supported, "mechanical_verdict": verdict, "evidence_class": value["evidence_class"],
        "business_eligibility": "unverified", "independence": "unverified"}


_NATIVE_CHECKS = frozenset({"materialization", "contract_projection", "workspace_binding", "worker_protocol", "installation",
    "tool_inventory", "prompt_installation", "asset_installation", "asset_observed_use", "actual_reasoning", "context_coverage",
    "fixture_inventory", "source_coverage", "actual_model", "session_binding", "side_effects", "completion", "event_coverage"})


def _summary(values):
    values = list(values)
    return "fail" if "fail" in values else "unknown" if not values or "unknown" in values else "pass"


def project_result(value, contract, request, trial_id, attempt, report):
    """Verify result identities and derive product versus execution verdicts.

    The scoped store separately verifies the exact encrypted result hash, linked
    trial and attempt. Missing native checks cannot become successful integrity.
    """
    from improvement_experiment_protocol import validate_request_v2
    from improvement_result_domain import NATIVE_GATES, require_product_report
    require_product_report(report)
    from improvement_view_trial_protocol import validate_request_v4
    import re
    value = definition(value)
    identifiers, _ = _contract(value, contract)
    view_runtime = type(request) is dict and type(request.get('version')) is int and request['version'] == 4
    request = validate_request_v4(request) if view_runtime else validate_request_v2(request)
    if (type(report) is not dict or type(report.get("version")) is not int or report["version"] != (4 if view_runtime else 2)
            or (view_runtime and report.get('effective_view') != request['view'])
            or report.get("trial_id") != trial_id or type(report.get("attempt")) is not int or report["attempt"] != attempt
            or report.get("request_hash") != _hash(request) or report.get("experiment_lineage") != request["lineage"]
            or report.get("contract_hash") != value["contract_hash"] or request["pins"]["contract_hash"] != value["contract_hash"]
            or report.get("execution_status") not in ("completed", "failed")
            or type(report.get("artifact_hash")) is not str or not re.fullmatch(r"[0-9a-f]{64}", report["artifact_hash"])):
        raise ValueError("comparison_result_identity_changed")
    evaluation = report.get("evaluation")
    if (type(evaluation) is not dict or type(evaluation.get("version")) is not int or evaluation["version"] != 1
            or evaluation.get("case_id") != request["case_id"] or evaluation.get("contract_hash") != value["contract_hash"]
            or evaluation.get("evaluator") != value["evaluator"] or evaluation.get("output_hash") != report["artifact_hash"]
            or type(evaluation.get("criteria")) is not list or len(evaluation["criteria"]) != len(identifiers)):
        raise ValueError("comparison_evaluation_changed")
    output = evaluation.get("output_manifest")
    if (type(output) is not list or len(output) != 1 or type(output[0]) is not dict
            or output[0].get("path") != contract["output"]["path"] or output[0].get("sha256") != report["artifact_hash"]
            or type(output[0].get("size")) is not int or not 0 <= output[0]["size"] <= 1048576):
        raise ValueError("comparison_output_changed")
    expected = {criterion["id"]: criterion for criterion in contract["criteria"]}
    criteria = {}
    for criterion in evaluation["criteria"]:
        if (type(criterion) is not dict or criterion.get("id") not in expected or criterion["id"] in criteria
                or type(criterion.get("verdict")) is not str or criterion["verdict"] not in _VERDICTS
                or type(criterion.get("critical")) is not bool
                or any(criterion.get(key) != expected[criterion["id"]][key] for key in ("kind", "category", "critical"))):
            raise ValueError("comparison_criterion_changed")
        criteria[criterion["id"]] = criterion["verdict"]
    mandatory = _summary(criteria[key] for key, row in expected.items() if row["category"] == "mandatory")
    business = _summary(criteria[key] for key, row in expected.items() if row["category"] == "business")
    if (evaluation.get("mandatory_verdict") != mandatory or evaluation.get("business_verdict") != business
            or evaluation.get("verdict") != _summary((mandatory, business))
            or evaluation.get("primary_metric") != {**contract["primary_metric"], "verdict": criteria[value["endpoint"]["criterion_id"]]}):
        raise ValueError("comparison_evaluation_summary_changed")
    checks = report.get("mandatory")
    if type(checks) is not list or len(checks) > 100:
        raise ValueError("invalid_comparison_execution_checks")
    native = {}
    for row in checks:
        if (type(row) is not dict or type(row.get("id")) is not str or row["id"] in native
                or type(row.get("verdict")) is not str or row["verdict"] not in _VERDICTS):
            raise ValueError("invalid_comparison_execution_checks")
        native[row["id"]] = row["verdict"]
    expected_checks = _NATIVE_CHECKS | (NATIVE_GATES if 'native_decisions' in report else set())
    if 'native_decisions' in report:
        decisions = report['native_decisions']
        if (type(decisions) is not list or len(decisions) != 4 or any(type(row) is not dict
                or set(row) != {'decision', 'durable_evidence_hash'} or row.get('decision') != 'allow'
                or type(row.get('durable_evidence_hash')) is not str
                or re.fullmatch('[0-9a-f]{64}', row['durable_evidence_hash']) is None for row in decisions)):
            raise ValueError('invalid_comparison_native_decisions')
    integrity = _summary(native.values()) if set(native) == expected_checks else "unknown"
    if report["execution_status"] != "completed":
        integrity = "fail"
    return {"integrity": integrity, "criteria": criteria}


class ComparisonResults:
    """Host-owned exact-result reports in the existing encrypted shared store.

    No result selector or verdict is accepted from owner JSON. Creation snapshots
    all expected cells; historical reads keep those exact references forever.
    """

    def __init__(self, plans):
        from improvement_comparison_plans import ExperimentPlans
        from improvement_trial_results import TrialResults
        if type(plans) is not ExperimentPlans:
            raise TypeError("concrete_comparison_plans_required")
        self.plans, self.assets, self.store, self.blobs = plans, plans.assets, plans.store, plans.blobs
        self.records = plans.records
        self.results = TrialResults(plans.admission.trials)

    @classmethod
    def from_existing(cls, assets):
        """Cold historical reader: no Host/Plans factory, migration or recovery."""
        import improvement_store as IM
        from improvement_experiments import ExperimentRecords
        from improvement_trials import TrialStore
        from improvement_trial_results import TrialResults
        if type(assets) is not IM.ImprovementStore:
            raise TypeError("concrete_comparison_assets_required")
        reader = cls.__new__(cls)
        reader.plans = None
        reader.assets, reader.store, reader.blobs = assets, assets.store, assets.blobs
        reader.records = ExperimentRecords(assets)
        reader.results = TrialResults(TrialStore(assets))
        return reader

    def _metadata(self, connection, brain, comparison_id):
        import json
        import improvement_store as IM
        import improvement_cases as IC
        from improvement_blobs import AssetUnavailable
        comparison = connection.execute("SELECT * FROM improvement_comparisons WHERE id=? AND brain_id=?",
                                        (comparison_id, brain)).fetchone()
        if comparison is None:
            raise PermissionError("comparison_unavailable")
        experiment = self.records._row(connection, brain, comparison["experiment_id"])
        self.records._public(experiment)
        value = definition(json.loads(experiment["definition_json"]))
        contract_row = IC.CaseStore._row(connection, "improvement_contracts", brain, value["contract_id"])
        contract = json.loads(contract_row["contract_json"])
        IC._contract(contract)
        case_set = IC.CaseStore._row(connection, "improvement_case_sets", brain, value["case_set_id"])
        manifest = json.loads(case_set["manifest_json"])
        arm = connection.execute("SELECT * FROM improvement_experiment_arms WHERE experiment_id=? AND brain_id=? AND ordinal=?",
                                 (experiment["id"], brain, comparison["ordinal"])).fetchone()
        if (arm is None or arm["envelope_hash"] != comparison["arm_hash"] or _hash(json.loads(arm["envelope_json"])) != arm["envelope_hash"]
                or comparison["definition_hash"] != experiment["definition_hash"] or contract_row["manifest_hash"] != value["contract_hash"]
                or case_set["manifest_hash"] != value["case_set_hash"]):
            raise AssetUnavailable("comparison_metadata_changed")
        actual = [json.loads(row[0]) for row in connection.execute(
            "SELECT case_json FROM improvement_cases WHERE brain_id=? AND case_set_id=? ORDER BY id", (brain, value["case_set_id"]))]
        if sorted(actual, key=lambda item: item["id"]) != sorted(manifest["cases"], key=lambda item: item["id"]):
            raise AssetUnavailable("comparison_case_membership_changed")
        raw = self.blobs.read(brain, comparison["matrix_blob_hash"])
        matrix = json.loads(raw)
        _contract(value, contract)
        _cases(value, matrix, manifest)
        if (len(raw) > 1048576 or raw != IM._json(matrix).encode("utf-8") or _hash(matrix) != comparison["matrix_hash"]
                or comparison["matrix_blob_hash"] != comparison["matrix_hash"] or comparison["cell_count"] != 2 * len(matrix["pairs"])
                or matrix["arm_hash"] != comparison["arm_hash"] or matrix["ordinal"] != comparison["ordinal"]
                or matrix["kind"] != comparison["kind"]):
            raise AssetUnavailable("comparison_matrix_changed")
        return {"comparison": dict(comparison), "definition": value, "contract": contract, "manifest": manifest,
                "matrix": matrix, "arm": json.loads(arm["envelope_json"])}

    def _guard(self, connection, principal, metadata, expected_generation):
        from improvement_experiment_lineage import current_fences
        from improvement_comparison_links import has_view_binding
        value, comparison = metadata["definition"], metadata["comparison"]
        view_runtime = has_view_binding(connection, principal.brain_id, comparison['id'])
        source = {'source_split': 'tuning'} if view_runtime else {}
        row, prepared = self.plans._state(connection, principal, value["experiment_id"], expected_generation,
                                          unsealed=comparison["kind"] == "tuning", **source)
        arm = self.plans._frozen_arm(connection, principal, row, prepared, comparison["ordinal"])
        if prepared[0] != value or arm["envelope_hash"] != comparison["arm_hash"]:
            raise ValueError("comparison_authority_changed")
        self.plans.host._snapshot_observe(principal, prepared[1])
        if view_runtime:
            from improvement_views import EffectiveViews
            views = self.plans.host._views
            if type(views) is not EffectiveViews or views.plans is not self.plans:
                raise PermissionError('view_resolver_unavailable')
            # Validates both frozen manifests and current meaning/dependencies,
            # followed by real source capture after all slow lineage I/O.
            if comparison['kind'] == 'final':
                from improvement_view_qualification import ViewQualification
                ViewQualification(self.plans, views).preview(connection, principal, comparison['id'],
                    expected_generation=expected_generation)
            else:
                views.load_current(principal, comparison['id'], 'baseline')
        current_fences(connection, principal.brain_id, metadata)

    def _snapshot(self, connection, brain, metadata):
        """SQL-only capture, including missing/nonterminal slots, for publication CAS."""
        import json
        from improvement_experiment_protocol import validate_request_v2, comparison_hash
        from improvement_view_trial_protocol import validate_request_v4
        from improvement_comparison_links import comparison_table
        from improvement_view_history import metadata as view_metadata, require_publication
        from improvement_blobs import AssetUnavailable
        comparison, value, matrix = metadata["comparison"], metadata["definition"], metadata["matrix"]
        table = comparison_table(connection, brain, comparison['id'])
        view_runtime = table == 'improvement_view_trial_links'
        binding = None
        if view_runtime:
            binding = view_metadata(connection, brain, comparison['id'])
            if binding is None:
                raise AssetUnavailable('comparison_views_unavailable')
            require_publication(connection, brain, binding, self.records._row(connection, brain, value['experiment_id'])['generation'])
        links = {row["cell_position"]: dict(row) for row in connection.execute(
            'SELECT * FROM ' + table + ' WHERE comparison_id=? AND brain_id=? LIMIT 4001', (comparison["id"], brain))}
        if any(type(position) is not int or not 0 <= position < comparison["cell_count"] for position in links):
            raise AssetUnavailable("comparison_cell_link_changed")
        captured = []
        for position in range(comparison["cell_count"]):
            link = links.get(position)
            if link is None:
                captured.append(None)
                continue
            trial = self.results.trials._row(connection, brain, link["trial_id"])
            raw_request = json.loads(trial['request_json'])
            request = validate_request_v4(raw_request) if view_runtime else validate_request_v2(raw_request)
            cell = matrix_cell(matrix, position)
            expected_pins = {key: value[key] for key in ("experiment_id", "base_bundle_hash", "contract_hash", "case_set_hash",
                "engine_config_hash", "grant_hash", "scope_hash", "policy_version")} | {"candidate_bundle_hash": comparison["arm_hash"]}
            expected_lineage = {"version": 1, "context_id": value["context_id"], "definition_hash": comparison["definition_hash"],
                "comparison_id": comparison["id"], "comparison_hash": comparison_hash(comparison), "matrix_hash": comparison["matrix_hash"],
                "arm_ordinal": comparison["ordinal"], "arm_hash": comparison["arm_hash"], "candidate_id": metadata["arm"]["candidate_id"],
                "pair_id": cell["pair_id"], "cell_position": position}
            if (trial["request_hash"] != _hash(request) or link["request_hash"] != trial["request_hash"]
                    or link["experiment_id"] != value["experiment_id"] or any(link[key] != item for key, item in cell.items())
                    or request["pins"] != expected_pins or request["lineage"] != expected_lineage
                    or request["case_set_id"] != value["case_set_id"] or any(request[key] != cell[key] for key in ("case_id", "variant", "repeat"))
                    or request["baseline_context_hash"] != value["baseline_context_hash"]
                    or request["target_generations"] != {value["target_id"]: value["base_generation"]}):
                raise AssetUnavailable("comparison_trial_lineage_changed")
            if view_runtime:
                descriptor = binding['views'][request['variant']]
                if (request['view'] != {'view_id': descriptor['view_id'], 'view_hash': descriptor['manifest_hash'],
                        'binding_hash': binding['binding_hash']}
                        or any(link[key] != child for key, child in request['view'].items())):
                    raise AssetUnavailable('comparison_trial_view_changed')
            attempt = connection.execute("SELECT * FROM improvement_trial_attempts WHERE trial_id=? AND brain_id=? AND attempt=?",
                                         (trial["id"], brain, trial["attempt"])).fetchone()
            call = None if attempt is None else connection.execute(
                "SELECT id,brain_id,purpose,reason_ref,context_ref,engine_at FROM agent_calls WHERE id=?", (attempt["call_id"],)).fetchone()
            captured.append({"trial": dict(trial), "request": request, "attempt": None if attempt is None else dict(attempt),
                             "call": None if call is None else dict(call)})
        return captured

    @staticmethod
    def _policy(value):
        import hashlib
        from pathlib import Path
        import improvement_trial_checks as checks
        import improvement_trial_results as results
        import improvement_experiment_protocol as protocol
        import improvement_view_trial_protocol as view_protocol
        import improvement_view_protocol as manifest_protocol
        return {"id": "complete-paired-results", "version": 1, "decision_policy": value["decision_policy"],
            "evaluator": value["evaluator"], "source_hash": _hash({name: hashlib.sha256(Path(path).read_bytes()).hexdigest()
                for name, path in {"comparison": __file__, "protocol": protocol.__file__, "checks": checks.__file__, "results": results.__file__,
                    'view_request': view_protocol.__file__, 'view_manifest': manifest_protocol.__file__}.items()})}

    def _evidence(self, principal, metadata, captured, *, refs=None):
        # Domain refusal is categorical, outside per-cell UNKNOWN recovery.
        require_product_store(self.assets, principal)
        import json
        import improvement_store as IM
        from improvement_blobs import AssetUnavailable
        from improvement_trials import TERMINAL
        from cryptography.fernet import InvalidToken
        rows, selected = [], []
        for position, item in enumerate(captured):
            ref = None if refs is None else refs[position]
            result_row = None
            if item is not None:
                trial, attempt = item["trial"], item["attempt"]
                if refs is not None and ref[1] is not None:
                    result_row = self._result_row(principal.brain_id, trial["id"], ref[1], ref[2])
                elif refs is None and (trial["status"] in TERMINAL and attempt is not None and attempt["status"] in TERMINAL
                        and attempt["engine_at"] is not None and attempt["result_json"]):
                    try:
                        pointer = json.loads(attempt["result_json"])
                        result_row = self._result_row(principal.brain_id, trial["id"], pointer["result_id"], pointer["result_hash"])
                        if result_row["attempt"] != attempt["attempt"] or result_row["blob_hash"] != pointer["blob_hash"]:
                            result_row = None
                    except (KeyError, TypeError, ValueError, PermissionError, AssetUnavailable):
                        result_row = None
            selected.append([position, None, None] if result_row is None else [position, result_row["id"], result_row["result_hash"]])
            evidence = None
            if result_row is not None:
                try:
                    report = self.results.read(principal, result_row["trial_id"], result_row["attempt"], result_id=result_row["id"])
                    if _hash(report) != result_row["result_hash"]:
                        raise AssetUnavailable("comparison_result_changed")
                    evidence = project_result(metadata["definition"], metadata["contract"], item["request"],
                        result_row["trial_id"], result_row["attempt"], report)
                    self._artifact(principal.brain_id, result_row, report)
                except (KeyError, TypeError, ValueError, PermissionError, AssetUnavailable, InvalidToken):
                    evidence = None
            rows.append(None if evidence is None else {"position": position, **evidence})
        if refs is not None and selected != refs:
            raise AssetUnavailable("comparison_result_reference_changed")
        summary = aggregate(metadata["definition"], metadata["matrix"], metadata["contract"], metadata["manifest"], rows)
        require_product_store(self.assets, principal)
        return selected, summary

    def _result_row(self, brain, trial_id, result_id, result_hash):
        from contextlib import closing
        from improvement_blobs import AssetUnavailable
        with closing(self.store._conn()) as connection:
            row = connection.execute("SELECT r.* FROM improvement_trial_results r "
                "JOIN improvement_trial_attempts a ON a.trial_id=r.trial_id AND a.brain_id=r.brain_id AND a.attempt=r.attempt "
                "JOIN agent_calls c ON c.id=a.call_id AND c.brain_id=r.brain_id "
                "JOIN improvement_trials t ON t.id=r.trial_id AND t.brain_id=r.brain_id "
                "WHERE r.id=? AND r.brain_id=? AND r.trial_id=? AND a.engine_at IS NOT NULL AND c.engine_at IS NOT NULL "
                "AND c.purpose='improve_probe' AND c.reason_ref=('improvement_trial:'||r.trial_id||':attempt:'||r.attempt) "
                "AND c.context_ref=('improvement:'||json_extract(t.request_json,'$.pins.experiment_id'))",
                (result_id, brain, trial_id)).fetchone()
        if row is None or row["result_hash"] != result_hash:
            raise AssetUnavailable("comparison_result_reference_changed")
        return dict(row)

    def _artifact(self, brain, result, report):
        from contextlib import closing
        from improvement_blobs import AssetUnavailable
        with closing(self.store._conn()) as connection:
            row = connection.execute("SELECT * FROM improvement_trial_artifacts WHERE brain_id=? AND trial_id=? AND attempt=?",
                                     (brain, result["trial_id"], result["attempt"])).fetchone()
        if row is None or row["content_hash"] != report["artifact_hash"]:
            raise AssetUnavailable("comparison_artifact_changed")
        raw = self.blobs.read(brain, row["content_hash"])
        if (len(raw) != row["byte_size"] or report["evaluation"]["output_manifest"] != [
                {"path": row["path"], "sha256": row["content_hash"], "size": row["byte_size"]}]):
            raise AssetUnavailable("comparison_artifact_changed")

    def create(self, principal, comparison_id, *, expected_generation, event_key):
        if self.plans is None:
            raise PermissionError("comparison_write_unavailable")
        import time
        from contextlib import closing
        import improvement_store as IM
        from improvement_experiments import _generation, _identifier
        _identifier(comparison_id)
        _generation(expected_generation)
        brain = IM._brain(principal)
        self.records._available()
        payload = {"comparison_id": comparison_id, "expected_generation": expected_generation}
        with closing(self.store._conn()) as connection:
            require_product_store(self.assets, principal, connection=connection)
            replay = self.assets._replay(connection, brain, event_key, "comparison_report", payload)
            if replay is not None:
                return replay
            metadata = self._metadata(connection, brain, comparison_id)
            self._guard(connection, principal, metadata, expected_generation)
            captured = self._snapshot(connection, brain, metadata)
        policy = self._policy(metadata["definition"])
        refs, summary = self._evidence(principal, metadata, captured)
        comparison = metadata["comparison"]
        from improvement_experiment_protocol import comparison_hash
        report = {"version": 1, "experiment_id": comparison["experiment_id"], "comparison_id": comparison_id,
            "definition_hash": comparison["definition_hash"], "comparison_hash": comparison_hash(comparison),
            "matrix_hash": comparison["matrix_hash"], "arm_hash": comparison["arm_hash"], "policy": policy,
            "result_refs": refs, "summary": summary}
        raw = IM._json(report).encode("utf-8")
        if len(raw) > 1048576:
            raise ValueError("comparison_report_too_large")
        blob = self.blobs.write(brain, raw)
        digest = _hash(report)
        if blob != digest:
            raise IM.ConflictError("comparison_report_hash_changed")
        with self.store._Tx(self.store) as connection:
            require_product_store(self.assets, principal, connection=connection)
            replay = self.assets._replay(connection, brain, event_key, "comparison_report", payload)
            if replay is not None:
                return replay
            if self._snapshot(connection, brain, metadata) != captured or self._policy(metadata["definition"]) != policy:
                raise IM.ConflictError("comparison_results_changed")
            # Policy hashing reads public source files. Final full observation
            # and SQL-only authority fences must follow that last slow I/O.
            self._guard(connection, principal, metadata, expected_generation)
            require_product_store(self.assets, principal, connection=connection)
            identifier = "icr_" + _hash([brain, comparison_id, digest])[:32]
            connection.execute("INSERT OR IGNORE INTO improvement_comparison_reports VALUES(?,?,?,?,?,?,?,?)", (
                identifier, brain, comparison["experiment_id"], comparison_id, digest, blob, _hash(policy), time.time()))
            connection.execute("UPDATE improvement_experiments SET generation=generation+1,updated_at=? WHERE id=? AND brain_id=?",
                               (time.time(), comparison["experiment_id"], brain))
            result = {"report_id": identifier, "report_hash": digest, "comparison_id": comparison_id,
                      "generation": expected_generation + 1, "complete": summary["complete"]}
            self.assets._event(connection, principal, event_key, "comparison_report", payload, result)
            return result

    def read(self, principal, report_id):
        import json
        from contextlib import closing
        import improvement_store as IM
        from improvement_blobs import AssetUnavailable
        from improvement_experiments import _identifier
        from improvement_experiment_protocol import comparison_hash
        _identifier(report_id)
        brain = IM._brain(principal)
        self.records._available()
        with closing(self.store._conn()) as connection:
            require_product_store(self.assets, principal, connection=connection)
            row = connection.execute("SELECT * FROM improvement_comparison_reports WHERE id=? AND brain_id=?", (report_id, brain)).fetchone()
            if row is None:
                raise PermissionError("comparison_report_unavailable")
            metadata = self._metadata(connection, brain, row["comparison_id"])
            raw = self.blobs.read(brain, row["blob_hash"])
            report = json.loads(raw)
            comparison = metadata["comparison"]
            if (len(raw) > 1048576 or raw != IM._json(report).encode("utf-8") or _hash(report) != row["report_hash"]
                    or row["blob_hash"] != row["report_hash"] or type(report) is not dict
                    or set(report) != {"version", "experiment_id", "comparison_id", "definition_hash", "comparison_hash",
                        "matrix_hash", "arm_hash", "policy", "result_refs", "summary"}
                    or type(report["version"]) is not int or report["version"] != 1
                    or any(report[key] != comparison[key] for key in ("experiment_id", "definition_hash", "matrix_hash", "arm_hash"))
                    or report["comparison_id"] != comparison["id"] or report["comparison_hash"] != comparison_hash(comparison)
                    or _hash(report["policy"]) != row["policy_hash"]):
                raise AssetUnavailable("comparison_report_changed")
            refs = report["result_refs"]
            if (type(refs) is not list or len(refs) != comparison["cell_count"]
                    or any(type(ref) is not list or len(ref) != 3 or type(ref[0]) is not int or ref[0] != index
                           or (ref[1] is None) != (ref[2] is None) for index, ref in enumerate(refs))):
                raise AssetUnavailable("comparison_report_references_changed")
            # A frozen report with no result references has no Trial evidence to
            # authenticate. Keep that exact missing/inconclusive history readable
            # even on metadata-only prototypes; this grants no current runtime.
            captured = [None] * comparison['cell_count'] if all(ref[1] is None for ref in refs) else self._snapshot(connection, brain, metadata)
        _, summary = self._evidence(principal, metadata, captured, refs=refs)
        if summary != report["summary"]:
            raise AssetUnavailable("comparison_report_evidence_changed")
        require_product_store(self.assets, principal)
        return report
