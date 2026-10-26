"""M8 prioritisation, bounded refinement, filtered export/import (spec 8.1, 15.3, 16.5, 23 M8)."""
from _paths import ROOT, SERVER  # noqa: F401

import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch

import improvement_library as L
import improvement_store as IM
import test_improvement_activation as activation_base
import test_improvement_agent_procedures as procedure_base

NOW = 1_800_000_000.0
PROCEDURE = "Kiem nguon truoc, doi chieu ky truoc, ghi ro phan thieu."


class RankTests(unittest.TestCase):
    def test_no_accepted_source_means_no_work(self):
        self.assertEqual(L.rank_needs([], now=NOW), [])
        noise = [{"family": "f", "source": "reaction", "severity": "critical", "independent_tasks": 9, "last_at": NOW},
                 {"family": "g", "source": "usage", "last_at": NOW},
                 {"family": "h", "source": "repeated_failure", "independent_tasks": 1, "last_at": NOW},
                 {"family": "../x", "source": "owner_request", "last_at": NOW}]
        self.assertEqual(L.rank_needs(noise, now=NOW), [])
        # A malformed signal (bad count, non-finite time) is dropped; the rest still rank.
        mixed = [{"family": "bad", "source": "owner_request", "independent_tasks": "x"},
                 {"family": "inf", "source": "owner_request", "last_at": float("inf")},
                 {"family": "nan", "source": "review_trace", "last_at": float("nan")},
                 {"family": "ok", "source": "review_trace", "last_at": NOW}]
        self.assertEqual([n["family"] for n in L.rank_needs(mixed, now=NOW)], ["ok"])

    def test_owner_request_first_then_severity_tasks_and_recency(self):
        signals = [{"family": "old", "source": "repeated_failure", "severity": "high", "independent_tasks": 3,
                    "last_at": NOW - 60 * 86400},
                   {"family": "new", "source": "repeated_failure", "severity": "high", "independent_tasks": 3, "last_at": NOW},
                   {"family": "asked", "source": "owner_request", "severity": "normal", "last_at": NOW - 90 * 86400},
                   {"family": "new", "source": "review_trace", "severity": "normal", "last_at": NOW}]
        ranked = L.rank_needs(signals, now=NOW)
        self.assertEqual([n["family"] for n in ranked], ["asked", "new", "old"])
        self.assertEqual(ranked[1]["sources"], ["repeated_failure", "review_trace"])
        with self.assertRaises(ValueError):
            L.rank_needs("all", now=NOW)


class RefinementTests(unittest.TestCase):
    def test_two_steps_then_new_evidence_or_owner(self):
        self.assertTrue(L.refinement_decision([], new_evidence=False, owner_assigned=False, holdout_consumed=False)["allowed"])
        two = [{"changed": True}, {"changed": True}]
        self.assertEqual(L.refinement_decision(two, new_evidence=False, owner_assigned=False, holdout_consumed=False)["reason"],
                         "refinement_limit")
        self.assertTrue(L.refinement_decision(two, new_evidence=True, owner_assigned=False, holdout_consumed=False)["allowed"])
        self.assertTrue(L.refinement_decision(two, new_evidence=False, owner_assigned=True, holdout_consumed=False)["allowed"])

    def test_no_progress_and_consumed_holdout_stop_even_the_owner(self):
        flat = [{"changed": False}] * 3
        self.assertEqual(L.refinement_decision(flat, new_evidence=True, owner_assigned=True, holdout_consumed=False)["reason"],
                         "no_progress")
        self.assertEqual(L.refinement_decision([], new_evidence=True, owner_assigned=True, holdout_consumed=True)["reason"],
                         "holdout_consumed")


