"""Adaptive Runtime Phase 7: multi-round, read-only orchestrator.

Planner chỉ thấy manifest tóm tắt. Exact JSON Schema chỉ xuất hiện trong argument round của
từng step. Task State được checkpoint mã hoá, tool read có thể chạy song song theo DAG và
resume đối chiếu invocation/evidence ledger trước khi quyết định chạy lại.
"""
from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import json
import math
import re
import time
import unicodedata
from dataclasses import dataclass, replace
from typing import Any, AsyncIterator, Awaitable, Callable, Optional

from jsonschema import Draft202012Validator

import capability_resolver
import context_compiler
import context_runtime
import engine
import fast_path_runtime
import secrets_store
from capability_executor import CapabilityExecutor


ORCHESTRATOR_POLICY_VERSION = "readonly-orchestrator-v1"
STATE_SCHEMA_VERSION = 1
Discoverer = Callable[[str, str], Awaitable[tuple[list[dict], dict]]]
Emitter = Callable[[str, dict], Awaitable[None]]
FinalGenerator = Callable[[str, str, str, list[dict], str], AsyncIterator[dict]]


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return int(default)


def _float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else float(default)
    except (TypeError, ValueError, OverflowError):
        return float(default)


def _rule_hash(rule: dict) -> str:
    """Băm toàn bộ giá trị của quota rule, không chỉ `id`."""
    return hashlib.sha256(json.dumps(
        rule, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8", errors="replace")).hexdigest()


def _norm(value: str) -> str:
    # "đ" không phân rã qua NFKD - map tay để deny-pattern ASCII khớp tiếng Việt có dấu.
    raw = str(value or "").replace("đ", "d").replace("Đ", "D")
    raw = unicodedata.normalize("NFKD", raw.casefold())
    return " ".join("".join(c for c in raw if not unicodedata.combining(c)).split())


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


_STATE_REF = re.compile(
    r"\b(truoc day|lan truoc|vua roi|cai do|cai nay|nhu cu|tiep tuc|nho khong|"
    r"previously|earlier|last time|remember|that one|same as before)\b"
)
_WRITE_INTENT = re.compile(
    r"\b(gui|send|xoa|delete|remove|huy|cancel|tao|create|cap nhat|update|sua|edit|"
    r"dang bai|publish|upload|dat lich|book|write|post)\b"
)


@dataclass(frozen=True)
class OrchestratorPolicy:
    mode: str
    allocation_basis_points: int
    salt: str
    channels: tuple[str, ...]
    provider_kinds: tuple[str, ...]
    registry_max_age_seconds: int
    min_resolver_score: float
    estimator_safety_factor: float
    max_candidate_manifests: int
    max_cycles: int
    max_total_steps: int
    max_parallel: int
    max_model_rounds: int
    max_evidence: int
    max_task_input_tokens: int
    max_task_output_tokens: int
    max_cost_usd: float
    max_deadline_extensions: int
    deadline_seconds: int
    planner_output_tokens: int
    argument_output_tokens: int
    min_information_gain: float
    per_evidence_excerpt_chars: int
    failure_repeat_limit: int
    capability_profiles: tuple[dict, ...]
    quota_profiles: tuple[dict, ...]
    version: str

    @classmethod
    def from_settings(cls, settings: dict) -> "OrchestratorPolicy":
        runtime = (settings or {}).get("context_runtime") or {}
        raw = runtime.get("orchestrator_canary")
        raw = raw if isinstance(raw, dict) else {}
        quotas = raw.get("quota_profiles") or ((runtime.get("canary") or {}).get(
            "quota_profiles") or [])
        profiles = tuple(
            dict(x) for x in (raw.get("capability_profiles") or [])
            if isinstance(x, dict) and str(x.get("id") or "").strip()
        )
        return cls(
            mode=str(raw.get("mode", runtime.get("mode", "off"))).lower(),
            allocation_basis_points=max(
                0, min(_int(raw.get("allocation_basis_points"), 0), 10_000)
            ),
            salt=str(raw.get("salt") or ORCHESTRATOR_POLICY_VERSION),
            channels=tuple(str(x) for x in (raw.get("channels") or ["dashboard"])),
            provider_kinds=tuple(str(x) for x in (raw.get("provider_kinds") or ["api"])),
            registry_max_age_seconds=max(
                1, min(_int(raw.get("registry_max_age_seconds"), 900), 86_400)
            ),
            min_resolver_score=max(
                0.0, min(_float(raw.get("min_resolver_score"), 0.32), 1.0)
            ),
            estimator_safety_factor=max(
                1.0, min(_float(raw.get("estimator_safety_factor"), 1.35), 3.0)
            ),
            max_candidate_manifests=max(
                2, min(_int(raw.get("max_candidate_manifests"), 8), 16)
            ),
            max_cycles=max(1, min(_int(raw.get("max_cycles"), 2), 4)),
            max_total_steps=max(2, min(_int(raw.get("max_total_steps"), 6), 12)),
            max_parallel=max(1, min(_int(raw.get("max_parallel"), 3), 6)),
            max_model_rounds=max(4, min(_int(raw.get("max_model_rounds"), 10), 24)),
            max_evidence=max(2, min(_int(raw.get("max_evidence"), 8), 16)),
            max_task_input_tokens=max(
                1000, min(_int(raw.get("max_task_input_tokens"), 20_000), 500_000)
            ),
            max_task_output_tokens=max(
                500, min(_int(raw.get("max_task_output_tokens"), 6_000), 100_000)
            ),
            max_cost_usd=max(0.0, min(_float(raw.get("max_cost_usd"), 0.05), 1000.0)),
            max_deadline_extensions=max(0, min(_int(raw.get("max_deadline_extensions"), 2), 10)),
            deadline_seconds=max(10, min(_int(raw.get("deadline_seconds"), 90), 900)),
            planner_output_tokens=max(
                100, min(_int(raw.get("planner_output_tokens"), 600), 4000)
            ),
            argument_output_tokens=max(
                100, min(_int(raw.get("argument_output_tokens"), 500), 4000)
            ),
            min_information_gain=max(
                0.0, min(_float(raw.get("min_information_gain"), 0.20), 1.0)
            ),
            per_evidence_excerpt_chars=max(
                300, min(_int(raw.get("per_evidence_excerpt_chars"), 2500), 10_000)
            ),
            failure_repeat_limit=max(
                1, min(_int(raw.get("failure_repeat_limit"), 2), 5)
            ),
            capability_profiles=profiles,
            quota_profiles=tuple(dict(x) for x in quotas if isinstance(x, dict)),
            version=str(raw.get("policy_version") or ORCHESTRATOR_POLICY_VERSION)[:120],
        )

    def capability_profile(self, capability: dict) -> Optional[dict]:
        matches = []
        for item in self.capability_profiles:
            if not fnmatch.fnmatchcase(
                    str(capability.get("source_type") or ""),
                    str(item.get("source_type") or "*")):
                continue
            if not fnmatch.fnmatchcase(
                    str(capability.get("name") or ""),
                    str(item.get("name_pattern") or "*")):
                continue
            if not fnmatch.fnmatchcase(
                    str(capability.get("capability_id") or ""),
                    str(item.get("capability_id_pattern") or "*")):
                continue
            matches.append(item)
        if not matches:
            return None
        matches.sort(key=lambda x: (
            -_int(x.get("priority"), 0),
            -len(str(x.get("capability_id_pattern") or "")),
            -len(str(x.get("name_pattern") or "")), str(x.get("id") or ""),
        ))
        return dict(matches[0])

    def quota_rule(self, provider: str, model: str) -> Optional[dict]:
        matches = []
        for index, item in enumerate(self.quota_profiles):
            if str(item.get("provider") or "").lower() != str(provider or "").lower():
                continue
            pattern = str(item.get("model_pattern") or item.get("model") or "")
            if not pattern or not fnmatch.fnmatchcase(str(model or ""), pattern):
                continue
            reserved = max(1, _int(item.get("reserved_output_tokens"), 0))
            hard_input = _int(item.get("max_input_tokens"), 0)
            window = _int(item.get("context_window"), 0)
            if hard_input <= 0 and window > reserved:
                hard_input = window - reserved
            rolling = _int(item.get("rolling_tpm"), 0)
            input_cost = _float(item.get("input_cost_per_million"), -1)
            output_cost = _float(item.get("output_cost_per_million"), -1)
            if (rolling <= 0 or hard_input <= 0 or input_cost < 0 or output_cost < 0):
                continue
            matches.append({
                **item, "_index": index, "rolling_tpm": rolling,
                "hard_max_input_tokens": hard_input,
                "reserved_output_tokens": reserved,
                "window_seconds": max(1, min(_int(item.get("window_seconds"), 60), 3600)),
                "input_cost_per_million": input_cost,
                "output_cost_per_million": output_cost,
                "id": str(item.get("id") or f"orchestrator-quota-{index + 1}")[:120],
            })
        if not matches:
            return None
        matches.sort(key=lambda x: (
            -_int(x.get("priority"), 0),
            -len(str(x.get("model_pattern") or x.get("model") or "")),
            str(x.get("id") or ""),
        ))
        return matches[0]


@dataclass(frozen=True)
class OrchestratorAdmission:
    action: str
    reason: str
    execution_path: str = "unassigned"
    bucket: Optional[int] = None
    trace: context_runtime.TurnTrace | None = None
    objective: str = ""
    brain: str = ""
    channel: str = "dashboard"
    provider: str = ""
    model: str = ""
    actor_id: str = ""
    policy: OrchestratorPolicy | None = None
    quota_rule: dict | None = None
    candidates: tuple[dict, ...] = ()
    profiles: dict | None = None
    routes: dict | None = None
    compile_request: context_compiler.CompileRequest | None = None
    estimated_input_tokens: int = 0
    reserved_output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    rejection_message: str = ""


@dataclass(frozen=True)
class OrchestratorResult:
    text: str
    model: str
    status: str
    task_id: str
    stop_reason: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    evidence_refs: tuple[str, ...]
    model_rounds: int = 0


class ReadonlyOrchestrator:
    def __init__(self, registry, resolver, compiler, runtime,
                 executor: CapabilityExecutor, settings_reader: Callable[[], dict],
                 discoverer: Discoverer, quality_gate=None,
                 state_encryptor: Callable[[str], str] | None = None,
                 state_decryptor: Callable[[str], str] | None = None):
        self.registry = registry
        self.resolver = resolver
        self.compiler = compiler
        self.runtime = runtime
        self.executor = executor
        self.settings_reader = settings_reader
        self.discoverer = discoverer
        self.quality_gate = quality_gate or context_compiler.get_quality_gate()
        self.state_encryptor = state_encryptor or secrets_store.encrypt_required
        self.state_decryptor = state_decryptor or secrets_store.decrypt

    @staticmethod
    async def _emit(emitter: Emitter | None, event_type: str, payload: dict) -> None:
        if emitter is not None:
            await emitter(event_type, payload)

    @staticmethod
    def _plan(action: str, reason: str, policy: OrchestratorPolicy,
              trace=None, bucket=None, path="unassigned", rejection=""):
        return OrchestratorAdmission(
            action, reason, path, bucket=bucket, trace=trace, policy=policy,
            rejection_message=rejection,
        )

    def _legacy(self, trace, policy, bucket, reason):
        path = self.runtime.pin_execution_path(
            trace, "legacy", bucket, policy.version, reason
        ) if trace else "legacy"
        return self._plan("legacy", reason, policy, trace, bucket, path)

    async def _refresh_full(self, trace, brain: str, reason: str) -> bool:
        try:
            tools, routes = await self.discoverer("refresh_full", brain)
            # refresh_tools giữ registry lock + ghi SQLite: chạy ngoài event loop.
            refreshed = await asyncio.to_thread(self.registry.refresh_tools, brain, tools, routes)
            revision = str(refreshed.get("revision") or self.registry.revision(brain))
            if revision != trace.registry_revision:
                return self.runtime.rebase_registry_revision(trace, revision, reason)
            return True
        except Exception as exc:
            self.runtime.record_runtime_event(trace, "orchestrator.discovery_failed", {
                "mode": "full", "error_type": type(exc).__name__,
            })
            return False

    def _resolve_candidates(self, trace, objective: str, brain: str, channel: str,
                            policy: OrchestratorPolicy) -> tuple[list[dict], str]:
        result = self.resolver.resolve(
            objective, brain,
            capability_resolver.ActorPolicy(
                mode="readonly", channel=channel,
                allowed_effects=frozenset({"none", "read"}),
            ),
        )
        self.runtime.record_runtime_event(trace, "resolver.orchestrator", {
            "policy_version": result.get("policy_version") or "",
            "registry_revision": result.get("registry_revision") or "",
            "candidate_count": result.get("candidate_count", 0),
            "ranked_count": result.get("ranked_count", 0),
            "miss_class": result.get("miss_class") or "",
        })
        if result.get("miss_class"):
            return [], "higher_ranked_capability_blocked"
        ranked = [x for x in (result.get("ranked") or result.get("selected") or [])
                  if float(x.get("score") or 0) >= policy.min_resolver_score]
        ids = [str(x.get("capability_id") or "") for x in ranked
               if x.get("capability_id")][:policy.max_candidate_manifests]
        score_by_id = {str(x.get("capability_id")): float(x.get("score") or 0)
                       for x in ranked}
        records = self.registry.get_capabilities(ids, brain)
        out = []
        for item in records:
            if (item.get("side_effect") not in ("none", "read") or
                    item.get("required_mode") != "readonly"):
                continue
            profile = policy.capability_profile(item)
            if profile is None:
                continue
            out.append({**item, "score": score_by_id.get(item["capability_id"], 0.0),
                        "_profile": profile})
        out.sort(key=lambda x: (-float(x.get("score") or 0), x["capability_id"]))
        if len(out) < 2:
            return out, "insufficient_multi_read_candidates"
        return out[:policy.max_candidate_manifests], ""

    async def _live_routes(self, trace, brain: str, candidates: list[dict]) -> tuple[dict, str]:
        try:
            tools, routes = await self.discoverer("readonly", brain)
        except Exception as exc:
            self.runtime.record_runtime_event(trace, "orchestrator.discovery_failed", {
                "mode": "readonly", "error_type": type(exc).__name__,
            })
            return {}, "readonly_discovery_failed"
        by_name = {str(x.get("fn") or x.get("name") or ""): x for x in tools}
        accepted = {}
        for item in candidates:
            tool = by_name.get(item["name"])
            route = routes.get(item["name"])
            live_hash = self.registry.schema_hash((tool or {}).get("schema") or {})
            if (not tool or not isinstance(route, dict) or
                    live_hash != item.get("schema_hash")):
                return {}, "schema_revision_mismatch"
            if (str(route.get("effect") or "read") not in ("none", "read") or
                    str(route.get("required_mode") or "readonly") != "readonly" or
                    not callable(route.get("call"))):
                return {}, "readonly_route_invalid"
            accepted[item["capability_id"]] = route
        return accepted, ""

    @staticmethod
    def _cost(rule: dict, input_tokens: int, output_tokens: int) -> float:
        return (
            max(0, int(input_tokens)) * float(rule["input_cost_per_million"]) +
            max(0, int(output_tokens)) * float(rule["output_cost_per_million"])
        ) / 1_000_000.0

    def _request(self, trace, objective: str, brain: str, channel: str,
                 provider: str, model: str, rule: dict,
                 policy: OrchestratorPolicy) -> context_compiler.CompileRequest:
        return context_compiler.CompileRequest(
            task_id=trace.task_id, step_id=trace.step_id, objective=objective,
            brain=brain, channel=channel, provider=provider, model=model,
            model_kind="api", task_tokens_remaining=policy.max_task_input_tokens,
            rolling_tpm_remaining=rule["rolling_tpm"],
            latency_deadline_ms=policy.deadline_seconds * 1000,
            monetary_remaining=policy.max_cost_usd,
            hard_max_input_tokens=rule["hard_max_input_tokens"],
            reserved_output_tokens=rule["reserved_output_tokens"],
            execution_mode="canary",
        )

    async def prepare(self, trace: context_runtime.TurnTrace | None, objective: str,
                      brain: str, channel: str, provider: str, model: str,
                      provider_kind: str, actor_id: str,
                      has_attachments: bool = False) -> OrchestratorAdmission:
        try:
            policy = OrchestratorPolicy.from_settings(self.settings_reader() or {})
        except Exception:
            policy = OrchestratorPolicy.from_settings({})
        if not trace:
            return self._plan("not_applicable", "trace_unavailable", policy)
        bucket = fast_path_runtime.stable_bucket(trace.session_id, policy.salt)
        if policy.mode not in ("canary", "on"):
            return self._plan("not_applicable", "mode_not_canary", policy, trace, bucket)
        if policy.allocation_basis_points <= bucket:
            return self._plan("not_applicable", "outside_allocation", policy, trace, bucket)
        if channel not in policy.channels or provider_kind not in policy.provider_kinds:
            return self._plan("not_applicable", "route_not_allowed", policy, trace, bucket)
        if has_attachments:
            return self._legacy(trace, policy, bucket, "attachment_present")
        normalized = _norm(objective)
        if _STATE_REF.search(normalized):
            return self._legacy(trace, policy, bucket, "conversation_state_required")
        if _WRITE_INTENT.search(normalized):
            return self._legacy(trace, policy, bucket, "write_intent")
        if not self.executor.evidence_store.ready():
            return self._legacy(trace, policy, bucket, "evidence_store_unavailable")
        rule = policy.quota_rule(provider, model)
        if rule is None or policy.max_cost_usd <= 0:
            return self._legacy(trace, policy, bucket, "task_budget_metadata_unknown")

        inventory = self.registry.inventory_status(brain)
        age = inventory.get("age_seconds")
        persisted_task = self.runtime.get_task(trace.task_id) or {}
        if (inventory.get("ready") and
                persisted_task.get("registry_revision") != inventory.get("revision")):
            if not self.runtime.rebase_registry_revision(
                    trace, str(inventory.get("revision") or ""),
                    "orchestrator_task_pin_sync"):
                return self._legacy(trace, policy, bucket, "registry_pin_sync_failed")
        if (not inventory.get("ready") or age is None or
                age > policy.registry_max_age_seconds or
                inventory.get("revision") != trace.registry_revision):
            if not await self._refresh_full(trace, brain, "orchestrator_preflight_refresh"):
                return self._legacy(trace, policy, bucket, "registry_refresh_failed")

        candidates, error = await asyncio.to_thread(
            self._resolve_candidates, trace, objective, brain, channel, policy
        )
        if error == "insufficient_multi_read_candidates":
            return self._plan("not_applicable", error, policy, trace, bucket)
        if error:
            return self._legacy(trace, policy, bucket, error)
        routes, route_error = await self._live_routes(trace, brain, candidates)
        if route_error == "schema_revision_mismatch":
            if not await self._refresh_full(trace, brain, "orchestrator_schema_mismatch"):
                return self._legacy(trace, policy, bucket, "schema_refresh_failed")
            candidates, error = await asyncio.to_thread(
                self._resolve_candidates, trace, objective, brain, channel, policy
            )
            if error:
                return self._legacy(trace, policy, bucket, "schema_reresolve_failed")
            routes, route_error = await self._live_routes(trace, brain, candidates)
        if route_error:
            return self._legacy(trace, policy, bucket, route_error)

        request = self._request(
            trace, objective, brain, channel, provider, model, rule, policy
        )
        manifests = [{k: x.get(k) for k in (
            "capability_id", "name", "summary", "capability_revision", "score"
        )} for x in candidates]
        planner = self.compiler.compile_orchestrator_plan(
            request, manifests, [], policy.max_total_steps
        )
        if planner.status != "compiled" or planner.capsule is None:
            # Budget của compiler = min(hard input, task budget - output reserve,
            # rolling - reserve). Nếu chính task budget là ràng buộc đang cắt thì
            # báo đúng mã task_budget để trace và người dùng biết nguyên nhân thật.
            task_bound = max(1, policy.max_task_input_tokens - int(rule["reserved_output_tokens"]))
            binding_task_budget = (
                int(planner.trace_report.get("max_input_tokens") or 0) <= task_bound
            )
            return self._plan(
                "reject",
                "task_budget_preflight_rejected" if binding_task_budget
                else "orchestrator_planner_compile_rejected",
                policy, trace, bucket, "orchestrator",
                "Planner capsule vượt budget đã xác minh. Javis chưa gọi model hoặc tool.",
            )
        exact_estimates = []
        for item in candidates:
            one = {"selected": [{"capability_id": item["capability_id"]}], "miss_class": ""}
            compiled = self.compiler.compile_canary(request, one)
            if (compiled.status != "compiled" or compiled.capsule is None or
                    compiled.trace_report.get("selected_count") != 1):
                continue
            exact_estimates.append(int(compiled.trace_report.get("estimated_input_tokens") or 0))
        if len(exact_estimates) < 2:
            return self._legacy(trace, policy, bucket, "exact_schema_budget_insufficient")
        placeholder = []
        for index in range(min(policy.max_evidence, policy.max_total_steps)):
            placeholder.append({
                "evidence_ref": f"evidence://task/placeholder/step/{index}/ev_placeholder",
                "source_type": "capability_read", "capability_id": f"placeholder-{index}",
                "capability_name": "placeholder", "capability_revision": "0" * 64,
                "content_hash": "0" * 64,
                "excerpt": "\\" * policy.per_evidence_excerpt_chars,
            })
        final_compile = self.compiler.compile_evidence_bundle_final(request, placeholder)
        if final_compile.status != "compiled" or final_compile.capsule is None:
            return self._plan(
                "reject", "task_budget_preflight_rejected", policy, trace, bucket,
                "orchestrator",
                "Evidence bundle dự kiến vượt budget. Javis chưa gọi model hoặc tool.",
            )
        worst_input = int(math.ceil((
            int(planner.trace_report.get("estimated_input_tokens") or 0) +
            max(exact_estimates) * policy.max_total_steps +
            int(final_compile.trace_report.get("estimated_input_tokens") or 0)
        ) * policy.estimator_safety_factor))
        worst_output = (
            policy.planner_output_tokens * policy.max_cycles +
            policy.argument_output_tokens * policy.max_total_steps +
            int(rule["reserved_output_tokens"])
        )
        estimated_cost = self._cost(rule, worst_input, worst_output)
        if (worst_input > policy.max_task_input_tokens or
                worst_output > policy.max_task_output_tokens or
                estimated_cost > policy.max_cost_usd):
            return self._plan(
                "reject", "task_budget_preflight_rejected", policy, trace, bucket,
                "orchestrator",
                "Task read-only nhiều bước vượt token hoặc monetary budget. "
                "Javis chưa gọi model hoặc tool.",
            )
        path = self.runtime.pin_execution_path(
            trace, "orchestrator", bucket, policy.version,
            "multi_read_admission_candidate",
        )
        if path != "orchestrator":
            return self._plan("legacy", "task_already_pinned", policy, trace, bucket, path)
        return OrchestratorAdmission(
            "execute", "admitted", path, bucket=bucket, trace=trace,
            objective=objective, brain=brain, channel=channel, provider=provider,
            model=model, actor_id=actor_id, policy=policy, quota_rule=rule,
            candidates=tuple(candidates),
            profiles={x["capability_id"]: x["_profile"] for x in candidates},
            routes=routes, compile_request=request,
            estimated_input_tokens=worst_input, reserved_output_tokens=worst_output,
            estimated_cost_usd=estimated_cost,
        )

    def _state_text(self, state: dict) -> tuple[str, str]:
        raw = json.dumps(state, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), default=str)
        return self.state_encryptor(raw), hashlib.sha256(
            raw.encode("utf-8", errors="replace")
        ).hexdigest()

    def _checkpoint(self, trace, state: dict, initialize: bool = False) -> bool:
        encrypted, digest = self._state_text(state)
        if initialize:
            objective_encrypted = self.state_encryptor(state["objective"])
            return self.runtime.initialize_orchestrator(
                trace, state["actor_hash"], objective_encrypted, encrypted, digest,
                state["status"], state["budget"], state["deadline_at"],
            )
        return self.runtime.checkpoint_orchestrator(
            trace, encrypted, digest, state["status"]
        )

    @staticmethod
    def _initial_state(plan: OrchestratorAdmission) -> dict:
        policy, rule, trace = plan.policy, plan.quota_rule, plan.trace
        now = time.time()
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "policy_version": policy.version,
            "quota_rule_id": rule["id"],
            # Pin theo NỘI DUNG, không theo nhãn: operator đổi rolling_tpm/giá/cửa sổ
            # mà giữ nguyên `id` (hoặc sửa policy mà quên bump policy_version) thì task
            # đang chạy KHÔNG được âm thầm nhận giá trị mới.
            "quota_rule_hash": _rule_hash(rule),
            "model_profile_revision": trace.model_profile_revision,
            "task_id": trace.task_id, "session_id": trace.session_id,
            "objective": plan.objective, "brain": plan.brain, "channel": plan.channel,
            "provider": plan.provider, "model": plan.model,
            "actor_hash": CapabilityExecutor.actor_hash(plan.actor_id),
            "registry_revision": trace.registry_revision,
            "status": "CREATED", "cycle": 0, "model_rounds": 0,
            "candidate_ids": [x["capability_id"] for x in plan.candidates],
            "used_capability_ids": [], "steps": [], "evidence": [],
            "failure_signatures": {}, "stop_reason": "", "final_text": "",
            "created_at": now, "deadline_at": now + policy.deadline_seconds,
            "deadline_extensions": 0,
            "budget": {
                "max_input_tokens": policy.max_task_input_tokens,
                "max_output_tokens": policy.max_task_output_tokens,
                "max_cost_usd": policy.max_cost_usd,
                "used_input_tokens": 0, "used_output_tokens": 0,
                "used_cost_usd": 0.0, "max_model_rounds": policy.max_model_rounds,
                "estimated_worst_input_tokens": plan.estimated_input_tokens,
                "estimated_worst_output_tokens": plan.reserved_output_tokens,
            },
        }

    @staticmethod
    def _child_trace(parent: context_runtime.TurnTrace, step_id: str):
        return context_runtime.TurnTrace(
            task_id=parent.task_id, step_id=step_id,
            session_id=parent.session_id, channel=parent.channel,
            expected_version=parent.expected_version,
            registry_revision=parent.registry_revision,
            model_profile_revision=parent.model_profile_revision,
            execution_path="orchestrator", canary_bucket=parent.canary_bucket,
            canary_policy_version=parent.canary_policy_version,
        )

    def _budget_allows(self, plan, state: dict, estimates: list[tuple[int, int]]) -> bool:
        budget = state["budget"]
        add_in = sum(max(0, x[0]) for x in estimates)
        add_out = sum(max(0, x[1]) for x in estimates)
        if state["model_rounds"] + len(estimates) > budget["max_model_rounds"]:
            return False
        if budget["used_input_tokens"] + add_in > budget["max_input_tokens"]:
            return False
        if budget["used_output_tokens"] + add_out > budget["max_output_tokens"]:
            return False
        projected = budget["used_cost_usd"] + self._cost(
            plan.quota_rule, add_in, add_out
        )
        return projected <= budget["max_cost_usd"] and time.time() < state["deadline_at"]

    def _admit_batch(self, plan, state: dict,
                     calls: list[tuple[context_runtime.TurnTrace, int, int]]) -> list[str]:
        estimates = [(x[1], x[2]) for x in calls]
        if not self._budget_allows(plan, state, estimates):
            return []
        reservations = []
        for trace, input_tokens, output_tokens in calls:
            admission = self.runtime.admit_quota(
                trace, plan.provider, plan.model,
                int(math.ceil(input_tokens * plan.policy.estimator_safety_factor)),
                output_tokens, plan.quota_rule["rolling_tpm"],
                plan.quota_rule["window_seconds"],
            )
            if not admission.allowed:
                for old_trace, reservation_id in zip(
                        [x[0] for x in calls], reservations):
                    self.runtime.release_quota(old_trace, reservation_id, "batch_admission_failed")
                return []
            reservations.append(admission.reservation_id)
        return reservations

    def _account(self, plan, state: dict, trace, reservation_id: str,
                 estimated_input: int, reserved_output: int,
                 actual_input: int, actual_output: int) -> None:
        accounted_in = max(int(actual_input or 0), int(estimated_input or 0))
        accounted_out = int(actual_output or 0)
        if actual_input <= 0 and actual_output <= 0:
            accounted_out = int(reserved_output or 0)
        self.runtime.consume_quota(
            trace, reservation_id, accounted_in, accounted_out
        )
        state["model_rounds"] += 1
        state["budget"]["used_input_tokens"] += accounted_in
        state["budget"]["used_output_tokens"] += accounted_out
        state["budget"]["used_cost_usd"] = round(
            state["budget"]["used_cost_usd"] +
            self._cost(plan.quota_rule, accounted_in, accounted_out), 9
        )

    @staticmethod
    def _validate_plan(arguments: dict, allowed_ids: set[str], max_steps: int) -> tuple[list[dict], str]:
        steps = arguments.get("steps") if isinstance(arguments, dict) else None
        if not isinstance(steps, list) or not steps or len(steps) > max_steps:
            return [], "planner_step_count"
        seen_ids, seen_caps = set(), set()
        clean = []
        for raw in steps:
            if not isinstance(raw, dict):
                return [], "planner_step_not_object"
            step_id = str(raw.get("id") or "")
            cap_id = str(raw.get("capability_id") or "")
            objective = str(raw.get("objective") or "").strip()
            deps = raw.get("depends_on")
            if (not re.fullmatch(r"[a-zA-Z0-9_-]{1,40}", step_id) or
                    cap_id not in allowed_ids or cap_id in seen_caps or
                    not objective or len(objective) > 1200 or not isinstance(deps, list)):
                return [], "planner_step_contract"
            dep_ids = [str(x) for x in deps]
            if len(dep_ids) != len(set(dep_ids)) or any(x not in seen_ids for x in dep_ids):
                return [], "planner_dependency_invalid"
            seen_ids.add(step_id)
            seen_caps.add(cap_id)
            clean.append({
                "id": step_id, "capability_id": cap_id,
                "objective": objective, "depends_on": dep_ids,
                "status": "PENDING", "child_step_id": "", "evidence_ref": "",
                "error_code": "", "attempt": 1,
            })
        return clean, ""

    def _failure(self, state: dict, signature: str) -> int:
        signatures = state["failure_signatures"]
        signatures[signature] = int(signatures.get(signature) or 0) + 1
        return signatures[signature]

    def _evidence_payload(self, capability: dict, evidence) -> dict:
        return {
            "evidence_ref": evidence.ref, "source_type": evidence.source_type,
            "capability_id": capability["capability_id"],
            "capability_name": capability["name"],
            "capability_revision": capability["capability_revision"],
            "content_hash": evidence.content_hash,
            "excerpt": evidence.inline_excerpt,
        }

    def _reconcile_running_steps(self, plan, state: dict, trace) -> int:
        by_id = {x["capability_id"]: x for x in plan.candidates}
        recovered = 0
        for step in state["steps"]:
            if step.get("status") != "RUNNING" or not step.get("child_step_id"):
                continue
            capability = by_id.get(step["capability_id"])
            if not capability:
                continue
            row = self.runtime.find_step_read_evidence(
                trace.task_id, step["child_step_id"], capability["capability_id"],
                capability["capability_revision"],
            )
            evidence = self.executor.evidence_store.get_valid(str((row or {}).get("id") or ""))
            if evidence is None:
                continue
            payload = self._evidence_payload(capability, evidence)
            if not any(x.get("evidence_ref") == evidence.ref for x in state["evidence"]):
                state["evidence"].append(payload)
            step["status"] = "SUCCEEDED"
            step["evidence_ref"] = evidence.ref
            self.runtime.finish_child_step(
                self._child_trace(trace, step["child_step_id"]), "COMPLETED"
            )
            recovered += 1
        return recovered

    async def _planner_round(self, plan, state: dict, trace, api_key: str,
                             reasoning: str, emitter: Emitter | None) -> tuple[list[dict], str]:
        used = set(state["used_capability_ids"])
        candidates = [x for x in plan.candidates if x["capability_id"] not in used]
        remaining_slots = plan.policy.max_total_steps - len(state["steps"])
        if not candidates or remaining_slots <= 0:
            return [], "no_remaining_candidates"
        child = self.runtime.create_child_step(
            trace, "plan", _hash({"cycle": state["cycle"], "objective": plan.objective})
        )
        if child is None:
            return [], "planner_step_store_failed"
        request = replace(
            plan.compile_request, step_id=child.step_id,
            task_tokens_remaining=(state["budget"]["max_input_tokens"] -
                                   state["budget"]["used_input_tokens"]),
            monetary_remaining=(state["budget"]["max_cost_usd"] -
                                state["budget"]["used_cost_usd"]),
        )
        manifests = [{k: x.get(k) for k in (
            "capability_id", "name", "summary", "capability_revision", "score"
        )} for x in candidates]
        compiled = self.compiler.compile_orchestrator_plan(
            request, manifests, state["evidence"],
            remaining_slots,
        )
        if compiled.status != "compiled" or compiled.capsule is None:
            self.runtime.finish_child_step(child, "FAILED", compiled.status)
            return [], compiled.status
        estimate = int(compiled.trace_report.get("estimated_input_tokens") or 0)
        reservations = self._admit_batch(
            plan, state, [(child, estimate, plan.policy.planner_output_tokens)]
        )
        if not reservations:
            self.runtime.finish_child_step(child, "FAILED", "planner_budget_or_quota")
            return [], "planner_budget_or_quota"
        spec = compiled.capsule.rendered_request["tools"][0]
        response = await engine.single_tool_plan(
            plan.provider, api_key, plan.model,
            list(compiled.capsule.rendered_request["messages"]), reasoning, spec,
        )
        self._account(
            plan, state, child, reservations[0], estimate,
            plan.policy.planner_output_tokens,
            int(response.get("input") or 0), int(response.get("output") or 0),
        )
        if response.get("model"):
            plan = replace(plan, model=response["model"])
        if response.get("status") != "ok":
            error = str(response.get("error_code") or "planner_model_failed")
            self.runtime.finish_child_step(child, "FAILED", error)
            return [], error
        try:
            Draft202012Validator(spec["function"]["parameters"]).validate(
                response.get("arguments")
            )
        except Exception:
            self.runtime.finish_child_step(child, "FAILED", "planner_schema_validation")
            return [], "planner_schema_validation"
        steps, error = self._validate_plan(
            response["arguments"], {x["capability_id"] for x in candidates},
            remaining_slots,
        )
        self.runtime.finish_child_step(
            child, "COMPLETED" if not error else "FAILED", error
        )
        if not error:
            await self._emit(emitter, "plan", {
                "cycle": state["cycle"], "step_count": len(steps),
                "parallel_candidates": sum(not x["depends_on"] for x in steps),
            })
        return steps, error

    def _step_objective(self, state: dict, step: dict) -> str:
        dep_refs = {x.get("evidence_ref") for x in state["steps"]
                    if x.get("id") in set(step.get("depends_on") or [])}
        evidence = [{
            "evidence_ref": x["evidence_ref"],
            "excerpt": str(x.get("excerpt") or "")[:1200],
        } for x in state["evidence"] if x.get("evidence_ref") in dep_refs]
        if not evidence:
            return step["objective"]
        return step["objective"] + "\nDependency evidence:\n" + json.dumps(
            evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )

    async def _execute_node(self, plan, state: dict, parent_trace, step: dict,
                            child, compiled, lease, reservation_id: str,
                            api_key: str, reasoning: str) -> dict:
        estimate = int(compiled.trace_report.get("estimated_input_tokens") or 0)
        spec = compiled.capsule.rendered_request["tools"][0]
        planned = await engine.single_tool_plan(
            plan.provider, api_key, plan.model,
            list(compiled.capsule.rendered_request["messages"]), reasoning, spec,
        )
        self._account(
            plan, state, child, reservation_id, estimate,
            plan.policy.argument_output_tokens,
            int(planned.get("input") or 0), int(planned.get("output") or 0),
        )
        if planned.get("status") != "ok":
            error = str(planned.get("error_code") or "argument_planner_failed")
            self.runtime.revoke_capability_lease(child, lease.lease_id, error)
            return {"status": "FAILED", "error_code": error}
        invocation = await self.executor.invoke(
            child, plan.actor_id, lease, planned.get("arguments"),
            plan.routes[step["capability_id"]]["call"],
        )
        if invocation.status != "SUCCEEDED" or invocation.evidence is None:
            return {"status": "FAILED", "error_code": (
                invocation.error_code or invocation.status
            )}
        capability = next(
            x for x in plan.candidates if x["capability_id"] == step["capability_id"]
        )
        return {
            "status": "SUCCEEDED", "error_code": "",
            "evidence": self._evidence_payload(capability, invocation.evidence),
        }

    async def _execute_dag(self, plan, state: dict, trace, api_key: str,
                           reasoning: str, emitter: Emitter | None) -> tuple[int, int]:
        succeeded_before = len({x["content_hash"] for x in state["evidence"]})
        attempted = 0
        by_cap = {x["capability_id"]: x for x in plan.candidates}
        while True:
            status_by_id = {x["id"]: x["status"] for x in state["steps"]}
            pending = [x for x in state["steps"] if x["status"] == "PENDING"]
            for step in pending:
                dep_statuses = [status_by_id.get(x) for x in step["depends_on"]]
                if any(x in ("FAILED", "SKIPPED") for x in dep_statuses):
                    step["status"] = "SKIPPED"
                    step["error_code"] = "dependency_failed"
            ready = [x for x in state["steps"] if x["status"] == "PENDING" and
                     all(status_by_id.get(dep) == "SUCCEEDED" for dep in x["depends_on"])]
            if not ready:
                break
            batch = ready[:plan.policy.max_parallel]
            prepared = []
            for step in batch:
                child = self.runtime.create_child_step(
                    trace, "read", _hash(step["objective"]), attempt=step.get("attempt", 1)
                )
                if child is None:
                    step["status"] = "FAILED"
                    step["error_code"] = "child_step_store_failed"
                    continue
                step["child_step_id"] = child.step_id
                step["status"] = "RUNNING"
                capability = by_cap[step["capability_id"]]
                request = replace(
                    plan.compile_request, step_id=child.step_id,
                    objective=self._step_objective(state, step),
                    task_tokens_remaining=(state["budget"]["max_input_tokens"] -
                                           state["budget"]["used_input_tokens"]),
                    monetary_remaining=(state["budget"]["max_cost_usd"] -
                                        state["budget"]["used_cost_usd"]),
                )
                resolution = {"selected": [{"capability_id": capability["capability_id"]}],
                              "miss_class": ""}
                compiled = self.compiler.compile_canary(request, resolution)
                if (compiled.status != "compiled" or compiled.capsule is None or
                        compiled.trace_report.get("selected_count") != 1):
                    step["status"] = "FAILED"
                    step["error_code"] = "exact_schema_compile_failed"
                    self.runtime.finish_child_step(child, "FAILED", step["error_code"])
                    continue
                lease = self.executor.issue_lease(
                    child, plan.actor_id, plan.brain, capability,
                    plan.profiles[capability["capability_id"]],
                )
                if lease is None:
                    step["status"] = "FAILED"
                    step["error_code"] = "lease_issue_failed"
                    self.runtime.finish_child_step(child, "FAILED", step["error_code"])
                    continue
                prepared.append((step, child, compiled, lease))

            # Mapping child step -> logical node phải bền trước model/tool I/O.
            state["status"] = "EXECUTING"
            if not self._checkpoint(trace, state):
                for step, child, _compiled, lease in prepared:
                    self.runtime.revoke_capability_lease(child, lease.lease_id,
                                                         "pre_execute_checkpoint_failed")
                    step["status"] = "FAILED"
                    step["error_code"] = "pre_execute_checkpoint_failed"
                break
            calls = [(child,
                      int(compiled.trace_report.get("estimated_input_tokens") or 0),
                      plan.policy.argument_output_tokens)
                     for _step, child, compiled, _lease in prepared]
            reservations = self._admit_batch(plan, state, calls) if calls else []
            if calls and not reservations:
                for step, child, _compiled, lease in prepared:
                    self.runtime.revoke_capability_lease(child, lease.lease_id,
                                                         "batch_budget_or_quota")
                    self.runtime.finish_child_step(child, "FAILED", "batch_budget_or_quota")
                    step["status"] = "FAILED"
                    step["error_code"] = "batch_budget_or_quota"
                state["stop_reason"] = "budget_or_quota"
                self._checkpoint(trace, state)
                break
            for step, _child, _compiled, _lease in prepared:
                await self._emit(emitter, "tool_call", {
                    "tool": by_cap[step["capability_id"]]["name"],
                    "logical_step_id": step["id"],
                })
            results = await asyncio.gather(*[
                self._execute_node(
                    plan, state, trace, step, child, compiled, lease, reservation,
                    api_key, reasoning,
                )
                for (step, child, compiled, lease), reservation in zip(prepared, reservations)
            ], return_exceptions=True)
            attempted += len(results)
            for (step, child, _compiled, _lease), result in zip(prepared, results):
                if isinstance(result, Exception):
                    result = {"status": "FAILED", "error_code": type(result).__name__}
                step["status"] = result["status"]
                step["error_code"] = result.get("error_code") or ""
                if result["status"] == "SUCCEEDED":
                    payload = result["evidence"]
                    step["evidence_ref"] = payload["evidence_ref"]
                    if not any(x["evidence_ref"] == payload["evidence_ref"]
                               for x in state["evidence"]):
                        state["evidence"].append(payload)
                    self.runtime.finish_child_step(child, "COMPLETED")
                    await self._emit(emitter, "tool_result", {
                        "tool": by_cap[step["capability_id"]]["name"],
                        "evidence_ref": payload["evidence_ref"],
                    })
                else:
                    self.runtime.finish_child_step(child, "FAILED", step["error_code"])
                    self._failure(state, step["error_code"] or "read_failed")
            if len(state["evidence"]) > plan.policy.max_evidence:
                state["evidence"] = state["evidence"][:plan.policy.max_evidence]
            state["status"] = "EVALUATING"
            if not self._checkpoint(trace, state):
                state["stop_reason"] = "checkpoint_failed"
                break
        succeeded_after = len({x["content_hash"] for x in state["evidence"]})
        return max(0, succeeded_after - succeeded_before), attempted

    async def _finalize(self, plan, state: dict, trace, api_key: str, reasoning: str,
                        emitter: Emitter | None, final_generator: FinalGenerator):
        if not state["evidence"]:
            return "Javis chưa thu được evidence read-only hợp lệ để trả lời an toàn.", "no_evidence"
        child = self.runtime.create_child_step(
            trace, "final", _hash({"evidence": [x["content_hash"] for x in state["evidence"]]})
        )
        if child is None:
            return self._evidence_only_message(state), "final_step_store_failed"
        request = replace(
            plan.compile_request, step_id=child.step_id,
            task_tokens_remaining=(state["budget"]["max_input_tokens"] -
                                   state["budget"]["used_input_tokens"]),
            monetary_remaining=(state["budget"]["max_cost_usd"] -
                                state["budget"]["used_cost_usd"]),
        )
        compiled = self.compiler.compile_evidence_bundle_final(request, state["evidence"])
        if compiled.status != "compiled" or compiled.capsule is None:
            self.runtime.finish_child_step(child, "FAILED", compiled.status)
            return self._evidence_only_message(state), compiled.status
        estimate = int(compiled.trace_report.get("estimated_input_tokens") or 0)
        output_reserve = int(plan.quota_rule["reserved_output_tokens"])
        reservations = self._admit_batch(plan, state, [(child, estimate, output_reserve)])
        if not reservations:
            self.runtime.finish_child_step(child, "FAILED", "final_budget_or_quota")
            return self._evidence_only_message(state), "final_budget_or_quota"
        final_text, actual_model = "", plan.model
        actual_in = actual_out = 0
        engine_failed = False
        async for event in final_generator(
                plan.provider, api_key, plan.model,
                list(compiled.capsule.rendered_request.get("messages") or []), reasoning):
            kind = event.get("type")
            if kind == "meta":
                actual_model = event.get("model") or actual_model
            elif kind == "usage":
                actual_in += int(event.get("input") or 0)
                actual_out += int(event.get("output") or 0)
            elif kind == "text":
                final_text += str(event.get("content") or "")
            elif kind == "error":
                engine_failed = True
        self._account(
            plan, state, child, reservations[0], estimate, output_reserve,
            actual_in, actual_out,
        )
        refs = tuple(x["evidence_ref"] for x in state["evidence"])
        if not final_text:
            final_text = self._evidence_only_message(state)
        # Gate chấm text THÔ của model; footer "Nguồn:" nối SAU để check citation còn sống.
        decision = self.quality_gate.evaluate(
            plan.objective, final_text, plan.channel, had_error=engine_failed,
            compiler_report=compiled.trace_report, read_only=True,
            expected_evidence_refs=refs,
        )
        if "false_action_claim" in decision.reasons:
            final_text = (
                "Bản tổng hợp đã bị chặn vì tuyên bố hành động không phù hợp với task "
                "read-only. Evidence vẫn được giữ tại: " + ", ".join(refs)
            )
        elif refs and not any(ref in final_text for ref in refs):
            final_text += "\n\nNguồn: " + ", ".join(refs)
        self.runtime.finish_child_step(
            child, "COMPLETED" if not engine_failed else "FAILED",
            "final_engine_error" if engine_failed else "",
        )
        await self._emit(emitter, "quality", {
            **decision.trace_report(), "evidence_count": len(refs),
        })
        return final_text, ("final_engine_error" if engine_failed else "objective_satisfied")

    @staticmethod
    def _evidence_only_message(state: dict) -> str:
        refs = [x["evidence_ref"] for x in state.get("evidence") or []]
        if not refs:
            return "Task dừng an toàn trước khi có evidence hợp lệ."
        return (
            "Task đã dừng trước vòng tổng hợp vì budget, quota hoặc runtime guard. "
            "Evidence đã đọc vẫn còn và có thể resume: " + ", ".join(refs)
        )

    async def _continue(self, plan: OrchestratorAdmission, state: dict, trace,
                        api_key: str, reasoning: str, emitter: Emitter | None,
                        final_generator: FinalGenerator) -> OrchestratorResult:
        if state.get("status") == "COMPLETED" and state.get("final_text"):
            refs = tuple(x["evidence_ref"] for x in state.get("evidence") or [])
            return OrchestratorResult(
                state["final_text"], plan.model, "COMPLETED", trace.task_id,
                state.get("stop_reason") or "already_completed",
                state["budget"]["used_input_tokens"],
                state["budget"]["used_output_tokens"],
                state["budget"]["used_cost_usd"], refs, state["model_rounds"],
            )
        # Deadline được đo từ lúc TẠO task. Nếu tiến trình chết rồi khởi động lại sau
        # deadline thì mọi batch đều bị chặn ngay và resume thành vô nghĩa - đúng thứ
        # Phase 7 sinh ra để tránh. Gia hạn một cửa sổ mới kể từ lúc resume, nhưng
        # KHÔNG vô hạn: đếm số lần gia hạn và chặn theo trần policy, nếu không một task
        # hỏng có thể được hồi sinh mãi.
        now = time.time()
        if now >= float(state.get("deadline_at") or 0):
            extensions = int(state.get("deadline_extensions") or 0)
            if extensions >= plan.policy.max_deadline_extensions:
                state["status"] = "FAILED"
                state["stop_reason"] = "deadline_extension_budget_exhausted"
                self._checkpoint(trace, state)
                return OrchestratorResult(
                    self._evidence_only_message(state), plan.model, "FAILED",
                    trace.task_id, "deadline_extension_budget_exhausted",
                    state["budget"]["used_input_tokens"],
                    state["budget"]["used_output_tokens"],
                    state["budget"]["used_cost_usd"],
                    tuple(x["evidence_ref"] for x in state.get("evidence") or []),
                    state["model_rounds"],
                )
            state["deadline_extensions"] = extensions + 1
            state["deadline_at"] = now + plan.policy.deadline_seconds
            self.runtime.record_runtime_event(trace, "orchestrator.deadline_extended", {
                "extension": state["deadline_extensions"],
                "deadline_seconds": plan.policy.deadline_seconds,
            })
        durable_usage = self.runtime.task_quota_usage(trace.task_id)
        state["budget"]["used_input_tokens"] = max(
            int(state["budget"].get("used_input_tokens") or 0),
            durable_usage["input_tokens"],
        )
        state["budget"]["used_output_tokens"] = max(
            int(state["budget"].get("used_output_tokens") or 0),
            durable_usage["output_tokens"],
        )
        state["model_rounds"] = max(
            int(state.get("model_rounds") or 0), durable_usage["model_rounds"]
        )
        state["budget"]["used_cost_usd"] = max(
            float(state["budget"].get("used_cost_usd") or 0.0),
            self._cost(
                plan.quota_rule, state["budget"]["used_input_tokens"],
                state["budget"]["used_output_tokens"],
            ),
        )
        recovered = self._reconcile_running_steps(plan, state, trace)
        if recovered:
            self.runtime.record_runtime_event(trace, "orchestrator.resume_reconciled", {
                "recovered_steps": recovered,
            })
            state["status"] = "EVALUATING"
            if not self._checkpoint(trace, state):
                state["stop_reason"] = "resume_checkpoint_failed"
            elif state["evidence"] and all(
                    x.get("status") == "SUCCEEDED" for x in state["steps"]):
                state["stop_reason"] = "evidence_complete"

        unfinished = [x for x in state["steps"]
                      if x.get("status") in ("PENDING", "RUNNING")]
        if unfinished:
            for step in unfinished:
                if step.get("status") == "RUNNING":
                    if step.get("child_step_id"):
                        self.runtime.finish_child_step(
                            self._child_trace(trace, step["child_step_id"]),
                            "FAILED", "interrupted_read_retry",
                        )
                    step["status"] = "PENDING"
                    step["child_step_id"] = ""
                    step["attempt"] = int(step.get("attempt") or 1) + 1
            gained, attempted = await self._execute_dag(
                plan, state, trace, api_key, reasoning, emitter
            )
            gain = gained / max(1, attempted)
            self.runtime.record_runtime_event(trace, "orchestrator.resume_gain", {
                "new_unique_evidence": gained, "attempted_steps": attempted,
                "marginal_gain": round(gain, 6),
            })
            if (attempted and gain < plan.policy.min_information_gain and
                    not state.get("evidence")):
                state["stop_reason"] = "marginal_information_gain"
            elif gained > 0 and all(
                    x.get("status") == "SUCCEEDED" for x in unfinished):
                state["stop_reason"] = "evidence_complete"

        while state["cycle"] < plan.policy.max_cycles and not state.get("stop_reason"):
            if (time.time() >= state["deadline_at"] or
                    len(state["steps"]) >= plan.policy.max_total_steps or
                    len(state["evidence"]) >= plan.policy.max_evidence):
                state["stop_reason"] = "task_limit_reached"
                break
            state["cycle"] += 1
            state["status"] = "RESOLVING"
            if not self._checkpoint(trace, state):
                state["stop_reason"] = "checkpoint_failed"
                break
            steps, error = await self._planner_round(
                plan, state, trace, api_key, reasoning, emitter
            )
            if error:
                repeats = self._failure(state, error)
                state["status"] = "RETRYABLE_ERROR"
                self._checkpoint(trace, state)
                if repeats >= plan.policy.failure_repeat_limit:
                    state["stop_reason"] = "repeated_failure"
                    break
                continue
            state["steps"].extend(steps)
            state["used_capability_ids"].extend(x["capability_id"] for x in steps)
            state["status"] = "COMPILING"
            if not self._checkpoint(trace, state):
                state["stop_reason"] = "checkpoint_failed"
                break
            gained, attempted = await self._execute_dag(
                plan, state, trace, api_key, reasoning, emitter
            )
            gain = gained / max(1, attempted)
            self.runtime.record_runtime_event(trace, "orchestrator.information_gain", {
                "cycle": state["cycle"], "new_unique_evidence": gained,
                "attempted_steps": attempted, "marginal_gain": round(gain, 6),
            })
            failed = any(x["status"] in ("FAILED", "SKIPPED") for x in steps)
            remaining = (set(state["candidate_ids"]) - set(state["used_capability_ids"]))
            if state.get("stop_reason"):
                break
            if attempted and gain < plan.policy.min_information_gain:
                state["stop_reason"] = "marginal_information_gain"
                break
            if gained > 0 and not failed:
                state["stop_reason"] = "evidence_complete"
                break
            if not remaining:
                state["stop_reason"] = "no_remaining_capability"
                break

        state["status"] = "EVALUATING"
        self._checkpoint(trace, state)
        text, final_reason = await self._finalize(
            plan, state, trace, api_key, reasoning, emitter, final_generator
        )
        state["final_text"] = text
        state["stop_reason"] = state.get("stop_reason") or final_reason
        state["status"] = "COMPLETED" if state["evidence"] else "FAILED"
        self._checkpoint(trace, state)
        refs = tuple(x["evidence_ref"] for x in state["evidence"])
        return OrchestratorResult(
            text=text, model=plan.model, status=state["status"],
            task_id=trace.task_id, stop_reason=state["stop_reason"],
            tokens_in=state["budget"]["used_input_tokens"],
            tokens_out=state["budget"]["used_output_tokens"],
            cost_usd=state["budget"]["used_cost_usd"], evidence_refs=refs,
            model_rounds=state["model_rounds"],
        )

    async def run(self, plan: OrchestratorAdmission, api_key: str, reasoning: str,
                  emitter: Emitter | None,
                  final_generator: FinalGenerator) -> OrchestratorResult:
        if plan.action != "execute" or not plan.trace:
            raise ValueError("orchestrator_plan_not_executable")
        state = self._initial_state(plan)
        if not self._checkpoint(plan.trace, state, initialize=True):
            return OrchestratorResult(
                "Không thể tạo checkpoint mã hoá cho task read-only; Javis đã dừng trước model/tool.",
                plan.model, "FAILED", plan.trace.task_id, "checkpoint_initialize_failed",
                0, 0, 0.0, (), 0,
            )
        await self._emit(emitter, "started", {
            "task_id": plan.trace.task_id, "candidate_count": len(plan.candidates),
            "deadline_seconds": plan.policy.deadline_seconds,
        })
        try:
            return await self._continue(
                plan, state, plan.trace, api_key, reasoning, emitter, final_generator
            )
        except Exception as exc:
            state["status"] = "RETRYABLE_ERROR"
            state["stop_reason"] = f"runtime_exception:{type(exc).__name__}"
            try:
                self._checkpoint(plan.trace, state)
            except Exception:
                pass
            return OrchestratorResult(
                self._evidence_only_message(state), plan.model, state["status"],
                plan.trace.task_id, state["stop_reason"],
                state["budget"]["used_input_tokens"],
                state["budget"]["used_output_tokens"],
                state["budget"]["used_cost_usd"],
                tuple(x["evidence_ref"] for x in state["evidence"]),
                state["model_rounds"],
            )

    async def resume(self, task_id: str, actor_id: str, provider: str, model: str,
                     api_key: str, reasoning: str, emitter: Emitter | None,
                     final_generator: FinalGenerator) -> OrchestratorResult:
        """Resume cùng runtime/policy/registry/model; lệch revision thì fail closed."""
        trace = self.runtime.resume_trace(task_id)
        snapshot = self.runtime.load_orchestrator_checkpoint(task_id)
        if trace is None or snapshot is None:
            raise ValueError("task_not_resumable")
        task = snapshot["task"]
        try:
            state = json.loads(self.state_decryptor(
                snapshot["checkpoint"]["state_encrypted"]
            ))
            objective = self.state_decryptor(task["objective_encrypted"])
        except Exception as exc:
            raise ValueError("task_state_decrypt_failed") from exc
        if (state.get("schema_version") != STATE_SCHEMA_VERSION or
                state.get("actor_hash") != CapabilityExecutor.actor_hash(actor_id) or
                state.get("objective") != objective):
            raise PermissionError("task_actor_or_state_mismatch")
        if (state.get("provider") != str(provider or "") or
                state.get("model") != str(model or "")):
            raise PermissionError("task_provider_or_model_mismatch")
        policy = OrchestratorPolicy.from_settings(self.settings_reader() or {})
        if policy.version != state.get("policy_version"):
            raise ValueError("task_policy_revision_mismatch")
        if self.registry.revision(task["brain"]) != trace.registry_revision:
            raise ValueError("task_registry_revision_mismatch")
        rule = policy.quota_rule(state["provider"], state["model"])
        if (rule is None or rule["id"] != state.get("quota_rule_id") or
                _rule_hash(rule) != state.get("quota_rule_hash")):
            raise ValueError("task_quota_rule_mismatch")
        # Metadata model cũng phải đúng revision đã ghim: compiler đọc lại model profile
        # LIVE khi resume, nên profile đổi giữa chừng sẽ đổi budget của task đang chạy.
        if (state.get("model_profile_revision") and
                self.registry.model_revision() != state["model_profile_revision"]):
            raise ValueError("task_model_profile_revision_mismatch")
        records = self.registry.get_capabilities(state["candidate_ids"], task["brain"])
        if len(records) != len(state["candidate_ids"]):
            raise ValueError("task_capability_missing")
        by_id = {x["capability_id"]: x for x in records}
        ordered = []
        profiles = {}
        for capability_id in state["candidate_ids"]:
            item = by_id[capability_id]
            profile = policy.capability_profile(item)
            if profile is None:
                raise ValueError("task_capability_policy_changed")
            ordered.append(item)
            profiles[capability_id] = profile
        routes, error = await self._live_routes(trace, task["brain"], ordered)
        if error:
            raise ValueError(error)
        request = self._request(
            trace, objective, task["brain"], task["channel"],
            state["provider"], state["model"], rule, policy,
        )
        plan = OrchestratorAdmission(
            "execute", "resumed", "orchestrator", trace.canary_bucket, trace,
            objective, task["brain"], task["channel"], state["provider"],
            state["model"], actor_id, policy, rule, tuple(ordered), profiles,
            routes, request,
        )
        if not self.runtime.claim_orchestrator_resume(trace):
            raise RuntimeError("task_resume_conflict")
        self.runtime.record_runtime_event(trace, "orchestrator.resumed", {
            "checkpoint_sequence": snapshot["checkpoint"]["sequence"],
            "orchestration_status": snapshot["checkpoint"]["orchestration_status"],
        })
        return await self._continue(
            plan, state, trace, api_key, reasoning, emitter, final_generator
        )
