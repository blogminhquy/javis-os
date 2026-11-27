"""Real isolated dashboard inputs compose protected context without live builders."""
from _paths import ROOT, SERVER  # noqa: F401

import atexit
import contextlib
import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

# A user-home temp directory inherits real ancestor .claude/settings.json.
# Use a disposable drive-root fixture so no real owner instructions enter tests.
_SCRATCH_PARENT = Path(tempfile.gettempdir()).anchor if os.name == "nt" else tempfile.gettempdir()
_SCRATCH_LIFETIME = tempfile.TemporaryDirectory(prefix="trial-dashboard-", dir=_SCRATCH_PARENT)
SCRATCH = Path(_SCRATCH_LIFETIME.name)
for key, child in {"JAVIS_STATE_DIR": "boot-state", "BRAINS_DIR": "boot-brains", "BRAIN_PATH": "boot-brain",
                   "OBSIDIAN_VAULT_PATH": "boot-vault", "SOURCES_PATH": "boot-sources",
                   "JAVIS_SESSIONS_DB": "boot-sessions.db"}.items():
    os.environ[key] = str(SCRATCH / child)

import main as H
# main eagerly opens scratch databases. Release their native
# lifetimes before TemporaryDirectory's cleanup (Windows forbids deleting open
# DBs). A previously imported main may belong to another fixture; never close it.
for _store, _filename in ((H.tasks_feature.store, "kanban.sqlite3"),
                          (H.watch_feature.store, "web_watch.sqlite3"),
                          (H.login_vault.current().store, "login_vault.sqlite3")):
    if _store.path == SCRATCH / "boot-state" / _filename:
        atexit.register(_store.close)
_boot_sessions = H.sessions._store
if _boot_sessions is not None and _boot_sessions.db_path == SCRATCH / "boot-sessions.db":
    atexit.register(_boot_sessions.close)
import packs
import turn_context
from evidence_store import redact
from resonance_store import Principal
from improvement_trial_sql_context import SQLiteContextProjection, ExistingSQLiteSource
from improvement_trial_plugins import PluginCapabilityProjection

if importlib.util.find_spec("improvement_trial_dashboard"):
    import improvement_trial_dashboard as D
else:
    D = None


