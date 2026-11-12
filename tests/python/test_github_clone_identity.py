"""GitHub inside chat: the chat's engine can run git in the worktree on a machine that has no git identity.

    python tests/run.py github_clone_identity      (no network: local fake GitHub and bare repos; needs git)

Javis names itself through the environment of its own commits, so its clones never held `user.name`. The engine runs
git in the worktree too: a conflict fix round asks it for `git merge origin/<base>`. There git falls back on the
machine, and a container or a fresh server has no identity to offer: the merge stopped with "empty ident name" or
"unable to auto-detect email address" before doing anything (found on a CI runner, 12/11/2026).

A clone now gets an identity of its own, the one Javis commits with, when it has none. Covered:
  1. A repo attached to a chat: plain git in the worktree knows who commits.
  2. A conflict fix round: the merge starts, stops on the real conflict, and is completed, as the same author as
     Javis's own commits.
  3. A worktree made before this change gets the identity when the conflict fix round is prepared.
  4. An identity the clone already holds is kept.

This file makes the machine identity-free for itself (no global config, no auto-detection), so it tests the same
thing on a developer's laptop and on CI.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-ghi-")
# A machine with no git identity: no global or system config, and git may not guess one from the login name.
for name in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "EMAIL"):
    os.environ.pop(name, None)
os.environ.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_COUNT="1",
                  GIT_CONFIG_KEY_0="user.useConfigOnly", GIT_CONFIG_VALUE_0="true")
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


turns = []


async def notify(sid, text, ok):
    pass


async def start_turn(sid, text):
    turns.append((sid, text))
    return True


w.configure(notify=notify, start_turn=start_turn, session_info=lambda sid: {"title": f"Job {sid}", "engine": "x"})
run = lambda coro: asyncio.run(coro)  # noqa: E731
BRAIN = tempfile.mkdtemp(prefix="brain-")
github_repos.connect(GOOD_TOKEN)
S = github_store.store
WHO = github_repos.identity()


def committer(cwd):
    """The committer plain git names in `cwd`, as the engine's shell would get it: "" when git has none."""
    p = git(["var", "GIT_COMMITTER_IDENT"], cwd, check=False)
    return p.stdout.strip() if p.returncode == 0 else ""


def setup(chat, repo):
    fake.add_repo(repo, files={"README.md": "x\n", "src/a.py": "a = 1\n"})
    github_repos.attach(chat, BRAIN, BRAIN, [repo])
    github_repos.set_checks(BRAIN, repo, [])
    return Path(github_repos.session_repos(chat, BRAIN)[0]["worktree"])


def conflicting_pr(chat, repo, wt):
    """The chat changes a line, someone else changes the same line on the base, and the PR is reported unmergeable."""
    (wt / "src" / "a.py").write_text("a = 'the chat'\n", encoding="utf-8")
    run(w.after_turn(chat, BRAIN, "change a"))
    row = S().get(chat, repo)
    fake.push_to_default(repo, "src/a.py", "a = 'someone else'\n")
    fake.pulls[repo][0]["mergeable"] = False
    fake.set_checks(row["head_sha"], [("test", "completed", "success")])
    return row


check("the test machine itself has no git identity", committer(BRAIN) == "")
check("Javis commits as the connected account, with its noreply address",
      WHO == {"name": "tester", "email": "4242+tester@users.noreply.github.com"})

# ---- 1. a repo attached to a chat ----
wt = setup("c1", "acme/app")
check("plain git in the worktree knows who commits", f"{WHO['name']} <{WHO['email']}>" in committer(wt))

# ---- 2. the conflict fix round ----
row = conflicting_pr("c1", "acme/app", wt)
run(w.tick())
check("the conflict starts a fix round", len(turns) == 1 and "git merge origin/main" in turns[0][1])
merge = git(["merge", "origin/main"], wt, check=False)
said = merge.stdout + merge.stderr
check(f"the engine's merge starts and stops on the real conflict: {said.strip().splitlines()[-1] if said.strip() else ''}",
      merge.returncode != 0 and "CONFLICT" in said and "ident" not in said and "email" not in said)
(wt / "src" / "a.py").write_text("a = 'both'\n", encoding="utf-8")
git(["add", "-A"], wt)
done = git(["commit", "-q", "--no-edit"], wt, check=False)
authors = git(["log", "-2", "--first-parent", "--format=%an <%ae>|%cn <%ce>"], wt).stdout.split("\n")
check("the merge is completed with no identity given on the command line", done.returncode == 0
      and len(git(["rev-list", "--parents", "-n", "1", "HEAD"], wt).stdout.split()) == 3)
check("the engine's commit and Javis's own commit carry the same author and committer",
      len(authors) >= 2 and authors[0] == authors[1] == f"{WHO['name']} <{WHO['email']}>|{WHO['name']} <{WHO['email']}>")

# ---- 3. a worktree made before clones had an identity ----
wt2 = setup("c2", "acme/old")
clone2 = github_repos.session_repos("c2", BRAIN)[0]["clone"]
git(["config", "--local", "--unset-all", "user.name"], clone2, check=False)
git(["config", "--local", "--unset-all", "user.email"], clone2, check=False)
check("such a worktree has no committer", committer(wt2) == "")
conflicting_pr("c2", "acme/old", wt2)
run(w.tick())
check("preparing the conflict fix round gives it one", f"<{WHO['email']}>" in committer(wt2) and len(turns) == 2)
merge2 = git(["merge", "origin/main"], wt2, check=False)
check("and the engine's merge reaches the conflict", "CONFLICT" in merge2.stdout + merge2.stderr)

# ---- 4. an identity the clone already holds is kept ----
wt3 = setup("c3", "acme/own")
clone3 = github_repos.session_repos("c3", BRAIN)[0]["clone"]
git(["config", "--local", "user.name", "Someone Else"], clone3)
git(["config", "--local", "user.email", "someone@example.test"], clone3)
github_repos.ensure_identity(str(wt3))
github_repos.attach("c3", BRAIN, BRAIN, ["acme/own"])
check("a name and an address set in the clone are left alone", "Someone Else <someone@example.test>" in committer(wt3))
config_text = (Path(clone3) / ".git" / "config").read_text()
check("the clone's git config still holds no token", GOOD_TOKEN not in config_text)

fake.close()
print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
