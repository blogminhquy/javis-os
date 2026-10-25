"""Schema4 preserves actual M1 records; candidate metadata never decrypts private bodies."""
from _paths import ROOT, SERVER  # noqa: F401

import hashlib
import importlib.util
import json
import sqlite3
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from unittest.mock import patch

import improvement_store as IM
import improvement_case_schema as CASE_SCHEMA
import improvement_trial_schema as TRIAL_SCHEMA
import test_improvement_trial_host as fixtures

if importlib.util.find_spec("improvement_candidate_records"):
    from improvement_candidate_records import CandidateRecords
    import improvement_candidate_schema as CANDIDATE_SCHEMA
else:
    CandidateRecords = CANDIDATE_SCHEMA = None


def legacy_ensure(store):
    """Install the three released schema blocks, without consulting a new dispatcher."""
    with store._Tx(store) as connection:
        if connection.execute("SELECT 1 FROM sqlite_master WHERE name='improvement_schema'").fetchone():
            return
        for statements, immutable in (
            (IM._SCHEMA, ("improvement_revisions", "improvement_bundles", "improvement_bundle_assets", "improvement_events")),
            (CASE_SCHEMA.SCHEMA, CASE_SCHEMA.IMMUTABLE),
            (TRIAL_SCHEMA.SCHEMA, TRIAL_SCHEMA.IMMUTABLE),
        ):
            for statement in statements:
                connection.execute(statement)
            IM._immutable_triggers(connection, immutable)
        connection.execute("INSERT INTO improvement_schema VALUES(1,3)")