@contextlib.contextmanager
def _posix_change_time_stats():
    """Exercise no-birthtime filesystems without requiring a second OS.

    Actual scratch I/O supplies each file's identity, permissions and timestamps.
    POSIX ctime changes on edits; mtime gives that behavior deterministically on
    Windows too. Descriptor and path observations share the same projection.
    """
    original_stat, original_lstat, original_fstat = Path.stat, Path.lstat, os.fstat

    class ChangeTimeStat:
        def __init__(self, observed):
            self.observed = observed

        def __getattr__(self, key):
            if key in {"st_birthtime", "st_birthtime_ns"}:
                raise AttributeError(key)
            if key == "st_ctime_ns":
                return self.observed.st_mtime_ns
            if key == "st_ctime":
                return self.observed.st_mtime
            return getattr(self.observed, key)

    with patch.object(Path, "stat", lambda path, *a, **kw: ChangeTimeStat(original_stat(path, *a, **kw))), \
            patch.object(Path, "lstat", lambda path, *a, **kw: ChangeTimeStat(original_lstat(path, *a, **kw))), \
            patch.object(os, "fstat", lambda *a, **kw: ChangeTimeStat(original_fstat(*a, **kw))):
        yield


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(D, "Concrete dashboard context capture is missing")
        self.root = Path(tempfile.mkdtemp(dir=SCRATCH))
        self.brain, self.state, self.app, self.native = [self.root / name for name in ("brain", "state", "app", ".claude")]
        for path in (self.brain, self.state, self.app, self.native):
            path.mkdir()
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(Path, "home", return_value=self.root))
        self.stack.enter_context(patch.dict(os.environ, {"JAVIS_PORT": "7777",
            "JAVIS_ENABLE_USER_PLUGINS": "", "JAVIS_ENABLE_VAULT_PLUGINS": "", "JAVIS_DISABLE_PACKS": "", "JAVIS_FILES_ROOT": "brain"}))
        os.environ.pop("CLAUDE_CONFIG_DIR", None)
        for obj, name, value in ((H, "CLAUDE_MD_PATH", self.app / "CLAUDE.md"), (H.cfgmod, "STATE_DIR", self.state),
            (H.cfgmod, "SETTINGS_PATH", self.state / "settings.json"), (H.coding_store, "STORE_PATH", self.state / "coding.json"),
            (H.usage_store, "_PATH", self.state / "usage.json"), (H.plugins_host, "BUNDLED_DIR", self.app / "plugins"),
            (H.plugins_host, "GLOBAL_DIR", self.state / "plugins"), (H.plugins_host, "_STATE_PATH", self.state / "plugins.json"),
            (packs, "PACKS_DIR", self.state / "packs"), (packs, "LEDGER", self.state / "packs.json"),
            (H.plugins_host, "_cache", {}), (H.plugins_host, "_MANIFEST_CACHE", {}),
            (H.plugins_host, "_STATE_CACHE", {"sig": None, "data": None}),
            (packs, "_cache", {"sig": None, "packs": [], "connectors": {}}), (H, "_PIN_LIMITED", {}), (H, "_TG_BOT", None)):
            self.stack.enter_context(patch.object(obj, name, value))
        self.owner = Principal("owner", "owner-1", str(self.brain))
        self.store = H.sessions.SessionStore(self.state / "sessions.db")
        self.addCleanup(self.store.close)
        self.workflow = H.workflow_runs.WorkflowRunStore(self.state / "workflow.db") if hasattr(H, "workflow_runs") else None
        if self.workflow is None:
            import workflow_runs
            self.workflow = workflow_runs.WorkflowRunStore(self.state / "workflow.db")
        self.addCleanup(self.workflow._db.close)
        db = self.store._conn
        db.execute("INSERT INTO projects(id,brain,name,instructions,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                   ("project-1", str(self.brain), "Owner Project", "Always retain this project rule.", 1, 1))
        db.execute("INSERT INTO sessions(id,brain,engine,model,channel,project_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                   ("session-1", str(self.brain), "cli", "sonnet", "web", "project-1", 1, 1))
        db.commit()
        self.sql = SQLiteContextProjection(self.state / "sessions.db", self.state / "workflow.db",
            existing_sources={self.state / "sessions.db": ExistingSQLiteSource(self.state / "sessions.db", self.store._conn, self.store._lock),
                self.state / "workflow.db": ExistingSQLiteSource(self.state / "workflow.db", self.workflow._db, self.workflow._lock)},
            principal_type=Principal, redactor=redact)
        self.plugins = PluginCapabilityProjection(host=H.plugins_host, packs_host=packs, redactor=redact)
        self.settings = {"model": {"main": {"provider": "anthropic-cli", "model": "sonnet"}, "reasoning": "high",
            "fast": False, "claude_auth": "subscription"}, "locale": {"ui_lang": "vi", "reply_lang": "auto", "tz": "Asia/Ho_Chi_Minh"},
            "context_runtime": {"mode": "off", "preset_choice": {"level": "off", "source": "user", "at": ""}}}
        self.save_settings()
        self.write(self.app, "CLAUDE.md", "Kernel owner contract.\n")
        self.write(self.state, "user_profile.md", "Use a concise, warm tone.")
        self.write(self.brain, "memory/MEMORY.md", "- [Rule](facts/rule.md) - Brain rule.\n")
        self.write(self.brain, "skills/custom/SKILL.md", "---\nname: Custom\ndescription: Perform custom work\ngroup: General\n---\nPRIVATE MUTABLE TARGET BODY\n")
        self.surface = {"kind": "dashboard", "session_id": "session-1", "language": "vi"}
        self.targets = [self.target()]
        (self.brain / "agents").mkdir()
        (self.brain / "workflows").mkdir()
        self.stack.enter_context(patch.object(H.system_sync, "_SYNCED_ROOTS", {str(self.brain)}))
        self.stack.enter_context(patch.object(H.system_sync, "_MIRROR_SIG", {str(self.brain): H.system_sync._mirror_signature(self.brain / "skills")}))
        self.stack.enter_context(patch.object(H.system_sync, "_MIRROR_RETRY", {}))
        H.plugins_host._load_all(str(self.brain))
        self.frozen_now = datetime(2026, 10, 23, 3, 15, tzinfo=timezone.utc)

    def save_settings(self):
        (self.state / "settings.json").write_text(json.dumps(self.settings), encoding="utf-8")

    def write(self, root, relative, text):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
        return path

    def target(self):
        path = self.brain / "skills/custom/SKILL.md"
        info = path.stat()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return {"id": "target-1", "generation": 1, "kind": "skill", "canonical_ref": "skills/custom/SKILL.md",
            "identity": hashlib.sha256(f":{info.st_dev}:{info.st_ino}".encode()).hexdigest(), "source_hash": digest,
            "protected_hash": digest, "ownership": "user_protected"}

    def collector(self):
        return D.DashboardContextCapture(host=H, sql=self.sql, plugins=self.plugins,
            project_root=self.app, state_root=self.state, native_user_root=self.native)

    def capture(self, *, frozen=None):
        with patch.object(D, "_utc_now", return_value=self.frozen_now):
            # Keep identities intact: replacing an ordinary source caller is a
            # completeness failure. Profiling traps execution without changing
            # any function/code object that the collector must verify.
            banned = {id(function.__code__) for function in (H.build_system_prompt, H._brain_memory_dir,
                H.cfgmod.read_settings, H.system_sync.ensure_synced, H.system_sync.mirror_skills,
                H._project_block, H._session_block, H.get_store, H.plugins_host._load_all,
                H.usage_store.summary, H.coding_store._load, H.localefmt.ten_tz,
                H.localefmt.now, H.context_compiler.dong_ho) if hasattr(function, "__code__")}
            def forbid_execution(frame, event, arg):
                if event == "call" and id(frame.f_code) in banned:
                    raise AssertionError("ordinary prompt source caller executed")
            prior = sys.gettrace()
            sys.settrace(forbid_execution)
            try:
                collector = self.collector()
                if frozen is not None:
                    return collector.revalidate(self.owner, self.surface, self.targets, frozen_capture=frozen)
                return collector(self.owner, self.surface, self.targets)
            finally:
                sys.settrace(prior)

    def test_concrete_complete_context_renders_all_protected_blocks_and_no_target_body(self):
        value = self.capture()
        content = value["baseline_context"]["content"]
        self.assertEqual(value["version"], 2)
        self.assertEqual(value["baseline_context"]["coverage"], "complete")
        for text in ("Kernel owner contract.", "Use a concise, warm tone.", "Brain rule.",
                     "Always retain this project rule.", "KÊNH HỘI THOẠI HIỆN TẠI", "23/10/2026",
                     "- General: custom"):   # 2026-11-27: the router names skills; descriptions come per turn
            self.assertIn(text, content)
        self.assertNotIn("PRIVATE MUTABLE TARGET BODY", json.dumps(value))
        self.assertTrue(any(row["role"] == "protected" and row["kind"] == "sql" for row in value["sources"]))

    def test_full_raw_protected_text_survives_beyond_legacy_caps(self):
        profile = " \r\n" + "Profile owner rule. " * 300 + "PROFILE TAIL\r\n "
        memory = "\r\n" + "Brain owner rule. " * 1500 + "MEMORY TAIL\r\n "
        pinned = " \r\n" + "Pinned owner rule. " * 200 + "PINNED TAIL\r\n "
        self.write(self.state, "user_profile.md", profile)
        self.write(self.brain, "memory/MEMORY.md", memory)
        self.write(self.brain, "rules/pinned.md", pinned)
        self.store._conn.execute("INSERT INTO session_files(id,session_id,path,name,pinned,added_at) VALUES(?,?,?,?,?,?)",
                                 ("file-1", "session-1", "rules/pinned.md", "Pinned", 1, 1))
        self.store._conn.commit()
        content = self.capture()["baseline_context"]["content"]
        for raw in (profile, memory, pinned):
            self.assertIn(raw, content)

    def test_revalidate_freezes_only_clock_and_usage(self):
        self.write(self.state, "usage.json", '{"days":{"2026-10-23":{"anthropic-cli|sonnet":{"in":10,"out":3,"turns":1,"cost":0}}},"total":{}}')
        first = self.capture()
        self.frozen_now = datetime(2030, 1, 2, tzinfo=timezone.utc)
        self.write(self.state, "usage.json", '{"days":{},"total":{}}')
        self.assertEqual(first, self.capture(frozen=first))
        self.write(self.state, "user_profile.md", "A new current owner rule.")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.capture(frozen=first)

    def test_sql_permissions_membership_and_target_changes_reject_revalidation(self):
        first = self.capture()
        self.store._conn.execute("UPDATE sessions SET brain=? WHERE id='session-1'", (str(self.root),))
        self.store._conn.commit()
        with self.assertRaises(PermissionError):
            self.capture(frozen=first)
        self.store._conn.execute("UPDATE sessions SET brain=? WHERE id='session-1'", (str(self.brain),))
        self.store._conn.commit()
        self.write(self.brain, "skills/custom/SKILL.md", "---\nname: Custom\ndescription: Perform custom work\n---\nChanged body")
        H.system_sync._MIRROR_SIG[str(self.brain)] = H.system_sync._mirror_signature(self.brain / "skills")
        with self.assertRaisesRegex(ValueError, "target_changed"):
            self.capture(frozen=first)

    def test_unknown_adaptive_pinned_model_and_coding_states_fail_closed(self):
        self.settings["context_runtime"]["mode"] = "on"
        self.save_settings()
        with self.assertRaisesRegex(ValueError, "adaptive"):
            self.capture()
        self.settings["context_runtime"]["mode"] = "off"
        self.save_settings()
        self.write(self.state, "coding.json", '{"version":2,"thu_muc":[],"phien":{"session-1":{"thu_muc":"folder"}}}')
        with self.assertRaisesRegex(ValueError, "coding"):
            self.capture()

    def test_native_owner_sources_preserved_and_unapproved_ambient_rejected(self):
        text = " Full native owner instruction.\r\n "
        self.write(self.brain, ".claude/rules/owner.md", text)
        self.assertIn(text, self.capture()["baseline_context"]["content"])
        self.write(self.native, "CLAUDE.md", "Unapproved global owner instruction")
        with self.assertRaisesRegex(ValueError, "native_ambient"):
            self.capture()

    def test_native_auto_memory_and_instruction_imports_unsupported(self):
        (self.native / "projects").mkdir()
        with self.assertRaisesRegex(ValueError, "native_ambient"):
            self.capture()
        (self.native / "projects").rmdir()
        self.write(self.brain, "CLAUDE.md", "@../foreign-owner.md\n")
        with self.assertRaisesRegex(ValueError, "native_import"):
            self.capture()

    def test_no_writes_constructors_loaders_or_unknown_missing_source_fallback(self):
        before = sorted(str(path) for path in self.root.rglob("*"))
        self.capture()
        self.assertEqual(before, sorted(str(path) for path in self.root.rglob("*")))
        (self.brain / "memory/MEMORY.md").unlink()
        with self.assertRaisesRegex(ValueError, "insufficient_source"):
            self.capture()

    def test_unknown_serving_ceiling_and_unwarmed_sync_are_not_complete(self):
        os.environ["JAVIS_FILES_ROOT"] = "drive"
        with self.assertRaisesRegex(ValueError, "serving"):
            self.capture()
        os.environ["JAVIS_FILES_ROOT"] = "brain"
        H.system_sync._SYNCED_ROOTS.clear()
        with self.assertRaisesRegex(ValueError, "sync"):
            self.capture()

    def test_protected_permission_drift_is_a_source_change(self):
        first = self.capture()
        original = D._authority
        def altered(root, relative):
            value = original(root, relative)
            if root == self.brain and relative == "memory/MEMORY.md":
                value[0]["acl_hash"] = "b" * 64
            return value
        with patch.object(D, "_authority", altered):
            with self.assertRaisesRegex(ValueError, "changed"):
                self.capture(frozen=first)

    def test_actual_prewarmed_main_parity_below_caps_with_real_sql_and_frozen_volatiles(self):
        import workflow_runs
        from zoneinfo import ZoneInfo
        self.write(self.brain, "rules/pinned.md", "Pinned owner rule.")
        self.store._conn.execute("INSERT INTO session_files(id,session_id,path,name,pinned,added_at) VALUES(?,?,?,?,?,?)",
                                 ("file-1", "session-1", "rules/pinned.md", "Pinned", 1, 1))
        self.store._conn.commit()
        self.workflow.bat_dau(brain=str(self.brain), slug="latest", name="Latest Workflow", input="PRIVATE INPUT", source="dashboard")
        H.system_sync._SYNCED_ROOTS.discard(str(self.brain))
        # Explicit production prewarm writes only this disposable authorized brain.
        H.system_sync.ensure_synced(str(self.brain))
        H.system_sync.mirror_skills(str(self.brain))
        H.plugins_host._load_all(str(self.brain))
        decision = H.lang_mod.LangDecision("vi", "ui", 1.0, True, theo_nguoi_dung=True)
        local = self.frozen_now.astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
        with patch.object(H, "get_store", return_value=self.store), \
             patch.object(workflow_runs, "get_store", return_value=self.workflow), \
             patch.object(H.localefmt, "now", return_value=local), \
             patch.object(H.context_compiler, "_DONG_HO_NOW", lambda: local):
            expected = H.build_system_prompt(str(self.brain), lang=decision, project_id="project-1", session_id="session-1")
            expected += H.channel_context.build_channel_block("dashboard", {"session_id": "session-1"},
                telegram_running=False, port=7777, brain_root=str(self.brain))
        value = self.capture()
        self.assertEqual(value["baseline_context"]["content"], expected)
        self.assertNotIn("PRIVATE INPUT", json.dumps(value))

    def test_membership_beyond_legacy_caps_preserved_and_current_rule_drift_rejected(self):
        for index in range(18):
            self.store._conn.execute("INSERT INTO session_links(id,session_id,url,label,pinned,added_at) VALUES(?,?,?,?,?,?)",
                (f"link-{index}", "session-1", f"https://example.invalid/{index}", f"Reference {index}", 0, index))
        self.store._conn.commit()
        first = self.capture()
        for index in range(18):
            self.assertIn(f"https://example.invalid/{index}", first["baseline_context"]["content"])
        self.store._conn.execute("UPDATE projects SET instructions='Current rule changed' WHERE id='project-1'")
        self.store._conn.commit()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.capture(frozen=first)

    def test_nonsecret_settings_semantics_change_but_unrelated_secret_does_not(self):
        first = self.capture()
        self.settings["auth"] = {"password_hash": "private-auth-hash"}
        self.settings["model"]["openrouter_key"] = "PRIVATE_PROVIDER_KEY"
        self.save_settings()
        self.assertEqual(first, self.capture(frozen=first))
        self.assertNotIn("PRIVATE_PROVIDER_KEY", json.dumps(first))
        self.settings["locale"]["tz"] = "UTC"
        self.save_settings()
        with self.assertRaisesRegex(ValueError, "changed"):
            self.capture(frozen=first)

    def test_source_optional_addition_and_metadata_only_case_document_scope(self):
        self.write(self.brain, "docs/case-private.md", "HOST PRIVATE SELECTED CASE CONTENT")
        self.store._conn.execute("INSERT INTO session_files(id,session_id,path,name,pinned,added_at) VALUES(?,?,?,?,?,?)",
            ("case-file", "session-1", "docs/case-private.md", "Case document", 0, 1))
        self.store._conn.commit()
        first = self.capture()
        self.assertIn("docs/case-private.md", first["baseline_context"]["content"])
        self.assertNotIn("HOST PRIVATE SELECTED CASE CONTENT", json.dumps(first))
        self.write(self.brain, "CLAUDE.local.md", "New owner native instruction.")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.capture(frozen=first)

    def test_pinned_target_alias_cannot_duplicate_variant_body(self):
        self.store._conn.execute("INSERT INTO session_files(id,session_id,path,name,pinned,added_at) VALUES(?,?,?,?,?,?)",
            ("target-file", "session-1", "skills/custom/SKILL.md", "Candidate alias", 1, 1))
        self.store._conn.commit()
        with self.assertRaisesRegex(ValueError, "target_context_overlap"):
            self.capture()

    def test_usage_malformed_and_pin_override_do_not_use_legacy_fallbacks(self):
        self.store._conn.execute("UPDATE sessions SET pinned_provider='openai-oauth',pinned_model='gpt-5' WHERE id='session-1'")
        self.store._conn.commit()
        with self.assertRaisesRegex(ValueError, "pinned_model"):
            self.capture()
        self.store._conn.execute("UPDATE sessions SET pinned_provider=NULL,pinned_model=NULL WHERE id='session-1'")
        self.store._conn.commit()
        self.write(self.state, "usage.json", "not valid JSON")
        with self.assertRaisesRegex(ValueError, "insufficient_source"):
            self.capture()

    def test_coding_other_session_does_not_enter_projection_or_change_selected_surface(self):
        self.write(self.state, "coding.json", '{"version":2,"thu_muc":[],"phien":{}}')
        first = self.capture()
        self.write(self.state, "coding.json", '{"version":2,"thu_muc":[],"phien":{"foreign":{"thu_muc":"PRIVATE FOREIGN PATH"}}}')
        self.assertEqual(first, self.capture(frozen=first))
        self.assertNotIn("PRIVATE FOREIGN PATH", json.dumps(self.capture()))

    def test_posix_nonsemantic_settings_and_coding_edits_preserve_selected_context(self):
        with _posix_change_time_stats():
            self.write(self.state, "coding.json", '{"version":2,"thu_muc":[],"phien":{}}')
            first = self.capture()
            self.settings["api"] = {"provider_key": "SYNTHETIC_UNRELATED_VALUE"}
            self.save_settings()
            self.write(self.state, "coding.json", '{"version":2,"thu_muc":[],"phien":{"foreign":{"thu_muc":"unselected"}}}')
            self.assertEqual(first, self.capture(frozen=first))
            self.settings["locale"]["tz"] = "UTC"
            self.save_settings()
            with self.assertRaisesRegex(ValueError, "changed"):
                self.capture(frozen=first)

    def test_posix_sql_journal_directory_change_preserves_protected_file_authority(self):
        connection = sqlite3.connect(self.state / "bookkeeping.sqlite3")
        self.addCleanup(connection.close)
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("CREATE TABLE bookkeeping(value TEXT)")
        connection.commit()
        with _posix_change_time_stats():
            first = self.capture()
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("INSERT INTO bookkeeping VALUES('host transaction')")
            try:
                self.assertTrue((self.state / "bookkeeping.sqlite3-journal").is_file())
                self.assertEqual(first, self.capture(frozen=first))
            finally:
                connection.rollback()
            self.write(self.state, "user_profile.md", "Changed protected owner instruction")
            with self.assertRaisesRegex(ValueError, "changed"):
                self.capture(frozen=first)

    def test_posix_semantic_source_replacement_is_not_an_unrelated_edit(self):
        with _posix_change_time_stats():
            first = self.capture()
            replacement = self.state / "replacement.json"
            replacement.write_bytes((self.state / "settings.json").read_bytes())
            replacement.replace(self.state / "settings.json")
            with self.assertRaisesRegex(ValueError, "changed"):
                self.capture(frozen=first)

    def test_posix_semantic_source_native_acl_change_is_not_an_unrelated_edit(self):
        with _posix_change_time_stats():
            first = self.capture()
            original = D._acl_hash
            with patch.object(D, "_acl_hash", lambda path: "b" * 64 if path == self.state / "settings.json" else original(path)):
                with self.assertRaisesRegex(ValueError, "changed"):
                    self.capture(frozen=first)

    def test_posix_sibling_journal_during_authority_stat_preserves_protected_context(self):
        with _posix_change_time_stats():
            first = self.capture()
            original = D._authority
            mutations = []
            def journal_after_authority(root, relative):
                observed = original(root, relative)
                if root == self.state and relative == "user_profile.md":
                    journal = root / "unrelated-sqlite-journal"
                    journal.write_bytes(b"host bookkeeping")
                    journal.unlink()
                    mutations.append(True)
                return observed
            with patch.object(D, "_authority", journal_after_authority):
                self.assertEqual(first, self.capture(frozen=first))
            self.assertTrue(mutations)

    def test_posix_protected_authority_rejects_directory_replacement_during_stat(self):
        root = self.root / "owner-rules"
        self.write(root, "owner.md", "Keep this owner instruction")
        original = D._authority
        def replace_after_authority(selected_root, relative):
            observed = original(selected_root, relative)
            root.rename(self.root / "old-owner-rules")
            self.write(root, "owner.md", "Keep this owner instruction")
            return observed
        with _posix_change_time_stats(), patch.object(D, "_authority", replace_after_authority):
            with self.assertRaisesRegex(ValueError, "protected_authority_changed"):
                D._protected_authority(root, "owner.md")

    def test_replaced_pure_renderer_is_rejected_before_calling_it(self):
        called = []
        original = H.main_prompt_rendering.render_memory_block
        def custom(*args, **kwargs):
            called.append(True)
            return original(*args, **kwargs) + "Unobserved custom runtime block"
        with patch.object(H.main_prompt_rendering, "render_memory_block", custom):
            with self.assertRaisesRegex(ValueError, "runtime_renderer"):
                self.capture()
        self.assertEqual(called, [])

    def test_custom_live_route_settings_reader_cannot_assert_disabled_adaptive_mode(self):
        with patch.object(H._CONTEXT_RUNTIME, "_settings_reader", lambda: {"context_runtime": {"mode": "on"}}):
            with self.assertRaisesRegex(ValueError, "runtime_reader"):
                self.capture()

    def test_target_copied_as_pinned_protected_file_does_not_duplicate_common_body(self):
        path = self.brain / "skills/custom/SKILL.md"
        self.write(self.brain, "docs/copy.md", path.read_bytes().decode("utf-8"))
        self.store._conn.execute("INSERT INTO session_files(id,session_id,path,name,pinned,added_at) VALUES(?,?,?,?,?,?)",
            ("copy", "session-1", "docs/copy.md", "Copy", 1, 1))
        self.store._conn.commit()
        with self.assertRaisesRegex(ValueError, "target_context_overlap"):
            self.capture()

    def test_runtime_port_telegram_and_catalog_priority_drift_reject_revalidation(self):
        first = self.capture()
        with patch.dict(os.environ, {"JAVIS_PORT": "7788"}):
            with self.assertRaisesRegex(ValueError, "changed"):
                self.capture(frozen=first)
        with patch.object(H, "_TG_BOT", object()):
            with self.assertRaisesRegex(ValueError, "changed"):
                self.capture(frozen=first)
        self.write(self.brain, "Javis/skill-usage.json", '{"custom":{"pinned":true,"use_count":1,"last_used_at":2}}')
        with self.assertRaisesRegex(ValueError, "changed"):
            self.capture(frozen=first)

    def test_no_global_snapshot_read_or_constructor_during_capture(self):
        with patch.object(H.sessions, "SessionStore", side_effect=AssertionError("SessionStore constructed")):
            self.assertEqual(self.capture()["baseline_context"]["coverage"], "complete")

    def test_unsafe_surface_nonowner_unknown_language_and_target_kind_rejected(self):
        self.surface["hidden_context"] = True
        with self.assertRaisesRegex(ValueError, "surface"):
            self.capture()
        del self.surface["hidden_context"]
        self.owner = Principal("agent", "agent-1", str(self.brain))
        with self.assertRaises((PermissionError, ValueError)):
            self.capture()
        self.owner = Principal("owner", "owner-1", str(self.brain))
        self.targets[0]["kind"] = "agent"
        with self.assertRaisesRegex(ValueError, "targets"):
            self.capture()

    def test_new_pinned_authority_alias_and_source_membership_during_outer_capture_rejected(self):
        original = self.sql.capture
        calls = [0]
        def mutate(*args, **kwargs):
            value = original(*args, **kwargs)
            calls[0] += 1
            if calls[0] == 1:
                self.store._conn.execute("INSERT INTO session_links(id,session_id,url,label,pinned,added_at) VALUES(?,?,?,?,?,?)",
                    ("new-link", "session-1", "https://example.invalid/new", "New", 0, 1))
                self.store._conn.commit()
            return value
        with patch.object(self.sql, "capture", mutate):
            with self.assertRaisesRegex(ValueError, "changed"):
                self.capture()

    def test_protected_registered_agent_file_can_also_be_pinned(self):
        text = "---\nname: Editor\nrole: Review\n---\nA protected owner instruction.\n"
        self.write(self.brain, "agents/editor.md", text)
        self.store._conn.execute("INSERT INTO session_files(id,session_id,path,name,pinned,added_at) VALUES(?,?,?,?,?,?)",
            ("agent-doc", "session-1", "agents/editor.md", "Owner instruction", 1, 1))
        self.store._conn.commit()
        value = self.capture()
        self.assertIn(text, value["baseline_context"]["content"])
        records = [row for row in value["sources"] if row["kind"] == "file" and row["locator"]["relative"] == "agents/editor.md"]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["role"], "protected")

    def test_custom_native_config_home_cannot_claim_default_worker_account(self):
        with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.native)}):
            with self.assertRaisesRegex(ValueError, "native_ambient_root"):
                self.capture()

    def test_native_user_discovery_additions_cannot_leave_complete_capture_unchanged(self):
        first = self.capture()
        for directory in ("skills", "agents", "plugins", "commands", "output-styles"):
            with self.subTest(directory=directory):
                path = self.native / directory
                path.mkdir()
                sentinel = path / "private-native-source.md"
                sentinel.write_text("NATIVE PRIVATE SENTINEL", encoding="utf-8")
                try:
                    with self.assertRaisesRegex(ValueError, "native_ambient"):
                        self.capture(frozen=first)
                finally:
                    sentinel.unlink()
                    path.rmdir()

    def test_ancestor_and_unmodeled_brain_native_discovery_rejected_but_cataloged_mirrors_remain_supported(self):
        H.system_sync._MIRROR_SIG.clear()
        H.system_sync.mirror_skills(str(self.brain))
        self.assertEqual(self.capture()["baseline_context"]["coverage"], "complete")
        # A distinct ancestor source, not the same path as default user discovery.
        self.native = self.root / "other-home" / ".claude"
        self.native.mkdir(parents=True)
        self.stack.enter_context(patch.object(Path, "home", return_value=self.native.parent))
        ancestor = self.root / ".claude" / "skills"
        ancestor.mkdir()
        try:
            with self.assertRaisesRegex(ValueError, "native_ambient"):
                self.capture()
        finally:
            ancestor.rmdir()
        for directory in ("agents", "commands", "plugins", "output-styles"):
            path = self.brain / ".claude" / directory
            path.mkdir()
            try:
                with self.assertRaisesRegex(ValueError, "native_ambient"):
                    self.capture()
            finally:
                path.rmdir()

    def test_actual_loaded_ordinary_builder_drift_rejected_without_executing_it(self):
        with patch.object(D, "_utc_now", return_value=self.frozen_now):
            collector = self.collector()
            first = collector(self.owner, self.surface, self.targets)
            called = []
            def changed_builder(*args, **kwargs):
                called.append(True)
                return "EXTRA ACTIVE OWNER CONTRACT"
            with patch.object(H, "build_system_prompt", changed_builder):
                with self.assertRaisesRegex(ValueError, "runtime"):
                    collector.revalidate(self.owner, self.surface, self.targets, frozen_capture=first)
            self.assertEqual(called, [])

    def test_actual_loaded_selected_source_helper_drift_rejected_without_execution(self):
        first = self.capture()
        called = []
        def changed_helper(*args, **kwargs):
            called.append(True)
            return "EXTRA ACTIVE OWNER CONTRACT"
        for name in ("_project_block", "_session_block", "_gather_capabilities", "_skill_router_block", "_safe_serve_path"):
            with self.subTest(helper=name), patch.object(H, name, changed_helper):
                with self.assertRaisesRegex(ValueError, "runtime"):
                    self.capture(frozen=first)
        self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()
