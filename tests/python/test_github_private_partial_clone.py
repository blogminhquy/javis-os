"""GitHub inside chat: a PRIVATE repo keeps working after its base branch moves.

    python tests/run.py github_private_partial_clone      (no network: local fake GitHub over HTTP; needs git)

Javis clones with `--filter=blob:none`, so the clone holds the file contents of what was checked out at clone time and
nothing newer: a later `git fetch` brings commits and trees only. The first checkout that needs a newer file makes git
fetch that content by itself, from origin, in the middle of the command. On a private repo that hidden fetch needs
the token like any other; without it, attaching the repo to a new chat failed with "could not read Username"
(owner, 12/11/2026).

The other GitHub tests use `file://` remotes, which ignore the filter and never ask for a token, so they could not see
this. Here the remote is served over HTTP and refuses every request that does not carry the token.

Covered, each one a checkout Javis runs itself:
  1. Attaching to a new chat after a commit landed on the default branch.
  2. Moving a chat onto another base branch ("Change branch").
  3. Restarting the chat's branch from the updated base after a merge.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-ghp-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from _fake_github import FakeGitHub, GOOD_TOKEN, git  # noqa: E402

fake = FakeGitHub()
os.environ["JAVIS_GITHUB_API"] = fake.url

import github_repos as r  # noqa: E402
import github_work as w  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def attempt(fn, *a):
    """"" when the call went through, the refusal text otherwise."""
    try:
        fn(*a)
    except r.RepoError as e:
        return str(e) or "failed"
    return ""


def missing_blobs(clone):
    out = git(["rev-list", "--objects", "--all", "--missing=print"], clone).stdout
    return [line for line in out.splitlines() if line.startswith("?")]


BRAIN = tempfile.mkdtemp(prefix="brain-")
r.connect(GOOD_TOKEN)
fake.add_repo("acme/secret", files={"README.md": "x\n", "src/a.py": "a = 1\n"})
fake.add_branch("acme/secret", "dev", "DEV.md", "only on dev\n")
url = fake.serve_private("acme/secret")

# ---- the setup really behaves like a private repo on github.com ----
anon = git(["ls-remote", url], BRAIN, check=False)
check("the remote refuses a caller without the token", anon.returncode != 0)

r.attach("c1", BRAIN, BRAIN, ["acme/secret"])
repo = r.session_repos("c1", BRAIN)[0]
clone = repo["clone"]
check("the first chat gets its worktree", (Path(repo["worktree"]) / "src" / "a.py").read_text() == "a = 1\n")
check("the clone is a partial one (dev's file was left on GitHub)", len(missing_blobs(clone)) == 1)
check("the clone's remote URL carries no token", GOOD_TOKEN not in git(["remote", "get-url", "origin"], clone).stdout)

# ---- 1. a commit lands on main, then a second chat attaches the same repo ----
fake.push_to_default("acme/secret", "NEW.md", "landed after the clone\n")
err = attempt(r.attach, "c2", BRAIN, BRAIN, ["acme/secret"])
check(f"attaching to a new chat works after the base moved{': ' + err if err else ''}", not err)
repos2 = r.session_repos("c2", BRAIN)
wt2 = Path(repos2[0]["worktree"]) if repos2 and repos2[0].get("worktree") else None
check("the new chat's worktree has the file that landed later",
      bool(wt2) and (wt2 / "NEW.md").is_file() and (wt2 / "NEW.md").read_text() == "landed after the clone\n")

# ---- 2. "Change branch": the other branch's files were never downloaded ----
err = attempt(r.set_base, "c1", BRAIN, "acme/secret", "dev")
check(f"a chat can move onto another base branch{': ' + err if err else ''}", not err)
wt1 = Path(repo["worktree"])
check("the worktree then holds that branch's file", (wt1 / "DEV.md").is_file())

# ---- 3. after a merge the chat's branch restarts from the updated base ----
fake.push_to_default("acme/secret", "MERGED.md", "the merged work\n")
if wt2:
    head = git(["rev-parse", "HEAD"], wt2).stdout.strip()
    w._restart_branch({"sid": "c2", "full_name": "acme/secret", "worktree": str(wt2), "head_sha": head,
                       "base_branch": "main"})
    check("the branch restarts from the updated base",
          git(["rev-parse", "--abbrev-ref", "HEAD"], wt2).stdout.strip() == r.session_branch("c2") + "-r2")
    check("and the worktree has the merged file", (wt2 / "MERGED.md").is_file())
else:
    check("the branch restarts from the updated base", False)

# ---- the token still never reaches the disk or the model's shell ----
config_text = (Path(clone) / ".git" / "config").read_text()
check("the clone's git config holds no token", GOOD_TOKEN not in config_text and "extraheader" not in config_text.lower())
check("every request git made carried the token", all(ok for _path, ok in fake.git_requests[1:]))

fake.close()
print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
