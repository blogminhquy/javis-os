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


async def review(prompt, provider, model=""):
    reviews.append((provider, prompt, model))
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


# ---- parsing ----
check("parse: JSON inside prose is read", w.parse_findings('Here: {"findings":[{"file":"a.py","line":3,"problem":"x"}]}')[0]["line"] == 3)
check("parse: unreadable answer is None, not 'no findings'", w.parse_findings("looks fine to me") is None)
check("parse: an empty list is no findings", w.parse_findings('{"findings": []}') == [])


def green(chat, fn):
    fake.set_checks(S().get(chat, fn)["head_sha"], [("test", "completed", "success")])


async def _review_now_wait(sid, fn, provider=""):
    out = w.review_now(sid, fn, provider)
    t = w._PERSON_REVIEWS.get(w._person_key(sid, fn))
    if t is not None:
        await t
    return out


def review_now(sid, fn, provider=""):
    return run(_review_now_wait(sid, fn, provider))


FINDING = '{"findings": [{"file": "src/a.py", "line": 1, "problem": "a phải là số âm", "scenario": "gọi f(2)"}]}'

# ---- owner, 08/11/2026: off by default, the person decides ----
wts = setup("cc0", ["acme/off"])
change("cc0", wts["acme/off"], "src/a.py", "a = 10\n")
green("cc0", "acme/off")
n = len(reviews)
run(w.tick())
check("cross review is off by default: no review, CI green merges", len(reviews) == n
      and S().get("cc0", "acme/off")["integ"] == "merged")
check("the repo switch reads off by default", github_repos.review_settings(github_repos.find(BRAIN, "acme/off"))["on"] is False)

# ---- switch on: the chat's own engine reviews, findings wait for the person ----
wts = setup("cc1", ["acme/app"])
github_repos.set_review(BRAIN, "acme/app", True)
wt = wts["acme/app"]
change("cc1", wt, "src/a.py", "a = 2\n")
review_answer["text"] = FINDING
green("cc1", "acme/app")
nt = len(turns)
run(w.tick())
r = S().get("cc1", "acme/app")
check("switch on: the diff is reviewed", reviews and "a = 2" in reviews[-1][1])
check("owner, 08/11/2026: the chat's own engine and model review by default",
      reviews[-1][0] == "anthropic-cli" and reviews[-1][2] == "m-cc")
check("a finding holds the merge", r["integ"] != "merged" and not fake.pulls["acme/app"][0]["merged"])
check("findings are NOT sent to the author on their own", len(turns) == nt)
check("the chat shows the findings and the two choices", any(sid == "cc1" and "a phải là số âm" in t and "Bỏ qua" in t
                                                              for sid, t, _ in posted))
check("the panel lists the open findings", w.session_state("cc1")["repos"][0]["review_open"][0]["problem"] == "a phải là số âm")
run(w.tick())
check("the same head is reviewed only once", sum(1 for x in reviews if "a = 2" in x[1]) == 1)
out = run(w.review_fix("cc1", "acme/app"))
check("'Fix them' starts one fix round with the findings", len(turns) == nt + 1
      and turns[-1][1].startswith(w.FIX_MARKER + " Review chéo") and "a phải là số âm" in turns[-1][1])
run(w.after_turn("cc1", BRAIN, turns[-1][1]))      # the author looked and changed nothing
check("an author rejecting the findings releases them", not w.open_findings(S().get("cc1", "acme/app")))
run(w.tick())
check("then the PR merges", S().get("cc1", "acme/app")["integ"] == "merged")

# ---- 'Skip and merge' ----
wts = setup("cc2", ["acme/two"])
github_repos.set_review(BRAIN, "acme/two", True)
change("cc2", wts["acme/two"], "src/a.py", "a = 3\n")
green("cc2", "acme/two")
run(w.tick())
check("held by a finding", S().get("cc2", "acme/two")["integ"] == "ready" and w.open_findings(S().get("cc2", "acme/two")))
run(w.review_skip("cc2", "acme/two"))
check("'Skip and merge' merges at once", S().get("cc2", "acme/two")["integ"] == "merged")

