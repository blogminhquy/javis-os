"""A workflow step runs at the reasoning level its assistant set for itself (#1302).

Before this, `reasoning:` in an assistant's frontmatter applied to its chat and its team turns only. A workflow step
(and so a Kanban job on route `wf:<slug>`, the one way a background job runs on the assistant's own model) built its
engine with no effort at all, so heavy and light steps of one assistant ran at the engine's default.

Contract:
  1. an assistant with `reasoning: high` gets a Claude step engine with effort "high";
  2. a Codex step gets `model_reasoning_effort` from that model's own ladder, replacing an earlier value;
  3. an assistant that set no level keeps the engine's default (existing workflows do not change);
  4. a step called with a plain `mk` (no `reasoning` keyword) is called exactly as before.

    python tests/run.py workflow_step_reasoning      (no network, spawns nothing)
"""
import os
import tempfile
from pathlib import Path

from _paths import ROOT, SERVER  # noqa: E402,F401

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-wf-reasoning-"))

import main  # noqa: E402

fails = []


def check(name, condition, extra=None):
    print(("ok   " if condition else "FAIL ") + name + ("" if condition or extra is None else f"  [{extra}]"))
    if not condition:
        fails.append(name)


brain = tempfile.mkdtemp(prefix="javis-wf-reasoning-brain-")
agents = Path(brain) / "agents"
agents.mkdir()
(agents / "writer.md").write_text(
    "---\nname: Writer\nrole: writes\nmodel: sonnet\nmodel_provider: anthropic-cli\nreasoning: high\n---\nWrite.\n",
    encoding="utf-8")
(agents / "plain.md").write_text("---\nname: Plain\nrole: plain\n---\nDo.\n", encoding="utf-8")
(agents / "off.md").write_text("---\nname: Off\nrole: off\nreasoning: off\n---\nDo.\n", encoding="utf-8")
(agents / "odd.md").write_text("---\nname: Odd\nrole: odd\nreasoning: enormous\n---\nDo.\n", encoding="utf-8")


class FakeCodex:
    def __init__(self, cwd=None, tag=None, model=None, instructions=None):
        self.model = model
        self.tag = tag
        self.extra_config = ["model_reasoning_effort=low"]


