"""GitHub inside chat, phase G3: commit, push, PR, CI tracking per commit, fix rounds, idempotency (spec sections 8-9).

    python tests/run.py github_ci      (no network: local fake GitHub and bare repos; needs git and bash)

Acceptance criteria covered here:
  8.  A new commit never inherits the green CI of the commit before it.
  9.  "No checks at all" never becomes green.
  10. Repeated events and a restart never create a second PR, a second fix round or a second notice.
  13. After 3 fix rounds the job is stuck, with the reason, in the right chat.
Plus: the red-on-base rule, one rerun for runner failures, cancelled CI, required checks, PR merged or closed by a
person, and the "no automatic turn possible" fallback.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-ghci-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from _fake_github import FakeGitHub, GOOD_TOKEN, git  # noqa: E402

fake = FakeGitHub()
os.environ["JAVIS_GITHUB_API"] = fake.url

import github_repos  # noqa: E402
import github_store  # noqa: E402
import github_work as w  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


posted, turns = [], []


async def notify(sid, text, ok):
    posted.append((sid, text, ok))


async def start_turn(sid, text):
    turns.append((sid, text))
    return True


w.configure(notify=notify, start_turn=start_turn,
            session_info=lambda sid: {"title": "Sửa lỗi đăng nhập", "engine": "anthropic-cli", "model": "opus"})
run = lambda coro: asyncio.run(coro)  # noqa: E731
BRAIN = tempfile.mkdtemp(prefix="brain-")
fake.add_repo("acme/app", files={"README.md": "app\n", "src/a.py": "a = 1\n"})
github_repos.connect(GOOD_TOKEN)
github_repos.attach("chat", BRAIN, BRAIN, ["acme/app"])
wt = Path(github_repos.session_repos("chat", BRAIN)[0]["worktree"])
github_repos.set_checks(BRAIN, "acme/app", [{"run": "true"}])
# This file is about CI per commit; merging (on by default since G4) is covered by test_github_merge.py.
github_repos.set_auto_merge(BRAIN, "acme/app", False)
S = github_store.store


def row():
    return S().get("chat", "acme/app")


# ---- aggregate (pure) ----
mk = lambda n, s, c: {"name": n, "status": s, "conclusion": c, "url": "", "job_id": 0}  # noqa: E731
check("no checks is 'none'", w.aggregate([], None) == "none")
check("one running check is 'running'", w.aggregate([mk("a", "completed", "success"), mk("b", "in_progress", "")], None) == "running")
check("a failure is 'red'", w.aggregate([mk("a", "completed", "failure"), mk("b", "completed", "success")], None) == "red")
check("criterion 9: all skipped is 'no_ci', never green", w.aggregate([mk("a", "completed", "skipped")], None) == "no_ci")
check("cancelled is not green", w.aggregate([mk("a", "completed", "cancelled")], None) == "cancelled")
check("skipped next to a success is green", w.aggregate([mk("a", "completed", "skipped"), mk("b", "completed", "success")], None) == "green")
check("a required check that has not appeared yet keeps it running",
      w.aggregate([mk("lint", "completed", "success")], ["lint", "test"]) == "running")
check("only required checks count", w.aggregate([mk("test", "completed", "success"), mk("extra", "completed", "failure")], ["test"]) == "green")

# ---- first push ----
(wt / "src/a.py").write_text("a = 2\n", encoding="utf-8")
run(w.after_turn("chat", BRAIN, "sửa giúp anh lỗi đăng nhập"))
r = row()
check("the gate passed and the branch got its final name from the chat title", r["branch"].startswith("javis/sua-loi-dang-nhap-"))
check("the commit is on GitHub", fake.branch_sha("acme/app", r["branch"]) == r["head_sha"] != "")
prs = fake.pulls["acme/app"]
check("a draft PR is opened against the default branch", len(prs) == 1 and prs[0]["draft"] and prs[0]["base"]["ref"] == "main")
check("the PR body lists the local checks and the engine", "Local checks" in prs[0]["body"] and "anthropic-cli" in prs[0]["body"])
check("state: pushed commit waits for CI, PR open", r["ci"] == "pending" and r["integ"] == "pr_open" and r["pr_number"] == 1)
check("the chat is told about the push and the PR", any("PR #1" in t and ok for _, t, ok in posted))
author = git(["log", "-1", "--format=%an <%ae>"], wt).stdout.strip()
check("the commit is authored as the connected account", author == "tester <4242+tester@users.noreply.github.com>")
n_posts = len(posted)
run(w.after_turn("chat", BRAIN, "còn gì không"))
check("a turn that changed nothing pushes nothing and says nothing", len(fake.pulls["acme/app"]) == 1 and len(posted) == n_posts)

# ---- CI: running, then green ----
sha1 = r["head_sha"]
fake.set_checks(sha1, [("test", "in_progress", None)])
run(w.tick())
check("running checks: ci running", row()["ci"] == "running")
fake.set_checks(sha1, [("test", "completed", "success")])
run(w.tick())
r = row()
check("green CI: PR ready to merge", r["ci"] == "green" and r["integ"] == "ready")
check("the draft PR is marked ready for review", ("POST", "/graphql") in fake.calls)
check("the chat hears it is ready", any("PR #1" in t and ("sẵn sàng" in t or "ready" in t) for _, t, _ in posted))

# ---- criterion 8: a new commit does not inherit green ----
(wt / "src/a.py").write_text("a = 3\n", encoding="utf-8")
run(w.after_turn("chat", BRAIN, "đổi thành 3"))
r = row()
check("the second push reuses the same PR", len(fake.pulls["acme/app"]) == 1 and r["pr_number"] == 1)
check("criterion 8: the new commit starts pending, not green", r["head_sha"] != sha1 and r["ci"] == "pending" and r["integ"] == "pr_open")
run(w.tick())
check("criterion 8: still not green while the new commit has no result", row()["ci"] in ("pending", "running") and row()["integ"] == "pr_open")
sha2 = row()["head_sha"]

# ---- someone else pushes to the branch: the recorded head follows GitHub ----
other = Path(tempfile.mkdtemp(prefix="other-"))
git(["clone", "-q", fake.repos["acme/app"]["bare"], str(other)], other.parent)
git(["config", "user.email", "o@o"], other)
git(["config", "user.name", "O"], other)
git(["checkout", "-q", r["branch"]], other)
(other / "x.txt").write_text("x\n", encoding="utf-8")
git(["add", "-A"], other)
git(["commit", "-qm", "outside"], other)
git(["push", "-q", "origin", r["branch"]], other)
fake.set_checks(sha2, [("test", "completed", "success")])
run(w.tick())
check("a commit pushed by someone else replaces the recorded one, green of the old one is ignored",
      row()["head_sha"] == fake.branch_sha("acme/app", r["branch"]) != sha2 and row()["ci"] in ("pending", "running"))
git(["pull", "-q", "origin", r["branch"]], wt)
sha3 = row()["head_sha"]

# ---- red: a fix round with the logs; duplicates do nothing ----
fake.set_checks(sha3, [("test", "completed", "failure", 501)])
fake.logs[501] = "FAILED tests/test_a.py::test_login - AssertionError\n"
run(w.tick())
check("red CI starts one fix turn in the same chat", len(turns) == 1 and turns[0][0] == "chat")
check("the fix turn carries the marker, the round and the log", turns[0][1].startswith(w.FIX_MARKER)
      and "1/3" in turns[0][1] and "test_login" in turns[0][1])
check("the fix prompt says reproduce first and never skip tests", "tái hiện" in turns[0][1] and "KHÔNG bỏ qua" in turns[0][1])
n_posts = len(posted)
run(w.tick())
run(w.tick())
check("criterion 10: repeated ticks start no second fix round and post nothing new", len(turns) == 1 and len(posted) == n_posts)
github_store._STORE = None          # a restart: a fresh store object over the same database
run(w.tick())
check("criterion 10: after a restart the same red commit starts no second fix round", len(turns) == 1)

# ---- criterion 13: three rounds, then stuck ----
for i in range(3):
    (wt / "src/a.py").write_text(f"a = {10 + i}\n", encoding="utf-8")
    run(w.after_turn("chat", BRAIN, turns[-1][1]))   # the fix turn's own message (marker): rounds keep counting
    sha = row()["head_sha"]
    fake.set_checks(sha, [("test", "completed", "failure", 600 + i)])
    run(w.tick())
r = row()
check("criterion 13: after 3 rounds the job is stuck", r["exec"] == "stuck" and "3" in r["stuck_reason"])
check("criterion 13: exactly 3 fix turns were started", len(turns) == 3)
check("criterion 13: the stuck reason lands in the same chat", posted[-1][0] == "chat" and posted[-1][2] is False
      and "3" in posted[-1][1])
run(w.after_turn("chat", BRAIN, "thử cách khác xem"))
check("a new instruction from the person resets the rounds", row()["fix_rounds"] == 0)

# ---- red on the base branch too: not this chat's failure ----
base_sha = fake.branch_sha("acme/app", "main")
fake.set_checks(base_sha, [("test", "completed", "failure")])
(wt / "src/a.py").write_text("a = 99\n", encoding="utf-8")
run(w.after_turn("chat", BRAIN, "làm lại"))
sha = row()["head_sha"]
fake.set_checks(sha, [("test", "completed", "failure", 700)])
n_turns = len(turns)
run(w.tick())
check("red on the base branch too: no fix round, stuck with the reason",
      len(turns) == n_turns and row()["exec"] == "stuck" and "main" in row()["stuck_reason"])
fake.checks.pop(base_sha, None)

# ---- runner failure: one rerun ----
(wt / "src/a.py").write_text("a = 100\n", encoding="utf-8")
run(w.after_turn("chat", BRAIN, "lại"))
sha = row()["head_sha"]
fake.set_checks(sha, [("test", "completed", "failure", 801)])
fake.logs[801] = "Error: The runner has received a shutdown signal.\n"
n_turns = len(turns)
run(w.tick())
check("a runner failure is rerun once instead of a fix round", 801 in fake.reruns and len(turns) == n_turns)
run(w.tick())
check("a second failure on the same commit is real: a fix round", len(turns) == n_turns + 1)

# ---- cancelled ----
(wt / "src/a.py").write_text("a = 101\n", encoding="utf-8")
run(w.after_turn("chat", BRAIN, "lại nữa"))
fake.set_checks(row()["head_sha"], [("test", "completed", "cancelled")])
run(w.tick())
check("cancelled CI is stuck, not green", row()["ci"] == "cancelled" and row()["exec"] == "stuck")

# ---- criterion 9: no checks at all ----
(wt / "src/a.py").write_text("a = 102\n", encoding="utf-8")
run(w.after_turn("chat", BRAIN, "tiếp"))
w.NO_CI_GRACE_S = 0
run(w.tick())
r = row()
check("criterion 9: no checks after the grace time is no_ci, never green", r["ci"] == "no_ci" and r["integ"] == "ready")
check("the chat is told Javis will not auto-merge without CI", any("CI" in t for _, t, _ in posted[-1:]))
w.NO_CI_GRACE_S = 180

# ---- required checks ----
fake.required[("acme/app", "main")] = ["test"]
(wt / "src/a.py").write_text("a = 103\n", encoding="utf-8")
run(w.after_turn("chat", BRAIN, "tiếp nữa"))
fake.set_checks(row()["head_sha"], [("test", "completed", "success"), ("optional", "completed", "failure")])
run(w.tick())
check("only required checks decide when the repo has branch protection", row()["ci"] == "green")
fake.required.pop(("acme/app", "main"))

# ---- PR merged or closed by a person ----
pr = fake.pulls["acme/app"][0]
pr.update(merged=True, state="closed", merge_commit_sha="abc123")
run(w.tick())
check("a PR merged on GitHub becomes merged here", row()["integ"] == "merged")
fake.add_repo("acme/lib")
github_repos.attach("chat2", BRAIN, BRAIN, ["acme/lib"])
wt2 = Path(github_repos.session_repos("chat2", BRAIN)[0]["worktree"])
(wt2 / "README.md").write_text("changed\n", encoding="utf-8")
github_repos.set_checks(BRAIN, "acme/lib", [])
run(w.after_turn("chat2", BRAIN, "đổi readme"))
pr2 = fake.pulls["acme/lib"][0]
pr2["state"] = "closed"
run(w.tick())
check("a PR closed without merge is stuck with the reason", S().get("chat2", "acme/lib")["exec"] == "stuck")

# ---- no automatic turn possible (after a restart) ----
w.configure(start_turn=None)
w._start_turn = None
(wt2 / "README.md").write_text("changed again\n", encoding="utf-8")
github_repos.set_checks(BRAIN, "acme/lib", [{"run": "false"}])
run(w.after_turn("chat2", BRAIN, "đổi tiếp"))
check("with no automatic turn the chat is asked to continue", S().get("chat2", "acme/lib")["exec"] == "stuck"
      and posted[-1][0] == "chat2" and posted[-1][2] is False)

# ---- busy jobs block removal ----
github_repos.set_checks(BRAIN, "acme/lib", [])
S().update("chat2", "acme/lib", ci="running", exec="done")
check("a running job blocks removal from the brain", w.busy_jobs(BRAIN, "acme/lib") != [])

# ---- icons ----
ic = github_store.icon
row_ = lambda **k: dict({"exec": "done", "ci": "green", "integ": "ready", "head_sha": "x", "post_merge": ""}, **k)  # noqa: E731
check("icon: running work shows as working with its count", ic([row_(ci="running"), row_()]) == {
    "state": "working", "running": 1, "sub": "waiting_ci", "merged_warning": False})
check("icon: all ready is ready", ic([row_()])["state"] == "ready")
check("icon: a conflict is broken even next to a ready repo", ic([row_(), row_(integ="conflict")])["state"] == "broken")
check("icon: merged with a red post-merge check stays merged with a warning",
      ic([row_(integ="merged", post_merge="red")]) == {"state": "merged", "running": 0, "sub": "", "merged_warning": True})
check("icon: no GitHub work, no icon", ic([])["state"] == "")

fake.close()
print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
