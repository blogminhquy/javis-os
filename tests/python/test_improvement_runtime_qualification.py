"""Explicitly pinned developer qualification; dummy HOME and localhost fake inference only."""
import asyncio
import contextlib
import gzip
import hashlib
import http.server
import importlib.metadata
import inspect
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

if "--qualification-worker" in sys.argv:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from _paths import ROOT, SERVER  # noqa: F401,E402

import improvement_claude as native
import improvement_worker as worker

CANDIDATE_VERSION = "2.1.310"
CANDIDATE_HASH = "f9a3920634ae3b961ee92c2eb58d0051f5f8852b120983d0a4f57b6a5efeba61"
SDK_VERSION = "0.2.116"
MARKERS = ("QUALIFICATION_AMBIENT_SKILL", "QUALIFICATION_AMBIENT_AGENT", "QUALIFICATION_AMBIENT_PLUGIN")
EVIDENCE = []


def append_tool_calls(body, calls):
    """Compose controlled provider replies without reusing or reordering indexes."""
    values = [json.loads(line[6:]) for line in body.decode().splitlines() if line.startswith('data: ')]
    indexes = [value['index'] for value in values if value.get('type') == 'content_block_start']
    if indexes != list(range(len(indexes))):
        raise AssertionError('Noncontiguous native qualification content blocks')
    additions = []
    for index, (identifier, name, args) in enumerate(calls, len(indexes)):
        for kind, data in (("content_block_start", {"type": "content_block_start", "index": index,
            "content_block": {"type": "tool_use", "id": identifier, "name": name, "input": {}}}),
            ("content_block_delta", {"type": "content_block_delta", "index": index,
             "delta": {"type": "input_json_delta", "partial_json": json.dumps(args)}}),
            ("content_block_stop", {"type": "content_block_stop", "index": index})):
            additions.append("event: " + kind + "\ndata: " + json.dumps(data) + "\n\n")
    marker = b"event: message_delta\n"
    if body.count(marker) != 1:
        raise AssertionError('Ambiguous native qualification message delta')
    return body.replace(marker, ''.join(additions).encode() + marker, 1)


def candidate(path):
    """No discovery, execution, authentication or generic unknown-runtime exemption."""
    from improvement_trial_selection import MAX_BINARY_BYTES, _read_stable
    path = Path(path)
    if os.name != "nt" or not path.is_absolute():
        raise ValueError("candidate_platform_or_path_unverified")
    digest, _ = _read_stable(path, MAX_BINARY_BYTES, digest=True)
    if digest != CANDIDATE_HASH or importlib.metadata.version("claude-agent-sdk") != SDK_VERSION:
        raise ValueError("candidate_identity_unverified")
    if native._managed_policy() != "absent":
        raise ValueError("candidate_managed_policy_unverified")
    return path


def _ambient(root):
    """Known harmless scratch-only ambient configurations that the profile must ignore."""
    skill = root / ".claude" / "skills" / "qualification-canary"
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text("---\nname: qualification-canary\ndescription: qualification ambient canary\n---\n" + MARKERS[0])
    agent = root / ".claude" / "agents"
    agent.mkdir(parents=True, exist_ok=True)
    (agent / "qualification-canary.md").write_text("---\nname: qualification-canary\ndescription: qualification ambient canary\n---\n" + MARKERS[1])
    config = Path(os.environ["CLAUDE_CONFIG_DIR"])
    plugin = config / "plugins" / "cache" / "qualification" / "canary" / "1.0.0"
    (plugin / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "canary", "version": "1.0.0", "description": MARKERS[2]}))
    (plugin / "hooks").mkdir()
    command = 'echo plugin > "' + str(root.parent / "outside" / "plugin-hook.txt") + '"'
    (plugin / "hooks" / "hooks.json").write_text(json.dumps({"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": command}]}]}}))
    (config / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {"canary@qualification": [{
        "scope": "user", "installPath": str(plugin), "version": "1.0.0", "installedAt": "2026-10-23T00:00:00Z", "lastUpdated": "2026-10-23T00:00:00Z"}]}}))
    settings = config / "settings.json"
    data = json.loads(settings.read_text()) if settings.exists() else {}
    data["enabledPlugins"] = {"canary@qualification": True}
    data["fastMode"] = True
    settings.write_text(json.dumps(data))


