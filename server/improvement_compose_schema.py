"""Schema8: one separately authorized composition, never a third proposal.

Historical schema1–7 literals stay frozen. Only four tables gain an explicit
compose enum/transport slot; their columns and existing rows are unchanged.
The official SQLite create/copy/drop/rename procedure runs in GoalStore's
serialized transaction, with foreign keys disabled only on that connection.
Composition output_hash names the existing operation result-report blob; a
publisher must separately authenticate its raw artifact and parsed decisions.
"""
from __future__ import annotations

import importlib
import re
from contextlib import closing, contextmanager


REBUILT = ('improvement_operations', 'improvement_skill_candidates',
           'improvement_experiment_arms', 'improvement_experiment_selections')
_NAME = re.compile(r'CREATE (?:UNIQUE )?(?:TABLE|INDEX|TRIGGER) "?([a-z_][a-z_0-9]*)"?')


def _name(statement):
    match = _NAME.match(statement)
    if not match:
        raise ValueError('invalid_compose_schema_statement')
    return match[1]


def _replace(statement, before, after):
    if statement.count(before) != 1:
        raise ValueError('historical_compose_schema_changed')
    return statement.replace(before, after)


def _immutable(tables):
    return tuple(f"CREATE TRIGGER {table}_{action.lower()} BEFORE {action} ON {table} "
                 "BEGIN SELECT RAISE(ABORT,'immutable_improvement_history'); END"
                 for table in tables for action in ('UPDATE', 'DELETE'))


def historical_statements():
    from improvement_store import _SCHEMA
    statements = [*_SCHEMA, *_immutable(('improvement_revisions', 'improvement_bundles',
                                        'improvement_bundle_assets', 'improvement_events'))]
    for module in ('case', 'trial', 'candidate', 'experiment', 'operation', 'view'):
        block = importlib.import_module('improvement_' + module + '_schema')
        statements.extend((*block.SCHEMA, *_immutable(block.IMMUTABLE)))
    return tuple(statements)


def overlay(statement):
    """Small, checked substitutions; no historical definition is modified."""
    name = _name(statement)
    if name in REBUILT:
        statement = _replace(statement, 'CREATE TABLE ' + name + '(', 'CREATE TABLE "' + name + '"(')
        if name == 'improvement_operations':
            statement = _replace(statement, "kind IN ('propose','repair','semantic')",
                                 "kind IN ('propose','repair','semantic','compose')")
            statement = _replace(statement,
                "OR (kind='semantic' AND role='semantic_reviewer' AND purpose='improve_evaluate' AND candidate_id IS NOT NULL))",
                "OR (kind='semantic' AND role='semantic_reviewer' AND purpose='improve_evaluate' AND candidate_id IS NOT NULL) "
                "OR (kind='compose' AND role='composer' AND purpose='improve_compose' AND candidate_id IS NULL))")
        else:
            statement = _replace(statement, 'ordinal IN (1,2)', 'ordinal IN (1,2,3)')
    elif name == 'improvement_operation_scope':
        statement = _replace(statement,
            "OR (NEW.kind='semantic' AND e.phase IN ('proposing','probing','comparing'))))",
            "OR (NEW.kind='semantic' AND e.phase IN ('proposing','probing','comparing')) "
            "OR (NEW.kind='compose' AND e.phase IN ('probing','comparing'))))")
    return statement


