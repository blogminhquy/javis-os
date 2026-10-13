"""Managed sections inside an agent's files, and the guard that keeps the owner's lines.

Self-learning used to lose rules the owner had given an agent (reported 2026-10-13: "messages
sent on Zalo must not use markdown" vanished after a few learning rounds). Two paths did it:

1. The learn engine updated an agent by replacing its whole body with a fresh system prompt,
   written by a model that had only ever seen the agent's slug and a 100-character role.
2. A rule the owner gave in chat could only be stored as a `JAVIS_LESSON`, and the lesson
   section keeps the 15 newest lines, so the rule was evicted 15 lessons later.

This module holds the pieces both paths now share:

- `merge_bullets`: add bullets to ONE `## ` section, dedupe, optionally keep only the newest N.
  Everything outside that section is copied through untouched.
- `extract_rules`: pull `JAVIS_RULE: ...` lines out of an agent's output (the owner-rule twin
  of `JAVIS_LESSON`). The model proposes, code writes.
- `missing_owner_lines`: the guard. Every line the owner wrote (anything outside the sections
  Javis manages itself) must still be present after a write, or the write is refused.

Section names stay Vietnamese: they are content inside the user's brain, read by people and
models, not identifiers.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional, Sequence, Tuple

# Owner rules: never evicted, never rewritten by self-learning. Lives in the agent's
# memory file (memory/agents/<slug>/MEMORY.md), which is loaded into every run of the agent.
OWNER_RULES_HEADER = "## Luật chủ dặn"
# Additions the learn engine makes to an agent body. Javis-managed, capped.
LEARNED_ADDITIONS_HEADER = "## Bổ sung (tự học)"
LEARNED_ADDITIONS_MAX = 20

RULE_MARKER_RE = re.compile(r"^[ \t]*JAVIS_RULE:[ \t]*(.+?)[ \t]*$", re.MULTILINE)
RULES_PER_TURN = 3
RULE_MAX_CHARS = 300


def normalize(line: str) -> str:
    """Dedupe key: drop punctuation, spacing and bullet marks, ignore case."""
    return re.sub(r"\W+", "", line or "").casefold()


def split_section(text: str, header: str) -> Tuple[List[str], List[str], List[str]]:
    """(lines before the section, bullet lines inside it, lines after it).

    The section runs from its exact header line to the next `## ` heading. Non-bullet lines
    inside it are dropped, matching how the lesson section has always been rebuilt.
    """
    lines = (text or "").splitlines()
    i0 = next((i for i, l in enumerate(lines) if l.strip() == header), None)
    if i0 is None:
        return lines, [], []
    i1 = next((i for i in range(i0 + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    bullets = [l.rstrip() for l in lines[i0 + 1:i1] if l.strip().startswith("- ")]
    return lines[:i0], bullets, lines[i1:]


def merge_bullets(text: str, header: str, items: Iterable[str],
                  cap: Optional[int] = None) -> str:
    """Append `items` as bullets to the `header` section, creating it at the end if absent.

    Duplicates (by `normalize`) are skipped. `cap=None` keeps every bullet; a number keeps
    only the newest that many. Lines outside the section come back exactly as they were.
    """
    before, bullets, after = split_section(text, header)
    seen = {normalize(b) for b in bullets}
    for item in items:
        item = (item or "").strip()
        if not item:
            continue
        b = "- " + item
        if normalize(b) in seen:
            continue
        bullets.append(b)
        seen.add(normalize(b))
    if cap is not None:
        bullets = bullets[-cap:]
    while before and not before[-1].strip():
        before.pop()
    out = before + ([""] if before else []) + [header] + bullets
    if after:
        out += [""] + after
    return "\n".join(out).strip()


def extract_rules(out: str) -> Tuple[List[str], str]:
    """Pull `JAVIS_RULE:` lines out of an agent's output. Returns (rules, cleaned output).

    The marker must leave the output: it flows on into `{{prev}}` of the next workflow step,
    into the chat bubble and into the voice.
    """
    if not out or "JAVIS_RULE" not in out:
        return [], out
    rules = [m.group(1).strip()[:RULE_MAX_CHARS] for m in RULE_MARKER_RE.finditer(out)]
    cleaned = re.sub(r"\n{3,}", "\n\n", RULE_MARKER_RE.sub("", out)).strip()
    return [r for r in rules if r][:RULES_PER_TURN], cleaned


def owner_lines(text: str, managed_headers: Sequence[str]) -> List[str]:
    """Non-blank lines outside every Javis-managed section, i.e. what the owner wrote."""
    managed = {h.strip() for h in managed_headers}
    out, inside = [], False
    for line in (text or "").splitlines():
        if line.startswith("## "):
            inside = line.strip() in managed
            if inside:
                continue
        if not inside and line.strip():
            out.append(line.strip())
    return out


def missing_owner_lines(old: str, new: str, managed_headers: Sequence[str]) -> List[str]:
    """Owner lines of `old` that `new` no longer contains. Empty list = safe to write.

    Compared as a multiset of normalized lines, so moving a line or retouching its
    punctuation is fine, while dropping one, or one of two identical lines, is not.
    """
    remaining = {}
    for line in owner_lines(new, managed_headers):
        k = normalize(line)
        remaining[k] = remaining.get(k, 0) + 1
    missing = []
    for line in owner_lines(old, managed_headers):
        k = normalize(line)
        if not k:
            continue
        if remaining.get(k, 0) > 0:
            remaining[k] -= 1
        else:
            missing.append(line)
    return missing
