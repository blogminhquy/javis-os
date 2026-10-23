"""A closed trial profile for the existing Claude engine; release capability is gated separately."""
from __future__ import annotations

import hashlib
import asyncio
import importlib.metadata
import json
import math
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import winproc

from improvement_blobs import MAX_ASSET_BYTES, check_ancestry
from improvement_cases import _digest, _fields, _frozen, _text
from improvement_store import _hash, _json
from improvement_native_qualifications import profile_qualification as _profile_qualification

PROFILE_VERSION = "claude-isolated-roles-v2"
PROFILE_SOURCES = ("improvement_claude.py", "improvement_sandbox.py", "improvement_worker.py", "claude_sdk_engine.py",
                   "improvement_native_transport.py", "improvement_operation_adapter.py", "improvement_operation_worker.py",
                   "improvement_operation_profile.py", "improvement_operation_workspace.py", "improvement_operation_protocol.py",
                   "improvement_operation_execution.py", "improvement_operation_evidence.py", "improvement_trial_evidence.py",
                   "improvement_operation_checks.py", "improvement_operation_results.py", "improvement_trial_checks.py",
                   "improvement_operation_runner.py", "improvement_operation_tasks.py", "improvement_operation_recovery.py",
                   "improvement_operation_retry.py", "improvement_operation_schema.py", "improvement_operation_records.py",
                   "improvement_improver_inputs.py", "improvement_generation_protocol.py", "improvement_comparison_plans.py",
                   "improvement_proposals.py", "improvement_skill_candidates.py", "improvement_role_workflow.py",
                   "improvement_semantic_review.py", "improvement_semantic_protocol.py", "improvement_semantic_records.py",
                   "improvement_dependency_evidence.py", "improvement_execution_limits.py", "improvement_native_lifetime.py",
                   "improvement_trials.py", "improvement_trial_host.py", "improvement_trial_records.py", "improvement_trial_admission.py",
                   "improvement_trial_context.py", "improvement_trial_sources.py", "improvement_trial_sql_context.py",
                   "improvement_trial_dashboard.py", "improvement_trial_file_sources.py", "improvement_trial_selection.py",
                   "improvement_trial_service.py", "improvement_trial_associations.py", "improvement_trial_runner.py",
                   "improvement_trial_tasks.py", "improvement_trial_results.py", "improvement_trial_products.py",
                   "improvement_trial_decisions.py", "improvement_trial_views.py", "improvement_trial_schema.py",
                   "improvement_experiment_lineage.py", "improvement_experiment_admission.py", "improvement_experiment_service.py",
                   "improvement_experiment_protocol.py", "improvement_experiment_qualification.py", "improvement_experiments.py",
                   "improvement_experiment_schema.py", "improvement_comparison_results.py", "improvement_comparison_links.py",
                   "improvement_views.py", "improvement_view_sources.py", "improvement_view_history.py", "improvement_view_lineage.py",
                   "improvement_view_trial_protocol.py", "improvement_view_protocol.py", "improvement_view_schema.py",
                   "improvement_store.py", "improvement_blobs.py", "improvement_cases.py", "improvement_case_schema.py",
                   "improvement_candidate_records.py", "improvement_candidate_schema.py", "improvement_skill_patch.py",
                   "improvement_comparison_schedule.py", "improvement_view_admission.py", "improvement_view_materialization.py",
                   "improvement_view_qualification.py", "improvement_view_qualification_history.py",
                   "improvement_skill_asset_broker.py", "improvement_skill_asset_proof.py")
VERIFIED_NATIVE_RUNTIMES = {("win32", "2.1.304",
    "019e5174d5d954585edb1a946fe280e44a973050b4897034adf0e16306f85fdd", "0.2.116"),
    ("win32", "2.1.308", "c9796ba22a9221586b36371b36f5b66198d66eb4badf6a4cf4a5f7b07becea53", "0.2.116"),
    ("win32", "2.1.309", "5441781f2b6bbd07354b4a74560ee88c68c9bf05d6db3c7e24c452c91673dc53", "0.2.116")}