def qualification_worker(root):
    """The parent owns the process job before this exact candidate may execute."""
    if sys.stdin.readline().strip() != "qualification_start":
        raise ValueError("qualification_gate_missing")
    from urllib.parse import urlsplit
    endpoint = urlsplit(os.environ["ANTHROPIC_BASE_URL"])
    if (endpoint.scheme != "http" or endpoint.hostname != "127.0.0.1" or not endpoint.port
            or os.environ.get("ANTHROPIC_API_KEY") != "synthetic-local-provider-only"):
        raise ValueError("qualification_transport_not_local_dummy")
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        if os.environ.get(name) != os.environ["ANTHROPIC_BASE_URL"]:
            raise ValueError("qualification_proxy_not_local")
    for name in ("HOME", "USERPROFILE", "CLAUDE_CONFIG_DIR"):
        expected = root.parent / ("config" if name == "CLAUDE_CONFIG_DIR" else "empty-auth-home")
        if Path(os.environ[name]) != expected:
            raise ValueError("qualification_home_not_scratch")
    pinned = candidate(os.environ["JAVIS_TEST_NATIVE_CLI"])
    version = subprocess.run([str(pinned), '--version'], cwd=root, capture_output=True, text=True,
        check=True, timeout=10, creationflags=worker.winproc.no_window()).stdout.strip().split()
    if not version or version[0] != CANDIDATE_VERSION:
        raise ValueError('qualification_native_version_changed')
    _ambient(root)
    import test_improvement_native as existing
    from claude_agent_sdk._internal.transport import subprocess_cli
    original = subprocess_cli.anyio.open_process
    spawns = []

    async def observed(command, **kwargs):
        if Path(command[0]) != pinned:
            raise ValueError("qualification_unpinned_executable")
        if not kwargs.get("creationflags", 0) & worker.winproc.no_window():
            raise ValueError("qualification_native_console_not_hidden")
        process = await original(command, **kwargs)
        spawns.append({"kind": "version" if any(flag in command for flag in ("-v", "--version")) else "query", "pid": process.pid,
                       "creationflags": kwargs["creationflags"]})
        print("qualification-spawn=" + json.dumps(spawns[-1]), file=sys.stderr, flush=True)
        return process

    output = io.StringIO()
    with patch.object(subprocess_cli.anyio, "open_process", side_effect=observed), worker._sdk_hidden_processes(), \
         patch("config.read_settings", side_effect=AssertionError("Ordinary configuration access forbidden")), \
         contextlib.redirect_stdout(output):
        existing.worker(root)
    result = json.loads(output.getvalue())
    import ctypes
    result["qualification"] = {"spawns": spawns, "worker_has_console": bool(ctypes.windll.kernel32.GetConsoleWindow()),
                               "version": version[0], "cli_hash": CANDIDATE_HASH, "sdk_version": SDK_VERSION}
    print(json.dumps(result), flush=True)


def _job_pids(group):
    if getattr(group, '_guardian', None) is not None:
        return group.inventory()
    import ctypes
    from ctypes import wintypes

    class List(ctypes.Structure):
        _fields_ = [("assigned", wintypes.DWORD), ("count", wintypes.DWORD), ("pids", ctypes.c_size_t * 128)]

    value = List()
    function = group._kernel.QueryInformationJobObject
    function.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
    function.restype = wintypes.BOOL
    if not function(group.handle, 3, ctypes.byref(value), ctypes.sizeof(value), None) or value.assigned > 128:
        raise RuntimeError("qualification_job_inventory_unavailable")
    return list(value.pids[:value.count])


def _alive(pid):
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x100000, False, pid)
    if not handle:
        return False
    try:
        return kernel.WaitForSingleObject(handle, 0) == 258
    finally:
        kernel.CloseHandle(handle)


