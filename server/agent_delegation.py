"""Let an agent running a workflow step ask one colleague agent for help mid-task.

The owner asked (2026-10-14) for agents to hand a sub-question to the colleague whose skills fit,
get the answer back and carry on, instead of only following hand-off paths drawn in advance.

The guards live here in code, not in the prompt:

- Who may ask whom is declared by the owner in the agent file (`can_ask: [slug, ...]`). An agent
  without that list never gets the tool's ticket, so it cannot ask anyone.
- The caller is identified by a random ticket written into its own system prompt, not by an
  argument the model fills in. A model can only spend its own ticket, so it cannot pose as a
  colleague with a wider list.
- One level only: the colleague's prompt is built without a ticket, and while a colleague is
  answering, the caller's ticket is busy, so even a colleague that was handed the ticket string
  cannot ask onward. This is what stops two agents bouncing a job back and forth.
- The ticket is revoked when its step ends (revoke_in), so a ticket string that leaks into a
  step's output cannot be spent later by another run.
- At most MAX_ASKS per ticket (one ticket per step run, retries included).
- The colleague runs through the SAME engine factory as the caller (same tool allowlist and the
  same permission level), so asking never lifts a level.
"""
from __future__ import annotations

import asyncio
import re
import sys
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

TOOL_NAME = "javis_ask_agent"
MAX_ASKS = 3
# A colleague's answer is one more model turn inside the caller's tool call; keep it well under
# the background wall clock so the caller still has time to finish its own step.
ASK_TIMEOUT_S = 600
TICKET_TTL_S = 3 * 3600
ANSWER_MAX_CHARS = 12000

_TICKET_RE = re.compile(r"\bask_ticket=(ak_[A-Za-z0-9_-]{16,64})\b")


@dataclass
class _Ticket:
    caller: str
    caller_name: str
    targets: dict              # slug -> display name, only colleagues whose file exists
    run_agent: Callable        # async (target_slug, prompt) -> (answer, error)
    created: float = field(default_factory=time.time)
    used: int = 0
    busy: bool = False


_lock = threading.Lock()
_tickets: dict[str, _Ticket] = {}


def _prune(now: float) -> None:
    for key in [k for k, t in _tickets.items() if now - t.created > TICKET_TTL_S]:
        _tickets.pop(key, None)


def declared_targets(meta: dict) -> list[str]:
    """Slugs listed under `can_ask` in an agent's frontmatter, cleaned and de-duplicated."""
    raw = (meta or {}).get("can_ask") or []
    if isinstance(raw, str):
        raw = [x for x in re.split(r"[,\s]+", raw) if x]
    out = []
    for item in raw if isinstance(raw, (list, tuple)) else []:
        slug = str(item or "").strip()
        if slug and slug not in out:
            out.append(slug)
    return out


def issue(caller: str, caller_name: str, targets: dict, run_agent: Callable) -> str:
    """Register a ticket for one step run and return the prompt block that carries it.

    Empty string when there is nobody to ask (no `can_ask`, or none of the slugs exist)."""
    targets = {k: v for k, v in (targets or {}).items() if k and k != caller}
    if not targets:
        return ""
    ticket = "ak_" + secrets.token_urlsafe(18)
    now = time.time()
    with _lock:
        _prune(now)
        _tickets[ticket] = _Ticket(caller, caller_name or caller, dict(targets), run_agent, now)
    who = "\n".join(f"- `{slug}`: {name}" for slug, name in targets.items())
    return (
        "\n# Nhờ đồng nghiệp\n"
        f"Khi một phần việc nằm ngoài chuyên môn của bạn, gọi tool `{TOOL_NAME}` để nhờ đúng "
        "người dưới đây làm phần đó, nhận câu trả lời rồi làm tiếp việc của bạn. Chỉ nhờ khi thật "
        f"cần, tối đa {MAX_ASKS} lần cho việc này. Viết `task` đủ rõ để người được nhờ làm được "
        "mà không cần hỏi lại (dán kèm số liệu, tên tour, ngày...). Người được nhờ không nhờ "
        "tiếp được ai.\n"
        f"Người bạn được nhờ:\n{who}\n"
        f"Luôn truyền `ticket` đúng chuỗi này: ask_ticket={ticket}\n"
    )


