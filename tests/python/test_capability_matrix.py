"""Regression matrix for provider/model capability resolution and Team runtime guards.

    python tests/python/test_capability_matrix.py

Runs purely in-process against temp state/SQLite stores with fake engines (no network,
no real CLI subprocesses, no live container state). Covers:
- 9 provider/model cases: explicit Antigravity, inherited Antigravity, Codex/openai-oauth,
  API providers (anthropic-compat / openai-compat), unknown provider, legacy model-only,
  missing auth, invalid model, and identical model name across two providers.
- Modes & paths: solo_chat, team_text, team_tool_full, team_tool_gated,
  validate_agent_selection, team_status, main_change_impact, classify_runtime_error,
  record_outcome, team_runner text-only (proving zero tool side effects), planning,
  tool turn, gated turn (proving approval still required), retry (config errors not
  auto-retried; manual retry reflects updated config), and restart persistence.
"""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="cap-matrix-state-")
TEMP_ROOT = Path(tempfile.mkdtemp(prefix="cap-matrix-work-")).resolve()

import aux_engine  # noqa: E402
import engine  # noqa: E402
import engine_capability as EC  # noqa: E402
import sessions  # noqa: E402
import task_store  # noqa: E402
import team_approval  # noqa: E402
import team_engine  # noqa: E402
import team_gate  # noqa: E402
import team_runner as TR  # noqa: E402
import team_store  # noqa: E402


MAIN_AGY = {"provider": EC.ANTIGRAVITY, "model": "gemini-pro-orchestrator"}
MAIN_CODEX = {"provider": EC.CODEX, "model": "gpt-6-astra"}


def make_probes(
    *,
    unavailable=(),
    gate_ok=(EC.CLAUDE, EC.CODEX) + EC.API_PROVIDERS,
    catalogs=None,
    legacy_map=None,
):
    unavailable_set = set(unavailable)
    gate_set = set(gate_ok)
    cats = dict(catalogs or {})
    lmap = dict(legacy_map or {})

    def availability(spec):
        prov = str((spec or {}).get("provider") or "")
        if prov in unavailable_set:
            return False, f"{prov} not signed in"
        return True, ""

    def gate_support(prov):
        if prov in gate_set:
            return {"ok": True, "reason": ""}
        return {"ok": False, "reason": f"{prov} gated tools unavailable on this machine"}

    def catalog(prov):
        return dict(cats.get(prov) or {})

    def legacy_provider(model):
        return str(lmap.get(model) or "")

    return EC.Probes(
        availability=availability,
        gate_support=gate_support,
        catalog=catalog,
        legacy_provider=legacy_provider,
        known_providers=EC.KNOWN_PROVIDERS,
    )


def run_async(coro):
    return asyncio.run(coro)


