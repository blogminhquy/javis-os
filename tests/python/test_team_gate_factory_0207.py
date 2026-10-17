"""0.207.0: how the real team engine factory (`main._team_engine_for`) builds a Work step of a GATED team.

    python tests/python/test_team_gate_factory_0207.py

Only `team_engine.build` / `build_tools` are swapped for fake engines; real SQLite stores in a temporary folder; no model
is called. Checks per provider: the hub level, the native level, the turn key, the Claude PreToolUse hook, and the
refusal of a provider that cannot stop its own tools before they run.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-team-gate-f-")
TEMP = Path(tempfile.mkdtemp(prefix="javis-team-gate-fw-"))

import main  # noqa: E402
import aux_engine  # noqa: E402
import sessions  # noqa: E402
import task_store  # noqa: E402
import team_engine  # noqa: E402
import team_gate  # noqa: E402
import team_runner as TR  # noqa: E402
import team_store  # noqa: E402
import turn_context  # noqa: E402
from claude_sdk_engine import ClaudeSDK  # noqa: E402

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


SEEN_TURN = []


class Engine:
    def __init__(self):
        self.extra_config, self.hub_turn = [], False

    def is_available(self):
        return True

    async def query(self, prompt):
        SEEN_TURN.append(turn_context.current())
        yield {"type": "final", "content": "Đã làm xong phần trong phạm vi."}


_n = [0]


def world(label, work_mode=None):
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
    r = TR.TeamRunner(teams=tm, tasks=ts, sessions=ss, engine_for=main._team_engine_for, agent_info=ident)
    return r, tm, ts, tm.get(tid)


def one_job(label, provider, work_mode=None):
    seen = []
    SEEN_TURN.clear()

    def fake_build_tools(spec, base, tag, settings=None, mode="full", codex_profile=None):
        e = Engine()
        seen.append({"base": base, "mode": mode, "spec": spec, "eng": e})
        return e

    r, tm, ts, t = world(label, work_mode)
    spec = {"provider": provider, "model": "m", "source": "agent", "note": ""}
    with patch.object(main, "_team_agent_info", side_effect=ident), \
            patch.object(team_engine, "choose_spec", return_value=spec), \
            patch.multiple(team_engine, build=lambda *a, **k: Engine(), build_tools=fake_build_tools):
        job = r.submit(t["team_id"], "Làm phần việc", mentions=["agent-two"], as_job=True,
                       client_msg_id=label)["task_id"]
        run(r.dispatch_once())
    return seen, ts.get_task(job), tm, t


# Claude, gated (the default)
seen, task, tm, t = one_job("claude", "anthropic-cli")
b = seen[0]["base"] if seen else None
check("claude gated: the hub level is `gated`", b is not None and b.javis_mode == team_gate.HUB_MODE
      and ".mcp_hub_gated" in str(b.mcp_config or ".mcp_hub_gated"), getattr(b, "javis_mode", None))
check("claude gated: the engine carries the gate id for its PreToolUse hook", b is not None and b.team_gate)
check("claude gated: the gate knows the brain as a writable root",
      b is not None and SEEN_TURN and SEEN_TURN[0] and SEEN_TURN[0]["team_gate"] == b.team_gate)
check("claude gated: the step ran inside a bound team turn and finished", task["status"] == "done"
      and SEEN_TURN[0]["kenh"] == "team", (task["status"], SEEN_TURN))
check("claude gated: the gate closed with the turn", team_gate.get(b.team_gate if b else "") is None)
opts_hooks = None
try:
    sdk = ClaudeSDK(system_prompt="x", cwd=str(TEMP), tag="team-x-y")
    sdk.team_gate = "tg_test"
    opts_hooks = (sdk._options().hooks or {})
except Exception as ex:  # noqa: BLE001
    opts_hooks = {"error": repr(ex)}
check("claude: a gated engine registers a PreToolUse hook (bypassPermissions does not skip hooks)",
      "PreToolUse" in (opts_hooks or {}), opts_hooks)
deny = run(sdk._team_gate_hook({"tool_name": "Bash", "tool_input": {"command": "rm -rf x"}}, "id", None))
check("claude: the hook denies an outside action with no live gate (fail closed)",
      deny.get("hookSpecificOutput", {}).get("permissionDecision") == "deny", deny)

# Codex, gated: natives in its own sandbox at auto, hub tools at gated with the turn key
with patch.object(main.claude_cli, "codex_sandbox_cho_mode", return_value="workspace-write"), \
        patch.object(main.openai_oauth, "write_codex_auth", return_value=None):
    seen, task, tm, t = one_job("codex", aux_engine.CODEX)
e = seen[0]["eng"] if seen else None
check("codex gated: built at auto (own sandbox, no network)", seen and seen[0]["mode"] == "auto", seen and seen[0]["mode"])
check("codex gated: hub level overridden to gated and the turn key on", e is not None and e.hub_turn
      and any(str(x).endswith('"gated"') for x in e.extra_config), getattr(e, "extra_config", None))
check("codex gated: ChatGPT apps off and no shell network", e is not None
      and any(str(x).endswith("=false") and "apps" in str(x) for x in e.extra_config)
      and "sandbox_workspace_write.network_access=false" in e.extra_config, getattr(e, "extra_config", None))
cb = seen[0]["base"] if seen else None
check("codex gated: works in the team's own folder, not at the brain root",
      cb is not None and Path(cb.cwd).parent.name == "teams", getattr(cb, "cwd", None))
with patch.object(main.claude_cli, "codex_sandbox_cho_mode", return_value=None):
    seen, task, tm, t = one_job("codex-nosandbox", aux_engine.CODEX)
check("codex gated without its sandbox: refused before the engine, with the reason",
      not seen and task["status"] == "team_blocked" and "sandbox" in (task["block_reason"] or ""), task["block_reason"])

# API engines: every tool through the hub in-process, at gated
with patch.object(aux_engine, "availability", return_value=(True, "")):
    seen, task, tm, t = one_job("api", "openrouter")
check("api gated: built at the gated hub level", seen and seen[0]["mode"] == team_gate.HUB_MODE, seen and seen[0]["mode"])

# Grok: shell denied at auto, hub at auto (no turn key, fail closed)
seen, task, tm, t = one_job("grok", aux_engine.GROK_CLI)
check("grok gated: refused before the engine (shared config file), with the reason",
      not seen and task["status"] == "team_blocked" and "Grok" in (task["block_reason"] or ""), task["block_reason"])
with patch.object(main, "_codex_user_mcp_servers", return_value=["github"]), \
        patch.object(main.claude_cli, "codex_sandbox_cho_mode", return_value="workspace-write"):
    seen, task, tm, t = one_job("codex-extra", aux_engine.CODEX)
check("codex gated with the user's own MCP servers: refused, named", not seen and "github" in (task["block_reason"] or ""),
      task["block_reason"])

# Antigravity: cannot pre-block its own tools -> refused with an explanation, nothing built
seen, task, tm, t = one_job("agy", aux_engine.ANTIGRAVITY)
check("antigravity gated: refused before the engine, job stopped with the reason",
      not seen and task["status"] == "team_blocked" and "Antigravity" in (task["block_reason"] or "")
      and "Claude, Codex" in (task["block_reason"] or ""), task["block_reason"])

# Full: the owner's switch gives the 0.194.0 private-chat level, no gate
seen, task, tm, t = one_job("full", "anthropic-cli", work_mode="full")
b = seen[0]["base"] if seen else None
check("full: Claude at full, no gate id, no team turn bound", b is not None and b.javis_mode == "full"
      and not b.team_gate and SEEN_TURN == [None], (getattr(b, "javis_mode", None), SEEN_TURN))
seen, task, tm, t = one_job("agy-full", aux_engine.ANTIGRAVITY, work_mode="full")
check("full: Antigravity runs (the owner chose full)", seen and seen[0]["mode"] == "full")

print()
if fails:
    print(f"FAILED {len(fails)}: {fails}")
    raise SystemExit(1)
print("ALL OK")
