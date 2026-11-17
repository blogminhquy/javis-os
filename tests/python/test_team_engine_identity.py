"""Provider identity must survive resolution, including unavailable selections. No network."""
from _paths import ROOT, SERVER  # noqa: F401
import os
import tempfile
import unittest
import asyncio
from types import SimpleNamespace
from unittest.mock import patch

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="engine-identity-")

import aux_engine
import team_engine
import team_gate
import engine
import engine_capability as cap


class EngineIdentityTests(unittest.TestCase):
    def test_unavailable_agent_never_falls_back(self):
        spec = team_engine.choose_spec("argon-4", "anthropic-compat",
                                       {"provider": "openai-oauth", "model": "codex-model"},
                                       lambda m, p: p, lambda s: (False, "missing endpoint"), tools=True)
        self.assertEqual((spec["provider"], spec["model"], spec["source"]),
                         ("anthropic-compat", "argon-4", "agent"))

    def test_text_only_selection_does_not_change_provider(self):
        for provider in (aux_engine.ANTIGRAVITY, aux_engine.GROK_CLI):
            with self.subTest(provider=provider):
                spec = team_engine.choose_spec("same-model", provider,
                                               {"provider": aux_engine.CODEX, "model": "other"},
                                               lambda m, p: p, lambda s: (True, ""))
                self.assertEqual(spec["provider"], provider)

    def test_only_empty_selection_inherits_main(self):
        spec = team_engine.choose_spec("", "", {"provider": "openai", "model": "main"},
                                       lambda m, p: p, lambda s: (False, "offline"))
        self.assertEqual((spec["provider"], spec["model"], spec["source"]), ("openai", "main", "main"))

    def test_identical_model_names_preserve_provider(self):
        for provider in aux_engine.API_PROVIDERS:
            with self.subTest(provider=provider):
                spec = team_engine.choose_spec("shared-name", provider, {}, lambda m, p: p,
                                               lambda s: (True, ""), tools=True)
                self.assertEqual((spec["provider"], spec["model"]), (provider, "shared-name"))

    def test_unknown_provider_is_not_reinterpreted(self):
        spec = team_engine.choose_spec("shared-name", "not-a-provider", {}, lambda m, p: aux_engine.CLAUDE,
                                       lambda s: (True, ""), tools=True)
        self.assertEqual(spec["provider"], "not-a-provider")
        with self.assertRaises(team_engine.TeamEngineUnavailable) as caught:
            team_engine.build_tools(spec, object(), "test", {})
        self.assertEqual(caught.exception.code, "provider_unknown")
        self.assertFalse(caught.exception.retryable)

    def test_gate_remains_fail_closed(self):
        for provider in (aux_engine.ANTIGRAVITY, aux_engine.GROK_CLI, "unknown"):
            self.assertFalse(team_gate.provider_support(provider)["ok"])
        self.assertFalse(team_gate.provider_support(aux_engine.CODEX, codex_sandbox=None)["ok"])
        for provider in aux_engine.API_PROVIDERS:
            self.assertTrue(team_gate.provider_support(provider, api_providers=aux_engine.API_PROVIDERS)["ok"])

    def test_every_api_adapter_builds_and_dispatches_selected_identity(self):
        adapters = {"openrouter": "openrouter", "openai": "openai", "gemini": "gemini", "groq": "groq",
                    "deepseek": "deepseek", "anthropic-api": "anthropic", "ollama": "ollama",
                    "ollama-local": "ollama_local", "openai-compat": "openai_compat",
                    "anthropic-compat": "anthropic_compat"}
        self.assertEqual(set(adapters), set(aux_engine.API_PROVIDERS))
        base = SimpleNamespace(system_prompt="fixture", cwd=None, javis_vault=None, allowed_tools=["none"])
        for provider, function in adapters.items():
            with self.subTest(provider=provider):
                seen = []

                async def stream(key, model, messages, reasoning):
                    seen.append(model)
                    yield {"type": "text", "content": "fixture response"}

                async def collect(adapter):
                    return [event async for event in adapter.query("harmless fixture")]

                with patch.object(aux_engine, "availability", return_value=(True, "")), \
                        patch.object(aux_engine, "api_key_for", return_value="fixture-not-a-key"), \
                        patch.object(engine, function + "_stream", stream):
                    adapter = team_engine.build({"provider": provider, "model": "shared-name"}, base, "test", {})
                    events = asyncio.run(collect(adapter))
                    self.assertEqual(seen, ["shared-name"])
                    self.assertEqual(adapter.provider, provider)
                    self.assertEqual(events[-1]["content"], "fixture response")
                    tools = team_engine.build_tools({"provider": provider, "model": "shared-name"}, base,
                                                    "test", {}, mode="gated")
                    self.assertEqual((tools.provider, tools.model, tools.javis_mode),
                                     (provider, "shared-name", "gated"))
                    self.assertFalse(tools.terminal)

    def test_missing_dependency_is_not_a_fallback(self):
        with patch.object(aux_engine, "availability", return_value=(False, "Missing CLI dependency")):
            with self.assertRaises(team_engine.TeamEngineUnavailable) as caught:
                team_engine.build_tools({"provider": aux_engine.CODEX, "model": "selected"}, object(), "test", {})
        self.assertEqual(caught.exception.provider, aux_engine.CODEX)
        self.assertFalse(caught.exception.retryable)


