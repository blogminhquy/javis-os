"""GitHub inside chat: what happens after a turn (github_work.after_turn).

    python tests/run.py github_work      (no network: local fake GitHub and bare repos; needs git and bash)

Phase G2: a turn that changed an attached repo runs the quality gate and posts the result into that chat; a turn that
changed nothing runs nothing; a failing check is reported as a failure; a chat without repos costs nothing.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-ghw-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from _fake_github import FakeGitHub, GOOD_TOKEN  # noqa: E402

fake = FakeGitHub()
os.environ["JAVIS_GITHUB_API"] = fake.url

import github_repos  # noqa: E402
import github_work  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


posted = []


async def notify(sid, text, ok):
    posted.append((sid, text, ok))


github_work.configure(notify=notify)
BRAIN = tempfile.mkdtemp(prefix="brain-")
fake.add_repo("acme/app", files={"README.md": "app\n", "src/a.py": "a = 1\n", "check.sh": "grep -q 'a = 2' src/a.py\n"})
github_repos.connect(GOOD_TOKEN)
view = github_repos.attach("chat", BRAIN, BRAIN, ["acme/app"])
wt = Path(view["repos"][0]["worktree"])
github_repos.set_checks(BRAIN, "acme/app", [{"run": "bash check.sh"}])

run = lambda: asyncio.run(github_work.after_turn("chat", BRAIN))  # noqa: E731

check("a turn that changed nothing runs no gate", run() == [] and posted == [])
(wt / "src/a.py").write_text("a = 3\n", encoding="utf-8")
reps = run()
check("a changed repo is gated after the turn", len(reps) == 1 and reps[0]["full_name"] == "acme/app")
check("criterion 5: the failing check is reported as a failure", reps[0]["ok"] is False and posted[-1][2] is False)
check("the chat message names the repo and the failing command",
      posted[-1][0] == "chat" and "acme/app" in posted[-1][1] and "bash check.sh" in posted[-1][1])
n = len(posted)
check("the same state is not gated twice", run() == [] and len(posted) == n)
(wt / "src/a.py").write_text("a = 2\n", encoding="utf-8")
reps = run()
check("after the fix the gate passes", reps and reps[0]["ok"] is True and posted[-1][2] is True)
check("a chat without repos does nothing", asyncio.run(github_work.after_turn("other-chat", BRAIN)) == [])
check("saved checks are used instead of suggestions", github_repos.get_checks(BRAIN, "acme/app")["custom"] is True)
github_repos.set_checks(BRAIN, "acme/app", None)
check("reset goes back to the suggested checks", github_repos.get_checks(BRAIN, "acme/app")["custom"] is False)
block = github_repos.prompt_block("chat", BRAIN)
check("the prompt asks for a reproducing test and forbids skipping tests", "TÁI HIỆN" in block and "KHÔNG bỏ qua" in block)
(wt / "AGENTS.md").write_text("Always run make lint.\n", encoding="utf-8")
block = github_repos.prompt_block("chat", BRAIN)
check("spec 7.1: the repo's AGENTS.md reaches the prompt of every engine", "Always run make lint." in block)

fake.close()
print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
