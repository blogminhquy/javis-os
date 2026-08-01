"""Read-only Capability Lease + Executor cho Adaptive Runtime Phase 6."""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

import context_runtime
from capability_registry import CapabilityRegistry
from evidence_store import Evidence, EvidenceStore


EXECUTOR_POLICY_VERSION = "readonly-executor-v1"


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def _has_external_ref(value: Any) -> bool:
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str) and ref and not ref.startswith("#/"):
            return True
        return any(_has_external_ref(x) for x in value.values())
    if isinstance(value, list):
        return any(_has_external_ref(x) for x in value)
    return False


def _depth(value: Any, limit: int = 65) -> int:
    if limit <= 0:
        return 66
    if isinstance(value, dict):
        return 1 + max((_depth(x, limit - 1) for x in value.values()), default=0)
    if isinstance(value, list):
        return 1 + max((_depth(x, limit - 1) for x in value), default=0)
    return 1


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


@dataclass(frozen=True)
class CapabilityLease:
    lease_id: str
    capability_id: str
    capability_name: str
    revision: str
    schema_hash: str
    schema: dict
    task_id: str
    step_id: str
    actor_hash: str
    allowed_effect: str
    resource_scope: dict
    expires_at: float
    brain: str
    timeout_seconds: float
    excerpt_chars: int
    max_artifact_bytes: int
    retention_seconds: int
    profile_id: str


@dataclass(frozen=True)
class InvocationResult:
    status: str
    model_payload: str
    invocation_id: str = ""
    evidence: Evidence | None = None
    error_code: str = ""