def _probes(avail=None, gate=None, catalog=None, legacy=None):
    return cap.Probes(availability=avail or (lambda sp: (True, "")),
                      gate_support=gate or (lambda p: {"ok": p in (aux_engine.CLAUDE,) + aux_engine.API_PROVIDERS,
                                                       "reason": "" if p == aux_engine.CLAUDE else "no gate"}),
                      catalog=catalog, legacy_provider=legacy)


class CapabilityContractTests(unittest.TestCase):
    def setUp(self):
        cap._reset_outcomes_for_tests()

    def test_known_providers_match_agent_providers(self):
        import re
        src = (SERVER / "main.py").read_text(encoding="utf-8")
        block = re.search(r"^AGENT_PROVIDERS = \((.*?)\)\n", src, re.S | re.M).group(1)
        names = set(re.findall(r'"([a-z0-9-]+)"', block))
        self.assertEqual(names, set(cap.KNOWN_PROVIDERS))

    def test_mode_matrix_keeps_guard(self):
        self.assertFalse(cap.adapter_static(aux_engine.ANTIGRAVITY, cap.TEAM_TEXT))
        self.assertFalse(cap.adapter_static(aux_engine.GROK_CLI, cap.TEAM_TEXT))
        self.assertTrue(cap.adapter_static(aux_engine.ANTIGRAVITY, cap.SOLO_CHAT))
        self.assertTrue(cap.adapter_static(aux_engine.ANTIGRAVITY, cap.TEAM_TOOL_FULL))
        self.assertFalse(cap.adapter_static(aux_engine.ANTIGRAVITY, cap.TEAM_TOOL_GATED))
        for p in (aux_engine.CLAUDE, aux_engine.CODEX) + aux_engine.API_PROVIDERS:
            self.assertTrue(cap.adapter_static(p, cap.TEAM_TEXT), p)
        # team_engine delegates to the same table
        for p in cap.KNOWN_PROVIDERS + ("unknown",):
            self.assertEqual(team_engine.text_only_supported(p), cap.adapter_static(p, cap.TEAM_TEXT))
            self.assertEqual(team_engine.tools_supported(p), cap.adapter_static(p, cap.TEAM_TOOL_FULL))

    def test_mode_for_matches_runner(self):
        self.assertEqual(cap.mode_for("leader_reply", "gated"), cap.TEAM_TEXT)
        self.assertEqual(cap.mode_for("plan", "full"), cap.TEAM_TEXT)
        self.assertEqual(cap.mode_for("work", "full"), cap.TEAM_TOOL_FULL)
        self.assertEqual(cap.mode_for("help", None), cap.TEAM_TOOL_GATED)   # missing work_mode = gated
        self.assertEqual(cap.mode_for("work", "full", has_task=False), cap.TEAM_TEXT)

    def test_naval_case_inherited_and_explicit_antigravity(self):
        main = {"provider": aux_engine.ANTIGRAVITY, "model": "gemini-pro-orchestrator"}
        naval = cap.resolve({"model": "claude-opus-5-5-high", "model_provider": aux_engine.ANTIGRAVITY}, main,
                            cap.TEAM_TEXT, _probes(), all_modes=True)
        self.assertEqual((naval["provider"], naval["source"], naval["status"], naval["reason_code"]),
                         (aux_engine.ANTIGRAVITY, "agent", "blocked", "capability_unsupported"))
        self.assertFalse(naval["retryable"])
        self.assertTrue(naval["message"] and naval["fix_hint"])
        self.assertEqual({m: v["ok"] for m, v in naval["modes"].items()},
                         {cap.SOLO_CHAT: True, cap.TEAM_TEXT: False, cap.TEAM_TOOL_FULL: True,
                          cap.TEAM_TOOL_GATED: False})
        inherited = cap.resolve({"model": "", "model_provider": ""}, main, cap.TEAM_TEXT, _probes())
        self.assertEqual((inherited["provider"], inherited["model"], inherited["source"], inherited["status"]),
                         (aux_engine.ANTIGRAVITY, "gemini-pro-orchestrator", "main", "blocked"))

    def test_codex_member_ready_and_never_rerouted(self):
        main = {"provider": aux_engine.ANTIGRAVITY, "model": "x"}
        eric = cap.resolve({"model": "gpt-6-astra", "model_provider": aux_engine.CODEX}, main, cap.TEAM_TEXT,
                           _probes())
        self.assertEqual((eric["provider"], eric["model"], eric["status"]), (aux_engine.CODEX, "gpt-6-astra", "ready"))
        down = cap.resolve({"model": "gpt-6-astra", "model_provider": aux_engine.CODEX}, main, cap.TEAM_TEXT,
                           _probes(avail=lambda sp: (False, "signed out")))
        self.assertEqual((down["provider"], down["status"], down["reason_code"]),
                         (aux_engine.CODEX, "blocked", "auth_missing"))
        self.assertEqual(down["evidence"]["configured"], {"ok": False, "detail": "signed out"})

    def test_unknown_provider_and_legacy(self):
        r = cap.resolve({"model": "m", "model_provider": "not-a-provider"}, {}, cap.SOLO_CHAT, _probes())
        self.assertEqual((r["provider"], r["reason_code"], r["status"]), ("not-a-provider", "provider_unknown", "blocked"))
        leg = cap.resolve({"model": "gpt-5", "model_provider": ""}, {"provider": aux_engine.CLAUDE}, cap.TEAM_TEXT,
                          _probes(legacy=lambda m: aux_engine.CODEX))
        self.assertEqual((leg["provider"], leg["source"], leg["status"]), (aux_engine.CODEX, "legacy", "ready"))
        noleg = cap.resolve({"model": "gpt-5"}, {}, cap.TEAM_TEXT, _probes())
        self.assertEqual(noleg["reason_code"], "provider_unknown")   # no resolver: never guessed

    def test_api_provider_needs_model(self):
        r = cap.resolve({"model": "", "model_provider": ""}, {"provider": "openrouter", "model": ""}, cap.TEAM_TEXT,
                        _probes())
        self.assertEqual(r["reason_code"], "model_invalid")

    def test_catalog_evidence_is_per_provider_and_source(self):
        cats = {"openai-compat": {"manual": ["shared"], "remote": []},
                "anthropic-compat": {"remote": ["other"]},
                "openrouter": {"remote": ["shared"], "default": ["d"]}}
        pr = _probes(catalog=lambda p: cats.get(p, {}))
        a = cap.resolve({"model": "shared", "model_provider": "openai-compat"}, {}, cap.TEAM_TEXT, pr)
        b = cap.resolve({"model": "shared", "model_provider": "anthropic-compat"}, {}, cap.TEAM_TEXT, pr)
        c = cap.resolve({"model": "shared", "model_provider": "openrouter"}, {}, cap.TEAM_TEXT, pr)
        self.assertEqual(a["evidence"]["model"], {"known": True, "sources": ["manual"]})
        self.assertEqual(a["status"], "unverified")   # manual-only compat gateway
        self.assertEqual(b["evidence"]["model"], {"known": False, "sources": []})   # name on another provider: no
        self.assertEqual(b["status"], "unverified")
        self.assertEqual((c["evidence"]["model"]["sources"], c["status"]), (["remote"], "ready"))

    def test_last_call_evidence_is_separate(self):
        cap.record_outcome("openai-oauth", "gpt-6-astra", False, "provider_not_ready")
        r = cap.resolve({"model": "gpt-6-astra", "model_provider": "openai-oauth"}, {}, cap.TEAM_TEXT, _probes())
        self.assertEqual(r["status"], "ready")   # history never changes routing or status
        self.assertEqual(r["evidence"]["last_call"]["code"], "auth_missing")

    def test_validate_agent_selection(self):
        self.assertFalse(cap.validate_agent_selection("bogus", "m")["ok"])
        r = cap.validate_agent_selection("", "gpt-5")
        self.assertEqual((r["ok"], r["reason_code"]), (False, "provider_unknown"))
        r = cap.validate_agent_selection("openai-oauth", "")
        self.assertEqual((r["ok"], r["provider"], r["model"]), (True, "", ""))   # empty model = inherit MAIN
        self.assertEqual(cap.validate_agent_selection("openai", "bad model\n")["reason_code"], "model_invalid")
        self.assertTrue(cap.validate_agent_selection(aux_engine.ANTIGRAVITY, "claude-opus-5-5-high")["ok"])

    def test_team_status_refuses_antigravity_leader_flags_auth(self):
        main = {"provider": aux_engine.CODEX, "model": "gpt-6-astra"}
        members = [{"agent_key": "naval", "name": "Naval", "model": "claude-opus-5-5-high",
                    "model_provider": aux_engine.ANTIGRAVITY},
                   {"agent_key": "eric", "name": "Eric", "model": "gpt-6-astra", "model_provider": aux_engine.CODEX}]
        st = cap.team_status(members, "naval", "gated", main, _probes(gate=lambda p: {"ok": True}))
        self.assertEqual((st["status"], st["refuse"]), ("blocked", True))
        naval = st["members"][0]
        self.assertEqual(naval["role"], "leader")
        self.assertEqual({i["mode"] for i in naval["issues"]}, {cap.TEAM_TEXT, cap.TEAM_TOOL_GATED})
        self.assertEqual(st["members"][1]["issues"], [])
        auth = cap.team_status(members[1:], "eric", "full", main, _probes(avail=lambda sp: (False, "x")))
        self.assertEqual((auth["status"], auth["refuse"]), ("blocked", False))
        self.assertEqual(len(auth["members"][0]["issues"]), 1)   # auth reported once, not per mode

    def test_codex_gated_off_is_warning_not_refusal(self):
        # #16/#18: machine without Codex sandbox; Codex member chats fine, only gated tool steps cannot run.
        gate = lambda p: {"ok": p != aux_engine.CODEX, "reason": "Codex sandbox off on this machine"}  # noqa: E731
        eric = {"agent_key": "eric", "name": "Eric", "model": "gpt-6-astra", "model_provider": aux_engine.CODEX}
        st = cap.team_status([eric], "eric", "gated", {}, _probes(gate=gate))
        self.assertEqual((st["status"], st["refuse"]), ("warning", False))
        issue = st["members"][0]["issues"][0]
        self.assertEqual((issue["mode"], issue["reason_code"], issue["severity"]),
                         (cap.TEAM_TOOL_GATED, "capability_unsupported", "warning"))
        self.assertIn("sandbox off", issue["message"])
        self.assertNotIn("full", issue["fix_hint"].lower())
        self.assertEqual(cap.team_status([eric], "eric", "full", {}, _probes(gate=gate))["status"], "ready")
        # runtime still refuses the gated step itself
        self.assertEqual(cap.resolve(eric, {}, cap.TEAM_TOOL_GATED, _probes(gate=gate))["status"], "blocked")

    def test_unverified_catalog_is_not_team_noise(self):
        pr = _probes(catalog=lambda p: {"remote": ["other"]})
        st = cap.team_status([{"agent_key": "a", "model": "m1", "model_provider": "openrouter"}], "a", "full", {}, pr)
        self.assertEqual(st["status"], "ready")

    def test_main_change_impact(self):
        agents = [{"key": "it-1", "name": "IT 1", "model": "", "model_provider": ""},
                  {"key": "eric", "name": "Eric", "model": "gpt-6-astra", "model_provider": aux_engine.CODEX}]
        teams = [{"team_id": "t1", "name": "IT", "leader_key": "it-1", "work_mode": "full",
                  "members": [dict(agents[0], agent_key="it-1")]}]
        old = {"provider": aux_engine.CODEX, "model": "gpt-6-astra"}
        new = {"provider": aux_engine.ANTIGRAVITY, "model": "gemini-pro-orchestrator"}
        imp = cap.main_change_impact(agents, teams, old, new, _probes())
        self.assertEqual([a["key"] for a in imp["agents"]], ["it-1"])   # explicit agents unaffected
        self.assertEqual(imp["agents"][0]["after_status"], "ready")    # solo chat still works
        self.assertFalse(imp["agents"][0]["team_text_after"]["ok"])
        self.assertEqual((imp["teams"][0]["before"], imp["teams"][0]["after"]), ("ready", "blocked"))
        self.assertEqual(imp["blocking"], 1)
        self.assertEqual(cap.main_change_impact(agents, teams, old, old, _probes())["blocking"], 0)

    def test_reason_codes_and_runtime_classification(self):
        for code, retry in (("capability_unsupported", False), ("auth_missing", False), ("model_invalid", False),
                            ("provider_unknown", False), ("quota_or_rate_limit", True), ("network", True),
                            ("build_failed", False)):
            r = cap.reason(code, "openai-oauth", cap.TEAM_TEXT)
            self.assertEqual((r["reason_code"], r["retryable"]), (code, retry))
            self.assertTrue(r["message"] and r["fix_hint"])
        self.assertEqual(cap.normalize_code("invalid_provider"), "provider_unknown")
        self.assertEqual(cap.normalize_code("provider_not_ready"), "auth_missing")
        self.assertEqual(cap.classify_runtime_error("HTTP 429 Too Many Requests"), "quota_or_rate_limit")
        self.assertEqual(cap.classify_runtime_error("401 Unauthorized"), "auth_missing")
        self.assertEqual(cap.classify_runtime_error("model gpt-x not found"), "model_invalid")
        self.assertEqual(cap.classify_runtime_error("ConnectError: connection refused"), "network")
        self.assertEqual(cap.classify_runtime_error("weird", stage="build"), "build_failed")
        self.assertEqual(cap.classify_runtime_error("weird"), "")

    def test_team_engine_errors_carry_stable_codes(self):
        base = SimpleNamespace(system_prompt="s", cwd=None, allowed_tools=["none"])
        with self.assertRaises(team_engine.TeamEngineUnavailable) as c:
            team_engine.build({"provider": aux_engine.ANTIGRAVITY, "model": "m"}, base, "t", {})
        self.assertEqual((c.exception.code, c.exception.stage, c.exception.retryable),
                         ("capability_unsupported", "capability", False))
        self.assertTrue(c.exception.fix_hint)
        with patch.object(aux_engine, "availability", return_value=(False, "no key")):
            with self.assertRaises(team_engine.TeamEngineUnavailable) as c:
                team_engine.build({"provider": "openai", "model": "m"}, base, "t", {})
        self.assertEqual((c.exception.code, c.exception.provider, c.exception.reason), ("auth_missing", "openai", "no key"))

    def test_gate_probe_failure_fails_closed(self):
        def boom(p):
            raise RuntimeError("probe broke")
        ok, _ = cap.adapter_supports(aux_engine.CLAUDE, cap.TEAM_TOOL_GATED, cap.Probes(gate_support=boom))
        self.assertFalse(ok)
        ok, _ = cap.adapter_supports(aux_engine.CODEX, cap.TEAM_TOOL_GATED, None)   # no probe: no sandbox assumed
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
