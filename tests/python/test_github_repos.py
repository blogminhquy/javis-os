"""GitHub inside chat, phase G1: the built-in connection, clones per brain, repos attached to a chat, removal guards.

    python tests/run.py github_repos      (no network: a local fake GitHub, bare repos as remotes; needs git)

Spec docs/dev/2026-10-github-trong-chat-spec.md, acceptance criteria covered here:
  1. Picking a repo a second time reuses the clone (no second clone).
  2. Two chats on the same repo work in two different worktrees, so they never overwrite each other's files.
  3. Removing a repo from the brain refuses while commits are not pushed, and never calls GitHub to delete anything.
  4. A folder the user added by hand is still never deleted from disk when it leaves the registry.
Plus: the token is stored encrypted and never appears in git's argv or the clone's remote URL; clones live outside the
brain tree; a pinned folder and attached repos coexist.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-gh-")
os.environ["JAVIS_STATE_DIR"] = _STATE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from _fake_github import FakeGitHub, GOOD_TOKEN, git  # noqa: E402

fake = FakeGitHub()
os.environ["JAVIS_GITHUB_API"] = fake.url

import config  # noqa: E402
import coding_store  # noqa: E402
import github_repos  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def raises(fn, *a, **kw):
    try:
        fn(*a, **kw)
    except github_repos.RepoError as e:
        return str(e)
    return ""


BRAIN = tempfile.mkdtemp(prefix="brain-")
fake.add_repo("acme/app", files={"README.md": "app\n", "src/main.py": "print('hi')\n"})
fake.add_repo("acme/lib", default_branch="trunk")

# ---- 1. Connection ----
check("not connected at first", github_repos.status()["connected"] is False)
check("a bad token is refused with a plain reason", "GitHub" in raises(github_repos.connect, "nope"))
st = github_repos.connect(GOOD_TOKEN)
check("a good token connects and shows the login", st["connected"] and st["login"] == "tester")
raw = json.loads(config.SETTINGS_PATH.read_text(encoding="utf-8"))
check("the token is not stored in clear", GOOD_TOKEN not in json.dumps(raw))
check("status never returns the token", GOOD_TOKEN not in json.dumps(github_repos.status()))
fake.scopes = "public_repo"
github_repos.disconnect()
st = github_repos.connect(GOOD_TOKEN)
check("a classic token missing scopes says which", set(st["missing"]) == {"repo", "workflow"})
fake.scopes = "repo, workflow"
github_repos.connect(GOOD_TOKEN)

# Reusing the brain-backup token
github_repos.disconnect()
config.update_settings({"backup": {"token": GOOD_TOKEN}})
check("status offers the backup token", github_repos.status()["backup_token"] is True)
st = github_repos.connect_backup()
check("the backup token can be reused after a check", st["connected"] and st["source"] == "backup")
check("the reused token is the backup one", github_repos.token() == GOOD_TOKEN)

# ---- 2. Remote list ----
items = github_repos.remote_repos("", BRAIN)
check("lists the account's repos", {x["full_name"] for x in items} == {"acme/app", "acme/lib"})
check("search filters the list", [x["full_name"] for x in github_repos.remote_repos("lib", BRAIN)] == ["acme/lib"])

# ---- 3. Clone and attach ----
view = github_repos.attach("chat-one", BRAIN, BRAIN, ["acme/app"])
repos = view["repos"]
check("attach returns the repo", len(repos) == 1 and repos[0]["full_name"] == "acme/app")
clone = Path(repos[0]["clone"])
check("the clone lives under STATE_DIR/repos, outside the brain",
      str(clone).startswith(str(Path(_STATE) / "repos")) and not str(clone).startswith(BRAIN))
remote = git(["remote", "get-url", "origin"], clone).stdout.strip()
check("origin has no token in it", GOOD_TOKEN not in remote and "x-access-token" not in remote)
check("git config of the clone has no token", GOOD_TOKEN not in (clone / ".git" / "config").read_text())
wt1 = Path(repos[0]["worktree"])
check("this chat has its own worktree", wt1.is_dir() and wt1 != clone)
check("on branch javis/<chat>", repos[0]["branch"] == "javis/chatone")
check("the engine runs in the worktree", coding_store.cwd_cua_phien("chat-one") == str(wt1))

calls_before = len([c for c in fake.calls if c[1] == "/repos/acme/app"])
clone_mtime = (clone / ".git").stat().st_mtime
view2 = github_repos.attach("chat-two", BRAIN, BRAIN, ["acme/app"])
check("criterion 1: a second pick reuses the same clone", Path(view2["repos"][0]["clone"]) == clone)
check("only one clone of the repo exists in the brain", len(github_repos.list_local(BRAIN)) == 1)
wt2 = Path(view2["repos"][0]["worktree"])
check("criterion 2: the second chat gets a different worktree", wt2.is_dir() and wt2 != wt1)
(wt1 / "src" / "main.py").write_text("print('one')\n", encoding="utf-8")
(wt2 / "src" / "main.py").write_text("print('two')\n", encoding="utf-8")
check("criterion 2: edits in one chat do not touch the other",
      (wt1 / "src/main.py").read_text() == "print('one')\n" and (wt2 / "src/main.py").read_text() == "print('two')\n")
check("the shared clone stays untouched", (clone / "src/main.py").read_text() == "print('hi')\n")

# Prompt block names the worktree and forbids pushing
block = github_repos.prompt_block("chat-one", BRAIN)
check("prompt block names the worktree", str(wt1) in block and "acme/app" in block)
check("prompt block tells the model not to push", "git push" in block)

# A pinned folder and attached repos coexist
pinned = tempfile.mkdtemp(prefix="pinned-")
rec = coding_store.them_thu_muc(pinned, brain=BRAIN)
ids = [rec["id"]] + [r["id"] for r in coding_store.thu_muc_cua_phien("chat-one")]
coding_store.dat_rang_buoc("chat-one", thu_muc_ids=ids)
check("a pinned folder stays the main one", coding_store.cwd_cua_phien("chat-one") == str(Path(pinned).resolve()))
lam = [r["lam_viec"] for r in coding_store.thu_muc_cua_phien("chat-one")]
check("the repo is reached through its worktree, not the clone", str(wt1) in lam and str(clone) not in lam)
coding_store.dat_rang_buoc("chat-one", thu_muc_ids=ids[1:])

# Two repos in one chat, other default branch
view3 = github_repos.attach("chat-one", BRAIN, BRAIN, ["acme/app", "acme/lib"])
names = [r["full_name"] for r in view3["repos"]]
check("one chat can hold two repos", names == ["acme/app", "acme/lib"])
lib = [r for r in view3["repos"] if r["full_name"] == "acme/lib"][0]
check("the second repo branches from its own default branch",
      git(["merge-base", "--is-ancestor", "origin/trunk", "HEAD"], lib["worktree"], check=False).returncode == 0)

# ---- 4. Detach and remove guards ----
err = raises(github_repos.detach, "chat-one", "acme/app", BRAIN)
check("detach refuses while this chat's worktree has unsaved edits", "acme/app" in err)
git(["checkout", "--", "src/main.py"], wt1)
out = github_repos.detach("chat-one", "acme/lib", BRAIN)
check("a clean repo detaches", out["detached"] and len(github_repos.session_repos("chat-one", BRAIN)) == 1)
check("detaching keeps the clone", Path(lib["clone"]).is_dir())

# Unpushed commit in chat-two blocks removal from the brain
git(["config", "user.email", "t@t"], wt2)
git(["config", "user.name", "T"], wt2)
git(["commit", "-qam", "work"], wt2)
calls_before = list(fake.calls)
err = raises(github_repos.remove_from_brain, BRAIN, "acme/app")
check("criterion 3: removal refuses while a commit is not pushed", "commit" in err and str(wt2) in err)
check("refused removal keeps the clone", clone.is_dir())
err2 = raises(github_repos.remove_from_brain, BRAIN, "acme/app", ["fix CI on chat-two"])
check("removal refuses while a job runs", "fix CI on chat-two" in err2)
git(["reset", "-q", "--hard", "origin/main"], wt2)
res = github_repos.remove_from_brain(BRAIN, "acme/app")
check("removal works once nothing would be lost", res["ok"] and not clone.exists())
check("worktrees of the removed repo are gone", not wt1.exists() and not wt2.exists())
check("criterion 3: GitHub was never asked to delete anything",
      not [c for c in fake.calls if c[0] == "DELETE"])
check("the bare repo on 'GitHub' still exists", Path(fake.repos["acme/app"]["bare"]).is_dir())
check("chats no longer list the removed repo", not github_repos.session_repos("chat-two", BRAIN))

# Criterion 4: a hand-added folder is never deleted from disk
mine = tempfile.mkdtemp(prefix="mine-")
r = coding_store.them_thu_muc(mine, brain=BRAIN)
coding_store.bo_thu_muc(r["id"])
check("criterion 4: a hand-added folder stays on disk after leaving the registry", Path(mine).is_dir())
check("removing a repo that is not in the brain says so", "acme/zzz" in raises(github_repos.remove_from_brain, BRAIN, "acme/zzz"))
check("a path-like repo name is refused", raises(github_repos.norm_full_name, "../../etc") != "")

# ---- 5. A deleted chat ----
v = github_repos.attach("chat-z", BRAIN, BRAIN, ["acme/lib"])
wtz = Path(v["repos"][0]["worktree"])
(wtz / "new.txt").write_text("x\n", encoding="utf-8")
out = github_repos.forget_session("chat-z")
check("deleting a chat keeps a worktree with unsaved work", out["kept"] == [str(wtz)] and wtz.is_dir())
(wtz / "new.txt").unlink()
out = github_repos.forget_session("chat-z")
check("deleting a chat removes its clean worktree", not out["kept"] and not wtz.exists())
check("the binding of the deleted chat is gone", coding_store.rang_buoc("chat-z") == {})

fake.close()
print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