class CapabilityResolveMatrixTests(unittest.TestCase):
    def setUp(self):
        EC._reset_outcomes_for_tests()

    def test_explicit_antigravity_modes(self):
        probes = make_probes(catalogs={EC.ANTIGRAVITY: {"default": ["gemini-4-hydrogen-high"]}})
        agent = {"model_provider": EC.ANTIGRAVITY, "model": "gemini-4-hydrogen-high"}

        solo = EC.resolve(agent, MAIN_CODEX, EC.SOLO_CHAT, probes, all_modes=True)
        self.assertEqual((solo["provider"], solo["model"], solo["source"], solo["status"]),
                         (EC.ANTIGRAVITY, "gemini-4-hydrogen-high", "agent", "ready"))
        self.assertTrue(solo["modes"][EC.SOLO_CHAT]["ok"])
        self.assertTrue(solo["modes"][EC.TEAM_TOOL_FULL]["ok"])
        self.assertFalse(solo["modes"][EC.TEAM_TEXT]["ok"])
        self.assertEqual(solo["modes"][EC.TEAM_TEXT]["reason_code"], EC.CAPABILITY_UNSUPPORTED)
        self.assertFalse(solo["modes"][EC.TEAM_TOOL_GATED]["ok"])
        self.assertEqual(solo["modes"][EC.TEAM_TOOL_GATED]["reason_code"], EC.CAPABILITY_UNSUPPORTED)

        ttext = EC.resolve(agent, MAIN_CODEX, EC.TEAM_TEXT, probes)
        self.assertEqual((ttext["status"], ttext["reason_code"], ttext["retryable"]),
                         ("blocked", EC.CAPABILITY_UNSUPPORTED, False))
        self.assertTrue(ttext["fix_hint"])

    def test_inherited_antigravity_from_main(self):
        probes = make_probes(catalogs={EC.ANTIGRAVITY: {"default": ["gemini-pro-orchestrator"]}})
        agent = {"model_provider": "", "model": ""}

        r_text = EC.resolve(agent, MAIN_AGY, EC.TEAM_TEXT, probes)
        self.assertEqual((r_text["provider"], r_text["model"], r_text["source"]),
                         (EC.ANTIGRAVITY, "gemini-pro-orchestrator", "main"))
        self.assertEqual((r_text["status"], r_text["reason_code"], r_text["retryable"]),
                         ("blocked", EC.CAPABILITY_UNSUPPORTED, False))

        r_full = EC.resolve(agent, MAIN_AGY, EC.TEAM_TOOL_FULL, probes)
        self.assertEqual((r_full["source"], r_full["status"]), ("main", "ready"))

    def test_codex_eric_like_does_not_regress(self):
        probes = make_probes(catalogs={EC.CODEX: {"remote": ["gpt-6-astra"]}})
        agent = {"model_provider": EC.CODEX, "model": "gpt-6-astra"}
        for mode in EC.MODES:
            with self.subTest(mode=mode):
                res = EC.resolve(agent, MAIN_AGY, mode, probes)
                self.assertEqual((res["provider"], res["model"], res["source"], res["status"]),
                                 (EC.CODEX, "gpt-6-astra", "agent", "ready"))

        # Machine gate unavailable (e.g. JAVIS_CODEX_SANDBOX=off): text & full still ready; gated blocked;
        # team_status gives warning + refuse=False (owner setting, never suggests sandbox-off)
        no_gate_probes = make_probes(gate_ok=(EC.CLAUDE,) + EC.API_PROVIDERS,
                                     catalogs={EC.CODEX: {"remote": ["gpt-6-astra"]}})
        self.assertEqual(EC.resolve(agent, MAIN_AGY, EC.TEAM_TEXT, no_gate_probes)["status"], "ready")
        self.assertEqual(EC.resolve(agent, MAIN_AGY, EC.TEAM_TOOL_FULL, no_gate_probes)["status"], "ready")
        gated = EC.resolve(agent, MAIN_AGY, EC.TEAM_TOOL_GATED, no_gate_probes)
        self.assertEqual((gated["status"], gated["reason_code"], gated["retryable"]),
                         ("blocked", EC.CAPABILITY_UNSUPPORTED, False))
        ts_codex = EC.team_status(
            [{"agent_key": "eric", "name": "Eric", "model_provider": EC.CODEX, "model": "gpt-6-astra"}],
            "eric", "gated", MAIN_AGY, no_gate_probes,
        )
        self.assertEqual((ts_codex["status"], ts_codex["refuse"]), ("warning", False))
        self.assertEqual(ts_codex["members"][0]["issues"][0]["severity"], "warning")
        self.assertIn("machine_reason", ts_codex["members"][0]["issues"][0])

    def test_api_providers_compat_and_manual_only_evidence(self):
        for prov in ("anthropic-compat", "openai-compat"):
            with self.subTest(provider=prov):
                probes_live = make_probes(catalogs={prov: {"remote": ["model-x"]}})
                for mode in EC.MODES:
                    r = EC.resolve({"model_provider": prov, "model": "model-x"}, MAIN_AGY, mode, probes_live)
                    self.assertEqual(r["status"], "ready")

                # Empty model on API provider -> model_invalid
                r_empty = EC.resolve({"model_provider": prov, "model": ""}, MAIN_AGY, EC.TEAM_TEXT, probes_live)
                self.assertEqual((r_empty["status"], r_empty["reason_code"], r_empty["retryable"]),
                                 ("blocked", EC.MODEL_INVALID, False))

                # Manual-only compat gateway -> unverified warning on member_status
                probes_manual = make_probes(catalogs={prov: {"manual": ["custom-model"], "remote": ["other"]}})
                r_man = EC.resolve({"model_provider": prov, "model": "custom-model"}, MAIN_AGY, EC.TEAM_TEXT, probes_manual)
                self.assertEqual((r_man["status"], r_man["reason_code"], r_man["evidence"]["model"]["sources"]),
                                 ("unverified", EC.MODEL_UNVERIFIED, ["manual"]))
                ts = EC.team_status(
                    [{"agent_key": "a1", "name": "A1", "model_provider": prov, "model": "custom-model"}],
                    "a1", "gated", MAIN_AGY, probes_manual,
                )
                self.assertEqual((ts["status"], ts["refuse"]), ("warning", False))

    def test_unknown_provider_never_reinterpreted_or_swapped(self):
        probes = make_probes(legacy_map={"gpt-6-astra": EC.CODEX})
        agent = {"model_provider": "made-up-provider", "model": "gpt-6-astra"}
        for mode in EC.MODES:
            r = EC.resolve(agent, MAIN_CODEX, mode, probes)
            self.assertEqual((r["provider"], r["source"], r["status"], r["reason_code"], r["retryable"]),
                             ("made-up-provider", "agent", "blocked", EC.PROVIDER_UNKNOWN, False))

    def test_legacy_model_only_resolved_without_fallback(self):
        probes = make_probes(legacy_map={"legacy-claude": EC.CLAUDE},
                             unavailable=(EC.CLAUDE,))
        r = EC.resolve({"model_provider": "", "model": "legacy-claude"}, MAIN_CODEX, EC.TEAM_TEXT, probes)
        self.assertEqual((r["provider"], r["model"], r["source"], r["status"], r["reason_code"], r["retryable"]),
                         (EC.CLAUDE, "legacy-claude", "legacy", "blocked", EC.AUTH_MISSING, False))

        # Unmapped legacy model -> provider_unknown
        r_unk = EC.resolve({"model_provider": "", "model": "mystery-model"}, MAIN_CODEX, EC.TEAM_TEXT, probes)
        self.assertEqual((r_unk["source"], r_unk["status"], r_unk["reason_code"]),
                         ("legacy", "blocked", EC.PROVIDER_UNKNOWN))

    def test_missing_auth_blocks_without_main_fallback(self):
        probes = make_probes(unavailable=(EC.CODEX,), catalogs={EC.CODEX: {"remote": ["gpt-6-astra"]}})
        r = EC.resolve({"model_provider": EC.CODEX, "model": "gpt-6-astra"}, MAIN_AGY, EC.TEAM_TEXT, probes)
        self.assertEqual((r["provider"], r["status"], r["reason_code"], r["retryable"]),
                         (EC.CODEX, "blocked", EC.AUTH_MISSING, False))

        # team_status flags auth_missing as blocked, but refuse=False (owner can still create & sign in later)
        ts = EC.team_status(
            [{"agent_key": "eric", "name": "Eric", "model_provider": EC.CODEX, "model": "gpt-6-astra"}],
            "eric", "gated", MAIN_AGY, probes,
        )
        self.assertEqual((ts["status"], ts["refuse"]), ("blocked", False))
        self.assertEqual(ts["members"][0]["issues"][0]["reason_code"], EC.AUTH_MISSING)

    def test_invalid_model_and_validation(self):
        probes = make_probes(catalogs={EC.CODEX: {"remote": ["gpt-6-astra"]}})
        # Save-time validator rejects bad shapes, unknown provider, model-without-provider
        v_bad_shape = EC.validate_agent_selection(EC.CODEX, "bad model\nname", probes)
        self.assertEqual((v_bad_shape["ok"], v_bad_shape["reason_code"], v_bad_shape["retryable"]),
                         (False, EC.MODEL_INVALID, False))
        v_no_prov = EC.validate_agent_selection("", "gpt-6-astra", probes)
        self.assertEqual((v_no_prov["ok"], v_no_prov["reason_code"]), (False, EC.PROVIDER_UNKNOWN))
        v_unk_prov = EC.validate_agent_selection("unknown-prov", "gpt-6-astra", probes)
        self.assertEqual((v_unk_prov["ok"], v_unk_prov["reason_code"]), (False, EC.PROVIDER_UNKNOWN))
        v_empty = EC.validate_agent_selection(EC.CODEX, "", probes)
        self.assertEqual((v_empty["ok"], v_empty["provider"], v_empty["model"]), (True, "", ""))

        # Unlisted model on non-manual-only provider -> unverified (info only, no team warning)
        r_unlisted = EC.resolve({"model_provider": EC.CODEX, "model": "gpt-unlisted"}, MAIN_AGY, EC.TEAM_TEXT, probes)
        self.assertEqual((r_unlisted["status"], r_unlisted["reason_code"]), ("unverified", EC.MODEL_UNVERIFIED))
        ts = EC.team_status(
            [{"agent_key": "e1", "name": "E1", "model_provider": EC.CODEX, "model": "gpt-unlisted"}],
            "e1", "gated", MAIN_AGY, probes,
        )
        self.assertEqual((ts["status"], ts["members"][0]["issues"]), ("ready", []))

    def test_same_model_name_on_two_providers_never_merged(self):
        shared = "shared-model-v1"
        probes = make_probes(catalogs={
            "openai-compat": {"remote": [shared]},
            "anthropic-compat": {"remote": ["completely-different"]},
            EC.CODEX: {"remote": [shared]},
            EC.ANTIGRAVITY: {"default": ["gemini-4-hydrogen-high"]},
        })

        r_oa = EC.resolve({"model_provider": "openai-compat", "model": shared}, MAIN_AGY, EC.TEAM_TEXT, probes)
        r_ac = EC.resolve({"model_provider": "anthropic-compat", "model": shared}, MAIN_AGY, EC.TEAM_TEXT, probes)
        self.assertEqual((r_oa["status"], r_oa["evidence"]["model"]),
                         ("ready", {"known": True, "sources": ["remote"]}))
        self.assertEqual((r_ac["status"], r_ac["reason_code"], r_ac["evidence"]["model"]),
                         ("unverified", EC.MODEL_UNVERIFIED, {"known": False, "sources": []}))

        # last_call outcome is keyed by (provider, model), never shared across providers
        EC.record_outcome("openai-compat", shared, False, EC.NETWORK)
        r_oa_after = EC.resolve({"model_provider": "openai-compat", "model": shared}, MAIN_AGY, EC.TEAM_TEXT, probes)
        r_ac_after = EC.resolve({"model_provider": "anthropic-compat", "model": shared}, MAIN_AGY, EC.TEAM_TEXT, probes)
        self.assertEqual(r_oa_after["evidence"]["last_call"]["code"], EC.NETWORK)
        self.assertIsNone(r_ac_after["evidence"]["last_call"])

    def test_reason_codes_aliases_and_runtime_classification(self):
        for code in (EC.CAPABILITY_UNSUPPORTED, EC.AUTH_MISSING, EC.MODEL_INVALID, EC.PROVIDER_UNKNOWN, EC.BUILD_FAILED):
            r = EC.reason(code, EC.ANTIGRAVITY, EC.TEAM_TEXT)
            self.assertFalse(r["retryable"], code)
            self.assertTrue(r["message"], code)
            self.assertTrue(r["fix_hint"], code)
        for code in (EC.QUOTA_OR_RATE_LIMIT, EC.NETWORK):
            r = EC.reason(code, EC.CODEX, EC.TEAM_TEXT)
            self.assertTrue(r["retryable"], code)

        self.assertEqual(EC.normalize_code("invalid_provider"), EC.PROVIDER_UNKNOWN)
        self.assertEqual(EC.normalize_code("provider_required"), EC.PROVIDER_UNKNOWN)
        self.assertEqual(EC.normalize_code("provider_not_ready"), EC.AUTH_MISSING)
        self.assertEqual(EC.normalize_code("engine_unavailable"), EC.BUILD_FAILED)
        self.assertEqual(EC.normalize_code("engine_build_failed"), EC.BUILD_FAILED)

        self.assertEqual(EC.classify_runtime_error("HTTP 429 rate limit exceeded"), EC.QUOTA_OR_RATE_LIMIT)
        self.assertEqual(EC.classify_runtime_error("401 unauthorized: invalid api key"), EC.AUTH_MISSING)
        self.assertEqual(EC.classify_runtime_error("model_not_found: bad-id"), EC.MODEL_INVALID)
        self.assertEqual(EC.classify_runtime_error("ConnectError: timed out"), EC.NETWORK)
        self.assertEqual(EC.classify_runtime_error("weird crash", stage="preflight"), EC.BUILD_FAILED)

    def test_main_change_impact_only_hits_inherited_agents_and_teams(self):
        probes = make_probes(catalogs={
            EC.CODEX: {"remote": ["gpt-6-astra"]},
            EC.ANTIGRAVITY: {"default": ["gemini-pro-orchestrator", "claude-opus-5-5-high"]},
        })
        agents = [
            {"key": "k_it", "name": "IT Dev", "model_provider": "", "model": ""},
            {"key": "k_eric", "name": "Eric", "model_provider": EC.CODEX, "model": "gpt-6-astra"},
        ]
        teams = [
            {"team_id": "tm_it", "name": "IT - Javis", "leader_key": "k_it", "work_mode": "gated",
             "members": [{"agent_key": "k_it", "name": "IT Dev", "model_provider": "", "model": ""}]},
            {"team_id": "tm_codex", "name": "Codex Team", "leader_key": "k_eric", "work_mode": "gated",
             "members": [{"agent_key": "k_eric", "name": "Eric", "model_provider": EC.CODEX, "model": "gpt-6-astra"}]},
        ]
        imp = EC.main_change_impact(agents, teams, MAIN_CODEX, MAIN_AGY, probes)
        self.assertEqual([a["key"] for a in imp["agents"]], ["k_it"])
        self.assertEqual(imp["agents"][0]["team_text_after"], {"ok": False, "reason_code": EC.CAPABILITY_UNSUPPORTED})
        self.assertEqual([t["team_id"] for t in imp["teams"]], ["tm_it"])
        self.assertEqual((imp["teams"][0]["before"], imp["teams"][0]["after"]), ("ready", "blocked"))
        self.assertGreaterEqual(imp["blocking"], 1)


