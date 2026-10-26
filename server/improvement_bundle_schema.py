"""Version15 agent-skill bundles (M6). Add-only over version14.

- improvement_bundle_activations: one owner-applied pointer over a set of existing overlays for one assistant.
  Content columns never change; the state moves applying -> active|failed and active -> reverted|suspended.
- improvement_bundle_members: which overlay pointer belongs to which bundle; written once per member.
"""
from __future__ import annotations

SCHEMA = (
    "CREATE TABLE improvement_bundle_activations("
    "id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,agent_key TEXT NOT NULL,agent_slug TEXT NOT NULL,"
    "manifest_json TEXT NOT NULL,manifest_hash TEXT NOT NULL,"
    "state TEXT NOT NULL CHECK(state IN ('applying','active','failed','reverted','suspended')),reason TEXT NOT NULL,"
    "generation INTEGER NOT NULL CHECK(generation>0),actor TEXT NOT NULL,created_at REAL NOT NULL,updated_at REAL NOT NULL,"
    "UNIQUE(id,brain_id))",
    # One bundle in flight or live per assistant.
    "CREATE UNIQUE INDEX improvement_bundle_live ON improvement_bundle_activations(brain_id,agent_key) "
    "WHERE state IN ('applying','active')",
    "CREATE TRIGGER improvement_bundle_insert BEFORE INSERT ON improvement_bundle_activations "
    "WHEN NEW.state<>'applying' OR NEW.generation<>1 BEGIN SELECT RAISE(ABORT,'bundle_must_start_applying'); END",
    "CREATE TRIGGER improvement_bundle_update BEFORE UPDATE ON improvement_bundle_activations "
    "WHEN NOT ((OLD.state='applying' AND NEW.state IN ('applying','active','failed')) "
    "OR (OLD.state='active' AND NEW.state IN ('reverted','suspended'))) "
    "OR NEW.generation<>OLD.generation+1 OR NEW.id IS NOT OLD.id OR NEW.brain_id IS NOT OLD.brain_id "
    "OR NEW.agent_key IS NOT OLD.agent_key OR NEW.agent_slug IS NOT OLD.agent_slug "
    "OR NEW.manifest_json IS NOT OLD.manifest_json OR NEW.manifest_hash IS NOT OLD.manifest_hash "
    "OR NEW.actor IS NOT OLD.actor OR NEW.created_at IS NOT OLD.created_at "
    "BEGIN SELECT RAISE(ABORT,'bundle_transition_invalid'); END",
    "CREATE TRIGGER improvement_bundle_delete BEFORE DELETE ON improvement_bundle_activations "
    "BEGIN SELECT RAISE(ABORT,'immutable_improvement_history'); END",
    "CREATE TABLE improvement_bundle_members("
    "bundle_id TEXT NOT NULL,brain_id TEXT NOT NULL,member_key TEXT NOT NULL,"
    "kind TEXT NOT NULL CHECK(kind IN ('skill','procedure')),pointer_id TEXT NOT NULL,"
    "PRIMARY KEY(bundle_id,member_key),UNIQUE(brain_id,kind,pointer_id),"
    "FOREIGN KEY(bundle_id,brain_id) REFERENCES improvement_bundle_activations(id,brain_id))",
    "CREATE TRIGGER improvement_bundle_member_update BEFORE UPDATE ON improvement_bundle_members "
    "BEGIN SELECT RAISE(ABORT,'immutable_improvement_history'); END",
    "CREATE TRIGGER improvement_bundle_member_delete BEFORE DELETE ON improvement_bundle_members "
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
        raise SchemaError("unexpected_bundle_schema")


def assert_installed(connection) -> None:
    from improvement_store import SchemaError
    if _installed(connection) != dict(zip(_NAMES, SCHEMA)):
        raise SchemaError("bundle_schema_changed")


def migrate(connection) -> None:
    from improvement_store import SchemaError
    version = connection.execute("SELECT version FROM improvement_schema WHERE id=1").fetchone()
    if not connection.in_transaction or not version or version[0] != 14:
        raise SchemaError("bundle_migration_requires_owned_fourteen_transaction")
    assert_absent(connection)
    for statement in SCHEMA:
        connection.execute(statement)
    assert_installed(connection)
    if connection.execute("PRAGMA foreign_key_check").fetchone():
        raise SchemaError("bundle_migration_foreign_key_violation")
