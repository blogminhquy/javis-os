"""GitHub inside chat, phase G5: cross review, lessons per repo, metrics, several repos and several engines.

    python tests/run.py github_review      (no network: local fake GitHub and bare repos; needs git and bash)

Acceptance criteria covered here:
  11. Two chats on two engines never mix their engine or credentials (PR bodies, git environment).
  12. A chat with two repos, one green and one red, shows the worst state and never reports done.
Plus spec 10 (cross review by another engine family, findings back to the author, rejection recorded, skipped review
noted on the PR), 13.1 (lessons written to the brain after a real failure, then fed to the next turn) and 13.2
(metrics per engine and model).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-ghr-")
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


posted, turns, reviews = [], [], []
review_answer = {"text": '{"findings": []}', "fail": False}


async def notify(sid, text, ok):
    posted.append((sid, text, ok))


async def start_turn(sid, text):
    turns.append((sid, text))
    return True


async def review(prompt, provider):
    reviews.append((provider, prompt))
    if review_answer["fail"]:
        raise RuntimeError("reviewer down")
    return review_answer["text"]


ENGINES = {"cc": "anthropic-cli", "cx": "openai"}
w.configure(notify=notify, start_turn=start_turn, review=review,
            reviewers=lambda: ["anthropic-cli", "openai", "gemini"],
            session_info=lambda sid: {"title": f"Việc {sid}", "engine": ENGINES.get(sid[:2], "anthropic-cli"),
                                      "model": "m-" + sid[:2]})
run = lambda coro: asyncio.run(coro)  # noqa: E731
BRAIN = tempfile.mkdtemp(prefix="brain-")
github_repos.connect(GOOD_TOKEN)
S = github_store.store
env_before = dict(os.environ)


def setup(chat, repos):
    for r in repos:
        if r not in fake.repos:
            fake.add_repo(r, files={"README.md": "x\n", "src/a.py": "a = 1\n"})
    github_repos.attach(chat, BRAIN, BRAIN, repos)
    for r in repos:
        github_repos.set_checks(BRAIN, r, [])
    return {x["full_name"]: Path(x["worktree"]) for x in github_repos.session_repos(chat, BRAIN)}


def change(chat, wt, name, text, msg="đổi"):
    (wt / name).write_text(text, encoding="utf-8")
    run(w.after_turn(chat, BRAIN, msg))


# ---- reviewer choice ----
check("a Claude author gets a reviewer from another family", w.pick_reviewer("anthropic-cli") == "openai")
check("an OpenAI author gets Claude", w.pick_reviewer("openai") == "anthropic-cli")
check("Claude API and Claude Code are the same family", w.pick_reviewer("anthropic-api") == "openai")
check("parse: JSON inside prose is read", w.parse_findings('Here: {"findings":[{"file":"a.py","line":3,"problem":"x"}]}')[0]["line"] == 3)
check("parse: unreadable answer is None, not 'no findings'", w.parse_findings("looks fine to me") is None)
check("parse: an empty list is no findings", w.parse_findings('{"findings": []}') == [])

# ---- findings go back to the author; rejection releases the merge ----
wts = setup("cc1", ["acme/app"])
wt = wts["acme/app"]
change("cc1", wt, "src/a.py", "a = 2\n")
r = S().get("cc1", "acme/app")
review_answer["text"] = '{"findings": [{"file": "src/a.py", "line": 1, "problem": "a phải là số âm", "scenario": "gọi f(2)"}]}'
fake.set_checks(r["head_sha"], [("test", "completed", "success")])
run(w.tick())
r = S().get("cc1", "acme/app")
check("spec 10: the diff went to the other engine", reviews and reviews[-1][0] == "openai" and "a = 2" in reviews[-1][1])
check("spec 10: a finding holds the merge", r["integ"] != "merged" and not fake.pulls["acme/app"][0]["merged"])
check("spec 10: the finding goes back to the author as a fix round", turns and turns[-1][1].startswith(w.FIX_MARKER + " Review chéo")
      and "a phải là số âm" in turns[-1][1] and "bác bỏ" in turns[-1][1])
run(w.tick())
check("the same head is reviewed only once", len(reviews) == 1)
run(w.after_turn("cc1", BRAIN, turns[-1][1]))      # the author looked and changed nothing
check("an author rejecting the findings releases them", not (S().get("cc1", "acme/app")["gate"] or {}).get("review_open"))
run(w.tick())
check("then the PR merges", S().get("cc1", "acme/app")["integ"] == "merged")

# ---- a finding the author fixes: new push, new review ----
wts = setup("cc2", ["acme/two"])
wt2 = wts["acme/two"]
change("cc2", wt2, "src/a.py", "a = 3\n")
fake.set_checks(S().get("cc2", "acme/two")["head_sha"], [("test", "completed", "success")])
run(w.tick())
review_answer["text"] = '{"findings": []}'
change("cc2", wt2, "src/a.py", "a = -3\n", msg=turns[-1][1])
r = S().get("cc2", "acme/two")
fake.set_checks(r["head_sha"], [("test", "completed", "success")])
run(w.tick())
check("the fixed commit is reviewed again, clean, and merges", S().get("cc2", "acme/two")["integ"] == "merged")

# ---- review findings that keep coming use up the rounds: stuck stays stuck while CI is green ----
wts = setup("cc9", ["acme/stubborn"])
wst = wts["acme/stubborn"]
review_answer["text"] = '{"findings": [{"file": "src/a.py", "line": 1, "problem": "vẫn sai", "scenario": "luôn"}]}'
for i in range(4):
    change("cc9", wst, "src/a.py", f"a = {100 + i}\n", msg=turns[-1][1] if i else "làm đi")
    fake.set_checks(S().get("cc9", "acme/stubborn")["head_sha"], [("test", "completed", "success")])
    run(w.tick())
r = S().get("cc9", "acme/stubborn")
check("review rounds used up: stuck, not merged", r["exec"] == "stuck" and r["integ"] != "merged")
run(w.tick())
run(w.tick())
r = S().get("cc9", "acme/stubborn")
check("green CI on the same commit does not lift the stuck state", r["exec"] == "stuck" and r["stuck_reason"])
check("the chat icon says it needs attention", github_store.icon(S().for_session("cc9"))["state"] == "broken")
review_answer["text"] = '{"findings": []}'

# ---- a later job in the same chat: its own request names the PR and guides the review ----
TASKS = {"cc7": "Đổi lời chào thành tiếng Anh"}
w.configure(session_info=lambda sid: {"title": "Tiêu đề cũ của cuộc trò chuyện", "task": TASKS.get(sid, ""),
                                      "engine": ENGINES.get(sid[:2], "anthropic-cli"), "model": "m-" + sid[:2]})
wts = setup("cc7", ["acme/task"])
change("cc7", wts["acme/task"], "src/a.py", "a = 11\n")
pr7 = fake.pulls["acme/task"][0]
check("the PR is named after the job's own request, not the chat title", pr7["title"] == "Đổi lời chào thành tiếng Anh")
n = len(reviews)
fake.set_checks(S().get("cc7", "acme/task")["head_sha"], [("test", "completed", "success")])
run(w.tick())
check("the reviewer gets the latest request to judge against", len(reviews) == n + 1
      and "Đổi lời chào thành tiếng Anh" in reviews[-1][1])
w.configure(session_info=lambda sid: {"title": f"Việc {sid}", "engine": ENGINES.get(sid[:2], "anthropic-cli"),
                                      "model": "m-" + sid[:2]})

# ---- no reviewer of another family: noted on the PR, merge goes on ----
w.configure(reviewers=lambda: ["anthropic-cli"])
wts = setup("cc3", ["acme/solo"])
change("cc3", wts["acme/solo"], "src/a.py", "a = 4\n")
fake.set_checks(S().get("cc3", "acme/solo")["head_sha"], [("test", "completed", "success")])
run(w.tick())
check("one engine family only: the PR says it was not cross-reviewed", any(c[0] == "acme/solo" and "Not cross-reviewed" in c[2]
                                                                          for c in fake.comments))
check("one engine family only: the merge is not held", S().get("cc3", "acme/solo")["integ"] == "merged")
w.configure(reviewers=lambda: ["anthropic-cli", "openai", "gemini"])

# ---- reviewer broken: skipped, not stuck ----
review_answer["fail"] = True
wts = setup("cc4", ["acme/down"])
change("cc4", wts["acme/down"], "src/a.py", "a = 5\n")
fake.set_checks(S().get("cc4", "acme/down")["head_sha"], [("test", "completed", "success")])
run(w.tick())
check("a broken reviewer is skipped with a notice and the PR merges", S().get("cc4", "acme/down")["integ"] == "merged"
      and any("review" in t.lower() for _, t, _ in posted))
review_answer["fail"] = False

# ---- 13.1 lessons ----
wts = setup("cc5", ["acme/learn"])
wl = wts["acme/learn"]
github_repos.set_auto_merge(BRAIN, "acme/learn", False)
change("cc5", wl, "src/a.py", "a = 6\n")
fake.set_checks(S().get("cc5", "acme/learn")["head_sha"], [("unit-tests", "completed", "failure", 901)])
run(w.tick())
change("cc5", wl, "src/a.py", "a = 7\n", msg=turns[-1][1])
fake.set_checks(S().get("cc5", "acme/learn")["head_sha"], [("unit-tests", "completed", "success")])
run(w.tick())
lessons = w.read_lessons(BRAIN, "acme/learn")
check("13.1: a CI failure fixed later becomes a lesson", any("unit-tests" in x for x in lessons))
check("13.1: lessons live in the brain, not in the repo",
      w.lessons_path(BRAIN, "acme/learn").is_file() and str(w.lessons_path(BRAIN, "acme/learn")).startswith(BRAIN)
      and not (wl / "Javis").exists())
check("13.1: the next turn's prompt carries the lesson", "unit-tests" in github_repos.prompt_block("cc5", BRAIN))
for i in range(40):
    w.add_lesson(BRAIN, "acme/learn", f"bài học {i}")
check("13.1: lessons stay under the ceiling", len(w.read_lessons(BRAIN, "acme/learn")) == w.LESSONS_MAX)
check("13.1: a duplicate lesson is not added", w.add_lesson(BRAIN, "acme/learn", "bài học 39") is False)

# ---- 13.2 metrics ----
ms = w.metrics_summary()
by = {(m["engine"], m["model"]): m for m in ms}
check("13.2: metrics per engine and model", ("anthropic-cli", "m-cc") in by and by[("anthropic-cli", "m-cc")]["jobs"] >= 3)
check("13.2: share green on the first push and review findings are counted",
      0 <= by[("anthropic-cli", "m-cc")]["first_push_green_pct"] <= 100 and by[("anthropic-cli", "m-cc")]["review_findings"] >= 1)

# ---- criterion 12: two repos, one green one red ----
wts = setup("cc6", ["acme/g", "acme/r"])
change("cc6", wts["acme/g"], "src/a.py", "a = 8\n")
change("cc6", wts["acme/r"], "src/a.py", "a = 9\n")
fake.set_checks(S().get("cc6", "acme/g")["head_sha"], [("test", "completed", "success")])
fake.set_checks(S().get("cc6", "acme/r")["head_sha"], [("test", "completed", "failure", 950)])
run(w.tick())
rows = S().for_session("cc6")
check("each repo keeps its own state", {r["full_name"]: r["integ"] for r in rows} == {"acme/g": "merged", "acme/r": "pr_open"})
ic = github_store.icon(rows)
check("criterion 12: one repo merged does not make the chat 'merged'", ic["state"] != "merged")
S().update("cc6", "acme/r", exec="stuck", stuck_reason="x")
check("criterion 12: a stuck repo makes the chat 'needs attention'", github_store.icon(S().for_session("cc6"))["state"] == "broken")
check("criterion 12: the next job waits for every repo of the chat", run(w.maybe_next("cc6")) is False)

# ---- criterion 11: two chats, two engines ----
wa = setup("cxA", ["acme/eng"])["acme/eng"]
wb = setup("ccB", ["acme/eng"])["acme/eng"]
change("cxA", wa, "x.txt", "a\n")
change("ccB", wb, "y.txt", "b\n")
pa = next(p for p in fake.pulls["acme/eng"] if p["head"]["ref"] == S().get("cxA", "acme/eng")["branch"])
pb = next(p for p in fake.pulls["acme/eng"] if p["head"]["ref"] == S().get("ccB", "acme/eng")["branch"])
check("criterion 11: each PR names its own chat's engine", "openai m-cx" in pa["body"] and "anthropic-cli m-cc" in pb["body"])
check("criterion 11: each chat's metrics row keeps its engine", S().get("cxA", "acme/eng")["engine"] == "openai"
      and S().get("ccB", "acme/eng")["engine"] == "anthropic-cli")
git_now = {k: v for k, v in os.environ.items() if k.startswith("GIT_")}
git_before = {k: v for k, v in env_before.items() if k.startswith("GIT_")}
check("criterion 11: no credential or identity leaks into the process environment",
      git_now == git_before and GOOD_TOKEN not in "".join(os.environ.values()))

fake.close()
print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
