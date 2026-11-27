"""Strict read-only agentic catalog inputs for a host-owned brain root.

This collects one dependency of ordinary main context, not a complete prompt. Plugin
visibility, SQL, protected memory/profile/kernel, channel and settings are separate.
Raw agent/skill/workflow bodies never enter this metadata projection. Every selected
file still retains its full source hash, so editing an unseen body invalidates a pin.
No sync, migration, directory creation, plugin callback or live prompt builder runs.
"""
from __future__ import annotations

import json
import math
import re
import stat
from datetime import date, datetime
from pathlib import Path

import agent_tags
import fastyaml
import skill_router
import workflow_graph
import yaml
from evidence_store import redact
from improvement_cases import _frozen
from improvement_store import _hash
from improvement_trial_context import ContextSource, _check_path, _read, _root

MAX_CATALOG_FILES = 512
MAX_CATALOG_BYTES = 8 * 1024 * 1024
MAX_DIRECTORY_ENTRIES = 2048
_LOOP_FM = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def _identity(info):
    return _hash({"dev": info.st_dev, "ino": info.st_ino, "ctime_ns": info.st_ctime_ns})


def _directory(root, relative, records):
    path = root / relative
    _check_path(path)
    try:
        before = path.stat()
    except FileNotFoundError:
        records.append({"relative": relative, "present": False, "identity": None, "entries": []})
        return None
    if not stat.S_ISDIR(before.st_mode):
        raise ValueError("insufficient_source: catalog_directory_not_directory")
    members = sorted(path.iterdir())
    if len(members) > MAX_DIRECTORY_ENTRIES:
        raise ValueError("insufficient_source: catalog_directory_too_large")
    entries, seen = [], set()
    for child in members:
        _check_path(child)
        info = child.lstat()
        if child.name.casefold() in seen:
            raise ValueError("insufficient_source: ambiguous_catalog_member")
        seen.add(child.name.casefold())
        kind = "directory" if stat.S_ISDIR(info.st_mode) else "file" if stat.S_ISREG(info.st_mode) else "other"
        entries.append({"name": child.name, "kind": kind})
    _check_path(path)
    after = path.stat()
    if (_identity(before), before.st_mtime_ns) != (_identity(after), after.st_mtime_ns):
        raise ValueError("insufficient_source: catalog_changed")
    records.append({"relative": relative, "present": True, "identity": _identity(before), "entries": entries})
    return entries


def _mapping(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_json_member")
            result[key] = value
        return result

    def invalid(_):
        raise ValueError("nonfinite_json_value")

    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)
        if not isinstance(value, dict):
            raise ValueError("mapping_required")
        return _frozen(value)
    except (TypeError, ValueError, RecursionError, OverflowError) as error:
        raise ValueError("insufficient_source: invalid_catalog_json") from error


def _frontmatter(text, *, loop=False):
    try:
        if loop:
            match = _LOOP_FM.match(text)
            if not match:
                raise ValueError("loop_frontmatter_required")
            header, body = match.groups()
        else:
            parts = fastyaml.split_frontmatter(text)
            if parts is None:
                if text.startswith("---"):
                    raise ValueError("unfinished_frontmatter")
                return {}, text
            header, body = parts
        # A bounded source can still expand exponentially through YAML aliases
        # when canonicalizing metadata. Unsupported aliases fail before loading.
        if any(isinstance(token, yaml.tokens.AliasToken) for token in yaml.scan(header)):
            raise ValueError("yaml_alias_unsupported")
        meta = fastyaml.safe_load(header)
        if meta is None and not loop:
            meta = {}
        if not isinstance(meta, dict):
            raise ValueError("frontmatter_mapping_required")
        return _frozen(_yaml_values(meta)), body
    except Exception as error:
        # Parser exceptions may embed source text; callers receive a fixed reason.
        raise ValueError("insufficient_source: invalid_catalog_frontmatter") from error