async def _settled_owned(future):
    """Retain an owned operation through repeated caller cancellation."""
    cancelled = None
    while True:
        try:
            return await asyncio.shield(future), cancelled
        except asyncio.CancelledError as error:
            if future.cancelled():
                raise
            cancelled = error


def profile_hash():
    root = Path(__file__).parent
    return _hash({name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in PROFILE_SOURCES})


def _managed_policy():
    """Detect policy presence without reading policy contents or login files."""
    roots = {"win32": Path(r"C:\Program Files\ClaudeCode"),
             "darwin": Path("/Library/Application Support/ClaudeCode"), "linux": Path("/etc/claude-code")}
    if sys.platform not in roots:
        return "unknown"
    paths = [roots[sys.platform] / name for name in ("managed-settings.json", "managed-settings.d", "managed-mcp.json")]
    paths.append(Path.home() / ".claude" / "remote-settings.json")
    try:
        for path in paths:
            try:
                path.lstat()
                return "present"
            except FileNotFoundError:
                pass
        if sys.platform == "win32":
            import winreg
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                for view in (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY):
                    try:
                        with winreg.OpenKey(hive, r"SOFTWARE\Policies\ClaudeCode", 0, winreg.KEY_READ | view):
                            return "present"
                    except FileNotFoundError:
                        pass
        elif sys.platform == "darwin":
            # No macOS native runtime has been verified; do not infer MDM absence from files.
            return "unknown"
    except OSError:
        return "unknown"
    return "absent"


def _runtime_observation(pin):
    from improvement_sandbox import worker_environment
    binary = Path(pin["cli_path"])
    if not binary.is_absolute():
        raise ValueError("invalid_trial_binary")
    check_ancestry(binary)
    with binary.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    managed = _managed_policy()
    result = {"platform": sys.platform, "cli_hash": digest,
              "sdk_version": importlib.metadata.version("claude-agent-sdk"),
              "profile_hash": profile_hash(), "managed_policy": managed, "auth": {}}
    known = (sys.platform, pin["cli_version"], digest, result["sdk_version"])
    if (managed != "absent" or digest != pin["cli_hash"] or known not in VERIFIED_NATIVE_RUNTIMES
            or result["profile_hash"] != pin["profile_hash"] or _profile_qualification(pin, sys.platform) is None):
        return result
    with tempfile.TemporaryDirectory(prefix="improvement-verify-") as scratch:
        environment = worker_environment(Path(scratch))
        version = subprocess.run([str(binary), "--version"], env=environment, capture_output=True,
                                 text=True, timeout=10, check=True, creationflags=winproc.no_window())
        result["cli_version"] = version.stdout.strip().split()[0]
        auth = subprocess.run([str(binary), "auth", "status", "--json"], env=environment, capture_output=True,
                              text=True, timeout=15, check=True, creationflags=winproc.no_window())
        status = json.loads(auth.stdout)
        result["auth"] = {"logged_in": status.get("loggedIn") is True, "method": status.get("authMethod"),
                          "provider": status.get("apiProvider"), "plan": status.get("subscriptionType")}
    return result


