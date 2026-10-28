"""Thin GitHub REST client for the GitHub-in-chat feature (spec docs/dev/2026-10-github-trong-chat-spec.md).

Why its own module instead of an MCP connector: the spec (section 4.1) keeps everything that talks to GitHub in Javis's
own server code, so the status icons and every step after a push come from GitHub's answers, never from what a model
says it did. It is also built into the core (section 5.1, owner 2026-10-27): no Store pack, no external MCP.

Design rules:
- Sync, small, stdlib plus httpx (already a dependency). Callers run it in a worker thread.
- The API base is configurable (`JAVIS_GITHUB_API`, or the `base` argument) so tests run against a local fake server.
  Nothing in tests ever reaches api.github.com.
- The token is never logged and never part of an exception message. Errors carry the HTTP status and GitHub's own
  `message`, which is what a person needs to fix a token or a permission.
- No FastAPI, no main import: testable in isolation.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

DEFAULT_BASE = "https://api.github.com"
TIMEOUT = 20.0
# Pages of 100 when listing repos. Three pages cover anyone who works with GitHub by hand; a person with more than 300
# repos still finds the rest with the search box (the list is sorted by last push, newest first).
MAX_REPO_PAGES = 3


class GitHubError(Exception):
    """A failed GitHub call, safe to show: status code plus GitHub's message, never the token."""

    def __init__(self, status: int, message: str):
        super().__init__(f"GitHub {status}: {message}" if status else message)
        self.status = status
        self.message = message


def api_base() -> str:
    return (os.environ.get("JAVIS_GITHUB_API") or DEFAULT_BASE).rstrip("/")