def _yaml_values(value):
    """Retain ordinary YAML date values in JSON, as production metadata does."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("unsupported_yaml_key")
        return {key: _yaml_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_yaml_values(item) for item in value]
    return value


def _scan(root, language):
    directories, files, identities = [], [], set()
    total_bytes = 0

    def read(relative, *, optional=False):
        nonlocal total_bytes
        if len(files) >= MAX_CATALOG_FILES:
            raise ValueError("insufficient_source: catalog_too_large")
        path = root / relative
        _check_path(path)
        try:
            if path.stat().st_nlink != 1:
                raise ValueError("insufficient_source: linked_catalog_file")
        except FileNotFoundError:
            pass
        metadata, text = _read(ContextSource("catalog:" + relative, root, relative, not optional))
        if metadata["present"]:
            if metadata["identity"] in identities:
                raise ValueError("insufficient_source: duplicate_catalog_identity")
            identities.add(metadata["identity"])
            total_bytes += len(text.encode("utf-8"))
            if total_bytes > MAX_CATALOG_BYTES:
                raise ValueError("insufficient_source: catalog_too_large")
        files.append({**metadata, "projection": None})
        return text, files[-1]

    caps = {"agents": [], "skills": [], "workflows": [], "loops": []}
    layout = {"skills": "skills"}
    for kind in ("agents", "workflows"):
        canonical = _directory(root, kind, directories)
        legacy = _directory(root, "Javis/" + kind, directories)
        chosen = kind if canonical is not None else "Javis/" + kind if legacy is not None else kind
        members = canonical if canonical is not None else legacy or []
        layout[kind] = chosen
        for entry in members:
            if entry["kind"] != "file" or not Path(entry["name"]).match("*.md"):
                continue
            relative = chosen + "/" + entry["name"]
            text, record = read(relative)
            meta, _ = _frontmatter(text)
            record["projection"] = meta
            slug = Path(entry["name"]).stem
            if kind == "agents":
                caps[kind].append({"slug": slug, "name": meta.get("name", slug), "role": meta.get("role", ""),
                    "model": meta.get("model", ""), "tags": agent_tags.tags_of(meta), "skills": meta.get("skills", []) or []})
            else:
                steps = meta.get("steps", []) or []
                if not isinstance(steps, list):
                    raise ValueError("insufficient_source: invalid_catalog_workflow")
                group = meta.get("group")
                caps[kind].append({"slug": slug, "name": meta.get("name", slug),
                    "status": workflow_graph.workflow_status(meta), "description": meta.get("description", ""),
                    "group": (str(group).strip() or "Chung") if group is not None else "Chung",
                    "agents": [step.get("agent") for step in steps if isinstance(step, dict)], "n_steps": len(steps)})

    seen_skills = set()
    for base, allow_disabled in (("skills", True), (".claude/skills", True), (".agents", False)):
        members = _directory(root, base, directories) or []
        for folder, enabled in ((base, True), (base + "/.disabled", False)) if allow_disabled else ((base, True),):
            candidates = members if enabled else _directory(root, folder, directories) or []
            for entry in candidates:
                if entry["kind"] != "directory" or entry["name"] == ".disabled":
                    continue
                directory = folder + "/" + entry["name"]
                inner = _directory(root, directory, directories) or []
                # Production looks up literal SKILL.md on the actual filesystem.
                # A case-insensitive volume may expose skill.md under that name;
                # retain the enumerated lexical filename in the immutable record.
                wanted = root / directory / "SKILL.md"
                _check_path(wanted)
                skill = next((item for item in inner if item["name"].casefold() == "skill.md"
                              and item["kind"] == "file"), None) if wanted.is_file() else None
                if skill is None:
                    continue
                text, record = read(directory + "/" + skill["name"])
                meta, body = _frontmatter(text)
                record["projection"] = meta
                slug = entry["name"]
                if slug in seen_skills:
                    continue
                seen_skills.add(slug)
                body = body.strip()
                caps["skills"].append({"slug": slug, "name": skill_router.theo_ngon_ngu(meta, "name", language) or slug,
                    "description": skill_router.theo_ngon_ngu(meta, "description", language) or (
                        body.split("\n")[0][:skill_router.SKILL_SUMMARY_MAX] if body else ""),
                    "group": meta.get("group") or "Chung", "enabled": enabled})

    state_text, record = read("Javis/loop-state.json", optional=True)
    loop_state = _mapping(state_text) if state_text is not None else {}
    # Runtime summaries and previous outputs are irrelevant to discovery and private.
    paused = {slug: bool(value.get("auto_paused_reason")) for slug, value in loop_state.items() if isinstance(value, dict)}
    record["projection"] = paused if state_text is not None else None
    for entry in _directory(root, "Javis/loops", directories) or []:
        if entry["kind"] != "file" or not Path(entry["name"]).match("*.md"):
            continue
        text, record = read("Javis/loops/" + entry["name"])
        meta, _ = _frontmatter(text, loop=True)
        record["projection"] = meta
        goal = str(meta.get("goal", "custom") or "custom").strip().lower()
        mode = str(meta.get("mode", "full") or "").strip().lower()
        try:
            interval = max(5, int(meta.get("interval_min", 60)))
        except (ValueError, TypeError):
            interval = 60
        slug = Path(entry["name"]).stem
        caps["loops"].append({"slug": slug, "name": str(meta.get("name") or slug),
            "enabled": bool(meta.get("enabled", False)), "mode": mode if mode in ("suggest", "auto", "full") else "full",
            "interval_min": interval, "goal": goal if goal in ("business", "brain", "product", "custom") else "custom",
            "paused": paused.get(slug, False)})

    usage_text, record = read("Javis/skill-usage.json", optional=True)
    usage = _mapping(usage_text) if usage_text is not None else {}
    priorities = {}
    for slug, value in usage.items():
        if not isinstance(value, dict):
            continue
        try:
            count, last = int(value.get("use_count") or 0), float(value.get("last_used_at") or 0)
        except (ValueError, TypeError, OverflowError) as error:
            raise ValueError("insufficient_source: invalid_catalog_priority") from error
        if not math.isfinite(last):
            raise ValueError("insufficient_source: invalid_catalog_priority")
        priorities[slug] = {"pinned": bool(value.get("pinned")), "use_count": count, "last_used_at": last}
    record["projection"] = priorities if usage_text is not None else None

    def priority(item):
        rec = priorities.get(item["slug"], {})
        return (0 if rec.get("pinned") else 1, -rec.get("use_count", 0), -rec.get("last_used_at", 0), item["slug"])

    enabled = sorted((item for item in caps["skills"] if item["enabled"]), key=priority)
    # The router names every enabled skill (2026-11-27, main_prompt_rendering.render_skill_router): nothing is cut
    # here, the renderer keeps to its own character budget the same way for the trial as for the chat.
    visible, hidden = enabled, 0
    result = {"version": 1, "root": str(root), "root_identity": _identity(root.stat()), "language": language,
        "layout": layout, "directories": directories, "files": files, "capabilities": caps,
        "router": {"visible": visible, "hidden_count": hidden}}
    value = _frozen(result)
    if redact(value) != value:
        raise ValueError("insufficient_source: credential_bearing_catalog")
    return value


def capture_catalog(root: Path, *, language="vi") -> dict:
    """Observe exact current membership twice; never upgrade this part to complete context."""
    if not isinstance(language, str) or not re.fullmatch("[a-z]{2}", language):
        raise ValueError("invalid_catalog_language")
    original = root
    try:
        root = _root(root)
        if root != original:
            raise ValueError("insufficient_source: catalog_root_changed")
        first = _scan(root, language)
        if _scan(root, language) != first:
            raise ValueError("insufficient_source: catalog_changed")
        return first
    except (OSError, RuntimeError) as error:
        raise ValueError("insufficient_source: catalog_unavailable") from error
