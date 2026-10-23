"""Append-only isolated skill-view metadata; never execution or live authority.

Encrypted manifests and current host authority require separate verification.
These joins only establish immutable lineage within the existing shared store.
"""


def _digest(column):
    return f"CHECK(length({column})=64 AND {column} NOT GLOB '*[^0-9a-f]*')"


SCHEMA = (
    "CREATE TABLE improvement_effective_views("
    "id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,experiment_id TEXT NOT NULL,target_id TEXT NOT NULL,"
    "context_id TEXT NOT NULL,comparison_id TEXT NOT NULL,variant TEXT NOT NULL CHECK(variant IN ('baseline','candidate')),"
    "candidate_id TEXT NOT NULL,base_revision_id TEXT NOT NULL,base_hash TEXT NOT NULL,"
    "base_generation INTEGER NOT NULL CHECK(base_generation>0),source_authority_hash TEXT NOT NULL,"
    "semantic_receipt_id TEXT NOT NULL,manifest_hash TEXT NOT NULL,manifest_blob_hash TEXT NOT NULL,created_at REAL NOT NULL,"
    "UNIQUE(id,brain_id),UNIQUE(comparison_id,brain_id,variant),CHECK(manifest_hash=manifest_blob_hash),"
    f"{_digest('manifest_hash')},{_digest('source_authority_hash')},"
    "FOREIGN KEY(experiment_id,brain_id) REFERENCES improvement_experiments(id,brain_id),"
    "FOREIGN KEY(target_id,brain_id) REFERENCES improvement_targets(id,brain_id),"
    "FOREIGN KEY(context_id,brain_id) REFERENCES improvement_trial_contexts(id,brain_id),"
    "FOREIGN KEY(comparison_id,brain_id) REFERENCES improvement_comparisons(id,brain_id),"
    "FOREIGN KEY(candidate_id,brain_id) REFERENCES improvement_skill_candidates(id,brain_id),"
    "FOREIGN KEY(base_revision_id,brain_id) REFERENCES improvement_revisions(id,brain_id),"
    "FOREIGN KEY(semantic_receipt_id,brain_id) REFERENCES improvement_semantic_receipts(id,brain_id))",
    "CREATE TABLE improvement_view_trial_links("
    "comparison_id TEXT NOT NULL,brain_id TEXT NOT NULL,experiment_id TEXT NOT NULL,"
    "cell_position INTEGER NOT NULL CHECK(cell_position BETWEEN 0 AND 3999),trial_id TEXT NOT NULL,request_hash TEXT NOT NULL,"
    "pair_id TEXT NOT NULL,case_id TEXT NOT NULL,repeat INTEGER NOT NULL CHECK(repeat IN (1,2)),"
    "variant TEXT NOT NULL CHECK(variant IN ('baseline','candidate')),view_id TEXT NOT NULL,view_hash TEXT NOT NULL,"
    "binding_hash TEXT NOT NULL,created_at REAL NOT NULL,PRIMARY KEY(comparison_id,brain_id,cell_position),UNIQUE(trial_id,brain_id),"
    f"{_digest('view_hash')},{_digest('binding_hash')},"
    "FOREIGN KEY(comparison_id,brain_id) REFERENCES improvement_comparison_views(comparison_id,brain_id),"
    "FOREIGN KEY(experiment_id,brain_id) REFERENCES improvement_experiments(id,brain_id),"
    "FOREIGN KEY(trial_id,brain_id) REFERENCES improvement_trials(id,brain_id),"
    "FOREIGN KEY(view_id,brain_id) REFERENCES improvement_effective_views(id,brain_id))",
    "CREATE TABLE improvement_effective_view_assets("
    "view_id TEXT NOT NULL,brain_id TEXT NOT NULL,position INTEGER NOT NULL CHECK(position=0),"
    "asset_id TEXT NOT NULL,canonical_ref TEXT NOT NULL,before_hash TEXT NOT NULL,content_hash TEXT NOT NULL,"
    "identity TEXT NOT NULL,authority_hash TEXT NOT NULL,origin TEXT NOT NULL CHECK(origin IN ('baseline','candidate')),"
    "PRIMARY KEY(view_id,brain_id,position),"
    "FOREIGN KEY(view_id,brain_id) REFERENCES improvement_effective_views(id,brain_id))",
    "CREATE TABLE improvement_comparison_views("
    "comparison_id TEXT NOT NULL,brain_id TEXT NOT NULL,base_view_id TEXT NOT NULL,candidate_view_id TEXT NOT NULL,"
    "semantic_receipt_id TEXT NOT NULL,binding_hash TEXT NOT NULL,binding_blob_hash TEXT NOT NULL,created_at REAL NOT NULL,"
    "PRIMARY KEY(comparison_id,brain_id),CHECK(base_view_id!=candidate_view_id),CHECK(binding_hash=binding_blob_hash),"
    f"{_digest('binding_hash')},"
    "FOREIGN KEY(comparison_id,brain_id) REFERENCES improvement_comparisons(id,brain_id),"
    "FOREIGN KEY(base_view_id,brain_id) REFERENCES improvement_effective_views(id,brain_id),"
    "FOREIGN KEY(candidate_view_id,brain_id) REFERENCES improvement_effective_views(id,brain_id),"
    "FOREIGN KEY(semantic_receipt_id,brain_id) REFERENCES improvement_semantic_receipts(id,brain_id))",
    "CREATE TABLE improvement_view_qualification_links("
    "comparison_id TEXT NOT NULL,brain_id TEXT NOT NULL,experiment_id TEXT NOT NULL,reservation_id TEXT NOT NULL,"
    "case_set_id TEXT NOT NULL,candidate_id TEXT NOT NULL,selection_event_key TEXT NOT NULL,reservation_event_key TEXT NOT NULL,"
    "selection_hash TEXT NOT NULL,binding_hash TEXT NOT NULL,pins_hash TEXT NOT NULL,family_hash TEXT NOT NULL,created_at REAL NOT NULL,"
    "PRIMARY KEY(comparison_id,brain_id),UNIQUE(reservation_id,brain_id),UNIQUE(experiment_id,brain_id),"
    "CHECK(selection_event_key!=reservation_event_key),"
    f"{_digest('selection_hash')},{_digest('binding_hash')},{_digest('pins_hash')},{_digest('family_hash')},"
    "FOREIGN KEY(comparison_id,brain_id) REFERENCES improvement_comparison_views(comparison_id,brain_id),"
    "FOREIGN KEY(experiment_id,brain_id) REFERENCES improvement_experiments(id,brain_id),"
    "FOREIGN KEY(reservation_id,brain_id) REFERENCES improvement_qualification(id,brain_id),"
    "FOREIGN KEY(case_set_id,brain_id) REFERENCES improvement_case_sets(id,brain_id),"
    "FOREIGN KEY(candidate_id,brain_id) REFERENCES improvement_skill_candidates(id,brain_id),"
    "FOREIGN KEY(brain_id,selection_event_key) REFERENCES improvement_events(brain_id,event_key),"
    "FOREIGN KEY(brain_id,reservation_event_key) REFERENCES improvement_events(brain_id,event_key) DEFERRABLE INITIALLY DEFERRED)",
    "CREATE TRIGGER improvement_view_qualification_scope BEFORE INSERT ON improvement_view_qualification_links WHEN NOT EXISTS "
    "(SELECT 1 FROM improvement_comparisons p "
    "JOIN improvement_experiments e ON e.id=p.experiment_id AND e.brain_id=p.brain_id "
    "JOIN improvement_experiment_arms a ON a.experiment_id=e.id AND a.brain_id=e.brain_id AND a.ordinal=p.ordinal "
    "JOIN improvement_experiment_selections s ON s.experiment_id=e.id AND s.brain_id=e.brain_id "
    "JOIN improvement_comparison_views b ON b.comparison_id=p.id AND b.brain_id=p.brain_id "
    "JOIN improvement_qualification q ON q.id=NEW.reservation_id AND q.brain_id=e.brain_id "
    "JOIN improvement_case_sets cs ON cs.id=q.case_set_id AND cs.brain_id=q.brain_id "
    "JOIN improvement_events se ON se.brain_id=s.brain_id AND se.event_key=s.event_key "
    "WHERE p.id=NEW.comparison_id AND p.brain_id=NEW.brain_id AND p.kind='final' AND e.id=NEW.experiment_id "
    "AND s.choice='candidate' AND s.ordinal=p.ordinal AND s.definition_hash=e.definition_hash "
    "AND p.definition_hash=e.definition_hash AND p.arm_hash=a.envelope_hash AND a.candidate_id=NEW.candidate_id "
    "AND s.event_key=NEW.selection_event_key AND se.operation='experiment_select' "
    "AND json_extract(se.result_json,'$.experiment_id')=e.id AND json_extract(se.result_json,'$.definition_hash')=e.definition_hash "
    "AND json_extract(se.result_json,'$.phase')='comparing' AND b.binding_hash=NEW.binding_hash "
    "AND q.status='reserved' AND q.consumed_at IS NULL AND q.case_set_id=NEW.case_set_id AND q.pins_hash=NEW.pins_hash "
    "AND cs.id=json_extract(e.definition_json,'$.case_set_id') AND cs.manifest_hash=json_extract(e.definition_json,'$.case_set_hash') "
    "AND json_type(q.pins_json)='object' AND (SELECT count(*) FROM json_each(q.pins_json))=9 "
    "AND json_extract(q.pins_json,'$.experiment_id')=e.id "
    "AND json_extract(q.pins_json,'$.base_bundle_hash')=json_extract(e.definition_json,'$.base_bundle_hash') "
    "AND json_extract(q.pins_json,'$.candidate_bundle_hash')=a.envelope_hash "
    "AND json_extract(q.pins_json,'$.contract_hash')=json_extract(e.definition_json,'$.contract_hash') "
    "AND json_extract(q.pins_json,'$.case_set_hash')=cs.manifest_hash "
    "AND json_extract(q.pins_json,'$.engine_config_hash')=json_extract(e.definition_json,'$.engine_config_hash') "
    "AND json_extract(q.pins_json,'$.grant_hash')=json_extract(e.definition_json,'$.grant_hash') "
    "AND json_extract(q.pins_json,'$.scope_hash')=json_extract(e.definition_json,'$.scope_hash') "
    "AND json_extract(q.pins_json,'$.policy_version')=json_extract(e.definition_json,'$.policy_version') "
    "AND NOT EXISTS(SELECT 1 FROM improvement_events old WHERE old.brain_id=q.brain_id AND old.operation='qualification_reserve' "
    "AND json_extract(old.result_json,'$.reservation_id')=q.id)) "
    "BEGIN SELECT RAISE(ABORT,'view_qualification_scope_mismatch'); END",
    "CREATE TRIGGER improvement_effective_view_scope BEFORE INSERT ON improvement_effective_views WHEN NOT EXISTS "
    "(SELECT 1 FROM improvement_comparisons p "
    "JOIN improvement_experiments e ON e.id=p.experiment_id AND e.brain_id=p.brain_id "
    "JOIN improvement_experiment_arms a ON a.experiment_id=e.id AND a.brain_id=e.brain_id AND a.ordinal=p.ordinal "
    "JOIN improvement_skill_candidates c ON c.id=a.candidate_id AND c.brain_id=a.brain_id "
    "JOIN improvement_revisions r ON r.id=c.base_revision_id AND r.brain_id=c.brain_id "
    "JOIN improvement_trial_contexts x ON x.id=e.context_id AND x.brain_id=e.brain_id "
    "JOIN improvement_semantic_receipts s ON s.id=NEW.semantic_receipt_id AND s.brain_id=e.brain_id "
    "WHERE p.id=NEW.comparison_id AND p.brain_id=NEW.brain_id AND e.id=NEW.experiment_id "
    "AND e.target_id=NEW.target_id AND e.context_id=NEW.context_id AND x.experiment_id=e.id "
    "AND c.id=NEW.candidate_id AND c.experiment_id=e.id AND c.context_id=e.context_id AND c.target_id=e.target_id "
    "AND c.base_revision_id=NEW.base_revision_id AND c.base_hash=NEW.base_hash AND c.base_generation=NEW.base_generation "
    "AND r.target_id=e.target_id AND r.content_hash=c.base_hash "
    "AND a.envelope_hash=p.arm_hash AND p.definition_hash=e.definition_hash "
    "AND json_extract(a.envelope_json,'$.source_authority_hash')=NEW.source_authority_hash "
    "AND s.experiment_id=e.id AND s.candidate_id=c.id) "
    "BEGIN SELECT RAISE(ABORT,'effective_view_scope_mismatch'); END",
    "CREATE TRIGGER improvement_effective_view_asset_scope BEFORE INSERT ON improvement_effective_view_assets WHEN NOT EXISTS "
    "(SELECT 1 FROM improvement_effective_views v "
    "JOIN improvement_targets t ON t.id=v.target_id AND t.brain_id=v.brain_id "
    "JOIN improvement_skill_candidates c ON c.id=v.candidate_id AND c.brain_id=v.brain_id "
    "WHERE v.id=NEW.view_id AND v.brain_id=NEW.brain_id AND NEW.origin=v.variant "
    "AND NEW.canonical_ref=t.canonical_ref AND NEW.identity=t.identity "
    "AND NEW.before_hash=v.base_hash AND NEW.authority_hash=v.source_authority_hash "
    "AND ((v.variant='baseline' AND NEW.asset_id=v.base_revision_id AND NEW.content_hash=v.base_hash) "
    "OR (v.variant='candidate' AND NEW.asset_id=c.id AND NEW.content_hash=c.content_hash))) "
    "BEGIN SELECT RAISE(ABORT,'effective_view_asset_scope_mismatch'); END",
    "CREATE TRIGGER improvement_comparison_view_scope BEFORE INSERT ON improvement_comparison_views WHEN NOT EXISTS "
    "(SELECT 1 FROM improvement_effective_views b "
    "JOIN improvement_effective_views c ON c.comparison_id=b.comparison_id AND c.brain_id=b.brain_id "
    "JOIN improvement_effective_view_assets ba ON ba.view_id=b.id AND ba.brain_id=b.brain_id AND ba.position=0 "
    "JOIN improvement_effective_view_assets ca ON ca.view_id=c.id AND ca.brain_id=c.brain_id AND ca.position=0 "
    "WHERE b.id=NEW.base_view_id AND c.id=NEW.candidate_view_id AND b.brain_id=NEW.brain_id "
    "AND b.comparison_id=NEW.comparison_id AND b.variant='baseline' AND c.variant='candidate' "
    "AND b.semantic_receipt_id=NEW.semantic_receipt_id AND c.semantic_receipt_id=NEW.semantic_receipt_id "
    "AND b.candidate_id=c.candidate_id AND b.source_authority_hash=c.source_authority_hash "
    "AND ba.canonical_ref=ca.canonical_ref AND ba.identity=ca.identity AND ba.before_hash=ca.before_hash) "
    "BEGIN SELECT RAISE(ABORT,'comparison_view_scope_mismatch'); END",
    "CREATE TRIGGER improvement_view_binding_runtime_fence BEFORE INSERT ON improvement_comparison_views WHEN EXISTS "
    "(SELECT 1 FROM improvement_experiment_trial_links l WHERE l.comparison_id=NEW.comparison_id AND l.brain_id=NEW.brain_id) "
    "BEGIN SELECT RAISE(ABORT,'comparison_runtime_already_started'); END",
    "CREATE TRIGGER improvement_legacy_trial_view_fence BEFORE INSERT ON improvement_experiment_trial_links WHEN EXISTS "
    "(SELECT 1 FROM improvement_comparison_views b WHERE b.comparison_id=NEW.comparison_id AND b.brain_id=NEW.brain_id) "
    "OR EXISTS(SELECT 1 FROM improvement_view_trial_links l WHERE l.trial_id=NEW.trial_id AND l.brain_id=NEW.brain_id) "
    "OR EXISTS(SELECT 1 FROM improvement_trials t WHERE t.id=NEW.trial_id AND t.brain_id=NEW.brain_id "
    "AND json_extract(t.request_json,'$.version')=4) "
    "BEGIN SELECT RAISE(ABORT,'view_trial_version_required'); END",
    "CREATE TRIGGER improvement_view_trial_scope BEFORE INSERT ON improvement_view_trial_links WHEN NOT EXISTS "
    "(SELECT 1 FROM improvement_comparison_views b "
    "JOIN improvement_comparisons p ON p.id=b.comparison_id AND p.brain_id=b.brain_id "
    "JOIN improvement_effective_views v ON v.id=NEW.view_id AND v.brain_id=b.brain_id AND v.comparison_id=p.id "
    "JOIN improvement_effective_view_assets a ON a.view_id=v.id AND a.brain_id=v.brain_id AND a.position=0 "
    "JOIN improvement_trials t ON t.id=NEW.trial_id AND t.brain_id=b.brain_id "
    "WHERE b.comparison_id=NEW.comparison_id AND b.brain_id=NEW.brain_id AND p.experiment_id=NEW.experiment_id "
    "AND v.experiment_id=NEW.experiment_id AND v.variant=NEW.variant AND v.manifest_hash=NEW.view_hash "
    "AND b.binding_hash=NEW.binding_hash AND NEW.cell_position<p.cell_count "
    "AND v.id=CASE NEW.variant WHEN 'baseline' THEN b.base_view_id ELSE b.candidate_view_id END "
    "AND t.request_hash=NEW.request_hash AND json_extract(t.request_json,'$.version')=4 "
    "AND json_extract(t.request_json,'$.pins.experiment_id')=NEW.experiment_id "
    "AND json_extract(t.request_json,'$.lineage.comparison_id')=p.id "
    "AND json_extract(t.request_json,'$.lineage.definition_hash')=p.definition_hash "
    "AND json_extract(t.request_json,'$.lineage.matrix_hash')=p.matrix_hash "
    "AND json_extract(t.request_json,'$.lineage.arm_hash')=p.arm_hash "
    "AND json_extract(t.request_json,'$.lineage.arm_ordinal')=p.ordinal "
    "AND json_extract(t.request_json,'$.lineage.context_id')=v.context_id "
    "AND json_extract(t.request_json,'$.lineage.candidate_id')=v.candidate_id "
    "AND json_extract(t.request_json,'$.lineage.cell_position')=NEW.cell_position "
    "AND json_extract(t.request_json,'$.lineage.pair_id')=NEW.pair_id "
    "AND json_extract(t.request_json,'$.case_id')=NEW.case_id AND json_extract(t.request_json,'$.repeat')=NEW.repeat "
    "AND json_extract(t.request_json,'$.variant')=NEW.variant "
    "AND json_extract(t.request_json,'$.view.view_id')=v.id AND json_extract(t.request_json,'$.view.view_hash')=NEW.view_hash "
    "AND json_extract(t.request_json,'$.view.binding_hash')=b.binding_hash "
    "AND EXISTS(SELECT 1 FROM improvement_events ev WHERE ev.brain_id=b.brain_id AND ev.operation='comparison_views_freeze' "
    "AND json_extract(ev.result_json,'$.comparison_id')=p.id AND json_extract(ev.result_json,'$.binding_hash')=b.binding_hash "
    "AND json_extract(ev.result_json,'$.views.'||NEW.variant||'.view_id')=v.id "
    "AND json_extract(ev.result_json,'$.views.'||NEW.variant||'.manifest_hash')=NEW.view_hash)) "
    "OR EXISTS(SELECT 1 FROM improvement_experiment_trial_links l WHERE l.trial_id=NEW.trial_id AND l.brain_id=NEW.brain_id) "
    "OR EXISTS(SELECT 1 FROM improvement_preparation_trial_links l WHERE l.trial_id=NEW.trial_id AND l.brain_id=NEW.brain_id) "
    "BEGIN SELECT RAISE(ABORT,'view_trial_scope_mismatch'); END",
)

IMMUTABLE = ('improvement_effective_views', 'improvement_effective_view_assets', 'improvement_comparison_views',
             'improvement_view_trial_links', 'improvement_view_qualification_links')


def assert_installed(connection):
    """Refuse changed draft guards before authority, without repairing history."""
    import re
    from improvement_store import ConflictError
    from improvement_operation_schema import assert_installed as assert_operations

    assert_operations(connection)
    statements = list(SCHEMA)
    statements.extend(f"CREATE TRIGGER {table}_{action.lower()} BEFORE {action} ON {table} "
                      "BEGIN SELECT RAISE(ABORT,'immutable_improvement_history'); END"
                      for table in IMMUTABLE for action in ('UPDATE', 'DELETE'))
    installed = {row['name']: ' '.join((row['sql'] or '').split()).rstrip(';')
                 for row in connection.execute("SELECT name,sql FROM sqlite_master WHERE name LIKE 'improvement_%'")}
    for statement in statements:
        name = re.match(r'CREATE (?:UNIQUE )?(?:TABLE|INDEX|TRIGGER) ([a-z_][a-z_0-9]*)', statement)[1]
        if installed.get(name) != ' '.join(statement.split()).rstrip(';'):
            raise ConflictError('view_schema_changed')
