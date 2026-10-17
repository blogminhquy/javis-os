"""What a chat turn changed in the brain's capabilities, shown under the answer with Undo (0.200.0).

Idea borrowed from OpenMausBot ("changes a bot makes to itself"): a bot can schedule, edit skills and
create agents on its own, and each change shows as one plain line with Undo. Javis already does this
for memory (memory_receipt.py, 0.190.0); this covers the rest of what a turn can create from chat:

    reminders and cron jobs   Javis/reminders.json (pending ones)
    loops                     Javis/loops/<slug>.md
    agents                    agents/<slug>.md
    workflows                 workflows/<slug>.md
    skills                    skills/<slug>/SKILL.md

The truth comes from the files, not from what the model says: a snapshot before the turn and a diff
after. The line is a hidden block (`<!-- JAVIS_DOI: {...} -->`) in a message stored through
`push_to_chat`, so a refresh draws it again (dashboard/chat-doi.js). Undo calls the existing route for
that kind (cancel a reminder, delete a loop, agent, workflow or skill); only NEW items get an Undo,
because putting an edited file back needs its old text, which this snapshot does not keep.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

import localefmt

MAX_ITEMS = 6
KINDS = ("reminder", "loop", "agent", "workflow", "skill")
_NAME_RE = re.compile(r"^name:\s*(.+?)\s*$", re.M)


def _mtimes(folder: Path, pattern: str) -> Dict[str, int]:
    out = {}
    if not folder.is_dir():
        return out
    for p in folder.glob(pattern):
        if not p.is_file():
            continue
        slug = p.parent.name if p.name == "SKILL.md" else p.stem
        if slug.startswith("."):
            continue
        try:
            out[slug] = p.stat().st_mtime_ns
        except OSError:
            continue
    return out


def _pending_reminders(root: Path) -> Dict[str, str]:
    try:
        d = json.loads((root / "Javis" / "reminders.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(r.get("id")): str(r.get("label") or r.get("text") or "")[:120]
            for r in (d or {}).get("reminders", []) if r.get("status") == "pending" and r.get("id")}


def snapshot(brain_root) -> dict:
    """Cheap: one stat per capability file plus one small JSON read."""
    root = Path(brain_root)
    return {
        "reminder": _pending_reminders(root),
        "loop": _mtimes(root / "Javis" / "loops", "*.md"),
        "agent": _mtimes(root / "agents", "*.md"),
        "workflow": _mtimes(root / "workflows", "*.md"),
        "skill": _mtimes(root / "skills", "*/SKILL.md"),
    }


def _title(root: Path, kind: str, slug: str) -> str:
    path = {"loop": root / "Javis" / "loops" / f"{slug}.md", "agent": root / "agents" / f"{slug}.md",
            "workflow": root / "workflows" / f"{slug}.md", "skill": root / "skills" / slug / "SKILL.md"}.get(kind)
    if path is None:
        return slug
    try:
        head = path.read_text(encoding="utf-8")[:2000]
    except OSError:
        return slug
    m = _NAME_RE.search(head)
    return (m.group(1).strip().strip("\"'") if m else slug)[:120]


def diff(before: Optional[dict], brain_root) -> List[dict]:
    """[{kind, id, title, act: new|updated|removed}] for the turn, at most MAX_ITEMS."""
    if not before:
        return []
    root = Path(brain_root)
    after = snapshot(root)
    items: List[dict] = []
    for kind in KINDS:
        old, new = before.get(kind) or {}, after.get(kind) or {}
        for key in new:
            if key not in old:
                title = new[key] if kind == "reminder" else _title(root, kind, key)
                items.append({"kind": kind, "id": key, "title": title or key, "act": "new"})
            elif kind != "reminder" and new[key] != old[key]:
                items.append({"kind": kind, "id": key, "title": _title(root, kind, key), "act": "updated"})
        for key in old:
            if key not in new:
                items.append({"kind": kind, "id": key, "title": (old[key] if kind == "reminder" else key) or key,
                              "act": "removed"})
    return items[:MAX_ITEMS]


def receipt_block(items: List[dict], brain_key: str) -> str:
    gon = [{"kind": i["kind"], "id": str(i["id"])[:120], "title": str(i.get("title") or "")[:120],
            "act": i["act"] if i.get("act") in ("new", "updated", "removed") else "updated"} for i in items]
    data = {"brain": str(brain_key or ""), "items": gon}
    return "<!-- JAVIS_DOI: " + json.dumps(data, ensure_ascii=False).replace("-->", "- ->") + " -->"


_KIND_VI = {"reminder": "lịch", "loop": "việc lặp", "agent": "cộng sự", "workflow": "quy trình", "skill": "kỹ năng"}
_KIND_EN = {"reminder": "schedule", "loop": "loop", "agent": "partner", "workflow": "workflow", "skill": "skill"}


def receipt_text(items: List[dict]) -> str:
    """Plain line under the hidden block, for channels without the block (Telegram) and screen readers."""
    parts = []
    for i in items:
        kv, ke = _KIND_VI.get(i["kind"], i["kind"]), _KIND_EN.get(i["kind"], i["kind"])
        t = str(i.get("title") or i.get("id") or "")
        if i["act"] == "new":
            parts.append(localefmt.chu(f"Đã tạo {kv}: {t}", f"Created {ke}: {t}"))
        elif i["act"] == "removed":
            parts.append(localefmt.chu(f"Đã gỡ {kv}: {t}", f"Removed {ke}: {t}"))
        else:
            parts.append(localefmt.chu(f"Đã sửa {kv}: {t}", f"Edited {ke}: {t}"))
    return " · ".join(parts)
