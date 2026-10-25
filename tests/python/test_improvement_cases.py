"""Immutable trial inputs, private splits and qualification claims use real scratch SQLite."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import hashlib
import importlib.util
import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

TEST_ROOT = Path(tempfile.mkdtemp(prefix="improvement-cases-"))
for key, name in {"JAVIS_STATE_DIR": "state", "BRAINS_DIR": "brains", "OBSIDIAN_VAULT_PATH": "vault",
                  "BRAIN_PATH": "brain", "SOURCES_PATH": "sources"}.items():
    os.environ[key] = str(TEST_ROOT / name)

import resonance_store as RS  # noqa: E402
import improvement_store as IM  # noqa: E402
from improvement_blobs import RevisionBlobs  # noqa: E402

if importlib.util.find_spec("improvement_cases"):
    import improvement_cases as IC
else:
    IC = None


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


class ImprovementCaseTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(IC, "Immutable trial case services are not implemented")
        self.root = Path(tempfile.mkdtemp(prefix="case-", dir=TEST_ROOT))
        self.rs = RS.GoalStore(self.root / "resonance.sqlite3")
        self.assets = IM.ImprovementStore(self.rs, RevisionBlobs(self.root / "assets"))
        self.cases = IC.CaseStore(self.assets)
        self.owner = RS.Principal("owner", "owner", "brain-a")
        self.other = RS.Principal("owner", "owner", "brain-b")

    def contract(self):
        return {"version": 1, "objective": "Report the authorized input accurately as JSON.",
            "output": {"kind": "text", "path": "answer.json", "media_type": "application/json"}, "criteria": [
            {"id": "shape", "category": "mandatory", "critical": True, "kind": "json_keys",
             "description": "Return an object with the value field.",
             "config": {"path": "answer.json", "keys": ["value"]}},
            {"id": "content", "category": "business", "critical": True, "kind": "owner_confirm",
             "description": "The value must accurately represent the authorized input.",
             "config": {"path": "answer.json"}}],
            "primary_metric": {"criterion_id": "content", "direction": "higher", "aggregation": "all_pass"},
            "evaluator": {"id": "trial-evaluator", "version": "1", "hash": digest("host-evaluator-v1")},
            "unknown_conditions": ["missing_artifact", "config_unknown", "unverified_installation"],
            "output_hash_policy": "raw_sha256"}

    def snapshot(self, index, *, raw=None, fixture=None, **changes):
        raw = f"visible-input-{index}".encode() if raw is None else raw
        fixture = raw if fixture is None else fixture
        manifest = {"version": 1, "source_ref": f"source:{index}", "source_version": "v1",
                    "captured_at": "2026-10-22T10:00:00+07:00", "timezone": "Asia/Ho_Chi_Minh",
                    "data_period": "2026-09", "cutoff": "2026-09-30T23:59:59+07:00", "schema": "text/plain",
                    "grant_hash": digest("grant-a"), "freshness": "current", "redaction": "none",
                    "sufficient_source": True, **changes}
        return self.cases.put_snapshot(self.owner, manifest, raw, fixture, event_key=f"snapshot-{index}")

    def case(self, index, split, **changes):
        snapshot = self.snapshot(index)
        return {"id": f"case-{index}", "family_key": f"family-{index}", "split": split,
                "task": f"Report input {index}", "snapshot_ids": [snapshot["snapshot_id"]],
                "answer": {"expected": f"private-answer-{index}"}, "evaluator_refs": ["host-checker-v1"], **changes}

    def case_set(self):
        items = [self.case(1, "tuning"), self.case(2, "qualification"), self.case(3, "regression")]
        result = self.cases.put_case_set(self.owner, items, 42, event_key="case-set-0001")
        return result, items

    def pins(self, case_set, **changes):
        contract = self.cases.put_contract(self.owner, self.contract(), event_key="contract-0001")
        bundles = []
        for index, raw in enumerate((b"Owner baseline", b"Owner second revision")):
            sha = hashlib.sha256(raw).hexdigest()
            source = IM.SourceSnapshot("skill", "skills/report/SKILL.md", sha, sha,
                                       True, "user_protected", "fixture-incarnation")
            captured = self.assets.capture(self.owner, source, raw, event_key=f"pin-source-{index}",
                                           expected_generation=1 if index else None)
            bundles.append(self.assets.create_bundle(self.owner, [captured["revision_id"]],
                                                       event_key=f"pin-bundle-{index}")["manifest_hash"])
        return {"experiment_id": "experiment-1", "base_bundle_hash": bundles[0], "candidate_bundle_hash": bundles[1],
                "contract_hash": contract["manifest_hash"], "case_set_hash": case_set["manifest_hash"],
                "engine_config_hash": digest("selected-model"), "grant_hash": digest("grant-a"),
                "policy_version": 0, "scope_hash": digest("scope-a"), **changes}

    def test_construct_and_read_missing_records_does_not_initialize_schema(self):
        with self.assertRaises(PermissionError):
            self.cases.get_contract(self.owner, "absent-contract")
        with self.rs._conn() as connection:
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name='improvement_contracts'").fetchone())

    def test_contract_is_complete_canonically_hashed_and_immutable(self):
        payload = self.contract()
        first = self.cases.put_contract(self.owner, payload, event_key="contract-0001")
        self.assertEqual(first, self.cases.put_contract(self.owner, copy.deepcopy(payload), event_key="contract-0001"))
        self.assertEqual(self.cases.get_contract(self.owner, first["contract_id"])["contract"], payload)
        changed = copy.deepcopy(payload)
        changed["primary_metric"]["direction"] = "lower"
        with self.assertRaises(IM.ConflictError):
            self.cases.put_contract(self.owner, changed, event_key="contract-0001")
        with self.rs._Tx(self.rs) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("DELETE FROM improvement_contracts WHERE id=?", (first["contract_id"],))

    def test_contract_requires_public_business_intent_and_declared_output(self):
        for missing in ("objective", "output", "description"):
            payload = self.contract()
            if missing == "description":
                payload["criteria"][1].pop("description", None)
            else:
                payload.pop(missing, None)
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                self.cases.put_contract(self.owner, payload, event_key="missing-public-" + missing)

    def test_public_contract_preserves_requirements_without_checker_implementation(self):
        self.assertTrue(hasattr(IC, "public_contract"), "Solver needs a safe public acceptance projection")
        payload = self.contract()
        payload["criteria"][1].update(kind="host_checker", config={"checker_id": "private-checker",
            "version": "private-version", "hash": digest("private-evaluator-code")})
        projected = IC.public_contract(payload)
        self.assertEqual(projected["objective"], payload["objective"])
        self.assertEqual(projected["output"], payload["output"])
        self.assertEqual(projected["criteria"][0]["config"], payload["criteria"][0]["config"])
        self.assertEqual(projected["criteria"][1]["description"], payload["criteria"][1]["description"])
        self.assertNotIn("private-checker", json.dumps(projected))
        self.assertNotIn("private-version", json.dumps(projected))
        self.assertNotIn(digest("private-evaluator-code"), json.dumps(projected))
        projected["criteria"][0]["config"]["path"] = "caller-mutation"
        self.assertEqual(payload["criteria"][0]["config"]["path"], "answer.json")

    def test_declared_output_path_is_portable_and_cannot_escape_the_artifact_root(self):
        self.assertTrue(hasattr(IC, "output_path"), "Artifact destination needs a shared safe path validator")
        self.assertEqual(IC.output_path("reports/answer.json"), "reports/answer.json")
        for path in ("../answer.json", "C:answer.json", "C:/answer.json", "//server/share", "reports\\answer.json",
                     "reports/CON.txt", "report./answer.json", "reports//answer.json", "reports/./answer.json",
                     "reports/COM¹.txt", "reports/LPT²", "reports/line\nfeed.txt", "reports/CONOUT$"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "invalid_trial_output_path"):
                IC.output_path(path)

    def test_mutating_the_callers_contract_cannot_change_the_pinned_record(self):
        payload = self.contract()
        expected = copy.deepcopy(payload)
        original_hash = IM._hash
        mutated = False

        def hashing(value):
            nonlocal mutated
            result = original_hash(value)
            if isinstance(value, dict) and "criteria" in value and not mutated:
                mutated = True
                payload["criteria"][1]["config"]["path"] = "different-output.json"
            return result

        with patch.object(IM, "_hash", side_effect=hashing):
            stored = self.cases.put_contract(self.owner, payload, event_key="mutation-at-boundary")
        self.assertTrue(mutated)
        actual = self.cases.get_contract(self.owner, stored["contract_id"])
        self.assertEqual(actual["contract"], expected)
        self.assertEqual(actual["manifest_hash"], original_hash(actual["contract"]))

    def test_empty_lossy_or_unsupported_contracts_are_rejected(self):
        variants = []
        for field, value in (("criteria", []), ("output_hash_policy", "word_count"), ("version", 999)):
            variant = self.contract()
            variant[field] = value
            variants.append(variant)
        variant = self.contract()
        variant["criteria"] = variant["criteria"][:1]
        variants.append(variant)
        variant = self.contract()
        variant["criteria"][1]["id"] = "shape"
        variants.append(variant)
        for index, variant in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.cases.put_contract(self.owner, variant, event_key=f"bad-contract-{index}")

    def test_structural_checks_cannot_be_declared_as_business_correctness(self):
        payload = self.contract()
        payload["criteria"][1] = {"id": "content", "category": "business", "critical": True,
                                    "description": "Claim business correctness using only a keyword.",
                                    "kind": "file_contains", "config": {"path": "answer.json", "must_contain": ["total"]}}
        with self.assertRaisesRegex(ValueError, "business"):
            self.cases.put_contract(self.owner, payload, event_key="structural-not-business")

    def test_off_policy_blocks_new_trial_records(self):
        self.assets.set_policy(self.owner, "off", expected_version=0, event_key="case-policy-off")
        with self.assertRaises(PermissionError):
            self.cases.put_contract(self.owner, self.contract(), event_key="off-contract-record")
        with self.assertRaises(PermissionError):
            self.snapshot(1)
        with self.rs._conn() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM improvement_contracts").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT count(*) FROM improvement_snapshots").fetchone()[0], 0)

    def test_snapshot_reference_cannot_cross_brains(self):
        snapshot = self.snapshot(1)
        item = {"id": "case-1", "family_key": "family-1", "split": "tuning", "task": "Read source",
                "snapshot_ids": [snapshot["snapshot_id"]], "answer": {}, "evaluator_refs": []}
        with self.assertRaises(PermissionError):
            self.cases.put_case_set(self.other, [item], 42, event_key="cross-brain-case")

    def test_snapshot_preserves_raw_and_fixture_hashes_without_plaintext(self):
        raw, fixture = b"Private source\r\nSecret removed", b"Authorized fixture\r\n"
        snapshot = self.snapshot(1, raw=raw, fixture=fixture, redaction="owner-reviewed")
        self.assertEqual(snapshot["source_hash"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(snapshot["fixture_hash"], hashlib.sha256(fixture).hexdigest())
        self.assertNotEqual(snapshot["source_hash"], snapshot["fixture_hash"])
        self.assertEqual(self.assets.blobs.read(self.owner.brain_id, snapshot["source_hash"]), raw)
        for path in (self.root / "assets").rglob("*.enc"):
            self.assertNotIn("Private source", path.read_text())
        self.assertNotIn("Private source", json.dumps(self.cases.get_snapshot(self.owner, snapshot["snapshot_id"])))

    def test_period_timezone_and_version_are_part_of_snapshot_identity(self):
        one = self.snapshot(1)
        two = self.snapshot(2, raw=b"visible-input-1", source_ref="source:1", data_period="2026-10")
        three = self.snapshot(3, raw=b"visible-input-1", source_ref="source:1", timezone="UTC")
        self.assertEqual(one["source_hash"], two["source_hash"])
        self.assertEqual(len({one["snapshot_id"], two["snapshot_id"], three["snapshot_id"]}), 3)

    def test_redaction_that_destroys_meaning_is_not_a_runnable_case(self):
        snapshot = self.snapshot(1, raw=b"Meaningful source", fixture=b"[redacted]",
                                 sufficient_source=False, redaction="insufficient")
        self.assertEqual(snapshot["status"], "insufficient_source")
        case = {"id": "case-1", "family_key": "family-1", "split": "tuning", "task": "Use source",
                "snapshot_ids": [snapshot["snapshot_id"]], "answer": {}, "evaluator_refs": []}
        with self.assertRaisesRegex(ValueError, "insufficient_source"):
            self.cases.put_case_set(self.owner, [case], 42, event_key="insufficient-set")

    def test_solver_materialization_excludes_answers_and_checker_references(self):
        case_set, _ = self.case_set()
        solver = self.cases.solver_case(self.owner, case_set["case_set_id"], "case-2")
        encoded = json.dumps(solver)
        self.assertIn("visible-input-2", encoded)
        self.assertNotIn("private-answer", encoded)
        self.assertNotIn("host-checker", encoded)
        self.assertNotIn("evaluator_refs", solver)
        private = self.cases.evaluator_case(self.owner, case_set["case_set_id"], "case-2")
        self.assertEqual(private["answer"]["expected"], "private-answer-2")
        with self.rs._conn() as connection:
            self.assertNotIn("private-answer", connection.execute("SELECT manifest_json FROM improvement_case_sets").fetchone()[0])

    def test_solver_receives_the_pinned_period_timezone_and_source_version(self):
        case_set, _ = self.case_set()
        solver = self.cases.solver_case(self.owner, case_set["case_set_id"], "case-2")
        source = solver["fixtures"][0].get("source", {})
        self.assertEqual(source.get("data_period"), "2026-09")
        self.assertEqual(source.get("timezone"), "Asia/Ho_Chi_Minh")
        self.assertEqual(source.get("source_version"), "v1")

    def test_lost_original_snapshot_is_unavailable_even_if_the_fixture_survives(self):
        snapshot = self.snapshot(1, raw=b"Original private source", fixture=b"Authorized fixture")
        item = {"id": "case-1", "family_key": "family-1", "split": "tuning", "task": "Use the fixture",
                "snapshot_ids": [snapshot["snapshot_id"]], "answer": {}, "evaluator_refs": []}
        case_set = self.cases.put_case_set(self.owner, [item], 42, event_key="raw-loss-case-set")
        self.assets.blobs._path(self.owner.brain_id, snapshot["source_hash"]).unlink()
        with self.assertRaises(IM.AssetUnavailable):
            self.cases.solver_case(self.owner, case_set["case_set_id"], "case-1")

    def test_malformed_nested_json_returns_validation_errors(self):
        bad = self.contract()
        bad["primary_metric"]["criterion_id"] = []
        with self.assertRaises(ValueError):
            self.cases.put_contract(self.owner, bad, event_key="bad-nested-metric")
        case = self.case(1, "tuning")
        case["snapshot_ids"] = [{}]
        with self.assertRaises(ValueError):
            self.cases.put_case_set(self.owner, [case], 42, event_key="bad-nested-snapshot")

    def legacy_schema(self):
        with self.rs._Tx(self.rs) as connection:
            for statement in IM._SCHEMA:
                connection.execute(statement)
            IM._immutable_triggers(connection, ("improvement_revisions", "improvement_bundles",
                                                "improvement_bundle_assets", "improvement_events"))
            connection.execute("INSERT INTO improvement_schema VALUES(1,1)")
            connection.execute("INSERT INTO improvement_policies VALUES(?,?,?)", (self.owner.brain_id, "off", 4))

    def test_m0_schema_reads_stay_lazy_and_m1_upgrade_preserves_prior_policy(self):
        self.legacy_schema()
        self.assertEqual(self.assets.get_policy(self.owner), {"mode": "off", "version": 4})
        with self.rs._conn() as connection:
            self.assertEqual(connection.execute("SELECT version FROM improvement_schema").fetchone()[0], 1)
        IM.ensure(self.rs)
        self.assertEqual(self.assets.get_policy(self.owner), {"mode": "off", "version": 4})
        backup = self.root / "resonance.sqlite3.pre-improvement-m2-experiments.bak"
        self.assertTrue(backup.is_file())
        with sqlite3.connect(backup) as connection:
            self.assertEqual(connection.execute("SELECT version FROM improvement_schema").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT mode,version FROM improvement_policies").fetchone(), ("off", 4))

    def test_failed_m1_upgrade_rolls_back_and_keeps_the_m0_store_usable(self):
        import improvement_case_schema as schema
        self.legacy_schema()
        with patch.object(schema, "SCHEMA", (*schema.SCHEMA, "INVALID M1 MIGRATION")):
            with self.assertRaises(sqlite3.OperationalError):
                IM.ensure(self.rs)
        self.assertEqual(self.assets.get_policy(self.owner), {"mode": "off", "version": 4})
        with self.rs._conn() as connection:
            self.assertEqual(connection.execute("SELECT version FROM improvement_schema").fetchone()[0], 1)
            self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name='improvement_cases'").fetchone())
        IM.ensure(self.rs)
        self.assertEqual(self.assets.get_policy(self.owner)["version"], 4)

    def test_concurrent_m1_migration_has_one_backup_and_no_partial_schema(self):
        self.legacy_schema()
        barrier = threading.Barrier(2)
        backups = []
        original = self.rs._backup_before

        def backup(*args):
            backups.append(args)
            time.sleep(0.1)
            return original(*args)

        def migrate(index):
            barrier.wait()
            try:
                IM.ensure(self.rs)
                return None
            except Exception as error:
                return type(error).__name__

        with patch.object(self.rs, "_backup_before", side_effect=backup), ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(migrate, (1, 2)))
        self.assertEqual(results, [None, None])
        self.assertEqual(backups, [("improvement_compositions", ".pre-improvement-m2-compose.bak"),
                                   ("improvement_experiments", ".pre-improvement-m2-experiments.bak"),
                                   ("improvement_preparations", ".pre-improvement-m2-generated.bak"),
                                   ("improvement_effective_views", ".pre-improvement-m2-views.bak")])
        for _, suffix in backups:
            with sqlite3.connect(self.rs.path.with_name(self.rs.path.name + suffix)) as connection:
                self.assertEqual(connection.execute("SELECT version FROM improvement_schema").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT mode,version FROM improvement_policies").fetchone(), ("off", 4))
        self.assertEqual(self.assets.get_policy(self.owner), {"mode": "off", "version": 4})

    def test_duplicate_content_and_family_crossings_are_rejected(self):
        first = self.case(1, "tuning")
        second = self.case(2, "qualification", family_key=first["family_key"])
        with self.assertRaisesRegex(ValueError, "family"):
            self.cases.put_case_set(self.owner, [first, second], 42, event_key="family-crossing")
        second["family_key"] = "independent-name"
        second["snapshot_ids"] = list(first["snapshot_ids"])
        second["task"] = "Paraphrase of the same source"
        with self.assertRaisesRegex(ValueError, "duplicate|source"):
            self.cases.put_case_set(self.owner, [first, second], 42, event_key="duplicate-source")

    def test_cross_brain_or_agent_cannot_access_private_case_records(self):
        case_set, _ = self.case_set()
        for principal in (self.other, RS.Principal("agent", "owner", self.owner.brain_id)):
            with self.assertRaises(PermissionError):
                self.cases.evaluator_case(principal, case_set["case_set_id"], "case-2")
            with self.assertRaises(PermissionError):
                self.cases.solver_case(principal, case_set["case_set_id"], "case-2")

    def test_qualification_resume_is_pinned_and_consumption_is_durable(self):
        case_set, _ = self.case_set()
        pins = self.pins(case_set)
        claimed = self.cases.reserve_qualification(self.owner, case_set["case_set_id"], pins, event_key="qual-reserve-1")
        self.assertEqual(claimed["status"], "reserved")
        self.assertEqual(claimed, self.cases.reserve_qualification(self.owner, case_set["case_set_id"], pins,
                                                                 event_key="qual-resume-1"))
        changed = {**pins, "candidate_bundle_hash": pins["base_bundle_hash"]}
        with self.assertRaises(IM.ConflictError):
            self.cases.reserve_qualification(self.owner, case_set["case_set_id"], changed, event_key="qual-changed-1")
        consumed = self.cases.consume_qualification(self.owner, claimed["reservation_id"], pins, event_key="qual-consume-1")
        self.assertEqual(consumed["status"], "consumed")
        reopened = IC.CaseStore(IM.ImprovementStore(RS.GoalStore(self.root / "resonance.sqlite3"), self.assets.blobs))
        self.assertEqual(consumed, reopened.consume_qualification(self.owner, claimed["reservation_id"], pins,
                                                                  event_key="qual-consume-1"))

    def test_qualification_clone_cannot_reset_consumed_family(self):
        case_set, items = self.case_set()
        pins = self.pins(case_set)
        claimed = self.cases.reserve_qualification(self.owner, case_set["case_set_id"], pins, event_key="qual-reserve-1")
        self.cases.consume_qualification(self.owner, claimed["reservation_id"], pins, event_key="qual-consume-1")
        clone = self.cases.put_case_set(self.owner, items, 99, event_key="case-set-clone")
        other_pins = {**pins, "experiment_id": "experiment-2", "case_set_hash": clone["manifest_hash"]}
        with self.assertRaises(IM.ConflictError):
            self.cases.reserve_qualification(self.owner, clone["case_set_id"], other_pins, event_key="qual-clone-1")

    def test_public_tuning_clone_cannot_leak_reserved_qualification(self):
        case_set, items = self.case_set()
        pins = self.pins(case_set)
        self.cases.reserve_qualification(self.owner, case_set["case_set_id"], pins, event_key="qual-reserve-1")
        clone_items = copy.deepcopy(items)
        clone_items[1]["split"] = "tuning"
        clone = self.cases.put_case_set(self.owner, clone_items, 99, event_key="tuning-clone-set")
        with self.assertRaises(IM.ConflictError):
            self.cases.improver_cases(self.owner, clone["case_set_id"])

    def test_exposed_tuning_cannot_be_relabelled_as_fresh_qualification(self):
        case_set, items = self.case_set()
        exposed = self.cases.improver_cases(self.owner, case_set["case_set_id"])
        self.assertEqual([item["id"] for item in exposed], ["case-1"])
        clone_items = copy.deepcopy(items)
        clone_items[0]["split"], clone_items[1]["split"] = "qualification", "tuning"
        clone = self.cases.put_case_set(self.owner, clone_items, 99, event_key="exposed-clone-set")
        pins = self.pins(clone)
        with self.assertRaises(IM.ConflictError):
            self.cases.reserve_qualification(self.owner, clone["case_set_id"], pins, event_key="qual-exposed-1")

    def test_concurrent_qualification_reservation_has_exactly_one_winner(self):
        case_set, _ = self.case_set()
        pins = self.pins(case_set)
        barrier = threading.Barrier(2)

        def claim(index):
            barrier.wait()
            try:
                return self.cases.reserve_qualification(self.owner, case_set["case_set_id"],
                    {**pins, "experiment_id": f"experiment-{index}"}, event_key=f"race-qualification-{index}")
            except IM.ConflictError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(claim, (1, 2)))
        self.assertEqual(sum(result is not None for result in results), 1)

    def test_unknown_or_stale_qualification_pins_do_not_consume_the_cases(self):
        case_set, _ = self.case_set()
        pins = self.pins(case_set)
        variants = [("contract_hash", digest("missing-contract"), PermissionError),
                    ("grant_hash", digest("revoked-grant"), IM.ConflictError),
                    ("case_set_hash", digest("changed-case-set"), IM.ConflictError),
                    ("policy_version", 1, IM.ConflictError)]
        for key, value, error in variants:
            with self.subTest(pin=key), self.assertRaises(error):
                self.cases.reserve_qualification(self.owner, case_set["case_set_id"], {**pins, key: value},
                                                   event_key=f"stale-pin-{key}")
        valid = self.cases.reserve_qualification(self.owner, case_set["case_set_id"], pins, event_key="valid-after-rejection")
        self.assertEqual(valid["status"], "reserved")


if __name__ == "__main__":
    unittest.main()
