"""GitHub connection and the repos a brain works on (spec docs/dev/2026-10-github-trong-chat-spec.md, phase G1).

What lives here:
  1. The ONE GitHub connection of this Javis (section 5.1). It is built into the core: the Connections page always
     shows it, no Store pack, no MCP. The token is stored encrypted (`secrets_store`), or the connection points at the
     brain-backup token (`settings.backup.token`) after a check, so a person who already set up backup has nothing to
     paste twice. One connection per install rather than per brain: the backup token is per install too, and a second
     account per brain has no user asking for it yet (the spec said per brain; corrected there).
  2. The repo registry: which GitHub repos a brain has cloned, and where. Clones live OUTSIDE the brain tree
     (`STATE_DIR/repos/<brain>/<owner>/<repo>`, section 4.3): the brain is synced to GitHub and indexed, so code inside
     it would leak into the brain backup and flood search.
  3. Attaching repos to a conversation. Each attached repo gets a worktree of its own for that conversation, on a new
     branch `javis/<session>`, so two conversations never edit the same files (section 6). The coding_store binding is
     the single source of truth for which folders a conversation works in; this module only adds GitHub repos to it.
  4. The two ways to let go of a repo (section 5.3): detach from one chat (the clone stays) and remove from the brain
     (the local clone and its worktrees are deleted, GitHub is never touched). Removal refuses while work could be lost.

Git authentication never goes through argv or the remote URL: the token rides in `GIT_CONFIG_*` environment variables
as an HTTP header, only for Javis's own git calls. The clone's `origin` stays the clean https URL, and a model running
shell commands in the worktree has no credential to push with (section 4.1: the model never pushes, Javis does).

Stdlib plus httpx (through github_api), no FastAPI, no main import.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import coding_store
import localefmt
import winproc
from config import STATE_DIR
from github_api import GitHub, GitHubError

REPOS_DIR = STATE_DIR / "repos"
STORE_PATH = STATE_DIR / "github.json"
GIT_TIMEOUT = 60
CLONE_TIMEOUT = 600
_lock = threading.RLock()
# Serialises git work per clone: two chats attaching the same repo at once must not run two `git worktree add` in it.
_repo_locks: Dict[str, threading.Lock] = {}
SOURCE = "github"
# Slow-changing list: cache the account's repos for a minute so typing in the search box costs no API calls.
_REPO_CACHE: Dict[str, Any] = {"at": 0.0, "token": "", "items": []}
REPO_CACHE_S = 60.0


class RepoError(Exception):
    """A failure worth showing as is (already localized)."""


def _c(vi: str, en: str) -> str:
    return localefmt.chu(vi, en)


def _now() -> float:
    return time.time()


# ============================================================
# Settings: the connection
# ============================================================
def _settings():
    import config as cfgmod
    return cfgmod


def _read_conn() -> Dict[str, Any]:
    return dict((_settings().read_settings().get("github") or {}))


def _write_conn(conn: Dict[str, Any]) -> None:
    """Replace the whole `github` section. The token is encrypted at rest by config (`github.token` is in
    `_SECRET_PATHS`), so it is written here in clear and never by hand-rolled crypto."""
    empty = {"source": "", "token": "", "login": "", "user_id": 0, "missing": [], "connected_at": 0}
    _settings().update_settings({"github": {**empty, **(conn or {})}})


def backup_token() -> str:
    return str(((_settings().read_settings().get("backup") or {}).get("token")) or "").strip()


def token() -> str:
    """The token Javis uses for GitHub, or "" when not connected."""
    conn = _read_conn()
    if conn.get("source") == "backup":
        return backup_token()
    return str(conn.get("token") or "").strip() if conn.get("source") == "own" else ""


def user_id() -> int:
    """GitHub numeric id of the connected account (for the noreply commit email), 0 when unknown."""
    try:
        return int(_read_conn().get("user_id") or 0)
    except (TypeError, ValueError):
        return 0


def _check_token(tok: str) -> Dict[str, Any]:
    """Validate a token against GitHub. Returns {login, scopes_ok, missing} or raises RepoError."""
    if not tok:
        raise RepoError(_c("Chưa có token.", "No token given."))
    try:
        u = GitHub(tok).user()
    except GitHubError as e:
        if e.status == 401:
            raise RepoError(_c("GitHub không nhận token này (sai hoặc đã hết hạn).",
                               "GitHub rejected this token (wrong or expired)."))
        raise RepoError(_c(f"Không kiểm tra được token: {e}", f"Could not check the token: {e}"))
    scopes = u.get("_scopes")
    missing: List[str] = []
    # Classic tokens list their scopes; fine-grained tokens do not (scopes is None) and are checked per repo instead.
    if scopes is not None and "repo" not in scopes:
        missing.append("repo")
    if scopes is not None and "workflow" not in scopes:
        missing.append("workflow")
    return {"login": u.get("login") or "", "id": int(u.get("id") or 0), "missing": missing,
            "classic": scopes is not None}


def connect(tok: str) -> Dict[str, Any]:
    tok = (tok or "").strip()
    info = _check_token(tok)
    _write_conn({"source": "own", "token": tok, "login": info["login"], "user_id": info["id"],
                 "missing": info["missing"], "connected_at": _now()})
    _REPO_CACHE.update(at=0.0, items=[])
    return status()


def connect_backup() -> Dict[str, Any]:
    tok = backup_token()
    if not tok:
        raise RepoError(_c("Chưa có token sao lưu brain để dùng chung.", "There is no brain-backup token to reuse."))
    info = _check_token(tok)
    _write_conn({"source": "backup", "login": info["login"], "user_id": info["id"], "missing": info["missing"],
                 "connected_at": _now()})
    _REPO_CACHE.update(at=0.0, items=[])
    return status()


def disconnect() -> Dict[str, Any]:
    _write_conn({})
    _REPO_CACHE.update(at=0.0, items=[])
    return status()


def status() -> Dict[str, Any]:
    conn = _read_conn()
    tok = token()
    return {
        "connected": bool(tok),
        "login": conn.get("login") or "",
        "source": conn.get("source") or "",
        # A classic token missing scopes still works for reading; say which ones so the person can add them.
        "missing": list(conn.get("missing") or []),
        "backup_token": bool(backup_token()),
        "has_git": shutil.which("git") is not None,
    }


def client() -> GitHub:
    tok = token()
    if not tok:
        raise RepoError(_c("Chưa kết nối GitHub. Vào trang Kết nối để kết nối.",
                           "GitHub is not connected. Connect it on the Connections page."))
    return GitHub(tok)


# ============================================================
# Git helpers (token in the environment, never in argv)
# ============================================================
def git_env(tok: Optional[str] = None) -> Dict[str, str]:
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["LC_ALL"] = "C"
    env.pop("GIT_ASKPASS", None)
    tok = token() if tok is None else tok
    if tok:
        basic = base64.b64encode(f"x-access-token:{tok}".encode()).decode()
        n = int(env.get("GIT_CONFIG_COUNT") or 0)
        env["GIT_CONFIG_COUNT"] = str(n + 1)
        env[f"GIT_CONFIG_KEY_{n}"] = "http.extraheader"
        env[f"GIT_CONFIG_VALUE_{n}"] = f"AUTHORIZATION: basic {basic}"
    return env


def _redact(text: str) -> str:
    tok = token()
    out = str(text or "")
    if tok:
        out = out.replace(tok, "***")
        out = out.replace(base64.b64encode(f"x-access-token:{tok}".encode()).decode(), "***")
    return out


def git(args: List[str], cwd: str, *, timeout: int = GIT_TIMEOUT, auth: bool = False,
        check: bool = True) -> subprocess.CompletedProcess:
    try:
        p = subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, env=git_env() if auth else git_env(""),
                           creationflags=winproc.no_window())
    except FileNotFoundError:
        raise RepoError(_c("Máy này chưa cài git.", "git is not installed on this machine."))
    except subprocess.TimeoutExpired:
        raise RepoError(_c(f"Lệnh git chạy quá {timeout} giây, đã dừng: git {args[0]}",
                           f"git {args[0]} ran over {timeout} seconds and was stopped."))
    if check and p.returncode != 0:
        lines = _redact((p.stderr or p.stdout or "").strip()).splitlines()
        last = lines[-1] if lines else _c("không rõ lý do", "unknown reason")
        raise RepoError(_c(f"git {args[0]} hỏng: {last}", f"git {args[0]} failed: {last}"))
    return p


def git_out(args: List[str], cwd: str, **kw) -> str:
    return (git(args, cwd, **kw).stdout or "").strip()


def is_dirty(path: str) -> bool:
    try:
        return bool(git_out(["status", "--porcelain"], path))
    except RepoError:
        return True     # unreadable counts as dirty: refusing a delete is the safe mistake


def unpushed_count(path: str) -> int:
    """Commits on HEAD that no origin branch has. Unreadable counts as 1 (the safe answer)."""
    try:
        return int(git_out(["rev-list", "--count", "HEAD", "--not", "--remotes=origin"], path) or 0)
    except (RepoError, ValueError):
        return 1


# ============================================================
# Registry
# ============================================================
def _empty() -> dict:
    return {"version": 1, "repos": [], "bases": {}}


def _load() -> dict:
    try:
        d = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _empty()
    except Exception:
        try:
            STORE_PATH.rename(STORE_PATH.with_suffix(".json.broken"))
        except Exception:
            pass
        return _empty()
    if not isinstance(d, dict) or not isinstance(d.get("repos"), list):
        return _empty()
    return d


def _save(d: dict) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STORE_PATH)


_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def norm_full_name(full_name: str) -> str:
    s = str(full_name or "").strip().strip("/")
    if s.endswith(".git"):
        s = s[:-4]
    if not _NAME_RE.match(s) or ".." in s:
        raise RepoError(_c(f"Tên repo không hợp lệ: {full_name}", f"Invalid repo name: {full_name}"))
    return s


def _brain_slug(brain_root: str) -> str:
    name = Path(str(brain_root or "brain")).name or "brain"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)[:60] or "brain"


def clone_path(brain_root: str, full_name: str) -> Path:
    owner, name = norm_full_name(full_name).split("/", 1)
    return REPOS_DIR / _brain_slug(brain_root) / owner / name


def list_local(brain: str = "") -> List[Dict[str, Any]]:
    return [dict(r) for r in _load()["repos"] if not brain or r.get("brain") == brain]


def find(brain: str, full_name: str) -> Optional[Dict[str, Any]]:
    fn = norm_full_name(full_name).lower()
    for r in _load()["repos"]:
        if r.get("brain") == brain and str(r.get("full_name") or "").lower() == fn:
            return dict(r)
    return None


def _put(rec: Dict[str, Any]) -> None:
    with _lock:
        d = _load()
        d["repos"] = [r for r in d["repos"] if r.get("id") != rec["id"]]
        d["repos"].append(rec)
        _save(d)


def _drop(rid: str) -> None:
    with _lock:
        d = _load()
        d["repos"] = [r for r in d["repos"] if r.get("id") != rid]
        _save(d)


# ---- base branch per conversation (0.368.0) ----
# A chat works on its own branch cut from a base: the repo's default branch unless the person picked another one
# ("Change branch" on the repo chip). The pick lives here, keyed by chat and repo, and the PR targets it.
def session_base(sid: str, full_name: str) -> str:
    bases = (_load().get("bases") or {}).get(str(sid or ""), {}) or {}
    return str(bases.get(str(full_name or "").lower()) or "")


def _set_session_base(sid: str, full_name: str, base: str) -> None:
    with _lock:
        d = _load()
        bases = d.setdefault("bases", {})
        per = bases.setdefault(str(sid), {})
        if base:
            per[str(full_name).lower()] = base
        else:
            per.pop(str(full_name).lower(), None)
        if not per:
            bases.pop(str(sid), None)
        _save(d)


def _forget_bases(sid: str) -> None:
    with _lock:
        d = _load()
        if (d.get("bases") or {}).pop(str(sid), None) is not None:
            _save(d)


def norm_branch(name: str) -> str:
    """A branch name safe to hand to git: no leading dash, no `..`, no `.lock`, nothing outside [A-Za-z0-9._/-]."""
    s = str(name or "").strip()
    if (not s or len(s) > 200 or s.startswith(("-", "/")) or s.endswith(("/", ".", ".lock")) or ".." in s
            or "//" in s or not re.match(r"^[A-Za-z0-9._/-]+$", s)):
        raise RepoError(_c(f"Tên nhánh không hợp lệ: {name}", f"Invalid branch name: {name}"))
    return s


def branches(full_name: str) -> Dict[str, Any]:
    """Branches of a repo for the branch picker: the default branch first, then the rest by name."""
    fn = norm_full_name(full_name)
    tok = token()
    if not tok:
        raise RepoError(_c("Chưa kết nối GitHub.", "GitHub is not connected."))
    gh = GitHub(tok)
    try:
        default = str((gh.repo(fn) or {}).get("default_branch") or "main")
        # Javis's own working branches (javis/...) are where chats push, never a base to start from.
        names = sorted({b for b in gh.branches(fn) if not b.startswith("javis/")} - {default}, key=str.lower)
    except GitHubError as e:
        raise RepoError(_c(f"Không lấy được danh sách nhánh: {e}", f"Could not list branches: {e}"))
    return {"default": default, "items": [default] + names}


def _repo_lock(path: str) -> threading.Lock:
    with _lock:
        lk = _repo_locks.get(path)
        if lk is None:
            lk = _repo_locks[path] = threading.Lock()
        return lk


# ============================================================
# Remote list
# ============================================================
def remote_repos(q: str = "", brain: str = "") -> List[Dict[str, Any]]:
    tok = token()
    if not tok:
        raise RepoError(_c("Chưa kết nối GitHub.", "GitHub is not connected."))
    now = _now()
    if _REPO_CACHE["token"] != tok or now - _REPO_CACHE["at"] > REPO_CACHE_S:
        try:
            items = GitHub(tok).repos()
        except GitHubError as e:
            raise RepoError(_c(f"Không lấy được danh sách repo: {e}", f"Could not list repos: {e}"))
        _REPO_CACHE.update(at=now, token=tok, items=items)
    local = {str(r.get("full_name") or "").lower() for r in list_local(brain)}
    term = str(q or "").strip().lower()
    out = []
    for r in _REPO_CACHE["items"]:
        fn = str(r.get("full_name") or "")
        if term and term not in fn.lower():
            continue
        out.append({"full_name": fn, "private": bool(r.get("private")), "default_branch": r.get("default_branch") or "",
                    "pushed_at": r.get("pushed_at") or "", "description": (r.get("description") or "")[:140],
                    "can_push": bool((r.get("permissions") or {}).get("push", True)),
                    "cloned": fn.lower() in local})
    return out


# ============================================================
# Clone
# ============================================================
def ensure_clone(brain: str, brain_root: str, full_name: str) -> Dict[str, Any]:
    """Clone the repo into this brain's repo folder, or fetch it when it is already there. Returns the record."""
    full_name = norm_full_name(full_name)
    gh = client()
    try:
        meta = gh.repo(full_name)
    except GitHubError as e:
        if e.status == 404:
            raise RepoError(_c(f"Không thấy repo {full_name}, hoặc token chưa được cấp quyền vào repo này.",
                               f"Repo {full_name} not found, or the token has no access to it."))
        raise RepoError(_c(f"Không đọc được repo {full_name}: {e}", f"Could not read repo {full_name}: {e}"))
    full_name = meta.get("full_name") or full_name
    default_branch = meta.get("default_branch") or "main"
    clone_url = meta.get("clone_url") or f"https://github.com/{full_name}.git"
    can_push = bool((meta.get("permissions") or {}).get("push", True))
    dest = clone_path(brain_root, full_name)
    with _repo_lock(str(dest)):
        rec = find(brain, full_name)
        if dest.is_dir() and (dest / ".git").exists():
            git(["fetch", "--prune", "origin"], str(dest), auth=True, timeout=CLONE_TIMEOUT)
        else:
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)   # a half-finished clone from a crash, never user work
            dest.parent.mkdir(parents=True, exist_ok=True)
            git(["clone", "--filter=blob:none", "--no-tags", clone_url, str(dest)], str(dest.parent),
                auth=True, timeout=CLONE_TIMEOUT)
        if not rec:
            rec = {"id": uuid.uuid4().hex[:12], "brain": brain, "added_at": _now()}
        # Merge methods the repo allows, in Javis's order of preference (spec 11.1: follow the repo's settings).
        allowed = [m for m, k in (("squash", "allow_squash_merge"), ("merge", "allow_merge_commit"),
                                  ("rebase", "allow_rebase_merge")) if meta.get(k, True)]
        rec.update({"full_name": full_name, "path": str(dest), "default_branch": default_branch,
                    "clone_url": clone_url, "private": bool(meta.get("private")), "can_push": can_push,
                    "merge_methods": allowed or ["squash", "merge", "rebase"], "fetched_at": _now()})
        folder = coding_store.them_thu_muc(str(dest), brain=brain, ten=full_name.split("/", 1)[1],
                                           nguon=SOURCE, repo=full_name)
        rec["folder_id"] = folder["id"]
        _put(rec)
    return dict(rec)


