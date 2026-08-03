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
import limit_learner
import model_limits
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
    # Câu nói cho người dùng khi action == "reject". Rỗng ở mọi action khác.
    rejection_message: str = ""


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
    def _subscription_quota(settings: dict) -> dict | None:
        """Ngân sách ngữ cảnh cho engine chạy bằng GÓI THUÊ BAO (Claude Code, Codex).

        Gói thuê bao không công bố hạn mức token-mỗi-phút, nên `_quota` bên dưới luôn trả
        None cho chúng và cả Phase 8 fail-closed về legacy vĩnh viễn - tức là toàn bộ phần
        tiết kiệm ngữ cảnh chỉ dùng được cho người có API key. Đó đúng là chỗ chủ repo bảo
        "phải dùng được cho cả Claude lẫn ChatGPT subscription".

        Ở đây KHÔNG suy ra hạn mức thương mại nào. Chỉ đọc trần ngữ cảnh do người vận hành
        khai trong `context_runtime.subscription_context` (mặc định có sẵn trong config), rồi
        đặt rolling_tpm bằng đúng trần đó để nó KHÔNG phải ràng buộc nào cả - cửa sổ trượt
        theo phút là thứ ta không biết và không được đoán.
        """
        runtime = (settings or {}).get("context_runtime") or {}
        raw = runtime.get("subscription_context")
        if not isinstance(raw, dict):
            return None
        try:
            reserved = max(1, int(raw.get("reserved_output_tokens") or 0))
            window = int(raw.get("context_window") or 0)
            hard_input = int(raw.get("max_input_tokens") or 0)
        except (TypeError, ValueError):
            return None
        if hard_input <= 0 and window > reserved:
            hard_input = window - reserved
        if hard_input <= 0:
            return None
        return {"hard_input": hard_input, "rolling_tpm": hard_input + reserved,
                "reserved": reserved, "id": "subscription-context", "soft": True}

    @staticmethod
    def _api_context_quota(settings: dict) -> dict | None:
        """Ngân sách biên soạn mặc định cho engine dùng API KEY, khi chưa biết gì khác.

        Cùng lỗ hổng với trần thuê bao ở trên, nhưng rộng hơn nhiều: `_quota` chỉ nhận hạn
        mức khai tay, mà bảng gợi ý `model_limits.KNOWN_LIMITS` hiện CHỈ có Groq. Nên người
        dùng OpenRouter, OpenAI, Gemini hay Anthropic API bấm mức Tối ưu là bật một đường
        fail-closed: trang báo đã bật và giảm 89%, còn mọi lượt vẫn gửi nguyên CLAUDE.md.
        Bốn trên năm engine API key rơi vào ca đó.

        Ở đây KHÔNG suy ra hạn mức thương mại nào - điều model_limits cố ý từ chối làm. Chỉ
        đọc trần ngữ cảnh người vận hành khai trong `context_runtime.api_context` (mặc định
        có sẵn), và trần đó là SOFT: vượt thì về đường cũ chứ không được reject lượt chat của
        người dùng bằng một con số của chính mình.
        """
        runtime = (settings or {}).get("context_runtime") or {}
        raw = runtime.get("api_context")
        if not isinstance(raw, dict):
            return None
        if not raw.get("enabled", True):
            return None
        try:
            reserved = max(1, int(raw.get("reserved_output_tokens") or 0))
            window = int(raw.get("context_window") or 0)
            hard_input = int(raw.get("max_input_tokens") or 0)
        except (TypeError, ValueError):
            return None
        if hard_input <= 0 and window > reserved:
            hard_input = window - reserved
        if hard_input <= 0:
            return None
        return {"hard_input": hard_input, "rolling_tpm": hard_input + reserved,
                "reserved": reserved, "id": "api-context", "soft": True}

    @staticmethod
    def _learned_quota(settings: dict, provider: str, model: str) -> dict | None:
        """Ngân sách dựng từ hạn mức Javis TỰ HỌC được từ lỗi nhà cung cấp.

        Đây không phải suy đoán hạn mức thương mại - điều mà module này vẫn từ chối làm. Đây
        là con số chính nhà cung cấp vừa nói ra cho ĐÚNG tài khoản này, đáng tin hơn mọi bảng
        tra. Chỗ này tồn tại vì thứ tự cũ bị ngược: fail-closed đòi khai quota trước, nên
        đúng lúc bị siết lại là đúng lúc phần tiết kiệm ngữ cảnh không chạy.

        Chỉ nhận hạn mức DÙNG ĐƯỢC làm ngân sách một request (token mỗi phút, cửa sổ ngữ
        cảnh). Hạn mức đếm lượt hay đếm theo ngày bị `learned_token_limit` loại từ trước.
        """
        runtime = (settings or {}).get("context_runtime") or {}
        raw = runtime.get("learned_quota")
        raw = raw if isinstance(raw, dict) else {}
        if not raw.get("enabled", True):
            return None
        fact = limit_learner.learned_token_limit(provider, model)
        if not fact:
            return None
        try:
            reserved = max(1, int(raw.get("reserved_output_tokens") or 1200))
            safety = float(raw.get("safety_factor") or 0.85)
        except (TypeError, ValueError):
            return None
        safety = max(0.1, min(safety, 0.99))
        hard_input = int(fact.limit * safety) - reserved
        if hard_input <= 0:
            return None
        return {"hard_input": hard_input, "rolling_tpm": fact.limit, "reserved": reserved,
                "id": f"learned:{fact.source}"}

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

    def _configured_providers(self) -> tuple[str, ...]:
        """Provider người dùng ĐÃ cấu hình khoá, để gợi ý đường lui có thật.

        Chỉ đọc SỰ TỒN TẠI của khoá, không đọc giá trị khoá. Gợi ý là phần phụ nên mọi lỗi
        đều nuốt về rỗng, không được làm hỏng lượt chat."""
        try:
            model_cfg = (self.settings_reader() or {}).get("model") or {}
        except Exception:  # noqa: BLE001 - xem docstring
            return ()
        out = []
        for field_name, name in (("openrouter_key", "openrouter"), ("openai_api_key", "openai"),
                                 ("gemini_api_key", "gemini"), ("groq_api_key", "groq"),
                                 ("anthropic_api_key", "anthropic")):
            if str(model_cfg.get(field_name) or "").strip():
                out.append(name)
        return tuple(out)

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
        subscription = str(provider_kind or "").strip().casefold() in ("cli", "oauth")
        # Thứ tự: người vận hành khai tay > hạn mức đã HỌC từ lỗi > trần ngữ cảnh gói thuê
        # bao. Khai tay đứng trước vì đó là chủ đích rõ ràng của người vận hành; hạn mức học
        # được đứng trên trần thuê bao vì nó là con số nhà cung cấp nói cho đúng tài khoản này.
        quota = self._quota(settings, provider, model)
        if quota is None:
            quota = self._learned_quota(settings, provider, model)
        if quota is None and subscription:
            quota = self._subscription_quota(settings)
        if quota is None and not subscription:
            # Engine API key chưa có hạn mức nào biết được. Trước đây dừng ở đây là legacy
            # vĩnh viễn, tức bấm mức tiết kiệm xong không tiết kiệm gì mà trang vẫn báo đã
            # bật. Trần mặc định là SOFT nên nó chỉ dùng để biên soạn, không để chặn.
            quota = self._api_context_quota(settings)
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
            # Rơi về legacy ở đây là SAI CHIỀU khi lý do là ngân sách. Phase 8 tồn tại để
            # THAY CLAUDE.md bằng capsule nhỏ; legacy là đường gửi nguyên CLAUDE.md cộng
            # MEMORY.md, tức là lớn hơn hẳn cái vừa bị từ chối vì quá lớn. Provider sẽ trả
            # lỗi hạn mức, và người dùng chỉ thấy một lỗi khó hiểu từ nhà cung cấp.
            #
            # Đây đúng là ca đã chặn Javis: gói Groq 12.000 TPM, một lượt cần 21.446 token.
            quota_reason = context_compiler.quota_block_reason(report)
            # Ngân sách SOFT = con số của CHÍNH TA (trần thuê bao, trần ngữ cảnh API mặc
            # định), không phải lời nhà cung cấp. Vượt nó thì lui về đường cũ, tuyệt đối
            # không được lấy nó ra để từ chối lượt chat của người dùng.
            if quota_reason and quota.get("soft") and not subscription:
                return AdaptiveContextPlan(
                    "legacy", "self_declared_soft_over_budget", feature_status=status,
                    compiler_report=report)
            if quota_reason and subscription:
                # ... TRỪ engine thuê bao. Ở đó con số vừa vượt là TRẦN NGỮ CẢNH do ta tự khai
                # trong subscription_context, không phải hạn mức nhà cung cấp nói ra. Lấy một
                # con số của chính mình để TỪ CHỐI lượt chat của người dùng là vượt quyền: khai
                # nhầm thấp một lần là chết cả đường Claude Code, mà lỗi đó lại im lặng.
                # Nhà cung cấp mới là bên có quyền nói không - để nó nói.
                return AdaptiveContextPlan(
                    "legacy", "subscription_soft_over_budget", feature_status=status,
                    compiler_report=report)
            if quota_reason:
                needed = (int(report.get("estimated_input_tokens") or 0)
                          + int(report.get("reserved_output_tokens") or 0))
                return AdaptiveContextPlan(
                    "reject", quota_reason, feature_status=status, compiler_report=report,
                    rejection_message=(
                        "Javis chưa gửi request vì biết trước là sẽ vượt hạn mức. "
                        + model_limits.blocked_hint(provider, model, needed,
                                                    self._configured_providers())
                    ),
                )
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
            # Ghim TÊN đường chạy. Không ghim thì lượt này vẫn bị đếm là "legacy", nên trang
            # Tiết kiệm token không phân biệt nổi lượt đã tiết kiệm với lượt gửi nguyên
            # CLAUDE.md - mà đó chính là con số duy nhất người dùng cần thấy.
            try:
                self.runtime.pin_execution_path(
                    trace, "sources", None, PHASE8_POLICY_VERSION, "context_sources")
            except Exception:  # noqa: BLE001 - ghim hỏng không được phá lượt chat
                pass
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
