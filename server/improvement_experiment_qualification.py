"""SQL-only qualification ownership; shares the existing global claim registry.

Ownership survives stopping, renaming and reclassifying cases. It is not a new
claim or exposure: the existing CaseStore tables remain the only such registry.
"""
from __future__ import annotations


def experiment_owned(connection, brain, case_set_id, pins):
    """Resolve exact ownership and aliases without decrypting private inputs."""
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                              "AND name='improvement_experiments'").fetchone():
        return False
    return connection.execute(
        "SELECT 1 FROM improvement_experiments e WHERE e.brain_id=? AND (e.id=? "
        "OR json_extract(e.definition_json,'$.case_set_id')=? "
        "OR json_extract(e.definition_json,'$.case_set_hash')=? "
        "OR EXISTS(SELECT 1 FROM improvement_case_families incoming "
        "JOIN improvement_case_families frozen ON frozen.brain_id=incoming.brain_id "
        "AND frozen.fingerprint=incoming.fingerprint "
        "WHERE incoming.brain_id=e.brain_id AND incoming.case_set_id=? "
        "AND frozen.case_set_id=json_extract(e.definition_json,'$.case_set_id') "
        "AND frozen.split='qualification')) LIMIT 1",
        (brain, pins.get("experiment_id"), case_set_id, pins.get("case_set_hash"), case_set_id)).fetchone() is not None


def require_legacy_qualification(connection, brain, case_set_id, pins):
    """Bare nine pins cannot establish final selected-arm/runtime readiness.

    B final execution remains unavailable until C semantic evidence and D's
    qualified effective view exist. A caller flag or a canonical bundle lookup
    cannot stand in for those prerequisites, even for the baseline counterpart.
    """
    if experiment_owned(connection, brain, case_set_id, pins):
        raise PermissionError("experiment_qualification_lineage_required")


def require_tuning_families(connection, brain, case_set_id):
    """Shared improver/view guard: consumed holdout aliases never become tuning."""
    if connection.execute("SELECT 1 FROM improvement_case_families t JOIN improvement_case_families h "
            "ON h.brain_id=t.brain_id AND h.fingerprint=t.fingerprint WHERE t.brain_id=? AND t.case_set_id=? "
            "AND t.split='tuning' AND h.split IN ('qualification','regression') LIMIT 1", (brain, case_set_id)).fetchone():
        raise PermissionError('improver_holdout_alias')
    if connection.execute("SELECT 1 FROM improvement_case_families t JOIN improvement_qualification_claims q "
            "ON q.brain_id=t.brain_id AND q.fingerprint=t.fingerprint WHERE t.brain_id=? AND t.case_set_id=? "
            "AND t.split='tuning' LIMIT 1", (brain, case_set_id)).fetchone():
        raise PermissionError('improver_holdout_alias')
