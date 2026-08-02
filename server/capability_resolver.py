"""Deterministic shadow Resolver cho Adaptive Context Runtime Phase 3.

Resolver chỉ đọc Capability Registry và tạo báo cáo. Nó không thay tool list, không dispatch
tool và không học trọng số online. Query chỉ tồn tại trong RAM; report dùng query_hash.
"""
from __future__ import annotations

import hashlib
import math
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Optional, Protocol

import capability_index
from capability_registry import CapabilityRegistry, get_registry


RESOLVER_POLICY_VERSION = "deterministic-shadow-v1"
_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")
_MODE_RANK = {"suggest": 0, "readonly": 0, "safe": 1, "full": 2}


def _norm(value: str) -> str:
    raw = unicodedata.normalize("NFKD", str(value or "").casefold())
    return " ".join(_TOKEN_RE.findall("".join(c for c in raw if not unicodedata.combining(c))))


def _terms(value: str) -> set[str]:
    return set(_norm(value).split())


class EmbeddingAdapter(Protocol):
    def search(self, query: str, brain: str, limit: int) -> list[tuple[str, float]]: ...


@dataclass(frozen=True)
class ResolverPolicy:
    version: str = RESOLVER_POLICY_VERSION
    candidate_limit: int = 120      # safety bound của policy versioned, không phải setting UI
    max_selected: int = 12
    min_score: float = 0.18
    near_top_band: float = 0.16
    meaningful_gap: float = 0.10
    # Hệ số nới rộng khi tín hiệu yếu (xem capability_index.needs_widening). Nới bằng cách
    # tăng candidate_limit chứ không hạ ngưỡng chất lượng - hạ ngưỡng là mở cửa cho rác.
    widen_factor: int = 3


@dataclass(frozen=True)
class ActorPolicy:
    mode: str = "full"
    channel: str = "dashboard"
    allowed_effects: frozenset[str] = field(
        default_factory=lambda: frozenset({"none", "read", "write", "danger"})
    )
    allowed_source_types: Optional[frozenset[str]] = None