def ticket_in(text: str) -> bool:
    """True when a system prompt carries a delegation ticket (the engine must then grant the tool)."""
    return bool(_TICKET_RE.search(text or ""))


def revoke_in(text: str) -> None:
    """Drop the ticket a system prompt carries. Called when the step that owns it ends."""
    for key in _TICKET_RE.findall(text or ""):
        with _lock:
            _tickets.pop(key, None)


def _trace(caller: str, target: str, outcome: str) -> None:
    print(f"[agent ask] {caller} -> {target or '?'}: {outcome}", file=sys.stderr)


def _parse_ticket(value: Any) -> str:
    value = str(value or "").strip()
    m = _TICKET_RE.search(value) or _TICKET_RE.search(f"ask_ticket={value}")
    return m.group(1) if m else ""


async def ask(ticket: Any, target: Any, task: Any) -> str:
    """Run the colleague and return its answer, or a plain ERROR line the caller can act on."""
    key = _parse_ticket(ticket)
    target = str(target or "").strip()
    task = str(task or "").strip()
    with _lock:
        _prune(time.time())
        entry = _tickets.get(key) if key else None
        if entry is None:
            return ("ERROR: ticket không hợp lệ hoặc đã hết hạn. Chỉ agent đang chạy một bước "
                    "quy trình, có khai người được nhờ, mới nhờ được đồng nghiệp.")
        if not task:
            return "ERROR: thiếu `task`: viết rõ việc cần đồng nghiệp làm."
        if target not in entry.targets:
            allowed = ", ".join(entry.targets) or "(không ai)"
            return f"ERROR: bạn không được nhờ '{target}'. Người được nhờ: {allowed}."
        if entry.busy:
            _trace(entry.caller, target, "refused: ticket busy (nested or parallel ask)")
            return ("ERROR: đang có một đồng nghiệp làm việc theo vé này. Không nhờ lồng và không "
                    "nhờ song song; chờ kết quả rồi mới nhờ tiếp.")
        if entry.used >= MAX_ASKS:
            _trace(entry.caller, target, "refused: ask cap reached")
            return (f"ERROR: đã nhờ đủ {MAX_ASKS} lần cho việc này. Làm tiếp bằng thông tin đang "
                    "có và ghi rõ phần còn thiếu trong kết quả.")
        entry.used += 1
        entry.busy = True
        caller = entry.caller
        run_agent = entry.run_agent
        caller_name = entry.caller_name
        target_name = entry.targets[target]
    prompt = (f"[{caller_name} nhờ bạn làm phần việc dưới đây. Trả kết quả gọn, đúng phần được "
              f"nhờ; bạn không nhờ tiếp được ai.]\n\n{task}")
    try:
        answer, error = await asyncio.wait_for(run_agent(target, prompt), ASK_TIMEOUT_S)
    except asyncio.TimeoutError:
        _trace(caller, target, "timeout")
        return f"ERROR: {target_name} chưa trả lời sau {int(ASK_TIMEOUT_S) // 60} phút."
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller as a tool result
        _trace(caller, target, f"error {type(exc).__name__}")
        return f"ERROR: chạy {target_name} lỗi: {type(exc).__name__}: {exc}"
    finally:
        with _lock:
            entry.busy = False
    if error and not answer:
        _trace(caller, target, "engine error")
        return f"ERROR: {target_name} không trả lời được: {error}"
    _trace(caller, target, "answered")
    answer = (answer or "").strip()
    if len(answer) > ANSWER_MAX_CHARS:
        answer = answer[:ANSWER_MAX_CHARS] + "\n...(đã cắt bớt)"
    return f"Kết quả từ {target_name}:\n{answer or '(trả lời rỗng)'}"


def reset_for_tests() -> None:
    with _lock:
        _tickets.clear()
