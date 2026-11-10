"""Team turns rotate over the accounts of a subscription plan card, like chat and background work (10/11/2026).

    python tests/run.py team_plan_accounts      (no network, no CLI needed)

Customer report, 10/11/2026: a Claude Code card with two accounts. Account 1 hit its weekly limit; chat and background
work were already running on the second account, but every team member answered "You've hit your weekly limit · resets
7am (Asia/Ho_Chi_Minh)". The team engine factory (`main._team_engine_for`) never picked a plan account, so team turns
always ran on account 1.

Goes through the REAL factory (only `team_engine.build` / `build_tools` swapped for fake engines); no model is called.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

_TMP = Path(tempfile.mkdtemp(prefix="javis-team-acc-"))
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
import team_engine  # noqa: E402
import team_runner as TR  # noqa: E402

fails = []
CLAUDE = "anthropic-cli"
WEEKLY = "You've hit your weekly limit · resets 7am (Asia/Ho_Chi_Minh)"


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:400]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


BRAIN = _TMP / "brain"
(BRAIN / "agents").mkdir(parents=True)
(BRAIN / "agents" / "mkt.md").write_text("---\ntype: agent\nname: Trưởng phòng Marketing\nrole: Marketing\n---\nThân.\n",
                                         encoding="utf-8")
TEAM = {"brain_id": main._brain_key(str(BRAIN)), "team_id": "tm_accounts01", "session_id": ""}
INFO = {"slug": "mkt", "name": "Trưởng phòng Marketing", "system": "s", "model": "", "model_provider": ""}


def settings(extra_account: bool):
    cfg = cfgmod.read_settings()
    m = cfg.setdefault("model", {})
    m["provider"] = CLAUDE
    m.pop("accounts", None)
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
    """A fake plan engine: `script[account id]` is the list of events that account answers with."""
    ran = []

    def __init__(self, script):
        self.script = script
        self.session_id = None

    def is_available(self):
        return True

    async def query(self, prompt):
        acc = getattr(self, "account_id", "untouched")
        Engine.ran.append(acc)
        for ev in self.script.get(acc, [{"type": "final", "content": f"Báo cáo quảng cáo, chạy trên {acc}."}]):
            yield ev


LIMIT_FINAL = [{"type": "final", "content": WEEKLY, "is_error": True, "subtype": "success"}]


async def _started(*a):
    return None


def turn(script, tool_turn=False):
    """One team turn through the real factory. Returns (result or None, error or None, accounts it ran on)."""
    Engine.ran = []
    with patch.object(main, "_team_agent_info", return_value=INFO), \
            patch.multiple(team_engine, build=lambda spec, base, tag, settings=None: Engine(script),
                           build_tools=lambda spec, base, tag, settings=None, mode="full", codex_profile=None: Engine(script)):
        prov, _model, run = main._team_engine_for(TEAM, "agent-mkt", "work" if tool_turn else "member_reply")
        req = {"team_id": TEAM["team_id"], "turn_id": "turn-1", "system": "s", "prompt": "p",
               "engine_started": _started, "tool_turn": tool_turn}
        try:
            return asyncio.run(run(req)), None, list(Engine.ran)
        except Exception as ex:  # noqa: BLE001 - the runner turns this into the "Chưa trả lời được" line
            return None, ex, list(Engine.ran)


# ---- 1. one account: nothing changes, the provider's own sentence is the error -------------------------------------
settings(extra_account=False)
wake()
res, err, ran = turn({"main": LIMIT_FINAL})
check("one account: the turn runs once, on account 1", ran == ["main"], ran)
check("one account: the provider's sentence is the turn's error, as before",
      isinstance(err, TR.EngineOutcomeError) and err.kind == "final_error" and "weekly limit" in err.detail, err)
check("one account: no tool was called, so a job step may still retry on its own (team_retry)",
      getattr(err, "team_tool_calls", None) == 0)

# ---- 2. the customer's case: account 1 already resting, the team turn starts on the other account ------------------
settings(extra_account=True)
wake()
R.mark_rest(CLAUDE, "main", seconds=3600)      # chat or background work found it out of quota earlier
res, err, ran = turn({"main": LIMIT_FINAL})
check("account 1 resting: the team turn runs on the account that still has quota", ran == ["acc_b"] and err is None,
      (ran, err))
check("and answers", res is not None and "acc_b" in res["text"], res)
check("a turn that did not move carries no note", res is not None and res["engine_note"] == "", res)

# ---- 3. account 1 runs out DURING a team turn: it rests and the turn runs again at once on the next account --------
wake()
res, err, ran = turn({"main": LIMIT_FINAL})
check("out of quota mid-rotation: the turn runs again on the next account", ran == ["main", "acc_b"] and err is None,
      (ran, err))
check("the account that ran out rests, the other does not", rested() == {"main": True, "acc_b": False}, rested())
check("the message says which account answered and why",
      res is not None and "Tài khoản phụ" in res["engine_note"] and "Claude Code" in res["engine_note"], res)
check("the plan is not marked out of quota while an account can still run", not main._pin_limited_until(CLAUDE))
res, err, ran = turn({"main": LIMIT_FINAL})
check("the next team turn starts on the account with quota, no wasted refusal", ran == ["acc_b"] and err is None, ran)

# ---- 4. Claude Code prints the sentence as the ANSWER, not flagged as an error ------------------------------------
wake()
res, err, ran = turn({"main": [{"type": "final", "content": WEEKLY}]})
check("the out-of-quota sentence as a plain answer moves on too, it is never posted as the member's reply",
      ran == ["main", "acc_b"] and err is None and res is not None and "weekly limit" not in res["text"], (ran, err, res))
wake()
quote = ("Khi Claude báo \"You've hit your weekly limit\" thì anh chờ tới giờ mở lại rồi thử lại ạ. " * 8)
res, err, ran = turn({"main": [{"type": "final", "content": quote}]})
check("an answer that only QUOTES the sentence is a normal answer", ran == ["main"] and err is None
      and res is not None and res["text"] == quote and rested() == {"main": False, "acc_b": False}, (ran, err))

# ---- 5. every account out of quota: the error comes back, nothing loops --------------------------------------------
wake()
res, err, ran = turn({"main": LIMIT_FINAL, "acc_b": LIMIT_FINAL})
check("every account out: each is tried once, then the provider's sentence is the error",
      ran == ["main", "acc_b"] and isinstance(err, TR.EngineOutcomeError) and "weekly limit" in err.detail, (ran, err))
check("both accounts rest", rested() == {"main": True, "acc_b": True}, rested())
check("the plan now counts as out of quota for chat too", bool(main._pin_limited_until(CLAUDE)))

# ---- 6. a Work step that already called a tool is never run twice --------------------------------------------------
wake()
acted = [{"type": "tool_call", "name": "Write", "input": {"file_path": "a.md"}}, {"type": "tool_result", "content": "ok"}]
res, err, ran = turn({"main": acted + LIMIT_FINAL}, tool_turn=True)
check("a tool step that acted before running out is not run again on another account",
      ran == ["main"] and isinstance(err, TR.EngineOutcomeError) and getattr(err, "team_tool_calls", None) == 1,
      (ran, err))
check("but its account rests, so the owner's Retry lands on the next account", rested() == {"main": True, "acc_b": False},
      rested())
res, err, ran = turn({"main": LIMIT_FINAL}, tool_turn=True)
check("the retried tool step runs on the account with quota", ran == ["acc_b"] and err is None, (ran, err))
wake()
res, err, ran = turn({"main": LIMIT_FINAL}, tool_turn=True)
check("a tool step refused before any tool call moves on at once", ran == ["main", "acc_b"] and err is None, (ran, err))

# ---- 7. another kind of error is left alone ------------------------------------------------------------------------
wake()
res, err, ran = turn({"main": [{"type": "final", "content": "model not found", "is_error": True}]})
check("an error that is not about quota does not move or rest anything",
      ran == ["main"] and isinstance(err, TR.EngineOutcomeError) and rested() == {"main": False, "acc_b": False},
      (ran, err, rested()))

# ---- 8. Claude Code on an API key has no plan account to rotate ----------------------------------------------------
wake()
cfg = cfgmod.read_settings()
cfg["model"]["claude_auth"] = "api_key"
cfgmod.write_settings(cfg)
R.mark_rest(CLAUDE, "main", seconds=3600)
res, err, ran = turn({})
check("Claude Code on an API key: the engine is left as it is (the key pays, no plan account is picked)",
      ran == ["untouched"] and err is None, ran)

print(f"\n{'ĐỎ' if fails else 'XANH'}: {len(fails)} lỗi")
raise SystemExit(1 if fails else 0)