saved = {name: getattr(main, name) for name in ("CodexCLI", "find_codex_cli", "_apply_codex_hub", "_step_engine")}
saved_read = main.cfgmod.read_settings
saved_auth = main.openai_oauth.write_codex_auth
saved_co_co = main.claude_cli.co_co
saved_muc = main.codex_models.muc_cho
saved_efforts = main.codex_models.efforts_for
try:
    main.CodexCLI = FakeCodex
    main.find_codex_cli = lambda: "/usr/bin/codex"
    main._apply_codex_hub = lambda cc, root: None
    main._step_engine = lambda eng, provider: eng       # no plan-account wrapper: the test reads the engine itself
    main.openai_oauth.write_codex_auth = lambda: None
    main.cfgmod.read_settings = lambda: {"model": {"main": {"provider": "anthropic-cli", "model": "sonnet"}}}
    main.claude_cli.co_co = lambda flag: flag == "--effort"
    main.codex_models.muc_cho = lambda model, level: {"high": "high", "ultra": "xhigh"}.get(level, "")

    mk, agent_sysprompt, _log, _learn = main._workflow_agent_helpers(brain, None)

    check("the helper exposes the assistant's own level", agent_sysprompt.own_reasoning("writer") == "high")
    check("no level set reads as none", agent_sysprompt.own_reasoning("plain") == "")
    check("`off` and an unknown level read as none",
          agent_sysprompt.own_reasoning("off") == "" and agent_sysprompt.own_reasoning("odd") == "")
    check("a missing assistant file reads as none", agent_sysprompt.own_reasoning("nobody") == "")

    kw = main._step_reasoning_kw(agent_sysprompt, "writer")
    check("the step passes reasoning=high for that assistant", kw == {"reasoning": "high"}, kw)
    check("the step passes nothing for an assistant without a level",
          main._step_reasoning_kw(agent_sysprompt, "plain") == {})
    check("a plain agent_sysprompt (tests, older runners) adds no keyword",
          main._step_reasoning_kw(lambda slug, surface=None: ("n", "s", None, ""), "writer") == {})

    cli = mk("prompt", "sonnet", "anthropic-cli", (), **kw)
    check("Claude step engine runs at effort high", getattr(cli, "effort", None) == "high", getattr(cli, "effort", None))
    cli = mk("prompt", "sonnet", "anthropic-cli", ())
    check("without a level the Claude step keeps the engine's default", not getattr(cli, "effort", None),
          getattr(cli, "effort", None))
    cli = mk("prompt", "sonnet", "anthropic-cli", (), reasoning="ultra")
    check("`ultra` maps to Claude Code's `max`", getattr(cli, "effort", None) == "max", getattr(cli, "effort", None))

    main.claude_cli.co_co = lambda flag: False
    cli = mk("prompt", "sonnet", "anthropic-cli", (), reasoning="high")
    check("a Claude Code without --effort is left alone", not getattr(cli, "effort", None))
    main.claude_cli.co_co = lambda flag: flag == "--effort"

    cc = mk("prompt", "gpt-5-codex", "openai-oauth", (), reasoning="high")
    check("Codex step gets the level from the model's ladder, replacing the earlier value",
          isinstance(cc, FakeCodex) and [x for x in cc.extra_config if x.startswith("model_reasoning_effort=")]
          == ["model_reasoning_effort=high"], getattr(cc, "extra_config", None))
    main.codex_models.efforts_for = lambda model: ["high", "xhigh"]
    cc = mk("prompt", "gpt-5-codex", "openai-oauth", (), reasoning="medium")
    check("a level a KNOWN Codex ladder does not answer leaves the config as it was",
          [x for x in cc.extra_config if x.startswith("model_reasoning_effort=")] == ["model_reasoning_effort=low"],
          cc.extra_config)
    main.codex_models.efforts_for = lambda model: []
    cc = mk("prompt", "gpt-5-codex", "openai-oauth", (), reasoning="medium")
    check("with no ladder read yet (after a restart) a common level is still passed",
          [x for x in cc.extra_config if x.startswith("model_reasoning_effort=")] == ["model_reasoning_effort=medium"],
          cc.extra_config)
    cc = mk("prompt", "gpt-5-codex", "openai-oauth", ())
    check("without a level the Codex step is untouched",
          [x for x in cc.extra_config if x.startswith("model_reasoning_effort=")] == ["model_reasoning_effort=low"])

    gated = main._workflow_agent_helpers(brain, ["Read"])[0]
    cli = gated("prompt", "sonnet", "anthropic-cli", (), reasoning="high")
    check("the gated background run applies the level too", getattr(cli, "effort", None) == "high")

    src = (Path(SERVER) / "main.py").read_text(encoding="utf-8")
    check("both runners pass the step assistant's level (graph path and legacy path)",
          "**_step_reasoning_kw(agent_sysprompt, node.agent)" in src
          and "**_step_reasoning_kw(_agent_sysprompt, agent_slug)" in src)
    check("both runners pass the verify assistant's level",
          "**_step_reasoning_kw(agent_sysprompt, node.verify_agent)" in src
          and "**_step_reasoning_kw(_agent_sysprompt, verify_slug)" in src)
finally:
    main.cfgmod.read_settings = saved_read
    main.openai_oauth.write_codex_auth = saved_auth
    main.claude_cli.co_co = saved_co_co
    main.codex_models.muc_cho = saved_muc
    main.codex_models.efforts_for = saved_efforts
    for name, value in saved.items():
        setattr(main, name, value)

print()
if fails:
    print(f"FAIL - test_workflow_step_reasoning: {len(fails)}: " + ", ".join(fails))
    raise SystemExit(1)
print("OK - test_workflow_step_reasoning: all pass")