class DeterministicResolver:
    def __init__(self, registry: CapabilityRegistry | None = None,
                 policy: ResolverPolicy | None = None,
                 embedding: EmbeddingAdapter | None = None):
        self.registry = registry or get_registry()
        self.policy = policy or ResolverPolicy()
        self.embedding = embedding

    @staticmethod
    def _hard_filter(item: dict, actor: ActorPolicy) -> str:
        # Skill manifests share the Registry in Phase 8, but they are context
        # sources, never executable tool schemas. LazySkillResolver owns them.
        if str(item.get("kind") or "tool") != "tool":
            return "capability_kind"
        if str(item.get("health") or "healthy") != "healthy":
            return "health"
        if actor.allowed_source_types is not None and item.get("source_type") not in actor.allowed_source_types:
            return "source_type"
        effect = str(item.get("side_effect") or "read")
        if effect not in actor.allowed_effects:
            return "side_effect"
        need = _MODE_RANK.get(str(item.get("required_mode") or "readonly"), 2)
        have = _MODE_RANK.get(str(actor.mode or "readonly"), 0)
        if have < need:
            return "permission"
        channels = (item.get("metadata") or {}).get("channels")
        if isinstance(channels, list) and channels and actor.channel not in channels:
            return "channel"
        return ""

    @staticmethod
    def _score(query_norm: str, query_terms: set[str], item: dict) -> tuple[float, float]:
        name = _norm(item.get("name") or "")
        aliases = [_norm(x) for x in item.get("aliases") or []]
        summary = _norm(item.get("summary") or "")
        name_terms = _terms(name + " " + " ".join(aliases))
        all_terms = name_terms | _terms(summary)
        coverage = len(query_terms & all_terms) / max(1, len(query_terms))
        name_coverage = len(query_terms & name_terms) / max(1, len(query_terms))
        exact = query_norm == name or query_norm in aliases
        phrase = bool(query_norm and (query_norm in name or query_norm in summary or
                                      any(query_norm in alias for alias in aliases)))
        score = coverage * 0.56 + name_coverage * 0.24
        score += 0.14 if phrase else 0.0
        score += 0.22 if exact else 0.0
        # FTS chỉ là bằng chứng lexical bổ sung. Không dùng popularity hay lịch sử click.
        if item.get("fts_rank") is not None:
            score += 0.04
        return min(1.0, score), coverage

    def _cut(self, ranked: list[dict]) -> tuple[list[dict], float, str]:
        ranked = [x for x in ranked if x["score"] >= self.policy.min_score]
        if not ranked:
            return [], self.policy.min_score, "below_min_score"
        top = ranked[0]["score"]
        window = ranked[:self.policy.max_selected]
        gaps = [(window[i]["score"] - window[i + 1]["score"], i)
                for i in range(len(window) - 1)]
        if gaps:
            gap, index = max(gaps, key=lambda x: (x[0], -x[1]))
        else:
            gap, index = 0.0, 0
        dynamic_gap = max(self.policy.meaningful_gap, top * 0.14)
        if gap >= dynamic_gap:
            chosen = window[:index + 1]
            cutoff = chosen[-1]["score"]
            reason = "largest_score_gap"
        else:
            cutoff = max(self.policy.min_score, top - self.policy.near_top_band)
            chosen = [x for x in window if x["score"] >= cutoff]
            reason = "near_top_band"
        return chosen or [window[0]], cutoff, reason

    def resolve(self, query: str, brain: str, actor: ActorPolicy | None = None) -> dict:
        started = time.perf_counter()
        actor = actor or ActorPolicy()
        query_norm = _norm(query)
        query_terms = set(query_norm.split())
        query_hash = hashlib.sha256(str(query or "").encode("utf-8", errors="replace")).hexdigest()
        candidates = self.registry.search(query, brain, self.policy.candidate_limit) if query_terms else []
        filtered: dict[str, int] = {}
        blocked_best: dict[str, float] = {}
        ranked = []
        for item in candidates:
            score, coverage = self._score(query_norm, query_terms, item)
            reason = self._hard_filter(item, actor)
            if reason:
                filtered[reason] = filtered.get(reason, 0) + 1
                blocked_best[reason] = max(blocked_best.get(reason, 0.0), score)
                continue
            ranked.append({
                "capability_id": item["capability_id"],
                "name": item["name"],
                "source_type": item.get("source_type"),
                "source_id": item.get("source_id"),
                "side_effect": item.get("side_effect"),
                "required_mode": item.get("required_mode"),
                "score": round(score, 6),
                "coverage": round(coverage, 6),
                "capability_revision": item.get("capability_revision"),
            })
        ranked.sort(key=lambda x: (-x["score"], -x["coverage"], x["capability_id"]))

        embedding_ids = []
        embedding_error = ""
        if self.embedding is not None:
            try:
                embedding_ids = [str(cid) for cid, _score in self.embedding.search(
                    query, brain, self.policy.candidate_limit
                )]
            except Exception as exc:
                embedding_error = type(exc).__name__

        # Nới rộng khi tín hiệu YẾU, không theo ngưỡng số lượng cố định. Ứng viên thêm vào
        # vẫn đi qua ĐÚNG _hard_filter ở dưới, nên widening không bao giờ nới quyền.
        widen_reason = capability_index.needs_widening(
            ranked, self.policy.min_score, self.policy.meaningful_gap)
        if widen_reason and query_terms:
            try:
                extra = self.registry.search(
                    query, brain, self.policy.candidate_limit * self.policy.widen_factor)
            except Exception:  # noqa: BLE001 - nới rộng là phần thêm, hỏng thì giữ kết quả cũ
                extra = []
            seen = {x["capability_id"] for x in ranked}
            for item in extra:
                if item["capability_id"] in seen:
                    continue
                if self._hard_filter(item, actor):
                    continue
                score, coverage = self._score(query_norm, query_terms, item)
                ranked.append({
                    "capability_id": item["capability_id"], "name": item["name"],
                    "source_type": item.get("source_type"),
                    "source_id": item.get("source_id"),
                    "side_effect": item.get("side_effect"),
                    "required_mode": item.get("required_mode"),
                    "score": round(score, 6), "coverage": round(coverage, 6),
                    "capability_revision": item.get("capability_revision"),
                })
            ranked.sort(key=lambda x: (-x["score"], -x["coverage"], x["capability_id"]))

        # Hợp nhất lexical + semantic + affinity nguồn. Chỉ ĐỔI THỨ TỰ trong nhóm đã lọc.
        fused = capability_index.apply_fusion(ranked, embedding_ids)
        if fused:
            ranked = fused
        selected, cutoff, cutoff_reason = self._cut(ranked)
        lexical_ids = {x["capability_id"] for x in ranked}
        selected_ids = {x["capability_id"] for x in selected}
        top_gap = (ranked[0]["score"] - ranked[1]["score"]) if len(ranked) > 1 else (
            ranked[0]["score"] if ranked else 0.0
        )
        selected_top = selected[0]["score"] if selected else 0.0
        relevant_block = sorted(
            ((score, reason) for reason, score in blocked_best.items() if score >= selected_top),
            key=lambda x: (-x[0], x[1]),
        )
        if relevant_block:
            # Có capability khớp ít nhất ngang kết quả được chọn nhưng bị hard filter.
            miss_class = relevant_block[0][1]
        elif selected:
            miss_class = ""
        elif filtered and not ranked:
            miss_class = sorted(filtered, key=lambda k: (-filtered[k], k))[0]
        elif not candidates:
            miss_class = "index_or_alias"
        else:
            miss_class = "coverage"
        return {
            "policy_version": self.policy.version,
            "registry_revision": self.registry.revision(brain),
            "query_hash": query_hash,
            "query_term_count": len(query_terms),
            "candidate_count": len(candidates),
            "ranked_count": len(ranked),
            # In-memory consumer Phase 7 cần manifest IDs để lập plan nhỏ. Reporter persist
            # chỉ ghi count/hash nên danh sách này không làm trace phình hoặc lộ user query.
            "ranked": ranked[:self.policy.max_selected],
            "selected": selected,
            "selected_count": len(selected),
            "cutoff": round(float(cutoff), 6),
            "cutoff_reason": cutoff_reason,
            "top_score_gap": round(float(top_gap), 6),
            "filtered": filtered,
            "miss_class": miss_class,
            "embedding_candidate_count": len(embedding_ids),
            "embedding_lexical_overlap": len(set(embedding_ids) & lexical_ids),
            "embedding_selected_overlap": len(set(embedding_ids) & selected_ids),
            "embedding_error": embedding_error,
            # Tín hiệu yếu tới mức phải tìm rộng hơn. Đây là thứ đọc trên trang Chẩn đoán
            # để biết registry đang thiếu mô tả tốt, chứ không phải resolver dở.
            "widen_reason": widen_reason,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        }


_RESOLVER: DeterministicResolver | None = None


def get_resolver() -> DeterministicResolver:
    global _RESOLVER
    if _RESOLVER is None:
        _RESOLVER = DeterministicResolver()
    return _RESOLVER
