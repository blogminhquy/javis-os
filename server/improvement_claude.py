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
                   "improvement_compose_schema.py", "improvement_recipe_schema.py", "improvement_recipe_view_schema.py",
                   "improvement_compose_protocol.py", "improvement_harness2_compose.py", "improvement_recipe_sources.py",
                   "improvement_compose_permissions.py", "improvement_compose_inputs.py",
                   "improvement_compositions.py", "improvement_compose_candidates.py",
                   "turn_context.py", "improvement_telemetry.py",
                   "improvement_native_protocol.py",
                   "improvement_improver_inputs.py", "improvement_tuning_history.py", "improvement_generation_protocol.py", "improvement_comparison_plans.py",
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
                   "improvement_skill_asset_broker.py", "improvement_skill_asset_proof.py", "improvement_native_formats.py",
                   "improvement_qualification_session.py", "improvement_qualification_results.py",
                   "improvement_activation_schema.py", "improvement_canary_schema.py",
                   "improvement_routing_schema.py", "improvement_agent_schema.py",
                   "improvement_bundle_schema.py", "improvement_team_schema.py",
                   "improvement_library_schema.py")
VERIFIED_NATIVE_RUNTIMES = {("win32", "2.1.304",
    "019e5174d5d954585edb1a946fe280e44a973050b4897034adf0e16306f85fdd", "0.2.116"),
    ("win32", "2.1.308", "c9796ba22a9221586b36371b36f5b66198d66eb4badf6a4cf4a5f7b07becea53", "0.2.116"),
    ("win32", "2.1.309", "5441781f2b6bbd07354b4a74560ee88c68c9bf05d6db3c7e24c452c91673dc53", "0.2.116"),
    ("win32", "2.1.310", "f9a3920634ae3b961ee92c2eb58d0051f5f8852b120983d0a4f57b6a5efeba61", "0.2.116")}


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


async def _verify_owned(adapter):
    """A cancelled preflight must settle before its caller releases ownership."""
    task = asyncio.create_task(asyncio.to_thread(adapter.verify))
    values, cancelled = await _settled_owned(asyncio.gather(task, return_exceptions=True))
    if cancelled is not None:
        raise cancelled
    if isinstance(values[0], BaseException):
        raise values[0]
    return values[0]


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


def _runtime_identity(pin):
    """Fresh static metadata only; never execute the selected binary."""
    binary = Path(pin["cli_path"])
    if not binary.is_absolute():
        raise ValueError("invalid_trial_binary")
    check_ancestry(binary)
    with binary.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    managed = _managed_policy()
    return {"platform": sys.platform, "cli_hash": digest,
              "sdk_version": importlib.metadata.version("claude-agent-sdk"),
              "profile_hash": profile_hash(), "managed_policy": managed}