SCHEMA = (
    "CREATE TABLE improvement_compose_authorizations("
    "id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,experiment_id TEXT NOT NULL,context_id TEXT NOT NULL,"
    "definition_hash TEXT NOT NULL,input_hash TEXT NOT NULL,basis_hash TEXT NOT NULL,"
    "context_generation INTEGER NOT NULL CHECK(context_generation>0),policy_version INTEGER NOT NULL CHECK(policy_version>=0),"
    "actor TEXT NOT NULL,created_at REAL NOT NULL,UNIQUE(id,brain_id),"
    "FOREIGN KEY(experiment_id,brain_id) REFERENCES improvement_experiments(id,brain_id),"
    "FOREIGN KEY(context_id,brain_id) REFERENCES improvement_trial_contexts(id,brain_id))",
    "CREATE TABLE improvement_compose_grants("
    "authorization_id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,generation INTEGER NOT NULL,"
    "status TEXT NOT NULL CHECK(status IN ('active','revoked')),revoked_at REAL,"
    "CHECK((status='active' AND generation=1 AND revoked_at IS NULL) OR "
    "(status='revoked' AND generation=2 AND revoked_at IS NOT NULL)),"
    "FOREIGN KEY(authorization_id,brain_id) REFERENCES improvement_compose_authorizations(id,brain_id))",
    "CREATE TABLE improvement_compositions("
    "id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,experiment_id TEXT NOT NULL,operation_id TEXT NOT NULL,result_id TEXT NOT NULL,"
    "authorization_id TEXT NOT NULL,input_hash TEXT NOT NULL,basis_hash TEXT NOT NULL,output_hash TEXT NOT NULL,"
    "decisions_hash TEXT NOT NULL,decisions_blob_hash TEXT NOT NULL,outcome TEXT NOT NULL CHECK(outcome IN ('keep_base','candidate')),"
    "candidate_id TEXT,content_hash TEXT,patch_hash TEXT,provenance_hash TEXT,created_at REAL NOT NULL,"
    "UNIQUE(id,brain_id),UNIQUE(experiment_id,brain_id),UNIQUE(operation_id,brain_id),"
    "CHECK(decisions_hash=decisions_blob_hash),"
    "CHECK((outcome='keep_base' AND candidate_id IS NULL AND content_hash IS NULL AND patch_hash IS NULL AND provenance_hash IS NULL) "
    "OR (outcome='candidate' AND candidate_id IS NOT NULL AND content_hash IS NOT NULL AND patch_hash IS NOT NULL AND provenance_hash IS NOT NULL)),"
    "FOREIGN KEY(experiment_id,brain_id) REFERENCES improvement_experiments(id,brain_id),"
    "FOREIGN KEY(operation_id,brain_id) REFERENCES improvement_operations(id,brain_id),"
    "FOREIGN KEY(result_id,brain_id) REFERENCES improvement_operation_results(id,brain_id),"
    "FOREIGN KEY(authorization_id,brain_id) REFERENCES improvement_compose_authorizations(id,brain_id),"
    "FOREIGN KEY(candidate_id,brain_id) REFERENCES improvement_skill_candidates(id,brain_id) DEFERRABLE INITIALLY DEFERRED)",
    "CREATE UNIQUE INDEX improvement_one_composer ON improvement_operations(experiment_id,brain_id) WHERE kind='compose'",
    "CREATE TRIGGER improvement_compose_authorization_scope BEFORE INSERT ON improvement_compose_authorizations WHEN NOT EXISTS "
    "(SELECT 1 FROM improvement_experiments e JOIN improvement_trial_context_grants g ON g.context_id=e.context_id AND g.brain_id=e.brain_id "
    "WHERE e.id=NEW.experiment_id AND e.brain_id=NEW.brain_id AND e.context_id=NEW.context_id AND e.definition_hash=NEW.definition_hash "
    "AND e.phase IN ('probing','comparing') AND g.status='active' AND g.generation=NEW.context_generation "
    "AND NOT EXISTS(SELECT 1 FROM improvement_experiment_selections s WHERE s.experiment_id=e.id AND s.brain_id=e.brain_id) "
    "AND COALESCE((SELECT mode FROM improvement_policies WHERE brain_id=e.brain_id),'suggest')='suggest' "
    "AND COALESCE((SELECT version FROM improvement_policies WHERE brain_id=e.brain_id),0)=NEW.policy_version) "
    "BEGIN SELECT RAISE(ABORT,'compose_authorization_scope_mismatch'); END",
    "CREATE TRIGGER improvement_compose_grant_update BEFORE UPDATE ON improvement_compose_grants WHEN "
    "OLD.status!='active' OR NEW.status!='revoked' OR NEW.generation!=OLD.generation+1 OR NEW.authorization_id IS NOT OLD.authorization_id "
    "OR NEW.brain_id IS NOT OLD.brain_id OR NEW.revoked_at IS NULL "
    "BEGIN SELECT RAISE(ABORT,'immutable_compose_permission'); END",
    "CREATE TRIGGER improvement_compose_grant_delete BEFORE DELETE ON improvement_compose_grants "
    "BEGIN SELECT RAISE(ABORT,'immutable_compose_permission'); END",
    "CREATE TRIGGER improvement_composer_permission BEFORE INSERT ON improvement_operations WHEN NEW.kind='compose' AND NOT EXISTS "
    "(SELECT 1 FROM improvement_compose_authorizations a JOIN improvement_compose_grants g ON g.authorization_id=a.id AND g.brain_id=a.brain_id "
    "JOIN improvement_trial_context_grants cg ON cg.context_id=a.context_id AND cg.brain_id=a.brain_id "
    "WHERE a.id=json_extract(NEW.request_json,'$.compose_authorization_id') AND a.brain_id=NEW.brain_id "
    "AND a.experiment_id=NEW.experiment_id AND a.context_id=NEW.context_id AND a.input_hash=NEW.input_hash "
    "AND a.definition_hash=json_extract(NEW.request_json,'$.definition_hash') AND g.status='active' AND g.generation=1 "
    "AND cg.status='active' AND cg.generation=a.context_generation "
    "AND NOT EXISTS(SELECT 1 FROM improvement_experiment_selections s WHERE s.experiment_id=a.experiment_id AND s.brain_id=a.brain_id) "
    "AND COALESCE((SELECT mode FROM improvement_policies WHERE brain_id=a.brain_id),'suggest')='suggest' "
    "AND COALESCE((SELECT version FROM improvement_policies WHERE brain_id=a.brain_id),0)=a.policy_version) "
    "BEGIN SELECT RAISE(ABORT,'compose_permission_required'); END",
    "CREATE TRIGGER improvement_composition_scope BEFORE INSERT ON improvement_compositions WHEN NOT EXISTS "
    "(SELECT 1 FROM improvement_operations o JOIN improvement_operation_results r ON r.operation_id=o.id AND r.brain_id=o.brain_id "
    "JOIN improvement_operation_attempts t ON t.operation_id=o.id AND t.brain_id=o.brain_id AND t.attempt=o.attempt "
    "JOIN agent_calls c ON c.id=t.call_id JOIN improvement_compose_authorizations a ON a.id=NEW.authorization_id AND a.brain_id=o.brain_id "
    "JOIN improvement_compose_grants g ON g.authorization_id=a.id AND g.brain_id=a.brain_id "
    "JOIN improvement_trial_context_grants cg ON cg.context_id=a.context_id AND cg.brain_id=a.brain_id "
    "JOIN improvement_experiments e ON e.id=o.experiment_id AND e.brain_id=o.brain_id "
    "WHERE o.id=NEW.operation_id AND o.brain_id=NEW.brain_id AND o.experiment_id=NEW.experiment_id AND o.kind='compose' "
    "AND o.status='completed' AND r.id=NEW.result_id AND r.attempt=o.attempt AND r.blob_hash=NEW.output_hash "
    "AND t.status='completed' AND t.engine_at IS NOT NULL AND c.engine_at=t.engine_at AND c.status='ok' "
    "AND c.brain_id=o.brain_id AND c.purpose='improve_compose' AND c.attempt=t.attempt "
    "AND c.context_ref='improvement:'||o.experiment_id AND c.mirror_ref='improvement_operation:'||o.id "
    "AND c.reason_ref='improvement_operation:'||o.id||':attempt:'||t.attempt "
    "AND a.experiment_id=o.experiment_id AND a.context_id=o.context_id "
    "AND a.id=json_extract(o.request_json,'$.compose_authorization_id') AND a.input_hash=o.input_hash AND a.input_hash=NEW.input_hash "
    "AND a.basis_hash=NEW.basis_hash AND a.definition_hash=e.definition_hash AND e.phase IN ('probing','comparing') "
    "AND NOT EXISTS(SELECT 1 FROM improvement_experiment_selections s WHERE s.experiment_id=e.id AND s.brain_id=e.brain_id) "
    "AND g.status='active' AND g.generation=1 AND cg.status='active' AND cg.generation=a.context_generation "
    "AND COALESCE((SELECT mode FROM improvement_policies WHERE brain_id=a.brain_id),'suggest')='suggest' "
    "AND COALESCE((SELECT version FROM improvement_policies WHERE brain_id=a.brain_id),0)=a.policy_version) "
    "OR (NEW.candidate_id IS NOT NULL AND EXISTS(SELECT 1 FROM improvement_skill_candidates WHERE id=NEW.candidate_id)) "
    "BEGIN SELECT RAISE(ABORT,'composition_scope_mismatch'); END",
    "CREATE TRIGGER improvement_composed_candidate_scope BEFORE INSERT ON improvement_skill_candidates WHEN "
    "(NEW.ordinal=3 AND (NEW.authority_id IS NOT NULL OR NOT EXISTS "
    "(SELECT 1 FROM improvement_compositions p JOIN improvement_compose_authorizations a ON a.id=p.authorization_id AND a.brain_id=p.brain_id "
    "WHERE p.experiment_id=NEW.experiment_id AND p.brain_id=NEW.brain_id AND p.outcome='candidate' AND p.candidate_id=NEW.id "
    "AND a.context_id=NEW.context_id AND p.content_hash=NEW.content_hash AND p.patch_hash=NEW.patch_hash AND p.provenance_hash=NEW.provenance_hash))) "
    "OR (NEW.ordinal!=3 AND EXISTS(SELECT 1 FROM improvement_compositions WHERE candidate_id=NEW.id AND brain_id=NEW.brain_id)) "
    "BEGIN SELECT RAISE(ABORT,'composed_candidate_provenance_required'); END",
)
IMMUTABLE = ('improvement_compose_authorizations', 'improvement_compositions')


