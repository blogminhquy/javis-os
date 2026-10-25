"""M2F simulated feasibility: the whole owner workflow on actual services, one scenario per outcome.

Every cell result here is a labelled synthetic storage fixture (`evidence_origin:
synthetic_storage_fixture`). These tests prove the mechanism: the comparison report, the
keep-baseline path, the evidence gate on apply, the scoped overlay and the pointer-only revert.
They are not model-backed feasibility, native readiness or business evidence.

Scenarios:
  win      candidate fixes the primary criterion -> tuning eligible -> manual trial apply -> revert
  tie      both variants pass everything -> inconclusive -> owner keeps the baseline
  loss     candidate breaks a required criterion -> rejected -> apply and selection refused
  unknown  candidate cells carry unknown verdicts -> inconclusive, coverage kept, baseline kept
"""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import hashlib
import json
import time
import unittest
from contextlib import closing
from pathlib import Path

import improvement_activation as IA
import improvement_comparison_results as C
import improvement_evaluation as E
import improvement_experiment_protocol as P
import improvement_store as IM
import test_improvement_experiment_lineage as fixtures
import turn_context
from agent_ledger import CallLedger

AGENT = {"key": "agent-ke-toan-1", "slug": "ke-toan"}


class SimulatedFeasibilityTests(unittest.TestCase):
    def setUp(self):
        self.h = fixtures.LineageTests()
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.owner, self.assets, self.store = self.h.owner, self.h.assets, self.h.store
        self.plans = self.h.h.plans()
        self.reports = C.ComparisonResults(self.plans)
        self.candidate = self.h.h.h.candidate
        self.skill = Path(self.h.h.f.skill)
        self.root = Path(self.owner.brain_id)
        self.canonical = self.skill.read_bytes()
        # The owner approves the exact diff while the experiment is still open; apply needs it.
        self.h.h.authoring.authorize_diff(self.owner, self.candidate["candidate_id"], expected_generation=1,
            before_hash=self.candidate["base_hash"], after_hash=self.candidate["content_hash"],
            event_key="feasibility-exact-diff")
        self.activations = IA.Activations(self.assets, agent_key=lambda brain, slug: AGENT["key"] if slug == AGENT["slug"] else "")
        IA.configure(self.store.path, self.assets.blobs)
        self.addCleanup(IA.configure, None, None)
        with closing(self.store._conn()) as connection:
            self.contract = json.loads(connection.execute("SELECT contract_json FROM improvement_contracts WHERE manifest_hash=?",
                                                          (self.h.value["contract_hash"],)).fetchone()[0])
        self.primary = self.contract["primary_metric"]["criterion_id"]
        self.required = next(c["id"] for c in self.contract["criteria"] if c["category"] == "mandatory" or c["critical"])

    # -- synthetic cells --------------------------------------------------------------------------

    def seed(self, verdict):
        """One labelled synthetic result per matrix cell; `verdict(variant, criterion_id)` decides."""
        ledger = CallLedger(self.store)
        for position in range(self.h.frozen["cell_count"]):
            cell = P.matrix_cell(self.h.matrix, position)
            request = copy.deepcopy(self.h.request)
            request.update({key: cell[key] for key in ("case_id", "variant", "repeat")})
            request["lineage"].update(pair_id=cell["pair_id"], cell_position=position)
            trial_id, result_id = "it_feasibility_" + str(position), "ir_feasibility_" + str(position)
            raw = IM._json({"value": "simulated-" + cell["variant"]}).encode()
            output_hash = self.assets.blobs.write(self.owner.brain_id, raw)
            artifact = E.TrialArtifact(self.contract["output"]["path"], hashlib.sha256(raw).hexdigest(), raw, raw.decode())
            criteria = [E._row(criterion, verdict(cell["variant"], criterion["id"]), "simulated_storage_fixture",
                               {"simulated": True}) for criterion in self.contract["criteria"]]
            evaluation = E._result(self.contract, {"id": cell["case_id"]}, criteria, artifact)
            report = {"version": 2, "trial_id": trial_id, "attempt": 1, "execution_status": "completed",
                "request_hash": IM._hash(request), "experiment_lineage": request["lineage"],
                "contract_hash": request["pins"]["contract_hash"], "artifact_hash": output_hash, "evaluation": evaluation,
                "mandatory": [{"id": identifier, "verdict": "pass", "reason": "simulated_storage_fixture"}
                              for identifier in sorted(C._NATIVE_CHECKS)],
                "verdict": evaluation["verdict"], "evidence_origin": "synthetic_storage_fixture"}
            report_hash = self.assets.blobs.write(self.owner.brain_id, IM._json(report).encode())
            pointer = {"result_id": result_id, "result_hash": IM._hash(report), "blob_hash": report_hash}
            stamp = time.time()
            with self.store._Tx(self.store) as connection:
                connection.execute("INSERT INTO improvement_trials VALUES(?,?,?,?,?,?,?,?,?,?)", (
                    trial_id, self.owner.brain_id, P.logical_key_v2(request), IM._hash(request), IM._json(request),
                    "completed", 1, 1, stamp, stamp))
                call = ledger.reserve(purpose="improve_probe", reason_ref="improvement_trial:" + trial_id + ":attempt:1",
                    brain_id=self.owner.brain_id, context_ref="improvement:association-experiment", obligation=True,
                    mirror_ref="improvement_trial:" + trial_id, attempt=1, now=stamp, c=connection)
                self.assertTrue(ledger._mark_engine_in(connection, call, "simulated_fixture", "unexecuted", stamp))
                self.assertTrue(ledger._settle_in(connection, call, "ok", None, None, None, stamp))
                connection.execute("INSERT INTO improvement_trial_attempts(trial_id,brain_id,attempt,status,call_id,engine_at,"
                    "result_json,created_at,updated_at) VALUES(?,?,1,'completed',?,?,?,?,?)",
                    (trial_id, self.owner.brain_id, call, stamp, IM._json(pointer), stamp, stamp))
                connection.execute("INSERT INTO improvement_experiment_trial_links VALUES(?,?,?,?,?,?,?,?,?,?,?)", (
                    self.h.comparison["id"], self.owner.brain_id, "association-experiment", position, trial_id,
                    IM._hash(request), cell["pair_id"], cell["case_id"], cell["repeat"], cell["variant"], stamp))
                connection.execute("INSERT INTO improvement_trial_artifacts VALUES(?,?,?,?,?,?,?)", (
                    trial_id, self.owner.brain_id, 1, self.contract["output"]["path"], output_hash, len(raw), stamp))
                connection.execute("INSERT INTO improvement_trial_results VALUES(?,?,?,?,?,?,?)", (
                    result_id, trial_id, self.owner.brain_id, 1, pointer["result_hash"], report_hash, stamp))
        saved = self.reports.create(self.owner, self.h.comparison["id"], expected_generation=self.h.frozen["generation"],
                                    event_key="feasibility-tuning-report")
        return saved, self.reports.read(self.owner, saved["report_id"])["summary"]

    # -- owner actions ----------------------------------------------------------------------------

    def select(self, choice, generation, key):
        return self.plans.select(self.owner, "association-experiment", choice, ordinal=1 if choice == "candidate" else None,
                                 expected_generation=generation, event_key=key)

    def apply(self, key="feasibility-apply"):
        return self.activations.apply(self.owner, self.candidate["candidate_id"], AGENT["slug"], event_key=key)

    def seen(self):
        token = turn_context.bind(turn_context.make("dashboard", la_chu=True, agent=dict(AGENT)))
        try:
            return IA.effective_skill_asset(self.root, self.skill.parent.name).content
        finally:
            turn_context.reset(token)

    def phase(self):
        with closing(self.store._conn()) as connection:
            return connection.execute("SELECT phase FROM improvement_experiments WHERE id='association-experiment'").fetchone()[0]

    # -- scenarios --------------------------------------------------------------------------------

    def test_win_tuning_is_only_a_manual_trial_then_revert_restores_canonical(self):
        saved, summary = self.seed(lambda variant, criterion: "fail" if variant == "baseline" and criterion == self.primary else "pass")
        self.assertEqual((summary["mechanical_verdict"], summary["selection_supported"]), ("eligible", True))
        self.assertGreater(summary["outcomes"]["tuning"]["win"], 0)
        self.assertEqual(summary["outcomes"]["tuning"]["loss"], 0)
        self.assertEqual(summary["business_eligibility"], "unverified")
        applied = self.apply()
        # Tuning eligibility selects a candidate; it never qualifies one for release.
        self.assertEqual(applied["evidence_level"], "manual_trial")
        self.assertEqual(applied["evidence"]["reports"][0]["report_id"], saved["report_id"])
        overlay = self.assets.blobs.read(self.owner.brain_id, self.candidate["content_hash"])
        self.assertEqual(self.seen(), overlay)
        self.assertEqual(self.skill.read_bytes(), self.canonical)
        self.select("candidate", saved["generation"], "feasibility-select-candidate")
        self.activations.revert(self.owner, applied["activation_id"], expected_generation=1, event_key="feasibility-revert")
        self.assertEqual(self.seen(), self.canonical)

    def test_tie_is_inconclusive_and_keep_baseline_completes_without_changes(self):
        saved, summary = self.seed(lambda variant, criterion: "pass")
        self.assertEqual(summary["mechanical_verdict"], "inconclusive")
        self.assertFalse(summary["selection_supported"])
        self.assertEqual(summary["outcomes"]["tuning"]["win"], 0)
        with self.assertRaises((PermissionError, IM.ConflictError)):
            self.select("candidate", saved["generation"], "feasibility-select-tie")
        self.select("keep_base", saved["generation"], "feasibility-keep-tie")
        self.assertIn(self.phase(), ("stopping", "completed"))
        self.assertEqual(self.seen(), self.canonical)
        self.assertEqual(self.activations.list(self.owner), [])

    def test_required_loss_is_rejected_and_cannot_be_applied_or_selected(self):
        saved, summary = self.seed(lambda variant, criterion: "fail" if variant == "candidate" and criterion == self.required else "pass")
        self.assertEqual(summary["mechanical_verdict"], "rejected")
        self.assertGreater(summary["required_loss_count"], 0)
        with self.assertRaisesRegex(PermissionError, "rejected"):
            self.apply()
        with self.assertRaises((PermissionError, IM.ConflictError)):
            self.select("candidate", saved["generation"], "feasibility-select-loss")
        self.select("keep_base", saved["generation"], "feasibility-keep-loss")
        self.assertEqual(self.seen(), self.canonical)
        self.assertEqual(self.activations.list(self.owner), [])

    def test_keep_baseline_closes_apply_for_the_candidate(self):
        saved, _ = self.seed(lambda variant, criterion: "pass")
        self.select("keep_base", saved["generation"], "feasibility-keep-then-apply")
        with self.assertRaisesRegex(PermissionError, "closed"):
            self.apply()

    def test_rejection_published_after_apply_suspends_the_pointer(self):
        applied = self.apply("feasibility-apply-early")
        self.assertEqual(applied["evidence_level"], "manual_trial")
        self.seed(lambda variant, criterion: "fail" if variant == "candidate" and criterion == self.required else "pass")
        self.assertEqual(self.activations.reconcile(self.owner),
                         [{"activation_id": applied["activation_id"], "reason": "candidate_rejected"}])
        self.assertEqual(self.seen(), self.canonical)

    def test_pilot_conclusions_follow_each_outcome(self):
        import improvement_canary as CN
        canaries = CN.Canaries(self.activations)
        cases = {"tie": (lambda variant, criterion: "pass", "equivalent"),
                 "loss": (lambda variant, criterion: "fail" if variant == "candidate" and criterion == self.required else "pass",
                          "worse")}
        for name, (verdict, expected) in cases.items():
            with self.subTest(name=name):
                fresh = type(self)(self._testMethodName)
                fresh.setUp()
                self.addCleanup(fresh.doCleanups)
                saved, _ = fresh.seed(verdict)
                pilot = CN.Canaries(fresh.activations).pilot_report(fresh.owner, saved["report_id"])
                self.assertEqual(pilot["conclusion"], expected)
                self.assertEqual(pilot["business_eligibility"], "unverified")
        saved, _ = self.seed(lambda variant, criterion: "fail" if variant == "baseline" and criterion == self.primary else "pass")
        win = canaries.pilot_report(self.owner, saved["report_id"])
        # A tuning win selects a candidate; it is never an improvement conclusion on its own.
        self.assertEqual((win["conclusion"], win["kind"]), ("insufficient_evidence", "tuning"))
        self.assertGreater(win["wins"], 0)

    def test_unknown_cells_stay_in_coverage_and_keep_the_baseline(self):
        saved, summary = self.seed(lambda variant, criterion: "unknown" if variant == "candidate" else "pass")
        self.assertEqual(summary["mechanical_verdict"], "inconclusive")
        self.assertFalse(summary["complete"])
        self.assertGreater(summary["outcomes"]["tuning"]["unknown"], 0)
        self.assertEqual(summary["outcomes"]["tuning"]["win"] + summary["outcomes"]["tuning"]["loss"], 0)
        self.select("keep_base", saved["generation"], "feasibility-keep-unknown")
        self.assertEqual(self.seen(), self.canonical)


if __name__ == "__main__":
    unittest.main()
