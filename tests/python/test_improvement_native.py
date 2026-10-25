"""Opt-in native process enforcement test, with dummy auth and a localhost fake provider."""
from _paths import ROOT, SERVER  # noqa: F401

import asyncio
import gzip
import hashlib
import http.server
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path


def worker(root):
    from improvement_claude import TrialProfile
    from improvement_sandbox import FixtureBroker, TrialWorkspace, trial_system_prompt
    from improvement_store import _hash
    from claude_cli import claude_engine

    async def run():
        grant = hashlib.sha256(b"synthetic grant").hexdigest()
        content = "SYNTHETIC_FIXTURE_ONLY"
        broker = FixtureBroker([{"snapshot_id": "fixture-allowed", "content": content,
            "hash": hashlib.sha256(content.encode()).hexdigest(),
            "source": {"source_version": "v1", "data_period": "synthetic", "timezone": "UTC",
                       "cutoff": "2026-10-22T00:00:00Z", "schema": "text/plain"}}], grant)

        async def ack():
            pass  # Synthetic host boundary; no production ledger or inference is involved.

        pin = {"provider": "anthropic-cli", "model": "claude-opus-5-5", "reasoning": "medium",
               "cli_path": os.environ["JAVIS_TEST_NATIVE_CLI"], "sdk_version": "0.2.116"}
        sha = lambda text: hashlib.sha256(text.encode()).hexdigest()
        acceptance = {"version": 1, "objective": "Exercise only the synthetic fixture boundary.",
            "output": {"kind": "text", "path": "result.txt", "media_type": "text/plain"},
            "criteria": [{"id": "artifact", "category": "mandatory", "critical": True,
                "description": "Return a text artifact.", "kind": "file_exists", "config": {"path": "result.txt"}},
                {"id": "synthetic", "category": "business", "critical": True,
                 "description": "Finish the local synthetic capability exercise.", "kind": "independent_check"}]}
        manifest = {"version": 1, "brain_id": "synthetic-brain", "bundle_hash": sha("synthetic-bundle"),
            "engine_config_hash": _hash(pin), "contract_hash": sha("synthetic-private-contract"), "grant_hash": grant,
            "baseline_context": {"content": "Exercise only the synthetic fixture boundary.",
                "hash": sha("Exercise only the synthetic fixture boundary."), "coverage": "complete"},
            "public_contract": {"content": acceptance, "hash": _hash(acceptance)},
            "assets": [{"id": "revision-synthetic", "path": "skills/synthetic/SKILL.md",
                        "content": "Use only the authorized fixture.", "hash": sha("Use only the authorized fixture.")}],
            "case": {"id": "synthetic-case", "task": "Exercise the local boundary.", "fixtures": list(broker.fixtures.values())},
            "learning_origin": "trial"}
        workspace = TrialWorkspace(root / "trial-workspaces").prepare("synthetic-native", 1, manifest)
        actual_root = Path(workspace["path"])
        shutil.copytree(root / ".claude", actual_root / ".claude")
        for name in ("CLAUDE.md", ".mcp.json"):
            shutil.copyfile(root / name, actual_root / name)
        engine = claude_engine(cwd=str(actual_root), tag="improvement:synthetic-native", model=pin["model"])
        profile = TrialProfile(pin, broker, trial_system_prompt(manifest), before_query=ack)
        profile.bind_installation(manifest, workspace, sha("synthetic-profile-capability"))
        engine.trial_profile = profile
        events = []
        async for event in engine.query("Exercise the local boundary."):
            events.append(event)
            print("native-probe-event=" + event["type"], file=sys.stderr, flush=True)
        print(json.dumps({"label": "synthetic/native-local-fake-provider", "production_billing": False,
                          "events": events, "broker_events": broker.events, "denials": profile.denials}))

    asyncio.run(run())


class NativeBoundaryTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("JAVIS_TEST_NATIVE_CLI"), "Explicit native binary required; no real provider fallback")
    def test_native_profile_denies_outside_tools_and_ambient_configuration(self):
        root = Path(tempfile.mkdtemp(prefix="improvement-native-local-"))
        work, outside = root / "workspace", root / "outside"
        work.mkdir()
        outside.mkdir()
        canary = "OUTSIDE_SYNTHETIC_CANARY_123"
        (outside / "keep.txt").write_text(canary)
        requests = []
        response_count = 0

        class Handler(http.server.BaseHTTPRequestHandler):
            def reply(self, status, body, content_type="application/json"):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_CONNECT(self):
                requests.append({"path": self.path, "method": "CONNECT"})
                self.reply(503, b"{}")

            def do_GET(self):
                requests.append({"path": self.path, "method": "GET"})
                self.reply(503, b"{}")

            def do_POST(self):
                nonlocal response_count
                raw = self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 4_000_000))
                if self.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                value = json.loads(raw or b"{}")
                path = self.path.split("?", 1)[0]
                requests.append({"path": path, "body": value})
                if path == "/v1/messages/count_tokens":
                    self.reply(200, b'{"input_tokens":1}')
                    return
                if path != "/v1/messages":
                    self.reply(503, b"{}")
                    return
                response_count += 1
                if response_count > 3:
                    self.reply(400, b'{"error":{"type":"invalid_request_error","message":"synthetic bound"}}')
                    return
                tools = [("bad-bash", "Bash", {"command": 'echo forbidden > "' + str(outside / "created.txt") + '"'}),
                         ("bad-read", "Read", {"file_path": str(outside / "keep.txt")}),
                         ("bad-web", "WebFetch", {"url": endpoint + "/forbidden-live", "prompt": "Read"}),
                         ("bad-mcp", "mcp__live__send", {"value": "forbidden"}),
                         ("hit", "mcp__fixture__fixture_read", {"snapshot_id": "fixture-allowed", "source_version": "v1"}),
                         ("miss", "mcp__fixture__fixture_read", {"snapshot_id": "../keep.txt", "source_version": "v1"})]
                blocks = ([{"type": "tool_use", "id": i, "name": name, "input": args} for i, name, args in tools]
                          if response_count == 1 else [{"type": "text", "text": "LOCAL_NATIVE_DONE"}])
                stop = "tool_use" if response_count == 1 else "end_turn"
                message = {"id": f"msg_local_{response_count}", "type": "message", "role": "assistant",
                           "model": "claude-opus-5-5", "content": [], "stop_reason": None, "stop_sequence": None,
                           "usage": {"input_tokens": 1, "output_tokens": 0}}
                events = []

                def emit(kind, data):
                    events.append("event: " + kind + "\ndata: " + json.dumps(data) + "\n\n")

                emit("message_start", {"type": "message_start", "message": message})
                for index, block in enumerate(blocks):
                    initial = {**block, "input": {}} if block["type"] == "tool_use" else {"type": "text", "text": ""}
                    delta = ({"type": "input_json_delta", "partial_json": json.dumps(block["input"])}
                             if block["type"] == "tool_use" else {"type": "text_delta", "text": block["text"]})
                    emit("content_block_start", {"type": "content_block_start", "index": index, "content_block": initial})
                    emit("content_block_delta", {"type": "content_block_delta", "index": index, "delta": delta})
                    emit("content_block_stop", {"type": "content_block_stop", "index": index})
                emit("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None},
                                       "usage": {"output_tokens": 1}})
                emit("message_stop", {"type": "message_stop"})
                self.reply(200, "".join(events).encode(), "text/event-stream")

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        endpoint = "http://127.0.0.1:" + str(server.server_port)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        from improvement_sandbox import worker_environment
        environment = worker_environment(root, auth_home=root / "empty-auth-home")
        for name in ("empty-auth-home", "tmp", "config"):
            (root / name).mkdir()
        environment.update({"CLAUDE_CONFIG_DIR": str(root / "config"), "ANTHROPIC_API_KEY": "synthetic-local-provider-only",
            "ANTHROPIC_BASE_URL": endpoint, "HTTP_PROXY": endpoint, "HTTPS_PROXY": endpoint, "ALL_PROXY": endpoint,
            "NO_PROXY": "127.0.0.1,localhost", "JAVIS_TEST_NATIVE_CLI": os.environ["JAVIS_TEST_NATIVE_CLI"]})
        ambient = {"permissions": {"allow": ["Bash", "Read", "WebFetch", "mcp__live__*"]},
                   "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command":
                             'echo ambient > "' + str(outside / "hook.txt") + '"'}]}]}}
        (work / ".claude").mkdir()
        (work / ".claude" / "settings.json").write_text(json.dumps(ambient))
        (root / "config" / "settings.json").write_text(json.dumps(ambient))
        (work / "CLAUDE.md").write_text("SYNTHETIC_AMBIENT_CONTEXT_DO_NOT_LOAD")
        (work / ".mcp.json").write_text(json.dumps({"mcpServers": {"ambient": {"type": "http", "url": endpoint + "/ambient"}}}))
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--native-worker", str(work)],
                                   cwd=work, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, start_new_session=os.name != "nt")
        try:
            try:
                stdout, stderr = process.communicate(timeout=35)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=5)
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate(timeout=5)
                summary = [{"path": r["path"], "model": r.get("body", {}).get("model"),
                            "tool_results": [block.get("tool_use_id") for message in r.get("body", {}).get("messages", [])
                                if isinstance(message.get("content"), list) for block in message["content"]
                                if block.get("type") == "tool_result"]} for r in requests]
                self.fail("Native fake-provider timeout; requests=" + json.dumps(summary) + "; stderr=" + stderr[-1500:])
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(process.returncode, 0, stderr[-1500:])
        observed = json.loads(stdout)
        self.assertFalse([e for e in observed["events"] if e["type"] == "error"], observed)
        initializations = [e["data"] for e in observed["events"] if e["type"] == "native_system" and e["subtype"] == "init"]
        self.assertEqual(len(initializations), 1)
        expected_tools = getattr(self, 'expected_tools', ["mcp__fixture__fixture_read"])
        self.assertEqual(initializations[0]["tools"], expected_tools)
        receipts = [e["receipt"] for e in observed["events"] if e["type"] == "installation_receipt"]
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]["coverage"]["tool_inventory"], "observed")
        self.assertEqual(receipts[0]["coverage"]["model"], "observed")
        if expected_tools == ['mcp__fixture__fixture_read']:
            self.assertEqual(receipts[0]["asset_revisions"][0]["observed_use"], "unknown")
        else:
            self.assertEqual(expected_tools, ['mcp__fixture__fixture_read', 'mcp__skill__skill_asset_read'])
            from improvement_skill_asset_proof import correlate_asset_reads
            # Recompute from the paired caller's frozen input, without assuming
            # optional SDK error flags are present on every successful result.
            payload = json.loads((work / 'view-input.json').read_bytes())
            proof = correlate_asset_reads(payload['manifest'], {key: receipts[0][key]
                for key in ('trial_id', 'attempt', 'input_hash')}, observed['events'])
            self.assertEqual(receipts[0]['asset_read_proofs'], proof['proofs'])
            self.assertEqual(receipts[0]['asset_revisions'][0]['observed_use'],
                'observed' if proof['verdict'] == 'pass' else 'unknown')
        self.assertEqual(receipts[0]["coverage"]["reasoning"], "unknown")
        self.assertEqual(observed["label"], "synthetic/native-local-fake-provider")
        self.assertEqual([e["content"] for e in observed["events"] if e["type"] == "artifact"], ["LOCAL_NATIVE_DONE"])
        self.assertEqual([e["status"] for e in observed["broker_events"]], ["fixture_hit", "fixture_miss"])
        self.assertEqual((outside / "keep.txt").read_text(), canary)
        self.assertFalse((outside / "created.txt").exists())
        self.assertFalse((outside / "hook.txt").exists())
        self.assertFalse(any("forbidden-live" in r["path"] or "/ambient" in r["path"] for r in requests))
        model_requests = [r["body"] for r in requests if r["path"] == "/v1/messages"]
        self.assertEqual(len(model_requests), 2)
        for request in model_requests:
            self.assertEqual(request["model"], "claude-opus-5-5")
            self.assertEqual(request["output_config"]["effort"], "medium")
            self.assertEqual([t["name"] for t in request["tools"]], expected_tools)
            self.assertNotIn(canary, json.dumps(request))
            self.assertNotIn("SYNTHETIC_AMBIENT_CONTEXT_DO_NOT_LOAD", json.dumps(request))
        results = {block["tool_use_id"]: block for message in model_requests[-1]["messages"]
                   if isinstance(message.get("content"), list) for block in message["content"] if block["type"] == "tool_result"}
        for identifier in ("bad-bash", "bad-read", "bad-web", "bad-mcp", "miss"):
            self.assertTrue(results[identifier]["is_error"], identifier)
        self.assertFalse(results["hit"].get("is_error", False))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--native-worker":
        worker(Path(sys.argv[2]))
    else:
        unittest.main()
