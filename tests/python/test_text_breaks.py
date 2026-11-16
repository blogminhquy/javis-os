"""Text before and after a tool call no longer reaches the chat glued together.

    python tests/run.py text_breaks      (no network, fake engines)

Owner, 16/11/2026, screenshot of a Claude Code turn: "... thay cho API cần đăng nhập.Xong mục 3. Giờ em đọc file vai
..." and "... chỗ trong bộ nhớ Hồng Ngọc.Now the CEO assistant role file." Every engine sends the text written before a
tool call and the text written after it as separate pieces, and the chat adds them up as they come. Codex on the
app-server already put a line break between its messages; Claude Code (tests/python/test_claude_stream_text.py), Codex
`exec`, Grok Build and Antigravity did not. One rule for all of them: `text_breaks.lead`.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import text_breaks as tb  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{extra!r}]" if (extra and not cond) else ""))
    if not cond:
        fails.append(name)


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---- 1. the rule ----
check("nothing shown yet: no break", tb.lead("", "Xin chào") == "")
check("after a sentence: a blank line", tb.lead("cần đăng nhập.", "Xong mục 3.") == "\n\n")
check("one newline already there: one more", tb.lead("xong.\n", "Tiếp.") == "\n")
check("a blank line already there: nothing", tb.lead("xong.\n\n", "Tiếp.") == "")
check("the piece opens with a blank line: nothing", tb.lead("xong.", "\n\nTiếp.") == "")
check("trailing spaces do not hide a newline", tb.lead("xong.\n  ", "Tiếp.") == "\n")
check("an empty piece gets nothing", tb.lead("xong.", "") == "")

j = tb.Joiner()
j.tool()
first = j.text("Em đọc file trước.")
j.tool()
second = j.text("Xong mục 3.")
third = j.text(" Giờ em đọc tiếp.")
check("Joiner: the first text of a turn has no break, even after a tool call", first == "Em đọc file trước.", first)
check("Joiner: text after a tool call starts a paragraph", second == "\n\nXong mục 3.", second)
check("Joiner: text that just continues is left as it is", third == " Giờ em đọc tiếp.", third)

pieces = ["Em đọc.", "\n\n", "Đã đọc", " xong."]
tb.break_after_tool(pieces, 2)
check("break_after_tool: nothing added when the break is already there", pieces == ["Em đọc.", "\n\n", "Đã đọc", " xong."],
      pieces)
pieces = ["Em đọc.", "Đã đọc"]
tb.break_after_tool(pieces, 1)
check("break_after_tool: the break goes in front of the new text", pieces == ["Em đọc.", "\n\n", "Đã đọc"], pieces)
pieces = ["Đã đọc"]
tb.break_after_tool(pieces, 0)
check("break_after_tool: no text before, nothing added", pieces == ["Đã đọc"], pieces)
for name, text in (("lead", tb.lead("a.", "b")), ("module", (Path(SERVER) / "text_breaks.py").read_text(encoding="utf-8"))):
    check(f"{name}: no em or en dash", "\u2014" not in text and "\u2013" not in text)

BEFORE, AFTER = "Em lưu bằng hàm của app thay cho API cần đăng nhập.", "Xong mục 3. Giờ em đọc file vai."

# ---- 2. Codex `exec --json`: each agent message is its own paragraph live ----
from claude_cli import CodexCLI  # noqa: E402

events = [
    {"type": "thread.started", "thread_id": "t1"},
    {"type": "item.completed", "item": {"id": "i0", "type": "agent_message", "text": BEFORE}},
    {"type": "item.started", "item": {"id": "i1", "type": "command_execution", "command": "ls", "status": "in_progress"}},
    {"type": "item.completed", "item": {"id": "i1", "type": "command_execution", "command": "ls", "status": "completed"}},
    {"type": "item.completed", "item": {"id": "i2", "type": "agent_message", "text": AFTER}},
    {"type": "turn.completed", "usage": {}},
]
script = "import json\n" + "".join(f"print(json.dumps({e!r}), flush=True)\n" for e in events)
cx = CodexCLI(cwd=tempfile.gettempdir())
cx.cli_path = sys.executable
cx._build_args = lambda: [sys.executable, "-c", script]


async def _codex():
    return [e async for e in cx.query("x")]


evs = run(_codex())
live = "".join(e["content"] for e in evs if e["type"] == "text")
check("Codex exec: the live text has a paragraph between the two messages", live == BEFORE + "\n\n" + AFTER, live)
final = next((e for e in evs if e["type"] == "final"), {}).get("content", "")
check("Codex exec: the answer itself is untouched (no added break)", final == AFTER, final)


# ---- 3. Grok Build: the break goes into the live preview and the final text ----
import grok_cli  # noqa: E402


def fake_binary(prefix, name, lines, help_text=""):
    d = Path(tempfile.mkdtemp(prefix=prefix))
    p = d / name
    p.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "a = sys.argv[1:]\n"
        f"if '--help' in a:\n    sys.stdout.write({help_text!r}); sys.exit(0)\n"
        "try:\n    sys.stdin.read()\nexcept Exception:\n    pass\n"
        f"for l in {json.dumps(lines)}:\n    print(l, flush=True)\n",
        encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(p)


grok_lines = [
    json.dumps({"type": "text", "data": "Em lưu bằng hàm của app "}),
    json.dumps({"type": "text", "data": "thay cho API cần đăng nhập."}),
    json.dumps({"type": "tool_call", "id": "t1", "name": "bash", "input": {"command": "ls"}}),
    json.dumps({"type": "tool_call_update", "id": "t1", "status": "completed", "output": "ok"}),
    json.dumps({"type": "text", "data": "Xong mục 3. "}),
    json.dumps({"type": "text", "data": "Giờ em đọc file vai."}),
]
g = grok_cli.GrokCLI(cwd="/tmp")
g.cli_path = fake_binary("javis-fakegrok-", "grok", grok_lines)


async def _grok():
    return [e async for e in g.query("x")]


evs = run(_grok())
live = "".join(e["content"] for e in evs if e["type"] == "delta")
final = next((e for e in evs if e["type"] == "final"), {}).get("content", "")
check("Grok: the live preview has a paragraph after the tool call", live == BEFORE + "\n\n" + AFTER, live)
check("Grok: the final text has the same paragraph", final == BEFORE + "\n\n" + AFTER, final)
check("Grok: pieces of one stretch are not broken up", "của app thay cho API" in final, final)


# ---- 4. Antigravity: the same ----
import antigravity_cli  # noqa: E402

HELP = ("Usage: agy [options]\n"
        "  -p, --print, --prompt   Run once and exit. Appended to input on stdin\n"
        "  --output-format <fmt>   text | json | stream-json\n"
        "  --model <slug>          Model to use\n"
        "  --dangerously-skip-permissions  Auto-approve tool calls\n")
agy_lines = [
    json.dumps({"type": "init", "conversation_id": "abc-123"}),
    json.dumps({"role": "assistant", "content": "Em lưu bằng hàm của app "}),
    json.dumps({"role": "assistant", "content": "thay cho API cần đăng nhập."}),
    json.dumps({"type": "tool_use", "tool_name": "run_command", "tool_id": "t1", "parameters": {"CommandLine": "ls"}}),
    json.dumps({"type": "tool_result", "tool_id": "t1", "status": "success", "output": "ok"}),
    json.dumps({"role": "assistant", "content": "Xong mục 3. "}),
    json.dumps({"role": "assistant", "content": "Giờ em đọc file vai."}),
    json.dumps({"type": "result", "status": "success", "stats": {"input_tokens": 10, "output_tokens": 5}}),
]
agy = fake_binary("javis-fakeagy-", "agy", agy_lines, HELP)
antigravity_cli._HELP_CACHE.update(path=None, text="", ts=0.0)
antigravity_cli._AUTH_CACHE.update(ts=0.0, val=None)
antigravity_cli.find_antigravity_cli = lambda: agy
a = antigravity_cli.AntigravityCLI(cwd="/tmp")
a.cli_path = agy
a.mode = "full"


async def _agy():
    return [e async for e in a.query("x")]


evs = run(_agy())
live = "".join(e["content"] for e in evs if e["type"] == "delta")
final = next((e for e in evs if e["type"] == "final"), {}).get("content", "")
check("Antigravity: the live preview has a paragraph after the tool call", live == BEFORE + "\n\n" + AFTER, live)
check("Antigravity: the final text has the same paragraph", final == BEFORE + "\n\n" + AFTER, final)

print()
if fails:
    print(f"FAIL: {len(fails)} check(s)")
    sys.exit(1)
print("All checks passed.")
