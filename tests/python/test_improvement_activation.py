"""M2E manual activation: one owner-chosen assistant scope, pointer-only revert, drift suspends."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import shutil
import sqlite3
import unittest
import unittest.mock
from contextlib import closing
from pathlib import Path

import improvement_activation as IA
import improvement_store as IM
import skill_router as SR
import test_improvement_comparison_plans as fixtures
import turn_context

AGENTS = {"ke-toan": "agent-ke-toan-1", "ban-hang": "agent-ban-hang-1"}


def summary(verdict, *, numeric_gate=False, complete=True):
    return {"mechanical_verdict": verdict, "complete": complete, "pilot": {"numeric_gate": numeric_gate}}


class ApplyEvidenceTests(unittest.TestCase):
    def test_no_report_is_a_manual_trial(self):
        self.assertEqual(IA.apply_evidence([])[0], "manual_trial")

    def test_rejected_report_blocks_apply(self):
        with self.assertRaisesRegex(PermissionError, "rejected"):
            IA.apply_evidence([{"report_id": "r1", "kind": "tuning", "summary": summary("rejected")}])

    def test_tuning_eligible_is_not_qualified(self):
        level, evidence = IA.apply_evidence([{"report_id": "r1", "kind": "tuning", "summary": summary("eligible")}])
        self.assertEqual(level, "manual_trial")
        self.assertEqual(evidence["business_eligibility"], "unverified")

    def test_final_numeric_gate_is_qualified_but_business_unverified(self):
        rows = [{"report_id": "r1", "kind": "tuning", "summary": summary("eligible")},
                {"report_id": "r2", "kind": "final", "summary": summary("eligible", numeric_gate=True)}]
        level, evidence = IA.apply_evidence(rows)
        self.assertEqual(level, "qualified")
        self.assertEqual(evidence["business_eligibility"], "unverified")
        self.assertEqual([ref["report_id"] for ref in evidence["reports"]], ["r1", "r2"])

    def test_final_without_numeric_gate_stays_manual(self):
        rows = [{"report_id": "r2", "kind": "final", "summary": summary("inconclusive")}]
        self.assertEqual(IA.apply_evidence(rows)[0], "manual_trial")


class ActivationBase(unittest.TestCase):
    def setUp(self):
        self.c = fixtures.ComparisonPlanTests()
        self.c.setUp()
        self.addCleanup(self.c.doCleanups)
        self.owner, self.assets, self.store = self.c.owner, self.c.assets, self.c.store
        self.root, self.skill = Path(self.owner.brain_id), Path(self.c.f.skill)
        self.candidate = self.c.h.candidate
        self.exact = self.c.authoring.authorize_diff(
            self.owner, self.candidate["candidate_id"], expected_generation=1,
            before_hash=self.candidate["base_hash"], after_hash=self.candidate["content_hash"],
            event_key="activation-exact-diff")
        self.activations = IA.Activations(self.assets, agent_key=lambda brain, slug: AGENTS.get(slug, ""))
        IA.configure(self.store.path, self.assets.blobs)
        self.addCleanup(IA.configure, None, None)
        self.canonical = self.skill.read_bytes()
        self.slug = self.skill.parent.name

    def apply(self, agent="ke-toan", key="apply-ke-toan", candidate=None):
        return self.activations.apply(self.owner, candidate or self.candidate["candidate_id"], agent, event_key=key)

    def seen(self, agent=None):
        token = turn_context.bind(turn_context.make("dashboard", la_chu=True,
            agent={"key": AGENTS[agent], "slug": agent} if agent else None))
        try:
            asset = IA.effective_skill_asset(self.root, self.slug)
        finally:
            turn_context.reset(token)
        return None if asset is None else asset.content

    def overlay(self):
        return self.assets.blobs.read(self.owner.brain_id, self.candidate["content_hash"])


class ActivationTests(ActivationBase):
    def test_apply_serves_overlay_only_in_the_chosen_assistant_chat(self):
        applied = self.apply()
        self.assertEqual((applied["state"], applied["generation"], applied["evidence_level"]), ("active", 1, "manual_trial"))
        self.assertEqual(applied["selector"], {"context": "dm", "agent_key": AGENTS["ke-toan"], "agent_slug": "ke-toan"})
        self.assertEqual(self.seen("ke-toan"), self.overlay())
        self.assertEqual(self.seen("ban-hang"), self.canonical)
        self.assertEqual(self.seen(None), self.canonical)
        # The canonical file is never written.
        self.assertEqual(self.skill.read_bytes(), self.canonical)
        self.assertEqual(SR.read_skill_asset(self.root, self.slug).content, self.canonical)

    def test_cli_transport_never_sees_the_overlay(self):
        self.apply()
        token = turn_context.bind(turn_context.make("dashboard", agent={"key": AGENTS["ke-toan"], "slug": "ke-toan"}))
        try:
            with IA.cli_transport():
                self.assertEqual(IA.effective_skill_asset(self.root, self.slug).content, self.canonical)
        finally:
            turn_context.reset(token)

    def test_apply_is_idempotent_and_one_pointer_per_scope(self):
        first = self.apply()
        self.assertEqual(self.apply(), first)
        with self.assertRaises(IM.ConflictError):
            self.apply(agent="ban-hang")  # same event key, different payload
        with self.assertRaisesRegex(IM.ConflictError, "scope_busy"):
            self.apply(key="apply-ke-toan-again")
        second = self.apply(agent="ban-hang", key="apply-ban-hang")
        self.assertNotEqual(second["scope_hash"], first["scope_hash"])

    def test_revert_moves_pointer_back_and_is_idempotent(self):
        applied = self.apply()
        with self.assertRaisesRegex(IM.ConflictError, "stale"):
            self.activations.revert(self.owner, applied["activation_id"], expected_generation=2, event_key="revert-stale")
        reverted = self.activations.revert(self.owner, applied["activation_id"], expected_generation=1, event_key="revert-1")
        self.assertEqual((reverted["state"], reverted["generation"]), ("reverted", 2))
        self.assertEqual(self.activations.revert(self.owner, applied["activation_id"], expected_generation=1,
                                                 event_key="revert-1"), reverted)
        with self.assertRaisesRegex(IM.ConflictError, "stale|not_active"):
            self.activations.revert(self.owner, applied["activation_id"], expected_generation=2, event_key="revert-2")
        self.assertEqual(self.seen("ke-toan"), self.canonical)
        # A reverted scope can be applied again as a new pointer.
        self.assertEqual(self.apply(key="apply-again")["state"], "active")

    def test_owner_edit_suspends_and_never_merges(self):
        applied = self.apply()
        edited = self.canonical + b"\nOwner added this line.\n"
        self.skill.write_bytes(edited)
        self.assertEqual(self.seen("ke-toan"), edited)
        self.assertEqual(self.activations.reconcile(self.owner),
                         [{"activation_id": applied["activation_id"], "reason": "canonical_changed"}])
        row = self.activations.list(self.owner)[0]
        self.assertEqual((row["state"], row["generation"]), ("suspended", 2))
        self.assertEqual(self.skill.read_bytes(), edited)
        with self.assertRaisesRegex(IM.ConflictError, "base_changed"):
            self.apply(key="apply-after-edit")

    def test_disabled_skill_is_not_revived(self):
        applied = self.apply()
        disabled = self.root / "skills" / ".disabled" / self.slug
        disabled.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(self.skill.parent), str(disabled))
        self.assertIsNone(self.seen("ke-toan"))
        self.assertEqual(self.activations.reconcile(self.owner),
                         [{"activation_id": applied["activation_id"], "reason": "source_unavailable"}])

    def test_revoked_authority_stops_serving_and_suspends(self):
        applied = self.apply()
        self.c.authoring.records.revoke_authority(self.owner, self.exact["authority_id"], expected_generation=1,
                                                  event_key="revoke-exact-diff")
        self.assertEqual(self.seen("ke-toan"), self.canonical)
        self.assertEqual(self.activations.reconcile(self.owner)[0]["reason"], "authority_revoked")
        with self.assertRaisesRegex(PermissionError, "authority"):
            self.apply(key="apply-revoked")
        self.assertEqual(self.activations.list(self.owner)[0]["activation_id"], applied["activation_id"])

    def test_policy_off_refuses_new_apply_but_keeps_owner_accepted_pointer(self):
        self.apply()
        policy = self.assets.get_policy(self.owner)
        self.assets.set_policy(self.owner, "off", expected_version=policy["version"], event_key="policy-off")
        self.assertEqual(self.seen("ke-toan"), self.overlay())
        with self.assertRaisesRegex(PermissionError, "disabled"):
            self.apply(agent="ban-hang", key="apply-while-off")

    def test_region_authority_alone_cannot_apply(self):
        self.c.authoring.records.revoke_authority(self.owner, self.exact["authority_id"], expected_generation=1,
                                                  event_key="revoke-before-apply")
        with self.assertRaisesRegex(PermissionError, "authority"):
            self.apply()

    def test_unknown_agent_is_refused(self):
        with self.assertRaisesRegex(ValueError, "agent"):
            self.apply(agent="khong-co")

    def test_agent_resolved_only_for_valid_slug_after_cheap_checks(self):
        calls = []
        self.activations.agent_key = lambda brain, slug: calls.append(slug) or AGENTS.get(slug, "")
        for bad in ("../whatever", "a/b", "", "x" * 200):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "agent"):
                self.apply(agent=bad, key="apply-bad-" + str(len(bad)))
        with self.assertRaises(PermissionError):
            self.activations.apply(self.owner, "missing-candidate", "ke-toan", event_key="apply-missing-candidate")
        self.assertEqual(calls, [])

    def test_transient_read_failure_suspends_nothing(self):
        applied = self.apply()
        with unittest.mock.patch.object(SR, "read_skill_asset", return_value=None):
            self.assertEqual(self.activations.reconcile(self.owner), [])
        self.assertEqual(self.activations.list(self.owner)[0]["state"], "active")
        self.assertEqual(self.seen("ke-toan"), self.overlay())
        self.assertEqual(applied["state"], "active")

    def test_disable_then_enable_never_revives_the_overlay(self):
        applied = self.apply()
        disabled = self.root / "skills" / ".disabled" / self.slug
        disabled.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(self.skill.parent), str(disabled))
        # The toggle route calls suspend_source right after the move.
        self.assertEqual(self.activations.suspend_source(self.owner, self.slug),
                         [{"activation_id": applied["activation_id"], "reason": "source_unavailable"}])
        shutil.move(str(disabled), str(self.skill.parent))
        self.assertEqual(self.seen("ke-toan"), self.canonical)

    def test_recreated_file_with_identical_bytes_is_a_new_target(self):
        applied = self.apply()
        before = self.skill.stat()
        self.skill.unlink()
        self.skill.write_bytes(self.canonical)
        after = self.skill.stat()
        if (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino):
            # ext4 and others reuse a freed inode at once: identical bytes in the same inode are
            # indistinguishable from the original, and serving the overlay on that base is harmless.
            self.skipTest("filesystem reused the inode")
        self.assertEqual(self.seen("ke-toan"), self.canonical)
        self.assertEqual(self.activations.reconcile(self.owner),
                         [{"activation_id": applied["activation_id"], "reason": "canonical_changed"}])

    def test_other_brain_cannot_read_or_revert(self):
        applied = self.apply()
        other = self.c.f.other
        self.assertEqual(self.activations.list(other), [])
        with self.assertRaises(PermissionError):
            self.activations.revert(other, applied["activation_id"], expected_generation=1, event_key="revert-foreign")

    def test_rows_cannot_be_rewritten_or_deleted(self):
        applied = self.apply()
        with closing(sqlite3.connect(self.store.path)) as connection:
            for statement in ("UPDATE improvement_activations SET content_hash=base_hash WHERE id=?",
                              "UPDATE improvement_activations SET state='active',generation=generation WHERE id=?",
                              "DELETE FROM improvement_activations WHERE id=?"):
                with self.subTest(statement=statement), self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(statement, (applied["activation_id"],))
        self.activations.revert(self.owner, applied["activation_id"], expected_generation=1, event_key="revert-final")
        with closing(sqlite3.connect(self.store.path)) as connection, self.assertRaises(sqlite3.IntegrityError):
            connection.execute("UPDATE improvement_activations SET state='active',generation=3 WHERE id=?",
                               (applied["activation_id"],))

    def test_schema_eleven_is_installed_and_asserted(self):
        self.apply()
        self.assertEqual(IM._schema_version(self.store), IM.SCHEMA_VERSION)
        self.assertGreaterEqual(IM.SCHEMA_VERSION, 11)
        IM.ensure(self.store)  # idempotent re-open asserts the exact definitions

    def ten(self):
        """A released-10 store: version 11 minus the add-only activation objects."""
        import improvement_activation_schema as S
        import improvement_canary_schema as C
        import improvement_routing_schema as RS
        IM.ensure(self.store)
        with self.store._Tx(self.store) as connection:
            for name in ("improvement_imports", "improvement_refinements", "improvement_transfers", "improvement_team_trials", "improvement_team_pins", "improvement_bundle_members", "improvement_bundle_activations", "improvement_agent_overlays", "improvement_agent_procedures", "improvement_routing_overlays", "improvement_routing_candidates"):
                connection.execute(f"DROP TABLE IF EXISTS {name}")  # their triggers and index go with them
            assert not any(connection.execute("SELECT 1 FROM sqlite_master WHERE name=?", (n,)).fetchone() for n in RS._NAMES)
            for name in reversed(C._NAMES):
                kind = "TABLE" if name in ("improvement_canaries", "improvement_canary_exposures", "improvement_canary_verdicts",
                    "improvement_auto_scopes") else "INDEX" if name.endswith("_live") else "TRIGGER"
                if kind != "TRIGGER" or connection.execute("SELECT 1 FROM sqlite_master WHERE name=?", (name,)).fetchone():
                    connection.execute(f"DROP {kind} IF EXISTS {name}")
            for name in reversed(S._NAMES):
                kind = "TABLE" if name == "improvement_activations" else "INDEX" if "_live" in name or "_lookup" in name else "TRIGGER"
                connection.execute(f"DROP {kind} {name}")
            connection.execute("UPDATE improvement_schema SET version=10 WHERE id=1")

    def history(self):
        with closing(self.store._conn()) as connection:
            names = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' "
                     "AND name LIKE 'improvement_%' AND name NOT IN ('improvement_schema','improvement_activations')")]
            return {name: connection.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall() for name in names}

    def backups(self):
        return sorted(str(path) for path in self.store.path.parent.glob(self.store.path.name + ".pre-improvement-m2-activations.bak"))

    def test_ten_to_eleven_adds_tables_keeps_history_and_backs_up_once(self):
        self.ten()
        before = [tuple(row) for rows in self.history().values() for row in rows]
        IM.ensure(self.store)
        self.assertEqual(IM._schema_version(self.store), IM.SCHEMA_VERSION)
        self.assertEqual([tuple(row) for rows in self.history().values() for row in rows], before)
        backups = self.backups()
        self.assertEqual(len(backups), 1)
        with closing(sqlite3.connect(backups[0])) as connection:
            self.assertEqual(connection.execute("SELECT version FROM improvement_schema").fetchone()[0], 10)
            self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name='improvement_activations'").fetchone())
        IM.ensure(self.store)
        self.assertEqual(self.backups(), backups)
        self.assertEqual(self.apply()["state"], "active")

    def test_interrupted_ten_to_eleven_rolls_back_and_retry_succeeds(self):
        import improvement_activation_schema as S
        self.ten()
        original = S.assert_installed
        with unittest.mock.patch.object(S, "assert_installed", side_effect=IM.SchemaError("interrupted")), \
                self.assertRaises(IM.SchemaError):
            IM.ensure(self.store)
        self.assertEqual(IM._schema_version(self.store), 10)
        with closing(self.store._conn()) as connection:
            self.assertIsNone(connection.execute("SELECT 1 FROM sqlite_master WHERE name='improvement_activations'").fetchone())
        self.assertIs(S.assert_installed, original)
        IM.ensure(self.store)
        self.assertEqual(IM._schema_version(self.store), IM.SCHEMA_VERSION)

    def test_partial_activation_objects_on_ten_refuse_before_backup(self):
        self.ten()
        with self.store._Tx(self.store) as connection:
            connection.execute("CREATE TABLE improvement_activations(private TEXT)")
        with self.assertRaises(IM.SchemaError):
            IM.ensure(self.store)
        self.assertEqual(IM._schema_version(self.store), 10)
        self.assertEqual(self.backups(), [])


class ActivationConsumerTests(ActivationBase):
    """The real lazy router and hub skill tool read through the same resolver."""

    def under(self, agent, call):
        token = turn_context.bind(turn_context.make("dashboard", la_chu=True,
                                                    agent={"key": AGENTS[agent], "slug": agent}))
        try:
            return call()
        finally:
            turn_context.reset(token)

    def hub(self):
        import mcp_hub
        _, routes = mcp_hub._builtin_tools("full", str(self.root))
        handler = routes["javis_use_skill"]["call"]
        return lambda: asyncio.run(handler({"name": self.slug}))

    def test_hub_tool_serves_overlay_in_chosen_chat_and_canonical_over_cli(self):
        import mcp_hub  # noqa: F401
        self.apply()
        overlay = self.overlay().decode().replace("\r\n", "\n")
        canonical = self.canonical.decode().replace("\r\n", "\n")
        with unittest.mock.patch("skill_usage.bump"):
            self.assertEqual(self.under("ke-toan", self.hub()), overlay)
            self.assertEqual(self.under("ban-hang", self.hub()), canonical)

            def over_cli():
                with IA.cli_transport():
                    return self.hub()()
            self.assertEqual(self.under("ke-toan", over_cli), canonical)

    def test_lazy_router_stays_canonical(self):
        """Phase 8 runs for CLI engines too and never for assistant chats, so it is not a covered path."""
        import hashlib
        from capability_registry import CapabilityRegistry
        from lazy_skill_runtime import LazySkillSource
        self.apply()
        registry = CapabilityRegistry(Path(self.c.f.root) / "registry")
        selected = self.under("ke-toan", lambda: LazySkillSource(registry).resolve(self.root, self.slug))
        self.assertEqual(selected.action, "load", selected.reason)
        self.assertTrue(selected.context_item.source_ref.endswith(hashlib.sha256(self.canonical).hexdigest()))

    def test_http_hub_handler_marks_cli_transport(self):
        import mcp_hub
        seen = []

        async def capture(*args, **kwargs):
            seen.append(IA._CLI_TRANSPORT.get())
            return "ok"

        class Request:
            headers = {"authorization": "Bearer hub-test-token"}

        with unittest.mock.patch.object(mcp_hub, "hub_token", return_value="hub-test-token"), \
                unittest.mock.patch.object(mcp_hub, "tra_loi_jsonrpc", side_effect=capture):
            self.assertEqual(asyncio.run(mcp_hub.handle_http(Request())), "ok")
        self.assertEqual(seen, [True])
        self.assertFalse(IA._CLI_TRANSPORT.get())

    def test_nested_team_or_kanban_work_never_inherits_the_chat_overlay(self):
        self.apply()
        agent = {"key": AGENTS["ke-toan"], "slug": "ke-toan"}
        for turn in (turn_context.make("team", agent=agent), turn_context.make("dashboard", agent=agent, job="kanban:1"),
                     turn_context.make("dashboard", agent=agent, team_gate="gate-1")):
            token = turn_context.bind(turn)
            try:
                self.assertEqual(IA.effective_skill_asset(self.root, self.slug).content, self.canonical)
            finally:
                turn_context.reset(token)


class ActivationApiTests(ActivationBase):
    """Owner HTTP routes over the same actual service; stale and foreign requests get typed errors."""

    def setUp(self):
        super().setUp()
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import improvement_activation_api as API
        app = FastAPI()
        brains = {"brain": self.owner.brain_id, "other": self.c.f.other.brain_id}

        def resolve(value):
            if value not in brains:
                raise ValueError("unknown_brain")
            return brains[value]
        API.register(app, API.ActivationApiDeps(activations=lambda: self.activations, resolve_brain=resolve))
        self.client = TestClient(app)

    def test_http_apply_list_revert_round_trip(self):
        response = self.client.post("/improvement-activations", json={
            "candidate_id": self.candidate["candidate_id"], "agent_slug": "ke-toan", "event_key": "http-apply-0001"})
        self.assertEqual(response.status_code, 200, response.text)
        activation = response.json()["activation"]
        listed = self.client.get("/improvement-activations").json()
        self.assertEqual([row["activation_id"] for row in listed["activations"]], [activation["activation_id"]])
        self.assertIn("claude_code", listed["coverage"]["not_served"])
        stale = self.client.post(f"/improvement-activations/{activation['activation_id']}/revert",
                                 json={"expected_generation": 5, "event_key": "http-revert-stale"})
        self.assertEqual(stale.status_code, 409)
        reverted = self.client.post(f"/improvement-activations/{activation['activation_id']}/revert",
                                    json={"expected_generation": 1, "event_key": "http-revert-0001"})
        self.assertEqual(reverted.json()["activation"]["state"], "reverted")
        self.assertEqual(self.seen("ke-toan"), self.canonical)

    def test_http_rejects_extra_fields_foreign_brain_and_unknown_agent(self):
        extra = self.client.post("/improvement-activations", json={
            "candidate_id": self.candidate["candidate_id"], "agent_slug": "ke-toan", "event_key": "http-apply-extra",
            "content_hash": "0" * 64})
        self.assertEqual(extra.status_code, 422)
        unknown = self.client.post("/improvement-activations", json={
            "candidate_id": self.candidate["candidate_id"], "agent_slug": "khong-co", "event_key": "http-apply-unknown"})
        self.assertEqual(unknown.status_code, 422)
        foreign = self.client.post("/improvement-activations?brain=other", json={
            "candidate_id": self.candidate["candidate_id"], "agent_slug": "ke-toan", "event_key": "http-apply-foreign"})
        self.assertIn(foreign.status_code, (403, 404))

    def test_http_writes_require_a_browser_session(self):
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse
        from fastapi.testclient import TestClient
        import improvement_activation_api as API
        app = FastAPI()
        API.register(app, API.ActivationApiDeps(activations=lambda: self.activations,
            resolve_brain=lambda value: self.owner.brain_id,
            owner_session=lambda request: JSONResponse({"ok": False}, status_code=403)))
        client = TestClient(app)
        denied = client.post("/improvement-activations", json={
            "candidate_id": self.candidate["candidate_id"], "agent_slug": "ke-toan", "event_key": "http-apply-token"})
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(self.activations.list(self.owner), [])
        self.assertEqual(client.get("/improvement-activations").status_code, 200)

    def test_http_list_records_drift_suspension(self):
        self.apply()
        self.skill.write_bytes(self.canonical + b"\nOwner edit.\n")
        rows = self.client.get("/improvement-activations").json()["activations"]
        self.assertEqual((rows[0]["state"], rows[0]["reason"]), ("suspended", "canonical_changed"))


if __name__ == "__main__":
    unittest.main()
