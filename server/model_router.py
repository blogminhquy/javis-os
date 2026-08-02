"""Adaptive Runtime Phase 12: chọn model theo từng bước.

Spec để phase này cuối cùng vì đổi model làm tăng mạnh số biến khi debug. Nguyên tắc
nặng nhất của mục 9.3 cũng chính là thứ dễ vi phạm nhất:

    **Không đổi model chỉ để tiết kiệm nếu việc đổi làm mất năng lực cần thiết.**

Nên router ở đây làm việc theo thứ tự cứng: LỌC trước, XẾP HẠNG sau. Ứng viên thiếu
một năng lực bắt buộc, hoặc bị chính sách dữ liệu cấm, thì bị loại hẳn - không có
điểm số nào cứu được nó. Rẻ hơn chỉ là tiêu chí xếp hạng giữa những ứng viên ĐÃ đủ
năng lực.

Router không tự đoán năng lực theo tên model. Cũng như quota ở các phase trước, mọi
thứ đều do người vận hành khai; không khai thì không có ứng viên nào và ta giữ nguyên
model người dùng đã chọn. Đoán mò "gpt-4 chắc là có vision" là cách chắc chắn để một
ngày nào đó gửi ảnh vào một model mù.
"""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

ROUTER_POLICY_VERSION = "model-router-canary-v1"

# Năng lực có thể bắt buộc cho một bước. Thiếu là loại, không phải trừ điểm.
CAPABILITY_FLAGS = ("tools", "vision", "reasoning", "parallel_tools", "prompt_cache")


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return int(default)


def _float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
        return parsed if parsed == parsed and parsed not in (float("inf"), float("-inf")) else float(default)
    except (TypeError, ValueError, OverflowError):
        return float(default)


@dataclass(frozen=True)
class ModelCandidate:
    """Một model người vận hành khai là dùng được, kèm năng lực và giá thật."""
    id: str
    provider: str
    model: str
    supports: frozenset[str]
    context_window: int
    input_cost_per_million: float
    output_cost_per_million: float
    latency_hint_ms: int
    reliability: float
    data_classes: frozenset[str]
    priority: int
    # Cờ RIÊNG cho "đây là model hạng thấp hơn". Không dùng chung với `priority`:
    # priority là thứ tự xếp hạng, còn cái này là rào an toàn cho bước rủi ro.
    is_downgrade: bool

    @classmethod
    def from_rule(cls, raw: dict, index: int) -> Optional["ModelCandidate"]:
        provider = str(raw.get("provider") or "").strip().casefold()
        model = str(raw.get("model") or "").strip()
        if not provider or not model:
            return None
        input_cost = _float(raw.get("input_cost_per_million"), -1.0)
        output_cost = _float(raw.get("output_cost_per_million"), -1.0)
        context = _int(raw.get("context_window"), 0)
        # Thiếu giá hoặc thiếu cửa sổ context thì không xếp hạng nổi -> bỏ, fail-closed.
        if input_cost < 0 or output_cost < 0 or context <= 0:
            return None
        supports = {str(x).strip().casefold() for x in (raw.get("supports") or [])}
        return cls(
            id=str(raw.get("id") or f"model-rule-{index + 1}")[:120],
            provider=provider, model=model,
            supports=frozenset(x for x in supports if x in CAPABILITY_FLAGS),
            context_window=context,
            input_cost_per_million=input_cost,
            output_cost_per_million=output_cost,
            latency_hint_ms=max(0, _int(raw.get("latency_hint_ms"), 0)),
            reliability=max(0.0, min(_float(raw.get("reliability"), 1.0), 1.0)),
            # Lớp dữ liệu model này được phép nhận. Rỗng = chỉ nhận dữ liệu thường.
            data_classes=frozenset(
                str(x).strip().casefold() for x in (raw.get("data_classes") or [])),
            priority=_int(raw.get("priority"), 0),
            is_downgrade=bool(raw.get("downgrade", False)),
        )


@dataclass(frozen=True)
class RoutingRequest:
    """Yêu cầu của MỘT bước, không phải của cả task."""
    step_kind: str = "model_step"
    requires: frozenset[str] = frozenset()
    estimated_input_tokens: int = 0
    reserved_output_tokens: int = 0
    data_class: str = ""
    risk: str = "none"
    max_cost_usd: Optional[float] = None
    deadline_ms: Optional[int] = None
    min_reliability: float = 0.0


@dataclass(frozen=True)
class RoutingDecision:
    action: str            # "route" | "keep" | "reject"
    provider: str = ""
    model: str = ""
    rule_id: str = ""
    reason: str = ""
    estimated_cost_usd: float = 0.0
    rejected: dict = field(default_factory=dict)
    considered: int = 0
    policy_version: str = ROUTER_POLICY_VERSION