# ---- a new commit leaves old findings behind ----
wts = setup("cc8", ["acme/newer"])
github_repos.set_auto_merge(BRAIN, "acme/newer", False)
change("cc8", wts["acme/newer"], "src/a.py", "a = 30\n")
green("cc8", "acme/newer")
run(w.tick())
review_now("cc8", "acme/newer")
check("a person's review records findings", w.open_findings(S().get("cc8", "acme/newer")))
review_answer["text"] = '{"findings": []}'
change("cc8", wts["acme/newer"], "src/a.py", "a = -30\n")
check("a newer commit: the old findings no longer hold the merge", not w.open_findings(S().get("cc8", "acme/newer")))

# ---- Review now, switch off: the merge waits for it ----
wts = setup("cc3", ["acme/manual"])
change("cc3", wts["acme/manual"], "src/a.py", "a = 4\n")
review_answer["text"] = FINDING
n = len(reviews)


async def start_then_tick():
    gate = asyncio.Event()
    orig = w._review

    async def slow(prompt, provider, model=""):
        await gate.wait()       # the review is still running while CI turns green
        return await orig(prompt, provider, model)

    w.configure(review=slow)
    out = w.review_now("cc3", "acme/manual", "gemini")
    task = w._PERSON_REVIEWS[w._person_key("cc3", "acme/manual")]
    green("cc3", "acme/manual")
    await w.tick()        # CI green while the review still runs: no merge past it
    mid = S().get("cc3", "acme/manual")["integ"]
    gate.set()
    await task
    w.configure(review=orig)
    return out, mid


out, mid = run(start_then_tick())
check("Review now names the engine a person picked", out["reviewer"].startswith("gemini") and reviews[-1][0] == "gemini")
check("CI green during a person's review does not merge past it", mid != "merged")
run(w.tick())
check("its findings then hold the merge", S().get("cc3", "acme/manual")["integ"] != "merged")
try:
    review_now("cc3", "acme/manual", "openai-oauth")
    bad = ""
except github_repos.RepoError as e:
    bad = str(e)
check("a plan run through a CLI cannot be picked to review", "openai-oauth" in bad)
run(w.review_skip("cc3", "acme/manual"))
check("skip after a person's review merges", S().get("cc3", "acme/manual")["integ"] == "merged")
try:
    review_now("cc3", "acme/manual")
    after = ""
except github_repos.RepoError as e:
    after = str(e)
check("nothing to review once merged", bool(after))
review_answer["text"] = '{"findings": []}'

# ---- a repo can pin its reviewer ----
wts = setup("cc4", ["acme/pin"])
github_repos.set_review(BRAIN, "acme/pin", True, "openai")
change("cc4", wts["acme/pin"], "src/a.py", "a = 5\n")
green("cc4", "acme/pin")
run(w.tick())
check("the repo's pinned reviewer reviews", reviews[-1][0] == "openai" and S().get("cc4", "acme/pin")["integ"] == "merged")
check("a clean review is said in the chat", any(sid == "cc4" and "review" in t.lower() for sid, t, _ in posted))

# ---- a later job in the same chat: its own request names the PR and guides the review ----
TASKS = {"cc7": "Đổi lời chào thành tiếng Anh"}
w.configure(session_info=lambda sid: {"title": "Tiêu đề cũ của cuộc trò chuyện", "task": TASKS.get(sid, ""),
                                      "engine": ENGINES.get(sid[:2], "anthropic-cli"), "model": "m-" + sid[:2]})
wts = setup("cc7", ["acme/task"])
github_repos.set_review(BRAIN, "acme/task", True)
change("cc7", wts["acme/task"], "src/a.py", "a = 11\n")
pr7 = fake.pulls["acme/task"][0]
check("the PR is named after the job's own request, not the chat title", pr7["title"] == "Đổi lời chào thành tiếng Anh")
n = len(reviews)
green("cc7", "acme/task")
run(w.tick())
check("the reviewer gets the latest request to judge against", len(reviews) == n + 1
      and "Đổi lời chào thành tiếng Anh" in reviews[-1][1])
w.configure(session_info=lambda sid: {"title": f"Việc {sid}", "engine": ENGINES.get(sid[:2], "anthropic-cli"),
                                      "model": "m-" + sid[:2]})

# ---- no engine can review: the chat says why, the merge goes on ----
w.configure(reviewers=lambda: [])
wts = setup("cc5", ["acme/solo"])
github_repos.set_review(BRAIN, "acme/solo", True)
change("cc5", wts["acme/solo"], "src/a.py", "a = 12\n")
green("cc5", "acme/solo")
run(w.tick())
check("no reviewer: the merge is not held", S().get("cc5", "acme/solo")["integ"] == "merged")
check("no reviewer: the chat says why and what can review",
      any(sid == "cc5" and "API" in t and "ChatGPT" in t for sid, t, _ in posted))
