"""Agent recall wired into the assistant prompts (2026-11-27).

    python tests/python/test_agent_recall_wiring.py      (no network, no engine)

A large assistant memory becomes its rules plus a map in the system prompt; the passages matching a message ride at
the head of that message (dashboard, Telegram/CLI, workflow steps, team turns) and never reach the stored history.
A small memory gives the very same prompt as before.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-recall-")
os.environ["BRAINS_DIR"] = tempfile.mkdtemp(prefix="javis-recall-brains-")
os.environ["JAVIS_AGENT_RECALL_ENRICH"] = "0"   # no background model call in a test

import main          # noqa: E402
import agent_recall  # noqa: E402
import chat_recall   # noqa: E402
import team_runner   # noqa: E402

fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


ag_dir = main._agents_dir("brain")
ag_dir.mkdir(parents=True, exist_ok=True)
(ag_dir / "lcx.md").write_text("---\nname: LCX\nrole: Bán nước mắm\nskills: []\n---\nTrả lời khách.\n",
                               encoding="utf-8")
mem_dir = main._brain_memory_dir("brain") / "agents" / "lcx"
mem_dir.mkdir(parents=True, exist_ok=True)
mem_file = mem_dir / "MEMORY.md"

# ---- 1. small memory: byte-for-byte the old prompt ----
small = "## Luật chủ dặn\n- Nhắn Zalo thì không dùng markdown.\n\n## Bảng giá\n- Chai 500ml giá đại lý 85.000đ.\n"
mem_file.write_text(small, encoding="utf-8")
os.environ["JAVIS_AGENT_RECALL"] = "0"
before = main._agent_chat_prompt("brain", "lcx")
os.environ["JAVIS_AGENT_RECALL"] = "1"
after = main._agent_chat_prompt("brain", "lcx")
check("small memory: the prompt is identical with recall on or off", before == after)
check("small memory: no recall block", main._agent_recall_block("brain", "lcx", "giá đại lý") == "")

# ---- 2. large memory: rules + map, knowledge on demand ----
big = (small + "".join(f"## Khách quen {i}\n- Chị Hoa {i} ở quận {i % 12}, hay mua thùng {i % 5} chai.\n\n"
                       for i in range(400)))
mem_file.write_text(big, encoding="utf-8")
p = main._agent_chat_prompt("brain", "lcx")
check("large memory: the owner's rule is in the system prompt", "Nhắn Zalo thì không dùng markdown" in p)
check("large memory: knowledge is not preloaded", "85.000" not in p and "Chị Hoa 377" not in p)
check("large memory: the map and the javis_recall note are there", "Memory map" in p and "javis_recall" in p
      and "agent=`lcx`" in p)
check("large memory: the prompt is far smaller than the memory", len(p) < len(big) // 2)

block = main._agent_recall_block("brain", "lcx", "chị Hoa 377 ở quận mấy")
check("recall block for a matching message", block.startswith(agent_recall.RECALL_HEAD) and "Chị Hoa 377" in block)
check("no block for an unrelated message", main._agent_recall_block("brain", "lcx", "em có tạo được ảnh không") == "")

# ---- 3. the block never reaches the stored history ----
msg = "chị Hoa 377 ở quận mấy"
engine_msg = block + msg
check("strip removes the block", chat_recall.strip_block(engine_msg) == msg)
both = chat_recall.block([{"title": "cũ", "snippet": "x" * 30}]) + engine_msg
check("strip removes both recall blocks in either order", chat_recall.strip_block(both) == msg
      and chat_recall.strip_block(block + chat_recall.block([{"title": "cũ", "snippet": "x" * 30}]) + msg) == msg)

# ---- 4. follow-up questions borrow the previous message ----
q = agent_recall.query_for_turn("còn quận thì sao?", ["chị Hoa 377 mua gì", "còn quận thì sao?"])
check("a short follow-up searches with the previous message", "Hoa 377" in q)
check("a full question searches on its own", agent_recall.query_for_turn("chị Hoa 377 mua thùng mấy chai", ["x y"])
      == "chị Hoa 377 mua thùng mấy chai")

# ---- 5. workflow graph steps and team turns ----
_mk, sysprompt_fn, _log, _learn = main._workflow_agent_helpers("brain", None)
check("the step runner can ask for an agent's recall", "Chị Hoa 377" in sysprompt_fn.recall("lcx", "chị Hoa 377"))


class _Runner(team_runner.TeamRunner):
    def __init__(self, fn):   # only what _recall needs
        self.recall_block = fn


r = _Runner(lambda brain, key, query: "[RECALLED MEMORY: x]\n- " + query + "\n[END RECALLED MEMORY]")
got = r._recall({"brain_id": "b"}, "k", "body text", {"title": "Báo giá"})
check("team turn: the recall block joins the member prompt", got.startswith("\n\n[RECALLED MEMORY")
      and "Báo giá" in got and "body text" in got)
check("team turn: a broken recall costs nothing", _Runner(lambda *a: 1 / 0)._recall({"brain_id": "b"}, "k", "x", None)
      == "")

# ---- 6. the javis_recall tool ----
root = main._brain_root("brain")
out = agent_recall.run_tool(root, {"op": "search", "query": "chị Hoa 377", "agent": "lcx"})
check("tool search finds the passage", "Chị Hoa 377" in out and out.startswith("passages") is False)
import re as _re
pid = int(_re.search(r"\[(\d+)\] Khách quen 377", out).group(1))
read = agent_recall.run_tool(root, {"op": "read", "id": pid, "agent": "lcx"})
check("tool read returns the passage and its neighbours", "Chị Hoa 377" in read and "Chị Hoa 376" in read)
check("tool: unknown assistant", agent_recall.run_tool(root, {"query": "x", "agent": "nobody"}).startswith("ERROR"))
check("tool: no assistant named and none in the turn", agent_recall.run_tool(root, {"query": "x"}).startswith("ERROR"))
check("tool: nothing matching says so", "Nothing in the memory" in agent_recall.run_tool(
    root, {"query": "tàu vũ trụ sao hoả", "agent": "lcx"}))
spec, entry = agent_recall.build(root, "full")
check("tool is read-only and always visible", entry["required_mode"] == "readonly" and entry.get("hat_nhan"))
check("tool description has no em dash", "\u2014" not in agent_recall.DESCRIPTION)

# ---- 7. fail-open ----
orig = main._agent_recall_engine
main._agent_recall_engine = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
try:
    p2 = main._agent_chat_prompt("brain", "lcx")
finally:
    main._agent_recall_engine = orig
check("a broken index loads the whole memory", "Chị Hoa 377" in p2)

if fails:
    print(f"\n{len(fails)} FAILED")
    sys.exit(1)
print("\nAll agent_recall_wiring tests passed.")
