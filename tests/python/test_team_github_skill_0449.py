"""GitHub repos and /skill commands in a team chat (0.449.0).

    python tests/python/test_team_github_skill_0449.py

Owner, 04/11/2026: a team could pin a working folder but could not push to GitHub like a private chat, and the /skill
commands of the main chat did not work in a team. Covered here, on the real host, no model call:
- the team chat's repos reach the prompt of a Work/Help turn only, with the "push when the job is done" note;
- a job closed as done runs the same GitHub pipeline as a private chat turn (github_work.after_turn);
- GitHub news of a team chat lands in the team chat as a system line; a CI fix round becomes ONE team job;
- a [SKILL: slug] block in a message or job puts that skill's text into the member's prompt.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-gh-")
BR = Path(tempfile.mkdtemp(prefix="javis-team-gh-brain-"))
(BR / "agents").mkdir()
for slug, name in (("lan", "Lan"), ("minh", "Minh")):
    (BR / "agents" / f"{slug}.md").write_text(f"---\nname: {name}\nrole: Thành viên\n---\nBạn là {name}.\n", encoding="utf-8")
(BR / "skills" / "viet-email").mkdir(parents=True)
(BR / "skills" / "viet-email" / "SKILL.md").write_text(
    "---\nname: Viết email\ndescription: Viết email bán hàng ngắn\ngroup: marketing\n---\n"
    "Luôn mở bằng tên người nhận. Tối đa 120 chữ.\n", encoding="utf-8")

import main  # noqa: E402
import team_runner  # noqa: E402
import github_repos  # noqa: E402
import github_work  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:300] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


async def _quiet(ev):
    return None

main._CHAT_RUNTIME.publish = _quiet
main._TEAM_API.deps.spawn = lambda job: job.close() if hasattr(job, "close") else None
main._TEAM_API.kick = lambda: None
main.cfgmod.gate_active = lambda: False
client = TestClient(main.app, base_url="http://127.0.0.1")
H = {"origin": "http://127.0.0.1"}
b = str(BR)
r = client.post("/teams", params={"brain": b}, headers=H, json={"name": "Phòng Code", "members": ["lan", "minh"],
                                                               "leader_slug": "lan", "client_req_id": "r1"})
team = r.json()["team"]
tid, sid = team["team_id"], team["session_id"]
team = main._TEAM_API.teams().get(tid)
runner = main._TEAM_API.runner()

# ---- the team behind a conversation ----
check("by_session finds the team of its chat", (main._TEAM_API.teams().by_session(sid) or {}).get("team_id") == tid)
check("by_session of another conversation is None", main._TEAM_API.teams().by_session("not-a-team") is None)
check("_github_team reads the same", (main._github_team(sid) or {}).get("team_id") == tid and main._github_team("x") is None)

# ---- repos in the prompt: Work/Help turns only ----
real_block = github_repos.prompt_block
github_repos.prompt_block = lambda s, br="": "\n# === REPO GITHUB CỦA CUỘC TRÒ CHUYỆN NÀY ===\n- o/r: sửa trong /wt\n" if s == sid else ""
try:
    work = main._team_docs_block(team, tools=True)
    talk = main._team_docs_block(team, tools=False)
finally:
    github_repos.prompt_block = real_block
check("a Work/Help turn gets the team chat's repos", "REPO GITHUB" in work and "/wt" in work, work)
check("it is told the push happens when the whole job is done", main.TEAM_GITHUB_NOTE in work)
check("a text-only turn does not get the repos", "REPO GITHUB" not in talk, talk)
check("no repo attached: nothing is added", main.TEAM_GITHUB_NOTE not in main._team_docs_block(team, tools=True))

# ---- a job done runs the GitHub pipeline ----
seen = []


async def _fake_after(s, br, text=""):
    seen.append((s, br, text))
    return []

real_after = github_work.after_turn
github_work.after_turn = _fake_after


async def _done():
    main._team_job_done(team, {"id": "t_1", "title": "Sửa nút", "intent": "Sửa nút Mua ngay"})
    await asyncio.sleep(0)
    await asyncio.gather(*list(main._PUSH_TASKS), return_exceptions=True)

try:
    asyncio.run(_done())
finally:
    github_work.after_turn = real_after
check("a team job done hands the team chat to github_work.after_turn, with the job's request",
      seen == [(sid, team["brain_id"], "Sửa nút Mua ngay")], seen)

got = []
old_hook = runner.job_done
runner.job_done = lambda t, k: got.append((t["team_id"], k.get("id")))
try:
    runner._job_done(team, "t_none")
finally:
    runner.job_done = old_hook
check("the runner calls its job_done hook with the team and the job", got == [(tid, "t_none")], got)


def _boom(t, k):
    raise RuntimeError("push failed")

runner.job_done = _boom
try:
    runner._job_done(team, "t_none")
    check("a failing job_done hook never breaks the runner", True)
except Exception as e:  # noqa: BLE001
    check("a failing job_done hook never breaks the runner", False, e)
finally:
    runner.job_done = old_hook
check("main wires the hooks into the team runner",
      runner.job_done is main._team_job_done and runner.skill_block is main._team_skill_block)
check("every path that closes a job as done tells the host",
      Path(team_runner.__file__).read_text(encoding="utf-8").count("self._job_done(team, task_id)") == 3)

# ---- GitHub news lands in the team chat ----
inbox = []


async def _fake_inbox(chat, text, **kw):
    inbox.append((chat, text, kw.get("quiet")))
    return {"id": 1}

real_inbox = main._bo_vao_hom_thu
main._bo_vao_hom_thu = _fake_inbox
try:
    ok = asyncio.run(main._github_notify(sid, "**o/r**\nĐã đẩy lên nhánh `javis/abc`, PR #7", True))
finally:
    main._bo_vao_hom_thu = real_inbox
store = main.get_store()
last = store.get_team_messages_page(sid, limit=1)["messages"][-1]
check("GitHub news of a team chat is a system line in the team chat",
      last["author_kind"] == "system" and (last.get("meta") or {}).get("kind") == "github" and "PR #7" in last["content"], last)
check("and a quiet copy in the inbox", inbox and inbox[0][0] == f"web:{sid}" and inbox[0][2] is True and ok == (True, ""), inbox)

# ---- a CI fix round becomes one team job ----
fix = "[Javis GitHub] CI đỏ (vòng sửa 1/3, repo o/r, PR #7)\nFAILED tests/test_x.py"
def _jobs():
    q = main.tasks_feature.store.team_queue(tid)
    return [t for v in q.values() if isinstance(v, list) for t in v if isinstance(t, dict) and t.get("id")]

before = len(_jobs())
started = asyncio.run(main._github_start_turn(sid, fix))
again = asyncio.run(main._github_start_turn(sid, fix))
jobs = _jobs()
check("a fix round of a team chat starts as a team job", started is True and again is True, (started, again))
check("the same round never makes a second job", len(jobs) == before + 1, (before, len(jobs)))
job = main.tasks_feature.store.get_task(jobs[0]["id"]) if jobs else {}
check("the job carries the fix text, marked so the round count is kept",
      str(job.get("intent") or "").startswith(github_work.FIX_MARKER), job)
msg = [m for m in store.get_team_messages_page(sid, limit=10)["messages"] if m["author_kind"] == "owner"][-1]
check("the job message says it came through Javis, from GitHub",
      ((msg.get("meta") or {}).get("via_core") or {}).get("kenh") == "github", msg.get("meta"))
check("a private chat with no follow-up runner still returns False (asks the person)",
      asyncio.run(main._github_start_turn("no-such-chat", fix)) is False)

# ---- /skill in a team ----
blk = main._team_skill_block(team, ["viet-email", "khong-co", "../etc"])
check("the named skill's text goes into the prompt", "Tối đa 120 chữ" in blk and "viet-email" in blk, blk)
check("its frontmatter does not", "description:" not in blk)
check("unknown or unsafe names are skipped", "khong-co" not in blk and "etc" not in blk)
check("no known skill: no block", main._team_skill_block(team, ["khong-co"]) == "")
text = "[SKILL: viet-email\nHãy dùng skill này để làm việc dưới đây.]\n\nViết email cho khách sỉ"
check("the runner finds the /skill block in the turn's text", "Tối đa 120 chữ" in runner._skills(team, text))
check("or in the job it works on", "Tối đa 120 chữ" in runner._skills(team, "Làm phần của bạn", "", text))
check("no block: no skills", runner._skills(team, "Viết email cho khách sỉ") == "")
check("the same skill twice is read once", runner._skills(team, text, text).count("Tối đa 120 chữ") == 1)

print("\n" + ("XANH" if not fails else f"ĐỎ: {len(fails)} lỗi"))
raise SystemExit(1 if fails else 0)