# ============================================================
# Attach to a conversation
# ============================================================
def _sid8(sid: str) -> str:
    return coding_store._sid_ngan(sid)


def session_branch(sid: str) -> str:
    return f"javis/{_sid8(sid)}"


def _worktree_dir(rec: Dict[str, Any], sid: str) -> Path:
    return coding_store.WORKTREE_DIR / f"gh-{rec['id']}-{_sid8(sid)}"


def ensure_worktree(sid: str, rec: Dict[str, Any]) -> Dict[str, str]:
    """This conversation's worktree of the repo, created on `javis/<session>` from origin's default branch."""
    existing = coding_store.worktree_thu_muc(sid, rec["folder_id"])
    if existing and Path(existing).is_dir():
        return {"worktree": existing, "branch": coding_store.nhanh_hien_tai(existing)}
    dest = _worktree_dir(rec, sid)
    branch = session_branch(sid)
    clone = rec["path"]
    with _repo_lock(clone):
        coding_store.WORKTREE_DIR.mkdir(parents=True, exist_ok=True)
        git(["worktree", "prune"], clone, check=False)
        have = git(["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"], clone, check=False).returncode == 0
        if dest.exists() and not (dest / ".git").exists():
            shutil.rmtree(dest, ignore_errors=True)
        if not dest.exists():
            base_name = session_base(sid, rec.get("full_name") or "") or rec.get("default_branch") or "main"
            if not have and base_name != (rec.get("default_branch") or "main"):
                git(["fetch", "origin", f"+refs/heads/{base_name}:refs/remotes/origin/{base_name}"], clone, auth=True,
                    timeout=300)
            base = f"origin/{base_name}"
            args = ["worktree", "add", str(dest), branch] if have else ["worktree", "add", "-b", branch, str(dest), base]
            git(args, clone)
            # The branch tracks nothing yet; the first push sets its upstream.
            git(["config", f"branch.{branch}.javisBase", base_name], clone, check=False)
    coding_store.dat_worktree_thu_muc(sid, rec["folder_id"], str(dest))
    return {"worktree": str(dest), "branch": branch}


