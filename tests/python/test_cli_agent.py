"""POST /chat and /chat/stream accept an `agent` field: the slug of an agent in the chosen brain.

    python tests/run.py cli_agent        (no network, scratch brains)

An integration that runs a fixed job through Javis over HTTP wants the quick version on the
agent's own model (a faster one) and the full version on the main model. Before this field the
endpoints silently ignored `agent` and every call ran Javis Core on the main model.

What is pinned, through the real endpoints and the real CLI shell (`_tg_answer`), with only the
model engine faked:
  1. `agent` names an agent of the resolved brain: the turn runs with that agent's prompt (role,
     body, skills) and model, inside that brain. The turn ends like an agent chat on the dashboard
     (the /chat caller is the authenticated owner): JAVIS_LESSON / JAVIS_RULE lines are stripped
     from the answer and recorded (lesson store, owner rules), and the run is logged.
  2. The agent is not in the resolved brain, or the brain does not exist: 400 and no turn runs.
     A wrong brain must NOT fall back to the default brain, where an agent with the same slug
     would answer instead.
  3. No `agent`: the turn is the old one (main model, Javis prompt, and a wrong brain still falls
     back to the default brain exactly as before).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-cli-agent-")
# The default brain lives under BRAINS_DIR: point it at a scratch folder so this test never
# writes into the repo's brains/.
os.environ["BRAINS_DIR"] = tempfile.mkdtemp(prefix="javis-cli-agent-brains-")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  [{detail!r}]"))
    if not cond:
        _fails.append(name)


def write_agent(brain, slug, body, model=""):
    d = Path(brain) / "agents"
    d.mkdir(parents=True, exist_ok=True)
    lines = ["---", "type: agent", f"name: {slug}", "role: analyst",
             "skills: [check-merchant, cpc-estimate]"]
    if model:
        lines.append(f"model: {model}")
    lines.append("---")
    (d / f"{slug}.md").write_text("\n".join(lines) + "\n" + body + "\n", encoding="utf-8")


BRAIN = tempfile.mkdtemp(prefix="javis-cli-agent-spy-")
OTHER = tempfile.mkdtemp(prefix="javis-cli-agent-other-")
DEFAULT = str(main._default_brain_dir())
write_agent(BRAIN, "quick-check", "QUICK CHECK ROLE BODY", model="sonnet")
write_agent(OTHER, "other-only", "OTHER BRAIN AGENT BODY", model="haiku")
# Two agents on "Default" (the main model), for the session isolation checks on an API engine.
write_agent(BRAIN, "api-one", "API ONE ROLE BODY")
write_agent(BRAIN, "api-two", "API TWO ROLE BODY")
# An agent that still names an API model Codex cannot run: the Codex branch coerces it.
write_agent(BRAIN, "codex-stale", "CODEX STALE ROLE BODY", model="gpt-4o")
# Same slug as BRAIN's agent, in the default brain: a mistyped brain must never reach this one.
write_agent(DEFAULT, "quick-check", "DEFAULT BRAIN IMPOSTOR BODY", model="haiku")


# ---------------------------------------------------------------- fakes
# The lesson and the rule the fake engine emits at the end of every answer.
LESSON = "cite the merchant domain in every report"
RULE = "always answer in short bullet points"


class FakeClaude:
    """Claude Code engine stand-in: records what the turn handed it, answers with a lesson line and
    a rule line, as an agent's answer ends."""
    runs = []

    def __init__(self, **kw):
        self.system_prompt = kw.get("system_prompt") or ""
        self.cwd = kw.get("cwd")
        self.model = None
        self.session_id = None

    def reset_session(self):
        self.session_id = None

    async def query(self, prompt):
        FakeClaude.runs.append({"system_prompt": self.system_prompt, "model": self.model, "cwd": self.cwd,
                                "engine": id(self)})
        yield {"type": "text", "content": "Report ready."}
        yield {"type": "final",
               "content": "Report ready.\nJAVIS_LESSON: " + LESSON + "\nJAVIS_RULE: " + RULE,
               "session_id": "fake-1", "tokens_in": 10, "tokens_out": 5, "cost_usd": 0}


class Recorder:
    """Stand-in for the fast path and the adaptive context: counts calls, never takes the turn."""

    def __init__(self):
        self.calls = 0

    def prepare(self, *a, **k):
        self.calls += 1
        return SimpleNamespace(action="skip", system_prompt="")


