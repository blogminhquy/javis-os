"""GitHub inside chat, 0.368.0: the base branch a chat works from ("Change branch" on the repo chip).

    python tests/run.py github_branch      (no network: local fake GitHub and bare repos; needs git and bash)

Covered: the branch list puts the default branch first; a chat with nothing on its branch can move onto another base
and its worktree then starts from that branch; the PR opened afterwards targets it; unsaved edits or unmerged work
refuse the switch (no work is ever dropped); names that git could misread are refused; going back to the default
branch clears the saved pick; deleting the chat forgets it.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-ghb-")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from _fake_github import FakeGitHub, GOOD_TOKEN, git  # noqa: E402

fake = FakeGitHub()
os.environ["JAVIS_GITHUB_API"] = fake.url

import github_repos as r  # noqa: E402
import github_store  # noqa: E402
import github_work as w  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def refused(fn, *a):
    try:
        fn(*a)
    except r.RepoError as e:
        return str(e) or True
    return False


posted, turns = [], []


async def notify(sid, text, ok):
    posted.append((sid, text, ok))


async def start_turn(sid, text):
    turns.append((sid, text))
    return True


w.configure(notify=notify, start_turn=start_turn, session_info=lambda sid: {"title": "Việc", "task": "Sửa trên dev", "engine": "x"})
BRAIN = tempfile.mkdtemp(prefix="brain-")
r.connect(GOOD_TOKEN)
fake.add_repo("acme/app", files={"README.md": "x\n", "src/a.py": "a = 1\n"})
fake.add_branch("acme/app", "dev", "DEV.md")
fake.add_branch("acme/app", "release/1.0", "REL.md")

# ---- the list ----
fake.add_branch("acme/app", "javis/old-work", "OLD.md")
b = r.branches("acme/app")
check("the default branch comes first, the rest by name", b["items"] == ["main", "dev", "release/1.0"] and b["default"] == "main")
check("Javis's own working branches are not offered as a base", not any(x.startswith("javis/") for x in b["items"]))

# ---- switch a fresh chat onto dev ----
r.attach("c1", BRAIN, BRAIN, ["acme/app"])
r.set_checks(BRAIN, "acme/app", [])
repo = r.session_repos("c1", BRAIN)[0]
check("a new chat works from the default branch", repo["base_branch"] == "main")
v = r.set_base("c1", BRAIN, "acme/app", "dev")
repo = r.session_repos("c1", BRAIN)[0]
wt = Path(repo["worktree"])
check("the chat's base is now dev", repo["base_branch"] == "dev" and v["repos"][0]["base_branch"] == "dev")
check("the worktree starts from dev (its file is there)", (wt / "DEV.md").exists())
check("the chat keeps its own branch name", repo["branch"] == r.session_branch("c1"))
check("the prompt tells the engine which base it works from", "tách từ dev" in r.prompt_block("c1", BRAIN))
check("a branch with a slash works too", r.set_base("c1", BRAIN, "acme/app", "release/1.0")["repos"][0]["base_branch"] == "release/1.0"
      and (wt / "REL.md").exists() and not (wt / "DEV.md").exists())
r.set_base("c1", BRAIN, "acme/app", "dev")

# ---- refusals ----
check("a branch GitHub does not have is refused", bool(refused(r.set_base, "c1", BRAIN, "acme/app", "nope")))
for bad in ["-x", "a..b", "x.lock", "a b", "/x", "x/"]:
    check(f"a name git could misread is refused: {bad!r}", bool(refused(r.set_base, "c1", BRAIN, "acme/app", bad)))
check("a repo not attached to the chat is refused", bool(refused(r.set_base, "c9", BRAIN, "acme/app", "dev")))
(wt / "src" / "a.py").write_text("a = 2\n", encoding="utf-8")
msg = refused(r.set_base, "c1", BRAIN, "acme/app", "main")
check("unsaved edits refuse the switch and keep the edit", bool(msg) and (wt / "src" / "a.py").read_text() == "a = 2\n"
      and r.session_repos("c1", BRAIN)[0]["base_branch"] == "dev")

# ---- the PR targets the chosen base ----
asyncio.run(w.after_turn("c1", BRAIN, "sửa a.py"))
prs = fake.pulls["acme/app"]
check("the PR opened afterwards targets dev", len(prs) == 1 and prs[0]["base"]["ref"] == "dev")
check("the job row remembers dev as its base", github_store.store().get("c1", "acme/app")["base_branch"] == "dev")
msg = refused(r.set_base, "c1", BRAIN, "acme/app", "main")
check("work not merged yet (an open PR) refuses the switch", bool(msg) and "dev" in str(msg))

# ---- back to default clears the pick; deleting the chat forgets it ----
r.attach("c2", BRAIN, BRAIN, ["acme/app"])
r.set_base("c2", BRAIN, "acme/app", "dev")
check("the pick is saved for the chat", r.session_base("c2", "acme/app") == "dev")
r.set_base("c2", BRAIN, "acme/app", "main")
check("going back to the default branch clears the saved pick", r.session_base("c2", "acme/app") == ""
      and r.session_repos("c2", BRAIN)[0]["base_branch"] == "main")
r.set_base("c2", BRAIN, "acme/app", "dev")
r.forget_session("c2")
check("deleting the chat forgets its pick", r.session_base("c2", "acme/app") == "")
check("another chat's pick is untouched", r.session_base("c1", "acme/app") == "dev")

# ---- a chat that picks a base before its worktree exists gets it from that base ----
r._set_session_base("c3", "acme/app", "dev")
r.attach("c3", BRAIN, BRAIN, ["acme/app"])
wt3 = Path(r.session_repos("c3", BRAIN)[0]["worktree"])
check("a worktree created after the pick starts from that branch", (wt3 / "DEV.md").exists())

print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
