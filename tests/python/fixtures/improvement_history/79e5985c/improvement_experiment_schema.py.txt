"""Durable experiment ownership and immutable comparison lineage in the shared DB."""

LIVE_PHASES = ("proposed", "preparing", "proposing", "probing", "comparing", "qualifying", "awaiting_apply", "blocked", "stopping")
TERMINAL_PHASES = ("completed", "rejected", "inconclusive", "cancelled", "stale")
_LIVE = ",".join("'" + value + "'" for value in LIVE_PHASES)
_TERMINAL = ",".join("'" + value + "'" for value in TERMINAL_PHASES)

SCHEMA = (
    "CREATE TABLE improvement_experiments("
    "id TEXT NOT NULL,brain_id TEXT NOT NULL,context_id TEXT NOT NULL,target_id TEXT NOT NULL,"
    "definition_hash TEXT NOT NULL,definition_json TEXT NOT NULL,"
    f"phase TEXT NOT NULL CHECK(phase IN ({_LIVE},{_TERMINAL})),generation INTEGER NOT NULL CHECK(generation>0),"
    "verdict TEXT CHECK(verdict IS NULL OR verdict IN ('eligible','rejected','inconclusive')),"
    "resume_from TEXT,blocker_json TEXT,blocker_hash TEXT,stop_kind TEXT,stop_event_key TEXT,stop_reason TEXT,"
    "created_at REAL NOT NULL,updated_at REAL NOT NULL,PRIMARY KEY(id,brain_id),"
    "CHECK(phase!='blocked' OR (resume_from IS NOT NULL AND blocker_json IS NOT NULL AND blocker_hash IS NOT NULL)),"
    f"CHECK((phase IN ({_LIVE}) AND phase!='stopping' AND stop_kind IS NULL AND stop_event_key IS NULL AND stop_reason IS NULL) "
    f"OR (phase IN ('stopping',{_TERMINAL}) AND stop_kind IS NOT NULL AND stop_kind IN ({_TERMINAL}) "
    "AND stop_event_key IS NOT NULL AND stop_reason IS NOT NULL)),"
    "FOREIGN KEY(context_id,brain_id) REFERENCES improvement_trial_contexts(id,brain_id),"
    "FOREIGN KEY(target_id,brain_id) REFERENCES improvement_targets(id,brain_id),"
    "FOREIGN KEY(brain_id,stop_event_key) REFERENCES improvement_events(brain_id,event_key) DEFERRABLE INITIALLY DEFERRED)",
    f"CREATE UNIQUE INDEX improvement_one_live_experiment ON improvement_experiments(brain_id) WHERE phase IN ({_LIVE})",
    "CREATE TABLE improvement_experiment_arms("
    "experiment_id TEXT NOT NULL,brain_id TEXT NOT NULL,ordinal INTEGER NOT NULL CHECK(ordinal IN (1,2)),"
    "candidate_id TEXT NOT NULL,authority_id TEXT NOT NULL,authority_generation INTEGER NOT NULL CHECK(authority_generation=1),"
    "envelope_hash TEXT NOT NULL,envelope_json TEXT NOT NULL,created_at REAL NOT NULL,"
    "PRIMARY KEY(experiment_id,brain_id,ordinal),UNIQUE(brain_id,candidate_id),"
    "FOREIGN KEY(experiment_id,brain_id) REFERENCES improvement_experiments(id,brain_id),"
    "FOREIGN KEY(candidate_id,brain_id) REFERENCES improvement_skill_candidates(id,brain_id),"
    "FOREIGN KEY(authority_id,brain_id) REFERENCES improvement_candidate_authorities(id,brain_id))",
    "CREATE TABLE improvement_comparisons("
    "id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,experiment_id TEXT NOT NULL,ordinal INTEGER NOT NULL,"
    "kind TEXT NOT NULL CHECK(kind IN ('tuning','final')),definition_hash TEXT NOT NULL,arm_hash TEXT NOT NULL,"
    "matrix_hash TEXT NOT NULL,matrix_blob_hash TEXT NOT NULL,cell_count INTEGER NOT NULL CHECK(cell_count BETWEEN 2 AND 4000),"
    "created_at REAL NOT NULL,UNIQUE(id,brain_id),UNIQUE(experiment_id,brain_id,ordinal,kind),"
    "FOREIGN KEY(experiment_id,brain_id) REFERENCES improvement_experiments(id,brain_id),"
    "FOREIGN KEY(experiment_id,brain_id,ordinal) REFERENCES improvement_experiment_arms(experiment_id,brain_id,ordinal))",
    "CREATE UNIQUE INDEX improvement_one_final_comparison ON improvement_comparisons(experiment_id,brain_id) WHERE kind='final'",
    "CREATE TABLE improvement_experiment_trial_links("
    "comparison_id TEXT NOT NULL,brain_id TEXT NOT NULL,experiment_id TEXT NOT NULL,"
    "cell_position INTEGER NOT NULL CHECK(cell_position BETWEEN 0 AND 3999),trial_id TEXT NOT NULL,request_hash TEXT NOT NULL,"
    "pair_id TEXT NOT NULL,case_id TEXT NOT NULL,repeat INTEGER NOT NULL CHECK(repeat IN (1,2)),"
    "variant TEXT NOT NULL CHECK(variant IN ('baseline','candidate')),created_at REAL NOT NULL,"
    "PRIMARY KEY(comparison_id,brain_id,cell_position),UNIQUE(trial_id,brain_id),"
    "FOREIGN KEY(comparison_id,brain_id) REFERENCES improvement_comparisons(id,brain_id),"
    "FOREIGN KEY(experiment_id,brain_id) REFERENCES improvement_experiments(id,brain_id),"
    "FOREIGN KEY(trial_id,brain_id) REFERENCES improvement_trials(id,brain_id))",
    "CREATE TABLE improvement_experiment_selections("
    "experiment_id TEXT NOT NULL,brain_id TEXT NOT NULL,choice TEXT NOT NULL CHECK(choice IN ('keep_base','candidate')),"
    "ordinal INTEGER,definition_hash TEXT NOT NULL,evidence_json TEXT NOT NULL,event_key TEXT NOT NULL,created_at REAL NOT NULL,"
    "PRIMARY KEY(experiment_id,brain_id),"
    "CHECK((choice='keep_base' AND ordinal IS NULL) OR (choice='candidate' AND ordinal IS NOT NULL AND ordinal IN (1,2))),"
    "FOREIGN KEY(experiment_id,brain_id) REFERENCES improvement_experiments(id,brain_id),"
    "FOREIGN KEY(experiment_id,brain_id,ordinal) REFERENCES improvement_experiment_arms(experiment_id,brain_id,ordinal),"
    "FOREIGN KEY(brain_id,event_key) REFERENCES improvement_events(brain_id,event_key) DEFERRABLE INITIALLY DEFERRED)",
    "CREATE TABLE improvement_comparison_reports("
    "id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,experiment_id TEXT NOT NULL,comparison_id TEXT NOT NULL,"
    "report_hash TEXT NOT NULL,blob_hash TEXT NOT NULL,policy_hash TEXT NOT NULL,created_at REAL NOT NULL,"
    "UNIQUE(id,brain_id),UNIQUE(comparison_id,report_hash),"
    "FOREIGN KEY(experiment_id,brain_id) REFERENCES improvement_experiments(id,brain_id),"
    "FOREIGN KEY(comparison_id,brain_id) REFERENCES improvement_comparisons(id,brain_id))",
    "CREATE TRIGGER improvement_experiment_context BEFORE INSERT ON improvement_experiments WHEN NOT EXISTS "
    "(SELECT 1 FROM improvement_trial_contexts c JOIN improvement_trial_context_grants g ON g.context_id=c.id AND g.brain_id=c.brain_id "
    "JOIN improvement_targets t ON t.id=NEW.target_id AND t.brain_id=c.brain_id "
    "WHERE c.id=NEW.context_id AND c.brain_id=NEW.brain_id AND c.experiment_id=NEW.id AND g.status='active' "
    "AND t.kind='skill' AND t.status='live' AND EXISTS(SELECT 1 FROM json_each(c.target_generations_json) "
    "WHERE key=t.id AND value=t.generation)) BEGIN SELECT RAISE(ABORT,'experiment_context_mismatch'); END",
    "CREATE TRIGGER improvement_experiment_initial BEFORE INSERT ON improvement_experiments "
    "WHEN NEW.phase!='proposed' OR NEW.generation!=1 OR NEW.verdict IS NOT NULL OR NEW.resume_from IS NOT NULL "
    "OR NEW.blocker_json IS NOT NULL OR NEW.blocker_hash IS NOT NULL "
    "BEGIN SELECT RAISE(ABORT,'invalid_experiment_initial_state'); END",
    "CREATE TRIGGER improvement_experiment_update BEFORE UPDATE ON improvement_experiments "
    f"WHEN OLD.phase IN ({_TERMINAL}) OR NEW.id!=OLD.id OR NEW.brain_id!=OLD.brain_id "
    "OR NEW.context_id!=OLD.context_id OR NEW.target_id!=OLD.target_id OR NEW.definition_hash!=OLD.definition_hash "
    "OR NEW.definition_json!=OLD.definition_json OR NEW.created_at!=OLD.created_at OR NEW.generation!=OLD.generation+1 "
    f"OR (NEW.phase IN ({_TERMINAL}) AND OLD.phase!='stopping') "
    "OR (OLD.phase='stopping' AND (NEW.phase NOT IN ('stopping',OLD.stop_kind) "
    "OR NEW.stop_kind IS NOT OLD.stop_kind OR NEW.stop_event_key IS NOT OLD.stop_event_key OR NEW.stop_reason IS NOT OLD.stop_reason)) "
    "BEGIN SELECT RAISE(ABORT,'immutable_experiment_definition_or_state'); END",
    "CREATE TRIGGER improvement_experiment_delete BEFORE DELETE ON improvement_experiments "
    "BEGIN SELECT RAISE(ABORT,'immutable_experiment_history'); END",
    "CREATE TRIGGER improvement_experiment_arm_scope BEFORE INSERT ON improvement_experiment_arms WHEN NOT EXISTS "
    "(SELECT 1 FROM improvement_experiments e JOIN improvement_skill_candidates c ON c.id=NEW.candidate_id AND c.brain_id=e.brain_id "
    "JOIN improvement_candidate_authorities a ON a.id=NEW.authority_id AND a.brain_id=e.brain_id "
    "JOIN improvement_candidate_authority_grants g ON g.authority_id=a.id AND g.brain_id=a.brain_id "
    "WHERE e.id=NEW.experiment_id AND e.brain_id=NEW.brain_id AND c.experiment_id=e.id AND c.context_id=e.context_id "
    "AND c.target_id=e.target_id AND c.ordinal=NEW.ordinal AND a.context_id=e.context_id AND a.target_id=e.target_id "
    "AND a.base_revision_id=c.base_revision_id AND a.base_hash=c.base_hash AND a.base_generation=c.base_generation "
    "AND g.status='active' AND g.generation=NEW.authority_generation "
    "AND ((a.kind='editable_region' AND a.id=c.authority_id) "
    "OR (a.kind='exact_diff' AND a.candidate_id=c.id AND a.after_hash=c.content_hash))) "
    "BEGIN SELECT RAISE(ABORT,'experiment_arm_scope_mismatch'); END",
    "CREATE TRIGGER improvement_comparison_scope BEFORE INSERT ON improvement_comparisons WHEN NOT EXISTS "
    "(SELECT 1 FROM improvement_experiments e JOIN improvement_experiment_arms a ON a.experiment_id=e.id AND a.brain_id=e.brain_id "
    "WHERE e.id=NEW.experiment_id AND e.brain_id=NEW.brain_id AND e.definition_hash=NEW.definition_hash "
    "AND a.ordinal=NEW.ordinal AND a.envelope_hash=NEW.arm_hash) "
    "BEGIN SELECT RAISE(ABORT,'comparison_scope_mismatch'); END",
    "CREATE TRIGGER improvement_experiment_trial_scope BEFORE INSERT ON improvement_experiment_trial_links WHEN NOT EXISTS "
    "(SELECT 1 FROM improvement_comparisons c JOIN improvement_trials t ON t.id=NEW.trial_id AND t.brain_id=c.brain_id "
    "WHERE c.id=NEW.comparison_id AND c.brain_id=NEW.brain_id AND c.experiment_id=NEW.experiment_id "
    "AND NEW.cell_position<c.cell_count AND t.request_hash=NEW.request_hash "
    "AND json_extract(t.request_json,'$.pins.experiment_id')=NEW.experiment_id) "
    "BEGIN SELECT RAISE(ABORT,'experiment_trial_scope_mismatch'); END",
    "CREATE TRIGGER improvement_experiment_selection_scope BEFORE INSERT ON improvement_experiment_selections WHEN NOT EXISTS "
    "(SELECT 1 FROM improvement_experiments e WHERE e.id=NEW.experiment_id AND e.brain_id=NEW.brain_id "
    "AND e.definition_hash=NEW.definition_hash) BEGIN SELECT RAISE(ABORT,'experiment_selection_scope_mismatch'); END",
    "CREATE TRIGGER improvement_comparison_report_scope BEFORE INSERT ON improvement_comparison_reports WHEN NOT EXISTS "
    "(SELECT 1 FROM improvement_comparisons c WHERE c.id=NEW.comparison_id AND c.brain_id=NEW.brain_id "
    "AND c.experiment_id=NEW.experiment_id) BEGIN SELECT RAISE(ABORT,'comparison_report_scope_mismatch'); END",
)

IMMUTABLE = ("improvement_experiment_arms", "improvement_comparisons", "improvement_experiment_trial_links",
             "improvement_experiment_selections", "improvement_comparison_reports")
