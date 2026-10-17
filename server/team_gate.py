"""Tool gate of a Team Work/Help step (0.207.0): outside actions wait for the owner's approval BEFORE they run.

A team runs at one of two levels (`teams.work_mode`, the owner's switch on the team settings):

- `gated` (default, every team created before 0.207.0 too): the step works freely inside its scope (read, write files in
  the brain and the team folder, read connections); an outside action (a hub tool classed `danger`: send, post, pay,
  order, delete; a plugin tool needing `full`; a shell command outside the read-only list; a Claude account connector
  that is not a read) is refused before it runs unless the owner approved that exact call for this step.
- `full`: the owner lets the team act without asking. Nothing here runs, the step gets the private chat's `full` level.

One gate per tool step, open while the engine runs. The host binds its id into the turn (`turn_context`, key
`team_gate`), so the hub finds it from the turn key a CLI engine sends (`X-Javis-Turn`) or from the ContextVar of an
in-process engine; the Claude engine also gets it directly for its PreToolUse hook. A refused call is recorded (tool,
exact arguments, fingerprint) and becomes the step's approval request: data the host saw, not the model's words.

Fail closed: the hub level of a gated step is `gated`, which caps like `auto` (mcp_catalog). A call that reaches the hub
without a live gate (missing or forged turn key) is simply refused like at `auto`; it never runs at `full`.

What each provider can enforce (`provider_support`): Claude (PreToolUse hook + hub), Codex (own sandbox
`workspace-write`, no network, + hub with the turn key), API engines (every tool goes through the hub in-process). Grok
Build denies its shell at `auto` but cannot carry the turn key to the hub (its MCP entry is a shared file per brain), so a
gated step on Grok works inside scope only and an approved outside action cannot run there. Antigravity has no way to
stop its own tools before they run at that level: a gated tool step on it is refused with an explanation.
"""
from __future__ import annotations

import os
import secrets
import shlex
import threading
from pathlib import Path
from typing import Any, Optional

import team_approval
import turn_context

GATED = "gated"
FULL = "full"
HUB_MODE = "gated"          # X-Javis-Mode of a gated step: lists like full, caps like auto, the gate decides the rest
MAX_BLOCKED = 5             # recorded refusals per step (an approval card lists at most this many actions)

# Claude Code native tools a gated step may use without asking: reading, searching, writing files inside the step's
# folders (checked below), planning and sub-agents (their own tool calls go through this same hook).
NATIVE_FREE = frozenset({"Read", "Glob", "Grep", "LS", "NotebookRead", "TodoWrite", "TodoRead", "WebSearch", "WebFetch",
                         "Task", "Agent", "BashOutput", "KillShell", "KillBash", "ExitPlanMode", "ToolSearch",
                         "ListMcpResourcesTool", "ReadMcpResourceTool"})
NATIVE_WRITE = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
# Shell programs that only read. Narrower than run_command's `auto` list on purpose: python, node, npm and make run any
# code, which can reach the network, so in a gated team they are outside actions.
BASH_READ = frozenset({"ls", "cat", "head", "tail", "wc", "find", "grep", "rg", "file", "stat", "du", "tree", "diff",
                       "pwd", "date", "which", "basename", "dirname", "realpath", "sort", "uniq", "cut", "jq"})