async def _no_schedule(message, brain):
    return None


async def _no_learn(*a, **k):
    return None


FAST, ADAPTIVE = Recorder(), Recorder()
main._FAST_PATH = FAST
main._get_adaptive_context = lambda: ADAPTIVE
main.claude_engine = lambda **kw: FakeClaude(**kw)
main._apply_mcp = lambda *a, **k: None
main._chat_provider = lambda mcfg: ("anthropic-cli", "cli", "", "opus")   # the main model
main.build_system_prompt = lambda *a, **k: "JAVIS MAIN PROMPT"
main.usage_store.record = lambda *a, **k: None
main.channel_context.collect_turn_files = lambda *a, **k: []
main._schedule_cancel_action = _no_schedule
main.learn_feature.enqueue = _no_learn

c = TestClient(main.app, base_url="http://127.0.0.1:8080")


def chat(path="/chat", **data):
    data.setdefault("message", "analyse merchant.example")
    return c.post(path, data=data)


def same_dir(a, b):
    return bool(a) and Path(a).resolve() == Path(b).resolve()


def stream_events(r):
    return [json.loads(ln[6:]) for ln in r.text.splitlines() if ln.startswith("data: ")]


# ================================================================
# 1. An agent of the resolved brain runs with its own prompt and model
# ================================================================
r = chat(brain=BRAIN, session="s1", agent="quick-check")
body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
run = FakeClaude.runs[-1] if FakeClaude.runs else {}
sp = run.get("system_prompt") or ""
check("agent: 200 and ok", r.status_code == 200 and body.get("ok") is True, r.text[:200])
check("agent: runs on the agent's model, not the main model", run.get("model") == "sonnet", run.get("model"))
check("agent: system prompt carries the agent's role body", "QUICK CHECK ROLE BODY" in sp, sp[:200])
check("agent: system prompt lists the agent's skills", "check-merchant" in sp and "cpc-estimate" in sp)
check("agent: Javis's own prompt is not used", "JAVIS MAIN PROMPT" not in sp)
check("agent: the CLI channel block is still there", "Terminal KHÔNG render markdown" in sp, sp[-300:])
check("agent: runs inside the chosen brain", same_dir(run.get("cwd"), BRAIN), run.get("cwd"))
check("agent: fast path and adaptive context are skipped (both answer in Javis's voice)",
      FAST.calls == 0 and ADAPTIVE.calls == 0, (FAST.calls, ADAPTIVE.calls))
check("agent: JAVIS_LESSON / JAVIS_RULE never reach the client",
      body.get("text") == "Report ready.", body.get("text"))
# The turn ends through the dashboard's agent handler (_ket_luot_agent): lessons go to the agent's
# private-chat lesson store, owner rules to its MEMORY.md, and the run to its run log.
check("precondition: learning is on for the test brain",
      main.memory_control.learning_enabled(main._brain_memory_dir(BRAIN)))
check("agent: the JAVIS_LESSON line is recorded in the agent's lesson store",
      LESSON in main._dm_lessons_prompt(BRAIN, "quick-check", ""))
_agent_mem = main._brain_memory_dir(BRAIN) / "agents" / "quick-check"
_mem_txt = (_agent_mem / "MEMORY.md").read_text(encoding="utf-8") if (_agent_mem / "MEMORY.md").is_file() else ""
check("agent: the JAVIS_RULE line is recorded as an owner rule",
      RULE in _mem_txt and main.agent_rules.OWNER_RULES_HEADER in _mem_txt, _mem_txt[:300])
_runs = "".join(f.read_text(encoding="utf-8") for f in (_agent_mem / "runs").glob("*.md")) \
    if (_agent_mem / "runs").is_dir() else ""
check("agent: the run is logged in the agent's run log", "analyse merchant.example" in _runs, _runs[:200])
_sid_s1 = main._TG_SID_MAP.get("cli:s1@quick-check")
_stored = [m.get("content") or "" for m in main.get_store().get_messages(_sid_s1)] if _sid_s1 else []
check("agent: the stored conversation holds the stripped answer",
      "Report ready." in _stored and not any("JAVIS_LESSON" in m or "JAVIS_RULE" in m for m in _stored),
      _stored)

