"""Closed immutable experiment data; no host, trial, case-store or engine imports."""
from __future__ import annotations

import re
import json
import math

from improvement_store import _json, _hash

_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}")
_HASH = re.compile(r"[0-9a-f]{64}")
_DEFINITION = {"version", "experiment_id", "context_id", "target_id", "base_revision_id", "base_hash", "base_generation",
    "base_bundle_id", "base_bundle_hash", "contract_id", "contract_hash", "case_set_id", "case_set_hash",
    "baseline_context_hash", "binding_hash", "engine_config_hash", "grant_hash", "scope_hash", "policy_version",
    "context_generation", "repeat_policy", "timeout_seconds", "endpoint", "decision_policy", "evaluator", "evidence_class"}


def _fields(value, fields):
    if type(value) is not dict or set(value) != fields:
        raise ValueError("invalid_experiment_definition")


def definition(value):
    """Validate metadata shape only; it is not live source or execution authority."""
    import json
    value = json.loads(_json(value))
    _fields(value, _DEFINITION)
    if type(value["version"]) is not int or value["version"] != 1 or value["evidence_class"] != "technical":
        raise ValueError("unsupported_experiment_definition")
    for name in ("experiment_id", "context_id", "target_id", "base_revision_id", "base_bundle_id", "contract_id", "case_set_id"):
        if type(value[name]) is not str or not _ID.fullmatch(value[name]):
            raise ValueError("invalid_experiment_definition")
    for name in ("base_hash", "base_bundle_hash", "contract_hash", "case_set_hash", "baseline_context_hash", "binding_hash",
                 "engine_config_hash", "grant_hash", "scope_hash"):
        if type(value[name]) is not str or not _HASH.fullmatch(value[name]):
            raise ValueError("invalid_experiment_definition")
    for name, minimum in (("base_generation", 1), ("context_generation", 1), ("policy_version", 0)):
        if type(value[name]) is not int or not minimum <= value[name] < 2 ** 63:
            raise ValueError("invalid_experiment_generation")
    repeat = value["repeat_policy"]
    _fields(repeat, {"kind", "repeats"})
    if (type(repeat["kind"]) is not str or repeat["kind"] not in {"feasibility", "pilot"}
            or type(repeat["repeats"]) is not int or repeat["repeats"] != (1 if repeat["kind"] == "feasibility" else 2)):
        raise ValueError("unsupported_experiment_repeat_policy")
    if type(value["timeout_seconds"]) is not int or not 1 <= value["timeout_seconds"] <= 300:
        raise ValueError("invalid_experiment_timeout")
    endpoint = value["endpoint"]
    _fields(endpoint, {"kind", "criterion_id", "direction"})
    if (endpoint["kind"] != "binary_all_pass" or endpoint["direction"] != "higher"
            or type(endpoint["criterion_id"]) is not str or not _ID.fullmatch(endpoint["criterion_id"])):
        raise ValueError("unsupported_experiment_endpoint")
    policy = value["decision_policy"]
    _fields(policy, {"id", "version", "multiple_tests"})
    if (policy["id"] != "paired-skill-v1" or type(policy["version"]) is not int or policy["version"] != 1
            or type(policy["multiple_tests"]) is not int or not 1 <= policy["multiple_tests"] <= 1000):
        raise ValueError("unsupported_experiment_decision_policy")
    evaluator = value["evaluator"]
    _fields(evaluator, {"id", "version", "hash"})
    if (any(type(evaluator[key]) is not str or not 1 <= len(evaluator[key]) <= 128 for key in ("id", "version"))
            or type(evaluator["hash"]) is not str or not _HASH.fullmatch(evaluator["hash"])):
        raise ValueError("invalid_experiment_evaluator")
    if len(_json(value).encode("utf-8")) > 16384:
        raise ValueError("experiment_definition_too_large")
    return value


