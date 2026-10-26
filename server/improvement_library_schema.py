"""Version17 refinement ledger and imported candidates (M8). Add-only over version16.

- improvement_refinements: one row per refinement step of a failure family in a cycle; written once.
- improvement_imports: an untrusted package's items, kept as untested candidates; written once.
"""
from __future__ import annotations

SCHEMA = (
    "CREATE TABLE improvement_refinements("
    "id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,family TEXT NOT NULL,cycle TEXT NOT NULL,"
    "step INTEGER NOT NULL CHECK(step>0),changed INTEGER NOT NULL CHECK(changed IN (0,1)),"
    "evidence_ref TEXT NOT NULL,owner_assigned INTEGER NOT NULL CHECK(owner_assigned IN (0,1)),"
    "actor TEXT NOT NULL,created_at REAL NOT NULL,UNIQUE(id,brain_id),UNIQUE(brain_id,family,cycle,step))",
    "CREATE TABLE improvement_imports("
    "id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,package_hash TEXT NOT NULL,position INTEGER NOT NULL,"
    "item_json TEXT NOT NULL,actor TEXT NOT NULL,created_at REAL NOT NULL,"
    "UNIQUE(id,brain_id),UNIQUE(brain_id,package_hash,position))",
    *(f"CREATE TRIGGER {table}_{action.lower()} BEFORE {action} ON {table} "
      "BEGIN SELECT RAISE(ABORT,'immutable_improvement_history'); END"
      for table in ("improvement_refinements", "improvement_imports") for action in ("UPDATE", "DELETE")),
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
        raise SchemaError("unexpected_library_schema")


def assert_installed(connection) -> None:
    from improvement_store import SchemaError
    if _installed(connection) != dict(zip(_NAMES, SCHEMA)):
        raise SchemaError("library_schema_changed")


def migrate(connection) -> None:
    from improvement_store import SchemaError
    version = connection.execute("SELECT version FROM improvement_schema WHERE id=1").fetchone()
    if not connection.in_transaction or not version or version[0] != 16:
        raise SchemaError("library_migration_requires_owned_sixteen_transaction")
    assert_absent(connection)
    for statement in SCHEMA:
        connection.execute(statement)
    assert_installed(connection)
    if connection.execute("PRAGMA foreign_key_check").fetchone():
        raise SchemaError("library_migration_foreign_key_violation")
