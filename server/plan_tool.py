"""`javis_plan`: a task checklist for the API brains, drawn as the plan card in the chat.

Owner, 08/11/2026: Claude Code (TodoWrite), Codex (update_plan) and Grok Build (todo_write) keep a checklist for a long
job and the chat shows it as a "Plan 2/5" card (turn_plan.py, chat-steps.js). The seven API brains (OpenRouter, OpenAI,
Anthropic API, Gemini, Groq, DeepSeek, Ollama) had no such tool, so the card never showed for them. This is that tool.

It does nothing but answer "saved": the list reaches the dashboard through the `tool_call` event the engine already
sends (turn_plan reads `javis_plan` like TodoWrite). Cost: the name, description and schema are 545 characters, about
180-200 tokens per request at the 3 characters per token Javis estimates with (cached by most providers), plus one short
tool round each time the model updates the list, which it is told to do only for jobs of three steps or more. The
owner can switch it off in the composer "+" menu (`settings.chat.plan_tool`).

Only the OWNER's chat turns get it (main._api_stream_mcp): a customer bot or a background job has no chat to draw in.
"""
from __future__ import annotations

NAME = "javis_plan"
MAX_ITEMS = 30
STATUSES = ("pending", "in_progress", "completed")

# Text for the MODEL (not translated with the interface language, like every tool description).
DESCRIPTION = ("Danh sách việc cho một việc từ 3 bước trở lên; người dùng thấy nó thành thẻ tiến độ trong khung chat. "
               "Gửi CẢ danh sách mỗi lần: một lần lúc bắt đầu, rồi mỗi khi một mục bắt đầu hay xong. Đúng một mục "
               "in_progress. Câu hỏi thường và việc một bước thì KHÔNG dùng.")

SCHEMA = {
    "type": "object",
    "properties": {
        "todos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "status": {"type": "string", "enum": list(STATUSES)},
                },
                "required": ["content", "status"],
            },
        },
    },
    "required": ["todos"],
}


def enabled(cfg) -> bool:
    """On unless the owner switched it off (`settings.chat.plan_tool = false`)."""
    return ((cfg or {}).get("chat") or {}).get("plan_tool", True) is not False


def check(args) -> str:
    """The tool's answer: a short "saved" line, or what is wrong with the list so the model can resend it."""
    todos = (args or {}).get("todos") if isinstance(args, dict) else None
    if not isinstance(todos, list) or not todos:
        return "ERROR: todos phải là một danh sách có ít nhất một mục {content, status}."
    if len(todos) > MAX_ITEMS:
        return f"ERROR: tối đa {MAX_ITEMS} mục; gộp các bước nhỏ lại."
    done = active = 0
    for i, t in enumerate(todos, 1):
        if not isinstance(t, dict) or not str(t.get("content") or "").strip():
            return f"ERROR: mục {i} thiếu content."
        st = str(t.get("status") or "")
        if st not in STATUSES:
            return f"ERROR: mục {i} có status '{st}', chỉ nhận pending, in_progress, completed."
        done += st == "completed"
        active += st == "in_progress"
    if active > 1:
        return "ERROR: chỉ một mục được in_progress cùng lúc."
    if done == len(todos):
        return f"OK: xong cả {done}/{len(todos)} mục."
    return f"OK: đã lưu, xong {done}/{len(todos)}. Làm tiếp; xong mục nào thì gửi lại cả danh sách."


async def _call(args):
    return check(args)


def add_to(tools: list, route: dict) -> None:
    """Append the tool to an API engine's (tools, route) from mcp_hub.discover_all. No-op when already there."""
    if NAME in route:
        return
    tools.append({"fn": NAME, "server": "javis", "name": NAME, "description": DESCRIPTION, "schema": SCHEMA})
    route[NAME] = {"call": _call, "source_type": "builtin", "source_id": "javis-core", "effect": "none",
                   "required_mode": "readonly", "health": "healthy"}