def comparison_matrix(value, arm_hash, ordinal, kind, case_ids, case_seed):
    """Complete metadata-only schedule; two complementary cells per canonical pair."""
    value = definition(value)
    if (type(arm_hash) is not str or not _HASH.fullmatch(arm_hash) or type(ordinal) is not int or ordinal not in (1, 2, 3)
            or ordinal == 3 and value['decision_policy']['multiple_tests'] < 3
            or type(kind) is not str or kind not in ("tuning", "final") or type(case_seed) is not int
            or type(case_ids) is not list or not 1 <= len(case_ids) <= 1000
            or any(type(item) is not str or not _ID.fullmatch(item) for item in case_ids)
            or len(set(case_ids)) != len(case_ids)):
        raise ValueError("invalid_comparison_matrix")
    seed = _hash(["javis-comparison-schedule-v1", _hash(value), arm_hash, ordinal, kind, case_seed])
    ordered = sorted(case_ids, key=lambda identifier: (_hash([seed, identifier]), identifier))
    repeats = value["repeat_policy"]["repeats"]
    pairs = []
    for index, case_id in enumerate(ordered):
        for repeat in range(1, repeats + 1):
            position = index * repeats + repeat - 1
            pairs.append({"pair_id": _hash(["javis-comparison-pair-v1", seed, case_id, repeat]),
                "case_id": case_id, "repeat": repeat,
                "first_variant": "baseline" if (int(seed[0], 16) + position) % 2 == 0 else "candidate"})
    matrix = {"version": 1, "experiment_id": value["experiment_id"], "definition_hash": _hash(value), "arm_hash": arm_hash,
        "ordinal": ordinal, "kind": kind, "case_set_id": value["case_set_id"], "case_set_hash": value["case_set_hash"],
        "repeat_policy": value["repeat_policy"], "schedule_seed": seed, "pairs": pairs}
    if len(_json(matrix).encode("utf-8")) > 1048576:
        raise ValueError("comparison_matrix_too_large")
    return matrix


def _freeze(value):
    try:
        return json.loads(_json(value))
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError("invalid_experiment_protocol") from error


def _id(value):
    if type(value) is not str or not _ID.fullmatch(value):
        raise ValueError("invalid_experiment_identity")


def _digest(value):
    if type(value) is not str or not _HASH.fullmatch(value):
        raise ValueError("invalid_experiment_hash")


def validate_lineage(value):
    value = _freeze(value)
    _fields(value, {"version", "context_id", "definition_hash", "comparison_id", "comparison_hash", "matrix_hash",
                    "arm_ordinal", "arm_hash", "candidate_id", "pair_id", "cell_position"})
    for key in ("context_id", "comparison_id", "candidate_id"):
        _id(value[key])
    for key in ("definition_hash", "comparison_hash", "matrix_hash", "arm_hash", "pair_id"):
        _digest(value[key])
    if (type(value["version"]) is not int or value["version"] != 1
            or type(value["arm_ordinal"]) is not int or value["arm_ordinal"] not in (1, 2, 3)
            or type(value["cell_position"]) is not int or not 0 <= value["cell_position"] < 4000):
        raise ValueError("invalid_experiment_lineage")
    return value