class ClaudeTrialAdapter:
    def __init__(self, config_pin, *, workspace_root=None, before_engine_start=None):
        self.pin = _frozen(config_pin)
        _fields(self.pin, {"version", "provider", "engine_id", "model", "reasoning", "cli_path", "cli_hash",
                           "cli_version", "sdk_version", "profile_version", "profile_hash"})
        if type(self.pin["version"]) is not int or self.pin["version"] != 1:
            raise ValueError("unsupported_trial_configuration")
        for name in ("cli_hash", "profile_hash"):
            _digest(self.pin[name])
        for name, value in self.pin.items():
            if name != "version":
                _text(value)
        self.workspace_root = Path(workspace_root) if workspace_root is not None else None
        self.before_engine_start = before_engine_start

    def verify(self):
        requested = {key: self.pin[key] for key in ("provider", "engine_id", "model", "reasoning")}

        def unsupported(reason):
            return {"supported": False, "reason": reason, "requested": requested}

        if (self.pin["provider"] != "anthropic-cli" or self.pin["engine_id"] != "claude-sdk"
                or self.pin["profile_version"] != PROFILE_VERSION
                or self.pin["reasoning"] not in ("low", "medium", "high", "xhigh", "max")):
            return unsupported("unsupported_trial_configuration")
        qualification = _profile_qualification(self.pin, sys.platform)
        if qualification is None:
            return unsupported("native_profile_unqualified")
        try:
            observed = _runtime_observation(self.pin)
        except (OSError, ValueError, IndexError, subprocess.SubprocessError, importlib.metadata.PackageNotFoundError):
            return unsupported("runtime_unavailable")
        if observed.get("managed_policy") != "absent":
            return unsupported("managed_policy_unverified")
        if any(observed.get(field) != self.pin[field] for field in ("cli_hash", "cli_version", "sdk_version", "profile_hash")):
            return unsupported("trial_runtime_drift")
        runtime = tuple(observed.get(key) for key in ("platform", "cli_version", "cli_hash", "sdk_version"))
        if runtime not in VERIFIED_NATIVE_RUNTIMES:
            return unsupported("native_enforcement_unverified")
        if observed.get("auth") != {"logged_in": True, "method": "claude.ai", "provider": "firstParty", "plan": "max"}:
            return unsupported("native_auth_policy_unverified")
        observed = {**observed, "profile_qualification_hash": qualification}
        return {"supported": True, "reason": None, "requested": requested,
                "capability_hash": _hash({"pin": self.pin, "runtime": observed}), "runtime": observed}

    async def execute(self, request, workspace):
        """The parent persists engine start before releasing a query in a clean process."""
        from improvement_sandbox import TrialWorkspace
        if self.workspace_root is None or not callable(self.before_engine_start):
            raise ValueError("trial_start_boundary_unbound")
        request = _frozen(request)
        _fields(request, {"version", "trial_id", "attempt", "deadline_at", "engine_config_hash", "capability_hash"})
        if type(request["version"]) is not int or request["version"] != 1 or type(request["attempt"]) is not int:
            raise ValueError("invalid_trial_execution_request")
        deadline = request["deadline_at"]
        if type(deadline) not in (int, float) or not math.isfinite(deadline) or deadline <= time.time():
            raise ValueError("trial_deadline_expired")
        for name in ("engine_config_hash", "capability_hash"):
            _digest(request[name])
        receipt = _frozen(workspace)
        manifest = await asyncio.to_thread(TrialWorkspace(self.workspace_root).validate, receipt)
        if (request["trial_id"] != receipt["trial_id"] or request["attempt"] != receipt["attempt"]
                or request["engine_config_hash"] != manifest["engine_config_hash"]
                or request["engine_config_hash"] != _hash(self.pin)):
            raise ValueError("trial_configuration_drift")
        verified = await asyncio.to_thread(self.verify)
        if not verified.get("supported") or verified.get("capability_hash") != request["capability_hash"]:
            raise ValueError("trial_capability_drift")
        from improvement_native_transport import execute_worker
        from contextlib import aclosing
        async with aclosing(execute_worker("trial", request, receipt, config_pin=self.pin,
                workspace_root=self.workspace_root, brain_id=manifest['brain_id'], before_engine_start=self.before_engine_start)) as packets:
            async for packet in packets:
                yield packet


