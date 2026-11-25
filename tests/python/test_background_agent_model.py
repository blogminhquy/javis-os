"""A Kanban job, reminder or loop that runs as an assistant uses that assistant's model and level.

    python tests/run.py background_agent_model      (no network, no CLI needed)

Goes through the REAL features main.py wires (`tasks_feature`, `reminders_feature`, `loop_feature`) and the real
background router (`aux_engine.swap`); only the engines' `query` is faked, so no model is called. What is recorded is
what the engine that was actually built would send: provider, model, effort.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

_TMP = Path(tempfile.mkdtemp(prefix="javis-bg-agent-"))
os.environ["JAVIS_STATE_DIR"] = str(_TMP / "state")
_FAKE_HOME = _TMP / "home"
(_FAKE_HOME / ".claude").mkdir(parents=True, exist_ok=True)
os.environ["HOME"] = str(_FAKE_HOME)
os.environ["USERPROFILE"] = str(_FAKE_HOME)
for v in ("CODEX_HOME", "GROK_HOME", "CLAUDE_CONFIG_DIR"):
    os.environ.pop(v, None)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BRAIN = (_TMP / "brain").resolve()
(BRAIN / "agents").mkdir(parents=True)
AGENTS = {
    "an": "model: gpt-6-luna\nmodel_provider: openai-oauth\nreasoning: xhigh\n",
    "binh": "model: claude-sonnet-5-5\nmodel_provider: anthropic-cli\nreasoning: high\n",
    "chi": "reasoning: high\n",
    "dung": "",
    "em": "model_provider: openai-oauth\n",
}
for slug, extra in AGENTS.items():
    (BRAIN / "agents" / f"{slug}.md").write_text(f"---\nname: {slug}\nrole: Thành viên\n{extra}---\nBạn là {slug}.\n",
                                                 encoding="utf-8", newline="\n")
B = str(BRAIN)

import main  # noqa: E402
import aux_engine  # noqa: E402
import claude_cli  # noqa: E402
import codex_models  # noqa: E402
import reminders  # noqa: E402
import self_improve  # noqa: E402
import tasks  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

codex_models._EFFORTS["gpt-6-luna"] = ["low", "medium", "high", "xhigh", "max"]

CLAUDE, CODEX, GROQ = "anthropic-cli", "openai-oauth", "groq"
fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:500]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


MODEL = {"order": [CODEX, CLAUDE, GROQ], "main": {"provider": CODEX, "model": "gpt-6-luna"}, "reasoning": "ultra",
         "profiles": {CODEX: {"model": "gpt-6-luna", "reasoning": "ultra"},
                      CLAUDE: {"model": "claude-sonnet-5-5", "reasoning": "low"},
                      GROQ: {"model": "llama-4", "reasoning": "medium"}},
         "auxiliary": {"provider": CLAUDE, "model": "claude-haiku-5-5", "reasoning": "low", "auto": False},
         "groq_api_key": "gsk_test", "catalog": {CODEX: ["gpt-6-luna"]}}
_real_settings = main.cfgmod.read_settings


def settings():
    s = dict(_real_settings() or {})
    s["model"] = MODEL
    return s


RAN = []   # (provider, model, effort) of every engine that was asked
ANSWER = '{"pass":true,"reason":"ok"} Đã làm xong việc được giao, kết quả đã ghi lại đầy đủ.'
WEEKLY = "You've hit your weekly limit · resets 7am (Asia/Ho_Chi_Minh)"
REFUSE = set()   # providers that answer with the quota refusal


class FakeClaude:
    def __init__(self, system_prompt=None, cwd=None, tag="chat", allowed_tools=None, model=None):
        self.system_prompt, self.cwd, self.tag, self.allowed_tools = system_prompt, cwd, tag, allowed_tools
        self.model, self.effort, self.disallowed_tools, self.max_wall_s = model, None, None, 0
        self.mcp_config, self.mcp_strict, self.session_id, self.extra_config = None, False, None, []

    def is_available(self):
        return True

    async def query(self, prompt):
        RAN.append((CLAUDE, self.model, self.effort))
        yield {"type": "final", "content": ANSWER}


async def codex_query(self, prompt):
    level = ""
    for item in self.extra_config:
        if str(item).startswith("model_reasoning_effort="):
            level = str(item).split("=", 1)[1]
    RAN.append((CODEX, self.model, level))
    if CODEX in REFUSE:
        yield {"type": "final", "content": WEEKLY, "is_error": True}
        return
    yield {"type": "final", "content": ANSWER}


async def api_query(self, prompt):
    RAN.append((self.provider, self.model, self.reasoning))
    yield {"type": "final", "content": ANSWER}


def rest(*engines):
    """Start from every card able to run, then put the named ones out of quota."""
    main._PIN_LIMITED.clear()
    main._SIGNED_OUT.clear()
    for prov in (CODEX, CLAUDE):
        main.model_routing.clear_rest(prov, main.plan_accounts.MAIN)
    for engine in engines:
        main._note_pin_limit(engine)
    RAN.clear()


client = TestClient(main.app, base_url="http://127.0.0.1:8080")
main.tasks_feature.store.set_orchestration(B, "off")
_JOB = {"n": 0}


def job(slug, light=False):
    """A Kanban job assigned to `slug` with the real "assign" route, executed by the real worker step."""
    _JOB["n"] += 1
    r = client.post(f"/agents/{slug}/jobs", params={"brain": B},
                    json={"text": f"Soạn báo cáo số {_JOB['n']}", "nonce": f"n{_JOB['n']}"})
    task = main.tasks_feature.store.get_task(r.json()["task_id"])
    if light:
        task = dict(task, metadata=dict(task.get("metadata") or {}, effort="light"))
    RAN.clear()
    out = asyncio.run(main.tasks_feature._execute(task))
    return list(RAN), out, task


def remind(slug):
    RAN.clear()
    asyncio.run(main.reminders_feature._run_task(B, "Gửi báo cáo ngày.", "full", agent=slug))
    return list(RAN)


def loop(slug):
    folder = BRAIN / "Javis" / "loops"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"vong-{slug or 'x'}.md").write_text(
        f"---\nname: Vong {slug}\ngoal: custom\nmode: auto\nenabled: false\nagent: {slug}\n---\nLàm một việc.\n",
        encoding="utf-8")
    RAN.clear()
    asyncio.run(main.loop_feature.run_cycle(B, f"vong-{slug or 'x'}", "manual"))
    return list(RAN)


BACKGROUND = (CLAUDE, "claude-haiku-5-5", "low")
AN = (CODEX, "gpt-6-luna", "xhigh")
BINH = (CLAUDE, "claude-sonnet-5-5", "high")

with patch.object(main.cfgmod, "read_settings", settings), \
        patch.object(tasks, "claude_engine", FakeClaude), \
        patch.object(reminders, "claude_engine", FakeClaude), \
        patch.object(self_improve, "claude_engine", FakeClaude), \
        patch.object(claude_cli, "find_codex_cli", lambda: "codex"), \
        patch.object(main, "find_codex_cli", lambda: "codex"), \
        patch.object(claude_cli.CodexCLI, "query", codex_query), \
        patch.object(claude_cli.CodexCLI, "is_available", lambda self: True), \
        patch.object(aux_engine._ApiAuxEngine, "query", api_query), \
        patch.object(claude_cli, "co_co", lambda *_a: True), \
        patch.object(main, "_write_codex_profile", lambda *a, **k: None), \
        patch.object(main.openai_oauth, "write_codex_auth", lambda *a, **k: None), \
        patch.object(main, "_routing_connected_ids", lambda _s=None: list(MODEL["order"])), \
        patch.object(main.inbox, "add", lambda *a, **k: {}):

    # 1. every card able to run: the assistant's own model and level, for the three kinds of background work
    rest()
    ran, out, task = job("an")
    check("Kanban as an assistant on ChatGPT: its model and level", ran == [AN], (ran, out[1]))
    check("Kanban records the provider that really ran", out[3].get("provider") == CODEX
          and not out[3].get("fallback_from"), out[3])
    ran, _, _ = job("binh")
    check("Kanban as an assistant on Claude: its model and level", ran == [BINH], ran)
    ran, _, _ = job("binh", light=True)
    check("a job judged light does not lower the assistant's level", ran == [BINH], ran)
    check("reminder as an assistant on ChatGPT", remind("an") == [AN], RAN)
    check("reminder as an assistant on Claude", remind("binh") == [BINH], RAN)
    ran = loop("an")
    check("loop round runs on the assistant's model and level", ran[:1] == [AN], ran)
    check("loop check stays on the background model", ran[1:] == [BACKGROUND], ran)
    ran = loop("binh")
    check("loop round as an assistant on Claude", ran[:1] == [BINH], ran)

    # 2. assistants that chose only part of it
    ran, _, _ = job("chi")
    check("level only: background model at the assistant's level",
          ran == [(CLAUDE, "claude-haiku-5-5", "high")], ran)
    ran, _, _ = job("em")
    check("card only: that card's model, assistant default level", ran == [(CODEX, "gpt-6-luna", "medium")], ran)
    ran, _, _ = job("dung")
    check("nothing chosen: background model as before", ran == [BACKGROUND], ran)
    check("reminder, nothing chosen: background model", remind("dung") == [BACKGROUND], RAN)
    check("reminder with no assistant: background model", remind("") == [BACKGROUND], RAN)
    cli = main.tasks_feature._base_cli(task, None, "suggest", "acceptance")
    RAN.clear()
    asyncio.run(main.tasks_feature._query(cli, "check"))
    check("the Kanban checker stays on the background model", RAN == [BACKGROUND], RAN)

    # 3. the assistant's card is out of quota: the highest card with quota, with that card's model and level
    rest("codex")
    down = (CLAUDE, "claude-sonnet-5-5", "low")
    ran, _, _ = job("an")
    check("ChatGPT out of quota: Kanban moves to Claude with the card's level", ran == [down], ran)
    rest("codex")
    check("ChatGPT out of quota: reminder moves to Claude with the card's level", remind("an") == [down], RAN)
    rest("codex")
    ran = loop("an")
    check("ChatGPT out of quota: loop round moves to Claude with the card's level", ran[:1] == [down], ran)

    rest("claude-code")
    top = (CODEX, "gpt-6-luna", "max")   # the card level, fitted to what Codex takes
    ran, _, _ = job("binh")
    check("Claude out of quota: Kanban moves up to ChatGPT, the top card", ran == [top], ran)
    rest("claude-code")
    check("Claude out of quota: reminder moves up to ChatGPT", remind("binh") == [top], RAN)
    rest("claude-code", "codex")
    third = (GROQ, "llama-4", "medium")
    check("Claude and ChatGPT out of quota: reminder runs on the third card", remind("binh") == [third], RAN)

    # 4. the refusal arrives during the job: the same job moves to another card, on that card's model and level
    for name, run in (("Kanban", lambda: job("an")[0]), ("reminder", lambda: remind("an"))):
        rest()
        REFUSE.add(CODEX)
        ran = run()
        REFUSE.clear()
        check(f"{name}: refused during the job, the next card finishes it at its level", ran == [AN, down], ran)

    # 5. the card is back: the assistant's own model again, nothing saved changed
    rest()
    ran, _, _ = job("an")
    check("card back: the assistant's own model and level again", ran == [AN], ran)
    check("assistant files untouched", all((BRAIN / "agents" / f"{slug}.md").read_text("utf-8").count(extra) == 1
                                           for slug, extra in AGENTS.items() if extra))
    check("model order untouched", MODEL["order"] == [CODEX, CLAUDE, GROQ] and MODEL["main"]["provider"] == CODEX)

print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