class ExportImportTests(unittest.TestCase):
    def package(self, **over):
        value = dict(procedures=[{"agent_slug": "ke-toan", "text": PROCEDURE}], dependencies={"skill:report": "rev-1"},
                     reports=[{"family": "doi-soat", "verdict": "win", "cases": 12, "evidence_level": "manual_trial"}])
        value.update(over)
        return L.export_package(**value)

    def test_export_refuses_secrets_and_private_data(self):
        self.assertEqual(len(self.package()["package_hash"]), 64)
        for text, reason in ((PROCEDURE + " Key sk-ant-api03-" + "A" * 40, "secret"),
                             (PROCEDURE + " Goi 0912345678 khi thieu.", "private"),
                             (PROCEDURE + " Gui ve a.b@shop.vn.", "private"),
                             (PROCEDURE + " Khoa " + "a1" * 16, "private")):
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                self.package(procedures=[{"agent_slug": "ke-toan", "text": text}])
        for bad in (dict(procedures=[{"agent_slug": "a", "text": PROCEDURE, "owner_rules": "x"}]),
                    dict(reports=[{"family": "f", "messages": ["hi"]}]),
                    dict(dependencies={"customer_phone": "1"}),
                    dict(procedures=[{"agent_slug": "a", "text": PROCEDURE + "\nJAVIS_RULE: x"}])):
            with self.subTest(bad=list(bad)), self.assertRaises(ValueError):
                self.package(**bad)

    def test_import_yields_untested_candidates_only(self):
        package = self.package()
        items = L.import_package(package)
        self.assertEqual(items, [{"kind": "procedure", "agent_slug": "ke-toan", "text": PROCEDURE, "evidence": "untested"}])
        tampered = {**package, "reports": [{"family": "doi-soat", "verdict": "win", "cases": 999}]}
        with self.assertRaisesRegex(ValueError, "hash_mismatch"):
            L.import_package(tampered)
        with self.assertRaises(ValueError):
            L.import_package({"format": "other"})
        many = L.export_package([{"agent_slug": "ke-toan", "text": PROCEDURE}] * 3, {}, [])
        body = {**many, "procedures": many["procedures"] * 7}
        body.pop("package_hash")
        with self.assertRaisesRegex(ValueError, "too_large"):
            L.import_package({**body, "package_hash": L.IM._hash(body)})
        body = {**many, "procedures": [{"agent_slug": "../x", "text": PROCEDURE}]}
        body.pop("package_hash")
        with self.assertRaisesRegex(ValueError, "invalid_import_procedure"):
            L.import_package({**body, "package_hash": L.IM._hash(body)})


