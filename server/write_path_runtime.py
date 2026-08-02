"""Adaptive Runtime Phase 9: tool write theo TỪNG capability group.

Ba tính chất quyết định đường này an toàn hay không:

1. **Không có cờ chung cho mọi write tool.** Mỗi group phải được operator khai
   riêng trong `write_canary.capability_profiles`. Danh sách rỗng = fail-closed.
2. **Không bao giờ chạy write mà chưa có xác nhận của con người.** Vòng một chỉ
   LẬP đề xuất rồi ghi ledger ở trạng thái PREPARED. Chỉ khi người dùng gõ lại
   đúng mã xác nhận thì vòng hai mới thực thi.
3. **Không bao giờ retry mù.** Timeout hoặc lỗi mập mờ chuyển UNKNOWN, giữ
   resource lock, và chỉ được kết luận bằng read reconcile hoặc bằng người dùng.

Effect `dangerous` không thuộc phạm vi Phase 9 trong mọi cấu hình.
"""
from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

import capability_resolver
import context_compiler
import context_runtime
import fast_path_runtime
from capability_executor import (
    CapabilityExecutor, CapabilityLease, arguments_hash, idempotency_key, resource_lock_key,
)


WRITE_POLICY_VERSION = "write-single-step-v1"
Discoverer = Callable[[str, str], Awaitable[tuple[list[dict], dict]]]
_CONFIRM_ALPHABET = "ACDEFGHJKLMNPQRTUVWXY34679"   # bỏ ký tự dễ đọc nhầm


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return int(default)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else float(default)
    except (TypeError, ValueError, OverflowError):
        return float(default)


def _norm(value: str) -> str:
    raw = str(value or "").replace("đ", "d").replace("Đ", "D")
    raw = unicodedata.normalize("NFKD", raw.casefold())
    return " ".join("".join(c for c in raw if not unicodedata.combining(c)).split())


# Người dùng phải gõ lại ĐÚNG mã. "ok", "đồng ý", "ừ" cố tình KHÔNG được chấp nhận:
# một câu ừ hử mơ hồ không đủ làm bằng chứng cho hành động không hoàn tác được.
_CONFIRM_RE = re.compile(r"(?i)\bxac\s*nhan\s+([a-z0-9]{6})\b")
_CANCEL_RE = re.compile(r"(?i)\b(huy|huy bo|khong lam|dung lai|cancel|abort)\b")


def confirmation_code(task_id: str, args_hash: str, salt: str) -> str:
    """Mã 6 ký tự suy ra từ chính ý định write, không phải số ngẫu nhiên.

    Nhờ vậy sau restart vẫn tính lại được cùng mã cho cùng ý định.
    """
    digest = hashlib.sha256(
        f"{salt}|{task_id}|{args_hash}".encode("utf-8", errors="replace")
    ).digest()
    return "".join(_CONFIRM_ALPHABET[b % len(_CONFIRM_ALPHABET)] for b in digest[:6])


def parse_confirmation(message: str) -> tuple[str, str]:
    """Trả `("confirm", mã)`, `("cancel", "")` hoặc `("", "")`."""
    normalized = _norm(message)
    match = _CONFIRM_RE.search(normalized)
    if match:
        return "confirm", match.group(1).upper()
    if _CANCEL_RE.search(normalized):
        return "cancel", ""
    return "", ""


