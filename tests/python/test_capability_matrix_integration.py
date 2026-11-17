"""Integration regression matrix for HTTP/store/admin/import paths + smoke script dry-run.

    python tests/python/test_capability_matrix_integration.py

Uses temp brain/state dirs, TestClient, and an in-process mock HTTP server (no
network, no live container state, no real model calls).
"""
from _paths import ROOT, SERVER  # noqa: F401
import asyncio
import contextlib
import importlib.util
import io
import json
import os
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

os.environ["JAVIS_HOST"] = "127.0.0.1"
os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="cap-integ-state-")
TEMP_ROOT = Path(tempfile.mkdtemp(prefix="cap-integ-brain-")).resolve()
(TEMP_ROOT / "agents").mkdir(parents=True, exist_ok=True)

import main  # noqa: E402
import config as cfgmod  # noqa: E402
import engine_capability as EC  # noqa: E402
import team_api  # noqa: E402
import team_bundle  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


SMOKE_ENV = os.environ.get("JAVIS_SMOKE_SCRIPT", "").strip()
SMOKE_PATH = Path(SMOKE_ENV) if SMOKE_ENV else Path("/smoke/smoke_capability.py")


class IntegrationCapabilityTests(unittest.TestCase):
    def setUp(self):
        self.brain = Path(tempfile.mkdtemp(prefix="cap-br-", dir=TEMP_ROOT)).resolve()
        (self.brain / "agents").mkdir(parents=True, exist_ok=True)
        (self.brain / "agents" / "eric.md").write_text(
            "---\nname: Eric Worre\nrole: Coach\nmodel_provider: openai-oauth\nmodel: gpt-6-astra\n---\nEric.\n",
            encoding="utf-8",
        )
        (self.brain / "agents" / "naval.md").write_text(
            "---\nname: Naval\nrole: Strategist\nmodel_provider: antigravity-cli\nmodel: claude-opus-5-5-high\n---\nNaval.\n",
            encoding="utf-8",
        )
        (self.brain / "agents" / "itdev.md").write_text(
            "---\nname: IT Dev\nrole: Helper\n---\nIT.\n",
            encoding="utf-8",
        )
        self.client = TestClient(main.app, base_url="http://127.0.0.1:8080")

    def test_post_agents_validates_and_preserves_on_error(self):
        # Unknown provider -> 400 and file unchanged
        r_bad = asyncio.run(main.save_agent(
            name="Eric Worre", role="Coach", skills="", model="gpt-6-astra", slug="eric",
            prompt="Updated", brain=str(self.brain), model_provider="unknown-prov",
            avatar_shape=None, avatar_palette=None, avatar_color=None, avatar_eye=None,
            avatar_eye_color=None, avatar_eye_size=None, avatar_image=None,
        ))
        self.assertEqual(getattr(r_bad, "status_code", None), 400)
        self.assertIn("openai-oauth", (self.brain / "agents" / "eric.md").read_text(encoding="utf-8"))

        # Valid save returns effective + used_by_teams
        r_save = self.client.post("/agents", data={
            "name": "IT Dev", "role": "Helper", "skills": "", "model": "", "model_provider": "",
            "slug": "itdev", "prompt": "IT.", "brain": str(self.brain),
        })
        self.assertEqual(r_save.status_code, 200, r_save.text)
        self.assertIn("effective", r_save.json())
        self.assertEqual(r_save.json()["effective"]["source"], "main")

        # GET /agents includes effective capability view
        r_list = self.client.get(f"/agents?brain={self.brain}&prompt=0")
        self.assertEqual(r_list.status_code, 200)
        by_slug = {a["slug"]: a for a in r_list.json()["agents"]}
        self.assertIn("effective", by_slug["eric"])
        self.assertEqual(by_slug["itdev"]["effective"]["source"], "main")

    def test_admin_create_agent_and_set_model_enforce_same_validation(self):
        adm = main._TeamAdmin()
        # Unknown provider & model-without-provider must refuse, never silently drop to legacy model-only
        with self.assertRaises(Exception):
            adm.create_agent(str(self.brain), "Bad Admin", "Helper", "Hi",
                             model="gpt-6-astra", model_provider="not-a-provider")
        with self.assertRaises(Exception):
            adm.create_agent(str(self.brain), "No Prov Admin", "Helper", "Hi",
                             model="gpt-6-astra", model_provider="")
        with self.assertRaises(Exception):
            adm.set_model(str(self.brain), "eric", model="gpt-6-astra", model_provider="not-a-provider")
        # Original eric.md intact
        meta, _ = main._read_md(self.brain / "agents" / "eric.md")
        self.assertEqual((meta["model_provider"], meta["model"]), ("openai-oauth", "gpt-6-astra"))

    def test_team_create_add_member_leader_change_capability_gates(self):
        # Codex-only team MUST succeed (even if machine gate unavailable, warning only)
        r_ok = self.client.post(
            f"/teams?brain={self.brain}",
            json={"name": "Codex OK", "members": ["eric"], "leader_slug": "eric", "client_req_id": "cap-ok-1"},
        )
        self.assertEqual(r_ok.status_code, 200, r_ok.text)
        team_ok = r_ok.json()["team"]
        self.assertIn("config_status", team_ok)

        # Team with Antigravity member -> 409 team_config_blocked (team_text unsupported)
        r_agy = self.client.post(
            f"/teams?brain={self.brain}",
            json={"name": "Agy Blocked", "members": ["naval"], "leader_slug": "naval", "client_req_id": "cap-agy-1"},
        )
        self.assertEqual(r_agy.status_code, 409, r_agy.text)
        self.assertEqual(r_agy.json().get("code"), "team_config_blocked")

        # Adding Antigravity member to existing Codex team -> 409 team_config_blocked
        tid = team_ok["team_id"]
        r_add = self.client.post(f"/teams/{tid}/members?brain={self.brain}", json={"slug": "naval"})
        self.assertEqual(r_add.status_code, 409, r_add.text)
        self.assertEqual(r_add.json().get("code"), "team_config_blocked")

        # Leader change to an incompatible member (added via legacy/import) -> 409 team_config_blocked
        got_legacy = team_api.TeamOps(main._TEAM_API).create(
            str(self.brain), str(self.brain), "Legacy Imported", ["eric", "naval"],
            leader="eric", client_req_id="cap-leg-1", enforce_capability=False,
        )
        leg_tid = got_legacy["team"]["team_id"]
        naval_key = next(m["agent_key"] for m in main._TEAM_API.teams().members(leg_tid)
                         if m["slug_at_join"] == "naval")
        r_lead = self.client.post(f"/teams/{leg_tid}/leader?brain={self.brain}", json={"agent_key": naval_key})
        self.assertEqual(r_lead.status_code, 409, r_lead.text)
        self.assertEqual(r_lead.json().get("code"), "team_config_blocked")

        # GET /teams/{id} on existing team returns config_status before any run
        r_get = self.client.get(f"/teams/{tid}?brain={self.brain}")
        self.assertEqual(r_get.status_code, 200)
        self.assertIn("config_status", r_get.json()["team"])

    def test_main_change_impact_and_confirm_gate(self):
        # Set MAIN to Codex and register an inherited-MAIN team so switching to Antigravity has blocking > 0
        s_before = cfgmod.read_settings() or {}
        orig_model = dict(s_before.get("model") or {})
        try:
            s_seed = dict(s_before)
            s_seed["model"] = dict(orig_model, main={"provider": EC.CODEX, "model": "gpt-6-astra"})
            cfgmod.write_settings(s_seed)

            r_tm = self.client.post(
                f"/teams?brain={self.brain}",
                json={"name": "Inherited IT", "members": ["itdev"], "leader_slug": "itdev", "client_req_id": "cap-it-1"},
            )
            self.assertEqual(r_tm.status_code, 200, r_tm.text)

            with patch.object(main, "_brain_root", return_value=self.brain):
                r_imp = self.client.post(
                    "/models/main/impact",
                    json={"provider": EC.ANTIGRAVITY, "model": "gemini-pro-orchestrator"},
                )
                self.assertEqual(r_imp.status_code, 200, r_imp.text)
                imp = r_imp.json()
                self.assertTrue(imp.get("ok"))
                self.assertGreaterEqual(imp.get("blocking", 0), 1)
                self.assertTrue(any(a.get("key") == "itdev" for a in imp.get("agents", [])))

                # Applying MAIN -> Antigravity WITHOUT confirm_impact refuses 409 main_change_impact
                r_refuse = self.client.post(
                    "/settings",
                    data={"section": "model", "data": json.dumps({
                        "main": {"provider": EC.ANTIGRAVITY, "model": "gemini-pro-orchestrator"},
                    })},
                )
                self.assertEqual(r_refuse.status_code, 409, r_refuse.text)
                self.assertEqual(r_refuse.json().get("code"), "main_change_impact")
                self.assertEqual((cfgmod.read_settings().get("model") or {}).get("main", {}).get("provider"), EC.CODEX)

                # With confirm_impact=True it applies cleanly
                r_conf = self.client.post(
                    "/settings",
                    data={"section": "model", "data": json.dumps({
                        "main": {"provider": EC.ANTIGRAVITY, "model": "gemini-pro-orchestrator"},
                        "confirm_impact": True,
                    })},
                )
                self.assertEqual(r_conf.status_code, 200, r_conf.text)
                self.assertEqual((cfgmod.read_settings().get("model") or {}).get("main", {}).get("provider"),
                                 EC.ANTIGRAVITY)
        finally:
            s_restore = cfgmod.read_settings() or {}
            s_restore["model"] = orig_model
            cfgmod.write_settings(s_restore)

    def test_team_bundle_export_import_preserves_member_config_and_flags_legacy(self):
        # Export preserves member_config without leaking secrets
        r_ok = self.client.post(
            f"/teams?brain={self.brain}",
            json={"name": "Exportable", "members": ["eric"], "leader_slug": "eric", "client_req_id": "cap-exp-1"},
        )
        self.assertEqual(r_ok.status_code, 200, r_ok.text)
        tid = r_ok.json()["team"]["team_id"]
        exp = self.client.get(f"/teams/{tid}/export?brain={self.brain}")
        self.assertEqual(exp.status_code, 200)
        z = zipfile.ZipFile(io.BytesIO(exp.content))
        manifest = json.loads(z.read(team_bundle.TEAM_ENTRY))
        self.assertIn("member_config", manifest)
        self.assertEqual(manifest["member_config"].get("eric", {}).get("provider"), "openai-oauth")
        self.assertEqual(manifest["member_config"].get("eric", {}).get("model"), "gpt-6-astra")

        # Import into fresh brain preserves per-agent provider/model and returns config_status
        dst = Path(tempfile.mkdtemp(prefix="cap-dst-", dir=TEMP_ROOT)).resolve()
        (dst / "agents").mkdir(parents=True, exist_ok=True)
        imp = self.client.post(
            "/teams/import",
            data={"brain": str(dst)},
            files={"file": ("team.javis.zip", exp.content, "application/zip")},
        )
        self.assertEqual(imp.status_code, 200, imp.text)
        j = imp.json()
        self.assertIn("config_status", j["team"])
        meta, _ = main._read_md(dst / "agents" / "eric.md")
        self.assertEqual((meta.get("model_provider"), meta.get("model")), ("openai-oauth", "gpt-6-astra"))

        # Legacy bundle (no member_config) imports cleanly and marks inherited members as source=main
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zin, zipfile.ZipFile(io.BytesIO(exp.content), "r") as zsrc:
            for item in zsrc.infolist():
                raw = zsrc.read(item.filename)
                if item.filename == team_bundle.TEAM_ENTRY:
                    m_old = json.loads(raw)
                    m_old.pop("member_config", None)
                    raw = json.dumps(m_old).encode("utf-8")
                zin.writestr(item, raw)
        dst2 = Path(tempfile.mkdtemp(prefix="cap-dst2-", dir=TEMP_ROOT)).resolve()
        (dst2 / "agents").mkdir(parents=True, exist_ok=True)
        imp_old = self.client.post(
            "/teams/import",
            data={"brain": str(dst2)},
            files={"file": ("legacy.javis.zip", buf.getvalue(), "application/zip")},
        )
        self.assertEqual(imp_old.status_code, 200, imp_old.text)
        cs = imp_old.json()["team"]["config_status"]
        self.assertEqual(cs["members"][0]["source"], "main")

    def test_smoke_script_dry_run_against_mock_server(self):
        if not SMOKE_PATH.is_file():
            self.skipTest(f"Missing smoke script at {SMOKE_PATH}")
        spec = importlib.util.spec_from_file_location("smoke_capability", str(SMOKE_PATH))
        smoke_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(smoke_mod)

        state = {
            "teams": {"tm_marathon": {"team_id": "tm_marathon", "name": "Marathon - V25", "status": "active"}},
            "messages": {},
            "deleted": [],
            "patched": [],
            "forbidden_hits": [],
            "auth_seen": [],
        }
        secret_tok = "jvs_smoke_unit_secret_do_not_print"

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                return

            def _send(self, code, payload):
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _body(self):
                n = int(self.headers.get("Content-Length") or 0)
                return json.loads(self.rfile.read(n).decode("utf-8")) if n else {}

            def do_GET(self):
                path = self.path.split("?", 1)[0]
                if path == "/health":
                    return self._send(200, {"status": "ok"})
                if path == "/auth/status":
                    return self._send(200, {"auth_required": True})
                state["auth_seen"].append(self.headers.get("Authorization", ""))
                if self.headers.get("Authorization") != f"Bearer {secret_tok}":
                    return self._send(401, {"error": "unauthorized"})
                if path == "/agents":
                    return self._send(200, {"agents": [
                        {"slug": "naval", "model_provider": "antigravity-cli", "model": "claude-opus-5-5-high"},
                        {"slug": "eric-worre", "model_provider": "openai-oauth", "model": "gpt-6-astra"},
                    ]})
                if path.startswith("/teams/") and path.endswith("/messages"):
                    tid = path.split("/")[2]
                    return self._send(200, {"ok": True, "messages": state["messages"].get(tid, [])})
                return self._send(404, {"error": "not found"})

            def do_POST(self):
                path = self.path.split("?", 1)[0]
                if path.startswith("/agents") or path.startswith("/settings"):
                    state["forbidden_hits"].append(path)
                    return self._send(403, {"error": "forbidden"})
                body = self._body()
                if path == "/teams":
                    tid = "tm_smoke_1"
                    team = {
                        "team_id": tid,
                        "name": body["name"],
                        "status": "active",
                        "leader_key": "ag_eric",
                        "members": [{"agent_key": "ag_eric", "slug": body["members"][0]}],
                    }
                    state["teams"][tid] = team
                    state["messages"][tid] = []
                    return self._send(200, {"ok": True, "team": team})
                if path.startswith("/teams/") and path.endswith("/messages"):
                    tid = path.split("/")[2]
                    state["messages"][tid] = [
                        {"id": 1, "author_kind": "owner", "content": body["text"],
                         "replies": [{"agent_key": "ag_eric", "status": "done"}]},
                        {"id": 2, "author_kind": "agent", "author_ref": "ag_eric",
                         "reply_to": 1, "content": "OK"},
                    ]
                    return self._send(200, {"ok": True, "message_id": 1})
                return self._send(404, {"error": "not found"})

            def do_PATCH(self):
                path = self.path.split("?", 1)[0]
                tid = path.split("/")[2]
                if tid == "tm_marathon":
                    state["forbidden_hits"].append(path)
                    return self._send(403, {"error": "forbidden"})
                body = self._body()
                state["teams"][tid]["status"] = body.get("status", "active")
                state["patched"].append((tid, body))
                return self._send(200, {"ok": True, "team": state["teams"][tid]})

            def do_DELETE(self):
                path = self.path.split("?", 1)[0]
                tid = path.split("/")[2]
                if tid == "tm_marathon":
                    state["forbidden_hits"].append(path)
                    return self._send(403, {"error": "forbidden"})
                state["teams"].pop(tid, None)
                state["deleted"].append(tid)
                return self._send(200, {"ok": True, "deleted": tid})

        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            out, err = io.StringIO(), io.StringIO()
            with patch.dict(os.environ, {"JAVIS_API_TOKEN": secret_tok}), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = smoke_mod.main(["--url", f"http://127.0.0.1:{port}", "--timeout", "10"])
            self.assertEqual(rc, 0, err.getvalue())
            self.assertNotIn(secret_tok, out.getvalue() + err.getvalue())
            self.assertEqual(state["forbidden_hits"], [])
            self.assertEqual(state["deleted"], ["tm_smoke_1"])
            self.assertIn("tm_marathon", state["teams"])
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
