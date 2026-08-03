"""Fast Path Canary Phase 5.

Module này chỉ chuẩn bị một model call chat-thuần. Nó không discover tool, không chạy tool,
không đọc memory/history và không tự replay. Mọi quyết định được pin theo task; thiếu bằng
chứng an toàn hoặc hard quota thì fallback legacy trước model call.
"""
from __future__ import annotations

import fnmatch
import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Callable, Optional

import capability_resolver
import context_compiler
import context_runtime


CANARY_POLICY_VERSION = "fast-path-canary-v1"


def _norm(value: str) -> str:
    # NFKD KHÔNG phân rã "đ" (U+0111) nên phải map tay, nếu không mọi deny-pattern
    # ASCII chứa "d" ("dinh kem", "dat lich", "dang bai"...) im lặng không bao giờ khớp
    # với tiếng Việt thật - lỗ hổng classifier đã kiểm chứng bằng test.
    raw = str(value or "").replace("đ", "d").replace("Đ", "D")
    raw = unicodedata.normalize("NFKD", raw.casefold())
    return " ".join("".join(c for c in raw if not unicodedata.combining(c)).split())


def stable_bucket(session_id: str, salt: str, buckets: int = 10_000) -> int:
    digest = hashlib.sha256(
        (str(salt or CANARY_POLICY_VERSION) + "|" + str(session_id or "")).encode(
            "utf-8", errors="replace"
        )
    ).digest()
    return int.from_bytes(digest[:8], "big") % max(1, int(buckets or 10_000))


@dataclass(frozen=True)
class IntentDecision:
    eligible: bool
    intent_class: str
    reason: str
    confidence: float


class FastIntentClassifier:
    """Gate cố ý bảo thủ: false-negative đi legacy, false-positive mới là nguy hiểm."""

    _DENY = (
        ("attachment", re.compile(
            r"\b(tep|file|attachment|attached|dinh kem|hinh anh|anh nay|tai lieu|"
            r"uploaded|the document i|i uploaded)\b"
        )),
        ("url_reference", re.compile(r"(https?://|www\.)")),
        ("live_data", re.compile(
            r"\b(hom nay|hom qua|bay gio|hien tai|moi nhat|thoi tiet|tin tuc|ty gia|gia vang|"
            r"gia co phieu|lich hom|thang nay|tuan nay|quy nay|thang truoc|tuan truoc|"
            r"doanh thu|don hang|email moi|email cua|hop thu|check email|"
            r"current|latest|today|yesterday|now|this week|this month|last week|last month|"
            r"weather|news|stock price|exchange rate|revenue|my email|my inbox)\b"
        )),
        ("external_source", re.compile(
            r"\b(web|internet|google|drive|gmail|calendar|github|repository|repo|database|"
            r"api|mcp|tool|vault|obsidian|slack|notion|airtable|facebook|tiktok|zalo|telegram)\b"
        )),
        ("side_effect", re.compile(
            r"\b(gui email|gui tin|xoa|delete|remove|tao lich|dat lich|nhac toi|upload|"
            r"publish|dang bai|dang len|cap nhat file|sua file|luu vao|write to|send email|"
            r"create event|post to|schedule)\b"
        )),
        ("conversation_state", re.compile(
            r"\b(truoc day|lan truoc|vua roi|luc nay|anh da|chung ta da|nho khong|memory|"
            r"cuoc tro chuyen|tin nhan truoc|doan chat|(nhung gi|cai) (anh|em|ban) (noi|viet)|"
            r"(em|anh|ban) vua (noi|viet)|viet tiep|previously|earlier|last time|we discussed|"
            r"do you remember|my last message|this conversation|cai nay|do nay|no)\b"
        )),
        ("agentic", re.compile(
            r"\b(hay lam giup|thuc hien|kiem tra giup|tim giup|doc giup|mo giup|"
            r"execute|run|check my|look up|search for|fetch|open my)\b"
        )),
    )
    _ALLOW = (
        ("conversation", re.compile(r"^(xin chao|chao|hello|hi|cam on|thank you)\b")),
        ("explanation", re.compile(
            r"\b(la gi|giai thich|tai sao|vi sao|khai niem|phan biet|what is|explain|why|difference)\b"
        )),
        ("writing", re.compile(
            r"\b(viet|viet lai|dat ten|tieu de|y tuong|brainstorm|rewrite|draft|headline|ideas|outline)\b"
        )),
        ("transform", re.compile(r"\b(dich|tom tat|rut gon|translate|summarize|shorten)\b")),
        ("reasoning", re.compile(
            r"\b(tinh|giai bai|phan tich logic|compare|calculate|solve|pros and cons|uu nhuoc diem)\b"
        )),
    )

    def classify(self, objective: str, has_attachments: bool = False,
                 max_chars: int = 12_000) -> IntentDecision:
        text = str(objective or "").strip()
        if not text:
            return IntentDecision(False, "empty", "empty_objective", 1.0)
        if has_attachments:
            return IntentDecision(False, "attachment", "attachment_present", 1.0)
        if len(text) > max(1, int(max_chars or 12_000)):
            return IntentDecision(False, "oversized", "objective_too_large", 1.0)
        normalized = _norm(text)
        for intent_class, pattern in self._DENY:
            if pattern.search(normalized):
                return IntentDecision(False, intent_class, f"requires_{intent_class}", 0.98)
        for intent_class, pattern in self._ALLOW:
            if pattern.search(normalized):
                return IntentDecision(True, intent_class, "self_contained_chat", 0.92)
        return IntentDecision(False, "uncertain", "intent_uncertain", 0.65)


