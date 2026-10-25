"""M1 immutable input and qualification tables in the shared improvement database."""

SCHEMA = (
    "CREATE TABLE improvement_contracts(id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,manifest_hash TEXT NOT NULL,"
    "contract_json TEXT NOT NULL,created_at REAL NOT NULL,UNIQUE(brain_id,manifest_hash),UNIQUE(id,brain_id))",
    "CREATE TABLE improvement_snapshots(id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,manifest_hash TEXT NOT NULL,"
    "manifest_json TEXT NOT NULL,source_hash TEXT NOT NULL,fixture_hash TEXT NOT NULL,status TEXT NOT NULL "
    "CHECK(status IN ('sufficient','insufficient_source')),created_at REAL NOT NULL,"
    "UNIQUE(brain_id,manifest_hash),UNIQUE(id,brain_id))",
    "CREATE TABLE improvement_case_sets(id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,manifest_hash TEXT NOT NULL,"
    "manifest_json TEXT NOT NULL,created_at REAL NOT NULL,UNIQUE(brain_id,manifest_hash),UNIQUE(id,brain_id))",
    "CREATE TABLE improvement_cases(case_set_id TEXT NOT NULL,id TEXT NOT NULL,brain_id TEXT NOT NULL,"
    "split TEXT NOT NULL CHECK(split IN ('tuning','qualification','regression')),case_json TEXT NOT NULL,"
    "PRIMARY KEY(case_set_id,id),UNIQUE(case_set_id,id,brain_id),"
    "FOREIGN KEY(case_set_id,brain_id) REFERENCES improvement_case_sets(id,brain_id))",
    "CREATE TABLE improvement_case_sources(case_set_id TEXT NOT NULL,case_id TEXT NOT NULL,brain_id TEXT NOT NULL,"
    "snapshot_id TEXT NOT NULL,PRIMARY KEY(case_set_id,case_id,snapshot_id),"
    "FOREIGN KEY(case_set_id,case_id,brain_id) REFERENCES improvement_cases(case_set_id,id,brain_id),"
    "FOREIGN KEY(snapshot_id,brain_id) REFERENCES improvement_snapshots(id,brain_id))",
    "CREATE TABLE improvement_case_families(case_set_id TEXT NOT NULL,case_id TEXT NOT NULL,brain_id TEXT NOT NULL,"
    "fingerprint TEXT NOT NULL,split TEXT NOT NULL,PRIMARY KEY(case_set_id,case_id,fingerprint),"
    "FOREIGN KEY(case_set_id,case_id,brain_id) REFERENCES improvement_cases(case_set_id,id,brain_id))",
    "CREATE INDEX improvement_family_lookup ON improvement_case_families(brain_id,fingerprint,split)",
    "CREATE TABLE improvement_qualification(id TEXT PRIMARY KEY,brain_id TEXT NOT NULL,case_set_id TEXT NOT NULL,"
    "pins_hash TEXT NOT NULL,pins_json TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('reserved','consumed')),"
    "created_at REAL NOT NULL,consumed_at REAL,UNIQUE(brain_id,case_set_id),UNIQUE(id,brain_id),"
    "FOREIGN KEY(case_set_id,brain_id) REFERENCES improvement_case_sets(id,brain_id))",
    "CREATE TABLE improvement_qualification_claims(brain_id TEXT NOT NULL,fingerprint TEXT NOT NULL,"
    "reservation_id TEXT NOT NULL,PRIMARY KEY(brain_id,fingerprint),"
    "FOREIGN KEY(reservation_id,brain_id) REFERENCES improvement_qualification(id,brain_id))",
    "CREATE TABLE improvement_case_exposures(brain_id TEXT NOT NULL,fingerprint TEXT NOT NULL,case_set_id TEXT NOT NULL,"
    "created_at REAL NOT NULL,PRIMARY KEY(brain_id,fingerprint),"
    "FOREIGN KEY(case_set_id,brain_id) REFERENCES improvement_case_sets(id,brain_id))",
    "CREATE TRIGGER improvement_qualification_update BEFORE UPDATE ON improvement_qualification "
    "WHEN OLD.status!='reserved' OR NEW.status!='consumed' OR NEW.id!=OLD.id OR NEW.brain_id!=OLD.brain_id "
    "OR NEW.case_set_id!=OLD.case_set_id OR NEW.pins_hash!=OLD.pins_hash OR NEW.pins_json!=OLD.pins_json "
    "OR NEW.created_at!=OLD.created_at OR NEW.consumed_at IS NULL "
    "BEGIN SELECT RAISE(ABORT,'immutable_qualification_pin'); END",
    "CREATE TRIGGER improvement_qualification_delete BEFORE DELETE ON improvement_qualification "
    "BEGIN SELECT RAISE(ABORT,'immutable_qualification_pin'); END",
)

IMMUTABLE = ("improvement_contracts", "improvement_snapshots", "improvement_case_sets", "improvement_cases",
             "improvement_case_sources", "improvement_case_families", "improvement_qualification_claims",
             "improvement_case_exposures")
