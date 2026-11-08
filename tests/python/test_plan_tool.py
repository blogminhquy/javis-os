"""javis_plan: the task checklist tool of the API brains (server/plan_tool.py).

    python tests/run.py plan_tool      (no network, no model)

Owner, 08/11/2026: Claude Code, Codex and Grok keep a checklist for a long job and the chat draws it as the plan card;
the seven API brains had no such tool. javis_plan gives it to them, on the owner's chat turns only, switchable in the
composer "+" menu. The list reaches the card through the tool_call event (turn_plan reads javis_plan like TodoWrite).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-plan-tool-"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import plan_tool  # noqa: E402
import turn_plan  # noqa: E402
import main  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or not extra else f"  [{str(extra)[:300]}]"))
    if not cond:
        fails.append(name)


T = lambda *items: {"todos": [{"content": c, "status": s} for c, s in items]}  # noqa: E731

# ---- the tool's answer ----
check("a good list is saved and counted",
      plan_tool.check(T(("a", "completed"), ("b", "in_progress"), ("c", "pending"))).startswith("OK: đã lưu, xong 1/3"))
check("all done says so", plan_tool.check(T(("a", "completed"), ("b", "completed"))) == "OK: xong cả 2/2 mục.")
check("empty list is refused", plan_tool.check({"todos": []}).startswith("ERROR"))
check("missing todos is refused", plan_tool.check({}).startswith("ERROR") and plan_tool.check(None).startswith("ERROR"))
check("two items in progress are refused", "in_progress" in plan_tool.check(T(("a", "in_progress"), ("b", "in_progress"))))
check("an unknown status is refused", "status" in plan_tool.check(T(("a", "doing"))))
check("an item with no text is refused", plan_tool.check(T(("  ", "pending"))).startswith("ERROR: mục 1"))
check("more than 30 items is refused", plan_tool.check(T(*[("x", "pending")] * 31)).startswith("ERROR"))
check("the answer is short (a tool round, not a report)", len(plan_tool.check(T(("a", "pending")))) < 120)

# ---- the tool's shape ----
tools, route = [], {}
plan_tool.add_to(tools, route)
plan_tool.add_to(tools, route)
check("added once, in the hub's tool format", len(tools) == 1 and tools[0]["fn"] == "javis_plan"
      and tools[0]["schema"]["required"] == ["todos"] and "javis_plan" in route)
check("the route answers like any hub tool",
      asyncio.run(main.mcp_client.call_route(route, "javis_plan", T(("a", "pending")))).startswith("OK"))
check("description and schema stay small (about 200 tokens a request)",
      len(plan_tool.DESCRIPTION + json.dumps(plan_tool.SCHEMA, ensure_ascii=False)) < 600)
check("on by default, off when the owner switches it off",
      plan_tool.enabled({}) and plan_tool.enabled({"chat": {}}) and not plan_tool.enabled({"chat": {"plan_tool": False}}))

# ---- the plan card reads it ----
op = turn_plan.plan_op({"type": "tool_call", "name": "javis_plan",
                        "input": T(("Đọc số liệu", "completed"), ("So sánh", "in_progress"))})
check("turn_plan reads javis_plan like TodoWrite",
      op == {"op": "set", "items": [{"text": "Đọc số liệu", "status": "done"}, {"text": "So sánh", "status": "active"}]}, op)

# ---- only the owner's chat turns get it ----
seen = {}


# One shared pair, like the hub's cache: adding javis_plan must not change it in place.
SHARED_TOOLS, SHARED_ROUTE = [{"fn": "javis_read_file", "name": "javis_read_file"}], {"javis_read_file": {"call": None}}


async def _discover(mode, **kw):
    return SHARED_TOOLS, SHARED_ROUTE


async def _deepseek(key, model, messages, reasoning, tools, route):
    seen["tools"] = [t.get("fn") or t.get("name") for t in tools]
    seen["route"] = sorted(route)
    yield {"type": "text", "content": "ok"}


def run_turn(**kw):
    seen.clear()

    async def go():
        out = main._api_stream_mcp("deepseek", "k", "deepseek-chat", [{"role": "user", "content": "làm báo cáo"}], **kw)
        if asyncio.iscoroutine(out):
            out = await out
        return [ev async for ev in out]
    asyncio.run(go())
    return seen.get("tools") or []


orig = (main.mcp_hub.discover_all, main.mcp_hub.registry_inventory, main.engine.deepseek_chat_with_mcp,
        main._hub_enabled, main.cfgmod.read_settings)
main.mcp_hub.discover_all = _discover
main.mcp_hub.registry_inventory = lambda *a, **k: ([], {})
main.engine.deepseek_chat_with_mcp = _deepseek
main._hub_enabled = lambda: True
settings = {"chat": {}}
real_read = orig[4]
main.cfgmod.read_settings = lambda *a, **k: dict(real_read(*a, **k), chat=settings["chat"])
try:
    check("owner's chat turn: javis_plan is offered", "javis_plan" in run_turn(owner_sid="s_owner"), seen)
    check("owner's chat turn: the route has it too", "javis_plan" in seen.get("route", []), seen)
    check("a turn with no owner chat (bot, background job): not offered", "javis_plan" not in run_turn(), seen)
    settings["chat"] = {"plan_tool": False}
    check("switched off by the owner: not offered", "javis_plan" not in run_turn(owner_sid="s_owner"), seen)
    settings["chat"] = {}
    run_turn(owner_sid="s_owner")
    check("the hub's cached list is not changed in place",
          [t["fn"] for t in SHARED_TOOLS] == ["javis_read_file"] and list(SHARED_ROUTE) == ["javis_read_file"],
          (SHARED_TOOLS, list(SHARED_ROUTE)))
finally:
    (main.mcp_hub.discover_all, main.mcp_hub.registry_inventory, main.engine.deepseek_chat_with_mcp,
     main._hub_enabled, main.cfgmod.read_settings) = orig

# ---- the switch ----
src = (SERVER / "main.py").read_text(encoding="utf-8")
check("settings route saves the switch", 'cfg.setdefault("chat", {})["plan_tool"] = bool(patch["plan_tool"])' in src)
check("GET /chat/plan reports it", '@app.get("/chat/plan")' in src)
js = (ROOT / "dashboard" / "chat-steps.js").read_text(encoding="utf-8")
check("the composer + menu has the switch", 'id: "plan-tool"' in js and "plan_tool: !!on" in js)
check("the step block names a javis_plan call", "javis_plan" in js)

print("\n" + (f"{len(fails)} FAIL" if fails else "All green"))
raise SystemExit(1 if fails else 0)
