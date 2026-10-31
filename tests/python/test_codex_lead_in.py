"""A Codex lead-in ("Let me check the class list.") never reaches the answer a customer gets (0.429.1).

    python tests/python/test_codex_lead_in.py      (no network, fake Codex)

LDA report 31/10/2026: a Messenger bot on Codex sent "Em tra danh sách lớp hiện có để xác nhận ạ." before its real answer.
Codex sends a lead-in as its own agent message (measured on Codex 0.160 `exec --json`: one message, a command, then the
answer), and both readers joined every message of the turn into `final`, which channels send as the reply. The
app-server reader is pinned in test_codex_steer_0213.py.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import sys
import tempfile

from claude_cli import CODEX_LEAD_IN_MAX, CodexCLI, codex_answer_text

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  [{detail!r}]"))
    if not cond:
        _fails.append(name)


LEAD = "Em tra danh sách lớp hiện có để xác nhận ạ."
ANSWER = "Dạ, Trung tâm có lớp Báo bài 2A ạ. Mình cần hỗ trợ con môn nào ạ?"

# ---- 1. The rule ----
check("phase commentary is left out, final_answer kept",
      codex_answer_text([{"text": LEAD, "phase": "commentary"}, {"text": ANSWER, "phase": "final_answer"}]) == ANSWER)
check("no phase: a short message before a step is a lead-in",
      codex_answer_text([{"text": LEAD, "before_step": True}, {"text": ANSWER}]) == ANSWER)
check("several steps, several lead-ins: only the answer",
      codex_answer_text([{"text": LEAD, "before_step": True}, {"text": "Em xem lịch học tiếp ạ.", "before_step": True},
                         {"text": ANSWER}]) == ANSWER)
check("a clarifying question with no step after it is kept",
      codex_answer_text([{"text": "Mình cho em xin tên của con được không ạ?"}]) == "Mình cho em xin tên của con được không ạ?")
check("a stated limit after a failed step is kept",
      codex_answer_text([{"text": LEAD, "before_step": True},
                         {"text": "Em chưa kiểm tra được vì nguồn dữ liệu đang lỗi ạ."}])
      == "Em chưa kiểm tra được vì nguồn dữ liệu đang lỗi ạ.")
long_text = "Bảng giá các lớp: " + "lớp 2A 500 nghìn, " * 30
check("a long message before a step is content, not a lead-in", len(long_text) > CODEX_LEAD_IN_MAX
      and codex_answer_text([{"text": long_text, "before_step": True}, {"text": "Đã lưu."}]) == long_text + "\nĐã lưu.")
check("final_answer before a step stays (phase wins over position)",
      codex_answer_text([{"text": "Có ạ.", "phase": "final_answer", "before_step": True}]) == "Có ạ.")
check("only lead-ins in the turn: kept rather than an empty reply",
      codex_answer_text([{"text": LEAD, "phase": "commentary"}]) == LEAD)
check("a turn without messages stays empty", codex_answer_text([]) == "")

# ---- 2. `codex exec --json` reader: the shape measured on Codex 0.160 ----
events = [
    {"type": "thread.started", "thread_id": "t1"},
    {"type": "item.completed", "item": {"id": "item_0", "type": "agent_message", "text": LEAD}},
    {"type": "item.started", "item": {"id": "item_1", "type": "command_execution", "command": "ls", "status": "in_progress"}},
    {"type": "item.completed", "item": {"id": "item_1", "type": "command_execution", "command": "ls", "status": "completed"}},
    {"type": "item.completed", "item": {"id": "item_2", "type": "agent_message", "text": ANSWER}},
    {"type": "turn.completed", "usage": {}},
]
script = "import json\n" + "".join(f"print(json.dumps({e!r}), flush=True)\n" for e in events)
cli = CodexCLI(cwd=tempfile.gettempdir())
cli.cli_path = sys.executable
cli._build_args = lambda: [sys.executable, "-c", script]


async def _collect():
    return [e async for e in cli.query("x")]


evs = asyncio.run(_collect())
final = next((e for e in evs if e["type"] == "final"), {})
shown = [e["content"] for e in evs if e["type"] == "text"]
check("exec: the customer answer has no lead-in", final.get("content") == ANSWER, final.get("content"))
check("exec: the lead-in is still shown live (owner's chat, progress)", LEAD in shown and ANSWER in shown, shown)

print()
if _fails:
    print(f"FAIL - {len(_fails)} check(s) failed")
    sys.exit(1)
print("ALL PASS")
