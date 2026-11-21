"""GitHub repos of a project, of an assistant and of a new team (2026-11-15).

    python tests/run.py project_repos      (no network: a local fake GitHub, bare repos as remotes; needs git)

Owner, 15/11/2026: "ở chức năng project cũng có khả năng thêm repo để dễ dàng tạo các dự án code, hoặc cả trong tài liệu
của agent và team cũng có khả năng thêm repo". What is guarded here, because each has a wrong version that looks fine:

1. The project's list lives in its own table (`project_repos`), never as a new column of `projects`: the qualified
   native trial reads exact column lists. Deleting the project drops the list, never a clone or a chat's branch.
2. An assistant's list rides in its own file (`assets.repos`) and survives every file and link edit, which all rebuild
   `assets` through one helper.
3. Adding a repo checks and clones it at once, so a chat that inherits it only adds a worktree.
4. A chat gets each inherited repo ONCE: a repo the person detached from that chat stays detached, a repo the project
   gains later still reaches it, a failure is retried next turn, and nothing is ever detached by the seeding.
5. The seeding runs before the engine reads the chat's folder, so the very first turn already works inside the repo.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import re
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-projrepo-")
os.environ["JAVIS_STATE_DIR"] = _STATE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from _fake_github import FakeGitHub, GOOD_TOKEN  # noqa: E402

fake = FakeGitHub()
os.environ["JAVIS_GITHUB_API"] = fake.url
BR = Path(tempfile.mkdtemp(prefix="javis-projrepo-brain-")).resolve()

import main  # noqa: E402
import agent_assets  # noqa: E402
import coding_store  # noqa: E402
import github_repos  # noqa: E402
import sessions  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra)[:400] + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


fake.add_repo("acme/app", files={"README.md": "app\n", "src/main.py": "print('hi')\n"})
fake.add_repo("acme/lib", default_branch="trunk")
fake.add_repo("acme/web")
github_repos.connect(GOOD_TOKEN)
client = TestClient(main.app, base_url="http://127.0.0.1")
st = main.get_store()
B = str(BR)


def names(rows):
    return [r["full_name"] for r in rows]


def session_names(sid):
    return [r["full_name"] for r in github_repos.session_repos(sid, B)]


# ============================================================
# 1. The project's list (sessions.project_repos)
# ============================================================
pid = st.create_project("Code", brain=B)
ch = st.set_project_repos(pid, ["acme/app", "ACME/app", " acme/lib "])
check("the list is set once per repo, whatever the case", st.project_repo_names(pid) == ["acme/app", "acme/lib"]
      and ch["added"] == ["acme/app", "acme/lib"] and ch["removed"] == [], ch)
ch = st.set_project_repos(pid, ["acme/lib", "acme/web"])
check("setting again adds and removes, a kept repo keeps its place",
      st.project_repo_names(pid) == ["acme/lib", "acme/web"] and ch == {"added": ["acme/web"], "removed": ["acme/app"]}, ch)
check("the full project carries its repos", names(st.get_project_full(pid)["repos"]) == ["acme/lib", "acme/web"])
st.set_project_repos(pid, [f"acme/r{i}" for i in range(sessions.PROJECT_REPOS_MAX + 3)])
check("at most PROJECT_REPOS_MAX repos are kept", len(st.project_repo_names(pid)) == sessions.PROJECT_REPOS_MAX)
st.set_project_repos(pid, [])
check("an empty list clears it", st.project_repo_names(pid) == [])
gone = st.create_project("Gone", brain=B)
st.set_project_repos(gone, ["acme/app"])
st.delete_project(gone)
check("deleting a project drops its list", st.list_project_repos(gone) == [])
cols = {r[1] for r in st._read("PRAGMA table_info(projects)")}
check("no new column on `projects` (the qualified trial reads exact column lists)", "repos" not in cols, cols)

# ============================================================
# 2. The drawer's route for a project: checks and clones at once
# ============================================================
r = client.post(f"/projects/{pid}/repos", data={"repos": "acme/app"})
check("POST /projects/<id>/repos stores the repo", r.status_code == 200 and names(r.json()["repos"]) == ["acme/app"], r.text)
check("the repo is cloned right away, so a chat only adds a worktree", bool(github_repos.find(B, "acme/app"))
      and Path(github_repos.find(B, "acme/app")["path"]).is_dir())
r = client.post(f"/projects/{pid}/repos", data={"repos": "acme/app,acme/missing"})
check("a repo GitHub does not know is refused with a reason, and nothing changes",
      r.status_code == 400 and "acme/missing" in r.json().get("error", "") and st.project_repo_names(pid) == ["acme/app"],
      r.text)
r = client.post(f"/projects/{pid}/repos", data={"repos": "acme/app,acme/lib"})
check("adding a second repo keeps the first", r.status_code == 200 and st.project_repo_names(pid) == ["acme/app", "acme/lib"],
      r.text)
too_many = ",".join(f"acme/x{i}" for i in range(sessions.PROJECT_REPOS_MAX + 1))
check("too many repos are refused", client.post(f"/projects/{pid}/repos", data={"repos": too_many}).status_code == 400)
check("an unknown project is 404", client.post("/projects/nope/repos", data={"repos": "acme/app"}).status_code == 404)

# ============================================================
# 3. An assistant's list (assets.repos in its own file)
# ============================================================
AG = BR / "agents"
AG.mkdir(exist_ok=True)
(AG / "lap-trinh.md").write_text("---\nname: Lập trình\nrole: Viết code\n---\nViết code gọn, có test.\n", encoding="utf-8")
(BR / "docs").mkdir(exist_ok=True)
(BR / "docs" / "quy-uoc.md").write_text("Quy ước code\n", encoding="utf-8")
r = client.post("/agents/lap-trinh/assets/repos", data={"repos": "acme/lib", "brain": B})
meta = main._read_md(AG / "lap-trinh.md")[0]
check("POST /agents/<slug>/assets/repos writes the repo into the assistant's file",
      r.status_code == 200 and agent_assets.repo_names(meta) == ["acme/lib"] and names(r.json()["repos"]) == ["acme/lib"], r.text)
check("the assistant's body and other keys are untouched",
      "Viết code gọn, có test." in (AG / "lap-trinh.md").read_text(encoding="utf-8") and meta.get("role") == "Viết code")
fid, err = main._agent_assets_sua(B, "lap-trinh", lambda m: agent_assets.them_file(m, "docs/quy-uoc.md"))
main._agent_assets_sua(B, "lap-trinh", lambda m: agent_assets.them_link(m, "https://example.com/style"))
meta = main._read_md(AG / "lap-trinh.md")[0]
check("adding a file or a link keeps the repos (every edit rebuilds `assets`)",
      fid and err is None and agent_assets.repo_names(meta) == ["acme/lib"]
      and len(agent_assets.doc(meta)["files"]) == 1 and len(agent_assets.doc(meta)["links"]) == 1, meta)
main._agent_assets_sua(B, "lap-trinh", lambda m: agent_assets.go_file(m, fid))
check("removing a file keeps them too", agent_assets.repo_names(main._read_md(AG / "lap-trinh.md")[0]) == ["acme/lib"])
g = client.get("/agents/lap-trinh/assets", params={"brain": B}).json()
check("GET /agents/<slug>/assets lists the repos too", names(g.get("repos") or []) == ["acme/lib"], g)
check("an unknown assistant is 404",
      client.post("/agents/nope/assets/repos", data={"repos": "acme/lib", "brain": B}).status_code == 404)

m0 = {"name": "x", "assets": {"files": [], "links": [], "repos": [
    {"full_name": "acme/app", "added_at": 5}, "acme/web", {"full_name": "no-slash"}, 7, {"full_name": "ACME/APP"}]}}
check("repos() keeps good rows only, once per name, oldest first",
      [r["full_name"] for r in agent_assets.repos(m0)] == ["acme/app", "acme/web"])
m1, ch = agent_assets.set_repos(m0, ["acme/web", "acme/lib"])
check("set_repos says what changed and keeps the added time of a kept repo",
      ch == {"added": ["acme/lib"], "removed": ["acme/app"]} and agent_assets.repo_names(m1)[0] == "acme/web")
m2, _ = agent_assets.set_repos({"name": "x"}, [])
check("no files, links or repos: no `assets` key left behind", "assets" not in m2)
try:
    agent_assets.set_repos({}, [f"a/b{i}" for i in range(agent_assets.REPOS_MAX + 1)])
    check("past REPOS_MAX is refused", False)
except ValueError:
    check("past REPOS_MAX is refused", True)

# ============================================================
# 4. A chat inherits the repos once (github_repos.seed_session, real git)
# ============================================================
sid = "chat-proj-one"
res = github_repos.seed_session(sid, B, B, ["acme/app"])
check("the first turn attaches the project's repo", res == {"attached": ["acme/app"], "failed": []}, res)
wt = coding_store.cwd_cua_phien(sid)
check("the chat works in its own worktree on its own branch",
      wt and Path(wt).is_dir() and wt != github_repos.find(B, "acme/app")["path"]
      and github_repos.session_repos(sid, B)[0]["branch"] == github_repos.session_branch(sid))
check("a second turn changes nothing", github_repos.seed_session(sid, B, B, ["acme/app"]) == {"attached": [], "failed": []})
res = github_repos.seed_session(sid, B, B, ["acme/app", "acme/lib"])
check("a repo the project gains later reaches the chat on its next turn",
      res["attached"] == ["acme/lib"] and session_names(sid) == ["acme/app", "acme/lib"], res)
check("the chat's main folder does not move", coding_store.cwd_cua_phien(sid) == wt)
github_repos.detach(sid, "acme/lib", B)
github_repos.seed_session(sid, B, B, ["acme/app", "acme/lib"])
check("a repo the person detached from this chat stays detached", session_names(sid) == ["acme/app"])
res = github_repos.seed_session(sid, B, B, ["acme/app", "acme/missing"])
check("a repo that fails is reported, not marked, and leaves nothing bound",
      res["attached"] == [] and [f["full_name"] for f in res["failed"]] == ["acme/missing"]
      and "acme/missing" not in github_repos.seeded(sid) and session_names(sid) == ["acme/app"], res)

plain = Path(tempfile.mkdtemp(prefix="javis-projrepo-plain-")).resolve()
folder = coding_store.them_thu_muc(str(plain), brain=B, ten="plain")
coding_store.dat_rang_buoc("chat-pinned", thu_muc_ids=[folder["id"]])
github_repos.seed_session("chat-pinned", B, B, ["acme/web"])
check("a folder pinned on the chat stays its main folder",
      coding_store.cwd_cua_phien("chat-pinned") == str(plain) and session_names("chat-pinned") == ["acme/web"])
github_repos.attach("chat-picked", B, B, ["acme/app"])
res = github_repos.seed_session("chat-picked", B, B, ["acme/app"])
check("a repo already picked in the composer is only remembered",
      res["attached"] == [] and "acme/app" in github_repos.seeded("chat-picked"))
github_repos.forget_session("chat-picked")
check("deleting a chat forgets what it was given", github_repos.seeded("chat-picked") == [])

# ============================================================
# 5. The turn: project and assistant repos join BEFORE the engine starts
# ============================================================
class WS:
    def __init__(self):
        self.frames = []

    async def send_text(self, text):
        self.frames.append(json.loads(text))


st.set_project_repos(pid, ["acme/app", "acme/lib"])
ws = WS()
run(main._seed_chat_repos(ws, {"id": "chat-turn-one", "project_id": pid}, B, None))
check("a turn in the project attaches its repos", session_names("chat-turn-one") == ["acme/app", "acme/lib"])
check("the person sees what is happening", [f["type"] for f in ws.frames] == ["status"], ws.frames)
ws2 = WS()
run(main._seed_chat_repos(ws2, {"id": "chat-turn-one", "project_id": pid}, B, None))
check("the next turn says nothing when there is nothing new", ws2.frames == [], ws2.frames)
ws3 = WS()
run(main._seed_chat_repos(ws3, {"id": "chat-agent-one"}, B, ("agent", "lap-trinh")))
check("a private chat with the assistant gets the assistant's repos", session_names("chat-agent-one") == ["acme/lib"])
ws4 = WS()
run(main._seed_chat_repos(ws4, {"id": "chat-plain"}, B, None))
check("a chat of no project and no assistant is left alone", ws4.frames == [] and session_names("chat-plain") == [])
bad = st.create_project("Bad", brain=B)
st.set_project_repos(bad, ["acme/missing"])
ws5 = WS()
run(main._seed_chat_repos(ws5, {"id": "chat-bad", "project_id": bad}, B, None))
check("a failure is said in one line and does not stop the turn",
      [f["type"] for f in ws5.frames] == ["status", "system"] and "acme/missing" in ws5.frames[-1]["content"], ws5.frames)

src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
turn = src[src.index("async def _do_turn("):]
seed_at = turn.index("await _seed_chat_repos(ws, _row0, brain, _persona)")
check("the seeding runs before the route is chosen and before any engine reads the chat's folder",
      seed_at < turn.index("_chat_provider_for_session(mcfg, _row0)") and seed_at < turn.index("_cwd_luot_chat(_row0, brain)"))

# ============================================================
# 6. The screens
# ============================================================
ui = (ROOT / "dashboard" / "sessions-ui.js").read_text(encoding="utf-8")
check("the drawer has a repo part for a project and an assistant only",
      'function pdCoRepo() { return pdCheDo === "project" || pdCheDo === "agent"; }' in ui
      and 'data-mode="repo"' in ui and "dsRepoHtml(p)" in ui)
check("the drawer saves through <its route>/repos with the team picker", 'pdPost("/repos", { repos: (names || []).join(",") })' in ui
      and "window.JavisTeamGithub.panel(box, {" in ui and "save: luuRepos" in ui)
check("the picker is loaded on demand on pages that lack it", 'window.JavisNapCham.cho("teams")' in ui)
gh = (ROOT / "dashboard" / "team-github.js").read_text(encoding="utf-8")
# 21/11/2026: the list is the shared one (github-connect.js); a project saves its names through opts.save as before.
check("the team picker can save somewhere other than a chat",
      "Promise.resolve(opts.save(next))" in gh and "if (opts.save) return saveList(" in gh)
tm = (ROOT / "dashboard" / "teams.js").read_text(encoding="utf-8")
check("a new team gets the repos picked in the create box", "attachNewTeamRepos(r.j.team, repos, missed > 0)" in tm
      and re.search(r'fetch\("/github/session/" \+ q\(sid\) \+ "/repos"', tm) is not None)
for lang in ("vi", "en"):
    d = json.loads((ROOT / "dashboard" / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
    need = ("proj.mode_repo", "proj.repos_group", "proj.repo_remove", "proj.repo_note", "proj.err_repo",
            "ags.repo_remove", "ags.repo_note")
    check(f"{lang}: every new string exists", all(d.get(k) for k in need), [k for k in need if not d.get(k)])
    check(f"{lang}: no em dash in the new strings", not any(chr(0x2014) in d[k] or chr(0x2013) in d[k] for k in need))

fake.close()
print()
if fails:
    print(f"FAIL {len(fails)}: " + "; ".join(fails))
    raise SystemExit(1)
print("ALL PASS")