class GitHub:
    """One token, one base URL. Cheap to build: make one per operation."""

    def __init__(self, token: str, base: Optional[str] = None, timeout: float = TIMEOUT):
        self.token = (token or "").strip()
        self.base = (base or api_base()).rstrip("/")
        self.timeout = timeout

    # ---- transport ----
    def _headers(self) -> Dict[str, str]:
        h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
             "User-Agent": "javis-os"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def request(self, method: str, path: str, *, params: Optional[dict] = None, json: Any = None,
                accept: Optional[str] = None, raw: bool = False):
        url = path if path.startswith("http") else self.base + path
        headers = self._headers()
        if accept:
            headers["Accept"] = accept
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as c:
                r = c.request(method, url, params=params, json=json, headers=headers)
        except httpx.HTTPError as e:
            raise GitHubError(0, f"cannot reach GitHub ({type(e).__name__})") from None
        if r.status_code >= 400:
            msg = ""
            try:
                body = r.json()
                msg = str(body.get("message") or "")
                errs = body.get("errors")
                if isinstance(errs, list) and errs:
                    first = errs[0]
                    detail = first.get("message") if isinstance(first, dict) else str(first)
                    if detail:
                        msg = f"{msg} ({detail})" if msg else str(detail)
            except Exception:
                msg = (r.text or "")[:200]
            raise GitHubError(r.status_code, msg or r.reason_phrase)
        if raw:
            return r
        if r.status_code == 204 or not r.content:
            return None
        try:
            return r.json()
        except ValueError:
            return r.text

    def get(self, path: str, **kw):
        return self.request("GET", path, **kw)

    def post(self, path: str, **kw):
        return self.request("POST", path, **kw)

    def put(self, path: str, **kw):
        return self.request("PUT", path, **kw)

    def patch(self, path: str, **kw):
        return self.request("PATCH", path, **kw)

    # ---- account ----
    def user(self) -> Dict[str, Any]:
        """The token's account. Also returns the classic-token scopes header when GitHub sends one."""
        r = self.request("GET", "/user", raw=True)
        data = r.json()
        scopes = r.headers.get("x-oauth-scopes")
        data["_scopes"] = [s.strip() for s in scopes.split(",") if s.strip()] if scopes is not None else None
        return data

    def repos(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for page in range(1, MAX_REPO_PAGES + 1):
            batch = self.get("/user/repos", params={"per_page": 100, "page": page, "sort": "pushed",
                                                     "affiliation": "owner,collaborator,organization_member"})
            if not isinstance(batch, list):
                break
            out.extend(batch)
            if len(batch) < 100:
                break
        return out

    def repo(self, full_name: str) -> Dict[str, Any]:
        return self.get(f"/repos/{full_name}")

    # ---- pull requests ----
    def find_pull(self, full_name: str, head_branch: str) -> Optional[Dict[str, Any]]:
        owner = full_name.split("/", 1)[0]
        prs = self.get(f"/repos/{full_name}/pulls", params={"head": f"{owner}:{head_branch}", "state": "all",
                                                             "per_page": 10})
        if isinstance(prs, list):
            for p in prs:
                if (p.get("head") or {}).get("ref") == head_branch:
                    return p
        return None

    def create_pull(self, full_name: str, head: str, base: str, title: str, body: str,
                    draft: bool = False) -> Dict[str, Any]:
        return self.post(f"/repos/{full_name}/pulls", json={"head": head, "base": base, "title": title,
                                                             "body": body, "draft": draft})

    def pull(self, full_name: str, number: int) -> Dict[str, Any]:
        return self.get(f"/repos/{full_name}/pulls/{int(number)}")

    def mark_ready(self, full_name: str, pull_node_id: str) -> None:
        """Draft -> ready for review. REST has no endpoint for this; GraphQL does."""
        q = "mutation($id: ID!) { markPullRequestReadyForReview(input: {pullRequestId: $id}) { clientMutationId } }"
        self.post("/graphql", json={"query": q, "variables": {"id": pull_node_id}})

    def merge_pull(self, full_name: str, number: int, sha: str, method: str) -> Dict[str, Any]:
        return self.put(f"/repos/{full_name}/pulls/{int(number)}/merge",
                        json={"sha": sha, "merge_method": method})

    def update_branch(self, full_name: str, number: int, expected_head: str) -> None:
        """Merge the base branch into the PR branch (branch protection that wants it up to date)."""
        self.put(f"/repos/{full_name}/pulls/{int(number)}/update-branch", json={"expected_head_sha": expected_head})

    def comment(self, full_name: str, number: int, body: str) -> None:
        self.post(f"/repos/{full_name}/issues/{int(number)}/comments", json={"body": body})

    # ---- checks ----
    def check_runs(self, full_name: str, sha: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for page in range(1, 4):
            d = self.get(f"/repos/{full_name}/commits/{sha}/check-runs", params={"per_page": 100, "page": page})
            runs = (d or {}).get("check_runs") or []
            out.extend(runs)
            if len(runs) < 100:
                break
        return out

    def statuses(self, full_name: str, sha: str) -> List[Dict[str, Any]]:
        d = self.get(f"/repos/{full_name}/commits/{sha}/status")
        return list((d or {}).get("statuses") or [])

    def required_checks(self, full_name: str, branch: str) -> Optional[List[str]]:
        """Names of required checks on a branch, or None when the token cannot read branch protection."""
        try:
            d = self.get(f"/repos/{full_name}/branches/{branch}/protection/required_status_checks")
        except GitHubError as e:
            if e.status == 404:
                return []          # no protection: nothing is formally required
            return None            # 403 and the rest: unknown
        ctx = list((d or {}).get("contexts") or [])
        for c in (d or {}).get("checks") or []:
            if isinstance(c, dict) and c.get("context") and c["context"] not in ctx:
                ctx.append(c["context"])
        return ctx

    def branches(self, full_name: str) -> List[str]:
        """Branch names of a repo, as GitHub lists them (paged, at most 1000)."""
        out: List[str] = []
        for page in range(1, 11):
            batch = self.get(f"/repos/{full_name}/branches", params={"per_page": 100, "page": page})
            if not isinstance(batch, list):
                break
            out.extend(str(b.get("name")) for b in batch if isinstance(b, dict) and b.get("name"))
            if len(batch) < 100:
                break
        return out

    def branch_sha(self, full_name: str, branch: str) -> str:
        """Head commit of a branch, "" when it does not exist."""
        try:
            d = self.get(f"/repos/{full_name}/branches/{branch}")
        except GitHubError as e:
            if e.status == 404:
                return ""
            raise
        return str(((d or {}).get("commit") or {}).get("sha") or "")

    def job_log(self, full_name: str, job_id: int) -> str:
        """Plain-text log of one Actions job ("" when GitHub does not give one)."""
        try:
            r = self.request("GET", f"/repos/{full_name}/actions/jobs/{int(job_id)}/logs", raw=True)
        except GitHubError:
            return ""
        return r.text or ""

    def rerun_job(self, full_name: str, job_id: int) -> None:
        self.post(f"/repos/{full_name}/actions/jobs/{int(job_id)}/rerun")
