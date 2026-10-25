"""Version14 agent procedure candidates and scoped overlays (M5). Add-only over version13.

- improvement_agent_procedures: one immutable owner-reviewed procedure text for one assistant identity.
- improvement_agent_overlays: the owner-applied pointer for chosen surfaces (dm, team, kanban, workflow).
  Content columns never change; the state moves active -> reverted|suspended, one generation at a time.
"""
from __future__ import annotations

SCHEMA = (
    "CREATE TABLE improvement_agent_procedures("
    "id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,agent_key TEXT NOT NULL,agent_slug TEXT NOT NULL,"
    "text TEXT NOT NULL,text_hash TEXT NOT NULL,owner_rules_hash TEXT NOT NULL,source TEXT NOT NULL "
    "CHECK(source IN ('owner','learn','review')),actor TEXT NOT NULL,created_at REAL NOT NULL,"
    "UNIQUE(id,brain_id),UNIQUE(brain_id,agent_key,text_hash,owner_rules_hash))",
    "CREATE TRIGGER improvement_agent_procedure_update BEFORE UPDATE ON improvement_agent_procedures "
    "BEGIN SELECT RAISE(ABORT,'immutable_improvement_history'); END",
    "CREATE TRIGGER improvement_agent_procedure_delete BEFORE DELETE ON improvement_agent_procedures "
    "BEGIN SELECT RAISE(ABORT,'immutable_improvement_history'); END",
    "CREATE TABLE improvement_agent_overlays("
    "id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,agent_key TEXT NOT NULL,procedure_id TEXT NOT NULL,"
    "surfaces_json TEXT NOT NULL,owner_rules_hash TEXT NOT NULL,"
    "state TEXT NOT NULL CHECK(state IN ('active','reverted','suspended')),reason TEXT NOT NULL,"
    "generation INTEGER NOT NULL CHECK(generation>0),actor TEXT NOT NULL,created_at REAL NOT NULL,updated_at REAL NOT NULL,"
    "UNIQUE(id,brain_id),"
    "FOREIGN KEY(procedure_id,brain_id) REFERENCES improvement_agent_procedures(id,brain_id))",
    # One live procedure per assistant; changing surfaces or text means revert and apply again.
    "CREATE UNIQUE INDEX improvement_agent_overlay_live ON improvement_agent_overlays(brain_id,agent_key) "
    "WHERE state='active'",
    "CREATE TRIGGER improvement_agent_overlay_insert BEFORE INSERT ON improvement_agent_overlays "
    "WHEN NEW.state<>'active' OR NEW.generation<>1 BEGIN SELECT RAISE(ABORT,'agent_overlay_must_start_active'); END",
    "CREATE TRIGGER improvement_agent_overlay_update BEFORE UPDATE ON improvement_agent_overlays "
    "WHEN OLD.state<>'active' OR NEW.state NOT IN ('reverted','suspended') OR NEW.generation<>OLD.generation+1 "
    "OR NEW.id IS NOT OLD.id OR NEW.brain_id IS NOT OLD.brain_id OR NEW.agent_key IS NOT OLD.agent_key "
    "OR NEW.procedure_id IS NOT OLD.procedure_id OR NEW.surfaces_json IS NOT OLD.surfaces_json "
    "OR NEW.owner_rules_hash IS NOT OLD.owner_rules_hash OR NEW.actor IS NOT OLD.actor "
    "OR NEW.created_at IS NOT OLD.created_at "
    "BEGIN SELECT RAISE(ABORT,'agent_overlay_transition_invalid'); END",
    "CREATE TRIGGER improvement_agent_overlay_delete BEFORE DELETE ON improvement_agent_overlays "
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
        raise SchemaError("unexpected_agent_schema")


def assert_installed(connection) -> None:
    from improvement_store import SchemaError
    if _installed(connection) != dict(zip(_NAMES, SCHEMA)):
        raise SchemaError("agent_schema_changed")


def migrate(connection) -> None:
    from improvement_store import SchemaError
    version = connection.execute("SELECT version FROM improvement_schema WHERE id=1").fetchone()
    if not connection.in_transaction or not version or version[0] != 13:
        raise SchemaError("agent_migration_requires_owned_thirteen_transaction")
    assert_absent(connection)
    for statement in SCHEMA:
        connection.execute(statement)
    assert_installed(connection)
    if connection.execute("PRAGMA foreign_key_check").fetchone():
        raise SchemaError("agent_migration_foreign_key_violation")
