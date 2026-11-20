"""Brain backup on the GitHub account Javis is already signed in to (owner, 20/11/2026).

The owner: "Javis can sign in to GitHub directly now, but the two-way sync on the Self-learning page is still manual. Once
GitHub is connected, linking the backup should be easy too." Before this module the backup card wanted a repository URL
and a fine-grained token made by hand on github.com, even on a machine whose Connections page already showed @login.

What it adds:
  - `effective_token(backup)`: the token the brain sync uses. A backup linked through the GitHub connection
    (`backup.use_github`) uses that connection's token, so a "Sign in with GitHub" token, which never expires, replaces
    a fine-grained token that does (a year at most). A backup with only a URL and no token of its own also borrows the
    connection. A pasted backup token still wins otherwise: whoever set up backup by hand keeps working unchanged.
  - `repos()`: the PRIVATE repos the connection can push to, newest push first, for the one-tap picker. Public repos
    are never offered: a brain holds notes, memories and numbers.
  - `link(full_name)`: point the backup at one of them and switch automatic sync on. The URL comes from GitHub's own
    `clone_url`, so GitHub Enterprise and the test fake work the same.
  - `create(name)`: make a new private repo. A classic token with `repo` can; a "Sign in with GitHub" token cannot,
    because the Javis app does not ask for the Administration permission, so GitHub answers 403. Then the answer
    carries `manual` with a github.com/new link already filled in (name, private) and, for an app sign-in, the page
    that lets Javis see the new repo, so the person still never makes a token.
  - `unlink()`: stop syncing. The repo on GitHub is never touched.

Stdlib plus github_api (httpx). No FastAPI, no main import: testable in isolation.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List
from urllib.parse import quote

import localefmt
from github_api import GitHub, GitHubError

DEFAULT_NAME = "javis-brain-backup"
_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


class BackupLinkError(Exception):
    """A failure worth showing as is (already localized, never carries a token)."""


def _c(vi: str, en: str) -> str:
    return localefmt.chu(vi, en)


def _cfg():
    import config as cfgmod
    return cfgmod


def _gh():
    import github_repos
    return github_repos


def _backup() -> Dict[str, Any]:
    return dict(_cfg().read_settings().get("backup") or {})


def effective_token(b: Dict[str, Any]) -> str:
    """Token of the brain sync for this `backup` section, "" when there is none."""
    b = b or {}
    own = str(b.get("token") or "").strip()
    if own and not b.get("use_github"):
        return own
    try:
        gh = _gh().token()
    except Exception:
        gh = ""
    return gh or own


def token_source(b: Dict[str, Any]) -> str:
    """"github" when the sync rides on the GitHub connection, "token" for a pasted backup token, "" for none."""
    b = b or {}
    own = str(b.get("token") or "").strip()
    if own and not b.get("use_github"):
        return "token"
    try:
        if _gh().token():
            return "github"
    except Exception:
        pass
    return "token" if own else ""


def ready(b: Dict[str, Any]) -> bool:
    """Enough to run a sync: a repository and a token from somewhere."""
    b = b or {}
    return bool(str(b.get("repo_url") or "").strip() and effective_token(b))


def _client() -> GitHub:
    gh = _gh()
    try:
        return gh.client()
    except gh.RepoError as e:
        raise BackupLinkError(str(e))


def _row(r: Dict[str, Any]) -> Dict[str, Any]:
    return {"full_name": str(r.get("full_name") or ""), "private": bool(r.get("private")),
            "pushed_at": r.get("pushed_at") or "", "default_branch": r.get("default_branch") or "",
            "description": (r.get("description") or "")[:140],
            "can_push": bool((r.get("permissions") or {}).get("push", True))}


def repos() -> List[Dict[str, Any]]:
    """Private repos the connection can push to, in GitHub's order (last push first)."""
    try:
        items = _client().repos()
    except GitHubError as e:
        raise BackupLinkError(_c(f"Không lấy được danh sách repository: {e}", f"Could not list repositories: {e}"))
    out = [_row(r) for r in items if isinstance(r, dict) and r.get("private")]
    return [r for r in out if r["full_name"] and r["can_push"]]


def _clone_url(r: Dict[str, Any]) -> str:
    url = str(r.get("clone_url") or "").strip()
    if url:
        return url[:-4] if url.startswith("https://") and url.endswith(".git") else url
    return "https://github.com/" + str(r.get("full_name") or "")


