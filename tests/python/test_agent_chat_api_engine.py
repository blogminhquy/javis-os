"""An assistant chat on an API engine can build agents/workflows and explains missing account connectors.

    python tests/run.py agent_chat_api_engine      (no network, no engine)

Customer report 2026-10-19: with Anthropic API or OpenAI API as the chat model, an assistant (a) said it could not
create agents or workflows, nor give an agent its own model, and (b) said it had no browser-control tool, while the
same request worked on Claude Code. Two causes:

1. `_agent_chat_prompt` leaves CLAUDE.md and the "LỚP AGENTIC" block out on purpose, and those were the only places
   naming the agent/workflow paths. Claude Code coped (it runs inside the brain and loads javis-builder natively);
   an API engine only knows its prompt.
2. Browser control came from a connector on the owner's Claude account (claude.ai). Those only exist on Claude
   Code; `javis_connections` on an API engine did not list them, so the model had nothing true to say.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-agapi-")
os.environ["BRAINS_DIR"] = tempfile.mkdtemp(prefix="javis-agapi-brains-")

import main      # noqa: E402
import mcp_hub   # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


# ============================================================
# 1. The assistant's chat prompt says where and how to build
# ============================================================
ag_dir = main._agents_dir("brain")
ag_dir.mkdir(parents=True, exist_ok=True)
(ag_dir / "emma.md").write_text("---\nname: Emma\nrole: COO\nskills: []\n---\nRun operations.\n", encoding="utf-8")
p = main._agent_chat_prompt("brain", "emma")

check("names the absolute agents/ path", f"{main._agents_dir('brain')}/<slug>.md" in p)
check("names the absolute workflows/ path", f"{main._workflows_dir('brain')}/<slug>.md" in p)
check("names the skills/ path", f"{main._skills_dir('brain')}/<slug>/SKILL.md" in p)
check("tells it to load the javis-builder template first", "javis-builder" in p and "javis_use_skill" in p)
check("gives the way to set an assistant's model on every engine",
      "javis_team" in p and "set_agent_model" in p and "create_agent" in p and "model_provider" in p)
check("still not the whole of CLAUDE.md (persona chat stays lean)",
      "SWAPPABLE BRAIN" not in p and "# === LỚP AGENTIC" not in p)
check("no em dash in the new block", "\u2014" not in main._agent_builder_block("brain"))

# ============================================================
# 2. javis_connections names Claude-account connectors on an API engine
# ============================================================
mcp_hub._ambient_cache.update(servers=[{"name": "Composio_MCP", "url": ""}], ts=10 ** 12, refreshing=False)

api_owner = json.loads(mcp_hub._connections_json(include_ambient=False, owner_chat=True))
acc = [r for r in api_owner if r.get("source") == "claude_account"]
check("API engine, owner chat: the Claude-account connector is listed", [r["connector"] for r in acc] == ["Composio_MCP"])
check("... marked not usable on this turn", acc and acc[0].get("dung_duoc_o_luot_nay") is False)
check("... with the two real fixes (connect it in Javis, or switch to Claude Code)",
      acc and "trang Kết nối" in acc[0]["ly_do"] and "Claude Code" in acc[0]["ly_do"])

bot = json.loads(mcp_hub._connections_json(include_ambient=False, owner_chat=False))
check("CANARY: a customer-facing bot does not learn the owner's account connectors",
      not any(r.get("source") == "claude_account" for r in bot))

claude = json.loads(mcp_hub._connections_json(include_ambient=True, owner_chat=True))
cl = [r for r in claude if r.get("source") == "claude_account"]
check("Claude engine keeps the old entry (call the native tool directly)",
      len(cl) == 1 and "goi_the_nao" in cl[0] and "dung_duoc_o_luot_nay" not in cl[0])

_hub = (SERVER / "mcp_hub.py").read_text(encoding="utf-8")
check("CANARY: the javis_connections tool passes the owner-chat flag",
      "_connections_json(include_ambient, hidden, bo_qua, owner_chat=staging)" in _hub)

# ============================================================
# 3. The javis-builder agent template carries model_provider
# ============================================================
skill = (ROOT / ".claude" / "skills" / "javis-builder" / "SKILL.md").read_text(encoding="utf-8")
tpl = skill[skill.index("### Agent ->"):skill.index("### Skill ->")]
check("agent template has a model_provider line", "\nmodel_provider:" in tpl)
check("agent template points at javis_team set_agent_model", "set_agent_model" in tpl)

print()
if fails:
    print(f"{len(fails)} test FAILED: " + ", ".join(fails))
    sys.exit(1)
print("All agent_chat_api_engine tests passed.")
