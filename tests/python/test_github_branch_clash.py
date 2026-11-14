"""GitHub inside chat: a new job never pushes onto a branch name an older job already used (owner, 14/11/2026).

    python tests/run.py github_branch_clash      (no network: local fake GitHub and bare repos; needs git and bash)

What happened (blogminhquy/javisos-blog): every request in the chat began with "[NGỮ CẢNH GIAO DIỆN: trang=workspace]",
so every job's branch was named from that line. The first job took `javis/ngu-canh-giao-dien-trang-workspace-<id>`.
A later job's rename to the same name failed, Javis fell back to `javis/<id>`, which GitHub still held from an
old squashed PR, and the push stopped with "has commits this machine lacks, Javis does not overwrite them".

Covered: the PR title and branch come from the person's own words, not the bracketed blocks; a name taken locally
or on GitHub by other history gets `-2`, `-3`...; the push then goes through without any force.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-ghbc-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from _fake_github import FakeGitHub, GOOD_TOKEN  # noqa: E402

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


# ---- the title comes from the request, not the dashboard's blocks ----
TASK = ("[NGỮ CẢNH GIAO DIỆN: trang=workspace]\n\n"
        "[File đính kèm để ĐỌC (đường dẫn):\n- /data/state/.staging/a.png\nMặc định: chỉ đọc file rồi trả lời.]\n\n"
        "📎 /data/state/.staging/b.png\n"
        "[Giờ gửi tin này: 00:34 Thứ Bảy 14/11/2026]\n"
        "thêm huy hiệu Hostinger Partner lên web\nchi tiết thêm ở dòng sau")
check("the bracketed blocks and attachment lines are skipped", w._task_title(TASK) == "thêm huy hiệu Hostinger Partner lên web")
check("a plain request keeps its first line", w._task_title("sửa lỗi đăng nhập\nthêm") == "sửa lỗi đăng nhập")
check("a request made only of blocks gives nothing (the chat title is used)", w._task_title("[NGỮ CẢNH: x]\n") == "")

posted, turns = [], []
task = {"text": TASK}


async def notify(sid, text, ok):
    posted.append((sid, text, ok))


async def start_turn(sid, text):
    turns.append((sid, text))
    return True


w.configure(notify=notify, start_turn=start_turn,
            session_info=lambda sid: {"title": "Web", "task": task["text"], "engine": "x"})
run = lambda coro: asyncio.run(coro)  # noqa: E731
BRAIN = tempfile.mkdtemp(prefix="brain-")
fake.add_repo("acme/app", files={"README.md": "app\n", "src/a.py": "a = 1\n"})
github_repos.connect(GOOD_TOKEN)
SID = "392bbabc07a943d3"
github_repos.attach(SID, BRAIN, BRAIN, ["acme/app"])
wt = Path(github_repos.session_repos(SID, BRAIN)[0]["worktree"])
github_repos.set_checks(BRAIN, "acme/app", [{"run": "true"}])
github_repos.set_auto_merge(BRAIN, "acme/app", False)
S = github_store.store
short = github_repos.session_branch(SID)
slugged = f"javis/{w._slug('thêm huy hiệu Hostinger Partner lên web')}-{short.split('/', 1)[1][:6]}"

# The state the owner hit: GitHub keeps the session branch from an old squashed PR, and the slugged name is
# already a local branch from an earlier job.
fake.add_branch("acme/app", short, "OLD.md", "old squashed job\n")
fake.add_branch("acme/app", slugged, "OLD2.md", "another old job\n")
github_repos.git(["branch", slugged], str(wt))
# ...and the first job of the chat, named from the dashboard's block before this fix, kept its branch here too.
github_repos.git(["branch", f"javis/ngu-canh-giao-dien-trang-workspace-{short.split('/', 1)[1][:6]}"], str(wt))

(wt / "src/a.py").write_text("a = 2\n", encoding="utf-8")
run(w.after_turn(SID, BRAIN, task["text"]))
r = S().get(SID, "acme/app") or {}
branch = r.get("branch") or ""
check("no 'does not overwrite' stop", not any("ghi đè" in p[1] or "overwrite" in p[1] for p in posted))
check("pushed to a fresh name built from the request", branch == slugged + "-2")
check("the old branches on GitHub are untouched", fake.branch_sha("acme/app", short) != r.get("head_sha")
      and fake.branch_sha("acme/app", slugged) != r.get("head_sha"))
check("the new branch on GitHub holds the job and a PR is open",
      fake.branch_sha("acme/app", branch) == r.get("head_sha") and r.get("integ") == "pr_open"
      and len(fake.pulls.get("acme/app") or []) == 1)
check("the PR is named from the request", (r.get("title") or "").startswith("thêm huy hiệu Hostinger Partner"))

# A later push of the same job keeps its branch (fast-forward, no renaming).
(wt / "src/a.py").write_text("a = 3\n", encoding="utf-8")
run(w.after_turn(SID, BRAIN, "đổi thành 3"))
r2 = S().get(SID, "acme/app") or {}
check("the next push of the same job stays on the same branch",
      r2.get("branch") == branch and fake.branch_sha("acme/app", branch) == r2.get("head_sha"))


# ---- a job stuck BEFORE this fix: its row already holds the clashing name (owner, 14/11/2026) ----
# The javisos-blog card kept "has commits this machine lacks" with a warning mark after the fix shipped: the branch
# is decided once and stored, so every retry and the "Push again" button pushed to the same taken name again.
SID2 = "51c0ffee07a943d3"
github_repos.attach(SID2, BRAIN, BRAIN, ["acme/app"])
wt2 = Path(github_repos.session_repos(SID2, BRAIN)[0]["worktree"])
short2 = github_repos.session_branch(SID2)
fake.add_branch("acme/app", short2, "OLD3.md", "old squashed job of chat 2\n")
(wt2 / "src/a.py").write_text("a = 20\n", encoding="utf-8")
w.commit_all(str(wt2), "huy hiệu Hostinger")
S().ensure(SID2, "acme/app", brain=BRAIN, worktree=str(wt2), base_branch="main")
S().update(SID2, "acme/app", branch=short2, exec="stuck", title="huy hiệu Hostinger",
           stuck_reason="Nhánh trên GitHub có commit mà máy này không có, Javis không ghi đè.",
           gate={"ship_failed": {"kind": "diverged", "tries": 23, "at": 0, "next_at": 0, "task": "huy hiệu Hostinger"}})
posted.clear()
try:
    run(w.retry_ship(SID2, "acme/app", by_person=True))
    raised = ""
except github_repos.RepoError as e:
    raised = str(e)
r3 = S().get(SID2, "acme/app") or {}
check("Push again on a row stuck before the fix goes through", not raised and not w.ship_failed(r3)
      and r3.get("exec") != "stuck")
check("...to a free name, never the taken one", r3.get("branch") not in ("", short2)
      and fake.branch_sha("acme/app", r3.get("branch") or "") == r3.get("head_sha") and r3.get("integ") == "pr_open")
check("...and the taken branch on GitHub is untouched", fake.branch_sha("acme/app", short2) != r3.get("head_sha"))

# Same stuck state, but the work was moved by hand to a fresh branch in the worktree (what the session did):
# the push follows the worktree's branch instead of the stored, never-pushed name.
SID3 = "7a1ce0de07a943d3"
github_repos.attach(SID3, BRAIN, BRAIN, ["acme/app"])
wt3 = Path(github_repos.session_repos(SID3, BRAIN)[0]["worktree"])
short3 = github_repos.session_branch(SID3)
fake.add_branch("acme/app", short3, "OLD4.md", "old squashed job of chat 3\n")
(wt3 / "src/a.py").write_text("a = 30\n", encoding="utf-8")
w.commit_all(str(wt3), "huy hiệu Hostinger")
github_repos.git(["branch", "-m", short3 + "-r8"], str(wt3))
S().ensure(SID3, "acme/app", brain=BRAIN, worktree=str(wt3), base_branch="main")
S().update(SID3, "acme/app", branch=short3, exec="stuck", title="huy hiệu Hostinger",
           gate={"ship_failed": {"kind": "diverged", "tries": 3, "at": 0, "next_at": 0, "task": "huy hiệu Hostinger"}})
run(w.retry_due())
r4 = S().get(SID3, "acme/app") or {}
check("the watcher's retry pushes the branch the worktree is on",
      r4.get("branch") == short3 + "-r8" and fake.branch_sha("acme/app", short3 + "-r8") == r4.get("head_sha")
      and not w.ship_failed(r4))

fake.close()
print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
