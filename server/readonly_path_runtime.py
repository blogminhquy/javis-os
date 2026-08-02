"""Adaptive Runtime Phase 6: single-step read-only capability canary.

Admission chạy hoàn toàn trước model call. Chỉ một capability allowlisted được phơi schema,
gateway giữ lease dùng một lần, và quota được giữ cho đúng hai model round.
"""
from __future__ import annotations

import asyncio
import fnmatch
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

import capability_resolver
import context_compiler
import context_runtime
import fast_path_runtime
from capability_executor import CapabilityExecutor, CapabilityLease


READONLY_POLICY_VERSION = "readonly-single-step-v1"
Discoverer = Callable[[str, str], Awaitable[tuple[list[dict], dict]]]


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return int(default)


def _norm(value: str) -> str:
    # "đ" không phân rã qua NFKD - phải map tay như fast_path_runtime._norm, nếu không
    # _WRITE_INTENT ("dat lich", "dang bai"...) không khớp tiếng Việt có dấu.
    raw = str(value or "").replace("đ", "d").replace("Đ", "D")
    raw = unicodedata.normalize("NFKD", raw.casefold())
    return " ".join("".join(c for c in raw if not unicodedata.combining(c)).split())


_STATE_REF = re.compile(
    r"\b(truoc day|lan truoc|vua roi|cai do|cai nay|nhu cu|tiep tuc|nho khong|"
    r"previously|earlier|last time|remember|that one|same as before)\b"
)
_WRITE_INTENT = re.compile(
    r"\b(gui|send|xoa|delete|remove|huy|cancel|tao|create|cap nhat|update|sua|edit|"
    r"dang bai|publish|upload|dat lich|book)\b"
)


@dataclass(frozen=True)
class ReadonlyPolicy:
    mode: str
    allocation_basis_points: int
    salt: str
    channels: tuple[str, ...]
    provider_kinds: tuple[str, ...]
    registry_max_age_seconds: int
    min_resolver_score: float
    estimator_safety_factor: float
    capability_profiles: tuple[dict, ...]
    quota_policy: fast_path_runtime.CanaryPolicy
    version: str

    @classmethod
    def from_settings(cls, settings: dict) -> "ReadonlyPolicy":
        runtime = (settings or {}).get("context_runtime") or {}
        raw = runtime.get("readonly_canary")
        raw = raw if isinstance(raw, dict) else {}
        quota_raw = raw.get("quota_profiles") or (
            (runtime.get("canary") or {}).get("quota_profiles") or []
        )
        quota_settings = {
            "context_runtime": {
                "mode": raw.get("mode", runtime.get("mode", "off")),
                "canary": {**raw, "quota_profiles": quota_raw},
            }
        }
        quota_policy = fast_path_runtime.CanaryPolicy.from_settings(quota_settings)
        profiles = tuple(
            dict(x) for x in (raw.get("capability_profiles") or [])
            if isinstance(x, dict) and str(x.get("id") or "").strip()
        )
        return cls(
            mode=str(raw.get("mode", runtime.get("mode", "off"))).lower(),
            allocation_basis_points=max(
                0, min(int(raw.get("allocation_basis_points") or 0), 10_000)
            ),
            salt=str(raw.get("salt") or READONLY_POLICY_VERSION),
            channels=tuple(str(x) for x in (raw.get("channels") or ["dashboard"])),
            provider_kinds=tuple(str(x) for x in (raw.get("provider_kinds") or ["api"])),
            registry_max_age_seconds=max(
                1, int(raw.get("registry_max_age_seconds") or 900)
            ),
            min_resolver_score=max(
                0.0, min(float(raw.get("min_resolver_score") or 0.45), 1.0)
            ),
            estimator_safety_factor=max(
                1.0, min(float(raw.get("estimator_safety_factor") or 1.35), 3.0)
            ),
            capability_profiles=profiles,
            quota_policy=quota_policy,
            version=str(raw.get("policy_version") or READONLY_POLICY_VERSION)[:120],
        )

    def profile_for(self, capability: dict) -> Optional[dict]:
        source = str(capability.get("source_type") or "")
        name = str(capability.get("name") or "")
        cap_id = str(capability.get("capability_id") or "")
        matches = []
        for profile in self.capability_profiles:
            if not fnmatch.fnmatchcase(source, str(profile.get("source_type") or "*")):
                continue
            if not fnmatch.fnmatchcase(name, str(profile.get("name_pattern") or "*")):
                continue
            if not fnmatch.fnmatchcase(
                    cap_id, str(profile.get("capability_id_pattern") or "*")):
                continue
            matches.append(profile)
        if not matches:
            return None
        matches.sort(key=lambda x: (
            -_int(x.get("priority"), 0),
            -len(str(x.get("capability_id_pattern") or "")),
            -len(str(x.get("name_pattern") or "")),
            str(x.get("id") or ""),
        ))
        return dict(matches[0])


