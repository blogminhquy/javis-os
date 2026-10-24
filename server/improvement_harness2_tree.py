# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Extracted from pinned Harness2; see third_party/harness2/LIBRARY-PROVENANCE.json.
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


Tree = dict[str, str]


_NAME = r"[a-z0-9][a-z0-9_\-]*"


@dataclass(frozen=True)
class SurfaceSpec:
    """The editable surface of one agent framework: paths, caps and per-surface rules."""

    name: str
    always_on: tuple[str, ...]
    always_on_max: int
    always_on_cap_reason: str
    skill_dir: str
    skill_name_rule: str
    trigger_hint: str
    autotrigger_file: str
    trigger_line: str
    subagent_requires_mode: bool
    plugin_dir: str | None
    hooks_file: str | None
    hook_events: frozenset[str] = frozenset()
    compile_skill_scripts: bool = False
    reject_empty_always_on: bool = False

    stubs: tuple[tuple[str, str], ...] = ()


@lru_cache(maxsize=8)
def _res(surface_name: str, skill_dir: str, plugin_dir: str | None) -> dict[str, re.Pattern]:
    sd = re.escape(skill_dir)
    out = {
        "skill": re.compile(rf"{sd}/({_NAME})/SKILL\.md"),
        "skill_script": re.compile(rf"{sd}/{_NAME}/scripts/[A-Za-z0-9_.\-]+"),
        "subagent": re.compile(rf"sub_agents/({_NAME})/AGENT\.md"),
        "script": re.compile(r"scripts/[a-z0-9_][a-z0-9_]*\.py"),
        "script_ref": re.compile(rf"(?:python3?\s+)((?:{sd}/[\w\-]+/)?scripts/[\w.\-]+\.py)"),
    }
    if plugin_dir is not None:
        out["plugin"] = re.compile(rf"{re.escape(plugin_dir)}/({_NAME})\.ts")
    return out


def _rx(surface: SurfaceSpec) -> dict[str, re.Pattern]:
    return _res(surface.name, surface.skill_dir, surface.plugin_dir)


def normalize_rel(rel: str) -> str:
    """Normalise a relative path, rejecting escapes before it is joined to a directory."""
    r = str(rel).strip().replace("\\", "/")
    if r.startswith("/") or ".." in r.split("/"):
        raise ValueError(f"path escapes the harness: {rel!r}")
    while r.startswith("./"):
        r = r[2:]
    return r.strip("/")


def is_allowed(surface: SurfaceSpec, rel: str) -> bool:
    """Whether this path is on the editable surface. A predicate: it never raises."""
    try:
        rel = normalize_rel(rel)
    except ValueError:
        return False
    if rel in surface.always_on:
        return True
    if surface.hooks_file is not None and rel == surface.hooks_file:
        return True
    r = _rx(surface)
    if (
        r["skill"].fullmatch(rel)
        or r["skill_script"].fullmatch(rel)
        or r["subagent"].fullmatch(rel)
        or r["script"].fullmatch(rel)
    ):
        return True
    return "plugin" in r and bool(r["plugin"].fullmatch(rel))


def _stub_paths(surface: SurfaceSpec) -> frozenset[str]:
    return frozenset(rel for rel, _ in surface.stubs)


def read_tree(surface: SurfaceSpec, d: Path | str, *, rejected: list[str] | None = None) -> Tree:
    """rel -> content for every file on the editable surface, README stubs excluded.

    Pass `rejected` to collect paths that exist on disk but are off the surface.
    """
    d = Path(d)
    out: Tree = {}
    if not d.is_dir():
        return out
    stubs = _stub_paths(surface)
    for p in sorted(d.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        rel = p.relative_to(d).as_posix()
        if rel in stubs:
            continue
        if not is_allowed(surface, rel):
            if rejected is not None:
                rejected.append(rel)
            continue
        out[rel] = p.read_bytes().decode("utf-8")
    return out


def write_tree(surface: SurfaceSpec, tree: Tree, dest: Path | str, *, stubs: bool = True) -> Path:
    """Materialise an exact editable tree, with always-on files and optional stubs present.

    Files outside the editable surface are preserved; editable files already there are not.
    """
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    stub_set = _stub_paths(surface)
    for p in sorted(dest.rglob("*"), reverse=True):
        if not p.is_file():
            continue
        rel = str(p.relative_to(dest))
        if is_allowed(surface, rel) or rel in stub_set:
            p.unlink()
    for a in surface.always_on:
        p = dest / a
        p.parent.mkdir(parents=True, exist_ok=True)
        if a not in tree and not p.exists():
            p.write_text("", encoding="utf-8")
    for rel, content in tree.items():
        p = dest / normalize_rel(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n")
    if stubs:
        for rel, body in surface.stubs:
            p = dest / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists():
                p.write_text(body, encoding="utf-8")
    return dest


def always_on_text(surface: SurfaceSpec, tree: Tree) -> str:
    return "\n\n".join(tree.get(a, "") for a in surface.always_on)
