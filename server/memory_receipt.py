"""What a chat turn did to the brain's memory, shown under the answer (0.190.0).

Owner, 16/10/2026: the memory list left the settings column; memory is handled in chat. Two things keep that honest:

- **A receipt.** A turn that saved, changed or forgot a memory gets one small line under the answer: "Đã nhớ: ... ·
  Hoàn tác". People see what Javis keeps at the moment it keeps it, and undo it with one tap. The line is a hidden
  block (`<!-- JAVIS_NHO: {...} -->`) in a message stored through `push_to_chat`, so a refresh draws it again
  (dashboard/chat-nho.js).
- **No empty claims.** An answer that says "đã nhớ", "đã quên", "đã thu hồi" while nothing changed in the brain's
  memory and no memory tool wrote anything gets one line of fact under it, the same way an empty "xong em báo" does
  (`background_status`). Weak models say "done" without calling the tool; this catches it.

The truth comes from the files: a snapshot of `memory/` before the turn and one after. `memory_control.note_change`
covers what lives outside those files (agent lessons in the lesson store).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Optional

import lang as lang_mod
import lang_registry
import lexicon
import localefmt
import memory_control as MC

SKIP_DIRS = ("conversations", "runs")      # chat logs and run logs change every turn: not memory
MAX_ITEMS = 5


def _walk(mem: Path):
    if not mem.is_dir():
        return
    for p in mem.rglob("*"):
        if not p.is_file() or p.suffix not in (".md", ".json"):
            continue
        rel = p.relative_to(mem)
        if any(part in SKIP_DIRS for part in rel.parts[:-1]):
            continue
        yield rel.as_posix(), p


def snapshot(mem_dir) -> dict:
    """{files: {relpath: mtime}, t0}. Cheap: one stat per file of the memory folder."""
    mem = Path(mem_dir)
    files = {}
    for rel, p in _walk(mem):
        try:
            files[rel] = p.stat().st_mtime_ns
        except OSError:
            continue
    titles = MC._index_titles(mem)
    return {"files": files, "titles": titles, "t0": time.time()}


def _title(mem: Path, slug: str, titles: Dict[str, str]) -> str:
    if titles.get(slug):
        return titles[slug]
    try:
        _meta, body = MC._split((mem / "facts" / f"{slug}.md").read_text(encoding="utf-8"))
        first = next((ln.strip() for ln in body.splitlines() if ln.strip()), "")
        return first[:80] or slug
    except OSError:
        return slug


def facts_diff(snap: Optional[dict], mem_dir) -> List[dict]:
    """Memories saved (new), changed (updated) or forgotten during the turn: [{slug, title, act}]."""
    if not snap:
        return []
    mem = Path(mem_dir)
    before = {k: v for k, v in snap.get("files", {}).items() if k.startswith("facts/") and k.endswith(".md")}
    now = {}
    for rel, p in _walk(mem):
        if rel.startswith("facts/") and rel.endswith(".md"):
            try:
                now[rel] = p.stat().st_mtime_ns
            except OSError:
                continue
    titles = MC._index_titles(mem)
    out = []
    for rel in sorted(now):
        slug = rel[len("facts/"):-3]
        if rel not in before:
            out.append({"slug": slug, "title": _title(mem, slug, titles), "act": "new"})
        elif now[rel] != before[rel]:
            out.append({"slug": slug, "title": _title(mem, slug, titles), "act": "updated"})
    for rel in sorted(set(before) - set(now)):
        slug = rel[len("facts/"):-3]
        out.append({"slug": slug, "title": (snap.get("titles") or {}).get(slug) or slug, "act": "forgot"})
    return out[:MAX_ITEMS]


def changed(snap: Optional[dict], mem_dir) -> bool:
    """Anything in the brain's memory changed during the turn (files, or a write noted by the memory tools)."""
    if not snap:
        return True        # no snapshot: cannot tell, so never accuse
    mem = Path(mem_dir)
    now = {}
    for rel, p in _walk(mem):
        try:
            now[rel] = p.stat().st_mtime_ns
        except OSError:
            continue
    if now != snap.get("files", {}):
        return True
    return MC.changed_since(mem, float(snap.get("t0") or 0))


# ── the receipt ───────────────────────────────────────────────────────────────

def receipt_block(items: List[dict], brain_key: str) -> str:
    gon = [{"slug": str(i.get("slug") or "")[:120], "title": str(i.get("title") or "")[:120],
            "act": i.get("act") if i.get("act") in ("new", "updated", "forgot") else "updated"} for i in items]
    data = {"brain": str(brain_key or ""), "items": gon}
    return "<!-- JAVIS_NHO: " + json.dumps(data, ensure_ascii=False).replace("-->", "- ->") + " -->"


def receipt_text(items: List[dict]) -> str:
    """Plain line under the hidden block: what a channel without the block (or a screen reader) shows."""
    parts = []
    for i in items:
        if i.get("act") == "new":
            parts.append(localefmt.chu("Đã nhớ: ", "Remembered: ") + str(i.get("title") or ""))
        elif i.get("act") == "forgot":
            parts.append(localefmt.chu("Đã quên: ", "Forgot: ") + str(i.get("title") or ""))
        else:
            parts.append(localefmt.chu("Đã cập nhật: ", "Updated: ") + str(i.get("title") or ""))
    return " · ".join(parts)


# ── empty claims ──────────────────────────────────────────────────────────────

def _patterns(text: str):
    lex = lexicon.get(lang_registry.chuan_hoa("") or lang_mod.detect(text or "")[0])
    if lex is not None:
        return lex.MEMORY_CLAIM
    out = []
    for ma in lexicon.ma_list():
        mod = lexicon.get(ma)
        if mod is not None:
            out.extend(mod.MEMORY_CLAIM)
    return tuple(out)


def detect_claim(text: str) -> str:
    """Name of the "I remembered / forgot / revoked it" pattern in an answer, or ""."""
    import background_status as BS   # same normalisation and code stripping as the empty-promise check
    raw = str(text or "")
    if not raw.strip():
        return ""
    norm = BS._norm(BS._INLINE_CODE.sub(" ", BS._CODE_FENCE.sub(" ", raw)))
    for name, pattern in _patterns(raw):
        if pattern.search(norm):
            return name
    return ""


def claim_note() -> str:
    return localefmt.chu(
        "⚠ Mình vừa nói đã nhớ hoặc đã quên, nhưng trí nhớ của brain này không đổi gì. Nhắn lại \"nhớ giúp: ...\" "
        "hoặc \"quên ...\" để mình làm thật.",
        "⚠ I just said I remembered or forgot something, but this brain's memory did not change. Say \"remember: ...\" "
        "or \"forget ...\" again and I will really do it.")
