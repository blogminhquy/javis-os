"""Routes of GitHub inside chat (spec docs/dev/2026-10-github-trong-chat-spec.md).

    GET  /github/status                        the built-in connection (no token ever leaves the server)
    POST /github/connect                       token=...  or  use_backup=1 (reuse the brain-backup token after a check)
    POST /github/disconnect
    GET  /github/repos?q=&brain=               the account's repos, marking the ones this brain has cloned
    GET  /github/branches?full_name=           a repo's branches, the default one first (the branch picker)
    GET  /github/local?brain=                  repos cloned in this brain
    POST /github/local/remove                  brain, full_name: delete the local clone (GitHub untouched)
    GET  /github/local/checks                  the repo's local check commands (saved, or suggested from its CI)
    POST /github/local/checks                  brain, full_name, commands (one per line) or reset=1
    POST /github/local/automerge               brain, full_name, on: the per-repo auto-merge switch (default on)
    GET  /github/local/metrics?full_name=      per engine and model: first-push green, fix rounds, review findings
    GET  /github/icons?sids=a,b                status icon per conversation for the chat list
    POST /github/session/{sid}/merge           full_name: a person merges a ready PR
    POST /github/session/{sid}/next            text: a job to start once this chat's PRs are merged; cancel=<id>
    GET  /github/session/{sid}?brain=          repos attached to a conversation, with its branch and worktree
    POST /github/session/{sid}/repos           brain, repos (comma separated full names): set the chat's repos
    POST /github/session/{sid}/detach          brain, full_name, force: remove one repo from this chat only
    POST /github/session/{sid}/base            brain, full_name, branch: the base branch this chat works from

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

    @r.get("/github/local/checks")
    async def gh_checks(brain: str = Query(""), full_name: str = Query(...)):
        return await _call(github_repos.get_checks, brain, full_name)

    @r.post("/github/local/checks")
    async def gh_checks_set(brain: str = Form(""), full_name: str = Form(...), commands: str = Form(""),
                            reset: str = Form("")):
        """`commands`: one command per line (a line ending in a backslash continues). `reset=1` goes back to the
        commands Javis suggests from the repo's CI."""
        if str(reset).strip() in ("1", "true"):
            return await _call(github_repos.set_checks, brain, full_name, None)
        lines, buf = [], ""
        for raw in str(commands or "").splitlines():
            buf = (buf + "\n" + raw) if buf else raw
            if raw.rstrip().endswith("\\"):
                continue
            if buf.strip():
                lines.append({"run": buf.strip()})
            buf = ""
        if buf.strip():
            lines.append({"run": buf.strip()})
        return await _call(github_repos.set_checks, brain, full_name, lines)

    @r.post("/github/local/automerge")
    async def gh_automerge(brain: str = Form(""), full_name: str = Form(...), on: str = Form("1")):
        return await _call(github_repos.set_auto_merge, brain, full_name, str(on).strip() in ("1", "true", "on"))

    @r.get("/github/local/metrics")
    async def gh_metrics(full_name: str = Query("")):
        """Per engine and model: jobs merged, share green on the first push, fix rounds, review findings (spec 13.2)."""
        import github_work
        return await _call(lambda: {"rows": github_work.metrics_summary(full_name)})

    @r.get("/github/icons")
    async def gh_icons(sids: str = Query("")):
        """Status icon per conversation for the chat list (spec 12.1). Only chats with GitHub work are returned."""
        def icons():
            import github_store
            rows = github_store.store().sessions([s.strip() for s in str(sids or "").split(",") if s.strip()])
            return {"icons": {sid: github_store.icon(rs) for sid, rs in rows.items()}}
        return await _call(icons)

    @r.post("/github/session/{sid}/merge")
    async def gh_merge(sid: str, full_name: str = Form(...)):
        """A person presses Merge (auto-merge off, no CI, or a change Javis would not merge alone)."""
        import github_work
        try:
            return {"ok": True, **(await github_work.merge_by_person(sid, full_name))}
        except github_repos.RepoError as e:
            return _err(str(e))

    @r.post("/github/session/{sid}/next")
    async def gh_next(sid: str, text: str = Form(""), cancel: str = Form("")):
        """Queue a next job for after this chat's PRs are merged, or cancel one (`cancel`=<id>)."""
        import github_work
        try:
            if str(cancel).strip():
                return {"ok": True, **github_work.cancel_next(sid, int(cancel))}
            return {"ok": True, **github_work.queue_next(sid, text)}
        except (github_repos.RepoError, ValueError) as e:
            return _err(str(e))

    @r.get("/github/session/{sid}")
    async def gh_session(sid: str, brain: str = Query("")):
        def view():
            import github_work
            v = github_repos.session_view(sid, brain)
            state = github_work.session_state(sid)
            v["icon"], v["work"] = state["icon"], state["repos"]
            return v
        return await _call(view)

    @r.post("/github/session/{sid}/repos")
    async def gh_session_repos(sid: str, brain: str = Form(""), repos: str = Form("")):
        names = [x.strip() for x in str(repos or "").split(",") if x.strip()]
        return await _call(github_repos.attach, sid, brain, _root(brain), names)

    @r.get("/github/branches")
    async def gh_branches(full_name: str = Query(...)):
        return await _call(github_repos.branches, full_name)

    @r.post("/github/session/{sid}/base")
    async def gh_session_base(sid: str, brain: str = Form(""), full_name: str = Form(...), branch: str = Form(...)):
        return await _call(github_repos.set_base, sid, brain, full_name, branch)

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