def attach(sid: str, brain: str, brain_root: str, full_names: List[str]) -> Dict[str, Any]:
    """Set the GitHub repos of a conversation (clone what is missing, one worktree each).

    Non-GitHub folders the conversation already has stay where they are (a pinned folder stays the main one). Repos no
    longer in the list are detached, which refuses while their worktree holds unsaved work.
    """
    sid = str(sid or "").strip()
    if not sid:
        raise RepoError(_c("Thiếu mã cuộc trò chuyện.", "Missing conversation id."))
    wanted: List[str] = []
    for fn in full_names or []:
        n = norm_full_name(fn)
        if n.lower() not in {w.lower() for w in wanted}:
            wanted.append(n)
    recs = [ensure_clone(brain, brain_root, fn) for fn in wanted]
    current = coding_store.thu_muc_cua_phien(sid)
    keep_other = [r["id"] for r in current if r.get("nguon") != SOURCE]
    wanted_ids = [r["folder_id"] for r in recs]
    for r in current:
        if r.get("nguon") == SOURCE and r["id"] not in wanted_ids:
            detach(sid, r.get("repo") or "", brain)
    coding_store.dat_rang_buoc(sid, thu_muc_ids=keep_other + wanted_ids)
    for rec in recs:
        ensure_worktree(sid, rec)
    return session_view(sid, brain)


