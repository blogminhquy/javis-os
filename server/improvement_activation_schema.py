"""Version11 manual skill activations: one owner-chosen scope per live pointer.

An activation points one context (an assistant's own chat) at the exact bytes of
an authorized skill candidate. Content columns are immutable; only the state
moves, one generation at a time, and a terminal state never moves again.
Version10 definitions stay untouched; this step only adds tables.
"""
from __future__ import annotations

STATES = ("active", "reverted", "suspended")
EVIDENCE_LEVELS = ("manual_trial", "qualified")

SCHEMA = (
    "CREATE TABLE improvement_activations("
    "id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,target_id TEXT NOT NULL,candidate_id TEXT NOT NULL,"
    "experiment_id TEXT NOT NULL,canonical_ref TEXT NOT NULL,base_hash TEXT NOT NULL,content_hash TEXT NOT NULL,"
    "frontmatter_hash TEXT NOT NULL,selector_json TEXT NOT NULL,scope_hash TEXT NOT NULL,"
    "evidence_level TEXT NOT NULL CHECK(evidence_level IN ('manual_trial','qualified')),evidence_json TEXT NOT NULL,"
    "state TEXT NOT NULL CHECK(state IN ('active','reverted','suspended')),reason TEXT NOT NULL,"
    "generation INTEGER NOT NULL CHECK(generation>0),actor TEXT NOT NULL,created_at REAL NOT NULL,updated_at REAL NOT NULL,"
    "UNIQUE(id,brain_id),CHECK(content_hash<>base_hash),"
    "FOREIGN KEY(target_id,brain_id) REFERENCES improvement_targets(id,brain_id),"
    "FOREIGN KEY(candidate_id,brain_id) REFERENCES improvement_skill_candidates(id,brain_id))",
    # At most one live pointer per target and scope: a second apply must revert first.
    "CREATE UNIQUE INDEX improvement_activation_live ON improvement_activations(brain_id,target_id,scope_hash) "
    "WHERE state='active'",
    "CREATE INDEX improvement_activation_lookup ON improvement_activations(brain_id,canonical_ref,scope_hash,state)",
    "CREATE TRIGGER improvement_activation_insert BEFORE INSERT ON improvement_activations "
    "WHEN NEW.state<>'active' OR NEW.generation<>1 "
    "BEGIN SELECT RAISE(ABORT,'activation_must_start_active'); END",
    "CREATE TRIGGER improvement_activation_update BEFORE UPDATE ON improvement_activations "
    "WHEN OLD.state<>'active' OR NEW.state NOT IN ('reverted','suspended') OR NEW.generation<>OLD.generation+1 "
    "OR NEW.id IS NOT OLD.id OR NEW.brain_id IS NOT OLD.brain_id OR NEW.target_id IS NOT OLD.target_id "
    "OR NEW.candidate_id IS NOT OLD.candidate_id OR NEW.experiment_id IS NOT OLD.experiment_id "
    "OR NEW.canonical_ref IS NOT OLD.canonical_ref OR NEW.base_hash IS NOT OLD.base_hash "
    "OR NEW.content_hash IS NOT OLD.content_hash OR NEW.frontmatter_hash IS NOT OLD.frontmatter_hash "
    "OR NEW.selector_json IS NOT OLD.selector_json OR NEW.scope_hash IS NOT OLD.scope_hash "
    "OR NEW.evidence_level IS NOT OLD.evidence_level OR NEW.evidence_json IS NOT OLD.evidence_json "
    "OR NEW.actor IS NOT OLD.actor OR NEW.created_at IS NOT OLD.created_at "
    "BEGIN SELECT RAISE(ABORT,'activation_transition_invalid'); END",
    "CREATE TRIGGER improvement_activation_delete BEFORE DELETE ON improvement_activations "
    "BEGIN SELECT RAISE(ABORT,'immutable_improvement_history'); END",
)

_NAMES = ("improvement_activations", "improvement_activation_live", "improvement_activation_lookup",
          "improvement_activation_insert", "improvement_activation_update", "improvement_activation_delete")


def _installed(connection) -> dict:
    return {row[0]: row[1] for row in connection.execute(
        "SELECT name,sql FROM sqlite_master WHERE name IN (%s)" % ",".join("?" * len(_NAMES)), _NAMES)}


def assert_absent(connection) -> None:
    from improvement_store import SchemaError
    if _installed(connection):
        raise SchemaError("unexpected_activation_schema")


def assert_installed(connection) -> None:
    from improvement_store import SchemaError
    installed = _installed(connection)
    expected = {name: sql for name, sql in zip(_NAMES, SCHEMA)}
    if installed != expected:
        raise SchemaError("activation_schema_changed")


def migrate(connection) -> None:
    from improvement_store import SchemaError
    version = connection.execute("SELECT version FROM improvement_schema WHERE id=1").fetchone()
    if not connection.in_transaction or not version or version[0] != 10:
        raise SchemaError("activation_migration_requires_owned_ten_transaction")
    assert_absent(connection)
    for statement in SCHEMA:
        connection.execute(statement)
    assert_installed(connection)
    if connection.execute("PRAGMA foreign_key_check").fetchone():
        raise SchemaError("activation_migration_foreign_key_violation")
