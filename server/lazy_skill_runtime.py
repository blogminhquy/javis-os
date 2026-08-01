"""Manifest-only SkillSource and exact lazy body loader for Phase 8."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import skill_router
from capability_registry import CapabilityRegistry
from context_compiler import ContextItem, HeuristicTokenizer

SKILL_SOURCE_POLICY_VERSION = "lazy-skill-source-v1"
_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")
_EXPLICIT_RE = re.compile(r"\b(skill|kỹ năng|quy trình|workflow|dùng .* để|use .* to)\b", re.IGNORECASE)


def _norm(value: str) -> str:
    raw = unicodedata.normalize("NFKD", str(value or "").casefold())
    return " ".join(_TOKEN_RE.findall("".join(c for c in raw if not unicodedata.combining(c))))


@dataclass(frozen=True)
class SkillSelection:
    action: str
    reason: str
    capability_id: str = ""
    slug: str = ""
    score: float = 0.0
    runner_up_score: float = 0.0
    registry_revision: str = ""
    context_item: ContextItem | None = None


class LazySkillSource:
    def __init__(self, registry: CapabilityRegistry):
        self.registry = registry
        self._refresh_cache: dict[str, tuple[tuple, dict]] = {}
        self._incomplete: dict[str, int] = {}

    def refresh(self, brain: str | Path) -> dict:
        key = str(Path(brain).resolve()).casefold()
        signature = skill_router.skill_manifest_signature(brain)
        cached = self._refresh_cache.get(key)
        if cached and cached[0] == signature:
            return dict(cached[1])
        manifests = skill_router.list_skill_manifests(brain)
        result = self.registry.refresh_skills(brain, manifests)
        result["manifest_count"] = len(manifests)
        result["body_loaded_count"] = 0
        result["incomplete_manifest_count"] = sum(
            1 for item in manifests if not str(item.get("description") or "").strip()
        )
        self._incomplete[key] = result["incomplete_manifest_count"]
        self._refresh_cache[key] = (signature, dict(result))
        return result

    @staticmethod
    def _score(query: str, item: dict) -> float:
        query_norm = _norm(query)
        query_terms = set(query_norm.split())
        name = _norm(item.get("name") or "")
        aliases = {_norm(x) for x in item.get("aliases") or []}
        summary = _norm(item.get("summary") or "")
        name_terms = set((name + " " + " ".join(aliases)).split())
        all_terms = name_terms | set(summary.split())
        coverage = len(query_terms & all_terms) / max(1, len(query_terms))
        discriminative = len(query_terms & name_terms) / max(1, len(name_terms))
        phrase = bool(query_norm and (query_norm in summary or query_norm in name))
        explicit = query_norm == name or query_norm in aliases
        return min(1.0, coverage * 0.52 + discriminative * 0.25 +
                   (0.13 if phrase else 0) + (0.25 if explicit else 0))

    def resolve(self, brain: str | Path, query: str, min_score: float = 0.24,
                ambiguity_margin: float = 0.08, max_body_chars: int = 12000) -> SkillSelection:
        self.refresh(brain)
        key = str(Path(brain).resolve()).casefold()
        if self._incomplete.get(key, 0):
            return SkillSelection(
                "fallback", "manifest_incomplete", registry_revision=self.registry.revision(brain)
            )
        candidates = [x for x in self.registry.search(query, brain, 40)
                      if str(x.get("kind") or "") == "skill"]
        ranked = sorted(((self._score(query, x), x) for x in candidates),
                        key=lambda pair: (-pair[0], pair[1]["capability_id"]))
        revision = self.registry.revision(brain)
        if not ranked:
            # No relevant skill is a valid lazy outcome, unless user explicitly asked
            # for one: then old router must remain the fallback.
            reason = "explicit_skill_unresolved" if _EXPLICIT_RE.search(query or "") else "no_skill_needed"
            action = "fallback" if reason == "explicit_skill_unresolved" else "none"
            return SkillSelection(action, reason, registry_revision=revision)
        top_score, top = ranked[0]
        runner = ranked[1][0] if len(ranked) > 1 else 0.0
        if top_score < min_score:
            if _EXPLICIT_RE.search(query or ""):
                return SkillSelection("fallback", "low_confidence", score=top_score,
                                      runner_up_score=runner, registry_revision=revision)
            return SkillSelection("none", "no_skill_needed", score=top_score,
                                  runner_up_score=runner, registry_revision=revision)
        if runner and top_score - runner < ambiguity_margin:
            return SkillSelection("fallback", "ambiguous", score=top_score,
                                  runner_up_score=runner, registry_revision=revision)

        slug = str((top.get("metadata") or {}).get("slug") or top.get("name") or "")
        path = skill_router.resolve_skill_file(brain, slug)
        if path is None:
            return SkillSelection("fallback", "source_missing", top["capability_id"], slug,
                                  top_score, runner, revision)
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return SkillSelection("fallback", "source_unreadable", top["capability_id"], slug,
                                  top_score, runner, revision)
        if not raw.strip() or len(raw) > max(1000, int(max_body_chars)):
            return SkillSelection("fallback", "body_over_limit", top["capability_id"], slug,
                                  top_score, runner, revision)
        _meta, body = skill_router.split_frontmatter(raw)
        body = body.strip()
        if not body:
            return SkillSelection("fallback", "body_empty", top["capability_id"], slug,
                                  top_score, runner, revision)
        try:
            relative = path.resolve().relative_to(Path(brain).resolve()).as_posix()
        except (OSError, ValueError):
            return SkillSelection("fallback", "source_outside_brain", top["capability_id"], slug,
                                  top_score, runner, revision)
        source_hash = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()
        content = (
            f"Selected skill `{slug}`. Apply only when it matches the current objective. "
            f"Source: file:{relative}.\n{body}"
        )
        tokenizer = HeuristicTokenizer("skill", "lazy")
        item = ContextItem(
            id=top["capability_id"], kind="selected_skill", content=content,
            source_ref=f"file:{relative}:{source_hash}", token_cost=tokenizer.count_text(content),
            relevance=top_score, confidence=top_score, authority=0.92, freshness=1.0,
            required=False, trust="local_skill",
            metadata={"slug": slug, "capability_revision": top.get("capability_revision") or "",
                      "policy_version": SKILL_SOURCE_POLICY_VERSION},
        )
        return SkillSelection("load", "selected", top["capability_id"], slug,
                              round(top_score, 6), round(runner, 6), revision, item)