class RuntimeMatrixTests(unittest.TestCase):
    def _world(self, name, engine_for, *, work_mode="gated", agents=None):
        d = TEMP_ROOT / name
        d.mkdir(parents=True, exist_ok=True)
        ss = sessions.SessionStore(db_path=d / "sessions.db")
        ts = task_store.TaskStore(d / "kanban.sqlite3")
        tm = team_store.TeamStore(d / "team.sqlite3")
        agent_map = agents or {
            "ag_eric": {"slug": "eric", "name": "Eric", "system": "Codex agent",
                        "model_provider": EC.CODEX, "model": "gpt-6-astra"},
            "ag_naval": {"slug": "naval", "name": "Naval", "system": "Antigravity agent",
                         "model_provider": EC.ANTIGRAVITY, "model": "claude-opus-5-5-high"},
        }
        runner = TR.TeamRunner(
            teams=tm, tasks=ts, sessions=ss,
            engine_for=engine_for,
            agent_info=lambda brain, key: agent_map.get(key),
        )
        tid = team_store.new_team_id()
        sid = ss.create_session(brain="B", channel=f"team:{tid}", title=name)
        tm.create_team("B", name, "", sid, team_id=tid)
        if work_mode:
            tm.set_work_mode(tid, work_mode)
        for k, info in agent_map.items():
            tm.add_member(tid, k, info["slug"])
        tm.set_leader(tid, next(iter(agent_map)))
        return d, ss, ts, tm, runner, tm.get(tid), agent_map

    def test_text_only_blocks_tool_side_effects_and_blocks_antigravity_preflight(self):
        side_effect_file = TEMP_ROOT / "should_not_exist.txt"
        calls = []

        def engine_for(team, agent_key, role):
            async def run(req):
                if agent_key == "ag_naval":
                    raise TR.EngineUnavailable("antigravity-cli unsupported for team_text",
                                               code=EC.CAPABILITY_UNSUPPORTED, stage="capability")
                await req["engine_started"]()
                calls.append((agent_key, role))
                if agent_key == "ag_rogue":
                    # Simulate an engine trying to emit a tool call during a text-only turn
                    o = TR.TextOnlyOutcome()
                    o.note({"type": "tool_call", "name": "Write", "input": {"file_path": str(side_effect_file)}})
                    o.note({"type": "final", "content": "Tried tool"})
                    return o.result()
                return {"text": "Codex text reply ok", "tokens_in": 5, "tokens_out": 3}

            run.marks_engine = True
            prov = EC.ANTIGRAVITY if agent_key == "ag_naval" else EC.CODEX
            mod = "claude-opus-5-5-high" if agent_key == "ag_naval" else "gpt-6-astra"
            return prov, mod, run

        agents = {
            "ag_eric": {"slug": "eric", "name": "Eric", "system": "S", "model_provider": EC.CODEX, "model": "gpt-6-astra"},
            "ag_naval": {"slug": "naval", "name": "Naval", "system": "S", "model_provider": EC.ANTIGRAVITY, "model": "claude-opus-5-5-high"},
            "ag_rogue": {"slug": "rogue", "name": "Rogue", "system": "S", "model_provider": EC.CODEX, "model": "gpt-6-astra"},
        }
        _, ss, _, tm, runner, team, _ = self._world("text-only", engine_for, agents=agents)

        # 1) Codex text-only reply succeeds
        sub_ok = runner.submit(team["team_id"], "Hello", mentions=["ag_eric"], as_job=False, client_msg_id="m-eric")
        run_async(runner.run_message(sub_ok))
        rep_ok = tm.replies_for(team["team_id"], [sub_ok["message_id"]])[sub_ok["message_id"]][0]
        self.assertEqual(rep_ok["status"], "done")

        # 2) Antigravity text-only reply fails at preflight with capability_unsupported, engine not called
        sub_agy = runner.submit(team["team_id"], "Hello", mentions=["ag_naval"], as_job=False, client_msg_id="m-naval")
        run_async(runner.run_message(sub_agy))
        rep_agy = tm.replies_for(team["team_id"], [sub_agy["message_id"]])[sub_agy["message_id"]][0]
        self.assertEqual((rep_agy["status"], rep_agy["reason"]), ("error", EC.CAPABILITY_UNSUPPORTED))
        self.assertNotIn(("ag_naval", "member_reply"), calls)

        # 3) TextOnlyOutcome rejects any tool_call event and produces zero side effects
        sub_rogue = runner.submit(team["team_id"], "Write file", mentions=["ag_rogue"], as_job=False, client_msg_id="m-rogue")
        run_async(runner.run_message(sub_rogue))
        rep_rogue = tm.replies_for(team["team_id"], [sub_rogue["message_id"]])[sub_rogue["message_id"]][0]
        self.assertEqual(rep_rogue["status"], "error")
        self.assertFalse(side_effect_file.exists())

    def test_team_engine_build_disables_tools_for_text_only(self):
        base = SimpleNamespace(system_prompt="sys", cwd=None, javis_vault=None, allowed_tools=["none"])
        with patch.object(aux_engine, "availability", return_value=(True, "")):
            codex_eng = team_engine.build({"provider": EC.CODEX, "model": "gpt-6-astra"}, base, "tag", {})
            self.assertEqual(codex_eng.sandbox, "read-only")
            self.assertFalse(codex_eng.hub_turn)
            self.assertIn("mcp_servers={}", codex_eng.extra_config)

            api_eng = team_engine.build({"provider": "openai-compat", "model": "m1"}, base, "tag", {})
            self.assertTrue(api_eng.no_tools)

            with self.assertRaises(team_engine.TeamEngineUnavailable) as ctx:
                team_engine.build({"provider": EC.ANTIGRAVITY, "model": "gemini-4-hydrogen-high"}, base, "tag", {})
            self.assertEqual((ctx.exception.code, ctx.exception.retryable), (EC.CAPABILITY_UNSUPPORTED, False))

    def test_planning_and_tool_turns_and_gated_approval_required(self):
        seen_roles = []

        def engine_for(team, agent_key, role):
            async def run(req):
                if agent_key == "ag_naval" and EC.mode_for(role, team.get("work_mode")) in (EC.TEAM_TEXT, EC.TEAM_TOOL_GATED):
                    raise TR.EngineUnavailable("unsupported", code=EC.CAPABILITY_UNSUPPORTED, stage="capability")
                seen_roles.append((agent_key, role))
                if role == "plan":
                    return {"text": '<!-- JAVIS_TEAM: {"op":"plan","steps":[{"agent":"ag_eric","brief":"Do work"}]} -->',
                            "tokens_in": 5, "tokens_out": 5}
                return {"text": "Work finished", "tokens_in": 5, "tokens_out": 5}

            return EC.CODEX, "gpt-6-astra", run

        # Planning + gated work on Codex
        _, ss, ts, tm, runner, team, _ = self._world("plan-and-gated", engine_for, work_mode="gated")
        runner.submit(team["team_id"], "Plan and execute", as_job=True, client_msg_id="job-1")
        run_async(runner.dispatch_once(wait=True))
        self.assertIn(("ag_eric", "plan"), seen_roles)

        # Tool turn in full mode allows Antigravity
        self.assertTrue(team_engine.tools_supported(EC.ANTIGRAVITY))
        base = SimpleNamespace(system_prompt="sys", cwd=None, javis_vault=None, allowed_tools=["Read"])
        with patch.object(aux_engine, "availability", return_value=(True, "")), \
                patch.object(aux_engine, "build_antigravity", return_value=SimpleNamespace(provider=EC.ANTIGRAVITY), create=True) if hasattr(aux_engine, "build_antigravity") else patch.object(team_engine, "tools_supported", return_value=True):
            # Verify mode_for maps work -> team_tool_full when work_mode='full'
            self.assertEqual(EC.mode_for("work", "full"), EC.TEAM_TOOL_FULL)
            self.assertEqual(EC.mode_for("work", "gated"), EC.TEAM_TOOL_GATED)
            self.assertEqual(EC.mode_for("plan", "full"), EC.TEAM_TEXT)

        # Prove gated turn STILL requires approval for outside actions via team_gate
        d_gate = TEMP_ROOT / "gate-approval-proof"
        d_gate.mkdir(parents=True, exist_ok=True)
        ap_store = team_approval.ApprovalStore(d_gate / "approvals.sqlite3")
        g = team_gate.open_gate(ap_store, "tm_gate", "t_gate", "st_gate")
        g.roots = [d_gate]
        try:
            # Outside write/shell command must be refused and record an approval request
            allowed, note = team_gate.native_check(g.gate_id, "Bash", {"command": "rm -rf /tmp/some-outside-target"})
            self.assertFalse(allowed)
            self.assertIn("duyệt", note)
            self.assertTrue(g.blocked)
            # While inside read-only ls is free
            free_ok, _ = team_gate.native_check(g.gate_id, "Bash", {"command": "ls"})
            self.assertTrue(free_ok)
        finally:
            team_gate.close_gate(g.gate_id)

    def test_config_errors_never_auto_retried_and_manual_retry_uses_current_config(self):
        # Mutable agent provider to simulate owner fixing config before manual retry
        state = {"provider": EC.ANTIGRAVITY}
        calls = []

        def engine_for(team, agent_key, role):
            async def run(req):
                if state["provider"] == EC.ANTIGRAVITY:
                    raise TR.EngineUnavailable("antigravity unsupported", code=EC.CAPABILITY_UNSUPPORTED, stage="capability")
                await req["engine_started"]()
                calls.append(agent_key)
                return {"text": "Fixed and replied", "tokens_in": 4, "tokens_out": 2}

            run.marks_engine = True
            return state["provider"], "gpt-6-astra", run

        _, _, _, tm, runner, team, _ = self._world("retry-cfg", engine_for)
        sub = runner.submit(team["team_id"], "Ping", mentions=["ag_naval"], as_job=False, client_msg_id="m-ret")
        run_async(runner.run_message(sub))

        rep1 = tm.replies_for(team["team_id"], [sub["message_id"]])[sub["message_id"]][0]
        self.assertEqual((rep1["status"], rep1["reason"], rep1["attempt"]), ("error", EC.CAPABILITY_UNSUPPORTED, 1))
        self.assertEqual(calls, [])

        # Manual retry WITHOUT fixing config returns the same coded error and still does not call engine
        ret1 = runner.retry_reply(team["team_id"], sub["message_id"], "ag_naval")
        run_async(runner.run_replies(ret1))
        rep2 = tm.replies_for(team["team_id"], [sub["message_id"]])[sub["message_id"]][0]
        self.assertEqual((rep2["status"], rep2["reason"], rep2["attempt"]), ("error", EC.CAPABILITY_UNSUPPORTED, 2))
        self.assertEqual(calls, [])

        # Fix config -> manual retry re-runs preflight on CURRENT config and succeeds
        state["provider"] = EC.CODEX
        ret2 = runner.retry_reply(team["team_id"], sub["message_id"], "ag_naval")
        run_async(runner.run_replies(ret2))
        rep3 = tm.replies_for(team["team_id"], [sub["message_id"]])[sub["message_id"]][0]
        self.assertEqual((rep3["status"], rep3["attempt"]), ("done", 3))
        self.assertEqual(calls, ["ag_naval"])

    def test_restart_persistence_resumes_in_same_mode(self):
        d = TEMP_ROOT / "restart-persist"
        d.mkdir(parents=True, exist_ok=True)
        ss1 = sessions.SessionStore(db_path=d / "sessions.db")
        ts1 = task_store.TaskStore(d / "kanban.sqlite3")
        tm1 = team_store.TeamStore(d / "team.sqlite3")
        agents = {"ag_eric": {"slug": "eric", "name": "Eric", "system": "S",
                              "model_provider": EC.CODEX, "model": "gpt-6-astra"}}

        def eng_ok(team, key, role):
            async def run(req):
                return {"text": f"{role} resumed ok", "tokens_in": 3, "tokens_out": 2}
            return EC.CODEX, "gpt-6-astra", run

        r1 = TR.TeamRunner(teams=tm1, tasks=ts1, sessions=ss1, engine_for=eng_ok,
                           agent_info=lambda b, k: agents.get(k))
        tid = team_store.new_team_id()
        sid = ss1.create_session(brain="B", channel=f"team:{tid}", title="Restart")
        tm1.create_team("B", "Restart", "", sid, team_id=tid)
        tm1.set_work_mode(tid, "gated")
        tm1.add_member(tid, "ag_eric", "eric")
        tm1.set_leader(tid, "ag_eric")
        j = r1.submit(tid, "Work task", mentions=["ag_eric"], as_job=True, client_msg_id="job-rst")
        ts1.claim_team_next(tid, "old-worker")
        r1.start_job_steps(j["task_id"])
        st = tm1.next_queued_step(j["task_id"])
        tm1.claim_step(st["step_id"])
        tu = tm1.reserve_turn(tid, j["task_id"], st["step_id"], "ag_eric", st["kind"])
        tm1.mark_engine(tu, EC.CODEX, "gpt-6-astra")
        orig_kind = st["kind"]

        # Simulate process restart with fresh store instances
        ss2 = sessions.SessionStore(db_path=d / "sessions.db")
        ts2 = task_store.TaskStore(d / "kanban.sqlite3")
        tm2 = team_store.TeamStore(d / "team.sqlite3")
        r2 = TR.TeamRunner(teams=tm2, tasks=ts2, sessions=ss2, engine_for=eng_ok,
                           agent_info=lambda b, k: agents.get(k))
        rep = r2.recover()
        self.assertIn(j["task_id"], rep["resumed"])
        queued = [s for s in tm2.steps(j["task_id"]) if s["status"] == "queued"]
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0]["kind"], orig_kind)
        self.assertEqual(EC.mode_for(queued[0]["kind"], tm2.get(tid)["work_mode"]),
                         EC.mode_for(orig_kind, "gated"))


if __name__ == "__main__":
    unittest.main()
