"""The Learned tab of an assistant (Cộng sự page, 2026-11-16).

Owner, 16/11/2026: bring the project's self-learning into the Cộng sự page, rename its documents button to
"Tài liệu & Đã học" and add a tab there. An assistant already learns on its own (`JAVIS_LESSON` lines go to
`agent_lessons`), but since 0.190.0 nothing on screen showed what it had learnt. This tab is that list, kept as plain
as the project's Learned tab: one row per lesson in use, with edit and remove, and a box to add one. No scopes to pick,
no promote button: the owner removed exactly that in 0.190.0 because nobody knew where a lesson applied.

It reads and writes the store that already feeds the prompt, never a second one, so what the tab shows is what the
assistant uses:

- `L<id>` rows: lessons in `agent_lessons` with status `active`. A lesson the owner adds here goes to scope `*`
  (every chat, team and workflow step), the same as `javis_memory op=lesson_add`. Editing keeps the scope and makes the
  lesson the owner's. Removing revokes it, so the assistant does not learn the same words again.
- `C<n>` rows: old lessons still under "## Bài học (tự học)" in the assistant's MEMORY.md (before 0.156.0). Removing
  deletes the line; editing moves it into the store as the owner's lesson.

Every write is checked the way project notes are (`refuse`: a key or a sentence shaped like an order is not stored).
`register_routes(app, Deps(...))` is called once by `main.py`; the functions above it are pure enough to test with a
real store and a temporary brain.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Optional

import agent_lessons as AL
import memory_chat

LIST_MAX = 200


@dataclass
class Deps:
    brain_key: Callable[[str], str]                         # dashboard brain -> resolved root
    agent_exists: Callable[[str, str], bool]                # (root, slug) -> the assistant file is there
    agent_key: Callable[[str, str, bool], Optional[str]]    # (root, slug, register) -> agent_key | None
    store: Callable[[bool], Any]                            # (create) -> GoalStore | None
    legacy_file: Callable[[str, str], Path]                 # (root, slug) -> memory/agents/<slug>/MEMORY.md
    refuse: Callable[[str], str]                            # text -> why it is not stored, "" when fine


def _where(scope: str) -> str:
    s = str(scope or "")
    return "all" if s == "*" else "team" if s.startswith("team:") else "dm"


def listing(d: Deps, root: str, slug: str) -> dict:
    """Lessons in use (the owner's first, then newest) and the old MEMORY.md lines."""
    key, store = d.agent_key(root, slug, False), d.store(False)
    rows = AL.lessons(store, key, status="active", limit=LIST_MAX) if key and store is not None else []
    rows.sort(key=lambda r: (r["source"] != "owner", -float(r.get("created_at") or 0)))
    lessons = [{"id": f"L{r['id']}", "text": r["text"], "source": "owner" if r["source"] == "owner" else "learnt",
                "where": _where(r["scope"]), "created_at": r.get("created_at") or 0} for r in rows]
    legacy = [{"id": f"C{i}", "text": t, "source": "legacy", "where": "all", "created_at": 0}
              for i, t in enumerate(memory_chat._legacy_file_lines(d.legacy_file(root, slug)), 1)]
    return {"lessons": lessons + legacy}


def add(d: Deps, root: str, slug: str, text: str) -> dict:
    body = AL.clean_text(text)
    if not AL.normalize(body):
        return {"error": "empty"}
    store, key = d.store(True), d.agent_key(root, slug, True)
    if not key or store is None:
        return {"error": "store"}
    return {"id": f"L{AL.add(store, agent_key=key, scope='*', kind='method', text=body, source='owner', by='owner')}"}


def _ref(lesson_id: str):
    s = str(lesson_id or "").strip().upper()
    if len(s) > 1 and s[0] in "LC" and s[1:].isdigit():
        return s[0], int(s[1:])
    return None, 0


def edit(d: Deps, root: str, slug: str, lesson_id: str, text: str) -> dict:
    kind, n = _ref(lesson_id)
    if not AL.normalize(AL.clean_text(text)):
        return {"error": "empty"}
    if kind == "C":
        path = d.legacy_file(root, slug)
        lines = memory_chat._legacy_file_lines(path)
        if not 1 <= n <= len(lines):
            return {"error": "gone"}
        res = add(d, root, slug, text)
        if "id" in res:
            memory_chat._remove_legacy_line(path, n)
        return res
    if kind != "L":
        return {"error": "gone"}
    key, store = d.agent_key(root, slug, False), d.store(False)
    r = AL.edit(store, n, text, agent_key=key, by="owner") if key and store is not None else None
    return {"id": f"L{r['id']}"} if r else {"error": "gone"}


def remove(d: Deps, root: str, slug: str, lesson_id: str) -> dict:
    kind, n = _ref(lesson_id)
    if kind == "C":
        gone = memory_chat._remove_legacy_line(d.legacy_file(root, slug), n)
        return {"ok": True} if gone else {"error": "gone"}
    if kind != "L":
        return {"error": "gone"}
    key, store = d.agent_key(root, slug, False), d.store(False)
    r = AL.revoke(store, n, by="owner", reason="owner_panel", agent_key=key) if key and store is not None else None
    return {"ok": True} if r else {"error": "gone"}


def register_routes(app, d: Deps) -> None:
    """Owner routes (main's auth and CSRF middleware run first). Forms, like the project notes routes:
    - `GET  /agents/{slug}/learned?brain=`: {ok, lessons: [{id, text, source, where, created_at}]}.
    - `POST /agents/{slug}/learned` (brain, text): add a lesson the owner wrote, used everywhere.
    - `POST /agents/{slug}/learned/{lesson_id}/update` (brain, text): rewrite one.
    - `POST /agents/{slug}/learned/{lesson_id}/delete` (brain): stop using one."""
    from fastapi import Form, Query
    from fastapi.responses import JSONResponse
    import localefmt

    errors = {
        "missing": (404, "Không tìm thấy trợ lý", "Assistant not found"),
        "empty": (400, "Bài học đang trống", "The lesson is empty"),
        "store": (409, "Kho bài học chưa sẵn sàng, thử lại sau vài giây",
                  "The lesson store is not ready yet, try again in a few seconds"),
        "gone": (409, "Bài học này không còn nữa, tải lại danh sách", "This lesson is gone, reload the list"),
    }

    def fail(code: str):
        status, vi, en = errors[code]
        return JSONResponse({"ok": False, "error": localefmt.chu(vi, en)}, status_code=status)

    def refused(text: str):
        why = d.refuse(text) if (text or "").strip() else ""
        if not why:
            return None
        return JSONResponse({"ok": False, "error": localefmt.chu(
            "Không lưu, vì nội dung " + why, "Not saved: the text looks like a secret or an injected command")},
            status_code=400)

    async def run(brain: str, slug: str, fn):
        def go():
            root = d.brain_key(brain)
            if not d.agent_exists(root, slug):
                return {"error": "missing"}
            return fn(root)
        res = await asyncio.to_thread(go)
        if "error" in res:
            return fail(res["error"])
        return {"ok": True, **res}

    @app.get("/agents/{slug}/learned")
    async def agent_learned_list(slug: str, brain: str = Query("brain")):
        return await run(brain, slug, lambda root: listing(d, root, slug))

    @app.post("/agents/{slug}/learned")
    async def agent_learned_add(slug: str, text: str = Form(""), brain: str = Form("brain")):
        return refused(text) or await run(brain, slug, lambda root: add(d, root, slug, text))

    @app.post("/agents/{slug}/learned/{lesson_id}/update")
    async def agent_learned_update(slug: str, lesson_id: str, text: str = Form(""), brain: str = Form("brain")):
        return refused(text) or await run(brain, slug, lambda root: edit(d, root, slug, lesson_id, text))

    @app.post("/agents/{slug}/learned/{lesson_id}/delete")
    async def agent_learned_delete(slug: str, lesson_id: str, brain: str = Form("brain")):
        return await run(brain, slug, lambda root: remove(d, root, slug, lesson_id))


__all__: List[str] = ["Deps", "listing", "add", "edit", "remove", "register_routes"]
