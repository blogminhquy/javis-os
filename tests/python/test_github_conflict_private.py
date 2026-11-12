"""GitHub inside chat: a PR of a PRIVATE repo that conflicts with its base can be merged by the model.

    python tests/run.py github_conflict_private      (no network: local fake GitHub over HTTP; needs git)

A conflict becomes a fix round: the chat's engine merges the base branch into the worktree and resolves it. The
engine's shell has no GitHub credential by design, and the clone is a partial one (`--filter=blob:none`), so on a
private repo it could do neither half on its own (owner, 12/11/2026):
  - `git fetch origin` stopped with "could not read Username";
  - `git merge origin/<base>` stopped with "could not fetch <sha> from promisor remote", the merge needing file
    contents that were never downloaded.

Javis now downloads the base and those contents itself, with its token, before the fix round starts. Covered:
  1. The fix round no longer asks the engine to fetch.
  2. A plain `git merge` with no token in its environment merges the CURRENT base, makes no request to GitHub, and can
     be completed after the conflict is resolved.
  3. When Javis cannot reach GitHub the fix round waits and starts on a later tick, instead of being spent on a merge
     that cannot work.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-ghc-")
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


w.configure(notify=notify, start_turn=start_turn, session_info=lambda sid: {"title": f"Job {sid}", "engine": "x"})
run = lambda coro: asyncio.run(coro)  # noqa: E731
BRAIN = tempfile.mkdtemp(prefix="brain-")
github_repos.connect(GOOD_TOKEN)
S = github_store.store
FILES = {"README.md": "x\n", "src/a.py": "a = 1\n", "docs/guide.md": "guide v1\n", "old.txt": "to be removed\n"}


def setup(chat, repo):
    """A private repo attached to a chat, with a PR open that changes src/a.py."""
    fake.add_repo(repo, files=FILES)
    fake.serve_private(repo)
    github_repos.attach(chat, BRAIN, BRAIN, [repo])
    github_repos.set_checks(BRAIN, repo, [])
    wt = Path(github_repos.session_repos(chat, BRAIN)[0]["worktree"])
    (wt / "src" / "a.py").write_text("a = 'the chat'\n", encoding="utf-8")
    run(w.after_turn(chat, BRAIN, "change a"))
    return wt, S().get(chat, repo)


def move_base(repo):
    """Other people land work on the base: the same line (a conflict), a new file, an edited one."""
    fake.push_to_default(repo, "src/a.py", "a = 'someone else'\n")
    fake.push_to_default(repo, "NEW.md", "landed after the clone\n")
    fake.push_to_default(repo, "docs/guide.md", "guide v2\n")


def engine_git(args, cwd):
    """git as the engine's shell runs it: no token. The identity is spelled out, a CI runner has none of its own."""
    return git(["-c", "user.name=Engine", "-c", "user.email=engine@test"] + args, cwd, check=False)


def conflict_tick(repo, row):
    fake.pulls[repo][0]["mergeable"] = False
    fake.set_checks(row["head_sha"], [("test", "completed", "success")])
    run(w.tick())


# ---- 1. the fix round ----
wt, row = setup("c1", "acme/secret")
check("the PR of the private repo is open", row["integ"] == "pr_open" and row["pr_number"] == 1)
move_base("acme/secret")
conflict_tick("acme/secret", row)
fix = turns[-1][1] if turns else ""
check("a conflict on a private repo starts one fix round", len(turns) == 1 and S().get("c1", "acme/secret")["integ"] == "conflict")
check("the fix round asks for the merge of the base", "git merge origin/main" in fix)
check("the fix round does not ask the engine to fetch (its shell has no token)", "git fetch" not in fix)

# ---- 2. what the engine's shell can do: `git` here carries no token ----
requests_before = len(fake.git_requests)
merge = engine_git(["merge", "origin/main"], wt)
said = merge.stdout + merge.stderr
check(f"the merge needs nothing from GitHub: {said.strip().splitlines()[-1] if said.strip() else ''}",
      "promisor" not in said and "could not read" not in said)
check("git made no request to GitHub during the merge", len(fake.git_requests) == requests_before)
check("it is the CURRENT base that is merged",
      git(["rev-parse", "--verify", "-q", "MERGE_HEAD"], wt, check=False).stdout.strip()
      == fake.branch_sha("acme/secret", "main"))
check("the merge stops on the real conflict", merge.returncode != 0 and "CONFLICT" in said
      and "<<<<<<<" in (wt / "src" / "a.py").read_text(encoding="utf-8"))
check("files only the base changed arrive with their contents",
      (wt / "NEW.md").is_file() and (wt / "NEW.md").read_text() == "landed after the clone\n"
      and (wt / "docs" / "guide.md").read_text() == "guide v2\n")
(wt / "src" / "a.py").write_text("a = 'both'\n", encoding="utf-8")
git(["add", "-A"], wt)
done = engine_git(["commit", "-q", "--no-edit"], wt)
parents = git(["rev-list", "--parents", "-n", "1", "HEAD"], wt).stdout.split()
check("the merge is completed without a token", done.returncode == 0 and len(parents) == 3
      and parents[2] == fake.branch_sha("acme/secret", "main"))
check("still no request to GitHub", len(fake.git_requests) == requests_before)

# ---- 3. GitHub out of reach: the round waits, then starts ----
wt2, row2 = setup("c2", "acme/offline")
move_base("acme/offline")
clone2 = github_repos.session_repos("c2", BRAIN)[0]["clone"]
real_url = git(["remote", "get-url", "origin"], clone2).stdout.strip()
git(["remote", "set-url", "origin", "http://127.0.0.1:9/acme__offline.git"], clone2)
n = len(turns)
conflict_tick("acme/offline", row2)
r2 = S().get("c2", "acme/offline")
check("no fix round is spent while the base cannot be downloaded", len(turns) == n)
check("the job stays on the watcher's list", any(a["sid"] == "c2" for a in S().active()))
check("the card says why", "git fetch" in (r2.get("stuck_reason") or ""))
git(["remote", "set-url", "origin", real_url], clone2)
run(w.tick())
check("the fix round starts once GitHub answers again", len(turns) == n + 1 and "git merge origin/main" in turns[-1][1]
      and S().get("c2", "acme/offline")["integ"] == "conflict")
run(w.tick())
check("and only once", len(turns) == n + 1)
merge2 = engine_git(["merge", "origin/main"], wt2)
check("that merge needs nothing from GitHub either", "CONFLICT" in merge2.stdout + merge2.stderr
      and "promisor" not in merge2.stdout + merge2.stderr)

# ---- the token still never reaches the disk or the engine's shell ----
for chat in ("c1", "c2"):
    clone = github_repos.session_repos(chat, BRAIN)[0]["clone"]
    config_text = (Path(clone) / ".git" / "config").read_text()
    check(f"{chat}: the clone's git config holds no token",
          GOOD_TOKEN not in config_text and "extraheader" not in config_text.lower())
check("every request git made carried the token", all(ok for _path, ok in fake.git_requests))

fake.close()
print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