r = chat("/chat/stream", brain=BRAIN, session="s2", agent="quick-check")
resp = [e for e in stream_events(r) if e.get("type") == "response"]
check("agent stream: the response event carries the agent's answer",
      r.status_code == 200 and bool(resp) and resp[-1].get("ok") is True and resp[-1].get("text") == "Report ready.",
      r.text[:200])
check("agent stream: ran on the agent's model", FakeClaude.runs[-1].get("model") == "sonnet")

# No brain sent: the agent is looked up in the session's brain (here the default one), the brain
# this turn runs in.
r = chat(session="s3", agent="quick-check")
run = FakeClaude.runs[-1]
check("agent without brain: resolved in the session's brain",
      r.status_code == 200 and same_dir(run.get("cwd"), DEFAULT)
      and "DEFAULT BRAIN IMPOSTOR BODY" in run.get("system_prompt", "") and run.get("model") == "haiku",
      (r.status_code, run.get("cwd"), run.get("model")))


# ================================================================
# 2. Not in the resolved brain, or no such brain: 400, nothing runs
# ================================================================
before = len(FakeClaude.runs)
r = chat(brain=BRAIN, session="s6", agent="no-such-agent")
check("missing agent: 400 with ok=false naming the slug",
      r.status_code == 400 and r.json().get("ok") is False and "no-such-agent" in r.json().get("error", ""), r.text[:200])
r = chat(brain=BRAIN, session="s6", agent="other-only")
check("agent of another brain: 400", r.status_code == 400, r.text[:200])
r = chat(brain=BRAIN + "-typo", session="s6", agent="quick-check")
check("wrong brain: 400, no fall back to the default brain's agent of the same slug",
      r.status_code == 400 and r.json().get("ok") is False, r.text[:200])
check("wrong brain: the error says brain must be a brain folder path on the server",
      any(w in r.json().get("error", "") for w in ("path of a brain folder on the server",
                                                    "đường dẫn tới một thư mục brain trên máy chủ")),
      r.text[:200])
r = chat(brain=BRAIN, session="s6", agent="../agents/quick-check")
check("slug that leaves the agents folder: 400", r.status_code == 400, r.text[:200])
r = chat("/chat/stream", brain=BRAIN, session="s6", agent="no-such-agent")
check("stream: missing agent is a real 400, not an error inside a 200 stream", r.status_code == 400, r.status_code)
r = chat("/chat/stream", brain=BRAIN + "-typo", session="s6", agent="quick-check")
check("stream: wrong brain is a real 400", r.status_code == 400, r.status_code)
check("no turn ran for any rejected request", len(FakeClaude.runs) == before, len(FakeClaude.runs) - before)


# ================================================================
# 3. No agent: the old turn, unchanged
# ================================================================
FAST.calls = ADAPTIVE.calls = 0
r = chat(brain=BRAIN, session="s4")
run = FakeClaude.runs[-1]
check("no agent: 200 and ok", r.status_code == 200 and r.json().get("ok") is True, r.text[:200])
check("no agent: main model as before", run.get("model") == "opus", run.get("model"))
check("no agent: Javis's prompt as before", "JAVIS MAIN PROMPT" in run.get("system_prompt", ""))
check("no agent: no agent role leaks in", "QUICK CHECK ROLE BODY" not in run.get("system_prompt", ""))
check("no agent: fast path and adaptive context still consulted",
      FAST.calls >= 1 and ADAPTIVE.calls >= 1, (FAST.calls, ADAPTIVE.calls))

r = chat(brain=BRAIN + "-typo", session="s5")
run = FakeClaude.runs[-1]
check("no agent: a wrong brain still falls back to the default brain, as before",
      r.status_code == 200 and same_dir(run.get("cwd"), DEFAULT), (r.status_code, run.get("cwd")))
r = chat("/chat/stream", brain=BRAIN, session="s7")
resp = [e for e in stream_events(r) if e.get("type") == "response"]
check("no agent stream: answers as before", r.status_code == 200 and bool(resp) and resp[-1].get("ok") is True)
check("no agent stream: main model", FakeClaude.runs[-1].get("model") == "opus")