def statements():
    return tuple(overlay(sql) for sql in historical_statements()) + SCHEMA + _immutable(IMMUTABLE)


def _assert_statements(connection, expected, *, error):
    installed = {row['name']: ' '.join((row['sql'] or '').split()).rstrip(';')
                 for row in connection.execute("SELECT name,sql FROM sqlite_master WHERE name LIKE 'improvement_%'")}
    for sql in expected:
        if installed.get(_name(sql)) != ' '.join(sql.split()).rstrip(';'):
            raise error('compose_schema_changed')


def assert_historical(connection):
    from improvement_store import SchemaError
    expected = historical_statements()
    _assert_statements(connection, expected, error=SchemaError)
    # A private or unknown trigger may depend on a rebuilt table. Do not discard
    # or re-interpret it as known authority during migration.
    names = {_name(sql) for sql in expected}
    extras = connection.execute("SELECT name FROM sqlite_master WHERE type IN ('trigger','index') "
                                "AND sql IS NOT NULL AND tbl_name IN (?,?,?,?)", REBUILT)
    if any(row['name'] not in names for row in extras):
        raise SchemaError('unknown_compose_migration_dependency')


def assert_installed(connection):
    from improvement_store import ConflictError
    _assert_statements(connection, statements(), error=ConflictError)


