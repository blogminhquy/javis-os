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

The snapshot covers the whole brain, and loops, reminders and Kanban jobs keep running while a chat turn
does. Owner, 27/11/2026: a background flow for a POSCake order created "Nhắc thanh toán đơn 3472" during
an unrelated chat, and the chat got "Đã tạo lịch" lines for it. So an item counts for the turn only when
it is not someone else's: a schedule or loop that names another dashboard chat is that chat's, and one
that appeared while background work ran in the brain (memory_control.background_writer) is that work's.
A schedule that fired or was paused is not one the turn removed.
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


def _reminder_rows(root: Path) -> Dict[str, dict]:
    try:
        d = json.loads((root / "Javis" / "reminders.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(r.get("id")): r for r in (d or {}).get("reminders", []) if isinstance(r, dict) and r.get("id")}


_OWNER_RE = re.compile(r"^owner_chat:\s*(.*?)\s*$", re.M)


def _loop_owner(root: Path, slug: str) -> str:
    try:
        head = (root / "Javis" / "loops" / f"{slug}.md").read_text(encoding="utf-8")[:3000]
    except OSError:
        return ""
    m = _OWNER_RE.search(head)
    return m.group(1).strip().strip("\"'") if m else ""


def _file_mtime(root: Path, kind: str, slug: str) -> float:
    path = {"loop": root / "Javis" / "loops" / f"{slug}.md", "agent": root / "agents" / f"{slug}.md",
            "workflow": root / "workflows" / f"{slug}.md", "skill": root / "skills" / slug / "SKILL.md"}.get(kind)
    try:
        return path.stat().st_mtime if path is not None else 0.0
    except OSError:
        return 0.0


def _background_at(root: Path, ts: float) -> bool:
    if not ts:
        return False
    try:
        import memory_control
        return memory_control.background_at(root, ts)
    except Exception:  # noqa: BLE001 - unknown means "not background": the old behaviour
        return False


def _someone_elses(root: Path, chat: str, item_chat: str, ts: float) -> bool:
    """True when this change belongs to another chat or to background work, not to the turn of `chat`."""
    item_chat = str(item_chat or "").strip()
    if chat and item_chat == chat:
        return False
    if chat and item_chat.startswith("web:"):
        return True
    return _background_at(root, ts)


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


def diff(before: Optional[dict], brain_root, chat: str = "") -> List[dict]:
    """[{kind, id, title, act: new|updated|removed}] for the turn, at most MAX_ITEMS.

    `chat` is the turn's own chat (`web:<session id>`): changes that name another chat, or that appeared while
    background work ran in this brain, are left out (see the module note)."""
    if not before:
        return []
    root = Path(brain_root)
    after = snapshot(root)
    chat = str(chat or "").strip()
    rows = _reminder_rows(root)
    items: List[dict] = []
    for kind in KINDS:
        old, new = before.get(kind) or {}, after.get(kind) or {}
        for key in new:
            if key not in old:
                if kind == "reminder":
                    r = rows.get(key) or {}
                    if _someone_elses(root, chat, r.get("chat_id"), float(r.get("created_at") or 0)):
                        continue
                    title = new[key]
                else:
                    owner = _loop_owner(root, key) if kind == "loop" else ""
                    if _someone_elses(root, chat, owner, _file_mtime(root, kind, key)):
                        continue
                    title = _title(root, kind, key)
                items.append({"kind": kind, "id": key, "title": title or key, "act": "new"})
            elif kind != "reminder" and new[key] != old[key]:
                owner = _loop_owner(root, key) if kind == "loop" else ""
                if _someone_elses(root, chat, owner, _file_mtime(root, kind, key)):
                    continue
                items.append({"kind": kind, "id": key, "title": _title(root, kind, key), "act": "updated"})
        for key in old:
            if key not in new:
                if kind == "reminder":
                    r = rows.get(key)
                    # Fired (done/failed) or paused is not a removal; only a cancel or a delete is.
                    if r is not None and r.get("status") != "cancelled":
                        continue
                    if r is not None and _someone_elses(root, chat, r.get("chat_id"), 0.0):
                        continue
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
