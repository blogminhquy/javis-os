"""What Javis does with a conversation's GitHub repos (spec docs/dev/2026-10-github-trong-chat-spec.md, sections 8-9).

After every saved turn (`after_turn`), for each attached repo whose worktree changed:

    gate (section 7) --red--> a fix turn in the same chat (counted, at most MAX_FIX_ROUNDS)
         |
        green --> commit --> push the branch --> open or reuse the PR (draft) --> CI pending

A background watcher (`tick`, every POLL_FAST_S / POLL_SLOW_S) then reads GitHub for every pushed commit:

    CI red    --> flaky-looking infra failure: rerun the job once; otherwise a fix turn with the failing logs.
                  Red on the base branch too: not this chat's failure, say so and stop.
    CI green  --> PR ready for review, `integ=ready` (phase G4 adds the merge)
    no checks --> after NO_CI_GRACE_S: `no_ci`, never treated as green
    too long  --> after CI_WAIT_S: stuck, with the reason

Every result is read from git and GitHub, never from what a model said (section 4.1). Every outward action is guarded
by a step key in github_store, so a repeated event or a restart never pushes, opens a PR or starts a fix round twice.
Results land in the chat that owns the repo (`notify`), and a fix round runs as the next turn of that same chat
(`start_turn`), so it works in the same worktree with the same engine.

main injects notify / start_turn / session_info through `configure`; this module never imports main.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
import threading
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import github_gate
import github_repos
import github_store
import localefmt
from github_api import GitHubError

MAX_FIX_ROUNDS = 3          # spec 9.4, owner 2026-10-27
CI_WAIT_S = 60 * 60         # spec 9.4: an hour per commit
NO_CI_GRACE_S = 180         # spec 9.3: three minutes for checks to appear
POLL_FAST_S = 30            # first ten minutes after a push
POLL_SLOW_S = 120
FAST_WINDOW_S = 600
LOG_TAIL = 6000
FIX_MARKER = "[Javis GitHub]"

Notify = Callable[[str, str, bool], Awaitable[Any]]
StartTurn = Callable[[str, str], Awaitable[bool]]
SessionInfo = Callable[[str], Dict[str, Any]]
# review(prompt, provider) -> raw text of a text-only turn on THAT provider (phase G5, spec section 10).
Review = Callable[[str, str], Awaitable[str]]
_notify: Optional[Notify] = None
_start_turn: Optional[StartTurn] = None
_session_info: Optional[SessionInfo] = None
_review: Optional[Review] = None
_reviewers: Optional[Callable[[], List[str]]] = None
_brain_root: Callable[[str], str] = lambda b: b
REVIEW_DIFF_MAX = 60000
REVIEW_TIMEOUT_S = 600
LESSONS_MAX = 30
# Provider families: a reviewer from the author's own family is not a second pair of eyes.
_FAMILY = {"anthropic-cli": "claude", "anthropic-api": "claude", "anthropic-compat": "claude",
           "openai-oauth": "openai", "openai": "openai"}

_last_gate: Dict[str, str] = {}
_running: Dict[str, bool] = {}
_lock = threading.Lock()


def _c(vi: str, en: str) -> str:
    return localefmt.chu(vi, en)


def configure(notify: Optional[Notify] = None, start_turn: Optional[StartTurn] = None,
              session_info: Optional[SessionInfo] = None, review: Optional[Review] = None,
              reviewers: Optional[Callable[[], List[str]]] = None,
              brain_root: Optional[Callable[[str], str]] = None) -> None:
    global _notify, _start_turn, _session_info, _review, _reviewers, _brain_root
    if notify is not None:
        _notify = notify
    if start_turn is not None:
        _start_turn = start_turn
    if session_info is not None:
        _session_info = session_info
    if review is not None:
        _review = review
    if reviewers is not None:
        _reviewers = reviewers
    if brain_root is not None:
        _brain_root = brain_root


def st() -> github_store.Store:
    return github_store.store()


async def _say(sid: str, text: str, ok: bool, once: str = "") -> None:
    """Post into the chat. `once` makes the message idempotent across repeats and restarts."""
    if once and not st().mark_step("notify:" + once):
        return
    if _notify is None or not text:
        return
    try:
        await _notify(sid, text, ok)
    except Exception:
        pass


# ============================================================
# Gate (phase G2)
# ============================================================
def checks_for(rec: Dict[str, Any], worktree: str) -> List[Dict[str, str]]:
    saved = rec.get("checks")
    if isinstance(saved, list):
        return [c for c in saved if isinstance(c, dict) and c.get("run")]
    return github_gate.suggest_checks(worktree)


def fingerprint(worktree: str) -> str:
    head = github_repos.git_out(["rev-parse", "HEAD"], worktree)
    status = github_repos.git_out(["status", "--porcelain", "--untracked-files=all"], worktree)
    diff = github_repos.git_out(["diff", "HEAD"], worktree)
    return hashlib.sha256(f"{head}\n{status}\n{diff}".encode("utf-8", "replace")).hexdigest()


def _base_name(repo: Dict[str, Any]) -> str:
    return repo.get("base_branch") or repo.get("default_branch") or "main"


def _base(repo: Dict[str, Any]) -> str:
    return f"origin/{_base_name(repo)}"


def _has_work(repo: Dict[str, Any]) -> bool:
    wt = repo["worktree"]
    ahead = github_repos.git_out(["rev-list", "--count", f"{_base(repo)}..HEAD"], wt) or "0"
    return ahead != "0" or github_repos.is_dirty(wt)


def _unpushed(repo: Dict[str, Any], row: Dict[str, Any]) -> bool:
    """Something here that GitHub does not have yet (uncommitted edits, or HEAD differs from the pushed commit)."""
    wt = repo["worktree"]
    if github_repos.is_dirty(wt):
        return True
    head = github_repos.git_out(["rev-parse", "HEAD"], wt)
    return head != (row.get("head_sha") or "") and _has_work(repo)


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
    with _lock:
        if _running.get(key) or (not force and _last_gate.get(key) == fp):
            return None
        _running[key] = True
    try:
        if not _has_work(repo):
            with _lock:
                _last_gate[key] = fp
            return None
        rec = github_repos.find(brain, repo["full_name"]) or {}
        report = github_gate.run_gate(wt, _base(repo), checks_for(rec, wt))
        report["full_name"] = repo["full_name"]
        with _lock:
            _last_gate[key] = fp
        return report
    finally:
        with _lock:
            _running.pop(key, None)


# ============================================================
# Commit, push, PR (section 8)
# ============================================================
def _slug(text: str) -> str:
    import unicodedata
    s = str(text or "").replace("đ", "d").replace("Đ", "D")   # NFKD does not split the Vietnamese d with stroke
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return "-".join(s.split("-")[:6])[:40].strip("-")


def _identity_env() -> Dict[str, str]:
    conn = github_repos.status()
    login = conn.get("login") or "javis"
    uid = github_repos.user_id()
    email = f"{uid}+{login}@users.noreply.github.com" if uid else f"{login}@users.noreply.github.com"
    return {"GIT_AUTHOR_NAME": login, "GIT_AUTHOR_EMAIL": email, "GIT_COMMITTER_NAME": login,
            "GIT_COMMITTER_EMAIL": email}


def commit_all(worktree: str, message: str) -> str:
    """Commit every change in the worktree (respecting .gitignore). Returns HEAD."""
    import subprocess
    import winproc
    github_repos.git(["add", "-A"], worktree)
    if github_repos.git_out(["diff", "--cached", "--name-only"], worktree):
        env = dict(github_repos.git_env(""), **_identity_env())
        p = subprocess.run(["git", "commit", "-q", "-F", "-"], cwd=worktree, input=message, text=True,
                           capture_output=True, env=env, encoding="utf-8", errors="replace",
                           creationflags=winproc.no_window())
        if p.returncode != 0:
            raise github_repos.RepoError(_c("Không commit được: ", "Commit failed: ")
                                         + ((p.stderr or p.stdout or "").strip().splitlines() or ["?"])[-1])
    return github_repos.git_out(["rev-parse", "HEAD"], worktree)


def _final_branch(sid: str, repo: Dict[str, Any], title: str) -> str:
    """`javis/<slug>-<id6>` decided at the first push (spec 6); after that the branch never changes."""
    wt = repo["worktree"]
    cur = github_repos.git_out(["rev-parse", "--abbrev-ref", "HEAD"], wt)
    short = github_repos.session_branch(sid)
    slug = _slug(title)
    if cur != short or not slug:
        return cur
    new = f"javis/{slug}-{short.split('/', 1)[1][:6]}"
    r = github_repos.git(["branch", "-m", new], wt, check=False)
    return new if r.returncode == 0 else cur


def push(repo: Dict[str, Any], branch: str) -> Tuple[str, bool]:
    """Push HEAD to origin/<branch>. Returns (sha, pushed_now). Never forces."""
    wt = repo["worktree"]
    sha = github_repos.git_out(["rev-parse", "HEAD"], wt)
    remote = github_repos.git(["ls-remote", "origin", f"refs/heads/{branch}"], wt, auth=True).stdout.split()
    if remote and remote[0] == sha:
        return sha, False
    p = github_repos.git(["push", "origin", f"HEAD:refs/heads/{branch}"], wt, auth=True, check=False, timeout=300)
    if p.returncode != 0:
        msg = github_repos._redact((p.stderr or "").strip().splitlines()[-1] if p.stderr else "?")
        if "non-fast-forward" in (p.stderr or "") or "fetch first" in (p.stderr or ""):
            raise github_repos.RepoError(_c(f"Nhánh {branch} trên GitHub có commit mà máy này không có, Javis không "
                                            f"ghi đè. ({msg})",
                                            f"Branch {branch} on GitHub has commits this machine lacks; Javis does "
                                            f"not overwrite them. ({msg})"))
        raise github_repos.RepoError(_c(f"Đẩy lên không được: {msg}", f"Push failed: {msg}"))
    github_repos.git(["branch", f"--set-upstream-to=origin/{branch}"], wt, check=False)
    return sha, True


def pr_body(info: Dict[str, Any], report: Dict[str, Any], sid: str) -> str:
    lines = ["Opened by Javis from a chat.", ""]
    if info.get("task"):
        lines += ["**Task**", "", "> " + str(info["task"])[:1500].replace("\n", "\n> "), ""]
    res = report.get("checks") or []
    if res:
        lines += ["**Local checks before push**", ""]
        for r in res:
            mark = {"pass": "passed", "fail": "FAILED", "skipped": "skipped (tool missing here, CI decides)"}[r["status"]]
            lines.append(f"- `{r['run'].splitlines()[0][:100]}`: {mark}")
        lines.append("")
    else:
        lines += ["No local check could run before push.", ""]
    if report.get("merge_block"):
        lines += ["**Needs a person before merging**", ""]
        lines += [f"- `{x['path']}`: {x['kind']}" for x in report["merge_block"][:10]]
        lines.append("")
    if report.get("too_big"):
        lines += [f"Diff: {report['diff_lines']} lines, over the {github_gate.DIFF_THRESHOLD}-line threshold.", ""]
    eng = " ".join(x for x in (info.get("engine"), info.get("model")) if x)
    if eng:
        lines.append(f"Engine: {eng}")
    lines.append(f"Javis chat: `{sid[:8]}`")
    return "\n".join(lines)


def ensure_pr(repo: Dict[str, Any], branch: str, title: str, body: str) -> Dict[str, Any]:
    gh = github_repos.client()
    fn = repo["full_name"]
    pr = gh.find_pull(fn, branch)
    if pr and pr.get("state") == "open":
        return pr
    return gh.create_pull(fn, branch, _base_name(repo), title[:120] or branch, body, draft=True)


def _session(sid: str) -> Dict[str, Any]:
    try:
        return dict((_session_info(sid) if _session_info else {}) or {})
    except Exception:
        return {}


def ship(sid: str, brain: str, repo: Dict[str, Any], report: Dict[str, Any]) -> Dict[str, Any]:
    """Gate passed: commit, push, open or reuse the PR, record the pushed commit as CI pending."""
    fn = repo["full_name"]
    info = _session(sid)
    # The job's own request names the PR; the chat title only describes the chat's FIRST job.
    task_line = (str(info.get("task") or "").strip().splitlines() or [""])[0]
    title = (task_line[:100] or (info.get("title") or "").strip() or _c("Thay đổi từ Javis", "Changes from Javis"))
    row = st().ensure(sid, fn, brain=brain, worktree=repo["worktree"], base_branch=_base_name(repo),
                      engine=str(info.get("engine") or ""), model=str(info.get("model") or ""))
    if not row.get("pr_number") or row.get("integ") == "merged":
        # A new job: its request names it, and it targets the base the chat picked now (0.368.0).
        row = st().update(sid, fn, title=title[:200], base_branch=_base_name(repo))
    else:
        title = row.get("title") or title               # the same job's later pushes keep the PR's name
    if row.get("integ") == "merged":
        # The last PR of this chat is merged: what comes now is a new job on the branch the worktree is on.
        row = st().update(sid, fn, branch="", head_sha="", pr_number=0, pr_url="", pr_node_id="", ci="none",
                          integ="no_pr", post_merge="", merged_sha="", fix_rounds=0, rerun_used=0)
    sha = commit_all(repo["worktree"], f"{title[:72]}\n\nJavis chat {sid[:8]}")
    branch = row.get("branch") or _final_branch(sid, repo, title)
    pushed_sha, pushed_now = push(repo, branch)
    pr = ensure_pr(repo, branch, title, pr_body(info, report, sid))
    fields = dict(branch=branch, head_sha=pushed_sha, exec="done", stuck_reason="",
                  pr_number=int(pr.get("number") or 0), pr_url=pr.get("html_url") or "", pr_node_id=pr.get("node_id") or "",
                  merge_block=report.get("merge_block") or [], gate={k: report.get(k) for k in
                                                                       ("diff_lines", "too_big", "skipped")},
                  integ="pr_open")
    if pushed_sha != row.get("head_sha") or row.get("ci") in ("none", ""):
        fields.update(ci="pending", pushed_at=time.time(), rerun_used=0)
    row = st().update(sid, fn, **fields)
    row["_pushed_now"] = pushed_now
    return row


# ============================================================
# Fix rounds
# ============================================================
async def request_fix(row: Dict[str, Any], why: str, details: str, key: str) -> bool:
    """Ask the chat's engine to fix something, as the next turn of that chat. Counted; stuck past the limit."""
    sid, fn = row["sid"], row["full_name"]
    if not st().mark_step("fix:" + key):
        return False
    rounds = int(row.get("fix_rounds") or 0) + 1
    if rounds > MAX_FIX_ROUNDS:
        reason = _c(f"Đã sửa {MAX_FIX_ROUNDS} vòng mà vẫn đỏ: {why}", f"Still red after {MAX_FIX_ROUNDS} fix rounds: {why}")
        # Remember which commit it got stuck on: a later green tick on that SAME commit must not clear it (the cross
        # review can exhaust the rounds on a commit whose CI is green).
        gate = dict(row.get("gate") or {})
        gate["stuck_head"] = row.get("head_sha") or ""
        st().update(sid, fn, exec="stuck", stuck_reason=reason, gate=gate)
        await _say(sid, f"**{fn}**: " + reason + _pr_tail(row), False, once=f"stuck:{key}")
        return False
    st().update(sid, fn, fix_rounds=rounds, exec="running")
    prompt = "\n".join([
        f"{FIX_MARKER} {why} (vòng sửa {rounds}/{MAX_FIX_ROUNDS}, repo {fn}"
        + (f", PR #{row['pr_number']}" if row.get("pr_number") else "") + ")",
        details,
        "",
        "Làm đúng thứ tự: 1) tái hiện ĐÚNG lỗi này ở máy, trong thư mục làm việc của repo (chạy lại đúng lệnh đã đỏ); "
        "2) tìm nguyên nhân gốc rồi sửa; 3) chạy lại đúng lệnh đó cho xanh. KHÔNG bỏ qua, xoá hay nới test, không sửa "
        "workflow CI để cho xanh. Nếu lỗi không do thay đổi của nhánh này thì nói rõ vì sao và dừng. "
        "Javis tự kiểm tra và đẩy lên sau lượt này.",
    ])
    started = False
    if _start_turn is not None:
        try:
            started = bool(await _start_turn(sid, prompt))
        except Exception:
            started = False
    if not started:
        reason = _c("Cần một lượt chat để sửa nhưng chưa mở được lượt tự động (máy chủ vừa khởi động lại?). "
                    "Nhắn \"sửa tiếp\" để Javis làm.",
                    "A fix turn is needed but could not start on its own (did the server restart?). "
                    "Send \"keep fixing\" and Javis takes it from there.")
        st().update(sid, fn, exec="stuck", stuck_reason=reason)
        await _say(sid, f"**{fn}**: {why}\n\n{details}\n\n{reason}", False, once=f"nofix:{key}")
    return started


