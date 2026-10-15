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


def _section_end(lines: List[str], i0: int) -> int:
    """Index just past the managed section whose header is `lines[i0]`.

    The section is the header, any blank lines right under it, then ONE run of contiguous
    `- ` bullets: exactly what Javis writes. It ends at the first line that is anything else,
    including a blank line after the bullets.

    Before 0.172.0 it ran to the next `## ` heading and only its bullets were kept, so an owner
    paragraph, numbered rule or `### ` subsection written after it was deleted on the next
    rewrite, and the guard (which skipped the same span) never noticed. On 2026-10-15 that
    removed four rule sections the owner had added under "## Lịch sử (tự học)" in a Zalo bot.
    """
    i, seen_bullet = i0 + 1, False
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith("- "):
            seen_bullet = True
        elif s or seen_bullet:
            break
        i += 1
    return i


def split_section(text: str, header: str) -> Tuple[List[str], List[str], List[str]]:
    """(lines before the section, bullet lines inside it, lines after it).

    See `_section_end` for where the section stops. Every line after it comes back in the third
    part untouched (leading blank lines dropped), so nothing the owner wrote there is lost.
    """
    lines = (text or "").splitlines()
    i0 = next((i for i, l in enumerate(lines) if l.strip() == header), None)
    if i0 is None:
        return lines, [], []
    i1 = _section_end(lines, i0)
    bullets = [l.rstrip() for l in lines[i0 + 1:i1] if l.strip().startswith("- ")]
    after = lines[i1:]
    while after and not after[0].strip():
        after.pop(0)
    return lines[:i0], bullets, after


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
    """Non-blank lines outside every Javis-managed section, i.e. what the owner wrote.

    A managed section stops where `split_section` stops (see `_section_end`), so anything the
    owner wrote after its bullets counts as the owner's and the guard notices when it goes.
    """
    managed = {h.strip() for h in managed_headers}
    lines = (text or "").splitlines()
    out, i = [], 0
    while i < len(lines):
        s = lines[i].strip()
        if lines[i].startswith("## ") and s in managed:
            i = _section_end(lines, i)
            continue
        if s:
            out.append(s)
        i += 1
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
