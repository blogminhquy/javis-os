"""M1 durable execution references in the existing improvement/resonance database."""

SCHEMA = (
    "CREATE TABLE improvement_trials(id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,logical_key TEXT NOT NULL,"
    "request_hash TEXT NOT NULL,request_json TEXT NOT NULL,status TEXT NOT NULL,generation INTEGER NOT NULL,"
    "attempt INTEGER NOT NULL,created_at REAL NOT NULL,updated_at REAL NOT NULL,"
    "UNIQUE(brain_id,logical_key),UNIQUE(id,brain_id))",
    "CREATE TABLE improvement_trial_attempts(trial_id TEXT NOT NULL,brain_id TEXT NOT NULL,attempt INTEGER NOT NULL,"
    "status TEXT NOT NULL,call_id INTEGER NOT NULL UNIQUE,lease_token TEXT,lease_until REAL,writer_hash TEXT,engine_at REAL,"
    "materialization_hash TEXT,workspace_json TEXT,result_json TEXT,failure_reason TEXT,created_at REAL NOT NULL,updated_at REAL NOT NULL,"
    "PRIMARY KEY(trial_id,attempt),FOREIGN KEY(trial_id,brain_id) REFERENCES improvement_trials(id,brain_id),"
    "FOREIGN KEY(call_id) REFERENCES agent_calls(id))",
    "CREATE TABLE improvement_trial_observations(trial_id TEXT NOT NULL,brain_id TEXT NOT NULL,attempt INTEGER NOT NULL,"
    "sequence INTEGER NOT NULL,kind TEXT NOT NULL,payload_hash TEXT NOT NULL,blob_hashes_json TEXT NOT NULL,late INTEGER NOT NULL,"
    "created_at REAL NOT NULL,PRIMARY KEY(trial_id,attempt,sequence),"
    "FOREIGN KEY(trial_id,brain_id) REFERENCES improvement_trials(id,brain_id),"
    "FOREIGN KEY(trial_id,attempt) REFERENCES improvement_trial_attempts(trial_id,attempt))",
    "CREATE TABLE improvement_trial_results(id TEXT PRIMARY KEY,trial_id TEXT NOT NULL,brain_id TEXT NOT NULL,"
    "attempt INTEGER NOT NULL,result_hash TEXT NOT NULL,blob_hash TEXT NOT NULL,created_at REAL NOT NULL,"
    "UNIQUE(trial_id,attempt,result_hash),FOREIGN KEY(trial_id,brain_id) REFERENCES improvement_trials(id,brain_id),"
    "FOREIGN KEY(trial_id,attempt) REFERENCES improvement_trial_attempts(trial_id,attempt))",
    "CREATE TABLE improvement_trial_owner_decisions(id INTEGER PRIMARY KEY AUTOINCREMENT,trial_id TEXT NOT NULL,"
    "brain_id TEXT NOT NULL,attempt INTEGER NOT NULL,criterion_id TEXT NOT NULL,output_hash TEXT NOT NULL,"
    "contract_hash TEXT NOT NULL,verdict TEXT NOT NULL CHECK(verdict IN ('pass','fail','unknown')),"
    "actor TEXT NOT NULL,created_at REAL NOT NULL,"
    "FOREIGN KEY(trial_id,brain_id) REFERENCES improvement_trials(id,brain_id),"
    "FOREIGN KEY(trial_id,attempt) REFERENCES improvement_trial_attempts(trial_id,attempt))",
    "CREATE TABLE improvement_trial_artifacts(trial_id TEXT NOT NULL,brain_id TEXT NOT NULL,attempt INTEGER NOT NULL,"
    "path TEXT NOT NULL,content_hash TEXT NOT NULL,byte_size INTEGER NOT NULL,created_at REAL NOT NULL,"
    "PRIMARY KEY(trial_id,attempt),FOREIGN KEY(trial_id,brain_id) REFERENCES improvement_trials(id,brain_id),"
    "FOREIGN KEY(trial_id,attempt) REFERENCES improvement_trial_attempts(trial_id,attempt))",
    "CREATE TABLE improvement_trial_receipts(trial_id TEXT NOT NULL,brain_id TEXT NOT NULL,attempt INTEGER NOT NULL,"
    "content_hash TEXT NOT NULL,created_at REAL NOT NULL,PRIMARY KEY(trial_id,attempt),"
    "FOREIGN KEY(trial_id,brain_id) REFERENCES improvement_trials(id,brain_id),"
    "FOREIGN KEY(trial_id,attempt) REFERENCES improvement_trial_attempts(trial_id,attempt))",
    "CREATE TABLE improvement_trial_contexts(id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,experiment_id TEXT NOT NULL,"
    "request_hash TEXT NOT NULL,context_hash TEXT NOT NULL,binding_hash TEXT NOT NULL,blob_hashes_json TEXT NOT NULL,"
    "scope_hash TEXT NOT NULL,grant_hash TEXT NOT NULL,engine_config_hash TEXT NOT NULL,policy_version INTEGER NOT NULL,"
    "target_generations_json TEXT NOT NULL,created_at REAL NOT NULL,UNIQUE(brain_id,experiment_id),UNIQUE(id,brain_id))",
    "CREATE TABLE improvement_trial_context_grants(context_id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,"
    "generation INTEGER NOT NULL,status TEXT NOT NULL CHECK(status IN ('active','revoked')),revoked_at REAL,"
    "FOREIGN KEY(context_id,brain_id) REFERENCES improvement_trial_contexts(id,brain_id))",
)

IMMUTABLE = ("improvement_trial_observations", "improvement_trial_artifacts", "improvement_trial_receipts",
             "improvement_trial_owner_decisions", "improvement_trial_results", "improvement_trial_contexts")
