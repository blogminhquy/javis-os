"""Engineering capability seams at real owner/DB boundaries; no native readiness proof."""
from _paths import ROOT, SERVER  # noqa: F401

import copy
import subprocess
import unittest
from contextlib import closing, contextmanager
from pathlib import Path
from unittest.mock import patch

import test_improvement_trial_admission as admission_fixtures
import test_improvement_operation_execution as operation_fixtures
import test_improvement_trial_runner as trial_runner_fixtures
import test_improvement_operation_runner as operation_runner_fixtures


REFUSALS = (
    {"account_ready": False},
    {"domain": "qualification"},
    {"account_ready": False, "domain": "qualification"},
    {"supported": False, "account_ready": False, "domain": "qualification"},
)
CONTROLS = ({}, {"account_ready": 0, "domain": "ordinary"})


@contextmanager
def scratch(case_type):
    """Compose fixture setup without inheriting its historical test discovery."""
    fixture = case_type()
    originals = [(subprocess, name, getattr(subprocess, name)) for name in ("run", "Popen")]
    for module, names in ((operation_fixtures.US, ("_PATH", "_EVENTS_PATH", "_TELEMETRY_ERRORS")),
                          (operation_fixtures.UI, ("_EVENTS_PATH", "DB_PATH", "_claude_dir", "_codex_dir"))):
        originals.extend((module, name, getattr(module, name)) for name in names)

    def cleanup(current):
        # Preserve registered LIFO order across nested fixtures. These fixtures
        # register synchronous callbacks; the outer test owns all async runs.
        while current._cleanups:
            callback, args, kwargs = current._cleanups.pop()
            owner = getattr(callback, "__self__", None)
            if isinstance(owner, unittest.TestCase) and getattr(callback, "__func__", None) is unittest.TestCase.doCleanups:
                cleanup(owner)
            else:
                callback(*args, **kwargs)

    try:
        fixture.setUp()
        yield fixture
    finally:
        chain, current = [], fixture
        while isinstance(current, unittest.TestCase):
            chain.append(current)
            current = getattr(current, "f", None)
        for current in chain:
            cleanup(current)
            directory = getattr(current, "directory", None)
            if directory is not None:
                current.assertFalse(Path(directory.name).exists())
        for module, name, original in originals:
            fixture.assertIs(getattr(module, name), original, "Scratch fixture did not restore " + name)


class AdmissionFenceTests(unittest.TestCase):
    def test_marked_capabilities_reserve_no_qualification_trial_or_call(self):
        for markers in REFUSALS:
            with self.subTest(markers=markers), scratch(admission_fixtures.AdmissionTests) as f:
                ordinary = copy.deepcopy(f.verified)
                f.verify.return_value = {**ordinary, **markers}
                with self.assertRaisesRegex(ValueError, "trial_native_unavailable"):
                    f.admit()
                f.verify.assert_called_once()
                f.assert_no_admission()
                self.assertEqual(f.verify.return_value["capability_hash"], ordinary["capability_hash"])

    def test_ordinary_capabilities_keep_real_owner_admission(self):
        for markers in CONTROLS:
            with self.subTest(markers=markers), scratch(admission_fixtures.AdmissionTests) as f:
                f.verify.return_value = {**f.verified, **markers}
                admitted = f.admit()
                row = f.admission.trials.get(f.owner, admitted.trial_id)
                self.assertEqual(row["status"], "reserved")
                for table in ("improvement_qualification", "improvement_trials", "agent_calls"):
                    self.assertEqual(f.count(table), 1, table)
                self.assertEqual(f.count("improvement_qualification_claims"), 2)
                with closing(f.store._conn()) as connection:
                    call = connection.execute("SELECT status,engine_at FROM agent_calls").fetchone()
                self.assertEqual(tuple(call), ("reserved", None))


class OperationReservationFenceTests(unittest.TestCase):
    def test_marked_capabilities_leave_real_operation_pending_without_call(self):
        for markers in REFUSALS:
            with self.subTest(markers=markers), scratch(operation_fixtures.OperationExecutionTests) as f:
                service = f.execution()
                capability = {"supported": True, "capability_hash": "c" * 64, **markers}
                with patch("improvement_operation_adapter.ClaudeOperationAdapter.verify", return_value=capability) as verify:
                    with self.assertRaisesRegex(ValueError, "operation_native_unavailable"):
                        service.reserve(f.owner, f.operation["operation_id"], expected_generation=1,
                                        event_key="qualification-fence-reserve")
                verify.assert_called_once()
                row = service.get(f.owner, f.operation["operation_id"])
                self.assertEqual((row["status"], row["attempts"]), ("pending", []))
                with closing(f.store._conn()) as connection:
                    self.assertEqual(connection.execute("SELECT COUNT(*) FROM agent_calls").fetchone()[0], 0)
                    self.assertEqual(connection.execute("SELECT COUNT(*) FROM improvement_operation_attempts").fetchone()[0], 0)

    def test_ordinary_capabilities_keep_real_operation_reservation(self):
        for markers in CONTROLS:
            with self.subTest(markers=markers), scratch(operation_fixtures.OperationExecutionTests) as f:
                service = f.execution()
                capability = {"supported": True, "capability_hash": "c" * 64, **markers}
                with patch("improvement_operation_adapter.ClaudeOperationAdapter.verify", return_value=capability):
                    row = service.reserve(f.owner, f.operation["operation_id"], expected_generation=1,
                                          event_key="ordinary-fence-control")
                self.assertEqual((row["status"], len(row["attempts"])), ("reserved", 1))
                call = service.ledger.get(row["attempts"][0]["call_id"])
                self.assertEqual((call["status"], call["engine_at"]), ("reserved", None))


class TrialRunnerFenceTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, markers, *, refused):
        with scratch(trial_runner_fixtures.TrialRunnerTests) as f:
            # The existing synthetic adapter retains its real packet/start/cleanup flow.
            # Only its capability result is the deliberate engineering seam.
            def factory(*args, **kwargs):
                adapter = f.factory(*args, **kwargs)
                verify = adapter.verify
                adapter.verify = lambda: {**verify(), **markers}
                return adapter

            runner = f.runner(adapter_factory=factory)
            with patch.object(runner, "context_loader", wraps=runner.context_loader) as context, \
                    patch.object(f.f.trials, "materialize", wraps=f.f.trials.materialize) as materialize, \
                    patch.object(f.f.trials, "start_engine", wraps=f.f.trials.start_engine) as start:
                result = await runner.run(f.f.owner, f.trial["trial_id"])
            call = f.call()
            self.assertEqual(len(f.adapters), 1)
            if refused:
                self.assertEqual(result["status"], "not_run")
                self.assertEqual(result["attempts"][0]["failure_reason"], "unsupported_configuration")
                self.assertEqual((call["status"], call["engine_at"]), ("refunded", None))
                self.assertEqual(f.recorders, [])
                self.assertNotIn("execute", f.log)
                context.assert_not_called()
                materialize.assert_not_called()
                start.assert_not_called()
            else:
                self.assertEqual(result["status"], "completed")
                self.assertEqual(call["status"], "ok")
                self.assertIsNotNone(call["engine_at"])
                context.assert_called_once()
                materialize.assert_called_once()
                start.assert_called_once()
                self.assertTrue(f.closed.is_set())
                self.assertLess(f.log.index("recorder-created"), f.log.index("ack"))
            self.assertEqual(len(f.f.ledger.rows()), 1)
            lifetime = f.f.trials.workspace.acquire_brain_execution(f.f.owner.brain_id)
            self.assertIsNotNone(lifetime, "Runner retained the brain execution lifetime")
            lifetime.close()

    async def test_marked_capabilities_refund_claim_before_context_materialization_or_query(self):
        for markers in REFUSALS:
            with self.subTest(markers=markers):
                await self.exercise(markers, refused=True)

    async def test_ordinary_capabilities_keep_real_trial_start_and_settlement(self):
        for markers in CONTROLS:
            with self.subTest(markers=markers):
                await self.exercise(markers, refused=False)


class OperationRunnerFenceTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, markers, *, refused):
        with scratch(operation_runner_fixtures.OperationRunnerTests) as f:
            runner = f.runner()
            original_factory = runner.adapter_factory
            adapters = []

            def factory(*args, **kwargs):
                adapter = original_factory(*args, **kwargs)
                verify = adapter.verify
                adapter.verify = lambda: {**verify(), **markers}
                adapters.append(adapter)
                return adapter

            runner.adapter_factory = factory
            with patch.object(f.execution, "materialize", wraps=f.execution.materialize) as materialize, \
                    patch.object(f.execution, "start_engine", wraps=f.execution.start_engine) as start, \
                    patch.object(runner, "recorder_factory", wraps=runner.recorder_factory) as recorder:
                result = await runner.run(f.owner, f.row["operation_id"])
            call = f.execution.ledger.get(result["attempts"][0]["call_id"])
            self.assertEqual(len(adapters), 1)
            if refused:
                self.assertEqual(result["status"], "not_run")
                self.assertEqual(result["attempts"][0]["failure_reason"], "unsupported_configuration")
                self.assertEqual((call["status"], call["engine_at"]), ("refunded", None))
                self.assertEqual(getattr(f, "native_queries", 0), 0)
                self.assertFalse(f.acked.is_set())
                materialize.assert_not_called()
                start.assert_not_called()
                recorder.assert_not_called()
            else:
                self.assertEqual(result["status"], "completed")
                self.assertEqual(call["status"], "ok")
                self.assertIsNotNone(call["engine_at"])
                self.assertEqual(f.native_queries, 1)
                self.assertTrue(f.closed.is_set())
                self.assertEqual(materialize.call_count, 2)
                start.assert_called_once()
                recorder.assert_called_once()
            self.assertFalse(f.path().exists())
            lifetime = f.execution.workspace.brain_barrier.acquire_brain_execution(f.owner.brain_id)
            self.assertIsNotNone(lifetime, "Runner retained the brain execution lifetime")
            lifetime.close()

    async def test_marked_capabilities_refund_claim_before_materialization_or_query(self):
        for markers in REFUSALS:
            with self.subTest(markers=markers):
                await self.exercise(markers, refused=True)

    async def test_ordinary_capabilities_keep_real_worker_start_and_settlement(self):
        for markers in CONTROLS:
            with self.subTest(markers=markers):
                await self.exercise(markers, refused=False)


if __name__ == "__main__":
    unittest.main()
