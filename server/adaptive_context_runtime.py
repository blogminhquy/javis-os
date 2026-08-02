"""Phase 8 adaptive context canaries for the existing API chat path.

Conversation state, memory retrieval and lazy skills have independent assignment and
fallback. They share ContextCompiler for final budgeting and provenance.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import context_compiler
import context_runtime
from context_compiler import ContextItem, HeuristicTokenizer
from conversation_state import ConversationStateStore
from lazy_skill_runtime import LazySkillSource
from memory_index import MemoryIndex

PHASE8_POLICY_VERSION = "adaptive-context-sources-v1"


def stable_bucket(session_id: str, salt: str) -> int:
    digest = hashlib.sha256(f"{salt}|{session_id}".encode("utf-8", errors="replace")).digest()
    return int.from_bytes(digest[:8], "big") % 10_000


@dataclass(frozen=True)
class FeaturePolicy:
    name: str
    version: str
    allocation_basis_points: int
    salt: str
    channels: tuple[str, ...]
    provider_kinds: tuple[str, ...]
    recent_messages: int = 6
    max_items: int = 6
    min_confidence: float = 0.38
    max_body_chars: int = 12000

    @classmethod
    def from_settings(cls, settings: dict, key: str) -> FeaturePolicy:
        # Settings do người vận hành sửa tay: một giá trị sai kiểu ("abc", "high")
        # phải rơi về default an toàn (allocation 0), không được raise giữa lượt chat.
        def _int(value, default):
            try:
                return int(value)
            except (TypeError, ValueError, OverflowError):
                return int(default)

        def _float(value, default):
            try:
                return float(value)
            except (TypeError, ValueError, OverflowError):
                return float(default)

        runtime = (settings or {}).get("context_runtime") or {}
        runtime = runtime if isinstance(runtime, dict) else {}
        raw = runtime.get(key) if isinstance(runtime.get(key), dict) else {}
        bps = raw.get("allocation_basis_points", 0)
        return cls(
            name=key,
            version=str(raw.get("policy_version") or f"{key}-v1"),
            allocation_basis_points=max(0, min(_int(bps or 0, 0), 10_000)),
            salt=str(raw.get("salt") or f"{key}-v1"),
            channels=tuple(str(x) for x in (raw.get("channels") or ["dashboard"])),
            provider_kinds=tuple(str(x) for x in (raw.get("provider_kinds") or ["api"])),
            recent_messages=max(2, min(_int(raw.get("recent_messages") or 6, 6), 20)),
            max_items=max(1, min(_int(raw.get("max_items") or 6, 6), 12)),
            min_confidence=max(0.0, min(_float(raw.get("min_confidence") or 0.38, 0.38), 1.0)),
            max_body_chars=max(1000, min(_int(raw.get("max_body_chars") or 12000, 12000), 40000)),
        )

    def assigned(self, mode: str, session_id: str, channel: str, provider_kind: str) -> tuple[bool, int, str]:
        bucket = stable_bucket(session_id, self.salt)
        if mode not in ("canary", "on"):
            return False, bucket, "mode_not_canary"
        if bucket >= self.allocation_basis_points:
            return False, bucket, "outside_allocation"
        if channel not in self.channels:
            return False, bucket, "channel_not_allowed"
        if provider_kind not in self.provider_kinds:
            return False, bucket, "provider_kind_not_allowed"
        return True, bucket, "assigned"


@dataclass(frozen=True)
class AdaptiveContextPlan:
    action: str
    reason: str
    system_prompt: str = ""
    state_applied: bool = False
    memory_applied: bool = False
    skill_applied: bool = False
    feature_status: dict = field(default_factory=dict)
    compiler_report: dict = field(default_factory=dict)


class AdaptiveContextCanary:
    def __init__(self, state_dir: str | Path, registry, compiler,
                 runtime: context_runtime.ObserveRuntime,
                 settings_reader: Callable[[], dict]):
        self.state = ConversationStateStore(state_dir)
        self.memory = MemoryIndex(state_dir)
        self.skills = LazySkillSource(registry)
        self.registry = registry
        self.compiler = compiler
        self.runtime = runtime
        self.settings_reader = settings_reader

    @staticmethod
    def _quota(settings: dict, provider: str, model: str) -> dict | None:
        """Reuse operator-declared hard quota profiles; never infer commercial limits."""
        import fnmatch
        runtime = (settings or {}).get("context_runtime") or {}
        profiles = []
        for owner in ("context_sources", "canary"):
            raw = runtime.get(owner) if isinstance(runtime.get(owner), dict) else {}
            profiles.extend(x for x in (raw.get("quota_profiles") or []) if isinstance(x, dict))
        matches = []
        for index, item in enumerate(profiles):
            if str(item.get("provider") or "").casefold() != str(provider or "").casefold():
                continue
            pattern = str(item.get("model_pattern") or item.get("model") or "")
            if not pattern or not fnmatch.fnmatchcase(str(model or ""), pattern):
                continue
            try:
                reserved = max(1, int(item.get("reserved_output_tokens") or 0))
                hard_input = int(item.get("max_input_tokens") or 0)
                context_window = int(item.get("context_window") or 0)
                if hard_input <= 0 and context_window > reserved:
                    hard_input = context_window - reserved
                rolling = int(item.get("rolling_tpm") or 0)
            except (TypeError, ValueError):
                continue
            if hard_input > 0 and rolling > 0:
                matches.append((int(item.get("priority") or 0), len(pattern), -index, {
                    "hard_input": hard_input, "rolling_tpm": rolling, "reserved": reserved,
                    "id": str(item.get("id") or f"phase8-quota-{index + 1}"),
                }))
        return max(matches)[3] if matches else None

    @staticmethod
    def _recent_item(session_id: str, messages: list[dict], count: int) -> ContextItem | None:
        usable = [x for x in messages if x.get("role") in ("user", "assistant") and x.get("content")]
        # Current user objective is already a required compiler item.
        if usable and usable[-1].get("role") == "user":
            usable = usable[:-1]
        usable = usable[-count:]
        if not usable:
            return None
        safe = [{"role": str(x["role"]), "content": str(x["content"])[:1800],
                 "source_ref": f"session:{session_id}:message:{int(x.get('id') or 0)}"}
                for x in usable]
        content = "Recent transcript window:\n" + json.dumps(
            safe, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        tokenizer = HeuristicTokenizer("state", "recent")
        source_hash = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()
        return ContextItem(
            id="recent_transcript", kind="recent_transcript", content=content,
            source_ref=f"transcript:{session_id}:{source_hash}",
            token_cost=tokenizer.count_text(content), relevance=1.0, confidence=1.0,
            authority=1.0, freshness=1.0, required=True, trust="transcript",
        )

    def prepare(self, trace: context_runtime.TurnTrace | None, objective: str,
                brain: str | Path, session_id: str, messages: list[dict], channel: str,
                provider: str, model: str, provider_kind: str,
                base_prompt_builder: Callable[[bool, bool], str]) -> AdaptiveContextPlan:
        # Ranh giới fallback cuối: bất kỳ lỗi nào ngoài các block per-source (compile,
        # settings, event ghi trace...) đều phải trả legacy, không được phá lượt chat.
        try:
            return self._prepare(trace, objective, brain, session_id, messages, channel,
                                 provider, model, provider_kind, base_prompt_builder)
        except Exception as exc:  # noqa: BLE001 - fallback-per-turn invariant
            return AdaptiveContextPlan("legacy", f"prepare_error:{type(exc).__name__}")

    def _prepare(self, trace: context_runtime.TurnTrace | None, objective: str,
                 brain: str | Path, session_id: str, messages: list[dict], channel: str,
                 provider: str, model: str, provider_kind: str,
                 base_prompt_builder: Callable[[bool, bool], str]) -> AdaptiveContextPlan:
        try:
            settings = self.settings_reader() or {}
        except Exception:  # noqa: BLE001 - settings failure must fail closed to legacy
            settings = {}
        runtime_cfg = settings.get("context_runtime") or {}
        mode = str(runtime_cfg.get("mode") or "off").casefold()
        policies = {
            "conversation_state": FeaturePolicy.from_settings(settings, "conversation_state_canary"),
            "memory": FeaturePolicy.from_settings(settings, "memory_canary"),
            "skill": FeaturePolicy.from_settings(settings, "lazy_skill_canary"),
        }
        status = {}
        assigned = {}
        for name, policy in policies.items():
            enabled, bucket, reason = policy.assigned(mode, session_id, channel, provider_kind)
            assigned[name] = enabled
            status[name] = {"assigned": enabled, "applied": False, "reason": reason,
                            "bucket": bucket, "policy_version": policy.version}
        if not any(assigned.values()):
            return AdaptiveContextPlan("legacy", "no_phase8_assignment", feature_status=status)
        quota = self._quota(settings, provider, model)
        if quota is None:
            for value in status.values():
                if value["assigned"]:
                    value["reason"] = "hard_quota_unknown"
            return AdaptiveContextPlan("legacy", "hard_quota_unknown", feature_status=status)

        brain = Path(brain).resolve()
        items: list[ContextItem] = []
        structured = None
        state_applied = memory_applied = skill_applied = False
        if assigned["conversation_state"]:
            try:
                structured = self.state.rebuild(session_id, brain, messages)
                items.append(structured.context_item())
                recent = self._recent_item(session_id, messages, policies["conversation_state"].recent_messages)
                if recent:
                    items.append(recent)
                state_applied = True
                status["conversation_state"].update(
                    {"applied": True, "reason": "projected", "revision": structured.revision}
                )
            except Exception as exc:  # noqa: BLE001 - source rollback boundary
                status["conversation_state"]["reason"] = "projection_error:" + type(exc).__name__

        if assigned["memory"]:
            try:
                active = structured.query_terms() if structured else []
                found = self.memory.retrieve(
                    brain, objective, active_state=active,
                    limit=policies["memory"].max_items,
                    min_confidence=policies["memory"].min_confidence,
                )
                status["memory"].update({
                    "confidence": found.confidence, "coverage": found.coverage,
                    "widened": found.widened, "stages": list(found.stages),
                    "revision": found.index_revision, "record_count": len(found.records),
                    "conflict_count": len(found.conflicts),
                })
                if found.fallback_required:
                    status["memory"]["reason"] = found.fallback_reason
                else:
                    items.extend(found.context_items())
                    memory_applied = True
                    status["memory"].update({"applied": True, "reason": "retrieved"})
            except Exception as exc:  # noqa: BLE001 - source rollback boundary
                status["memory"]["reason"] = "retrieval_error:" + type(exc).__name__

        if assigned["skill"]:
            try:
                selected = self.skills.resolve(
                    brain, objective, max_body_chars=policies["skill"].max_body_chars
                )
                status["skill"].update({
                    "reason": selected.reason, "score": selected.score,
                    "runner_up_score": selected.runner_up_score,
                    "capability_id": selected.capability_id, "slug": selected.slug,
                    "revision": selected.registry_revision,
                })
                if selected.action in ("load", "none"):
                    if selected.context_item:
                        items.append(selected.context_item)
                    skill_applied = True
                    status["skill"]["applied"] = True
            except Exception as exc:  # noqa: BLE001 - source rollback boundary
                status["skill"]["reason"] = "skill_error:" + type(exc).__name__

        if not any((state_applied, memory_applied, skill_applied)):
            return AdaptiveContextPlan("legacy", "all_assigned_sources_fell_back", feature_status=status)

        # Unapplied/unassigned sources remain in the legacy base independently.
        base_prompt = base_prompt_builder(not memory_applied, not skill_applied)
        base_tokenizer = HeuristicTokenizer(provider, model)
        base_item = ContextItem(
            id="source_fallback_contract", kind="source_fallback_contract", content=base_prompt,
            source_ref=("javis:legacy-base:memory=" + str(not memory_applied).lower() +
                        ":skills=" + str(not skill_applied).lower()),
            token_cost=base_tokenizer.count_text(base_prompt), relevance=1.0, confidence=1.0,
            authority=1.0, freshness=1.0, required=True, trust="system",
        )
        compiled = self.compiler.compile_canary(
            context_compiler.CompileRequest(
                task_id=trace.task_id if trace else "phase8-" + hashlib.sha256(session_id.encode()).hexdigest()[:16],
                step_id=trace.step_id if trace else "context",
                objective=objective, brain=str(brain), channel=channel,
                provider=provider, model=model, model_kind=provider_kind,
                rolling_tpm_remaining=quota["rolling_tpm"],
                hard_max_input_tokens=quota["hard_input"],
                reserved_output_tokens=quota["reserved"], execution_mode="canary",
                context_items=tuple([base_item] + items),
            ),
            {"selected": [], "selected_count": 0, "candidate_count": 0, "miss_class": ""},
        )
        report = compiled.trace_report
        expected = {base_item.id}
        if state_applied:
            expected.add("conversation_state")
            if any(x.id == "recent_transcript" for x in items):
                expected.add("recent_transcript")
        if compiled.status != "compiled" or compiled.capsule is None:
            return AdaptiveContextPlan("legacy", "compiler_rejected", feature_status=status,
                                       compiler_report=report)
        selected_ids = set(report.get("selected_context_ids") or [])
        if not expected.issubset(selected_ids):
            return AdaptiveContextPlan("legacy", "required_source_dropped", feature_status=status,
                                       compiler_report=report)
        rendered = compiled.capsule.rendered_request
        system_prompt = next((str(x.get("content") or "") for x in rendered.get("messages") or []
                              if x.get("role") == "system"), "")
        if not system_prompt:
            return AdaptiveContextPlan("legacy", "compiled_system_missing", feature_status=status,
                                       compiler_report=report)
        if trace:
            self.runtime.record_runtime_event(trace, "context_sources.canary", {
                "policy_version": PHASE8_POLICY_VERSION,
                "state_applied": state_applied, "memory_applied": memory_applied,
                "skill_applied": skill_applied,
                "estimated_input_tokens": int(report.get("estimated_input_tokens") or 0),
                "source_count": int(report.get("source_count") or 0),
                "quota_rule_id": quota["id"],
            })
        return AdaptiveContextPlan(
            "use", "compiled", system_prompt, state_applied, memory_applied, skill_applied,
            status, report,
        )
