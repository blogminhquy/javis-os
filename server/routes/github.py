"""Routes of GitHub inside chat (spec docs/dev/2026-10-github-trong-chat-spec.md).

    GET  /github/status                        the built-in connection (no token ever leaves the server)
    POST /github/connect                       token=...  or  use_backup=1 (reuse the brain-backup token after a check)
    POST /github/disconnect
    GET  /github/repos?q=&brain=               the account's repos, marking the ones this brain has cloned
    GET  /github/local?brain=                  repos cloned in this brain
    POST /github/local/remove                  brain, full_name: delete the local clone (GitHub untouched)
    GET  /github/session/{sid}?brain=          repos attached to a conversation, with its branch and worktree
    POST /github/session/{sid}/repos           brain, repos (comma separated full names): set the chat's repos
    POST /github/session/{sid}/detach          brain, full_name, force: remove one repo from this chat only

Every handler runs its git and HTTP work in a worker thread: a clone can take minutes and must not block the loop.
Errors from github_repos are already localized and safe to show (no token in them).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from fastapi import APIRouter, Form, Query
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

import github_repos


@dataclass
class GitHubDeps:
    brain_root: Callable[[str], str]
    # Names of jobs still running on a repo (phase G3 fills this in); removal refuses while any is listed.
    busy_jobs: Optional[Callable[[str, str], List[str]]] = None


_DEPS: Optional[GitHubDeps] = None


def _err(msg: str, status: int = 400):
    return JSONResponse({"ok": False, "error": msg}, status_code=status)


async def _call(fn, *args, **kw):
    try:
        out = await run_in_threadpool(fn, *args, **kw)
    except github_repos.RepoError as e:
        return _err(str(e))
    if isinstance(out, dict):
        return {"ok": True, **out}
    return {"ok": True, "items": out}


def _root(brain: str) -> str:
    return _DEPS.brain_root(brain) if _DEPS else brain


def _make_router() -> APIRouter:
    r = APIRouter()

    @r.get("/github/status")
    async def gh_status():
        return {"ok": True, **github_repos.status()}

    @r.post("/github/connect")
    async def gh_connect(token: str = Form(""), use_backup: str = Form("")):
        if str(use_backup).strip() in ("1", "true", "on"):
            return await _call(github_repos.connect_backup)
        return await _call(github_repos.connect, token)

    @r.post("/github/disconnect")
    async def gh_disconnect():
        return await _call(github_repos.disconnect)

    @r.get("/github/repos")
    async def gh_repos(q: str = Query(""), brain: str = Query("")):
        return await _call(github_repos.remote_repos, q, brain)

    @r.get("/github/local")
    async def gh_local(brain: str = Query("")):
        return await _call(github_repos.local_view, brain)

    @r.post("/github/local/remove")
    async def gh_local_remove(brain: str = Form(""), full_name: str = Form(...)):
        busy = _DEPS.busy_jobs(brain, full_name) if (_DEPS and _DEPS.busy_jobs) else []
        return await _call(github_repos.remove_from_brain, brain, full_name, busy)

    @r.get("/github/session/{sid}")
    async def gh_session(sid: str, brain: str = Query("")):
        return await _call(github_repos.session_view, sid, brain)

    @r.post("/github/session/{sid}/repos")
    async def gh_session_repos(sid: str, brain: str = Form(""), repos: str = Form("")):
        names = [x.strip() for x in str(repos or "").split(",") if x.strip()]
        return await _call(github_repos.attach, sid, brain, _root(brain), names)

    @r.post("/github/session/{sid}/detach")
    async def gh_session_detach(sid: str, brain: str = Form(""), full_name: str = Form(...),
                                force: str = Form("")):
        return await _call(github_repos.detach, sid, full_name, brain, str(force).strip() in ("1", "true"))

    return r


def register(app, deps: GitHubDeps):
    """Attach the router. main.py calls this right after the Coding routes (route_table.json locks the order)."""
    global _DEPS
    _DEPS = deps
    router = _make_router()
    app.include_router(router)
    return router
