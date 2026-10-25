"""Synthetic asynchronous adapters exercise real trial storage without native/model calls."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import copy
import importlib.util
import threading
import time
import unittest
from unittest.mock import patch

import test_improvement_trials as fixtures
import improvement_store as IM
import turn_context

if importlib.util.find_spec("improvement_trial_runner"):
    import improvement_trial_runner as runner_module
else:
    runner_module = None


class TrialRunnerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.assertIsNotNone(runner_module, "Host trial runner is not implemented")
        self.f = fixtures.TrialStoreTests()
        self.f.setUp()
        self.trial = self.f.reserve()
        self.log, self.adapters, self.recorders = [], [], []
        self.revoked = False
        self.supported = True
        self.hang = False
        self.cleanup_failure = False
        self.before_callback = None
        self.after_ack = None
        self.after_cleanup = None
        self.acked, self.closed = asyncio.Event(), asyncio.Event()
        self.usage_patch = patch("improvement_usage.trial_usage", return_value={
            "label": "synthetic", "coverage": {"status": "partial"}, "requests": None})
        self.usage_patch.start()
        self.addCleanup(self.usage_patch.stop)

    def guard(self, principal, request):
        self.assertEqual(principal, self.f.owner)
        value = {key: request[key] for key in ("baseline_context_hash", "target_generations")}
        value.update({key: request["pins"][key] for key in ("scope_hash", "grant_hash", "engine_config_hash")})
        return {**value, "grant_hash": "f" * 64} if self.revoked else copy.deepcopy(value)

    def factory(self, pin, *, workspace_root, before_engine_start):
        test = self

        class Adapter:
            def verify(self):
                test.log.append("verify")
                return {"supported": test.supported, "capability_hash": "d" * 64}

            async def execute(self, request, workspace):
                test.log.append("execute")
                identity = {key: workspace[key] for key in ("trial_id", "attempt", "input_hash")}

                def packet(number, kind, **fields):
                    return {"version": 1, "sequence": number, "type": kind, **identity, **fields}

                try:
                    yield packet(1, "worker_ready", capability_hash="d" * 64)
                    if test.before_callback:
                        test.before_callback()
                    await before_engine_start()
                    test.log.append("ack")
                    test.acked.set()
                    if test.after_ack:
                        await test.after_ack()
                    yield packet(2, "engine_start_requested")
                    events = [
                        {"type": "observation", "model": pin["model"], "message_id": "synthetic-request",
                         "session_id": "synthetic-session", "usage": {"input_tokens": 3, "output_tokens": 2}},
                        {"type": "artifact", "content": '{"value":"synthetic"}\r\n',
                         "hash": fixtures.fixtures.digest('{"value":"synthetic"}\r\n')},
                        {"type": "installation_receipt", "receipt": {"label": "synthetic"},
                         "hash": IM._hash({"label": "synthetic"})},
                        {"type": "terminal", "subtype": "success", "is_error": False, "artifact_status": "observed"}]
                    for number, event in enumerate(events, 3):
                        yield packet(number, "engine_event", event=event)
                        if test.hang and number == 3:
                            await asyncio.Event().wait()
                    yield packet(7, "worker_complete", fixture_events=[], tool_denials=[])
                finally:
                    await asyncio.sleep(0)
                    test.log.append("closed")
                    test.closed.set()
                    if test.after_cleanup:
                        test.after_cleanup()
                    if test.cleanup_failure:
                        raise RuntimeError("synthetic cleanup failure")

        self.adapters.append(Adapter())
        self.assertEqual(pin, self.f.request["engine_config"])
        self.assertEqual(workspace_root, self.f.trials.workspace.root)
        return self.adapters[-1]

    def recorder(self, ledger, call_id, execution, *, brain_id, provider, model):
        test = self
        call = ledger.get(call_id)
        self.assertIsNotNone(call["engine_at"])
        self.assertEqual(call["status"], "running")
        self.assertEqual((brain_id, provider, model), (self.f.owner.brain_id, "anthropic-cli", "claude-opus-5-5"))
        self.assertEqual(execution["trial_id"], self.trial["trial_id"])
        self.assertEqual(execution["attempt"], 1)
        self.assertIsNotNone(turn_context.execution_metadata(execution), "Recorder identity must use the host canonical schema")
        self.log.append("recorder-created")

        class Recorder:
            def observe(self, event, *, sequence):
                test.log.append("observe:" + str(sequence))
                if not getattr(test, "allow_unpersisted_usage", False):
                    saved = test.f.trials.read_observation(test.f.owner, test.trial["trial_id"], 1, sequence)
                    test.assertEqual(saved["event"], event)
                self.observed.append((sequence, event))

            def finish(self, status):
                test.log.append("usage-finish:" + status)
                self.finished.append(status)

            observed = None
            finished = None

        value = Recorder()
        value.observed, value.finished = [], []
        self.recorders.append(value)
        return value

    def runner(self, **changes):
        fields = {"context_loader": lambda p, r: copy.deepcopy(self.f.context), "live_guard": self.guard,
                  "adapter_factory": self.factory, "recorder_factory": self.recorder, "checker_registry": {}}
        return runner_module.TrialRunner(self.f.trials, **{**fields, **changes})

    async def run_trial(self, **changes):
        return await self.runner(**changes).run(self.f.owner, self.trial["trial_id"])

    def call(self):
        return self.f.ledger.get(self.trial["attempts"][0]["call_id"])

    async def test_cancelled_verification_retains_execution_until_thread_settles(self):
        entered, release = threading.Event(), threading.Event()
        original_factory = self.factory

        def factory(*args, **kwargs):
            adapter = original_factory(*args, **kwargs)
            original = adapter.verify

            def blocked():
                entered.set()
                if not release.wait(15):
                    raise RuntimeError("synthetic verification barrier expired")
                return original()

            adapter.verify = blocked
            return adapter

        task = asyncio.create_task(self.run_trial(adapter_factory=factory))
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 15))
            task.cancel()
            await asyncio.sleep(.05)
            task.cancel()
            await asyncio.wait((task,), timeout=1)
            self.assertFalse(task.done(), "verification escaped its owned execution")
            other = self.f.trials.workspace.acquire_brain_execution(self.f.owner.brain_id)
            try:
                self.assertIsNone(other, "verification released its brain lifetime early")
            finally:
                if other is not None:
                    other.close()
        finally:
            release.set()
            await asyncio.gather(task, return_exceptions=True)
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertNotIn("execute", self.log)
        self.assertIsNone(self.call()["engine_at"])
        self.assertEqual(self.call()["status"], "refunded")

    async def test_success_orders_marker_and_recorder_before_ack_and_cleanup_before_evaluation(self):
        original = self.f.trials.stage_evaluation

        def stage(*args, **kwargs):
            self.assertTrue(self.closed.is_set())
            self.log.append("stage")
            return original(*args, **kwargs)

        with patch.object(self.f.trials, "stage_evaluation", side_effect=stage):
            result = await self.run_trial()
        self.assertEqual(result["status"], "completed")
        self.assertIsInstance(result["result"], dict)
        self.assertEqual(result["result"]["usage"]["coverage"]["status"], "partial")
        self.assertLess(self.log.index("recorder-created"), self.log.index("ack"))
        self.assertLess(self.log.index("closed"), self.log.index("stage"))
        self.assertEqual(self.recorders[0].finished, ["completed"])
        self.assertEqual(self.call()["status"], "ok")
        with self.f.rs._conn() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM improvement_trial_observations").fetchone()[0], 7)

    async def test_host_claim_callback_observes_owned_lease_before_any_adapter(self):
        observed = []

        def claimed(row):
            self.assertEqual(self.adapters, [])
            self.assertIsNotNone(row["lease_token"])
            self.assertIsNone(self.call()["engine_at"])
            observed.append(row)

        result = await self.runner().run(self.f.owner, self.trial["trial_id"], on_claimed=claimed)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(observed), 1)

    async def test_failing_host_claim_callback_refunds_owned_claim_without_query(self):
        def fail(row):
            raise RuntimeError("synthetic claim observer failed")

        with self.assertRaises(RuntimeError):
            await self.runner().run(self.f.owner, self.trial["trial_id"], on_claimed=fail)
        self.assertEqual(self.call()["status"], "refunded")
        self.assertEqual(self.adapters, [])

    async def test_async_host_claim_callback_is_rejected_before_claim(self):
        async def unsupported(row):
            pass

        with self.assertRaises(ValueError):
            await self.runner().run(self.f.owner, self.trial["trial_id"], on_claimed=unsupported)
        self.assertEqual(self.f.trials.get(self.f.owner, self.trial["trial_id"])["generation"], 1)

    async def test_repeated_terminal_run_returns_stored_result_without_another_adapter_or_call(self):
        first = await self.run_trial()
        second = await self.run_trial()
        self.assertEqual(first, second)
        self.assertEqual(len(self.adapters), 1)
        self.assertEqual(len(self.f.ledger.rows()), 1)

    async def test_real_usage_recorder_accepts_canonical_identity_and_preserves_unknown_telemetry(self):
        records = []
        with patch("improvement_telemetry.usage_index.improvement_events", return_value=([], [])), \
             patch("improvement_telemetry.usage_store.record", side_effect=lambda *a, **kw: records.append((a, kw))), \
             patch("improvement_telemetry.usage_store.improvement_telemetry_errors", return_value=0):
            result = await self.run_trial(recorder_factory=runner_module.NativeUsageRecorder)
        self.assertEqual(result["status"], "completed")
        self.assertTrue(records)
        for _, fields in records:
            self.assertEqual(fields["execution"]["execution_id"], "improvement_trial:" + self.trial["trial_id"])
            self.assertEqual(fields["execution"]["attempt"], 1)
        terminal = records[-1][1]
        self.assertEqual(terminal["event_kind"], "execution")
        self.assertFalse(terminal["usage_complete"])

    async def test_unsupported_adapter_refunds_before_any_query_or_recorder(self):
        self.supported = False
        result = await self.run_trial()
        self.assertEqual(result["status"], "not_run")
        self.assertNotIn("execute", self.log)
        self.assertEqual(self.recorders, [])
        self.assertEqual(self.call()["status"], "refunded")

    async def test_host_callbacks_are_required_and_foreign_scope_cannot_query(self):
        for field in ("context_loader", "live_guard"):
            with self.assertRaises(ValueError):
                self.runner(**{field: None})
        with self.assertRaises(PermissionError):
            await self.runner().run(self.f.other, self.trial["trial_id"])
        self.assertEqual(self.adapters, [])

    async def test_async_host_dependencies_are_rejected_before_claim(self):
        async def asynchronous(*args, **kwargs):
            return None

        class AsyncCallable:
            async def __call__(self, *args, **kwargs):
                return None

        for field in ("context_loader", "live_guard", "adapter_factory", "recorder_factory"):
            for dependency in (asynchronous, AsyncCallable()):
                with self.assertRaises(ValueError):
                    self.runner(**{field: dependency})
        self.assertEqual(self.f.trials.get(self.f.owner, self.trial["trial_id"])["status"], "reserved")

    async def test_cancellation_waits_for_inflight_start_and_closes_its_committed_call(self):
        entered, release = threading.Event(), threading.Event()
        original = self.f.trials.start_engine

        def blocked(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("synthetic start barrier expired")
            return original(*args, **kwargs)

        with patch.object(self.f.trials, "start_engine", side_effect=blocked):
            task = asyncio.create_task(self.run_trial())
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 5))
                task.cancel()
                await asyncio.sleep(0.05)
                task.cancel()
                await asyncio.sleep(0.05)
                self.assertFalse(task.done(), "Runner must settle its owned transition before returning")
            finally:
                release.set()
                await asyncio.gather(task, return_exceptions=True)
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertNotIn("ack", self.log)
        self.assertTrue(self.closed.is_set())
        self.assertEqual(self.f.trials.get(self.f.owner, self.trial["trial_id"])["status"], "unknown")
        self.assertEqual(self.call()["status"], "interrupted")

    async def test_cancellation_revokes_inflight_evaluation_before_waiting_for_its_thread(self):
        entered, release = threading.Event(), threading.Event()
        from improvement_trial_results import EVAL
        original = EVAL.evaluate_trial

        def blocked(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("synthetic finish barrier expired")
            return original(*args, **kwargs)

        # Block after finish captured its leased snapshot and released the DB lock.
        with patch.object(EVAL, "evaluate_trial", side_effect=blocked):
            task = asyncio.create_task(self.run_trial())
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 5))
                task.cancel()
                for _ in range(100):
                    status = self.f.trials.get(self.f.owner, self.trial["trial_id"])["status"]
                    if status == "unknown":
                        break
                    await asyncio.sleep(0.01)
                self.assertEqual(status, "unknown")
                task.cancel()
                await asyncio.sleep(0.05)
                self.assertFalse(task.done(), "Runner cannot return with its evaluation thread in flight")
            finally:
                release.set()
                await asyncio.gather(task, return_exceptions=True)
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.f.trials.get(self.f.owner, self.trial["trial_id"])["status"], "unknown")
        with self.assertRaises(PermissionError):
            self.f.trials.read_result(self.f.owner, self.trial["trial_id"], 1)
        self.assertEqual(self.call()["status"], "interrupted")

    async def test_cancellation_during_claim_refunds_the_committed_lease_without_an_adapter(self):
        entered, release = threading.Event(), threading.Event()
        original = self.f.trials.claim

        def blocked(*args, **kwargs):
            result = original(*args, **kwargs)
            entered.set()
            if not release.wait(5):
                raise RuntimeError("synthetic claim barrier expired")
            return result

        with patch.object(self.f.trials, "claim", side_effect=blocked):
            task = asyncio.create_task(self.run_trial())
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 5))
                task.cancel()
                await asyncio.sleep(0.05)
                task.cancel()
                await asyncio.sleep(0.05)
                self.assertFalse(task.done())
            finally:
                release.set()
                await asyncio.gather(task, return_exceptions=True)
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.adapters, [])
        self.assertEqual(self.f.trials.get(self.f.owner, self.trial["trial_id"])["status"], "not_run")
        self.assertIsNone(self.call()["engine_at"])
        self.assertEqual(self.call()["status"], "refunded")

    async def test_guard_revoked_at_ack_boundary_does_not_mark_or_release_query(self):
        self.before_callback = lambda: setattr(self, "revoked", True)
        result = await self.run_trial()
        self.assertEqual(result["status"], "not_run")
        self.assertNotIn("ack", self.log)
        self.assertTrue(self.closed.is_set())
        self.assertIsNone(self.call()["engine_at"])
        self.assertEqual(self.call()["status"], "refunded")

    async def test_policy_revoked_before_claim_refunds_unclaimed_reservation(self):
        self.f.assets.set_policy(self.f.owner, "off", expected_version=0,
                                 event_key="synthetic-before-claim-policy-off")
        result = await self.run_trial()
        self.assertEqual(result["status"], "not_run")
        self.assertEqual(result["attempts"][-1]["failure_reason"], "authority_changed")
        self.assertEqual(self.adapters, [])
        self.assertIsNone(self.call()["engine_at"])
        self.assertEqual(self.call()["status"], "refunded")

    async def test_postmarker_guard_revocation_cancels_closes_and_keeps_counted_usage(self):
        self.hang = True

        async def revoke():
            self.revoked = True

        self.after_ack = revoke
        with patch.object(runner_module, "HEARTBEAT_SECONDS", 0.01):
            result = await asyncio.wait_for(self.run_trial(), 5)
        self.assertEqual(result["status"], "unknown")
        self.assertTrue(self.closed.is_set())
        self.assertIsNotNone(self.call()["engine_at"])
        self.assertEqual(self.call()["status"], "interrupted")
        self.assertEqual(self.recorders[0].finished[-1], "unknown")

    async def test_external_cancellation_remains_terminal_and_stops_the_query(self):
        self.hang = True
        with patch.object(runner_module, "HEARTBEAT_SECONDS", 0.01):
            task = asyncio.create_task(self.run_trial())
            await asyncio.wait_for(self.acked.wait(), 5)
            current = self.f.trials.get(self.f.owner, self.trial["trial_id"])
            self.f.trials.cancel(self.f.owner, self.trial["trial_id"], expected_generation=current["generation"],
                                 event_key="synthetic-external-cancel")
            result = await asyncio.wait_for(task, 5)
        self.assertEqual(result["status"], "cancelled")
        self.assertTrue(self.closed.is_set())
        self.assertEqual(self.call()["status"], "interrupted")

    async def test_task_cancellation_awaits_generator_cleanup_before_abort(self):
        self.hang = True
        task = asyncio.create_task(self.run_trial())
        await asyncio.wait_for(self.acked.wait(), 5)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(self.closed.is_set())
        self.assertEqual(self.f.trials.get(self.f.owner, self.trial["trial_id"])["status"], "unknown")
        self.assertEqual(self.call()["status"], "interrupted")

    async def test_append_failure_still_records_known_usage_and_never_requeries(self):
        original = self.f.trials.append_observation
        self.allow_unpersisted_usage = True

        def append(*args, **kwargs):
            if args[2].get("event", {}).get("type") == "observation":
                raise OSError("synthetic evidence disk failure")
            return original(*args, **kwargs)

        with patch.object(self.f.trials, "append_observation", side_effect=append):
            result = await self.run_trial()
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(self.recorders[0].observed[0][1]["usage"]["input_tokens"], 3)
        self.assertEqual(self.recorders[0].finished[-1], "unknown")
        await self.run_trial()
        self.assertEqual(len(self.adapters), 1)

    async def test_worker_cleanup_failure_after_complete_cannot_publish_a_result(self):
        self.cleanup_failure = True
        result = await self.run_trial()
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["result"])
        self.assertTrue(self.closed.is_set())
        self.assertEqual(self.call()["status"], "interrupted")

    async def test_guard_rechecked_after_cleanup_before_evaluation(self):
        self.after_cleanup = lambda: setattr(self, "revoked", True)
        with patch.object(self.f.trials, "stage_evaluation", wraps=self.f.trials.stage_evaluation) as stage:
            result = await self.run_trial()
        self.assertEqual(result["status"], "unknown")
        stage.assert_not_called()
        self.assertEqual(self.recorders[0].finished[-1], "unknown")

    async def test_invalid_recorder_cannot_release_worker_ack_after_the_marker(self):
        result = await self.run_trial(recorder_factory=lambda *args, **kwargs: object())
        self.assertEqual(result["status"], "unknown")
        self.assertNotIn("ack", self.log)
        self.assertIsNotNone(self.call()["engine_at"])
        self.assertEqual(self.call()["status"], "interrupted")
        self.assertTrue(self.closed.is_set())

    async def test_inflight_repeat_cannot_construct_a_second_adapter_or_steal_the_lease(self):
        self.hang = True
        task = asyncio.create_task(self.run_trial())
        await asyncio.wait_for(self.acked.wait(), 5)
        repeated = await self.run_trial()
        self.assertEqual(repeated["status"], "running")
        self.assertEqual(len(self.adapters), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_policy_revocation_is_detected_even_when_host_guard_hashes_match(self):
        self.hang = True

        async def revoke_policy():
            await asyncio.to_thread(self.f.assets.set_policy, self.f.owner, "off", expected_version=0,
                                    event_key="synthetic-runner-policy-off")

        self.after_ack = revoke_policy
        with patch.object(runner_module, "HEARTBEAT_SECONDS", 0.01):
            result = await asyncio.wait_for(self.run_trial(), 5)
        self.assertEqual(result["status"], "unknown")
        self.assertTrue(self.closed.is_set())
        self.assertEqual(self.call()["status"], "interrupted")

    async def test_deadline_closes_started_query_without_refund(self):
        self.hang = True
        self.f.request["repeat"] = 2
        self.f.request["deadline_at"] = time.time() + 1.5
        self.trial = self.f.reserve(key="short-deadline-trial", **self.f.request)
        result = await asyncio.wait_for(self.run_trial(), 5)
        self.assertEqual(result["status"], "unknown")
        self.assertTrue(self.closed.is_set())
        self.assertEqual(self.call()["status"], "interrupted")


if __name__ == "__main__":
    unittest.main()