# ================================================================
# 4. Session isolation: the same `session` with and without `agent`, and with two agents
# ================================================================
# Claude Code keeps one engine object per RAM session and resumes its native thread, so a shared
# session would run the agent turn inside Javis's thread (and the reverse).
r1 = chat(brain=BRAIN, session="iso", message="plain question")
plain_run = FakeClaude.runs[-1]
r2 = chat(brain=BRAIN, session="iso", agent="quick-check", message="agent question")
agent_run = FakeClaude.runs[-1]
r3 = chat(brain=BRAIN, session="iso", message="plain again")
plain_again = FakeClaude.runs[-1]
check("isolation: all three turns answered", all(x.status_code == 200 for x in (r1, r2, r3)),
      [x.status_code for x in (r1, r2, r3)])
check("isolation (Claude Code): the agent turn gets its own engine, not the plain session's",
      agent_run["engine"] != plain_run["engine"], (agent_run["engine"], plain_run["engine"]))
check("isolation (Claude Code): the plain session keeps its engine after an agent turn",
      plain_again["engine"] == plain_run["engine"])
check("isolation (Claude Code): the plain turn after an agent turn has Javis's prompt, no agent role",
      "JAVIS MAIN PROMPT" in plain_again["system_prompt"]
      and "QUICK CHECK ROLE BODY" not in plain_again["system_prompt"])
_sid_plain = main._TG_SID_MAP.get("cli:iso")
_sid_agent = main._TG_SID_MAP.get("cli:iso@quick-check")
check("isolation: the agent turn has its own stored conversation",
      bool(_sid_plain) and bool(_sid_agent) and _sid_plain != _sid_agent, (_sid_plain, _sid_agent))
_store = main.get_store()
_plain_msgs = [m.get("content") for m in _store.get_messages(_sid_plain)] if _sid_plain else []
_agent_msgs = [m.get("content") for m in _store.get_messages(_sid_agent)] if _sid_agent else []
check("isolation: the agent question is stored only in the agent conversation",
      "agent question" in _agent_msgs and "agent question" not in _plain_msgs, (_plain_msgs, _agent_msgs))
check("isolation: the reply still names the plain session the client sent",
      r2.json().get("session") == "cli:iso", r2.json().get("session"))


# API engines build the system prompt only when the RAM session is new (`sess["or"] is None`),
# so a shared session made the FIRST turn's prompt stick for every later turn of that session.
API_RUNS = []


async def fake_api_stream(prov, api_key, api_model, msgs, reasoning, **kw):
    API_RUNS.append({"system": "\n".join(m["content"] for m in msgs if m.get("role") == "system"),
                     "user": [m["content"] for m in msgs if m.get("role") == "user"]})

    async def _gen():
        yield {"type": "text", "content": "api answer"}
    return _gen()


class api_engine:
    """Runs the turns inside on a fake API engine (OpenRouter shape) as the main model."""

    def __enter__(self):
        self.saved = (main._chat_provider, main._api_stream_mcp, main._tg_compact_bg)
        main._chat_provider = lambda mcfg: ("openrouter", "api", "sk-test", "test/model")
        main._api_stream_mcp = fake_api_stream
        main._tg_compact_bg = lambda *a, **k: None

    def __exit__(self, *exc):
        main._chat_provider, main._api_stream_mcp, main._tg_compact_bg = self.saved


with api_engine():
    chat(brain=BRAIN, session="apiiso", message="api plain 1")
    api_plain = API_RUNS[-1]
    chat(brain=BRAIN, session="apiiso", agent="api-one", message="api agent one")
    api_one = API_RUNS[-1]
    chat(brain=BRAIN, session="apiiso", agent="api-two", message="api agent two")
    api_two = API_RUNS[-1]
    chat(brain=BRAIN, session="apiiso", message="api plain 2")
    api_plain2 = API_RUNS[-1]
check("isolation (API): plain turn first, then agent: the agent turn runs with the agent's prompt",
      "API ONE ROLE BODY" in api_one["system"] and "JAVIS MAIN PROMPT" not in api_one["system"],
      api_one["system"][:200])
check("isolation (API): agent one then agent two: agent two runs with its own prompt, not agent one's",
      "API TWO ROLE BODY" in api_two["system"] and "API ONE ROLE BODY" not in api_two["system"],
      api_two["system"][:200])
check("isolation (API): the plain session keeps Javis's prompt and none of the agent turns",
      "JAVIS MAIN PROMPT" in api_plain2["system"] and "API ONE ROLE BODY" not in api_plain2["system"]
      and api_plain2["user"] == ["api plain 1", "api plain 2"], api_plain2["user"])