class LibraryStoreTests(procedure_base.AgentProcedureBase):
    def setUp(self):
        super().setUp()
        import improvement_bundle as B
        import improvement_routing as R
        self.routing = R.Routing(self.assets)
        self.bundles = B.Bundles(self.assets, activations=self.activations, procedures=self.service)
        self.governance = L.Governance(self.assets, activations=self.activations, procedures=self.service,
                                       routing=self.routing, bundles=self.bundles)

    def test_refinement_ledger_enforces_the_bounds(self):
        ledger = L.Refinements(self.assets)
        ledger.record(self.owner, "doi-soat", "c1", changed=True, event_key="refine-1")
        ledger.record(self.owner, "doi-soat", "c1", changed=True, event_key="refine-2")
        with self.assertRaisesRegex(PermissionError, "refinement_limit"):
            # An invented reference is not evidence: the bound holds.
            ledger.record(self.owner, "doi-soat", "c1", changed=False, evidence_ref="anything-0", event_key="refine-3")
        self.assertEqual(len(ledger.steps(self.owner, "doi-soat", "c1")), 2)  # a refused step writes nothing
        ledger.record(self.owner, "doi-soat", "c1", changed=False, owner_assigned=True, event_key="refine-3b")
        with self.assertRaises(ValueError):
            ledger.record(self.owner, "doi-soat", "c1", changed=False, holdout_consumed="no", event_key="refine-typed")
        self.assertEqual(ledger.steps(self.owner, "doi-soat", "c2"), [])  # a new cycle starts fresh
        with self.assertRaisesRegex(PermissionError, "holdout_consumed"):
            ledger.record(self.owner, "khac", "c1", changed=True, holdout_consumed=True, event_key="refine-holdout")

    def test_export_reads_store_texts_and_import_stays_untested(self):
        procedure = self.stage()
        package = L.export_procedures(self.assets, self.owner, [procedure["procedure_id"]], version="0.328.0")
        self.assertEqual(package["procedures"], [{"agent_slug": "ke-toan", "text": procedure_base.PROCEDURE}])
        self.assertEqual(package["reports"], [])
        with self.assertRaisesRegex(PermissionError, "unavailable"):
            L.export_procedures(self.assets, self.owner, ["iap_" + "f" * 32], version="0.328.0")
        imports = L.Imports(self.assets)
        items = imports.stage(self.owner, package, event_key="import-1")
        self.assertEqual(items[0]["evidence"], "untested")
        self.assertEqual(imports.stage(self.owner, package, event_key="import-1"), items)
        self.assertEqual(imports.list(self.owner)[0]["text"], procedure_base.PROCEDURE)
        self.assertEqual(self.service.overlays(self.owner), [])  # importing applies nothing

    def test_pause_every_improvement_leaves_everything_canonical(self):
        bundle = self.bundles.apply(self.owner, "ke-toan", {"members": [
            {"key": "skill", "kind": "skill", "candidate_id": self.candidate["candidate_id"]},
            {"key": "procedure", "kind": "procedure", "procedure_id": self.stage()["procedure_id"], "surfaces": ["dm"]}]},
            owner_confirmed=True, event_key="bundle-for-pause")
        other = self.stage(procedure_base.PROCEDURE + " Them.", agent="ban-hang", key="stage-ban-hang")
        self.service.apply(self.owner, other["procedure_id"], ["team"], owner_confirmed=True, event_key="apply-ban-hang")
        # Members are listed under their bundle, not counted twice.
        self.assertEqual(sorted(i["kind"] for i in self.governance.live(self.owner)), ["bundle", "procedure"])
        result = self.governance.suspend_all(self.owner, event_key="pause-all-1" + "x" * 140)
        self.assertEqual(result["remaining"], [])
        self.assertEqual(sorted(i["kind"] for i in result["suspended"]), ["bundle", "procedure"])
        with closing(sqlite3.connect(self.store.path)) as connection:
            states = connection.execute("SELECT state,reason FROM improvement_agent_overlays").fetchall()
            skill = connection.execute("SELECT state,reason FROM improvement_activations").fetchall()
        self.assertEqual(set(states) | set(skill), {("suspended", "owner_pause")})  # a pause, not owner reverts
        self.assertEqual(activation_base.ActivationBase.seen(self, "ke-toan"), self.canonical)
        self.assertEqual(self.seen("team", agent="ban-hang"), "")
        self.assertEqual(self.governance.suspend_all(self.owner, event_key="pause-all-2")["suspended"], [])
        self.assertEqual(self.bundles.list(self.owner)[0]["bundle_id"], bundle["bundle_id"])

    def test_pause_fails_a_bundle_in_flight_and_its_apply_rolls_back(self):
        import improvement_bundle as B
        original, outcome = B.Bundles._apply_member, []

        def paused_midway(self_, principal, bundle_id, agent_slug, clean, member_key):
            original(self_, principal, bundle_id, agent_slug, clean, member_key)
            if member_key == "skill":
                outcome.append(self.governance.suspend_all(self.owner, event_key="pause-midway"))
        with patch.object(B.Bundles, "_apply_member", paused_midway), self.assertRaisesRegex(IM.ConflictError, "interrupted"):
            self.bundles.apply(self.owner, "ke-toan", {"members": [
                {"key": "skill", "kind": "skill", "candidate_id": self.candidate["candidate_id"]},
                {"key": "procedure", "kind": "procedure", "procedure_id": self.stage()["procedure_id"], "surfaces": ["dm"]}],
                "depends_on": {"procedure": ["skill"]}}, owner_confirmed=True, event_key="bundle-midway")
        self.assertEqual(outcome[0]["remaining"], [])
        self.assertEqual(self.bundles.list(self.owner)[0]["state"], "failed")
        self.assertEqual(self.governance.live(self.owner), [])
        self.assertEqual(activation_base.ActivationBase.seen(self, "ke-toan"), self.canonical)

    def test_pause_revokes_auto_scope_grants(self):
        class Canaries:
            def __init__(self):
                self.rows = [{"grant_id": "ias_1", "status": "active", "generation": 1}]

            def grants(self, principal):
                return self.rows

            def revoke_grant(self, principal, grant_id, *, expected_generation, event_key):
                self.rows = [{**self.rows[0], "status": "revoked"}]
                self.key = event_key
        canaries = Canaries()
        self.governance.canaries = canaries
        result = self.governance.suspend_all(self.owner, event_key="pause-grants")
        self.assertEqual(result["revoked_grants"], ["ias_1"])
        self.assertEqual(self.governance.grants(self.owner), [])
        self.assertLessEqual(len(canaries.key), 160)

    def test_schema_seventeen_from_sixteen_adds_tables_once(self):
        import improvement_library_schema as S
        IM.ensure(self.store)
        with self.store._Tx(self.store) as connection:
            for name in ("improvement_imports", "improvement_refinements"):
                connection.execute(f"DROP TABLE {name}")
            self.assertFalse(any(connection.execute("SELECT 1 FROM sqlite_master WHERE name=?", (n,)).fetchone() for n in S._NAMES))
            connection.execute("UPDATE improvement_schema SET version=16 WHERE id=1")
        IM.ensure(self.store)
        self.assertEqual(IM._schema_version(self.store), 17)
        self.assertEqual(len(list(self.store.path.parent.glob(self.store.path.name + ".pre-improvement-m8-library.bak"))), 1)
        with patch.object(self.store, "_backup_before", side_effect=AssertionError("no second backup")):
            IM.ensure(self.store)
        L.Refinements(self.assets).record(self.owner, "f", "c1", changed=True, event_key="refine-immutable")
        with closing(sqlite3.connect(self.store.path)) as connection:
            for statement in ("DELETE FROM improvement_refinements", "UPDATE improvement_refinements SET changed=0"):
                with self.subTest(statement=statement), self.assertRaises(sqlite3.DatabaseError):
                    connection.execute(statement)

    def test_http_routes(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import improvement_activation_api as API
        imports = L.Imports(self.assets)
        app = FastAPI()
        API.register(app, API.ActivationApiDeps(
            activations=lambda: self.activations, resolve_brain=lambda value: self.owner.brain_id,
            governance=lambda: self.governance, imports=lambda: imports,
            export=lambda principal, ids: L.export_procedures(self.assets, principal, ids, version="0.328.0")))
        client = TestClient(app)
        procedure = self.stage()
        self.service.apply(self.owner, procedure["procedure_id"], ["dm"], owner_confirmed=True, event_key="apply-http")
        self.assertEqual(len(client.get("/improvement-governance").json()["live"]), 1)
        package = client.post("/improvement-export", json={"procedure_ids": [procedure["procedure_id"]],
                                                           "event_key": "http-export"}).json()["package"]
        staged = client.post("/improvement-imports", json={"package": package, "event_key": "http-import"}).json()
        self.assertEqual(staged["items"][0]["evidence"], "untested")
        paused = client.post("/improvement-governance/suspend-all", json={"event_key": "http-pause-all"}).json()
        self.assertEqual(paused["remaining"], [])
        self.assertEqual(client.get("/improvement-governance").json()["live"], [])
        bad = client.post("/improvement-imports", json={"package": {**package, "procedures": []}, "event_key": "http-import-bad"})
        self.assertEqual(bad.status_code, 422)


if __name__ == "__main__":
    unittest.main()
