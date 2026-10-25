"""Typed preparation and native role ownership in the existing resonance DB.

These rows are history/ownership, never native readiness or activation authority.
"""

TERMINAL = ("completed", "failed", "interrupted", "cancelled", "not_run")
STATUSES = ("pending", "reserved", "prepared", "running", *TERMINAL)
_STATUSES = ",".join("'" + value + "'" for value in STATUSES)
_TERMINAL = ",".join("'" + value + "'" for value in TERMINAL)
_RETRYABLE_PREVIOUS = (
    "((p.status='not_run' AND p.failure_reason='capacity_unavailable' AND p.engine_at IS NULL "
    "AND pc.engine_at IS NULL AND pc.status='refunded') OR "
    "(p.status='interrupted' AND p.failure_reason='native_transient_error' AND p.engine_at IS NOT NULL "
    "AND pc.engine_at=p.engine_at AND pc.status='interrupted' AND EXISTS "
    "(SELECT 1 FROM improvement_operation_observations ob WHERE ob.operation_id=p.operation_id "
    "AND ob.brain_id=p.brain_id AND ob.attempt=p.attempt AND ob.kind='engine_event' AND ob.late=0)))")

SCHEMA = (
    "CREATE TABLE improvement_preparations("
    "id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,experiment_id TEXT NOT NULL,context_id TEXT NOT NULL,"
    "definition_hash TEXT NOT NULL,schedule_hash TEXT NOT NULL,schedule_blob_hash TEXT NOT NULL,"
    "cell_count INTEGER NOT NULL CHECK(cell_count BETWEEN 1 AND 2000),created_at REAL NOT NULL,"
    "UNIQUE(id,brain_id),UNIQUE(experiment_id,brain_id),"
    "FOREIGN KEY(experiment_id,brain_id) REFERENCES improvement_experiments(id,brain_id),"
    "FOREIGN KEY(context_id,brain_id) REFERENCES improvement_trial_contexts(id,brain_id))",
    "CREATE TABLE improvement_preparation_trial_links("
    "preparation_id TEXT NOT NULL,brain_id TEXT NOT NULL,experiment_id TEXT NOT NULL,"
    "cell_position INTEGER NOT NULL CHECK(cell_position BETWEEN 0 AND 1999),trial_id TEXT NOT NULL,"
    "request_hash TEXT NOT NULL,case_id TEXT NOT NULL,repeat INTEGER NOT NULL CHECK(repeat IN (1,2)),created_at REAL NOT NULL,"
    "PRIMARY KEY(preparation_id,brain_id,cell_position),UNIQUE(trial_id,brain_id),"
    "FOREIGN KEY(preparation_id,brain_id) REFERENCES improvement_preparations(id,brain_id),"
    "FOREIGN KEY(experiment_id,brain_id) REFERENCES improvement_experiments(id,brain_id),"
    "FOREIGN KEY(trial_id,brain_id) REFERENCES improvement_trials(id,brain_id))",
    "CREATE TABLE improvement_operations("
    "id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,experiment_id TEXT NOT NULL,context_id TEXT NOT NULL,"
    "kind TEXT NOT NULL CHECK(kind IN ('propose','repair','semantic')),role TEXT NOT NULL,purpose TEXT NOT NULL,"
    "candidate_id TEXT,parent_id TEXT,request_hash TEXT NOT NULL,request_json TEXT NOT NULL,"
    "input_hash TEXT NOT NULL,input_blob_hash TEXT NOT NULL,"
    f"status TEXT NOT NULL CHECK(status IN ({_STATUSES})),generation INTEGER NOT NULL CHECK(generation>0),"
    "attempt INTEGER NOT NULL CHECK(attempt BETWEEN 0 AND 2),created_at REAL NOT NULL,updated_at REAL NOT NULL,"
    "UNIQUE(id,brain_id),CHECK(input_hash=input_blob_hash),"
    "CHECK((kind IN ('propose','repair') AND role='improver' AND purpose='improve_propose' AND candidate_id IS NULL) "
    "OR (kind='semantic' AND role='semantic_reviewer' AND purpose='improve_evaluate' AND candidate_id IS NOT NULL)),"
    "CHECK((kind='repair' AND parent_id IS NOT NULL) OR (kind!='repair' AND parent_id IS NULL)),"
    "FOREIGN KEY(experiment_id,brain_id) REFERENCES improvement_experiments(id,brain_id),"
    "FOREIGN KEY(context_id,brain_id) REFERENCES improvement_trial_contexts(id,brain_id),"
    "FOREIGN KEY(candidate_id,brain_id) REFERENCES improvement_skill_candidates(id,brain_id),"
    "FOREIGN KEY(parent_id,brain_id) REFERENCES improvement_operations(id,brain_id))",
    "CREATE UNIQUE INDEX improvement_one_proposer ON improvement_operations(experiment_id,brain_id) WHERE kind='propose'",
    "CREATE UNIQUE INDEX improvement_one_repair ON improvement_operations(experiment_id,brain_id) WHERE kind='repair'",
    "CREATE UNIQUE INDEX improvement_one_semantic ON improvement_operations(candidate_id,brain_id) WHERE kind='semantic'",
    "CREATE INDEX improvement_operations_experiment ON improvement_operations(brain_id,experiment_id,id)",
    "CREATE TABLE improvement_operation_attempts("
    "operation_id TEXT NOT NULL,brain_id TEXT NOT NULL,attempt INTEGER NOT NULL CHECK(attempt IN (1,2)),"
    f"status TEXT NOT NULL CHECK(status IN ({_STATUSES})),call_id INTEGER NOT NULL UNIQUE,"
    "lease_token TEXT,lease_until REAL,writer_hash TEXT,engine_at REAL,materialization_hash TEXT,workspace_json TEXT,"
    "result_json TEXT,failure_reason TEXT,created_at REAL NOT NULL,updated_at REAL NOT NULL,"
    "PRIMARY KEY(operation_id,brain_id,attempt),"
    "FOREIGN KEY(operation_id,brain_id) REFERENCES improvement_operations(id,brain_id),"
    "FOREIGN KEY(call_id) REFERENCES agent_calls(id))",
    "CREATE TABLE improvement_operation_observations("
    "operation_id TEXT NOT NULL,brain_id TEXT NOT NULL,attempt INTEGER NOT NULL,sequence INTEGER NOT NULL CHECK(sequence>0),"
    "kind TEXT NOT NULL,payload_hash TEXT NOT NULL,blob_hashes_json TEXT NOT NULL,"
    "late INTEGER NOT NULL CHECK(late IN (0,1)),created_at REAL NOT NULL,"
    "PRIMARY KEY(operation_id,brain_id,attempt,sequence),"
    "FOREIGN KEY(operation_id,brain_id,attempt) REFERENCES improvement_operation_attempts(operation_id,brain_id,attempt))",
    "CREATE TABLE improvement_operation_results("
    "id TEXT PRIMARY KEY,operation_id TEXT NOT NULL,brain_id TEXT NOT NULL,attempt INTEGER NOT NULL,"
    "result_hash TEXT NOT NULL,blob_hash TEXT NOT NULL,created_at REAL NOT NULL,"
    "UNIQUE(id,brain_id),UNIQUE(operation_id,attempt,result_hash),"
    "FOREIGN KEY(operation_id,brain_id,attempt) REFERENCES improvement_operation_attempts(operation_id,brain_id,attempt))",
    "CREATE TABLE improvement_proposal_publications("
    "experiment_id TEXT NOT NULL,brain_id TEXT NOT NULL,operation_id TEXT NOT NULL,result_id TEXT NOT NULL,"
    "batch_hash TEXT NOT NULL,created_at REAL NOT NULL,PRIMARY KEY(experiment_id,brain_id),"
    "FOREIGN KEY(experiment_id,brain_id) REFERENCES improvement_experiments(id,brain_id),"
    "FOREIGN KEY(operation_id,brain_id) REFERENCES improvement_operations(id,brain_id),"
    "FOREIGN KEY(result_id,brain_id) REFERENCES improvement_operation_results(id,brain_id))",
    "CREATE TABLE improvement_generated_candidates("
    "experiment_id TEXT NOT NULL,brain_id TEXT NOT NULL,ordinal INTEGER NOT NULL CHECK(ordinal IN (1,2)),"
    "candidate_id TEXT NOT NULL,operation_id TEXT NOT NULL,result_id TEXT NOT NULL,created_at REAL NOT NULL,"
    "PRIMARY KEY(experiment_id,brain_id,ordinal),UNIQUE(candidate_id,brain_id),"
    "FOREIGN KEY(experiment_id,brain_id) REFERENCES improvement_proposal_publications(experiment_id,brain_id),"
    "FOREIGN KEY(candidate_id,brain_id) REFERENCES improvement_skill_candidates(id,brain_id),"
    "FOREIGN KEY(operation_id,brain_id) REFERENCES improvement_operations(id,brain_id),"
    "FOREIGN KEY(result_id,brain_id) REFERENCES improvement_operation_results(id,brain_id))",
    "CREATE TABLE improvement_semantic_receipts("
    "id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,experiment_id TEXT NOT NULL,candidate_id TEXT NOT NULL,"
    "operation_id TEXT NOT NULL,result_id TEXT NOT NULL,binding_hash TEXT NOT NULL,binding_blob_hash TEXT NOT NULL,"
    "assessment_hash TEXT NOT NULL,blob_hash TEXT NOT NULL,created_at REAL NOT NULL,"
    "UNIQUE(id,brain_id),UNIQUE(operation_id,result_id,candidate_id),"
    "FOREIGN KEY(experiment_id,brain_id) REFERENCES improvement_experiments(id,brain_id),"
    "FOREIGN KEY(candidate_id,brain_id) REFERENCES improvement_skill_candidates(id,brain_id),"
    "FOREIGN KEY(operation_id,brain_id) REFERENCES improvement_operations(id,brain_id),"
    "FOREIGN KEY(result_id,brain_id) REFERENCES improvement_operation_results(id,brain_id))",
    "CREATE TRIGGER improvement_preparation_scope BEFORE INSERT ON improvement_preparations WHEN NOT EXISTS "
    "(SELECT 1 FROM improvement_experiments e WHERE e.id=NEW.experiment_id AND e.brain_id=NEW.brain_id "
    "AND e.context_id=NEW.context_id AND e.definition_hash=NEW.definition_hash AND e.phase='proposed') "
    "BEGIN SELECT RAISE(ABORT,'preparation_scope_mismatch'); END",
    "CREATE TRIGGER improvement_preparation_trial_scope BEFORE INSERT ON improvement_preparation_trial_links WHEN NOT EXISTS "
    "(SELECT 1 FROM improvement_preparations p JOIN improvement_trials t ON t.id=NEW.trial_id AND t.brain_id=p.brain_id "
    "JOIN improvement_experiments e ON e.id=p.experiment_id AND e.brain_id=p.brain_id "
    "WHERE p.id=NEW.preparation_id AND p.brain_id=NEW.brain_id AND p.experiment_id=NEW.experiment_id "
    "AND e.phase='preparing' AND NEW.cell_position<p.cell_count AND t.request_hash=NEW.request_hash "
    "AND json_extract(t.request_json,'$.version')=3 AND json_extract(t.request_json,'$.variant')='baseline' "
    "AND json_extract(t.request_json,'$.case_id')=NEW.case_id AND json_extract(t.request_json,'$.repeat')=NEW.repeat "
    "AND json_extract(t.request_json,'$.pins.experiment_id')=NEW.experiment_id "
    "AND json_extract(t.request_json,'$.preparation.preparation_id')=p.id "
    "AND json_extract(t.request_json,'$.preparation.context_id')=p.context_id "
    "AND json_extract(t.request_json,'$.preparation.definition_hash')=p.definition_hash "
    "AND json_extract(t.request_json,'$.preparation.schedule_hash')=p.schedule_hash "
    "AND json_extract(t.request_json,'$.preparation.cell_position')=NEW.cell_position) "
    "BEGIN SELECT RAISE(ABORT,'preparation_trial_scope_mismatch'); END",
    "CREATE TRIGGER improvement_preparation_arm_fence BEFORE INSERT ON improvement_experiment_arms WHEN EXISTS "
    "(SELECT 1 FROM improvement_experiments e JOIN improvement_preparations p ON p.experiment_id=e.id AND p.brain_id=e.brain_id "
    "WHERE e.id=NEW.experiment_id AND e.brain_id=NEW.brain_id AND e.phase='preparing') "
    "BEGIN SELECT RAISE(ABORT,'preparation_incomplete'); END",
    "CREATE TRIGGER improvement_operation_scope BEFORE INSERT ON improvement_operations WHEN "
    "NEW.status!='pending' OR NEW.generation!=1 OR NEW.attempt!=0 OR NOT EXISTS "
    "(SELECT 1 FROM improvement_experiments e WHERE e.id=NEW.experiment_id AND e.brain_id=NEW.brain_id "
    "AND e.context_id=NEW.context_id AND e.definition_hash=json_extract(NEW.request_json,'$.definition_hash') "
    "AND ((NEW.kind IN ('propose','repair') AND e.phase='proposing') "
    "OR (NEW.kind='semantic' AND e.phase IN ('proposing','probing','comparing')))) "
    "OR (NEW.kind='repair' AND NOT EXISTS(SELECT 1 FROM improvement_operations p WHERE p.id=NEW.parent_id "
    "AND p.brain_id=NEW.brain_id AND p.experiment_id=NEW.experiment_id AND p.kind='propose')) "
    "OR (NEW.kind='semantic' AND NOT EXISTS(SELECT 1 FROM improvement_skill_candidates c WHERE c.id=NEW.candidate_id "
    "AND c.brain_id=NEW.brain_id AND c.experiment_id=NEW.experiment_id AND c.context_id=NEW.context_id)) "
    "BEGIN SELECT RAISE(ABORT,'operation_scope_mismatch'); END",
    "CREATE TRIGGER improvement_operation_update BEFORE UPDATE ON improvement_operations WHEN "
    "NEW.id IS NOT OLD.id OR NEW.brain_id IS NOT OLD.brain_id OR NEW.experiment_id IS NOT OLD.experiment_id "
    "OR NEW.context_id IS NOT OLD.context_id OR NEW.kind IS NOT OLD.kind OR NEW.role IS NOT OLD.role "
    "OR NEW.purpose IS NOT OLD.purpose OR NEW.candidate_id IS NOT OLD.candidate_id OR NEW.parent_id IS NOT OLD.parent_id "
    "OR NEW.request_hash IS NOT OLD.request_hash OR NEW.request_json IS NOT OLD.request_json "
    "OR NEW.input_hash IS NOT OLD.input_hash OR NEW.input_blob_hash IS NOT OLD.input_blob_hash "
    "OR NEW.created_at IS NOT OLD.created_at OR NEW.generation!=OLD.generation+1 "
    f"OR (OLD.status IN ({_TERMINAL}) AND NOT (OLD.status IN ('not_run','interrupted') AND "
    "((OLD.attempt=1 AND NEW.status='reserved' AND NEW.attempt=2) OR (NEW.status='cancelled' AND NEW.attempt=OLD.attempt AND EXISTS "
    "(SELECT 1 FROM improvement_events ev WHERE ev.brain_id=OLD.brain_id AND ev.operation='operation_owner_cancel' "
    "AND json_extract(ev.result_json,'$.operation_id')=OLD.id AND json_extract(ev.result_json,'$.status')='cancelled' "
    "AND json_extract(ev.result_json,'$.generation')=NEW.generation))))) "
    "OR NOT ((NEW.status=OLD.status AND NEW.attempt=OLD.attempt) "
    "OR (OLD.status='pending' AND NEW.status='reserved' AND NEW.attempt=1 AND EXISTS "
    "(SELECT 1 FROM improvement_operation_attempts a WHERE a.operation_id=OLD.id AND a.brain_id=OLD.brain_id AND a.attempt=1)) "
    "OR (OLD.status IN ('not_run','interrupted') AND OLD.attempt=1 AND NEW.status='reserved' AND NEW.attempt=2 AND EXISTS "
    "(SELECT 1 FROM improvement_operation_attempts a JOIN improvement_operation_attempts p "
    "ON p.operation_id=a.operation_id AND p.brain_id=a.brain_id AND p.attempt=1 "
    "JOIN agent_calls pc ON pc.id=p.call_id JOIN agent_calls nc ON nc.id=a.call_id "
    "WHERE a.operation_id=OLD.id AND a.brain_id=OLD.brain_id AND a.attempt=2 AND a.status='reserved' "
    f"AND p.status=OLD.status AND nc.status='reserved' AND nc.engine_at IS NULL AND {_RETRYABLE_PREVIOUS})) "
    "OR (OLD.status='reserved' AND NEW.status='prepared' AND NEW.attempt=OLD.attempt) "
    "OR (OLD.status='prepared' AND NEW.status='running' AND NEW.attempt=OLD.attempt) "
    "OR (NEW.status IN ('cancelled','not_run','interrupted','failed') AND NEW.attempt=OLD.attempt) "
    "OR (NEW.status='completed' AND OLD.status='running' AND NEW.attempt=OLD.attempt AND EXISTS "
    "(SELECT 1 FROM improvement_operation_attempts a JOIN agent_calls c ON c.id=a.call_id "
    "WHERE a.operation_id=OLD.id AND a.brain_id=OLD.brain_id AND a.attempt=OLD.attempt "
    "AND a.status='completed' AND a.engine_at IS NOT NULL AND c.engine_at=a.engine_at AND c.status='ok'))) "
    "BEGIN SELECT RAISE(ABORT,'immutable_operation_identity_or_state'); END",
    "CREATE TRIGGER improvement_operation_delete BEFORE DELETE ON improvement_operations "
    "BEGIN SELECT RAISE(ABORT,'immutable_operation_history'); END",
    "CREATE TRIGGER improvement_operation_attempt_scope BEFORE INSERT ON improvement_operation_attempts WHEN "
    "NEW.status!='reserved' OR NEW.engine_at IS NOT NULL OR NOT EXISTS "
    "(SELECT 1 FROM improvement_operations o JOIN agent_calls c ON c.id=NEW.call_id "
    "WHERE o.id=NEW.operation_id AND o.brain_id=NEW.brain_id AND NEW.attempt=o.attempt+1 "
    "AND ((o.status='pending' AND o.attempt=0 AND NEW.attempt=1) OR "
    "(o.status IN ('not_run','interrupted') AND o.attempt=1 AND NEW.attempt=2 AND EXISTS "
    "(SELECT 1 FROM improvement_operation_attempts p JOIN agent_calls pc ON pc.id=p.call_id "
    "WHERE p.operation_id=o.id AND p.brain_id=o.brain_id AND p.attempt=1 AND p.status=o.status "
    f"AND {_RETRYABLE_PREVIOUS}))) AND c.brain_id=o.brain_id AND c.purpose=o.purpose "
    "AND c.context_ref='improvement:'||o.experiment_id AND c.mirror_ref='improvement_operation:'||o.id "
    "AND c.reason_ref='improvement_operation:'||o.id||':attempt:'||NEW.attempt "
    "AND c.attempt=NEW.attempt AND c.status='reserved' AND c.engine_at IS NULL) "
    "BEGIN SELECT RAISE(ABORT,'operation_call_scope_mismatch'); END",
    "CREATE TRIGGER improvement_operation_attempt_update BEFORE UPDATE ON improvement_operation_attempts WHEN "
    "NEW.operation_id IS NOT OLD.operation_id OR NEW.brain_id IS NOT OLD.brain_id OR NEW.attempt IS NOT OLD.attempt "
    "OR NEW.call_id IS NOT OLD.call_id OR NEW.created_at IS NOT OLD.created_at "
    f"OR OLD.status IN ({_TERMINAL}) "
    "OR (OLD.engine_at IS NOT NULL AND NEW.engine_at IS NOT OLD.engine_at) "
    "OR (NEW.engine_at IS NOT NULL AND NOT EXISTS (SELECT 1 FROM agent_calls c WHERE c.id=OLD.call_id "
    "AND c.engine_at=NEW.engine_at AND c.status IN ('running','ok','error','interrupted'))) "
    "BEGIN SELECT RAISE(ABORT,'immutable_operation_attempt_identity'); END",
    "CREATE TRIGGER improvement_operation_attempt_delete BEFORE DELETE ON improvement_operation_attempts "
    "BEGIN SELECT RAISE(ABORT,'immutable_operation_attempt_history'); END",
    "CREATE TRIGGER improvement_proposal_publication_scope BEFORE INSERT ON improvement_proposal_publications WHEN NOT EXISTS "
    "(SELECT 1 FROM improvement_operations o JOIN improvement_operation_results r ON r.operation_id=o.id AND r.brain_id=o.brain_id "
    "WHERE o.id=NEW.operation_id AND o.brain_id=NEW.brain_id AND o.experiment_id=NEW.experiment_id "
    "AND o.kind IN ('propose','repair') AND o.status='completed' AND r.id=NEW.result_id AND r.attempt=o.attempt) "
    "BEGIN SELECT RAISE(ABORT,'proposal_publication_scope_mismatch'); END",
    "CREATE TRIGGER improvement_generated_candidate_scope BEFORE INSERT ON improvement_generated_candidates WHEN NOT EXISTS "
    "(SELECT 1 FROM improvement_proposal_publications p JOIN improvement_skill_candidates c "
    "ON c.experiment_id=p.experiment_id AND c.brain_id=p.brain_id WHERE p.experiment_id=NEW.experiment_id "
    "AND p.brain_id=NEW.brain_id AND p.operation_id=NEW.operation_id AND p.result_id=NEW.result_id "
    "AND c.id=NEW.candidate_id AND c.ordinal=NEW.ordinal) "
    "BEGIN SELECT RAISE(ABORT,'generated_candidate_scope_mismatch'); END",
    "CREATE TRIGGER improvement_semantic_receipt_scope BEFORE INSERT ON improvement_semantic_receipts WHEN NOT EXISTS "
    "(SELECT 1 FROM improvement_operations o JOIN improvement_operation_results r ON r.operation_id=o.id AND r.brain_id=o.brain_id "
    "WHERE o.id=NEW.operation_id AND o.brain_id=NEW.brain_id AND o.experiment_id=NEW.experiment_id "
    "AND o.kind='semantic' AND o.status='completed' AND o.candidate_id=NEW.candidate_id "
    "AND r.id=NEW.result_id AND r.attempt=o.attempt) "
    "BEGIN SELECT RAISE(ABORT,'semantic_receipt_scope_mismatch'); END",
)