@dataclass(frozen=True)
class ReadonlyPathPlan:
    action: str
    reason: str
    execution_path: str = "unassigned"
    bucket: Optional[int] = None
    messages: tuple[dict, ...] = ()
    tool_spec: dict | None = None
    lease: CapabilityLease | None = None
    route_call: Callable[[dict], Awaitable[Any]] | None = None
    compile_request: context_compiler.CompileRequest | None = None
    reservation_id: str = ""
    estimated_input_tokens: int = 0
    reserved_input_tokens: int = 0
    reserved_output_tokens: int = 0
    policy_version: str = READONLY_POLICY_VERSION
    rejection_message: str = ""


class ReadonlyPathCanary:
    def __init__(self, registry, resolver, compiler, runtime,
                 executor: CapabilityExecutor, settings_reader: Callable[[], dict],
                 discoverer: Discoverer):
        self.registry = registry
        self.resolver = resolver
        self.compiler = compiler
        self.runtime = runtime
        self.executor = executor
        self.settings_reader = settings_reader
        self.discoverer = discoverer

    @staticmethod
    def _plan(action: str, reason: str, policy: ReadonlyPolicy,
              bucket: Optional[int] = None, path: str = "unassigned",
              rejection: str = "") -> ReadonlyPathPlan:
        return ReadonlyPathPlan(
            action, reason, path, bucket=bucket, policy_version=policy.version,
            rejection_message=rejection,
        )

    def _legacy(self, trace, policy, bucket, reason) -> ReadonlyPathPlan:
        path = self.runtime.pin_execution_path(
            trace, "legacy", bucket, policy.version, reason
        ) if trace else "legacy"
        return self._plan("legacy", reason, policy, bucket, path)

    def _reject(self, trace, policy, bucket, reason, message) -> ReadonlyPathPlan:
        path = self.runtime.pin_execution_path(
            trace, "readonly", bucket, policy.version, reason
        ) if trace else "readonly"
        return self._plan("reject", reason, policy, bucket, path, message)

    async def _refresh_full(self, trace, brain: str, reason: str) -> bool:
        try:
            tools, route = await self.discoverer("refresh_full", brain)
            # refresh_tools giữ registry lock và ghi SQLite - phải rời event loop,
            # nếu không một source đổi lớn có thể treo mọi request chat vài giây.
            refreshed = await asyncio.to_thread(self.registry.refresh_tools, brain, tools, route)
            revision = str(refreshed.get("revision") or self.registry.revision(brain))
            if revision != trace.registry_revision:
                return self.runtime.rebase_registry_revision(trace, revision, reason)
            return True
        except Exception as exc:
            self.runtime.record_runtime_event(trace, "readonly.discovery_failed", {
                "mode": "full", "error_type": type(exc).__name__,
            })
            return False

    def _resolve_one(self, trace, objective: str, brain: str, channel: str,
                     policy: ReadonlyPolicy) -> tuple[dict | None, dict, str]:
        resolution = self.resolver.resolve(
            objective, brain,
            capability_resolver.ActorPolicy(
                mode="readonly", channel=channel,
                allowed_effects=frozenset({"none", "read"}),
            ),
        )
        selected = resolution.get("selected") or []
        self.runtime.record_runtime_event(trace, "resolver.readonly", {
            "policy_version": resolution.get("policy_version") or "",
            "registry_revision": resolution.get("registry_revision") or "",
            "candidate_count": resolution.get("candidate_count", 0),
            "selected_count": len(selected),
            "miss_class": resolution.get("miss_class") or "",
        })
        if not selected:
            return None, resolution, "no_read_capability"
        if len(selected) != 1:
            return None, resolution, "read_capability_ambiguous"
        if resolution.get("miss_class"):
            return None, resolution, "higher_ranked_capability_blocked"
        if float(selected[0].get("score") or 0) < policy.min_resolver_score:
            return None, resolution, "resolver_score_too_low"
        records = self.registry.get_capabilities(
            [selected[0]["capability_id"]], brain
        )
        if len(records) != 1:
            return None, resolution, "registry_record_missing"
        capability = records[0]
        if (capability.get("side_effect") not in ("none", "read") or
                capability.get("required_mode") != "readonly"):
            return None, resolution, "capability_not_readonly"
        return capability, resolution, ""

    async def prepare(self, trace: context_runtime.TurnTrace | None, objective: str,
                      brain: str, channel: str, provider: str, model: str,
                      provider_kind: str, actor_id: str,
                      has_attachments: bool = False) -> ReadonlyPathPlan:
        try:
            policy = ReadonlyPolicy.from_settings(self.settings_reader() or {})
        except Exception:
            policy = ReadonlyPolicy.from_settings({})
        if not trace:
            return self._plan("not_applicable", "trace_unavailable", policy)
        bucket = fast_path_runtime.stable_bucket(trace.session_id, policy.salt)
        if policy.mode not in ("canary", "on"):
            return self._plan("not_applicable", "mode_not_canary", policy, bucket)
        if policy.allocation_basis_points <= bucket:
            return self._plan("not_applicable", "outside_allocation", policy, bucket)
        if channel not in policy.channels or provider_kind not in policy.provider_kinds:
            return self._plan("not_applicable", "route_not_allowed", policy, bucket)
        if has_attachments:
            return self._legacy(trace, policy, bucket, "attachment_present")
        normalized = _norm(objective)
        if _STATE_REF.search(normalized):
            return self._legacy(trace, policy, bucket, "conversation_state_required")
        if _WRITE_INTENT.search(normalized):
            return self._legacy(trace, policy, bucket, "write_intent")
        rule = policy.quota_policy.quota_rule(provider, model)
        if rule is None:
            return self._legacy(trace, policy, bucket, "hard_quota_unknown")
        if not self.executor.evidence_store.ready():
            return self._legacy(trace, policy, bucket, "evidence_store_unavailable")

        inventory = self.registry.inventory_status(brain)
        age = inventory.get("age_seconds")
        if (not inventory.get("ready") or age is None or
                age > policy.registry_max_age_seconds or
                inventory.get("revision") != trace.registry_revision):
            if not await self._refresh_full(trace, brain, "readonly_preflight_refresh"):
                return self._legacy(trace, policy, bucket, "registry_refresh_failed")

        capability, resolution, error = await asyncio.to_thread(
            self._resolve_one, trace, objective, brain, channel, policy
        )
        if error == "no_read_capability":
            return self._plan("not_applicable", error, policy, bucket)
        if error:
            return self._legacy(trace, policy, bucket, error)
        profile = policy.profile_for(capability)
        if profile is None:
            return self._legacy(trace, policy, bucket, "capability_not_allowlisted")

        async def current_read_route() -> tuple[dict | None, dict | None]:
            tools, route = await self.discoverer("readonly", brain)
            by_name = {str(x.get("fn") or x.get("name") or ""): x for x in tools}
            return by_name.get(capability["name"]), route.get(capability["name"])

        try:
            tool, route_entry = await current_read_route()
        except Exception as exc:
            self.runtime.record_runtime_event(trace, "readonly.discovery_failed", {
                "mode": "readonly", "error_type": type(exc).__name__,
            })
            return self._legacy(trace, policy, bucket, "readonly_discovery_failed")
        live_hash = self.registry.schema_hash((tool or {}).get("schema") or {})
        if (not tool or not route_entry or live_hash != capability.get("schema_hash")):
            if not await self._refresh_full(trace, brain, "schema_revision_mismatch"):
                return self._legacy(trace, policy, bucket, "schema_refresh_failed")
            capability, resolution, error = await asyncio.to_thread(
                self._resolve_one, trace, objective, brain, channel, policy
            )
            if error or capability is None:
                return self._legacy(trace, policy, bucket, "schema_reresolve_failed")
            profile = policy.profile_for(capability)
            if profile is None:
                return self._legacy(trace, policy, bucket, "reresolved_capability_not_allowlisted")
            try:
                tool, route_entry = await current_read_route()
            except Exception:
                return self._legacy(trace, policy, bucket, "readonly_rediscovery_failed")
            live_hash = self.registry.schema_hash((tool or {}).get("schema") or {})
            if (not tool or not route_entry or live_hash != capability.get("schema_hash")):
                return self._legacy(trace, policy, bucket, "schema_revision_unstable")

        if (str(route_entry.get("effect") or "read") not in ("none", "read") or
                str(route_entry.get("required_mode") or "readonly") != "readonly" or
                not callable(route_entry.get("call"))):
            return self._legacy(trace, policy, bucket, "readonly_route_invalid")

        request = context_compiler.CompileRequest(
            task_id=trace.task_id, step_id=trace.step_id, objective=objective,
            brain=brain, channel=channel, provider=provider, model=model,
            model_kind=provider_kind, rolling_tpm_remaining=rule.rolling_tpm,
            hard_max_input_tokens=rule.hard_max_input_tokens,
            reserved_output_tokens=rule.reserved_output_tokens,
            execution_mode="canary",
        )
        compiled = self.compiler.compile_canary(request, resolution)
        report = compiled.trace_report
        if (compiled.status != "compiled" or compiled.capsule is None or
                report.get("path") != "tool" or report.get("selected_count") != 1 or
                report.get("preflight_decision") != "would_allow"):
            return self._reject(
                trace, policy, bucket, "readonly_compile_rejected",
                "Request vượt context budget đã xác minh cho vòng lập arguments. "
                "Javis chưa gửi model call hoặc gọi tool.",
            )

        excerpt_chars = max(500, min(_int(profile.get("excerpt_chars"), 4000), 20_000))
        placeholder = self.compiler.compile_evidence_final(request, {
            "evidence_ref": "evidence://task/placeholder/step/placeholder/ev_placeholder",
            "source_type": "capability_read",
            "capability_id": capability["capability_id"],
            "capability_name": capability["name"],
            "capability_revision": capability["capability_revision"],
            "content_hash": "0" * 64,
            # Backslash là trường hợp JSON escaping xấu hơn text thường, dùng để reserve bảo thủ.
            "excerpt": "\\" * excerpt_chars,
        })
        final_report = placeholder.trace_report
        if (placeholder.status != "compiled" or placeholder.capsule is None or
                final_report.get("preflight_decision") != "would_allow"):
            return self._reject(
                trace, policy, bucket, "readonly_final_compile_rejected",
                "Evidence capsule dự kiến vượt context budget của vòng tổng hợp. "
                "Javis chưa gửi model call hoặc gọi tool.",
            )

        initial_estimate = max(1, int(report.get("estimated_input_tokens") or 0))
        final_estimate = max(1, int(final_report.get("estimated_input_tokens") or 0))
        if (initial_estimate > rule.hard_max_input_tokens or
                final_estimate > rule.hard_max_input_tokens):
            return self._reject(
                trace, policy, bucket, "hard_input_limit",
                "Request vượt hard context limit đã xác minh. Javis chưa gửi model call nào.",
            )
        reserved_input = int(math.ceil(
            (initial_estimate + final_estimate) * policy.estimator_safety_factor
        ))
        reserved_output = rule.reserved_output_tokens * 2
        path = self.runtime.pin_execution_path(
            trace, "readonly", bucket, policy.version, "readonly_admission_candidate"
        )
        if path != "readonly":
            return self._plan("legacy", "task_already_pinned", policy, bucket, path)
        admission = self.runtime.admit_quota(
            trace, provider, model, reserved_input, reserved_output,
            rule.rolling_tpm, rule.window_seconds,
        )
        if not admission.allowed:
            return self._plan(
                "reject", admission.reason, policy, bucket, "readonly",
                "Model hiện tại không còn đủ ngân sách token cho hai vòng kiểm soát. "
                "Javis chưa gửi request; anh chờ hết cửa sổ quota hoặc đổi model/provider.",
            )
        lease = self.executor.issue_lease(
            trace, actor_id, brain, capability, profile
        )
        if lease is None:
            self.runtime.release_quota(trace, admission.reservation_id, "lease_issue_failed")
            return self._plan(
                "reject", "lease_issue_failed", policy, bucket, "readonly",
                "Capability không đạt policy lease read-only. Javis chưa gọi model hoặc tool.",
            )
        rendered = compiled.capsule.rendered_request
        return ReadonlyPathPlan(
            "execute", "admitted", "readonly", bucket=bucket,
            messages=tuple(rendered.get("messages") or []),
            tool_spec=(rendered.get("tools") or [None])[0],
            lease=lease, route_call=route_entry["call"], compile_request=request,
            reservation_id=admission.reservation_id,
            estimated_input_tokens=initial_estimate + final_estimate,
            reserved_input_tokens=reserved_input,
            reserved_output_tokens=reserved_output,
            policy_version=policy.version,
        )
