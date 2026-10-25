"""Actual owner HTTP composition with synthetic native packets, never a model call.

This verifies integration and accounting, not native isolation, model feasibility,
business quality, or a complete production Dashboard profile.
"""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import hashlib
import json
import subprocess
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import httpx
import test_improvement_trial_service as fixtures
import improvement_store as IM
from improvement_claude import ClaudeTrialAdapter
from improvement_trials import TrialStore
from agent_ledger import CallLedger
import usage_store as US
import usage_index as UI

_REAL_RUN, _REAL_POPEN = subprocess.run, subprocess.Popen


def _acl_only(original, command, *args, **kwargs):
    if Path(command[0]).name.lower() not in {"whoami", "whoami.exe", "icacls", "icacls.exe"}:
        raise AssertionError("Only scratch workspace ACL metadata commands are permitted")
    return original(command, *args, **kwargs)


class OwnerTrialEndToEndTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fixture = fixtures.DashboardServiceTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f, self.main = self.fixture.f, self.fixture.host
        self.assets, self.stack = self.fixture.assets, self.fixture.stack
        for obj, name, value in ((self.main, "_resonance_store", lambda: self.assets.store),
                (self.main, "RevisionBlobs", lambda *a, **kw: self.assets.blobs),
                (self.main, "_IMPROVEMENT_TRIAL_SERVICE", None),
                (self.main, "_IMPROVEMENT_TRIAL_SHUTTING_DOWN", False),
                (self.main.cfgmod, "gate_active", lambda: False),
                (US, "_PATH", self.f.state / "usage.json"),
                (US, "_EVENTS_PATH", self.f.state / "usage-events.jsonl"),
                (US, "_TELEMETRY_ERRORS", {}),
                (UI, "_EVENTS_PATH", self.f.state / "usage-events.jsonl"),
                (UI, "DB_PATH", self.f.state / "usage_index.db"),
                (UI, "_claude_dir", lambda: str(self.f.state / "empty-native")),
                (UI, "_codex_dir", lambda: str(self.f.state / "empty-codex"))):
            self.stack.enter_context(patch.object(obj, name, value))
        self.stack.enter_context(patch("subprocess.run", side_effect=lambda *a, **kw: _acl_only(_REAL_RUN, *a, **kw)))
        self.stack.enter_context(patch("subprocess.Popen", side_effect=lambda *a, **kw: _acl_only(_REAL_POPEN, *a, **kw)))
        self.execute_count, self.verify_count, self.closed = 0, 0, False
        test = self

        def verify(adapter):
            test.verify_count += 1
            if test.verify_count == 1:
                with closing(test.assets.store._conn()) as connection:
                    test.assertEqual(connection.execute("SELECT COUNT(*) FROM agent_calls").fetchone()[0], 0)
            return {"supported": True, "capability_hash": "d" * 64}

        async def execute(adapter, request, workspace):
            test.execute_count += 1
            identity = {key: workspace[key] for key in ("trial_id", "attempt", "input_hash")}
            def packet(sequence, kind, **fields):
                return {"version": 1, "sequence": sequence, "type": kind, **identity, **fields}
            try:
                yield packet(1, "worker_ready", capability_hash="d" * 64)
                await adapter.before_engine_start()
                # The actual Runner has persisted the marker and constructed the
                # real NativeUsageRecorder before releasing the synthetic ACK.
                row = await asyncio.to_thread(TrialStore(test.assets).get, test.owner, request["trial_id"])
                call = CallLedger(test.assets.store).get(row["attempts"][0]["call_id"])
                test.assertIsNotNone(call["engine_at"])
                test.assertEqual(call["status"], "running")
                yield packet(2, "engine_start_requested")
                artifact = '{"value":"synthetic fixture result"}\r\n'
                events = [
                    {"type": "native_system", "subtype": "init", "data": {"session_id": "synthetic-e2e-session"}},
                    {"type": "observation", "model": adapter.pin["model"], "message_id": "synthetic-e2e-request",
                     "session_id": "synthetic-e2e-session", "usage": {"input_tokens": 3, "output_tokens": 2,
                        "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}},
                    {"type": "artifact", "content": artifact, "hash": hashlib.sha256(artifact.encode()).hexdigest()},
                    {"type": "installation_receipt", "receipt": {"label": "synthetic-incomplete"},
                     "hash": IM._hash({"label": "synthetic-incomplete"})},
                    {"type": "terminal", "subtype": "success", "is_error": False, "artifact_status": "observed"}]
                for sequence, event in enumerate(events, 3):
                    yield packet(sequence, "engine_event", event=event)
                yield packet(8, "worker_complete", fixture_events=[], tool_denials=[])
            finally:
                test.closed = True
        self.stack.enter_context(patch.object(ClaudeTrialAdapter, "verify", verify))
        # The runner verifies real Claude adapters through the owned async preflight.
        async def verify_async(adapter):
            return verify(adapter)
        self.stack.enter_context(patch.object(ClaudeTrialAdapter, "verify_async", verify_async))
        self.stack.enter_context(patch.object(ClaudeTrialAdapter, "execute", execute))
        from resonance_store import Principal
        self.owner = Principal("owner", "owner", str(self.f.brain))
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.main.app), base_url="http://localhost")
        self.addAsyncCleanup(self.client.aclose)
        self.addAsyncCleanup(self.main._shutdown_improvement_trials)

    async def request(self, method, path, *, status=200, brain=None, **kwargs):
        response = await self.client.request(method, path, params={"brain": str(brain or self.f.brain)}, **kwargs)
        self.assertEqual(response.status_code, status, response.text)
        for private in ("cli_path", "PRIVATE MUTABLE TARGET BODY", "PRIVATE OWNER ANSWER", str(self.f.root)):
            self.assertNotIn(private, response.text)
        return response.json()

    async def test_actual_main_owner_lifecycle_counts_one_synthetic_query_and_preserves_unknowns(self):
        selections = []
        for split in ("tuning", "qualification", "regression"):
            ref = "brain-file:reports/" + split + ".json"
            self.f.write(self.f.brain, "reports/" + split + ".json", json.dumps({"source": split, "value": split}))
            selections.append({**self.fixture.selections[0], "source_ref": ref})
        experiment = "e2e-owner-experiment"
        context = (await self.request("POST", "/improvement-contexts/" + experiment, status=201, json={
            "event_key": "e2e-create-context", "surface": self.f.surface,
            "target_ids": [self.fixture.target["target_id"]], "source_selections": selections}))["context"]
        self.assertIsNone(self.main._IMPROVEMENT_TRIAL_SERVICE)
        snapshots = []
        for selection in selections:
            snapshots.append((await self.request("POST", f"/improvement-contexts/{experiment}/snapshots", status=201,
                json={"event_key": "e2e-snapshot-" + selection["source_ref"].split("/")[-1],
                    "source_ref": selection["source_ref"]}))["snapshot"])
        contract = {"event_key": "e2e-contract-create", "objective": "Return a JSON value from the authorized fixture.",
            "output": {"kind": "text", "path": "answer.json", "media_type": "application/json"},
            "criteria": [{"id": "shape", "category": "mandatory", "critical": True, "description": "A value object.",
                "kind": "json_keys", "config": {"path": "answer.json", "keys": ["value"]}},
                {"id": "business", "category": "business", "critical": True, "description": "Owner confirmation.",
                 "kind": "owner_confirm", "config": {"path": "answer.json"}}],
            "primary_metric": {"criterion_id": "business", "direction": "higher", "aggregation": "all_pass"},
            "unknown_conditions": ["missing_artifact"]}
        saved = (await self.request("POST", "/improvement-contracts", status=201, json=contract))["contract"]
        cases = [{"id": split, "family_key": "family-" + split, "split": split,
            "task": "Return a value object using only the authorized fixture.", "snapshot_ids": [snapshot["snapshot_id"]],
            "answer": {"expected": "PRIVATE OWNER ANSWER " + split}}
            for split, snapshot in zip(("tuning", "qualification", "regression"), snapshots)]
        case_set = (await self.request("POST", f"/improvement-contexts/{experiment}/case-sets", status=201,
            json={"event_key": "e2e-case-set-create", "contract_id": saved["contract_id"], "seed": 11, "cases": cases}))["case_set"]
        bundle = (await self.request("POST", "/improvement-bundles", status=201,
            json={"event_key": "e2e-bundle-create", "revision_ids": [self.fixture.target["revision_id"]]}))["bundle"]
        public = {"event_key": "e2e-one-owner-start", "experiment_id": experiment, "contract_id": saved["contract_id"],
            "case_set_id": case_set["case_set_id"], "case_id": "qualification", "base_bundle_id": bundle["bundle_id"],
            "candidate_bundle_id": bundle["bundle_id"], "variant": "baseline", "repeat": 1,
            "timeout_seconds": 300, "expected_context_generation": context["generation"]}
        started = (await self.request("POST", "/improvement-trials", status=202, json=public))["trial"]
        identifier = started["trial_id"]
        trials = TrialStore(self.assets)
        deadline = (await asyncio.to_thread(trials.get, self.owner, identifier))["request"]["deadline_at"]
        for _ in range(1200):
            row = await asyncio.to_thread(trials.get, self.owner, identifier)
            if row["status"] in {"completed", "failed", "unknown", "not_run", "cancelled"}:
                break
            await asyncio.sleep(.05)
        self.assertEqual(row["status"], "completed", row)
        self.assertTrue(self.closed)
        self.assertEqual(self.execute_count, 1)
        with patch.object(UI, "improvement_events", side_effect=AssertionError("Cold GET cannot ingest usage")), \
             patch.object(UI, "refresh", side_effect=AssertionError("Cold GET cannot refresh"), create=True):
            view = (await self.request("GET", "/improvement-trials/" + identifier))["trial"]
            await self.request("GET", "/improvement-contexts/" + experiment)
        self.assertEqual(view["evaluation"]["criteria"], [{"id": "shape", "verdict": "pass"}, {"id": "business", "verdict": "unknown"}])
        self.assertIn(view["verdict"], {"unknown", "fail"})
        self.assertIn("unknown", {check["verdict"] for check in view["execution_checks"]})
        self.assertEqual((view["usage"]["tokens_in"], view["usage"]["tokens_out"]), (3, 2))
        self.assertEqual(view["usage"]["coverage"]["status"], "partial")
        self.assertIsNone(view["usage"]["requests"])
        self.assertFalse(view["usage"]["coverage"]["requests_complete"])
        self.assertEqual(view["selection"], {"provider": "anthropic-cli", "engine_id": "claude-sdk", "model": "sonnet", "reasoning": "high"})
        replay = (await self.request("POST", "/improvement-trials", status=202, json=public))["trial"]
        self.assertEqual(replay["trial_id"], identifier)
        self.assertEqual((await asyncio.to_thread(trials.get, self.owner, identifier))["request"]["deadline_at"], deadline)
        self.assertEqual(self.execute_count, 1)
        await self.request("POST", "/improvement-trials", status=409, json={**public, "timeout_seconds": 299})
        self.assertEqual(self.execute_count, 1)
        events = [json.loads(line) for line in US._EVENTS_PATH.read_text(encoding="utf-8").splitlines()]
        self.assertTrue(events)
        for event in events:
            self.assertEqual(event["execution"]["execution_id"], "improvement_trial:" + identifier)
            self.assertEqual(event["execution"]["attempt"], 1)
        self.assertTrue(any(event.get("event_kind") == "cli_detail" for event in events))
        call = CallLedger(self.assets.store).get(row["attempts"][0]["call_id"])
        self.assertIsNotNone(call["engine_at"])
        self.assertEqual(call["status"], "ok")
        with closing(self.assets.store._conn()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agent_calls").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM improvement_qualification").fetchone()[0], 1)
        decision = (await self.request("POST", f"/improvement-trials/{identifier}/attempts/1/owner-decisions", json={
            "event_key": "e2e-owner-decision", "criterion_id": "business", "verdict": "pass",
            "output_hash": view["artifact_hash"], "contract_hash": view["contract_hash"],
            "expected_generation": view["generation"]}))["trial"]
        reevaluated = (await self.request("POST", f"/improvement-trials/{identifier}/attempts/1/reevaluate", json={
            "event_key": "e2e-owner-reevaluate", "expected_generation": decision["generation"]}))["trial"]
        self.assertEqual(reevaluated["evaluation"]["business_verdict"], "pass")
        self.assertIn(reevaluated["verdict"], {"fail", "unknown"})
        self.assertEqual(self.execute_count, 1)
        await self.request("POST", f"/improvement-trials/{identifier}/cancel", status=409, json={
            "event_key": "e2e-terminal-cancel", "expected_generation": reevaluated["generation"]})
        await self.request("POST", "/improvement-trials/recover", json={"event_key": "e2e-owner-recovery"})
        foreign = self.f.root / "foreign-brain"; foreign.mkdir()
        await self.request("GET", "/improvement-trials/" + identifier, brain=foreign, status=403)
        await self.request("POST", "/improvement-contexts/" + experiment + "/revoke", json={
            "event_key": "e2e-context-revoke", "expected_generation": context["generation"]})
        await self.main._shutdown_improvement_trials()
        self.assertFalse(self.main._IMPROVEMENT_TRIAL_SERVICE.tasks._tasks)
        self.assertFalse(self.main._IMPROVEMENT_TRIAL_SERVICE._operations)
        self.assertEqual(self.execute_count, 1)
        self.assertGreaterEqual(self.verify_count, 2)
        with closing(self.assets.store._conn()) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agent_calls WHERE status IN ('reserved','running')").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM improvement_trial_attempts WHERE lease_token IS NOT NULL").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
