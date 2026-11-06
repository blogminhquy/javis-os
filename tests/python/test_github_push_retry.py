"""GitHub inside chat: a push that fails is retried, never left for the person to notice (owner, 06/11/2026).

    python tests/run.py github_push_retry      (no network: local fake GitHub and bare repos; needs git and bash)

What happened: the gate was green, the push failed with git's raw "could not read Username ... terminal prompts
disabled", the person signed in to GitHub again and asked three times to push and merge. Nothing ran: the gate
remembered the worktree state, so every later turn counted as "nothing changed", and the stuck reason was wiped to
"idle". This file replays that and checks each way back: the next turn, the watcher, a reconnect, the button.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-ghpr-")
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


posted, turns = [], []
task = {"text": "thêm dấu chấm đỏ cho tin chưa đọc"}


async def notify(sid, text, ok):
    posted.append((sid, text, ok))


async def start_turn(sid, text):
    turns.append((sid, text))
    return True


w.configure(notify=notify, start_turn=start_turn,
            session_info=lambda sid: {"title": "Chấm đỏ", "task": task["text"], "engine": "anthropic-cli", "model": "opus"})
run = lambda coro: asyncio.run(coro)  # noqa: E731
BRAIN = tempfile.mkdtemp(prefix="brain-")
fake.add_repo("acme/app", files={"README.md": "app\n", "src/a.py": "a = 1\n"})
github_repos.connect(GOOD_TOKEN)
github_repos.attach("chat", BRAIN, BRAIN, ["acme/app"])
wt = Path(github_repos.session_repos("chat", BRAIN)[0]["worktree"])
gate_runs = []
github_repos.set_checks(BRAIN, "acme/app", [{"run": "true"}])
_real_gate = w.github_gate.run_gate


def counting_gate(*a, **kw):
    gate_runs.append(1)
    return _real_gate(*a, **kw)


w.github_gate.run_gate = counting_gate
github_repos.set_auto_merge(BRAIN, "acme/app", False)
S = github_store.store


def row():
    return S().get("chat", "acme/app")


# ---- push refused the way the owner saw it: git asks for a username it cannot type ----
_real_git = github_repos.git
refuse = {"on": True}


def git_refusing_push(args, cwd, **kw):
    if refuse["on"] and args and args[0] == "push":
        import subprocess
        return subprocess.CompletedProcess(["git"] + list(args), 128, "",
                                           "fatal: could not read Username for 'https://github.com': "
                                           "terminal prompts disabled\n")
    return _real_git(args, cwd, **kw)


github_repos.git = git_refusing_push
(wt / "src/a.py").write_text("a = 2\n", encoding="utf-8")
run(w.after_turn("chat", BRAIN, task["text"]))
r = row()
check("a refused push leaves the row stuck with a pending retry", r["exec"] == "stuck" and w.ship_failed(r).get("kind") == "auth")
check("the chat gets plain words, not git's prompt error",
      posted and posted[-1][2] is False and "could not read Username" not in posted[-1][1]
      and ("Kết nối" in posted[-1][1] or "Connections" in posted[-1][1]))
check("nothing reached GitHub", not fake.pulls.get("acme/app") and r["branch"])
branch = r["branch"]
title = r["title"]
gates_after_first = len(gate_runs)

# ---- the person reconnects and asks to push (the turn that did nothing before) ----
task["text"] = "ok đẩy lên github rồi merge giúp anh luôn nhé"
n_posts = len(posted)
run(w.after_turn("chat", BRAIN, task["text"]))
r = row()
check("still refused: the retry ran and kept the failure showing (never a silent idle)",
      r["exec"] == "stuck" and r["stuck_reason"] and w.ship_failed(r).get("tries") == 2)
check("the same failure on the same commit is not announced twice", len(posted) == n_posts)
check("the retry did not rerun the local checks for unchanged code", len(gate_runs) == gates_after_first)
check("the prompt tells the model the real state and not to refuse",
      "CHƯA lên GitHub" in github_repos.prompt_block("chat", BRAIN)
      and "KHÔNG nói là mình không được làm" in github_repos.prompt_block("chat", BRAIN))

# ---- the watcher waits for the backoff, then retries on its own ----
check("the watcher lists the row", [x["full_name"] for x in S().ship_pending()] == ["acme/app"])
check("the watcher does not retry before the wait is over", run(w.retry_due()) == 0)
refuse["on"] = False
check("a reconnect retries right away, whatever the wait", run(w.retry_due(force=True)) == 1)
r = row()
check("pushed: PR open, CI pending, nothing owed any more",
      r["exec"] == "done" and r["integ"] == "pr_open" and r["ci"] == "pending" and not w.ship_failed(r)
      and len(fake.pulls["acme/app"]) == 1 and fake.branch_sha("acme/app", branch) == r["head_sha"])
check("the PR keeps the branch and the name of the original job, not the 'push it' message",
      r["branch"] == branch and r["title"] == title and fake.pulls["acme/app"][0]["title"] == title
      and "dấu chấm đỏ" in fake.pulls["acme/app"][0]["body"] and "merge giúp" not in fake.pulls["acme/app"][0]["body"])
check("the chat hears it went through", any("PR #1" in t and ok for _, t, ok in posted[n_posts:]))
check("nothing left to retry", S().ship_pending() == [])

# ---- the button: a person retries, and hears the reason when it still fails ----
(wt / "src/a.py").write_text("a = 3\n", encoding="utf-8")
refuse["on"] = True
task["text"] = "đổi thành 3"
run(w.after_turn("chat", BRAIN, task["text"]))
check("a second job's refused push is owed again", w.ship_failed(row()).get("kind") == "auth")
try:
    run(w.retry_ship("chat", "acme/app", by_person=True))
    raised = ""
except github_repos.RepoError as e:
    raised = str(e)
check("the button reports why it is still refused", "GitHub" in raised)
refuse["on"] = False
r = run(w.retry_ship("chat", "acme/app", by_person=True))
check("the button pushes once GitHub accepts", not w.ship_failed(r) and r["head_sha"] == fake.branch_sha("acme/app", branch)
      and len(fake.pulls["acme/app"]) == 1)

# ---- no token at all: refused before git runs, with the same words ----
github_repos.git = _real_git
(wt / "src/a.py").write_text("a = 4\n", encoding="utf-8")
github_repos.disconnect()
run(w.after_turn("chat", BRAIN, "đổi thành 4"))
check("not connected: the push is owed with the sign-in reason", w.ship_failed(row()).get("kind") == "auth")
check("the watcher does nothing while GitHub is not connected", run(w.retry_due(force=True)) == 0)
github_repos.connect(GOOD_TOKEN)


async def reconnect_hook():
    w.on_connected()        # what the Connections routes call after a successful connect or sign-in
    await asyncio.gather(*list(w._BG_TASKS))


run(reconnect_hook())
check("connected again: the reconnect hook pushes the owed commit", not w.ship_failed(row())
      and row()["head_sha"] == fake.branch_sha("acme/app", branch))

# ---- the wording of each git failure ----
check("401 reads as sign-in", w.push_error("fatal: Authentication failed for 'https://github.com/a/b'", "x", "a/b").kind == "auth")
check("403 reads as permission", w.push_error("remote: Permission to a/b.git denied to bot.\nfatal: unable to access: "
                                              "The requested URL returned error: 403", "x", "a/b").kind == "perm")
check("non-fast-forward is never overwritten", w.push_error(" ! [rejected] HEAD -> x (fetch first)", "x", "a/b").kind == "diverged")
check("anything else is retried later", w.push_error("fatal: unable to access: Could not resolve host", "x", "a/b").kind == "other")
check("the backoff grows", w.SHIP_RETRY_S == tuple(sorted(w.SHIP_RETRY_S)) and w.SHIP_RETRY_S[0] >= 60)

# ---- a red gate drops the owed push: the code must be fixed first ----
row_now = row()
gate = dict(row_now["gate"])
gate["ship_failed"] = {"kind": "other", "tries": 1, "at": time.time(), "next_at": 0, "task": "x"}
S().update("chat", "acme/app", gate=gate, exec="stuck")
github_repos.set_checks(BRAIN, "acme/app", [{"run": "false"}])
(wt / "src/a.py").write_text("a = 5\n", encoding="utf-8")
run(w.after_turn("chat", BRAIN, "đổi thành 5"))
check("red local checks: no push is owed, the watcher stops", not w.ship_failed(row()) and S().ship_pending() == [])

fake.close()
print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