class CapabilityExecutor:
    def __init__(self, registry: CapabilityRegistry, runtime: context_runtime.ObserveRuntime,
                 evidence_store: EvidenceStore):
        self.registry = registry
        self.runtime = runtime
        self.evidence_store = evidence_store

    @staticmethod
    def actor_hash(actor_id: str) -> str:
        return hashlib.sha256(
            str(actor_id or "anonymous").encode("utf-8", errors="replace")
        ).hexdigest()

    def issue_lease(self, trace: context_runtime.TurnTrace, actor_id: str, brain: str,
                    capability: dict, profile: dict) -> CapabilityLease | None:
        effect = str(capability.get("side_effect") or "read")
        required_mode = str(capability.get("required_mode") or "readonly")
        if effect not in {"none", "read"} or required_mode != "readonly":
            return None
        schema = capability.get("schema") if isinstance(capability.get("schema"), dict) else {}
        if (_has_external_ref(schema) or _depth(schema) > 64 or
                len(json.dumps(schema, ensure_ascii=False, separators=(",", ":"))) > 262_144):
            return None
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError:
            return None
        actor_hash = self.actor_hash(actor_id)
        props = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        constraints = profile.get("argument_constraints")
        constraints = constraints if isinstance(constraints, dict) else {}
        if bool((capability.get("metadata") or {}).get("multiplexed")) and not constraints:
            return None
        scope = {
            "argument_keys": sorted(str(x) for x in props),
            "additional_properties": bool(schema.get("additionalProperties", True)),
            "argument_constraints": constraints,
            "max_argument_bytes": max(
                1024, min(_int(profile.get("max_argument_bytes"), 131_072), 1_000_000)
            ),
        }
        ttl = max(5, min(_int(profile.get("lease_ttl_seconds"), 120), 900))
        lease_id = self.runtime.create_capability_lease(
            trace, capability["capability_id"], capability["capability_revision"],
            capability["schema_hash"], actor_hash, effect, scope, ttl,
        )
        if not lease_id:
            return None
        return CapabilityLease(
            lease_id=lease_id,
            capability_id=capability["capability_id"],
            capability_name=capability["name"],
            revision=capability["capability_revision"],
            schema_hash=capability["schema_hash"],
            schema=schema,
            task_id=trace.task_id,
            step_id=trace.step_id,
            actor_hash=actor_hash,
            allowed_effect=effect,
            resource_scope=scope,
            expires_at=time.time() + ttl,
            brain=str(brain),
            timeout_seconds=max(1.0, min(_float(profile.get("timeout_seconds"), 30), 180.0)),
            excerpt_chars=max(500, min(_int(profile.get("excerpt_chars"), 4000), 20_000)),
            max_artifact_bytes=max(
                10_000, min(_int(profile.get("max_artifact_bytes"), 5_000_000), 25_000_000)
            ),
            retention_seconds=max(
                3600, min(_int(profile.get("retention_seconds"), 14 * 86400), 90 * 86400)
            ),
            profile_id=str(profile.get("id") or "readonly-default")[:120],
        )

    def _validate(self, lease: CapabilityLease, args: Any) -> tuple[bool, str]:
        if not isinstance(args, dict):
            return False, "arguments_not_object"
        try:
            args_size = len(json.dumps(
                args, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8", errors="replace"))
        except (TypeError, ValueError, OverflowError):
            return False, "arguments_not_json"
        if args_size > int(lease.resource_scope.get("max_argument_bytes") or 131_072):
            return False, "arguments_too_large"
        if _has_external_ref(lease.schema):
            return False, "external_schema_ref_blocked"
        try:
            validator = Draft202012Validator(lease.schema)
            errors = sorted(validator.iter_errors(args), key=lambda e: list(e.absolute_path))
        except (SchemaError, TypeError, ValueError):
            return False, "schema_invalid"
        if errors:
            first = errors[0]
            path_depth = len(list(first.absolute_path))
            return False, f"json_schema:{first.validator or 'invalid'}:depth_{path_depth}"
        allowed_keys = set(lease.resource_scope.get("argument_keys") or [])
        if not lease.resource_scope.get("additional_properties", True):
            if any(str(key) not in allowed_keys for key in args):
                return False, "resource_scope_argument_key"
        for key, expected in (lease.resource_scope.get("argument_constraints") or {}).items():
            if key not in args or args.get(key) != expected:
                return False, "resource_scope_argument_constraint"
        return True, ""

    async def invoke(self, trace: context_runtime.TurnTrace, actor_id: str,
                     lease: CapabilityLease, args: Any,
                     route_call: Callable[[dict], Awaitable[Any]]) -> InvocationResult:
        if (not trace or trace.task_id != lease.task_id or trace.step_id != lease.step_id or
                self.actor_hash(actor_id) != lease.actor_hash or time.time() >= lease.expires_at):
            return InvocationResult(
                "REJECTED", "ERROR: capability lease không hợp lệ hoặc đã hết hạn.",
                error_code="lease_mismatch_or_expired",
            )
        valid, error_code = self._validate(lease, args)
        if not valid:
            self.runtime.revoke_capability_lease(trace, lease.lease_id, error_code)
            self.runtime.record_runtime_event(trace, "arguments.rejected", {
                "lease_id": lease.lease_id, "capability_id": lease.capability_id,
                "error_code": error_code,
            })
            return InvocationResult(
                "FAILED_VALIDATION", "ERROR: arguments không đạt JSON Schema của capability.",
                error_code=error_code,
            )
        current = self.registry.get_capabilities([lease.capability_id], lease.brain)
        if (len(current) != 1 or current[0].get("capability_revision") != lease.revision or
                current[0].get("schema_hash") != lease.schema_hash):
            self.runtime.revoke_capability_lease(
                trace, lease.lease_id, "capability_revision_mismatch"
            )
            self.runtime.record_runtime_event(trace, "lease.revision_mismatch", {
                "lease_id": lease.lease_id, "capability_id": lease.capability_id,
                "pinned_revision": lease.revision,
                "current_revision": current[0].get("capability_revision") if current else "missing",
            })
            return InvocationResult(
                "REJECTED", "ERROR: capability revision đã thay đổi; cần resolve lại.",
                error_code="capability_revision_mismatch",
            )
        args_hash = _hash(args)
        invocation_id = self.runtime.claim_read_invocation(
            trace, lease.lease_id, lease.capability_id, lease.revision,
            lease.schema_hash, lease.actor_hash, args_hash,
        )
        if not invocation_id:
            return InvocationResult(
                "REJECTED", "ERROR: capability lease đã dùng hoặc không còn hợp lệ.",
                error_code="lease_claim_failed",
            )
        try:
            result = await asyncio.wait_for(route_call(args), timeout=lease.timeout_seconds)
        except TimeoutError:
            self.runtime.finish_read_invocation(
                trace, invocation_id, lease.lease_id, "TIMEOUT", error_code="tool_timeout"
            )
            return InvocationResult(
                "TIMEOUT", "ERROR: capability read bị timeout; task state và invocation đã được lưu.",
                invocation_id=invocation_id, error_code="tool_timeout",
            )
        except Exception as exc:
            code = f"tool_exception:{type(exc).__name__}"
            self.runtime.finish_read_invocation(
                trace, invocation_id, lease.lease_id, "FAILED_FINAL", error_code=code
            )
            return InvocationResult(
                "FAILED_FINAL", "ERROR: capability read gặp lỗi thực thi.",
                invocation_id=invocation_id, error_code=code,
            )
        if str(result).startswith("ERROR:"):
            self.runtime.finish_read_invocation(
                trace, invocation_id, lease.lease_id, "FAILED_FINAL",
                error_code="tool_returned_error",
            )
            return InvocationResult(
                "FAILED_FINAL", str(result)[:2000], invocation_id=invocation_id,
                error_code="tool_returned_error",
            )
        try:
            evidence = self.evidence_store.put(
                trace, "capability_read", f"{lease.capability_id}:{lease.revision}", result,
                metadata={
                    "capability_id": lease.capability_id,
                    "capability_revision": lease.revision,
                    "profile_id": lease.profile_id,
                    "executor_policy": EXECUTOR_POLICY_VERSION,
                },
                excerpt_chars=lease.excerpt_chars,
                max_artifact_bytes=lease.max_artifact_bytes,
                retention_seconds=lease.retention_seconds,
            )
        except Exception as exc:
            code = str(exc)[:120] or type(exc).__name__
            self.runtime.finish_read_invocation(
                trace, invocation_id, lease.lease_id, "FAILED_FINAL", error_code=code
            )
            return InvocationResult(
                "FAILED_FINAL", "ERROR: không thể lưu evidence an toàn.",
                invocation_id=invocation_id, error_code=code,
            )
        finished = self.runtime.finish_read_invocation(
            trace, invocation_id, lease.lease_id, "SUCCEEDED", evidence.id
        )
        if not finished:
            return InvocationResult(
                "FAILED_FINAL",
                f"ERROR: evidence đã lưu tại {evidence.ref} nhưng invocation ledger chưa chốt.",
                invocation_id=invocation_id, evidence=evidence,
                error_code="invocation_finalize_failed",
            )
        model_payload = json.dumps({
            "evidence_ref": evidence.ref,
            "source_type": evidence.source_type,
            "capability_id": lease.capability_id,
            "capability_name": lease.capability_name,
            "capability_revision": lease.revision,
            "content_hash": evidence.content_hash,
            "excerpt": evidence.inline_excerpt,
            "instruction": "Chỉ dùng excerpt này cho dữ liệu live và phải dẫn evidence_ref.",
        }, ensure_ascii=False, separators=(",", ":"))
        return InvocationResult(
            "SUCCEEDED", model_payload, invocation_id=invocation_id, evidence=evidence,
        )