@dataclass(frozen=True)
class WritePolicy:
    mode: str
    allocation_basis_points: int
    salt: str
    channels: tuple[str, ...]
    provider_kinds: tuple[str, ...]
    registry_max_age_seconds: int
    min_resolver_score: float
    estimator_safety_factor: float
    confirmation_ttl_seconds: int
    capability_profiles: tuple[dict, ...]
    quota_policy: fast_path_runtime.CanaryPolicy
    version: str

    @classmethod
    def from_settings(cls, settings: dict) -> "WritePolicy":
        runtime = (settings or {}).get("context_runtime") or {}
        runtime = runtime if isinstance(runtime, dict) else {}
        raw = runtime.get("write_canary")
        raw = raw if isinstance(raw, dict) else {}
        quota_raw = raw.get("quota_profiles") or (
            (runtime.get("canary") or {}).get("quota_profiles") or []
        )
        quota_policy = fast_path_runtime.CanaryPolicy.from_settings({
            "context_runtime": {
                "mode": raw.get("mode", runtime.get("mode", "off")),
                "canary": {**raw, "quota_profiles": quota_raw},
            }
        })
        profiles = tuple(
            dict(x) for x in (raw.get("capability_profiles") or [])
            if isinstance(x, dict) and str(x.get("id") or "").strip()
        )
        return cls(
            mode=str(raw.get("mode", runtime.get("mode", "off"))).lower(),
            allocation_basis_points=max(
                0, min(_int(raw.get("allocation_basis_points"), 0), 10_000)),
            salt=str(raw.get("salt") or WRITE_POLICY_VERSION),
            channels=tuple(str(x) for x in (raw.get("channels") or ["dashboard"])),
            provider_kinds=tuple(str(x) for x in (raw.get("provider_kinds") or ["api"])),
            registry_max_age_seconds=max(
                1, _int(raw.get("registry_max_age_seconds"), 900)),
            min_resolver_score=max(
                0.0, min(_float(raw.get("min_resolver_score"), 0.55), 1.0)),
            estimator_safety_factor=max(
                1.0, min(_float(raw.get("estimator_safety_factor"), 1.35), 3.0)),
            confirmation_ttl_seconds=max(
                60, min(_int(raw.get("confirmation_ttl_seconds"), 900), 86_400)),
            capability_profiles=profiles,
            quota_policy=quota_policy,
            version=str(raw.get("policy_version") or WRITE_POLICY_VERSION)[:120],
        )

    def profile_for(self, capability: dict) -> Optional[dict]:
        """Allowlist theo connector/group. Không khớp profile nào = không được write."""
        source = str(capability.get("source_type") or "")
        source_id = str((capability.get("metadata") or {}).get("source_id") or "")
        name = str(capability.get("name") or "")
        cap_id = str(capability.get("capability_id") or "")
        matches = []
        for profile in self.capability_profiles:
            if not fnmatch.fnmatchcase(source, str(profile.get("source_type") or "*")):
                continue
            if not fnmatch.fnmatchcase(source_id, str(profile.get("source_id_pattern") or "*")):
                continue
            if not fnmatch.fnmatchcase(name, str(profile.get("name_pattern") or "*")):
                continue
            if not fnmatch.fnmatchcase(cap_id, str(profile.get("capability_id_pattern") or "*")):
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
class WritePlan:
    action: str            # not_applicable | legacy | reject | propose | execute
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
    policy_version: str = WRITE_POLICY_VERSION
    rejection_message: str = ""
    profile: dict | None = None
    logical_action_id: str = ""
    # Nhánh xác nhận (vòng hai)
    invocation: dict | None = None
    confirmation_code: str = ""


