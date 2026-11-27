"""Manifest-only SkillSource and exact lazy body loader for Phase 8."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import skill_finder
import skill_router
from capability_registry import CapabilityRegistry
from context_compiler import ContextItem, HeuristicTokenizer

SKILL_SOURCE_POLICY_VERSION = "lazy-skill-source-v2"


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
        # `lang` is part of the cache key, not only of the call: the manifests carry the description in the
        # language asked for (`description_<lang>`), and a language switch that kept the old set would score the
        # request against the wrong text. A missing translation falls back to the original (skill_router).
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

    def resolve(self, brain: str | Path, query: str, min_score: float = 0.24,
                ambiguity_margin: float = 0.08, max_body_chars: int = 12000,
                lang: str = "", descriptions: dict | None = None, session_key: str = "") -> SkillSelection:
        """Preload the body of the skill this request clearly needs, ranked by skill_finder. `descriptions`:
        owner-applied routing descriptions (M4) for this chat, {slug: text}, scored instead of the file's own.
        `min_score` and `ambiguity_margin` belonged to the word-overlap ranking this replaced; they are ignored."""
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
                candidates = _task_candidates(brain, manifests)
            except (ScopeUnavailable, AssetUnavailable, OSError, sqlite3.Error):
                # AdaptiveContext treats exceptions/fallback as permission to restore
                # its legacy router. A dead bound owner must suppress that fallback.
                return SkillSelection('none', 'task_scope_unavailable')
        else:
            # Unbound: the registry is refreshed as before (other readers use it) and a registry error still
            # propagates, so the caller keeps the legacy router.
            self.refresh(brain, lang)
            if descriptions:
                revision = hashlib.sha256(json.dumps({'registry': self.registry.revision(brain),
                    'routing_overlay': descriptions}, ensure_ascii=False, sort_keys=True,
                    separators=(',', ':')).encode()).hexdigest()
            else:
                revision = self.registry.revision(brain)
            manifests = skill_router.list_skill_manifests(brain, lang)
            candidates = None
        # 2026-11-27: which skill is ranked by skill_finder over the WHOLE text of every skill (description, "When to
        # use", learned requests), not by word overlap with a description cut at 150 characters. Its body is loaded
        # here only when the first skill is clearly the one (skill_finder.confident); otherwise nothing is loaded
        # and the turn's suggestions (main._skill_turn_head) put the few that fit in front of the model. An empty or
        # missing description no longer sends the turn back to the old router: the finder reads the body too.
        matches = skill_finder.suggest(brain, query, (), session_key, lang,
                                       descriptions=(descriptions if scope is None else None))
        if not matches:
            return SkillSelection("none", "no_skill_needed", registry_revision=revision)
        first = matches[0]
        runner = (first.score / first.margin) if first.margin else 0.0
        if not skill_finder.confident(matches):
            return SkillSelection("none", "not_confident", score=round(first.score, 6),
                                  runner_up_score=round(runner, 6), registry_revision=revision)
        if candidates is None:
            manifest = next((m for m in manifests if m.get("slug") == first.slug), None)
            candidates = _task_candidates(brain, [manifest]) if manifest else []
        top = next((c for c in candidates if (c.get("metadata") or {}).get("slug") == first.slug), None)
        if top is None:
            return SkillSelection("none" if scope is not None else "fallback", "source_unreadable",
                                  slug=first.slug, score=round(first.score, 6), registry_revision=revision)
        top_score = first.score
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
        picked = None
        if raw.strip() and len(raw) > max(1000, int(max_body_chars)) and session_key:
            # 2026-11-18: a long skill built as a menu brings the parts this objective needs, chosen before loading
            # (section_select); when Javis is not sure the old fallback below applies.
            try:
                import section_select
                picked = section_select.for_skill(slug, raw, "", question=query, session=session_key,
                                                  tool="lazy_skill")
            except Exception:  # noqa: BLE001 - a saving never stands in the way of the old path
                picked = None
            if picked is not None and len(picked) > max(1000, int(max_body_chars)):
                picked = None
        if not raw.strip() or (picked is None and len(raw) > max(1000, int(max_body_chars))):
            return SkillSelection("none" if scope is not None else "fallback", "body_over_limit", top["capability_id"], slug,
                                  top_score, runner, revision)
        if picked is not None:
            body = picked.strip()
        else:
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
