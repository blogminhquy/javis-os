"""0.194.0: Work and Help steps of a team job run with the member's own toolkit; chat replies stay text only.

    python tests/run.py team_work_tools

Owner, 17/10/2026: "team phải đầy đủ các quyền thì mới làm việc được". Goes through the REAL factory
`main._team_engine_for` (only `team_engine.build` / `build_tools` swapped for fake engines) and real SQLite stores in a
temporary folder; no model is called.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-tools-")
TEMP = Path(tempfile.mkdtemp(prefix="javis-team-tools-w-"))

import main  # noqa: E402
import aux_engine  # noqa: E402
import sessions  # noqa: E402
import task_store  # noqa: E402
import team_engine  # noqa: E402
import team_runner as TR  # noqa: E402
import team_store  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


def run(coro):
    return asyncio.run(coro)


INFO = {"agent-one": {"slug": "one", "name": "One", "system": "You are One.", "model": "", "model_provider": ""},
        "agent-two": {"slug": "two", "name": "Two", "system": "You are Two.", "model": "", "model_provider": ""}}


def ident(root, key):
    return INFO.get(key)


class Engine:
    def __init__(self, events):
        self.events, self.prompts = events, []

    def is_available(self):
        return True

    async def query(self, prompt):
        self.prompts.append(prompt)
        for ev in self.events:
            yield ev


_n = [0]


def world(label, engine_for=None, work_mode="full"):
    """`work_mode` full: these cases check the 0.194.0 private-chat level, which since 0.207.0 is the owner's choice
    (`teams.work_mode`); the gated default is covered by test_team_gate_factory_0207.py."""
    _n[0] += 1
    d = TEMP / f"{_n[0]:02d}-{label}"
    (d / "agents").mkdir(parents=True)
    for k in INFO:
        (d / "agents" / f"{INFO[k]['slug']}.md").write_text(f"---\nname: {INFO[k]['name']}\nrole: Helper\n---\n",
                                                            encoding="utf-8", newline="\n")
    ss = sessions.SessionStore(db_path=d / "chat.db")
    ts = task_store.TaskStore(d / "kanban.sqlite3")
    tm = team_store.TeamStore(d / "team.sqlite3")
    tid = team_store.new_team_id()
    sid = ss.create_session(brain=str(d), channel=f"team:{tid}")
    tm.create_team(str(d), label, "", sid, team_id=tid)
    for k in INFO:
        tm.add_member(tid, k, INFO[k]["slug"])
    tm.set_leader(tid, "agent-one")
    if work_mode:
        tm.set_work_mode(tid, work_mode)
    r = TR.TeamRunner(teams=tm, tasks=ts, sessions=ss, engine_for=engine_for or main._team_engine_for,
                      agent_info=ident)
    return r, tm, ts, ss, tm.get(tid), d


TOOL_RUN = [{"type": "tool_call", "name": "Write", "input": {"file_path": "web/index.html"}},
            {"type": "tool_result", "content": "ok"},
            {"type": "usage", "input_tokens": 9, "output_tokens": 4},
            {"type": "final", "content": "Đã ghi web/index.html và deploy, link: https://x.pages.dev"}]


# ═════ The real factory: Work steps go through build_tools with the member's toolkit ═════
seen = {"text": [], "tools": []}


def fake_build(spec, base, tag, settings=None):
    seen["text"].append(base)
    return Engine(TOOL_RUN)


def fake_build_tools(spec, base, tag, settings=None, mode="full", codex_profile=None):
    seen["tools"].append({"base": base, "mode": mode, "spec": spec, "codex_profile": codex_profile})
    return Engine(TOOL_RUN)


r, tm, ts, ss, t, d = world("work")
with patch.object(main, "_team_agent_info", side_effect=ident), \
        patch.multiple(team_engine, build=fake_build, build_tools=fake_build_tools):
    job = r.submit(t["team_id"], "Làm trang bán hàng rồi deploy", mentions=["agent-two"], as_job=True,
                   client_msg_id="w1")["task_id"]
    run(r.dispatch_once())
task = ts.get_task(job)
check("a Work step that calls tools and returns a final finishes the job", task["status"] == "done"
      and "pages.dev" in (task["result"] or ""), task)
check("the Work step was built through build_tools, not the text-only build",
      len(seen["tools"]) >= 1 and seen["text"] == [], (len(seen["tools"]), len(seen["text"])))
tb = seen["tools"][0]["base"] if seen["tools"] else None
check("the tool engine runs in the brain (no pinned folder), like a private chat",
      tb is not None and Path(tb.cwd).resolve() == Path(main._brain_root(t["brain_id"])).resolve(), getattr(tb, "cwd", None))
check("the tool engine has the hub attached at the private chat level (full) and knows its brain",
      tb is not None and tb.javis_mode == "full" and seen["tools"][0]["mode"] == "full"
      and Path(tb.javis_vault).resolve() == Path(main._brain_root(t["brain_id"])).resolve()
      and not getattr(tb, "allowed_tools", None), (getattr(tb, "javis_mode", None), getattr(tb, "allowed_tools", None)))
check("the tool engine is not the empty team sandbox", tb is not None and "team_cwd" not in str(tb.cwd))
check("Codex tool turns get the Javis MCP profile", seen["tools"] and seen["tools"][0]["codex_profile"] is main._write_codex_profile)
check("the Work prompt carries the tool note, not the text-only note",
      tb is not None and TR.WORK_TOOLS_NOTE in (tb.system_prompt or "") and TR.TEXT_ONLY_NOTE not in (tb.system_prompt or ""))
turns = tm.turns(t["team_id"])
check("the Work turn is settled ok with its tokens", [(x["role"], x["status"], x["tokens_in"]) for x in turns
                                                      if x["role"] == "work"] == [("work", "ok", 9)], turns)

# A pinned working folder: the Work step runs inside it.
r, tm, ts, ss, t, d = world("folder")
proj = d / "du-an"
(proj / "web").mkdir(parents=True)
seen["tools"].clear()
seen["text"].clear()
with patch.object(main, "_team_agent_info", side_effect=ident), \
        patch.object(main.coding_store, "cwd_cua_phien", side_effect=lambda sid: str(proj)), \
        patch.multiple(team_engine, build=fake_build, build_tools=fake_build_tools):
    job = r.submit(t["team_id"], "Sửa trang", mentions=["agent-two"], as_job=True, client_msg_id="f1")["task_id"]
    run(r.dispatch_once())
check("with a pinned folder the Work step runs inside that folder, files still belong to the brain",
      seen["tools"] and Path(seen["tools"][0]["base"].cwd) == proj
      and Path(seen["tools"][0]["base"].javis_vault).resolve() == Path(main._brain_root(t["brain_id"])).resolve(),
      [getattr(x["base"], "cwd", None) for x in seen["tools"]])

# Chat replies stay text only: built through `build`, a tool call breaks the turn.
r, tm, ts, ss, t, d = world("reply")
seen["tools"].clear()
seen["text"].clear()
with patch.object(main, "_team_agent_info", side_effect=ident), \
        patch.multiple(team_engine, build=fake_build, build_tools=fake_build_tools):
    outs = run(r.run_replies(r.submit(t["team_id"], "Chào", client_msg_id="r1")))
check("a chat reply is built through the text-only build", seen["text"] and seen["tools"] == [])
check("a chat reply that calls a tool is still an error (text only)", [o["status"] for o in outs] == ["error"], outs)
check("the chat reply engine is the empty sandbox, not the brain",
      seen["text"] and "team_cwd" in str(seen["text"][0].cwd), getattr(seen["text"][0], "cwd", None) if seen["text"] else None)

# The test guard: without a swapped build_tools no real engine is built.
r, tm, ts, ss, t, d = world("guard")
with patch.object(main, "_team_agent_info", side_effect=ident), \
        patch.object(team_engine, "build", fake_build):
    job = r.submit(t["team_id"], "Làm", mentions=["agent-two"], as_job=True, client_msg_id="g1")["task_id"]
    run(r.dispatch_once())
check("JAVIS_NO_REAL_TEAM_ENGINE stops a real tool engine too (job blocked, nothing built)",
      ts.get_task(job)["status"] == "team_blocked", ts.get_task(job))

# ═════ The outcome contract of a tool turn ═════
o = TR.ToolTurnOutcome()
for ev in TOOL_RUN:
    o.note(ev)
check("ToolTurnOutcome: tool calls are normal, the final is the answer, calls are counted",
      o.result()["text"].startswith("Đã ghi") and o.tool_calls == 1)
for bad, kind in (([{"type": "final", "content": "x", "is_error": True}], "final_error"),
                  ([{"type": "tool_call", "name": "Bash"}], "no_final"),
                  ([{"type": "final", "content": "  "}], "empty"),
                  ([{"type": "final", "content": "ok"}, {"type": "error", "content": "socket"}], "error_after_final")):
    o = TR.ToolTurnOutcome()
    for ev in bad:
        o.note(ev)
    try:
        o.result()
        got = None
    except TR.EngineOutcomeError as ex:
        got = ex.kind
    check(f"ToolTurnOutcome keeps the error rules: {kind}", got == kind, got)

# ═════ team_engine: which providers run tool turns, and how they are built ═════
main_spec = {"provider": "anthropic-cli", "model": ""}
sp = team_engine.choose_spec("grok-4", "grok-cli", main_spec, lambda m, p: p, lambda s: (True, ""), tools=True)
check("choose_spec(tools=True) keeps a Grok Build member on Grok Build", sp["provider"] == "grok-cli" and sp["source"] == "agent", sp)
sp = team_engine.choose_spec("grok-4", "grok-cli", main_spec, lambda m, p: p, lambda s: (True, ""))
check("choose_spec without tools still moves Grok Build to the main model (text-only contract)", sp["source"] == "main", sp)


class Base:
    def __init__(self):
        self.cwd, self.tag, self.system_prompt = str(TEMP), "t", "SYS"
        self.javis_vault, self.javis_mode, self.model = str(TEMP), "full", None


b = Base()
check("build_tools Claude: the caller's engine, with the member's model", team_engine.build_tools(
    {"provider": "anthropic-cli", "model": "claude-x"}, b, "t") is b and b.model == "claude-x")
with patch.object(aux_engine, "availability", return_value=(True, "")):
    eng = team_engine.build_tools({"provider": "openrouter", "model": "m"}, Base(), "t", mode="full")
check("build_tools API: a tool-calling API engine on the brain at the full level",
      isinstance(eng, aux_engine._ApiAuxEngine) and not getattr(eng, "no_tools", False)
      and eng.javis_mode == "full" and eng.vault_root == str(TEMP), vars(eng))
with patch.object(aux_engine, "availability", return_value=(True, "")), \
        patch.object(aux_engine, "_build_codex", side_effect=lambda sp, base, mode, tag, prof: ("codex", mode, prof)):
    eng = team_engine.build_tools({"provider": "openai-oauth", "model": "gpt"}, Base(), "t", mode="full",
                                  codex_profile=main._write_codex_profile)
check("build_tools Codex: the background Codex builder with the hub profile and the level",
      eng == ("codex", "full", main._write_codex_profile), eng)
with patch.object(aux_engine, "availability", return_value=(False, "chưa đăng nhập")):
    try:
        team_engine.build_tools({"provider": "openai-oauth", "model": "gpt"}, Base(), "t")
        why = None
    except team_engine.TeamEngineUnavailable as ex:
        why = ex.reason
check("build_tools: a provider that is not ready says why (no silent fallback)", why == "chưa đăng nhập", why)

# ═════ Runner: tool turns of one team take turns ═════


class Overlap:
    def __init__(self):
        self.live, self.peak, self.roles = 0, 0, []

    def engine_for(self, team, key, role):
        async def run_(req):
            self.roles.append((role, bool(req.get("tool_turn"))))
            self.live += 1
            self.peak = max(self.peak, self.live)
            await asyncio.sleep(0.15)
            self.live -= 1
            return {"text": f"{key} xong"}
        return "fake", "fake", run_


def two_jobs(label, slots=None, own_folders=False):
    """Two teams of the SAME brain, one job each: the pool runs them side by side (one job per team already)."""
    ov = Overlap()
    r, tm, ts, ss, t, d = world(label, engine_for=ov.engine_for)
    tid2 = team_store.new_team_id()
    sid2 = ss.create_session(brain=str(d), channel=f"team:{tid2}")
    tm.create_team(str(d), label + "-2", "", sid2, team_id=tid2)
    for k in INFO:
        tm.add_member(tid2, k, INFO[k]["slug"])
    tm.set_leader(tid2, "agent-one")
    # Different members: one member already runs one turn at a time (busy lock), the lock here is about the brain.
    for i, (team_id, who) in enumerate(((t["team_id"], "agent-two"), (tid2, "agent-one"))):
        r.submit(team_id, f"Việc {i}", mentions=[who], as_job=True, client_msg_id=f"{label}{i}")
    if slots is not None:
        r.tool_slots = slots
    if own_folders:
        r.work_dir = lambda team: "/work/" + team["team_id"]   # each team pinned its own working folder

    async def go():
        await r.dispatch_once()
        await r.wait_jobs()
    run(go())
    return ov


# 0.260.0: the tool slot is per working folder (pinned folder, else the brain) and TOOL_SLOTS wide.
ctl = two_jobs("slots-default")
ov = two_jobs("slots-one", slots=1)
own = two_jobs("slots-one-own-folders", slots=1, own_folders=True)
check("default: Work steps of two teams in one brain run side by side", ctl.peak == 2, (ctl.peak, ctl.roles))
check("one slot (JAVIS_TEAM_TOOL_SLOTS=1): Work steps in one folder run one at a time", ov.peak == 1
      and len(ov.roles) >= 2, (ov.peak, ov.roles))
check("one slot, each team has its own pinned folder: they still run side by side", own.peak == 2,
      (own.peak, own.roles))
check("both Work steps were tool turns", all(tt for role, tt in ov.roles if role in TR.TOOL_ROLES)
      and sum(role in TR.TOOL_ROLES for role, _ in ov.roles) >= 2, ov.roles)

# ═════ Wording ═════
check("TOOL_ROLES are exactly Work and Help", TR.TOOL_ROLES == ("work", "help"))
check("the tool note tells the member to do the work itself, not to send the owner to a private chat",
      "TỰ LÀM" in TR.WORK_TOOLS_NOTE and "chat riêng" in TR.WORK_TOOLS_NOTE)
check("the text-only note points the member to a job instead of a private chat",
      "giao thành việc" in TR.TEXT_ONLY_NOTE and "Đừng bảo chủ nhóm chuyển sang chat riêng" in TR.TEXT_ONLY_NOTE)
for name in ("team_runner.py", "team_engine.py", "team_docs.py"):
    src = (ROOT / "server" / name).read_text(encoding="utf-8")
    check(f"{name} has no long dash", "—" not in src and "–" not in src)

print()
print(("FAIL - " + str(len(fails)) + " check(s)") if fails else "PASS - test_team_work_tools")
raise SystemExit(1 if fails else 0)
