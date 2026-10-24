"""Schema9 immutable archive references and revocable availability metadata.

These relational pins grant no plaintext retrieval, source authority or grade.
Physical blob erasure and shorter source freshness limits belong to the host.
"""
from __future__ import annotations

from improvement_compose_schema import _immutable, _name


def _text(name):
    return f"{name} TEXT NOT NULL CHECK(typeof({name})='text' AND length({name})>0)"


def _hash(name):
    return (f"{name} TEXT NOT NULL CHECK(typeof({name})='text' AND length({name})=64 "
            f"AND instr({name},char(0))=0 AND {name} NOT GLOB '*[^0-9a-f]*')")


SCHEMA = (
    'CREATE TABLE improvement_recipes(' + ','.join((
        _text('id') + ' PRIMARY KEY', *(_text(name) for name in (
            'brain_id', 'experiment_id', 'context_id', 'target_id', 'base_revision_id', 'candidate_id')),
        "comparison_report_id TEXT CHECK(comparison_report_id IS NULL OR (typeof(comparison_report_id)='text' AND length(comparison_report_id)>0))",
        *(_hash(name) for name in ('manifest_hash', 'manifest_blob_hash', 'source_basis_hash', 'scope_hash',
                                  'engine_config_hash', 'owner_rule_hash', 'target_protected_hash', 'source_authority_hash')),
        "language TEXT NOT NULL CHECK(language IN ('vi','en'))",
        "verdict TEXT NOT NULL CHECK(verdict IN ('helped','hurt','no_observed_effect','confounded','untested'))",
        "checked_at REAL NOT NULL CHECK(typeof(checked_at) IN ('real','integer') AND checked_at>=0 AND checked_at<=created_at)",
        "expires_at REAL NOT NULL CHECK(typeof(expires_at) IN ('real','integer') AND expires_at>created_at AND expires_at<=created_at+2592000)",
        _text('actor'),
        "created_at REAL NOT NULL CHECK(typeof(created_at) IN ('real','integer') AND created_at>=0 AND created_at<9007199254740992)",
        'UNIQUE(id,brain_id)', 'UNIQUE(brain_id,manifest_hash)', 'CHECK(manifest_hash=manifest_blob_hash)',
        'FOREIGN KEY(experiment_id,brain_id) REFERENCES improvement_experiments(id,brain_id)',
        'FOREIGN KEY(context_id,brain_id) REFERENCES improvement_trial_contexts(id,brain_id)',
        'FOREIGN KEY(target_id,brain_id) REFERENCES improvement_targets(id,brain_id)',
        'FOREIGN KEY(base_revision_id,brain_id) REFERENCES improvement_revisions(id,brain_id)',
        'FOREIGN KEY(candidate_id,brain_id) REFERENCES improvement_skill_candidates(id,brain_id)',
        'FOREIGN KEY(comparison_report_id,brain_id) REFERENCES improvement_comparison_reports(id,brain_id)')) + ')',
    'CREATE TABLE improvement_recipe_trial_refs(' + ','.join((
        _text('recipe_id'), _text('brain_id'),
        "position INTEGER NOT NULL CHECK(typeof(position)='integer' AND position BETWEEN 0 AND 3999)",
        _text('trial_id'), "attempt INTEGER NOT NULL CHECK(typeof(attempt)='integer' AND attempt IN (1,2))",
        _text('result_id'), _hash('result_hash'), _hash('trace_hash'),
        "trace_count INTEGER NOT NULL CHECK(typeof(trace_count)='integer' AND trace_count>0)",
        'PRIMARY KEY(recipe_id,brain_id,position)', 'UNIQUE(recipe_id,brain_id,trial_id,attempt)',
        'FOREIGN KEY(recipe_id,brain_id) REFERENCES improvement_recipes(id,brain_id)',
        'FOREIGN KEY(trial_id,brain_id) REFERENCES improvement_trials(id,brain_id)',
        'FOREIGN KEY(trial_id,attempt) REFERENCES improvement_trial_attempts(trial_id,attempt)',
        'FOREIGN KEY(result_id) REFERENCES improvement_trial_results(id)')) + ')',
    'CREATE TABLE improvement_recipe_states(' + ','.join((
        _text('recipe_id') + ' PRIMARY KEY', _text('brain_id'),
        "status TEXT NOT NULL CHECK(status IN ('active','revoked','expired','superseded','erased'))",
        "generation INTEGER NOT NULL CHECK(typeof(generation)='integer' AND generation>0)",
        'reason TEXT', 'successor_id TEXT',
        "changed_at REAL NOT NULL CHECK(typeof(changed_at) IN ('real','integer') AND changed_at>=0 AND changed_at<9007199254740992)",
        'FOREIGN KEY(recipe_id,brain_id) REFERENCES improvement_recipes(id,brain_id)',
        'FOREIGN KEY(successor_id,brain_id) REFERENCES improvement_recipes(id,brain_id)')) + ')',
    'CREATE INDEX improvement_recipe_catalogue ON improvement_recipes(brain_id,scope_hash,target_id,engine_config_hash,language,expires_at,id)',
    'CREATE INDEX improvement_recipe_sources ON improvement_recipe_trial_refs(brain_id,trial_id,attempt)',
    "CREATE TRIGGER improvement_recipe_scope BEFORE INSERT ON improvement_recipes WHEN "
    "EXISTS(SELECT 1 FROM improvement_recipes WHERE id=NEW.id OR (brain_id=NEW.brain_id AND manifest_hash=NEW.manifest_hash)) OR NOT EXISTS "
    "(SELECT 1 FROM improvement_experiments e "
    "JOIN improvement_trial_contexts x ON x.id=e.context_id AND x.brain_id=e.brain_id "
    "JOIN improvement_skill_candidates c ON c.experiment_id=e.id AND c.brain_id=e.brain_id "
    "JOIN improvement_revisions b ON b.id=c.base_revision_id AND b.brain_id=c.brain_id "
    "JOIN improvement_targets t ON t.id=b.target_id AND t.brain_id=b.brain_id "
    "WHERE e.id=NEW.experiment_id AND e.brain_id=NEW.brain_id AND e.context_id=NEW.context_id AND e.target_id=NEW.target_id "
    "AND x.experiment_id=e.id AND x.scope_hash=NEW.scope_hash AND x.engine_config_hash=NEW.engine_config_hash "
    "AND c.id=NEW.candidate_id AND c.context_id=NEW.context_id AND c.target_id=NEW.target_id AND c.base_revision_id=NEW.base_revision_id "
    "AND b.target_id=NEW.target_id AND t.protected_hash=NEW.target_protected_hash "
    "AND (NEW.comparison_report_id IS NULL OR EXISTS "
    "(SELECT 1 FROM improvement_comparison_reports r JOIN improvement_comparisons p ON p.id=r.comparison_id AND p.brain_id=r.brain_id "
    "WHERE r.id=NEW.comparison_report_id AND r.brain_id=e.brain_id AND r.experiment_id=e.id "
    "AND p.experiment_id=e.id AND p.ordinal=c.ordinal))) "
    "BEGIN SELECT RAISE(ABORT,'recipe_scope_mismatch'); END",
    "CREATE TRIGGER improvement_recipe_trial_scope BEFORE INSERT ON improvement_recipe_trial_refs WHEN "
    "EXISTS(SELECT 1 FROM improvement_recipe_trial_refs WHERE recipe_id=NEW.recipe_id AND brain_id=NEW.brain_id "
    "AND (position=NEW.position OR (trial_id=NEW.trial_id AND attempt=NEW.attempt))) OR "
    "EXISTS(SELECT 1 FROM improvement_recipe_states WHERE recipe_id=NEW.recipe_id) OR NOT EXISTS "
    "(SELECT 1 FROM improvement_recipes p JOIN improvement_trial_results r ON r.id=NEW.result_id "
    "JOIN improvement_trials t ON t.id=r.trial_id AND t.brain_id=r.brain_id "
    "JOIN improvement_trial_attempts a ON a.trial_id=t.id AND a.brain_id=t.brain_id AND a.attempt=r.attempt "
    "WHERE p.id=NEW.recipe_id AND p.brain_id=NEW.brain_id AND r.brain_id=p.brain_id AND r.trial_id=NEW.trial_id "
    "AND r.attempt=NEW.attempt AND r.result_hash=NEW.result_hash AND r.blob_hash=NEW.result_hash "
    "AND (EXISTS(SELECT 1 FROM improvement_preparation_trial_links l "
    "JOIN improvement_preparations h ON h.id=l.preparation_id AND h.brain_id=l.brain_id "
    "WHERE l.trial_id=t.id AND l.brain_id=p.brain_id AND l.experiment_id=p.experiment_id "
    "AND h.experiment_id=p.experiment_id AND h.context_id=p.context_id) OR "
    "EXISTS(SELECT 1 FROM improvement_experiment_trial_links l "
    "JOIN improvement_experiments e ON e.id=l.experiment_id AND e.brain_id=l.brain_id "
    "JOIN improvement_comparisons c ON c.id=l.comparison_id AND c.brain_id=l.brain_id "
    "WHERE l.trial_id=t.id AND l.brain_id=p.brain_id AND l.experiment_id=p.experiment_id "
    "AND e.context_id=p.context_id AND c.experiment_id=p.experiment_id))) "
    "BEGIN SELECT RAISE(ABORT,'recipe_trial_scope_mismatch'); END",
    "CREATE TRIGGER improvement_recipe_states_insert BEFORE INSERT ON improvement_recipe_states WHEN "
    "EXISTS(SELECT 1 FROM improvement_recipe_states WHERE recipe_id=NEW.recipe_id) OR NOT EXISTS "
    "(SELECT 1 FROM improvement_recipes p WHERE p.id=NEW.recipe_id AND p.brain_id=NEW.brain_id "
    "AND NEW.status='active' AND NEW.generation=1 AND NEW.reason IS NULL AND NEW.successor_id IS NULL AND NEW.changed_at=p.created_at) "
    "BEGIN SELECT RAISE(ABORT,'invalid_recipe_initial_state'); END",
    "CREATE TRIGGER improvement_recipe_states_update BEFORE UPDATE ON improvement_recipe_states WHEN NOT EXISTS "
    "(SELECT 1 FROM improvement_recipes p WHERE p.id=OLD.recipe_id AND p.brain_id=OLD.brain_id "
    "AND NEW.recipe_id IS OLD.recipe_id AND NEW.brain_id IS OLD.brain_id AND NEW.generation=OLD.generation+1 AND NEW.changed_at>=OLD.changed_at "
    "AND ((OLD.status='active' AND ((NEW.status='revoked' AND NEW.reason='owner_revoked' AND NEW.successor_id IS NULL) "
    "OR (NEW.status='expired' AND NEW.reason='retention_expired' AND NEW.changed_at>=p.expires_at AND NEW.successor_id IS NULL) "
    "OR (NEW.status='superseded' AND NEW.reason='superseded' AND NEW.successor_id!=p.id AND EXISTS "
    "(SELECT 1 FROM improvement_recipes s JOIN improvement_recipe_states g ON g.recipe_id=s.id AND g.brain_id=s.brain_id "
    "WHERE s.id=NEW.successor_id AND s.brain_id=p.brain_id AND g.status='active' AND s.target_id=p.target_id "
    "AND s.scope_hash=p.scope_hash AND s.engine_config_hash=p.engine_config_hash AND s.language=p.language AND s.owner_rule_hash=p.owner_rule_hash)))) "
    "OR (OLD.status IN ('active','revoked','expired','superseded') AND NEW.status='erased' "
    "AND NEW.reason IN ('source_erased','owner_erased') AND NEW.successor_id IS NULL))) "
    "BEGIN SELECT RAISE(ABORT,'immutable_recipe_availability'); END",
    "CREATE TRIGGER improvement_recipe_states_delete BEFORE DELETE ON improvement_recipe_states "
    "BEGIN SELECT RAISE(ABORT,'immutable_recipe_availability'); END",
)

