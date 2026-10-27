"""Fast mode on the CLI brains (0.164.0): Claude Code through the Agent SDK, and Codex CLI.

    python tests/run.py fast_mode_cli
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-fastcli-"))
import fast_mode  # noqa: E402
import codex_models  # noqa: E402
import main as srv  # noqa: E402
from claude_sdk_engine import ClaudeSDK, map_message  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


class _Cli:
    def __init__(self, model=""):
        self.model = model
        self.extra_config = []
        self.fast_settings = None


# 1. Claude Code: settings='{"fastMode": true}' only when the bolt is on and the model supports it.
tok = fast_mode.use(True)
c = _Cli("claude-opus-5-5")
srv._cli_fast(c)
check("Claude Code + bolt on + Opus 5.5: fastMode setting", json.loads(c.fast_settings or "{}").get("fastMode") is True, c.fast_settings)
s = _Cli("claude-sonnet-5-5")
srv._cli_fast(s)
check("Claude Code + Sonnet: fastMode false (model does not support it)", json.loads(s.fast_settings).get("fastMode") is False)
fast_mode.CURRENT.reset(tok)
o = _Cli("claude-opus-5-5")
srv._cli_fast(o)
check("Claude Code + bolt off: fastMode false, so a persisted /fast cannot bill 2x", json.loads(o.fast_settings).get("fastMode") is False)

e = ClaudeSDK(tag="chat", model="claude-opus-5-5")
e.fast_settings = fast_mode.claude_sdk_settings("claude-opus-5-5", True)
opts = e._options()
# 0.345.0: settings also carries claudeMdExcludes (test_token_luot_claude.py), so read the fastMode field.
check("ClaudeAgentOptions carries settings when fast",
      json.loads(getattr(opts, "settings", None) or "{}").get("fastMode") is True, getattr(opts, "settings", None))
e2 = ClaudeSDK(tag="chat", model="claude-opus-5-5")
check("background Claude Code runs (never touched by _cli_fast) send fastMode false",
      json.loads(getattr(e2._options(), "settings", None) or "{}").get("fastMode") is False,
      getattr(e2._options(), "settings", None))

# The SDK passes Claude Code's init data through; Javis remembers the real Fast mode state.
from claude_agent_sdk import SystemMessage  # noqa: E402
map_message(SystemMessage(subtype="init", data={"session_id": "x", "fast_mode_state": "cooldown",
                                                "fast_mode_disabled_reason": "rate limit"}))
st = fast_mode.states().get("anthropic-cli", {})
check("Claude Code reported state is remembered for the tooltip", st == {"state": "cooldown", "reason": "rate limit"}, st)

# 2. Codex: the model list keeps the service tiers; on asks for priority, off forces default.
items = codex_models._normalize_items([
    {"id": "gpt-x", "displayName": "X", "serviceTiers": [{"id": "priority", "name": "Fast"}], "defaultServiceTier": "priority"},
    {"id": "gpt-y", "displayName": "Y", "serviceTiers": []},
])
check("model list keeps service tier ids", items[0].get("service_tiers") == ["priority"] and items[1].get("service_tiers") == [], items)
codex_models._nho_tiers(items)
check("tiers_for reads the cache", codex_models.tiers_for("gpt-x") == ["priority"] and codex_models.tiers_for("gpt-y") == [])

tok = fast_mode.use(True)
cx = _Cli("gpt-x")
cx.extra_config = ["model_reasoning_effort=medium", 'service_tier="default"']
srv._codex_fast(cx)
check("Codex + bolt on: service_tier priority replaces any earlier tier, keeps the effort",
      cx.extra_config == ["model_reasoning_effort=medium", 'service_tier="priority"'], cx.extra_config)
cy = _Cli("gpt-y")
srv._codex_fast(cy)
check("Codex + bolt on + model without a priority tier: nothing", cy.extra_config == [], cy.extra_config)
fast_mode.CURRENT.reset(tok)
cz = _Cli("gpt-x")
srv._codex_fast(cz)
check("Codex + bolt off: forces the normal tier", cz.extra_config == ['service_tier="default"'], cz.extra_config)

# Background Codex runs (loops, reminders, kanban, team turns) never get the bolt: force the normal
# tier, or a config.toml with service_tier = "priority" would make every background run fast.
import aux_engine  # noqa: E402
import team_engine  # noqa: E402


class _Base:
    cwd = "."
    tag = "loop"
    system_prompt = "x"
    javis_vault = None
    javis_mode = "auto"


bg = aux_engine._build_codex({"model": "gpt-x"}, _Base(), "auto", "loop")
check("background Codex runs force the normal tier", 'service_tier="default"' in bg.extra_config, bg.extra_config)
from claude_cli import CodexCLI  # noqa: E402
tm = team_engine.codex_text_only(CodexCLI(cwd=".", tag="team", model="gpt-x"))
check("team Codex turns force the normal tier", 'service_tier="default"' in tm.extra_config, tm.extra_config)

# The bolt tooltip reads the remembered states.
from fastapi.testclient import TestClient  # noqa: E402
_r = TestClient(srv.app, base_url="http://localhost").get("/model/fast-state")
check("GET /model/fast-state returns the remembered states",
      _r.status_code == 200 and _r.json().get("states", {}).get("anthropic-cli", {}).get("state") == "cooldown", _r.text[:200])

# 3. Wiring: both chat entry points set the per-turn choice next to the thinking level, and call the helpers.
src = open(os.path.join(SERVER, "main.py"), encoding="utf-8").read()
check("dashboard and Telegram turns set fast_mode next to the thinking level",
      src.count("reasoning = _chat_reasoning(mcfg, prov)") >= 2 and src.count("fast_mode.use(mcfg.get(\"fast\") is True") >= 2)
check("Codex call sites apply the tier right after the effort", src.count("_codex_fast(ccli)") >= 2)
check("Claude Code call sites apply fast right after the effort", src.count("_cli_fast(cli)") >= 2)
check("customer chatbots do not inherit the owner's bolt", 'fast_mode.use(mcfg.get("fast") is True and not bot)' in src)
check("compaction spawned from a turn runs at the normal tier", src.count("fast_mode.normal(") >= 2)
_wf = src[src.index("def _workflow_agent_helpers"):]
_wf = _wf[:_wf.index("\ndef ", 10)]
check("workflow Codex agents force the normal tier", 'service_tier="default"' in _wf)

if fails:
    print("\nFAIL - test_fast_mode_cli: %d" % len(fails))
    sys.exit(1)
print("\nOK - test_fast_mode_cli: all pass")