def _pr_tail(row: Dict[str, Any]) -> str:
    return f"\n{row['pr_url']}" if row.get("pr_url") else ""


# ============================================================
# after_turn
# ============================================================
async def after_turn(sid: str, brain: str, user_message: str = "") -> List[Dict[str, Any]]:
    """Called after every saved web turn. Cheap when the chat has no GitHub repo (one registry read)."""
    try:
        repos = await asyncio.to_thread(github_repos.session_repos, sid, brain)
    except Exception:
        return []
    repos = [r for r in repos if r.get("worktree")]
    if not repos:
        return []
    # A turn the person started (not a fix round) resets the round count: it is a new instruction.
    if user_message and not str(user_message).lstrip().startswith(FIX_MARKER):
        for r in repos:
            if st().get(sid, r["full_name"]):
                st().update(sid, r["full_name"], fix_rounds=0)
    out = []
    for repo in repos:
        try:
            out.append(await _after_turn_repo(sid, brain, repo, user_message))
        except Exception as e:  # noqa: BLE001 - one repo's failure must not stop the others
            await _say(sid, f"**{repo['full_name']}**: {e}", False)
    return [x for x in out if x]


async def _after_turn_repo(sid: str, brain: str, repo: Dict[str, Any], user_message: str = "") -> Optional[Dict[str, Any]]:
    fn = repo["full_name"]
    row = st().get(sid, fn) or {}
    if not await asyncio.to_thread(_unpushed, repo, row):
        # A review round that changed nothing: the author weighed the findings and rejected them (spec 10). Its
        # reasons are in the chat; the findings no longer hold the merge.
        if row and _is_review_turn(user_message) and (row.get("gate") or {}).get("review_open"):
            gate = dict(row.get("gate") or {})
            gate["review_dismissed"] = gate.pop("review_open")
            st().update(sid, fn, gate=gate, exec="done")
            await _say(sid, _c(f"**{fn}**: tác giả bác bỏ các phát hiện của review chéo (lý do ở trên), không sửa gì.",
                               f"**{fn}**: the author rejected the cross-review findings (reasons above) and changed "
                               "nothing."), True, once=f"dismiss:{sid}:{fn}:{row.get('head_sha')}")
        return None
    st().ensure(sid, fn, brain=brain, worktree=repo["worktree"])
    st().update(sid, fn, exec="running", stuck_reason="")
    report = await asyncio.to_thread(gate_repo, sid, brain, repo)
    if report is None:
        st().update(sid, fn, exec="done" if row.get("head_sha") else "idle")
        return None
    row = st().get(sid, fn) or {}
    if not report["ok"]:
        head = await asyncio.to_thread(github_repos.git_out, ["rev-parse", "HEAD"], repo["worktree"])
        why = _c("Kiểm tra ở máy đỏ trước khi đẩy lên", "Local checks failed before push") if not report["secrets"] \
            else _c("Diff có thứ giống thông tin bí mật, chưa commit", "The diff looks like it has a secret, not committed")
        details = github_gate.summary(report) + _fail_output(report)
        await asyncio.to_thread(learn_from_gate, brain, fn, report)
        await _say(sid, f"**{fn}**\n{github_gate.summary(report)}", False)
        await request_fix(row, why, details, f"{sid}:{fn}:gate:{head}:{_fingerprint_short(repo)}")
        return report
    if not repo.get("can_push", True):
        reason = _c("Token không có quyền đẩy lên repo này.", "The token cannot push to this repo.")
        st().update(sid, fn, exec="stuck", stuck_reason=reason)
        await _say(sid, f"**{fn}**: {reason}", False)
        return report
    try:
        row = await asyncio.to_thread(ship, sid, brain, repo, report)
    except (github_repos.RepoError, GitHubError) as e:
        st().update(sid, fn, exec="stuck", stuck_reason=str(e))
        await _say(sid, f"**{fn}**: {e}", False)
        return report
    if row.get("_pushed_now"):
        msg = _c(f"Đã đẩy lên nhánh `{row['branch']}`, PR #{row['pr_number']}: {row['pr_url']}\nĐang chờ CI.",
                 f"Pushed to `{row['branch']}`, PR #{row['pr_number']}: {row['pr_url']}\nWaiting for CI.")
        summary = github_gate.summary(report)
        await _say(sid, f"**{fn}**\n{summary}\n{msg}" if summary else f"**{fn}**\n{msg}", True,
                   once=f"pushed:{sid}:{fn}:{row['head_sha']}")
    return report


