"""A workflow step keeps its assistant's model and level; while its card cannot run it takes the highest card of the
usage order that can, and goes back once its card has quota again.

    python tests/run.py workflow_card_down      (no network, no CLI needed)

Goes through the REAL step factory (`main._workflow_agent_helpers`) and `main._step_run`; only the engine classes are
fakes, so no model is called.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

_TMP = Path(tempfile.mkdtemp(prefix="javis-wf-down-"))
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
import codex_models  # noqa: E402

codex_models._EFFORTS["gpt-6-luna"] = ["low", "medium", "high", "xhigh", "max"]

CLAUDE, CODEX, GROQ = "anthropic-cli", "openai-oauth", "groq"
WEEKLY = "You've hit your weekly limit · resets 7am (Asia/Ho_Chi_Minh)"
ANSWER = "Báo cáo đã xong, đây là một câu trả lời đủ dài để được coi là nội dung thật của bước quy trình này."
fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {str(extra)[:500]}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


BRAIN = _TMP / "brain"
(BRAIN / "agents").mkdir(parents=True)


def model_cfg(order=(CODEX, CLAUDE, GROQ), key="gsk_test"):
    top = order[0]
    profiles = {CODEX: {"model": "gpt-6-luna", "reasoning": "ultra"},
                CLAUDE: {"model": "claude-sonnet-5-5", "reasoning": "low"},
                GROQ: {"model": "llama-4", "reasoning": "medium"}}
    return {"order": list(order), "main": {"provider": top, "model": profiles[top]["model"]},
            "reasoning": profiles[top]["reasoning"], "profiles": profiles, "groq_api_key": key,
            "catalog": {CODEX: ["gpt-6-luna"]}}


SCRIPT = {}   # provider -> events the next engines of that provider answer with
RAN = []      # (provider, model, level) of every engine that was asked


class Fake:
    def __init__(self, provider, model="", level=""):
        self.provider_name, self.model, self.effort = provider, model, level
        self.extra_config, self.session_id = [], None

    async def query(self, prompt):
        level = self.effort
        for item in self.extra_config:
            if str(item).startswith("model_reasoning_effort="):
                level = str(item).split("=", 1)[1]
        RAN.append((self.provider_name, self.model, level))
        for ev in SCRIPT.get(self.provider_name, [{"type": "final", "content": ANSWER}]):
            yield ev


def swap(_cli, spec=None, **_kw):
    return Fake(spec["provider"], spec.get("model") or "", spec.get("reasoning") or "")


def reset(m):
    main._PIN_LIMITED.clear()
    main._SIGNED_OUT.clear()
    for prov in (CODEX, CLAUDE):
        main.model_routing.clear_rest(prov, main.plan_accounts.MAIN)
    SCRIPT.clear()
    RAN.clear()
    return patch.multiple(
        main,
        claude_engine=lambda **_kw: Fake(CLAUDE),
        CodexCLI=lambda **kw: Fake(CODEX, kw.get("model") or ""),
        find_codex_cli=lambda: "codex",
        _apply_codex_hub=lambda cli, vault_root=None: cli,
        _apply_mcp=lambda *a, **k: None,
        _empty_mcp_file=lambda: "",
        _codex_user_mcp_servers=lambda: {},
        _routing_connected_ids=lambda _s=None: list(m["order"]),
    )


def scene(m, body):
    with reset(m), patch.object(main.cfgmod, "read_settings", lambda: {"model": m}), \
            patch.object(main.openai_oauth, "write_codex_auth", lambda *a, **k: None), \
            patch.object(main.claude_cli, "co_co", lambda *_a: True), \
            patch.object(main.aux_engine, "swap", swap), \
            patch.object(main.aux_engine, "availability", lambda *a, **k: (True, "")), \
            patch.object(main.inbox, "add", lambda *a, **k: {}):
        mk = main._workflow_agent_helpers(str(BRAIN), None)[0]
        body(mk)


def run(build):
    async def go():
        return [ev async for ev in main._step_run(build, "p")]
    return asyncio.run(go())


def first(mk, model, provider, level):
    RAN.clear()
    events = run(lambda: mk("s", model, provider, (), reasoning=level))
    return list(RAN), events


# 1. every card able to run: exactly the assistant's model and level
def _own(mk):
    ran, _ = first(mk, "claude-opus-5-5", CLAUDE, "high")
    check("own Claude model and level", ran == [(CLAUDE, "claude-opus-5-5", "high")], ran)
    ran, _ = first(mk, "gpt-6-luna", CODEX, "xhigh")
    check("own ChatGPT model and level", ran == [(CODEX, "gpt-6-luna", "xhigh")], ran)
    ran, _ = first(mk, "llama-4-scout", GROQ, "high")
    check("own API model and level reach the background engine", ran == [(GROQ, "llama-4-scout", "high")], ran)


scene(model_cfg(), _own)


# 2. the assistant's card is out of quota: the highest card with quota, with that card's model and level
def _down(mk):
    main._note_pin_limit("claude-code")
    ran, _ = first(mk, "claude-opus-5-5", CLAUDE, "high")
    check("Claude out of quota: up to ChatGPT, the top card, at its level", ran == [(CODEX, "gpt-6-luna", "max")], ran)
    main._note_pin_limit("codex")
    ran, _ = first(mk, "claude-opus-5-5", CLAUDE, "high")
    check("Claude and ChatGPT out of quota: the third card", ran == [(GROQ, "llama-4", "medium")], ran)
    main._PIN_LIMITED.clear()
    main.model_routing.clear_rest(CLAUDE, main.plan_accounts.MAIN)
    main.model_routing.clear_rest(CODEX, main.plan_accounts.MAIN)
    ran, _ = first(mk, "claude-opus-5-5", CLAUDE, "high")
    check("quota back: the assistant's own model and level again", ran == [(CLAUDE, "claude-opus-5-5", "high")], ran)


scene(model_cfg(), _down)


def _down_codex(mk):
    main._note_pin_limit("codex")
    ran, _ = first(mk, "gpt-6-luna", CODEX, "xhigh")
    check("ChatGPT out of quota: Claude with the card's model and level",
          ran == [(CLAUDE, "claude-sonnet-5-5", "low")], ran)


scene(model_cfg(), _down_codex)


# 3. no other card can run: the step stays and reports its own limit
def _bottom(mk):
    main._note_pin_limit("claude-code")
    main._note_pin_limit("codex")
    ran, _ = first(mk, "claude-opus-5-5", CLAUDE, "high")
    check("no other card usable: the step stays on its card and level", ran == [(CLAUDE, "claude-opus-5-5", "high")], ran)


scene(model_cfg(order=(CODEX, CLAUDE, GROQ), key=""), _bottom)


# 4. the refusal arrives during the step: one new run on another card, and the refusal is not shown
def _midway(mk):
    SCRIPT[CODEX] = [{"type": "session", "session_id": "x"},
                     {"type": "final", "content": WEEKLY, "is_error": True}]
    ran, events = first(mk, "gpt-6-luna", CODEX, "xhigh")
    check("refused mid-step: second run is on the next card at its level",
          [r[0] for r in ran] == [CODEX, CLAUDE] and ran[1][1:] == ("claude-sonnet-5-5", "low"), ran)
    check("refused mid-step: only the real answer comes out", [e.get("content") for e in events] == [ANSWER], events)
    check("refused mid-step: the card rests", bool(main._pin_limited_until(CODEX)))


scene(model_cfg(), _midway)


def _two_hops(mk):
    SCRIPT[CODEX] = [{"type": "text", "content": WEEKLY}, {"type": "final", "content": WEEKLY}]
    ran, events = first(mk, "gpt-6-luna", CODEX, "xhigh")
    check("limit sentence printed as the answer moves too", [r[0] for r in ran] == [CODEX, CLAUDE], ran)
    check("limit sentence is not shown when another card answers", [e.get("content") for e in events] == [ANSWER], events)


scene(model_cfg(), _two_hops)


# 5. a step that already wrote or called a tool is never run twice
def _acted(mk):
    SCRIPT[CODEX] = [{"type": "tool_call", "name": "zalo_send_message"},
                     {"type": "final", "content": WEEKLY, "is_error": True}]
    ran, events = first(mk, "gpt-6-luna", CODEX, "xhigh")
    check("tool already called: no second run", [r[0] for r in ran] == [CODEX], ran)
    check("tool already called: the refusal is shown", events[-1].get("content") == WEEKLY, events)
    SCRIPT[CODEX] = [{"type": "text", "content": ANSWER}, {"type": "final", "content": WEEKLY, "is_error": True}]
    main._PIN_LIMITED.clear()
    main.model_routing.clear_rest(CODEX, main.plan_accounts.MAIN)
    ran, _ = first(mk, "gpt-6-luna", CODEX, "xhigh")
    check("text already written: no second run", [r[0] for r in ran] == [CODEX], ran)


scene(model_cfg(), _acted)


# 6. the lowest card refuses: the top card takes the step; with no card left the refusal comes out
def _lowest(mk):
    SCRIPT[CLAUDE] = [{"type": "final", "content": WEEKLY, "is_error": True}]
    ran, events = first(mk, "claude-opus-5-5", CLAUDE, "high")
    check("lowest card refuses: the top card runs it at its level",
          [r[0] for r in ran] == [CLAUDE, CODEX] and ran[1][1:] == ("gpt-6-luna", "max"), ran)
    main._PIN_LIMITED.clear()
    main.model_routing.clear_rest(CLAUDE, main.plan_accounts.MAIN)
    main._note_pin_limit("codex")
    ran, events = first(mk, "claude-opus-5-5", CLAUDE, "high")
    check("last card refuses: one run only", [r[0] for r in ran] == [CLAUDE], ran)
    check("last card refuses: its own words come out", [e.get("content") for e in events] == [WEEKLY], events)


scene(model_cfg(order=(CODEX, CLAUDE)), _lowest)


# 7. the model router never replaces a model the assistant chose
def _router():
    asked, made = [], []

    class Engine:
        async def query(self, prompt):
            yield {"type": "final", "content": ANSWER}

    def mk(sysprompt, model=None, provider="", extra_tools=(), reasoning=""):
        made.append((model, provider))
        return Engine()

    async def sink(_ev):
        return None

    node = SimpleNamespace(agent="a", verify_agent="", id="n1", metadata={}, max_retries=0)
    with patch.object(main, "_route_step_model", lambda *a: (asked.append(a), ("opus", "router"))[1]):
        for own in (("gpt-6-luna", CODEX), ("", CLAUDE), ("claude-sonnet-5-5", "")):
            asyncio.run(main._run_workflow_step(node, "p", mk, lambda *_a: ("A", "s", *own), sink))
        check("assistant with a model or a card: the router is never asked", not asked, asked)
        check("assistant with a model or a card: it runs on exactly that",
              made == [("gpt-6-luna", CODEX), ("", CLAUDE), ("claude-sonnet-5-5", "")], made)
        made.clear()
        asyncio.run(main._run_workflow_step(node, "p", mk, lambda *_a: ("A", "s", "", ""), sink))
        check("assistant without a model: the router still picks", made == [("opus", "")], made)


_router()


# 8. restricted background steps stay on Claude Code or ChatGPT
def _gated():
    m = model_cfg(order=(CLAUDE, CODEX, GROQ))
    with reset(m), patch.object(main.cfgmod, "read_settings", lambda: {"model": m}), \
            patch.object(main.aux_engine, "availability", lambda *a, **k: (True, "")):
        main._note_pin_limit("claude-code")
        alt = main._step_stand_in(CLAUDE, gated=True)
        check("gated: Claude out of quota goes to ChatGPT",
              (alt.get("provider"), alt.get("model"), alt.get("reasoning")) == (CODEX, "gpt-6-luna", "ultra"), alt)
        main._note_pin_limit("codex")
        check("gated: groq is not taken", main._step_stand_in(CODEX, gated=True) == {})
        check("ungated: groq is", main._step_stand_in(CODEX).get("provider") == GROQ)
        main._PIN_LIMITED.clear()
        main.model_routing.clear_rest(CLAUDE, main.plan_accounts.MAIN)
        main._note_pin_limit("codex")
        check("gated: ChatGPT out of quota goes up to Claude",
              main._step_stand_in(CODEX, gated=True).get("provider") == CLAUDE)
        main._PIN_LIMITED.clear()
        check("a card that can run never moves", main._step_stand_in(CLAUDE) == {})


_gated()

print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