def _spawn(command, **kwargs):
    """Reuse the existing blackbox worker while adding the production job/start gate."""
    original = _spawn.original
    if "--native-worker" not in command:
        raise AssertionError("Qualification may spawn only its explicitly gated worker")
    root = Path(command[-1])
    command = [sys.executable, "-I", "-X", "utf8", str(Path(__file__).resolve()), "--qualification-worker", str(root)]
    from improvement_sandbox import TrialWorkspace
    workspace = TrialWorkspace(root / 'trial-workspaces')
    # These are the actual synthetic solver identities used by the blackbox.
    with patch.object(subprocess, 'Popen', original):
        lifetime = workspace.acquire_execution('synthetic-brain', 'synthetic-native', 1)
    if lifetime is None:
        raise RuntimeError('qualification_solver_lifetime_unavailable')
    kwargs.update(stdin=subprocess.PIPE, creationflags=worker.process_flags() | (4 if os.name == 'nt' else 0))
    process = original(command, **kwargs)
    try:
        with patch.object(subprocess, 'Popen', original):
            group = worker.WorkerGroup(process.pid, recovery_fences=tuple(handle.name for handle in lifetime), suspended=os.name == 'nt')
    except BaseException:
        process.kill()
        process.communicate(timeout=5)
        workspace.release_execution(lifetime)
        raise
    _spawn.roots.append(root)
    process.stdin.write("qualification_start\n")
    process.stdin.flush()
    communicate = process.communicate

    def owned_communicate(*args, **options):
        try:
            stdout, stderr = communicate(*args, **options)
            if stdout:
                _spawn.observations.append(json.loads(stdout))
            return stdout, stderr
        finally:
            group.close()
            with patch.object(subprocess, 'Popen', original):
                try:
                    workspace.cleanup('synthetic-native', 1)
                finally:
                    workspace.release_execution(lifetime)
            if (root / 'trial-workspaces' / 'synthetic-native' / 'attempt-1').exists():
                raise AssertionError('Solver plaintext workspace survived native drain')

    process.communicate = owned_communicate
    process.qualification_group = group
    return process


class CandidateNativeTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("JAVIS_TEST_NATIVE_QUALIFICATION_CLI"), "Explicit candidate developer qualification only")
    def test_candidate_reuses_full_native_blackbox_with_extra_tool_and_ambient_canaries(self):
        path = candidate(os.environ["JAVIS_TEST_NATIVE_QUALIFICATION_CLI"])
        import test_improvement_native as existing
        original_server, requests = http.server.ThreadingHTTPServer, []
        extras = [("bad-agent", "Agent", {"subagent_type": "qualification-canary", "description": "synthetic", "prompt": "synthetic"}),
                  ("bad-task", "Task", {"subagent_type": "qualification-canary", "description": "synthetic", "prompt": "synthetic"}),
                  ("bad-skill", "Skill", {"skill": "qualification-canary"}),
                  ("bad-search", "ToolSearch", {"query": "+fixture", "max_results": 5}),
                  ("bad-deferred", "DeferredToolPlaceholder", {"query": "synthetic"})]

        def server(address, handler):
            post, reply = handler.do_POST, handler.reply

            def observed_post(instance):
                length = int(instance.headers.get("Content-Length", 0))
                raw = instance.rfile.read(min(length, 4_000_000))
                instance.rfile = io.BytesIO(raw)
                content = gzip.decompress(raw) if instance.headers.get("Content-Encoding") == "gzip" else raw
                body = json.loads(content or b"{}")
                text = json.dumps(body)
                requests.append({"path": instance.path.split("?", 1)[0], "model": body.get("model"),
                    "method": "POST", "dummy_auth_only": instance.headers.get("x-api-key") == "synthetic-local-provider-only"
                    and instance.headers.get("Authorization") in (None, "Bearer synthetic-local-provider-only"),
                    "effort": body.get("output_config", {}).get("effort"), "tools": [v.get("name") for v in body.get("tools", [])],
                    "fast_requested": body.get("speed") == "fast" or body.get("service_tier") in {"fast", "priority"},
                    "ambient_markers": [marker for marker in MARKERS if marker in text],
                    "results": {block["tool_use_id"]: bool(block.get("is_error")) for message in body.get("messages", [])
                                if isinstance(message.get("content"), list) for block in message["content"] if block.get("type") == "tool_result"}})
                return post(instance)

            def injected_reply(instance, status, body, content_type="application/json"):
                if content_type == "text/event-stream" and b'"stop_reason": "tool_use"' in body:
                    body = append_tool_calls(body, extras)
                return reply(instance, status, body, content_type)

            handler.do_POST, handler.reply = observed_post, injected_reply
            for method in ("GET", "CONNECT"):
                original = getattr(handler, "do_" + method)

                def unexpected(instance, original=original, method=method):
                    requests.append({"method": method, "path": instance.path, "ambient_markers": [], "fast_requested": False})
                    return original(instance)

                setattr(handler, "do_" + method, unexpected)
            return original_server(address, handler)

        _spawn.original, _spawn.observations, _spawn.roots = subprocess.Popen, [], []
        started = time.monotonic()
        with patch.dict(os.environ, {"JAVIS_TEST_NATIVE_CLI": str(path)}), \
             patch.object(existing.http.server, "ThreadingHTTPServer", side_effect=server), \
             patch.object(existing.subprocess, "Popen", side_effect=_spawn):
            method = inspect.unwrap(existing.NativeBoundaryTests.test_native_profile_denies_outside_tools_and_ambient_configuration)
            boundary = existing.NativeBoundaryTests()
            boundary.expected_tools = getattr(self, 'expected_tools', ['mcp__fixture__fixture_read'])
            method(boundary)
        self.assertEqual(len(_spawn.observations), 1)
        result = _spawn.observations[0]
        observations = result["qualification"]
        self.assertEqual(observations['version'], CANDIDATE_VERSION)
        self.assertFalse(observations["worker_has_console"])
        self.assertEqual({spawn["kind"] for spawn in observations["spawns"]}, {"version", "query"})
        self.assertTrue(all(spawn["creationflags"] & worker.winproc.no_window() for spawn in observations["spawns"]))
        for request in requests:
            self.assertIn(request["path"], {"/v1/messages", "/v1/messages/count_tokens"})
            self.assertEqual(request["method"], "POST")
            self.assertTrue(request["dummy_auth_only"])
            self.assertFalse(request["ambient_markers"])
            self.assertFalse(request["fast_requested"])
        messages = [value for value in requests if value["path"] == "/v1/messages"]
        self.assertEqual(len(messages), 2)
        self.assertTrue(all(messages[-1]["results"][identifier] for identifier, _, _ in extras))
        self.assertTrue(any(event["type"] == "usage" for event in result["events"]))
        for root in _spawn.roots:
            self.assertFalse((root.parent / "outside" / "plugin-hook.txt").exists())
            self.assertFalse(list((root.parent / "config" / "projects").rglob("*.jsonl")))
        for spawn in observations["spawns"]:
            self.assertFalse(_alive(spawn["pid"]))
        # Rehash the exact binary after the exercise; auto-update cannot silently substitute it.
        self.assertEqual(candidate(path), path)
        EVIDENCE.append({"scenario": "synthetic/native-local-fake-provider", "elapsed_s": round(time.monotonic() - started, 3),
            "production_billing": False, "runtime": {"version": observations['version'], "sha256": CANDIDATE_HASH, "sdk": SDK_VERSION},
            "sdk_spawn_flags": [spawn["creationflags"] for spawn in observations["spawns"]],
            "worker_has_console": False, "requests": requests, "tool_denials": [identifier for identifier, _, _ in extras],
            "fixture_statuses": [event["status"] for event in result["broker_events"]],
            "ambient_plugin_hook_ran": False, "session_transcripts_persisted": False,
            "coverage": {"model": "observed", "reasoning": "unknown", "asset_use": "unknown"}, "sdk_children_closed": True})

    @unittest.skipUnless(os.environ.get("JAVIS_TEST_NATIVE_QUALIFICATION_CLI"), "Explicit candidate developer qualification only")
    def test_candidate_pending_query_cancellation_closes_the_owned_native_tree(self):
        from improvement_sandbox import worker_environment
        path = candidate(os.environ["JAVIS_TEST_NATIVE_QUALIFICATION_CLI"])
        requested, release = threading.Event(), threading.Event()
        requests, dummy_auth = [], []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                self.rfile.read(min(length, 4_000_000))
                requests.append(self.path.split("?", 1)[0])
                dummy_auth.append(self.headers.get("x-api-key") == "synthetic-local-provider-only"
                                  and self.headers.get("Authorization") in (None, "Bearer synthetic-local-provider-only"))
                if self.path.split("?", 1)[0] == "/v1/messages/count_tokens":
                    body = b'{"input_tokens":1}'
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path.split("?", 1)[0] != "/v1/messages":
                    self.send_error(503)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                requested.set()
                release.wait(40)  # Native remains genuinely in flight until the host closes its job.

            def log_message(self, *args):
                pass

            def do_GET(self):
                requests.append("unexpected_GET")
                self.send_error(503)

            def do_CONNECT(self):
                requests.append("unexpected_CONNECT")
                self.send_error(503)

        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="qualification-cancel-") as directory:
            root = Path(directory)
            work = root / "workspace"
            (work / ".claude").mkdir(parents=True)
            for name in ("empty-auth-home", "tmp", "config", "outside"):
                (root / name).mkdir()
            (work / "CLAUDE.md").write_text("SYNTHETIC_AMBIENT_CONTEXT_DO_NOT_LOAD")
            (work / ".mcp.json").write_text('{"mcpServers":{}}')
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            endpoint = "http://127.0.0.1:" + str(server.server_port)
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            environment = worker_environment(root, auth_home=root / "empty-auth-home")
            environment.update({"CLAUDE_CONFIG_DIR": str(root / "config"), "ANTHROPIC_API_KEY": "synthetic-local-provider-only",
                "ANTHROPIC_BASE_URL": endpoint, "HTTP_PROXY": endpoint, "HTTPS_PROXY": endpoint, "ALL_PROXY": endpoint,
                "NO_PROXY": "127.0.0.1,localhost", "JAVIS_TEST_NATIVE_CLI": str(path)})
            _spawn.original, _spawn.observations, _spawn.roots = subprocess.Popen, [], []
            process = _spawn([sys.executable, "unused-controlled-helper", "--native-worker", str(work)],
                cwd=work, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                start_new_session=False)
            pids, stderr = [], ""
            try:
                if not requested.wait(25):
                    self.fail("Candidate did not reach the local pending query boundary")
                pids = _job_pids(process.qualification_group)
                self.assertIn(process.pid, pids)
                self.assertGreaterEqual(len(pids), 2, "Expected the real candidate child in the owned job")
                process.qualification_group.close()
                _, stderr = process.communicate(timeout=5)
                deadline = time.monotonic() + 5
                while any(_alive(pid) for pid in pids) and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertFalse(any(_alive(pid) for pid in pids))
                self.assertIsNotNone(process.returncode)
            finally:
                process.qualification_group.close()
                if process.poll() is None:
                    process.wait(timeout=5)
                release.set()
                server.shutdown()
                server.server_close()
                for stream in (process.stdin, process.stdout, process.stderr):
                    stream.close()
            spawns = [json.loads(line.split("=", 1)[1]) for line in stderr.splitlines() if line.startswith("qualification-spawn=")]
            self.assertEqual({value["kind"] for value in spawns}, {"version", "query"})
            self.assertTrue(all(value["creationflags"] & worker.winproc.no_window() for value in spawns))
            self.assertEqual(requests.count("/v1/messages"), 1)
            self.assertTrue(dummy_auth and all(dummy_auth))
            self.assertTrue(all(value.split("?", 1)[0] in {"/v1/messages", "/v1/messages/count_tokens"} for value in requests))
            EVIDENCE.append({"scenario": "synthetic/native-pending-query-cancellation", "elapsed_s": round(time.monotonic() - started, 3),
                "production_billing": False, "query_count": 1, "owned_process_count": len(pids), "all_owned_processes_closed": True,
                "sdk_spawn_flags": [value["creationflags"] for value in spawns], "requests": requests,
                "usage_coverage": "unknown: cancelled before synthetic response", "retry_count": 0})


