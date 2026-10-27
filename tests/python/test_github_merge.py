"""GitHub inside chat, phase G4: merge policy, merge queue, post-merge checks, next jobs, the javis_github tool.

    python tests/run.py github_merge      (no network: local fake GitHub and bare repos; needs git and bash)

Owner decision 2026-10-27: green CI merges on its own, with a per-repo switch. Acceptance criteria covered here:
  14. A PR merged whose post-merge check fails stays "merged", with a warning.
  15. A next job only starts once its dependency is met (merged and post-merge checks passed) and is the job asked for.
Plus: no auto-merge with the switch off, with a flagged change, or without CI; a person can merge; the repo's allowed
merge methods are followed; a branch behind its base is updated first; a conflict becomes a fix round; merges of one
repo run one at a time; after a merge the chat's next work starts on a fresh branch and a new PR.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-ghm-")
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


w.configure(notify=notify, start_turn=start_turn, session_info=lambda sid: {"title": f"Việc {sid}", "engine": "x"})
run = lambda coro: asyncio.run(coro)  # noqa: E731
BRAIN = tempfile.mkdtemp(prefix="brain-")
github_repos.connect(GOOD_TOKEN)
S = github_store.store


def setup(chat, repo, files=None):
    if repo not in fake.repos:
        fake.add_repo(repo, files=files or {"README.md": "x\n", "src/a.py": "a = 1\n"})
    github_repos.attach(chat, BRAIN, BRAIN, [repo])
    github_repos.set_checks(BRAIN, repo, [])
    return Path(github_repos.session_repos(chat, BRAIN)[0]["worktree"])


def push_change(chat, repo, wt, name, text):
    (wt / name).parent.mkdir(parents=True, exist_ok=True)
    (wt / name).write_text(text, encoding="utf-8")
    run(w.after_turn(chat, BRAIN, f"đổi {name}"))
    return S().get(chat, repo)


def green(sha, name="test"):
    fake.set_checks(sha, [(name, "completed", "success")])


# ---- default: green merges on its own; next job waits for the post-merge checks ----
wt = setup("c1", "acme/app")
r = push_change("c1", "acme/app", wt, "src/a.py", "a = 2\n")
out = w.queue_next("c1", "Thêm trang đăng ký")
check("a next job can be queued for the chat", out["id"] > 0 and out["queue"][0]["text"] == "Thêm trang đăng ký")
check("criterion 15: nothing starts while the PR is not merged", turns == [])
green(r["head_sha"])
run(w.tick())
r = S().get("c1", "acme/app")
check("default policy: green CI merges on its own", r["integ"] == "merged" and fake.pulls["acme/app"][0]["merged"])
check("the repo's first allowed method is used (squash)", "(#1)" in git(["log", "-1", "--format=%s", "main"],
                                                                          fake.repos["acme/app"]["bare"]).stdout)
check("post-merge checks are now awaited", r["post_merge"] == "pending")
check("criterion 15: the next job still waits for the post-merge checks", turns == [])
green(r["merged_sha"])
run(w.tick())
check("post-merge green", S().get("c1", "acme/app")["post_merge"] == "green")
check("criterion 15: the next job starts once, as the job that was asked for",
      len(turns) == 1 and "Thêm trang đăng ký" in turns[0][1] and turns[0][1].startswith(w.FIX_MARKER))
run(w.tick())
check("the next job is never handed out twice", len(turns) == 1 and w.session_state("c1")["queue"] == [])
merge_calls = lambda: [c for c in fake.calls if c[0] == "PUT" and c[1] == "/repos/acme/app/pulls/1/merge"]  # noqa: E731
n_calls = len(merge_calls())
github_store._STORE = None          # a restart: the state is read back from disk
for _ in range(3):
    run(w.tick())
run(w.after_turn("c1", BRAIN, "không đổi gì"))
check("criterion 10: repeated ticks and a restart after the merge make no second PR, merge or next job",
      n_calls == 1 and len(merge_calls()) == 1 and len(fake.pulls["acme/app"]) == 1 and len(turns) == 1)
check("after the merge the worktree moved to a fresh branch from the new base",
      git(["rev-parse", "--abbrev-ref", "HEAD"], wt).stdout.strip() == "javis/c1-r2"
      and git(["merge-base", "--is-ancestor", "origin/main", "HEAD"], wt, check=False).returncode == 0)
r2 = push_change("c1", "acme/app", wt, "src/b.py", "b = 1\n")
check("new work after a merge opens a new PR on the fresh branch",
      r2["pr_number"] == 2 and r2["branch"] == "javis/c1-r2" and r2["integ"] == "pr_open" and r2["ci"] == "pending")

# ---- criterion 14: post-merge red keeps merged, with a warning; next job does not start ----
w.queue_next("c1", "Việc thứ ba")
green(r2["head_sha"])
run(w.tick())
r2 = S().get("c1", "acme/app")
fake.set_checks(r2["merged_sha"], [("test", "completed", "failure")])
n = len(turns)
run(w.tick())
r2 = S().get("c1", "acme/app")
check("criterion 14: merged stays merged when the post-merge check fails", r2["integ"] == "merged" and r2["post_merge"] == "red")
ic = github_store.icon(S().for_session("c1"))
check("criterion 14: the icon says merged, with the warning", ic["state"] == "merged" and ic["merged_warning"] is True)
check("criterion 15: a red base after merge holds the next job", len(turns) == n)
check("the chat hears about the red post-merge check", any("sau merge" in t or "after the merge" in t for _, t, _ in posted))

# ---- switch off: ready, not merged; a person merges ----
wt3 = setup("c3", "acme/off")
github_repos.set_auto_merge(BRAIN, "acme/off", False)
r = push_change("c3", "acme/off", wt3, "src/a.py", "a = 5\n")
green(r["head_sha"])
run(w.tick())
r = S().get("c3", "acme/off")
check("auto-merge off: ready, not merged", r["integ"] == "ready" and not fake.pulls["acme/off"][0]["merged"])
check("the chat is told why Javis did not merge", any("acme/off" in t and ("tắt" in t or "off" in t) for _, t, _ in posted))
out = run(w.merge_by_person("c3", "acme/off"))
check("a person can merge a ready PR", out["row"]["integ"] == "merged" and fake.pulls["acme/off"][0]["merged"])

# ---- a flagged change (7.4) never auto-merges ----
wt4 = setup("c4", "acme/flag", files={"README.md": "x\n", "tests/test_a.py": "def test_a():\n    assert 1\n"})
r = push_change("c4", "acme/flag", wt4, "tests/test_a.py", "import pytest\n@pytest.mark.skip\ndef test_a():\n    assert 1\n")
check("the skip is recorded on the job", any(x["kind"] == "test skipped" for x in r["merge_block"]))
green(r["head_sha"])
run(w.tick())
check("criterion 7: a skipped test blocks the auto-merge", S().get("c4", "acme/flag")["integ"] == "ready"
      and not fake.pulls["acme/flag"][0]["merged"])

# ---- no CI never auto-merges ----
wt5 = setup("c5", "acme/noci")
r = push_change("c5", "acme/noci", wt5, "src/a.py", "a = 6\n")
w.NO_CI_GRACE_S = 0
run(w.tick())
w.NO_CI_GRACE_S = 180
check("no CI: ready for a person, never merged by Javis", S().get("c5", "acme/noci")["integ"] == "ready"
      and not fake.pulls["acme/noci"][0]["merged"])

# ---- merge method not allowed: next allowed one ----
wt6 = setup("c6", "acme/meth")
fake.repos["acme/meth"]["disallowed_methods"] = ["squash"]
r = push_change("c6", "acme/meth", wt6, "src/a.py", "a = 7\n")
green(r["head_sha"])
run(w.tick())
check("a refused merge method falls through to the next one", S().get("c6", "acme/meth")["integ"] == "merged"
      and "Merge #" in git(["log", "-1", "--format=%s", "main"], fake.repos["acme/meth"]["bare"]).stdout)

# ---- behind the base: update the branch first ----
wt7 = setup("c7", "acme/behind")
r = push_change("c7", "acme/behind", wt7, "src/a.py", "a = 8\n")
fake.push_to_default("acme/behind", "other.txt", "o\n")
fake.pulls["acme/behind"][0]["mergeable_state"] = "behind"
green(r["head_sha"])
run(w.tick())
r7 = S().get("c7", "acme/behind")
check("a branch behind its base is updated, not merged stale", not fake.pulls["acme/behind"][0]["merged"]
      and r7["ci"] == "pending" and fake.branch_sha("acme/behind", r7["branch"]) != r["head_sha"])
run(w.tick())
new_head = S().get("c7", "acme/behind")["head_sha"]
check("the updated head is followed", new_head == fake.branch_sha("acme/behind", r7["branch"]))
green(new_head)
run(w.tick())
check("once green on the updated head it merges", S().get("c7", "acme/behind")["integ"] == "merged")

# ---- conflict: a fix round ----
wt8 = setup("c8", "acme/conf")
r = push_change("c8", "acme/conf", wt8, "src/a.py", "a = 9\n")
fake.pulls["acme/conf"][0]["mergeable"] = False
green(r["head_sha"])
n = len(turns)
run(w.tick())
check("a conflict marks the job broken and starts one fix round to merge the base in",
      S().get("c8", "acme/conf")["integ"] == "conflict" and len(turns) == n + 1 and "git merge origin/main" in turns[-1][1])
check("the conflict icon is 'broken'", github_store.icon(S().for_session("c8"))["state"] == "broken")

# ---- two chats on one repo: merges run one at a time ----
wa = setup("ca", "acme/q")
wb = setup("cb", "acme/q")
ra = push_change("ca", "acme/q", wa, "a.txt", "a\n")
rb = push_change("cb", "acme/q", wb, "b.txt", "b\n")
green(ra["head_sha"])
green(rb["head_sha"])
run(w.tick())
check("two ready PRs of one repo both merge, one after the other",
      S().get("ca", "acme/q")["integ"] == "merged" and S().get("cb", "acme/q")["integ"] == "merged"
      and len([p for p in fake.pulls["acme/q"] if p["merged"]]) == 2)

# ---- the javis_github tool ----
spec = importlib.util.spec_from_file_location("javis_github_plugin", ROOT / "system/plugins/javis-github/plugin.py")
plug = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plug)


class Ctx:
    vault_root = None


out = plug._chay({"op": "status", "chat_id": "web:c3"}, Ctx())
check("tool status lists the repo, CI and merge state", "acme/off" in out and "đã merge" in out)
out = plug._chay({"op": "next", "chat_id": "web:c3", "text": "Viết tài liệu"}, Ctx())
check("tool next queues the job and tells the model not to promise reports", "Đã xếp" in out and "đừng hứa" in out)
qid = w.session_state("c3")["queue"][0]["id"]
check("tool cancel drops it", "Đã bỏ" in plug._chay({"op": "cancel", "chat_id": "web:c3", "id": qid}, Ctx())
      and w.session_state("c3")["queue"] == [])
check("tool refuses outside a web chat", plug._chay({"op": "status"}, Ctx()).startswith("ERROR"))
check("a next job needs an attached repo", plug._chay({"op": "next", "chat_id": "web:nope", "text": "x"}, Ctx()).startswith("ERROR"))

fake.close()
print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
