"""Version16 Team trial pins, Team trial reports and recipe transfers (M7). Add-only over version15.

- improvement_team_pins: an immutable snapshot of what a Team arm runs with (roster, roles, leader, member
  prompts incl. overlays on the team surface, models, acceptance contract).
- improvement_team_trials: one immutable report comparing two pins; it never touches production team work.
- improvement_transfers: a recipe proposed for another assistant, team or engine; always untested there.
"""
from __future__ import annotations

SCHEMA = (
    "CREATE TABLE improvement_team_pins("
    "id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,team_id TEXT NOT NULL,manifest_json TEXT NOT NULL,"
    "manifest_hash TEXT NOT NULL,actor TEXT NOT NULL,created_at REAL NOT NULL,"
    "UNIQUE(id,brain_id),UNIQUE(brain_id,manifest_hash))",
    "CREATE TABLE improvement_team_trials("
    "id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,baseline_pin_id TEXT NOT NULL,candidate_pin_id TEXT NOT NULL,"
    "change_json TEXT NOT NULL,report_json TEXT NOT NULL,"
    "verdict TEXT NOT NULL CHECK(verdict IN ('win','tie','loss','unknown','incomparable')),"
    "actor TEXT NOT NULL,created_at REAL NOT NULL,UNIQUE(id,brain_id),"
    "FOREIGN KEY(baseline_pin_id,brain_id) REFERENCES improvement_team_pins(id,brain_id),"
    "FOREIGN KEY(candidate_pin_id,brain_id) REFERENCES improvement_team_pins(id,brain_id))",
    "CREATE TABLE improvement_transfers("
    "id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,recipe_id TEXT NOT NULL,source_scope_hash TEXT NOT NULL,"
    "target_json TEXT NOT NULL,target_hash TEXT NOT NULL,actor TEXT NOT NULL,created_at REAL NOT NULL,"
    "UNIQUE(id,brain_id),UNIQUE(brain_id,recipe_id,target_hash),"
    "FOREIGN KEY(recipe_id,brain_id) REFERENCES improvement_recipes(id,brain_id))",
    "CREATE INDEX improvement_transfer_scope ON improvement_transfers(brain_id,target_hash)",
    *(f"CREATE TRIGGER {table}_{action.lower()} BEFORE {action} ON {table} "
      "BEGIN SELECT RAISE(ABORT,'immutable_improvement_history'); END"
      for table in ("improvement_team_pins", "improvement_team_trials", "improvement_transfers")
      for action in ("UPDATE", "DELETE")),
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
        raise SchemaError("unexpected_team_schema")


def assert_installed(connection) -> None:
    from improvement_store import SchemaError
    if _installed(connection) != dict(zip(_NAMES, SCHEMA)):
        raise SchemaError("team_schema_changed")


def migrate(connection) -> None:
    from improvement_store import SchemaError
    version = connection.execute("SELECT version FROM improvement_schema WHERE id=1").fetchone()
    if not connection.in_transaction or not version or version[0] != 15:
        raise SchemaError("team_migration_requires_owned_fifteen_transaction")
    assert_absent(connection)
    for statement in SCHEMA:
        connection.execute(statement)
    assert_installed(connection)
    if connection.execute("PRAGMA foreign_key_check").fetchone():
        raise SchemaError("team_migration_foreign_key_violation")