def validate_request_v2(value):
    """Pure shape/pin checks only; scoped SQL/blob/source authorization is separate."""
    request = _freeze(value)
    required = {"version", "pins", "case_set_id", "case_id", "variant", "repeat", "engine_config",
                "baseline_context_hash", "target_generations", "deadline_at", "lineage"}
    if type(request) is not dict or set(request) not in (required, required | {"qualification_id"}):
        raise ValueError("invalid_experiment_request")
    if (type(request["version"]) is not int or request["version"] != 2
            or type(request["variant"]) is not str or request["variant"] not in ("baseline", "candidate")
            or type(request["repeat"]) is not int or request["repeat"] not in (1, 2)):
        raise ValueError("invalid_experiment_request")
    for key in ("case_set_id", "case_id"):
        _id(request[key])
    if "qualification_id" in request:
        _id(request["qualification_id"])
    _digest(request["baseline_context_hash"])
    pins = request["pins"]
    _fields(pins, {"experiment_id", "base_bundle_hash", "candidate_bundle_hash", "contract_hash", "case_set_hash",
                   "engine_config_hash", "grant_hash", "scope_hash", "policy_version"})
    _id(pins["experiment_id"])
    for key in set(pins) - {"experiment_id", "policy_version"}:
        _digest(pins[key])
    if type(pins["policy_version"]) is not int or not 0 <= pins["policy_version"] < 2 ** 63:
        raise ValueError("invalid_experiment_policy")
    lineage = validate_lineage(request["lineage"])
    if lineage["arm_hash"] != pins["candidate_bundle_hash"]:
        raise ValueError("experiment_arm_pin_changed")
    engine = request["engine_config"]
    _fields(engine, {"version", "provider", "engine_id", "model", "reasoning", "cli_path", "cli_hash",
                     "cli_version", "sdk_version", "profile_version", "profile_hash"})
    if type(engine["version"]) is not int or engine["version"] != 1:
        raise ValueError("invalid_experiment_engine")
    if any(type(child) is not str or not 1 <= len(child) <= 4096 for key, child in engine.items() if key != "version"):
        raise ValueError("invalid_experiment_engine")
    for key in ("cli_hash", "profile_hash"):
        _digest(engine[key])
    if (engine["provider"] != "anthropic-cli" or engine["engine_id"] != "claude-sdk"
            or _hash(engine) != pins["engine_config_hash"]):
        raise ValueError("unsupported_experiment_engine")
    targets = request["target_generations"]
    if type(targets) is not dict or len(targets) != 1:
        raise ValueError("invalid_experiment_targets")
    for identifier, generation in targets.items():
        _id(identifier)
        if type(generation) is not int or not 1 <= generation < 2 ** 63:
            raise ValueError("invalid_experiment_targets")
    deadline = request["deadline_at"]
    if type(deadline) not in (int, float) or not math.isfinite(deadline) or deadline <= 0:
        raise ValueError("invalid_experiment_deadline")
    if len(_json(request).encode("utf-8")) > 65536:
        raise ValueError("experiment_request_too_large")
    return request


def matrix_cell(matrix, position):
    if (type(matrix) is not dict or type(matrix.get("pairs")) is not list or not 1 <= len(matrix["pairs"]) <= 2000
            or type(position) is not int or not 0 <= position < 2 * len(matrix["pairs"])):
        raise ValueError("invalid_comparison_cell")
    pair = _freeze(matrix["pairs"][position // 2])
    _fields(pair, {"pair_id", "case_id", "repeat", "first_variant"})
    _digest(pair["pair_id"])
    _id(pair["case_id"])
    if (type(pair["repeat"]) is not int or pair["repeat"] not in (1, 2)
            or type(pair["first_variant"]) is not str or pair["first_variant"] not in ("baseline", "candidate")):
        raise ValueError("invalid_comparison_cell")
    variant = pair["first_variant"] if position % 2 == 0 else ("candidate" if pair["first_variant"] == "baseline" else "baseline")
    return {key: pair[key] for key in ("pair_id", "case_id", "repeat")} | {"variant": variant}


def logical_key_v2(request):
    request = validate_request_v2(request)
    lineage = request["lineage"]
    return _hash(["improvement-trial-v2", request["pins"]["experiment_id"], lineage["comparison_id"],
        lineage["comparison_hash"], lineage["arm_hash"], lineage["pair_id"], lineage["cell_position"],
        request["case_set_id"], request["case_id"], request["repeat"], request["variant"]])


def comparison_hash(row):
    return _hash({key: row[key] for key in ("id", "experiment_id", "ordinal", "kind", "definition_hash", "arm_hash", "matrix_hash", "cell_count")})
