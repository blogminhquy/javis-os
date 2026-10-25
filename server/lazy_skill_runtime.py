"""Manifest-only SkillSource and exact lazy body loader for Phase 8."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import skill_router
from capability_registry import CapabilityRegistry
from context_compiler import ContextItem, HeuristicTokenizer

SKILL_SOURCE_POLICY_VERSION = "lazy-skill-source-v2"
_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")
_EXPLICIT_RE = re.compile(r"\b(skill|kỹ năng|quy trình|workflow|dùng .* để|use .* to)\b", re.IGNORECASE)


def _task_candidates(brain, manifests):
    """Private frozen projection; never replace the brain-global registry source."""
    from capability_registry import brain_scope
    source = brain_scope(brain) + ':skill:brain-skills'
    result = []
    for manifest in manifests:
        slug = manifest['slug']
        name = str(manifest['name'] or slug).strip()[:180]
        summary = str(manifest['description'] or name).strip()[:2000]
        group = str(manifest['group'] or 'Chung').strip()[:120]
        payload = {'slug': slug, 'name': name, 'summary': summary, 'group': group,
            'path': manifest['relative_path'], 'frontmatter_hash': manifest['frontmatter_hash']}
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        result.append({'capability_id': 'skill_' + hashlib.sha256((source + '|' + slug).encode()).hexdigest()[:24],
            'name': slug, 'aliases': list(dict.fromkeys((slug, name, group))), 'summary': summary,
            'kind': 'skill', 'capability_revision': digest, 'metadata': payload, '_task_manifest': manifest})
    return result


def _overlay_candidates(brain, lang, query, found, descriptions):
    """Registry-search skill rows with overlaid summaries; an overlaid skill the search missed is added."""
    found = [dict(x) for x in found if str(x.get("kind") or "") == "skill"]
    seen = set()
    for row in found:
        slug = str((row.get("metadata") or {}).get("slug") or row.get("name") or "")
        seen.add(slug)
        if slug in descriptions:
            row["summary"] = descriptions[slug]
    missing = [m for m in skill_router.list_skill_manifests(brain, lang) if m["slug"] in descriptions and m["slug"] not in seen]
    for manifest in missing:
        found.extend(_task_candidates(brain, [{**manifest, "description": descriptions[manifest["slug"]]}]))
    return found


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
        self._refresh_cache: dict[tuple, tuple[tuple, dict]] = {}
        self._incomplete: dict[tuple, int] = {}

    def refresh(self, brain: str | Path, lang: str = "") -> dict:
        # `lang` nằm TRONG khoá cache, không chỉ trong lời gọi. Chấm điểm ở `_score` là so
        # TRÙNG TỪ giữa câu người dùng và mô tả skill, nên mô tả phải cùng thứ tiếng với câu
        # hỏi thì mới có điểm; đổi ngôn ngữ mà vẫn trả bộ manifest cũ là im lặng vô hiệu hoá
        # đúng cái vừa sửa. Thiếu bản dịch thì skill_router tự rơi về mô tả gốc.
        key = (str(Path(brain).resolve()).casefold(), str(lang or ""))
        signature = skill_router.skill_manifest_signature(brain)
        cached = self._refresh_cache.get(key)
        if cached and cached[0] == signature:
            return dict(cached[1])
        manifests = skill_router.list_skill_manifests(brain, lang)
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
                ambiguity_margin: float = 0.08, max_body_chars: int = 12000,
                lang: str = "", descriptions: dict | None = None) -> SkillSelection:
        """`descriptions`: owner-applied routing descriptions (M4) for this chat, {slug: text}. With
        any, ranking runs over the frozen manifest projection so the overlay text is what is scored."""
        from improvement_task_skill_scope import current, ScopeUnavailable
        from improvement_blobs import AssetUnavailable
        try:
            # Unbound returns None without I/O; any error here comes from a bound (maybe dead) scope.
            scope = current(brain)
        except (ScopeUnavailable, AssetUnavailable, OSError, sqlite3.Error):
            return SkillSelection('none', 'task_scope_unavailable')
        if scope is not None:
            try:
                manifests = scope.manifests(lang)
                revision = hashlib.sha256(json.dumps({'scope': scope.registry_revision, 'lang': str(lang or ''),
                    'manifests': manifests}, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
                incomplete = any(not str(item['description'] or '').strip() for item in manifests)
                candidates = _task_candidates(brain, manifests)
            except (ScopeUnavailable, AssetUnavailable, OSError, sqlite3.Error):
                # AdaptiveContext treats exceptions/fallback as permission to restore
                # its legacy router. A dead bound owner must suppress that fallback.
                return SkillSelection('none', 'task_scope_unavailable')
        elif descriptions:
            # Same registry search as without an overlay; only the overlaid skills are rescored with the
            # owner-applied text (added when the search missed them), so no other skill's routing moves.
            self.refresh(brain, lang)
            key = (str(Path(brain).resolve()).casefold(), str(lang or ""))
            incomplete = self._incomplete.get(key, 0)
            revision = hashlib.sha256(json.dumps({'registry': self.registry.revision(brain), 'routing_overlay': descriptions},
                ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            candidates = _overlay_candidates(brain, lang, query, self.registry.search(query, brain, 40), descriptions)
        else:
            # Unbound: a registry error still propagates, so the caller keeps the legacy router.
            self.refresh(brain, lang)
            key = (str(Path(brain).resolve()).casefold(), str(lang or ""))
            incomplete = self._incomplete.get(key, 0)
            revision = self.registry.revision(brain)
            candidates = [x for x in self.registry.search(query, brain, 40)
                          if str(x.get("kind") or "") == "skill"]
        if incomplete:
            return SkillSelection(
                "fallback", "manifest_incomplete", registry_revision=revision
            )
        ranked = sorted(((self._score(query, x), x) for x in candidates),
                        key=lambda pair: (-pair[0], pair[1]["capability_id"]))
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
        try:
            asset = (scope.read(slug, expected_manifest=top['_task_manifest']) if scope is not None
                else skill_router.read_skill_asset(brain, slug))
        except (ScopeUnavailable, AssetUnavailable, OSError, sqlite3.Error):
            return SkillSelection('none', 'task_scope_unavailable', top['capability_id'], slug,
                top_score, runner, revision)
        if asset is None:
            return SkillSelection("none" if scope is not None else "fallback", "source_unreadable", top["capability_id"], slug,
                                  top_score, runner, revision)
        selected_meta = top.get("metadata") or {}
        if (asset.relative_path != selected_meta.get("path")
                or asset.frontmatter_hash != selected_meta.get("frontmatter_hash")):
            return SkillSelection("none" if scope is not None else "fallback", "source_manifest_changed", top["capability_id"], slug,
                                  top_score, runner, revision)
        raw = asset.text
        if not raw.strip() or len(raw) > max(1000, int(max_body_chars)):
            return SkillSelection("none" if scope is not None else "fallback", "body_over_limit", top["capability_id"], slug,
                                  top_score, runner, revision)
        _meta, body = skill_router.split_frontmatter(raw)
        body = body.strip()
        if not body:
            return SkillSelection("none" if scope is not None else "fallback", "body_empty", top["capability_id"], slug,
                                  top_score, runner, revision)
        relative = asset.relative_path
        source_hash = asset.content_hash
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
                      "policy_version": SKILL_SOURCE_POLICY_VERSION,
                      **({'task_scope_hash': scope.scope_hash, 'task_inventory_hash': scope.inventory_hash}
                          if scope is not None else {}),
                      # M4 telemetry: which description the router scored for the selected skill.
                      **({'routing_description': 'overlay' if slug in descriptions else 'canonical'}
                         if descriptions and scope is None else {})},
        )
        return SkillSelection("load", "selected", top["capability_id"], slug,
                              round(top_score, 6), round(runner, 6), revision, item)
