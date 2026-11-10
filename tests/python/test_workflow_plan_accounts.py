"""Workflow steps rotate over the accounts of a subscription plan card, like chat, background work and team turns.

    python tests/run.py workflow_plan_accounts      (no network, no CLI needed)

Before 10/11/2026 the step engine builder (`main._workflow_agent_helpers`) built Claude Code or Codex without picking a
plan account, so a step always ran on account 1 and the whole run stopped with "the plan is out of quota" while the
card's other account still had quota.

Goes through the REAL runner (`main._execute_workflow_raw`) with `main.claude_engine` swapped for a fake engine.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

_TMP = Path(tempfile.mkdtemp(prefix="javis-wf-acc-"))
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

import main  # noqa: E402
import config as cfgmod  # noqa: E402
import model_routing as R  # noqa: E402
import plan_accounts as P  # noqa: E402

fails = []
CLAUDE = "anthropic-cli"
WEEKLY = "You've hit your weekly limit · resets 7am (Asia/Ho_Chi_Minh)"


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:500]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


BRAIN = _TMP / "brain"
(BRAIN / "workflows").mkdir(parents=True)
(BRAIN / "agents").mkdir(parents=True)
(BRAIN / "workflows" / "demo.md").write_text(
    "---\ntype: workflow\nname: Demo\nslug: demo\nstatus: active\nsteps:\n"
    "  - agent: writer\n    task: 'Viết {{input}}'\n  - agent: poster\n    task: 'Đăng {{prev}}'\n---\n", encoding="utf-8")
for slug in ("writer", "poster"):
    (BRAIN / "agents" / f"{slug}.md").write_text(
        f"---\ntype: agent\nname: {slug}\nslug: {slug}\nrole: r\nskills: []\nmodel: opus\nmodel_provider: {CLAUDE}\n---\nthân\n",
        encoding="utf-8")


def settings(extra_account: bool, api_key: bool = False):
    cfg = cfgmod.read_settings()
    m = cfg.setdefault("model", {})
    m["provider"] = CLAUDE
    m.pop("accounts", None)
    m["claude_auth"] = "api_key" if api_key else "subscription"
    if extra_account:
        P.add(m, CLAUDE, "acc_b", "Tài khoản phụ")
        (P.home(CLAUDE, "acc_b") / ".credentials.json").write_text("{}", encoding="utf-8")
    cfgmod.write_settings(cfg)


def rested():
    return {a: bool(R.resting_until(CLAUDE, a)) for a in ("main", "acc_b")}


def wake():
    for a in ("main", "acc_b"):
        R.clear_rest(CLAUDE, a)
    main._PIN_LIMITED.clear()


class Engine:
    """A fake Claude engine: `SCRIPT[account id]` is what that account answers with. `ran` logs (account, prompt)."""
    SCRIPT = {}
    ran = []

    def __init__(self, **k):
        self.model = None
        self.session_id = None
        self.cwd = k.get("cwd")

    async def query(self, prompt):
        acc = getattr(self, "account_id", "untouched")
        Engine.ran.append((acc, prompt.split()[0]))
        for ev in Engine.SCRIPT.get(acc, [{"type": "text", "content": f"bài viết ({acc})"},
                                          {"type": "final", "content": f"bài viết ({acc})"}]):
            yield ev


# What Claude Code really sends when the plan is out: the sentence as text, then as the answer flagged as an error.
LIMIT = [{"type": "text", "content": WEEKLY}, {"type": "final", "content": WEEKLY, "is_error": True}]
LIMIT_PLAIN = [{"type": "text", "content": WEEKLY}, {"type": "final", "content": WEEKLY}]


def run(script, tools=None):
    """One run of the two-step workflow. Returns (events, accounts each engine call ran on)."""
    Engine.SCRIPT, Engine.ran = script, []

    async def go():
        return [e async for e in main._execute_workflow_raw("brain", "demo", input="S07", tools=tools)]
    with patch.object(main, "claude_engine", lambda **k: Engine(**k)), \
            patch.object(main, "_brain_root", lambda b: str(BRAIN)), \
            patch.object(main, "_workflows_dir", lambda b: BRAIN / "workflows"), \
            patch.object(main, "_agents_dir", lambda b: BRAIN / "agents"), \
            patch.object(main, "_agent_memory", lambda b, s: ""), \
            patch.object(main, "_log_agent_run", lambda *a, **k: None), \
            patch.object(main, "_apply_mcp", lambda *a, **k: None), \
            patch.object(main.system_sync, "ensure_synced", lambda *a, **k: None), \
            patch.object(main.system_sync, "mirror_skills", lambda *a, **k: None):
        events = asyncio.run(go())
    return events, [a for a, _p in Engine.ran]


def kinds(events):
    return [e["type"] for e in events]


def texts(events):
    return [e.get("content") for e in events if e["type"] == "step_text"]


# ---- 1. one account: exactly as before ----------------------------------------------------------------------------
settings(extra_account=False)
wake()
ev, ran = run({})
check("one account: both steps run and the run finishes", kinds(ev)[-1] == "done" and len(ran) == 2, (kinds(ev), ran))
check("one account: the step text streams through as before", texts(ev) == ["bài viết (main)"] * 2, texts(ev))
ev, ran = run({"main": LIMIT})
check("one account out of quota: the run stops at step 1 with the out-of-quota message, as before",
      kinds(ev)[-1] == "error" and "done" not in kinds(ev) and ran == ["main"], (kinds(ev), ran))
with patch.object(main, "claude_engine", lambda **k: Engine(**k)), patch.object(main, "_brain_root", lambda b: str(BRAIN)), \
        patch.object(main, "_apply_mcp", lambda *a, **k: None):
    eng = main._workflow_agent_helpers("brain", None)[0]("s", "opus", CLAUDE)
check("one account: the builder hands back the engine itself, not a wrapper", isinstance(eng, Engine), type(eng).__name__)

# ---- 2. account 1 already resting: every step starts on the account with quota ------------------------------------
settings(extra_account=True)
wake()
R.mark_rest(CLAUDE, "main", seconds=3600)
ev, ran = run({"main": LIMIT})
check("account 1 resting: both steps run on the other account and the run finishes",
      ran == ["acc_b", "acc_b"] and kinds(ev)[-1] == "done", (ran, kinds(ev)))
check("the run's result is the second account's answer", ev[-1].get("result") == "bài viết (acc_b)", ev[-1])

# ---- 3. account 1 runs out DURING the run: it rests, the step runs again at once on the next account --------------
wake()
ev, ran = run({"main": LIMIT})
check("out of quota mid-run: step 1 runs again on the next account, step 2 starts there",
      ran == ["main", "acc_b", "acc_b"] and kinds(ev)[-1] == "done", (ran, kinds(ev)))
check("the account that ran out rests, the other does not", rested() == {"main": True, "acc_b": False}, rested())
check("the provider's sentence never reaches the step text or the result",
      not any("weekly limit" in str(e) for e in ev), [e for e in ev if "weekly limit" in str(e)])
check("no step error was reported for the refused attempt", "step_error" not in kinds(ev), kinds(ev))
wake()
ev, ran = run({"main": LIMIT_PLAIN})
check("the sentence as a plain answer (no error flag) moves on the same way",
      ran == ["main", "acc_b", "acc_b"] and kinds(ev)[-1] == "done" and not any("weekly limit" in str(e) for e in ev),
      (ran, kinds(ev)))
wake()
ev, ran = run({"main": [{"type": "error", "content": "Claude AI usage limit reached|9999999999"}]})
check("an engine error event that says out of quota moves on too",
      ran == ["main", "acc_b", "acc_b"] and kinds(ev)[-1] == "done", (ran, kinds(ev)))

# ---- 4. a gated background run stays on Claude Code and rotates accounts too --------------------------------------
wake()
ev, ran = run({"main": LIMIT}, tools=["Read"])
check("a gated run (limited tools) rotates accounts, the provider does not change",
      ran == ["main", "acc_b", "acc_b"] and kinds(ev)[-1] == "done", (ran, kinds(ev)))

# ---- 5. every account out: the run stops with the out-of-quota message, nothing loops -----------------------------
wake()
ev, ran = run({"main": LIMIT, "acc_b": LIMIT})
check("every account out: each is tried once, then the run stops at step 1",
      ran == ["main", "acc_b"] and kinds(ev)[-1] == "error" and "done" not in kinds(ev), (ran, kinds(ev)))
check("both accounts rest and the plan counts as out of quota", rested() == {"main": True, "acc_b": True}
      and bool(main._pin_limited_until(CLAUDE)), rested())

# ---- 6. a step that already acted is never run twice ---------------------------------------------------------------
wake()
acted = [{"type": "tool_call", "name": "Write", "input": {}}] + LIMIT
ev, ran = run({"main": acted})
check("a step that called a tool before running out is not run again on another account",
      ran == ["main"] and kinds(ev)[-1] == "error" and "step_tool" in kinds(ev), (ran, kinds(ev)))
check("but its account rests, so running the workflow again lands on the next account",
      rested() == {"main": True, "acc_b": False}, rested())
ev, ran = run({"main": acted})
check("the next run starts on the account with quota", ran == ["acc_b", "acc_b"] and kinds(ev)[-1] == "done", (ran, kinds(ev)))
wake()
long_text = "Đây là bản nháp bài viết về sản phẩm, đã viết được vài đoạn trước khi gói hết lượt giữa chừng. " * 2
ev, ran = run({"main": [{"type": "text", "content": long_text}] + LIMIT[1:]})
check("a step that already wrote real text is not run again either", ran == ["main"] and kinds(ev)[-1] == "error"
      and texts(ev) == [long_text], (ran, kinds(ev), texts(ev)))

# ---- 7. ordinary answers and errors are untouched ------------------------------------------------------------------
wake()
quote = ("Khi Claude báo \"You've hit your weekly limit\" thì anh chờ tới giờ mở lại rồi thử lại ạ. " * 8)
ev, ran = run({"main": [{"type": "text", "content": quote}, {"type": "final", "content": quote}]})
check("an answer that only QUOTES the sentence is a normal answer", ran == ["main", "main"] and kinds(ev)[-1] == "done"
      and rested() == {"main": False, "acc_b": False}, (ran, kinds(ev), rested()))
ev, ran = run({"main": [{"type": "text", "content": "ok"}, {"type": "final", "content": "ok"}]})
check("a short answer still reaches the step text, in order", texts(ev) == ["ok", "ok"] and kinds(ev)[-1] == "done", texts(ev))
ev, ran = run({"main": [{"type": "text", "content": "đang viết"}]})
check("text of an engine that stopped with no answer is still shown", "đang viết" in texts(ev), texts(ev))
ev, ran = run({"main": [{"type": "error", "content": "model not found"}]})
check("an error that is not about quota stops the run as before and rests nothing",
      ran == ["main"] and kinds(ev)[-1] == "error" and rested() == {"main": False, "acc_b": False}, (ran, rested()))

# ---- 8. Claude Code on an API key has no plan account to rotate ---------------------------------------------------
settings(extra_account=True, api_key=True)
wake()
R.mark_rest(CLAUDE, "main", seconds=3600)
ev, ran = run({})
check("Claude Code on an API key: the engine is left as it is", ran == ["untouched", "untouched"] and kinds(ev)[-1] == "done", ran)

print(f"\n{'ĐỎ' if fails else 'XANH'}: {len(fails)} lỗi")
raise SystemExit(1 if fails else 0)