@dataclass(frozen=True)
class QuotaRule:
    provider: str
    model_pattern: str
    rolling_tpm: int
    hard_max_input_tokens: int
    reserved_output_tokens: int
    window_seconds: int
    priority: int
    rule_id: str


@dataclass(frozen=True)
class CanaryPolicy:
    mode: str
    allocation_basis_points: int
    salt: str
    channels: tuple[str, ...]
    provider_kinds: tuple[str, ...]
    registry_max_age_seconds: int
    estimator_safety_factor: float
    max_objective_chars: int
    min_resolver_score: float
    rules: tuple[QuotaRule, ...]
    version: str

    @classmethod
    def from_settings(cls, settings: dict) -> "CanaryPolicy":
        runtime = (settings or {}).get("context_runtime") or {}
        raw = runtime.get("canary") if isinstance(runtime.get("canary"), dict) else {}
        bps = raw.get("allocation_basis_points")
        if bps is None:
            try:
                bps = round(float(raw.get("percent") or 0) * 100)
            except (TypeError, ValueError):
                bps = 0
        rules = []
        for index, item in enumerate(raw.get("quota_profiles") or []):
            if not isinstance(item, dict):
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
            provider = str(item.get("provider") or "").strip().lower()
            pattern = str(item.get("model_pattern") or item.get("model") or "").strip()
            if not provider or not pattern or rolling <= 0 or hard_input <= 0:
                continue
            rule_id = str(item.get("id") or f"quota-rule-{index + 1}")[:120]
            rules.append(QuotaRule(
                provider=provider, model_pattern=pattern, rolling_tpm=rolling,
                hard_max_input_tokens=hard_input, reserved_output_tokens=reserved,
                window_seconds=max(1, min(int(item.get("window_seconds") or 60), 3600)),
                priority=int(item.get("priority") or 0), rule_id=rule_id,
            ))
        return cls(
            mode=str(runtime.get("mode") or "off").lower(),
            allocation_basis_points=max(0, min(int(bps or 0), 10_000)),
            salt=str(raw.get("salt") or CANARY_POLICY_VERSION),
            channels=tuple(str(x) for x in (raw.get("channels") or ["dashboard"])),
            provider_kinds=tuple(str(x) for x in (raw.get("provider_kinds") or ["api"])),
            registry_max_age_seconds=max(1, int(raw.get("registry_max_age_seconds") or 900)),
            estimator_safety_factor=max(1.0, min(float(raw.get("estimator_safety_factor") or 1.35), 3.0)),
            max_objective_chars=max(100, int(raw.get("max_objective_chars") or 12_000)),
            min_resolver_score=max(0.0, min(float(raw.get("min_resolver_score") or 0.45), 1.0)),
            rules=tuple(rules), version=str(raw.get("policy_version") or CANARY_POLICY_VERSION),
        )

    @staticmethod
    def _rule_thue_bao(settings: dict) -> Optional[QuotaRule]:
        """Ngân sách biên soạn cho engine gói thuê bao, đọc từ `subscription_context`.

        Cùng lý do với Phase 8: gói thuê bao không công bố hạn mức token nên `quota_rule`
        luôn trả None cho chúng, và đường tắt fail-closed vĩnh viễn. Đó là lý do mức "Siêu
        tiết kiệm" trước nay chỉ là cái tên với người dùng gói ChatGPT.

        Con số này KHÔNG phải hạn mức thương mại, chỉ là trần ngữ cảnh người vận hành tự
        khai. Đường tắt vốn không dùng nó để từ chối lượt chat: vượt trần thì compiler trả
        về không-fast và lượt rơi về đường thường.
        """
        raw = ((settings or {}).get("context_runtime") or {}).get("subscription_context")
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
        return QuotaRule(
            provider="*", model_pattern="*", rolling_tpm=hard_input + reserved,
            hard_max_input_tokens=hard_input, reserved_output_tokens=reserved,
            window_seconds=60, priority=-1, rule_id="subscription-context",
        )

    def quota_rule(self, provider: str, model: str) -> Optional[QuotaRule]:
        # Casefold cả model lẫn pattern: "LLAMA-3" phải khớp rule "llama-*" thay vì
        # rơi nhầm vào rule "*" catch-all có quota khác.
        matches = [rule for rule in self.rules if rule.provider == str(provider or "").lower()
                   and fnmatch.fnmatchcase(str(model or "").casefold(),
                                           rule.model_pattern.casefold())]
        if not matches:
            return None
        return sorted(matches, key=lambda r: (-r.priority, -len(r.model_pattern), r.rule_id))[0]