def _runtime_observation(pin):
    from improvement_sandbox import worker_environment
    result = {**_runtime_identity(pin), "auth": {}}
    binary, digest = Path(pin["cli_path"]), result['cli_hash']
    known = (sys.platform, pin["cli_version"], digest, result["sdk_version"])
    if (result['managed_policy'] != "absent" or digest != pin["cli_hash"] or known not in VERIFIED_NATIVE_RUNTIMES
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
        self._native_boundary = None

    def bind_native_authority(self, assets, principal, *, scope_hash, current, lock=None):
        if self._native_boundary is not None:
            raise ValueError('native_parent_already_bound')
        from improvement_native_parent import NativeParentBoundary
        self._native_boundary = NativeParentBoundary(self.pin, assets, principal,
            scope_hash=scope_hash, current=current, lock=lock)

    def verify(self):
        if self._native_boundary is not None:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return asyncio.run(self.verify_async())
            raise RuntimeError('native_sync_preflight_in_async_context')
        # A release qualified for the owned boundary cannot silently return to
        # legacy subprocess probes when a service forgot its actual authority.
        from improvement_native_qualifications import REVIEWED_RELEASES
        prefix = (sys.platform, self.pin['cli_version'], self.pin['cli_hash'], self.pin['sdk_version'],
                  self.pin['profile_version'], self.pin['profile_hash'])
        if any(type(key) is tuple and len(key) == 7 and key[:6] == prefix for key in REVIEWED_RELEASES):
            return {'supported': False, 'reason': 'native_host_authority_unbound',
                'requested': {key: self.pin[key] for key in ('provider', 'engine_id', 'model', 'reasoning')}}
        return self._verify_with_observer(lambda: _runtime_observation(self.pin))

    async def verify_async(self):
        if self._native_boundary is not None:
            return await self._native_boundary.verify(self)
        return await _verify_owned(self)

    def admit_preflight(self):
        """Permit guarded observation, never account/query or live capability.

        The isolated consumer must call this before its first CLI command and
        still authenticate actual child observations with verify_observed after
        guarded preflight. Static admission is not auth or execution evidence.
        """
        def refused(reason): return {'admitted': False, 'reason': reason}
        pin = self.pin
        if (pin['provider'] != 'anthropic-cli' or pin['engine_id'] != 'claude-sdk'
                or pin['profile_version'] != PROFILE_VERSION
                or pin['reasoning'] not in ('low', 'medium', 'high', 'xhigh', 'max')):
            return refused('unsupported_trial_configuration')
        qualification = _profile_qualification(pin, sys.platform)
        if qualification is None: return refused('native_profile_unqualified')
        try:
            runtime = _runtime_identity(pin)
        except (OSError, ValueError, importlib.metadata.PackageNotFoundError):
            return refused('runtime_unavailable')
        if runtime['managed_policy'] != 'absent': return refused('managed_policy_unverified')
        if any(runtime[key] != pin[key] for key in ('cli_hash', 'sdk_version', 'profile_hash')):
            return refused('trial_runtime_drift')
        known = (runtime['platform'], pin['cli_version'], runtime['cli_hash'], runtime['sdk_version'])
        if known not in VERIFIED_NATIVE_RUNTIMES: return refused('native_enforcement_unverified')
        return {'admitted': True, 'reason': None, 'runtime': runtime, 'profile_qualification_hash': qualification}

    def verify_observed(self, runtime):
        """Check a qualified consumer's closed observation without another spawn.

        This validates data and the existing registration/configuration gates.
        Actual process/channel provenance must already be established by the
        trusted worker/host consumer; caller-supplied hashes are not authority.
        """
        def observe():
            from improvement_native_protocol import _tree, _fields as closed_fields, _text as closed_text, _digest as closed_digest
            _tree(runtime)
            closed_fields(runtime, {'platform', 'cli_hash', 'sdk_version', 'profile_hash',
                'managed_policy', 'cli_version', 'auth'})
            for field in ('platform', 'sdk_version', 'cli_version'):
                closed_text(runtime[field], 128)
            for field in ('cli_hash', 'profile_hash'):
                closed_digest(runtime[field])
            if type(runtime['managed_policy']) is not str or runtime['managed_policy'] not in ('absent', 'present', 'unknown'):
                raise ValueError('invalid_observed_runtime')
            closed_fields(runtime['auth'], {'logged_in', 'method', 'provider', 'plan'})
            if type(runtime['auth']['logged_in']) is not bool:
                raise ValueError('invalid_observed_runtime')
            for field in ('method', 'provider', 'plan'):
                if runtime['auth'][field] is not None:
                    closed_text(runtime['auth'][field], 128)
            # The isolated preflight carries these pin fields too; compare them
            # to fresh local metadata rather than treating an assertion as an
            # observation of the currently installed source/SDK.
            if (profile_hash() != runtime['profile_hash']
                    or importlib.metadata.version('claude-agent-sdk') != runtime['sdk_version']):
                raise ValueError('observed_runtime_metadata_drift')
            return _frozen(runtime)

        return self._verify_with_observer(observe)

    def _verify_with_observer(self, observe):
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
            observed = observe()
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

    async def execute(self, request, workspace, *, on_closing_observations=None):
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
        if manifest['version'] in (4, 5):
            if self._native_boundary is None:
                raise ValueError('trial_native_parent_unbound')
            from improvement_sandbox import trial_system_prompt
            from contextlib import aclosing
            async with aclosing(self._native_boundary.execute('trial', request, receipt, adapter=self,
                    workspace_root=self.workspace_root, brain_id=manifest['brain_id'],
                    before_engine_start=self.before_engine_start, system_prompt=trial_system_prompt(manifest),
                    tool_policy='pinned_skill' if manifest['version'] == 4 else 'baseline_inline',
                    on_closing_observations=on_closing_observations)) as packets:
                async for packet in packets: yield packet
            return
        if self._native_boundary is not None:
            raise ValueError('trial_native_parent_legacy_input')
        verified = await _verify_owned(self)
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
        self._read_outcome_broker = None
        self._pending_read_observations = []
        self._read_events = []
        self._native_binding = None
        self._native_environment = None

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
        read_broker = None
        if manifest['version'] == 4:
            from improvement_read_outcome_broker import PinnedReadOutcomeBroker
            read_broker = PinnedReadOutcomeBroker(manifest, fixture_broker=self.broker, **{
                key: workspace[key] for key in ('trial_id', 'attempt', 'input_hash')})
        self._installation = {"manifest": manifest, "workspace": workspace,
                              "capability_hash": capability_hash, "prompt_hash": prompt_hash}
        self._read_outcome_broker = read_broker
        if manifest['version'] == 3:
            from improvement_skill_asset_broker import SkillAssetBroker
            self._asset_broker = SkillAssetBroker(manifest, **{
                key: workspace[key] for key in ('trial_id', 'attempt', 'input_hash')})

    def _tools(self):
        return ['mcp__fixture__fixture_read'] + (['mcp__skill__skill_asset_read']
            if self._asset_broker is not None or self._read_outcome_broker is not None else [])

    def bind_native_runtime(self, runtime, *, environment, user_prompt):
        """Install the root-owned native factory for a fresh native input4/5.

        The concrete binding validates the runtime's full configuration, exact
        environment/policy and completed original-stream delivery. This profile
        neither opens a transport nor infers provider acceptance from that proof.
        """
        if (self._installation is None or self._installation['manifest']['version'] not in (4, 5)
                or self._native_binding is not None or self._selection is not None or self._started):
            raise ValueError('trial_native_binding_unavailable')
        from improvement_native_profile import NativeProfileBinding
        workspace = self._installation['workspace']
        policy = {'version': 2, 'cli_path': self.pin['cli_path'], 'model': self.pin['model'],
            'reasoning': self.pin['reasoning'], 'prompt_hash': self._installation['prompt_hash'],
            'cwd': workspace['path'], 'tools': self._tools(),
            'tool_policy': 'pinned_skill' if self._installation['manifest']['version'] == 4 else 'baseline_inline'}
        binding = NativeProfileBinding(runtime, kind='trial', identity={key: workspace[key] for key in
            ('trial_id', 'attempt', 'input_hash')}, data_hash=workspace['input_hash'], user_prompt=user_prompt,
            environment=environment, query_policy=policy)
        self._native_environment = _frozen(environment)
        self._native_binding = binding
        # An INSTANCE hook, absent from every legacy/unbound profile. Failure
        # above cannot leave an ambient-client fallback factory installed.
        self.create_client = binding.create_client

    def _native_required(self):
        if (self._installation is not None and self._installation['manifest']['version'] in (4, 5)
                and self._native_binding is None):
            raise ValueError('trial_native_runtime_unbound')

    def bind_qualification_runtime(self, owner, *, user_prompt):
        if (self._installation is None or self._installation['manifest']['version'] != 5
                or self._native_binding is not None or self._selection is not None or self._started):
            raise ValueError('trial_native_binding_unavailable')
        from improvement_native_profile import NativeProfileBinding
        workspace = self._installation['workspace']
        if (owner._packet['request']['receipt'] != workspace
                or owner._packet['request']['capability_hash'] != self._installation['capability_hash']):
            raise ValueError('qualification_profile_installation_changed')
        policy = dict(version=2, **{key: self.pin[key] for key in ('cli_path', 'model', 'reasoning')},
            prompt_hash=self._installation['prompt_hash'], cwd=workspace['path'], tools=self._tools(), tool_policy='baseline_inline')
        binding = NativeProfileBinding.from_qualification_worker(owner, kind='trial',
            identity={key: workspace[key] for key in ('trial_id', 'attempt', 'input_hash')},
            data_hash=workspace['input_hash'], user_prompt=user_prompt, query_policy=policy)
        self._native_environment = _frozen(owner._packet['environment'])
        self._native_binding = binding
        self.create_client = binding.create_client

    def _read_outcome(self, tool_name, args):
        response = self._read_outcome_broker.read(tool_name, args)
        observation = next(item for item in reversed(self._read_outcome_broker.observations)
                           if item['observation_id'] == response['observation_id'])
        # Keep only immutable host evidence before init; no None or fabricated
        # session field is attached. Association waits for the actual init UUID.
        self._pending_read_observations.append(_json(observation))
        return response

    def _flush_read_observations(self):
        if type(self._native_session_id) is not str or not self._native_session_id:
            return []
        events = [{'type': 'trial_read_broker_observation', 'observation': json.loads(item),
                   'session_id': self._native_session_id} for item in self._pending_read_observations]
        self._pending_read_observations.clear()
        return events

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
        if manifest['version'] in (2, 3, 4):
            receipt.update(version=2, effective_view=_frozen(manifest['effective_view']))
        if manifest['version'] == 3:
            from improvement_skill_asset_proof import correlate_asset_reads
            proof = correlate_asset_reads(manifest, workspace, self._asset_events + list(pending_events))
            receipt.update(version=3, asset_read_proofs=proof['proofs'])
            if proof['verdict'] == 'pass':
                for asset in receipt['asset_revisions']:
                    asset['observed_use'] = 'observed'
        if manifest['version'] == 4:
            from improvement_read_outcome_proof import correlate_read_outcomes, SKILL_TOOL
            proof = correlate_read_outcomes(manifest, workspace,
                [json.loads(event) for event in self._read_events] + list(pending_events))
            delivery = None if self._native_binding is None else self._native_binding.completed_delivery
            receipt.update(version=4, read_outcome_proofs=proof['proofs'], native_input_delivery=_frozen(delivery))
            if proof['verdict'] == 'pass':
                for asset in receipt['asset_revisions']:
                    if any(item['tool_name'] == SKILL_TOOL and item['outcome'] == 'hit'
                           and item['resource_id'] == asset['id'] for item in proof['proofs']):
                        asset['observed_use'] = 'observed'
        if manifest['version'] == 5:
            delivery = None if self._native_binding is None else self._native_binding.completed_delivery
            receipt.update(version=5, native_input_delivery=_frozen(delivery))
        return receipt

    async def before_query(self):
        self._native_required()
        if self._started:
            raise ValueError("trial_profile_already_used")
        self._started = True
        if self._before_query is None:
            raise RuntimeError("host_engine_start_not_acknowledged")
        await self._before_query()

    def options(self, engine):
        self._native_required()
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
            if self._read_outcome_broker is not None:
                result = self._read_outcome('mcp__fixture__fixture_read', args)
                return {'content': [{'type': 'text', 'text': _json(result)}], 'is_error': result['outcome'] != 'hit'}
            if isinstance(args, dict) and set(args) == {"snapshot_id", "source_version"}:
                result = self.broker.read("fixture.read", {"snapshot_id": args["snapshot_id"]},
                                          args["source_version"], self.broker.grant_hash)
            else:
                result = self.broker.read("fixture.read", {}, None, self.broker.grant_hash)
            return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                    "is_error": result["status"] != "fixture_hit"}

        servers = {"fixture": create_sdk_mcp_server("fixture", tools=[fixture_read])}
        if self._asset_broker is not None or self._read_outcome_broker is not None:
            @tool('skill_asset_read', 'Read the selected immutable trial skill by exact view, asset and content identity',
                  {'view_id': str, 'view_hash': str, 'asset_id': str, 'content_hash': str})
            async def skill_asset_read(args):
                if self._read_outcome_broker is not None:
                    result = self._read_outcome('mcp__skill__skill_asset_read', args)
                    return {'content': [{'type': 'text', 'text': _json(result)}], 'is_error': result['outcome'] != 'hit'}
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
        if self._native_binding is not None:
            options.env = _frozen(self._native_environment)
        self._selection = {"system_prompt_hash": hashlib.sha256(options.system_prompt.encode("utf-8")).hexdigest()}
        return options

    def observe(self, message):
        """Never fabricate a missing usage field or assemble an artifact from narration."""
        from claude_agent_sdk import AssistantMessage, ResultMessage, SystemMessage, ToolUseBlock, UserMessage, ToolResultBlock
        events = [json.loads(event) for event in self._pending_asset_events]
        self._pending_asset_events.clear()
        if self._read_outcome_broker is not None and not (isinstance(message, SystemMessage) and message.subtype == 'init'):
            events.extend(self._flush_read_observations())
        if isinstance(message, SystemMessage):
            if message.subtype == "init":
                tools = message.data.get("tools")
                if tools is not None:
                    if tools != self._tools():
                        raise ValueError("trial_native_tool_inventory_mismatch")
                    self._native_tools = list(tools)
                self._native_session_id = message.data.get("session_id")
            events.append({"type": "native_system", "subtype": message.subtype, "data": _frozen(message.data)})
            if self._read_outcome_broker is not None and message.subtype == 'init':
                # Host association uses this actual exclusive stream init; emit
                # it first so early SDK handler execution cannot precede init.
                events.extend(self._flush_read_observations())
        elif isinstance(message, AssistantMessage):
            if message.model:
                self.observed_models.add(message.model)
            events.append({"type": "observation", "model": message.model, "message_id": message.message_id,
                           "usage": _frozen(message.usage), "session_id": message.session_id, "error": message.error})
            for block in message.content:
                if isinstance(block, ToolUseBlock):
                    self._tool_names[block.id] = block.name
                    event = {"type": "tool_call", "name": block.name, "id": block.id}
                    if self._asset_broker is not None or self._read_outcome_broker is not None:
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
                    if self._asset_broker is not None or self._read_outcome_broker is not None:
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
        if self._read_outcome_broker is not None:
            self._read_events.extend(_json(event) for event in events if event['type'] in
                ('native_system', 'tool_call', 'tool_result', 'trial_read_broker_observation'))
        return events
