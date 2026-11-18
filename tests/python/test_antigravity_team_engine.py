"""Offline tests for Antigravity CLI across Team text, gated tool, full tool, and X-Javis-Turn isolation.

    python tests/python/test_antigravity_team_engine.py
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

TEMP_ROOT = Path(tempfile.mkdtemp(prefix="javis-agy-team-"))
STATE_DIR = TEMP_ROOT / "state"
HOME_DIR = TEMP_ROOT / "home"
VAULT_DIR = TEMP_ROOT / "vault"
for _d in (STATE_DIR, HOME_DIR / ".gemini" / "config", HOME_DIR / ".gemini" / "antigravity-cli",
           HOME_DIR / ".agents", VAULT_DIR / "teams" / "tm_agy"):
    _d.mkdir(parents=True, exist_ok=True)

(HOME_DIR / ".gemini" / "antigravity-cli" / "antigravity-oauth-token").write_text("oauth-token-main", encoding="utf-8")
(HOME_DIR / ".gemini" / "config" / "mcp_config.json").write_text(
    json.dumps({"mcpServers": {"user_custom": {"url": "http://127.0.0.1:9999/user"}}}),
    encoding="utf-8",
)
(HOME_DIR / ".gemini" / "config" / "hooks.json").write_text(
    json.dumps({"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "true"}]}]}}),
    encoding="utf-8",
)
(HOME_DIR / ".agents" / "hooks.json").write_text("{}", encoding="utf-8")

os.environ["JAVIS_STATE_DIR"] = str(STATE_DIR)
os.environ["HOME"] = str(HOME_DIR)
os.environ["BRAIN_PATH"] = str(VAULT_DIR)
os.environ["BRAINS_DIR"] = str(TEMP_ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from fastapi.testclient import TestClient  # noqa: E402
import antigravity_cli  # noqa: E402
import aux_engine  # noqa: E402
import main  # noqa: E402
import mcp_hub  # noqa: E402
import team_approval  # noqa: E402
import team_engine  # noqa: E402
import team_gate  # noqa: E402
import turn_context  # noqa: E402


def tearDownModule():
    shutil.rmtree(TEMP_ROOT, ignore_errors=True)


class _FakePopen:
    def __init__(self, args, stdout_lines, inspect_cb=None, cwd=None, env=None, exit_code=0):
        self.args = list(args)
        self.cwd = cwd
        self.env = dict(env or os.environ)
        self.exit_code = exit_code
        self.pid = 424242
        self._stdin_buf = []
        self._lines = list(stdout_lines)
        self._idx = 0
        if inspect_cb is not None:
            inspect_cb(self)
        self.stdin = SimpleNamespace(
            write=lambda s: self._stdin_buf.append(s),
            flush=lambda: None,
            close=lambda: None,
        )
        self.stdout = self
        self.stderr = SimpleNamespace(readline=lambda: "", read=lambda: "", close=lambda: None)

    def readline(self):
        if self._idx < len(self._lines):
            line = self._lines[self._idx]
            self._idx += 1
            return line + "\n"
        return ""

    def poll(self):
        return self.exit_code

    def wait(self, timeout=None):
        return self.exit_code

    def terminate(self):
        pass

    def kill(self):
        pass


class AntigravityTeamEngineTests(unittest.TestCase):
    def setUp(self):
        antigravity_cli._HELP_CACHE.update(
            path="/fake/agy",
            text=(
                "--model --output-format --conversation --add-dir --settings "
                "--disable-slash-commands --dangerously-skip-permissions --sandbox --print-timeout"
            ),
            ts=9999999999.0,
        )

    def tearDown(self):
        antigravity_cli._HELP_CACHE.update(path="", text="", ts=0.0)

    def test_text_only_build_flags_and_isolated_turn_cleanup(self):
        base = SimpleNamespace(system_prompt="Team leader system prompt", cwd=str(VAULT_DIR), mode="suggest")
        with patch.object(aux_engine, "availability", return_value=(True, "")), \
                patch.object(antigravity_cli, "find_antigravity_cli", return_value="/fake/agy"), \
                patch.object(antigravity_cli, "hooks_supported", return_value=True):
            self.assertTrue(team_engine.text_only_supported(aux_engine.ANTIGRAVITY))
            ac = team_engine.build({"provider": aux_engine.ANTIGRAVITY, "model": "gemini-3.8-flash-low"}, base, "t-txt", {})

        self.assertTrue(ac.text_only)
        self.assertFalse(ac.hub_turn)
        self.assertIsNone(ac.mcp_config)
        self.assertIsNone(ac.team_gate)
        self.assertEqual(ac.include_dirs, [])

        with patch.object(aux_engine, "availability", return_value=(True, "")), \
                patch.object(antigravity_cli, "hooks_supported", return_value=False):
            self.assertFalse(team_engine.text_only_supported(aux_engine.ANTIGRAVITY))
            with self.assertRaises(team_engine.TeamEngineUnavailable):
                team_engine.build({"provider": aux_engine.ANTIGRAVITY, "model": "gemini-3.8-flash-low"}, base, "t-txt", {})

        with patch.object(antigravity_cli, "find_antigravity_cli", return_value="/fake/agy"), \
                patch.dict(os.environ, {"JAVIS_AGY_PROMPT_DAI": "file"}):
            self.assertEqual(ac._chon_duong("x" * 200000), "stdin:trong")

        captured = {}

        def _inspect(proc):
            h = Path(proc.env["HOME"])
            c = Path(proc.cwd)
            captured["args"] = list(proc.args)
            captured["cwd"] = c
            captured["home"] = h
            captured["cwd_hook"] = json.loads((c / ".agents" / "hooks.json").read_text(encoding="utf-8"))
            captured["home_mcp"] = json.loads((h / ".gemini" / "config" / "mcp_config.json").read_text(encoding="utf-8"))
            captured["home_hook"] = json.loads((h / ".gemini" / "config" / "hooks.json").read_text(encoding="utf-8"))
            captured["oauth_ok"] = (h / ".gemini" / "antigravity-cli" / "antigravity-oauth-token").read_text(encoding="utf-8")
            captured["agents_omitted"] = not (h / ".agents").exists()

        lines = [
            json.dumps({"event": "step_update", "step_update": {"step_type": "tool", "step_index": 1, "state": "ACTIVE",
                                                                 "tool_name": "read_file",
                                                                 "tool_info": {"name": "read_file", "parameters": {"Path": "/etc/passwd"}}}}),
            json.dumps({"event": "step_update", "step_update": {"step_type": "tool", "step_index": 1, "state": "ERROR",
                                                                 "tool_name": "read_file",
                                                                 "tool_info": {"error": {"message": "tool call denied by pre-tool hook"}}}}),
            json.dumps({"event": "result", "result": {"status": "SUCCESS", "response": "Pure text reply"}}),
        ]

        async def run_turn():
            with patch.dict(os.environ, {"JAVIS_AGY_PER_TURN_HOME": "1", "JAVIS_AGY_HOOKS": "1"}), \
                    patch.object(antigravity_cli, "find_antigravity_cli", return_value="/fake/agy"), \
                    patch.object(antigravity_cli.subprocess, "Popen",
                                 side_effect=lambda args, **kw: _FakePopen(args, lines, _inspect, cwd=kw.get("cwd"), env=kw.get("env"))):
                ac.cli_path = "/fake/agy"
                return [ev async for ev in ac.query("Hello team")]

        events = asyncio.run(run_turn())
        self.assertFalse(any(e.get("type") == "tool_call" for e in events), events)
        final_evs = [e for e in events if e.get("type") in ("final", "text")]
        self.assertTrue(final_evs, events)
        self.assertEqual(final_evs[-1]["content"], "Pure text reply")
        self.assertIn("--disable-slash-commands", captured["args"])
        self.assertIn("--settings", captured["args"])
        settings_val = json.loads(captured["args"][captured["args"].index("--settings") + 1])
        self.assertEqual(settings_val, {"permissions": {"deny": ["*", "mcp(*)"]}})
        self.assertNotIn("--add-dir", captured["args"])
        self.assertEqual(captured["home_mcp"], {"mcpServers": {}})
        self.assertEqual(captured["oauth_ok"], "oauth-token-main")
        self.assertTrue(captured["agents_omitted"])
        self.assertNotEqual(captured["cwd"], VAULT_DIR)
        self.assertFalse(captured["cwd"].exists())
        self.assertFalse(captured["home"].exists())

        # If a tool somehow completes (DONE) in text_only, _doi_su_kien still emits tool_call fail-closed.
        breach = ac._doi_su_kien({"step_type": "tool", "step_index": 2, "state": "DONE", "tool_name": "run_command",
                                    "tool_info": {"parameters": {"CommandLine": "id"}}}, [], {})
        self.assertTrue(any(e.get("type") == "tool_call" for e in breach))

    def test_per_turn_home_x_javis_turn_and_turn_context_isolation(self):
        with patch.object(antigravity_cli, "find_antigravity_cli", return_value="/fake/agy"):
            ac = antigravity_cli.AntigravityCLI(cwd=str(VAULT_DIR), tag="owner-chat", model="gemini-4-argon-high")
        ac.mode = "full"
        ac.hub_turn = True
        ac.hub_url = mcp_hub.hub_url()
        ac.hub_headers = {"Authorization": f"Bearer {mcp_hub.hub_token()}", "X-Javis-Mode": "full",
                          "X-Javis-Vault": str(VAULT_DIR)}

        captured = {}

        def _inspect(proc):
            h = Path(proc.env["HOME"])
            captured["force_file"] = proc.env.get("GEMINI_FORCE_FILE_STORAGE")
            captured["cfg_mcp"] = json.loads((h / ".gemini" / "config" / "mcp_config.json").read_text(encoding="utf-8"))
            captured["cli_mcp"] = json.loads((h / ".gemini" / "antigravity-cli" / "mcp_config.json").read_text(encoding="utf-8"))
            captured["turn_hdr"] = captured["cfg_mcp"]["mcpServers"]["javis"]["headers"].get(turn_context.HEADER)
            captured["resolved_during_run"] = turn_context.resolve_key(captured["turn_hdr"])

        lines = [json.dumps({"event": "result", "result": {"status": "SUCCESS", "response": "ok"}})]

        async def run_owner():
            tok = turn_context.bind(turn_context.make(kenh="dashboard", sender_id="owner", la_chu=True))
            try:
                with patch.dict(os.environ, {"JAVIS_AGY_PER_TURN_HOME": "1"}), \
                        patch.object(antigravity_cli, "find_antigravity_cli", return_value="/fake/agy"), \
                        patch.object(antigravity_cli.subprocess, "Popen",
                                     side_effect=lambda args, **kw: _FakePopen(args, lines, _inspect, cwd=kw.get("cwd"), env=kw.get("env"))):
                    return [ev async for ev in ac.query("check owner scope")]
            finally:
                turn_context.reset(tok)

        had_force_before = "GEMINI_FORCE_FILE_STORAGE" in os.environ
        events = asyncio.run(run_owner())
        self.assertEqual(events[-1]["content"], "ok")
        self.assertTrue(captured["turn_hdr"])
        self.assertTrue(captured["resolved_during_run"]["la_chu"])
        self.assertEqual(captured["resolved_during_run"]["kenh"], "dashboard")
        self.assertEqual(captured["cfg_mcp"], captured["cli_mcp"])
        # Shared user HOME mcp_config.json must stay untouched.
        shared = json.loads((HOME_DIR / ".gemini" / "config" / "mcp_config.json").read_text(encoding="utf-8"))
        self.assertNotIn("javis", shared.get("mcpServers", {}))
        if not had_force_before:
            self.assertIsNone(captured["force_file"])
        # Turn key expires immediately when turn_context resets.
        self.assertIsNone(turn_context.resolve_key(captured["turn_hdr"]))

        # Extra account HOME sets GEMINI_FORCE_FILE_STORAGE=true and symlinks that account's token.
        extra_home = TEMP_ROOT / "extra_agy"
        (extra_home / ".gemini" / "antigravity-cli").mkdir(parents=True, exist_ok=True)
        (extra_home / ".gemini" / "antigravity-cli" / "antigravity-oauth-token").write_text("oauth-token-2", encoding="utf-8")
        ac.agy_home = str(extra_home)
        captured_extra = {}

        def _inspect_extra(proc):
            h = Path(proc.env["HOME"])
            captured_extra["force_file"] = proc.env.get("GEMINI_FORCE_FILE_STORAGE")
            captured_extra["token"] = (h / ".gemini" / "antigravity-cli" / "antigravity-oauth-token").read_text(encoding="utf-8")

        async def run_extra():
            with patch.dict(os.environ, {"JAVIS_AGY_PER_TURN_HOME": "1"}), \
                    patch.object(antigravity_cli, "find_antigravity_cli", return_value="/fake/agy"), \
                    patch.object(antigravity_cli.subprocess, "Popen",
                                 side_effect=lambda args, **kw: _FakePopen(args, lines, _inspect_extra, cwd=kw.get("cwd"), env=kw.get("env"))):
                return [ev async for ev in ac.query("extra account")]

        asyncio.run(run_extra())
        self.assertEqual(captured_extra["force_file"], "true")
        self.assertEqual(captured_extra["token"], "oauth-token-2")

        # Team turn key resolves la_chu=False and team_gate, and invalidates on reset.
        tok_team = turn_context.bind(turn_context.make(kenh="team", sender_id="team:tm_1", team_gate="tg_team1"))
        try:
            key_team = turn_context.issue_key()
            resolved_team = turn_context.resolve_key(key_team)
            self.assertIsNotNone(resolved_team)
            self.assertFalse(resolved_team.get("la_chu"))
            self.assertEqual(resolved_team.get("team_gate"), "tg_team1")
        finally:
            turn_context.reset(tok_team)
        self.assertIsNone(turn_context.resolve_key(key_team))
        self.assertIsNone(turn_context.current())

    def test_team_gate_native_classify_and_hook_http_flow(self):
        self.assertFalse(team_gate.provider_support(aux_engine.ANTIGRAVITY)["ok"])
        self.assertTrue(team_gate.provider_support(aux_engine.ANTIGRAVITY, antigravity_gate=True)["ok"])

        roots = [str(VAULT_DIR)]
        self.assertEqual(team_gate.classify_native("read_file", {"Path": "/etc/hosts"}, roots), "free")
        self.assertEqual(team_gate.classify_native("write_to_file", {"TargetFile": str(VAULT_DIR / "notes.md")}, roots), "free")
        self.assertEqual(team_gate.classify_native("write_to_file", {"TargetFile": str(VAULT_DIR / ".antigravitycli" / "x")}, roots), "outside")
        self.assertEqual(team_gate.classify_native("write_to_file", {"TargetFile": "/tmp/outside.txt"}, roots), "outside")
        self.assertEqual(team_gate.classify_native("run_command", {"CommandLine": "git status"}, roots), "free")
        self.assertEqual(team_gate.classify_native("run_command", {"CommandLine": "rm -rf /tmp/x"}, roots), "outside")
        self.assertEqual(team_gate.classify_native("call_mcp_tool", {"ServerName": "javis", "ToolName": "send_email"}, roots), "free")
        self.assertEqual(team_gate.classify_native("call_mcp_tool", {"ServerName": "other", "ToolName": "delete_all"}, roots), "outside")

        # Live FastAPI /hub/team-gate + real agy_gate_hook.py subprocess bridge
        store = team_approval.ApprovalStore(TEMP_ROOT / "approvals.sqlite3")
        g = team_gate.open_gate(store, "tm_1", "task_1", "step_1")
        team_gate.set_roots(g.gate_id, roots)

        tok = turn_context.bind(turn_context.make(kenh="team", sender_id="team:tm_1", team_gate=g.gate_id))
        srv = None
        try:
            turn_key = turn_context.issue_key()

            client = TestClient(main.app, base_url="http://127.0.0.1:8080", client=("127.0.0.1", 50000))
            remote_client = TestClient(main.app, base_url="http://127.0.0.1:8080", client=("8.8.8.8", 50000))
            hdrs = {"Authorization": f"Bearer {mcp_hub.hub_token()}", turn_context.HEADER: turn_key}

            # Auth / locality / gate-binding guards
            self.assertEqual(client.post("/hub/team-gate", json={"gate_id": g.gate_id, "tool": "read_file", "input": {}},
                                         headers={"Authorization": "Bearer wrong"}).status_code, 401)
            self.assertEqual(remote_client.post("/hub/team-gate", json={"gate_id": g.gate_id, "tool": "read_file", "input": {}},
                                                headers=hdrs).status_code, 403)
            self.assertEqual(client.post("/hub/team-gate", json={"gate_id": g.gate_id, "tool": "read_file", "input": {}},
                                         headers={"Authorization": f"Bearer {mcp_hub.hub_token()}", "X-Forwarded-For": "8.8.8.8"}).status_code, 403)
            self.assertEqual(client.post("/hub/team-gate", json={"gate_id": "tg_wrong", "tool": "read_file", "input": {}},
                                         headers=hdrs).status_code, 403)

            class _BridgeHandler(BaseHTTPRequestHandler):
                def do_POST(self):
                    n = int(self.headers.get("Content-Length") or "0")
                    raw = self.rfile.read(n)
                    pass_hdrs = {"Content-Type": "application/json"}
                    for hk in ("Authorization", turn_context.HEADER):
                        if self.headers.get(hk):
                            pass_hdrs[hk] = self.headers.get(hk)
                    resp = client.post(self.path, content=raw, headers=pass_hdrs)
                    self.send_response(resp.status_code)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(resp.content)

                def log_message(self, *args):
                    pass

            srv = ThreadingHTTPServer(("127.0.0.1", 0), _BridgeHandler)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            url = f"http://127.0.0.1:{srv.server_port}/hub/team-gate"
            gate_cfg = TEMP_ROOT / "gate_cfg.json"
            gate_cfg.write_text(json.dumps({"url": url, "token": mcp_hub.hub_token(),
                                            "gate_id": g.gate_id, "turn_key": turn_key}), encoding="utf-8")
            hook_py = str(SERVER / "agy_gate_hook.py")

            def _run_hook(stdin_obj, arg_url=url, cfg=str(gate_cfg)):
                res = subprocess.run([sys.executable, hook_py, arg_url, cfg],
                                     input=json.dumps(stdin_obj), text=True, capture_output=True, timeout=15)
                self.assertEqual(res.returncode, 0, res.stderr)
                return json.loads(res.stdout.strip())

            # 1) Free read and in-scope write allowed
            r_free = _run_hook({"toolCall": {"name": "read_file", "args": {"Path": "/etc/hosts"}}})
            self.assertEqual(r_free.get("decision"), "allow", r_free)
            r_in = _run_hook({"toolCall": {"name": "write_to_file", "args": {"TargetFile": str(VAULT_DIR / "ok.md")}}})
            self.assertEqual(r_in.get("decision"), "allow", r_in)

            # 2) Outside shell denied fail-closed and recorded in gate.blocked
            r_deny = _run_hook({"toolCall": {"name": "run_command", "args": {"CommandLine": "rm -rf /tmp/nonexistent_x"}}})
            self.assertEqual(r_deny["decision"], "deny")
            self.assertEqual(len(g.blocked), 1)
            blocked = g.blocked[0]

            # 3) Approve once via approval store -> allowed once -> consumed -> replay denied
            ap = store.create(
                team_id="tm_1", task_id="task_1", step_id="step_1", team_rev=1,
                requested_by="ag_1", kind="action", title="Approve command", action="run_command",
                fingerprints=[{"fp": blocked["fp"], "label": blocked["label"], "call": "rm -rf /tmp/nonexistent_x"}],
            )
            dec = store.decide(ap["approval_id"], "approve", by="owner", decision_key="dk-1")
            self.assertTrue(dec["ok"], dec)
            store.granted_step(ap["approval_id"], "step_1")
            self.assertEqual(_run_hook({"toolCall": {"name": "run_command", "args": {"CommandLine": "rm -rf /tmp/nonexistent_x"}}})["decision"], "allow")
            self.assertEqual(_run_hook({"toolCall": {"name": "run_command", "args": {"CommandLine": "rm -rf /tmp/nonexistent_x"}}})["decision"], "deny")

            # 4) Dead server -> fail-closed deny
            r_dead = _run_hook({"toolCall": {"name": "read_file", "args": {"Path": "/etc/hosts"}}},
                               arg_url="http://127.0.0.1:1/hub/team-gate")
            self.assertEqual(r_dead["decision"], "deny")
        finally:
            if srv is not None:
                srv.shutdown()
                srv.server_close()
            turn_context.reset(tok)
            team_gate.close_gate(g.gate_id)

        # After turn reset, an expired turn key is also denied fail-closed.
        self.assertEqual(client.post("/hub/team-gate", json={"gate_id": g.gate_id, "tool": "read_file", "input": {}},
                                     headers=hdrs).status_code, 403)

    def test_gated_turn_fails_closed_without_hooks_and_single_hook_file(self):
        with patch.object(antigravity_cli, "find_antigravity_cli", return_value="/fake/agy"):
            ac = antigravity_cli.AntigravityCLI(cwd=str(VAULT_DIR), tag="gated-fail", model="gemini-4-argon-high")
        ac.team_gate = "tg_fake"
        ac.hub_turn = True
        ac.hub_url = mcp_hub.hub_url()
        ac.hub_headers = {"Authorization": f"Bearer {mcp_hub.hub_token()}", "X-Javis-Mode": team_gate.HUB_MODE}

        async def run_fail():
            with patch.object(antigravity_cli, "hooks_supported", return_value=False):
                return [ev async for ev in ac.query("hi")]

        with patch.object(antigravity_cli.subprocess, "Popen", side_effect=AssertionError("Popen must not run")):
            evs = asyncio.run(run_fail())
        self.assertEqual(evs[-1]["type"], "error")

        # Verify gated Antigravity _mot_luot writes ONLY .gemini/config/hooks.json (single PreToolUse call) & cleans up
        captured = {}

        def _inspect_gate(proc):
            h = Path(proc.env["HOME"])
            captured["has_cfg_hook"] = (h / ".gemini" / "config" / "hooks.json").is_file()
            captured["has_cli_hook"] = (h / ".gemini" / "antigravity-cli" / "hooks.json").exists()
            captured["mcp"] = json.loads((h / ".gemini" / "config" / "mcp_config.json").read_text(encoding="utf-8"))
            captured["home"] = h

        lines = [json.dumps({"event": "result", "result": {"status": "SUCCESS", "response": "done"}})]

        async def run_gated_ok():
            tok = turn_context.bind(turn_context.make(kenh="team", sender_id="team:tm_x", team_gate="tg_fake"))
            try:
                with patch.dict(os.environ, {"JAVIS_AGY_HOOKS": "1", "JAVIS_AGY_PER_TURN_HOME": "1"}), \
                        patch.object(antigravity_cli, "find_antigravity_cli", return_value="/fake/agy"), \
                        patch.object(antigravity_cli.subprocess, "Popen",
                                     side_effect=lambda args, **kw: _FakePopen(args, lines, _inspect_gate, cwd=kw.get("cwd"), env=kw.get("env"))):
                    return [ev async for ev in ac.query("do work")]
            finally:
                turn_context.reset(tok)

        ok_evs = asyncio.run(run_gated_ok())
        self.assertEqual(ok_evs[-1]["content"], "done")
        self.assertTrue(captured["has_cfg_hook"])
        self.assertFalse(captured["has_cli_hook"])
        self.assertEqual(captured["mcp"]["mcpServers"]["javis"]["headers"].get("X-Javis-Mode"), team_gate.HUB_MODE)
        self.assertTrue(captured["mcp"]["mcpServers"]["javis"]["headers"].get(turn_context.HEADER))
        self.assertFalse(captured["home"].exists())


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        shutil.rmtree(TEMP_ROOT, ignore_errors=True)