@dataclass(frozen=True)
class FastPathPlan:
    action: str
    reason: str
    execution_path: str
    bucket: Optional[int] = None
    messages: tuple[dict, ...] = ()
    reservation_id: str = ""
    capsule_hash: str = ""
    estimated_input_tokens: int = 0
    reserved_input_tokens: int = 0
    reserved_output_tokens: int = 0
    policy_version: str = CANARY_POLICY_VERSION
    rejection_message: str = ""


class FastPathCanary:
    def __init__(self, registry, resolver, compiler, runtime,
                 settings_reader: Callable[[], dict],
                 classifier: FastIntentClassifier | None = None):
        self.registry = registry
        self.resolver = resolver
        self.compiler = compiler
        self.runtime = runtime
        self.settings_reader = settings_reader
        self.classifier = classifier or FastIntentClassifier()

    def _legacy(self, trace: context_runtime.TurnTrace | None, policy: CanaryPolicy,
                bucket: Optional[int], reason: str) -> FastPathPlan:
        pinned = self.runtime.pin_execution_path(
            trace, "legacy", bucket, policy.version, reason
        ) if trace else "legacy"
        return FastPathPlan("legacy", reason, pinned, bucket=bucket,
                            policy_version=policy.version)

    def prepare(self, trace: context_runtime.TurnTrace | None, objective: str, brain: str,
                channel: str, provider: str, model: str, provider_kind: str,
                has_attachments: bool = False) -> FastPathPlan:
        try:
            policy = CanaryPolicy.from_settings(self.settings_reader() or {})
        except Exception:
            policy = CanaryPolicy.from_settings({})
        if not trace:
            return FastPathPlan("legacy", "trace_unavailable", "legacy")
        bucket = stable_bucket(trace.session_id, policy.salt)
        if policy.mode not in ("canary", "on"):
            return self._legacy(trace, policy, bucket, "mode_not_canary")
        if policy.allocation_basis_points <= bucket:
            return self._legacy(trace, policy, bucket, "outside_allocation")
        if channel not in policy.channels:
            return self._legacy(trace, policy, bucket, "channel_not_allowed")
        if provider_kind not in policy.provider_kinds:
            return self._legacy(trace, policy, bucket, "provider_kind_not_allowed")
        rule = policy.quota_rule(provider, model)
        if rule is None and str(provider_kind or "") in ("cli", "oauth"):
            rule = policy._rule_thue_bao(self.settings_reader() or {})
        if rule is None:
            return self._legacy(trace, policy, bucket, "hard_quota_unknown")

        intent = self.classifier.classify(
            objective, has_attachments=has_attachments,
            max_chars=policy.max_objective_chars,
        )
        if not intent.eligible:
            return self._legacy(trace, policy, bucket, intent.reason)

        inventory = self.registry.inventory_status(brain)
        age = inventory.get("age_seconds")
        if not inventory.get("ready") or age is None or age > policy.registry_max_age_seconds:
            return self._legacy(trace, policy, bucket, "registry_stale")
        if inventory.get("revision") != trace.registry_revision:
            return self._legacy(trace, policy, bucket, "registry_revision_changed")

        resolution = self.resolver.resolve(
            objective, brain,
            capability_resolver.ActorPolicy(mode="full", channel=channel),
        )
        # Điểm CAO NHẤT sau khi chấm và lọc, không phải số lần dò trúng chữ. Xem lý do ngay
        # dưới - đây là chỗ mức Siêu tiết kiệm chết lặng suốt mấy bản liền.
        _ranked = resolution.get("ranked") or []
        diem_cao = 0.0
        try:
            diem_cao = max(float(x.get("score") or 0.0) for x in _ranked) if _ranked else 0.0
        except (TypeError, ValueError):
            diem_cao = 0.0
        self.runtime.record_runtime_event(trace, "resolver.canary", {
            "policy_version": resolution.get("policy_version") or "",
            "registry_revision": resolution.get("registry_revision") or "",
            "candidate_count": resolution.get("candidate_count", 0),
            "selected_count": resolution.get("selected_count", 0),
            "top_score": round(diem_cao, 6),
            "min_resolver_score": policy.min_resolver_score,
            "miss_class": resolution.get("miss_class") or "",
            "intent_class": intent.intent_class,
            "intent_confidence": intent.confidence,
        })
        if int(resolution.get("selected_count") or 0) > 0:
            return self._legacy(trace, policy, bucket, "capability_selected")
        # VÌ SAO KHÔNG CÒN XÉT `candidate_count`. Nó là số ứng viên dò được bằng CHỮ, tính
        # trước khi chấm điểm và trước khi lọc quyền. Trên máy có vài trăm tool MCP (Gmail,
        # Drive, Lịch, quảng cáo...), gần như câu tiếng Việt nào cũng dò trúng ít nhất một
        # tool qua một từ chung, nên `candidate_count > 0` đúng với MỌI lượt. Kết quả là mức
        # Siêu tiết kiệm càng đấu nhiều nguồn càng không bao giờ chạy - ngược hẳn với thứ nó
        # hứa. Chủ repo báo đúng triệu chứng đó: chưa lần nào thấy chữ "Tức thì".
        #
        # Trên máy dev thì không lộ, vì kho tool ở đó gần như rỗng và mọi test đều xanh.
        #
        # Nay xét ĐIỂM cao nhất sau khi chấm. Resolver đã tự nói "không chọn cái nào"
        # (selected_count = 0) ở trên; điểm ở đây trả lời tiếp câu "có cái nào SUÝT trúng
        # không". Suýt trúng thì nhường đường thường cho chắc, còn dò trúng một từ vu vơ thì
        # không phải lý do để bỏ đường tắt. `filtered` cũng thôi được xét: capability đã bị
        # chặn quyền thì đi đường thường cũng không gọi được, chặn đường tắt chẳng cứu ai.
        if diem_cao >= policy.min_resolver_score:
            return self._legacy(trace, policy, bucket, "capability_ambiguous")

        compile_resolution = dict(resolution)
        # Resolver miss "index_or_alias" nghĩa là không tìm thấy capability, không đồng nghĩa
        # chat-thuần bị lỗi. Classifier bảo thủ ở trên là authority để chọn path fast.
        compile_resolution["miss_class"] = ""
        compiled = self.compiler.compile_canary(
            context_compiler.CompileRequest(
                task_id=trace.task_id, step_id=trace.step_id, objective=objective,
                brain=brain, channel=channel, provider=provider, model=model,
                model_kind=provider_kind, rolling_tpm_remaining=rule.rolling_tpm,
                hard_max_input_tokens=rule.hard_max_input_tokens,
                reserved_output_tokens=rule.reserved_output_tokens,
                execution_mode="canary",
            ),
            compile_resolution,
        )
        report = compiled.trace_report
        self.runtime.record_runtime_event(trace, "compiler.canary", {
            "status": report.get("status") or compiled.status,
            "path": report.get("path") or "",
            "policy_version": report.get("policy_version") or "",
            "capsule_hash": report.get("capsule_hash") or "",
            "estimated_input_tokens": report.get("estimated_input_tokens", 0),
            "max_input_tokens": report.get("max_input_tokens", 0),
            "reserved_output_tokens": report.get("reserved_output_tokens", 0),
            "hard_context_known": bool(report.get("hard_context_known", False)),
            "preflight_decision": report.get("preflight_decision") or "",
            "quota_known": bool(report.get("quota_known", False)),
        })
        if compiled.status != "compiled" or compiled.capsule is None:
            self.runtime.pin_execution_path(trace, "fast", bucket, policy.version, "compile_rejected")
            return FastPathPlan(
                "reject", "compile_rejected", "fast", bucket=bucket,
                policy_version=policy.version,
                rejection_message=(
                    "Request này vượt ngân sách context đã xác minh của model hiện tại. "
                    "Javis chưa gửi request; anh hãy rút gọn nội dung hoặc đổi model/provider."
                ),
            )
        if report.get("path") != "fast" or report.get("preflight_decision") != "would_allow":
            return self._legacy(trace, policy, bucket, "compiler_not_fast")

        estimate = max(1, int(report.get("estimated_input_tokens") or 0))
        reserved_input = int(math.ceil(estimate * policy.estimator_safety_factor))
        pinned = self.runtime.pin_execution_path(
            trace, "fast", bucket, policy.version, "admission_candidate"
        )
        if pinned != "fast":
            return FastPathPlan("legacy", "task_already_pinned", pinned, bucket=bucket,
                                policy_version=policy.version)
        if reserved_input > rule.hard_max_input_tokens:
            self.runtime.record_runtime_event(trace, "quota.rejected", {
                "reason": "input_safety_margin", "requested_tokens": reserved_input,
                "limit_tokens": rule.hard_max_input_tokens,
            })
            return FastPathPlan(
                "reject", "input_safety_margin", "fast", bucket=bucket,
                estimated_input_tokens=estimate, reserved_input_tokens=reserved_input,
                reserved_output_tokens=rule.reserved_output_tokens,
                policy_version=policy.version,
                rejection_message=(
                    "Request này quá sát hard limit của model sau khi cộng biên an toàn. "
                    "Javis chưa gửi request; anh hãy rút gọn nội dung hoặc đổi model/provider."
                ),
            )
        admission = self.runtime.admit_quota(
            trace, provider, model, reserved_input, rule.reserved_output_tokens,
            rule.rolling_tpm, rule.window_seconds,
        )
        if not admission.allowed:
            return FastPathPlan(
                "reject", admission.reason, "fast", bucket=bucket,
                estimated_input_tokens=estimate, reserved_input_tokens=reserved_input,
                reserved_output_tokens=rule.reserved_output_tokens,
                policy_version=policy.version,
                rejection_message=(
                    "Model hiện tại đã hết ngân sách token trong cửa sổ quota. "
                    "Javis chưa gửi request; anh chờ hết cửa sổ hoặc đổi model/provider."
                ),
            )
        rendered = compiled.capsule.rendered_request
        messages = tuple(rendered.get("messages") or [])
        return FastPathPlan(
            "execute", "admitted", "fast", bucket=bucket, messages=messages,
            reservation_id=admission.reservation_id,
            capsule_hash=compiled.capsule.capsule_hash,
            estimated_input_tokens=estimate, reserved_input_tokens=reserved_input,
            reserved_output_tokens=rule.reserved_output_tokens,
            policy_version=policy.version,
        )
