"""Improvement execution views reuse usage events; call records only reveal missing telemetry."""
from __future__ import annotations

import sqlite3

from usage_execution import _aggregate
import usage_index
import usage_store


def _execution_references(experiment_id, trial_id=None):
    path = usage_store._PATH.parent / "resonance.sqlite3"
    if not path.is_file():
        return set(), [], 0
    connection = None
    try:
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        where, args = "context_ref=? AND purpose='improve_probe' AND engine_at IS NOT NULL", ["improvement:" + experiment_id]
        if trial_id is not None:
            where += " AND mirror_ref=?"
            args.append("improvement_trial:" + trial_id)
        refs = set()
        for identifier, mirror, attempt in connection.execute("SELECT id,mirror_ref,attempt FROM agent_calls WHERE " + where, args):
            trial = mirror.split(":", 1)[1] if str(mirror).startswith("improvement_trial:") else "unscoped-call:" + str(identifier)
            refs.add((trial, attempt))
        return refs, ["resonance.sqlite3"], 0
    except (OSError, sqlite3.Error):
        return set(), ["resonance.sqlite3"], 1
    finally:
        if connection is not None:
            connection.close()


def trial_usage(experiment_id, trial_id=None):
    try:
        events, details = usage_index.improvement_events(experiment_id, trial_id)
        result = _aggregate(events, details, usage_store.improvement_telemetry_errors(experiment_id, trial_id))
    except Exception:
        events = []
        result = _aggregate([], telemetry_errors=1)
    references, sources, errors = _execution_references(experiment_id, trial_id)
    observed = {(event.get("execution", {}).get("trial_id"), event.get("execution", {}).get("attempt")) for event in events}
    missing = references - observed
    coverage = result["coverage"]
    coverage.update(execution_sources=sources, execution_reference_errors=errors)
    if missing or errors:
        result["attempts"] += len(missing)
        coverage["unobserved_attempts"] += len(missing)
        coverage.update(status="partial", tokens_complete=False, money_complete=False, requests_complete=False)
        result["requests"] = None
    result.update(experiment_id=experiment_id, trial_id=trial_id)
    return result


def _operation_references(experiment_id, operation_id):
    path = usage_store._PATH.parent / "resonance.sqlite3"
    if not path.is_file():
        return set(), [], 0
    connection = None
    try:
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        rows = connection.execute("SELECT attempt FROM agent_calls WHERE context_ref=? "
            "AND purpose IN ('improve_propose','improve_evaluate','improve_compose') AND engine_at IS NOT NULL AND mirror_ref=?",
            ("improvement:" + experiment_id, "improvement_operation:" + operation_id))
        return {("improvement_operation:" + operation_id, row[0]) for row in rows}, ["resonance.sqlite3"], 0
    except (OSError, sqlite3.Error):
        return set(), ["resonance.sqlite3"], 1
    finally:
        if connection is not None:
            connection.close()


def operation_usage(experiment_id, operation_id):
    """One genuine operation; never mix these roles into the legacy solver view."""
    if type(operation_id) is not str or not operation_id:
        raise ValueError("operation_usage_identity_required")
    try:
        events, details = usage_index.improvement_events(experiment_id, operation_id=operation_id)
        result = _aggregate(events, details, usage_store.operation_telemetry_errors(experiment_id, operation_id))
    except Exception:
        events = []
        result = _aggregate([], telemetry_errors=1)
    references, sources, errors = _operation_references(experiment_id, operation_id)
    observed = {(event.get("execution", {}).get("execution_id"), event.get("execution", {}).get("attempt")) for event in events}
    missing = references - observed
    coverage = result["coverage"]
    coverage.update(execution_sources=sources, execution_reference_errors=errors)
    if missing or errors:
        result["attempts"] += len(missing)
        coverage["unobserved_attempts"] += len(missing)
        coverage.update(status="partial", tokens_complete=False, money_complete=False, requests_complete=False)
        result["requests"] = None
    result.update(experiment_id=experiment_id, operation_id=operation_id)
    return result