check("isolation (API): each agent's history holds only its own turn",
      api_one["user"] == ["api agent one"] and api_two["user"] == ["api agent two"],
      (api_one["user"], api_two["user"]))


# ================================================================
# 5. Prompt parity with the dashboard agent chat
# ================================================================
# The CLI agent turn must get what an agent chat on the Partners page gets: the builder block
# (where to write agents/workflows/skills), the lesson rule and the agent's learned lessons.
main._ket_luot_agent(BRAIN, "api-one", "earlier dashboard question",
                     "ok\nJAVIS_LESSON: PARITY LESSON MARKER", conv_sid="")
_dash = main._agent_turn_system_prompt(BRAIN, "api-one", "")
with api_engine():
    chat(brain=BRAIN, session="parity", agent="api-one", message="parity question")
_cli_sp = API_RUNS[-1]["system"]
check("parity: the dashboard agent prompt has the builder block and the learned lesson (precondition)",
      main._agent_builder_block(BRAIN) in _dash and "PARITY LESSON MARKER" in _dash)
check("parity: the CLI agent prompt has the builder block", main._agent_builder_block(BRAIN) in _cli_sp)
check("parity: the CLI agent prompt has the lesson rule", main.agent_lessons.DM_LESSON_RULE in _cli_sp)
check("parity: the CLI agent prompt has the agent's learned lessons", "PARITY LESSON MARKER" in _cli_sp,
      _cli_sp[-600:])
check("parity: the CLI agent prompt names the CLI, not the Partners page",
      "trang Cộng sự). Trả lời" not in _cli_sp and "qua Javis CLI" in _cli_sp)
check("parity: the dashboard agent prompt still names the Partners page",
      "trên dashboard Javis (trang Cộng sự). Trả lời" in _dash)


# ================================================================
# 6. A stale Codex model on an agent never rewrites the owner's MAIN model
# ================================================================
# The Codex branch self-heals a stale model by writing the corrected one as the main model. Right
# for the owner's own turn, wrong for an agent turn: the stale model is the agent's (same bug as
# the dedicated bots fixed in 0.102.1).
class FakeCodex:
    runs = []

    def __init__(self, **kw):
        self.cwd = kw.get("cwd")
        self.model = kw.get("model")
        self.instructions = kw.get("instructions") or ""
        self.session_id = None
        self.extra_config = []
        self.steer = False

    def is_available(self):
        return True

    async def query(self, prompt):
        FakeCodex.runs.append({"instructions": self.instructions, "model": self.model})
        yield {"type": "final", "content": "codex answer", "tokens_in": 1, "tokens_out": 1}


_cfg = main.cfgmod.read_settings()
main._set_main_model(_cfg, "anthropic-cli", "opus")
main.cfgmod.write_settings(_cfg)
_main_before = dict(main.cfgmod.read_settings()["model"].get("main") or {})
_saved_codex = (main.CodexCLI, main._apply_codex_hub, main.openai_oauth.write_codex_auth)
main.CodexCLI = lambda **kw: FakeCodex(**kw)
main._apply_codex_hub = lambda cli, vault_root=None: cli
main.openai_oauth.write_codex_auth = lambda *a, **k: None
try:
    r = chat(brain=BRAIN, session="codex", agent="codex-stale")
finally:
    main.CodexCLI, main._apply_codex_hub, main.openai_oauth.write_codex_auth = _saved_codex
_main_after = dict(main.cfgmod.read_settings()["model"].get("main") or {})
check("stale Codex model: the agent turn ran on Codex with the agent's prompt",
      r.status_code == 200 and bool(FakeCodex.runs)
      and "CODEX STALE ROLE BODY" in FakeCodex.runs[-1]["instructions"], r.text[:200])
check("stale Codex model: the owner's main model is unchanged after the agent turn",
      _main_before == _main_after == {"provider": "anthropic-cli", "model": "opus"}, (_main_before, _main_after))
_txt = r.json().get("text") or ""
check("stale Codex model: the notice names the agent and its settings, not the Models page",
      "codex-stale" in _txt and "gpt-4o" in _txt and "Models" not in _txt, _txt[:300])

print()
if _fails:
    print(f"FAILED {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_cli_agent: all pass")