w.configure(reviewers=lambda: ["anthropic-cli", "openai", "gemini"])

# ---- reviewer broken: skipped, not stuck ----
review_answer["fail"] = True
wts = setup("ccD", ["acme/down"])
github_repos.set_review(BRAIN, "acme/down", True)
change("ccD", wts["acme/down"], "src/a.py", "a = 13\n")
green("ccD", "acme/down")
run(w.tick())
check("a broken reviewer is skipped with a notice and the PR merges", S().get("ccD", "acme/down")["integ"] == "merged")
fail_note = [t for sid, t, _ in posted if sid == "ccD" and "reviewer down" in t]
check("every reviewer down: the notice names those tried and why", bool(fail_note)
      and "anthropic-cli" in fail_note[-1] and "openai" in fail_note[-1])
review_answer["fail"] = False

# ---- the chat's engine cannot run: the next one reviews ----
_orig_review = w._review


async def review_first_down(prompt, provider, model=""):
    reviews.append((provider, prompt, model))
    if provider == "anthropic-cli":
        raise RuntimeError("claude down")
    return '{"findings": []}'


w.configure(review=review_first_down)
n0 = len(reviews)
wts = setup("cc9", ["acme/next"])
github_repos.set_review(BRAIN, "acme/next", True)
change("cc9", wts["acme/next"], "src/a.py", "a = 14\n")
green("cc9", "acme/next")
run(w.tick())
tried = [x[0] for x in reviews[n0:]]
check("a reviewer that cannot run hands over to the next one", tried == ["anthropic-cli", "openai"], )
check("the next reviewer's clean review lets the PR merge", S().get("cc9", "acme/next")["integ"] == "merged"
      and (S().get("cc9", "acme/next")["gate"] or {}).get("reviewer") == "openai")
check("no 'did not run' notice when the next reviewer ran",
      not any(sid == "cc9" and ("did not run" in t or "không chạy được" in t) for sid, t, _ in posted))
w.configure(review=_orig_review)

# ---- a restart drops a review in flight: its flag must not hold the merge ----
r = S().get("cc8", "acme/newer")
S().update("cc8", "acme/newer", gate=dict(r.get("gate") or {}, review_running=True))
w.reconcile_on_start()
check("restart clears a stale 'review running'", not (S().get("cc8", "acme/newer")["gate"] or {}).get("review_running"))

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

# ---- the javis_github tool: "review this PR" and "skip them" from the chat ----
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("javis_github_plugin", ROOT / "system/plugins/javis-github/plugin.py")
plug = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(plug)


class Ctx:
    vault_root = None


async def tool(args):
    out = plug._chay(args, Ctx())
    if asyncio.iscoroutine(out):
        out = await out
    t = w._PERSON_REVIEWS.get(w._person_key("ccT", "acme/tool"))
    if t is not None:
        await t
    return out

wts = setup("ccT", ["acme/tool"])
github_repos.set_auto_merge(BRAIN, "acme/tool", False)
change("ccT", wts["acme/tool"], "src/a.py", "a = 21\n")
review_answer["text"] = FINDING
n = len(reviews)
out = run(tool({"op": "review", "chat_id": "web:ccT"}))
check("tool review starts a review of the chat's only PR", "Đã bắt đầu review" in out and len(reviews) == n + 1)
out = run(tool({"op": "status", "chat_id": "web:ccT"}))
check("tool status lists the findings waiting for the person", "a phải là số âm" in out)
out = run(tool({"op": "review", "chat_id": "web:ccT", "provider": "grok-cli"}))
check("tool review refuses an engine that cannot review", out.startswith("ERROR") and "grok-cli" in out)
out = run(tool({"op": "review", "chat_id": "web:ccT", "repo": "acme/none"}))
check("tool review names a repo the chat has no PR for", out.startswith("ERROR"))
green("ccT", "acme/tool")
run(w.tick())
out = run(tool({"op": "review_skip", "chat_id": "web:ccT"}))
check("tool review_skip drops the findings and merges", "merge" in out
      and S().get("ccT", "acme/tool")["integ"] == "merged")
review_answer["text"] = '{"findings": []}'

fake.close()
print()
if _fails:
    print(f"FAIL {len(_fails)} test: " + ", ".join(_fails))
    sys.exit(1)
print("TẤT CẢ PASS")
