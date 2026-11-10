"""Concrete service composition uses actual initialized scratch application sources."""
from _paths import ROOT, SERVER  # noqa: F401

import hashlib
import importlib.metadata
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import test_improvement_trial_dashboard as fixtures
from cryptography.fernet import Fernet
from improvement_assets import capture_source
from improvement_blobs import RevisionBlobs
from improvement_store import ImprovementStore
from resonance_store import GoalStore

if importlib.util.find_spec("improvement_trial_service"):
    import improvement_trial_service as service
else:
    service = None


class DashboardServiceTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(service, "Concrete dashboard service composition is missing")
        self.f = fixtures.DashboardTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.host = fixtures.H
        self.stack = self.f.stack
        self.stack.enter_context(patch.dict(os.environ, {"JAVIS_STATE_DIR": str(self.f.state)}))
        self.stack.enter_context(patch.object(self.host.sessions, "_store", self.f.store))
        self.stack.enter_context(patch.object(sys.modules["workflow_runs"], "_STORE", self.f.workflow))
        self.codec = Fernet(Fernet.generate_key())
        blobs = RevisionBlobs(self.f.state / "improvement",
            encrypt=lambda text: "enc:" + self.codec.encrypt(text.encode()).decode(),
            decrypt=lambda text: self.codec.decrypt(text.removeprefix("enc:").encode()).decode())
        self.assets = ImprovementStore(GoalStore(self.f.state / "resonance.sqlite3"), blobs)
        source, raw = capture_source(self.f.brain, "skill", "custom", pack_state_dir=self.f.state / "packs-state")
        self.target = self.assets.capture(self.f.owner, source, raw, event_key="service-capture-target")
        self.ref = "brain-file:reports/input.json"
        self.input = self.f.write(self.f.brain, "reports/input.json", '{"input":"private fixture"}\r\n')
        self.selections = [{"source_ref": self.ref, "timezone": "UTC", "data_period": "synthetic",
            "cutoff": "2026-10-23T00:00:00+00:00", "schema": "application/json"}]
        import claude_cli
        import claude_sdk_engine
        import improvement_claude
        self.binary = self.f.root / "inert-cli.exe"
        self.binary.write_bytes(b"Never execute this synthetic binary")
        self.stack.enter_context(patch.dict(os.environ, {"JAVIS_CLAUDE_CLI": str(self.binary)}))
        self.stack.enter_context(patch.object(improvement_claude, "VERIFIED_NATIVE_RUNTIMES", {
            # The SDK version of this environment, not a fixed number: requirements.txt carries a range since
            # 2026-11-10 (the SDK updates itself inside its series), and `create_pin` matches the installed version.
            (sys.platform, "synthetic", hashlib.sha256(self.binary.read_bytes()).hexdigest(),
             importlib.metadata.version("claude-agent-sdk"))}))
        self.stack.enter_context(patch("subprocess.run", side_effect=AssertionError("No native/auth/model call")))
        self.stack.enter_context(patch("subprocess.Popen", side_effect=AssertionError("No native/auth/model call")))

    def factory(self, **kwargs):
        return service.dashboard_host(self.host, self.assets, **kwargs)

    def create(self, host=None):
        host = host or self.factory(source_selections=self.selections)
        return host.create(self.f.owner, "service-experiment", self.f.surface, [self.target["target_id"]],
                           source_refs=[self.ref], event_key="service-context-create")

    def test_actual_sources_build_complete_bound_context_without_native_query(self):
        host = self.factory(source_selections=self.selections)
        meta = self.create(host)
        self.assertEqual(meta["engine_config"]["model"], "sonnet")
        self.assertEqual(meta["engine_config"]["reasoning"], "high")
        self.assertEqual(meta["grant_status"], "active")
        self.assertNotIn("private fixture", str(meta))
        self.assertNotIn("PRIVATE MUTABLE TARGET BODY", str(meta))
        with self.assets.store._conn() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM agent_calls").fetchone()[0], 0)

    def test_construction_is_metadata_only_and_does_not_probe_or_capture(self):
        with patch.object(fixtures.D.DashboardContextCapture, "__call__", side_effect=AssertionError("No capture")), \
                patch.object(self.host.sessions, "get_store", side_effect=AssertionError("No store construction")):
            host = self.factory()
        self.assertIs(host.assets, self.assets)
        with self.assets.store._conn() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM improvement_trial_contexts").fetchone()[0], 0)

    def test_cold_source_lifetimes_are_unavailable_without_warming(self):
        for module, name in ((self.host.sessions, "_store"), (sys.modules["workflow_runs"], "_STORE")):
            with patch.object(module, name, None), self.assertRaises((ValueError, PermissionError)):
                self.factory()

    def test_source_selection_is_closed_and_host_fixes_freshness(self):
        for rows in ([{**self.selections[0], "permission_version": 1}],
                     [{**self.selections[0], "freshness_policy": "snapshot_version"}],
                     self.selections * 2, [{}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.factory(source_selections=rows)

    def test_current_selected_binary_and_target_drift_are_observed(self):
        host = self.factory(source_selections=self.selections)
        self.binary.write_bytes(b"unverified replacement")
        with self.assertRaises(ValueError):
            self.create(host)

    def test_foreign_module_or_store_path_cannot_be_production_dependencies(self):
        with self.assertRaises((TypeError, ValueError)):
            service.dashboard_host(object(), self.assets)
        wrong = ImprovementStore(GoalStore(self.f.state / "other.sqlite3"), self.assets.blobs)
        with self.assertRaises((TypeError, ValueError)):
            service.dashboard_host(self.host, wrong)

    def test_missing_skill_cannot_be_replaced_by_stale_database_metadata(self):
        host = self.factory(source_selections=self.selections)
        (self.f.brain / "skills/custom/SKILL.md").unlink()
        with self.assertRaises((ValueError, PermissionError)):
            self.create(host)

    def test_production_module_and_goal_store_instances_are_concrete(self):
        fake_sessions = types.SimpleNamespace(_store=self.f.store, SessionStore=self.host.sessions.SessionStore)
        with patch.object(self.host, "sessions", fake_sessions), self.assertRaises((TypeError, ValueError)):
            self.factory()
        fake_store = types.SimpleNamespace(path=self.f.state / "resonance.sqlite3")
        with self.assertRaises((TypeError, ValueError)):
            service.dashboard_host(self.host, ImprovementStore(fake_store, self.assets.blobs))

    def test_replaced_ordinary_session_source_cannot_validate_retained_owner_authority(self):
        host = self.factory()
        capture = host.context_capture(self.f.owner, self.f.surface, self.f.targets)
        replacement = self.host.sessions.SessionStore(self.f.state / "replacement-sessions.db")
        self.addCleanup(replacement.close)
        self.f.store._conn.backup(replacement._conn)
        replacement._conn.execute("UPDATE sessions SET brain='foreign-brain' WHERE id='session-1'")
        replacement._conn.commit()
        with patch.object(self.host.sessions, "_store", replacement):
            self.assertIs(self.host.get_store(), replacement)
            with self.assertRaisesRegex(ValueError, "trial_service_source_lifetime_changed"):
                host.context_capture.revalidate(self.f.owner, self.f.surface, self.f.targets,
                                                frozen_capture=capture)

    def test_changed_native_source_members_or_modules_fail_before_capture(self):
        host = self.factory()
        workflow = sys.modules["workflow_runs"]
        mutations = [(self.f.store, "_conn", self.f.workflow._db),
                     (self.f.store, "_lock", self.f.workflow._lock),
                     (self.f.store, "db_path", self.f.state / "other.db"),
                     (self.f.workflow, "_db", self.f.store._conn),
                     (self.f.workflow, "_lock", self.f.store._lock),
                     (self.f.workflow, "path", self.f.state / "other.db"),
                     (workflow, "_STORE", object()),
                     (self.host, "sessions", types.SimpleNamespace(_store=self.f.store))]
        for obj, name, replacement in mutations:
            with self.subTest(member=name), patch.object(obj, name, replacement):
                with self.assertRaisesRegex(ValueError, "trial_service_source_lifetime_changed"):
                    host.context_capture(self.f.owner, self.f.surface, self.f.targets)

    def test_source_replacement_during_observation_rejects_result(self):
        host = self.factory()
        ordinary = fixtures.D.DashboardContextCapture.__call__
        def replace_after_capture(collector, *args):
            value = ordinary(collector, *args)
            self.host.sessions._store = None
            return value
        with patch.object(fixtures.D.DashboardContextCapture, "__call__", replace_after_capture):
            with self.assertRaisesRegex(ValueError, "trial_service_source_lifetime_changed"):
                host.context_capture(self.f.owner, self.f.surface, self.f.targets)


if __name__ == "__main__":
    unittest.main()
