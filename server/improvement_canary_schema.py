"""Version12 canary observation and conditional activation grants (M3). Add-only over version11.

- improvement_canaries: one partial allocation per activation; the session bucket decides the arm.
- improvement_canary_exposures: one row per (activation, session, message) where a covered skill read
  happened while the canary ran, for both arms, so the control group shares the eligibility.
- improvement_canary_verdicts: explicit owner verdicts on exposures; emoji reactions never land here.
- improvement_auto_scopes: owner grants that let a qualified candidate open a canary by itself in one
  target and scope; revoking stops new auto canaries and leaves accepted ones alone.
"""
from __future__ import annotations

SCHEMA = (
    "CREATE TABLE improvement_canaries("
    "activation_id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,allocation_pct INTEGER NOT NULL CHECK(allocation_pct BETWEEN 1 AND 99),"
    "salt TEXT NOT NULL,started_at REAL NOT NULL,state TEXT NOT NULL CHECK(state IN ('canary','promoted','ended')),"
    "reason TEXT NOT NULL,generation INTEGER NOT NULL CHECK(generation>0),updated_at REAL NOT NULL,"
    "UNIQUE(activation_id,brain_id),"
    "FOREIGN KEY(activation_id,brain_id) REFERENCES improvement_activations(id,brain_id))",
    "CREATE TRIGGER improvement_canary_insert BEFORE INSERT ON improvement_canaries "
    "WHEN NEW.state<>'canary' OR NEW.generation<>1 BEGIN SELECT RAISE(ABORT,'canary_must_start_running'); END",
    "CREATE TRIGGER improvement_canary_update BEFORE UPDATE ON improvement_canaries "
    "WHEN OLD.state<>'canary' OR NEW.state NOT IN ('promoted','ended') OR NEW.generation<>OLD.generation+1 "
    "OR NEW.activation_id IS NOT OLD.activation_id OR NEW.brain_id IS NOT OLD.brain_id "
    "OR NEW.allocation_pct IS NOT OLD.allocation_pct OR NEW.salt IS NOT OLD.salt OR NEW.started_at IS NOT OLD.started_at "
    "BEGIN SELECT RAISE(ABORT,'canary_transition_invalid'); END",
    "CREATE TRIGGER improvement_canary_delete BEFORE DELETE ON improvement_canaries "
    "BEGIN SELECT RAISE(ABORT,'immutable_improvement_history'); END",
    "CREATE TABLE improvement_canary_exposures("
    "activation_id TEXT NOT NULL,brain_id TEXT NOT NULL,session_id TEXT NOT NULL,message_id INTEGER NOT NULL CHECK(message_id>0),"
    "arm TEXT NOT NULL CHECK(arm IN ('canary','control')),content_hash TEXT NOT NULL,at REAL NOT NULL,"
    "PRIMARY KEY(activation_id,session_id,message_id),"
    "FOREIGN KEY(activation_id,brain_id) REFERENCES improvement_canaries(activation_id,brain_id))",
    "CREATE TRIGGER improvement_canary_exposure_update BEFORE UPDATE ON improvement_canary_exposures "
    "BEGIN SELECT RAISE(ABORT,'immutable_improvement_history'); END",
    "CREATE TRIGGER improvement_canary_exposure_delete BEFORE DELETE ON improvement_canary_exposures "
    "BEGIN SELECT RAISE(ABORT,'immutable_improvement_history'); END",
    "CREATE TABLE improvement_canary_verdicts("
    "activation_id TEXT NOT NULL,brain_id TEXT NOT NULL,session_id TEXT NOT NULL,message_id INTEGER NOT NULL,"
    "verdict TEXT NOT NULL CHECK(verdict IN ('pass','fail')),reason TEXT NOT NULL,actor TEXT NOT NULL,at REAL NOT NULL,"
    "PRIMARY KEY(activation_id,session_id,message_id),"
    "FOREIGN KEY(activation_id,session_id,message_id) REFERENCES "
    "improvement_canary_exposures(activation_id,session_id,message_id))",
    "CREATE TRIGGER improvement_canary_verdict_update BEFORE UPDATE ON improvement_canary_verdicts "
    "BEGIN SELECT RAISE(ABORT,'immutable_improvement_history'); END",
    "CREATE TRIGGER improvement_canary_verdict_delete BEFORE DELETE ON improvement_canary_verdicts "
    "BEGIN SELECT RAISE(ABORT,'immutable_improvement_history'); END",
    "CREATE TABLE improvement_auto_scopes("
    "id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,target_id TEXT NOT NULL,scope_hash TEXT NOT NULL,selector_json TEXT NOT NULL,"
    "surface TEXT NOT NULL CHECK(surface='skill_body'),allocation_pct INTEGER NOT NULL CHECK(allocation_pct BETWEEN 1 AND 99),"
    "status TEXT NOT NULL CHECK(status IN ('active','revoked')),generation INTEGER NOT NULL CHECK(generation>0),"
    "granted_by TEXT NOT NULL,granted_at REAL NOT NULL,revoked_at REAL,UNIQUE(id,brain_id),"
    "CHECK((status='active' AND generation=1 AND revoked_at IS NULL) OR (status='revoked' AND generation=2 AND revoked_at IS NOT NULL)),"
    "FOREIGN KEY(target_id,brain_id) REFERENCES improvement_targets(id,brain_id))",
    "CREATE UNIQUE INDEX improvement_auto_scope_live ON improvement_auto_scopes(brain_id,target_id,scope_hash) "
    "WHERE status='active'",
    "CREATE TRIGGER improvement_auto_scope_update BEFORE UPDATE ON improvement_auto_scopes "
    "WHEN OLD.status<>'active' OR NEW.status<>'revoked' OR NEW.id IS NOT OLD.id OR NEW.brain_id IS NOT OLD.brain_id "
    "OR NEW.target_id IS NOT OLD.target_id OR NEW.scope_hash IS NOT OLD.scope_hash OR NEW.selector_json IS NOT OLD.selector_json "
    "OR NEW.allocation_pct IS NOT OLD.allocation_pct OR NEW.granted_by IS NOT OLD.granted_by OR NEW.granted_at IS NOT OLD.granted_at "
    "BEGIN SELECT RAISE(ABORT,'auto_scope_transition_invalid'); END",
    "CREATE TRIGGER improvement_auto_scope_delete BEFORE DELETE ON improvement_auto_scopes "
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
        raise SchemaError("unexpected_canary_schema")


def assert_installed(connection) -> None:
    from improvement_store import SchemaError
    if _installed(connection) != dict(zip(_NAMES, SCHEMA)):
        raise SchemaError("canary_schema_changed")


def migrate(connection) -> None:
    from improvement_store import SchemaError
    version = connection.execute("SELECT version FROM improvement_schema WHERE id=1").fetchone()
    if not connection.in_transaction or not version or version[0] != 11:
        raise SchemaError("canary_migration_requires_owned_eleven_transaction")
    assert_absent(connection)
    for statement in SCHEMA:
        connection.execute(statement)
    assert_installed(connection)
    if connection.execute("PRAGMA foreign_key_check").fetchone():
        raise SchemaError("canary_migration_foreign_key_violation")