class CandidateRecordTests(unittest.TestCase):
    def setUp(self):
        # Real encrypted host bindings, case sets, contract, call ledger and a reserved trial.
        with patch.object(IM, "ensure", side_effect=legacy_ensure):
            self.h = fixtures.HostContextTests()
            self.h.setUp()
            self.context = self.h.create()
            self.f = self.h.f
            self.request = self.h.request(self.context)
            self.trial = self.f.trials.reserve(self.f.owner, self.request, event_key="legacy-reserved-trial")
            self.qualification = self.f.cases.reserve_qualification(self.f.owner, self.request["case_set_id"],
                self.request["pins"], event_key="legacy-private-qualification")
        self.rs, self.assets, self.owner = self.f.rs, self.f.assets, self.f.owner
        with closing(self.rs._conn()) as connection:
            self.target = dict(connection.execute("SELECT * FROM improvement_targets WHERE brain_id=? AND status='live'",
                                                  (self.owner.brain_id,)).fetchone())
        self.before = self.history()

    def records(self):
        self.assertIsNotNone(CandidateRecords, "Owner-scoped candidate records have not been implemented")
        return CandidateRecords(self.assets)

    def history(self):
        with closing(self.rs._conn()) as connection:
            names = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' "
                "AND (name LIKE 'improvement_%' OR name='agent_calls') ORDER BY name")]
            return {name: [tuple(row) for row in connection.execute('SELECT * FROM "' + name + '" ORDER BY rowid')]
                    for name in names if name != "improvement_schema"}

    def files(self):
        # SQLite's own -wal/-shm journals come and go with the last open connection (garbage collection timing
        # differs per platform); they are not a migration. Schema version and table history are checked below.
        return {str(path.relative_to(self.f.root)) for path in self.f.root.rglob("*")
                if path.is_file() and not path.name.endswith(("-wal", "-shm"))}

    def test_schema3_cold_reads_do_not_migrate(self):
        records = self.records()
        before_files = self.files()
        with patch.object(self.assets.blobs, "read", side_effect=AssertionError("Cold metadata cannot decrypt")):
            self.assertEqual(records.list(self.owner, "experiment-host"), [])
            with self.assertRaises(PermissionError):
                records.get(self.owner, "candidate-absent")
            page = records.contexts(self.owner, "skills/report/SKILL.md")
            self.assertEqual([item["experiment_id"] for item in page["items"]], ["experiment-host"])
            self.assertEqual(page["items"][0]["grant_status"], "active")
        self.assertEqual(IM._schema_version(self.rs), 3)
        self.assertEqual(self.history(), self.before)
        self.assertEqual(before_files, self.files())

    def test_latest_upgrade_preserves_real_m1_trial_history(self):
        IM.ensure(self.rs)
        self.assertEqual(IM._schema_version(self.rs), IM.SCHEMA_VERSION, "Upgrade must include candidate history")
        after = self.history()
        self.assertEqual({name: after[name] for name in self.before}, self.before)
        self.assertEqual(self.f.trials.get(self.owner, self.trial["trial_id"])["status"], "reserved")
        self.assertEqual(self.h.host.get(self.owner, "experiment-host"), self.context)
        backup = self.rs.path.with_name(self.rs.path.name + ".pre-improvement-m2-experiments.bak")
        self.assertTrue(backup.is_file(), "Existing schema3 needs a recoverable complete pre-upgrade backup")
        with closing(sqlite3.connect(backup)) as connection:
            self.assertEqual(connection.execute("SELECT version FROM improvement_schema").fetchone()[0], 3)
            self.assertEqual(connection.execute("SELECT id FROM improvement_trials").fetchone()[0], self.trial["trial_id"])
        # Idempotent upgrade must not replay installed immutable triggers or rewrite backup.
        digest = hashlib.sha256(backup.read_bytes()).hexdigest()
        IM.ensure(self.rs)
        self.assertEqual(hashlib.sha256(backup.read_bytes()).hexdigest(), digest)

    def test_concurrent_upgrade_has_one_serialized_backup(self):
        gate, backups = threading.Barrier(2), []
        original = self.rs._backup_before

        def backup(*args):
            backups.append(args)
            return original(*args)

        def migrate(_):
            gate.wait()
            IM.ensure(self.rs)

        with patch.object(self.rs, "_backup_before", side_effect=backup), ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(migrate, (1, 2)))
        self.assertEqual(backups, [("improvement_compositions", ".pre-improvement-m2-compose.bak"),
                                   ("improvement_experiments", ".pre-improvement-m2-experiments.bak"),
                                   ("improvement_preparations", ".pre-improvement-m2-generated.bak"),
                                   ("improvement_effective_views", ".pre-improvement-m2-views.bak")])
        for _, suffix in backups:
            with closing(sqlite3.connect(self.rs.path.with_name(self.rs.path.name + suffix))) as connection:
                self.assertEqual(connection.execute("SELECT version FROM improvement_schema").fetchone()[0], 3)
                self.assertEqual(connection.execute("SELECT id FROM improvement_trials").fetchone()[0], self.trial["trial_id"])
        self.assertEqual(IM._schema_version(self.rs), IM.SCHEMA_VERSION)
        self.assertEqual({name: self.history()[name] for name in self.before}, self.before)

    def test_failed_upgrade_rolls_back(self):
        self.assertIsNotNone(CANDIDATE_SCHEMA, "The candidate migration is absent")
        with patch.object(CANDIDATE_SCHEMA, "SCHEMA", (*CANDIDATE_SCHEMA.SCHEMA, "INVALID CANDIDATE MIGRATION")):
            with self.assertRaises(sqlite3.OperationalError):
                IM.ensure(self.rs)
        self.assertEqual(IM._schema_version(self.rs), 3)
        self.assertEqual(self.history(), self.before)
        IM.ensure(self.rs)
        self.assertEqual(IM._schema_version(self.rs), IM.SCHEMA_VERSION)

    def seed(self):
        """Seed records through real SQL to test constraints before owner staging exists."""
        IM.ensure(self.rs)
        records = self.records()
        target = self.target
        with self.rs._Tx(self.rs) as connection:
            connection.execute("INSERT INTO improvement_candidate_authorities "
                "(id,brain_id,context_id,target_id,base_revision_id,base_hash,base_generation,context_generation,"
                "kind,start,end,before_hash,after_hash,candidate_id,source_authority_hash,actor,created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    "ica-test-region", self.owner.brain_id, self.context["context_id"], target["id"],
                    target["current_revision_id"], target["source_hash"], target["generation"], 1,
                    "editable_region", 0, 1, target["source_hash"], None, None, "d" * 64, self.owner.by, 1.0))
            connection.execute("INSERT INTO improvement_candidate_authority_grants VALUES(?,?,1,'active',NULL)",
                               ("ica-test-region", self.owner.brain_id))
            connection.execute("INSERT INTO improvement_skill_candidates "
                "(id,brain_id,context_id,experiment_id,target_id,base_revision_id,base_hash,base_generation,ordinal,"
                "content_hash,byte_size,patch_hash,provenance_hash,authority_id,authority_generation,semantic_status,"
                "owner_event_key,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    "isc-test-1", self.owner.brain_id, self.context["context_id"], "experiment-host", target["id"],
                    target["current_revision_id"], target["source_hash"], target["generation"], 1,
                    "a" * 64, 10, "b" * 64, "c" * 64, "ica-test-region", 1, "unreviewed", "seed-candidate-event", 1.0))
            self.assets._event(connection, self.owner, "seed-candidate-event", "skill_candidate_stage", {}, {"candidate_id": "isc-test-1"})
        return records

    def test_foreign_brain_and_revoked_authority_do_not_read_private_records(self):
        records = self.seed()
        with patch.object(self.assets.blobs, "read", side_effect=AssertionError("No private read in metadata")):
            metadata = records.get(self.owner, "isc-test-1")
            self.assertEqual(metadata["semantic_status"], "unreviewed")
            self.assertEqual(metadata["edit_authority"]["status"], "active")
            self.assertEqual(len(records.list(self.owner, "experiment-host")), 1)
            with self.assertRaises(PermissionError):
                records.get(self.f.other, "isc-test-1")
            self.assertEqual(records.list(self.f.other, "experiment-host"), [])
            revoked = records.revoke_authority(self.owner, "ica-test-region", expected_generation=1, event_key="revoke-edit-region")
            self.assertEqual(revoked["status"], "revoked")
            self.assertEqual(revoked["generation"], 2)
            self.assertEqual(records.get(self.owner, "isc-test-1")["edit_authority"]["status"], "revoked")
            self.assertEqual(records.revoke_authority(self.owner, "ica-test-region", expected_generation=1,
                                                     event_key="revoke-edit-region"), revoked)
            with self.assertRaises(IM.ConflictError):
                records.revoke_authority(self.owner, "ica-test-region", expected_generation=1, event_key="revoke-stale-region")
        projection = json.dumps(metadata)
        for private in ("replacement", "provenance_json", "body", "private-answer", "root", "cli_path"):
            self.assertNotIn(private, projection)
        self.assertEqual(self.h.host.get(self.owner, "experiment-host")["grant_status"], "active")

    def test_candidate_history_and_authority_scope_cannot_be_rewritten(self):
        self.seed()
        with self.rs._Tx(self.rs) as connection:
            for statement in (
                "UPDATE improvement_skill_candidates SET ordinal=2",
                "DELETE FROM improvement_skill_candidates",
                "UPDATE improvement_candidate_authorities SET start=1",
                "DELETE FROM improvement_candidate_authorities",
                "UPDATE improvement_candidate_authority_grants SET generation=99",
                "DELETE FROM improvement_candidate_authority_grants",
            ):
                with self.subTest(statement=statement), self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(statement)
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO improvement_skill_candidates SELECT 'isc-duplicate',brain_id,context_id,"
                    "experiment_id,target_id,base_revision_id,base_hash,base_generation,ordinal,content_hash,byte_size,"
                    "patch_hash,provenance_hash,authority_id,authority_generation,semantic_status,owner_event_key,created_at "
                    "FROM improvement_skill_candidates")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE improvement_candidate_authority_grants SET brain_id='brain-b',status='revoked',"
                                   "generation=2,revoked_at=2")

    def test_context_listing_is_scoped_paged_and_does_not_decrypt(self):
        records = self.records()
        with patch.object(self.assets.blobs, "read", side_effect=AssertionError("No binding decrypt")):
            self.assertEqual(records.contexts(self.f.other, "skills/report/SKILL.md")["items"], [])
            self.assertEqual(records.contexts(self.owner, "skills/other/SKILL.md")["items"], [])
            first = records.contexts(self.owner, "skills/report/SKILL.md", limit=1)
            self.assertEqual(len(first["items"]), 1)
            self.assertNotIn("baseline_context", first["items"][0])
            for changes in ({"limit": True}, {"limit": 0}, {"limit": 101}, {"cursor": "../path"}):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    records.contexts(self.owner, "skills/report/SKILL.md", **changes)
        with self.assertRaises(ValueError):
            records.contexts(self.owner, "agents/report.md")

    def test_context_pagination_and_objectives_use_existing_association_only(self):
        records = self.records()
        second = self.h.host.create(self.owner, "experiment-another", self.h.capture["surface"], self.h.target_ids,
                                   source_refs=list(self.h.fixture_content), event_key="create-second-context")
        with self.rs._Tx(self.rs) as connection:
            contract = connection.execute("SELECT * FROM improvement_contracts WHERE brain_id=?", (self.owner.brain_id,)).fetchone()
            association = {"context_id": self.context["context_id"], "experiment_id": "experiment-host",
                "contract_id": contract["id"], "contract_hash": contract["manifest_hash"],
                "case_set_id": self.request["case_set_id"], "manifest_hash": self.request["pins"]["case_set_hash"],
                "counts": {"tuning": 1, "qualification": 1, "regression": 1}, "grant_hash": self.context["grant_hash"]}
            self.assets._event(connection, self.owner, "link-public-objective", "owner_trial_case_set", {}, association)
        with patch.object(self.assets.blobs, "read", side_effect=AssertionError("No encrypted source or private answer read")):
            one = records.contexts(self.owner, "skills/report/SKILL.md", limit=1)
            two = records.contexts(self.owner, "skills/report/SKILL.md", limit=1, cursor=one["next_cursor"])
            self.assertIsNotNone(one["next_cursor"])
            self.assertIsNone(two["next_cursor"])
            rows = {row["context_id"]: row for row in one["items"] + two["items"]}
            self.assertEqual(set(rows), {self.context["context_id"], second["context_id"]})
            self.assertEqual(rows[self.context["context_id"]]["objectives"],
                             [{"contract_id": contract["id"], "objective": json.loads(contract["contract_json"])["objective"]}])
            self.assertEqual(rows[second["context_id"]]["objectives"], [])

    def test_unknown_newer_schema_rejects_before_backup_or_writes(self):
        with self.rs._Tx(self.rs) as connection:
            connection.execute("UPDATE improvement_schema SET version=999")
        with patch.object(self.rs, "_backup_before", side_effect=AssertionError("Unknown schema must not be touched")):
            with self.assertRaisesRegex(IM.SchemaError, "unsupported_improvement_schema"):
                IM.ensure(self.rs)
            with self.assertRaises(IM.SchemaError):
                self.records().list(self.owner, "experiment-host")
        with closing(self.rs._conn()) as connection:
            self.assertEqual(connection.execute("SELECT version FROM improvement_schema").fetchone()[0], 999)

    def test_revoked_context_cannot_receive_a_new_diff_only_candidate(self):
        records = self.seed()
        self.h.host.revoke(self.owner, "experiment-host", expected_generation=1, event_key="revoke-context-before-candidate")
        # Existing metadata remains historical, but SQL itself prevents a new proposal under that grant.
        self.assertEqual(records.get(self.owner, "isc-test-1")["context_grant"]["status"], "revoked")
        with self.rs._Tx(self.rs) as connection, self.assertRaises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO improvement_skill_candidates SELECT 'isc-revoked',brain_id,context_id,"
                "experiment_id,target_id,base_revision_id,base_hash,base_generation,2,content_hash,byte_size,"
                "patch_hash,provenance_hash,NULL,NULL,semantic_status,owner_event_key,created_at "
                "FROM improvement_skill_candidates WHERE id='isc-test-1'")

    def test_two_ordinal_slots_accept_two_candidates_and_reject_a_third(self):
        self.seed()
        with self.rs._Tx(self.rs) as connection:
            connection.execute("INSERT INTO improvement_skill_candidates SELECT 'isc-test-2',brain_id,context_id,"
                "experiment_id,target_id,base_revision_id,base_hash,base_generation,2,content_hash,byte_size,"
                "patch_hash,provenance_hash,NULL,NULL,semantic_status,owner_event_key,created_at FROM improvement_skill_candidates")
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM improvement_skill_candidates").fetchone()[0], 2)
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO improvement_skill_candidates SELECT 'isc-third',brain_id,context_id,"
                    "experiment_id,target_id,base_revision_id,base_hash,base_generation,3,content_hash,byte_size,"
                    "patch_hash,provenance_hash,NULL,NULL,semantic_status,owner_event_key,created_at "
                    "FROM improvement_skill_candidates WHERE id='isc-test-1'")

    def test_foreign_revoke_and_missing_origin_event_leave_no_partial_write(self):
        records = self.seed()
        before = self.history()
        with self.assertRaises(PermissionError):
            records.revoke_authority(self.f.other, "ica-test-region", expected_generation=1, event_key="foreign-edit-revoke")
        with self.assertRaises(sqlite3.IntegrityError), self.rs._Tx(self.rs) as connection:
            connection.execute("INSERT INTO improvement_skill_candidates SELECT 'isc-orphan',brain_id,context_id,"
                "experiment_id,target_id,base_revision_id,base_hash,base_generation,2,content_hash,byte_size,"
                "patch_hash,provenance_hash,NULL,NULL,semantic_status,'missing-owner-event',created_at "
                "FROM improvement_skill_candidates WHERE id='isc-test-1'")
        self.assertEqual(self.history(), before)


if __name__ == "__main__":
    unittest.main()
