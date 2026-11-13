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

fake.close()
print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
