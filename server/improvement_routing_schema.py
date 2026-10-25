"""Version13 routing candidates and description overlays (M4). Add-only over version12.

- improvement_routing_candidates: one immutable evaluated description candidate with its routing report.
- improvement_routing_overlays: an owner-applied description for the brain's main chat on API engines.
  Content columns never change; the state moves active -> reverted|suspended, one generation at a time.
"""
from __future__ import annotations

SCHEMA = (
    "CREATE TABLE improvement_routing_candidates("
    "id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,target_id TEXT NOT NULL,base_hash TEXT NOT NULL,description TEXT NOT NULL,"
    "content_hash TEXT NOT NULL,report_hash TEXT NOT NULL,report_blob TEXT NOT NULL,"
    "verdict TEXT NOT NULL CHECK(verdict IN ('eligible','inconclusive','rejected')),actor TEXT NOT NULL,created_at REAL NOT NULL,"
    "UNIQUE(id,brain_id),CHECK(content_hash<>base_hash),"
    "FOREIGN KEY(target_id,brain_id) REFERENCES improvement_targets(id,brain_id))",
    "CREATE TRIGGER improvement_routing_candidate_update BEFORE UPDATE ON improvement_routing_candidates "
    "BEGIN SELECT RAISE(ABORT,'immutable_improvement_history'); END",
    "CREATE TRIGGER improvement_routing_candidate_delete BEFORE DELETE ON improvement_routing_candidates "
    "BEGIN SELECT RAISE(ABORT,'immutable_improvement_history'); END",
    "CREATE TABLE improvement_routing_overlays("
    "id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,target_id TEXT NOT NULL,candidate_id TEXT NOT NULL,canonical_ref TEXT NOT NULL,"
    "base_hash TEXT NOT NULL,description TEXT NOT NULL,scope_hash TEXT NOT NULL,"
    "state TEXT NOT NULL CHECK(state IN ('active','reverted','suspended')),reason TEXT NOT NULL,"
    "generation INTEGER NOT NULL CHECK(generation>0),actor TEXT NOT NULL,created_at REAL NOT NULL,updated_at REAL NOT NULL,"
    "UNIQUE(id,brain_id),"
    "FOREIGN KEY(target_id,brain_id) REFERENCES improvement_targets(id,brain_id),"
    "FOREIGN KEY(candidate_id,brain_id) REFERENCES improvement_routing_candidates(id,brain_id))",
    "CREATE UNIQUE INDEX improvement_routing_overlay_live ON improvement_routing_overlays(brain_id,target_id,scope_hash) "
    "WHERE state='active'",
    "CREATE TRIGGER improvement_routing_overlay_insert BEFORE INSERT ON improvement_routing_overlays "
    "WHEN NEW.state<>'active' OR NEW.generation<>1 BEGIN SELECT RAISE(ABORT,'routing_overlay_must_start_active'); END",
    "CREATE TRIGGER improvement_routing_overlay_update BEFORE UPDATE ON improvement_routing_overlays "
    "WHEN OLD.state<>'active' OR NEW.state NOT IN ('reverted','suspended') OR NEW.generation<>OLD.generation+1 "
    "OR NEW.id IS NOT OLD.id OR NEW.brain_id IS NOT OLD.brain_id OR NEW.target_id IS NOT OLD.target_id "
    "OR NEW.candidate_id IS NOT OLD.candidate_id OR NEW.canonical_ref IS NOT OLD.canonical_ref "
    "OR NEW.base_hash IS NOT OLD.base_hash OR NEW.description IS NOT OLD.description "
    "OR NEW.scope_hash IS NOT OLD.scope_hash OR NEW.actor IS NOT OLD.actor OR NEW.created_at IS NOT OLD.created_at "
    "BEGIN SELECT RAISE(ABORT,'routing_overlay_transition_invalid'); END",
    "CREATE TRIGGER improvement_routing_overlay_delete BEFORE DELETE ON improvement_routing_overlays "
    "BEGIN SELECT RAISE(ABORT,'immutable_improvement_history'); END",
)


def _name(statement: str) -> str:
    words = statement.split()
    return (words[2] if words[1] in ("TABLE", "TRIGGER", "INDEX") else words[3]).split("(")[0]


_NAMES = tuple(_name(statement) for statement in SCHEMA)


def _installed(connection) -> dict:
    return {row[0]: row[1] for row in connection.execute(
        "SELECT name,sql FROM sqlite_master WHERE name IN (%s)" % ",".join("?" * len(_NAMES)), _NAMES)}


def assert_absent(connection) -> None:
    from improvement_store import SchemaError
    if _installed(connection):
        raise SchemaError("unexpected_routing_schema")


def assert_installed(connection) -> None:
    from improvement_store import SchemaError
    if _installed(connection) != dict(zip(_NAMES, SCHEMA)):
        raise SchemaError("routing_schema_changed")


def migrate(connection) -> None:
    from improvement_store import SchemaError
    version = connection.execute("SELECT version FROM improvement_schema WHERE id=1").fetchone()
    if not connection.in_transaction or not version or version[0] != 12:
        raise SchemaError("routing_migration_requires_owned_twelve_transaction")
    assert_absent(connection)
    for statement in SCHEMA:
        connection.execute(statement)
    assert_installed(connection)
    if connection.execute("PRAGMA foreign_key_check").fetchone():
        raise SchemaError("routing_migration_foreign_key_violation")
