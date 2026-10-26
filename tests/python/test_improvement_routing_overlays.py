"""M4 routing overlays: evaluate a description, apply it to the brain's main chat, revert, suspend on drift."""
from _paths import ROOT, SERVER  # noqa: F401

import shutil
import unittest

import improvement_routing as R
import improvement_store as IM
import test_improvement_activation as base

CASES = [{"query": q, "expected": "report", "kind": "positive"} for q in (
    "doi soat ma hang giua hai bang", "doi soat so tien thanh toan", "doi soat don hang ton kho",
    "doi soat cong no khach hang", "doi soat hoa don nha cung cap")]
CASES += [{"query": "thoi tiet hom nay", "expected": "", "kind": "negative"},
          {"query": "soan thu cam on khach hang", "expected": "viet-email", "kind": "competing"}]
DESCRIPTION = "Doi soat ma hang, so tien, don hang, cong no, hoa don"


class RoutingOverlayTests(base.ActivationBase):
    def setUp(self):
        super().setUp()
        other = self.root / "skills" / "viet-email" / "SKILL.md"
        other.parent.mkdir(parents=True, exist_ok=True)
        other.write_bytes(b"---\nname: viet-email\ndescription: Soan thu gui khach hang\n---\nWrite email.\n")
        self.routing = R.Routing(self.assets)
        self.target = self.candidate["target_id"]

    def evaluate(self, description=DESCRIPTION, key="routing-evaluate", cases=CASES):
        return self.routing.evaluate(self.owner, self.target, description, cases, event_key=key)

    def test_evaluate_records_an_immutable_candidate_and_replays(self):
        result = self.evaluate()
        self.assertEqual(result["verdict"], "eligible")
        self.assertEqual(result["report"]["outcomes"]["win"], 5)
        self.assertEqual(self.evaluate(), result)
        self.assertEqual(self.routing.candidates(self.owner, target_id=self.target)[0]["candidate_id"], result["candidate_id"])
        self.assertEqual(self.skill.read_bytes(), self.canonical)

    def test_applied_description_reaches_the_main_chat_router_only(self):
        from capability_registry import CapabilityRegistry
        from lazy_skill_runtime import LazySkillSource
        candidate = self.evaluate()
        self.assertEqual(R.main_chat_descriptions(self.root), {})
        overlay = self.routing.apply(self.owner, candidate["candidate_id"], event_key="routing-apply")
        self.assertEqual(overlay["scope"], {"context": "main"})
        descriptions = R.main_chat_descriptions(self.root)
        self.assertEqual(descriptions, {"report": DESCRIPTION})
        source = LazySkillSource(CapabilityRegistry(self.root.parent / "registry"))
        selected = source.resolve(self.root, "doi soat cong no khach hang", descriptions=descriptions)
        self.assertEqual((selected.action, selected.slug), ("load", "report"))
        self.assertEqual(selected.context_item.metadata["routing_description"], "overlay")
        plain = source.resolve(self.root, "doi soat cong no khach hang", descriptions={"other": "x"})
        self.assertNotEqual(plain.slug, "report")
        metas = R.with_descriptions([{"slug": "report", "description": "old"}, {"slug": "viet-email", "description": "e"}], descriptions)
        self.assertEqual([m["description"] for m in metas], [DESCRIPTION, "e"])
        self.assertEqual(self.skill.read_bytes(), self.canonical)
        reverted = self.routing.revert(self.owner, overlay["overlay_id"], expected_generation=1, event_key="routing-revert")
        self.assertEqual(reverted["state"], "reverted")
        self.assertEqual(R.main_chat_descriptions(self.root), {})

    def test_rejected_candidate_cannot_be_applied(self):
        stealing = [{"query": "gui thu cam on khach hang", "expected": "viet-email", "kind": "competing"}]
        candidate = self.evaluate("Gui thu cam on khach hang moi tuan", key="routing-steal", cases=stealing)
        self.assertEqual(candidate["verdict"], "rejected")
        with self.assertRaisesRegex(PermissionError, "rejected"):
            self.routing.apply(self.owner, candidate["candidate_id"], event_key="routing-apply-rejected")

    def test_owner_edit_or_disable_drops_the_overlay(self):
        candidate = self.evaluate()
        overlay = self.routing.apply(self.owner, candidate["candidate_id"], event_key="routing-apply-drift")
        self.skill.write_bytes(self.canonical + b"\nOwner edit.\n")
        self.assertEqual(R.main_chat_descriptions(self.root), {})
        self.assertEqual(self.routing.reconcile(self.owner), [{"overlay_id": overlay["overlay_id"], "reason": "canonical_changed"}])
        with self.assertRaises(IM.ConflictError):
            self.routing.apply(self.owner, candidate["candidate_id"], event_key="routing-apply-after-edit")

    def test_disabled_skill_is_never_described(self):
        candidate = self.evaluate()
        self.routing.apply(self.owner, candidate["candidate_id"], event_key="routing-apply-disabled")
        disabled = self.root / "skills" / ".disabled" / self.slug
        disabled.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(self.skill.parent), str(disabled))
        self.assertEqual(R.main_chat_descriptions(self.root), {})

    def test_one_overlay_per_skill_in_the_main_chat(self):
        first = self.evaluate()
        self.routing.apply(self.owner, first["candidate_id"], event_key="routing-apply-one")
        second = self.evaluate("Doi soat cong no va hoa don", key="routing-evaluate-two")
        with self.assertRaisesRegex(IM.ConflictError, "busy"):
            self.routing.apply(self.owner, second["candidate_id"], event_key="routing-apply-two")

    def test_production_router_evaluation_and_refusals(self):
        from capability_registry import CapabilityRegistry
        live = R.Routing(self.assets, registry=CapabilityRegistry(self.root.parent / "registry-live"))
        result = live.evaluate(self.owner, self.target, DESCRIPTION, CASES, event_key="routing-live-eval")
        self.assertIn(result["verdict"], ("eligible", "inconclusive"))
        self.assertEqual(len(result["report"]["cases"]), len(CASES))
        current = self.skill.read_text(encoding="utf-8").split("description:", 1)[1].splitlines()[0].strip()
        with self.assertRaisesRegex(ValueError, "unchanged"):
            live.evaluate(self.owner, self.target, current, CASES, event_key="routing-unchanged")
        with self.assertRaisesRegex(ValueError, "regression"):
            live.evaluate(self.owner, self.target, DESCRIPTION, CASES[:5], event_key="routing-no-regression")
        self.skill.write_bytes(self.canonical.replace(b"\n---\n", b"\ndescription_en: English text\n---\n", 1))
        with self.assertRaisesRegex(ValueError, "translated"):
            live.evaluate(self.owner, self.target, DESCRIPTION, CASES, event_key="routing-translated")

    def test_overlay_candidates_keep_the_search_set(self):
        from lazy_skill_runtime import _overlay_candidates
        found = [{"name": "viet-email", "kind": "skill", "summary": "Soan thu", "metadata": {"slug": "viet-email"}},
                 {"name": "web-tool", "kind": "tool", "summary": "x", "metadata": {}}]
        rows = _overlay_candidates(self.root, "", "doi soat", found, {"report": DESCRIPTION})
        self.assertEqual([r["metadata"]["slug"] for r in rows], ["viet-email", "report"])
        self.assertEqual(rows[0]["summary"], "Soan thu")
        self.assertEqual(rows[1]["summary"], DESCRIPTION)
        rows = _overlay_candidates(self.root, "", "q", [{"name": "report", "kind": "skill", "summary": "old",
                                                        "metadata": {"slug": "report"}}], {"report": DESCRIPTION})
        self.assertEqual([r["summary"] for r in rows], [DESCRIPTION])

    def test_prompt_index_uses_overlays_only_when_the_caller_says_api(self):
        import main
        base.IA.configure(self.store.path, self.assets.blobs)  # importing main points read time at its own state
        candidate = self.evaluate(key="routing-prompt-eval")
        self.routing.apply(self.owner, candidate["candidate_id"], event_key="routing-prompt-apply")
        api = main.build_adaptive_source_prompt(str(self.root), include_skills=True, routing_overlays=True)
        cli = main.build_adaptive_source_prompt(str(self.root), include_skills=True)
        self.assertIn(DESCRIPTION, api)
        self.assertNotIn(DESCRIPTION, cli)

    def test_bound_task_scope_never_mixes_live_overlays(self):
        from unittest.mock import patch
        candidate = self.evaluate(key="routing-scope-eval")
        self.routing.apply(self.owner, candidate["candidate_id"], event_key="routing-scope-apply")
        with patch("improvement_task_skill_scope.has_binding", return_value=True):
            self.assertEqual(R.main_chat_descriptions(self.root), {})

    def test_schema_thirteen_from_twelve_adds_tables_once(self):
        import sqlite3
        from contextlib import closing
        from unittest.mock import patch
        IM.ensure(self.store)
        with self.store._Tx(self.store) as connection:
            for name in ("improvement_imports", "improvement_refinements", "improvement_transfers", "improvement_team_trials", "improvement_team_pins", "improvement_bundle_members", "improvement_bundle_activations", "improvement_agent_overlays", "improvement_agent_procedures", "improvement_routing_overlays", "improvement_routing_candidates"):
                connection.execute(f"DROP TABLE {name}")
            connection.execute("UPDATE improvement_schema SET version=12 WHERE id=1")
        IM.ensure(self.store)
        self.assertEqual(IM._schema_version(self.store), IM.SCHEMA_VERSION)
        backups = list(self.store.path.parent.glob(self.store.path.name + ".pre-improvement-m4-routing.bak"))
        self.assertEqual(len(backups), 1)
        with closing(sqlite3.connect(backups[0])) as connection:
            self.assertEqual(connection.execute("SELECT version FROM improvement_schema").fetchone()[0], 12)
        with patch.object(self.store, "_backup_before", side_effect=AssertionError("no second backup")):
            IM.ensure(self.store)

    def test_http_routes_round_trip(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        import improvement_activation_api as API
        app = FastAPI()
        API.register(app, API.ActivationApiDeps(activations=lambda: self.activations,
            resolve_brain=lambda value: self.owner.brain_id, routing=lambda: self.routing))
        client = TestClient(app)
        evaluated = client.post("/improvement-routing/evaluate", json={"target_id": self.target, "description": DESCRIPTION,
                                                                       "cases": CASES, "event_key": "http-routing-eval"})
        self.assertEqual(evaluated.status_code, 200, evaluated.text)
        candidate = evaluated.json()["routing"]["candidate_id"]
        applied = client.post(f"/improvement-routing/{candidate}/apply", json={"event_key": "http-routing-apply"}).json()
        listed = client.get(f"/improvement-routing?target_id={self.target}").json()
        self.assertEqual(listed["overlays"][0]["overlay_id"], applied["overlay"]["overlay_id"])
        self.assertIn("assistant_chats", listed["coverage"]["not_served"])
        bad = client.post("/improvement-routing/evaluate", json={"target_id": self.target, "description": "x" * 200,
                                                                 "cases": CASES, "event_key": "http-routing-bad"})
        self.assertEqual(bad.status_code, 422)


class CanaryRoutingEngineTests(unittest.TestCase):
    """The Phase 8 canary hands routing descriptions to API engines and never to CLI engines."""

    def resolve_kwargs(self, provider_kind):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        import test_adaptive_context_phase8 as phase8
        from adaptive_context_runtime import AdaptiveContextCanary
        from capability_registry import CapabilityRegistry
        from context_compiler import ContextCompiler
        from context_runtime import ObserveRuntime
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            tmp = Path(tmp)
            phase8._write(tmp / "brain" / "skills" / "webcake" / "SKILL.md",
                          "---\nname: Webcake\ndescription: Xuat landing page Webcake\n---\nBody.")
            settings = phase8._settings("lazy_skill_canary")
            settings["context_runtime"]["lazy_skill_canary"]["provider_kinds"] = ["api", "cli"]
            registry = CapabilityRegistry(tmp / "state")
            canary = AdaptiveContextCanary(tmp / "state", registry, ContextCompiler(registry),
                                           ObserveRuntime(tmp / "state", settings_reader=lambda: settings), lambda: settings)
            canary.routing_descriptions = lambda brain: {"webcake": "Overlay description"}
            seen = []
            real = canary.skills.resolve

            def capture(*args, **kwargs):
                seen.append(kwargs.get("descriptions"))
                return real(*args, **kwargs)
            with patch.object(canary.skills, "resolve", side_effect=capture):
                canary.prepare(None, "Xuat landing page Webcake", tmp / "brain", "s", phase8._messages(), "dashboard",
                               "groq", "llama-test", provider_kind, lambda _m, _s: "base")
            return seen

    def test_api_engine_gets_descriptions_cli_engine_does_not(self):
        self.assertEqual(self.resolve_kwargs("api"), [{"webcake": "Overlay description"}])
        self.assertEqual(self.resolve_kwargs("cli"), [None])


if __name__ == "__main__":
    unittest.main()