class WritePathCanary:
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

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _plan(action: str, reason: str, policy: WritePolicy,
              bucket: Optional[int] = None, path: str = "unassigned",
              rejection: str = "", **extra) -> WritePlan:
        return WritePlan(action, reason, path, bucket=bucket,
                         policy_version=policy.version, rejection_message=rejection,
                         **extra)

    def _legacy(self, trace, policy, bucket, reason) -> WritePlan:
        path = self.runtime.pin_execution_path(
            trace, "legacy", bucket, policy.version, reason) if trace else "legacy"
        return self._plan("legacy", reason, policy, bucket, path)

    def _reject(self, trace, policy, bucket, reason, message) -> WritePlan:
        path = self.runtime.pin_execution_path(
            trace, "write", bucket, policy.version, reason) if trace else "write"
        return self._plan("reject", reason, policy, bucket, path, message)

    def policy(self) -> WritePolicy:
        try:
            return WritePolicy.from_settings(self.settings_reader() or {})
        except Exception:
            return WritePolicy.from_settings({})

    async def _refresh_full(self, trace, brain: str, reason: str) -> bool:
        try:
            tools, route = await self.discoverer("refresh_full", brain)
            refreshed = await asyncio.to_thread(
                self.registry.refresh_tools, brain, tools, route)
            revision = str(refreshed.get("revision") or self.registry.revision(brain))
            if revision != trace.registry_revision:
                return self.runtime.rebase_registry_revision(trace, revision, reason)
            return True
        except Exception as exc:
            self.runtime.record_runtime_event(trace, "write.discovery_failed", {
                "mode": "full", "error_type": type(exc).__name__,
            })
            return False

    def _resolve_one_write(self, trace, objective: str, brain: str, channel: str,
                           policy: WritePolicy) -> tuple[dict | None, dict, str]:
        """Đúng MỘT capability write. Mơ hồ là dừng, không đoán giúp."""
        resolution = self.resolver.resolve(
            objective, brain,
            capability_resolver.ActorPolicy(
                mode="safe", channel=channel,
                allowed_effects=frozenset({"write"}),
            ),
        )
        selected = resolution.get("selected") or []
        self.runtime.record_runtime_event(trace, "resolver.write", {
            "policy_version": resolution.get("policy_version") or "",
            "registry_revision": resolution.get("registry_revision") or "",
            "candidate_count": resolution.get("candidate_count", 0),
            "selected_count": len(selected),
            "miss_class": resolution.get("miss_class") or "",
        })
        if not selected:
            return None, resolution, "no_write_capability"
        if len(selected) != 1:
            return None, resolution, "write_capability_ambiguous"
        if resolution.get("miss_class"):
            return None, resolution, "higher_ranked_capability_blocked"
        if float(selected[0].get("score") or 0) < policy.min_resolver_score:
            return None, resolution, "resolver_score_too_low"
        records = self.registry.get_capabilities([selected[0]["capability_id"]], brain)
        if len(records) != 1:
            return None, resolution, "registry_record_missing"
        capability = records[0]
        if (capability.get("side_effect") != "write" or
                capability.get("required_mode") != "safe"):
            return None, resolution, "capability_not_write_safe"
        return capability, resolution, ""

    # ------------------------------------------------- vòng 1: lập đề xuất

    async def prepare(self, trace: context_runtime.TurnTrace | None, objective: str,
                      brain: str, channel: str, provider: str, model: str,
                      provider_kind: str, actor_id: str,
                      has_attachments: bool = False) -> WritePlan:
        """Toàn bộ admission chạy TRƯỚC model call. Không nhánh nào ở đây gọi tool."""
        policy = self.policy()
        if not trace:
            return self._plan("not_applicable", "trace_unavailable", policy)
        bucket = fast_path_runtime.stable_bucket(trace.session_id, policy.salt)
        if policy.mode not in ("canary", "on"):
            return self._plan("not_applicable", "mode_not_canary", policy, bucket)
        if policy.allocation_basis_points <= bucket:
            return self._plan("not_applicable", "outside_allocation", policy, bucket)
        if not policy.capability_profiles:
            return self._plan("not_applicable", "no_write_group_enabled", policy, bucket)
        if channel not in policy.channels or provider_kind not in policy.provider_kinds:
            return self._plan("not_applicable", "route_not_allowed", policy, bucket)
        if has_attachments:
            return self._legacy(trace, policy, bucket, "attachment_present")
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
            if not await self._refresh_full(trace, brain, "write_preflight_refresh"):
                return self._legacy(trace, policy, bucket, "registry_refresh_failed")

        capability, resolution, error = await asyncio.to_thread(
            self._resolve_one_write, trace, objective, brain, channel, policy)
        if error == "no_write_capability":
            return self._plan("not_applicable", error, policy, bucket)
        if error:
            return self._legacy(trace, policy, bucket, error)
        profile = policy.profile_for(capability)
        if profile is None:
            return self._legacy(trace, policy, bucket, "capability_not_allowlisted")
        # Spec Phase 9: tool không reconcile được thì hoặc dùng legacy, hoặc phải
        # được operator khai rõ là chấp nhận dừng ở UNKNOWN.
        if not profile.get("reconcile_capability_id") and not profile.get("allow_unreconcilable"):
            return self._legacy(trace, policy, bucket, "capability_cannot_reconcile")

        async def current_write_route() -> tuple[dict | None, dict | None]:
            tools, route = await self.discoverer("write", brain)
            by_name = {str(x.get("fn") or x.get("name") or ""): x for x in tools}
            return by_name.get(capability["name"]), route.get(capability["name"])

        try:
            tool, route_entry = await current_write_route()
        except Exception as exc:
            self.runtime.record_runtime_event(trace, "write.discovery_failed", {
                "mode": "write", "error_type": type(exc).__name__,
            })
            return self._legacy(trace, policy, bucket, "write_discovery_failed")
        live_hash = self.registry.schema_hash((tool or {}).get("schema") or {})
        if not tool or not route_entry or live_hash != capability.get("schema_hash"):
            # Schema đổi giữa resolve và invoke: KHÔNG chạy schema cũ cho write.
            return self._legacy(trace, policy, bucket, "schema_revision_mismatch")
        if (str(route_entry.get("effect") or "") != "write" or
                str(route_entry.get("required_mode") or "") != "safe" or
                not callable(route_entry.get("call"))):
            return self._legacy(trace, policy, bucket, "write_route_invalid")

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
                report.get("selected_count") != 1 or
                report.get("preflight_decision") != "would_allow"):
            return self._reject(
                trace, policy, bucket, "write_compile_rejected",
                "Yêu cầu vượt context budget đã xác minh cho vòng lập tham số. "
                "Javis chưa gửi model call và chưa gọi tool.",
            )
        estimate = max(1, _int(report.get("estimated_input_tokens"), 1))
        if estimate > rule.hard_max_input_tokens:
            return self._reject(
                trace, policy, bucket, "hard_input_limit",
                "Yêu cầu vượt hard context limit. Javis chưa gửi model call nào.",
            )
        reserved_input = int(math.ceil(estimate * policy.estimator_safety_factor))
        path = self.runtime.pin_execution_path(
            trace, "write", bucket, policy.version, "write_admission_candidate")
        if path != "write":
            return self._plan("legacy", "task_already_pinned", policy, bucket, path)
        admission = self.runtime.admit_quota(
            trace, provider, model, reserved_input, rule.reserved_output_tokens,
            rule.rolling_tpm, rule.window_seconds,
        )
        if not admission.allowed:
            return self._plan(
                "reject", admission.reason, policy, bucket, "write",
                "Model hiện tại không còn đủ ngân sách token. Javis chưa gửi request nào.",
            )
        lease = self.executor.issue_lease(
            trace, actor_id, brain, capability, profile, allow_write=True)
        if lease is None:
            self.runtime.release_quota(trace, admission.reservation_id, "lease_issue_failed")
            return self._plan(
                "reject", "lease_issue_failed", policy, bucket, "write",
                "Capability không đạt policy lease write. Javis chưa gọi model hoặc tool.",
            )
        rendered = compiled.capsule.rendered_request
        return WritePlan(
            "propose", "admitted", "write", bucket=bucket,
            messages=tuple(rendered.get("messages") or []),
            tool_spec=(rendered.get("tools") or [None])[0],
            lease=lease, route_call=route_entry["call"], compile_request=request,
            reservation_id=admission.reservation_id,
            estimated_input_tokens=estimate,
            reserved_input_tokens=reserved_input,
            reserved_output_tokens=rule.reserved_output_tokens,
            policy_version=policy.version, profile=dict(profile),
            logical_action_id=hashlib.sha256(
                _norm(objective).encode("utf-8", errors="replace")
            ).hexdigest()[:32],
        )

    def register_proposal(self, trace, plan: WritePlan, args: dict,
                          session_id: str) -> dict:
        """Ghi ý định write vào ledger ở trạng thái PREPARED, trước khi hỏi người dùng.

        Đây là nơi ba hàng rào chống chạy trùng được đặt xuống: idempotency key,
        resource lock và mã xác nhận.
        """
        policy = self.policy()
        lease = plan.lease
        profile = plan.profile or {}
        args_hash = arguments_hash(args)
        key = idempotency_key(
            trace.task_id, plan.logical_action_id, lease.capability_id,
            lease.revision, args)
        lock_fields = tuple(str(x) for x in (profile.get("resource_lock_fields") or []))
        lock_key = resource_lock_key(lease.capability_id, args, lock_fields)
        code = confirmation_code(trace.task_id, args_hash, policy.salt)
        result = self.runtime.prepare_write_invocation(
            trace, lease.lease_id, lease.capability_id, lease.revision,
            lease.actor_hash, args_hash, key, lock_key, code, session_id,
            ttl_seconds=policy.confirmation_ttl_seconds,
        )
        result["confirmation_code"] = code
        result["args_hash"] = args_hash
        return result

    # -------------------------------------------- vòng 2: người dùng xác nhận

    def pending_for(self, session_id: str, message: str) -> WritePlan:
        """Khớp tin nhắn của người dùng với ý định write đang chờ. Không đoán mò."""
        policy = self.policy()
        kind, code = parse_confirmation(message)
        if not kind:
            return self._plan("not_applicable", "no_confirmation_token", policy)
        if kind == "cancel":
            return self._plan("not_applicable", "cancel_without_code", policy)
        invocation = self.runtime.find_pending_write(session_id, code)
        if not invocation:
            return self._plan("not_applicable", "no_pending_write", policy)
        return self._plan("execute", "confirmed", policy, path="write",
                          invocation=invocation, confirmation_code=code)

    async def execute_confirmed(self, trace, invocation: dict,
                                route_call: Callable[[dict], Awaitable[Any]],
                                args: dict, timeout_seconds: float,
                                actor_hash: str) -> dict:
        """Thực thi ĐÚNG MỘT lần. Timeout/exception -> UNKNOWN, tuyệt đối không retry."""
        invocation_id = str(invocation.get("id") or "")
        lease_id = str(invocation.get("lease_id") or "")
        if arguments_hash(args) != str(invocation.get("args_hash") or ""):
            # Tham số bị đổi giữa lúc đề xuất và lúc xác nhận: người dùng đã duyệt
            # một hành động KHÁC với hành động sắp chạy.
            self.runtime.finish_write_invocation(
                trace, invocation_id, lease_id, "FAILED_VALIDATION",
                error_code="args_changed_after_confirmation")
            return {"status": "FAILED_VALIDATION", "error_code": "args_changed_after_confirmation"}
        if not self.runtime.start_write_invocation(trace, invocation_id, actor_hash):
            return {"status": "REJECTED", "error_code": "not_prepared_or_actor_mismatch"}
        try:
            result = await asyncio.wait_for(
                route_call(args), timeout=max(1.0, float(timeout_seconds or 30)))
        except (TimeoutError, asyncio.TimeoutError):
            self.runtime.finish_write_invocation(
                trace, invocation_id, lease_id, "UNKNOWN", error_code="write_timeout")
            return {"status": "UNKNOWN", "error_code": "write_timeout",
                    "invocation_id": invocation_id}
        except asyncio.CancelledError:
            self.runtime.finish_write_invocation(
                trace, invocation_id, lease_id, "UNKNOWN", error_code="cancelled_in_flight")
            raise
        except Exception as exc:
            # Exception phía client KHÔNG chứng minh server chưa thực hiện.
            self.runtime.finish_write_invocation(
                trace, invocation_id, lease_id, "UNKNOWN",
                error_code=f"write_exception:{type(exc).__name__}")
            return {"status": "UNKNOWN", "error_code": f"write_exception:{type(exc).__name__}",
                    "invocation_id": invocation_id}
        if str(result).startswith("ERROR:"):
            # Tool trả lỗi tường minh: đây là bằng chứng hành động KHÔNG xảy ra.
            self.runtime.finish_write_invocation(
                trace, invocation_id, lease_id, "FAILED_FINAL",
                error_code="tool_returned_error")
            return {"status": "FAILED_FINAL", "error_code": "tool_returned_error",
                    "invocation_id": invocation_id, "result": str(result)[:2000]}
        evidence = None
        try:
            evidence = self.executor.evidence_store.put(
                trace, "capability_write",
                f"{invocation.get('capability_id')}:{invocation.get('capability_revision')}",
                result,
                metadata={"capability_id": invocation.get("capability_id"),
                          "capability_revision": invocation.get("capability_revision"),
                          "invocation_id": invocation_id, "effect": "write"},
            )
        except Exception as exc:
            # Write ĐÃ chạy nhưng không lưu được evidence: vẫn là SUCCEEDED, chỉ mất
            # bằng chứng. Không được coi là thất bại rồi chạy lại.
            self.runtime.finish_write_invocation(
                trace, invocation_id, lease_id, "SUCCEEDED",
                error_code=f"evidence_store_failed:{type(exc).__name__}")
            return {"status": "SUCCEEDED", "invocation_id": invocation_id,
                    "error_code": f"evidence_store_failed:{type(exc).__name__}"}
        self.runtime.finish_write_invocation(
            trace, invocation_id, lease_id, "SUCCEEDED", evidence_id=evidence.id,
            provider_request_id=str((invocation.get("capability_id") or ""))[:200])
        return {"status": "SUCCEEDED", "invocation_id": invocation_id, "evidence": evidence}

    async def reconcile_unknown(self, trace, invocation: dict, brain: str,
                                profile: dict) -> dict:
        """Kết luận một write UNKNOWN bằng READ, không bao giờ bằng cách chạy lại write."""
        reconcile_id = str(profile.get("reconcile_capability_id") or "")
        invocation_id = str(invocation.get("id") or "")
        if not reconcile_id:
            return {"status": "UNKNOWN", "reason": "no_reconcile_capability"}
        records = self.registry.get_capabilities([reconcile_id], brain)
        if len(records) != 1 or records[0].get("side_effect") not in ("none", "read"):
            return {"status": "UNKNOWN", "reason": "reconcile_capability_unavailable"}
        try:
            _tools, route = await self.discoverer("readonly", brain)
            entry = route.get(records[0]["name"])
            if not entry or not callable(entry.get("call")):
                return {"status": "UNKNOWN", "reason": "reconcile_route_unavailable"}
            result = await asyncio.wait_for(
                entry["call"](dict(profile.get("reconcile_arguments") or {})),
                timeout=max(1.0, _float(profile.get("timeout_seconds"), 30)),
            )
        except Exception as exc:
            self.runtime.record_runtime_event(trace, "write.reconcile_failed", {
                "invocation_id": invocation_id, "error_type": type(exc).__name__,
            })
            return {"status": "UNKNOWN", "reason": "reconcile_call_failed"}
        marker = str(profile.get("reconcile_success_marker") or "")
        if not marker:
            return {"status": "UNKNOWN", "reason": "no_reconcile_marker"}
        landed = marker in str(result)
        self.runtime.resolve_unknown_write(trace, invocation_id, landed)
        return {"status": "SUCCEEDED" if landed else "FAILED_FINAL",
                "reason": "reconciled", "landed": landed}
