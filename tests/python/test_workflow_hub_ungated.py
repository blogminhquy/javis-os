"""A Claude workflow step that is not gated gets the Javis hub, at the run's level (#1252).

    python tests/run.py workflow_hub_ungated      (no network, spawns nothing)

The bug: `_workflow_agent_helpers._mk` built the Claude engine of an ungated step (a workflow run from chat, or a Kanban
`wf:` job at `full`, where tools is None) with only `javis_vault` set. In-process plugins worked; every MCP registered
in Javis did not, so the agent reported "missing tool" and the Kanban job stopped at its acceptance check. The Codex
branch of the same function already attached the hub (_apply_codex_hub), and route `auto` at `full` did too.

Pinned here:
  1. Kanban `wf:` at full: the Claude step's engine points at the hub config for `full`
  2. a run started from chat (no mode): the hub at `full`, the owner's own run
  3. the gated run (tools is not None) is unchanged: empty MCP file, strict
  4. an unknown level falls back to the strictest one
"""
import os
import tempfile

from _paths import ROOT, SERVER  # noqa: E402,F401

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-wf-hub-"))

import main  # noqa: E402

fails = []


def check(name, condition, extra=None):
    print(("ok   " if condition else "FAIL ") + name + ("" if condition or extra is None else f"  [{extra}]"))
    if not condition:
        fails.append(name)


saved = {n: getattr(main, n) for n in ("_hub_enabled", "_empty_mcp_file")}
saved_cfg = main.mcp_hub.claude_config_path
try:
    main._hub_enabled = lambda: True
    main.mcp_hub.claude_config_path = lambda mode: f"/hub/claude-{mode}.json"
    main._empty_mcp_file = lambda: "/tmp/empty-mcp.json"

    # 1. Kanban wf: at full
    mk = main._workflow_agent_helpers("brain", None, "full")[0]
    c = mk("prompt", "sonnet", "anthropic-cli")
    check("1. Kanban wf: at full: the Claude step is on the hub", getattr(c, "mcp_config", None) == "/hub/claude-full.json",
          getattr(c, "mcp_config", None))
    check("1. the hub level is the job's level", getattr(c, "javis_mode", None) == "full", getattr(c, "javis_mode", None))
    check("1. the brain is still set for in-process plugins", bool(getattr(c, "javis_vault", None)))
    check("1. full is not strict (ambient account connectors stay reachable)", not getattr(c, "mcp_strict", False))

    # 2. run from chat
    mk = main._workflow_agent_helpers("brain", None)[0]
    c = mk("prompt", "sonnet", "anthropic-cli")
    check("2. a run from chat gets the hub at full", getattr(c, "mcp_config", None) == "/hub/claude-full.json"
          and getattr(c, "javis_mode", None) == "full", (getattr(c, "mcp_config", None), getattr(c, "javis_mode", None)))

    # 3. gated run unchanged
    mk = main._workflow_agent_helpers("brain", ["Read", "Write"], "auto")[0]
    c = mk("prompt", "sonnet", "anthropic-cli")
    check("3. the gated run keeps the empty MCP file", getattr(c, "mcp_config", None) == "/tmp/empty-mcp.json",
          getattr(c, "mcp_config", None))
    check("3. and stays strict", getattr(c, "mcp_strict", False) is True)

    # 4. unknown level
    mk = main._workflow_agent_helpers("brain", None, "weird")[0]
    c = mk("prompt", "sonnet", "anthropic-cli")
    check("4. an unknown level falls back to suggest", getattr(c, "mcp_config", None) == "/hub/claude-suggest.json",
          getattr(c, "mcp_config", None))
finally:
    for n, v in saved.items():
        setattr(main, n, v)
    main.mcp_hub.claude_config_path = saved_cfg

src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("the ungated branch attaches the hub", "_apply_mcp(c, mode=ungated_mode, brain=vault_root)" in src)

if fails:
    raise SystemExit(f"{len(fails)} check(s) failed: {fails}")
print("all ok")
