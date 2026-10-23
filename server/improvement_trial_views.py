"""Cold owner projections of stored evidence, without refreshing the usage index.

Usage is explicitly a historical result snapshot. Missing snapshots stay unknown;
GET does not ingest events or reconstruct telemetry. Private checker reasons and
evidence, answers, artifacts, baseline text and native paths never enter this view.
"""
from __future__ import annotations

import json
import math
from contextlib import closing

import improvement_store as IM
from evidence_store import redact
from improvement_blobs import AssetUnavailable
from improvement_trial_records import _brain
from improvement_trials import TrialStore

_VERDICTS = {"pass", "fail", "unknown"}
_MONEY = ("reported_usd", "estimated_usd", "subscription_equivalent_usd")


def _verdict(value):
    if type(value) is not str or value not in _VERDICTS:
        raise AssetUnavailable("trial_view_unavailable")
    return value


def _count(value):
    return value if type(value) is int and value >= 0 else None


def _usage(value=None):
    value = value if type(value) is dict else {}
    coverage = value.get("coverage") if type(value.get("coverage")) is dict else {}
    money = value.get("money") if type(value.get("money")) is dict else {}
    status = coverage.get("status")
    return {"origin": "stored_result" if value else "unavailable",
            **{key: _count(value.get(key)) for key in ("attempts", "requests", "tokens_in", "tokens_out")},
            "money": {"currency": "USD", **{key: money.get(key) if type(money.get(key)) in (int, float)
                      and math.isfinite(money[key]) and money[key] >= 0 else None for key in _MONEY}},
            "coverage": {"status": status if status in ("observed", "partial", "unknown") else "unknown",
                         **{key: coverage.get(key) is True for key in
                            ("tokens_complete", "money_complete", "requests_complete")}}}


def _checks(rows):
    if type(rows) is not list or len(rows) > 1000:
        raise AssetUnavailable("trial_view_unavailable")
    result = []
    for row in rows:
        if type(row) is not dict or type(row.get("id")) is not str or not 1 <= len(row["id"]) <= 128:
            raise AssetUnavailable("trial_view_unavailable")
        result.append({"id": row["id"], "verdict": _verdict(row.get("verdict"))})
    return result


def read_trial(assets, principal, identifier):
    brain = _brain(principal)
    if type(assets) is not IM.ImprovementStore:
        raise TypeError("concrete_trial_view_required")
    if IM._schema_version(assets.store) < 3:
        raise PermissionError("trial_record_unavailable")
    trials = TrialStore(assets)  # Constructors only retain paths/dependencies.
    with closing(assets.store._conn()) as connection:
        connection.execute("BEGIN")
        row = trials._row(connection, brain, identifier)
        current = trials._public(connection, row)
        if IM._hash(current["request"]) != row["request_hash"]:
            raise AssetUnavailable("trial_view_unavailable")
        if current['request'].get('version') == 4:
            from improvement_view_trial_protocol import validate_request_v4
            validated = validate_request_v4(current['request'])
            link = connection.execute('SELECT * FROM improvement_view_trial_links WHERE comparison_id=? AND brain_id=? AND cell_position=?',
                (validated['lineage']['comparison_id'], brain, validated['lineage']['cell_position'])).fetchone()
            if (link is None or link['trial_id'] != row['id'] or link['request_hash'] != row['request_hash']
                    or link['experiment_id'] != validated['pins']['experiment_id']
                    or any(link[key] != value for key, value in validated['view'].items())
                    or any(link[key] != validated[key] for key in ('case_id', 'repeat', 'variant'))
                    or link['pair_id'] != validated['lineage']['pair_id']):
                raise AssetUnavailable('trial_view_unavailable')
        if current["request"].get("version") == 3:
            from improvement_preparation_protocol import validate_preparation_request_v3
            validated = validate_preparation_request_v3(current["request"])
            link = connection.execute("SELECT * FROM improvement_preparation_trial_links "
                "WHERE preparation_id=? AND brain_id=? AND cell_position=?", (
                    validated["preparation"]["preparation_id"], brain, validated["preparation"]["cell_position"])).fetchone()
            if link is None or link["trial_id"] != row["id"] or link["request_hash"] != row["request_hash"]:
                raise AssetUnavailable("trial_view_unavailable")
        if current["request"].get("version") == 2:
            from improvement_experiment_protocol import validate_request_v2
            validated = validate_request_v2(current["request"])
            link = connection.execute("SELECT * FROM improvement_experiment_trial_links WHERE comparison_id=? AND brain_id=? AND cell_position=?",
                (validated["lineage"]["comparison_id"], brain, validated["lineage"]["cell_position"])).fetchone()
            if link is None or link["trial_id"] != row["id"] or link["request_hash"] != row["request_hash"]:
                raise AssetUnavailable("trial_view_unavailable")
        attempt = connection.execute("SELECT result_json FROM improvement_trial_attempts "
            "WHERE trial_id=? AND brain_id=? AND attempt=?", (identifier, brain, row["attempt"])).fetchone()
        if attempt is None:
            raise AssetUnavailable("trial_view_unavailable")
        pointer = json.loads(attempt["result_json"]) if attempt["result_json"] else None
        if pointer is not None:
            if type(pointer) is not dict or set(pointer) != {"result_id", "result_hash", "blob_hash"}:
                raise AssetUnavailable("trial_view_unavailable")
            immutable = connection.execute("SELECT result_hash,blob_hash FROM improvement_trial_results "
                "WHERE id=? AND trial_id=? AND brain_id=? AND attempt=?",
                (pointer["result_id"], identifier, brain, row["attempt"])).fetchone()
            if immutable is None:
                raise PermissionError("trial_result_unavailable")
            if any(immutable[key] != pointer[key] for key in ("result_hash", "blob_hash")):
                raise AssetUnavailable("trial_view_unavailable")
    request = current["request"]
    result = {key: current[key] for key in ("trial_id", "status", "generation", "attempt", "attempts")}
    result.update({key: request[key] for key in ("case_set_id", "case_id", "variant", "repeat")})
    result.update(experiment_id=request["pins"]["experiment_id"],
                  selection={key: request["engine_config"][key] for key in ("provider", "engine_id", "model", "reasoning")},
                  verdict=None, evaluation=None, execution_checks=[], usage=_usage())
    if request.get("version") == 2:
        result["experiment_lineage"] = request["lineage"]
    elif request.get('version') == 4:
        result['experiment_lineage'] = request['lineage']
        result['effective_view'] = request['view']
    elif request.get("version") == 3:
        result["preparation_lineage"] = request["preparation"]
    if pointer is not None:
        report = trials.read_result(principal, identifier, current["attempt"], result_id=pointer["result_id"])
        if IM._hash(report) != pointer["result_hash"]:
            raise AssetUnavailable("trial_view_unavailable")
        evaluation = report["evaluation"]
        result.update(verdict=_verdict(report["verdict"]),
                      artifact_hash=report["artifact_hash"], contract_hash=report["contract_hash"],
                      evaluation={**{key: _verdict(evaluation[key]) for key in
                                     ("verdict", "mandatory_verdict", "business_verdict")},
                                  "criteria": _checks(evaluation["criteria"])},
                      execution_checks=_checks(report["mandatory"]), usage=_usage(report.get("usage")))
    if redact(result) != result:
        raise AssetUnavailable("trial_view_unavailable")
    return result