def assert_roles_installed(connection):
    """Keep role authority scoped; view consumers retain their own diagnostics."""
    from improvement_store import ConflictError
    from improvement_operation_schema import SCHEMA as ROLES, IMMUTABLE as ROLE_HISTORY
    expected = tuple(overlay(sql) for sql in (*ROLES, *_immutable(ROLE_HISTORY)))
    _assert_statements(connection, expected + SCHEMA + _immutable(IMMUTABLE), error=ConflictError)


@contextmanager
def migration_transaction(store):
    transaction = store._Tx(store)
    # _Tx owns BEGIN IMMEDIATE/COMMIT/ROLLBACK. Closing also covers a failed
    # PRAGMA or BEGIN, for which Python does not enter _Tx.__exit__.
    with closing(transaction.c):
        transaction.c.execute('PRAGMA foreign_keys=OFF')
        with transaction as connection:
            yield connection


def _rebuild_table(connection, name, sql):
    temporary = name + '_compose_migration'
    connection.execute(_replace(sql, 'CREATE TABLE "' + name + '"(', 'CREATE TABLE ' + temporary + '('))
    columns = [row['name'] for row in connection.execute('PRAGMA table_info("' + name + '")')]
    projection = ','.join('"' + column + '"' for column in columns)
    connection.execute(f'INSERT INTO {temporary} ({projection}) SELECT {projection} FROM "{name}" ORDER BY rowid')
    connection.execute('DROP TABLE "' + name + '"')
    connection.execute(f'ALTER TABLE {temporary} RENAME TO "{name}"')


def migrate(connection):
    from improvement_store import SchemaError
    assert_historical(connection)
    if connection.execute('PRAGMA foreign_keys').fetchone()[0] != 0:
        raise SchemaError('compose_migration_requires_owned_connection')
    old = historical_statements()
    # SQLite parses triggers on other tables while renaming. Drop known guards
    # inside the same transaction and restore their exact definitions afterward.
    for sql in old:
        if sql.startswith('CREATE TRIGGER '):
            connection.execute('DROP TRIGGER ' + _name(sql))
    for name in REBUILT:
        sql = next(sql for sql in old if sql.startswith('CREATE TABLE ' + name + '('))
        _rebuild_table(connection, name, overlay(sql))
    for sql in old:
        if sql.startswith('CREATE TRIGGER ') or ('INDEX ' in sql and any(' ON ' + name + '(' in sql for name in REBUILT)):
            connection.execute(overlay(sql))
    for sql in (*SCHEMA, *_immutable(IMMUTABLE)):
        connection.execute(sql)
    assert_installed(connection)
    if connection.execute('PRAGMA foreign_key_check').fetchone():
        raise SchemaError('compose_migration_foreign_key_violation')