_GIT_READ = frozenset({"status", "diff", "log", "show", "ls-files", "rev-parse", "describe", "blame", "shortlog"})
_FIND_ACT = frozenset({"-exec", "-execdir", "-delete", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf", "-fls"})
_SHELL_CHARS = set(">|&;<`$\n")
_READ_VERBS = ("get", "list", "search", "read", "fetch", "query", "find", "describe", "lookup", "view", "count",
               "download", "export", "suggest")

BLOCK_NOTE = ("ERROR: Hành động này ra ngoài phạm vi nên cần chủ nhóm duyệt trước (nhóm đang ở quyền 'cần duyệt'). "
              "Javis đã ghi lại ĐÚNG lời gọi này thành yêu cầu duyệt, chưa có gì được thực hiện. Đừng tìm cách khác để làm "
              "cùng việc. Làm xong phần trong phạm vi rồi kết thúc bước, nêu ngắn gọn vì sao cần hành động này.")
NO_GATE_NOTE = ("ERROR: Hành động ra ngoài của nhóm cần chủ nhóm duyệt, mà lời gọi này không gắn với bước nào đang mở nên "
                "Javis không ghi được yêu cầu. Chưa có gì được thực hiện.")


class Gate:
    __slots__ = ("gate_id", "team_id", "task_id", "step_id", "store", "roots", "blocked", "passed", "lock")

    def __init__(self, store, team_id: str, task_id: str, step_id: str):
        self.gate_id = "tg_" + secrets.token_hex(8)
        self.team_id, self.task_id, self.step_id = team_id, task_id, step_id
        self.store = store
        self.roots: list = []
        self.blocked: list = []
        self.passed: list = []
        self.lock = threading.Lock()


_GATES: dict = {}
_LOCK = threading.Lock()


def open_gate(store, team_id: str, task_id: str, step_id: str) -> Gate:
    g = Gate(store, team_id, task_id or "", step_id or "")
    with _LOCK:
        _GATES[g.gate_id] = g
    return g


def set_roots(gate_id: str, roots: list) -> None:
    """Folders a gated step may write natively (the team folder, the brain). Set by the host that built the engine."""
    g = get(gate_id)
    if g is not None:
        out = []
        for r in roots or []:
            if r:
                try:
                    out.append(str(Path(r).expanduser().resolve()))
                except Exception:  # noqa: BLE001
                    continue
        g.roots = out


def close_gate(gate_id: str) -> dict:
    with _LOCK:
        g = _GATES.pop(gate_id, None)
    if g is None:
        return {"blocked": [], "passed": []}
    with g.lock:
        return {"blocked": list(g.blocked), "passed": list(g.passed)}


def get(gate_id: Optional[str]) -> Optional[Gate]:
    if not gate_id:
        return None
    with _LOCK:
        return _GATES.get(gate_id)


def current() -> Optional[Gate]:
    """The gate of the turn this call belongs to, or None (no turn, not a team step, or the turn key was not sent)."""
    t = turn_context.current()
    return get((t or {}).get("team_gate"))


def _trim(args: Any) -> Any:
    if isinstance(args, dict):
        return {str(k)[:80]: (v if isinstance(v, (int, float, bool)) or v is None else str(v)[:600])
                for k, v in list(args.items())[:20]}
    return str(args)[:600]


def decide(g: Gate, kind: str, name: str, args: Any, label: str) -> tuple:
    """(True, "") when the owner approved this exact call for this step (the approval's fingerprint is consumed now, so
    the effect can never happen twice), else (False, note) and the call is recorded for the approval card."""
    fp = team_approval.fingerprint(kind, name, args)
    aid = g.store.consume_fingerprint(g.step_id, fp) if (g.store is not None and g.step_id) else None
    with g.lock:
        if aid:
            g.passed.append({"fp": fp, "approval_id": aid, "kind": kind, "name": name})
            return True, ""
        if not any(b["fp"] == fp for b in g.blocked) and len(g.blocked) < MAX_BLOCKED:
            g.blocked.append({"fp": fp, "kind": kind, "name": str(name)[:120], "args": _trim(args),
                              "label": str(label or name)[:300]})
    return False, BLOCK_NOTE


def hub_check(name: str, args: Any, label: str = "") -> tuple:
    """For the hub and plugin host, on a call the `gated` level refuses but `full` would allow."""
    g = current()
    if g is None:
        return False, NO_GATE_NOTE
    return decide(g, "hub", name, args, label or name)


# ---- Claude native tools (PreToolUse hook) ----

def bash_readonly(command: str) -> bool:
    cmd = str(command or "").strip()
    if not cmd or any(ch in _SHELL_CHARS for ch in cmd):
        return False
    try:
        argv = shlex.split(cmd)
    except ValueError:
        return False
    if not argv:
        return False
    prog = os.path.basename(argv[0]).lower()
    if prog not in BASH_READ and prog != "git":
        return False
    if prog == "git":
        return len(argv) > 1 and argv[1].lower() in _GIT_READ
    if prog == "find" and any(a in _FIND_ACT for a in argv[1:]):
        return False
    return True


def _inside(path: str, roots: list) -> bool:
    if not path or not roots:
        return False
    try:
        p = Path(path).expanduser().resolve()
    except Exception:  # noqa: BLE001
        return False
    for r in roots:
        try:
            p.relative_to(r)
            return True
        except ValueError:
            continue
    return False


def _native_args(tool: str, inp: dict) -> Any:
    """What makes two native calls the same action. Bash: the command alone (the description wording varies)."""
    if tool == "Bash":
        return {"command": str((inp or {}).get("command") or "")}
    return {k: v for k, v in (inp or {}).items() if k not in ("description",)}


def classify_native(tool: str, inp: dict, roots: list) -> str:
    """'free' (runs) or 'outside' (needs approval)."""
    name = str(tool or "")
    if name.startswith("mcp__javis__") or name.startswith("mcp__javis-plugins__"):
        return "free"           # the hub and the plugin host apply the gate themselves
    if name in NATIVE_FREE:
        return "free"
    if name in NATIVE_WRITE:
        path = (inp or {}).get("file_path") or (inp or {}).get("notebook_path") or ""
        return "free" if _inside(str(path), roots) else "outside"
    if name == "Bash":
        return "free" if bash_readonly((inp or {}).get("command")) else "outside"
    if name.startswith("mcp__"):
        last = name.rsplit("__", 1)[-1].lower()
        return "free" if last.startswith(_READ_VERBS) else "outside"
    return "outside"


def native_check(gate_id: Optional[str], tool: str, inp: dict) -> tuple:
    g = get(gate_id)
    if g is None:
        return False, NO_GATE_NOTE
    if classify_native(tool, inp, g.roots) == "free":
        return True, ""
    args = _native_args(tool, inp)
    label = f"{tool}: {args.get('command') if tool == 'Bash' else (inp or {}).get('file_path') or ''}".strip(": ")
    return decide(g, "native", tool, args, label)


# ---- providers ----

# Same ids as aux_engine (kept literal so this module imports nothing heavy).
CLAUDE = "anthropic-cli"
CODEX = "openai-oauth"
GROK = "grok-cli"
ANTIGRAVITY = "antigravity-cli"


def provider_support(provider: str, *, codex_sandbox: Optional[str] = "workspace-write", grok_deny: bool = True,
                     api_providers: tuple = ()) -> dict:
    """{"ok": can run a gated tool step, "approved_actions": an approved outside action can run on it, "reason": ...}."""
    p = str(provider or CLAUDE)
    if p == CLAUDE:
        return {"ok": True, "approved_actions": True, "reason": ""}
    if p == CODEX:
        if codex_sandbox != "workspace-write":
            return {"ok": False, "approved_actions": False,
                    "reason": ("Codex đang chạy không có sandbox riêng (JAVIS_CODEX_SANDBOX=off) nên Javis không chặn "
                               "được lệnh máy của nó trước khi chạy")}
        return {"ok": True, "approved_actions": True, "reason": ""}
    if p in api_providers:
        return {"ok": True, "approved_actions": True, "reason": ""}
    if p == GROK:
        if not grok_deny:
            return {"ok": False, "approved_actions": False,
                    "reason": "bản Grok Build đang cài không có cờ --deny nên Javis không chặn được lệnh máy của nó"}
        return {"ok": True, "approved_actions": False,
                "reason": "Grok Build không mang được khoá lượt tới MCP Hub nên hành động đã duyệt không chạy được trên nó"}
    if p == ANTIGRAVITY:
        return {"ok": False, "approved_actions": False,
                "reason": "Antigravity CLI không có cách chặn công cụ của chính nó trước khi chạy ở mức này"}
    return {"ok": False, "approved_actions": False, "reason": f"{p} chưa được kiểm là chặn được công cụ trước khi chạy"}


def unsupported_text(reason: str) -> str:
    return (f"Nhóm đang ở quyền 'cần duyệt' mà {reason}. Đổi trợ lý làm bước này sang Claude, Codex hay một model API, "
            "hoặc bật 'Nhóm tự làm hành động ra ngoài' trong cài đặt nhóm nếu anh tin nhóm này.")
