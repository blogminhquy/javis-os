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

from pathlib import Path
from typing import Mapping, Sequence


GRADER_VERDICT_MARKERS: tuple[str, ...] = (
    "deterministic_eval_summary",
    "deterministic_eval_result",
    "judge_scope_and_deterministic_status",
    "Judge findings on the rendered result",
    '"passed_count"',
    '"pass_rate"',
    '"test_pass_rate"',
)


_MARKER_SCAN_SUFFIXES = frozenset(
    {
        ".md",
        ".txt",
        ".json",
        ".csv",
        ".tsv",
        ".yaml",
        ".yml",
        ".html",
        ".htm",
        ".log",
        ".py",
        ".js",
        ".sh",
        ".xml",
        ".ini",
        ".toml",
        ".patch",
        ".diff",
        "",
    }
)


def assert_tree_has_no_grader_verdicts(
    tree: Mapping[str, str], markers: Sequence[str] = GRADER_VERDICT_MARKERS
) -> None:
    """The same tripwire on an agent-authored harness tree (rel -> body), before it can be
    rolled or stored: such a tree could never afterwards be served as evidence.
    """
    for rel in sorted(tree):
        for m in markers:
            if m in rel:
                raise ValueError(
                    f"harness file {rel!r} has grader-verdict marker {m!r} in its NAME; rename "
                    f"it -- files carrying these strings cannot be served as evidence to later "
                    f"tasks"
                )
        if Path(rel).suffix.lower() not in _MARKER_SCAN_SUFFIXES:
            continue
        body = str(tree[rel])
        for m in markers:
            if m in body:
                where = body.index(m)
                raise ValueError(
                    f"harness file {rel!r} contains grader-verdict marker {m!r} at offset "
                    f"{where} ({body[max(0, where - 60) : where + 120]!r}); remove or rename "
                    f"that string -- files carrying it cannot be served as evidence to later "
                    f"tasks"
                )