IMMUTABLE = ("improvement_preparations", "improvement_preparation_trial_links", "improvement_operation_observations",
             "improvement_operation_results", "improvement_proposal_publications", "improvement_generated_candidates",
             "improvement_semantic_receipts")


def assert_installed(connection):
    """Same-number draft schemas are readable, but are not current role authority.

    Schema6 has not shipped; its prototype guards changed during implementation.
    Refuse missing/older guards before new work without rewriting history or
    blocking cancellation, policy-off and settlement. No cached ready verdict.
    """
    import re
    from improvement_store import ConflictError
    statements = list(SCHEMA)
    statements.extend(f"CREATE TRIGGER {table}_{action.lower()} BEFORE {action} ON {table} "
                      "BEGIN SELECT RAISE(ABORT,'immutable_improvement_history'); END"
                      for table in IMMUTABLE for action in ("UPDATE", "DELETE"))
    installed = {row["name"]: " ".join((row["sql"] or "").split()).rstrip(";")
                 for row in connection.execute("SELECT name,sql FROM sqlite_master WHERE name LIKE 'improvement_%'")}
    for statement in statements:
        name = re.match(r"CREATE (?:UNIQUE )?(?:TABLE|INDEX|TRIGGER) ([a-z_][a-z_0-9]*)", statement)[1]
        if installed.get(name) != " ".join(statement.split()).rstrip(";"):
            raise ConflictError("operation_schema_changed")