def _rec_for_folder(brain: str, folder: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    fn = folder.get("repo") or ""
    if not fn:
        return None
    try:
        return find(brain, fn) or next((r for r in list_local() if r.get("folder_id") == folder.get("id")), None)
    except RepoError:
        return None


def _work_at_risk(path: str) -> str:
    """Why deleting `path` would lose work, or "" when it is safe."""
    if not Path(path).is_dir():
        return ""
    if is_dirty(path):
        return _c("còn sửa đổi chưa commit", "has uncommitted changes")
    n = unpushed_count(path)
    if n:
        return _c(f"còn {n} commit chưa đẩy lên GitHub", f"has {n} commit(s) not pushed to GitHub")
    return ""


def _remove_worktree(clone: str, wt: str) -> None:
    if Path(clone).is_dir():
        git(["worktree", "remove", "--force", wt], clone, check=False)
        git(["worktree", "prune"], clone, check=False)
    if Path(wt).exists():
        shutil.rmtree(wt, ignore_errors=True)


def detach(sid: str, full_name: str, brain: str = "", force: bool = False) -> Dict[str, Any]:
    """Remove a repo from ONE conversation. The clone stays in the brain; this chat's worktree goes when it is safe."""
    full_name = norm_full_name(full_name)
    folders = [r for r in coding_store.thu_muc_cua_phien(sid)
               if r.get("nguon") == SOURCE and str(r.get("repo") or "").lower() == full_name.lower()]
    if not folders:
        return {"ok": True, "detached": False}
    folder = folders[0]
    wt = coding_store.worktree_thu_muc(sid, folder["id"])
    if wt and not force:
        risk = _work_at_risk(wt)
        if risk:
            raise RepoError(_c(f"Chưa bỏ được {full_name} khỏi cuộc trò chuyện: nhánh của cuộc này {risk} (tại {wt}).",
                               f"Cannot detach {full_name}: this chat's branch {risk} (at {wt})."))
    if wt:
        _remove_worktree(folder["duong_dan"], wt)
    coding_store.dat_worktree_thu_muc(sid, folder["id"], "")
    ids = [r["id"] for r in coding_store.thu_muc_cua_phien(sid) if r["id"] != folder["id"]]
    coding_store.dat_rang_buoc(sid, thu_muc_ids=ids)
    return {"ok": True, "detached": True}


def remove_from_brain(brain: str, full_name: str, busy: Optional[List[str]] = None) -> Dict[str, Any]:
    """Delete the local clone and every worktree of it. GitHub is never called (section 5.3).

    Refuses, naming each place, while a job runs on it (`busy`), or while the clone or any worktree holds
    uncommitted changes or commits GitHub does not have.
    """
    rec = find(brain, full_name)
    if not rec:
        raise RepoError(_c(f"Brain này không có repo {full_name}.", f"This brain has no repo {full_name}."))
    problems: List[str] = []
    for b in busy or []:
        problems.append(_c(f"đang có việc chạy: {b}", f"a job is running: {b}"))
    risk = _work_at_risk(rec["path"])
    if risk:
        problems.append(f"{rec['path']}: {risk}")
    users = coding_store.sessions_using(rec.get("folder_id") or "")
    for sid in users:
        wt = coding_store.worktree_thu_muc(sid, rec["folder_id"])
        r = _work_at_risk(wt) if wt else ""
        if r:
            problems.append(f"{wt}: {r}")
    if problems:
        raise RepoError(_c("Chưa gỡ được, để khỏi mất việc: ", "Not removed, to avoid losing work: ") + "; ".join(problems))
    for sid in users:
        wt = coding_store.worktree_thu_muc(sid, rec["folder_id"])
        if wt:
            _remove_worktree(rec["path"], wt)
            coding_store.dat_worktree_thu_muc(sid, rec["folder_id"], "")
        ids = [r["id"] for r in coding_store.thu_muc_cua_phien(sid) if r["id"] != rec["folder_id"]]
        coding_store.dat_rang_buoc(sid, thu_muc_ids=ids)
    path = Path(rec["path"]).resolve()
    root = REPOS_DIR.resolve()
    # Only ever delete inside STATE_DIR/repos: a registry edited by hand must not be able to point rmtree elsewhere.
    if root in path.parents and path.exists():
        shutil.rmtree(path, ignore_errors=False, onerror=_force_remove)
    if rec.get("folder_id"):
        coding_store.bo_thu_muc(rec["folder_id"])
    _drop(rec["id"])
    return {"ok": True, "removed": rec["full_name"], "github_untouched": True}


def _force_remove(func, path, _exc):
    """Windows keeps git object files read-only; clear the bit and retry once."""
    try:
        os.chmod(path, 0o700)
        func(path)
    except Exception:
        pass


# ============================================================
# Views
# ============================================================
def session_repos(sid: str, brain: str = "") -> List[Dict[str, Any]]:
    """GitHub repos attached to a conversation, with this chat's worktree and branch."""
    out = []
    for folder in coding_store.thu_muc_cua_phien(sid):
        if folder.get("nguon") != SOURCE:
            continue
        rec = _rec_for_folder(brain, folder) or {}
        wt = coding_store.worktree_thu_muc(sid, folder["id"])
        out.append({"full_name": folder.get("repo") or rec.get("full_name") or "", "folder_id": folder["id"],
                    "clone": folder["duong_dan"], "worktree": wt,
                    "branch": coding_store.nhanh_hien_tai(wt) if wt and Path(wt).is_dir() else "",
                    "default_branch": rec.get("default_branch") or "", "repo_id": rec.get("id") or "",
                    "base_branch": session_base(sid, folder.get("repo") or rec.get("full_name") or "")
                    or rec.get("default_branch") or "main",
                    "can_push": rec.get("can_push", True)})
    return out


def set_base(sid: str, brain: str, full_name: str, base: str) -> Dict[str, Any]:
    """Move this chat's work in one repo onto another base branch (spec 6, "Change branch" on the repo chip).

    Only while the chat has nothing on its branch yet: no unsaved edit and no commit the current base lacks (an open
    PR always has one). Then the chat's branch restarts from the new base and the next PR targets it.
    """
    fn = norm_full_name(full_name)
    base = norm_branch(base)
    repo = next((r for r in session_repos(sid, brain) if r["full_name"].lower() == fn.lower()), None)
    if not repo:
        raise RepoError(_c(f"{fn} chưa gắn vào cuộc trò chuyện này.", f"{fn} is not attached to this chat."))
    if base == repo["base_branch"]:
        return session_view(sid, brain)
    if base not in branches(fn)["items"]:
        raise RepoError(_c(f"Không thấy nhánh {base} trên GitHub.", f"Branch {base} does not exist on GitHub."))
    wt = repo.get("worktree") or ""
    if wt and Path(wt).is_dir():
        if is_dirty(wt):
            raise RepoError(_c(f"{fn}: còn sửa đổi chưa lưu trong cuộc này, xong việc đó rồi đổi nhánh.",
                               f"{fn}: this chat still has unsaved edits; finish that work before changing branch."))
        try:
            ahead = int(git_out(["rev-list", "--count", f"origin/{repo['base_branch']}..HEAD"], wt) or 0)
        except (RepoError, ValueError):
            ahead = 1
        if ahead:
            raise RepoError(_c(f"{fn}: nhánh của cuộc này đang có việc chưa merge vào {repo['base_branch']}. "
                               "Xong việc đó (hoặc mở cuộc trò chuyện mới) rồi đổi nhánh.",
                               f"{fn}: this chat's branch has work not merged into {repo['base_branch']} yet. Finish it "
                               "(or start a new chat) before changing branch."))
        git(["fetch", "origin", f"+refs/heads/{base}:refs/remotes/origin/{base}"], wt, auth=True, timeout=300)
        cur = coding_store.nhanh_hien_tai(wt) or session_branch(sid)
        git(["checkout", "-q", "-B", cur, f"origin/{base}"], wt)
        git(["config", f"branch.{cur}.javisBase", base], wt, check=False)
    _set_session_base(sid, fn, "" if base == (repo.get("default_branch") or "main") else base)
    return session_view(sid, brain)


def session_view(sid: str, brain: str = "") -> Dict[str, Any]:
    return {"ok": True, "repos": session_repos(sid, brain)}


def local_view(brain: str) -> List[Dict[str, Any]]:
    out = []
    for r in list_local(brain):
        users = coding_store.sessions_using(r.get("folder_id") or "")
        out.append({"full_name": r["full_name"], "path": r["path"], "exists": Path(r["path"]).is_dir(),
                    "default_branch": r.get("default_branch") or "", "chats": len(users),
                    "auto_merge": auto_merge_on(r), "fetched_at": r.get("fetched_at") or 0})
    return out


def prompt_block(sid: str, brain: str = "") -> str:
    """Prompt lines naming the conversation's GitHub repos and where to edit them. "" when none is attached.

    Prompt text stays Vietnamese like the other coding blocks (docs/quy-uoc-dev.md: prompts are not translated).
    """
    try:
        repos = [r for r in session_repos(sid, brain) if r.get("worktree")]
    except Exception:
        return ""
    if not repos:
        return ""
    lines = ["", "# === REPO GITHUB CỦA CUỘC TRÒ CHUYỆN NÀY ==="]
    for r in repos:
        lines.append(f"- {r['full_name']}: sửa trong {r['worktree']} (nhánh {r['branch'] or session_branch(sid)}, "
                     f"tách từ {r.get('base_branch') or r['default_branch'] or 'main'})")
    lines.append("Chỉ sửa trong các thư mục trên, KHÔNG sửa bản clone gốc. KHÔNG tự `git push`, không tự merge, "
                 "không đổi remote: việc đẩy lên GitHub do Javis làm.")
    lines.append("Trước khi kết thúc lượt có sửa code: tự chạy test và lint của repo. Sửa lỗi thì viết hoặc chạy một "
                 "test TÁI HIỆN lỗi trước (đỏ), sửa, rồi chạy lại đúng test đó cho xanh. KHÔNG bỏ qua, xoá hay nới "
                 "test, không sửa workflow CI để cho xanh. Sau mỗi lượt Javis tự chạy bộ kiểm tra của repo; xanh thì Javis "
                 "tự commit, đẩy lên nhánh của cuộc này, mở PR và theo dõi CI. CI đỏ thì Javis mở một lượt sửa "
                 "kèm log, tối đa 3 vòng.")
    # Spec 7.1: the repo's own rules reach every engine, not only the ones that read CLAUDE.md natively.
    # Spec 13.1: plus the lessons Javis wrote down for this repo after real failures (kept in the brain).
    try:
        import github_gate
        import github_work
        for r in repos:
            lessons = github_work.read_lessons(brain, r["full_name"])
            if lessons:
                lines.append(f"Bài học đã ghi cho repo {r['full_name']} (từ lỗi thật trước đây):")
                lines += [f"- {x}" for x in lessons]
            rules = github_gate.repo_rules(r["worktree"])
            if rules["files"]:
                lines.append(f"Luật của repo {r['full_name']} (đọc đủ ở: {', '.join(rules['files'])}):")
                lines.append(rules["text"])
    except Exception:
        pass
    return "\n".join(lines) + "\n"


def forget_session(sid: str) -> Dict[str, Any]:
    """A deleted conversation: remove its worktrees that hold nothing unsaved; keep (and report) the others.

    A worktree with work left is kept on disk on purpose: deleting a chat must never delete code. The branch stays in
    the clone either way, so the work is still reachable from the repo.
    """
    kept: List[str] = []
    for folder in coding_store.thu_muc_cua_phien(sid):
        if folder.get("nguon") != SOURCE:
            continue
        wt = coding_store.worktree_thu_muc(sid, folder["id"])
        if not wt:
            continue
        if _work_at_risk(wt):
            kept.append(wt)
            continue
        _remove_worktree(folder["duong_dan"], wt)
        coding_store.dat_worktree_thu_muc(sid, folder["id"], "")
    if not kept:
        coding_store.xoa_rang_buoc(sid)
        _forget_bases(sid)
    return {"kept": kept}


def set_checks(brain: str, full_name: str, checks: Optional[List[Dict[str, str]]]) -> Dict[str, Any]:
    """Save the repo's local check commands (None = go back to the suggested ones)."""
    rec = find(brain, full_name)
    if not rec:
        raise RepoError(_c(f"Brain này không có repo {full_name}.", f"This brain has no repo {full_name}."))
    if checks is None:
        rec.pop("checks", None)
    else:
        clean = []
        for c in checks:
            run = str((c or {}).get("run") or "").strip()
            if run:
                clean.append({"name": str((c or {}).get("name") or run.splitlines()[0])[:80], "run": run[:2000]})
        rec["checks"] = clean[:30]
    _put(rec)
    return get_checks(brain, full_name)


def get_checks(brain: str, full_name: str) -> Dict[str, Any]:
    rec = find(brain, full_name)
    if not rec:
        raise RepoError(_c(f"Brain này không có repo {full_name}.", f"This brain has no repo {full_name}."))
    import github_gate
    suggested = github_gate.suggest_checks(rec["path"]) if Path(rec["path"]).is_dir() else []
    saved = rec.get("checks")
    return {"full_name": rec["full_name"], "custom": isinstance(saved, list),
            "checks": saved if isinstance(saved, list) else suggested, "suggested": suggested}


def auto_merge_on(rec: Dict[str, Any]) -> bool:
    """Spec 11.1 (owner 2026-10-27): green CI merges on its own; a per-repo switch turns it off. Default on."""
    return rec.get("auto_merge", True) is not False


def set_auto_merge(brain: str, full_name: str, on: bool) -> Dict[str, Any]:
    rec = find(brain, full_name)
    if not rec:
        raise RepoError(_c(f"Brain này không có repo {full_name}.", f"This brain has no repo {full_name}."))
    rec["auto_merge"] = bool(on)
    _put(rec)
    return {"full_name": rec["full_name"], "auto_merge": bool(on)}
