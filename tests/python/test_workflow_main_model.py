"""An interactive workflow step whose agent pins no model runs on the owner's MAIN model.

Before this, `_workflow_agent_helpers._mk` sent an unpinned agent to Claude Code whatever brain was picked on the
Models page (reported in PR #1125). The fix must not lose what the old builder guarantees:

  * a pinned agent keeps its pin;
  * a Codex step still runs at the normal service tier (workflow steps are background work);
  * other providers still go through aux_engine.swap, which owns keys and the fallback chain;
  * the gated background run (tools is not None) stays on Claude Code.

    python tests/run.py workflow_main_model      (no network, spawns nothing)
"""
import os
import tempfile

from _paths import ROOT, SERVER  # noqa: E402,F401

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-wf-main-"))

import aux_engine  # noqa: E402
import main  # noqa: E402

fails = []


def check(name, condition, extra=None):
    print(("ok   " if condition else "FAIL ") + name + ("" if condition or extra is None else f"  [{extra}]"))
    if not condition:
        fails.append(name)


swapped = {}


def fake_swap(cli, **kw):
    swapped.clear()
    swapped.update(kw.get("spec") or {})
    swapped["tag"] = kw.get("tag")
    return cli


class FakeCodex:
    def __init__(self, cwd=None, tag=None, model=None, instructions=None):
        self.model = model
        self.tag = tag
        self.extra_config = ['service_tier="fast"']


settings = {"model": {"main": {}}}

saved = {name: getattr(main, name) for name in
         ("CodexCLI", "find_codex_cli", "_apply_codex_hub")}
saved_read = main.cfgmod.read_settings
saved_auth = main.openai_oauth.write_codex_auth
saved_swap = aux_engine.swap
try:
    aux_engine.swap = fake_swap
    main.CodexCLI = FakeCodex
    main.find_codex_cli = lambda: "/usr/bin/codex"
    main._apply_codex_hub = lambda cc, root: None
    main.openai_oauth.write_codex_auth = lambda: None
    main.cfgmod.read_settings = lambda: settings

    mk = main._workflow_agent_helpers("brain", None)[0]

    def use_main(provider, model):
        settings["model"]["main"] = {"provider": provider, "model": model}

    # --- unpinned agent follows the main model ---
    use_main("openrouter", "openai/gpt-4o-mini")
    swapped.clear()
    cli = mk("prompt", "", "")
    check("unpinned agent on an OpenRouter main goes through aux_engine with the main model",
          swapped.get("provider") == "openrouter" and swapped.get("model") == "openai/gpt-4o-mini"
          and swapped.get("tag") == "workflow", swapped)
    check("the main model's name is not put into a Claude engine", getattr(cli, "model", None) != "openai/gpt-4o-mini")

    use_main("openai-oauth", "gpt-5-codex")
    swapped.clear()
    cc = mk("prompt", "", "")
    check("unpinned agent on a ChatGPT main runs Codex with the main model",
          isinstance(cc, FakeCodex) and cc.model == "gpt-5-codex" and cc.tag == "workflow", vars(cc))
    check("that Codex step is forced to the normal tier",
          'service_tier="default"' in cc.extra_config and 'service_tier="fast"' not in cc.extra_config,
          cc.extra_config)
    check("Codex does not go through aux_engine", not swapped, swapped)

    use_main("openai-oauth", "")
    cc = mk("prompt", "", "")
    check("a ChatGPT main with no model still runs Codex (Codex picks its default)",
          isinstance(cc, FakeCodex), type(cc).__name__)

    use_main("anthropic-cli", "sonnet")
    swapped.clear()
    cli = mk("prompt", "", "")
    check("unpinned agent on a Claude Code main runs Claude with the main model",
          not swapped and getattr(cli, "model", None) == "sonnet", (swapped, getattr(cli, "model", None)))

    # --- what must not change ---
    use_main("openrouter", "openai/gpt-4o-mini")
    swapped.clear()
    cli = mk("prompt", "opus", "anthropic-cli")
    check("a pinned agent keeps its pin over the main model",
          not swapped and getattr(cli, "model", None) == "opus", (swapped, getattr(cli, "model", None)))

    swapped.clear()
    mk("prompt", "grok-4.6", "grok-cli")
    check("a pinned agent on another provider still goes through aux_engine",
          swapped.get("provider") == "grok-cli", swapped)

    gated = main._workflow_agent_helpers("brain", ["Read"])[0]
    swapped.clear()
    cli = gated("prompt", "", "")
    check("gated background run stays on Claude Code even with an OpenRouter main",
          not swapped and not isinstance(cli, FakeCodex), swapped)
    use_main("openai-oauth", "gpt-5-codex")
    cli = gated("prompt", "", "")
    check("gated background run does not switch to Codex either", not isinstance(cli, FakeCodex))
finally:
    aux_engine.swap = saved_swap
    main.cfgmod.read_settings = saved_read
    main.openai_oauth.write_codex_auth = saved_auth
    for name, value in saved.items():
        setattr(main, name, value)

print()
if fails:
    print(f"FAIL - test_workflow_main_model: {len(fails)}: " + ", ".join(fails))
    raise SystemExit(1)
print("OK - test_workflow_main_model: all pass")
