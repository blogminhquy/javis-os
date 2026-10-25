"""M2A immutable skill proposals and separately revocable owner edit authority.

No candidate is an asset revision or executable bundle. Semantic evidence and
later trial arms are intentionally separate from these authoring records.
"""

SCHEMA = (
    "CREATE TABLE improvement_candidate_authorities("
    "id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,context_id TEXT NOT NULL,target_id TEXT NOT NULL,"
    "base_revision_id TEXT NOT NULL,base_hash TEXT NOT NULL,base_generation INTEGER NOT NULL CHECK(base_generation>0),"
    "context_generation INTEGER NOT NULL CHECK(context_generation>0),"
    "kind TEXT NOT NULL CHECK(kind IN ('editable_region','exact_diff')),start INTEGER,end INTEGER,"
    "before_hash TEXT NOT NULL,after_hash TEXT,candidate_id TEXT,source_authority_hash TEXT NOT NULL,actor TEXT NOT NULL,created_at REAL NOT NULL,"
    "UNIQUE(id,brain_id),CHECK(before_hash=base_hash),"
    "CHECK((kind='editable_region' AND start IS NOT NULL AND end IS NOT NULL AND start>=0 AND end>=start "
    "AND after_hash IS NULL AND candidate_id IS NULL) OR (kind='exact_diff' AND start IS NULL AND end IS NULL "
    "AND after_hash IS NOT NULL AND candidate_id IS NOT NULL)),"
    "FOREIGN KEY(context_id,brain_id) REFERENCES improvement_trial_contexts(id,brain_id),"
    "FOREIGN KEY(target_id,brain_id) REFERENCES improvement_targets(id,brain_id),"
    "FOREIGN KEY(base_revision_id,brain_id) REFERENCES improvement_revisions(id,brain_id),"
    "FOREIGN KEY(candidate_id,brain_id) REFERENCES improvement_skill_candidates(id,brain_id))",
    "CREATE TABLE improvement_candidate_authority_grants("
    "authority_id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,generation INTEGER NOT NULL,"
    "status TEXT NOT NULL CHECK(status IN ('active','revoked')),revoked_at REAL,"
    "CHECK((status='active' AND generation=1 AND revoked_at IS NULL) OR "
    "(status='revoked' AND generation=2 AND revoked_at IS NOT NULL)),"
    "FOREIGN KEY(authority_id,brain_id) REFERENCES improvement_candidate_authorities(id,brain_id))",
    "CREATE TABLE improvement_skill_candidates("
    "id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,context_id TEXT NOT NULL,experiment_id TEXT NOT NULL,"
    "target_id TEXT NOT NULL,base_revision_id TEXT NOT NULL,base_hash TEXT NOT NULL,"
    "base_generation INTEGER NOT NULL CHECK(base_generation>0),ordinal INTEGER NOT NULL CHECK(ordinal IN (1,2)),"
    "content_hash TEXT NOT NULL,byte_size INTEGER NOT NULL CHECK(byte_size BETWEEN 0 AND 1048576),"
    "patch_hash TEXT NOT NULL,provenance_hash TEXT NOT NULL,authority_id TEXT,authority_generation INTEGER,"
    "semantic_status TEXT NOT NULL CHECK(semantic_status='unreviewed'),owner_event_key TEXT NOT NULL,created_at REAL NOT NULL,"
    "UNIQUE(id,brain_id),UNIQUE(brain_id,experiment_id,ordinal),"
    "CHECK((authority_id IS NULL AND authority_generation IS NULL) OR "
    "(authority_id IS NOT NULL AND authority_generation=1)),"
    "FOREIGN KEY(context_id,brain_id) REFERENCES improvement_trial_contexts(id,brain_id),"
    "FOREIGN KEY(target_id,brain_id) REFERENCES improvement_targets(id,brain_id),"
    "FOREIGN KEY(base_revision_id,brain_id) REFERENCES improvement_revisions(id,brain_id),"
    "FOREIGN KEY(authority_id,brain_id) REFERENCES improvement_candidate_authorities(id,brain_id),"
    "FOREIGN KEY(brain_id,owner_event_key) REFERENCES improvement_events(brain_id,event_key) DEFERRABLE INITIALLY DEFERRED)",
    "CREATE INDEX improvement_candidates_context ON improvement_skill_candidates(brain_id,context_id,ordinal)",
    "CREATE INDEX improvement_authorities_candidate ON improvement_candidate_authorities(brain_id,candidate_id)",
    "CREATE TRIGGER improvement_candidate_base BEFORE INSERT ON improvement_skill_candidates WHEN NOT EXISTS "
    "(SELECT 1 FROM improvement_revisions r JOIN improvement_targets t ON t.id=r.target_id AND t.brain_id=r.brain_id "
    "JOIN improvement_trial_contexts c ON c.id=NEW.context_id AND c.brain_id=NEW.brain_id "
    "JOIN improvement_trial_context_grants g ON g.context_id=c.id AND g.brain_id=c.brain_id "
    "WHERE r.id=NEW.base_revision_id AND r.brain_id=NEW.brain_id AND r.target_id=NEW.target_id "
    "AND r.content_hash=NEW.base_hash AND t.kind='skill' AND t.status='live' AND g.status='active' "
    "AND t.current_revision_id=NEW.base_revision_id AND t.generation=NEW.base_generation "
    "AND c.experiment_id=NEW.experiment_id "
    "AND EXISTS(SELECT 1 FROM json_each(c.target_generations_json) WHERE key=NEW.target_id AND value=NEW.base_generation)) "
    "BEGIN SELECT RAISE(ABORT,'candidate_base_mismatch'); END",
    "CREATE TRIGGER improvement_candidate_region BEFORE INSERT ON improvement_skill_candidates "
    "WHEN NEW.authority_id IS NOT NULL AND NOT EXISTS "
    "(SELECT 1 FROM improvement_candidate_authorities a JOIN improvement_candidate_authority_grants g ON g.authority_id=a.id "
    "AND g.brain_id=a.brain_id WHERE a.id=NEW.authority_id AND a.brain_id=NEW.brain_id AND a.context_id=NEW.context_id "
    "AND a.target_id=NEW.target_id AND a.base_revision_id=NEW.base_revision_id AND a.base_hash=NEW.base_hash "
    "AND a.base_generation=NEW.base_generation AND a.kind='editable_region' AND g.status='active' "
    "AND g.generation=NEW.authority_generation) BEGIN SELECT RAISE(ABORT,'candidate_authority_mismatch'); END",
    "CREATE TRIGGER improvement_candidate_authority_base BEFORE INSERT ON improvement_candidate_authorities WHEN NOT EXISTS "
    "(SELECT 1 FROM improvement_revisions r JOIN improvement_targets t ON t.id=r.target_id AND t.brain_id=r.brain_id "
    "JOIN improvement_trial_contexts c ON c.id=NEW.context_id AND c.brain_id=NEW.brain_id "
    "JOIN improvement_trial_context_grants g ON g.context_id=c.id AND g.brain_id=c.brain_id "
    "WHERE r.id=NEW.base_revision_id AND r.brain_id=NEW.brain_id AND r.target_id=NEW.target_id "
    "AND r.content_hash=NEW.base_hash AND t.kind='skill' AND t.status='live' AND g.status='active' "
    "AND t.current_revision_id=NEW.base_revision_id AND t.generation=NEW.base_generation AND g.generation=NEW.context_generation "
    "AND EXISTS(SELECT 1 FROM json_each(c.target_generations_json) WHERE key=NEW.target_id AND value=NEW.base_generation)) "
    "BEGIN SELECT RAISE(ABORT,'candidate_authority_base_mismatch'); END",
    "CREATE TRIGGER improvement_candidate_authority_diff BEFORE INSERT ON improvement_candidate_authorities "
    "WHEN NEW.kind='exact_diff' AND NOT EXISTS(SELECT 1 FROM improvement_skill_candidates s WHERE s.id=NEW.candidate_id "
    "AND s.brain_id=NEW.brain_id AND s.context_id=NEW.context_id AND s.target_id=NEW.target_id "
    "AND s.base_revision_id=NEW.base_revision_id AND s.base_hash=NEW.before_hash "
    "AND s.base_generation=NEW.base_generation AND s.content_hash=NEW.after_hash) "
    "BEGIN SELECT RAISE(ABORT,'candidate_authority_diff_mismatch'); END",
    "CREATE TRIGGER improvement_candidate_grant_update BEFORE UPDATE ON improvement_candidate_authority_grants "
    "WHEN OLD.status!='active' OR NEW.status!='revoked' OR NEW.generation!=OLD.generation+1 "
    "OR NEW.authority_id!=OLD.authority_id OR NEW.brain_id!=OLD.brain_id OR NEW.revoked_at IS NULL "
    "BEGIN SELECT RAISE(ABORT,'immutable_candidate_authority'); END",
    "CREATE TRIGGER improvement_candidate_grant_delete BEFORE DELETE ON improvement_candidate_authority_grants "
    "BEGIN SELECT RAISE(ABORT,'immutable_candidate_authority'); END",
)

IMMUTABLE = ("improvement_candidate_authorities", "improvement_skill_candidates")