class QualificationEngineeringTests(unittest.TestCase):
    def test_sdk_launch_boundary_hides_version_and_query_spawns_and_restores_itself(self):
        from claude_agent_sdk._internal.transport import subprocess_cli
        import test_improvement_worker as fixtures
        original = AsyncMock(side_effect=["version", "query"])
        payload = fixtures.WorkerProcessTests().payload()

        class Adapter:
            def __init__(self, pin):
                pass

            def verify(self):
                return {"supported": True, "capability_hash": "c" * 64}

        class Engine:
            def __init__(self, **kwargs):
                pass

            async def query(self, prompt):
                await subprocess_cli.anyio.open_process(["pinned", "--version"])
                await subprocess_cli.anyio.open_process(["pinned", "--print"], creationflags=0x200)
                yield {"type": "artifact", "content": "synthetic"}

        async def acknowledge():
            return {"type": "engine_start_ack", "trial_id": "trial-a", "attempt": 1,
                    "input_hash": payload["receipt"]["input_hash"]}

        async def emit(value):
            pass

        async def exercise():
            with patch.object(subprocess_cli.anyio, "open_process", original):
                with patch.object(worker.winproc, "no_window", return_value=0x08000000):
                    await worker.run_request(payload, acknowledge, emit, adapter_factory=Adapter, engine_factory=Engine)
                    self.assertIs(subprocess_cli.anyio.open_process, original)

        asyncio.run(exercise())
        self.assertEqual(original.call_args_list[0].kwargs.get("creationflags", 0), 0x08000000)
        self.assertEqual(original.call_args_list[1].kwargs["creationflags"], 0x08000200)

    def test_sdk_launch_boundary_restores_after_exception_and_handles_posix_zero(self):
        from claude_agent_sdk._internal.transport import subprocess_cli
        original = AsyncMock(side_effect=RuntimeError("synthetic spawn failure"))

        async def exercise():
            with patch.object(subprocess_cli.anyio, "open_process", original), patch.object(worker.winproc, "no_window", return_value=0):
                self.assertTrue(hasattr(worker, "_sdk_hidden_processes"))
                with self.assertRaises(RuntimeError):
                    with worker._sdk_hidden_processes():
                        await subprocess_cli.anyio.open_process(["pinned"])
                self.assertIs(subprocess_cli.anyio.open_process, original)

        asyncio.run(exercise())
        self.assertEqual(original.call_args.kwargs["creationflags"], 0)

    def test_candidate_identity_rejects_arbitrary_files_without_execution(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "not-the-qualified-candidate.exe"
            path.write_bytes(b"synthetic inert unknown binary")
            with patch("subprocess.Popen", side_effect=AssertionError("Unknown executable launched")), \
                 patch("subprocess.run", side_effect=AssertionError("Unknown version/auth launched")):
                with self.assertRaises(ValueError):
                    candidate(path)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--qualification-worker":
        qualification_worker(Path(sys.argv[2]))
    else:
        result = unittest.main(exit=False)
        if EVIDENCE and os.environ.get("JAVIS_TEST_NATIVE_QUALIFICATION_EVIDENCE"):
            target = Path(os.environ["JAVIS_TEST_NATIVE_QUALIFICATION_EVIDENCE"])
            target.write_text(json.dumps({"label": "synthetic/native-technical-qualification-only", "production_billing": False,
                "passed": result.result.wasSuccessful(), "profile_hash": native.profile_hash(), "scenarios": EVIDENCE}, indent=2))
        raise SystemExit(not result.result.wasSuccessful())
