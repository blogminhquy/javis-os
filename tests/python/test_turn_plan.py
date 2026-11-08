"""The engine's task plan, read from its tool calls for the plan card in the chat (server/turn_plan.py).

    python tests/python/test_turn_plan.py

Owner, 08/11/2026: Claude's app shows a Plan checklist beside a long task and Javis showed nothing, though Claude Code,
Codex and Grok already make that list. These checks pin how each engine's shape becomes one plan op, and that main.py
and the Codex readers really pass it on.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import re

import turn_plan  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond or not extra else f"  [{extra}]"))
    if not cond:
        fails.append(name)


op = turn_plan.plan_op

# Claude Code TodoWrite (SDK event: `input`)
r = op({"type": "tool_call", "name": "TodoWrite", "input": {"todos": [
    {"content": "Read the code", "status": "completed", "activeForm": "Reading"},
    {"content": "Write the fix", "status": "in_progress", "activeForm": "Writing"},
    {"content": "Run the tests", "status": "pending", "activeForm": "Running"}]}})
check("TodoWrite: whole list, statuses normalised",
      r == {"op": "set", "items": [{"text": "Read the code", "status": "done"},
                                   {"text": "Write the fix", "status": "active"},
                                   {"text": "Run the tests", "status": "pending"}]}, r)

# Claude Code CLI raw block: input under `item`
r = op({"type": "tool_call", "name": "TodoWrite", "item": {"type": "tool_use", "name": "TodoWrite",
                                                          "input": {"todos": [{"content": "A", "status": "pending"}]}}})
check("TodoWrite from the raw CLI block", r and r["items"] == [{"text": "A", "status": "pending"}], r)

# Codex app-server turn/plan/updated
ev = turn_plan.from_codex_notification({"threadId": "t", "turnId": "u", "explanation": None, "plan": [
    {"step": "Look around", "status": "completed"}, {"step": "Patch", "status": "inProgress"},
    {"step": "Test", "status": "pending"}]})
check("Codex notification becomes an update_plan tool call", ev and ev["name"] == "update_plan", ev)
r = op(ev)
check("Codex plan: steps and camelCase status",
      r and [i["status"] for i in r["items"]] == ["done", "active", "pending"]
      and r["items"][1]["text"] == "Patch", r)
check("Codex notification without a plan: nothing", turn_plan.from_codex_notification({"plan": []}) is None)

# Codex exec todo_list item
r = op({"type": "tool_call", "name": "todo_list", "item": {"id": "i1", "type": "todo_list", "items": [
    {"text": "One", "completed": True}, {"text": "Two", "completed": False}]}})
check("Codex exec todo_list: completed flag",
      r and r["items"] == [{"text": "One", "status": "done"}, {"text": "Two", "status": "pending"}], r)

# Codex function_call update_plan with JSON arguments
r = op({"type": "tool_call", "name": "update_plan",
        "item": {"arguments": '{"plan": [{"step": "S1", "status": "in_progress"}]}'}})
check("update_plan with JSON string arguments", r and r["items"] == [{"text": "S1", "status": "active"}], r)

# Grok todo_write, an MCP-prefixed name
r = op({"type": "tool_call", "name": "todo_write", "input": {"todos": [{"description": "G", "status": "done"}]}})
check("Grok todo_write", r and r["items"] == [{"text": "G", "status": "done"}], r)
r = op({"type": "tool_call", "name": "mcp__x__write_todos", "input": {"todos": ["plain string item"]}})
check("MCP prefix and plain string items", r and r["items"] == [{"text": "plain string item", "status": "pending"}], r)

# Claude Code TaskCreate / TaskUpdate
check("TaskCreate: one item", op({"name": "TaskCreate", "input": {"subject": "Fix it", "description": "long"}})
      == {"op": "add", "text": "Fix it"})
check("TaskUpdate: status", op({"name": "TaskUpdate", "input": {"taskId": "3", "status": "completed"}})
      == {"op": "update", "id": "3", "status": "done"})
check("TaskUpdate: deleted", op({"name": "TaskUpdate", "input": {"taskId": "3", "status": "deleted"}})
      == {"op": "update", "id": "3", "status": "deleted"})
check("TaskUpdate without an id: nothing", op({"name": "TaskUpdate", "input": {"status": "completed"}}) is None)

# Not a plan, or junk: never raises, returns nothing
check("other tools: nothing", op({"name": "Bash", "input": {"command": "ls"}}) is None)
check("TodoWrite with an empty list: nothing", op({"name": "TodoWrite", "input": {"todos": []}}) is None)
check("junk payloads: nothing", op(None) is None and op({"name": "TodoWrite", "input": "{bad"}) is None
      and op({"name": "TodoWrite", "input": {"todos": [None, 3, {}]}}) is None)
long = op({"name": "TodoWrite", "input": {"todos": [{"content": "x" * 999, "status": "pending"}] * 99}})
check("long list and long text are capped", len(long["items"]) == turn_plan.MAX_ITEMS
      and len(long["items"][0]["text"]) <= turn_plan.MAX_TEXT, len(long["items"]))
check("fields(): spread-ready", turn_plan.fields({"name": "Bash"}) == {}
      and "plan" in turn_plan.fields({"name": "TodoWrite", "input": {"todos": ["a"]}}))

# Wiring: every tool_call frame main.py sends the dashboard carries the plan, and the Codex readers emit it.
main_src = (SERVER / "main.py").read_text(encoding="utf-8")
frames = len(re.findall(r'"detail": tool_label\.chi_tiet\((?:ev|event)\)', main_src))
with_plan = len(re.findall(r'"detail": tool_label\.chi_tiet\((ev|event)\), \*\*turn_plan\.fields\(\1\)', main_src))
check("main.py: every tool_call frame carries the plan", frames > 0 and frames == with_plan, f"{with_plan}/{frames}")
steer_src = (SERVER / "codex_steer.py").read_text(encoding="utf-8")
check("codex_steer: turn/plan/updated is read", 'method == "turn/plan/updated"' in steer_src)
cli_src = (SERVER / "claude_cli.py").read_text(encoding="utf-8")
check("codex exec: todo_list items are passed on", '"name": "todo_list"' in cli_src)

print("\n" + (f"{len(fails)} FAIL" if fails else "All green"))
raise SystemExit(1 if fails else 0)