def _fingerprint_short(repo: Dict[str, Any]) -> str:
    try:
        return fingerprint(repo["worktree"])[:12]
    except Exception:
        return str(time.time())


def _fail_output(report: Dict[str, Any]) -> str:
    out = []
    for r in report.get("failed") or []:
        out.append(f"\nLệnh đỏ: `{r['run']}`\n```\n{_redact(r.get('output') or '')[-LOG_TAIL:]}\n```")
    return "".join(out)


def _redact(text: str) -> str:
    try:
        import secret_redact
        return secret_redact.redact_secrets(github_repos._redact(text))
    except Exception:
        return text


# ============================================================
# CI (section 9)
# ============================================================
_BAD = {"failure", "timed_out", "action_required", "startup_failure"}
_OK = {"success", "neutral"}


def normalize_runs(runs: List[Dict[str, Any]], statuses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in runs:
        out.append({"name": r.get("name") or "", "status": r.get("status") or "",
                    "conclusion": r.get("conclusion") or "", "url": r.get("html_url") or r.get("details_url") or "",
                    "job_id": int(r.get("id") or 0) if ((r.get("app") or {}).get("slug") == "github-actions") else 0})
    for s in statuses:
        state = s.get("state") or ""
        out.append({"name": s.get("context") or "", "status": "completed" if state != "pending" else "in_progress",
                    "conclusion": {"success": "success", "failure": "failure", "error": "failure"}.get(state, ""),
                    "url": s.get("target_url") or "", "job_id": 0})
    # The same check can appear once per rerun: keep the last one per name.
    seen: Dict[str, Dict[str, Any]] = {}
    for x in out:
        seen[x["name"]] = x
    return list(seen.values())


def aggregate(items: List[Dict[str, Any]], required: Optional[List[str]]) -> str:
    """CI verdict of ONE commit: none | running | red | cancelled | no_ci | green (spec 9.2-9.3)."""
    if required:
        by = {x["name"]: x for x in items}
        items = [by.get(n) or {"name": n, "status": "queued", "conclusion": ""} for n in required]
    if not items:
        return "none"
    if any(x["status"] != "completed" for x in items):
        return "running"
    if any(x["conclusion"] in _BAD for x in items):
        return "red"
    if any(x["conclusion"] == "cancelled" for x in items):
        return "cancelled"
    if not any(x["conclusion"] in _OK for x in items):
        return "no_ci"          # everything skipped: nothing actually checked this commit
    return "green"


_INFRA = re.compile(r"(runner has received a shutdown signal|lost communication with the server|"
                    r"The operation was canceled|ECONNRESET|ETIMEDOUT|rate limit|503 Service Unavailable|"
                    r"Could not resolve host|No space left on device|exit code 143)", re.I)


def _ci_snapshot(row: Dict[str, Any]) -> Dict[str, Any]:
    """Read GitHub for a row: the PR, the checks of its CURRENT head, the base branch's checks when needed."""
    gh = github_repos.client()
    fn = row["full_name"]
    pr = gh.pull(fn, row["pr_number"]) if row.get("pr_number") else {}
    head = ((pr.get("head") or {}).get("sha")) or row["head_sha"]
    runs = gh.check_runs(fn, head)
    try:
        statuses = gh.statuses(fn, head)
    except GitHubError:
        statuses = []
    items = normalize_runs(runs, statuses)
    required = gh.required_checks(fn, row.get("base_branch") or "main")
    return {"pr": pr, "head": head, "items": items, "required": required}


def _failed_logs(row: Dict[str, Any], failed: List[Dict[str, Any]]) -> str:
    gh = github_repos.client()
    parts = []
    for f in failed[:3]:
        log = gh.job_log(row["full_name"], f["job_id"]) if f.get("job_id") else ""
        tail = _redact(log)[-LOG_TAIL:] if log else ""
        parts.append(f"Kiểm tra đỏ: {f['name']} ({f.get('url') or ''})" + (f"\n```\n{tail}\n```" if tail else ""))
    return "\n\n".join(parts)


def _base_also_red(row: Dict[str, Any], failed_names: List[str]) -> bool:
    """The same checks fail on the base branch's head: not this chat's failure (spec 9.3)."""
    try:
        gh = github_repos.client()
        base_sha = gh.branch_sha(row["full_name"], row.get("base_branch") or "main")
        if not base_sha:
            return False
        items = normalize_runs(gh.check_runs(row["full_name"], base_sha), [])
        bad = {x["name"] for x in items if x["conclusion"] in _BAD}
        return bool(failed_names) and all(n in bad for n in failed_names)
    except Exception:
        return False


async def check_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """One watcher pass over one row. Returns the updated row."""
    sid, fn = row["sid"], row["full_name"]
    if row.get("integ") == "merged":
        return await check_post_merge(row) if row.get("post_merge") == "pending" else row
    try:
        snap = await asyncio.to_thread(_ci_snapshot, row)
    except (GitHubError, github_repos.RepoError):
        return row      # GitHub unreachable or not connected: try again next tick, change nothing
    pr = snap["pr"] or {}
    # The PR itself first: merged or closed by a person outside Javis.
    if pr.get("merged"):
        return await on_merged(row, pr)
    if pr and pr.get("state") == "closed":
        reason = _c("PR đã bị đóng mà không merge.", "The PR was closed without merging.")
        st().update(sid, fn, exec="stuck", stuck_reason=reason, integ="no_pr", ci="none")
        await _say(sid, f"**{fn}**: {reason}{_pr_tail(row)}", False, once=f"closed:{sid}:{fn}:{row['pr_number']}")
        return st().get(sid, fn) or row
    if snap["head"] != row["head_sha"]:
        # A newer commit replaced the one Javis recorded: its CI result belongs to that commit only (spec 9.3).
        row = st().update(sid, fn, head_sha=snap["head"], ci="pending", pushed_at=time.time(), rerun_used=0,
                          integ="pr_open")
    st().save_checks(fn, row["head_sha"], snap["items"])
    verdict = aggregate(snap["items"], snap["required"])
    summary = [{"name": x["name"], "conclusion": x["conclusion"] or x["status"], "url": x["url"]} for x in snap["items"]]
    age = time.time() - float(row.get("pushed_at") or time.time())
    if verdict == "none":
        if age > NO_CI_GRACE_S:
            row = st().update(sid, fn, ci="no_ci", checks_summary=summary)
            await on_no_ci(row, pr)
        return st().get(sid, fn) or row
    if verdict == "running":
        if age > CI_WAIT_S:
            reason = _c("CI chạy quá 60 phút chưa xong.", "CI has run for over 60 minutes.")
            st().update(sid, fn, ci="running", exec="stuck", stuck_reason=reason, checks_summary=summary)
            await _say(sid, f"**{fn}**: {reason}{_pr_tail(row)}", False, once=f"slow:{sid}:{fn}:{row['head_sha']}")
        else:
            st().update(sid, fn, ci="running", checks_summary=summary)
        return st().get(sid, fn) or row
    if verdict == "red":
        return await on_red(st().update(sid, fn, ci="red", checks_summary=summary), snap)
    if verdict == "cancelled":
        reason = _c("CI bị huỷ (không phải xanh).", "CI was cancelled (not green).")
        st().update(sid, fn, ci="cancelled", exec="stuck", stuck_reason=reason, checks_summary=summary)
        await _say(sid, f"**{fn}**: {reason}{_pr_tail(row)}", False, once=f"cancel:{sid}:{fn}:{row['head_sha']}")
        return st().get(sid, fn) or row
    if verdict == "no_ci":
        row = st().update(sid, fn, ci="no_ci", checks_summary=summary)
        await on_no_ci(row, pr)
        return st().get(sid, fn) or row
    prev_fail = [x for x in (row.get("checks_summary") or []) if x.get("conclusion") in _BAD]
    if row.get("exec") == "stuck" and (row.get("gate") or {}).get("stuck_head") == row["head_sha"]:
        # Stuck on this very commit (fix rounds used up): green CI does not lift it; a new commit or a person does.
        st().update(sid, fn, ci="green", checks_summary=summary)
        return st().get(sid, fn) or row
    row = st().update(sid, fn, ci="green", checks_summary=summary, exec="done", stuck_reason="")
    if int(row.get("fix_rounds") or 0) > 0:
        await asyncio.to_thread(learn_from_fix, row, prev_fail)
    return await on_green(row, pr)


async def on_red(row: Dict[str, Any], snap: Dict[str, Any]) -> Dict[str, Any]:
    sid, fn = row["sid"], row["full_name"]
    failed = [x for x in snap["items"] if x["conclusion"] in _BAD]
    if snap.get("required"):
        failed = [x for x in failed if x["name"] in snap["required"]] or failed
    names = [x["name"] for x in failed]
    logs = await asyncio.to_thread(_failed_logs, row, failed)
    if await asyncio.to_thread(_base_also_red, row, names):
        reason = _c(f"CI đỏ ({', '.join(names)}) nhưng nhánh {row.get('base_branch')} cũng đỏ đúng các kiểm tra đó: "
                    "không phải lỗi của thay đổi này. Javis không sửa lan ra ngoài phạm vi.",
                    f"CI is red ({', '.join(names)}) but {row.get('base_branch')} fails the same checks: not this "
                    "change's fault. Javis does not widen the job to fix it.")
        st().update(sid, fn, exec="stuck", stuck_reason=reason)
        await _say(sid, f"**{fn}**: {reason}{_pr_tail(row)}", False, once=f"basered:{sid}:{fn}:{row['head_sha']}")
        return st().get(sid, fn) or row
    # One rerun, only for a failure that looks like the runner and not the code (spec 9.3).
    if not row.get("rerun_used") and _INFRA.search(logs or "") and any(x.get("job_id") for x in failed):
        if st().mark_step(f"rerun:{sid}:{fn}:{row['head_sha']}"):
            try:
                gh = github_repos.client()
                for x in failed:
                    if x.get("job_id"):
                        await asyncio.to_thread(gh.rerun_job, fn, x["job_id"])
                st().update(sid, fn, rerun_used=1, ci="running", pushed_at=time.time())
                await _say(sid, _c(f"**{fn}**: CI đỏ vì lỗi máy chạy CI, chạy lại một lần.",
                                   f"**{fn}**: CI failed on the runner, rerunning once."), True)
                return st().get(sid, fn) or row
            except (GitHubError, github_repos.RepoError):
                pass
    why = _c(f"CI đỏ: {', '.join(names) or '?'}", f"CI failed: {', '.join(names) or '?'}")
    await _say(sid, f"**{fn}**: {why}{_pr_tail(row)}", False, once=f"red:{sid}:{fn}:{row['head_sha']}")
    await request_fix(row, why, logs, f"{sid}:{fn}:ci:{row['head_sha']}")
    return st().get(sid, fn) or row


def _merge_blockers(row: Dict[str, Any], pr: Dict[str, Any]) -> List[str]:
    """Why Javis must not merge this PR on its own right now (spec 11.1). Empty list = it may."""
    out = []
    rec = github_repos.find(row.get("brain") or "", row["full_name"]) or {}
    if not github_repos.auto_merge_on(rec):
        out.append(_c("tự merge đang tắt cho repo này", "auto-merge is off for this repo"))
    if row.get("merge_block"):
        what = ", ".join(f"{x['path']} ({x['kind']})" for x in row["merge_block"][:5])
        out.append(_c(f"thay đổi cần người xem: {what}", f"changes a person must look at: {what}"))
    if row.get("ci") != "green":
        out.append(_c("chưa có CI xanh trên commit này", "no green CI on this commit"))
    review = (row.get("gate") or {}).get("review_open") or []
    if review:
        out.append(_c(f"review chéo còn {len(review)} phát hiện mở", f"cross review has {len(review)} open findings"))
    if pr.get("mergeable_state") == "blocked":
        out.append(_c("repo còn điều kiện chưa đạt (cần người duyệt hoặc kiểm tra bắt buộc)",
                      "the repo still requires something (a review or a required check)"))
    return out


_MERGE_LOCKS: Dict[str, asyncio.Lock] = {}


async def merge_now(row: Dict[str, Any], pr: Dict[str, Any], by_person: bool = False) -> Dict[str, Any]:
    """Merge the PR at exactly the head CI was green on. One merge at a time per repo (spec 11.1 queue)."""
    sid, fn, head = row["sid"], row["full_name"], row["head_sha"]
    lock = _MERGE_LOCKS.setdefault(fn.lower(), asyncio.Lock())
    async with lock:
        # A person pressing Merge again after a failure is a new decision; the automatic attempt happens once per head.
        key = f"merge:{fn}:{head}" + (f":person:{time.time():.0f}" if by_person else "")
        if not st().mark_step(key):
            return st().get(sid, fn) or row
        gh = github_repos.client()
        # Fresh read right before merging: the base may have moved since the tick that saw green.
        try:
            fresh = await asyncio.to_thread(gh.pull, fn, row["pr_number"])
        except GitHubError:
            fresh = pr
        if (fresh.get("head") or {}).get("sha") not in (None, "", head):
            st().update(sid, fn, head_sha=fresh["head"]["sha"], ci="pending", pushed_at=time.time(), integ="pr_open")
            return st().get(sid, fn) or row
        if fresh.get("mergeable") is False:
            return await _conflict(row)
        rec = github_repos.find(row.get("brain") or "", fn) or {}
        last_err = ""
        for method in rec.get("merge_methods") or ["squash", "merge", "rebase"]:
            try:
                res = await asyncio.to_thread(gh.merge_pull, fn, row["pr_number"], head, method)
            except GitHubError as e:
                last_err = e.message
                if e.status == 405 and "not allowed" in e.message.lower():
                    continue
                if e.status == 409:       # head moved under us: the next tick follows the new head
                    st().update(sid, fn, ci="pending", pushed_at=time.time(), integ="pr_open")
                    return st().get(sid, fn) or row
                break
            sha = (res or {}).get("sha") or ""
            row = st().update(sid, fn, integ="merged", merged_sha=sha, post_merge="pending", pushed_at=time.time(),
                              exec="done", stuck_reason="")
            _record_metric(row, "merged")
            who = _c("Đã tự merge", "Auto-merged") if not by_person else _c("Đã merge", "Merged")
            await _say(sid, _c(f"**{fn}**: {who} PR #{row['pr_number']} ({method}). Đang chờ kiểm tra trên nhánh "
                               f"{row.get('base_branch')}.{_pr_tail(row)}",
                               f"**{fn}**: {who} PR #{row['pr_number']} ({method}). Waiting for the checks on "
                               f"{row.get('base_branch')}.{_pr_tail(row)}"), True, once=f"merged:{sid}:{fn}:{row['pr_number']}")
            await asyncio.to_thread(_restart_branch, row)
            return row
        reason = _c(f"Merge không được: {last_err}", f"Merge failed: {last_err}")
        st().update(sid, fn, integ="merge_failed", stuck_reason=reason)
        await _say(sid, f"**{fn}**: {reason}{_pr_tail(row)}", False, once=f"mergefail:{sid}:{fn}:{head}")
        return st().get(sid, fn) or row


async def _conflict(row: Dict[str, Any]) -> Dict[str, Any]:
    sid, fn = row["sid"], row["full_name"]
    reason = _c("PR bị xung đột với nhánh chính, cần làm lại.", "The PR conflicts with the base branch.")
    st().update(sid, fn, integ="conflict", stuck_reason=reason)
    await _say(sid, f"**{fn}**: {reason}{_pr_tail(row)}", False, once=f"conflict:{sid}:{fn}:{row['head_sha']}")
    # A conflict is work for the chat: one fix round to merge the base branch in and resolve it.
    await request_fix(st().get(sid, fn) or row, _c("PR xung đột với nhánh chính", "The PR conflicts with the base"),
                      f"Trong thư mục làm việc của {fn}: `git fetch origin` rồi `git merge origin/{row.get('base_branch')}`, "
                      "giải quyết xung đột giữ đúng ý của cả hai bên, chạy lại test. Không rebase, không force push.",
                      f"{sid}:{fn}:conflict:{row['head_sha']}")
    return st().get(sid, fn) or row


def _restart_branch(row: Dict[str, Any]) -> None:
    """After a merge, move the chat's worktree to a fresh branch from the updated base, when nothing is left on it.

    The next job then starts clean instead of stacking on a branch whose history was squashed into the base.
    """
    wt = row.get("worktree") or ""
    try:
        if not wt or github_repos.is_dirty(wt):
            return
        if github_repos.git_out(["rev-parse", "HEAD"], wt) != row.get("head_sha"):
            return
        github_repos.git(["fetch", "origin"], wt, auth=True, timeout=300)
        base = f"origin/{row.get('base_branch') or 'main'}"
        stem = github_repos.session_branch(row["sid"])
        n = 2
        while github_repos.git(["rev-parse", "--verify", "--quiet", f"refs/heads/{stem}-r{n}"], wt,
                               check=False).returncode == 0:
            n += 1
        github_repos.git(["checkout", "-q", "-b", f"{stem}-r{n}", base], wt)
    except github_repos.RepoError:
        pass


async def on_green(row: Dict[str, Any], pr: Dict[str, Any]) -> Dict[str, Any]:
    """CI green on the current head: ready, and merged right away when nothing stands in the way (spec 11.1)."""
    sid, fn = row["sid"], row["full_name"]
    if pr.get("mergeable") is None:
        return row      # GitHub is still computing mergeability: ask again next tick
    if pr.get("mergeable") is False or pr.get("mergeable_state") == "dirty":
        return await _conflict(row)
    if pr.get("mergeable_state") == "behind" and st().mark_step(f"update:{fn}:{row['head_sha']}"):
        # Branch protection wants the branch up to date: GitHub merges the base in, CI runs again on the new head.
        try:
            await asyncio.to_thread(github_repos.client().update_branch, fn, row["pr_number"], row["head_sha"])
            st().update(sid, fn, ci="pending", pushed_at=time.time(), integ="pr_open")
            await _say(sid, _c(f"**{fn}**: nhánh cũ hơn {row.get('base_branch')}, GitHub đang cập nhật nhánh, CI chạy lại.",
                               f"**{fn}**: the branch is behind {row.get('base_branch')}; GitHub is updating it and CI "
                               "runs again."), True)
            return st().get(sid, fn) or row
        except (GitHubError, github_repos.RepoError):
            pass
    if pr.get("draft") and row.get("pr_node_id"):
        try:
            await asyncio.to_thread(github_repos.client().mark_ready, fn, row["pr_node_id"])
        except (GitHubError, github_repos.RepoError):
            pass
    row = st().update(sid, fn, integ="ready")
    row = await cross_review(row)
    if (row.get("gate") or {}).get("review_running"):
        return row
    blockers = await asyncio.to_thread(_merge_blockers, row, pr)
    if not blockers:
        return await merge_now(row, pr)
    await _say(sid, _c(f"**{fn}**: CI xanh, PR #{row['pr_number']} sẵn sàng merge. Javis chưa tự merge vì "
                       f"{'; '.join(blockers)}.{_pr_tail(row)}",
                       f"**{fn}**: CI green, PR #{row['pr_number']} is ready to merge. Javis did not merge it because "
                       f"{'; '.join(blockers)}.{_pr_tail(row)}"), True, once=f"green:{sid}:{fn}:{row['head_sha']}")
    return row


async def on_no_ci(row: Dict[str, Any], pr: Dict[str, Any]) -> Dict[str, Any]:
    """No check ran on the commit. Never green: ready to merge by hand only (spec 17, proposal)."""
    sid, fn = row["sid"], row["full_name"]
    if pr.get("mergeable") is False:
        return await on_green(row, pr)      # conflict wording and state are the same
    st().update(sid, fn, integ="ready")
    await _say(sid, _c(f"**{fn}**: repo không có CI cho commit này. Kiểm tra ở máy đã qua; PR #{row['pr_number']} "
                       f"chờ người bấm merge, Javis không tự merge khi không có CI.{_pr_tail(row)}",
                       f"**{fn}**: no CI ran on this commit. Local checks passed; PR #{row['pr_number']} waits for a "
                       f"person to merge, Javis never auto-merges without CI.{_pr_tail(row)}"), True,
               once=f"noci:{sid}:{fn}:{row['head_sha']}")
    return st().get(sid, fn) or row


async def on_merged(row: Dict[str, Any], pr: Dict[str, Any]) -> Dict[str, Any]:
    """The PR was merged on GitHub (by a person, or by Javis on an earlier tick)."""
    sid, fn = row["sid"], row["full_name"]
    if row.get("integ") == "merged":
        return row
    row = st().update(sid, fn, integ="merged", merged_sha=pr.get("merge_commit_sha") or "", exec="done",
                      post_merge="pending" if pr.get("merge_commit_sha") else "", pushed_at=time.time(), stuck_reason="")
    _record_metric(row, "merged")
    await _say(sid, _c(f"**{fn}**: PR #{row['pr_number']} đã merge.{_pr_tail(row)}",
                       f"**{fn}**: PR #{row['pr_number']} is merged.{_pr_tail(row)}"), True,
               once=f"merged:{sid}:{fn}:{row['pr_number']}")
    await asyncio.to_thread(_restart_branch, row)
    if not row.get("post_merge"):
        await maybe_next(sid)
    return row


async def check_post_merge(row: Dict[str, Any]) -> Dict[str, Any]:
    """Checks of the merge commit on the base branch (spec 11.2): what next jobs wait for."""
    sid, fn, sha = row["sid"], row["full_name"], row.get("merged_sha") or ""
    if not sha:
        row = st().update(sid, fn, post_merge="")
        await maybe_next(sid)
        return row
    try:
        gh = github_repos.client()
        runs = await asyncio.to_thread(gh.check_runs, fn, sha)
        try:
            statuses = await asyncio.to_thread(gh.statuses, fn, sha)
        except GitHubError:
            statuses = []
    except (GitHubError, github_repos.RepoError):
        return row
    verdict = aggregate(normalize_runs(runs, statuses), None)
    age = time.time() - float(row.get("pushed_at") or time.time())
    if verdict in ("none", "no_ci"):
        if age > NO_CI_GRACE_S:
            row = st().update(sid, fn, post_merge="")
            await maybe_next(sid)
        return row
    if verdict == "running":
        if age > CI_WAIT_S:
            row = st().update(sid, fn, post_merge="")
            await maybe_next(sid)
        return row
    if verdict in ("red", "cancelled"):
        row = st().update(sid, fn, post_merge="red")
        await _say(sid, _c(f"**{fn}**: đã merge, nhưng kiểm tra trên nhánh {row.get('base_branch')} sau merge bị đỏ. "
                           "Việc kế tiếp đang chờ sẽ không chạy cho tới khi nhánh xanh lại.",
                           f"**{fn}**: merged, but the checks on {row.get('base_branch')} after the merge failed. "
                           "Waiting next jobs will not start until the branch is green again."), False,
                   once=f"postred:{sid}:{fn}:{sha}")
        return row
    row = st().update(sid, fn, post_merge="green")
    await maybe_next(sid)
    return row


async def maybe_next(sid: str) -> bool:
    """Start the chat's next queued job when every repo of it is merged and settled (spec 11.2)."""
    rows = st().for_session(sid)
    if not rows or not all(r["integ"] == "merged" and r.get("post_merge") in ("", "green") for r in rows):
        return False
    job = st().queue_take(sid)
    if not job:
        return False
    prompt = (f"{FIX_MARKER} Việc kế tiếp người dùng đã giao (PR trước đã merge, kiểm tra sau merge đã qua):\n"
              f"{job['text']}\n\nLàm việc này trên nhánh mới tách từ nhánh chính mới nhất. Chỉ làm đúng việc này.")
    started = False
    if _start_turn is not None:
        try:
            started = bool(await _start_turn(sid, prompt))
        except Exception:
            started = False
    if not started:
        await _say(sid, _c(f"Việc kế tiếp đã tới lượt nhưng chưa tự mở được lượt chat: {job['text']}\n"
                           "Nhắn \"làm tiếp\" để Javis bắt đầu.",
                           f"The next job is due but no automatic turn could start: {job['text']}\n"
                           "Send \"go on\" and Javis starts it."), False, once=f"next:{job['id']}")
    return started


def _record_metric(row: Dict[str, Any], outcome: str) -> None:
    try:
        st().add_metric(sid=row["sid"], full_name=row["full_name"], engine=row.get("engine") or "",
                        model=row.get("model") or "", first_push_green=int(row.get("fix_rounds") or 0) == 0,
                        fix_rounds=int(row.get("fix_rounds") or 0),
                        review_findings=int((row.get("gate") or {}).get("review_found") or 0),
                        seconds=time.time() - float(row.get("created_at") or time.time()), outcome=outcome)
    except Exception:
        pass


# ============================================================
# Cross review (phase G5, spec section 10)
# ============================================================
REVIEW_PROMPT = """Bạn là người review code độc lập cho PR "{title}" trên repo {repo}. Một engine khác đã viết thay đổi này.

Yêu cầu mới nhất của người dùng cho việc này (đánh giá thay đổi theo đúng yêu cầu này, không theo việc cũ):
{task}

Chỉ nêu LỖI có đường gây hỏng CỤ THỂ: với đầu vào hay tình huống nào thì ra kết quả sai, chương trình hỏng, mất dữ liệu,
hay một lỗ hổng bảo mật. KHÔNG nêu đặt tên, phong cách, khẩu vị, gợi ý cải tiến, hay thứ có từ trước thay đổi này.
Không chắc thì không nêu. Không có lỗi thì trả danh sách rỗng.

Trả về DUY NHẤT một JSON, không lời dẫn:
{{"findings": [{{"file": "đường/dẫn", "line": 12, "problem": "lỗi gì", "scenario": "đầu vào nào thì hỏng ra sao"}}]}}

Diff:
```diff
{diff}
```"""


def _family(provider: str) -> str:
    return _FAMILY.get(provider or "", provider or "")


def pick_reviewer(author_provider: str) -> str:
    """The first available engine of ANOTHER family than the author's, "" when there is none (spec 10)."""
    try:
        avail = list(_reviewers() if _reviewers else [])
    except Exception:
        avail = []
    fam = _family(author_provider)
    for p in avail:
        if _family(p) != fam:
            return p
    return ""


def parse_findings(raw: str) -> Optional[List[Dict[str, Any]]]:
    """Findings from a reviewer's answer. None = not readable (counts as no review)."""
    import json
    text = str(raw or "")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return None
    out = []
    for f in (d.get("findings") if isinstance(d, dict) else None) or []:
        if isinstance(f, dict) and str(f.get("problem") or "").strip():
            out.append({"file": str(f.get("file") or "")[:200], "line": int(f.get("line") or 0) if str(f.get("line") or "0").isdigit() else 0,
                        "problem": str(f.get("problem"))[:500], "scenario": str(f.get("scenario") or "")[:500]})
    return out[:10]


def _review_diff(row: Dict[str, Any]) -> str:
    wt = row.get("worktree") or ""
    base = f"origin/{row.get('base_branch') or 'main'}"
    diff = github_repos.git_out(["diff", "--no-color", f"{base}...HEAD"], wt)
    return diff[:REVIEW_DIFF_MAX] + ("\n[... diff cắt bớt ...]" if len(diff) > REVIEW_DIFF_MAX else "")


async def cross_review(row: Dict[str, Any]) -> Dict[str, Any]:
    """Review the head commit once with another engine. Findings go back to the author as a fix round."""
    sid, fn, head = row["sid"], row["full_name"], row["head_sha"]
    gate = dict(row.get("gate") or {})
    if gate.get("reviewed_sha") == head:
        return row
    reviewer = pick_reviewer(row.get("engine") or "")
    if not reviewer or _review is None:
        gate["reviewed_sha"] = head
        gate["review_skipped"] = True
        row = st().update(sid, fn, gate=gate)
        if row.get("pr_number") and st().mark_step(f"noreview:{fn}:{row['pr_number']}"):
            try:
                await asyncio.to_thread(github_repos.client().comment, fn, row["pr_number"],
                                        "Not cross-reviewed: only one engine family is connected to Javis.")
            except Exception:
                pass
        return row
    if not st().mark_step(f"review:{fn}:{head}"):
        return row
    gate["review_running"] = True
    st().update(sid, fn, gate=gate)
    findings: Optional[List[Dict[str, Any]]] = None
    try:
        diff = await asyncio.to_thread(_review_diff, row)
        task = str(_session(sid).get("task") or row.get("title") or "")[:2000]
        prompt = REVIEW_PROMPT.format(title=row.get("title") or "", repo=fn, diff=diff, task=task)
        raw = await asyncio.wait_for(_review(prompt, reviewer), timeout=REVIEW_TIMEOUT_S)
        findings = parse_findings(raw)
    except Exception as e:  # noqa: BLE001 - a broken reviewer must not hold the PR forever
        print(f"[github review] {fn}: {type(e).__name__}: {e}")
    gate = dict((st().get(sid, fn) or row).get("gate") or {})
    gate.pop("review_running", None)
    gate["reviewed_sha"] = head
    gate["reviewer"] = reviewer
    if findings is None:
        gate["review_skipped"] = True
        row = st().update(sid, fn, gate=gate)
        await _say(sid, _c(f"**{fn}**: review chéo bằng {reviewer} không chạy được, bỏ qua lần này.",
                           f"**{fn}**: cross review with {reviewer} did not run; skipped this time."), True,
                   once=f"reviewfail:{fn}:{head}")
        return row
    if not findings:
        gate["review_open"] = []
        return st().update(sid, fn, gate=gate)
    gate["review_open"] = findings
    gate["review_found"] = int(gate.get("review_found") or 0) + len(findings)
    row = st().update(sid, fn, gate=gate, integ="pr_open")
    lines = [f"- `{f['file']}:{f['line']}` {f['problem']}" + (f" (khi: {f['scenario']})" if f["scenario"] else "")
             for f in findings]
    await _say(sid, _c(f"**{fn}**: review chéo ({reviewer}) có {len(findings)} phát hiện.",
                       f"**{fn}**: cross review ({reviewer}) found {len(findings)} issue(s).") + "\n" + "\n".join(lines),
               False, once=f"reviewsay:{fn}:{head}")
    await request_fix(row, f"Review chéo ({reviewer}) có {len(findings)} phát hiện",
                      "\n".join(lines) + "\n\nKiểm chứng TỪNG phát hiện bằng cách lần theo đúng đường gây hỏng. Đúng thì "
                      "sửa (kèm test tái hiện). Sai thì nói rõ vì sao bác bỏ, không sửa gì cho phát hiện đó.",
                      f"{sid}:{fn}:review:{head}")
    return st().get(sid, fn) or row


def _is_review_turn(user_message: str) -> bool:
    s = str(user_message or "").lstrip()
    return s.startswith(f"{FIX_MARKER} Review chéo")


# ============================================================
# Lessons per repo (phase G5, spec 13.1)
# ============================================================
def lessons_path(brain: str, full_name: str):
    from pathlib import Path
    root = Path(_brain_root(brain) or brain or ".")
    return root / "Javis" / "learned" / "repos" / (full_name.replace("/", "__") + ".md")


def read_lessons(brain: str, full_name: str) -> List[str]:
    p = lessons_path(brain, full_name)
    try:
        return [ln[2:].strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.startswith("- ")]
    except OSError:
        return []


def add_lesson(brain: str, full_name: str, lesson: str) -> bool:
    """One line per lesson, deduplicated, at most LESSONS_MAX (oldest go first). Stored in the brain, never the repo."""
    lesson = " ".join(str(lesson or "").split())[:300]
    if not lesson:
        return False
    cur = read_lessons(brain, full_name)
    if any(lesson.lower() == x.lower() for x in cur):
        return False
    cur = (cur + [lesson])[-LESSONS_MAX:]
    p = lessons_path(brain, full_name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"# Bài học của repo {full_name}\n\nJavis tự ghi khi một lỗi thật vừa được sửa. Mỗi dòng một bài học.\n\n"
                 + "\n".join(f"- {x}" for x in cur) + "\n", encoding="utf-8")
    return True


def learn_from_fix(row: Dict[str, Any], failed_before: List[Dict[str, Any]]) -> None:
    """CI went green after fix rounds: write down which checks broke, so the next turn runs them first."""
    brain, fn = row.get("brain") or "", row["full_name"]
    for f in failed_before[:3]:
        add_lesson(brain, fn, f"Kiểm tra CI `{f.get('name')}` từng đỏ ở repo này: chạy lệnh tương ứng ở máy và "
                              "cho xanh trước khi kết thúc lượt.")


def learn_from_gate(brain: str, full_name: str, report: Dict[str, Any]) -> None:
    for r in (report.get("failed") or [])[:2]:
        add_lesson(brain, full_name, f"Lệnh `{r['run'].splitlines()[0][:120]}` từng đỏ ở máy: chạy nó trước khi "
                                     "kết thúc lượt.")


# ============================================================
# Metrics (phase G5, spec 13.2)
# ============================================================
def metrics_summary(full_name: str = "") -> List[Dict[str, Any]]:
    """Per engine/model: jobs merged, share green on the first push, average fix rounds, review findings."""
    agg: Dict[str, Dict[str, Any]] = {}
    for m in st().metrics(full_name):
        k = f"{m['engine']}|{m['model']}"
        a = agg.setdefault(k, {"engine": m["engine"], "model": m["model"], "jobs": 0, "first_green": 0,
                               "rounds": 0, "findings": 0, "seconds": 0.0})
        a["jobs"] += 1
        a["first_green"] += int(m["first_push_green"])
        a["rounds"] += int(m["fix_rounds"])
        a["findings"] += int(m["review_findings"])
        a["seconds"] += float(m["seconds"])
    out = []
    for a in agg.values():
        n = max(1, a["jobs"])
        out.append({"engine": a["engine"], "model": a["model"], "jobs": a["jobs"],
                    "first_push_green_pct": round(100.0 * a["first_green"] / n),
                    "avg_fix_rounds": round(a["rounds"] / n, 2), "review_findings": a["findings"],
                    "avg_minutes": round(a["seconds"] / n / 60, 1)})
    return sorted(out, key=lambda x: -x["jobs"])


# ============================================================
# Watcher
# ============================================================
async def tick() -> int:
    """One pass over every row that waits on GitHub. Returns how many were looked at."""
    rows = await asyncio.to_thread(st().active)
    for row in rows:
        try:
            await check_row(row)
        except Exception as e:  # noqa: BLE001 - one row must not stop the watcher
            print(f"[github watcher] {row.get('full_name')}: {type(e).__name__}: {e}")
    return len(rows)


def reconcile_on_start() -> None:
    """A restart in the middle of a gate leaves `exec=running`: put it back so the next turn or tick decides."""
    for row in st().active():
        if row["exec"] == "running" and row["ci"] not in ("pending", "running"):
            st().update(row["sid"], row["full_name"], exec="done" if row["head_sha"] else "idle")


async def run_watcher() -> None:
    try:
        await asyncio.to_thread(reconcile_on_start)
    except Exception:
        pass
    while True:
        delay = POLL_SLOW_S
        try:
            rows = await asyncio.to_thread(st().active)
            if rows:
                await tick()
                now = time.time()
                if any(now - float(r.get("pushed_at") or 0) < FAST_WINDOW_S for r in rows):
                    delay = POLL_FAST_S
        except Exception as e:  # noqa: BLE001
            print(f"[github watcher] {type(e).__name__}: {e}")
        await asyncio.sleep(delay)


# ============================================================
# Views
# ============================================================
def session_state(sid: str) -> Dict[str, Any]:
    rows = st().for_session(sid)
    return {"icon": github_store.icon(rows), "repos": [_row_view(r) for r in rows],
            "queue": [{"id": q["id"], "text": q["text"]} for q in st().queue_list(sid)]}


def queue_next(sid: str, text: str) -> Dict[str, Any]:
    text = str(text or "").strip()
    if not text:
        raise ValueError(_c("Chưa có nội dung việc kế tiếp.", "The next job has no text."))
    if not st().for_session(sid) and not github_repos.session_repos(sid):
        raise ValueError(_c("Cuộc trò chuyện này chưa gắn repo GitHub nào.", "This chat has no GitHub repo attached."))
    qid = st().queue_add(sid, text[:4000])
    return {"id": qid, "queue": [{"id": q["id"], "text": q["text"]} for q in st().queue_list(sid)]}


def cancel_next(sid: str, qid: int) -> Dict[str, Any]:
    return {"cancelled": st().queue_cancel(sid, qid),
            "queue": [{"id": q["id"], "text": q["text"]} for q in st().queue_list(sid)]}


async def merge_by_person(sid: str, full_name: str) -> Dict[str, Any]:
    row = st().get(sid, full_name)
    if not row or not row.get("pr_number"):
        raise github_repos.RepoError(_c("Cuộc này chưa có PR cho repo đó.", "This chat has no PR for that repo."))
    if row.get("integ") == "merged":
        return {"row": _row_view(row)}
    if row.get("ci") not in ("green", "no_ci"):
        raise github_repos.RepoError(_c("CI chưa xanh trên commit hiện tại.", "CI is not green on the current commit."))
    pr = await asyncio.to_thread(github_repos.client().pull, full_name, row["pr_number"])
    if pr.get("merged"):
        return {"row": _row_view(await on_merged(row, pr))}
    return {"row": _row_view(await merge_now(row, pr, by_person=True))}


def _row_view(r: Dict[str, Any]) -> Dict[str, Any]:
    keep = ("full_name", "branch", "head_sha", "pr_number", "pr_url", "exec", "ci", "integ", "post_merge",
            "stuck_reason", "fix_rounds", "merge_block", "checks_summary", "gate", "updated_at")
    return {k: r.get(k) for k in keep}


def busy_jobs(brain: str, full_name: str) -> List[str]:
    """Chats still working on a repo (removal from the brain refuses while any is listed)."""
    out = []
    for r in st().for_repo(brain, full_name):
        if r["exec"] == "running" or r["ci"] in ("pending", "running"):
            out.append(f"{r.get('title') or r['sid'][:8]}")
    return out
