"""What Javis does with a conversation's GitHub repos after each turn (spec docs/dev/2026-10-github-trong-chat-spec.md).

Phase G2 (this file's first version): when a turn changed a repo's worktree, run the pre-push quality gate
(github_gate) and post its result into the same conversation. Nothing is pushed yet; phase G3 adds commit, push, PR and
CI tracking on top of the same hook.

The hook is `after_turn(sid, brain)`, called by main right after a turn is saved. main injects how to reach the chat
(`configure(notify=...)`); this module never imports main.
"""
from __future__ import annotations

import asyncio
import hashlib
import threading
from typing import Any, Awaitable, Callable, Dict, List, Optional

import github_gate
import github_repos
import localefmt

# notify(sid, text, ok) posts a Javis message into the web chat `sid`. ok=False makes it a visible alert.
Notify = Callable[[str, str, bool], Awaitable[Any]]
_notify: Optional[Notify] = None
# Last gated state per (session, repo): a turn that changed nothing in a repo does not rerun its checks.
_last_gate: Dict[str, str] = {}
_running: Dict[str, bool] = {}
_lock = threading.Lock()


def configure(notify: Optional[Notify] = None) -> None:
    global _notify
    if notify is not None:
        _notify = notify


def checks_for(rec: Dict[str, Any], worktree: str) -> List[Dict[str, str]]:
    """The repo's saved local checks, or the suggested ones when the owner never edited them."""
    saved = rec.get("checks")
    if isinstance(saved, list):
        return [c for c in saved if isinstance(c, dict) and c.get("run")]
    return github_gate.suggest_checks(worktree)


def fingerprint(worktree: str) -> str:
    """Changes in the worktree relative to its last gate: HEAD plus every uncommitted edit."""
    head = github_repos.git_out(["rev-parse", "HEAD"], worktree)
    status = github_repos.git_out(["status", "--porcelain", "--untracked-files=all"], worktree)
    diff = github_repos.git_out(["diff", "HEAD"], worktree)
    return hashlib.sha256(f"{head}\n{status}\n{diff}".encode("utf-8", "replace")).hexdigest()


def gate_repo(sid: str, brain: str, repo: Dict[str, Any], force: bool = False) -> Optional[Dict[str, Any]]:
    """Run the gate on one attached repo if its worktree changed since the last run. None = nothing to do."""
    wt = repo.get("worktree") or ""
    if not wt:
        return None
    key = f"{sid}:{repo.get('full_name')}"
    try:
        fp = fingerprint(wt)
    except github_repos.RepoError:
        return None
    base = f"origin/{repo.get('default_branch') or 'main'}"
    with _lock:
        if _running.get(key) or (not force and _last_gate.get(key) == fp):
            return None
        _running[key] = True
    try:
        # A worktree identical to the base (no commit, no edit) has nothing to check.
        ahead = github_repos.git_out(["rev-list", "--count", f"{base}..HEAD"], wt) or "0"
        dirty = github_repos.is_dirty(wt)
        if ahead == "0" and not dirty:
            with _lock:
                _last_gate[key] = fp
            return None
        rec = github_repos.find(brain, repo["full_name"]) or {}
        report = github_gate.run_gate(wt, base, checks_for(rec, wt))
        report["full_name"] = repo["full_name"]
        with _lock:
            _last_gate[key] = fp
        return report
    finally:
        with _lock:
            _running.pop(key, None)


def _message(reports: List[Dict[str, Any]]) -> str:
    parts = []
    for r in reports:
        body = github_gate.summary(r) or localefmt.chu("Không có lệnh kiểm tra nào chạy được ở máy.",
                                                        "No local check could run on this machine.")
        parts.append(f"**{r['full_name']}**\n{body}")
    return "\n\n".join(parts)


async def after_turn(sid: str, brain: str) -> List[Dict[str, Any]]:
    """Called after every saved web turn. Cheap when the chat has no GitHub repo (one registry read)."""
    try:
        repos = await asyncio.to_thread(github_repos.session_repos, sid, brain)
    except Exception:
        return []
    repos = [r for r in repos if r.get("worktree")]
    if not repos:
        return []
    reports = []
    for repo in repos:
        rep = await asyncio.to_thread(gate_repo, sid, brain, repo)
        if rep is not None:
            reports.append(rep)
    if reports and _notify is not None:
        ok = all(r["ok"] and not r["merge_block"] for r in reports)
        try:
            await _notify(sid, _message(reports), ok)
        except Exception:
            pass
    return reports
