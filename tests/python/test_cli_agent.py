"""POST /chat and /chat/stream accept an `agent` field: the slug of an agent in the chosen brain.

    python tests/run.py cli_agent        (no network, scratch brains)

An integration that runs a fixed job through Javis over HTTP wants the quick version on the
agent's own model (a faster one) and the full version on the main model. Before this field the
endpoints silently ignored `agent` and every call ran Javis Core on the main model.

What is pinned, through the real endpoints and the real CLI shell (`_tg_answer`), with only the
model engine faked:
  1. `agent` names an agent of the resolved brain: the turn runs with that agent's prompt (role,
     body, skills) and model, inside that brain, and JAVIS_LESSON lines never reach the client.
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
# Same slug as BRAIN's agent, in the default brain: a mistyped brain must never reach this one.
write_agent(DEFAULT, "quick-check", "DEFAULT BRAIN IMPOSTOR BODY", model="haiku")


# ---------------------------------------------------------------- fakes
class FakeClaude:
    """Claude Code engine stand-in: records what the turn handed it, answers with a lesson line."""
    runs = []

    def __init__(self, **kw):
        self.system_prompt = kw.get("system_prompt") or ""
        self.cwd = kw.get("cwd")
        self.model = None
        self.session_id = None

    def reset_session(self):
        self.session_id = None

    async def query(self, prompt):
        FakeClaude.runs.append({"system_prompt": self.system_prompt, "model": self.model, "cwd": self.cwd})
        yield {"type": "text", "content": "Report ready."}
        yield {"type": "final", "content": "Report ready.\nJAVIS_LESSON: read the refund policy first",
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
check("agent: the CLI channel block is still there", "Javis CLI" in sp)
check("agent: runs inside the chosen brain", same_dir(run.get("cwd"), BRAIN), run.get("cwd"))
check("agent: fast path and adaptive context are skipped (both answer in Javis's voice)",
      FAST.calls == 0 and ADAPTIVE.calls == 0, (FAST.calls, ADAPTIVE.calls))
check("agent: JAVIS_LESSON never reaches the client",
      body.get("text") == "Report ready." and "JAVIS_LESSON" not in (body.get("text") or ""), body.get("text"))
if main.memory_control.learning_enabled(main._brain_memory_dir(BRAIN)):
    mem = main._brain_memory_dir(BRAIN) / "agents" / "quick-check" / "MEMORY.md"
    check("agent: the lesson lands in that agent's own memory",
          mem.is_file() and "refund policy" in mem.read_text(encoding="utf-8"))

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

print()
if _fails:
    print(f"FAILED {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_cli_agent: all pass")