def _save_link(r: Dict[str, Any]) -> Dict[str, Any]:
    branch = str(r.get("default_branch") or "").strip() or "main"
    _cfg().update_settings({"backup": {"repo_url": _clone_url(r), "use_github": True, "enabled": True,
                                       "branch": branch}})
    return {"full_name": str(r.get("full_name") or ""), "repo_url": _clone_url(r), "branch": branch}


def link(full_name: str) -> Dict[str, Any]:
    """Point the backup at a private repo of the connected account and switch automatic sync on."""
    fn = str(full_name or "").strip().strip("/")
    if fn.count("/") != 1:
        raise BackupLinkError(_c("Tên repository không hợp lệ.", "Invalid repository name."))
    try:
        r = _client().repo(fn)
    except GitHubError as e:
        if e.status == 404:
            raise BackupLinkError(_c(f"Javis không thấy repository {fn}. Kiểm tra tên, hoặc cho Javis quyền vào repo đó.",
                                     f"Javis cannot see the repository {fn}. Check the name, or give Javis access to it."))
        raise BackupLinkError(_c(f"Không đọc được repository: {e}", f"Could not read the repository: {e}"))
    if not r.get("private"):
        raise BackupLinkError(_c("Repository này đang công khai. Brain có ghi chú và số liệu riêng, chỉ dùng repository riêng tư.",
                                 "This repository is public. A brain holds private notes and numbers: use a private repository."))
    if not bool((r.get("permissions") or {}).get("push", True)):
        raise BackupLinkError(_c("Tài khoản này không có quyền ghi vào repository đó.",
                                 "This account cannot write to that repository."))
    return _save_link(r)


def manual_steps(name: str = DEFAULT_NAME) -> Dict[str, Any]:
    """Where to make the repo by hand when the token may not create one: github.com/new already filled in."""
    gh = _gh()
    conn = gh.status()
    web = "https://github.com"
    new_url = (f"{web}/new?name={quote(name)}&visibility=private"
               f"&description={quote('Javis OS brain backup')}")
    return {"manual": True, "new_url": new_url, "name": name,
            "install_url": conn.get("install_url") if conn.get("source") == "app" else ""}


def create(name: str = DEFAULT_NAME) -> Dict[str, Any]:
    """Make a private repo and link it. Returns the link, or `manual` steps when GitHub refuses to create one."""
    name = str(name or "").strip() or DEFAULT_NAME
    if not _NAME_RE.match(name) or name in (".", ".."):
        raise BackupLinkError(_c("Tên repository chỉ gồm chữ, số, dấu chấm, gạch nối và gạch dưới.",
                                 "A repository name can only hold letters, digits, dots, hyphens and underscores."))
    cl = _client()
    try:
        r = cl.post("/user/repos", json={"name": name, "private": True, "auto_init": False,
                                         "description": "Javis OS brain backup"})
    except GitHubError as e:
        if e.status == 422:
            # The name is taken on this account: most often the repo made on another machine. Link it when it is a
            # private repo this connection can push to; otherwise say so instead of guessing.
            login = str(_gh().status().get("login") or "")
            if login:
                try:
                    return {**link(f"{login}/{name}"), "existing": True}
                except BackupLinkError as le:
                    raise BackupLinkError(_c(f"Tài khoản đã có repository tên {name}. {le}",
                                             f"The account already has a repository named {name}. {le}"))
            raise BackupLinkError(_c(f"Tài khoản đã có repository tên {name}. Chọn nó trong danh sách.",
                                     f"The account already has a repository named {name}. Pick it from the list."))
        if e.status in (401, 403, 404):
            return manual_steps(name)
        raise BackupLinkError(_c(f"GitHub không tạo được repository: {e}", f"GitHub could not create the repository: {e}"))
    if not isinstance(r, dict) or not r.get("full_name"):
        return manual_steps(name)
    return {**_save_link(r), "created": True}


def unlink() -> Dict[str, Any]:
    """Stop syncing: forget the repository and switch automatic sync off. GitHub and the pasted token are untouched."""
    _cfg().update_settings({"backup": {"repo_url": "", "use_github": False, "enabled": False}})
    return {"unlinked": True}