class TrialProfile:
    """Host-created options and raw telemetry, used only in an isolated child process."""

    def __init__(self, pin, broker, system_prompt, *, before_query=None):
        self.pin = _frozen(pin)
        _fields(self.pin, {"provider", "model", "reasoning", "cli_path", "sdk_version"})
        if self.pin["provider"] != "anthropic-cli" or self.pin["reasoning"] not in ("low", "medium", "high", "xhigh", "max"):
            raise ValueError("unsupported_trial_configuration")
        for value in self.pin.values():
            _text(value)
        if not isinstance(system_prompt, str) or len(system_prompt.encode()) > MAX_ASSET_BYTES:
            raise ValueError("invalid_trial_system_prompt")
        self.broker, self.system_prompt = broker, system_prompt
        self._before_query = before_query
        self._started = False
        self.observed_models = set()
        self.actual_reasoning_coverage = "unknown"
        self.denials = []
        self._installation = None
        self._selection = None
        self._native_tools = None
        self._native_session_id = None
        self._tool_names = {}
        self._denied_calls = set()
        self._asset_broker = None
        self._pending_asset_events = []
        self._asset_events = []

    def bind_installation(self, manifest, workspace, capability_hash):
        from improvement_sandbox import TrialWorkspace, _manifest, trial_system_prompt
        if self._installation is not None or self._started:
            raise ValueError("trial_installation_already_bound")
        _digest(capability_hash)
        manifest = _manifest(manifest)
        workspace = _frozen(workspace)
        actual = TrialWorkspace(Path(workspace["path"]).parents[1]).validate(workspace)
        if _hash(actual) != _hash(manifest):
            raise ValueError("trial_installation_input_mismatch")
        if (self.broker.grant_hash != manifest["grant_hash"]
                or _hash(list(self.broker.fixtures.values())) != _hash(manifest["case"]["fixtures"])):
            raise ValueError("trial_fixture_installation_mismatch")
        prompt_hash = hashlib.sha256(trial_system_prompt(manifest).encode("utf-8")).hexdigest()
        if hashlib.sha256(self.system_prompt.encode("utf-8")).hexdigest() != prompt_hash:
            raise ValueError("trial_prompt_installation_mismatch")
        self._installation = {"manifest": manifest, "workspace": workspace,
                              "capability_hash": capability_hash, "prompt_hash": prompt_hash}
        if manifest['version'] == 3:
            from improvement_skill_asset_broker import SkillAssetBroker
            self._asset_broker = SkillAssetBroker(manifest, **{
                key: workspace[key] for key in ('trial_id', 'attempt', 'input_hash')})

    def _tools(self):
        return ['mcp__fixture__fixture_read'] + (['mcp__skill__skill_asset_read'] if self._asset_broker is not None else [])

    def installation_receipt(self, session_id, *, pending_events=()):
        if self._installation is None:
            return None
        bound = self._installation
        manifest, workspace = bound["manifest"], bound["workspace"]
        selection = self._selection or {}
        tools = self._tools()
        model_coverage = ("observed" if self.observed_models == {self.pin["model"]}
                          else "mismatch" if self.observed_models else "unknown")
        receipt = {"version": 1, "trial_id": workspace["trial_id"], "attempt": workspace["attempt"], "session_id": session_id,
                "input_hash": workspace["input_hash"], "effective_hash": workspace["effective_hash"],
                "bundle_hash": manifest["bundle_hash"], "contract_hash": manifest["contract_hash"],
                "public_contract_hash": manifest["public_contract"]["hash"], "engine_config_hash": manifest["engine_config_hash"],
                "grant_hash": manifest["grant_hash"], "capability_hash": bound["capability_hash"],
                "baseline_context_hash": manifest["baseline_context"]["hash"],
                "expected_system_prompt_hash": bound["prompt_hash"], "system_prompt_hash": selection.get("system_prompt_hash"),
                "tool_inventory_hash": _hash(tools),
                "observed_tool_inventory_hash": _hash(self._native_tools) if self._native_tools is not None else None,
                "fixture_inventory_hash": _hash([{key: item[key] for key in ("snapshot_id", "hash", "source")}
                                                 for item in manifest["case"]["fixtures"]]),
                "asset_revisions": [{**{key: asset[key] for key in ("id", "path", "hash")}, "available": True,
                                     "selected": self._selection is not None, "observed_use": "unknown"}
                                    for asset in manifest["assets"]],
                "requested": {key: self.pin[key] for key in ("provider", "model", "reasoning")},
                "actual_models": sorted(self.observed_models), "actual_reasoning": None,
                "coverage": {"input": "host_verified", "runtime": "host_verified",
                             "context": manifest["baseline_context"]["coverage"],
                             "prompt": "host_attested" if self._selection is not None else "unknown",
                             "tool_inventory": "observed" if self._native_tools == tools else "unknown",
                             "model": model_coverage, "reasoning": "unknown"}}
        if manifest['version'] in (2, 3):
            receipt.update(version=2, effective_view=_frozen(manifest['effective_view']))
        if manifest['version'] == 3:
            from improvement_skill_asset_proof import correlate_asset_reads
            proof = correlate_asset_reads(manifest, workspace, self._asset_events + list(pending_events))
            receipt.update(version=3, asset_read_proofs=proof['proofs'])
            if proof['verdict'] == 'pass':
                for asset in receipt['asset_revisions']:
                    asset['observed_use'] = 'observed'
        return receipt

    async def before_query(self):
        if self._started:
            raise ValueError("trial_profile_already_used")
        self._started = True
        if self._before_query is None:
            raise RuntimeError("host_engine_start_not_acknowledged")
        await self._before_query()

    def options(self, engine):
        from claude_agent_sdk import ClaudeAgentOptions, PermissionResultDeny, create_sdk_mcp_server, tool
        if engine.session_id:
            raise ValueError("trial_resume_forbidden")
        if self._installation is not None:
            if hashlib.sha256(self.system_prompt.encode("utf-8")).hexdigest() != self._installation["prompt_hash"]:
                raise ValueError("trial_prompt_installation_mismatch")
            if Path(engine.cwd).resolve() != Path(self._installation["workspace"]["path"]).resolve():
                raise ValueError("trial_workspace_installation_mismatch")

        @tool("fixture_read", "Read a pinned authorized fixture by snapshot identity and source version",
              {"snapshot_id": str, "source_version": str})
        async def fixture_read(args):
            if isinstance(args, dict) and set(args) == {"snapshot_id", "source_version"}:
                result = self.broker.read("fixture.read", {"snapshot_id": args["snapshot_id"]},
                                          args["source_version"], self.broker.grant_hash)
            else:
                result = self.broker.read("fixture.read", {}, None, self.broker.grant_hash)
            return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                    "is_error": result["status"] != "fixture_hit"}

        servers = {"fixture": create_sdk_mcp_server("fixture", tools=[fixture_read])}
        if self._asset_broker is not None:
            @tool('skill_asset_read', 'Read the selected immutable trial skill by exact view, asset and content identity',
                  {'view_id': str, 'view_hash': str, 'asset_id': str, 'content_hash': str})
            async def skill_asset_read(args):
                result = self._asset_broker.read(args)
                if result['status'] == 'skill_asset_hit':
                    observation = self._asset_broker.observations[-1]
                    self._pending_asset_events.append(_json({'type': 'skill_asset_broker_observation',
                        'observation': observation, 'session_id': self._native_session_id}))
                return {'content': [{'type': 'text', 'text': _json(result)}],
                        'is_error': result['status'] != 'skill_asset_hit'}
            servers['skill'] = create_sdk_mcp_server('skill', tools=[skill_asset_read])

        async def deny(name, args, context):
            self.denials.append({"type": "tool_denied", "name": str(name), "reason": "outside_trial_fixture_grant"})
            return PermissionResultDeny(message="Only the pinned fixture tool is authorized in this trial")

        options = ClaudeAgentOptions(cli_path=self.pin["cli_path"], cwd=engine.cwd,
            system_prompt=self.system_prompt, model=self.pin["model"], effort=self.pin["reasoning"],
            tools=[], skills=[], setting_sources=[], plugins=[], agents={}, hooks={}, add_dirs=[],
            mcp_servers=servers, strict_mcp_config=True,
            allowed_tools=self._tools(), permission_mode="default", can_use_tool=deny,
            settings='{"fastMode":false,"disableAllHooks":true}',
            extra_args={"no-session-persistence": None, "disable-slash-commands": None, "no-chrome": None,
                        "restricted": None, "safe-mode": None},
            max_buffer_size=8 * 1024 * 1024, stderr=engine._on_stderr)
        self._selection = {"system_prompt_hash": hashlib.sha256(options.system_prompt.encode("utf-8")).hexdigest()}
        return options

    def observe(self, message):
        """Never fabricate a missing usage field or assemble an artifact from narration."""
        from claude_agent_sdk import AssistantMessage, ResultMessage, SystemMessage, ToolUseBlock, UserMessage, ToolResultBlock
        events = [json.loads(event) for event in self._pending_asset_events]
        self._pending_asset_events.clear()
        if isinstance(message, SystemMessage):
            if message.subtype == "init":
                tools = message.data.get("tools")
                if tools is not None:
                    if tools != self._tools():
                        raise ValueError("trial_native_tool_inventory_mismatch")
                    self._native_tools = list(tools)
                self._native_session_id = message.data.get("session_id")
            events.append({"type": "native_system", "subtype": message.subtype, "data": _frozen(message.data)})
        elif isinstance(message, AssistantMessage):
            if message.model:
                self.observed_models.add(message.model)
            events.append({"type": "observation", "model": message.model, "message_id": message.message_id,
                           "usage": _frozen(message.usage), "session_id": message.session_id, "error": message.error})
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    self._tool_names[block.id] = block.name
                    event = {"type": "tool_call", "name": block.name, "id": block.id}
                    if self._asset_broker is not None:
                        event.update(input=_frozen(block.input), session_id=message.session_id or self._native_session_id)
                    events.append(event)
        elif isinstance(message, UserMessage) and isinstance(message.content, list):
            for block in message.content:
                if isinstance(block, ToolResultBlock):
                    name = self._tool_names.get(block.tool_use_id)
                    if name is not None and name not in self._tools():
                        if not block.is_error:
                            raise ValueError("trial_unknown_tool_execution")
                        if block.tool_use_id not in self._denied_calls:
                            denial = {"type": "tool_denied", "name": name, "tool_use_id": block.tool_use_id,
                                      "reason": "tool_unavailable_in_trial"}
                            self._denied_calls.add(block.tool_use_id)
                            self.denials.append(denial)
                            events.append(denial)
                    event = {"type": "tool_result", "id": block.tool_use_id, "is_error": block.is_error}
                    if self._asset_broker is not None:
                        # UserMessage has no session field in the pinned SDK. This
                        # is the initialized client stream, not an invented wire field.
                        event.update(content=_frozen(block.content), native_is_error=block.is_error,
                                     session_id=self._native_session_id)
                    events.append(event)
        elif isinstance(message, ResultMessage):
            if self._native_session_id and self._native_session_id != message.session_id:
                raise ValueError("trial_native_session_mismatch")
            events.append({"type": "usage", "usage": _frozen(message.usage), "cost_usd": message.total_cost_usd,
                           "model_usage": _frozen(message.model_usage), "session_id": message.session_id})
            content = message.result
            artifact_status = "unknown"
            if isinstance(content, str) and len(content.encode("utf-8")) <= MAX_ASSET_BYTES:
                events.append({"type": "artifact", "content": content,
                               "hash": hashlib.sha256(content.encode("utf-8")).hexdigest()})
                artifact_status = "observed"
            receipt = self.installation_receipt(message.session_id, pending_events=events)
            if receipt is not None:
                events.append({"type": "installation_receipt", "receipt": receipt, "hash": _hash(receipt)})
            events.append({"type": "terminal", "subtype": message.subtype, "is_error": message.is_error,
                           "artifact_status": artifact_status, "session_id": message.session_id,
                           "api_error_status": message.api_error_status, "errors": _frozen(message.errors),
                           "actual_models": sorted(self.observed_models), "actual_reasoning_coverage": "unknown"})
        if self._asset_broker is not None:
            self._asset_events.extend(_frozen([event for event in events if event['type'] in
                ('native_system', 'tool_call', 'tool_result', 'skill_asset_broker_observation')]))
        return events
