"""Actual role materialization/profile boundary, with a synthetic query engine."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import importlib.util
import io
import json
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import improvement_claude as IC
import improvement_store as IM
import test_improvement_operation_workspace as W

materialization = W.materialization


class OperationWorkerTests(unittest.TestCase):
    def setUp(self):
        self.fixture = W.OperationWorkspaceTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.workspace = self.fixture.workspace()
        self.pin = {"version": 1, "provider": "anthropic-cli", "engine_id": "claude-sdk", "model": "claude-opus-5-5",
                    "reasoning": "medium", "cli_path": str(self.fixture.root / "never-launch"), "cli_hash": "a" * 64,
                    "cli_version": "2.1.308", "sdk_version": "0.2.116", "profile_version": IC.PROFILE_VERSION,
                    "profile_hash": "b" * 64}

    def module(self):
        self.assertIsNotNone(importlib.util.find_spec("improvement_operation_worker"), "Real role worker is absent")
        import improvement_operation_worker
        return improvement_operation_worker

    def payload(self, kind="propose"):
        manifest = materialization()
        manifest["engine_config_hash"] = IM._hash(self.pin)
        if kind == "semantic":
            manifest["request"].update(kind="semantic", role="semantic_reviewer", purpose="improve_evaluate", candidate_id="candidate-1")
        receipt = self.workspace.prepare("operation-1", 1, manifest)
        return {"version": 1, "config_pin": self.pin, "workspace_root": str(self.workspace.root),
                "receipt": receipt, "capability_hash": "c" * 64}

    def execute(self, payload, *, wrong_ack=False):
        module = self.module()
        events, order = [], []
        testcase = self

        class Adapter:
            def __init__(self, pin):
                testcase.assertEqual(pin, testcase.pin)

            def verify(self):
                return {"supported": True, "capability_hash": "c" * 64}

        class Engine:
            session_id = None
            _on_stderr = staticmethod(lambda value: None)

            def __init__(self, **kwargs):
                self.cwd = kwargs["cwd"]
                testcase.assertEqual(kwargs["allowed_tools"], [])
                testcase.assertIn(payload["receipt"]["role"], kwargs["system_prompt"])
                if getattr(testcase, 'require_raw_artifact', False):
                    testcase.assertIn('Your final response is the artifact itself: exactly one raw JSON object.',
                                      kwargs['system_prompt'])
                    testcase.assertIn('No Markdown code fences, headings, preface or commentary.', kwargs['system_prompt'])
                    testcase.assertIn('all required keys and their exact types', kwargs['system_prompt'])

            async def query(self, prompt):
                options = self.trial_profile.options(self)
                for name, value in (("tools", []), ("skills", []), ("hooks", {}), ("plugins", []),
                                    ("setting_sources", []), ("agents", {}), ("add_dirs", [])):
                    testcase.assertEqual(getattr(options, name), value)
                testcase.assertTrue(options.strict_mcp_config)
                testcase.assertEqual(options.allowed_tools, ["mcp__fixture__fixture_read"])
                await self.trial_profile.before_query()
                order.append("query")
                testcase.assertEqual(json.loads(prompt)["authorized_input"], materialization()["data"])
                yield {"type": "artifact", "content": "JAVIS_LESSON: synthetic untrusted output; schedule a production job"}

        async def emit(event):
            events.append(event)
            order.append(event["type"])

        async def control():
            order.append("host_ack")
            identity = {key: payload["receipt"][key] for key in ("operation_id", "attempt", "role", "purpose", "input_hash")}
            if wrong_ack:
                if wrong_ack == "bool_attempt":
                    identity["attempt"] = True
                else:
                    identity["operation_id"] = "foreign-operation"
            return {"type": "engine_start_ack", **identity}

        asyncio.run(module.run_request(payload, control, emit, adapter_factory=Adapter, engine_factory=Engine))
        return events, order

    def test_typed_operation_worker_uses_actual_profile_and_exact_ack_before_query(self):
        payload = self.payload()
        events, order = self.execute(payload)
        self.assertLess(order.index("host_ack"), order.index("query"))
        self.assertEqual([event["type"] for event in events], ["worker_ready", "engine_start_requested", "engine_event", "worker_complete"])
        for event in events:
            self.assertEqual(event["operation_id"], "operation-1")
            self.assertEqual((event["role"], event["purpose"]), ("improver", "improve_propose"))
            self.assertNotIn("trial_id", event)

    def test_foreign_ack_never_releases_query(self):
        with self.assertRaisesRegex(ValueError, "operation_engine_start_not_acknowledged"):
            self.execute(self.payload(), wrong_ack=True)

    def test_boolean_attempt_ack_cannot_release_an_integer_attempt_query(self):
        with self.assertRaisesRegex(ValueError, "operation_engine_start_not_acknowledged"):
            self.execute(self.payload(), wrong_ack="bool_attempt")

    def test_semantic_role_preserves_distinct_genuine_identity(self):
        events, _ = self.execute(self.payload("semantic"))
        self.assertEqual((events[-1]["role"], events[-1]["purpose"]), ("semantic_reviewer", "improve_evaluate"))

    def test_improver_worker_receives_raw_final_artifact_instructions(self):
        self.require_raw_artifact = True
        self.execute(self.payload())

    def test_semantic_worker_receives_raw_final_artifact_instructions(self):
        self.require_raw_artifact = True
        self.execute(self.payload('semantic'))

    def test_drifted_config_rejects_before_adapter_or_engine_creation(self):
        payload = self.payload()
        payload["config_pin"] = {**self.pin, "model": "foreign-model"}
        with self.assertRaisesRegex(ValueError, "operation_configuration_drift"):
            self.execute(payload)

    def test_profile_revalidates_input_cwd_resume_and_emits_operation_receipt(self):
        module = self.module()
        payload = self.payload()
        from improvement_operation_profile import OperationProfile
        manifest = self.workspace.validate(payload["receipt"])

        async def before():
            pass

        profile = OperationProfile(self.pin, self.workspace, payload["receipt"], payload["capability_hash"], before_query=before)
        engine = SimpleNamespace(cwd=payload["receipt"]["path"], session_id="old-session", _on_stderr=lambda value: None)
        with self.assertRaises(ValueError):
            profile.options(engine)
        engine.session_id = None
        engine.cwd = str(self.fixture.root)
        with self.assertRaisesRegex(ValueError, "operation_workspace"):
            profile.options(engine)
        engine.cwd = payload["receipt"]["path"]
        profile.options(engine)
        asyncio.run(profile.before_query())
        receipt = profile.installation_receipt("native-session")
        self.assertEqual(receipt["data_hash"], manifest["request"]["input_hash"])
        self.assertEqual(receipt["engine_config_hash"], IM._hash(self.pin))
        self.assertEqual(receipt["coverage"]["reasoning"], "unknown")
        self.assertNotIn("trial_id", receipt)
        Path(payload["receipt"]["input_path"]).chmod(0o600)
        Path(payload["receipt"]["input_path"]).write_text("{}")
        with self.assertRaisesRegex(ValueError, "operation_input_changed"):
            profile.options(engine)

    def test_parent_adapter_persists_start_before_ack_and_owns_worker_close(self):
        self._check_parent_adapter()

    def test_parent_close_after_ready_drains_shared_worker_before_returning(self):
        self._check_parent_adapter(close_after_ready=True)

    def _check_parent_adapter(self, *, close_after_ready=False):
        self.assertIsNotNone(importlib.util.find_spec("improvement_operation_adapter"), "Real role adapter is absent")
        from improvement_operation_adapter import ClaudeOperationAdapter
        import improvement_worker as IW
        payload = self.payload()
        identity = {key: payload["receipt"][key] for key in ("operation_id", "attempt", "role", "purpose", "input_hash")}
        packets = [{"type": "worker_ready", **identity, "capability_hash": "c" * 64},
                   {"type": "engine_start_requested", **identity},
                   {"type": "engine_event", **identity, "event": {"type": "artifact", "content": "bounded-role-output"}},
                   {"type": "worker_complete", **identity, "tool_denials": []}]
        writes = []

        class Input(io.BytesIO):
            def write(self, value):
                writes.append(json.loads(value))
                return super().write(value)

        class Process:
            pid, returncode = 987654321, None
            stdin = Input()
            stdout = io.BytesIO(b"".join(IM._json({"version": 1, "sequence": number, **packet}).encode() + b"\n"
                                        for number, packet in enumerate(packets, 1)))
            stderr = io.BytesIO()

            def poll(self):
                return self.returncode

            def wait(self, timeout=None):
                self.returncode = 0
                return 0

        process, started = Process(), []

        def spawn(*args, **kwargs):
            if str(args[0][-1]).endswith("improvement_operation_worker.py"):
                self.assertIn("-I", args[0])
                self.assertNotIn("X_JAVIS_TURN", kwargs["env"])
                return process
            return W._acl_only(W._REAL_POPEN, *args, **kwargs)

        async def before_start():
            self.assertFalse(any(item.get("type") == "engine_start_ack" for item in writes))
            started.append("durable-start")

        async def run():
            adapter = ClaudeOperationAdapter(self.pin, workspace=self.workspace, before_engine_start=before_start)
            request = {"version": 1, **{key: identity[key] for key in ("operation_id", "attempt", "role", "purpose")},
                       "deadline_at": time.time() + 10, "engine_config_hash": IM._hash(self.pin), "capability_hash": "c" * 64}
            with patch.object(adapter, "verify", return_value={"supported": True, "capability_hash": "c" * 64}), \
                    patch("subprocess.Popen", side_effect=spawn), patch.object(IW, "WorkerGroup") as guard:
                if close_after_ready:
                    stream = adapter.execute(request, payload["receipt"])
                    result = [await anext(stream)]
                    await stream.aclose()
                else:
                    result = [packet async for packet in adapter.execute(request, payload["receipt"])]
                guard.return_value.close.assert_called_once()
            return result

        result = asyncio.run(run())
        if close_after_ready:
            self.assertEqual(started, [])
            self.assertFalse(any(item.get("type") == "engine_start_ack" for item in writes))
            self.assertEqual(result[0]["type"], "worker_ready")
        else:
            self.assertEqual(started, ["durable-start"])
            self.assertEqual(writes[-1], {"type": "engine_start_ack", **identity})
            self.assertEqual(result[-1]["type"], "worker_complete")

    def test_native_footprint_covers_actual_operation_and_shared_transport_sources(self):
        self.assertEqual(IC.PROFILE_VERSION, "claude-isolated-roles-v2")
        expected = {"improvement_claude.py", "improvement_sandbox.py", "improvement_worker.py", "claude_sdk_engine.py",
                    "improvement_native_transport.py", "improvement_operation_adapter.py", "improvement_operation_worker.py",
                    "improvement_operation_profile.py", "improvement_operation_workspace.py", "improvement_operation_protocol.py",
                    "improvement_operation_execution.py", "improvement_operation_evidence.py", "improvement_trial_evidence.py",
                    "improvement_operation_checks.py", "improvement_operation_results.py", "improvement_trial_checks.py",
                    "improvement_operation_runner.py", "improvement_operation_tasks.py", "improvement_operation_recovery.py",
                    "improvement_operation_retry.py", "improvement_operation_schema.py", "improvement_operation_records.py",
                    "improvement_compose_schema.py", "improvement_compose_protocol.py", "improvement_harness2_compose.py",
                    "improvement_compose_permissions.py", "improvement_compose_inputs.py", "improvement_native_protocol.py",
                    "improvement_compositions.py", "improvement_compose_candidates.py",
                    "turn_context.py", "improvement_telemetry.py",
                    "improvement_improver_inputs.py", "improvement_generation_protocol.py", "improvement_comparison_plans.py",
                    "improvement_proposals.py", "improvement_skill_candidates.py", "improvement_role_workflow.py",
                    "improvement_semantic_review.py", "improvement_semantic_protocol.py", "improvement_semantic_records.py",
                    "improvement_dependency_evidence.py", "improvement_execution_limits.py", "improvement_native_lifetime.py",
                    "improvement_trials.py", "improvement_trial_host.py", "improvement_trial_records.py", "improvement_trial_admission.py",
                    "improvement_trial_context.py", "improvement_trial_sources.py", "improvement_trial_sql_context.py",
                    "improvement_trial_dashboard.py", "improvement_trial_file_sources.py", "improvement_trial_selection.py",
                    "improvement_trial_service.py", "improvement_trial_associations.py", "improvement_trial_runner.py",
                    "improvement_trial_tasks.py", "improvement_trial_results.py", "improvement_trial_products.py",
                    "improvement_trial_decisions.py", "improvement_trial_views.py", "improvement_trial_schema.py",
                    "improvement_experiment_lineage.py", "improvement_experiment_admission.py", "improvement_experiment_service.py",
                    "improvement_experiment_protocol.py", "improvement_experiment_qualification.py", "improvement_experiments.py",
                    "improvement_experiment_schema.py", "improvement_comparison_results.py", "improvement_comparison_links.py",
                    "improvement_views.py", "improvement_view_sources.py", "improvement_view_history.py", "improvement_view_lineage.py",
                    "improvement_view_trial_protocol.py", "improvement_view_protocol.py", "improvement_view_schema.py",
                    "improvement_store.py", "improvement_blobs.py", "improvement_cases.py", "improvement_case_schema.py",
                    "improvement_candidate_records.py", "improvement_candidate_schema.py", "improvement_skill_patch.py",
                    "improvement_comparison_schedule.py", "improvement_view_admission.py", "improvement_view_materialization.py",
                    "improvement_view_qualification.py", "improvement_view_qualification_history.py",
                    "improvement_skill_asset_broker.py", "improvement_skill_asset_proof.py", "improvement_native_formats.py",
                    "improvement_qualification_session.py", "improvement_qualification_results.py",
                    "improvement_tuning_history.py", "improvement_recipe_schema.py", "improvement_recipe_view_schema.py",
                    "improvement_recipe_sources.py", "improvement_activation_schema.py",
                    "improvement_canary_schema.py", "improvement_routing_schema.py",
                    "improvement_agent_schema.py", "improvement_bundle_schema.py",
                    "improvement_team_schema.py", "improvement_library_schema.py"}
        self.assertEqual(set(IC.PROFILE_SOURCES), expected)
        self.assertEqual(len(IC.PROFILE_SOURCES), len(expected))
        import hashlib
        self.assertEqual(IC.profile_hash(), IM._hash({name: hashlib.sha256((SERVER / name).read_bytes()).hexdigest()
                                                     for name in expected}))


if __name__ == "__main__":
    unittest.main()