@dataclass(frozen=True)
class RouterPolicy:
    mode: str
    allocation_basis_points: int
    salt: str
    candidates: tuple[ModelCandidate, ...]
    allow_downgrade_on_risk: bool
    step_kinds: tuple[str, ...]
    version: str

    @classmethod
    def from_settings(cls, settings: dict) -> "RouterPolicy":
        runtime = (settings or {}).get("context_runtime") or {}
        runtime = runtime if isinstance(runtime, dict) else {}
        raw = runtime.get("model_router_canary")
        raw = raw if isinstance(raw, dict) else {}
        candidates = []
        for index, item in enumerate(raw.get("models") or []):
            if isinstance(item, dict):
                candidate = ModelCandidate.from_rule(item, index)
                if candidate is not None:
                    candidates.append(candidate)
        return cls(
            mode=str(raw.get("mode", runtime.get("mode", "off"))).casefold(),
            allocation_basis_points=max(0, min(_int(raw.get("allocation_basis_points"), 0), 10_000)),
            salt=str(raw.get("salt") or ROUTER_POLICY_VERSION),
            candidates=tuple(candidates),
            # Bước rủi ro cao mặc định KHÔNG được đổi sang model rẻ hơn.
            allow_downgrade_on_risk=bool(raw.get("allow_downgrade_on_risk", False)),
            step_kinds=tuple(str(x) for x in (raw.get("step_kinds") or ["model_step"])),
            version=str(raw.get("policy_version") or ROUTER_POLICY_VERSION)[:120],
        )

    def admits(self, session_id: str) -> tuple[bool, int, str]:
        from fast_path_runtime import stable_bucket
        bucket = stable_bucket(session_id, self.salt)
        if self.mode not in ("canary", "on"):
            return False, bucket, "mode_not_canary"
        if bucket >= self.allocation_basis_points:
            return False, bucket, "outside_allocation"
        if not self.candidates:
            return False, bucket, "no_model_rules_declared"
        return True, bucket, "admitted"


class ModelRouter:
    """Lọc theo năng lực và chính sách TRƯỚC, rồi mới xếp hạng theo chi phí."""

    def __init__(self, settings_reader: Callable[[], dict]):
        self.settings_reader = settings_reader

    def policy(self) -> RouterPolicy:
        try:
            return RouterPolicy.from_settings(self.settings_reader() or {})
        except Exception:
            return RouterPolicy.from_settings({})

    @staticmethod
    def _cost(candidate: ModelCandidate, request: RoutingRequest) -> float:
        return (max(0, request.estimated_input_tokens) * candidate.input_cost_per_million
                + max(0, request.reserved_output_tokens) * candidate.output_cost_per_million) / 1_000_000

    def _reject_reason(self, candidate: ModelCandidate, request: RoutingRequest,
                       policy: RouterPolicy) -> str:
        """Lọc CỨNG. Trả mã lý do nếu loại; rỗng nếu ứng viên đi tiếp được."""
        missing = sorted(request.requires - candidate.supports)
        if missing:
            # Đây là luật nặng nhất của mục 9.3: thiếu năng lực thì rẻ mấy cũng loại.
            return f"missing_capability:{','.join(missing)}"
        needed = max(0, request.estimated_input_tokens) + max(0, request.reserved_output_tokens)
        if needed > candidate.context_window:
            return "context_window_too_small"
        if request.data_class and request.data_class.casefold() not in candidate.data_classes:
            # Chính sách dữ liệu: model chưa được khai là nhận được lớp dữ liệu này
            # thì không bao giờ được nhận, kể cả khi nó là ứng viên duy nhất.
            return f"data_class_not_allowed:{request.data_class[:40]}"
        if candidate.reliability < request.min_reliability:
            return "reliability_below_requirement"
        if (request.deadline_ms is not None and candidate.latency_hint_ms
                and candidate.latency_hint_ms > request.deadline_ms):
            return "latency_hint_exceeds_deadline"
        cost = self._cost(candidate, request)
        if request.max_cost_usd is not None and cost > request.max_cost_usd:
            return "cost_above_step_budget"
        if (request.risk in ("write", "dangerous") and not policy.allow_downgrade_on_risk
                and candidate.is_downgrade):
            return "downgrade_not_allowed_for_risky_step"
        return ""

    def route(self, request: RoutingRequest, session_id: str,
              current_provider: str = "", current_model: str = "") -> RoutingDecision:
        policy = self.policy()
        admitted, _bucket, reason = policy.admits(session_id)
        if not admitted:
            return RoutingDecision("keep", current_provider, current_model,
                                   reason=reason, policy_version=policy.version)
        if request.step_kind not in policy.step_kinds:
            return RoutingDecision("keep", current_provider, current_model,
                                   reason="step_kind_not_routed",
                                   policy_version=policy.version)

        rejected: dict[str, str] = {}
        eligible: list[ModelCandidate] = []
        for candidate in policy.candidates:
            error = self._reject_reason(candidate, request, policy)
            if error:
                rejected[candidate.id] = error
            else:
                eligible.append(candidate)

        if not eligible:
            # Không ai đủ năng lực thì GIỮ NGUYÊN model người dùng đã chọn, không hạ
            # tiêu chuẩn để có cái mà chạy.
            return RoutingDecision("keep", current_provider, current_model,
                                   reason="no_eligible_model", rejected=rejected,
                                   considered=len(policy.candidates),
                                   policy_version=policy.version)

        # Xếp hạng CHỈ trong số đã đủ năng lực: ưu tiên khai báo, rồi rẻ, rồi nhanh,
        # rồi ổn định. Tie-break bằng id để quyết định deterministic.
        eligible.sort(key=lambda c: (
            -c.priority,
            self._cost(c, request),
            c.latency_hint_ms,
            -c.reliability,
            c.id,
        ))
        best = eligible[0]
        cost = self._cost(best, request)
        if best.provider == (current_provider or "").casefold() and best.model == current_model:
            return RoutingDecision("keep", best.provider, best.model, best.id,
                                   "already_on_best_model", cost, rejected,
                                   len(policy.candidates), policy.version)
        return RoutingDecision("route", best.provider, best.model, best.id,
                               "best_eligible", cost, rejected,
                               len(policy.candidates), policy.version)


def requirements_for(step_kind: str, *, needs_tools: bool = False,
                     needs_vision: bool = False, needs_reasoning: bool = False) -> frozenset[str]:
    """Suy năng lực bắt buộc từ nhu cầu THẬT của bước, không đoán theo tên model."""
    required = set()
    if needs_tools:
        required.add("tools")
    if needs_vision:
        required.add("vision")
    if needs_reasoning:
        required.add("reasoning")
    return frozenset(required)
