"""Version10 recipe reference overlay for actual v4 effective-view lineage.

Only the trial membership trigger changes. Version9 definitions remain exact
historical authority; encrypted lineage and trace validation stays with owners.
"""
from __future__ import annotations

from improvement_recipe_schema import _assert_expected, assert_installed as assert_nine, statements as nine_statements

_TRIGGER = 'CREATE TRIGGER improvement_recipe_trial_scope '
_TAIL = 'AND e.context_id=p.context_id AND c.experiment_id=p.experiment_id))) '
_VIEW = (
    'AND e.context_id=p.context_id AND c.experiment_id=p.experiment_id) OR '
    'EXISTS(SELECT 1 FROM improvement_view_trial_links l '
    'JOIN improvement_comparisons c ON c.id=l.comparison_id AND c.brain_id=l.brain_id '
    'JOIN improvement_experiments e ON e.id=c.experiment_id AND e.brain_id=c.brain_id '
    'JOIN improvement_trial_contexts x ON x.id=e.context_id AND x.brain_id=e.brain_id '
    'JOIN improvement_comparison_views b ON b.comparison_id=c.id AND b.brain_id=c.brain_id '
    'JOIN improvement_effective_views v ON v.id=l.view_id AND v.brain_id=l.brain_id AND v.comparison_id=c.id '
    'JOIN improvement_effective_view_assets z ON z.view_id=v.id AND z.brain_id=v.brain_id AND z.position=0 '
    "WHERE l.trial_id=t.id AND l.brain_id=p.brain_id AND l.experiment_id=p.experiment_id AND c.kind='tuning' "
    'AND e.id=p.experiment_id AND e.context_id=p.context_id AND x.experiment_id=e.id '
    'AND v.experiment_id=e.id AND v.context_id=x.id AND v.variant=l.variant AND v.manifest_hash=l.view_hash '
    'AND b.binding_hash=l.binding_hash AND l.cell_position<c.cell_count '
    "AND v.id=CASE l.variant WHEN 'baseline' THEN b.base_view_id ELSE b.candidate_view_id END "
    "AND t.request_hash=l.request_hash AND json_extract(t.request_json,'$.version')=4 "
    "AND json_extract(t.request_json,'$.pins.experiment_id')=e.id "
    "AND json_extract(t.request_json,'$.pins.base_bundle_hash')=json_extract(e.definition_json,'$.base_bundle_hash') "
    "AND json_extract(t.request_json,'$.pins.candidate_bundle_hash')=c.arm_hash "
    "AND json_extract(t.request_json,'$.pins.contract_hash')=json_extract(e.definition_json,'$.contract_hash') "
    "AND json_extract(t.request_json,'$.pins.case_set_hash')=json_extract(e.definition_json,'$.case_set_hash') "
    "AND json_extract(t.request_json,'$.pins.scope_hash')=x.scope_hash "
    "AND json_extract(t.request_json,'$.pins.grant_hash')=x.grant_hash "
    "AND json_extract(t.request_json,'$.pins.engine_config_hash')=x.engine_config_hash "
    "AND json_extract(t.request_json,'$.pins.policy_version')=x.policy_version "
    "AND json_extract(t.request_json,'$.lineage.comparison_id')=c.id "
    "AND json_extract(t.request_json,'$.lineage.definition_hash')=c.definition_hash "
    "AND json_extract(t.request_json,'$.lineage.matrix_hash')=c.matrix_hash "
    "AND json_extract(t.request_json,'$.lineage.arm_hash')=c.arm_hash "
    "AND json_extract(t.request_json,'$.lineage.arm_ordinal')=c.ordinal "
    "AND json_extract(t.request_json,'$.lineage.context_id')=v.context_id "
    "AND json_extract(t.request_json,'$.lineage.candidate_id')=v.candidate_id "
    "AND json_extract(t.request_json,'$.lineage.cell_position')=l.cell_position "
    "AND json_extract(t.request_json,'$.lineage.pair_id')=l.pair_id "
    "AND json_extract(t.request_json,'$.case_id')=l.case_id AND json_extract(t.request_json,'$.repeat')=l.repeat "
    "AND json_extract(t.request_json,'$.variant')=l.variant "
    "AND json_extract(t.request_json,'$.view.view_id')=v.id AND json_extract(t.request_json,'$.view.view_hash')=l.view_hash "
    "AND json_extract(t.request_json,'$.view.binding_hash')=b.binding_hash "
    "AND EXISTS(SELECT 1 FROM improvement_events ev WHERE ev.brain_id=b.brain_id AND ev.operation='comparison_views_freeze' "
    "AND json_extract(ev.result_json,'$.comparison_id')=c.id AND json_extract(ev.result_json,'$.binding_hash')=b.binding_hash "
    "AND json_extract(ev.result_json,'$.views.'||l.variant||'.view_id')=v.id "
    "AND json_extract(ev.result_json,'$.views.'||l.variant||'.manifest_hash')=l.view_hash)))) "
)


def statements() -> tuple[str, ...]:
    original = nine_statements()
    trial = next(sql for sql in original if sql.startswith(_TRIGGER))
    if trial.count(_TAIL) != 1:
        raise RuntimeError('recipe_nine_trial_guard_changed')
    return tuple(sql.replace(_TAIL, _VIEW) if sql == trial else sql for sql in original)


def assert_installed(connection) -> None:
    _assert_expected(connection, statements())


def migrate(connection) -> None:
    from improvement_store import SchemaError
    from improvement_compose_schema import assert_installed as assert_compose
    version = connection.execute('SELECT version FROM improvement_schema WHERE id=1').fetchone()
    if not connection.in_transaction or not version or version[0] != 9:
        raise SchemaError('recipe_view_migration_requires_owned_nine_transaction')
    assert_compose(connection)
    assert_nine(connection)
    connection.execute('DROP TRIGGER improvement_recipe_trial_scope')
    connection.execute(next(sql for sql in statements() if sql.startswith(_TRIGGER)))
    assert_installed(connection)
    if connection.execute('PRAGMA foreign_key_check').fetchone():
        raise SchemaError('recipe_view_migration_foreign_key_violation')