IMMUTABLE = ('improvement_recipes', 'improvement_recipe_trial_refs')


def statements() -> tuple[str, ...]:
    return SCHEMA + _immutable(IMMUTABLE)


def _assert_absent(connection):
    from improvement_store import SchemaError
    if connection.execute("SELECT 1 FROM sqlite_master WHERE lower(name) GLOB 'improvement_recipe*' OR lower(tbl_name) GLOB 'improvement_recipe*'").fetchone():
        raise SchemaError('recipe_schema_collision')


def assert_installed(connection) -> None:
    from improvement_store import ConflictError
    from improvement_compose_schema import _assert_statements
    expected = statements()
    try:
        _assert_statements(connection, expected, error=ConflictError)
    except ConflictError as exc:
        raise ConflictError('recipe_schema_changed') from exc
    names = {_name(sql) for sql in expected}
    if any(row['name'] not in names for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE sql IS NOT NULL AND (lower(name) GLOB 'improvement_recipe*' OR lower(tbl_name) GLOB 'improvement_recipe*')")):
        raise ConflictError('recipe_schema_changed')


def migrate(connection) -> None:
    from improvement_store import SchemaError
    from improvement_compose_schema import assert_installed as assert_compose
    if not connection.in_transaction:
        raise SchemaError('recipe_migration_requires_owned_transaction')
    assert_compose(connection)
    _assert_absent(connection)
    for sql in statements():
        connection.execute(sql)
    assert_installed(connection)
    if connection.execute('PRAGMA foreign_key_check').fetchone():
        raise SchemaError('recipe_migration_foreign_key_violation')
