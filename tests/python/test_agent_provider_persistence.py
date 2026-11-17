"""Real agent save/read boundaries in a temporary brain, without model or external calls."""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="provider-persistence-")
import main


class ProviderPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="provider-brain-"))
        self.agents = self.root / "agents"
        self.agents.mkdir()
        self.paths = patch.object(main, "_agents_dir", return_value=self.agents)
        self.paths.start()
        self.addCleanup(self.paths.stop)

    def save(self, provider, model="same-model"):
        return asyncio.run(main.save_agent(name="Fixture", role="", skills="", model=model, slug="fixture",
                                          prompt="Harmless fixture", brain=str(self.root), model_provider=provider,
                                          avatar_shape=None, avatar_palette=None, avatar_color=None, avatar_eye=None,
                                          avatar_eye_color=None, avatar_eye_size=None, avatar_image=None))

    def test_duplicate_model_roundtrip(self):
        for provider in ("anthropic-compat", "antigravity-cli", "openai-compat", "openai-oauth"):
            with self.subTest(provider=provider):
                self.assertTrue(self.save(provider)["ok"])
                metadata, _ = main._read_md(self.agents / "fixture.md")
                self.assertEqual((metadata["model_provider"], metadata["model"]), (provider, "same-model"))
                self.assertEqual(main._agent_model_provider(metadata["model"], metadata["model_provider"]), provider)

    def test_invalid_provider_cannot_erase_previous_selection(self):
        self.save("anthropic-compat")
        before = (self.agents / "fixture.md").read_bytes()
        response = self.save("CLAUDE COMPATIBLE")
        self.assertEqual(getattr(response, "status_code", None), 400)
        self.assertEqual((self.agents / "fixture.md").read_bytes(), before)

    def test_missing_provider_cannot_erase_previous_selection(self):
        self.save("anthropic-compat")
        before = (self.agents / "fixture.md").read_bytes()
        response = self.save("")
        self.assertEqual(getattr(response, "status_code", None), 400)
        self.assertEqual((self.agents / "fixture.md").read_bytes(), before)

    def test_explicit_default_clears_pair(self):
        self.save("anthropic-compat")
        self.assertTrue(self.save("", "")["ok"])
        metadata, _ = main._read_md(self.agents / "fixture.md")
        self.assertEqual((metadata["model_provider"], metadata["model"]), ("", ""))

    def test_save_returns_effective_and_admin_enforces_identical_validation(self):
        res = self.save("openai-oauth", "gpt-6-astra")
        self.assertTrue(res["ok"])
        self.assertEqual(res["effective"]["provider"], "openai-oauth")
        self.assertEqual(res["effective"]["model"], "gpt-6-astra")
        self.assertEqual(res["effective"]["source"], "agent")
        self.assertIn("modes", res["effective"])

        adm = main._TeamAdmin()
        with self.assertRaises(ValueError):
            adm.set_model(str(self.root), "fixture", "gpt-6-astra", "unknown-provider")
        with self.assertRaises(ValueError):
            adm.set_model(str(self.root), "fixture", "gpt-6-astra", "")
        meta, _ = main._read_md(self.agents / "fixture.md")
        self.assertEqual((meta["model_provider"], meta["model"]), ("openai-oauth", "gpt-6-astra"))

    def test_compat_gateway_manual_catalog_source_and_forced_logout_impact(self):
        cfg = main.cfgmod.read_settings()
        m = cfg.setdefault("model", {})
        main.adv_keys.add(m, main.adv_keys.OPENAI, "Seller", "https://api.seller.example/v1", "k-1", ["manual-only-m1"])
        main._set_main_model(cfg, "antigravity-cli", "gemini-pro-orchestrator")
        main.cfgmod.write_settings(cfg)
        main._PROV_MODELS_CACHE.pop("openai-compat", None)

        probes = main._capability_probes(main.cfgmod.read_settings())
        cats = probes.catalog("openai-compat")
        self.assertEqual(cats.get("manual"), ["manual-only-m1"])
        self.assertFalse(cats.get("remembered"))
        eff = main._agent_effective({"model_provider": "openai-compat", "model": "manual-only-m1"}, probes)
        self.assertEqual(eff["evidence"]["model"]["sources"], ["manual"])
        self.assertEqual(eff["status"], "unverified")
        self.assertEqual(eff["reason_code"], "model_unverified")

        imp = main._drop_card("antigravity-cli")
        self.assertIsNotNone(imp)
        self.assertEqual(imp["before"]["provider"], "antigravity-cli")
        self.assertEqual(imp["after"]["provider"], "anthropic-cli")


if __name__ == "__main__":
    unittest.main()
